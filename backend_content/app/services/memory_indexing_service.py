from typing import Literal


import logging
from uuid import UUID

from app.db.uow import UnitOfWork
from app.embeddings.base import EmbeddingProvider
from app.errors import EmbeddingProviderError, VectorIndexError
from app.models.memory import Memory
from app.repositories.memory_repository import (
    clear_inactive_pending_flags,
    list_active_memories_unscoped,
    list_pending_memories_unscoped,
)
from app.vector_index.base import MemoryVectorIndex

logger = logging.getLogger(__name__)


class MemoryIndexingService:
    """Projects a committed Memory into the vector index."""

    def __init__(
        self,
        embeddings: EmbeddingProvider,
        vector_index: MemoryVectorIndex,
    ) -> None:
        self.embeddings = embeddings
        self.vector_index = vector_index

    async def index(self, memory: Memory) -> None:
        """Embed memory content and upsert a stable point for `memory.id`."""
        vector = await self.embeddings.embed(memory.content)
        await self.vector_index.upsert(
            memory_id=memory.id,
            vector=vector,
            user_id=memory.user_id,
            companion_id=memory.companion_id,
            memory_type=memory.type.value,
            is_active=memory.is_active,
        )

    async def sync_payload(self, memory: Memory) -> None:
        """Refresh payload, or re-embed and upsert if the point is missing."""
        updated = await self.vector_index.update_payload(
            memory_id=memory.id,
            user_id=memory.user_id,
            companion_id=memory.companion_id,
            memory_type=memory.type.value,
            is_active=memory.is_active,
        )
        if not updated:
            await self.index(memory)

    async def mark_inactive(self, memory: Memory) -> None:
        """Set `is_active=false` on the index point if it exists."""
        await self.vector_index.update_payload(
            memory_id=memory.id,
            user_id=memory.user_id,
            companion_id=memory.companion_id,
            memory_type=memory.type.value,
            is_active=False,
        )

    async def project(self, memory: Memory) -> None:
        """Project the current PostgreSQL state; missing inactive points are consistent."""
        if memory.is_active:
            await self.index(memory)
            return
        await self.mark_inactive(memory)

    async def delete_for_companion(self, user_id: UUID, companion_id: UUID) -> None:
        """Remove index points for a deleted companion."""
        await self.vector_index.delete_for_companion(user_id, companion_id)


async def project_and_clear_pending(
    indexing: MemoryIndexingService | None,
    memory: Memory,
    uow: UnitOfWork,
) -> bool:
    """Best-effort projection after a PostgreSQL commit; failures leave pending set."""
    if indexing is None:
        return False
    action: Literal["upsert", "deactivate"] = "upsert" if memory.is_active else "deactivate"
    try:
        await indexing.project(memory)
    except (EmbeddingProviderError, VectorIndexError) as exc:
        logger.warning(
            "memory_index_sync_failed",
            extra={
                "memory_id": str(memory.id),
                "companion_id": str(memory.companion_id),
                "user_id": str(memory.user_id),
                "action": action,
                "index_sync_pending": True,
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )
        return False
    memory.index_sync_pending = False
    await uow.commit()
    logger.info(
        "memory_index_sync_succeeded",
        extra={
            "memory_id": str(memory.id),
            "companion_id": str(memory.companion_id),
            "user_id": str(memory.user_id),
            "action": action,
            "index_sync_pending": False,
        },
    )
    return True


async def reindex_active_memories(
    uow: UnitOfWork,
    indexing: MemoryIndexingService,
    vector_index: MemoryVectorIndex,
    *,
    batch_size: int = 100,
) -> tuple[int, int]:
    """Rebuild the index from active PostgreSQL memories.

    Recreates the collection, then upserts points in batches. Successfully
    indexed active rows and absent inactive rows clear `index_sync_pending`.
    Returns `(indexed, failed)` counts; individual failures do not stop the run.
    """
    await vector_index.recreate()
    indexed = 0
    failed = 0
    after_created_at = None
    after_id = None
    while True:
        batch = await list_active_memories_unscoped(
            uow,
            limit=batch_size,
            after_created_at=after_created_at,
            after_id=after_id,
        )
        if not batch:
            break
        for memory in batch:
            try:
                await indexing.index(memory)
                memory.index_sync_pending = False
                indexed += 1
            except (EmbeddingProviderError, VectorIndexError):
                memory.index_sync_pending = True
                failed += 1
                logger.warning(
                    "memory_reindex_failed",
                    extra={
                        "memory_id": str(memory.id),
                        "companion_id": str(memory.companion_id),
                        "user_id": str(memory.user_id),
                        "error_type": "reindex",
                        "index_sync_pending": True,
                    },
                    exc_info=True,
                )
        await uow.commit()
        after_created_at = batch[-1].created_at
        after_id = batch[-1].id
    await clear_inactive_pending_flags(uow)
    await uow.commit()
    return indexed, failed


async def sync_pending_memories(
    uow: UnitOfWork,
    indexing: MemoryIndexingService,
    *,
    batch_size: int = 100,
) -> tuple[int, int]:
    """Project pending PostgreSQL memories into the derived index.

    Walks pending rows once; failures stay pending for a later retry.
    Returns `(synced, failed)` counts.
    """
    synced = 0
    failed = 0
    after_created_at = None
    after_id = None
    while True:
        batch = await list_pending_memories_unscoped(
            uow,
            limit=batch_size,
            after_created_at=after_created_at,
            after_id=after_id,
        )
        if not batch:
            break
        for memory in batch:
            try:
                await indexing.project(memory)
            except (EmbeddingProviderError, VectorIndexError):
                failed += 1
                logger.warning(
                    "memory_index_sync_failed",
                    extra={
                        "memory_id": str(memory.id),
                        "companion_id": str(memory.companion_id),
                        "user_id": str(memory.user_id),
                        "action": "retry",
                        "index_sync_pending": True,
                        "error_type": "retry",
                    },
                    exc_info=True,
                )
                continue
            memory.index_sync_pending = False
            synced += 1
        await uow.commit()
        after_created_at = batch[-1].created_at
        after_id = batch[-1].id
    logger.info(
        "memory_index_sync_retry_completed",
        extra={"synced_count": synced, "failed_count": failed, "attempt_count": synced + failed},
    )
    return synced, failed
