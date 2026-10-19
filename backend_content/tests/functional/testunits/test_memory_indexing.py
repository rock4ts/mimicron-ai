from collections.abc import AsyncIterator, Sequence
from decimal import Decimal
from math import sqrt
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.uow import UnitOfWork
from app.errors import VectorIndexError
from app.models.companion import Companion
from app.models.memory import Memory, MemoryType
from app.repositories.companion_repository import CompanionRepository
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.services.companion_service import CompanionService
from app.services.memory_indexing_service import (
    MemoryIndexingService,
    reindex_active_memories,
    sync_pending_memories,
)
from app.services.memory_service import MemoryService
from app.vector_index.qdrant import QdrantMemoryVectorIndex
from tests.functional.fakes import FakeEmbeddingProvider, FakeMemoryVectorIndex
from tests.functional.jwt import OTHER_USER_ID
from tests.functional.settings import tests_settings


def _payload(**overrides: object) -> MemoryCreate:
    data: dict[str, object] = {
        "type": MemoryType.FACT,
        "content": "User has a dog named Charlie.",
        "importance": Decimal("0.8"),
        "confidence": Decimal("0.9"),
    }
    data.update(overrides)
    return MemoryCreate.model_validate(data)


def _vector_index() -> QdrantMemoryVectorIndex:
    return QdrantMemoryVectorIndex(
        url=tests_settings.qdrant.url,
        api_key=tests_settings.qdrant.api_key,
        collection=tests_settings.qdrant.collection,
        dimensions=tests_settings.embedding.dimensions,
        distance="Cosine",
    )


def _memory_service(
    session: AsyncSession,
    user_id: UUID,
    indexing: MemoryIndexingService,
) -> MemoryService:
    uow = UnitOfWork(session)
    return MemoryService(
        CompanionRepository(uow, user_id),
        MemoryRepository(uow, user_id),
        indexing,
    )


async def _create_companion(
    session: AsyncSession,
    user_id: UUID | None,
    *,
    name: str = "Nova",
) -> Companion:
    companion = Companion(name=name, personality="A helper.", user_id=user_id)
    session.add(companion)
    await session.commit()
    await session.refresh(companion)
    return companion


def _as_vector(point: models.Record) -> list[float]:
    vector = point.vector
    if isinstance(vector, dict):
        vector = next(iter(vector.values()))
    assert vector is not None
    return list(vector)


def _normalize(vector: Sequence[float]) -> list[float]:
    norm = sqrt(sum(value * value for value in vector))
    assert norm > 0
    return [value / norm for value in vector]


def _assert_same_vector(actual: Sequence[float], expected: Sequence[float]) -> None:
    actual_normalized = _normalize(actual)
    expected_normalized = _normalize(expected)
    assert len(actual_normalized) == len(expected_normalized)
    for left, right in zip(actual_normalized, expected_normalized, strict=True):
        assert left == pytest.approx(right, rel=1e-5, abs=1e-5)


async def _retrieve(
    client: AsyncQdrantClient,
    memory_id: UUID,
) -> models.Record | None:
    points = await client.retrieve(
        collection_name=tests_settings.qdrant.collection,
        ids=[str(memory_id)],
        with_payload=True,
        with_vectors=True,
    )
    return points[0] if points else None


async def _scroll_filtered(
    client: AsyncQdrantClient,
    *,
    user_id: UUID,
    companion_id: UUID,
    is_active: bool = True,
) -> list[models.Record]:
    points, _offset = await client.scroll(
        collection_name=tests_settings.qdrant.collection,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=str(user_id)),
                ),
                models.FieldCondition(
                    key="companion_id",
                    match=models.MatchValue(value=str(companion_id)),
                ),
                models.FieldCondition(
                    key="is_active",
                    match=models.MatchValue(value=is_active),
                ),
            ]
        ),
        with_payload=True,
        with_vectors=True,
    )
    return list(points)


@pytest_asyncio.fixture
async def vector_index() -> AsyncIterator[QdrantMemoryVectorIndex]:
    index = _vector_index()
    try:
        yield index
    finally:
        await index.aclose()


@pytest.fixture
def embeddings() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dimensions=tests_settings.embedding.dimensions)


@pytest.fixture
def indexing(
    embeddings: FakeEmbeddingProvider,
    vector_index: QdrantMemoryVectorIndex,
) -> MemoryIndexingService:
    return MemoryIndexingService(embeddings, vector_index)


async def test_indexes_memory_with_stable_id_and_payload(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
    indexing: MemoryIndexingService,
    qdrant_client: AsyncQdrantClient,
) -> None:
    companion = await _create_companion(db_session, user_id)
    expected = [0.11, 0.22, 0.33, 0.44, 0.55, 0.66, 0.77, 0.88]
    embeddings.vectors["User has a dog named Charlie."] = expected
    service = _memory_service(db_session, user_id, indexing)

    memory = await service.create(companion.id, _payload())

    point = await _retrieve(qdrant_client, memory.id)
    assert point is not None
    assert str(point.id) == str(memory.id)
    _assert_same_vector(_as_vector(point), expected)
    assert point.payload == {
        "memory_id": str(memory.id),
        "user_id": str(user_id),
        "companion_id": str(companion.id),
        "memory_type": "fact",
        "is_active": True,
    }
    assert embeddings.calls == ["User has a dog named Charlie."]
    stored = await db_session.get(Memory, memory.id)
    assert stored is not None
    assert stored.index_sync_pending is False


async def test_payload_is_filterable_by_owner_and_active_state(
    db_session: AsyncSession,
    user_id: UUID,
    indexing: MemoryIndexingService,
    qdrant_client: AsyncQdrantClient,
) -> None:
    companion = await _create_companion(db_session, user_id)
    other = await _create_companion(db_session, user_id, name="Other")
    foreign = await _create_companion(db_session, OTHER_USER_ID, name="Theirs")
    service = _memory_service(db_session, user_id, indexing)
    foreign_service = _memory_service(db_session, OTHER_USER_ID, indexing)
    matching = await service.create(companion.id, _payload(content="Matching"))
    await service.create(other.id, _payload(content="Other companion"))
    inactive = await service.create(companion.id, _payload(content="Inactive"))
    await service.deactivate(inactive.id, companion.id)
    await foreign_service.create(foreign.id, _payload(content="Foreign"))

    points = await _scroll_filtered(
        qdrant_client,
        user_id=user_id,
        companion_id=companion.id,
        is_active=True,
    )

    assert [str(point.id) for point in points] == [str(matching.id)]
    assert points[0].payload is not None
    assert points[0].payload["user_id"] == str(user_id)
    assert points[0].payload["companion_id"] == str(companion.id)
    assert points[0].payload["is_active"] is True


async def test_update_reembeds_when_content_changes(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
    indexing: MemoryIndexingService,
    qdrant_client: AsyncQdrantClient,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id, indexing)
    memory = await service.create(companion.id, _payload())
    updated_content = "User prefers concise explanations."
    expected = embeddings.vector_for(updated_content)

    updated = await service.update(
        memory.id,
        companion.id,
        MemoryUpdate(content=updated_content, type=MemoryType.PREFERENCE),
    )

    point = await _retrieve(qdrant_client, updated.id)
    assert point is not None
    _assert_same_vector(_as_vector(point), expected)
    assert point.payload is not None
    assert point.payload["memory_type"] == "preference"
    assert embeddings.calls == [
        "User has a dog named Charlie.",
        updated_content,
    ]


async def test_metadata_update_reembeds_and_heals_missing_point(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
    indexing: MemoryIndexingService,
    qdrant_client: AsyncQdrantClient,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id, indexing)
    memory = await service.create(companion.id, _payload())
    original_vector = embeddings.vector_for(memory.content)

    updated = await service.update(
        memory.id,
        companion.id,
        MemoryUpdate(type=MemoryType.GOAL),
    )
    point = await _retrieve(qdrant_client, updated.id)
    assert point is not None
    _assert_same_vector(_as_vector(point), original_vector)
    assert point.payload is not None
    assert point.payload["memory_type"] == "goal"
    assert embeddings.calls == [
        "User has a dog named Charlie.",
        "User has a dog named Charlie.",
    ]

    await qdrant_client.delete(
        collection_name=tests_settings.qdrant.collection,
        points_selector=[str(memory.id)],
    )
    assert await _retrieve(qdrant_client, memory.id) is None

    healed = await service.update(
        memory.id,
        companion.id,
        MemoryUpdate(type=MemoryType.EVENT),
    )
    point = await _retrieve(qdrant_client, healed.id)
    assert point is not None
    _assert_same_vector(_as_vector(point), original_vector)
    assert point.payload is not None
    assert point.payload["memory_type"] == "event"
    assert embeddings.calls == [
        "User has a dog named Charlie.",
        "User has a dog named Charlie.",
        "User has a dog named Charlie.",
    ]


async def test_deactivate_marks_index_inactive_and_ignores_missing_point(
    db_session: AsyncSession,
    user_id: UUID,
    indexing: MemoryIndexingService,
    qdrant_client: AsyncQdrantClient,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id, indexing)
    memory = await service.create(companion.id, _payload())

    deactivated = await service.deactivate(memory.id, companion.id)
    point = await _retrieve(qdrant_client, deactivated.id)
    assert point is not None
    assert point.payload is not None
    assert point.payload["is_active"] is False
    stored = await db_session.get(Memory, memory.id)
    assert stored is not None
    assert stored.is_active is False
    assert stored.index_sync_pending is False

    await qdrant_client.delete(
        collection_name=tests_settings.qdrant.collection,
        points_selector=[str(memory.id)],
    )
    again = await service.deactivate(memory.id, companion.id)
    assert again.is_active is False
    assert await _retrieve(qdrant_client, memory.id) is None


async def test_indexing_is_idempotent(
    db_session: AsyncSession,
    user_id: UUID,
    indexing: MemoryIndexingService,
    qdrant_client: AsyncQdrantClient,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id, indexing)
    memory = await service.create(companion.id, _payload())

    await indexing.index(memory)
    await indexing.index(memory)

    points, _offset = await qdrant_client.scroll(
        collection_name=tests_settings.qdrant.collection,
        with_payload=True,
    )
    assert [str(point.id) for point in points] == [str(memory.id)]


async def test_companion_deletion_removes_qdrant_points(
    db_session: AsyncSession,
    user_id: UUID,
    indexing: MemoryIndexingService,
    qdrant_client: AsyncQdrantClient,
) -> None:
    companion = await _create_companion(db_session, user_id)
    other = await _create_companion(db_session, user_id, name="Other")
    service = _memory_service(db_session, user_id, indexing)
    memory = await service.create(companion.id, _payload(content="To delete"))
    kept = await service.create(other.id, _payload(content="To keep"))
    companions = CompanionService(
        CompanionRepository(UnitOfWork(db_session), user_id),
        indexing,
    )

    await companions.delete(companion.id)
    db_session.expunge_all()

    assert await db_session.get(Memory, memory.id) is None
    assert await _retrieve(qdrant_client, memory.id) is None
    kept_point = await _retrieve(qdrant_client, kept.id)
    assert kept_point is not None
    assert kept_point.payload is not None
    assert kept_point.payload["companion_id"] == str(other.id)


async def test_qdrant_request_failure_is_wrapped() -> None:
    failing = QdrantMemoryVectorIndex(
        url="http://127.0.0.1:1",
        collection="memories_test",
        dimensions=tests_settings.embedding.dimensions,
        distance="Cosine",
        timeout_seconds=1,
    )
    try:
        with pytest.raises(VectorIndexError, match="Qdrant request failed"):
            await failing.ensure_collection()
    finally:
        await failing.aclose()


async def test_incompatible_collection_is_rejected(
    vector_index: QdrantMemoryVectorIndex,
    qdrant_client: AsyncQdrantClient,
) -> None:
    await qdrant_client.create_collection(
        collection_name=tests_settings.qdrant.collection,
        vectors_config=models.VectorParams(size=3, distance=models.Distance.EUCLID),
    )

    with pytest.raises(VectorIndexError, match="does not match embedding configuration"):
        await vector_index.ensure_collection()


async def test_reindex_rebuilds_active_memories_from_postgres(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
    indexing: MemoryIndexingService,
    vector_index: QdrantMemoryVectorIndex,
    qdrant_client: AsyncQdrantClient,
) -> None:
    companion = await _create_companion(db_session, user_id)
    foreign_companion = await _create_companion(db_session, OTHER_USER_ID, name="Theirs")
    service = _memory_service(db_session, user_id, indexing)
    foreign_service = _memory_service(db_session, OTHER_USER_ID, indexing)
    active = await service.create(companion.id, _payload(content="Active memory"))
    inactive = await service.create(companion.id, _payload(content="Inactive memory"))
    await service.deactivate(inactive.id, companion.id)
    foreign = await foreign_service.create(
        foreign_companion.id,
        _payload(content="Foreign active"),
    )
    stale_id = uuid4()
    await vector_index.upsert(
        memory_id=stale_id,
        vector=embeddings.vector_for("stale"),
        user_id=user_id,
        companion_id=companion.id,
        memory_type="fact",
        is_active=True,
    )

    indexed, failed = await reindex_active_memories(
        UnitOfWork(db_session),
        indexing,
        vector_index,
        batch_size=1,
    )
    again_indexed, again_failed = await reindex_active_memories(
        UnitOfWork(db_session),
        indexing,
        vector_index,
        batch_size=1,
    )

    assert (indexed, failed) == (2, 0)
    assert (again_indexed, again_failed) == (2, 0)
    assert await _retrieve(qdrant_client, stale_id) is None
    assert await _retrieve(qdrant_client, inactive.id) is None
    active_point = await _retrieve(qdrant_client, active.id)
    foreign_point = await _retrieve(qdrant_client, foreign.id)
    assert active_point is not None
    assert foreign_point is not None
    assert active_point.payload == {
        "memory_id": str(active.id),
        "user_id": str(user_id),
        "companion_id": str(companion.id),
        "memory_type": "fact",
        "is_active": True,
    }
    assert foreign_point.payload == {
        "memory_id": str(foreign.id),
        "user_id": str(OTHER_USER_ID),
        "companion_id": str(foreign_companion.id),
        "memory_type": "fact",
        "is_active": True,
    }
    assert (await db_session.get(Memory, active.id)).index_sync_pending is False
    assert (await db_session.get(Memory, foreign.id)).index_sync_pending is False
    assert (await db_session.get(Memory, inactive.id)).index_sync_pending is False


async def test_reindex_counts_individual_failures(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
    indexing: MemoryIndexingService,
    vector_index: QdrantMemoryVectorIndex,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id, indexing)
    first = await service.create(companion.id, _payload(content="Keep this"))
    second = await service.create(companion.id, _payload(content="Fail this"))
    embeddings.calls.clear()
    embeddings.error_on_call = 1

    indexed, failed = await reindex_active_memories(
        UnitOfWork(db_session),
        indexing,
        vector_index,
        batch_size=10,
    )

    assert indexed + failed == 2
    assert failed == 1
    assert indexed == 1
    kept = await db_session.get(Memory, first.id)
    broken = await db_session.get(Memory, second.id)
    assert kept is not None
    assert broken is not None
    assert kept.index_sync_pending is False
    assert broken.index_sync_pending is True


async def test_pending_index_retries_after_qdrant_failure(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
    indexing: MemoryIndexingService,
    vector_index: QdrantMemoryVectorIndex,
    qdrant_client: AsyncQdrantClient,
) -> None:
    companion = await _create_companion(db_session, user_id)
    await vector_index.ensure_collection()
    embeddings.error = "embedding failed"
    service = _memory_service(db_session, user_id, indexing)
    memory = await service.create(companion.id, _payload())
    stored = await db_session.get(Memory, memory.id)
    assert stored is not None
    assert stored.index_sync_pending is True
    assert await _retrieve(qdrant_client, memory.id) is None

    embeddings.error = None
    synced, failed = await sync_pending_memories(UnitOfWork(db_session), indexing, batch_size=10)
    again_synced, again_failed = await sync_pending_memories(
        UnitOfWork(db_session),
        indexing,
        batch_size=10,
    )

    assert (synced, failed) == (1, 0)
    assert (again_synced, again_failed) == (0, 0)
    stored = await db_session.get(Memory, memory.id)
    assert stored is not None
    assert stored.index_sync_pending is False
    point = await _retrieve(qdrant_client, memory.id)
    assert point is not None
    assert point.payload is not None
    assert point.payload["is_active"] is True


async def test_deactivate_keeps_postgres_row_when_index_fails(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings = FakeEmbeddingProvider(dimensions=tests_settings.embedding.dimensions)
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    memory = await service.create(companion.id, _payload())
    vector_index.error = "qdrant down"

    deactivated = await service.deactivate(memory.id, companion.id)

    stored = await db_session.get(Memory, memory.id)
    assert stored is not None
    assert stored.is_active is False
    assert stored.index_sync_pending is True
    assert deactivated.is_active is False
    assert vector_index.points[memory.id]["is_active"] is True
