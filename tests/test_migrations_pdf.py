from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic import command
from alembic.config import Config
from pathlib import Path
import pytest
from sqlalchemy import inspect, select, text

from athenix.config import Settings
from athenix.db import Artifact, AuditHead, Base, Interpretation, database, initialize, verify_chain
from athenix.auth import create_user
from athenix.services import receive
from athenix.structure import extract
from conftest import propose
from pdf_helpers import synthetic_pdf


def test_versioned_schema_matches_models(tmp_path):
    engine, _ = database(f"sqlite:///{tmp_path / 'discardable.db'}")
    initialize(engine)
    initialize(engine)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
        assert "call_claims" in inspect(connection).get_table_names()
    engine.dispose()


def test_pdf_extraction_offsets_and_no_text_warning():
    value = extract(synthetic_pdf(), "application/pdf", Settings())
    assert "Art. 1" in value["text"]
    assert len(value["pages"]) == 1
    assert all(u["text"] == value["text"][u["start"] : u["end"]] for u in value["units"])
    scan = extract(synthetic_pdf(scanned=True), "application/pdf", Settings())
    assert scan["text"] == ""
    assert any("requer OCR" in w for w in scan["warnings"])


def test_pdf_end_to_end(env):
    app, client, _ = env
    _, rows = propose(env, synthetic_pdf())
    assert len(rows) == 1 and rows[0]["anchors"][0]["state"] == "verified"
    with app.state.factory() as session:
        assert len(list(session.scalars(select(Interpretation)))) == 1
    assert client.get("/api/evidence/verify").json()["valid"]


def test_additive_upgrade_preserves_populated_history(tmp_path):
    root = Path(__file__).resolve().parent.parent
    engine, factory = database(f"sqlite:///{tmp_path / 'migration-test.db'}")
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001")
        connection.execute(AuditHead.__table__.insert().values(id=1, hash="0" * 64, revision=0))
    raw = b"<html>Art. 1 As empresas devem manter todos os registros.</html>"
    with factory.begin() as session:
        user = create_user(session, "migracao", "senha-sintetica-migracao")
        document, _ = receive(
            session, Settings(), raw, "Migracao", "Sintetico", "norm", "", user.id
        )
        hashed = document.artifact_id
    initialize(engine)
    with factory() as session:
        assert session.get(Artifact, hashed).content == raw
        assert verify_chain(session)["valid"]
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        with pytest.raises(RuntimeError, match="Downgrade"):
            command.downgrade(config, "base")
    with factory() as session:
        assert session.get(Artifact, hashed).content == raw
    engine.dispose()
