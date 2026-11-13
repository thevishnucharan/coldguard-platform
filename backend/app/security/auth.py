import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pre-computed hash used to equalise timing when the e-mail does not exist
_DUMMY_HASH = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


def dummy_verify() -> None:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = pwd_context.hash("timing-equaliser")
    pwd_context.verify("not-the-password", _DUMMY_HASH)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(user_id: uuid.UUID, expires_delta: Optional[timedelta] = None, extra: Optional[dict] = None) -> str:
    """Access token carries only identity. Role/permissions are re-read from the DB on every
    request so a client can never elevate itself by editing token claims."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": str(user_id), "typ": "access", "iat": int(now.timestamp()), "exp": expire,
               "jti": uuid.uuid4().hex}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("typ") != "access":
        raise ValueError("wrong token type")
    return payload


def new_refresh_token() -> tuple[str, str]:
    """Returns (plain_token, sha256_hash). Only the hash is stored."""
    token = secrets.token_urlsafe(48)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_device_key(key: str) -> str:
    return hashlib.sha256(("device:" + key).encode("utf-8")).hexdigest()
