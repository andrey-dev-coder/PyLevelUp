from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e4f5a6b7c88"
down_revision: str | None = "7d3e4f5a6b77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "custom_categories",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("short", sa.String(length=64), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("custom_categories")
