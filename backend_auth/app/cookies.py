from typing import Literal
from uuid import UUID

from fastapi import Response

from app.config import Settings

COOKIE_PATH = "/"
COOKIE_SAMESITE: Literal["lax"] = "lax"

REFRESH_COOKIE_NAME = "refresh"
DEVICE_ID_COOKIE_NAME = "device_id"
OAUTH_STATE_COOKIE_NAME = "state"


def _secure(settings: Settings) -> bool:
    return settings.prod


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        path=COOKIE_PATH,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=_secure(settings),
        max_age=settings.jwt.refresh_token_expire_days * 60 * 60 * 24,
    )


def set_device_id_cookie(response: Response, device_id: UUID, settings: Settings) -> None:
    response.set_cookie(
        key=DEVICE_ID_COOKIE_NAME,
        value=str(device_id),
        path=COOKIE_PATH,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=_secure(settings),
    )


def set_oauth_state_cookie(response: Response, state: UUID, settings: Settings) -> None:
    response.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        value=str(state),
        path=COOKIE_PATH,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=_secure(settings),
        max_age=settings.yandexid.confirmation_code_ttl,
    )


def delete_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=COOKIE_PATH,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=_secure(settings),
    )


def delete_oauth_state_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        path=COOKIE_PATH,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=_secure(settings),
    )
