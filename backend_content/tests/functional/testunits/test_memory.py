from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.uow import UnitOfWork
from app.errors import CompanionNotFoundError, MemoryNotFoundError
from app.models.companion import Companion
from app.models.memory import DeactivationReason, Memory, MemoryType
from app.repositories.companion_repository import CompanionRepository
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.services.companion_service import CompanionService
from app.services.memory_indexing_service import MemoryIndexingService
from app.services.memory_service import MemoryService
from tests.functional.fakes import FakeEmbeddingProvider, FakeMemoryVectorIndex
from tests.functional.jwt import OTHER_USER_ID


def _payload(**overrides: object) -> MemoryCreate:
    data: dict[str, object] = {
        "type": MemoryType.FACT,
        "content": "User has a dog named Charlie.",
        "importance": Decimal("0.8"),
        "confidence": Decimal("0.9"),
    }
    data.update(overrides)
    return MemoryCreate.model_validate(data)


def _memory_service(
    session: AsyncSession,
    user_id: UUID,
    indexing: MemoryIndexingService | None = None,
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


async def test_memory_create_persists_defaults(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id)

    memory = await service.create(companion.id, _payload())

    stored = await db_session.get(Memory, memory.id)
    assert stored is not None
    assert stored.user_id == user_id
    assert stored.companion_id == companion.id
    assert stored.type is MemoryType.FACT
    assert stored.content == "User has a dog named Charlie."
    assert stored.importance == Decimal("0.8")
    assert stored.confidence == Decimal("0.9")
    assert stored.is_active is True
    assert stored.last_accessed_at is None
    assert stored.source_conversation_id is None
    assert stored.superseded_by_id is None
    assert stored.deactivated_at is None
    assert stored.deactivation_reason is None
    assert stored.index_sync_pending is True
    assert stored.created_at is not None
    assert stored.updated_at is not None


async def test_get_returns_memory_for_owning_user_and_companion(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id)
    created = await service.create(companion.id, _payload())

    fetched = await service.get(created.id, companion.id)

    assert fetched.id == created.id
    assert fetched.content == created.content


async def test_get_another_users_memory_raises_not_found(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    foreign_companion = await _create_companion(db_session, OTHER_USER_ID, name="Theirs")
    foreign_service = _memory_service(db_session, OTHER_USER_ID)
    memory = await foreign_service.create(foreign_companion.id, _payload())

    with pytest.raises(MemoryNotFoundError):
        await _memory_service(db_session, user_id).get(memory.id, foreign_companion.id)


async def test_get_same_user_wrong_companion_raises_not_found(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    other = await _create_companion(db_session, user_id, name="Other")
    service = _memory_service(db_session, user_id)
    memory = await service.create(companion.id, _payload())

    with pytest.raises(MemoryNotFoundError):
        await service.get(memory.id, other.id)


async def test_list_for_companion_is_newest_first_and_scoped(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    other = await _create_companion(db_session, user_id, name="Other")
    service = _memory_service(db_session, user_id)
    first = await service.create(companion.id, _payload(content="First fact"))
    second = await service.create(companion.id, _payload(content="Second fact"))
    await service.create(other.id, _payload(content="Other companion"))

    listed = await service.list_for_companion(companion.id)

    assert {memory.id for memory in listed} == {first.id, second.id}
    assert listed == sorted(
        listed,
        key=lambda memory: (memory.created_at, memory.id),
        reverse=True,
    )


async def test_list_defaults_to_active_and_can_include_inactive(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id)
    active = await service.create(companion.id, _payload(content="Active"))
    inactive = await service.create(companion.id, _payload(content="Inactive"))
    await service.deactivate(inactive.id, companion.id)

    listed = await service.list_for_companion(companion.id)
    assert [memory.id for memory in listed] == [active.id]

    including_inactive = await service.list_for_companion(companion.id, include_inactive=True)
    assert {memory.id for memory in including_inactive} == {active.id, inactive.id}
    stored = await db_session.get(Memory, inactive.id)
    assert stored is not None
    assert stored.is_active is False


async def test_update_mutates_allowed_fields_only(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id)
    memory = await service.create(companion.id, _payload())
    created_at = memory.created_at
    last_accessed_at = memory.last_accessed_at

    updated = await service.update(
        memory.id,
        companion.id,
        MemoryUpdate(
            type=MemoryType.PREFERENCE,
            content="User prefers concise explanations.",
            importance=Decimal("0.4"),
            confidence=Decimal("0.6"),
        ),
    )

    assert updated.user_id == user_id
    assert updated.companion_id == companion.id
    assert updated.type is MemoryType.PREFERENCE
    assert updated.content == "User prefers concise explanations."
    assert updated.importance == Decimal("0.4")
    assert updated.confidence == Decimal("0.6")
    assert updated.is_active is True
    assert updated.last_accessed_at == last_accessed_at
    assert updated.created_at == created_at


async def test_deactivate_is_idempotent(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id)
    memory = await service.create(companion.id, _payload())

    first = await service.deactivate(memory.id, companion.id)
    second = await service.deactivate(memory.id, companion.id)

    assert first.is_active is False
    assert second.is_active is False
    stored = await db_session.get(Memory, memory.id)
    assert stored is not None
    assert stored.is_active is False
    assert stored.deactivation_reason is DeactivationReason.MANUAL
    assert stored.deactivated_at is not None
    assert stored.superseded_by_id is None


@pytest.mark.parametrize("memory_type", list(MemoryType))
async def test_valid_memory_types_persist(
    db_session: AsyncSession,
    user_id: UUID,
    memory_type: MemoryType,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id)

    memory = await service.create(companion.id, _payload(type=memory_type))

    assert memory.type is memory_type
    stored = await db_session.get(Memory, memory.id)
    assert stored is not None
    assert stored.type is memory_type


def test_invalid_memory_type_is_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        MemoryCreate.model_validate(
            {
                "type": "unknown",
                "content": "Invalid type",
                "importance": "0.5",
                "confidence": "0.5",
            }
        )


async def test_invalid_memory_type_is_rejected_by_database(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)

    with pytest.raises(DBAPIError):
        await db_session.execute(
            text(
                """
                INSERT INTO memories (
                    id, user_id, companion_id, type, content, importance, confidence
                )
                VALUES (
                    :id, :user_id, :companion_id, 'not_a_type', 'Invalid', 0.5, 0.5
                )
                """
            ),
            {
                "id": uuid4(),
                "user_id": user_id,
                "companion_id": companion.id,
            },
        )
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize(
    "value", [Decimal("0"), Decimal("1"), Decimal("0.0000"), Decimal("1.0000")]
)
async def test_importance_and_confidence_accept_range_boundaries(
    db_session: AsyncSession,
    user_id: UUID,
    value: Decimal,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id)

    memory = await service.create(
        companion.id,
        _payload(importance=value, confidence=value),
    )

    assert memory.importance == value
    assert memory.confidence == value


@pytest.mark.parametrize("field", ["importance", "confidence"])
@pytest.mark.parametrize("value", [Decimal("-0.0001"), Decimal("1.0001")])
def test_schema_rejects_importance_and_confidence_outside_range(
    field: str,
    value: Decimal,
) -> None:
    with pytest.raises(ValidationError):
        _payload(**{field: value})


@pytest.mark.parametrize("field", ["importance", "confidence"])
@pytest.mark.parametrize("value", [Decimal("-0.0001"), Decimal("1.0001")])
async def test_database_enforces_importance_and_confidence_range(
    db_session: AsyncSession,
    user_id: UUID,
    field: str,
    value: Decimal,
) -> None:
    companion = await _create_companion(db_session, user_id)
    values = {
        "importance": Decimal("0.5"),
        "confidence": Decimal("0.5"),
        field: value,
    }
    db_session.add(
        Memory(
            user_id=user_id,
            companion_id=companion.id,
            type=MemoryType.FACT,
            content="Out of range",
            importance=values["importance"],
            confidence=values["confidence"],
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_cannot_create_memory_for_unowned_or_legacy_companion(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    service = _memory_service(db_session, user_id)
    foreign = await _create_companion(db_session, OTHER_USER_ID, name="Theirs")
    legacy = await _create_companion(db_session, None, name="Legacy")

    with pytest.raises(CompanionNotFoundError):
        await service.create(foreign.id, _payload())
    with pytest.raises(CompanionNotFoundError):
        await service.create(legacy.id, _payload())
    with pytest.raises(CompanionNotFoundError):
        await service.create_many(foreign.id, [_payload()])
    with pytest.raises(CompanionNotFoundError):
        await service.list_for_companion(foreign.id)


async def test_create_many_persists_multiple_payloads_atomically(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id)
    payloads = [
        _payload(content="User has a dog named Charlie."),
        _payload(
            type=MemoryType.PREFERENCE,
            content="User prefers concise explanations.",
            importance=Decimal("0.7"),
            confidence=Decimal("0.8"),
        ),
    ]

    created = await service.create_many(companion.id, payloads)

    assert len(created) == 2
    assert [memory.content for memory in created] == [
        "User has a dog named Charlie.",
        "User prefers concise explanations.",
    ]
    listed = await service.list_for_companion(companion.id)
    assert {memory.id for memory in listed} == {memory.id for memory in created}
    for memory in created:
        assert memory.user_id == user_id
        assert memory.companion_id == companion.id
        assert memory.is_active is True


async def test_create_many_empty_payloads_returns_empty_without_rows(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id)

    created = await service.create_many(companion.id, [])

    assert created == []
    assert await service.list_for_companion(companion.id) == []


async def test_companion_deletion_cascades_to_memories(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id)
    memory = await service.create(companion.id, _payload())
    companions = CompanionService(CompanionRepository(UnitOfWork(db_session), user_id))

    await companions.delete(companion.id)
    db_session.expunge_all()

    assert await db_session.get(Memory, memory.id) is None
    assert await db_session.get(Companion, companion.id) is None


def test_memory_update_requires_at_least_one_non_null_field() -> None:
    with pytest.raises(ValidationError):
        MemoryUpdate()
    with pytest.raises(ValidationError):
        MemoryUpdate(content=None)
    with pytest.raises(ValidationError):
        MemoryUpdate.model_validate({"content": "   "})


def _failing_indexing(
    *,
    error_on_call: int | None = None,
) -> tuple[MemoryIndexingService, FakeEmbeddingProvider, FakeMemoryVectorIndex]:
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.error = None if error_on_call is not None else "embedding failed"
    embeddings.error_on_call = error_on_call
    vector_index = FakeMemoryVectorIndex()
    return MemoryIndexingService(embeddings, vector_index), embeddings, vector_index


async def test_create_keeps_postgres_row_when_indexing_fails(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    indexing, _, vector_index = _failing_indexing()
    service = _memory_service(db_session, user_id, indexing)

    memory = await service.create(companion.id, _payload())

    stored = await db_session.get(Memory, memory.id)
    assert stored is not None
    assert stored.content == "User has a dog named Charlie."
    assert stored.index_sync_pending is True
    assert vector_index.points == {}


async def test_create_many_indexes_remaining_memories_after_one_failure(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    indexing, embeddings, vector_index = _failing_indexing(error_on_call=1)
    embeddings.error = None
    service = _memory_service(db_session, user_id, indexing)
    payloads = [
        _payload(content="First fact"),
        _payload(content="Second fact"),
        _payload(content="Third fact"),
    ]

    created = await service.create_many(companion.id, payloads)

    assert len(created) == 3
    listed = await service.list_for_companion(companion.id)
    assert {memory.content for memory in listed} == {
        "First fact",
        "Second fact",
        "Third fact",
    }
    assert {point["memory_id"] for point in vector_index.points.values()} == {
        str(created[0].id),
        str(created[2].id),
    }
    assert created[0].index_sync_pending is False
    assert created[1].index_sync_pending is True
    assert created[2].index_sync_pending is False


async def test_active_memory_rejects_deactivation_metadata(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id)
    memory = await service.create(companion.id, _payload())
    stored = await db_session.get(Memory, memory.id)
    assert stored is not None
    stored.deactivation_reason = DeactivationReason.MANUAL

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_superseded_memory_must_be_inactive(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    service = _memory_service(db_session, user_id)
    original = await service.create(companion.id, _payload(content="Original"))
    replacement = await service.create(companion.id, _payload(content="Replacement"))
    stored = await db_session.get(Memory, original.id)
    assert stored is not None
    stored.superseded_by_id = replacement.id

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
