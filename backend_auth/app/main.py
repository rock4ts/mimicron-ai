import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, RedirectResponse, Response
from redis.asyncio import Redis

from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.yandexid import router as yandexid_router
from app.config import Settings, get_settings
from app.db.session import create_engine_and_session_factory
from app.errors import (
    EmailAlreadyExistsError,
    InvalidTokenError,
    RateLimitExceededError,
    RateLimitStorageError,
    RefreshTokenError,
    RefreshTokenMissingError,
    UserAlreadyExistsError,
    UserNotFoundError,
    WrongCredentialsError,
    WrongPasswordError,
    YandexIdAccountConflictError,
    YandexIdProviderError,
    YandexIdStateError,
    YandexIdTokenError,
    YandexIdUserInfoError,
)
from app.logging import configure_logging

logger = logging.getLogger(__name__)


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    application_settings = settings or get_settings()
    configure_logging(application_settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        engine, session_factory = create_engine_and_session_factory(
            application_settings.postgres.url
        )
        redis = Redis(
            host=application_settings.redis.host,
            port=application_settings.redis.port,
        )
        application.state.session_factory = session_factory
        application.state.redis = redis
        application.state.settings = application_settings
        try:
            yield
        finally:
            await redis.aclose()
            await engine.dispose()

    application = FastAPI(
        title="Auth API",
        description="Identity service: JWT auth, users, Yandex ID OAuth, login history.",
        version="0.1.0",
        lifespan=lifespan,
        root_path=application_settings.root_path,
    )
    application.include_router(auth_router)
    application.include_router(users_router)
    application.include_router(yandexid_router)

    @application.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    @application.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.middleware("http")
    async def log_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        header_name = application_settings.request_id_header
        request_id = request.headers.get(header_name, str(uuid4()))
        started_at = time.perf_counter()
        response = await call_next(request)
        response.headers[header_name] = request_id
        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return response

    @application.exception_handler(WrongCredentialsError)
    async def wrong_credentials(_request: Request, exc: WrongCredentialsError) -> JSONResponse:
        return _unauthorized(str(exc))

    @application.exception_handler(RefreshTokenError)
    async def refresh_token_error(_request: Request, _exc: RefreshTokenError) -> JSONResponse:
        return _unauthorized("Invalid refresh token")

    @application.exception_handler(RefreshTokenMissingError)
    async def refresh_token_missing(
        _request: Request, exc: RefreshTokenMissingError
    ) -> JSONResponse:
        return _unauthorized(str(exc))

    @application.exception_handler(InvalidTokenError)
    async def invalid_token(_request: Request, exc: InvalidTokenError) -> JSONResponse:
        return _unauthorized(str(exc))

    @application.exception_handler(UserAlreadyExistsError)
    async def user_already_exists(_request: Request, exc: UserAlreadyExistsError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc)},
        )

    @application.exception_handler(EmailAlreadyExistsError)
    async def email_already_exists(_request: Request, exc: EmailAlreadyExistsError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc)},
        )

    @application.exception_handler(WrongPasswordError)
    async def wrong_password(_request: Request, exc: WrongPasswordError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Wrong password"},
        )

    @application.exception_handler(UserNotFoundError)
    async def user_not_found(_request: Request, _exc: UserNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "User not found"},
        )

    @application.exception_handler(RateLimitExceededError)
    async def rate_limited(_request: Request, exc: RateLimitExceededError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": str(exc)},
            headers={"Retry-After": str(max(1, exc.retry_after_seconds))},
        )

    @application.exception_handler(RateLimitStorageError)
    async def rate_limit_storage(_request: Request, exc: RateLimitStorageError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": str(exc)},
        )

    @application.exception_handler(YandexIdStateError)
    async def yandex_state(_request: Request, exc: YandexIdStateError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc)},
        )

    @application.exception_handler(YandexIdTokenError)
    async def yandex_token(_request: Request, _exc: YandexIdTokenError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "Error during token exchange with provider"},
        )

    @application.exception_handler(YandexIdUserInfoError)
    async def yandex_user_info(_request: Request, _exc: YandexIdUserInfoError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "Error during user profile fetch from provider"},
        )

    @application.exception_handler(YandexIdProviderError)
    async def yandex_provider(_request: Request, _exc: YandexIdProviderError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "OAuth provider is temporarily unavailable"},
        )

    @application.exception_handler(YandexIdAccountConflictError)
    async def yandex_conflict(_request: Request, exc: YandexIdAccountConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> Response:
        if isinstance(exc, HTTPException):
            return await http_exception_handler(request, exc)
        logger.error("unhandled_error", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    return application


app = create_app()
