import logging
from collections.abc import AsyncIterator
from typing import Annotated, cast
from uuid import UUID, uuid4

import jwt
import user_agents
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.rate_limiter import RedisFixedWindowRateLimiter, enforce_rate_limit, ip_per_route_rule
from app.config import Settings
from app.db.uow import UnitOfWork
from app.errors import InvalidTokenError, RefreshTokenMissingError
from app.models.user import User
from app.repositories.login_history_repository import LoginHistoryRepository
from app.repositories.oauth_account_repository import OAuthAccountRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import AccessTokenPayload
from app.schemas.misc import DeviceInfo, RequestMeta
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.services.yandexid_service import YandexIdService

logger = logging.getLogger(__name__)
oauth2_scheme = HTTPBearer()


def get_settings_from_app(request: Request) -> Settings:
    return request.app.state.settings


def get_client_ip(request: Request) -> str:
    settings: Settings = request.app.state.settings
    direct_client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if not forwarded_for or not settings.trust_proxy_headers:
        return direct_client_ip

    trusted_proxy_ips = settings.trusted_proxy_ip_set
    if trusted_proxy_ips and direct_client_ip not in trusted_proxy_ips:
        return direct_client_ip

    first_hop = forwarded_for.split(",")[0].strip()
    return first_hop or direct_client_ip


async def get_uow(request: Request) -> AsyncIterator[UnitOfWork]:
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield UnitOfWork(session)


def get_request_meta(request: Request) -> RequestMeta:
    return RequestMeta(
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )


def get_or_create_device_id(request: Request) -> UUID:
    raw_device_id = request.cookies.get("device_id")
    if not raw_device_id:
        return uuid4()
    try:
        return UUID(raw_device_id)
    except ValueError:
        return uuid4()


def get_device_info(
    device_id: Annotated[UUID, Depends(get_or_create_device_id)],
    request_meta: Annotated[RequestMeta, Depends(get_request_meta)],
) -> DeviceInfo:
    if request_meta.user_agent:
        device = user_agents.parse(request_meta.user_agent).device
        device_name = f"{device.family} {device.brand} {device.model}".strip()
    else:
        device_name = None
    return DeviceInfo(device_id=device_id, device_name=device_name)


def get_refresh_token(request: Request) -> str:
    refresh_token = request.cookies.get("refresh")
    if not refresh_token:
        raise RefreshTokenMissingError()
    return refresh_token


def get_rate_limiter(request: Request) -> RedisFixedWindowRateLimiter:
    redis: Redis = request.app.state.redis
    settings: Settings = request.app.state.settings
    return RedisFixedWindowRateLimiter(redis=redis, settings=settings.rate_limit)


async def rate_limit_route_by_ip(
    request: Request,
    limiter: Annotated[RedisFixedWindowRateLimiter, Depends(get_rate_limiter)],
) -> None:
    settings: Settings = request.app.state.settings
    route = request.scope.get("route")
    route_path = getattr(route, "path", request.url.path)
    route_key = f"{request.method}:{route_path}"
    await enforce_rate_limit(
        rule=ip_per_route_rule(settings.rate_limit),
        identity=f"{get_client_ip(request)}:{route_key}",
        limiter=limiter,
        enabled=settings.rate_limit.enabled,
    )


UowDependency = Annotated[UnitOfWork, Depends(get_uow)]
SettingsDependency = Annotated[Settings, Depends(get_settings_from_app)]


def get_auth_service(uow: UowDependency, request: Request) -> AuthService:
    settings: Settings = request.app.state.settings
    redis: Redis = request.app.state.redis
    return AuthService(
        UserRepository(uow),
        LoginHistoryRepository(uow),
        redis,
        settings.jwt,
    )


def get_user_service(uow: UowDependency) -> UserService:
    return UserService(UserRepository(uow), LoginHistoryRepository(uow))


def get_yandexid_service(uow: UowDependency, request: Request) -> YandexIdService:
    settings: Settings = request.app.state.settings
    redis: Redis = request.app.state.redis
    return YandexIdService(
        UserRepository(uow),
        OAuthAccountRepository(uow),
        LoginHistoryRepository(uow),
        redis,
        settings,
    )


def get_access_token_payload(
    token: Annotated[HTTPAuthorizationCredentials, Depends(oauth2_scheme)],
    request: Request,
) -> AccessTokenPayload:
    settings: Settings = request.app.state.settings
    try:
        payload = cast(
            dict[str, object],
            jwt.decode(
                token.credentials,
                settings.jwt.public_key,
                algorithms=[settings.jwt.algorithm],
            ),
        )
    except jwt.ExpiredSignatureError:
        raise InvalidTokenError("Token has expired") from None
    except jwt.InvalidTokenError as exc:
        logger.error("Invalid token: %s", exc)
        raise InvalidTokenError() from None

    try:
        validated_payload = AccessTokenPayload.model_validate(payload)
    except ValidationError:
        raise InvalidTokenError("Invalid token payload") from None
    if validated_payload.type != "access":
        raise InvalidTokenError("Token is not an access token")
    return validated_payload


async def get_token_user(
    payload: Annotated[AccessTokenPayload, Depends(get_access_token_payload)],
    uow: UowDependency,
) -> User:
    user = await UserRepository(uow).get_by_id(payload.sub)
    if not user:
        raise InvalidTokenError("User not found")
    if payload.tv != user.token_version:
        raise InvalidTokenError("Token version mismatch")
    return user


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]
UserServiceDependency = Annotated[UserService, Depends(get_user_service)]
YandexIdServiceDependency = Annotated[YandexIdService, Depends(get_yandexid_service)]
TokenUserDependency = Annotated[User, Depends(get_token_user)]
RequestMetaDependency = Annotated[RequestMeta, Depends(get_request_meta)]
DeviceInfoDependency = Annotated[DeviceInfo, Depends(get_device_info)]
RefreshTokenDependency = Annotated[str, Depends(get_refresh_token)]
RateLimited = Annotated[None, Depends(rate_limit_route_by_ip)]
