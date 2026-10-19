from sqlalchemy import select

from app.db.uow import UnitOfWork
from app.models.oauth_account import OAuthAccount
from app.models.user import User


class OAuthAccountRepository:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def get_user_by_provider_account(
        self, provider: str, provider_user_id: str
    ) -> User | None:
        result = await self.uow.session.execute(
            select(User)
            .join(OAuthAccount, OAuthAccount.user_id == User.id)
            .where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_user_id == provider_user_id,
            )
        )
        return result.scalars().first()

    async def add(self, account: OAuthAccount) -> OAuthAccount:
        self.uow.session.add(account)
        await self.uow.session.flush()
        return account
