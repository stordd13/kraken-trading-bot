"""Rejeu diagnostic grid § B — the direct, out-of-simulation measurement of the spacing clamp.

``scripts/audit/rejeu_spacing_clamp.py`` is driven here on **synthetic** series, never on the
database: ``measure_pair`` is a pure function of a list of ``(timestamp, high, low, close)``
Decimal rows, so the binding bounds the pre-specification published in advance can be checked
exactly instead of being re-derived from data.

A constant-close candle with ``high = close + a`` and ``low = close − a`` has
``TR = max(2a, a, a) = 2a`` on every bar (and ``high − low = 2a`` on the first), so Wilder's
average is exactly ``2a`` from the 14th bar on: the series below pin ``ATR`` to the decimal, and
with it ``raw = ATR × m / close``. The tests cover the three regimes (strictly inside the band,
the ceiling saturated for every multiplier, the floor for every couple), the four published
ceiling thresholds ``ATR/close >= 0.05/m`` = 3,3333 / 2,50 / 2,00 / 1,6667 % with their inclusive
equality, the end-stamped window and quarter conventions, and the defects that would quietly
falsify the artefact: a close at zero, rows out of order, an ATR that is not ready yet, an empty
quarter turned into a 0/0 share, a NaN reaching the JSON, and a DB failure that must still exit 0
with ``producible: false`` — the clamp moves no verdict, in any direction.

The one DB-touching test is skipped behind a socket probe (tunnel on 5433, then local 5432).
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import socket
import sys

import pytest

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts"))
sys.path.insert(0, str(_project_root / "scripts" / "audit"))

import p7_grids
import rejeu_common as rc
import rejeu_spacing_clamp as clamp

# ---------------------------------------------------------------------------
# Synthetic series
# ---------------------------------------------------------------------------

SHORT_LEAD_IN = datetime(2023, 3, 1, tzinfo=UTC)  # 31 days = 186 candles, ATR ready long before
SHORT_END = datetime(2023, 4, 3, tzinfo=UTC)  # two days in window -> 12 closes


def _rows(
    atr: Decimal,
    *,
    close: Decimal = Decimal("2000"),
    lead_in: datetime = SHORT_LEAD_IN,
    end: datetime = SHORT_END,
    skip: tuple[datetime, datetime] | None = None,
) -> list[tuple[datetime, Decimal, Decimal, Decimal]]:
    """4 h candles whose Wilder ATR is exactly ``atr`` and whose close is constant."""
    half = atr / Decimal("2")
    step = timedelta(minutes=clamp.INTERVAL_MINUTES)
    out = []
    stamp = lead_in + step
    while stamp <= end:
        if skip is None or not (skip[0] < stamp <= skip[1]):
            out.append((stamp, close + half, close - half, close))
        stamp += step
    return out


def _cells(block: dict) -> dict[tuple[float, float], str]:
    """The class each couple gives when the whole window falls in one class."""
    cells = {}
    for couple in block["couples"]:
        classes = [name for name in clamp.CLASSES if couple[name] == 1.0]
        assert len(classes) == 1, f"couple {couple} is not uniform: {couple}"
        cells[(couple["min_spacing_pct"], couple["atr_multiplier"])] = classes[0]
    return cells


# ---------------------------------------------------------------------------
# The swept couples
# ---------------------------------------------------------------------------


def test_couples_are_the_frozen_grid_never_literals() -> None:
    expected = [
        (Decimal(str(f)), Decimal(str(m)))
        for f in p7_grids.GRID_ATR_GRID["min_spacing_pct"]
        for m in p7_grids.GRID_ATR_GRID["atr_multiplier"]
    ]
    assert list(clamp.COUPLES) == expected
    assert len(clamp.COUPLES) == 16
    assert clamp.LEAD_IN_START == datetime(2023, 2, 1, tzinfo=UTC)
    assert clamp.LEVEL_QUANTIZATION_STEP == Decimal("0.1")
    assert clamp.QUANTIZATION_MIN_SHARE == Decimal("0.1")
    # Two different things: the price step in USD, and the share of the spacing it is
    # compared to. They happen to share a value; they are not the same symbol.
    assert clamp.LEVEL_QUANTIZATION_STEP is not clamp.QUANTIZATION_MIN_SHARE


# ---------------------------------------------------------------------------
# The three regimes
# ---------------------------------------------------------------------------


def test_constant_volatility_lands_on_the_published_cells() -> None:
    """ATR/close = 1.25 % -> raw = 1.875 / 2.5 / 3.125 / 3.75 %.

    No single volatility can be interior for the sixteen couples at once (interior everywhere
    would need ``ATR/close > 0.03/1.5 = 2 %`` and ``< 0.05/3 = 1.667 %``), so the whole 16-cell
    map is asserted against the published binding rules, floor equality included: at m = 2.0 the
    raw spacing is exactly the 2.5 % floor, which the inclusive ``<=`` must call ``at_floor``.
    """
    block = clamp.measure_pair(_rows(Decimal("25")), window_end=SHORT_END)
    assert block["n_closes"] == 12
    assert _cells(block) == {
        (0.015, 1.5): "interior",
        (0.015, 2.0): "interior",
        (0.015, 2.5): "interior",
        (0.015, 3.0): "interior",
        (0.020, 1.5): "at_floor",
        (0.020, 2.0): "interior",
        (0.020, 2.5): "interior",
        (0.020, 3.0): "interior",
        (0.025, 1.5): "at_floor",
        (0.025, 2.0): "at_floor",  # raw == floor exactly
        (0.025, 2.5): "interior",
        (0.025, 3.0): "interior",
        (0.030, 1.5): "at_floor",
        (0.030, 2.0): "at_floor",
        (0.030, 2.5): "interior",
        (0.030, 3.0): "interior",
    }
    for couple in block["couples"]:
        total = couple["at_floor"] + couple["interior"] + couple["at_ceiling"]
        assert total == pytest.approx(1.0)


def test_ceiling_saturates_for_every_multiplier() -> None:
    """ATR/close = 5 % -> raw 7.5 … 15 %, above the 5 % ceiling for all sixteen couples."""
    block = clamp.measure_pair(_rows(Decimal("100")), window_end=SHORT_END)
    assert set(_cells(block).values()) == {"at_ceiling"}
    assert all(couple["at_ceiling"] == 1.0 for couple in block["couples"])


def test_floor_holds_for_every_couple() -> None:
    """ATR/close = 0.2 % -> raw 0.3 … 0.6 %, at or below every swept floor."""
    block = clamp.measure_pair(_rows(Decimal("4")), window_end=SHORT_END)
    assert set(_cells(block).values()) == {"at_floor"}


@pytest.mark.parametrize(
    ("multiplier", "atr"),
    [
        (Decimal("1.5"), Decimal("50")),
        (Decimal("2.0"), Decimal("37.5")),
        (Decimal("2.5"), Decimal("30")),
        (Decimal("3.0"), Decimal("25")),
    ],
)
def test_published_ceiling_threshold_binds_inclusively(multiplier: Decimal, atr: Decimal) -> None:
    """The ceiling binds iff ``ATR/close >= 0.05/m`` (3,3333 / 2,50 / 2,00 / 1,6667 %).

    ``close = 1500`` makes the threshold ATR exact in Decimal; one cent below it the spacing is
    interior for every floor (raw stays above 3 %), which is what "strictly" costs.
    """
    close = Decimal("1500")
    assert atr * multiplier / close == rc.MAX_SPACING_PCT
    couples = [(floor, multiplier) for floor in p7_grids.GRID_ATR_GRID["min_spacing_pct"]]
    couples = [(Decimal(str(f)), m) for f, m in couples]

    at_threshold = clamp.measure_pair(
        _rows(atr, close=close), window_end=SHORT_END, couples=couples
    )
    assert set(_cells(at_threshold).values()) == {"at_ceiling"}

    below = clamp.measure_pair(
        _rows(atr - Decimal("0.01"), close=close), window_end=SHORT_END, couples=couples
    )
    assert set(_cells(below).values()) == {"interior"}


def test_classify_is_a_strict_decimal_comparison() -> None:
    floor, ceiling = Decimal("0.02"), rc.MAX_SPACING_PCT
    assert clamp.classify(ceiling, floor, ceiling) == "at_ceiling"
    assert clamp.classify(ceiling - Decimal("1e-28"), floor, ceiling) == "interior"
    assert clamp.classify(floor, floor, ceiling) == "at_floor"
    assert clamp.classify(floor + Decimal("1e-28"), floor, ceiling) == "interior"


# ---------------------------------------------------------------------------
# Window, lead-in and quarters (end-stamped)
# ---------------------------------------------------------------------------


def test_quarter_label_reads_the_period_not_the_stamp() -> None:
    # A candle stamped at a quarter boundary covers the four hours BEFORE it.
    assert clamp.quarter_label(datetime(2026, 4, 1, tzinfo=UTC)) == "2026Q1"
    assert clamp.quarter_label(datetime(2023, 7, 1, tzinfo=UTC)) == "2023Q2"
    assert clamp.quarter_label(datetime(2023, 4, 1, 4, tzinfo=UTC)) == "2023Q2"
    assert clamp.quarter_label(datetime(2023, 7, 1, 4, tzinfo=UTC)) == "2023Q3"


def test_lead_in_is_excluded_and_bounds_are_open_left_closed_right() -> None:
    rows = _rows(Decimal("25"))
    block = clamp.measure_pair(rows, window_end=SHORT_END)
    # 186 lead-in candles + 12 in-window candles, only the latter counted.
    assert len(rows) == 198
    assert block["n_closes"] == 12
    # The candle stamped exactly at the window start covers the last 4 h of March: excluded.
    stamps = [stamp for stamp, *_ in rows if rc.WINDOW_START < stamp <= SHORT_END]
    assert stamps[0] == datetime(2023, 4, 1, 4, tzinfo=UTC)
    assert stamps[-1] == SHORT_END
    assert len(stamps) == 12


def test_full_window_is_6576_closes_over_the_twelve_quarters() -> None:
    block = clamp.measure_pair(_rows(Decimal("25"), lead_in=clamp.LEAD_IN_START, end=rc.WINDOW_END))
    assert block["n_closes"] == rc.WINDOW_DAYS * 6 == 6576
    quarters = block["couples"][0]["by_quarter"]
    assert list(quarters) == [
        "2023Q2",
        "2023Q3",
        "2023Q4",
        "2024Q1",
        "2024Q2",
        "2024Q3",
        "2024Q4",
        "2025Q1",
        "2025Q2",
        "2025Q3",
        "2025Q4",
        "2026Q1",
    ]
    assert sum(entry["n"] for entry in quarters.values()) == block["n_closes"]


def test_a_quarter_without_a_close_is_absent_not_a_zero_denominator() -> None:
    """A data hole must not publish a 0/0 share — the quarter is simply missing."""
    hole = (datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 4, 1, tzinfo=UTC))
    block = clamp.measure_pair(
        _rows(Decimal("25"), lead_in=clamp.LEAD_IN_START, end=rc.WINDOW_END, skip=hole)
    )
    quarters = block["couples"][0]["by_quarter"]
    assert "2024Q1" not in quarters
    assert len(quarters) == 11
    assert block["n_closes"] == 6576 - 91 * 6
    assert all(entry["n"] > 0 for entry in quarters.values())


# ---------------------------------------------------------------------------
# Defects the measurement must not paper over
# ---------------------------------------------------------------------------


def test_closes_without_a_ready_atr_are_skipped() -> None:
    """With a lead-in of 3 candles the first 13 bars have no ATR: 10 in-window closes drop."""
    lead_in = rc.WINDOW_START - timedelta(minutes=3 * clamp.INTERVAL_MINUTES)
    block = clamp.measure_pair(_rows(Decimal("25"), lead_in=lead_in), window_end=SHORT_END)
    assert block["n_closes"] == 12 - 10


def test_rows_must_be_strictly_ascending() -> None:
    rows = _rows(Decimal("25"))
    rows[100], rows[101] = rows[101], rows[100]
    with pytest.raises(ValueError, match="strictly ascending"):
        clamp.measure_pair(rows, window_end=SHORT_END)
    duplicated = _rows(Decimal("25"))
    duplicated.insert(100, duplicated[100])
    with pytest.raises(ValueError, match="strictly ascending"):
        clamp.measure_pair(duplicated, window_end=SHORT_END)


def test_a_non_positive_close_takes_the_strategy_floor_branch() -> None:
    """``_calculate_spacing`` returns ``min_spacing_pct`` when ``price <= 0``: no division."""
    rows = _rows(Decimal("25"))
    stamp, high, low, _ = rows[-1]
    rows[-1] = (stamp, high, low, Decimal("0"))
    block = clamp.measure_pair(rows, window_end=SHORT_END)
    assert block["n_closes"] == 12
    for couple in block["couples"]:
        assert couple["at_floor"] >= 1 / 12 - 1e-12


# ---------------------------------------------------------------------------
# The SOL-relevant side measure
# ---------------------------------------------------------------------------


def test_quantization_share_counts_the_inclusive_boundary() -> None:
    """``0.1 USD >= 10 % × spacing × close`` <=> ``spacing × close <= 1 USD``.

    At a 50 USD close pinned on the floor, the absolute spacing is 0.75 / 1.00 / 1.25 / 1.50 USD
    for the four floors: the first two hit (the second exactly on the boundary), the last two do
    not — 8 of the 16 cells.
    """
    block = clamp.measure_pair(_rows(Decimal("0.1"), close=Decimal("50")), window_end=SHORT_END)
    assert set(_cells(block).values()) == {"at_floor"}
    assert block["quantization_share"] == pytest.approx(0.5)


def test_quantization_share_is_zero_on_a_btc_scale_close() -> None:
    block = clamp.measure_pair(_rows(Decimal("750"), close=Decimal("60000")), window_end=SHORT_END)
    assert block["quantization_share"] == 0.0


# ---------------------------------------------------------------------------
# Artefact
# ---------------------------------------------------------------------------

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def _series_both() -> dict[str, list]:
    return {
        "BTC/USDC": _rows(Decimal("750"), close=Decimal("60000")),
        "SOL/USDC": _rows(Decimal("0.1"), close=Decimal("50")),
    }


def test_payload_carries_the_frozen_schema_and_the_mandatory_label() -> None:
    payload = clamp.build_payload(_series_both(), now=NOW)
    assert set(payload) == {
        "generated_at",
        "base_sha",
        "prespec",
        "producible",
        "reason",
        "label",
        "atr_period",
        "max_spacing_pct",
        "lead_in_start",
        "pairs",
    }
    assert payload["label"] == (
        "mesure distributionnelle, pas un rejeu ; aucune paire ne reproduit l'état ATR "
        "réalisé du moteur"
    )
    assert payload["producible"] is True
    assert payload["reason"] is None
    assert payload["generated_at"] == "2026-09-20T12:00:00+00:00"
    assert payload["base_sha"] == rc.BASE_SHA
    assert payload["atr_period"] == 14
    assert payload["max_spacing_pct"] == 0.05
    assert payload["lead_in_start"] == "2023-02-01T00:00:00+00:00"
    assert set(payload["prespec"]) == {"path", "sha256"}
    assert payload["prespec"]["path"] == "docs/rejeu_grid_prespec.md"
    assert len(payload["prespec"]["sha256"]) == 64
    assert set(payload["pairs"]) == set(rc.PAIRS)
    for block in payload["pairs"].values():
        assert set(block) == {"n_closes", "couples", "quantization_share"}
        assert len(block["couples"]) == 16
        for couple in block["couples"]:
            assert set(couple) == {
                "min_spacing_pct",
                "atr_multiplier",
                "at_floor",
                "interior",
                "at_ceiling",
                "by_quarter",
            }
            for entry in couple["by_quarter"].values():
                assert set(entry) == {"n", "at_floor", "interior", "at_ceiling"}


def test_payload_is_deterministic_and_free_of_nan() -> None:
    first = clamp.build_payload(_series_both(), now=NOW)
    second = clamp.build_payload(_series_both(), now=NOW)
    # ``dumps_canonical`` has allow_nan=False: a NaN share would raise here, not slip through.
    assert rc.dumps_canonical(first) == rc.dumps_canonical(second)
    assert rc.sig(first) == rc.sig(second)


def test_payload_is_not_producible_when_a_pair_is_missing() -> None:
    series = _series_both()
    del series["SOL/USDC"]
    payload = clamp.build_payload(series, now=NOW)
    assert payload["producible"] is False
    assert "SOL/USDC" in payload["reason"]
    assert set(payload["pairs"]) == {"BTC/USDC"}


def test_payload_is_not_producible_when_no_close_falls_in_the_window() -> None:
    series = {pair: _rows(Decimal("25"), end=rc.WINDOW_START) for pair in rc.PAIRS}
    payload = clamp.build_payload(series, now=NOW)
    assert payload["producible"] is False
    assert payload["reason"].count("aucune clôture 4h") == 2
    for block in payload["pairs"].values():
        assert block["n_closes"] == 0
        assert block["quantization_share"] == 0.0


def test_loader_failure_is_a_reason_not_an_exception() -> None:
    payload = clamp.build_payload({}, now=NOW, reason="série 4h non chargeable (OSError: down)")
    assert payload["producible"] is False
    assert payload["reason"].startswith("série 4h non chargeable")
    assert payload["pairs"] == {}


def test_markdown_opens_on_the_label_and_prints_the_published_bounds() -> None:
    text = clamp.render_markdown(clamp.build_payload(_series_both(), now=NOW))
    assert clamp.LABEL in text.splitlines()[2]
    assert "3.3333 %" in text and "1.6667 %" in text  # 0.05 / 1.5 and 0.05 / 3.0
    assert "at_ceiling par trimestre" in text
    assert "BTC/USDC" in text and "SOL/USDC" in text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch):
    """``main()`` without the DB and without loading the developer's .env."""
    monkeypatch.setattr(clamp, "load_dotenv", lambda *a, **k: False)

    def _install(series, reason=None):
        monkeypatch.setattr(clamp, "collect_series", lambda *a, **k: (series, reason))

    return _install


def test_main_writes_the_artifact_and_exits_zero(offline, tmp_path: Path, capsys) -> None:
    offline(_series_both())
    out = tmp_path / "clamp.json"
    md = tmp_path / "sub" / "clamp.md"
    code = clamp.main(["--output", str(out), "--markdown", str(md), "--now", NOW.isoformat()])
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["producible"] is True
    assert payload["generated_at"] == "2026-09-20T12:00:00+00:00"
    assert md.exists()
    assert clamp.LABEL in capsys.readouterr().out


def test_main_exits_zero_when_the_series_cannot_be_loaded(offline, tmp_path: Path, capsys) -> None:
    """The clamp never moves a verdict: an unreachable DB is a reason, not a failure."""
    offline({}, "série 4h non chargeable (OSError: connection refused)")
    out = tmp_path / "clamp.json"
    assert clamp.main(["--output", str(out), "--now", NOW.isoformat()]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["producible"] is False
    assert "connection refused" in payload["reason"]
    assert payload["pairs"] == {}
    assert "non productible" in capsys.readouterr().err


def test_main_rejects_a_malformed_now(offline, tmp_path: Path) -> None:
    offline(_series_both())
    assert clamp.main(["--output", str(tmp_path / "c.json"), "--now", "not-a-date"]) == 2


# ---------------------------------------------------------------------------
# DB (skipped behind a socket probe)
# ---------------------------------------------------------------------------


def _db_reachable() -> bool:
    for port in (5433, 5432):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            continue
    return False


@pytest.fixture
def restored_environ():
    """``load_dotenv`` is the documented root cause of this suite's order-dependent failures:
    the one test that needs the real .env puts ``os.environ`` back exactly as it found it."""
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


@pytest.mark.skipif(not _db_reachable(), reason="Database not reachable (tunnel down)")
def test_btc_series_from_the_db_covers_the_frozen_window(restored_environ) -> None:
    clamp.load_dotenv(clamp._ROOT / ".env")
    series, reason = clamp.collect_series(("BTC/USDC",))
    assert reason is None, reason
    rows = series["BTC/USDC"]
    assert rows and all(a[0] < b[0] for a, b in zip(rows, rows[1:], strict=False))
    block = clamp.measure_pair(rows)
    assert block["n_closes"] == rc.WINDOW_DAYS * 6
    for couple in block["couples"]:
        total = couple["at_floor"] + couple["interior"] + couple["at_ceiling"]
        assert total == pytest.approx(1.0)
