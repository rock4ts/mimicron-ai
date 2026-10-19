from decimal import Decimal
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.uow import UnitOfWork
from app.models.companion import Companion
from app.models.conversation import Conversation
from app.models.memory import MemoryType
from app.repositories.companion_repository import CompanionRepository
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import MemoryCreate
from app.services.chat_service import MEMORY_SYSTEM_PROMPT_PREFIX, TITLE_SYSTEM_PROMPT
from app.services.memory_indexing_service import MemoryIndexingService
from app.services.memory_service import MemoryService
from app.vector_index.qdrant import QdrantMemoryVectorIndex
from tests.functional.fakes import (
    FakeEmbeddingController,
    FakeEmbeddingProvider,
    FakeLLMController,
    FakeVectorIndexController,
)
from tests.functional.settings import tests_settings


async def create_companion(session: AsyncSession, user_id: UUID) -> dict[str, str]:
    companion = Companion(
        name="Nova",
        personality="Спокойная и немного саркастичная.",
        user_id=user_id,
    )
    session.add(companion)
    await session.commit()
    await session.refresh(companion)
    return {"id": str(companion.id)}


async def create_conversation(session: AsyncSession, companion_id: str) -> dict[str, str]:
    conversation = Conversation(companion_id=UUID(companion_id))
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return {"id": str(conversation.id)}


async def test_companion_crud(client: AsyncClient) -> None:
    response = await client.post(
        "/companions",
        json={"name": "Nova", "personality": "Спокойная и немного саркастичная."},
    )
    assert response.status_code == 201
    companion = response.json()

    response = await client.get(f"/companions/{companion['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Nova"

    response = await client.get("/companions")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [companion["id"]]

    response = await client.patch(
        f"/companions/{companion['id']}",
        json={"name": "Nova Prime", "personality": "Любит глубокие разговоры."},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Nova Prime"

    response = await client.delete(f"/companions/{companion['id']}")
    assert response.status_code == 204
    assert (await client.get(f"/companions/{companion['id']}")).status_code == 404


async def test_companion_validation(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    response = await client.post("/companions", json={"name": "  ", "personality": "valid"})
    assert response.status_code == 422

    companion = await create_companion(db_session, user_id)
    response = await client.patch(f"/companions/{companion['id']}", json={})
    assert response.status_code == 422


async def test_conversation_creation_and_cascade_delete(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await create_companion(db_session, user_id)
    response = await client.post(f"/companions/{companion['id']}/conversations")
    assert response.status_code == 201
    conversation = response.json()

    response = await client.get(f"/conversations/{conversation['id']}")
    assert response.status_code == 200
    assert response.json()["companion_id"] == companion["id"]
    assert response.json()["title"] is None

    await client.delete(f"/companions/{companion['id']}")
    assert (await client.get(f"/conversations/{conversation['id']}")).status_code == 404


async def test_send_and_list_messages(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
) -> None:
    companion = await create_companion(db_session, user_id)
    conversation = await create_conversation(db_session, companion["id"])
    await fake_llm.configure(responses=["Привет :)"])

    response = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Привет!"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "assistant"
    assert response.json()["content"] == "Привет :)"

    response = await client.get(f"/conversations/{conversation['id']}/messages")
    assert response.status_code == 200
    assert [(item["role"], item["content"]) for item in response.json()] == [
        ("user", "Привет!"),
        ("assistant", "Привет :)"),
    ]


async def test_history_is_sent_once_and_in_order(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
) -> None:
    companion = await create_companion(db_session, user_id)
    conversation = await create_conversation(db_session, companion["id"])
    await fake_llm.configure(
        responses=["Приятно познакомиться!", "Знакомство", "Тебя зовут Артём."]
    )

    first = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Меня зовут Артём."},
    )
    second = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Как меня зовут?"},
    )
    assert first.status_code == second.status_code == 201

    second_prompt = (await fake_llm.calls())[2]
    assert [(message.role, message.content) for message in second_prompt] == [
        (
            "system",
            "Ты AI-компаньон по имени Nova.\n\nТвоя личность:\nСпокойная и немного саркастичная.",
        ),
        ("user", "Меня зовут Артём."),
        ("assistant", "Приятно познакомиться!"),
        ("user", "Как меня зовут?"),
    ]


async def test_llm_failure_keeps_user_message(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
) -> None:
    companion = await create_companion(db_session, user_id)
    conversation = await create_conversation(db_session, companion["id"])
    await fake_llm.configure(error="upstream failed")

    response = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Ты здесь?"},
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "LLM provider is temporarily unavailable"}

    messages = await client.get(f"/conversations/{conversation['id']}/messages")
    assert [(item["role"], item["content"]) for item in messages.json()] == [
        ("user", "Ты здесь?"),
    ]
    listed = await client.get(f"/conversations/{conversation['id']}")
    assert listed.json()["title"] is None


async def test_llm_timeout_keeps_user_message(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
) -> None:
    companion = await create_companion(db_session, user_id)
    conversation = await create_conversation(db_session, companion["id"])
    await fake_llm.configure(responses=["too late"], delay_seconds=2.0)

    response = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Ты здесь?"},
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "LLM provider is temporarily unavailable"}

    messages = await client.get(f"/conversations/{conversation['id']}/messages")
    assert [(item["role"], item["content"]) for item in messages.json()] == [
        ("user", "Ты здесь?"),
    ]
    fetched = await client.get(f"/conversations/{conversation['id']}")
    assert fetched.json()["title"] is None


async def test_list_companion_conversations(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    companion = await create_companion(db_session, user_id)
    empty = await client.get(f"/companions/{companion['id']}/conversations")
    assert empty.status_code == 200
    assert empty.json() == []

    first = await create_conversation(db_session, companion["id"])
    second = await create_conversation(db_session, companion["id"])
    listed = await client.get(f"/companions/{companion['id']}/conversations")
    assert listed.status_code == 200
    items = listed.json()
    assert {item["id"] for item in items} == {first["id"], second["id"]}
    assert all(item["companion_id"] == companion["id"] for item in items)
    assert all(item["title"] is None for item in items)
    created_at = [item["created_at"] for item in items]
    assert created_at == sorted(created_at, reverse=True)


async def test_first_message_sets_conversation_title(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
) -> None:
    companion = await create_companion(db_session, user_id)
    conversation = await create_conversation(db_session, companion["id"])
    await fake_llm.configure(responses=["Привет :)", '"Приветствие"'])

    response = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Привет!"},
    )
    assert response.status_code == 201
    assert response.json()["content"] == "Привет :)"

    listed = await client.get(f"/companions/{companion['id']}/conversations")
    assert listed.status_code == 200
    assert listed.json()[0]["title"] == "Приветствие"
    fetched = await client.get(f"/conversations/{conversation['id']}")
    assert fetched.json()["title"] == "Приветствие"

    title_prompt = (await fake_llm.calls())[1]
    assert [(message.role, message.content) for message in title_prompt] == [
        ("system", TITLE_SYSTEM_PROMPT),
        (
            "user",
            "Сообщение пользователя:\nПривет!\n\nОтвет компаньона:\nПривет :)",
        ),
    ]


async def test_second_message_does_not_regenerate_title(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
) -> None:
    companion = await create_companion(db_session, user_id)
    conversation = await create_conversation(db_session, companion["id"])
    await fake_llm.configure(responses=["Привет :)", "Приветствие", "Как дела?"])

    first = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Привет!"},
    )
    second = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Что нового?"},
    )
    assert first.status_code == second.status_code == 201

    calls = await fake_llm.calls()
    assert len(calls) == 3
    assert "название диалога" in calls[1][0].content
    assert "AI-компаньон" in calls[2][0].content

    fetched = await client.get(f"/conversations/{conversation['id']}")
    assert fetched.json()["title"] == "Приветствие"


async def test_title_generation_failure_keeps_assistant_reply(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
) -> None:
    companion = await create_companion(db_session, user_id)
    conversation = await create_conversation(db_session, companion["id"])
    await fake_llm.configure(responses=["Привет :)"], error_on_call=1)

    response = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Привет!"},
    )
    assert response.status_code == 201
    assert response.json()["content"] == "Привет :)"

    messages = await client.get(f"/conversations/{conversation['id']}/messages")
    assert [(item["role"], item["content"]) for item in messages.json()] == [
        ("user", "Привет!"),
        ("assistant", "Привет :)"),
    ]
    fetched = await client.get(f"/conversations/{conversation['id']}")
    assert fetched.json()["title"] is None


async def test_empty_title_response_keeps_null_title(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
) -> None:
    companion = await create_companion(db_session, user_id)
    conversation = await create_conversation(db_session, companion["id"])
    await fake_llm.configure(responses=["Привет :)", '  "«»"  '])

    response = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Привет!"},
    )
    assert response.status_code == 201
    fetched = await client.get(f"/conversations/{conversation['id']}")
    assert fetched.json()["title"] is None


async def test_title_is_truncated_to_max_length(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
) -> None:
    companion = await create_companion(db_session, user_id)
    conversation = await create_conversation(db_session, companion["id"])
    await fake_llm.configure(responses=["Привет :)", "А" * 150])

    response = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Привет!"},
    )
    assert response.status_code == 201
    fetched = await client.get(f"/conversations/{conversation['id']}")
    assert fetched.json()["title"] == "А" * 100


async def test_missing_resources(client: AsyncClient) -> None:
    missing_id = uuid4()
    assert (await client.get(f"/companions/{missing_id}")).status_code == 404
    assert (await client.patch(f"/companions/{missing_id}", json={"name": "X"})).status_code == 404
    assert (await client.delete(f"/companions/{missing_id}")).status_code == 404
    assert (await client.post(f"/companions/{missing_id}/conversations")).status_code == 404
    assert (await client.get(f"/companions/{missing_id}/conversations")).status_code == 404
    assert (await client.get(f"/conversations/{missing_id}")).status_code == 404
    assert (await client.get(f"/conversations/{missing_id}/messages")).status_code == 404
    assert (
        await client.post(
            f"/conversations/{missing_id}/messages",
            json={"content": "Привет"},
        )
    ).status_code == 404


def _one_hot(index: int) -> list[float]:
    vector = [0.0] * tests_settings.embedding.dimensions
    vector[index] = 1.0
    return vector


CHARLIE_VECTOR = _one_hot(0)
IRRELEVANT_VECTOR = _one_hot(1)


async def _index_memory(
    session: AsyncSession,
    user_id: UUID,
    companion_id: UUID,
    content: str,
    vector: list[float],
) -> None:
    embeddings = FakeEmbeddingProvider(dimensions=tests_settings.embedding.dimensions)
    embeddings.vectors[content] = vector
    index = QdrantMemoryVectorIndex(
        url=tests_settings.qdrant.url,
        api_key=tests_settings.qdrant.api_key,
        collection=tests_settings.qdrant.collection,
        dimensions=tests_settings.embedding.dimensions,
        distance="Cosine",
    )
    try:
        service = MemoryService(
            CompanionRepository(UnitOfWork(session), user_id),
            MemoryRepository(UnitOfWork(session), user_id),
            MemoryIndexingService(embeddings, index),
        )
        await service.create(
            companion_id,
            MemoryCreate(
                type=MemoryType.FACT,
                content=content,
                importance=Decimal("0.8"),
                confidence=Decimal("0.9"),
            ),
        )
    finally:
        await index.aclose()


async def test_chat_includes_relevant_memory_from_earlier_conversation(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
    fake_embeddings: FakeEmbeddingController,
) -> None:
    companion = await create_companion(db_session, user_id)
    await create_conversation(db_session, companion["id"])
    later = await create_conversation(db_session, companion["id"])
    await _index_memory(
        db_session,
        user_id,
        UUID(companion["id"]),
        "User has a dog named Charlie.",
        CHARLIE_VECTOR,
    )
    await fake_embeddings.configure(
        vectors={"Charlie hasn't been eating today.": CHARLIE_VECTOR},
    )
    await fake_llm.configure(responses=["Charlie should see a vet."])

    response = await client.post(
        f"/conversations/{later['id']}/messages",
        json={"content": "Charlie hasn't been eating today."},
    )
    assert response.status_code == 201

    prompt = (await fake_llm.calls())[0]
    assert prompt[0].role == "system"
    assert "Nova" in prompt[0].content
    assert prompt[1].role == "system"
    assert prompt[1].content.startswith(MEMORY_SYSTEM_PROMPT_PREFIX)
    assert "User has a dog named Charlie." in prompt[1].content
    assert '"type": "fact"' in prompt[1].content
    assert all(
        message.role != "user" or "User has a dog named Charlie." not in message.content
        for message in prompt
    )
    assert prompt[-1].role == "user"
    assert prompt[-1].content == "Charlie hasn't been eating today."
    embedding_calls = await fake_embeddings.calls()
    assert embedding_calls == ["Charlie hasn't been eating today."]


async def test_chat_excludes_irrelevant_memory(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
    fake_embeddings: FakeEmbeddingController,
) -> None:
    companion = await create_companion(db_session, user_id)
    conversation = await create_conversation(db_session, companion["id"])
    await _index_memory(
        db_session,
        user_id,
        UUID(companion["id"]),
        "User has a dog named Charlie.",
        CHARLIE_VECTOR,
    )
    await fake_embeddings.configure(
        vectors={"What is the capital of France?": IRRELEVANT_VECTOR},
    )
    await fake_llm.configure(responses=["Paris."])

    response = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "What is the capital of France?"},
    )
    assert response.status_code == 201

    prompt = (await fake_llm.calls())[0]
    assert [message.role for message in prompt] == ["system", "user"]
    assert "Charlie" not in prompt[0].content
    assert MEMORY_SYSTEM_PROMPT_PREFIX not in prompt[0].content


async def test_chat_works_when_no_memories_exist(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
) -> None:
    companion = await create_companion(db_session, user_id)
    conversation = await create_conversation(db_session, companion["id"])
    await fake_llm.configure(responses=["Привет :)"])

    response = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Привет!"},
    )
    assert response.status_code == 201
    assert response.json()["content"] == "Привет :)"

    prompt = (await fake_llm.calls())[0]
    assert [message.role for message in prompt] == ["system", "user"]
    assert MEMORY_SYSTEM_PROMPT_PREFIX not in prompt[0].content


async def test_chat_works_when_embedding_retrieval_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
    fake_embeddings: FakeEmbeddingController,
) -> None:
    companion = await create_companion(db_session, user_id)
    conversation = await create_conversation(db_session, companion["id"])
    await _index_memory(
        db_session,
        user_id,
        UUID(companion["id"]),
        "User has a dog named Charlie.",
        CHARLIE_VECTOR,
    )
    await fake_embeddings.configure(error="embedding failed")
    await fake_llm.configure(responses=["Привет :)"])

    response = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Charlie hasn't been eating today."},
    )
    assert response.status_code == 201
    assert response.json()["content"] == "Привет :)"

    prompt = (await fake_llm.calls())[0]
    assert MEMORY_SYSTEM_PROMPT_PREFIX not in "".join(message.content for message in prompt)


async def test_chat_works_when_qdrant_retrieval_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
    fake_llm: FakeLLMController,
    fake_vector_index: FakeVectorIndexController,
) -> None:
    companion = await create_companion(db_session, user_id)
    conversation = await create_conversation(db_session, companion["id"])
    await fake_vector_index.configure(error="qdrant down")
    await fake_llm.configure(responses=["Привет :)"])

    response = await client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Привет!"},
    )
    assert response.status_code == 201
    assert response.json()["content"] == "Привет :)"

    prompt = (await fake_llm.calls())[0]
    assert [message.role for message in prompt] == ["system", "user"]
