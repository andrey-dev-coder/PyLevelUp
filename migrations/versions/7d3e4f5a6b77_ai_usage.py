from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d3e4f5a6b77"
down_revision: str | None = "6c2d3e4f5a66"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("usage_date", sa.Date(), nullable=False, index=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_ai_usage_user_date", "ai_usage", ["user_id", "usage_date"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_ai_usage_user_date", table_name="ai_usage")
    op.drop_table("ai_usage")
