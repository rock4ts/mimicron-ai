import uuid
from http import HTTPStatus
from typing import Any

import pytest

from tests.functional.testunits.yandexid.conftest import (
    complete_yandex_callback,
    get_yandex_mock_stats,
    start_yandex_login,
    yandex_token_payload,
    yandex_user_profile_payload,
)


@pytest.mark.asyncio
async def test_yandex_callback_rejects_missing_state_cookie(http_client):
    state, _ = await start_yandex_login(http_client)
    http_client.cookies.clear()

    body, status, _ = await complete_yandex_callback(http_client, state)

    assert status == HTTPStatus.BAD_REQUEST
    assert body["detail"] == "Cookie state is invalid or expired"
    stats = await get_yandex_mock_stats()
    assert stats["token_requests"] == 0
    assert stats["user_info_requests"] == 0


@pytest.mark.asyncio
async def test_yandex_callback_rejects_mismatched_state_cookie(http_client):
    state, _ = await start_yandex_login(http_client)
    other_state = str(uuid.uuid4())

    body, status, _ = await complete_yandex_callback(http_client, other_state)

    assert status == HTTPStatus.BAD_REQUEST
    assert body["detail"] == "Login state is invalid or expired"
    stats = await get_yandex_mock_stats()
    assert stats["token_requests"] == 0
    assert stats["user_info_requests"] == 0


@pytest.mark.asyncio
async def test_yandex_callback_rejects_malformed_state_cookie(http_client):
    state, _ = await start_yandex_login(http_client)
    http_client.cookies.set("state", "not-a-uuid")

    body, status, _ = await complete_yandex_callback(http_client, state)

    assert status == HTTPStatus.BAD_REQUEST
    assert body["detail"] == "Cookie state is invalid or expired"
    stats = await get_yandex_mock_stats()
    assert stats["token_requests"] == 0
    assert stats["user_info_requests"] == 0


@pytest.mark.asyncio
async def test_yandex_callback_rejects_missing_redis_state_with_valid_cookie(
    http_client,
    redis_client,
):
    state, _ = await start_yandex_login(http_client)
    await redis_client.delete(f"oauth:yandex:state:{state}")

    body, status, _ = await complete_yandex_callback(http_client, state)

    assert status == HTTPStatus.BAD_REQUEST
    assert body["detail"] == "OAuth state is invalid or expired"
    stats = await get_yandex_mock_stats()
    assert stats["token_requests"] == 0
    assert stats["user_info_requests"] == 0


@pytest.mark.asyncio
async def test_yandex_callback_rejects_reused_redis_state(http_client, configure_mock):
    profile: dict[str, Any] = yandex_user_profile_payload()
    await configure_mock(
        token_body=yandex_token_payload(),
        user_info_body=profile,
    )

    state, _ = await start_yandex_login(http_client)
    _, first_status, _ = await complete_yandex_callback(http_client, state)
    assert first_status == HTTPStatus.OK

    http_client.cookies.set("state", state)
    body, second_status, _ = await complete_yandex_callback(http_client, state)

    assert second_status == HTTPStatus.BAD_REQUEST
    assert body["detail"] == "OAuth state is invalid or expired"
    stats = await get_yandex_mock_stats()
    assert stats["token_requests"] == 1
    assert stats["user_info_requests"] == 1
