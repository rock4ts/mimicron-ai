import logging
import time
from dataclasses import dataclass
from uuid import UUID

from app.embeddings.base import EmbeddingProvider
from app.models.memory import Memory
from app.repositories.memory_repository import MemoryRepository
from app.vector_index.base import MemoryVectorIndex, MemoryVectorMatch

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetrievedMemory:
    """Canonical memory paired with its Qdrant similarity score."""

    memory: Memory
    score: float


class MemoryRetrievalService:
    """Finds relevant active memories for the current user message."""

    def __init__(
        self,
        embeddings: EmbeddingProvider,
        vector_index: MemoryVectorIndex,
        memories: MemoryRepository,
        *,
        top_k: int,
        score_threshold: float,
    ) -> None:
        self.embeddings = embeddings
        self.vector_index = vector_index
        self.memories = memories
        self.top_k = top_k
        self.score_threshold = score_threshold

    async def retrieve(self, companion_id: UUID, query: str) -> list[RetrievedMemory]:
        started_embed = time.perf_counter()
        vector = await self.embeddings.embed(query)
        embedding_duration_ms = _duration_ms(started_embed)

        started_search = time.perf_counter()
        matches = await self.vector_index.search(
            query=vector,
            user_id=self.memories.user_id,
            companion_id=companion_id,
            top_k=self.top_k,
            score_threshold=self.score_threshold,
        )
        qdrant_duration_ms = _duration_ms(started_search)

        postgres_duration_ms = 0.0
        results: list[RetrievedMemory] = []
        if matches:
            ordered_matches = _unique_matches(matches)
            started_resolve = time.perf_counter()
            stored = await self.memories.get_active_by_ids(
                companion_id,
                [match.memory_id for match in ordered_matches],
            )
            postgres_duration_ms = _duration_ms(started_resolve)
            by_id = {memory.id: memory for memory in stored}
            results = [
                RetrievedMemory(memory=by_id[match.memory_id], score=match.score)
                for match in ordered_matches
                if match.memory_id in by_id
            ]

        logger.info(
            "memory_retrieval_completed",
            extra={
                "user_id": str(self.memories.user_id),
                "companion_id": str(companion_id),
                "top_k": self.top_k,
                "embedding_duration_ms": embedding_duration_ms,
                "qdrant_duration_ms": qdrant_duration_ms,
                "postgres_duration_ms": postgres_duration_ms,
                "candidate_count": len(matches),
                "included_count": len(results),
            },
        )
        return results


def _unique_matches(matches: list[MemoryVectorMatch]) -> list[MemoryVectorMatch]:
    unique: list[MemoryVectorMatch] = []
    seen: set[UUID] = set()
    for match in matches:
        if match.memory_id in seen:
            continue
        seen.add(match.memory_id)
        unique.append(match)
    return unique


def _duration_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)
