from uuid import UUID

from sqlalchemy import select

from app.db.uow import UnitOfWork
from app.models.user import User


class UserRepository:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.uow.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.uow.session.execute(select(User).where(User.email == email))
        return result.scalars().first()

    async def add(self, user: User) -> User:
        self.uow.session.add(user)
        await self.uow.session.flush()
        return user
