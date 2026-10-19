"""add memory lifecycle provenance and index sync state

Revision ID: f1b9e6c4a280
Revises: d7f3c2a18b90
Create Date: 2026-09-21 17:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1b9e6c4a280"
down_revision: str | Sequence[str] | None = "d7f3c2a18b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

deactivation_reason = postgresql.ENUM(
    "updated",
    "contradicted",
    "manual",
    name="memory_deactivation_reason",
)


def upgrade() -> None:
    deactivation_reason.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "memories",
        sa.Column("source_conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "memories",
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "memories",
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "memories",
        sa.Column(
            "deactivation_reason",
            postgresql.ENUM(
                "updated",
                "contradicted",
                "manual",
                name="memory_deactivation_reason",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "memories",
        sa.Column(
            "index_sync_pending",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE memories
        SET deactivated_at = COALESCE(updated_at, created_at, now()),
            deactivation_reason = 'manual'
        WHERE is_active = false
          AND deactivated_at IS NULL
          AND deactivation_reason IS NULL
        """
    )
    op.create_foreign_key(
        op.f("fk_memories_source_conversation_id_conversations"),
        "memories",
        "conversations",
        ["source_conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_memories_superseded_by_id_memories"),
        "memories",
        "memories",
        ["superseded_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_memories_source_conversation_id"),
        "memories",
        ["source_conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memories_superseded_by_id"),
        "memories",
        ["superseded_by_id"],
        unique=False,
    )
    op.create_index(
        "ix_memories_user_id_companion_id_index_sync_pending",
        "memories",
        ["user_id", "companion_id", "index_sync_pending"],
        unique=False,
        postgresql_where=sa.text("index_sync_pending"),
    )
    op.create_check_constraint(
        op.f("ck_memories_active_has_no_deactivation"),
        "memories",
        "(is_active = true AND deactivated_at IS NULL"
        " AND deactivation_reason IS NULL AND superseded_by_id IS NULL)"
        " OR is_active = false",
    )
    op.create_check_constraint(
        op.f("ck_memories_superseded_is_inactive"),
        "memories",
        "superseded_by_id IS NULL OR is_active = false",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_memories_superseded_is_inactive"), "memories", type_="check")
    op.drop_constraint(op.f("ck_memories_active_has_no_deactivation"), "memories", type_="check")
    op.drop_index(
        "ix_memories_user_id_companion_id_index_sync_pending",
        table_name="memories",
    )
    op.drop_index(op.f("ix_memories_superseded_by_id"), table_name="memories")
    op.drop_index(op.f("ix_memories_source_conversation_id"), table_name="memories")
    op.drop_constraint(
        op.f("fk_memories_superseded_by_id_memories"),
        "memories",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_memories_source_conversation_id_conversations"),
        "memories",
        type_="foreignkey",
    )
    op.drop_column("memories", "index_sync_pending")
    op.drop_column("memories", "deactivation_reason")
    op.drop_column("memories", "deactivated_at")
    op.drop_column("memories", "superseded_by_id")
    op.drop_column("memories", "source_conversation_id")
    deactivation_reason.drop(op.get_bind(), checkfirst=True)
