from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.oauth_account import OAuthAccount


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(nullable=False)
    token_version: Mapped[int] = mapped_column(nullable=False, default=1)
    first_name: Mapped[str] = mapped_column(nullable=False, default="")
    last_name: Mapped[str] = mapped_column(nullable=False, default="")
    is_superuser: Mapped[bool] = mapped_column(default=False, nullable=False)

    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User {self.email}>"
