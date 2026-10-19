import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.uow import UnitOfWork
from app.errors import (
    ConversationNotFoundError,
    LLMProviderError,
    MemoryExtractionError,
    MemoryReconciliationError,
)
from app.llm.base import LLMMessage
from app.models.companion import Companion
from app.models.conversation import Conversation
from app.models.memory import Memory, MemoryType
from app.models.message import Message, MessageRole
from app.repositories.companion_repository import CompanionRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.message_repository import MessageRepository
from app.services.memory_extraction_service import (
    EXTRACTION_SYSTEM_PROMPT,
    MemoryExtractionService,
)
from app.services.memory_indexing_service import MemoryIndexingService
from app.services.memory_management_service import MemoryManagementService
from app.services.memory_service import MemoryService
from tests.functional.fakes import FakeEmbeddingProvider, FakeLLMProvider, FakeMemoryVectorIndex
from tests.functional.jwt import OTHER_USER_ID


def _fake_llm(
    *,
    responses: list[str] | None = None,
    error: str | None = None,
) -> FakeLLMProvider:
    llm = FakeLLMProvider(timeout_seconds=5.0)
    llm.responses = list(responses or [])
    llm.error = error
    return llm


def _candidate(
    *,
    type: str = "fact",
    content: str = "User has a dog named Charlie.",
    importance: float = 0.9,
    confidence: float = 0.99,
) -> dict[str, object]:
    return {
        "type": type,
        "content": content,
        "importance": importance,
        "confidence": confidence,
    }


def _extraction_json(memories: list[dict[str, object]]) -> str:
    return json.dumps({"memories": memories})


def _reconciliation_json(decisions: list[dict[str, object]]) -> str:
    return json.dumps({"decisions": decisions})


def _unrelated_reconciliation(count: int) -> str:
    return _reconciliation_json(
        [{"candidate_index": index, "relation": "unrelated"} for index in range(count)]
    )


def _extraction_service(
    session: AsyncSession,
    user_id: UUID,
    llm: FakeLLMProvider,
    indexing: MemoryIndexingService | None = None,
    embeddings: FakeEmbeddingProvider | None = None,
    vector_index: FakeMemoryVectorIndex | None = None,
) -> MemoryExtractionService:
    uow = UnitOfWork(session)
    embeddings = embeddings or FakeEmbeddingProvider(dimensions=8)
    vector_index = vector_index or FakeMemoryVectorIndex()
    indexing = indexing or MemoryIndexingService(embeddings, vector_index)
    return MemoryExtractionService(
        ConversationRepository(uow, user_id),
        MessageRepository(uow),
        MemoryManagementService(
            CompanionRepository(uow, user_id),
            MemoryRepository(uow, user_id),
            indexing,
            embeddings,
            vector_index,
            llm,
            top_k=10,
            score_threshold=0.55,
        ),
        llm,
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


async def _create_conversation(session: AsyncSession, companion_id: UUID) -> Conversation:
    conversation = Conversation(companion_id=companion_id)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def _add_messages(
    session: AsyncSession,
    conversation_id: UUID,
    turns: list[tuple[MessageRole, str]],
) -> None:
    started_at = datetime.now(UTC)
    for index, (role, content) in enumerate(turns):
        session.add(
            Message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                created_at=started_at + timedelta(seconds=index),
            )
        )
    await session.commit()


async def _memory_count(session: AsyncSession) -> int:
    result = await session.scalar(select(func.count()).select_from(Memory))
    return int(result or 0)


async def test_extracts_factual_memory(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    llm = _fake_llm(responses=[_extraction_json([_candidate()]), _unrelated_reconciliation(1)])
    service = _extraction_service(db_session, user_id, llm)

    memories = await service.extract_from_conversation(conversation.id)

    assert len(memories) == 1
    memory = memories[0]
    assert memory.type is MemoryType.FACT
    assert memory.content == "User has a dog named Charlie."
    assert memory.importance == Decimal("0.9")
    assert memory.confidence == Decimal("0.99")
    assert memory.user_id == user_id
    assert memory.companion_id == companion.id
    assert memory.source_conversation_id == conversation.id
    assert memory.is_active is True
    assert memory.index_sync_pending is False
    assert llm.calls[0][0] == LLMMessage(role="system", content=EXTRACTION_SYSTEM_PROMPT)
    assert llm.calls[0][1:] == [
        LLMMessage(role="user", content="I have a dog named Charlie."),
    ]


@pytest.mark.parametrize(
    ("memory_type", "user_content", "extracted_content"),
    [
        (
            MemoryType.PREFERENCE,
            "I prefer concise answers when we're discussing programming.",
            "User prefers concise answers for programming discussions.",
        ),
        (
            MemoryType.GOAL,
            "I want to learn Rust.",
            "User wants to learn Rust.",
        ),
        (
            MemoryType.EVENT,
            "I graduated from university last June.",
            "User graduated from university last June.",
        ),
        (
            MemoryType.RELATIONSHIP,
            "My sister lives in Berlin.",
            "User's sister lives in Berlin.",
        ),
    ],
)
async def test_extracts_typed_memory(
    db_session: AsyncSession,
    user_id: UUID,
    memory_type: MemoryType,
    user_content: str,
    extracted_content: str,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, user_content)],
    )
    llm = _fake_llm(
        responses=[
            _extraction_json(
                [
                    _candidate(
                        type=memory_type.value,
                        content=extracted_content,
                        importance=0.8,
                        confidence=0.95,
                    )
                ]
            ),
            _unrelated_reconciliation(1),
        ]
    )
    service = _extraction_service(db_session, user_id, llm)

    memories = await service.extract_from_conversation(conversation.id)

    assert len(memories) == 1
    assert memories[0].type is memory_type
    assert memories[0].content == extracted_content
    assert memories[0].importance == Decimal("0.8")
    assert memories[0].confidence == Decimal("0.95")


async def test_conversation_producing_zero_memories_persists_nothing(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "What is the weather today?")],
    )
    llm = _fake_llm(responses=[_extraction_json([])])
    service = _extraction_service(db_session, user_id, llm)

    memories = await service.extract_from_conversation(conversation.id)

    assert memories == []
    assert await _memory_count(db_session) == 0
    assert len(llm.calls) == 1


async def test_multiple_memories_extracted_from_one_conversation(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [
            (MessageRole.USER, "I have a dog named Charlie."),
            (MessageRole.ASSISTANT, "Nice to meet Charlie."),
            (MessageRole.USER, "I prefer concise answers when we're discussing programming."),
        ],
    )
    llm = _fake_llm(
        responses=[
            _extraction_json(
                [
                    _candidate(),
                    _candidate(
                        type="preference",
                        content="User prefers concise answers for programming discussions.",
                        importance=0.8,
                        confidence=0.95,
                    ),
                ]
            ),
            _unrelated_reconciliation(2),
        ]
    )
    service = _extraction_service(db_session, user_id, llm)

    memories = await service.extract_from_conversation(conversation.id)

    assert [memory.type for memory in memories] == [MemoryType.FACT, MemoryType.PREFERENCE]
    assert [memory.content for memory in memories] == [
        "User has a dog named Charlie.",
        "User prefers concise answers for programming discussions.",
    ]
    listed = await MemoryService(
        CompanionRepository(UnitOfWork(db_session), user_id),
        MemoryRepository(UnitOfWork(db_session), user_id),
    ).list_for_companion(companion.id)
    assert {memory.id for memory in listed} == {memory.id for memory in memories}
    assert llm.calls[0][1:] == [
        LLMMessage(role="user", content="I have a dog named Charlie."),
        LLMMessage(role="assistant", content="Nice to meet Charlie."),
        LLMMessage(
            role="user",
            content="I prefer concise answers when we're discussing programming.",
        ),
    ]


@pytest.mark.parametrize("field", ["importance", "confidence"])
@pytest.mark.parametrize("value", [-0.0001, 1.0001])
async def test_out_of_range_scores_persist_nothing(
    db_session: AsyncSession,
    user_id: UUID,
    field: str,
    value: float,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    candidate = _candidate()
    candidate[field] = value
    llm = _fake_llm(responses=[_extraction_json([candidate])])
    service = _extraction_service(db_session, user_id, llm)

    with pytest.raises(MemoryExtractionError):
        await service.extract_from_conversation(conversation.id)

    assert await _memory_count(db_session) == 0


async def test_malformed_llm_output_persists_nothing(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    llm = _fake_llm(responses=["not-json"])
    service = _extraction_service(db_session, user_id, llm)

    with pytest.raises(MemoryExtractionError):
        await service.extract_from_conversation(conversation.id)

    assert await _memory_count(db_session) == 0


async def test_json_fences_are_rejected(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    fenced = "```json\n" + _extraction_json([_candidate()]) + "\n```"
    llm = _fake_llm(responses=[fenced])
    service = _extraction_service(db_session, user_id, llm)

    with pytest.raises(MemoryExtractionError):
        await service.extract_from_conversation(conversation.id)

    assert await _memory_count(db_session) == 0


async def test_unsupported_memory_type_persists_nothing(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    llm = _fake_llm(responses=[_extraction_json([_candidate(type="hobby")])])
    service = _extraction_service(db_session, user_id, llm)

    with pytest.raises(MemoryExtractionError):
        await service.extract_from_conversation(conversation.id)

    assert await _memory_count(db_session) == 0


async def test_blank_content_and_unknown_fields_persist_nothing(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    service = _extraction_service(
        db_session,
        user_id,
        _fake_llm(responses=[_extraction_json([_candidate(content="   ")])]),
    )

    with pytest.raises(MemoryExtractionError):
        await service.extract_from_conversation(conversation.id)
    assert await _memory_count(db_session) == 0

    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    extra_field = _candidate()
    extra_field["source"] = "invented"
    service = _extraction_service(
        db_session,
        user_id,
        _fake_llm(responses=[_extraction_json([extra_field])]),
    )

    with pytest.raises(MemoryExtractionError):
        await service.extract_from_conversation(conversation.id)
    assert await _memory_count(db_session) == 0

    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    service = _extraction_service(
        db_session,
        user_id,
        _fake_llm(responses=[json.dumps({"memories": [_candidate()], "notes": "nope"})]),
    )

    with pytest.raises(MemoryExtractionError):
        await service.extract_from_conversation(conversation.id)
    assert await _memory_count(db_session) == 0


@pytest.mark.parametrize(
    "error",
    [
        "LLM request failed",
        "LLM request timed out",
    ],
)
async def test_llm_failure_persists_nothing(
    db_session: AsyncSession,
    user_id: UUID,
    error: str,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    llm = _fake_llm(error=error)
    service = _extraction_service(db_session, user_id, llm)

    with pytest.raises(LLMProviderError, match=error):
        await service.extract_from_conversation(conversation.id)

    assert await _memory_count(db_session) == 0
    stored_messages = await MessageRepository(UnitOfWork(db_session)).list_for_conversation(
        conversation.id
    )
    assert [message.content for message in stored_messages] == ["I have a dog named Charlie."]


async def test_empty_conversation_skips_llm(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    llm = _fake_llm(responses=[_extraction_json([_candidate()]), _unrelated_reconciliation(1)])
    service = _extraction_service(db_session, user_id, llm)

    memories = await service.extract_from_conversation(conversation.id)

    assert memories == []
    assert llm.calls == []
    assert await _memory_count(db_session) == 0


async def test_missing_or_foreign_conversation_is_rejected_before_llm(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    foreign_companion = await _create_companion(db_session, OTHER_USER_ID, name="Theirs")
    foreign_conversation = await _create_conversation(db_session, foreign_companion.id)
    await _add_messages(
        db_session,
        foreign_conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    llm = _fake_llm(responses=[_extraction_json([_candidate()]), _unrelated_reconciliation(1)])
    service = _extraction_service(db_session, user_id, llm)

    with pytest.raises(ConversationNotFoundError):
        await service.extract_from_conversation(foreign_conversation.id)
    with pytest.raises(ConversationNotFoundError):
        await service.extract_from_conversation(uuid4())

    assert llm.calls == []
    assert await _memory_count(db_session) == 0


async def test_ownership_propagates_from_conversation_to_memory(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    other_companion = await _create_companion(db_session, user_id, name="Other")
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    llm = _fake_llm(responses=[_extraction_json([_candidate()]), _unrelated_reconciliation(1)])
    service = _extraction_service(db_session, user_id, llm)

    memories = await service.extract_from_conversation(conversation.id)

    assert len(memories) == 1
    stored = await db_session.get(Memory, memories[0].id)
    assert stored is not None
    assert stored.user_id == user_id
    assert stored.companion_id == companion.id
    assert stored.companion_id != other_companion.id
    other_listed = await MemoryService(
        CompanionRepository(UnitOfWork(db_session), user_id),
        MemoryRepository(UnitOfWork(db_session), user_id),
    ).list_for_companion(other_companion.id)
    assert other_listed == []


async def test_extraction_indexes_through_memory_service(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    embeddings = FakeEmbeddingProvider(dimensions=8)
    vector_index = FakeMemoryVectorIndex()
    service = _extraction_service(
        db_session,
        user_id,
        _fake_llm(responses=[_extraction_json([_candidate()]), _unrelated_reconciliation(1)]),
        MemoryIndexingService(embeddings, vector_index),
        embeddings=embeddings,
        vector_index=vector_index,
    )

    memories = await service.extract_from_conversation(conversation.id)

    assert len(memories) == 1
    point = vector_index.points[memories[0].id]
    assert point["user_id"] == str(user_id)
    assert point["companion_id"] == str(companion.id)
    assert point["memory_type"] == "fact"
    assert point["is_active"] is True
    assert embeddings.calls == [
        "User has a dog named Charlie.",
        "User has a dog named Charlie.",
    ]


async def test_repeated_extraction_does_not_duplicate_exact_memory(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    llm = _fake_llm(
        responses=[
            _extraction_json([_candidate()]),
            _unrelated_reconciliation(1),
            _extraction_json([_candidate()]),
        ]
    )
    service = _extraction_service(db_session, user_id, llm)

    first = await service.extract_from_conversation(conversation.id)
    second = await service.extract_from_conversation(conversation.id)

    assert len(first) == 1
    assert second == []
    assert await _memory_count(db_session) == 1
    stored = await db_session.get(Memory, first[0].id)
    assert stored is not None
    assert stored.is_active is True
    assert stored.source_conversation_id == conversation.id
    assert len(llm.calls) == 3


async def test_reconciliation_failure_persists_nothing(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    await _add_messages(
        db_session,
        conversation.id,
        [(MessageRole.USER, "I have a dog named Charlie.")],
    )
    llm = _fake_llm(responses=[_extraction_json([_candidate()]), "not-json"])
    service = _extraction_service(db_session, user_id, llm)

    with pytest.raises(MemoryReconciliationError):
        await service.extract_from_conversation(conversation.id)

    assert await _memory_count(db_session) == 0
