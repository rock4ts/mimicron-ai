"""add conversation title

Revision ID: e9a1c4d8b270
Revises: c4e8a91b2d70
Create Date: 2026-09-07 15:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9a1c4d8b270"
down_revision: str | Sequence[str] | None = "c4e8a91b2d70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("title", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "title")
