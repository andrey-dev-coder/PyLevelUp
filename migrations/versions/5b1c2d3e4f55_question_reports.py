from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b1c2d3e4f55"
down_revision: str | None = "4f9a1b2c3d44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "question_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.Integer(),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="open",
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
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_question_reports_user_id", "question_reports", ["user_id"])
    op.create_index("ix_question_reports_question_id", "question_reports", ["question_id"])
    op.create_index("ix_question_reports_status", "question_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_question_reports_status", table_name="question_reports")
    op.drop_index("ix_question_reports_question_id", table_name="question_reports")
    op.drop_index("ix_question_reports_user_id", table_name="question_reports")
    op.drop_table("question_reports")
