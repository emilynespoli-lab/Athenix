import socket

import pytest
from fastapi.testclient import TestClient

from athenix.app import create_app
from athenix.config import Settings
from athenix.services import run_one


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    original_connect = socket.socket.connect

    def blocked(*args, **kwargs):
        raise AssertionError("Rede proibida na suíte; use transporte falso explícito.")

    monkeypatch.setattr(socket, "create_connection", blocked)

    def local_only(sock, address):
        # Windows asyncio creates a loopback socket pair for its own event loop.
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        return blocked()

    monkeypatch.setattr(socket.socket, "connect", local_only)


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        model="",
        api_key="",
        input_price="",
        output_price="",
        price_source="",
        price_date="",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        nonce = app.state.setup_nonce
        response = client.post(
            "/setup",
            data={"nonce": nonce, "username": "analista", "password": "sintetico-teste-2026"},
        )
        assert response.status_code == 200
        response = client.post(
            "/api/login", json={"username": "analista", "password": "sintetico-teste-2026"}
        )
        assert response.status_code == 200
        csrf = response.json()["csrf"]
        client.headers["x-csrf-token"] = csrf
        yield app, client, settings


def drain(app, settings):
    count = 0
    while run_one(app.state.factory, settings):
        count += 1
        assert count < 30


def upload(env, content, role="norm", **extra):
    app, client, settings = env
    response = client.post(
        "/api/documents",
        files={"file": ("renomeado.pdf", content, "application/pdf")},
        data={
            "title": "Corpus sintético",
            "origin": "Fixture sintética nova",
            "role": role,
            **extra,
        },
    )
    assert response.status_code == 200, response.text
    drain(app, settings)
    return response.json()


def propose(env, content=None, role="norm", **extra):
    app, client, settings = env
    content = (
        content
        or "<html><body>Publicado em 04/11/2026.<p>Art. 1º As distribuidoras deverão manter registros auditáveis por 20 dias contados da publicação.</p></body></html>".encode()
    )
    doc = upload(env, content, role, **extra)
    response = client.post(f"/api/documents/{doc['id']}/runs", json={"kind": "rules"})
    assert response.status_code == 200, response.text
    drain(app, settings)
    return doc, client.get("/api/obligations").json()["items"]
