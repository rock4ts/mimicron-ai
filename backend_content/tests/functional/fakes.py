import asyncio
import hashlib
from collections.abc import Sequence
from math import sqrt
from uuid import UUID

from httpx import AsyncClient

from app.embeddings.base import EmbeddingProvider
from app.errors import EmbeddingProviderError, LLMProviderError, VectorIndexError
from app.llm.base import LLMMessage, LLMProvider
from app.vector_index.base import MemoryVectorIndex, MemoryVectorMatch


class FakeLLMProvider(LLMProvider):
    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self.responses: list[str] = []
        self.calls: list[list[LLMMessage]] = []
        self.error: str | None = None
        self.error_on_call: int | None = None
        self.delay_seconds: float = 0.0

    async def generate_response(self, messages: list[LLMMessage]) -> str:
        call_index = len(self.calls)
        self.calls.append(messages)
        try:
            return await asyncio.wait_for(
                self._generate(call_index),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            raise LLMProviderError("LLM request timed out") from exc

    async def _generate(self, call_index: int) -> str:
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error is not None:
            raise LLMProviderError(self.error)
        if self.error_on_call is not None and call_index == self.error_on_call:
            raise LLMProviderError("title generation failed")
        return self.responses.pop(0) if self.responses else "Тестовый ответ"

    def reset(self) -> None:
        self.responses.clear()
        self.calls.clear()
        self.error = None
        self.error_on_call = None
        self.delay_seconds = 0.0


class FakeLLMController:
    def __init__(self, client: AsyncClient) -> None:
        self.client = client

    async def configure(
        self,
        *,
        responses: list[str] | None = None,
        error: str | None = None,
        error_on_call: int | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        response = await self.client.put(
            "/__test__/llm",
            json={
                "responses": responses or [],
                "error": error,
                "error_on_call": error_on_call,
                "delay_seconds": delay_seconds,
            },
        )
        response.raise_for_status()

    async def calls(self) -> list[list[LLMMessage]]:
        response = await self.client.get("/__test__/llm/calls")
        response.raise_for_status()
        return [
            [LLMMessage(role=message["role"], content=message["content"]) for message in call]
            for call in response.json()
        ]


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions
        self.vectors: dict[str, list[float]] = {}
        self.calls: list[str] = []
        self.error: str | None = None
        self.error_on_call: int | None = None

    async def embed(self, content: str) -> list[float]:
        call_index = len(self.calls)
        self.calls.append(content)
        if self.error is not None:
            raise EmbeddingProviderError(self.error)
        if self.error_on_call is not None and call_index == self.error_on_call:
            raise EmbeddingProviderError("embedding failed")
        return self.vector_for(content)

    def vector_for(self, content: str) -> list[float]:
        if content in self.vectors:
            return list(self.vectors[content])
        digest = hashlib.sha256(content.encode()).digest()
        return [(digest[index % len(digest)] / 255.0) for index in range(self.dimensions)]

    def reset(self) -> None:
        self.vectors.clear()
        self.calls.clear()
        self.error = None
        self.error_on_call = None


class FakeMemoryVectorIndex(MemoryVectorIndex):
    def __init__(self) -> None:
        self.points: dict[UUID, dict[str, object]] = {}
        self.search_calls: list[dict[str, object]] = []
        self.error: str | None = None

    async def ensure_collection(self) -> None:
        self._raise()

    async def recreate(self) -> None:
        self._raise()
        self.points.clear()

    async def upsert(
        self,
        *,
        memory_id: UUID,
        vector: list[float],
        user_id: UUID,
        companion_id: UUID,
        memory_type: str,
        is_active: bool,
    ) -> None:
        self._raise()
        self.points[memory_id] = {
            "vector": list(vector),
            "memory_id": str(memory_id),
            "user_id": str(user_id),
            "companion_id": str(companion_id),
            "memory_type": memory_type,
            "is_active": is_active,
        }

    async def update_payload(
        self,
        *,
        memory_id: UUID,
        user_id: UUID,
        companion_id: UUID,
        memory_type: str,
        is_active: bool,
    ) -> bool:
        self._raise()
        point = self.points.get(memory_id)
        if point is None:
            return False
        point.update(
            {
                "memory_id": str(memory_id),
                "user_id": str(user_id),
                "companion_id": str(companion_id),
                "memory_type": memory_type,
                "is_active": is_active,
            }
        )
        return True

    async def delete_for_companion(self, user_id: UUID, companion_id: UUID) -> None:
        self._raise()
        stale = [
            memory_id
            for memory_id, point in self.points.items()
            if point["user_id"] == str(user_id) and point["companion_id"] == str(companion_id)
        ]
        for memory_id in stale:
            del self.points[memory_id]

    async def search(
        self,
        *,
        query: list[float],
        user_id: UUID,
        companion_id: UUID,
        top_k: int,
        score_threshold: float,
    ) -> list[MemoryVectorMatch]:
        self._raise()
        self.search_calls.append(
            {
                "query": list(query),
                "user_id": user_id,
                "companion_id": companion_id,
                "top_k": top_k,
                "score_threshold": score_threshold,
            }
        )
        scored: list[MemoryVectorMatch] = []
        for memory_id, point in self.points.items():
            if point["user_id"] != str(user_id):
                continue
            if point["companion_id"] != str(companion_id):
                continue
            if point["is_active"] is not True:
                continue
            vector = point["vector"]
            assert isinstance(vector, list)
            score = _cosine_similarity(query, vector)
            if score < score_threshold:
                continue
            scored.append(
                MemoryVectorMatch(
                    memory_id=memory_id,
                    score=score,
                    user_id=user_id,
                    companion_id=companion_id,
                    is_active=True,
                    memory_type=str(point["memory_type"]),
                )
            )
        scored.sort(key=lambda match: match.score, reverse=True)
        return scored[:top_k]

    def _raise(self) -> None:
        if self.error is not None:
            raise VectorIndexError(self.error)


class ControllableMemoryVectorIndex(MemoryVectorIndex):
    """Delegates to an inner index and can inject VectorIndexError for tests."""

    def __init__(self, inner: MemoryVectorIndex) -> None:
        self.inner = inner
        self.error: str | None = None

    def _raise(self) -> None:
        if self.error is not None:
            raise VectorIndexError(self.error)

    async def ensure_collection(self) -> None:
        self._raise()
        await self.inner.ensure_collection()

    async def recreate(self) -> None:
        self._raise()
        await self.inner.recreate()

    async def upsert(
        self,
        *,
        memory_id: UUID,
        vector: list[float],
        user_id: UUID,
        companion_id: UUID,
        memory_type: str,
        is_active: bool,
    ) -> None:
        self._raise()
        await self.inner.upsert(
            memory_id=memory_id,
            vector=vector,
            user_id=user_id,
            companion_id=companion_id,
            memory_type=memory_type,
            is_active=is_active,
        )

    async def update_payload(
        self,
        *,
        memory_id: UUID,
        user_id: UUID,
        companion_id: UUID,
        memory_type: str,
        is_active: bool,
    ) -> bool:
        self._raise()
        return await self.inner.update_payload(
            memory_id=memory_id,
            user_id=user_id,
            companion_id=companion_id,
            memory_type=memory_type,
            is_active=is_active,
        )

    async def delete_for_companion(self, user_id: UUID, companion_id: UUID) -> None:
        self._raise()
        await self.inner.delete_for_companion(user_id, companion_id)

    async def search(
        self,
        *,
        query: list[float],
        user_id: UUID,
        companion_id: UUID,
        top_k: int,
        score_threshold: float,
    ) -> list[MemoryVectorMatch]:
        self._raise()
        return await self.inner.search(
            query=query,
            user_id=user_id,
            companion_id=companion_id,
            top_k=top_k,
            score_threshold=score_threshold,
        )

    async def aclose(self) -> None:
        await self.inner.aclose()


class FakeEmbeddingController:
    def __init__(self, client: AsyncClient) -> None:
        self.client = client

    async def configure(
        self,
        *,
        vectors: dict[str, list[float]] | None = None,
        error: str | None = None,
        error_on_call: int | None = None,
    ) -> None:
        response = await self.client.put(
            "/__test__/embeddings",
            json={
                "vectors": vectors or {},
                "error": error,
                "error_on_call": error_on_call,
            },
        )
        response.raise_for_status()

    async def calls(self) -> list[str]:
        response = await self.client.get("/__test__/embeddings/calls")
        response.raise_for_status()
        return response.json()


class FakeVectorIndexController:
    def __init__(self, client: AsyncClient) -> None:
        self.client = client

    async def configure(self, *, error: str | None = None) -> None:
        response = await self.client.put(
            "/__test__/vector_index",
            json={"error": error},
        )
        response.raise_for_status()


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        return -1.0
    dot = sum(first * second for first, second in zip(left, right, strict=True))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
