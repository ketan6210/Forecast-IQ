"""Create or adopt the frozen Phase 1/2 schema without deleting existing records."""

import sqlalchemy as sa
from alembic import op

revision = "0001_forecasting"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "datasets" not in existing:
        op.create_table(
            "datasets",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("is_demo", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("report", sa.JSON(), nullable=False),
            sa.Column("timings", sa.JSON(), nullable=False),
        )
    if "forecast_runs" not in existing:
        op.create_table(
            "forecast_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id"), nullable=False),
            sa.Column("selected_model", sa.String(40), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            *[
                sa.Column(name, sa.JSON(), nullable=False)
                for name in ("request", "validation_metrics", "test_metrics", "result")
            ],
        )
        op.create_index("ix_forecast_runs_dataset_id", "forecast_runs", ["dataset_id"])
    if "advanced_runs" not in existing:
        op.create_table(
            "advanced_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id"), nullable=False),
            sa.Column("champion_model", sa.String(40), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("configuration", sa.JSON(), nullable=False),
            sa.Column("result", sa.JSON(), nullable=False),
        )
        op.create_index("ix_advanced_runs_dataset_id", "advanced_runs", ["dataset_id"])


def downgrade():
    raise RuntimeError("Baseline adoption is irreversible here; restoring a backup is explicit.")
