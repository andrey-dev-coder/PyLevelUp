from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5bb"
down_revision: str | None = "b0c1d2e3f4aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column("code", sa.Text(), nullable=True),
    )
    op.add_column(
        "questions",
        sa.Column("code_language", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "open_questions",
        sa.Column("code", sa.Text(), nullable=True),
    )
    op.add_column(
        "open_questions",
        sa.Column("code_language", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("open_questions", "code_language")
    op.drop_column("open_questions", "code")
    op.drop_column("questions", "code_language")
    op.drop_column("questions", "code")
