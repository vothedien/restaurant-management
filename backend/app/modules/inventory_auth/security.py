from datetime import UTC, datetime, timedelta
from functools import lru_cache
from secrets import token_bytes
from uuid import uuid4

import bcrypt
import jwt
from fastapi import HTTPException

from app.core.config import Settings

AUDIENCE = "inventory"
ISSUER = "restaurant-management/inventory-auth"


def signing_key(settings: Settings) -> str:
    secret = settings.inventory_jwt_secret_key
    key = secret.get_secret_value() if secret else ""
    if (
        len(key.encode("utf-8")) < 32
        or key == settings.jwt_secret_key
        or settings.inventory_jwt_algorithm != "HS256"
    ):
        raise HTTPException(503, "Inventory authentication is not configured")
    return key


@lru_cache(maxsize=1)
def _dummy_hash() -> bytes:
    # Similar password verification work even when the username does not exist.
    return bcrypt.hashpw(token_bytes(32), bcrypt.gensalt(rounds=10))


def verify_password(password: str, stored_hash: str | None) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > 72 or b"\0" in encoded:
        bcrypt.checkpw(b"invalid-password-length", _dummy_hash())
        return False
    try:
        matched = bcrypt.checkpw(
            encoded, stored_hash.encode("ascii") if stored_hash else _dummy_hash()
        )
        return matched and stored_hash is not None
    except (ValueError, UnicodeError):
        bcrypt.checkpw(encoded, _dummy_hash())
        return False


def issue_token(user_id: int, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "aud": AUDIENCE,
            "iss": ISSUER,
            "iat": now,
            "exp": now + timedelta(minutes=settings.inventory_access_token_expire_minutes),
            "jti": str(uuid4()),
        },
        signing_key(settings),
        algorithm="HS256",
    )


def decode_subject(token: str, settings: Settings) -> int:
    key = signing_key(settings)
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["HS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["sub", "aud", "iss", "iat", "exp", "jti"], "strict_aud": True},
        )
        subject = claims["sub"]
        if (
            not subject.isascii()
            or not subject.isdecimal()
            or not 0 < int(subject) <= 9223372036854775807
        ):
            raise ValueError("Invalid subject")
        if not claims["jti"] or type(claims["iat"]) is not int or type(claims["exp"]) is not int:
            raise ValueError("Invalid claims")
        return int(subject)
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError) as error:
        raise HTTPException(401, "Invalid or expired Inventory token") from error
