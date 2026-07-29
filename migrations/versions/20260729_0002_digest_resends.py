"""Add retry-safe forced resend ledger.

Revision ID: 20260729_0002
Revises: 20260729_0001
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0002"
down_revision: str | None = "20260729_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "digest_resends",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("digest_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provider_message_id", sa.String(length=100), nullable=True),
        sa.Column("error_category", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["digest_id"], ["digests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("digest_id", "sequence", name="uq_digest_resend_sequence"),
    )
    op.create_index(
        op.f("ix_digest_resends_digest_id"),
        "digest_resends",
        ["digest_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_digest_resends_digest_id"), table_name="digest_resends")
    op.drop_table("digest_resends")
