"""Initial private digest ledger.

Revision ID: 20260729_0001
Revises:
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("collected_count", sa.Integer(), nullable=False),
        sa.Column("digest_count", sa.Integer(), nullable=False),
        sa.Column("degraded_sources", sa.Integer(), nullable=False),
        sa.Column("error_category", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "digests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("edition_date", sa.Date(), nullable=False),
        sa.Column("recipient_hmac", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=150), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("provider_message_id", sa.String(length=100), nullable=True),
        sa.Column("error_category", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("edition_date", "recipient_hmac", name="uq_digest_recipient_date"),
    )
    op.create_table(
        "digest_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("digest_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("story_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["digest_id"], ["digests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("digest_id", "position", name="uq_digest_position"),
    )
    op.create_index(
        op.f("ix_digest_items_story_fingerprint"),
        "digest_items",
        ["story_fingerprint"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_digest_items_story_fingerprint"), table_name="digest_items")
    op.drop_table("digest_items")
    op.drop_table("digests")
    op.drop_table("runs")
