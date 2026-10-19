from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, Callable
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest_asyncio
from redis.asyncio import Redis

from tests.functional.conftest import _api_path
from tests.functional.settings import tests_settings

YANDEX_STATE_CACHE_PREFIX = "oauth:yandex:state"


def yandex_user_profile_payload(
    email: str | None = None,
    provider_user_id: int | str | None = None,
) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:8]
    resolved_email = email or f"yandex_{suffix}@example.com"
    resolved_id = (
        provider_user_id if provider_user_id is not None else int(uuid.uuid4().int % 10_000_000)
    )
    return {
        "login": f"yandex_{suffix}",
        "id": resolved_id,
        "client_id": "your-client-id",
        "psuid": f"1.AAA.{suffix}",
        "default_email": resolved_email,
        "first_name": "Yandex",
        "last_name": "User",
        "display_name": "Yandex User",
        "real_name": "Yandex User",
        "sex": "male",
    }


def yandex_token_payload(
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> dict[str, Any]:
    suffix = uuid.uuid4().hex
    return {
        "token_type": "bearer",
        "access_token": access_token or f"mock-access-{suffix}",
        "expires_in": 3600,
        "refresh_token": refresh_token or f"mock-refresh-{suffix}",
        "scope": "login:info",
    }


def parse_redirect_query(redirect_url: str) -> dict[str, str]:
    query = parse_qs(urlparse(redirect_url).query)
    return {key: values[0] for key, values in query.items()}


def _response_payload(response: httpx.Response) -> dict | list | str:
    try:
        return response.json()
    except ValueError:
        return response.text


async def reset_yandex_mock() -> None:
    async with httpx.AsyncClient(base_url=tests_settings.yandex_mock_url, timeout=5.0) as client:
        await client.post("/admin/reset")


async def configure_yandex_mock(**kwargs: Any) -> None:
    async with httpx.AsyncClient(base_url=tests_settings.yandex_mock_url, timeout=5.0) as client:
        await client.post("/admin/configure", json=kwargs)


async def get_yandex_mock_stats() -> dict[str, int]:
    async with httpx.AsyncClient(base_url=tests_settings.yandex_mock_url, timeout=5.0) as client:
        response = await client.get("/admin/stats")
        return response.json()


async def start_yandex_login(http_client: httpx.AsyncClient) -> tuple[str, httpx.Response]:
    response = await http_client.get(_api_path("/yandexid/login"))
    assert response.status_code == HTTPStatus.FOUND
    redirect_url = response.headers["location"]
    query = parse_redirect_query(redirect_url)
    return query["state"], response


async def complete_yandex_callback(
    http_client: httpx.AsyncClient,
    state: str,
    code: str = "test-oauth-code",
    headers: dict[str, str] | None = None,
) -> tuple[dict | list | str, int, httpx.Response]:
    response = await http_client.get(
        _api_path("/yandexid/token"),
        params={"code": code, "state": state},
        headers=headers,
    )
    return _response_payload(response), response.status_code, response


@pytest_asyncio.fixture(scope="function", autouse=True)
async def reset_mock_provider() -> AsyncGenerator[None, None]:
    await reset_yandex_mock()
    yield
    await reset_yandex_mock()


@pytest_asyncio.fixture(scope="function")
def configure_mock() -> Callable[..., Any]:
    async def inner(**kwargs: Any) -> dict[str, int]:
        await configure_yandex_mock(**kwargs)
        return await get_yandex_mock_stats()

    return inner


async def get_redis_state_payload(redis_client: Redis, state: str) -> dict[str, Any] | None:
    payload = await redis_client.get(f"{YANDEX_STATE_CACHE_PREFIX}:{state}")
    if payload is None:
        return None
    return json.loads(payload)


def assert_cookie_flags(
    set_cookie_header: str,
    *,
    httponly: bool = True,
    samesite_lax: bool = True,
    secure: bool = False,
    path: str = "/",
    max_age: int | None = None,
) -> None:
    lowered = set_cookie_header.lower()
    if httponly:
        assert "httponly" in lowered
    if samesite_lax:
        assert "samesite=lax" in lowered
    if secure:
        assert "secure" in lowered
    else:
        assert "secure" not in lowered
    assert f"path={path.lower()}" in lowered
    if max_age is not None:
        assert f"max-age={max_age}" in lowered
