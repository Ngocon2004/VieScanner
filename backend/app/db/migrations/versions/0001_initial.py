"""initial database schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column(
            "role",
            sa.Enum("admin", "user", name="user_role_enum", native_enum=False),
            nullable=False,
            server_default="user",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)

    op.create_table(
        "scans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("request_id", sa.String(length=36), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("image_hash", sa.String(length=64), nullable=True),
        sa.Column("ocr_engine", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.Enum("success", "failed", "partial", name="scan_status_enum", native_enum=False),
            nullable=False,
            server_default="success",
        ),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("confidences", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_scans_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scans")),
    )
    op.create_index(op.f("ix_scans_created_at"), "scans", ["created_at"], unique=False)
    op.create_index(op.f("ix_scans_image_hash"), "scans", ["image_hash"], unique=False)
    op.create_index(op.f("ix_scans_request_id"), "scans", ["request_id"], unique=False)
    op.create_index(op.f("ix_scans_user_id"), "scans", ["user_id"], unique=False)

    op.create_table(
        "cccd_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scan_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("id_number", sa.String(length=12), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("dob", sa.Date(), nullable=False),
        sa.Column("gender", sa.String(length=8), nullable=False),
        sa.Column("nationality", sa.String(length=100), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("residence", sa.Text(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], name=op.f("fk_cccd_records_scan_id_scans"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_cccd_records_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cccd_records")),
    )
    op.create_index(op.f("ix_cccd_records_id_number"), "cccd_records", ["id_number"], unique=False)
    op.create_index(op.f("ix_cccd_records_scan_id"), "cccd_records", ["scan_id"], unique=False)
    op.create_index(op.f("ix_cccd_records_user_id"), "cccd_records", ["user_id"], unique=False)

    op.create_table(
        "corrections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scan_id", sa.String(length=36), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("ocr_value", sa.Text(), nullable=True),
        sa.Column("corrected_value", sa.Text(), nullable=True),
        sa.Column("confidence_at_ocr", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], name=op.f("fk_corrections_scan_id_scans"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_corrections")),
    )
    op.create_index(op.f("ix_corrections_field_name"), "corrections", ["field_name"], unique=False)
    op.create_index(op.f("ix_corrections_scan_id"), "corrections", ["scan_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_corrections_scan_id"), table_name="corrections")
    op.drop_index(op.f("ix_corrections_field_name"), table_name="corrections")
    op.drop_table("corrections")

    op.drop_index(op.f("ix_cccd_records_user_id"), table_name="cccd_records")
    op.drop_index(op.f("ix_cccd_records_scan_id"), table_name="cccd_records")
    op.drop_index(op.f("ix_cccd_records_id_number"), table_name="cccd_records")
    op.drop_table("cccd_records")

    op.drop_index(op.f("ix_scans_user_id"), table_name="scans")
    op.drop_index(op.f("ix_scans_request_id"), table_name="scans")
    op.drop_index(op.f("ix_scans_image_hash"), table_name="scans")
    op.drop_index(op.f("ix_scans_created_at"), table_name="scans")
    op.drop_table("scans")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
