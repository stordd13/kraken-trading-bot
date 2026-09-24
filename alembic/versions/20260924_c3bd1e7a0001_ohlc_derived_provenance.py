"""ohlc_derived: provenance of the market_data_ohlc rows that are derived, not observed

Revision ID: c3bd1e7a0001
Revises: c1ae7a1c0001
Create Date: 2026-09-24

Reconstruction of the 8 missing 1 w stamps of the Binance USDT series (``agent/agent_reconstruction_1w.md``,
protocol C3 v2.1 § A.8): the rebuilt rows go into ``market_data_ohlc`` with ``exchange='binance'``, and each one
gets a row here — a row in ``ohlc_derived`` ⟺ the OHLC row with the same key is not exchange data. New table
only: no ALTER on ``market_data_ohlc``, no hypertable, no foreign key constraint (the target is a hypertable).
Light DDL on an empty table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3bd1e7a0001"
down_revision: str | None = "c1ae7a1c0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_COMMENT = (
    "Rows de market_data_ohlc non observées, dérivées par agrégation. Une row ici ⟺ la row "
    "OHLC correspondante n'est pas une donnée d'exchange."
)


def upgrade() -> None:
    op.create_table(
        "ohlc_derived",
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            comment="Period-end timestamp of the derived market_data_ohlc row (UTC)",
        ),
        sa.Column("pair", sa.String(20), nullable=False, comment="Trading pair of the derived row"),
        sa.Column(
            "interval",
            sa.Integer(),
            nullable=False,
            comment="Interval of the derived row (minutes)",
        ),
        sa.Column("exchange", sa.String(20), nullable=False, comment="Exchange of the derived row"),
        sa.Column(
            "method", sa.String(32), nullable=False, comment="Derivation method (e.g. agg_1d_v1)"
        ),
        sa.Column(
            "source_interval",
            sa.Integer(),
            nullable=False,
            comment="Interval of the source rows (minutes)",
        ),
        sa.Column(
            "source_stamps",
            postgresql.JSONB(),
            nullable=False,
            comment="Period-end stamps of the source rows (ISO)",
        ),
        sa.Column(
            "source_sha256",
            sa.String(64),
            nullable=False,
            comment="sha256 of the serialised source rows (replayable proof)",
        ),
        sa.Column(
            "vwap_policy",
            sa.String(16),
            nullable=False,
            comment="How vwap was derived: null or weighted",
        ),
        sa.Column(
            "script_sha256",
            sa.String(64),
            nullable=False,
            comment="sha256 of the script that wrote the row",
        ),
        sa.Column(
            "git_sha", sa.String(40), nullable=False, comment="Commit the script was run from"
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="When the row was written (UTC)",
        ),
        sa.Column("note", sa.Text(), nullable=False, comment="Reference to the research log entry"),
        sa.PrimaryKeyConstraint(
            "timestamp", "pair", "interval", "exchange", name="ohlc_derived_pkey"
        ),
        comment=_TABLE_COMMENT,
    )


def downgrade() -> None:
    op.drop_table("ohlc_derived")
