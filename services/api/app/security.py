"""Primitivas de segurança: senhas, JWT, TOTP (MFA), cifragem de segredos, URLs assinadas.

- Senhas: Argon2id (nunca guardamos a senha, só o hash).
- JWT: curta duração (15 min). Refresh tokens são opacos, guardados só como hash SHA-256
  e rotacionados a cada uso (reuso de token antigo revoga a família inteira).
- Cifragem de segredos de provedores: Fernet (AES-128-CBC + HMAC).
"""
import base64
import hashlib
import hmac
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from cryptography.fernet import Fernet

from .config import get_settings

settings = get_settings()
_ph = PasswordHasher()

# Hash "isca" para gastar o mesmo tempo quando o e-mail não existe (evita enumeração por tempo).
_DUMMY_HASH = _ph.hash("dummy-password-for-timing")


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str | None) -> bool:
    try:
        return _ph.verify(hashed or _DUMMY_HASH, pw) and hashed is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def validate_password_strength(pw: str) -> str | None:
    """Retorna mensagem de erro se a senha for fraca; None se ok."""
    if len(pw) < 12:
        return "A senha precisa ter pelo menos 12 caracteres."
    if pw.lower() == pw or pw.upper() == pw:
        return "Use letras maiúsculas e minúsculas."
    if not any(c.isdigit() for c in pw):
        return "Inclua pelo menos um número."
    return None


# ---------------- JWT ----------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, *, mfa: bool = False, extra: dict | None = None,
                        minutes: int | None = None) -> str:
    payload = {
        "iss": settings.jwt_issuer,
        "sub": user_id,
        "typ": "access",
        "mfa": mfa,
        "jti": uuid.uuid4().hex,
        "iat": _now(),
        "exp": _now() + timedelta(minutes=minutes or settings.access_token_minutes),
        **(extra or {}),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str, expected_typ: str) -> dict:
    """Decodifica e valida. Levanta jwt.PyJWTError se inválido/expirado/tipo errado."""
    data = jwt.decode(
        token, settings.jwt_secret, algorithms=["HS256"],  # algoritmo fixo: evita 'alg=none'
        issuer=settings.jwt_issuer, options={"require": ["exp", "iss", "sub"]},
    )
    if data.get("typ") != expected_typ:
        raise jwt.InvalidTokenError("tipo de token incorreto")
    return data


def create_listener_token(session_id: str, tenant_id: str) -> str:
    """Token de ouvinte (público) limitado a UMA sessão, só leitura."""
    payload = {
        "iss": settings.jwt_issuer, "sub": f"listener:{uuid.uuid4().hex}", "typ": "listener",
        "sid": session_id, "tid": tenant_id,
        "exp": _now() + timedelta(minutes=settings.listener_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_ingest_token(session_id: str, tenant_id: str, minutes: int = 240) -> str:
    """Token efêmero de ingestão de áudio, por sessão (spec: per-event ephemeral token)."""
    payload = {
        "iss": settings.jwt_issuer, "sub": f"ingest:{uuid.uuid4().hex}", "typ": "ingest",
        "sid": session_id, "tid": tenant_id, "exp": _now() + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


# ---------------- Refresh tokens (opacos) ----------------
def new_refresh_token() -> tuple[str, str]:
    """Retorna (token_para_o_cliente, hash_para_o_banco)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------- TOTP / MFA ----------------
def new_totp_secret() -> str:
    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="SelaVoice")


# ---------------- Cifragem de segredos ----------------
def _fernet() -> Fernet:
    key = settings.encryption_key
    if not key:  # somente dev/teste: deriva chave do jwt_secret
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


# ---------------- URLs de mídia assinadas ----------------
def _media_key() -> bytes:
    return (settings.media_signing_secret or settings.jwt_secret).encode()


def sign_media_url(path: str, tenant_id: str, ttl_seconds: int = 300) -> dict:
    """Gera parâmetros (exp, sig) para acesso temporário a um arquivo do tenant."""
    exp = int(time.time()) + ttl_seconds
    msg = f"{tenant_id}|{path}|{exp}".encode()
    sig = hmac.new(_media_key(), msg, hashlib.sha256).hexdigest()
    return {"exp": exp, "sig": sig}


def verify_media_url(path: str, tenant_id: str, exp: int, sig: str) -> bool:
    if exp < time.time():
        return False
    msg = f"{tenant_id}|{path}|{exp}".encode()
    good = hmac.new(_media_key(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, sig)


def gen_join_code() -> str:
    """Código curto e imprevisível para o link/QR público do evento."""
    return secrets.token_urlsafe(8).replace("-", "x").replace("_", "y")[:10].lower()
