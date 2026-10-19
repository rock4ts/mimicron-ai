import logging
from datetime import UTC, datetime
from uuid import UUID

from app.errors import CompanionNotFoundError, MemoryNotFoundError
from app.models.memory import DeactivationReason, Memory
from app.repositories.companion_repository import CompanionRepository
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.services.memory_indexing_service import MemoryIndexingService, project_and_clear_pending

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(
        self,
        companions: CompanionRepository,
        memories: MemoryRepository,
        indexing: MemoryIndexingService | None = None,
    ) -> None:
        self.companions = companions
        self.memories = memories
        self.indexing = indexing

    async def create(self, companion_id: UUID, payload: MemoryCreate) -> Memory:
        memories = await self.create_many(companion_id, [payload])
        return memories[0]

    async def create_many(
        self,
        companion_id: UUID,
        payloads: list[MemoryCreate],
    ) -> list[Memory]:
        if await self.companions.get(companion_id) is None:
            raise CompanionNotFoundError
        if not payloads:
            return []
        memories = [await self.memories.create(companion_id, payload) for payload in payloads]
        await self.memories.uow.commit()
        for memory in memories:
            await self.memories.uow.refresh(memory)
        for memory in memories:
            await self._project_and_clear(memory)
        return memories

    async def get(self, memory_id: UUID, companion_id: UUID) -> Memory:
        memory = await self.memories.get(memory_id, companion_id)
        if memory is None:
            raise MemoryNotFoundError
        return memory

    async def list_for_companion(
        self,
        companion_id: UUID,
        *,
        include_inactive: bool = False,
    ) -> list[Memory]:
        if await self.companions.get(companion_id) is None:
            raise CompanionNotFoundError
        return await self.memories.list_for_companion(
            companion_id,
            include_inactive=include_inactive,
        )

    async def update(
        self,
        memory_id: UUID,
        companion_id: UUID,
        payload: MemoryUpdate,
    ) -> Memory:
        memory = await self.get(memory_id, companion_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(memory, field, value)
        self.memories.mark_index_sync_pending(memory)
        await self.memories.uow.commit()
        await self.memories.uow.refresh(memory)
        await self._project_and_clear(memory)
        return memory

    async def deactivate(self, memory_id: UUID, companion_id: UUID) -> Memory:
        memory = await self.get(memory_id, companion_id)
        if memory.is_active:
            self.memories.mark_deactivated(
                memory,
                reason=DeactivationReason.MANUAL,
                at=datetime.now(UTC),
            )
            await self.memories.uow.commit()
            await self.memories.uow.refresh(memory)
        await self._project_and_clear(memory)
        return memory

    async def _project_and_clear(self, memory: Memory) -> bool:
        return await project_and_clear_pending(self.indexing, memory, self.memories.uow)
