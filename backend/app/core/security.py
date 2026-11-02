from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def get_jwt_secret() -> str:
    if settings.jwt_secret_key is None:
        raise RuntimeError("JWT_SECRET_KEY is not configured")

    secret = settings.jwt_secret_key.get_secret_value()

    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")

    return secret


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(UTC)

    payload = {
        "sub": str(user_id),
        "iss": "opspilot",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }

    return jwt.encode(
        payload,
        get_jwt_secret(),
        algorithm="HS256",
    )


def decode_user_id(token: str) -> UUID:
    payload = jwt.decode(
        token,
        get_jwt_secret(),
        algorithms=["HS256"],
        issuer="opspilot",
        options={"require": ["sub", "iss", "iat", "exp"]},
    )

    try:
        return UUID(payload["sub"])
    except (ValueError, TypeError, KeyError) as exc:
        raise InvalidTokenError("Invalid token subject") from exc
