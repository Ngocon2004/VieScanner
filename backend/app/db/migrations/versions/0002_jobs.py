"""jobs + job_items for async processing; scans.job_id; cache lookup index

Revision ID: 0002_jobs
Revises: 0001_initial
Create Date: 2026-10-10 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_jobs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "source",
            sa.Enum("upload", "import_pdf", "camera", name="job_source_enum", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "queued", "processing", "completed", "partial", "failed", "cancelled",
                name="job_status_enum", native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("processed_items", sa.Integer(), nullable=False),
        sa.Column("succeeded_items", sa.Integer(), nullable=False),
        sa.Column("failed_items", sa.Integer(), nullable=False),
        sa.Column("ocr_engine", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_jobs_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_user_id"), "jobs", ["user_id"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_index(op.f("ix_jobs_created_at"), "jobs", ["created_at"], unique=False)

    op.create_table(
        "job_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("upload_index", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("container_filename", sa.String(length=255), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "queued", "processing", "done", "rejected", "failed", "cancelled",
                name="job_item_status_enum", native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("scan_id", sa.String(length=36), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name=op.f("fk_job_items_job_id_jobs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], name=op.f("fk_job_items_scan_id_scans"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_items")),
        sa.UniqueConstraint("job_id", "seq", name=op.f("uq_job_items_job_id")),
    )
    op.create_index(op.f("ix_job_items_job_id"), "job_items", ["job_id"], unique=False)
    op.create_index(op.f("ix_job_items_status"), "job_items", ["status"], unique=False)

    # SQLite không ALTER thêm FK trực tiếp -> batch mode (tạo lại bảng).
    with op.batch_alter_table("scans") as batch:
        batch.add_column(sa.Column("job_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            op.f("fk_scans_job_id_jobs"), "jobs", ["job_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index(op.f("ix_scans_job_id"), ["job_id"], unique=False)
        batch.create_index(
            "ix_scans_cache_lookup", ["image_hash", "user_id", "status", "created_at"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("scans") as batch:
        batch.drop_index("ix_scans_cache_lookup")
        batch.drop_index(op.f("ix_scans_job_id"))
        batch.drop_constraint(op.f("fk_scans_job_id_jobs"), type_="foreignkey")
        batch.drop_column("job_id")

    op.drop_index(op.f("ix_job_items_status"), table_name="job_items")
    op.drop_index(op.f("ix_job_items_job_id"), table_name="job_items")
    op.drop_table("job_items")
    op.drop_index(op.f("ix_jobs_created_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_user_id"), table_name="jobs")
    op.drop_table("jobs")
