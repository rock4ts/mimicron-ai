from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.memory import Memory


class Companion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companions"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    personality: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)

    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="companion",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    memories: Mapped[list[Memory]] = relationship(
        back_populates="companion",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
