from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PostgresSettings(BaseSettings):
    db: str
    user: str
    password: str
    host: str
    port: int = 5432

    model_config = SettingsConfigDict(
        env_prefix="POSTGRES_",
        env_file=".env.tests",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    @property
    def url(self) -> str:
        user = quote_plus(self.user)
        password = quote_plus(self.password)
        return f"postgresql+asyncpg://{user}:{password}@{self.host}:{self.port}/{self.db}"


class QdrantSettings(BaseSettings):
    url: str
    collection: str = "memories_test"
    api_key: str = ""

    model_config = SettingsConfigDict(
        env_prefix="QDRANT_",
        env_file=".env.tests",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )


class EmbeddingSettings(BaseSettings):
    dimensions: int = 8
    model: str = "Embeddings"

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        env_file=".env.tests",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )


class Settings(BaseSettings):
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    test_base_url: str = "http://localhost:8000"
    jwt_public_key_path: str = Field(
        default="tests/docker/certs/jwt-public.pem",
        validation_alias="JWT_PUBLIC_KEY_PATH",
    )
    jwt_private_key_path: str = Field(
        default="tests/docker/certs/jwt-private.pem",
        validation_alias="JWT_PRIVATE_KEY_PATH",
    )
    jwt_algorithm: str = Field(default="RS256", validation_alias="JWT_ALGORITHM")

    model_config = SettingsConfigDict(
        env_file=".env.tests",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )


tests_settings = Settings()
