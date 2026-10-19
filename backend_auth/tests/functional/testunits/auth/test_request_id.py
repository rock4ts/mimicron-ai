from http import HTTPStatus

import pytest


@pytest.mark.asyncio
async def test_health_echoes_supplied_request_id(http_client):
    response = await http_client.get("/health", headers={"x-request-id": "test-correlation-123"})

    assert response.status_code == HTTPStatus.OK
    assert response.headers["x-request-id"] == "test-correlation-123"


@pytest.mark.asyncio
async def test_health_generates_request_id_when_missing(http_client):
    response = await http_client.get("/health")

    assert response.status_code == HTTPStatus.OK
    assert response.headers.get("x-request-id")
