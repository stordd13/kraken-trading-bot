"""Vérifie l'attendu déclaré (``../ATTENDU.md``) sur les artefacts du run serveur (C3b lot 3).

Champs déclarés seulement : rien de l'issue BTC/ETH (ni statut de sélection, ni raison, ni candidat retenu, ni
métrique) n'est lu. Le seul regard sur ``selection.status`` est le booléen ``!= "SÉLECTION_VALIDE"``, qui ne
distingue pas une sélection descriptive d'une abstention.

Usage : depuis le répertoire ``out/`` de l'archive extraite (``~/archive/c3b_lot3_20260928/``, qui contient aussi
``run1/candles.json``, 15 Mo, non versionné) : ``python verify_attendu.py > verify_attendu.out``.
"""

from __future__ import annotations

from collections import Counter
import json
from typing import Any

T = "2020-09-11T21:36:00+00:00"
START = "2020-01-06T00:00:00+00:00"
CLASSES = {
    "{}": "C1",
    '{"bear_protection_mode": "1w_only", "bias_1d": 0}': "C2",
    '{"bear_protection_mode": "none"}': "C5",
    '{"bear_protection_mode": "none", "bias_1d": 0}': "C6",
}


def load(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def cls(params: Any) -> str:
    return CLASSES[json.dumps(params, sort_keys=True)]


def producer() -> None:
    obs = load("run1/observations.json")
    run = load("run1/prefix_run.json")
    run2 = load("run2/prefix_run.json")
    cov = load("run1/coverage.json")
    can = load("run1/candles.json")
    durations = [c["duration_s"] for c in run["candidates"]]
    print("## 1. producteur")
    print("entrées", len(obs), "; paires", dict(Counter(e["pair"] for e in obs.values())))
    print("anchor", run["anchor"], "== T" if run["anchor"] == T else "!= T")
    print("exec_interval", sorted({e["exec_interval"] for e in obs.values()}))
    print(
        "decision_timeframes par classe",
        sorted({(cls(e["params"]), tuple(e["decision_timeframes"])) for e in obs.values()}),
    )
    derived = sum(len(v) for p in run["derived_stamps"].values() for v in p.values())
    print("estampilles dérivées dans (début, T]", derived)
    resumed = [c["identity"][:8] for c in run["candidates"] if c["resumed"]]
    print("workers run1/run2", run["workers"], run2["workers"], "; repris", resumed)
    print("durée des jobs run1 (s) min/max", min(durations), max(durations))
    print("provenance git", run["provenance"])
    print("base", run["database"])
    print("environnement", run["environment"])
    print("interpréteur", run["interpreter"])
    print("manifeste", run["manifest"])
    print(
        "sorties run1 == run2 (prefix_run.outputs)",
        run["outputs"] == run2["outputs"],
        run["outputs"],
    )
    print("couverture fenêtre", cov["window"], "; paires", sorted(cov["pairs"]))
    rows = {p: v["exec"] + v["daily"] for p, v in can["pairs"].items()}
    print("bougies : max t <= T", {p: max(r["t"] for r in v) <= T for p, v in rows.items()})
    print("bougies : min t >= début", {p: min(r["t"] for r in v) >= START for p, v in rows.items()})


def chain() -> None:
    obs = load("run1/observations.json")
    anchor = load("chain/anchor.json")
    print("## 2. c3_anchor")
    print(
        "exit",
        anchor["exit_code"],
        "anchor",
        anchor["anchor"],
        "variant",
        anchor["variant_key"][:16],
    )
    entry = load("chain/entry.json")
    print("## 3. c3_entry")
    print(
        "exit", entry["exit_code"], "; refus", entry["refusal"], "; violations", entry["violations"]
    )
    print(
        "provenance", entry["universe_provenance"], "; couverture", entry["coverage"].get("status")
    )
    print(
        "assertions",
        [(r.get("id") or r.get("assertion"), r["status"]) for r in entry["assertions"]],
    )
    print("non assertables", entry["not_assertable"])
    diagnostics = sorted(
        (
            obs[d["key"]]["pair"],
            cls(obs[d["key"]]["params"]),
            tuple(d["timeframes_insufficient"]),
            d["reason"],
        )
        for d in entry["candidate_diagnostics"]
    )
    print("D2 en échec", entry["n_candidates_d2_failed"], diagnostics)
    bench = load("chain/benchmark.json")
    sol = bench["pairs"]["SOL/USDT"]
    print("## 4. c3_benchmark")
    print(
        "exit", bench["exit_code"], "; SOL buildable", sol["buildable"], "; reason", sol["reason"]
    )
    selection = load("chain/selection.json")
    pair = selection["pairs"]["SOL/USDT"]
    five = {k: pair["d1"]["per_interval"]["5"][k] for k in ("covered_units", "expected_units")}
    print("## 5. c3_select")
    print("exit", selection["exit_code"], "; provenance", selection["provenance"])
    print("aucune SÉLECTION_VALIDE", selection["status"] != "SÉLECTION_VALIDE")
    print(
        "SOL paire",
        pair["status"],
        "; d1.ok",
        pair["d1"]["ok"],
        "; benchmark_ok",
        pair["benchmark_ok"],
        "; 5 min",
        five,
    )
    sol_candidates = sorted(
        (cls(c["params"]), c["first_failed_gate"], c["status"], c["candidate_reason"])
        for c in selection["candidates"]
        if c["pair"] == "SOL/USDT"
    )
    print("SOL candidats", sol_candidates)


if __name__ == "__main__":
    producer()
    chain()
