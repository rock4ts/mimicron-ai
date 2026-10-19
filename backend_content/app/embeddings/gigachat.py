import asyncio
import logging
import math
from typing import Any

from gigachat import GigaChat

from app.embeddings.base import EmbeddingProvider
from app.errors import EmbeddingProviderError

logger = logging.getLogger(__name__)


class GigachatEmbeddingProvider(EmbeddingProvider):
    """GigaChat adapter that validates vector size and translates API failures."""

    def __init__(
        self,
        api_key: str,
        model: str,
        dimensions: int,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.timeout_seconds = timeout_seconds

    async def embed(self, content: str) -> list[float]:
        """Return a GigaChat embedding, or raise EmbeddingProviderError on failure."""
        if not self.api_key:
            raise EmbeddingProviderError("Embedding provider is not configured")

        try:
            response = await asyncio.wait_for(
                self._create(content),
                timeout=self.timeout_seconds,
            )
            vector = self._extract_vector(response)
            self._validate_vector(vector)
            return vector
        except TimeoutError as exc:
            logger.error(
                "embedding_request_timed_out",
                extra={
                    "provider": "gigachat",
                    "timeout_seconds": self.timeout_seconds,
                },
            )
            raise EmbeddingProviderError("Embedding request timed out") from exc
        except EmbeddingProviderError:
            raise
        except Exception as exc:
            logger.error(
                "embedding_request_failed",
                extra={"provider": "gigachat", "error_type": type(exc).__name__},
            )
            raise EmbeddingProviderError("Embedding request failed") from exc

    async def _create(self, content: str) -> Any:
        async with GigaChat(
            credentials=self.api_key,
            # TODO: enable SSL verification after adding Russian CA chain
            verify_ssl_certs=False,
        ) as client:
            return await client.aembeddings([content], model=self.model)

    def _extract_vector(self, response: Any) -> list[float]:
        data = getattr(response, "data", None)
        if not data:
            raise EmbeddingProviderError("Embedding provider returned an invalid response")
        embedding = getattr(data[0], "embedding", None)
        if embedding is None:
            raise EmbeddingProviderError("Embedding provider returned an invalid response")
        try:
            return list(embedding)
        except TypeError as exc:
            raise EmbeddingProviderError("Embedding provider returned an invalid response") from exc

    def _validate_vector(self, vector: list[float]) -> None:
        if len(vector) != self.dimensions:
            raise EmbeddingProviderError("Embedding provider returned an invalid response")
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise EmbeddingProviderError("Embedding provider returned an invalid response")
            if not math.isfinite(value):
                raise EmbeddingProviderError("Embedding provider returned an invalid response")
