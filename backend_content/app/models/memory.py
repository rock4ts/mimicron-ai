from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    Text,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.companion import Companion
    from app.models.conversation import Conversation


class MemoryType(StrEnum):
    FACT = "fact"
    PREFERENCE = "preference"
    GOAL = "goal"
    EVENT = "event"
    RELATIONSHIP = "relationship"


class DeactivationReason(StrEnum):
    UPDATED = "updated"
    CONTRADICTED = "contradicted"
    MANUAL = "manual"


def normalize_memory_content(content: str) -> str:
    """Collapse surrounding and internal whitespace for exact matching."""
    return " ".join(content.split())


class Memory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memories"
    __table_args__ = (
        CheckConstraint("importance >= 0 AND importance <= 1", name="importance_range"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(
            "(is_active = true AND deactivated_at IS NULL"
            " AND deactivation_reason IS NULL AND superseded_by_id IS NULL)"
            " OR is_active = false",
            name="active_has_no_deactivation",
        ),
        CheckConstraint(
            "superseded_by_id IS NULL OR is_active = false",
            name="superseded_is_inactive",
        ),
        Index(
            "ix_memories_user_id_companion_id_is_active",
            "user_id",
            "companion_id",
            "is_active",
        ),
        Index("ix_memories_companion_id_is_active", "companion_id", "is_active"),
        Index(
            "ix_memories_user_id_companion_id_index_sync_pending",
            "user_id",
            "companion_id",
            "index_sync_pending",
            postgresql_where=text("index_sync_pending"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    companion_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companions.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[MemoryType] = mapped_column(
        Enum(
            MemoryType,
            name="memory_type",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    source_conversation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    superseded_by_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("memories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deactivation_reason: Mapped[DeactivationReason | None] = mapped_column(
        Enum(
            DeactivationReason,
            name="memory_deactivation_reason",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=True,
    )
    index_sync_pending: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    companion: Mapped[Companion] = relationship(back_populates="memories")
    source_conversation: Mapped[Conversation | None] = relationship("Conversation")
    superseded_by: Mapped[Memory | None] = relationship(
        "Memory",
        remote_side="Memory.id",
        foreign_keys="Memory.superseded_by_id",
    )
