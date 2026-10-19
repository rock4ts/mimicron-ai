from app.config import Settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.gigachat import GigachatEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "GigachatEmbeddingProvider",
    "create_embedding_provider",
]


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Build the configured embedding provider."""
    return GigachatEmbeddingProvider(
        api_key=settings.embedding.api_key or settings.llm_api_key,
        model=settings.embedding.model,
        dimensions=settings.embedding.dimensions,
        timeout_seconds=settings.embedding.timeout_seconds,
    )
