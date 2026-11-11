"""Estruturação regulatória da PoC. Texto literal e interpretação ficam em campos separados.

Nada aqui é validado automaticamente: todo item nasce `pending_human_review`. A IA só propõe
candidatos; âncoras são verificadas deterministicamente por `evidence.verify` (via `evaluate`).
"""

import json
import re
from decimal import Decimal

import httpx

from .. import llm
from ..db import digest
from ..proposals import evaluate, rule_candidates
from ..structure import ACT

LABEL = {
    "article": "Art. {}",
    "paragraph": "{}",
    "clause": "inciso {}",
    "letter": "alínea {})",
    "item": "item {}",
    "annex": "Anexo {}",
    "table": "Tabela {}",
    "formula": "fórmula {}",
    "question": "pergunta {}",
    "heading": "{}",
}
# Tipos não deônticos, detectados por padrão literal; sem interpretação além do tipo.
TYPES = (
    ("penalty", re.compile(r"constitui infração|\bmulta\b|\bpenalidade", re.I)),
    ("revocation", re.compile(r"\brevoga-se\b|\bficam? revogad[oa]s?\b", re.I)),
    (
        "transitional",
        re.compile(
            r"^\s*[IVXL]+\s*[-–]\s*até\s+\d+|\bcontados da publicação\b|\bentra em vigor\b", re.I
        ),
    ),
)
REF = re.compile(
    rf"(?:{ACT.pattern})|\b(?:art\.?\s*\d+[º°]?(?:-[A-Z])?|Anexo\s+[IVXLCDM]+|Tabela\s+\d+)",
    re.I,
)
DOCUMENTAL = re.compile(r"relatório|plano|registro|publicar|disponibilizar|documento|dossiê", re.I)


def dispositivo(unit, by_id):
    chain = []
    while unit:
        chain.append(LABEL.get(unit["kind"], "{}").format(unit["label"]))
        unit = by_id.get(unit["parent"])
    return " › ".join(reversed(chain))


def _item(
    doc, extraction, pages, unit, kind, anchors, interpretation, notes, generator, extra=None
):
    by_id = {u["id"]: u for u in extraction["units"]}
    page_info = {p["number"]: p for p in pages}
    verified = [a for a in anchors if a["state"] == "verified"]
    first = verified[0] if verified else None
    start, end = (first["start"], first["end"]) if first else (unit["start"], unit["end"])
    uncertainties = list(notes)
    for number in unit["pages"]:
        page = page_info[number]
        if page["state"] != "faithful":
            uncertainties.append(f"página {number}: {page['state']} ({'; '.join(page['reasons'])})")
    if anchors and len(verified) != len(anchors):
        uncertainties.append("âncora não verificada literalmente (pendente/inválida)")
    return {
        "id": digest([doc["sha256"], kind, generator, start, end, first and first["quote_hash"]])[
            :20
        ],
        "type": kind,
        "literal_text": first["quote"] if first else None,
        "document": {"file": doc["file"], "sha256": doc["sha256"]},
        "pages": unit["pages"],
        "dispositivo": dispositivo(unit, by_id),
        "owner_norm": unit["owner"],  # norma-alvo quando o bloco é citação de alteração
        "locator": {"unit_id": unit["id"], "start": start, "end": end},
        "anchors": anchors,
        "interpretation": interpretation,  # inferência; nunca é texto normativo
        "interpretation_generator": generator,
        "validation_state": "pending_human_review"
        if anchors and len(verified) == len(anchors)
        else "anchor_unverified",
        "uncertainties": uncertainties,
        **(extra or {}),
    }


def deterministic_items(doc, extraction, pages):
    units = extraction["units"]
    by_id = {u["id"]: u for u in units}
    items, discarded = [], []
    for cand in rule_candidates(extraction):
        try:
            result = evaluate(cand, extraction, "norm", None, "rules")
        except ValueError as error:
            discarded.append({"reason": str(error), "evidence": cand["evidence"][0]["unit_id"]})
            continue
        unit = by_id[result["anchors"][0]["unit_id"]]
        kind = {"duty": "obligation"}.get(result["modality"], result["modality"])
        text = unit["text"]
        notes = result["reasons"]
        if result["subject"] == "não identificado":
            notes.append("sujeito não identificado explicitamente")
        items.append(
            _item(
                doc,
                extraction,
                pages,
                unit,
                kind,
                result["anchors"],
                {
                    "subject": result["subject"],
                    "modality": result["modality"],
                    "action": result["action"],
                    "conditions": result["conditions"],
                    "exceptions": result["exceptions"],
                    "documental": bool(DOCUMENTAL.search(text)),
                },
                notes,
                "rules",
                {"band": result["band"], "objections": result["objections"]},
            )
        )
        for deadline in result["deadlines"]:
            # O prazo pertence ao dispositivo onde está escrito: alíneas que herdam o caput não o
            # repetem (mesmo id → _unique descarta as cópias).
            owner = by_id[deadline["unit_id"]]
            own_anchors = [a for a in result["anchors"] if a["unit_id"] == owner["id"]]
            items.append(
                _item(
                    doc,
                    extraction,
                    pages,
                    owner,
                    "deadline",
                    own_anchors,
                    deadline,
                    [],
                    "rules",
                )
                | {
                    "id": digest(
                        [
                            doc["sha256"],
                            "deadline",
                            owner["start"],
                            deadline["quote"],
                            deadline["quantity"],
                        ]
                    )[:20]
                }
            )
    for unit in units:
        for kind, pattern in TYPES:
            # Penalidade/revogação só com base no próprio dispositivo, nunca num título.
            if unit["kind"] != "heading" and pattern.search(unit["text"]):
                anchor = _anchor(unit, extraction)
                items.append(_item(doc, extraction, pages, unit, kind, [anchor], None, [], "rules"))
        for match in REF.finditer(unit["text"]):
            if not unit["text"][: match.start()].strip(' “"'):
                continue  # rótulo do próprio dispositivo, não é remissão
            anchor = _anchor(unit, extraction)
            items.append(
                _item(
                    doc,
                    extraction,
                    pages,
                    unit,
                    "reference",
                    [anchor],
                    None,
                    ["remissão não resolvida contra o acervo; alvo não verificado"],
                    "rules",
                    {"reference": {"text": match.group(), "offset": match.start(), "target": None}},
                )
                | {"id": digest([doc["sha256"], "reference", unit["start"], match.start()])[:20]}
            )
    return _unique(items), discarded


def _anchor(unit, extraction):
    from ..evidence import verify

    return verify(
        unit["text"].strip(),
        unit["id"],
        extraction["units"],
        extraction["text_hash"],
        source=extraction.get("source"),
    )


def _unique(items):
    seen, out = set(), []
    for item in items:
        if item["id"] not in seen:
            seen.add(item["id"])
            out.append(item)
    return out


def ai_items(doc, extraction, pages, settings, run, call=llm.call_model, raw_dir=None):
    """Chama o modelo por lote sob teto de custo por execução. `run` acumula gasto e registros."""
    prices = llm.price_config(settings)
    if not (settings.model and settings.api_key and settings.azure_endpoint and prices):
        run["ai"] = {"status": "skipped", "reason": "provedor, chave ou preço verificável ausente"}
        return [], []
    budget = Decimal(settings.run_budget_usd)
    units = {u["id"]: u for u in extraction["units"]}
    items, discarded = [], []
    for index, batch in enumerate(llm.select_batches(extraction)):
        payload = llm.request_payload(settings.model, batch, settings.reasoning_effort)
        bound = len(json.dumps(payload, ensure_ascii=False).encode()) + 2048
        reserve = llm.cost(prices, bound, payload["max_completion_tokens"])
        if run["spent"] + reserve > budget:
            run["calls"].append(
                {"batch": index, "status": "budget_stop", "reserve_usd": str(reserve)}
            )
            run["ai"] = {"status": "stopped_by_budget", "remaining_batches_from": index}
            break
        try:
            record = call(settings, payload)
        except httpx.HTTPError as error:  # resultado desconhecido: pode ter sido cobrado
            record = {"status": "unknown_result", "raw": None, "error": type(error).__name__}
        usage = ((record.get("raw") or {}).get("usage")) or {}
        if record["status"] in {"rate_limited", "provider_error"}:
            actual = Decimal(0)
        elif isinstance(usage.get("prompt_tokens"), int) and isinstance(
            usage.get("completion_tokens"), int
        ):
            actual = llm.cost(prices, usage["prompt_tokens"], usage["completion_tokens"])
        else:
            actual = reserve  # custo desconhecido nunca vira zero
        run["spent"] += actual
        key = llm.cache_key(payload)
        run["calls"].append(
            {
                "batch": index,
                "units": len(batch),
                "status": record["status"],
                "usage": usage or None,
                "cost_usd": str(actual),
                "cost_basis": "usage" if usage and actual != reserve else "reserva conservadora",
                "request_hash": key,
            }
        )
        if raw_dir is not None and record.get("raw") is not None:
            (raw_dir / f"{key}.json").write_text(
                json.dumps(record["raw"], ensure_ascii=False, indent=1), encoding="utf-8"
            )
        if record["status"] in {"rate_limited", "unknown_result"}:
            run["ai"] = {"status": "stopped_on_" + record["status"], "batch": index}
            break  # sem retentativa automática: pode haver cobrança
        proposed, problems = llm.decode_response(record)
        discarded += [{"batch": index} | p for p in problems]
        for candidate in proposed:
            try:
                result = evaluate(candidate, extraction, "norm", None, "azure")
            except ValueError as error:
                discarded.append({"batch": index, "reason": str(error)})
                continue
            unit = units[result["anchors"][0]["unit_id"]]
            kind = {"duty": "obligation"}.get(result["modality"], result["modality"])
            items.append(
                _item(
                    doc,
                    extraction,
                    pages,
                    unit,
                    kind,
                    result["anchors"],
                    {
                        k: result[k]
                        for k in (
                            "subject",
                            "modality",
                            "action",
                            "object",
                            "conditions",
                            "exceptions",
                        )
                    },
                    result["reasons"],
                    f"azure:{settings.model}",
                    {"band": result["band"], "objections": result["objections"]},
                )
            )
    run.setdefault("ai", {"status": "complete"})
    return _unique(items), discarded
