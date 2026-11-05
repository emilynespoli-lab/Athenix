from conftest import propose


def test_correction_form_uses_domain_fields(env):
    _, client, _ = env
    _, rows = propose(env)
    item = rows[0]
    response = client.post(
        f"/obligations/{item['id']}/review",
        data={
            "action": "correct",
            "expected_count": "0",
            "reason": "Objeto explicitado pela interface",
            "correction_subject": item["subject"],
            "correction_modality": item["modality"],
            "correction_action": item["action"],
            "correction_object": "registros auditáveis",
            "correction_conditions": "",
            "correction_exceptions": "",
            "anchor_count": "1",
            "anchor_unit_0": item["evidence"][0]["unit_id"],
            "anchor_quote_0": item["evidence"][0]["quote"],
        },
    )
    assert response.status_code == 200
    current = client.get("/api/obligations").json()["items"][0]
    assert current["version"] == 2 and current["object"] == "registros auditáveis"
    assert current["status"] == "pending_review"


def test_confirmed_objection_requires_separate_human_resolution(env):
    _, client, _ = env
    _, rows = propose(
        env,
        "<html><p>Art. 1º As empresas poderão enviar documentos complementares.</p></html>".encode(),
    )
    item = rows[0]
    candidate = {
        k: item[k]
        for k in ("subject", "modality", "action", "object", "conditions", "exceptions", "evidence")
    }
    candidate["modality"] = "duty"
    response = client.post(
        f"/api/obligations/{item['id']}/review",
        json={
            "action": "correct",
            "review_type": "technical",
            "reason": "Contraste sintético faculdade versus dever",
            "expected_count": 0,
            "candidate": candidate,
        },
    )
    successor = response.json()["data"]["successor"]
    current = client.get("/api/obligations").json()["items"][0]
    objection = next(o for o in current["objections"] if o["state"] == "confirmed")
    endpoint = f"/api/obligations/{successor}/review"
    base = {
        "review_type": "technical",
        "reason": "Decisão técnica de teste, sem mérito jurídico",
        "expected_count": 0,
    }
    assert client.post(endpoint, json=base | {"action": "accept"}).status_code == 400
    assert (
        client.post(
            endpoint, json=base | {"action": "resolve", "objection_id": objection["id"]}
        ).status_code
        == 200
    )
    assert (
        client.post(endpoint, json=base | {"action": "accept", "expected_count": 1}).status_code
        == 200
    )
    finding = client.post(
        f"/api/obligations/{successor}/findings",
        json={
            "kind": "unsupported_modality",
            "unit_id": current["anchors"][0]["unit_id"],
            "quote": current["anchors"][0]["quote"],
            "explanation": "Novo achado após o aceite técnico",
        },
    )
    assert finding.status_code == 200 and finding.json()["state"] == "confirmed"
    assert client.get("/api/obligations").json()["items"][0]["status"] == "pending_review"


def test_deadline_confirmation_is_separate_event(env):
    _, client, _ = env
    _, rows = propose(env)
    item = rows[0]
    assert item["deadlines"][0]["state"] == "provisional"
    response = client.post(
        f"/api/obligations/{item['id']}/review",
        json={
            "action": "confirm_deadline",
            "review_type": "technical",
            "reason": "Confirmação técnica da convenção sintética",
            "expected_count": 0,
            "index": 0,
        },
    )
    assert response.status_code == 200
    current = client.get("/api/obligations").json()["items"][0]
    assert current["deadlines"][0]["state"] == "confirmed"
    assert current["deadlines"][0]["confirmation_level"] == "technical"


def test_missing_dependency_requires_explicit_decision(env):
    _, client, _ = env
    _, rows = propose(
        env,
        "<html><p>Art. 1º As empresas deverão aplicar os requisitos do Anexo I.</p></html>".encode(),
    )
    item = rows[0]
    assert item["band"] == "attention"
    response = client.post(
        f"/api/obligations/{item['id']}/review",
        json={
            "action": "accept",
            "review_type": "technical",
            "reason": "Tentativa sem tratar dependência",
            "expected_count": 0,
        },
    )
    assert response.status_code == 400 and "Dependência" in response.text
