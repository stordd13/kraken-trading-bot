"""add exchange column to market_data_ohlc

Revision ID: f7a8b9c0d1e2
Revises: da05b87b4016
Create Date: 2026-04-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "da05b87b4016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add the column with a server default so existing rows get 'kraken'
    op.add_column(
        "market_data_ohlc",
        sa.Column(
            "exchange",
            sa.String(20),
            nullable=False,
            server_default="kraken",
        ),
    )

    # 2. Drop the old primary key (timestamp, pair, interval)
    op.execute("ALTER TABLE market_data_ohlc DROP CONSTRAINT IF EXISTS market_data_ohlc_pkey")

    # 3. Create the new primary key including exchange
    #    TimescaleDB requires the time column in the PK — timestamp is still there.
    op.create_primary_key(
        "market_data_ohlc_pkey",
        "market_data_ohlc",
        ["timestamp", "pair", "interval", "exchange"],
    )


def downgrade() -> None:
    # 1. Drop the new PK
    op.execute("ALTER TABLE market_data_ohlc DROP CONSTRAINT IF EXISTS market_data_ohlc_pkey")

    # 2. Delete non-kraken rows to avoid PK conflicts on the narrower key
    op.execute("DELETE FROM market_data_ohlc WHERE exchange != 'kraken'")

    # 3. Restore the old PK
    op.create_primary_key(
        "market_data_ohlc_pkey",
        "market_data_ohlc",
        ["timestamp", "pair", "interval"],
    )

    # 4. Drop the column
    op.drop_column("market_data_ohlc", "exchange")
