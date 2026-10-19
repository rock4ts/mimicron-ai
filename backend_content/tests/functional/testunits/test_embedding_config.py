import pytest
from pydantic import ValidationError

from app.config import (
    EmbeddingSettings,
    MemoryManagementSettings,
    MemoryRetrievalSettings,
    QdrantSettings,
    Settings,
)
from app.embeddings import create_embedding_provider
from app.embeddings.gigachat import GigachatEmbeddingProvider


def test_embedding_settings_reject_unknown_provider() -> None:
    with pytest.raises(ValidationError):
        EmbeddingSettings(provider="openai")


def test_embedding_settings_reject_non_positive_dimensions() -> None:
    with pytest.raises(ValidationError):
        EmbeddingSettings(dimensions=0)
    with pytest.raises(ValidationError):
        EmbeddingSettings(dimensions=-8)


def test_embedding_settings_reject_non_positive_timeout() -> None:
    with pytest.raises(ValidationError):
        EmbeddingSettings(timeout_seconds=0)


def test_qdrant_settings_reject_blank_url_and_collection() -> None:
    with pytest.raises(ValidationError):
        QdrantSettings(url="")
    with pytest.raises(ValidationError):
        QdrantSettings(collection="")


def test_qdrant_settings_reject_unknown_distance() -> None:
    with pytest.raises(ValidationError):
        QdrantSettings(distance="cosine")
    with pytest.raises(ValidationError):
        QdrantSettings(distance="unknown")


def test_create_embedding_provider_uses_embedding_credentials() -> None:

    settings = Settings.model_construct(
        embedding=EmbeddingSettings(
            provider="gigachat",
            api_key="embedding-key",
            model="EmbeddingsGigaR",
            dimensions=2560,
            timeout_seconds=12.0,
        ),
        llm_api_key="llm-key",
    )
    provider = create_embedding_provider(settings)

    assert isinstance(provider, GigachatEmbeddingProvider)
    assert provider.api_key == "embedding-key"
    assert provider.model == "EmbeddingsGigaR"
    assert provider.dimensions == 2560
    assert provider.timeout_seconds == 12.0


def test_create_embedding_provider_falls_back_to_llm_api_key() -> None:

    settings = Settings.model_construct(
        embedding=EmbeddingSettings(api_key=""),
        llm_api_key="llm-key",
    )
    provider = create_embedding_provider(settings)

    assert isinstance(provider, GigachatEmbeddingProvider)
    assert provider.api_key == "llm-key"


def test_retrieval_settings_reject_top_k_outside_range() -> None:
    with pytest.raises(ValidationError):
        MemoryRetrievalSettings(top_k=0)
    with pytest.raises(ValidationError):
        MemoryRetrievalSettings(top_k=51)


def test_retrieval_settings_reject_non_finite_threshold() -> None:
    with pytest.raises(ValidationError):
        MemoryRetrievalSettings(score_threshold=float("inf"))
    with pytest.raises(ValidationError):
        MemoryRetrievalSettings(score_threshold=float("nan"))


def test_settings_reject_cosine_threshold_out_of_range() -> None:
    with pytest.raises(ValidationError, match="Cosine"):
        Settings(
            qdrant=QdrantSettings(distance="Cosine"),
            memory_retrieval=MemoryRetrievalSettings(score_threshold=1.5),
        )


def test_settings_reject_negative_euclid_threshold() -> None:
    with pytest.raises(ValidationError, match="Euclid"):
        Settings(
            qdrant=QdrantSettings(distance="Euclid"),
            memory_retrieval=MemoryRetrievalSettings(score_threshold=-0.1),
        )


def test_management_settings_reject_top_k_outside_range() -> None:
    with pytest.raises(ValidationError):
        MemoryManagementSettings(top_k=0)
    with pytest.raises(ValidationError):
        MemoryManagementSettings(top_k=51)


def test_management_settings_reject_non_finite_threshold() -> None:
    with pytest.raises(ValidationError):
        MemoryManagementSettings(score_threshold=float("inf"))
    with pytest.raises(ValidationError):
        MemoryManagementSettings(score_threshold=float("nan"))


def test_settings_reject_management_cosine_threshold_out_of_range() -> None:
    with pytest.raises(ValidationError, match="MEMORY_MANAGEMENT_SCORE_THRESHOLD"):
        Settings(
            qdrant=QdrantSettings(distance="Cosine"),
            memory_management=MemoryManagementSettings(score_threshold=1.5),
        )
