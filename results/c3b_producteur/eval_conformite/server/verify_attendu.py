"""C3b lot 4a — vérification de l'attendu (``../ATTENDU.md``) sur les sorties rapatriées du run serveur.

Ne lit que les champs déclarés à l'attendu : codes de ``status.txt``, clés et preuves de l'artefact désigné, bornes,
états des clauses de ``continuity.json``, ``alembic``. Aucune métrique n'est lue ni imprimée ; aucun fichier du chemin
sélection n'est ouvert (ils ne sont pas rapatriés : archive seulement).

Usage (depuis la racine du dépôt) ::

    poetry run python results/c3b_producteur/eval_conformite/server/verify_attendu.py <répertoire rapatrié>
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
for sub in ("src", "scripts", "scripts/audit"):
    sys.path.insert(0, str(ROOT / sub))

import c3_common as cc  # noqa: E402

from krakenbot.backtest_metrics import daily_grid  # noqa: E402

T = datetime(2020, 9, 11, 21, 36, tzinfo=UTC)
FIN = datetime(2020, 12, 28, tzinfo=UTC)
DESIGNATED = "145867637b7f9bac6b556efc9dc48e929f18624f1c56d54eebe83b6c5eb47962"
KEYS = {
    "synthetic",
    "strategy",
    "pair",
    "params",
    "period",
    "equity_daily",
    "liquidation",
    "warmup",
    "invocation",
    "first_fill_at",
    "flat_start_proof",
    "metrics",
}
OBSERVED = {
    "usdc_balance": "1000.0",
    "btc_held": "0",
    "active_buy_orders": 0,
    "active_sell_orders": 0,
    "strategy_built": False,
    "trades": 0,
}
PROOF = {"at": "2020-09-11T21:36:00+00:00", "cash": "1000", "qty": "0", "pending": 0}


def status(path: Path) -> dict[str, str]:
    """``clé=valeur`` de chaque ligne de ``status.txt`` (premier mot de la ligne) et ses attributs."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        for token in line.split():
            if "=" in token:
                key, value = token.split("=", 1)
                out.setdefault(key, value)
                if token == line.split()[0]:
                    out[key] = value
    return out


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    base = Path(sys.argv[1])
    out = base / "out"
    st = status(out / "status.txt")
    results: list[tuple[str, bool, str]] = []

    # 1. désignation
    results.append(
        (
            "1 désignation",
            st["designation"] == "0" and st["identity"] == DESIGNATED,
            f"designation={st['designation']} identity={st['identity'][:16]}…",
        )
    )

    # 2. chemin sélection : codes seulement
    lines = (out / "status.txt").read_text(encoding="utf-8").splitlines()
    sel = {
        line.split("=")[0]: line.split()[0].split("=")[1]
        for line in lines
        if line.startswith("eval_select_run")
    }
    events = [
        line.split("event=")[1].split()[0] for line in lines if line.startswith("eval_select_run")
    ]
    codes = [sel["eval_select_run1"], sel["eval_select_run2"]]
    same = next(line for line in lines if line.startswith("select_sha_equal"))
    ok2 = codes[0] == codes[1] and codes[0] in {"0", "2"}
    if codes[0] == "0":
        ok2 = ok2 and events == ["evaluated", "evaluated"] and same == "select_sha_equal=0"
    elif codes[0] == "2":
        ok2 = ok2 and events == ["nothing_to_evaluate"] * 2 and "nothing_written" in same
    results.append(("2 chemin sélection", ok2, f"codes {codes}, événements {events}, {same}"))

    # 3. chemin désigné, exécution
    runs = [out / "designated" / f"run{i}" for i in (1, 2)]
    run = load(runs[0] / "evaluation_run.json")
    prov = load(runs[0] / "evaluation_run_provenance.json")
    same_bits = (runs[0] / "evaluation_run.json").read_bytes() == (
        runs[1] / "evaluation_run.json"
    ).read_bytes()
    ok3 = (
        st["eval_designated_run1"] == "0"
        and st["eval_designated_run2"] == "0"
        and st["designated_sha_equal"] == "0"
        and same_bits
        and set(run) == KEYS
        and set(run["metrics"]) == {"net_pnl"}
        and run["synthetic"] is False
        and prov["flat_start_observed"] == OBSERVED
        and run["flat_start_proof"] == PROOF
        and run["invocation"] == {"single_call": True}
        and run["period"] == {"start": T.isoformat(), "end": FIN.isoformat()}
        and prov["source"] == {"kind": "designation", "identity": DESIGNATED}
        and cc.candidate_identity(run["strategy"], run["pair"], run["params"]) == DESIGNATED
    )
    results.append(
        (
            "3 chemin désigné, exécution",
            ok3,
            f"codes 0/0, identique au bit {same_bits}, clés {sorted(run)}, observé {prov['flat_start_observed']}, "
            f"preuve {run['flat_start_proof']}, invocation {run['invocation']}, période {run['period']}",
        )
    )

    # 4. séries et contrôles
    first = run["first_fill_at"]
    equity = run["equity_daily"]
    ok4 = (
        first is not None
        and cc.parse_datetime(first, where="first_fill_at") > T
        and equity["start"] == T.isoformat()
        and equity["end"] == FIN.isoformat()
        and len(equity["values"]) == len(daily_grid(T, FIN)) == 109
    )
    results.append(
        (
            "4 séries",
            ok4,
            f"first_fill_at {first} (> T), equity_daily [{equity['start']}, {equity['end']}] "
            f"{len(equity['values'])} points",
        )
    )

    # 5. admission
    admitted = cc.evaluation_admission(run)
    results.append(
        (
            "5 admission",
            st["admission"] == "0" and admitted is False,
            f"serveur admission={st['admission']}, recalcul local evaluation_admission -> {admitted}",
        )
    )

    # 6. continuité
    report = load(out / "chain" / "continuity.json")
    states = {key: clause["state"] for key, clause in report["clauses"].items()}
    expected = {
        "c1": "DECLARED",
        "c2": "DECLARED",
        "c3": "VERIFIED",
        "c4": "VERIFIED",
        "c5": "DECLARED",
    }
    ok6 = (
        st["c3_continuity"] == "0"
        and st["continuity_declared"] == "0"
        and states == expected
        and report["comparator"]["state"] == "VERIFIED"
        and report["state"] == "DECLARED"
        and report["synthetic"] is False
        and report["identity"] == DESIGNATED
    )
    results.append(
        (
            "6 continuité",
            ok6,
            f"c3_continuity={st['c3_continuity']}, clauses {states}, stamp_cell "
            f"{report['stamp_cell']['state']}, comparateur {report['comparator']['state']} (synthétique), "
            f"agrégat {report['state']}",
        )
    )

    # 7. base
    before = (out / "alembic_before.txt").read_text(encoding="utf-8")
    after = (out / "alembic_after.txt").read_text(encoding="utf-8")
    database = prov["database"]
    ok7 = (
        st["alembic_before"] == "0"
        and st["alembic_after"] == "0"
        and "c3bd1e7a0001 (head)" in before
        and before == after
        and database["transaction_read_only"] == "on"
        and database["alembic_version"] == ["c3bd1e7a0001"]
    )
    results.append(
        (
            "7 base",
            ok7,
            f"alembic identique avant/après ({before.strip().splitlines()[-1]}), transaction_read_only "
            f"{database['transaction_read_only']}",
        )
    )

    # 8. bornes des lectures
    firsts = [
        cc.parse_datetime(block["first"], where="warmup.first")
        for block in run["warmup"].values()
        if block["first"] is not None
    ]
    lasts = [
        cc.parse_datetime(block["last"], where="warmup.last")
        for block in run["warmup"].values()
        if block["last"] is not None
    ]
    stamp = run["liquidation"]["timestamp"]
    ok8 = (
        min(firsts) >= T - timedelta(days=400)
        and max(lasts) <= T
        and (stamp is None or cc.parse_datetime(stamp, where="liquidation") <= FIN)
        and prov["window"] == {"anchor": T.isoformat(), "end": FIN.isoformat()}
        and FIN < datetime(2021, 3, 1, tzinfo=UTC)
    )
    results.append(
        (
            "8 bornes",
            ok8,
            f"amorçage [{min(firsts).isoformat()}, {max(lasts).isoformat()}] (≥ T − 400 j, ≤ T), liquidation "
            f"{stamp} (≤ fin), fenêtre {prov['window']}",
        )
    )

    failed = 0
    for name, ok, detail in results:
        print(f"{'TENU ' if ok else 'ÉCART'}  {name} — {detail}")
        failed += 0 if ok else 1
    print(f"items tenus : {len(results) - failed}/{len(results)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
