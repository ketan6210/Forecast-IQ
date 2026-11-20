"""Persist shared-resource allocation decisions without changing individual plans."""

import sqlalchemy as sa
from alembic import op

revision = "0003_allocation"
down_revision = "0002_inventory"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_allocations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
    )
    op.create_index("ix_inventory_allocations_dataset_id", "inventory_allocations", ["dataset_id"])


def downgrade():
    op.drop_table("inventory_allocations")
