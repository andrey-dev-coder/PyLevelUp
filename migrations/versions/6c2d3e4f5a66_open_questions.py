from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6c2d3e4f5a66"
down_revision: str | None = "5b1c2d3e4f55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "open_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("topic", sa.String(length=64), nullable=False, index=True),
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("ideal_answer", sa.Text(), nullable=False),
        sa.Column("checklist", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
    op.create_index("ix_open_questions_topic", "open_questions", ["topic"])


def downgrade() -> None:
    op.drop_index("ix_open_questions_topic", table_name="open_questions")
    op.drop_table("open_questions")
