"""scans.exported_at: when a scan was exported to Excel (denominator of the correction rate)

Revision ID: 0003_scan_exported_at
Revises: 0002_jobs
Create Date: 2026-10-15 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_scan_exported_at"
down_revision = "0002_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("scans") as batch:
        batch.add_column(sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("scans") as batch:
        batch.drop_column("exported_at")
