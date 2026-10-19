import logging
from uuid import UUID

from app.errors import CompanionNotFoundError, VectorIndexError
from app.models.companion import Companion
from app.repositories.companion_repository import CompanionRepository
from app.schemas.companion import CompanionCreate, CompanionUpdate
from app.services.memory_indexing_service import MemoryIndexingService

logger = logging.getLogger(__name__)


class CompanionService:
    def __init__(
        self,
        repository: CompanionRepository,
        indexing: MemoryIndexingService | None = None,
    ) -> None:
        self.repository = repository
        self.indexing = indexing

    async def create(self, payload: CompanionCreate) -> Companion:
        companion = await self.repository.create(payload.name, payload.personality)
        await self.repository.uow.commit()
        await self.repository.uow.refresh(companion)
        return companion

    async def list(self) -> list[Companion]:
        return await self.repository.list()

    async def get(self, companion_id: UUID) -> Companion:
        companion = await self.repository.get(companion_id)
        if companion is None:
            raise CompanionNotFoundError
        return companion

    async def update(self, companion_id: UUID, payload: CompanionUpdate) -> Companion:
        companion = await self.get(companion_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(companion, field, value)
        await self.repository.uow.commit()
        await self.repository.uow.refresh(companion)
        return companion

    async def delete(self, companion_id: UUID) -> None:
        companion = await self.get(companion_id)
        user_id = companion.user_id
        await self.repository.delete(companion)
        await self.repository.uow.commit()
        if self.indexing is None or user_id is None:
            return
        try:
            await self.indexing.delete_for_companion(user_id, companion_id)
        except VectorIndexError as exc:
            logger.warning(
                "companion_index_cleanup_failed",
                extra={
                    "companion_id": str(companion_id),
                    "user_id": str(user_id),
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
