from http import HTTPStatus

import pytest

from tests.functional.testunits.yandexid.conftest import (
    complete_yandex_callback,
    get_yandex_mock_stats,
    start_yandex_login,
    yandex_token_payload,
    yandex_user_profile_payload,
)


@pytest.mark.asyncio
async def test_yandex_callback_returns_bad_gateway_when_token_endpoint_rejects_code(
    http_client,
    configure_mock,
    count_users,
    count_oauth_accounts,
):
    await configure_mock(token_status=400)

    state, _ = await start_yandex_login(http_client)
    body, status, _ = await complete_yandex_callback(http_client, state)

    assert status == HTTPStatus.BAD_GATEWAY
    assert body["detail"] == "Error during token exchange with provider"
    assert await count_users() == 0
    assert await count_oauth_accounts() == 0

    stats = await get_yandex_mock_stats()
    assert stats["token_requests"] == 1
    assert stats["user_info_requests"] == 0


@pytest.mark.asyncio
async def test_yandex_callback_returns_bad_gateway_when_token_endpoint_times_out(
    http_client,
    configure_mock,
):
    await configure_mock(
        token_delay_seconds=2.0
    )  # should be more than YANDEXID_HTTP_TIMEOUT_SECONDS in .env.tests

    state, _ = await start_yandex_login(http_client)
    body, status, _ = await complete_yandex_callback(http_client, state)

    assert status == HTTPStatus.BAD_GATEWAY
    assert body["detail"] == "Error during token exchange with provider"
    stats = await get_yandex_mock_stats()
    assert stats["token_requests"] == 1
    assert stats["user_info_requests"] == 0


@pytest.mark.asyncio
async def test_yandex_callback_returns_bad_gateway_for_invalid_token_payload(
    http_client,
    configure_mock,
    count_users,
    count_oauth_accounts,
):
    await configure_mock(token_body={"wrong_key": "wrong_value"})

    state, _ = await start_yandex_login(http_client)
    body, status, _ = await complete_yandex_callback(http_client, state)

    assert status == HTTPStatus.BAD_GATEWAY
    assert body["detail"] == "OAuth provider is temporarily unavailable"
    assert await count_users() == 0
    assert await count_oauth_accounts() == 0


@pytest.mark.asyncio
async def test_yandex_callback_returns_bad_gateway_when_user_info_http_fails(
    http_client,
    configure_mock,
    count_users,
    count_oauth_accounts,
):
    profile = yandex_user_profile_payload()
    await configure_mock(
        token_body=yandex_token_payload(),
        user_info_body=profile,
        user_info_status=500,
    )

    state, _ = await start_yandex_login(http_client)
    body, status, _ = await complete_yandex_callback(http_client, state)

    assert status == HTTPStatus.BAD_GATEWAY
    assert body["detail"] == "Error during user profile fetch from provider"
    assert await count_users() == 0
    assert await count_oauth_accounts() == 0


@pytest.mark.asyncio
async def test_yandex_callback_returns_bad_gateway_for_invalid_user_info_payload(
    http_client,
    configure_mock,
    count_users,
    count_oauth_accounts,
):
    await configure_mock(
        token_body=yandex_token_payload(),
        user_info_body={"wrong_key": "wrong_value"},
    )

    state, _ = await start_yandex_login(http_client)
    body, status, _ = await complete_yandex_callback(http_client, state)

    assert status == HTTPStatus.BAD_GATEWAY
    assert body["detail"] == "Error during user profile fetch from provider"
    assert await count_users() == 0
    assert await count_oauth_accounts() == 0


@pytest.mark.asyncio
async def test_yandex_callback_returns_bad_gateway_when_user_info_request_times_out(
    http_client,
    configure_mock,
):
    profile = yandex_user_profile_payload()
    await configure_mock(
        token_body=yandex_token_payload(),
        user_info_body=profile,
        user_info_delay_seconds=2.0,
    )  # should be more than YANDEXID_HTTP_TIMEOUT_SECONDS in .env.tests

    state, _ = await start_yandex_login(http_client)
    body, status, _ = await complete_yandex_callback(http_client, state)

    assert status == HTTPStatus.BAD_GATEWAY
    assert body["detail"] == "Error during user profile fetch from provider"
    stats = await get_yandex_mock_stats()
    assert stats["token_requests"] == 1
    assert stats["user_info_requests"] == 1
