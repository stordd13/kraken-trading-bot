"""market_data_ohlc.timestamp column comment: period end, not open time

Revision ID: b4c0ffee0001
Revises: f7a8b9c0d1e2
Create Date: 2026-09-13

Metadata-only DDL (``COMMENT ON COLUMN``): instant, no data lock. Documents the
convention that has always been used by the WebSocket collectors and the Bybit
import, and that the Binance rows follow since the B4.1 re-stamp
(``results/B4_1_timestamp_restamp_report.md``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c0ffee0001"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW = "Candle period-end timestamp (UTC): open_time + interval"
_OLD = "Candle open timestamp (UTC)"


def upgrade() -> None:
    op.execute(sa.text(f"COMMENT ON COLUMN market_data_ohlc.\"timestamp\" IS '{_NEW}'"))


def downgrade() -> None:
    op.execute(sa.text(f"COMMENT ON COLUMN market_data_ohlc.\"timestamp\" IS '{_OLD}'"))
