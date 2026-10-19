from http import HTTPStatus

import pytest


@pytest.mark.parametrize(
    "payload, expected_status",
    [
        ({"email": "invalid-email", "password": "password"}, HTTPStatus.UNPROCESSABLE_ENTITY),
        ({"email": "user@example.com"}, HTTPStatus.UNPROCESSABLE_ENTITY),
        ({"password": "password"}, HTTPStatus.UNPROCESSABLE_ENTITY),
    ],
)
@pytest.mark.asyncio
async def test_token_request_payload_validation(make_post_request, payload, expected_status):
    _, status, _ = await make_post_request("/token", payload)
    assert status == expected_status


@pytest.mark.asyncio
async def test_logout_others_requires_bearer_token(make_post_request):
    body, status, _ = await make_post_request("/logout-others")

    assert status == HTTPStatus.FORBIDDEN
    assert body["detail"] == "Not authenticated"
