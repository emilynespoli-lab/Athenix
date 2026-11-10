import json
import time
from collections import Counter
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select, update

from . import llm
from .db import (
    Artifact,
    AuditHead,
    CallClaim,
    Decision,
    DependencyLink,
    Document,
    Extraction,
    Finding,
    Interpretation,
    ModelResponse,
    Run,
    audit,
    digest,
    now,
    uid,
)
from .proposals import assert_reviewable, evaluate, rule_candidates, validate_item
from .structure import detect_media, extract
from .evidence import verify

ROLES = {"norm", "compiled", "clarification", "auxiliary"}


def extraction_data(session, document_id):
    item = session.scalar(select(Extraction).where(Extraction.document_id == document_id))
    if not item:
        raise ValueError("Documento ainda não estruturado.")
    result = json.loads(json.dumps(item.data)) | {"text": item.text, "text_hash": item.text_hash}
    associations = list(
        session.scalars(
            select(DependencyLink)
            .where(DependencyLink.document_id == document_id)
            .order_by(DependencyLink.created)
        )
    )
    for association in associations:
        for link in result["links"]:
            if link["id"] == association.link_id:
                processed = session.scalar(
                    select(Run.id)
                    .where(
                        Run.document_id == association.target_id,
                        Run.kind.in_(["rules", "ai", "replay"]),
                        Run.state == "completed",
                    )
                    .limit(1)
                )
                target = session.get(Document, association.target_id)
                link.update(
                    state="interpreted" if processed else "obtained",
                    target_id=association.target_id,
                    target_hash=target.artifact_id,
                    association_reason=association.reason,
                )
    return result


def associate_dependency(session, document_id, link_id, target_id, reason, actor):
    if not reason.strip() or target_id == document_id or not session.get(Document, target_id):
        raise ValueError("Escolha outro documento existente e justifique a associação.")
    extraction = extraction_data(session, document_id)
    if link_id not in {link["id"] for link in extraction["links"]}:
        raise ValueError("Link inventariado não encontrado.")
    association = DependencyLink(
        document_id=document_id,
        target_id=target_id,
        link_id=link_id,
        reason=reason.strip(),
        user_id=actor.id,
    )
    session.add(association)
    session.flush()
    audit(
        session,
        actor.id,
        "dependency.associated",
        association.id,
        {"document_id": document_id, "target_id": target_id, "link_id": link_id, "reason": reason},
    )
    return association


def propose_finding(session, interpretation_id, actor, kind, quote, unit_id, explanation):
    session.execute(update(AuditHead).values(revision=AuditHead.revision + 1))
    item = session.get(Interpretation, interpretation_id)
    if not item or not explanation.strip():
        raise ValueError("Interpretação e justificativa são obrigatórias.")
    allowed = {
        "unsupported_modality",
        "unsupported_duty",
        "subject_mismatch",
        "ignored_exception",
        "omitted_condition",
        "clarification_only",
        "unavailable_dependency",
        "grouped_actions",
        "incorrect_period",
        "wrong_landmark",
    }
    if kind not in allowed:
        raise ValueError("Tipo de contestação desconhecido.")
    extracted = extraction_data(session, item.document_id)
    anchor = verify(quote, unit_id, extracted["units"], extracted["text_hash"])
    if anchor["state"] != "verified":
        raise ValueError("Contestação exige trecho literal verificável na unidade declarada.")
    document = session.get(Document, item.document_id)
    reevaluated = evaluate(item.data, extracted, document.role)
    agreeing = [
        o
        for o in reevaluated["objections"]
        if o["kind"] == kind and o["evidence"]["unit_id"] == unit_id
    ]
    data = {
        "kind": kind,
        "state": "confirmed"
        if any(o["state"] == "confirmed" for o in agreeing)
        else "inconclusive",
        "severity": "high",
        "evidence": anchor,
        "explanation": explanation.strip(),
        "source": "human_proposal",
    }
    finding = Finding(interpretation_id=item.id, user_id=actor.id, data=data)
    session.add(finding)
    session.flush()
    audit(
        session,
        actor.id,
        "finding.proposed",
        finding.id,
        {"interpretation_id": item.id, "kind": kind, "state": data["state"]},
    )
    return finding


def receive(
    session, settings, content, title, origin, role, url, actor, related_id=None, synthetic=False
):
    if not origin.strip():
        raise ValueError("Declare a origem do documento.")
    if role not in ROLES:
        raise ValueError("Papel documental inválido.")
    media = detect_media(content, settings.max_bytes)
    hashed = digest(content)
    # Serialize ingest with audit head; uniqueness remains the final database guard.
    session.execute(update(AuditHead).values(revision=AuditHead.revision + 1))
    existing = session.scalar(select(Document).where(Document.artifact_id == hashed))
    if existing:
        return existing, True
    if related_id and not session.get(Document, related_id):
        raise ValueError("Norma vinculada não encontrada.")
    session.add(Artifact(id=hashed, content=content, media=media, size=len(content)))
    session.flush()
    document = Document(
        title=(title.strip() or "Documento sem título")[:250],
        origin=origin.strip(),
        role=role,
        source_url=url.strip(),
        artifact_id=hashed,
        related_id=related_id or None,
        synthetic=synthetic,
    )
    session.add(document)
    session.flush()
    audit(
        session,
        actor,
        "document.received",
        document.id,
        {"sha256": hashed, "origin": origin, "synthetic": synthetic},
    )
    session.add(
        Run(
            document_id=document.id,
            key=digest(["structure-v1", hashed]),
            kind="structure",
            parameters={},
        )
    )
    return document, False


def enqueue(
    session,
    document_id,
    kind,
    actor,
    settings,
    scope=None,
    budget="0",
    response_id=None,
    fresh=False,
):
    if kind not in {"rules", "ai", "replay"}:
        raise ValueError("Estratégia inválida.")
    document = session.get(Document, document_id)
    if not document:
        raise ValueError("Documento não encontrado.")
    extraction = extraction_data(session, document_id)
    scope = sorted(set(scope or [u["id"] for u in extraction["units"]]))
    if set(scope) - {u["id"] for u in extraction["units"]}:
        raise ValueError("Escopo contém unidade inexistente.")
    parameters = {"scope": scope}
    if kind == "ai":
        estimated = llm.estimate(extraction, settings, scope)
        parameters["estimate"] = estimated
        if estimated["batches"] and not estimated["configured"]:
            raise ValueError(
                "Configure credencial, modelo e preço com fonte/data antes de executar IA."
            )
        try:
            limit = Decimal(budget)
            reservation = Decimal(estimated["max_cost_usd"] or "0")
            if not limit.is_finite() or limit < 0 or reservation > limit:
                raise ValueError("Teto insuficiente para a reserva conservadora exibida.")
        except InvalidOperation as error:
            raise ValueError("Orçamento inválido.") from error
        parameters["budget_usd"] = str(limit)
        parameters["reserved_usd"] = str(reservation)
        parameters["model"] = settings.model
    elif kind == "replay":
        response = session.get(ModelResponse, response_id)
        if not response or session.get(Run, response.run_id).document_id != document_id:
            raise ValueError("Resposta não pertence a este documento.")
        parameters["response_id"] = response_id
    identity = {
        k: v for k, v in parameters.items() if k not in {"estimate", "budget_usd", "reserved_usd"}
    }
    key = digest(
        [
            document_id,
            extraction["text_hash"],
            digest(extraction["links"]),
            kind,
            identity,
            digest(llm.PROMPT.encode()),
            llm.PROMPT_VERSION,
            uid() if fresh else "stable",
        ]
    )
    # One serial gate covers same-key creation and daily cost reservation.
    from .db import AuditHead

    session.execute(update(AuditHead).values(revision=AuditHead.revision + 1))
    existing = session.scalar(select(Run).where(Run.key == key))
    if existing:
        return existing, True
    if kind == "ai":
        from datetime import datetime
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
        total = Decimal("0")
        for previous in session.scalars(select(Run).where(Run.kind == "ai")):
            if previous.parameters.get("budget_date") == today:
                total += Decimal(previous.parameters.get("reserved_usd", "0"))
        # Conservative: reservations are not released automatically after ambiguous failures.
        if total + Decimal(parameters["reserved_usd"]) > Decimal("5"):
            raise ValueError("Teto diário local de US$ 5 alcançado pelas reservas.")
        parameters["budget_date"] = today
    run = Run(document_id=document_id, kind=kind, key=key, parameters=parameters)
    session.add(run)
    session.flush()
    audit(session, actor, "run.queued", run.id, {"kind": kind, "parameters": parameters})
    return run, False


def save_candidates(session, run, items, extraction, generator, allowed=None, batch_key="default"):
    document = session.get(Document, run.document_id)
    target_dates = None
    if document.related_id:
        try:
            target_dates = extraction_data(session, document.related_id)["dates"]
        except ValueError:
            pass
    discards, accepted = [], 0
    for index, raw in enumerate(items):
        try:
            item = validate_item(raw, set(allowed or [u["id"] for u in extraction["units"]]))
            data = evaluate(item, extraction, document.role, target_dates, generator)
            fingerprint = digest(
                {
                    k: item[k]
                    for k in (
                        "subject",
                        "modality",
                        "action",
                        "object",
                        "conditions",
                        "exceptions",
                        "evidence",
                    )
                }
            )
            data["fingerprint"] = fingerprint
            data["inventory_snapshot"] = extraction["links"]
            identifier = digest([run.id, batch_key, index, data])[:32]
            if not session.get(Interpretation, identifier):
                session.add(
                    Interpretation(
                        id=identifier,
                        obligation_id=identifier,
                        document_id=document.id,
                        run_id=run.id,
                        version=1,
                        data=data,
                    )
                )
                session.flush()
                audit(
                    session,
                    "worker",
                    "interpretation.proposed",
                    identifier,
                    {"run_id": run.id, "fingerprint": fingerprint},
                )
            accepted += 1
        except (ValueError, TypeError, KeyError) as error:
            discards.append({"index": index, "reason": str(error)})
    return {"accepted": accepted, "total": len(items), "discards": discards}


def run_one(factory, settings):
    with factory.begin() as session:
        queued = session.scalar(
            select(Run)
            .where(Run.state == "queued")
            .order_by(Run.created)
            .with_for_update(skip_locked=True)
        )
        if not queued:
            return False
        claimed = session.execute(
            update(Run)
            .where(Run.id == queued.id, Run.state == "queued")
            .values(state="running", updated=now())
        )
        if claimed.rowcount != 1:
            return False
        run_id = queued.id
        audit(session, "worker", "run.started", run_id, {})
    try:
        with factory() as session:
            run = session.get(Run, run_id)
            document = session.get(Document, run.document_id)
            if run.kind == "structure":
                artifact = session.get(Artifact, document.artifact_id)
                started = time.monotonic()
                result = extract(artifact.content, artifact.media, settings, document.role)
                elapsed = time.monotonic() - started
                with factory.begin() as write:
                    write.add(
                        Extraction(
                            document_id=document.id,
                            text=result["text"],
                            text_hash=result["text_hash"],
                            data={
                                k: v for k, v in result.items() if k not in {"text", "text_hash"}
                            },
                        )
                    )
                    complete(
                        write, run_id, {"units": len(result["units"]), "duration_seconds": elapsed}
                    )
                return True
            extraction = extraction_data(session, document.id)
            if run.kind == "rules":
                items = rule_candidates(extraction)
                items = [
                    i
                    for i in items
                    if any(e["unit_id"] in run.parameters["scope"] for e in i["evidence"])
                ]
                with factory.begin() as write:
                    summary = save_candidates(
                        write, write.get(Run, run_id), items, extraction, "rules"
                    )
                    complete(write, run_id, summary)
                return True
            if run.kind == "replay":
                response = session.get(ModelResponse, run.parameters["response_id"])
                items, errors = llm.decode_response(response.data["record"])
                allowed = [
                    u["id"]
                    for u in json.loads(
                        response.data["request"]["messages"][1]["content"].split("\n", 1)[1]
                    )
                ]
                with factory.begin() as write:
                    summary = save_candidates(
                        write, write.get(Run, run_id), items, extraction, "replay", allowed
                    )
                    summary["response_errors"] = errors
                    summary["reproduction"] = True
                    complete(write, run_id, summary)
                return True
            parameters = run.parameters
        batches = llm.select_batches(extraction, parameters["scope"])
        summaries = []
        for number, batch in enumerate(batches):
            payload = llm.request_payload(parameters["model"], batch)
            key = llm.cache_key(payload)
            with factory.begin() as session:
                session.execute(update(AuditHead).values(revision=AuditHead.revision + 1))
                cached = session.scalars(
                    select(ModelResponse)
                    .where(ModelResponse.cache_key == key)
                    .order_by(ModelResponse.created.desc())
                ).first()
                if cached and cached.data["record"]["status"] != "complete":
                    cached = None
                if not cached:
                    if session.get(CallClaim, key):
                        raise ValueError(
                            "Requisição idêntica ativa ou com resultado desconhecido. Reconciliação necessária antes de repetir cobrança."
                        )
                    session.add(CallClaim(cache_key=key, run_id=run_id))
                    session.flush()
            if cached and not parameters.get("fresh"):
                data = cached.data | {"cached_from": cached.id, "incremental_cost_usd": "0"}
            else:
                with factory.begin() as session:
                    audit(
                        session,
                        "worker",
                        "model.intent",
                        run_id,
                        {"batch": number, "request_hash": key},
                    )
                    current = session.get(Run, run_id)
                    current.result = {
                        "in_flight_batch": number,
                        "outcome": "unknown_until_recorded",
                    }
                started = time.monotonic()
                try:
                    record = llm.call_model(settings, payload)
                except (TimeoutError, OSError, __import__("httpx").HTTPError):
                    record = {"status": "unknown_result", "raw": None}
                raw = record.get("raw") or {}
                usage = raw.get("usage", {})
                measured = (
                    "prompt_tokens" in usage
                    and "completion_tokens" in usage
                    and raw.get("model") == parameters["model"]
                )
                amount = (
                    str(
                        llm.cost(
                            parameters["estimate"]["price"],
                            usage["prompt_tokens"],
                            usage["completion_tokens"],
                        )
                    )
                    if measured
                    else None
                )
                data = {
                    "request": payload,
                    "record": record,
                    "requested_model": parameters["model"],
                    "returned_model": raw.get("model"),
                    "usage": usage,
                    "cost_usd": amount,
                    "incremental_cost_usd": amount,
                    "price": parameters["estimate"]["price"],
                    "latency_seconds": time.monotonic() - started,
                    "prompt_version": llm.PROMPT_VERSION,
                    "prompt_hash": digest(llm.PROMPT.encode()),
                    "model_warning": raw.get("model") != parameters["model"],
                }
            with factory.begin() as session:
                response = ModelResponse(run_id=run_id, cache_key=key, data=data)
                session.add(response)
                session.flush()
                claim = session.get(CallClaim, key)
                if claim:
                    claim.state = data["record"]["status"]
                audit(
                    session,
                    "worker",
                    "model.recorded",
                    response.id,
                    {"run": run_id, "status": data["record"]["status"]},
                )
            items, errors = llm.decode_response(data["record"])
            with factory.begin() as session:
                current = session.get(Run, run_id)
                summary = save_candidates(
                    session, current, items, extraction, "ai", [u["id"] for u in batch], str(number)
                )
                summary["response_errors"] = errors
                summaries.append(summary)
                current.progress = int(100 * (number + 1) / len(batches))
                current.updated = now()
                current.result = {"batches": summaries}
            if data["record"]["status"] != "complete":
                raise ValueError(
                    "Execução interrompida: "
                    + data["record"]["status"]
                    + ". Resposta preservada; repetição automática desativada."
                )
            if errors:
                raise ValueError(
                    "Saída JSON inválida. Resposta bruta preservada para diagnóstico e reprodução."
                )
        with factory.begin() as session:
            complete(
                session,
                run_id,
                {
                    "accepted": sum(s["accepted"] for s in summaries),
                    "total": sum(s["total"] for s in summaries),
                    "batches": summaries,
                },
            )
    except Exception as error:
        with factory.begin() as session:
            run = session.get(Run, run_id)
            run.state = "failed"
            run.updated = now()
            # Never expose exception bodies from network libraries or filesystem paths.
            message = (
                str(error)
                if isinstance(error, ValueError)
                else "Falha interna na etapa; consulte a trilha e reavalie a entrada."
            )
            run.result = run.result | {"error": message}
            audit(session, "worker", "run.failed", run_id, {"reason": message})
    return True


def recover_stale(factory, seconds=600):
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    count = 0
    with factory.begin() as session:
        session.execute(update(AuditHead).values(revision=AuditHead.revision + 1))
        stale = list(
            session.scalars(select(Run).where(Run.state == "running", Run.updated < cutoff))
        )
        for run in stale:
            run.state = "queued" if run.kind in {"rules", "structure", "replay"} else "interrupted"
            run.updated = now()
            run.result = run.result | {
                "recovery": "Lease expirado; chamadas pagas não são repetidas automaticamente."
            }
            audit(session, "worker", "run.recovered", run.id, {"state": run.state})
            count += 1
    return count


def complete(session, run_id, result):
    run = session.get(Run, run_id)
    run.state, run.progress, run.result, run.updated = "completed", 100, result, now()
    audit(session, "worker", "run.completed", run_id, result)


def decision_state(session, interpretation):
    decisions = list(
        session.scalars(
            select(Decision)
            .where(Decision.interpretation_id == interpretation.id)
            .order_by(Decision.created, Decision.id)
        )
    )
    data = json.loads(json.dumps(interpretation.data))
    decisions.sort(key=lambda decision: decision.data.get("_ordinal", 0))
    findings = list(
        session.scalars(select(Finding).where(Finding.interpretation_id == interpretation.id))
    )
    data["objections"].extend(f.data | {"id": f.id} for f in findings)
    if findings and data["band"] == "ready":
        data["band"] = "attention"
        data["reasons"].extend(f.data["explanation"] for f in findings)
    data["review_level"] = "none"
    for decision in decisions:
        if decision.action in {"accept", "reject", "supersede", "revoke", "correct"}:
            data["status"] = {
                "accept": "validated",
                "reject": "rejected",
                "supersede": "superseded",
                "revoke": "revoked",
                "correct": "superseded",
            }[decision.action]
            data["review_level"] = decision.review_type
        if decision.action == "confirm_deadline":
            index = decision.data["index"]
            if index < len(data["deadlines"]):
                data["deadlines"][index]["state"] = "confirmed"
                data["deadlines"][index]["confirmation_level"] = decision.review_type
    resolved = {d.data["objection_id"] for d in decisions if d.action == "resolve"}
    data["resolved"] = sorted(resolved)
    unresolved_confirmed = [
        o for o in data["objections"] if o["state"] == "confirmed" and o["id"] not in resolved
    ]
    if data["status"] == "validated" and unresolved_confirmed:
        data["status"] = "pending_review"
        data["reasons"].append(
            "Contestação confirmada posterior ao aceite exige nova decisão humana."
        )
    # Revision token also advances when a human submits a new finding.
    data["decisions_count"] = len(decisions) + len(findings)
    return data, decisions


def review(session, interpretation_id, actor, action, review_type, reason, expected_count, payload):
    from .db import AuditHead

    session.execute(update(AuditHead).values(revision=AuditHead.revision + 1))
    item = session.get(Interpretation, interpretation_id)
    if not item:
        raise ValueError("Interpretação inexistente.")
    if actor.role == "operator" or review_type not in {"technical", "legal"}:
        raise ValueError("Papel sem permissão de revisão.")
    if review_type == "legal" and actor.role != "legal":
        raise ValueError(
            "Revisão jurídica exige conta de especialista provisionada explicitamente."
        )
    if not reason.strip():
        raise ValueError("Justificativa obrigatória.")
    latest = session.scalar(
        select(func.max(Interpretation.version)).where(
            Interpretation.obligation_id == item.obligation_id
        )
    )
    data, decisions = decision_state(session, item)
    if item.version != latest or data["decisions_count"] != expected_count:
        raise ValueError("A interpretação mudou. Recarregue antes de decidir.")
    if action not in {
        "accept",
        "reject",
        "correct",
        "resolve",
        "supersede",
        "revoke",
        "confirm_deadline",
    }:
        raise ValueError("Ação inválida.")
    extraction = extraction_data(session, item.document_id)
    decision_payload = {}
    if action == "accept":
        assert_reviewable(data, extraction, set(data["resolved"]))
        missing = [
            o
            for o in data["objections"]
            if o["kind"] == "unavailable_dependency" and o["id"] not in data["resolved"]
        ]
        if missing:
            raise ValueError(
                "Dependência ausente bloqueia aceite até decisão explícita sobre a pendência."
            )
    elif action == "resolve":
        objection_id = payload.get("objection_id")
        if objection_id not in {o["id"] for o in data["objections"]}:
            raise ValueError("Contestação inexistente.")
        decision_payload = {
            "objection_id": objection_id,
            "resolution": payload.get("resolution", "human_override"),
        }
    elif action == "confirm_deadline":
        index = int(payload.get("index", -1))
        if index < 0 or index >= len(data["deadlines"]) or not data["deadlines"][index].get("date"):
            raise ValueError("Prazo calculado não encontrado.")
        decision_payload = {"index": index, "convention": data["deadlines"][index]["convention"]}
    elif action == "correct":
        candidate = validate_item(
            payload.get("candidate", {}), {u["id"] for u in extraction["units"]}
        )
        document = session.get(Document, item.document_id)
        target_dates = (
            extraction_data(session, document.related_id)["dates"] if document.related_id else None
        )
        evaluated = evaluate(candidate, extraction, document.role, target_dates, "human")
        successor = Interpretation(
            obligation_id=item.obligation_id,
            document_id=item.document_id,
            version=item.version + 1,
            predecessor=item.id,
            data=evaluated,
        )
        session.add(successor)
        session.flush()
        decision_payload = {
            "successor": successor.id,
            "previous_hash": digest(item.data),
            "new_hash": digest(evaluated),
        }
    decision = Decision(
        interpretation_id=item.id,
        user_id=actor.id,
        action=action,
        review_type=review_type,
        reason=reason.strip(),
        data=decision_payload | {"_ordinal": len(decisions)},
    )
    session.add(decision)
    session.flush()
    audit(
        session,
        actor.id,
        "review." + action,
        decision.id,
        {
            "interpretation_id": item.id,
            "reason": reason.strip(),
            "type": review_type,
            **decision_payload,
        },
    )
    return decision


def obligations(session):
    items = list(session.scalars(select(Interpretation).order_by(Interpretation.created)))
    latest = {}
    for item in items:
        if item.obligation_id not in latest or item.version > latest[item.obligation_id].version:
            latest[item.obligation_id] = item
    counts = Counter(
        i.data.get("fingerprint") for i in latest.values() if i.data.get("fingerprint")
    )
    result = []
    for item in latest.values():
        data, _ = decision_state(session, item)
        document = session.get(Document, item.document_id)
        result.append(
            {
                "id": item.id,
                "document_id": item.document_id,
                "document_title": document.title,
                "file_sha256": document.artifact_id,
                "document_role": document.role,
                "origin": document.origin,
                "synthetic": document.synthetic,
                "version": item.version,
                **data,
                "duplicate_candidate": counts[item.data.get("fingerprint")] > 1
                if item.data.get("fingerprint")
                else False,
            }
        )
    return result
