from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

import jwt

from tests.functional.settings import tests_settings

DEFAULT_USER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_USER_ID = UUID("22222222-2222-4222-8222-222222222222")


def _private_key() -> bytes:
    return Path(tests_settings.jwt_private_key_path).read_bytes()


def mint_token(
    *,
    sub: UUID = DEFAULT_USER_ID,
    token_type: Literal["access", "refresh"] = "access",
    tv: int = 1,
    is_superuser: bool = False,
    expires_in_seconds: int = 1800,
    extra: dict[str, Any] | None = None,
    private_key: bytes | None = None,
    algorithm: str | None = None,
    omit: set[str] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "type": token_type,
        "sub": str(sub),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
        "jti": str(uuid4()),
        "tv": tv,
        "is_superuser": is_superuser,
    }
    if token_type == "refresh":
        payload.pop("is_superuser", None)
    if extra:
        payload.update(extra)
    if omit:
        for key in omit:
            payload.pop(key, None)
    return jwt.encode(
        payload,
        private_key or _private_key(),
        algorithm=algorithm or tests_settings.jwt_algorithm,
    )


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}
