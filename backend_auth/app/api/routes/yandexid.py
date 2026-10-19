from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse

from app.api.dependencies import (
    DeviceInfoDependency,
    RateLimited,
    RequestMetaDependency,
    SettingsDependency,
    YandexIdServiceDependency,
)
from app.cookies import (
    delete_oauth_state_cookie,
    set_device_id_cookie,
    set_oauth_state_cookie,
    set_refresh_cookie,
)
from app.errors import YandexIdStateError
from app.schemas.auth import AccessTokenResponse

router = APIRouter(prefix="/yandexid", tags=["yandexid"])


def generate_login_state() -> UUID:
    return uuid4()


def validate_login_state(request: Request, state: UUID) -> None:
    cookie_state_raw = request.cookies.get("state")
    if not cookie_state_raw:
        raise YandexIdStateError("Cookie state is invalid or expired")
    try:
        cookie_state = UUID(cookie_state_raw)
    except ValueError:
        raise YandexIdStateError("Cookie state is invalid or expired") from None
    if state != cookie_state:
        raise YandexIdStateError("Login state is invalid or expired")


@router.get("/login")
async def oauth_login(
    _rate_limited: RateLimited,
    yandexid_service: YandexIdServiceDependency,
    settings: SettingsDependency,
    state: Annotated[UUID, Depends(generate_login_state)],
) -> RedirectResponse:
    redirect_url = await yandexid_service.build_login_redirect(state)
    response = RedirectResponse(url=redirect_url, status_code=302)
    set_oauth_state_cookie(response, state, settings)
    return response


@router.get("/token")
async def confirm_login_yandex(
    response: Response,
    code: str,
    state: UUID,
    _rate_limited: RateLimited,
    _validate_login_state: Annotated[None, Depends(validate_login_state)],
    request_meta: RequestMetaDependency,
    device_info: DeviceInfoDependency,
    yandexid_service: YandexIdServiceDependency,
    settings: SettingsDependency,
) -> AccessTokenResponse:
    tokens = await yandexid_service.authorize(
        code=code,
        state=state,
        request_meta=request_meta,
        device_info=device_info,
    )
    delete_oauth_state_cookie(response, settings)
    set_device_id_cookie(response, device_info.device_id, settings)
    set_refresh_cookie(response, tokens.refresh, settings)
    return AccessTokenResponse(access=tokens.access)
