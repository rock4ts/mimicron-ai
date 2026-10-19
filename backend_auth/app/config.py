from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PostgresSettings(BaseSettings):
    db: str = "auth"
    user: str = "admin"
    password: str = "password"
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


class RedisSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6379

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )


class JWTSettings(BaseSettings):
    algorithm: str = "RS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    private_key_path: str = "certs/jwt-private.pem"
    public_key_path: str = "certs/jwt-public.pem"

    model_config = SettingsConfigDict(
        env_prefix="JWT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    @property
    def private_key(self) -> bytes:
        with open(self.private_key_path, "rb") as key_file:
            return key_file.read()

    @property
    def public_key(self) -> bytes:
        with open(self.public_key_path, "rb") as key_file:
            return key_file.read()


class YandexIdSettings(BaseSettings):
    auth_url: str = "https://oauth.yandex.ru/authorize"
    token_url: str = "https://oauth.yandex.ru/token"
    user_info_url: str = "https://login.yandex.ru/info"
    redirect_url: str = "http://localhost:8000/yandexid/token"
    client_id: str = ""
    client_secret: str = ""
    confirmation_code_ttl: int = 600
    http_timeout_seconds: float = 10.0

    model_config = SettingsConfigDict(
        env_prefix="YANDEXID_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    @property
    def auth_header(self) -> str:
        import base64

        encoded_client_data = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        return f"Basic {encoded_client_data}"


class RateLimitSettings(BaseSettings):
    enabled: bool = True
    redis_prefix: str = "rate_limit"
    fail_open: bool = False
    ip_limit: int = 5
    ip_window_seconds: int = 60

    model_config = SettingsConfigDict(
        env_prefix="RATE_LIMIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )


class Settings(BaseSettings):
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)
    yandexid: YandexIdSettings = Field(default_factory=YandexIdSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    prod: bool = Field(default=False, validation_alias="PROD_RUN")
    log_level: str = "INFO"
    superuser_email: str = "admin@example.com"
    superuser_password: str = "password"
    request_id_header: str = "x-request-id"
    root_path: str = ""
    trust_proxy_headers: bool = False
    trusted_proxy_ips: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    @property
    def trusted_proxy_ip_set(self) -> set[str]:
        return {ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
