"""Add inventory plans and simulation/policy runs; preserve forecasting data."""

import sqlalchemy as sa
from alembic import op

revision = "0002_inventory"
down_revision = "0001_forecasting"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column(
            "forecast_run_id", sa.String(36), sa.ForeignKey("advanced_runs.id"), nullable=False
        ),
        sa.Column("sku_id", sa.String(255), nullable=False),
        sa.Column("store_id", sa.String(255), nullable=False),
        sa.Column("location_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
    )
    for column in ("dataset_id", "forecast_run_id", "sku_id"):
        op.create_index(f"ix_inventory_plans_{column}", "inventory_plans", [column])
    op.create_table(
        "inventory_simulations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("inventory_plans.id"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
    )
    op.create_index("ix_inventory_simulations_plan_id", "inventory_simulations", ["plan_id"])


def downgrade():
    op.drop_table("inventory_simulations")
    op.drop_table("inventory_plans")
