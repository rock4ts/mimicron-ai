import json
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.uow import UnitOfWork
from app.errors import (
    CompanionNotFoundError,
    EmbeddingProviderError,
    LLMProviderError,
    MemoryIndexOutOfSyncError,
    MemoryReconciliationError,
    VectorIndexError,
)
from app.models.companion import Companion
from app.models.conversation import Conversation
from app.models.memory import DeactivationReason, Memory, MemoryType
from app.repositories.companion_repository import CompanionRepository
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import MemoryCreate
from app.schemas.memory_extraction import MemoryCandidate
from app.schemas.memory_management import MemoryReconciliationDecision
from app.services.memory_indexing_service import MemoryIndexingService
from app.services.memory_management_service import MemoryManagementService
from app.services.memory_retrieval_service import MemoryRetrievalService
from app.services.memory_service import MemoryService
from tests.functional.fakes import FakeEmbeddingProvider, FakeLLMProvider, FakeMemoryVectorIndex
from tests.functional.jwt import OTHER_USER_ID


def _one_hot(index: int) -> list[float]:
    vector = [0.0] * 8
    vector[index] = 1.0
    return vector


CHARLIE_VECTOR = _one_hot(0)
TEA_VECTOR = _one_hot(1)
CITY_VECTOR = _one_hot(2)
PYTHON_VECTOR = _one_hot(3)


def _candidate(
    *,
    type: str = "fact",
    content: str = "User has a dog named Charlie.",
    importance: float = 0.9,
    confidence: float = 0.99,
) -> MemoryCandidate:
    return MemoryCandidate.model_validate(
        {
            "type": type,
            "content": content,
            "importance": importance,
            "confidence": confidence,
        }
    )


def _payload(**overrides: object) -> MemoryCreate:
    data: dict[str, object] = {
        "type": MemoryType.FACT,
        "content": "User has a dog named Charlie.",
        "importance": Decimal("0.8"),
        "confidence": Decimal("0.9"),
    }
    data.update(overrides)
    return MemoryCreate.model_validate(data)


def _reconciliation_json(decisions: list[dict[str, object]]) -> str:
    return json.dumps({"decisions": decisions})


def _unrelated(count: int) -> str:
    return _reconciliation_json(
        [{"candidate_index": index, "relation": "unrelated"} for index in range(count)]
    )


def _fake_llm(responses: list[str] | None = None, error: str | None = None) -> FakeLLMProvider:
    llm = FakeLLMProvider(timeout_seconds=5.0)
    llm.responses = list(responses or [])
    llm.error = error
    return llm


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


def _management_service(
    session: AsyncSession,
    user_id: UUID,
    llm: FakeLLMProvider,
    embeddings: FakeEmbeddingProvider | None = None,
    vector_index: FakeMemoryVectorIndex | None = None,
) -> tuple[MemoryManagementService, FakeEmbeddingProvider, FakeMemoryVectorIndex]:
    embeddings = embeddings or FakeEmbeddingProvider(dimensions=8)
    vector_index = vector_index or FakeMemoryVectorIndex()
    uow = UnitOfWork(session)
    service = MemoryManagementService(
        CompanionRepository(uow, user_id),
        MemoryRepository(uow, user_id),
        MemoryIndexingService(embeddings, vector_index),
        embeddings,
        vector_index,
        llm,
        top_k=10,
        score_threshold=0.55,
    )
    return service, embeddings, vector_index


async def _memory_count(session: AsyncSession) -> int:
    result = await session.scalar(select(func.count()).select_from(Memory))
    return int(result or 0)


def test_reconciliation_schema_requires_existing_id_for_replacement() -> None:
    with pytest.raises(ValidationError):
        MemoryReconciliationDecision.model_validate({"candidate_index": 0, "relation": "update"})
    with pytest.raises(ValidationError):
        MemoryReconciliationDecision.model_validate(
            {
                "candidate_index": 0,
                "relation": "unrelated",
                "existing_memory_id": str(uuid4()),
            }
        )
    with pytest.raises(ValidationError):
        MemoryReconciliationDecision.model_validate({"candidate_index": 0, "relation": "unknown"})


async def test_exact_duplicate_is_skipped_without_llm(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    llm = _fake_llm(responses=[_unrelated(1)])
    management, embeddings, vector_index = _management_service(db_session, user_id, llm)
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    existing = await service.create(companion.id, _payload())
    llm.calls.clear()

    created = await management.ingest(companion.id, [_candidate()])

    assert created == []
    assert llm.calls == []
    listed = await service.list_for_companion(companion.id, include_inactive=True)
    assert [memory.id for memory in listed] == [existing.id]
    assert listed[0].is_active is True


async def test_semantically_equivalent_memory_is_treated_as_duplicate(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.vectors["User has a dog named Charlie."] = CHARLIE_VECTOR
    embeddings.vectors["User owns a dog called Charlie."] = CHARLIE_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    existing = await service.create(companion.id, _payload())
    llm = _fake_llm(
        responses=[
            _reconciliation_json(
                [
                    {
                        "candidate_index": 0,
                        "relation": "duplicate",
                        "existing_memory_id": str(existing.id),
                    }
                ]
            )
        ]
    )
    management, _, _ = _management_service(
        db_session,
        user_id,
        llm,
        embeddings=embeddings,
        vector_index=vector_index,
    )

    created = await management.ingest(
        companion.id,
        [_candidate(content="User owns a dog called Charlie.")],
    )

    assert created == []
    listed = await service.list_for_companion(companion.id, include_inactive=True)
    assert [memory.id for memory in listed] == [existing.id]
    assert listed[0].content == "User has a dog named Charlie."
    assert listed[0].is_active is True


async def test_unrelated_memory_is_created(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.vectors["User has a dog named Charlie."] = CHARLIE_VECTOR
    embeddings.vectors["User prefers tea."] = TEA_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    existing = await service.create(companion.id, _payload())
    llm = _fake_llm(responses=[_unrelated(1)])
    management, _, _ = _management_service(
        db_session,
        user_id,
        llm,
        embeddings=embeddings,
        vector_index=vector_index,
    )

    created = await management.ingest(
        companion.id,
        [
            _candidate(
                type="preference", content="User prefers tea.", importance=0.7, confidence=0.8
            )
        ],
    )

    assert len(created) == 1
    assert created[0].content == "User prefers tea."
    listed = await service.list_for_companion(companion.id)
    assert {memory.id for memory in listed} == {existing.id, created[0].id}


async def test_additional_information_keeps_existing_active(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.vectors["User has a dog named Charlie."] = CHARLIE_VECTOR
    embeddings.vectors["User's dog Charlie is three years old."] = CHARLIE_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    existing = await service.create(companion.id, _payload())
    llm = _fake_llm(
        responses=[_reconciliation_json([{"candidate_index": 0, "relation": "additional"}])]
    )
    management, _, _ = _management_service(
        db_session,
        user_id,
        llm,
        embeddings=embeddings,
        vector_index=vector_index,
    )

    created = await management.ingest(
        companion.id,
        [_candidate(content="User's dog Charlie is three years old.")],
    )

    assert len(created) == 1
    stored_existing = await db_session.get(Memory, existing.id)
    stored_new = await db_session.get(Memory, created[0].id)
    assert stored_existing is not None
    assert stored_new is not None
    assert stored_existing.is_active is True
    assert stored_new.is_active is True
    assert stored_existing.superseded_by_id is None


async def test_update_deactivates_superseded_memory(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.vectors["User lives in Amsterdam."] = CITY_VECTOR
    embeddings.vectors["User moved to Rotterdam."] = CITY_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    existing = await service.create(
        companion.id,
        _payload(content="User lives in Amsterdam."),
    )
    llm = _fake_llm(
        responses=[
            _reconciliation_json(
                [
                    {
                        "candidate_index": 0,
                        "relation": "update",
                        "existing_memory_id": str(existing.id),
                    }
                ]
            )
        ]
    )
    management, _, _ = _management_service(
        db_session,
        user_id,
        llm,
        embeddings=embeddings,
        vector_index=vector_index,
    )

    created = await management.ingest(
        companion.id,
        [_candidate(content="User moved to Rotterdam.")],
        source_conversation_id=None,
    )

    assert len(created) == 1
    replacement = await db_session.get(Memory, created[0].id)
    old = await db_session.get(Memory, existing.id)
    assert replacement is not None
    assert old is not None
    assert replacement.is_active is True
    assert replacement.content == "User moved to Rotterdam."
    assert old.is_active is False
    assert old.deactivation_reason is DeactivationReason.UPDATED
    assert old.deactivated_at is not None
    assert old.superseded_by_id == replacement.id
    assert vector_index.points[old.id]["is_active"] is False
    assert vector_index.points[replacement.id]["is_active"] is True


async def test_contradiction_deactivates_obsolete_memory(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.vectors["User is learning Python."] = PYTHON_VECTOR
    embeddings.vectors["User stopped learning Python."] = PYTHON_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    existing = await service.create(
        companion.id,
        _payload(content="User is learning Python."),
    )
    llm = _fake_llm(
        responses=[
            _reconciliation_json(
                [
                    {
                        "candidate_index": 0,
                        "relation": "contradiction",
                        "existing_memory_id": str(existing.id),
                    }
                ]
            )
        ]
    )
    management, _, _ = _management_service(
        db_session,
        user_id,
        llm,
        embeddings=embeddings,
        vector_index=vector_index,
    )

    created = await management.ingest(
        companion.id,
        [_candidate(content="User stopped learning Python.")],
    )

    assert len(created) == 1
    old = await db_session.get(Memory, existing.id)
    assert old is not None
    assert old.is_active is False
    assert old.deactivation_reason is DeactivationReason.CONTRADICTED
    assert old.superseded_by_id == created[0].id
    retrieval = MemoryRetrievalService(
        embeddings,
        vector_index,
        MemoryRepository(UnitOfWork(db_session), user_id),
        top_k=5,
        score_threshold=0.55,
    )
    results = await retrieval.retrieve(companion.id, "User stopped learning Python.")
    assert [item.memory.id for item in results] == [created[0].id]


async def test_unrelated_memories_are_preserved_during_update(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.vectors["User lives in Amsterdam."] = CITY_VECTOR
    embeddings.vectors["User moved to Rotterdam."] = CITY_VECTOR
    embeddings.vectors["User prefers tea."] = TEA_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    city = await service.create(companion.id, _payload(content="User lives in Amsterdam."))
    tea = await service.create(companion.id, _payload(content="User prefers tea."))
    llm = _fake_llm(
        responses=[
            _reconciliation_json(
                [
                    {
                        "candidate_index": 0,
                        "relation": "update",
                        "existing_memory_id": str(city.id),
                    }
                ]
            )
        ]
    )
    management, _, _ = _management_service(
        db_session,
        user_id,
        llm,
        embeddings=embeddings,
        vector_index=vector_index,
    )

    created = await management.ingest(
        companion.id,
        [_candidate(content="User moved to Rotterdam.")],
    )

    stored_tea = await db_session.get(Memory, tea.id)
    stored_city = await db_session.get(Memory, city.id)
    assert stored_tea is not None
    assert stored_city is not None
    assert stored_tea.is_active is True
    assert stored_tea.content == "User prefers tea."
    assert stored_city.is_active is False
    assert created[0].is_active is True
    assert vector_index.points[tea.id]["is_active"] is True


async def test_same_batch_exact_duplicates_create_once(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    llm = _fake_llm(responses=[_unrelated(1)])
    management, _, vector_index = _management_service(db_session, user_id, llm)

    created = await management.ingest(
        companion.id,
        [
            _candidate(),
            _candidate(content="  User has a dog named Charlie.  "),
        ],
    )

    assert len(created) == 1
    assert await _memory_count(db_session) == 1
    assert created[0].id in vector_index.points
    assert len(llm.calls) == 1


async def test_discard_persists_nothing(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    llm = _fake_llm(
        responses=[_reconciliation_json([{"candidate_index": 0, "relation": "discard"}])]
    )
    management, _, _ = _management_service(db_session, user_id, llm)

    created = await management.ingest(
        companion.id,
        [_candidate(content="User asked what time it is.", importance=0.1, confidence=0.2)],
    )

    assert created == []
    assert await _memory_count(db_session) == 0


async def test_malformed_and_hallucinated_decisions_persist_nothing(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.vectors["User has a dog named Charlie."] = CHARLIE_VECTOR
    embeddings.vectors["User owns a dog called Charlie."] = CHARLIE_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    existing = await service.create(companion.id, _payload())

    llm = _fake_llm(responses=["not-json"])
    management, _, _ = _management_service(
        db_session,
        user_id,
        llm,
        embeddings=embeddings,
        vector_index=vector_index,
    )
    with pytest.raises(MemoryReconciliationError):
        await management.ingest(
            companion.id,
            [_candidate(content="User owns a dog called Charlie.")],
        )
    assert await _memory_count(db_session) == 1

    llm.responses = [
        _reconciliation_json(
            [
                {
                    "candidate_index": 0,
                    "relation": "update",
                    "existing_memory_id": str(uuid4()),
                }
            ]
        )
    ]
    with pytest.raises(MemoryReconciliationError):
        await management.ingest(
            companion.id,
            [_candidate(content="User owns a dog called Charlie.")],
        )
    stored = await db_session.get(Memory, existing.id)
    assert stored is not None
    assert stored.is_active is True
    assert await _memory_count(db_session) == 1


async def test_conflicting_batch_decisions_persist_nothing(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.vectors["User lives in Amsterdam."] = CITY_VECTOR
    embeddings.vectors["User moved to Rotterdam."] = CITY_VECTOR
    embeddings.vectors["User now lives in Rotterdam."] = CITY_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    existing = await service.create(
        companion.id,
        _payload(content="User lives in Amsterdam."),
    )
    llm = _fake_llm(
        responses=[
            _reconciliation_json(
                [
                    {
                        "candidate_index": 0,
                        "relation": "update",
                        "existing_memory_id": str(existing.id),
                    },
                    {
                        "candidate_index": 1,
                        "relation": "contradiction",
                        "existing_memory_id": str(existing.id),
                    },
                ]
            )
        ]
    )
    management, _, _ = _management_service(
        db_session,
        user_id,
        llm,
        embeddings=embeddings,
        vector_index=vector_index,
    )

    with pytest.raises(MemoryReconciliationError):
        await management.ingest(
            companion.id,
            [
                _candidate(content="User moved to Rotterdam."),
                _candidate(content="User now lives in Rotterdam."),
            ],
        )

    stored = await db_session.get(Memory, existing.id)
    assert stored is not None
    assert stored.is_active is True
    assert await _memory_count(db_session) == 1


async def test_multiple_candidates_mixed_relations(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.vectors["User lives in Amsterdam."] = CITY_VECTOR
    embeddings.vectors["User moved to Rotterdam."] = CITY_VECTOR
    embeddings.vectors["User prefers tea."] = TEA_VECTOR
    embeddings.vectors["User has a dog named Charlie."] = CHARLIE_VECTOR
    embeddings.vectors["User owns a dog called Charlie."] = CHARLIE_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    city = await service.create(companion.id, _payload(content="User lives in Amsterdam."))
    dog = await service.create(companion.id, _payload())
    llm = _fake_llm(
        responses=[
            _reconciliation_json(
                [
                    {
                        "candidate_index": 0,
                        "relation": "update",
                        "existing_memory_id": str(city.id),
                    },
                    {"candidate_index": 1, "relation": "unrelated"},
                    {
                        "candidate_index": 2,
                        "relation": "duplicate",
                        "existing_memory_id": str(dog.id),
                    },
                ]
            )
        ]
    )
    management, _, _ = _management_service(
        db_session,
        user_id,
        llm,
        embeddings=embeddings,
        vector_index=vector_index,
    )

    created = await management.ingest(
        companion.id,
        [
            _candidate(content="User moved to Rotterdam."),
            _candidate(type="preference", content="User prefers tea."),
            _candidate(content="User owns a dog called Charlie."),
        ],
    )

    assert [memory.content for memory in created] == [
        "User moved to Rotterdam.",
        "User prefers tea.",
    ]
    stored_city = await db_session.get(Memory, city.id)
    stored_dog = await db_session.get(Memory, dog.id)
    assert stored_city is not None
    assert stored_dog is not None
    assert stored_city.is_active is False
    assert stored_dog.is_active is True
    active = await service.list_for_companion(companion.id)
    assert {memory.content for memory in active} == {
        "User moved to Rotterdam.",
        "User prefers tea.",
        "User has a dog named Charlie.",
    }


async def test_ownership_isolation_ignores_foreign_memories(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    other = await _create_companion(db_session, user_id, name="Other")
    foreign = await _create_companion(db_session, OTHER_USER_ID, name="Theirs")
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.vectors["User has a dog named Charlie."] = CHARLIE_VECTOR
    embeddings.vectors["User owns a dog called Charlie."] = CHARLIE_VECTOR
    vector_index = FakeMemoryVectorIndex()
    own_service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    foreign_service = _memory_service(
        db_session,
        OTHER_USER_ID,
        MemoryIndexingService(embeddings, vector_index),
    )
    await own_service.create(other.id, _payload())
    foreign_memory = await foreign_service.create(foreign.id, _payload())
    llm = _fake_llm(responses=[_unrelated(1)])
    management, _, _ = _management_service(
        db_session,
        user_id,
        llm,
        embeddings=embeddings,
        vector_index=vector_index,
    )

    created = await management.ingest(
        companion.id,
        [_candidate(content="User owns a dog called Charlie.")],
    )

    assert len(created) == 1
    assert created[0].companion_id == companion.id
    stored_foreign = await db_session.get(Memory, foreign_memory.id)
    assert stored_foreign is not None
    assert stored_foreign.is_active is True
    listed_other = await own_service.list_for_companion(other.id)
    assert len(listed_other) == 1
    assert listed_other[0].is_active is True


async def test_cannot_ingest_for_unowned_companion(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    foreign = await _create_companion(db_session, OTHER_USER_ID, name="Theirs")
    llm = _fake_llm(responses=[_unrelated(1)])
    management, _, _ = _management_service(db_session, user_id, llm)

    with pytest.raises(CompanionNotFoundError):
        await management.ingest(foreign.id, [_candidate()])
    assert llm.calls == []
    assert await _memory_count(db_session) == 0


async def test_llm_failure_during_reconciliation_persists_nothing(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    llm = _fake_llm(error="LLM request failed")
    management, _, _ = _management_service(db_session, user_id, llm)

    with pytest.raises(LLMProviderError, match="LLM request failed"):
        await management.ingest(companion.id, [_candidate()])

    assert await _memory_count(db_session) == 0


async def test_embedding_failure_during_search_persists_nothing(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    llm = _fake_llm(responses=[_unrelated(1)])
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.error = "embedding failed"
    management, _, _ = _management_service(db_session, user_id, llm, embeddings=embeddings)

    with pytest.raises(EmbeddingProviderError, match="embedding failed"):
        await management.ingest(companion.id, [_candidate()])

    assert await _memory_count(db_session) == 0
    assert llm.calls == []


async def test_vector_index_failure_during_search_persists_nothing(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    llm = _fake_llm(responses=[_unrelated(1)])
    vector_index = FakeMemoryVectorIndex()
    vector_index.error = "qdrant down"
    management, _, _ = _management_service(db_session, user_id, llm, vector_index=vector_index)

    with pytest.raises(VectorIndexError, match="qdrant down"):
        await management.ingest(companion.id, [_candidate()])

    assert await _memory_count(db_session) == 0


async def test_pending_active_index_blocks_semantic_ingest(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.vectors["User has a dog named Charlie."] = CHARLIE_VECTOR
    embeddings.vectors["User prefers tea."] = TEA_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    existing = await service.create(companion.id, _payload())
    stored = await db_session.get(Memory, existing.id)
    assert stored is not None
    stored.index_sync_pending = True
    await db_session.commit()
    vector_index.error = "qdrant down"
    llm = _fake_llm(responses=[_unrelated(1)])
    management, _, _ = _management_service(
        db_session,
        user_id,
        llm,
        embeddings=embeddings,
        vector_index=vector_index,
    )

    with pytest.raises(MemoryIndexOutOfSyncError):
        await management.ingest(
            companion.id,
            [_candidate(type="preference", content="User prefers tea.")],
        )

    assert await _memory_count(db_session) == 1
    assert llm.calls == []


async def test_qdrant_failure_after_commit_keeps_canonical_state(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings = FakeEmbeddingProvider(dimensions=8)
    embeddings.vectors["User has a dog named Charlie."] = CHARLIE_VECTOR
    embeddings.vectors["User prefers tea."] = TEA_VECTOR
    vector_index = FakeMemoryVectorIndex()
    llm = _fake_llm(responses=[_unrelated(1)])
    management, _, _ = _management_service(
        db_session,
        user_id,
        llm,
        embeddings=embeddings,
        vector_index=vector_index,
    )

    class FlakyIndex(FakeMemoryVectorIndex):
        async def upsert(self, **kwargs: object) -> None:
            raise VectorIndexError("qdrant down")

    management.vector_index = FlakyIndex()
    management.indexing = MemoryIndexingService(embeddings, management.vector_index)

    created = await management.ingest(
        companion.id,
        [_candidate(type="preference", content="User prefers tea.")],
    )

    assert len(created) == 1
    stored = await db_session.get(Memory, created[0].id)
    assert stored is not None
    assert stored.content == "User prefers tea."
    assert stored.index_sync_pending is True


async def test_ingest_records_source_conversation(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = Conversation(companion_id=companion.id)
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    llm = _fake_llm(responses=[_unrelated(1)])
    management, _, _ = _management_service(db_session, user_id, llm)

    created = await management.ingest(
        companion.id,
        [_candidate()],
        source_conversation_id=conversation.id,
    )

    assert len(created) == 1
    assert created[0].source_conversation_id == conversation.id
    stored = await db_session.get(Memory, created[0].id)
    assert stored is not None
    assert stored.source_conversation_id == conversation.id
