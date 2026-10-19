from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, and_, or_, select, update

from app.db.uow import UnitOfWork
from app.models.companion import Companion
from app.models.memory import DeactivationReason, Memory, normalize_memory_content
from app.schemas.memory import MemoryCreate


class MemoryRepository:
    def __init__(self, uow: UnitOfWork, user_id: UUID) -> None:
        self.uow = uow
        self.user_id = user_id

    async def create(
        self,
        companion_id: UUID,
        payload: MemoryCreate,
        *,
        source_conversation_id: UUID | None = None,
    ) -> Memory:
        memory = Memory(
            user_id=self.user_id,
            companion_id=companion_id,
            type=payload.type,
            content=payload.content,
            importance=payload.importance,
            confidence=payload.confidence,
            source_conversation_id=source_conversation_id,
            index_sync_pending=True,
        )
        self.uow.session.add(memory)
        await self.uow.session.flush()
        return memory

    async def get(self, memory_id: UUID, companion_id: UUID) -> Memory | None:
        result = await self.uow.session.scalars(
            self._owned().where(
                Memory.id == memory_id,
                Memory.companion_id == companion_id,
            )
        )
        return result.first()

    async def list_for_companion(
        self,
        companion_id: UUID,
        *,
        include_inactive: bool = False,
    ) -> list[Memory]:
        query = self._owned().where(Memory.companion_id == companion_id)
        if not include_inactive:
            query = query.where(Memory.is_active.is_(True))
        result = await self.uow.session.scalars(
            query.order_by(Memory.created_at.desc(), Memory.id.desc())
        )
        return list(result)

    async def get_active_by_ids(
        self,
        companion_id: UUID,
        memory_ids: Sequence[UUID],
    ) -> list[Memory]:
        if not memory_ids:
            return []
        result = await self.uow.session.scalars(
            self._owned().where(
                Memory.companion_id == companion_id,
                Memory.is_active.is_(True),
                Memory.id.in_(memory_ids),
            )
        )
        return list(result)

    async def find_active_by_normalized_content(
        self,
        companion_id: UUID,
        content: str,
    ) -> Memory | None:
        key = normalize_memory_content(content)
        if not key:
            return None
        for memory in await self.list_for_companion(companion_id):
            if normalize_memory_content(memory.content) == key:
                return memory
        return None

    async def list_pending_for_companion(self, companion_id: UUID) -> list[Memory]:
        result = await self.uow.session.scalars(
            self._owned()
            .where(
                Memory.companion_id == companion_id,
                Memory.index_sync_pending.is_(True),
            )
            .order_by(Memory.created_at.asc(), Memory.id.asc())
        )
        return list(result)

    def mark_deactivated(
        self,
        memory: Memory,
        *,
        reason: DeactivationReason,
        at: datetime,
        superseded_by: Memory | None = None,
    ) -> None:
        memory.is_active = False
        memory.deactivated_at = at
        memory.deactivation_reason = reason
        memory.superseded_by_id = superseded_by.id if superseded_by is not None else None
        memory.index_sync_pending = True

    def mark_index_sync_pending(self, memory: Memory) -> None:
        memory.index_sync_pending = True

    def _owned(self) -> Select[tuple[Memory]]:
        return (
            select(Memory)
            .join(Companion, Memory.companion_id == Companion.id)
            .where(
                Memory.user_id == self.user_id,
                Companion.user_id == self.user_id,
            )
        )


async def list_active_memories_unscoped(
    uow: UnitOfWork,
    *,
    limit: int,
    after_created_at: datetime | None = None,
    after_id: UUID | None = None,
) -> list[Memory]:
    """Return active memories across all tenants for reindex batches only."""
    return await list_memories_unscoped(
        uow,
        limit=limit,
        after_created_at=after_created_at,
        after_id=after_id,
        is_active=True,
    )


async def list_pending_memories_unscoped(
    uow: UnitOfWork,
    *,
    limit: int,
    after_created_at: datetime | None = None,
    after_id: UUID | None = None,
) -> list[Memory]:
    """Return memories with pending index projection for retry batches."""
    return await list_memories_unscoped(
        uow,
        limit=limit,
        after_created_at=after_created_at,
        after_id=after_id,
        index_sync_pending=True,
    )


async def list_memories_unscoped(
    uow: UnitOfWork,
    *,
    limit: int,
    after_created_at: datetime | None = None,
    after_id: UUID | None = None,
    is_active: bool | None = None,
    index_sync_pending: bool | None = None,
) -> list[Memory]:
    """Return memories across all tenants for index maintenance batches only."""
    query = select(Memory)
    if is_active is not None:
        query = query.where(Memory.is_active.is_(is_active))
    if index_sync_pending is not None:
        query = query.where(Memory.index_sync_pending.is_(index_sync_pending))
    if after_created_at is not None and after_id is not None:
        query = query.where(
            or_(
                Memory.created_at > after_created_at,
                and_(Memory.created_at == after_created_at, Memory.id > after_id),
            )
        )
    result = await uow.session.scalars(
        query.order_by(Memory.created_at.asc(), Memory.id.asc()).limit(limit)
    )
    return list(result)


async def clear_inactive_pending_flags(uow: UnitOfWork) -> None:
    """Mark inactive rows synchronized after a full index rebuild."""
    await uow.session.execute(
        update(Memory)
        .where(Memory.is_active.is_(False), Memory.index_sync_pending.is_(True))
        .values(index_sync_pending=False)
    )
