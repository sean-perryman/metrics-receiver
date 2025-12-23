"""initial

Revision ID: 0001_initial
Revises: 
Create Date: 2025-12-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.Enum("admin", "viewer", name="user_role"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "endpoints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("machine_id", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_interval_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_endpoints_hostname", "endpoints", ["hostname"], unique=False)
    op.create_index("ix_endpoints_machine_id", "endpoints", ["machine_id"], unique=True)

    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("endpoint_id", sa.Integer(), sa.ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("cpu_utilization_pct", sa.Float(), nullable=True),
        sa.Column("cpu_idle_pct", sa.Float(), nullable=True),
        sa.Column("mem_total_bytes", sa.Integer(), nullable=True),
        sa.Column("mem_used_bytes", sa.Integer(), nullable=True),
        sa.Column("mem_free_bytes", sa.Integer(), nullable=True),
        sa.Column("mem_used_pct", sa.Float(), nullable=True),
        sa.Column("users_count", sa.Integer(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_snapshots_endpoint_id", "snapshots", ["endpoint_id"], unique=False)
    op.create_index("ix_snapshots_timestamp_utc", "snapshots", ["timestamp_utc"], unique=False)

    op.create_table(
        "disk_physical",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instance", sa.String(length=255), nullable=False),
        sa.Column("reads_per_sec", sa.Float(), nullable=False),
        sa.Column("writes_per_sec", sa.Float(), nullable=False),
        sa.Column("avg_queue_length", sa.Float(), nullable=False),
        sa.Column("read_latency_ms", sa.Float(), nullable=False),
        sa.Column("write_latency_ms", sa.Float(), nullable=False),
        sa.Column("utilization_pct", sa.Float(), nullable=False),
    )
    op.create_index("ix_disk_physical_snapshot_id", "disk_physical", ["snapshot_id"], unique=False)
    op.create_index("ix_disk_physical_instance", "disk_physical", ["instance"], unique=False)

    op.create_table(
        "disk_volumes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mount", sa.String(length=64), nullable=False),
        sa.Column("filesystem", sa.String(length=32), nullable=True),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("free_bytes", sa.Integer(), nullable=False),
        sa.Column("free_pct", sa.Float(), nullable=False),
    )
    op.create_index("ix_disk_volumes_snapshot_id", "disk_volumes", ["snapshot_id"], unique=False)
    op.create_index("ix_disk_volumes_mount", "disk_volumes", ["mount"], unique=False)

    op.create_table(
        "network_interfaces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("bytes_total_per_sec", sa.Float(), nullable=False),
        sa.Column("bits_total_per_sec", sa.Float(), nullable=False),
        sa.Column("utilization_pct", sa.Float(), nullable=True),
        sa.Column("packets_in_errors", sa.Integer(), nullable=False),
        sa.Column("packets_out_errors", sa.Integer(), nullable=False),
    )
    op.create_index("ix_network_interfaces_snapshot_id", "network_interfaces", ["snapshot_id"], unique=False)
    op.create_index("ix_network_interfaces_name", "network_interfaces", ["name"], unique=False)

    op.create_table(
        "logged_in_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("session_type", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_logged_in_users_snapshot_id", "logged_in_users", ["snapshot_id"], unique=False)
    op.create_index("ix_logged_in_users_username", "logged_in_users", ["username"], unique=False)

    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_type", sa.Enum("heartbeat", "low_disk", name="alert_type"), nullable=False),
        sa.Column("endpoint_id", sa.Integer(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "alert_dedup",
        sa.Column("key", sa.String(length=255), primary_key=True),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_table("alert_dedup")
    op.drop_table("alert_events")
    op.drop_table("logged_in_users")
    op.drop_table("network_interfaces")
    op.drop_table("disk_volumes")
    op.drop_table("disk_physical")
    op.drop_table("snapshots")
    op.drop_table("settings")
    op.drop_index("ix_endpoints_machine_id", table_name="endpoints")
    op.drop_index("ix_endpoints_hostname", table_name="endpoints")
    op.drop_table("endpoints")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS user_role")
    op.execute("DROP TYPE IF EXISTS alert_type")
