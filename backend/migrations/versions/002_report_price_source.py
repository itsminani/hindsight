"""report price source: remember where a report's prices came from (demo or tiingo).

A backward-compatible, expand-only change: a new nullable column, so code that does not know
about it keeps working, and existing reports simply have no source (they never finished).

Revision ID: 002
Revises: 001
Create Date: 2026-11-14 20:07:47.742761

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add reports.price_source, limited to the known sources."""
    op.add_column("reports", sa.Column("price_source", sa.Text(), nullable=True))
    # Alembic's autogenerate does not see CHECK constraints, so this one is written by hand.
    op.create_check_constraint(
        op.f("ck_reports_price_source"), "reports", "price_source IN ('demo', 'tiingo')"
    )


def downgrade() -> None:
    """Remove the column (and its constraint with it)."""
    op.drop_constraint(op.f("ck_reports_price_source"), "reports", type_="check")
    op.drop_column("reports", "price_source")
