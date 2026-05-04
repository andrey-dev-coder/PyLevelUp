from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3a2f1e0c8b91"
down_revision: str | None = "26c828142161"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("total_starts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "total_starts")
