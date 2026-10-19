from http import HTTPStatus

import pytest

from tests.functional.conftest import _api_path
from tests.functional.testunits.yandexid.conftest import start_yandex_login


@pytest.mark.asyncio
async def test_yandex_callback_requires_state_query_param(http_client):
    response = await http_client.get(
        _api_path("/yandexid/token"),
        params={"code": "test-code"},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_yandex_callback_requires_code(http_client):
    state, _ = await start_yandex_login(http_client)
    response = await http_client.get(
        _api_path("/yandexid/token"),
        params={"state": state},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_yandex_callback_rejects_malformed_state_query_param(http_client):
    response = await http_client.get(
        _api_path("/yandexid/token"),
        params={"code": "test-code", "state": "not-a-uuid"},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
