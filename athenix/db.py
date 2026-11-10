import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
    event,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    raw = value if isinstance(value, bytes) else canonical(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(30), default="technical")


class LoginSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    csrf: Mapped[str] = mapped_column(String(64))
    expires: Mapped[str] = mapped_column(String(60))


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    media: Mapped[str] = mapped_column(String(30))
    size: Mapped[int] = mapped_column(Integer)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace: Mapped[str] = mapped_column(String(32), default="main")
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"), unique=True)
    title: Mapped[str] = mapped_column(String(250))
    role: Mapped[str] = mapped_column(String(30))
    origin: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, default="")
    created: Mapped[str] = mapped_column(String(60), default=now)
    related_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class Extraction(Base):
    __tablename__ = "extractions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), unique=True)
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[dict] = mapped_column(JSON)


class Interpretation(Base):
    __tablename__ = "interpretations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    obligation_id: Mapped[str] = mapped_column(String(32), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    predecessor: Mapped[str | None] = mapped_column(ForeignKey("interpretations.id"), nullable=True)
    data: Mapped[dict] = mapped_column(JSON)
    created: Mapped[str] = mapped_column(String(60), default=now)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    interpretation_id: Mapped[str] = mapped_column(ForeignKey("interpretations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    review_type: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON)
    created: Mapped[str] = mapped_column(String(60), default=now)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    interpretation_id: Mapped[str] = mapped_column(ForeignKey("interpretations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    data: Mapped[dict] = mapped_column(JSON)
    created: Mapped[str] = mapped_column(String(60), default=now)


class DependencyLink(Base):
    __tablename__ = "dependency_links"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    link_id: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(Text)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created: Mapped[str] = mapped_column(String(60), default=now)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    key: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(30), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    parameters: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[str] = mapped_column(String(60), default=now)
    updated: Mapped[str] = mapped_column(String(60), default=now)


class ModelResponse(Base):
    __tablename__ = "model_responses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    created: Mapped[str] = mapped_column(String(60), default=now)


class CallClaim(Base):
    __tablename__ = "call_claims"
    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    state: Mapped[str] = mapped_column(String(30), default="intent")
    created: Mapped[str] = mapped_column(String(60), default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    previous: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    data: Mapped[dict] = mapped_column(JSON)


class AuditHead(Base):
    __tablename__ = "audit_head"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hash: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=0)


IMMUTABLE = (
    "artifacts",
    "documents",
    "extractions",
    "interpretations",
    "decisions",
    "model_responses",
    "audit_events",
    "findings",
    "dependency_links",
)


def database(url):
    args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=args, pool_pre_ping=True)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def configure(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")

    return engine, sessionmaker(engine, expire_on_commit=False)


def install_guards(connection, tables=IMMUTABLE):
    for table in tables:
        if connection.dialect.name == "sqlite":
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()} "
                        f"BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'append-only'); END"
                    )
                )
        else:
            connection.execute(
                text(
                    "CREATE OR REPLACE FUNCTION athenix_immutable() RETURNS trigger LANGUAGE plpgsql "
                    "AS $$ BEGIN RAISE EXCEPTION 'append-only'; END; $$"
                )
            )
            connection.execute(text(f"DROP TRIGGER IF EXISTS immutable_guard ON {table}"))
            connection.execute(
                text(
                    f"CREATE TRIGGER immutable_guard BEFORE UPDATE OR DELETE ON {table} "
                    "FOR EACH ROW EXECUTE FUNCTION athenix_immutable()"
                )
            )


def initialize(engine):
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parent.parent
    configuration = Config(str(root / "alembic.ini"))
    configuration.set_main_option("script_location", str(root / "migrations"))
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(481709621)"))
        else:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        configuration.attributes["connection"] = connection
        command.upgrade(configuration, "head")
        if not connection.execute(select(AuditHead.id)).first():
            connection.execute(AuditHead.__table__.insert().values(id=1, hash="0" * 64, revision=0))


def audit(session, actor, kind, entity, payload):
    # Write serialization protects the head from forks, including concurrent workers.
    session.execute(text("UPDATE audit_head SET revision=revision+1 WHERE id=1"))
    head = session.get(AuditHead, 1, populate_existing=True)
    data = {"actor": actor, "kind": kind, "entity": entity, "payload": payload, "at": now()}
    hashed = digest({"previous": head.hash, "data": data})
    session.add(AuditEvent(previous=head.hash, hash=hashed, data=data))
    head.hash = hashed
    session.flush()


def verify_chain(session):
    previous = "0" * 64
    count = 0
    for item in session.scalars(select(AuditEvent).order_by(AuditEvent.sequence)):
        count += 1
        if item.previous != previous or item.hash != digest(
            {"previous": previous, "data": item.data}
        ):
            return {"valid": False, "broken_at": item.sequence, "events": count}
        previous = item.hash
    head = session.get(AuditHead, 1)
    return {"valid": head.hash == previous, "events": count, "head": previous}
