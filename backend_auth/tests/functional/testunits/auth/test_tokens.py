from http import HTTPStatus

import pytest

from tests.functional.conftest import auth_headers
from tests.functional.testunits.yandexid.conftest import assert_cookie_flags


@pytest.mark.asyncio
async def test_issue_tokens_returns_access_and_refresh_cookie_and_persists_login_history(
    create_user_payload,
    create_db_user,
    login_user,
    get_user_by_email,
    get_login_history_for_user,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    body, response = await login_user(create_user_payload["email"], create_user_payload["password"])

    assert "access" in body
    assert response.cookies.get("refresh")

    user = await get_user_by_email(create_user_payload["email"])
    history = await get_login_history_for_user(user["id"])
    assert len(history) == 1


@pytest.mark.asyncio
async def test_issue_tokens_rejects_wrong_password(
    create_user_payload,
    create_db_user,
    make_post_request,
    get_user_by_email,
    get_login_history_for_user,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    body, status, _ = await make_post_request(
        "/token",
        {"email": create_user_payload["email"], "password": "wrong-password"},
    )

    assert status == HTTPStatus.UNAUTHORIZED
    assert body["detail"] == "Incorrect email or password"

    user = await get_user_by_email(create_user_payload["email"])
    history = await get_login_history_for_user(user["id"])
    assert len(history) == 0


@pytest.mark.asyncio
async def test_refresh_rotates_refresh_cookie(
    create_user_payload,
    create_db_user,
    login_user,
    make_post_request,
    is_refresh_token_blacklisted,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    _, login_response = await login_user(
        create_user_payload["email"],
        create_user_payload["password"],
    )
    refresh_before = login_response.cookies.get("refresh")

    body, status, refresh_response = await make_post_request("/refresh")

    assert status == HTTPStatus.OK
    assert "access" in body
    assert refresh_response.cookies.get("refresh")
    assert refresh_response.cookies.get("refresh") != refresh_before
    assert await is_refresh_token_blacklisted(refresh_before)


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_unauthorized(make_post_request):
    body, status, _ = await make_post_request("/refresh")

    assert status == HTTPStatus.UNAUTHORIZED
    assert body["detail"] == "Refresh token is required"


@pytest.mark.asyncio
async def test_refresh_rejects_invalid_token_cookie(make_post_request):
    body, status, _ = await make_post_request(
        "/refresh",
        headers={"Cookie": "refresh=bad-token"},
    )

    assert status == HTTPStatus.UNAUTHORIZED
    assert body["detail"] == "Invalid refresh token"


@pytest.mark.asyncio
async def test_logout_blacklists_old_refresh_token(
    create_user_payload,
    create_db_user,
    login_user,
    make_post_request,
    is_refresh_token_blacklisted,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    _, login_response = await login_user(
        create_user_payload["email"],
        create_user_payload["password"],
    )
    previous_refresh = login_response.cookies.get("refresh")

    _, logout_status, logout_response = await make_post_request("/logout")
    assert logout_status == HTTPStatus.OK
    assert await is_refresh_token_blacklisted(previous_refresh)
    refresh_header = next(
        header
        for header in logout_response.headers.get_list("set-cookie")
        if header.lower().startswith("refresh=")
    )
    assert_cookie_flags(refresh_header, max_age=0)

    body, refresh_status, _ = await make_post_request(
        "/refresh",
        headers={"Cookie": f"refresh={previous_refresh}"},
    )
    assert refresh_status == HTTPStatus.UNAUTHORIZED
    assert body["detail"] == "Invalid refresh token"


@pytest.mark.asyncio
async def test_logout_rejects_invalid_refresh_cookie(make_post_request):
    body, status, _ = await make_post_request(
        "/logout",
        headers={"Cookie": "refresh=bad-token"},
    )

    assert status == HTTPStatus.UNAUTHORIZED
    assert body["detail"] == "Invalid refresh token"


@pytest.mark.asyncio
async def test_logout_others_changes_token_version_and_invalidates_previous_tokens(
    create_user_payload,
    create_db_user,
    login_user,
    make_post_request,
    make_get_request,
    get_user_by_email,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    login_body, login_response = await login_user(
        create_user_payload["email"],
        create_user_payload["password"],
    )
    previous_access = login_body["access"]
    previous_refresh = login_response.cookies.get("refresh")

    user_before = await get_user_by_email(create_user_payload["email"])
    token_version_before = user_before["token_version"]

    rotate_body, rotate_status, _ = await make_post_request(
        "/logout-others",
        headers=auth_headers(previous_access),
    )
    assert rotate_status == HTTPStatus.OK
    assert "access" in rotate_body

    user_after = await get_user_by_email(create_user_payload["email"])
    assert user_after["token_version"] == token_version_before + 1

    _, old_token_status = await make_get_request("/users/me", headers=auth_headers(previous_access))
    assert old_token_status == HTTPStatus.UNAUTHORIZED

    refresh_body, old_refresh_status, _ = await make_post_request(
        "/refresh",
        headers={"Cookie": f"refresh={previous_refresh}"},
    )
    assert old_refresh_status == HTTPStatus.UNAUTHORIZED
    assert refresh_body["detail"] == "Invalid refresh token"

    _, new_token_status = await make_get_request(
        "/users/me",
        headers=auth_headers(rotate_body["access"]),
    )
    assert new_token_status == HTTPStatus.OK
