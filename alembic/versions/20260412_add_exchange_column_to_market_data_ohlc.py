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
    # Disable timeouts — PK rebuild on a 1.13M-row TimescaleDB hypertable is slow.
    # This migration MUST run on the server directly (not through SSH tunnel).
    op.execute(sa.text("SET statement_timeout = '0'"))
    op.execute(sa.text("SET lock_timeout = '0'"))

    # Step 1: Add column (idempotent, fast — metadata-only in PG 11+)
    op.execute(
        sa.text(
            "ALTER TABLE market_data_ohlc "
            "ADD COLUMN IF NOT EXISTS exchange VARCHAR(20) NOT NULL DEFAULT 'kraken'"
        )
    )

    # Step 2: Drop old PK (idempotent via IF EXISTS)
    op.execute(
        sa.text("ALTER TABLE market_data_ohlc DROP CONSTRAINT IF EXISTS market_data_ohlc_pkey")
    )

    # Step 3: Create new PK including exchange (~1-2 min on 1.13M rows).
    # TimescaleDB requires the time column in the PK and propagates to all chunks.
    op.execute(
        sa.text(
            "ALTER TABLE market_data_ohlc "
            "ADD CONSTRAINT market_data_ohlc_pkey "
            'PRIMARY KEY ("timestamp", pair, "interval", exchange)'
        )
    )


def downgrade() -> None:
    op.execute(sa.text("SET statement_timeout = '0'"))
    op.execute(sa.text("SET lock_timeout = '0'"))

    # Step 1: Drop the new PK
    op.execute(
        sa.text("ALTER TABLE market_data_ohlc DROP CONSTRAINT IF EXISTS market_data_ohlc_pkey")
    )

    # Step 2: Delete non-kraken rows to avoid PK conflicts on the narrower key
    op.execute(sa.text("DELETE FROM market_data_ohlc WHERE exchange != 'kraken'"))

    # Step 3: Restore the old PK
    op.execute(
        sa.text(
            "ALTER TABLE market_data_ohlc "
            "ADD CONSTRAINT market_data_ohlc_pkey "
            'PRIMARY KEY ("timestamp", pair, "interval")'
        )
    )

    # Step 4: Drop the column
    op.drop_column("market_data_ohlc", "exchange")
