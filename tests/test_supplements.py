from sqlalchemy import select

from athenix import llm
from athenix.db import Finding, Run
from athenix.services import extraction_data, recover_stale
from conftest import drain, propose, upload
from test_proposals_ai import candidate, configured


def test_human_finding_requires_literal_and_cannot_self_confirm(env):
    app, client, _ = env
    _, rows = propose(env)
    item = rows[0]
    endpoint = f"/api/obligations/{item['id']}/findings"
    base = {
        "kind": "subject_mismatch",
        "unit_id": item["anchors"][0]["unit_id"],
        "quote": "",
        "explanation": "Contestação sintética",
        "state": "confirmed",
    }
    assert client.post(endpoint, json=base).status_code == 400
    result = client.post(endpoint, json=base | {"quote": item["anchors"][0]["quote"]})
    assert result.status_code == 200 and result.json()["state"] == "inconclusive"
    with app.state.factory() as session:
        assert session.scalar(select(Finding)).data["evidence"]["state"] == "verified"
    # The finding advances the revision token: a stale review cannot silently accept it.
    assert (
        client.post(
            f"/api/obligations/{item['id']}/review",
            json={
                "action": "accept",
                "review_type": "technical",
                "reason": "Antes do novo achado",
                "expected_count": 0,
            },
        ).status_code
        == 400
    )


def test_dependency_obtained_and_interpreted_are_distinct(env):
    app, client, settings = env
    source = upload(
        env,
        b'<html><p>Art. 1 As empresas devem usar o Anexo I.</p><a href="https://example.invalid/a">Anexo I</a></html>',
    )
    target = upload(env, b"<html><p>Art. 1 As empresas devem manter os dados completos.</p></html>")
    endpoint = f"/api/documents/{source['id']}/dependencies"
    result = client.post(
        endpoint,
        json={
            "link_id": "link-0",
            "target_id": target["id"],
            "reason": "Correspondência manual sintética",
        },
    )
    assert result.status_code == 200
    with app.state.factory() as session:
        link = extraction_data(session, source["id"])["links"][0]
        assert link["state"] == "obtained" and link["target_hash"] == target["sha256"]
    client.post(f"/api/documents/{target['id']}/runs", json={"kind": "rules"})
    drain(app, settings)
    with app.state.factory() as session:
        assert extraction_data(session, source["id"])["links"][0]["state"] == "interpreted"


def test_stale_paid_job_not_automatically_retried(env):
    app, _, _ = env
    doc, _ = propose(env)
    with app.state.factory.begin() as session:
        for kind in ("rules", "ai"):
            session.add(
                Run(
                    document_id=doc["id"],
                    key=kind * 3,
                    kind=kind,
                    state="running",
                    updated="2020-01-01T00:00:00+00:00",
                    parameters={},
                )
            )
    assert recover_stale(app.state.factory) == 2
    with app.state.factory() as session:
        assert session.scalar(select(Run).where(Run.key == "ai" * 3)).state == "interrupted"
        assert session.scalar(select(Run).where(Run.key == "rules" * 3)).state == "queued"


def test_cache_across_different_artifacts_same_text_and_request(env, monkeypatch):
    app, client, settings = env
    configured(settings)
    base = "<html><p>Art. 1º As empresas deverão enviar relatórios completos.</p><script>var x=VALUE</script></html>"
    first = upload(env, base.replace("VALUE", "1").encode())
    second = upload(env, base.replace("VALUE", "2").encode())
    with app.state.factory() as session:
        extracted = extraction_data(session, first["id"])
    calls = []

    def fake(*_):
        import json

        calls.append(1)
        return {
            "status": "complete",
            "raw": {
                "model": settings.model,
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps({"items": [candidate(extracted)]})},
                    }
                ],
            },
        }

    monkeypatch.setattr(llm, "call_model", fake)
    for document in (first, second):
        assert (
            client.post(
                f"/api/documents/{document['id']}/runs",
                json={"kind": "ai", "budget": "1", "confirm_paid": True},
            ).status_code
            == 200
        )
        drain(app, settings)
    assert len(calls) == 1
