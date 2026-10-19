from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Turns memory content into a vector without exposing a specific vendor."""

    @abstractmethod
    async def embed(self, content: str) -> list[float]:
        """Return the embedding for `content`."""
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release provider resources. Default is a no-op."""
        return None
