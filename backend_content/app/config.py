import math
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EmbeddingProviderName = Literal["gigachat"]
QdrantDistanceName = Literal["Cosine", "Euclid", "Dot", "Manhattan"]


class PostgresSettings(BaseSettings):
    db: str = "mimicron"
    user: str = "admin"
    password: str = "mimicron"
    host: str = "localhost"
    port: int = 5432

    model_config = SettingsConfigDict(
        env_prefix="POSTGRES_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def sync_url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class GigaChatSettings(BaseSettings):
    scope: str = "GIGACHAT_API_PERS"
    auth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

    model_config = SettingsConfigDict(
        env_prefix="GIGACHAT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )


class JWTSettings(BaseSettings):
    algorithm: str = "RS256"
    public_key_path: str = "certs/jwt-public.pem"

    model_config = SettingsConfigDict(
        env_prefix="JWT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    @property
    def public_key(self) -> bytes:
        try:
            with open(self.public_key_path, "rb") as key_file:
                return key_file.read()
        except OSError as exc:
            raise RuntimeError(
                f"JWT public key could not be read from {self.public_key_path}"
            ) from exc


class EmbeddingSettings(BaseSettings):
    provider: EmbeddingProviderName = "gigachat"
    api_key: str = ""
    model: str = "Embeddings"
    dimensions: int = Field(default=1024, gt=0)
    timeout_seconds: float = Field(default=30.0, gt=0)

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )


class QdrantSettings(BaseSettings):
    url: str = Field(default="http://localhost:6333", min_length=1)
    api_key: str = ""
    collection: str = Field(default="memories", min_length=1)
    distance: QdrantDistanceName = "Cosine"
    timeout_seconds: float = Field(default=5.0, gt=0)

    model_config = SettingsConfigDict(
        env_prefix="QDRANT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )


class MemoryRetrievalSettings(BaseSettings):
    top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: float = Field(default=0.70)

    model_config = SettingsConfigDict(
        env_prefix="MEMORY_RETRIEVAL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    @field_validator("score_threshold")
    @classmethod
    def score_threshold_must_be_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("must be finite")
        return value


class MemoryManagementSettings(BaseSettings):
    top_k: int = Field(default=10, ge=1, le=50)
    score_threshold: float = Field(default=0.55)

    model_config = SettingsConfigDict(
        env_prefix="MEMORY_MANAGEMENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    @field_validator("score_threshold")
    @classmethod
    def score_threshold_must_be_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("must be finite")
        return value


class Settings(BaseSettings):
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    gigachat: GigaChatSettings = Field(default_factory=GigaChatSettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    memory_retrieval: MemoryRetrievalSettings = Field(default_factory=MemoryRetrievalSettings)
    memory_management: MemoryManagementSettings = Field(default_factory=MemoryManagementSettings)
    llm_api_key: str = ""
    llm_model: str = "GigaChat-2"
    llm_timeout_seconds: float = 60.0
    log_level: str = "INFO"
    request_id_header: str = "x-request-id"
    root_path: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    @model_validator(mode="after")
    def score_threshold_matches_distance(self) -> Self:
        distance = self.qdrant.distance
        for name, threshold in (
            ("MEMORY_RETRIEVAL_SCORE_THRESHOLD", self.memory_retrieval.score_threshold),
            ("MEMORY_MANAGEMENT_SCORE_THRESHOLD", self.memory_management.score_threshold),
        ):
            if distance == "Cosine" and not -1.0 <= threshold <= 1.0:
                raise ValueError(f"{name} must be in [-1, 1] for Cosine")
            if distance in {"Euclid", "Manhattan"} and threshold < 0:
                raise ValueError(f"{name} must be non-negative for Euclid and Manhattan")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
