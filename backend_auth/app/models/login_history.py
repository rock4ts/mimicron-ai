from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class LoginHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "login_history"
    __table_args__ = (
        Index("ix_login_history_user_id_logged_in_at", "user_id", "logged_in_at"),
        Index("ix_login_history_logged_in_at", "logged_in_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    ip_address: Mapped[str] = mapped_column(nullable=False)
    user_agent: Mapped[str | None] = mapped_column(nullable=True)
    device_id: Mapped[str | None] = mapped_column(nullable=True)
    logged_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<LoginHistory user_id={self.user_id}, "
            f"timestamp={self.logged_in_at}, "
            f"ip_address={self.ip_address}>"
        )
