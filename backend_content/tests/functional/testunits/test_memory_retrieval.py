from collections.abc import AsyncIterator, Sequence
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.uow import UnitOfWork
from app.errors import EmbeddingProviderError, VectorIndexError
from app.llm.base import LLMMessage
from app.models.companion import Companion
from app.models.conversation import Conversation
from app.models.memory import Memory, MemoryType
from app.models.message import Message, MessageRole
from app.repositories.companion_repository import CompanionRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.memory import MemoryCreate
from app.services.chat_service import (
    MEMORY_SYSTEM_PROMPT_PREFIX,
    ChatService,
    build_chat_prompt,
)
from app.services.memory_indexing_service import MemoryIndexingService
from app.services.memory_retrieval_service import MemoryRetrievalService
from app.services.memory_service import MemoryService
from app.vector_index.qdrant import QdrantMemoryVectorIndex
from tests.functional.fakes import FakeEmbeddingProvider, FakeLLMProvider, FakeMemoryVectorIndex
from tests.functional.jwt import OTHER_USER_ID
from tests.functional.settings import tests_settings


def _one_hot(index: int) -> list[float]:
    vector = [0.0] * tests_settings.embedding.dimensions
    vector[index] = 1.0
    return vector


CHARLIE_VECTOR = _one_hot(0)
IRRELEVANT_VECTOR = _one_hot(1)
LOW_SIMILARITY_VECTOR = [0.5, 0.5, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0]


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


def _retrieval_service(
    session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
    vector_index: FakeMemoryVectorIndex | QdrantMemoryVectorIndex,
    *,
    top_k: int = 5,
    score_threshold: float = 0.70,
    memories: MemoryRepository | None = None,
) -> MemoryRetrievalService:
    return MemoryRetrievalService(
        embeddings,
        vector_index,
        memories or MemoryRepository(UnitOfWork(session), user_id),
        top_k=top_k,
        score_threshold=score_threshold,
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


class CountingMemoryRepository(MemoryRepository):
    def __init__(self, uow: UnitOfWork, user_id: UUID) -> None:
        super().__init__(uow, user_id)
        self.get_active_by_ids_calls = 0
        self.received_ids: list[Sequence[UUID]] = []

    async def get_active_by_ids(
        self,
        companion_id: UUID,
        memory_ids: Sequence[UUID],
    ) -> list[Memory]:
        self.get_active_by_ids_calls += 1
        self.received_ids.append(list(memory_ids))
        return await super().get_active_by_ids(companion_id, memory_ids)


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


async def test_search_returns_relevant_memory_and_excludes_irrelevant(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
    indexing: MemoryIndexingService,
    vector_index: QdrantMemoryVectorIndex,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings.vectors["User has a dog named Charlie."] = CHARLIE_VECTOR
    embeddings.vectors["User prefers tea."] = IRRELEVANT_VECTOR
    service = _memory_service(db_session, user_id, indexing)
    matching = await service.create(companion.id, _payload())
    await service.create(companion.id, _payload(content="User prefers tea."))

    matches = await vector_index.search(
        query=CHARLIE_VECTOR,
        user_id=user_id,
        companion_id=companion.id,
        top_k=5,
        score_threshold=0.70,
    )

    assert [match.memory_id for match in matches] == [matching.id]
    assert matches[0].score == pytest.approx(1.0, abs=1e-5)
    assert matches[0].user_id == user_id
    assert matches[0].companion_id == companion.id
    assert matches[0].is_active is True


async def test_search_respects_top_k(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
    indexing: MemoryIndexingService,
    vector_index: QdrantMemoryVectorIndex,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings.vectors["First"] = CHARLIE_VECTOR
    embeddings.vectors["Second"] = CHARLIE_VECTOR
    embeddings.vectors["Third"] = CHARLIE_VECTOR
    service = _memory_service(db_session, user_id, indexing)
    await service.create(companion.id, _payload(content="First"))
    await service.create(companion.id, _payload(content="Second"))
    await service.create(companion.id, _payload(content="Third"))

    matches = await vector_index.search(
        query=CHARLIE_VECTOR,
        user_id=user_id,
        companion_id=companion.id,
        top_k=2,
        score_threshold=0.70,
    )

    assert len(matches) == 2
    assert all(match.score == pytest.approx(1.0, abs=1e-5) for match in matches)


async def test_search_respects_similarity_threshold(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
    indexing: MemoryIndexingService,
    vector_index: QdrantMemoryVectorIndex,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings.vectors["User has a dog named Charlie."] = CHARLIE_VECTOR
    service = _memory_service(db_session, user_id, indexing)
    await service.create(companion.id, _payload())

    below = await vector_index.search(
        query=LOW_SIMILARITY_VECTOR,
        user_id=user_id,
        companion_id=companion.id,
        top_k=5,
        score_threshold=0.70,
    )
    above = await vector_index.search(
        query=CHARLIE_VECTOR,
        user_id=user_id,
        companion_id=companion.id,
        top_k=5,
        score_threshold=0.70,
    )

    assert below == []
    assert len(above) == 1


async def test_search_is_scoped_to_user_and_companion(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
    indexing: MemoryIndexingService,
    vector_index: QdrantMemoryVectorIndex,
) -> None:
    companion = await _create_companion(db_session, user_id)
    other = await _create_companion(db_session, user_id, name="Other")
    foreign = await _create_companion(db_session, OTHER_USER_ID, name="Theirs")
    embeddings.vectors["Matching"] = CHARLIE_VECTOR
    embeddings.vectors["Other companion"] = CHARLIE_VECTOR
    embeddings.vectors["Foreign"] = CHARLIE_VECTOR
    service = _memory_service(db_session, user_id, indexing)
    foreign_service = _memory_service(db_session, OTHER_USER_ID, indexing)
    matching = await service.create(companion.id, _payload(content="Matching"))
    await service.create(other.id, _payload(content="Other companion"))
    await foreign_service.create(foreign.id, _payload(content="Foreign"))

    matches = await vector_index.search(
        query=CHARLIE_VECTOR,
        user_id=user_id,
        companion_id=companion.id,
        top_k=5,
        score_threshold=0.70,
    )

    assert [match.memory_id for match in matches] == [matching.id]


async def test_search_excludes_inactive_payload(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
    indexing: MemoryIndexingService,
    vector_index: QdrantMemoryVectorIndex,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings.vectors["Active"] = CHARLIE_VECTOR
    embeddings.vectors["Inactive"] = CHARLIE_VECTOR
    service = _memory_service(db_session, user_id, indexing)
    active = await service.create(companion.id, _payload(content="Active"))
    inactive = await service.create(companion.id, _payload(content="Inactive"))
    await service.deactivate(inactive.id, companion.id)

    matches = await vector_index.search(
        query=CHARLIE_VECTOR,
        user_id=user_id,
        companion_id=companion.id,
        top_k=5,
        score_threshold=0.70,
    )

    assert [match.memory_id for match in matches] == [active.id]


async def test_search_returns_empty_when_collection_is_empty(
    user_id: UUID,
    vector_index: QdrantMemoryVectorIndex,
) -> None:
    await vector_index.ensure_collection()

    matches = await vector_index.search(
        query=CHARLIE_VECTOR,
        user_id=user_id,
        companion_id=uuid4(),
        top_k=5,
        score_threshold=0.70,
    )

    assert matches == []


async def test_search_wraps_missing_collection_as_vector_index_error(
    user_id: UUID,
    vector_index: QdrantMemoryVectorIndex,
) -> None:
    with pytest.raises(VectorIndexError, match="Qdrant request failed"):
        await vector_index.search(
            query=CHARLIE_VECTOR,
            user_id=user_id,
            companion_id=uuid4(),
            top_k=5,
            score_threshold=0.70,
        )


async def test_retrieve_embeds_once_and_resolves_postgres(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings.vectors["User has a dog named Charlie."] = CHARLIE_VECTOR
    embeddings.vectors["Charlie hasn't been eating today."] = CHARLIE_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    memory = await service.create(companion.id, _payload())
    embeddings.calls.clear()
    retrieval = _retrieval_service(db_session, user_id, embeddings, vector_index)

    results = await retrieval.retrieve(companion.id, "Charlie hasn't been eating today.")

    assert embeddings.calls == ["Charlie hasn't been eating today."]
    assert len(results) == 1
    assert results[0].memory.id == memory.id
    assert results[0].memory.content == "User has a dog named Charlie."
    assert results[0].score == pytest.approx(1.0, abs=1e-5)
    assert len(vector_index.search_calls) == 1


async def test_postgres_content_is_canonical(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings.vectors["User has a dog named Charlie."] = CHARLIE_VECTOR
    embeddings.vectors["Charlie hasn't been eating today."] = CHARLIE_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    memory = await service.create(companion.id, _payload())
    stored = await db_session.get(Memory, memory.id)
    assert stored is not None
    stored.content = "User has a cat named Charlie."
    stored.type = MemoryType.RELATIONSHIP
    await db_session.commit()
    retrieval = _retrieval_service(db_session, user_id, embeddings, vector_index)

    results = await retrieval.retrieve(companion.id, "Charlie hasn't been eating today.")

    assert len(results) == 1
    assert results[0].memory.content == "User has a cat named Charlie."
    assert results[0].memory.type is MemoryType.RELATIONSHIP


async def test_postgres_inactive_memory_is_excluded_even_if_qdrant_is_active(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings.vectors["User has a dog named Charlie."] = CHARLIE_VECTOR
    embeddings.vectors["Charlie hasn't been eating today."] = CHARLIE_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    memory = await service.create(companion.id, _payload())
    stored = await db_session.get(Memory, memory.id)
    assert stored is not None
    stored.is_active = False
    await db_session.commit()
    retrieval = _retrieval_service(db_session, user_id, embeddings, vector_index)

    results = await retrieval.retrieve(companion.id, "Charlie hasn't been eating today.")

    assert results == []
    assert vector_index.points[memory.id]["is_active"] is True


async def test_postgres_rejects_foreign_and_wrong_companion_leaks(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
) -> None:
    companion = await _create_companion(db_session, user_id)
    other = await _create_companion(db_session, user_id, name="Other")
    foreign = await _create_companion(db_session, OTHER_USER_ID, name="Theirs")
    embeddings.vectors["Own"] = CHARLIE_VECTOR
    embeddings.vectors["Other companion"] = CHARLIE_VECTOR
    embeddings.vectors["Foreign"] = CHARLIE_VECTOR
    embeddings.vectors["Charlie hasn't been eating today."] = CHARLIE_VECTOR
    own_index = FakeMemoryVectorIndex()
    leaky = FakeMemoryVectorIndex()
    own_service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, own_index),
    )
    foreign_service = _memory_service(
        db_session,
        OTHER_USER_ID,
        MemoryIndexingService(embeddings, leaky),
    )
    own = await own_service.create(companion.id, _payload(content="Own"))
    wrong_companion = await own_service.create(other.id, _payload(content="Other companion"))
    foreign_memory = await foreign_service.create(foreign.id, _payload(content="Foreign"))
    leaky.points[own.id] = own_index.points[own.id]
    leaky.points[wrong_companion.id] = {
        **own_index.points[wrong_companion.id],
        "companion_id": str(companion.id),
    }
    leaky.points[foreign_memory.id] = {
        **leaky.points[foreign_memory.id],
        "user_id": str(user_id),
        "companion_id": str(companion.id),
    }
    retrieval = _retrieval_service(db_session, user_id, embeddings, leaky)

    results = await retrieval.retrieve(companion.id, "Charlie hasn't been eating today.")

    assert [item.memory.id for item in results] == [own.id]


async def test_stale_qdrant_ids_are_omitted(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings.vectors["Charlie hasn't been eating today."] = CHARLIE_VECTOR
    vector_index = FakeMemoryVectorIndex()
    await vector_index.upsert(
        memory_id=uuid4(),
        vector=CHARLIE_VECTOR,
        user_id=user_id,
        companion_id=companion.id,
        memory_type="fact",
        is_active=True,
    )
    retrieval = _retrieval_service(db_session, user_id, embeddings, vector_index)

    results = await retrieval.retrieve(companion.id, "Charlie hasn't been eating today.")

    assert results == []


async def test_scores_and_order_are_preserved(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
) -> None:
    companion = await _create_companion(db_session, user_id)
    first_vector = [1.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    second_vector = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    embeddings.vectors["First"] = first_vector
    embeddings.vectors["Second"] = second_vector
    embeddings.vectors["query"] = CHARLIE_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    first = await service.create(companion.id, _payload(content="First"))
    second = await service.create(companion.id, _payload(content="Second"))
    retrieval = _retrieval_service(db_session, user_id, embeddings, vector_index)

    results = await retrieval.retrieve(companion.id, "query")

    assert [item.memory.id for item in results] == [second.id, first.id]
    assert results[0].score > results[1].score


async def test_multiple_memories_are_resolved_in_one_query(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings.vectors["First"] = CHARLIE_VECTOR
    embeddings.vectors["Second"] = CHARLIE_VECTOR
    embeddings.vectors["query"] = CHARLIE_VECTOR
    vector_index = FakeMemoryVectorIndex()
    service = _memory_service(
        db_session,
        user_id,
        MemoryIndexingService(embeddings, vector_index),
    )
    first = await service.create(companion.id, _payload(content="First"))
    second = await service.create(companion.id, _payload(content="Second"))
    repo = CountingMemoryRepository(UnitOfWork(db_session), user_id)
    retrieval = _retrieval_service(
        db_session,
        user_id,
        embeddings,
        vector_index,
        memories=repo,
    )

    results = await retrieval.retrieve(companion.id, "query")

    assert {item.memory.id for item in results} == {first.id, second.id}
    assert repo.get_active_by_ids_calls == 1
    assert set(repo.received_ids[0]) == {first.id, second.id}


async def test_retrieve_skips_postgres_when_qdrant_is_empty(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings.vectors["query"] = CHARLIE_VECTOR
    repo = CountingMemoryRepository(UnitOfWork(db_session), user_id)
    retrieval = _retrieval_service(
        db_session,
        user_id,
        embeddings,
        FakeMemoryVectorIndex(),
        memories=repo,
    )

    results = await retrieval.retrieve(companion.id, "query")

    assert results == []
    assert repo.get_active_by_ids_calls == 0
    assert embeddings.calls == ["query"]


async def test_retrieve_propagates_embedding_failure(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings.error = "embedding failed"
    retrieval = _retrieval_service(
        db_session,
        user_id,
        embeddings,
        FakeMemoryVectorIndex(),
    )

    with pytest.raises(EmbeddingProviderError, match="embedding failed"):
        await retrieval.retrieve(companion.id, "query")


async def test_retrieve_propagates_vector_index_failure(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
) -> None:
    companion = await _create_companion(db_session, user_id)
    embeddings.vectors["query"] = CHARLIE_VECTOR
    vector_index = FakeMemoryVectorIndex()
    vector_index.error = "qdrant down"
    retrieval = _retrieval_service(db_session, user_id, embeddings, vector_index)

    with pytest.raises(VectorIndexError, match="qdrant down"):
        await retrieval.retrieve(companion.id, "query")


async def test_get_active_by_ids_returns_empty_without_ids(
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await _create_companion(db_session, user_id)
    repo = MemoryRepository(UnitOfWork(db_session), user_id)

    assert await repo.get_active_by_ids(companion.id, []) == []


async def test_build_chat_prompt_keeps_memories_out_of_user_messages() -> None:
    companion = Companion(name="Nova", personality="Calm.")
    history = [
        Message(
            conversation_id=uuid4(),
            role=MessageRole.USER,
            content="Charlie hasn't been eating today.",
        )
    ]
    memory = Memory(
        user_id=uuid4(),
        companion_id=uuid4(),
        type=MemoryType.FACT,
        content="User has a dog named Charlie.",
        importance=Decimal("0.8"),
        confidence=Decimal("0.9"),
    )

    prompt = build_chat_prompt(companion, history, [memory])

    assert prompt[0].role == "system"
    assert "Nova" in prompt[0].content
    assert prompt[1].role == "system"
    assert prompt[1].content.startswith(MEMORY_SYSTEM_PROMPT_PREFIX)
    assert '"type": "fact"' in prompt[1].content
    assert "User has a dog named Charlie." in prompt[1].content
    assert "11111111" not in prompt[1].content
    assert prompt[2] == LLMMessage(
        role="user",
        content="Charlie hasn't been eating today.",
    )
    assert all(
        message.role != "user" or "dog named Charlie" not in message.content
        for message in prompt[:-1]
    )


async def test_build_chat_prompt_omits_memory_block_when_empty() -> None:
    companion = Companion(name="Nova", personality="Calm.")
    history = [Message(conversation_id=uuid4(), role=MessageRole.USER, content="Hello")]

    prompt = build_chat_prompt(companion, history, [])

    assert [message.role for message in prompt] == ["system", "user"]
    assert MEMORY_SYSTEM_PROMPT_PREFIX not in prompt[0].content


async def _create_conversation(session: AsyncSession, companion_id: UUID) -> Conversation:
    conversation = Conversation(companion_id=companion_id)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def test_chat_continues_when_postgres_resolution_fails(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)
    embeddings.vectors["Hello"] = CHARLIE_VECTOR
    vector_index = FakeMemoryVectorIndex()
    await vector_index.upsert(
        memory_id=uuid4(),
        vector=CHARLIE_VECTOR,
        user_id=user_id,
        companion_id=companion.id,
        memory_type="fact",
        is_active=True,
    )

    class FailingRepository(MemoryRepository):
        async def get_active_by_ids(
            self,
            companion_id: UUID,
            memory_ids: Sequence[UUID],
        ) -> list[Memory]:
            raise OperationalError("SELECT", {}, Exception("connection lost"))

    retrieval = MemoryRetrievalService(
        embeddings,
        vector_index,
        FailingRepository(UnitOfWork(db_session), user_id),
        top_k=5,
        score_threshold=0.70,
    )
    llm = FakeLLMProvider(timeout_seconds=5.0)
    llm.responses = ["Still here"]
    chat = ChatService(
        CompanionRepository(UnitOfWork(db_session), user_id),
        ConversationRepository(UnitOfWork(db_session), user_id),
        MessageRepository(UnitOfWork(db_session)),
        llm,
        retrieval,
    )

    message = await chat.send_message(conversation.id, "Hello")

    assert message.content == "Still here"
    assert llm.calls[0][0].role == "system"
    assert MEMORY_SYSTEM_PROMPT_PREFIX not in llm.calls[0][0].content
    assert [item.role for item in llm.calls[0]] == ["system", "user"]


async def test_chat_does_not_swallow_programming_errors(
    db_session: AsyncSession,
    user_id: UUID,
    embeddings: FakeEmbeddingProvider,
) -> None:
    companion = await _create_companion(db_session, user_id)
    conversation = await _create_conversation(db_session, companion.id)

    class BrokenRetrieval(MemoryRetrievalService):
        async def retrieve(self, companion_id: UUID, query: str):
            raise RuntimeError("invariant broken")

    retrieval = BrokenRetrieval(
        embeddings,
        FakeMemoryVectorIndex(),
        MemoryRepository(UnitOfWork(db_session), user_id),
        top_k=5,
        score_threshold=0.70,
    )
    chat = ChatService(
        CompanionRepository(UnitOfWork(db_session), user_id),
        ConversationRepository(UnitOfWork(db_session), user_id),
        MessageRepository(UnitOfWork(db_session)),
        FakeLLMProvider(timeout_seconds=5.0),
        retrieval,
    )

    with pytest.raises(RuntimeError, match="invariant broken"):
        await chat.send_message(conversation.id, "Hello")
