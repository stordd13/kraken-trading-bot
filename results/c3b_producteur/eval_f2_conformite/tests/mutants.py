"""C3b lot 4b — mutants temporaires de la partie 2 de l'évaluateur (``c3b_evaluate.py``).

Harnais des lots 3 et 4a (``eval_conformite/tests/mutants.py``), étendu aux mutants **à plusieurs sites** (M03, M06 :
une source fautive qui doit d'abord être rendue joignable). Chaque mutant remplace des chaînes présentes chacune
exactement une fois, lance les trois fichiers de tests des lots 3-4, consigne le verdict, les tests rouges, la durée,
puis **restaure** le fichier et vérifie son sha256. Un mutant qui ne rougit pas est un trou des tests, sauf s'il est
déclaré équivalent avec sa raison. Une durée anormale est un signal d'herméticité (lot 2 : 579 s).

Usage (depuis la racine du dépôt, après la suite complète, jamais pendant) ::

    poetry run python results/c3b_producteur/eval_f2_conformite/tests/mutants.py > mutants.log
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
EVAL = "scripts/audit/c3b_evaluate.py"
TESTS = [
    "tests/test_scripts/test_c3b_common.py",
    "tests/test_scripts/test_c3b_prefix.py",
    "tests/test_scripts/test_c3b_evaluate.py",
]

Site = tuple[str, str]
#: (identifiant, sites (ancienne chaîne, nouvelle chaîne), ce que le mutant casse) — plan du lot 4b § 3.3.
MUTANTS: list[tuple[str, list[Site], str]] = [
    (
        "M01",
        [
            (
                "        pair_index=pairs.index(pair),\n",
                "        pair_index=[c.pair for c in manifest.candidates].index(pair),\n",
            )
        ],
        "index de paire pris dans l'ordre des candidats du manifeste",
    ),
    (
        "M02",
        [
            (
                "        days=(end - anchor).total_seconds() / 86400.0,\n",
                '        days=float(raw["evaluation_days"]),\n',
            )
        ],
        "n_jours = anchor.evaluation_days",
    ),
    (
        "M03",
        [
            (
                "            metrics = engine.metrics.to_dict()\n",
                "            metrics = engine.metrics.to_dict()\n"
                '            observed["duration_days"] = metrics.get("duration_days", 0.0)\n',
            ),
            (
                "            days=draw.days,\n",
                '            days=result.observed["duration_days"],\n',
            ),
            (
                "            inputs=draw,\n",
                '            inputs=replace(draw, days=result.observed["duration_days"]),\n',
            ),
        ],
        "n_jours = metrics.duration_days du moteur (équivalent sur le vrai moteur, plan E8)",
    ),
    (
        "M04",
        [
            (
                "            inputs=draw,\n",
                "            inputs=replace(draw, days=float(len(series.returns_config))),\n",
            )
        ],
        "n_jours = nombre de rendements",
    ),
    (
        "M05",
        [("    if seed != manifest.seed:\n", "    if False:\n")],
        "graine non recoupée au manifeste",
    ),
    (
        "M06",
        [
            (
                "            metrics = engine.metrics.to_dict()\n",
                "            metrics = engine.metrics.to_dict()\n"
                '            observed["curve"] = [float(v) for _, v in engine.equity_curve]\n',
            ),
            (
                '            result.payload["equity_daily"]["values"],\n',
                '            result.observed["curve"],\n',
            ),
        ],
        "returns_config depuis engine.equity_curve",
    ),
    (
        "M07",
        [
            (
                "            matching: list(\n"
                "                cc.recompute_daily(\n"
                "                    [float(v) for v in cb.blend_nav(nav_bh, lambdas[matching], capital)],\n"
                "                    days=days,\n"
                "                ).returns\n"
                "            )\n",
                "            matching: [\n"
                "                float(c / p - 1)\n"
                "                for p, c in zip(\n"
                "                    cb.blend_nav(nav_bh, lambdas[matching], capital),\n"
                "                    cb.blend_nav(nav_bh, lambdas[matching], capital)[1:],\n"
                "                )\n"
                "            ]\n",
            )
        ],
        "rendements du comparateur par le chemin Decimal de build_pair",
    ),
    (
        "M08",
        [
            (
                "cb.blend_nav(nav_bh, lambdas[matching], capital)",
                "cb.blend_nav(nav_bh, Decimal(str(cb.match_lambda(cb.LambdaCurve(nav_bh, capital, matching), "
                '{"dd": daily.mdd_daily, "sigma": daily.sigma_daily}[matching] or 0.0).lam or 0.0)), capital)',
            )
        ],
        "λ ré-estimé sur la fenêtre d'évaluation au lieu du λ du préfixe",
    ),
    (
        "M09",
        [
            (
                "        lambdas[matching] = Decimal(str(value))\n",
                '        lambdas["sigma" if matching == "dd" else "dd"] = Decimal(str(value))\n',
            )
        ],
        "λ dd et σ permutés",
    ),
    (
        "M10",
        [
            (
                "        lambdas[matching] = Decimal(str(value))\n",
                "        lambdas[matching] = Decimal(value)\n",
            )
        ],
        "Decimal(λ) au lieu de Decimal(str(λ))",
    ),
    (
        "M11",
        [
            (
                "    block = candidates[candidate.identity]\n",
                "    block = next(iter(candidates.values()))\n",
            )
        ],
        "λ du premier bloc de benchmark.json",
    ),
    (
        "M12",
        [
            (
                '            "cagr_pct": replay.cagr_config,\n',
                '            "cagr_pct": cc.cagr_pct(returns_config, inputs.days),\n',
            )
        ],
        "cagr_pct par cc.cagr_pct (math.fsum) au lieu du chemin du rejeu",
    ),
    (
        "M13",
        [
            (
                '            "delta_dd": replay.delta_hat["dd"],\n',
                '            "delta_dd": replay.delta_hat["sigma"],\n',
            )
        ],
        "delta_dd pris sur l'appariement σ",
    ),
    (
        "M14",
        [("    if len(set(lengths.values())) != 1:\n", "    if False:\n")],
        "longueurs non contrôlées",
    ),
    (
        "M15",
        [
            (
                '        cc.check_returns(returns_config, label="returns_config")\n'
                "        for matching, series in returns_bench.items():\n"
                '            cc.check_returns(series, label=f"returns_bench.{matching}")\n',
                "        pass\n",
            )
        ],
        "entrées invalides (§ F.2 e) non contrôlées",
    ),
    (
        "M16",
        [("    return {**base, **f2}\n", '    return {**base, **f2, "n_days": 0.0}\n')],
        "clé en trop dans evaluation.json",
    ),
    (
        "M17",
        [("    comparable = all(tests.values())\n", "    comparable = True\n")],
        "comparable posé",
    ),
    (
        "M18",
        [
            (
                '        "window": {"start": anchor.isoformat(), "end": end.isoformat()},\n'
                '        "comparable": comparable,\n',
                '        "window": {"start": bench.entry_stamp, "end": bench.exit_stamp},\n'
                '        "comparable": comparable,\n',
            )
        ],
        "fenêtre de benchmark_eval = estampilles d'entrée et de sortie",
    ),
    (
        "M19",
        [
            (
                '        "comparability": tests,\n',
                '        "comparability": dict(bench.comparability),\n',
            )
        ],
        "comparability à sept clés",
    ),
    (
        "M20",
        [
            (
                "            interval=manifest.exec_interval,\n            start=anchor,\n",
                "            interval=manifest.exec_interval,\n            start=manifest.window_start,\n",
            )
        ],
        "bougies lues depuis le début de la fenêtre",
    ),
    (
        "M21",
        [
            (
                "            interval=c3bc.DAILY_INTERVAL,\n            start=anchor,\n            end=end,\n",
                "            interval=c3bc.DAILY_INTERVAL,\n            start=anchor,\n"
                "            end=end.replace(year=end.year + 1),\n",
            )
        ],
        "bougies quotidiennes lues au-delà de fin",
    ),
    (
        "M22",
        [
            (
                "        comparator, benchmark_eval = evaluation_comparator(\n"
                "            candles, manifest=manifest, candidate=candidate, anchor=anchor, end=end\n"
                "        )\n"
                "        started = time.monotonic()\n"
                "        try:\n"
                "            engine = c3bc.build_engine(get_settings(), db, manifest, candidate, pair_costs)\n",
                "        started = time.monotonic()\n"
                "        try:\n"
                "            engine = c3bc.build_engine(get_settings(), db, manifest, candidate, pair_costs)\n"
                "            comparator, benchmark_eval = evaluation_comparator(\n"
                "                candles, manifest=manifest, candidate=candidate, anchor=anchor, end=end\n"
                "            )\n",
            )
        ],
        "comparateur construit après le moteur",
    ),
    (
        "M23",
        [
            (
                '        raise c3bc.ProducerRefusal(\n            "comparator_not_buildable"',
                '        raise c3bc.ProducerControlError(\n            "comparator_not_buildable"',
            )
        ],
        "comparateur non constructible en code 3",
    ),
    (
        "M24",
        [
            (
                '    if not estimable:\n        raise c3bc.ProducerRefusal(\n            "lambda_not_estimable",',
                '    if False:\n        raise c3bc.ProducerRefusal(\n            "lambda_not_estimable",',
            )
        ],
        "NOT_ESTIMABLE ignoré",
    ),
    (
        "M25",
        [
            (
                '    if mismatch:\n        raise c3bc.ProducerRefusal("benchmark_inputs_mismatch", mismatch)',
                '    if False:\n        raise c3bc.ProducerRefusal("benchmark_inputs_mismatch", mismatch)',
            )
        ],
        "empreintes de benchmark.json non recoupées",
    ),
    (
        "M26",
        [
            (
                '        if mismatch:\n            return _refuse("selection_benchmark_mismatch", mismatch)',
                '        if False:\n            return _refuse("selection_benchmark_mismatch", mismatch)',
            )
        ],
        "empreinte de benchmark.json enregistrée par c3_select non recoupée",
    ),
    (
        "M27",
        [("        if not 0.0 <= value <= 1.0:\n", "        if False:\n")],
        "domaine de λ non contrôlé",
    ),
    (
        "M28",
        [
            (
                "            (EVALUATION, evaluation),\n",
                '            (EVALUATION, {**evaluation, "sensitivity": sensitivity}),\n',
            )
        ],
        "sensibilité écrite dans evaluation.json",
    ),
    (
        "M29",
        [
            (
                '        combination: {"delta_stars": list(kept), ',
                '        combination: {"delta_stars": __import__("numpy").asarray(kept), ',
            )
        ],
        "delta_stars en ndarray",
    ),
    (
        "M30",
        [
            (
                '        "environment": cc.replay_environment(),\n        "B": cc.BOOTSTRAP_B,\n',
                '        "environment": {**cc.replay_environment(), "system": "x"},\n        "B": cc.BOOTSTRAP_B,\n',
            )
        ],
        "environnement avec un champ en trop",
    ),
    (
        "M31",
        [
            (
                "    if args.candidate is not None and c3bc.designation_window_forbidden(manifest.window_end):",
                "    if False:",
            )
        ],
        "garde de désignation retirée (reprise du 4a)",
    ),
    (
        "M32",
        [("    if mode != cc.LAMBDA_MODE_DECISIONAL:\n", "    if False:\n")],
        "mode de λ non contrôlé",
    ),
    (
        "M33",
        [("    except OverflowError as exc:\n", "    except ZeroDivisionError as exc:\n")],
        "CAGR observé non fini (math.exp) non rattrapé",
    ),
    (
        "M34",
        [
            (
                '            "benchmark_refused", ["benchmark.candidates : aucun bloc pour l\'identité évaluée"]',
                '            "benchmark_refused", [f"benchmark.candidates : aucun bloc pour {candidate.identity}"]',
            )
        ],
        "identité absente nommée dans le journal",
    ),
    (
        "M35",
        [("    if pair != candidate.pair:\n", "    if False:\n")],
        "paire du bloc de benchmark non recoupée",
    ),
]

#: Mutants équivalents : la sortie est identique par construction ; la raison est écrite avant le passage et relue.
EQUIVALENT: dict[str, str] = {}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_tests() -> tuple[int, str, list[str]]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "-rfE", *TESTS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    lines = proc.stdout.strip().splitlines()
    tail = lines[-1] if lines else proc.stderr[-300:]
    red = sorted(
        {
            match.group(1).replace("tests/test_scripts/", "")
            for line in lines
            if (match := re.match(r"^(?:FAILED|ERROR) (.+?)(?: - .*)?$", line))
        }
    )
    return proc.returncode, tail, red


def main() -> int:
    path = ROOT / EVAL
    original = path.read_bytes()
    digest = sha256(path)
    print(f"original : {EVAL} {digest}")
    code, tail, _ = run_tests()
    print(f"témoin (aucun mutant) : code {code} — {tail}")
    if code != 0:
        print("ARRÊT : le témoin n'est pas vert")
        return 2
    survivors: list[str] = []
    for ident, sites, what in MUTANTS:
        text = original.decode("utf-8")
        counts = [text.count(old) for old, _ in sites]
        if counts != [1] * len(sites):
            print(f"{ident} {what} : chaînes présentes {counts} fois — mutant non appliqué")
            survivors.append(ident)
            continue
        for old, new in sites:
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
        started = time.monotonic()
        try:
            code, tail, red = run_tests()
        finally:
            path.write_bytes(original)
        elapsed = time.monotonic() - started
        restored = sha256(path) == digest
        verdict = "ROUGE" if code != 0 else ("ÉQUIVALENT" if ident in EQUIVALENT else "SURVIVANT")
        if verdict == "SURVIVANT":
            survivors.append(ident)
        print(
            f"{ident} {what} : {verdict} — {tail} — {elapsed:.1f} s, restauré {'oui' if restored else 'NON'}"
        )
        for test in red:
            print(f"    rouge : {test}")
        if not restored:
            print("ARRÊT : fichier non restauré")
            return 3
    for ident, reason in EQUIVALENT.items():
        print(f"équivalent {ident} : {reason}")
    print(f"survivants : {survivors or 'aucun'}")
    return 0 if not survivors else 1


if __name__ == "__main__":
    raise SystemExit(main())
