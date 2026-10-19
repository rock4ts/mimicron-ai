import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from app.embeddings.gigachat import GigachatEmbeddingProvider
from app.errors import EmbeddingProviderError


class _FakeGigaChat:
    last_init: dict[str, Any] = {}
    last_texts: list[str] | None = None
    last_model: str | None = None
    response: Any = None
    error: Exception | None = None
    delay_seconds: float = 0.0

    def __init__(self, **kwargs: Any) -> None:
        type(self).last_init = kwargs

    async def __aenter__(self) -> "_FakeGigaChat":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def aembeddings(self, texts: list[str], model: str = "Embeddings") -> Any:
        type(self).last_texts = texts
        type(self).last_model = model
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error is not None:
            raise self.error
        return self.response


def _response(embedding: object) -> SimpleNamespace:
    return SimpleNamespace(data=[SimpleNamespace(embedding=embedding)])


def _provider(**overrides: object) -> GigachatEmbeddingProvider:
    values: dict[str, object] = {
        "api_key": "test-key",
        "model": "Embeddings",
        "dimensions": 4,
        "timeout_seconds": 1.0,
    }
    values.update(overrides)
    return GigachatEmbeddingProvider(
        api_key=str(values["api_key"]),
        model=str(values["model"]),
        dimensions=int(values["dimensions"]),
        timeout_seconds=float(values["timeout_seconds"]),
    )


@pytest.fixture(autouse=True)
def fake_gigachat(monkeypatch: pytest.MonkeyPatch) -> type[_FakeGigaChat]:
    _FakeGigaChat.last_init = {}
    _FakeGigaChat.last_texts = None
    _FakeGigaChat.last_model = None
    _FakeGigaChat.response = _response([0.1, 0.2, 0.3, 0.4])
    _FakeGigaChat.error = None
    _FakeGigaChat.delay_seconds = 0.0
    monkeypatch.setattr("app.embeddings.gigachat.GigaChat", _FakeGigaChat)
    return _FakeGigaChat


async def test_embed_returns_configured_model_vector(fake_gigachat: type[_FakeGigaChat]) -> None:
    provider = _provider(model="Embeddings-2")

    vector = await provider.embed("User has a dog named Charlie.")

    assert vector == [0.1, 0.2, 0.3, 0.4]
    assert fake_gigachat.last_model == "Embeddings-2"
    assert fake_gigachat.last_texts == ["User has a dog named Charlie."]
    assert fake_gigachat.last_init["credentials"] == "test-key"


async def test_embed_requires_api_key() -> None:
    provider = _provider(api_key="")

    with pytest.raises(EmbeddingProviderError, match="not configured"):
        await provider.embed("text")


async def test_embed_times_out(fake_gigachat: type[_FakeGigaChat]) -> None:
    fake_gigachat.delay_seconds = 0.2
    provider = _provider(timeout_seconds=0.05)

    with pytest.raises(EmbeddingProviderError, match="timed out"):
        await provider.embed("text")


async def test_embed_wraps_provider_failure(fake_gigachat: type[_FakeGigaChat]) -> None:
    fake_gigachat.error = RuntimeError("network down")
    provider = _provider()

    with pytest.raises(EmbeddingProviderError, match="request failed"):
        await provider.embed("text")


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[SimpleNamespace(embedding=None)]),
        _response([]),
        _response([0.1, 0.2]),
        _response([0.1, 0.2, float("nan"), 0.4]),
        _response([0.1, 0.2, float("inf"), 0.4]),
        _response([0.1, True, 0.3, 0.4]),
        _response(["0.1", 0.2, 0.3, 0.4]),
    ],
)
async def test_embed_rejects_invalid_response(
    fake_gigachat: type[_FakeGigaChat],
    response: object,
) -> None:
    fake_gigachat.response = response
    provider = _provider()

    with pytest.raises(EmbeddingProviderError, match="invalid response"):
        await provider.embed("text")
