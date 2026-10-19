"""add memories

Revision ID: d7f3c2a18b90
Revises: e9a1c4d8b270
Create Date: 2026-09-07 15:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7f3c2a18b90"
down_revision: str | Sequence[str] | None = "e9a1c4d8b270"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

memory_type = postgresql.ENUM(
    "fact",
    "preference",
    "goal",
    "event",
    "relationship",
    name="memory_type",
)


def upgrade() -> None:
    memory_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "memories",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("companion_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(
                "fact",
                "preference",
                "goal",
                "event",
                "relationship",
                name="memory_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "importance >= 0 AND importance <= 1",
            name=op.f("ck_memories_importance_range"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_memories_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["companion_id"],
            ["companions.id"],
            name=op.f("fk_memories_companion_id_companions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memories")),
    )
    op.create_index(op.f("ix_memories_user_id"), "memories", ["user_id"], unique=False)
    op.create_index(
        "ix_memories_user_id_companion_id_is_active",
        "memories",
        ["user_id", "companion_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_memories_companion_id_is_active",
        "memories",
        ["companion_id", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_memories_companion_id_is_active", table_name="memories")
    op.drop_index("ix_memories_user_id_companion_id_is_active", table_name="memories")
    op.drop_index(op.f("ix_memories_user_id"), table_name="memories")
    op.drop_table("memories")
    memory_type.drop(op.get_bind(), checkfirst=True)
