import csv
import io
import json
import secrets
import threading
import time
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from sqlalchemy import func, select

from .auth import authenticate, create_user, login
from .config import NOTICE, Settings
from .db import (
    Artifact,
    AuditEvent,
    Decision,
    Document,
    Extraction,
    Interpretation,
    LoginSession,
    ModelResponse,
    Run,
    User,
    database,
    initialize,
    verify_chain,
)
from .evidence import recheck
from .llm import estimate
from .services import (
    associate_dependency,
    decision_state,
    enqueue,
    extraction_data,
    obligations,
    propose_finding,
    receive,
    recover_stale,
    review,
    run_one,
)

ROOT = Path(__file__).resolve().parent
LABELS = {
    "human": "Proposta humana",
    "question": "Pergunta / resposta",
    "pending_review": "Pendente de revisão",
    "detected": "Detectada por regras",
    "suggested": "Sugerida",
    "validated": "Aceita",
    "rejected": "Rejeitada",
    "superseded": "Superada",
    "revoked": "Revogada",
    "blocked": "Bloqueada",
    "attention": "Requer atenção",
    "ready": "Pronta para revisão",
    "verified": "Verificada",
    "pending": "Pendente",
    "invalid": "Inválida",
    "technical": "Técnica",
    "legal": "Jurídica especializada",
    "none": "Sem revisão",
    "provisional": "Calculado provisório",
    "confirmed": "Confirmado por pessoa",
    "awaiting_event": "Sem data até evento",
    "not_calculated": "Não calculado",
    "norm": "Norma",
    "compiled": "Versão compilada",
    "clarification": "Esclarecimento",
    "auxiliary": "Auxiliar",
    "duty": "Dever",
    "permission": "Faculdade",
    "prohibition": "Vedação",
    "confirmed_finding": "Confirmada",
    "inconclusive": "Inconclusiva",
    "queued": "Na fila",
    "running": "Em execução",
    "completed": "Concluída",
    "failed": "Falhou",
    "structure": "Estruturação",
    "rules": "Regras",
    "ai": "IA",
    "replay": "Reprodução",
    "interrupted": "Interrompida — requer reconciliação",
    "article": "Artigo",
    "paragraph": "Parágrafo",
    "clause": "Inciso",
    "letter": "Alínea",
    "item": "Item",
    "table": "Tabela",
    "formula": "Fórmula",
    "annex": "Anexo",
    "unstructured": "Texto",
    "unsupported_modality": "Modalidade não sustentada",
    "unsupported_duty": "Dever não sustentado",
    "subject_mismatch": "Sujeito divergente",
    "ignored_exception": "Exceção omitida",
    "omitted_condition": "Condição omitida",
    "clarification_only": "Fundamento em esclarecimento",
    "unavailable_dependency": "Dependência indisponível",
    "grouped_actions": "Agrupamento de ações",
    "incorrect_period": "Prazo divergente",
    "wrong_landmark": "Marco divergente",
    "critical": "Crítica",
    "high": "Alta",
}


def create_app(settings=None, embedded_worker=False):
    settings = settings or Settings()
    settings.prepare()
    engine, factory = database(settings.database_url)
    initialize(engine)
    stop = threading.Event()

    def worker():
        recover_stale(factory)
        while not stop.is_set():
            if not run_one(factory, settings):
                stop.wait(0.5)

    @asynccontextmanager
    async def lifespan(_):
        thread = None
        if embedded_worker:
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
        yield
        stop.set()
        if thread:
            thread.join(timeout=2)
        engine.dispose()

    app = FastAPI(title="Athenix", version="0.1.0", lifespan=lifespan)
    app.state.factory, app.state.settings, app.state.engine = factory, settings, engine
    app.state.setup_nonce = secrets.token_urlsafe(32)
    attempts = {}
    templates = Jinja2Templates(directory=str(ROOT / "templates"))
    templates.env.filters["label"] = lambda value: LABELS.get(value, value)
    templates.env.filters["pretty"] = lambda value: json.dumps(value, ensure_ascii=False, indent=2)
    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

    @app.middleware("http")
    async def security(request, call_next):
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin
            and origin != str(request.base_url).rstrip("/")
        ):
            return JSONResponse({"detail": "Origem da requisição recusada."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        return response

    @app.exception_handler(ValueError)
    async def bad_value(request, error):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": str(error)}, status_code=400)
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"message": str(error), "notice": NOTICE},
            status_code=400,
        )

    def guard(request, session, form=None):
        user, record = authenticate(session, request.cookies.get("athenix_session"))
        if not user:
            raise HTTPException(401, "Autenticação necessária.")
        if request.method not in {"GET", "HEAD"}:
            token = request.headers.get("x-csrf-token") or (form or {}).get("csrf", "")
            if not secrets.compare_digest(str(token), record.csrf):
                raise HTTPException(403, "Token CSRF inválido.")
        return user, record

    def render(request, session, page, **context):
        user, record = guard(request, session)
        docs = list(session.scalars(select(Document).order_by(Document.created.desc())))
        missing = []
        for extracted in session.scalars(select(Extraction)):
            for link in extraction_data(session, extracted.document_id)["links"]:
                if link["state"] != "interpreted":
                    missing.append(link)
        legal_count = sum(
            1
            for d in session.scalars(
                select(Decision).where(Decision.action == "accept", Decision.review_type == "legal")
            )
        )
        return templates.TemplateResponse(
            request=request,
            name="page.html",
            context={
                "page": page,
                "user": user,
                "csrf": record.csrf,
                "notice": NOTICE,
                "documents": docs,
                "missing": missing,
                "legal_count": legal_count,
                **context,
            },
        )

    @app.get("/health")
    def health():
        with factory() as session:
            session.execute(select(func.count()).select_from(User))
        return {
            "status": "ok",
            "version": "0.1.0",
            "ai_enabled": False,
            "ai_configured": bool(settings.api_key and settings.model),
        }

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        with factory() as session:
            empty = not session.scalar(select(User.id).limit(1))
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"setup": empty, "nonce": app.state.setup_nonce, "notice": NOTICE},
        )

    @app.post("/setup")
    async def setup(request: Request):
        form = await request.form()
        if not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            raise HTTPException(403, "Configuração inicial disponível apenas em acesso local.")
        if not secrets.compare_digest(str(form.get("nonce", "")), app.state.setup_nonce):
            raise HTTPException(403, "Recarregue o formulário de configuração.")
        from .db import AuditHead
        from sqlalchemy import update

        with factory.begin() as session:
            session.execute(update(AuditHead).values(revision=AuditHead.revision + 1))
            if session.scalar(select(User.id).limit(1)):
                raise ValueError("A configuração inicial já foi concluída.")
            create_user(session, str(form.get("username", "")), str(form.get("password", "")))
        return RedirectResponse("/login", status_code=303)

    async def do_login(request, as_json=False):
        form = await request.json() if as_json else await request.form()
        key = request.client.host if request.client else "unknown"
        recent = [t for t in attempts.get(key, []) if time.monotonic() - t < 60]
        if len(recent) >= 8:
            raise HTTPException(429, "Muitas tentativas; aguarde um minuto.")
        attempts[key] = recent + [time.monotonic()]
        with factory.begin() as session:
            token, csrf, user = login(
                session,
                str(form.get("username", "")),
                str(form.get("password", "")),
                settings.session_hours,
            )
        attempts.pop(key, None)
        response = (
            JSONResponse({"csrf": csrf, "username": user.username, "role": user.role})
            if as_json
            else RedirectResponse("/", status_code=303)
        )
        response.set_cookie(
            "athenix_session",
            token,
            httponly=True,
            secure=settings.secure_cookie,
            samesite="strict",
            max_age=settings.session_hours * 3600,
        )
        return response

    @app.post("/login")
    async def login_form(request: Request):
        return await do_login(request)

    @app.post("/api/login")
    async def login_api(request: Request):
        return await do_login(request, True)

    @app.post("/logout")
    async def logout(request: Request):
        form = await request.form()
        with factory.begin() as session:
            _, record = guard(request, session, form)
            session.delete(session.get(LoginSession, record.id))
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("athenix_session")
        return response

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        with factory() as session:
            if not authenticate(session, request.cookies.get("athenix_session"))[0]:
                return RedirectResponse("/login", status_code=303)
            rows = obligations(session)
            return render(
                request, session, "dashboard", rows=rows, counts=Counter(r["band"] for r in rows)
            )

    @app.get("/documents", response_class=HTMLResponse)
    def documents(request: Request):
        with factory() as session:
            return render(request, session, "documents")

    @app.post("/documents")
    @app.post("/api/documents")
    async def upload(request: Request):
        form = await request.form()
        with factory.begin() as session:
            user, _ = guard(request, session, form)
            file = form.get("file")
            if not file or not hasattr(file, "read"):
                raise ValueError("Selecione um arquivo PDF ou HTML.")
            content = await file.read(settings.max_bytes + 1)
            document, reused = receive(
                session,
                settings,
                content,
                str(form.get("title", "")),
                str(form.get("origin", "")),
                str(form.get("role", "norm")),
                str(form.get("source_url", "")),
                user.id,
                form.get("related_id") or None,
            )
        if request.url.path.startswith("/api/"):
            return {"id": document.id, "sha256": document.artifact_id, "reused": reused}
        return RedirectResponse("/documents/" + document.id, status_code=303)

    @app.post("/demo")
    async def demo(request: Request):
        form = await request.form()
        with factory.begin() as session:
            user, _ = guard(request, session, form)
            content = (ROOT / "sample.html").read_bytes()
            document, _ = receive(
                session,
                settings,
                content,
                "Norma sintética — laboratório",
                "Corpus sintético criado nesta implementação; sem validade normativa.",
                "norm",
                "",
                user.id,
                synthetic=True,
            )
        return RedirectResponse("/documents/" + document.id, status_code=303)

    @app.get("/documents/{document_id}", response_class=HTMLResponse)
    def document_page(request: Request, document_id: str):
        with factory() as session:
            doc = session.get(Document, document_id)
            if not doc:
                raise HTTPException(404, "Documento não encontrado.")
            item = session.scalar(select(Extraction).where(Extraction.document_id == document_id))
            extracted = extraction_data(session, document_id) if item else None
            runs = list(
                session.scalars(
                    select(Run).where(Run.document_id == document_id).order_by(Run.created.desc())
                )
            )
            responses = list(
                session.scalars(
                    select(ModelResponse).join(Run).where(Run.document_id == document_id)
                )
            )
            identical = (
                list(
                    session.scalars(
                        select(Extraction).where(
                            Extraction.text_hash == item.text_hash,
                            Extraction.document_id != document_id,
                        )
                    )
                )
                if item
                else []
            )
            return render(
                request,
                session,
                "document",
                doc=doc,
                extracted=extracted,
                runs=runs,
                responses=responses,
                identical=identical,
                estimated=estimate(extracted, settings) if extracted else None,
            )

    @app.get("/api/documents/{document_id}")
    def get_document(request: Request, document_id: str):
        with factory() as session:
            guard(request, session)
            doc = session.get(Document, document_id)
            if not doc:
                raise HTTPException(404)
            return {
                "id": doc.id,
                "title": doc.title,
                "sha256": doc.artifact_id,
                "origin": doc.origin,
                "role": doc.role,
                "synthetic": doc.synthetic,
                "extraction": extraction_data(session, doc.id),
            }

    @app.get("/documents/{document_id}/original")
    def original(request: Request, document_id: str):
        with factory() as session:
            guard(request, session)
            doc = session.get(Document, document_id)
            if not doc:
                raise HTTPException(404)
            artifact = session.get(Artifact, doc.artifact_id)
            # HTML is always downloaded, never executed inside the application origin.
            extension = ".pdf" if artifact.media == "application/pdf" else ".html"
            return Response(
                artifact.content,
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{artifact.id}{extension}"'},
            )

    @app.post("/documents/{document_id}/runs")
    @app.post("/api/documents/{document_id}/runs")
    async def queue(request: Request, document_id: str):
        payload = (
            await request.json()
            if "application/json" in request.headers.get("content-type", "")
            else dict(await request.form())
        )
        scope = payload.get("scope")
        if isinstance(scope, str):
            scope = [s.strip() for s in scope.split(",") if s.strip()] or None
        with factory.begin() as session:
            user, _ = guard(request, session, payload)
            kind = str(payload.get("kind", "rules"))
            if kind == "ai" and payload.get("confirm_paid") not in {True, "yes"}:
                raise ValueError("Confirme a execução paga após conferir a estimativa.")
            run, reused = enqueue(
                session,
                document_id,
                kind,
                user.id,
                settings,
                scope,
                str(payload.get("budget", "0")),
                payload.get("response_id"),
            )
        if request.url.path.startswith("/api/"):
            return {"id": run.id, "state": run.state, "reused": reused}
        return RedirectResponse("/documents/" + document_id, status_code=303)

    @app.get("/api/documents/{document_id}/estimate")
    def get_estimate(request: Request, document_id: str, scope: str = ""):
        with factory() as session:
            guard(request, session)
            return estimate(
                extraction_data(session, document_id), settings, scope.split(",") if scope else None
            )

    @app.post("/documents/{document_id}/dependencies")
    @app.post("/api/documents/{document_id}/dependencies")
    async def attach_dependency(request: Request, document_id: str):
        payload = (
            await request.json()
            if "application/json" in request.headers.get("content-type", "")
            else dict(await request.form())
        )
        with factory.begin() as session:
            user, _ = guard(request, session, payload)
            association = associate_dependency(
                session,
                document_id,
                str(payload.get("link_id", "")),
                str(payload.get("target_id", "")),
                str(payload.get("reason", "")),
                user,
            )
        if request.url.path.startswith("/api/"):
            return {"id": association.id}
        return RedirectResponse("/documents/" + document_id, status_code=303)

    @app.get("/api/runs/{run_id}")
    def get_run(request: Request, run_id: str):
        with factory() as session:
            guard(request, session)
            run = session.get(Run, run_id)
            if not run:
                raise HTTPException(404)
            return {
                "id": run.id,
                "state": run.state,
                "progress": run.progress,
                "result": run.result,
            }

    @app.get("/api/runs/{run_id}/reproduction")
    def reproducible_run(request: Request, run_id: str):
        from .reproduction import bundle

        with factory() as session:
            guard(request, session)
            run = session.get(Run, run_id)
            if not run or run.kind == "structure":
                raise HTTPException(404)
            document = session.get(Document, run.document_id)
            extracted = extraction_data(session, document.id)
            items = list(
                session.scalars(select(Interpretation).where(Interpretation.run_id == run.id))
            )
            return bundle(document.artifact_id, extracted["text_hash"], [i.data for i in items])

    def filtered(request, session):
        rows = obligations(session)
        for key in ("status", "band", "document_id"):
            value = request.query_params.get(key)
            if value:
                rows = [r for r in rows if r.get(key) == value]
        for key in ("subject", "origin"):
            value = request.query_params.get(key, "").casefold()
            if value:
                rows = [r for r in rows if value in r[key].casefold()]
        deadline = request.query_params.get("deadline")
        if deadline:
            rows = [r for r in rows if any(d["state"] == deadline for d in r["deadlines"])]
        if request.query_params.get("history") != "yes":
            rows = [r for r in rows if r["status"] != "superseded"]
        return rows

    @app.get("/matrix", response_class=HTMLResponse)
    def matrix(request: Request):
        with factory() as session:
            return render(request, session, "matrix", rows=filtered(request, session))

    @app.get("/api/obligations")
    def get_obligations(request: Request):
        with factory() as session:
            guard(request, session)
            rows = filtered(request, session)
            return {"items": rows, "count": len(rows), "notice": NOTICE}

    @app.get("/obligations/{interpretation_id}", response_class=HTMLResponse)
    def obligation_page(request: Request, interpretation_id: str):
        with factory() as session:
            item = session.get(Interpretation, interpretation_id)
            if not item:
                raise HTTPException(404)
            data, decisions = decision_state(session, item)
            extracted = extraction_data(session, item.document_id)
            highlights = []
            for anchor in data["anchors"]:
                if recheck(anchor, extracted["text"], extracted["units"]):
                    start, end = anchor["start"], anchor["end"]
                    snippet = (
                        escape(extracted["text"][max(0, start - 100) : start])
                        + Markup("<mark>")
                        + escape(extracted["text"][start:end])
                        + Markup("</mark>")
                        + escape(extracted["text"][end : end + 100])
                    )
                    highlights.append(snippet)
                else:
                    highlights.append(None)
            history = list(
                session.scalars(
                    select(Interpretation)
                    .where(Interpretation.obligation_id == item.obligation_id)
                    .order_by(Interpretation.version)
                )
            )
            candidate = {
                k: data[k]
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
            return render(
                request,
                session,
                "obligation",
                item=item,
                data=data,
                decisions=decisions,
                doc=session.get(Document, item.document_id),
                highlights=highlights,
                history=history,
                candidate=candidate,
            )

    @app.post("/obligations/{interpretation_id}/review")
    @app.post("/api/obligations/{interpretation_id}/review")
    async def decide(request: Request, interpretation_id: str):
        payload = (
            await request.json()
            if "application/json" in request.headers.get("content-type", "")
            else dict(await request.form())
        )
        if payload.get("action") == "correct" and "correction_subject" in payload:
            count = int(payload.get("anchor_count", 0))
            if count < 1 or count > 20:
                raise ValueError("Quantidade de fundamentos inválida.")
            evidence = []
            for index in range(count + 1):
                unit_id = str(payload.get(f"anchor_unit_{index}", "")).strip()
                quote = str(payload.get(f"anchor_quote_{index}", "")).strip()
                if unit_id or quote:
                    evidence.append({"unit_id": unit_id, "quote": quote})
            payload["candidate"] = {
                "subject": str(payload.get("correction_subject", "")).strip(),
                "modality": str(payload.get("correction_modality", "")),
                "action": str(payload.get("correction_action", "")).strip(),
                "object": str(payload.get("correction_object", "")).strip(),
                "conditions": [
                    s.strip()
                    for s in str(payload.get("correction_conditions", "")).splitlines()
                    if s.strip()
                ],
                "exceptions": [
                    s.strip()
                    for s in str(payload.get("correction_exceptions", "")).splitlines()
                    if s.strip()
                ],
                "evidence": evidence,
            }
        if isinstance(payload.get("candidate"), str):
            try:
                payload["candidate"] = json.loads(payload["candidate"])
            except ValueError as error:
                raise ValueError("JSON de correção inválido.") from error
        with factory.begin() as session:
            user, _ = guard(request, session, payload)
            decision = review(
                session,
                interpretation_id,
                user,
                str(payload.get("action", "")),
                str(payload.get("review_type", "technical")),
                str(payload.get("reason", "")),
                int(payload.get("expected_count", -1)),
                payload,
            )
        if request.url.path.startswith("/api/"):
            return {"id": decision.id, "data": decision.data}
        return RedirectResponse(
            "/obligations/" + decision.data.get("successor", interpretation_id), status_code=303
        )

    @app.get("/timeline", response_class=HTMLResponse)
    def timeline(request: Request):
        with factory() as session:
            deadlines = [
                {"obligation": r, **d}
                for r in obligations(session)
                for d in r["deadlines"]
                if r["status"] != "superseded"
            ]
            deadlines.sort(key=lambda d: d.get("date") or "9999")
            return render(request, session, "timeline", deadlines=deadlines)

    @app.post("/obligations/{interpretation_id}/findings")
    @app.post("/api/obligations/{interpretation_id}/findings")
    async def add_finding(request: Request, interpretation_id: str):
        payload = (
            await request.json()
            if "application/json" in request.headers.get("content-type", "")
            else dict(await request.form())
        )
        with factory.begin() as session:
            user, _ = guard(request, session, payload)
            finding = propose_finding(
                session,
                interpretation_id,
                user,
                str(payload.get("kind", "")),
                str(payload.get("quote", "")),
                str(payload.get("unit_id", "")),
                str(payload.get("explanation", "")),
            )
        if request.url.path.startswith("/api/"):
            return {"id": finding.id, "state": finding.data["state"]}
        return RedirectResponse("/obligations/" + interpretation_id, status_code=303)

    @app.get("/risks", response_class=HTMLResponse)
    def risks(request: Request):
        with factory() as session:
            rows = obligations(session)
            counts = Counter(o["kind"] for r in rows for o in r["objections"])
            severities = Counter(o["severity"] for r in rows for o in r["objections"])
            return render(
                request,
                session,
                "risks",
                rows=rows,
                counts=counts,
                severities=severities,
                total=sum(counts.values()),
            )

    @app.get("/audit", response_class=HTMLResponse)
    def audit_page(request: Request):
        with factory() as session:
            events = list(
                session.scalars(select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(250))
            )
            return render(request, session, "audit", events=events, integrity=verify_chain(session))

    @app.get("/api/audit/verify")
    def audit_check(request: Request):
        with factory() as session:
            guard(request, session)
            return verify_chain(session)

    @app.get("/api/evidence/verify")
    def verify_all(request: Request):
        with factory() as session:
            guard(request, session)
            checked, invalid = 0, []
            for item in session.scalars(select(Interpretation)):
                extracted = extraction_data(session, item.document_id)
                for anchor in item.data["anchors"]:
                    if anchor["state"] == "verified":
                        checked += 1
                        if not recheck(anchor, extracted["text"], extracted["units"]):
                            invalid.append(item.id)
            return {"verified_anchors_checked": checked, "invalid": invalid, "valid": not invalid}

    @app.get("/export/{format}")
    def export(request: Request, format: str):
        with factory() as session:
            guard(request, session)
            rows = filtered(request, session)
            missing = [
                link
                for e in session.scalars(select(Extraction))
                for link in extraction_data(session, e.document_id)["links"]
                if link["state"] != "interpreted"
            ]
            notice = {
                "notice": NOTICE,
                "legal_reviews": sum(r["review_level"] == "legal" for r in rows),
                "missing_documents": missing,
                "data_types": sorted(
                    {"synthetic" if r["synthetic"] else "user_supplied" for r in rows}
                ),
            }
            if format == "json":
                return JSONResponse(
                    {**notice, "count": len(rows), "items": rows},
                    headers={"Content-Disposition": 'attachment; filename="athenix.json"'},
                )
            if format == "html":
                return templates.TemplateResponse(
                    request=request,
                    name="report.html",
                    context={"rows": rows, **notice},
                    headers={"Content-Disposition": 'attachment; filename="athenix.html"'},
                )
            if format != "csv":
                raise HTTPException(404)
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer)
            writer.writerow(
                [
                    "aviso",
                    "revisao_juridica",
                    "documentos_ausentes",
                    "tipo_dado",
                    "id",
                    "origem",
                    "arquivo_sha256",
                    "sujeito",
                    "acao",
                    "estado",
                    "faixa",
                    "nivel_revisao",
                    "prazos",
                    "evidencias",
                ]
            )

            def safe(value):
                value = str(value)
                return (
                    "'" + value
                    if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
                    else value
                )

            for row in rows:
                writer.writerow(
                    [
                        safe(v)
                        for v in (
                            NOTICE,
                            notice["legal_reviews"],
                            json.dumps(missing, ensure_ascii=False),
                            "sintético" if row["synthetic"] else "fornecido pelo usuário",
                            row["id"],
                            row["origin"],
                            row["file_sha256"],
                            row["subject"],
                            row["action"],
                            row["status"],
                            row["band"],
                            row["review_level"],
                            json.dumps(row["deadlines"], ensure_ascii=False),
                            json.dumps(row["anchors"], ensure_ascii=False),
                        )
                    ]
                )
            if not rows:
                writer.writerow(
                    [
                        NOTICE,
                        notice["legal_reviews"],
                        json.dumps(missing, ensure_ascii=False),
                        "sem resultados",
                    ]
                )
            return Response(
                "\ufeff" + buffer.getvalue(),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": 'attachment; filename="athenix.csv"'},
            )

    return app
