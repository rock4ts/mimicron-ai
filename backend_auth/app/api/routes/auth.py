from fastapi import APIRouter, Response, status

from app.api.dependencies import (
    AuthServiceDependency,
    DeviceInfoDependency,
    RateLimited,
    RefreshTokenDependency,
    RequestMetaDependency,
    SettingsDependency,
    TokenUserDependency,
)
from app.cookies import delete_refresh_cookie, set_device_id_cookie, set_refresh_cookie
from app.schemas.auth import AccessTokenResponse, UserLoginData

router = APIRouter(tags=["auth"])


@router.post("/token")
async def issue_tokens(
    response: Response,
    login_data: UserLoginData,
    _rate_limited: RateLimited,
    request_meta: RequestMetaDependency,
    device_info: DeviceInfoDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
) -> AccessTokenResponse:
    tokens = await auth_service.login_user(login_data, request_meta, device_info)
    set_refresh_cookie(response, tokens.refresh, settings)
    set_device_id_cookie(response, device_info.device_id, settings)
    return AccessTokenResponse(access=tokens.access)


@router.post("/refresh")
async def refresh_tokens(
    response: Response,
    _rate_limited: RateLimited,
    refresh_token: RefreshTokenDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
) -> AccessTokenResponse:
    tokens = await auth_service.refresh_tokens(refresh_token)
    set_refresh_cookie(response, tokens.refresh, settings)
    return AccessTokenResponse(access=tokens.access)


@router.post("/logout")
async def logout(
    response: Response,
    _rate_limited: RateLimited,
    refresh_token: RefreshTokenDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
) -> Response:
    await auth_service.logout(refresh_token)
    delete_refresh_cookie(response, settings)
    response.status_code = status.HTTP_200_OK
    return response


@router.post("/logout-others")
async def logout_others(
    response: Response,
    _rate_limited: RateLimited,
    user: TokenUserDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
) -> AccessTokenResponse:
    tokens = await auth_service.logout_others(user)
    set_refresh_cookie(response, tokens.refresh, settings)
    return AccessTokenResponse(access=tokens.access)
