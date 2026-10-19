from http import HTTPStatus

import pytest

from tests.functional.conftest import auth_headers


@pytest.mark.asyncio
async def test_login_history_returns_records_with_metadata(
    create_user_payload,
    create_db_user,
    make_post_request,
    make_get_request,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])

    _, first_login_status, _ = await make_post_request(
        "/token",
        body=create_user_payload,
        headers={"User-Agent": "pytest-agent"},
    )
    assert first_login_status == HTTPStatus.OK

    second_login_body, second_login_status, _ = await make_post_request(
        "/token",
        body=create_user_payload,
        headers={"User-Agent": "pytest-agent"},
    )
    assert second_login_status == HTTPStatus.OK

    history_body, history_status = await make_get_request(
        "/users/me/login-history",
        headers=auth_headers(second_login_body["access"]),
    )
    assert history_status == HTTPStatus.OK
    assert len(history_body) == 2
    assert history_body[0]["ip_address"]
    assert history_body[0]["logged_in_at"]
    assert history_body[1]["ip_address"]
    assert history_body[1]["logged_in_at"]


@pytest.mark.asyncio
async def test_login_history_pagination(
    create_user_payload,
    create_db_user,
    make_post_request,
    make_get_request,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    latest_access = ""

    for _ in range(3):
        login_body, login_status, _ = await make_post_request(
            "/token",
            body=create_user_payload,
            headers={"User-Agent": "pytest-agent"},
        )
        assert login_status == HTTPStatus.OK
        latest_access = login_body["access"]

    page_one, page_one_status = await make_get_request(
        "/users/me/login-history",
        query_data={"page": 1, "page_size": 2},
        headers=auth_headers(latest_access),
    )
    assert page_one_status == HTTPStatus.OK
    assert len(page_one) == 2

    page_two, page_two_status = await make_get_request(
        "/users/me/login-history",
        query_data={"page": 2, "page_size": 2},
        headers=auth_headers(latest_access),
    )
    assert page_two_status == HTTPStatus.OK
    assert len(page_two) >= 1
