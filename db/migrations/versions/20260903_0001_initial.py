"""Create UST auction and QRA schema.

Revision ID: 20260903_0001
Revises: None
"""
from pathlib import Path

from alembic import op


revision = "20260903_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    ddl = Path(__file__).resolve().parents[2] / "ust_pipeline_schema.sql"
    if op.get_context().as_sql:
        op.execute(ddl.read_text(encoding="utf-8"))
    else:
        op.get_bind().exec_driver_sql(ddl.read_text(encoding="utf-8"), execution_options={"no_parameters": True})


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS ust CASCADE")
