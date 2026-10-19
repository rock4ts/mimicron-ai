import pytest

from tests.functional.settings import tests_settings
from tests.functional.testunits.yandexid.conftest import (
    assert_cookie_flags,
    get_redis_state_payload,
    parse_redirect_query,
    start_yandex_login,
)


@pytest.mark.asyncio
async def test_yandex_login_redirects_to_provider_sets_state_cookie_and_stores_pkce(
    http_client,
    redis_client,
):
    state, login_response = await start_yandex_login(http_client)

    redirect_url = login_response.headers["location"]
    query = parse_redirect_query(redirect_url)

    assert redirect_url.startswith("http://yandex-mock:8080/authorize")
    assert query["response_type"] == "code"
    assert query["client_id"] == "your-client-id"
    assert query["redirect_uri"] == "https://oauth.yandex.ru/verification_code"
    assert query["state"] == state
    assert query["code_challenge"]
    assert query["code_challenge_method"] == "S256"
    assert "code_verifier" not in query

    state_cookie_header = login_response.headers.get_list("set-cookie")
    state_header = next(header for header in state_cookie_header if header.startswith("state="))
    assert_cookie_flags(
        state_header,
        max_age=tests_settings.yandex_confirmation_code_ttl,
    )
    assert login_response.cookies.get("state") == state

    redis_payload = await get_redis_state_payload(redis_client, state)
    assert redis_payload is not None
    assert "code_verifier" in redis_payload
    assert redis_payload["code_verifier"]


@pytest.mark.asyncio
async def test_yandex_login_redirect_does_not_include_authorization_header(http_client):
    _, login_response = await start_yandex_login(http_client)

    header_names = {name.lower() for name in login_response.headers.keys()}
    assert "authorization" not in header_names
    assert not any(value.lower().startswith("basic ") for value in login_response.headers.values())
