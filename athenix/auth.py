import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .db import LoginSession, User, audit


def password_hash(password, salt=None):
    if len(password) < 12:
        raise ValueError("A senha precisa de pelo menos 12 caracteres.")
    salt = salt or secrets.token_hex(16)
    result = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"scrypt:{salt}:{result.hex()}"


def check_password(password, stored):
    try:
        _, salt, expected = stored.split(":")
        result = password_hash(password, salt).split(":")[-1]
        return secrets.compare_digest(result, expected)
    except (ValueError, TypeError):
        return False


def create_user(session, username, password, role="technical"):
    username = username.strip()
    if not username or len(username) > 100 or role not in {"operator", "technical", "legal"}:
        raise ValueError("Usuário ou papel inválido.")
    if session.scalar(select(User).where(User.username == username)):
        raise ValueError("Usuário já existe.")
    user = User(username=username, password_hash=password_hash(password), role=role)
    session.add(user)
    session.flush()
    audit(session, user.id, "user.created", user.id, {"username": username, "role": role})
    return user


def login(session, username, password, hours):
    user = session.scalar(select(User).where(User.username == username))
    if not user or not check_password(password, user.password_hash):
        # Uniform KDF on unknown users reduces username timing disclosure.
        if not user:
            hashlib.scrypt(b"invalid-password", salt=b"athenix-login-v1", n=16384, r=8, p=1)
        raise ValueError("Usuário ou senha inválidos.")
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    session.add(
        LoginSession(
            id=hashlib.sha256(token.encode()).hexdigest(),
            user_id=user.id,
            csrf=csrf,
            expires=(datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(),
        )
    )
    audit(session, user.id, "session.created", user.id, {})
    return token, csrf, user


def authenticate(session, token):
    if not token:
        return None, None
    record = session.get(LoginSession, hashlib.sha256(token.encode()).hexdigest())
    if not record or datetime.fromisoformat(record.expires) < datetime.now(timezone.utc):
        return None, None
    return session.get(User, record.user_id), record
