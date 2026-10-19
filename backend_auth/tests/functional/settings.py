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
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class RedisSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6379

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env.tests",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )


class Settings(BaseSettings):
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    test_base_url: str = "http://localhost:8000"
    yandex_mock_url: str = "http://localhost:8090"
    yandex_confirmation_code_ttl: int = Field(
        default=600,
        validation_alias="YANDEXID_CONFIRMATION_CODE_TTL",
    )
    jwt_public_key_path: str = Field(
        default="tests/docker/certs/jwt-public.pem",
        validation_alias="JWT_PUBLIC_KEY_PATH",
    )

    model_config = SettingsConfigDict(
        env_file=".env.tests",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )


tests_settings = Settings()
