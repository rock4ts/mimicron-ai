from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, Response
from pydantic import BaseModel, Field

app = FastAPI(title="Yandex OAuth mock")


def _default_token_body() -> dict[str, Any]:
    return {
        "token_type": "bearer",
        "access_token": "mock-yandex-access-token",
        "expires_in": 3600,
        "refresh_token": "mock-yandex-refresh-token",
        "scope": "login:info",
    }


def _default_user_info_body() -> dict[str, Any]:
    return {
        "login": "yandex_user",
        "id": 100001,
        "client_id": "your-client-id",
        "psuid": "1.AAA.yandex_user",
        "default_email": "yandex_user@example.com",
        "first_name": "Yandex",
        "last_name": "User",
        "display_name": "Yandex User",
        "real_name": "Yandex User",
        "sex": "male",
    }


class ConfigureRequest(BaseModel):
    token_status: int | None = None
    token_body: dict[str, Any] | None = None
    token_delay_seconds: float | None = None
    user_info_status: int | None = None
    user_info_body: dict[str, Any] | None = None
    user_info_delay_seconds: float | None = None


class MockState:
    token_status: int = 200
    token_body: dict[str, Any] = _default_token_body()
    token_delay_seconds: float = 0.0
    user_info_status: int = 200
    user_info_body: dict[str, Any] = _default_user_info_body()
    user_info_delay_seconds: float = 0.0
    token_requests: int = 0
    user_info_requests: int = 0


state = MockState()


@app.get("/authorize")
async def authorize() -> dict[str, str]:
    return {"status": "mock_authorize_endpoint"}


@app.post("/token")
async def token() -> Response:
    state.token_requests += 1
    if state.token_delay_seconds > 0:
        await asyncio.sleep(state.token_delay_seconds)
    if state.token_status >= 400:
        return Response(
            content='{"error": "invalid_grant"}',
            status_code=state.token_status,
            media_type="application/json",
        )
    return Response(
        content=__import__("json").dumps(state.token_body),
        status_code=state.token_status,
        media_type="application/json",
    )


@app.get("/info")
async def user_info() -> Response:
    state.user_info_requests += 1
    if state.user_info_delay_seconds > 0:
        await asyncio.sleep(state.user_info_delay_seconds)
    if state.user_info_status >= 400:
        return Response(
            content='{"error": "internal_error"}',
            status_code=state.user_info_status,
            media_type="application/json",
        )
    return Response(
        content=__import__("json").dumps(state.user_info_body),
        status_code=state.user_info_status,
        media_type="application/json",
    )


class ConfigureResponse(BaseModel):
    token_requests: int
    user_info_requests: int


@app.post("/admin/reset")
async def admin_reset() -> ConfigureResponse:
    state.token_status = 200
    state.token_body = _default_token_body()
    state.token_delay_seconds = 0.0
    state.user_info_status = 200
    state.user_info_body = _default_user_info_body()
    state.user_info_delay_seconds = 0.0
    state.token_requests = 0
    state.user_info_requests = 0
    return ConfigureResponse(
        token_requests=state.token_requests,
        user_info_requests=state.user_info_requests,
    )


@app.post("/admin/configure")
async def admin_configure(payload: ConfigureRequest) -> ConfigureResponse:
    if payload.token_status is not None:
        state.token_status = payload.token_status
    if payload.token_body is not None:
        state.token_body = payload.token_body
    if payload.token_delay_seconds is not None:
        state.token_delay_seconds = payload.token_delay_seconds
    if payload.user_info_status is not None:
        state.user_info_status = payload.user_info_status
    if payload.user_info_body is not None:
        state.user_info_body = payload.user_info_body
    if payload.user_info_delay_seconds is not None:
        state.user_info_delay_seconds = payload.user_info_delay_seconds
    return ConfigureResponse(
        token_requests=state.token_requests,
        user_info_requests=state.user_info_requests,
    )


class StatsResponse(BaseModel):
    token_requests: int = Field(...)
    user_info_requests: int = Field(...)


@app.get("/admin/stats")
async def admin_stats() -> StatsResponse:
    return StatsResponse(
        token_requests=state.token_requests,
        user_info_requests=state.user_info_requests,
    )
