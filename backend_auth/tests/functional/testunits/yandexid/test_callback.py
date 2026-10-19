import uuid
from http import HTTPStatus

import pytest

from tests.functional.conftest import auth_headers
from tests.functional.testunits.yandexid.conftest import (
    assert_cookie_flags,
    complete_yandex_callback,
    configure_yandex_mock,
    start_yandex_login,
    yandex_token_payload,
    yandex_user_profile_payload,
)

REFRESH_COOKIE_MAX_AGE = 30 * 60 * 60 * 24


@pytest.mark.asyncio
async def test_yandex_callback_first_login_creates_user_and_issues_tokens(
    http_client,
    make_get_request,
    configure_mock,
    count_users,
    count_oauth_accounts,
    get_user_by_email,
    get_oauth_accounts,
    get_login_history_for_user,
):
    profile = yandex_user_profile_payload()
    await configure_mock(
        token_body=yandex_token_payload(),
        user_info_body=profile,
    )

    state, _ = await start_yandex_login(http_client)
    body, status, callback_response = await complete_yandex_callback(
        http_client,
        state,
        headers={"User-Agent": "pytest-agent"},
    )

    assert status == HTTPStatus.OK
    assert "access" in body
    assert callback_response.cookies.get("refresh")
    assert callback_response.cookies.get("device_id")
    assert callback_response.cookies.get("state") is None

    assert await count_users() == 1
    assert await count_oauth_accounts() == 1

    user = await get_user_by_email(profile["default_email"])
    assert user is not None
    assert user["first_name"] == profile["first_name"]
    assert user["last_name"] == profile["last_name"]

    accounts = await get_oauth_accounts(str(profile["id"]))
    assert len(accounts) == 1
    assert accounts[0]["provider"] == "yandex"
    assert accounts[0]["user_id"] == user["id"]

    history = await get_login_history_for_user(user["id"])
    assert len(history) == 1

    me_body, me_status = await make_get_request("/users/me", headers=auth_headers(body["access"]))
    assert me_status == HTTPStatus.OK
    assert me_body["email"] == profile["default_email"]


@pytest.mark.asyncio
async def test_yandex_callback_sets_refresh_and_device_id_cookie_flags(
    http_client,
    configure_mock,
):
    profile = yandex_user_profile_payload()
    await configure_mock(
        token_body=yandex_token_payload(),
        user_info_body=profile,
    )

    state, login_response = await start_yandex_login(http_client)
    _, status, callback_response = await complete_yandex_callback(http_client, state)

    assert status == HTTPStatus.OK
    refresh_max_age = REFRESH_COOKIE_MAX_AGE
    set_cookie_headers = callback_response.headers.get_list("set-cookie")

    refresh_header = next(header for header in set_cookie_headers if header.startswith("refresh="))
    device_header = next(header for header in set_cookie_headers if header.startswith("device_id="))
    assert_cookie_flags(refresh_header, max_age=refresh_max_age)
    assert_cookie_flags(device_header)

    state_deleted = any(
        header.startswith("state=") and "Max-Age=0" in header for header in set_cookie_headers
    )
    assert state_deleted or callback_response.cookies.get("state") is None


@pytest.mark.asyncio
async def test_yandex_callback_records_login_history_metadata(
    http_client,
    configure_mock,
    get_user_by_email,
    get_login_history_for_user,
):
    profile = yandex_user_profile_payload()
    device_id = str(uuid.uuid4())
    await configure_mock(
        token_body=yandex_token_payload(),
        user_info_body=profile,
    )

    http_client.cookies.set("device_id", device_id)
    state, _ = await start_yandex_login(http_client)
    _, status, _ = await complete_yandex_callback(
        http_client,
        state,
        headers={"User-Agent": "pytest-agent"},
    )

    assert status == HTTPStatus.OK
    user = await get_user_by_email(profile["default_email"])
    history = await get_login_history_for_user(user["id"])
    assert len(history) == 1
    assert history[0]["user_agent"] == "pytest-agent"
    assert history[0]["ip_address"]
    assert history[0]["device_id"] == device_id


@pytest.mark.asyncio
async def test_yandex_callback_reuses_device_id_from_cookie(
    http_client,
    configure_mock,
    get_user_by_email,
    get_login_history_for_user,
):
    profile_one = yandex_user_profile_payload()
    profile_two = yandex_user_profile_payload()
    await configure_mock(
        token_body=yandex_token_payload(),
        user_info_body=profile_one,
    )

    state_one, _ = await start_yandex_login(http_client)
    _, status_one, first_callback = await complete_yandex_callback(http_client, state_one)
    assert status_one == HTTPStatus.OK
    first_device_id = first_callback.cookies.get("device_id")
    assert first_device_id

    await configure_yandex_mock(
        token_body=yandex_token_payload(),
        user_info_body=profile_two,
    )
    state_two, _ = await start_yandex_login(http_client)
    _, status_two, second_callback = await complete_yandex_callback(http_client, state_two)

    assert status_two == HTTPStatus.OK
    assert second_callback.cookies.get("device_id") == first_device_id

    user = await get_user_by_email(profile_two["default_email"])
    history = await get_login_history_for_user(user["id"])
    assert history[0]["device_id"] == first_device_id


@pytest.mark.asyncio
async def test_yandex_callback_existing_oauth_account_logs_in_without_new_user_or_account(
    http_client,
    configure_mock,
    create_db_user,
    create_oauth_account,
    count_users,
    count_oauth_accounts,
    get_login_history_for_user,
):
    profile = yandex_user_profile_payload()
    user_id = await create_db_user(profile["default_email"])
    await create_oauth_account(user_id, str(profile["id"]))

    await configure_mock(
        token_body=yandex_token_payload(),
        user_info_body=profile,
    )

    state, _ = await start_yandex_login(http_client)
    _, status, _ = await complete_yandex_callback(http_client, state)

    assert status == HTTPStatus.OK
    assert await count_users() == 1
    assert await count_oauth_accounts() == 1
    history = await get_login_history_for_user(user_id)
    assert len(history) == 1


@pytest.mark.asyncio
async def test_yandex_callback_existing_email_links_oauth_account(
    http_client,
    configure_mock,
    create_db_user,
    create_user_payload,
    count_users,
    count_oauth_accounts,
    get_oauth_accounts,
    get_login_history_for_user,
):
    user_id = await create_db_user(
        create_user_payload["email"], password=create_user_payload["password"]
    )
    profile = yandex_user_profile_payload(email=create_user_payload["email"])
    await configure_mock(
        token_body=yandex_token_payload(),
        user_info_body=profile,
    )

    state, _ = await start_yandex_login(http_client)
    _, status, _ = await complete_yandex_callback(http_client, state)

    assert status == HTTPStatus.OK
    assert await count_users() == 1
    assert await count_oauth_accounts() == 1

    accounts = await get_oauth_accounts(str(profile["id"]))
    assert len(accounts) == 1
    assert str(accounts[0]["user_id"]) == str(user_id)


@pytest.mark.asyncio
async def test_yandex_callback_repeated_login_does_not_duplicate_user_or_oauth_account(
    http_client,
    configure_mock,
    count_users,
    count_oauth_accounts,
    get_login_history_for_user,
    get_user_by_email,
):
    profile = yandex_user_profile_payload()
    await configure_mock(
        token_body=yandex_token_payload(),
        user_info_body=profile,
    )

    state_one, _ = await start_yandex_login(http_client)
    _, status_one, _ = await complete_yandex_callback(http_client, state_one)
    assert status_one == HTTPStatus.OK

    await configure_mock(
        token_body=yandex_token_payload(),
        user_info_body=profile,
    )
    state_two, _ = await start_yandex_login(http_client)
    _, status_two, _ = await complete_yandex_callback(http_client, state_two)
    assert status_two == HTTPStatus.OK

    assert await count_users() == 1
    assert await count_oauth_accounts() == 1
    user = await get_user_by_email(profile["default_email"])
    history = await get_login_history_for_user(user["id"])
    assert len(history) == 2
