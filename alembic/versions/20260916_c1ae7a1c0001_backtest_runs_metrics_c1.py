"""backtest_runs: undefined ratios stored as NULL + C1 metrics columns

Revision ID: c1ae7a1c0001
Revises: b4c0ffee0001
Create Date: 2026-09-16

Chantier C1 (metrics, post-audit B4): ``sharpe_ratio`` / ``sortino_ratio`` / ``profit_factor``
become nullable — an undefined ratio (std 0, no loss, 0/0) is stored as NULL, never as a fake 0
— and four nullable columns document the new contract: ``metrics_version``,
``gross_profit_net``, ``gross_loss_net`` (the sums behind the net-of-both-legs profit factor)
and ``pf_excluded_trades``. ``max_drawdown_pct`` now receives the daily-NAV figure relative to
the running peak (comment only). Metadata-only DDL on a small table (no rewrite, no data lock).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1ae7a1c0001"
down_revision: str | None = "b4c0ffee0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RATIO = sa.DECIMAL(precision=10, scale=4)
_MONEY = sa.DECIMAL(precision=18, scale=8)


def upgrade() -> None:
    for column, comment in (
        ("sharpe_ratio", "Sharpe ratio (daily returns); NULL when undefined"),
        ("sortino_ratio", "Sortino ratio (downside volatility); NULL when undefined"),
        ("profit_factor", "Profit factor net of both legs; NULL when losses == 0 (see the sums)"),
    ):
        op.alter_column(
            "backtest_runs", column, existing_type=_RATIO, nullable=True, comment=comment
        )
    op.alter_column(
        "backtest_runs",
        "max_drawdown_pct",
        existing_type=_RATIO,
        existing_nullable=False,
        comment="Maximum drawdown percentage (C1: daily NAV, relative to the running peak)",
    )
    op.add_column(
        "backtest_runs",
        sa.Column(
            "gross_profit_net",
            _MONEY,
            nullable=True,
            comment="C1: sum of the net gains (buy fee imputed) behind profit_factor",
        ),
    )
    op.add_column(
        "backtest_runs",
        sa.Column(
            "gross_loss_net",
            _MONEY,
            nullable=True,
            comment="C1: sum of the net losses (absolute value) behind profit_factor",
        ),
    )
    op.add_column(
        "backtest_runs",
        sa.Column(
            "pf_excluded_trades",
            sa.Integer(),
            nullable=True,
            comment="C1: closed lots with an unknown cost basis, excluded from profit_factor",
        ),
    )
    op.add_column(
        "backtest_runs",
        sa.Column(
            "metrics_version",
            sa.Integer(),
            nullable=True,
            comment="C1: contract version of the ratios (krakenbot.backtest_metrics); NULL = pre-C1",
        ),
    )


def downgrade() -> None:
    for column in ("metrics_version", "pf_excluded_trades", "gross_loss_net", "gross_profit_net"):
        op.drop_column("backtest_runs", column)
    for column, comment in (
        ("sharpe_ratio", "Sharpe ratio"),
        ("sortino_ratio", "Sortino ratio (downside volatility)"),
        ("profit_factor", "Profit factor (total_wins / total_losses)"),
    ):
        # pre-C1 rows never held NULL; C1 rows lose the distinction (NULL -> 0) on downgrade
        op.execute(sa.text(f"UPDATE backtest_runs SET {column} = 0 WHERE {column} IS NULL"))
        op.alter_column(
            "backtest_runs", column, existing_type=_RATIO, nullable=False, comment=comment
        )
    op.alter_column(
        "backtest_runs",
        "max_drawdown_pct",
        existing_type=_RATIO,
        existing_nullable=False,
        comment="Maximum drawdown percentage",
    )
