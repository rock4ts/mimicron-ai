"""add companion user_id

Revision ID: c4e8a91b2d70
Revises: be5f945a9fa0
Create Date: 2026-09-01 17:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8a91b2d70"
down_revision: str | Sequence[str] | None = "be5f945a9fa0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(op.f("ix_companions_user_id"), "companions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_companions_user_id"), table_name="companions")
    op.drop_column("companions", "user_id")
