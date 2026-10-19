from uuid import UUID

from sqlalchemy import select

from app.db.uow import UnitOfWork
from app.models.login_history import LoginHistory
from app.schemas.misc import DeviceInfo, RequestMeta


class LoginHistoryRepository:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def add(
        self,
        user_id: UUID,
        request_meta: RequestMeta,
        device_info: DeviceInfo | None = None,
    ) -> LoginHistory:
        login_history = LoginHistory(
            user_id=user_id,
            ip_address=request_meta.ip_address or "unknown",
            user_agent=request_meta.user_agent[:500] if request_meta.user_agent else None,
            device_id=str(device_info.device_id) if device_info else None,
        )
        self.uow.session.add(login_history)
        await self.uow.session.flush()
        return login_history

    async def list_for_user(self, user_id: UUID, page: int, page_size: int) -> list[LoginHistory]:
        result = await self.uow.session.execute(
            select(LoginHistory)
            .where(LoginHistory.user_id == user_id)
            .order_by(LoginHistory.logged_in_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all())
