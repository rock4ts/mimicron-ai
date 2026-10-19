from collections.abc import AsyncIterator, Callable
from functools import lru_cache
from http import HTTPStatus
from typing import Any
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
import pytest_asyncio
from pwdlib import PasswordHash
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.functional.settings import tests_settings

_test_password_hash = PasswordHash.recommended()


@lru_cache
def _jwt_public_key() -> bytes:
    with open(tests_settings.jwt_public_key_path, "rb") as key_file:
        return key_file.read()


def _api_path(path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    return path


def _response_payload(response: httpx.Response):
    try:
        return response.json()
    except ValueError:
        return response.text


@pytest_asyncio.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        base_url=tests_settings.test_base_url,
        timeout=10.0,
        follow_redirects=False,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def db_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(tests_settings.postgres.url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    client = Redis(host=tests_settings.redis.host, port=tests_settings.redis.port)
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture(autouse=True)
async def reset(
    http_client: httpx.AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
) -> None:
    async with db_session_factory() as session:
        await session.execute(text("TRUNCATE TABLE oauth_accounts, login_history, users CASCADE"))
        await session.commit()
    await redis_client.flushdb()


@pytest.fixture
def client(http_client: httpx.AsyncClient) -> httpx.AsyncClient:
    return http_client


@pytest_asyncio.fixture
async def make_get_request(
    http_client: httpx.AsyncClient,
) -> Callable[[str, dict | None, dict | None], tuple[dict | list | str, int]]:
    async def inner(
        path: str, query_data: dict | None = None, headers: dict | None = None
    ) -> tuple[dict | list | str, int]:
        response = await http_client.get(_api_path(path), params=query_data, headers=headers)
        return _response_payload(response), response.status_code

    return inner


@pytest_asyncio.fixture
async def make_post_request(
    http_client: httpx.AsyncClient,
) -> Callable[[str, dict | None, dict | None], tuple[dict | list | str, int, httpx.Response]]:
    async def inner(
        path: str, body: dict | None = None, headers: dict | None = None
    ) -> tuple[dict | list | str, int, httpx.Response]:
        response = await http_client.post(_api_path(path), json=body, headers=headers)
        return _response_payload(response), response.status_code, response

    return inner


@pytest_asyncio.fixture
async def make_patch_request(
    http_client: httpx.AsyncClient,
) -> Callable[[str, dict | None, dict | None], tuple[dict | list | str, int]]:
    async def inner(
        path: str, body: dict | None = None, headers: dict | None = None
    ) -> tuple[dict | list | str, int]:
        response = await http_client.patch(_api_path(path), json=body, headers=headers)
        return _response_payload(response), response.status_code

    return inner


@pytest_asyncio.fixture
async def make_delete_request(
    http_client: httpx.AsyncClient,
) -> Callable[[str, dict | None], tuple[dict | list | str, int]]:
    async def inner(path: str, headers: dict | None = None) -> tuple[dict | list | str, int]:
        response = await http_client.delete(_api_path(path), headers=headers)
        return _response_payload(response), response.status_code

    return inner


@pytest_asyncio.fixture
async def user_password() -> str:
    return "UserPassword123!"


@pytest_asyncio.fixture
async def create_user_payload(user_password: str) -> dict[str, str]:
    return {
        "email": f"test_{uuid4().hex}@example.com",
        "password": user_password,
    }


@pytest_asyncio.fixture
async def create_db_user(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., UUID]:
    async def inner(
        email: str,
        password: str | None = None,
        first_name: str = "Local",
        last_name: str = "User",
    ) -> UUID:
        from app.models.user import User

        user_id = uuid4()
        password_hash_value = (
            _test_password_hash.hash(password) if password is not None else "hashed-password"
        )
        async with db_session_factory() as session:
            session.add(
                User(
                    id=user_id,
                    email=email,
                    password_hash=password_hash_value,
                    first_name=first_name,
                    last_name=last_name,
                )
            )
            await session.commit()
        return user_id

    return inner


@pytest_asyncio.fixture
async def login_user(
    make_post_request: Callable[
        [str, dict | None, dict | None], tuple[dict | list | str, int, httpx.Response]
    ],
) -> Callable[[str, str], tuple[dict, httpx.Response]]:
    async def inner(email: str, password: str) -> tuple[dict, httpx.Response]:
        body, status, response = await make_post_request(
            "/token",
            {"email": email, "password": password},
        )
        assert status == HTTPStatus.OK
        return body, response

    return inner


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture
async def get_user_by_email(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[str], Any]:
    async def inner(email: str) -> Any:
        async with db_session_factory() as session:
            result = await session.execute(
                text("SELECT * FROM users WHERE email = :email"),
                {"email": email},
            )
            return result.mappings().first()

    return inner


@pytest_asyncio.fixture
async def get_user_by_id(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[str], Any]:
    async def inner(user_id: str) -> Any:
        async with db_session_factory() as session:
            result = await session.execute(
                text("SELECT * FROM users WHERE id = :user_id"),
                {"user_id": user_id},
            )
            return result.mappings().first()

    return inner


@pytest_asyncio.fixture
async def count_users(db_session_factory: async_sessionmaker[AsyncSession]) -> Callable[[], int]:
    async def inner() -> int:
        async with db_session_factory() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM users"))
            return int(result.scalar_one())

    return inner


@pytest_asyncio.fixture
async def count_oauth_accounts(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[], int]:
    async def inner() -> int:
        async with db_session_factory() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM oauth_accounts"))
            return int(result.scalar_one())

    return inner


@pytest_asyncio.fixture
async def get_oauth_accounts(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[str | None], list[Any]]:
    async def inner(provider_user_id: str | None = None) -> list[Any]:
        async with db_session_factory() as session:
            if provider_user_id is None:
                result = await session.execute(text("SELECT * FROM oauth_accounts"))
            else:
                result = await session.execute(
                    text("SELECT * FROM oauth_accounts WHERE provider_user_id = :provider_user_id"),
                    {"provider_user_id": provider_user_id},
                )
            return list(result.mappings().all())

    return inner


@pytest_asyncio.fixture
async def get_login_history_for_user(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[UUID], list[Any]]:
    async def inner(user_id: UUID) -> list[Any]:
        async with db_session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT * FROM login_history WHERE user_id = :user_id "
                    "ORDER BY logged_in_at DESC"
                ),
                {"user_id": user_id},
            )
            return list(result.mappings().all())

    return inner


@pytest_asyncio.fixture
async def is_refresh_token_blacklisted(
    redis_client: Redis,
) -> Callable[[str], bool]:
    async def inner(refresh_token: str) -> bool:
        payload = jwt.decode(
            refresh_token,
            _jwt_public_key(),
            algorithms=["RS256"],
        )
        return await redis_client.get(f"blacklist:{payload['jti']}") is not None

    return inner


@pytest_asyncio.fixture
async def create_oauth_account(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., UUID]:
    async def inner(user_id: UUID, provider_user_id: str, provider: str = "yandex") -> UUID:
        from app.models.oauth_account import OAuthAccount

        account_id = uuid4()
        async with db_session_factory() as session:
            session.add(
                OAuthAccount(
                    id=account_id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    user_id=user_id,
                )
            )
            await session.commit()
        return account_id

    return inner
