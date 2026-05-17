from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b0c1d2e3f4aa"
down_revision: str | None = "af1b2c3d4e55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_paths",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("slug", name="uq_learning_paths_slug"),
    )

    op.create_table(
        "learning_path_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "path_id",
            sa.Integer(),
            sa.ForeignKey("learning_paths.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("topic_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=True),
        sa.Column("required_accuracy", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("required_questions", sa.Integer(), nullable=False, server_default="10"),
        sa.UniqueConstraint("path_id", "position", name="uq_path_step_position"),
    )

    op.create_table(
        "user_learning_path_progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "path_id",
            sa.Integer(),
            sa.ForeignKey("learning_paths.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("current_position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "path_id", name="uq_user_path"),
    )
    op.create_index(
        "ix_user_learning_path_progress_user_id",
        "user_learning_path_progress",
        ["user_id"],
    )
    op.create_index(
        "ix_user_learning_path_progress_path_id",
        "user_learning_path_progress",
        ["path_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_learning_path_progress_path_id", table_name="user_learning_path_progress"
    )
    op.drop_index(
        "ix_user_learning_path_progress_user_id", table_name="user_learning_path_progress"
    )
    op.drop_table("user_learning_path_progress")
    op.drop_table("learning_path_steps")
    op.drop_table("learning_paths")
