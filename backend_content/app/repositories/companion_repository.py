from uuid import UUID

from sqlalchemy import select

from app.db.uow import UnitOfWork
from app.models.companion import Companion


class CompanionRepository:
    def __init__(self, uow: UnitOfWork, user_id: UUID) -> None:
        self.uow = uow
        self.user_id = user_id

    async def create(self, name: str, personality: str) -> Companion:
        companion = Companion(name=name, personality=personality, user_id=self.user_id)
        self.uow.session.add(companion)
        await self.uow.session.flush()
        return companion

    async def get(self, companion_id: UUID) -> Companion | None:
        result = await self.uow.session.scalars(
            select(Companion).where(
                Companion.id == companion_id,
                Companion.user_id == self.user_id,
            )
        )
        return result.first()

    async def list(self) -> list[Companion]:
        result = await self.uow.session.scalars(
            select(Companion)
            .where(Companion.user_id == self.user_id)
            .order_by(Companion.created_at, Companion.id)
        )
        return list(result)

    async def delete(self, companion: Companion) -> None:
        await self.uow.session.delete(companion)
