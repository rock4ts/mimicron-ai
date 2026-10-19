import uuid
from http import HTTPStatus

import pytest

from tests.functional.conftest import auth_headers


@pytest.mark.asyncio
async def test_create_user(
    make_post_request,
    create_user_payload,
    count_users,
    get_user_by_email,
):
    body, status, _ = await make_post_request("/users", create_user_payload)

    assert status == HTTPStatus.OK
    assert body["email"] == create_user_payload["email"]
    assert "id" in body
    assert "created_at" in body

    assert await count_users() == 1
    user = await get_user_by_email(create_user_payload["email"])
    assert user is not None
    assert str(user["id"]) == body["id"]
    assert user["token_version"] == 1


@pytest.mark.asyncio
async def test_create_user_rejects_duplicate_email(
    make_post_request,
    create_user_payload,
    count_users,
):
    _, first_status, _ = await make_post_request("/users", create_user_payload)
    body, second_status, _ = await make_post_request("/users", create_user_payload)

    assert first_status == HTTPStatus.OK
    assert second_status == HTTPStatus.BAD_REQUEST
    assert body["detail"] == "User already exists"
    assert await count_users() == 1


@pytest.mark.asyncio
async def test_get_me_returns_current_user(
    create_user_payload, create_db_user, login_user, make_get_request
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    token_body, _ = await login_user(create_user_payload["email"], create_user_payload["password"])

    body, status = await make_get_request("/users/me", headers=auth_headers(token_body["access"]))

    assert status == HTTPStatus.OK
    assert body["email"] == create_user_payload["email"]


@pytest.mark.asyncio
async def test_change_email_updates_credentials(
    create_user_payload,
    create_db_user,
    login_user,
    make_patch_request,
    make_post_request,
    get_user_by_email,
):
    user_id = await create_db_user(
        create_user_payload["email"], password=create_user_payload["password"]
    )
    token_body, _ = await login_user(create_user_payload["email"], create_user_payload["password"])
    next_email = f"updated_{uuid.uuid4().hex}@example.com"

    _, change_status = await make_patch_request(
        "/users/me/email",
        body={"email": next_email, "password": create_user_payload["password"]},
        headers=auth_headers(token_body["access"]),
    )
    assert change_status == HTTPStatus.OK

    assert await get_user_by_email(create_user_payload["email"]) is None
    updated_user = await get_user_by_email(next_email)
    assert updated_user is not None
    assert updated_user["id"] == user_id

    _, old_login_status, _ = await make_post_request("/token", create_user_payload)
    _, new_login_status, _ = await make_post_request(
        "/token",
        {"email": next_email, "password": create_user_payload["password"]},
    )
    assert old_login_status == HTTPStatus.UNAUTHORIZED
    assert new_login_status == HTTPStatus.OK


@pytest.mark.asyncio
async def test_change_email_rejects_wrong_password(
    create_user_payload,
    create_db_user,
    login_user,
    make_patch_request,
    get_user_by_email,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    token_body, _ = await login_user(create_user_payload["email"], create_user_payload["password"])
    next_email = f"updated_{uuid.uuid4().hex}@example.com"

    wrong_password = "bad-password"
    assert wrong_password != create_user_payload["password"]
    body, status = await make_patch_request(
        "/users/me/email",
        body={"email": next_email, "password": wrong_password},
        headers=auth_headers(token_body["access"]),
    )

    assert status == HTTPStatus.BAD_REQUEST
    assert body["detail"] == "Wrong password"

    user = await get_user_by_email(create_user_payload["email"])
    assert user is not None
    assert await get_user_by_email(next_email) is None


@pytest.mark.asyncio
async def test_change_password_invalidates_old_access_token(
    create_user_payload,
    create_db_user,
    login_user,
    make_patch_request,
    make_get_request,
    make_post_request,
    get_user_by_email,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    token_body, _ = await login_user(create_user_payload["email"], create_user_payload["password"])
    new_password = "NewPassword456!"
    user_before = await get_user_by_email(create_user_payload["email"])
    assert user_before is not None
    password_hash_before = user_before["password_hash"]
    token_version_before = user_before["token_version"]

    _, change_status = await make_patch_request(
        "/users/me/password",
        body={"old_password": create_user_payload["password"], "new_password": new_password},
        headers=auth_headers(token_body["access"]),
    )
    assert change_status == HTTPStatus.OK

    user_after = await get_user_by_email(create_user_payload["email"])
    assert user_after is not None
    assert user_after["token_version"] == token_version_before + 1
    assert user_after["password_hash"] != password_hash_before

    _, old_access_status = await make_get_request(
        "/users/me",
        headers=auth_headers(token_body["access"]),
    )
    assert old_access_status == HTTPStatus.UNAUTHORIZED

    _, old_password_status, _ = await make_post_request("/token", create_user_payload)
    _, new_password_status, _ = await make_post_request(
        "/token",
        {"email": create_user_payload["email"], "password": new_password},
    )
    assert old_password_status == HTTPStatus.UNAUTHORIZED
    assert new_password_status == HTTPStatus.OK


@pytest.mark.asyncio
async def test_change_password_rejects_wrong_old_password(
    create_user_payload,
    create_db_user,
    login_user,
    make_patch_request,
    get_user_by_email,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    token_body, _ = await login_user(create_user_payload["email"], create_user_payload["password"])

    user_before = await get_user_by_email(create_user_payload["email"])
    password_hash_before = user_before["password_hash"]
    token_version_before = user_before["token_version"]

    body, status = await make_patch_request(
        "/users/me/password",
        body={"old_password": "bad-password", "new_password": "AnotherPass123!"},
        headers=auth_headers(token_body["access"]),
    )

    assert status == HTTPStatus.BAD_REQUEST
    assert body["detail"] == "Wrong password"

    user_after = await get_user_by_email(create_user_payload["email"])
    assert user_after["password_hash"] == password_hash_before
    assert user_after["token_version"] == token_version_before
