from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from athenix.db import Artifact, AuditEvent, Decision, Interpretation, Run, User, verify_chain
from athenix.evidence import recheck
from athenix.services import enqueue, extraction_data, receive, run_one
from conftest import drain, propose, upload


def test_end_to_end_review_export_and_trace(env):
    app, client, settings = env
    doc, items = propose(env)
    assert len(items) == 1
    item = items[0]
    assert item["status"] == "detected" and item["anchors"][0]["state"] == "verified"
    response = client.post(
        f"/api/obligations/{item['id']}/review",
        json={
            "action": "accept",
            "review_type": "technical",
            "reason": "Conferência técnica sintética",
            "expected_count": 0,
            "user_id": "FORJADO",
        },
    )
    assert response.status_code == 200, response.text
    rows = client.get("/api/obligations").json()["items"]
    assert rows[0]["status"] == "validated" and rows[0]["review_level"] == "technical"
    with app.state.factory() as session:
        decision = session.scalars(select(Decision)).first()
        assert session.get(User, decision.user_id).username == "analista"
        extracted = extraction_data(session, doc["id"])
        assert all(recheck(a, extracted["text"], extracted["units"]) for a in item["anchors"])
    assert client.get("/api/audit/verify").json()["valid"]
    assert client.get("/api/evidence/verify").json()["invalid"] == []
    for path in (
        "/",
        "/documents",
        f"/documents/{doc['id']}",
        "/matrix",
        f"/obligations/{item['id']}",
        "/timeline",
        "/risks",
        "/audit",
    ):
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert "Estudo experimental" in response.text
    for format in ("csv", "json", "html"):
        result = client.get("/export/" + format)
        assert result.status_code == 200
        assert "Estudo experimental" in result.text
    assert client.get(f"/documents/{doc['id']}/original").content.startswith(b"<html>")


def test_upload_and_execution_idempotency(env):
    app, client, settings = env
    content = b"<html><p>Art. 1 As empresas devem preservar os registros.</p></html>"
    first = upload(env, content)
    second = upload(env, content)
    assert first["id"] == second["id"] and second["reused"]
    endpoint = f"/api/documents/{first['id']}/runs"
    a = client.post(endpoint, json={"kind": "rules"}).json()
    b = client.post(endpoint, json={"kind": "rules"}).json()
    assert a["id"] == b["id"] and b["reused"]
    drain(app, settings)


def test_unauthenticated_and_csrf_writes_refused(env):
    _, client, _ = env
    saved = client.cookies.get("athenix_session")
    client.cookies.clear()
    assert client.post("/api/documents", data={}).status_code == 401
    client.cookies.set("athenix_session", saved)
    client.headers.pop("x-csrf-token")
    assert client.post("/demo", data={}).status_code == 403


def test_legal_impersonation_reason_and_stale_decision(env):
    _, client, _ = env
    _, items = propose(env)
    endpoint = f"/api/obligations/{items[0]['id']}/review"
    base = {"action": "accept", "review_type": "legal", "reason": "teste", "expected_count": 0}
    assert client.post(endpoint, json=base).status_code == 400
    assert (
        client.post(endpoint, json=base | {"review_type": "technical", "reason": " "}).status_code
        == 400
    )
    assert client.post(endpoint, json=base | {"review_type": "technical"}).status_code == 200
    assert client.post(endpoint, json=base | {"review_type": "technical"}).status_code == 400


def test_correction_keeps_original_and_rechecks_evidence(env):
    app, client, _ = env
    _, items = propose(env)
    original = items[0]
    candidate = {
        k: original[k]
        for k in ("subject", "modality", "action", "object", "conditions", "exceptions", "evidence")
    }
    candidate["subject"] = "Sujeito corrigido pelo revisor"
    candidate["evidence"][0]["quote"] = "Este trecho não existe no texto recebido, portanto falha."
    response = client.post(
        f"/api/obligations/{original['id']}/review",
        json={
            "action": "correct",
            "review_type": "technical",
            "reason": "Regressão sintética de correção",
            "expected_count": 0,
            "candidate": candidate,
        },
    )
    assert response.status_code == 200, response.text
    successor = response.json()["data"]["successor"]
    assert (
        client.post(
            f"/api/obligations/{successor}/review",
            json={
                "action": "accept",
                "review_type": "technical",
                "reason": "tentativa",
                "expected_count": 0,
            },
        ).status_code
        == 400
    )
    with app.state.factory() as session:
        assert session.get(Interpretation, original["id"]).data["subject"] == original["subject"]
        assert session.get(Interpretation, successor).version == 2
        assert session.get(Interpretation, successor).data["anchors"][0]["state"] == "invalid"


def test_append_only_and_detect_tamper(env):
    app, _, _ = env
    propose(env)
    for table in (
        "artifacts",
        "documents",
        "extractions",
        "interpretations",
        "decisions",
        "model_responses",
        "audit_events",
    ):
        with app.state.factory() as session:
            # Trigger compilation is checked even if a table has no rows.
            trigger = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=:table"),
                {"table": table},
            ).all()
            assert len(trigger) == 2
    with app.state.factory.begin() as session:
        with pytest.raises(DBAPIError):
            session.execute(text("UPDATE artifacts SET size=0"))
    with app.state.engine.begin() as connection:
        connection.execute(text("DROP TRIGGER immutable_audit_events_update"))
        connection.execute(
            text("UPDATE audit_events SET hash=:hash WHERE sequence=1"), {"hash": "a" * 64}
        )
    with app.state.factory() as session:
        assert not verify_chain(session)["valid"]


def test_review_rollback_has_no_partial_audit(env):
    app, client, _ = env
    _, items = propose(env)
    with app.state.factory() as session:
        before = session.scalar(select(func.count()).select_from(AuditEvent))
    response = client.post(
        f"/api/obligations/{items[0]['id']}/review",
        json={"action": "accept", "review_type": "technical", "reason": "", "expected_count": 0},
    )
    assert response.status_code == 400
    with app.state.factory() as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == before


def test_concurrent_ingest_has_one_document(env):
    app, _, settings = env
    content = b"<html><p>Art. 1 As empresas devem manter registros.</p></html>"

    def ingest(_):
        with app.state.factory.begin() as session:
            doc, _ = receive(
                session, settings, content, "Concorrente", "Sintético", "norm", "", "teste"
            )
            return doc.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(ingest, range(2)))
    assert len(set(ids)) == 1


def test_concurrent_enqueue_and_workers_do_not_duplicate(env):
    app, _, settings = env
    doc = upload(env, b"<html><p>Art. 1 As empresas devem manter registros.</p></html>")

    def queue(_):
        with app.state.factory.begin() as session:
            run, _ = enqueue(session, doc["id"], "rules", "teste", settings)
            return run.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(queue, range(2)))
    assert len(set(ids)) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: run_one(app.state.factory, settings), range(2)))
    with app.state.factory() as session:
        assert session.get(Run, ids[0]).state == "completed"
        assert session.scalar(select(func.count()).select_from(Interpretation)) == 1


def test_csv_formula_escaping_and_html_escaping(env):
    _, client, _ = env
    propose(
        env,
        "<html><p>Art. 1º =SOMA(1) deve manter registros &lt;script&gt;alert(1)&lt;/script&gt;.</p></html>".encode(),
    )
    csv = client.get("/export/csv").text
    assert "'=SOMA" in csv
    response = client.get("/matrix")
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_origin_required_and_original_html_never_served_active(env):
    _, client, _ = env
    response = client.post(
        "/api/documents",
        data={"origin": "", "role": "norm"},
        files={"file": ("a.html", b"<html>dados</html>")},
    )
    assert response.status_code == 400
    doc = upload(env, b"<html><script>alert(1)</script>dados</html>")
    response = client.get(f"/documents/{doc['id']}/original")
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")


def test_failed_pdf_preserved_with_explicit_error(env):
    app, client, _ = env
    doc = upload(env, b"%PDF-1.7\ncorrompido")
    with app.state.factory() as session:
        run = session.scalars(select(Run).where(Run.document_id == doc["id"])).first()
        assert run.state == "failed"
        assert "corrompido" in run.result["error"]
        assert session.get(Artifact, doc["sha256"]).content == b"%PDF-1.7\ncorrompido"
    assert client.get(f"/documents/{doc['id']}").status_code == 200


def test_filters_and_timeline_match_database(env):
    _, client, _ = env
    propose(env)
    rows = client.get(
        "/api/obligations?band=ready&status=detected&deadline=provisional&subject=distribuidoras"
    ).json()["items"]
    assert len(rows) == 1
    assert "2026-11-24" in client.get("/timeline").text
    assert client.get("/api/obligations?origin=inexistente").json()["count"] == 0


def test_synthetic_demo_explicit(env):
    app, client, settings = env
    result = client.post("/demo", data={"csrf": client.headers["x-csrf-token"]})
    assert result.status_code == 200
    drain(app, settings)
    assert "SINTÉTICO" in client.get("/documents").text


def test_cross_origin_request_blocked(env):
    _, client, _ = env
    assert client.post("/demo", headers={"origin": "https://evil.invalid"}).status_code == 403
