from collections.abc import AsyncIterator
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tests.functional.fakes import (
    FakeEmbeddingController,
    FakeLLMController,
    FakeVectorIndexController,
)
from tests.functional.jwt import DEFAULT_USER_ID, auth_headers, mint_token
from tests.functional.settings import tests_settings


@pytest_asyncio.fixture
async def http_client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(base_url=tests_settings.test_base_url) as test_client:
        yield test_client


@pytest.fixture
def user_id() -> UUID:
    return DEFAULT_USER_ID


@pytest.fixture
def access_token(user_id: UUID) -> str:
    return mint_token(sub=user_id)


@pytest_asyncio.fixture
async def client(access_token: str) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        base_url=tests_settings.test_base_url,
        headers=auth_headers(access_token),
    ) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def db_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        tests_settings.postgres.url,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(
    db_session_factory: async_sessionmaker[AsyncSession],
    reset: None,
) -> AsyncIterator[AsyncSession]:
    async with db_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def qdrant_client() -> AsyncIterator[AsyncQdrantClient]:
    client = AsyncQdrantClient(
        url=tests_settings.qdrant.url,
        api_key=tests_settings.qdrant.api_key or None,
        timeout=5,
        check_compatibility=False,
    )
    try:
        yield client
    finally:
        await client.close()


@pytest_asyncio.fixture(autouse=True)
async def reset(
    http_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    qdrant_client: AsyncQdrantClient,
) -> None:
    async with db_session_factory() as session:
        await session.execute(
            text("TRUNCATE TABLE memories, messages, conversations, companions CASCADE")
        )
        await session.commit()
    if await qdrant_client.collection_exists(tests_settings.qdrant.collection):
        await qdrant_client.delete_collection(tests_settings.qdrant.collection)
    response = await http_client.post("/__test__/llm_reset")
    response.raise_for_status()


@pytest.fixture
def fake_llm(http_client: AsyncClient) -> FakeLLMController:
    return FakeLLMController(http_client)


@pytest.fixture
def fake_embeddings(http_client: AsyncClient) -> FakeEmbeddingController:
    return FakeEmbeddingController(http_client)


@pytest.fixture
def fake_vector_index(http_client: AsyncClient) -> FakeVectorIndexController:
    return FakeVectorIndexController(http_client)
