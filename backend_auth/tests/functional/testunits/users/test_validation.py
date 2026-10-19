from http import HTTPStatus

import pytest

from tests.functional.conftest import auth_headers


@pytest.mark.parametrize(
    "payload, expected_status",
    [
        ({"email": "bad-email", "password": "password"}, HTTPStatus.UNPROCESSABLE_ENTITY),
        ({"email": "good@example.com"}, HTTPStatus.UNPROCESSABLE_ENTITY),
        ({"password": "password"}, HTTPStatus.UNPROCESSABLE_ENTITY),
    ],
)
@pytest.mark.asyncio
async def test_create_user_payload_validation(make_post_request, payload, expected_status):
    _, status, _ = await make_post_request("/users", payload)
    assert status == expected_status


@pytest.mark.asyncio
async def test_login_history_query_validation(
    create_user_payload,
    create_db_user,
    login_user,
    make_get_request,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    login_body, _ = await login_user(create_user_payload["email"], create_user_payload["password"])

    _, page_status = await make_get_request(
        "/users/me/login-history",
        query_data={"page": 0},
        headers=auth_headers(login_body["access"]),
    )
    assert page_status == HTTPStatus.UNPROCESSABLE_ENTITY

    _, page_size_status = await make_get_request(
        "/users/me/login-history",
        query_data={"page_size": 101},
        headers=auth_headers(login_body["access"]),
    )
    assert page_size_status == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_get_me_without_token_returns_forbidden(make_get_request):
    body, status = await make_get_request("/users/me")

    assert status == HTTPStatus.FORBIDDEN
    assert body["detail"] == "Not authenticated"
