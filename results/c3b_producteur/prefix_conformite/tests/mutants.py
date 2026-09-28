"""C3b lot 3 — mutants temporaires du producteur (``c3b_common.py``, ``c3b_prefix.py``).

Chaque mutant remplace **une** chaîne (présente exactement une fois) dans un fichier source, lance les deux fichiers
de tests du lot, consigne le nombre d'échecs et la durée, puis **restaure** le fichier et vérifie que son sha256 est
celui d'origine. Un mutant qui ne rougit pas est un trou des tests, sauf s'il est déclaré équivalent (sortie
identique par construction), avec la raison. Une durée anormale est un signal (lot 2 : 579 s, test non hermétique).

Usage (depuis la racine du dépôt, après la suite complète, jamais pendant) ::

    poetry run python results/c3b_producteur/prefix_conformite/tests/mutants.py > mutants.log
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
COMMON = "scripts/audit/c3b_common.py"
PREFIX = "scripts/audit/c3b_prefix.py"
TESTS = ["tests/test_scripts/test_c3b_common.py", "tests/test_scripts/test_c3b_prefix.py"]

#: (identifiant, fichier, ancienne chaîne, nouvelle chaîne, ce que le mutant casse)
MUTANTS: list[tuple[str, str, str, str, str]] = [
    ("M01", COMMON, '"amount_base": str(amount),', '"amount_btc": str(amount),', "lot non renommé"),
    (
        "M02",
        COMMON,
        '"residual_trade_btc": "residual_trade_base",',
        '"residual_trade_btc": "residual_trade_btc",',
        "bloc non renommé",
    ),
    (
        "M03",
        COMMON,
        "(gross - fee - pnl) / amount",
        "(gross - pnl) / amount",
        "entry_price sans le fee",
    ),
    (
        "M04",
        COMMON,
        "if trade.forced_liquidation is not True:",
        "if False:",
        "lots depuis tous les trades",
    ),
    (
        "M05",
        COMMON,
        "entry = None if pnl is None else (gross - fee - pnl) / amount",
        "entry = (gross - fee - (pnl or 0)) / amount",
        "entry_price calculé quand pnl est nul",
    ),
    (
        "M06",
        COMMON,
        '"expected_units": cc.expected_units(start, end, interval),',
        '"expected_units": cc.full_days_in(start, end),',
        "1 w compté en jours (dénominateur)",
    ),
    (
        "M07",
        COMMON,
        '"unit": cc.coverage_unit(interval),',
        '"unit": "day",',
        "1 w compté en jours (unité)",
    ),
    (
        "M08",
        COMMON,
        "seen = set(observed)\n",
        "seen = set(observed) - set(derived)\n",
        "dérivées non comptées",
    ),
    (
        "M09",
        COMMON,
        "missing = [stamp for stamp in grid if stamp not in seen]",
        "missing = [stamp for stamp in grid if stamp not in seen and seen and stamp > min(seen)]",
        "trou de bord ignoré",
    ),
    (
        "M10",
        COMMON,
        "covered = [unit for unit in units if _unit_covered(unit, by_unit[unit.hi], interval)]",
        "covered = [unit for unit in units if len(by_unit[unit.hi]) < (unit.hi - unit.lo) / _step(interval)]",
        "first_day sur les observées",
    ),
    (
        "M11",
        COMMON,
        "late = [stamp for stamp in stamps if stamp > end]",
        "late: list[datetime] = []",
        "filtre > T retiré",
    ),
    (
        "M12",
        COMMON,
        "if len(set(stamps)) != len(stamps):",
        "if False:",
        "doublon de bougie accepté",
    ),
    ("M13", COMMON, '"close": str(close)}', '"close": float(close)}', "close en float"),
    (
        "M14",
        COMMON,
        "early = [stamp for stamp in stamps if stamp < start]",
        "early: list[datetime] = []",
        "bougie avant le début acceptée",
    ),
    (
        "M15",
        COMMON,
        '        "exec_interval": manifest.exec_interval,\n',
        "",
        "exec_interval non exporté",
    ),
    (
        "M16",
        COMMON,
        "out[candidate.identity] = sorted(timeframes)",
        "out[candidate.identity] = sorted(timeframes, reverse=True)",
        "decision_timeframes non triée",
    ),
    (
        "M17",
        COMMON,
        '        "decision_timeframes": list(decision_timeframes),\n',
        "",
        "decision_timeframes absente",
    ),
    (
        "M18",
        COMMON,
        'f"{prefix}_end": anchor.isoformat(),',
        'f"{prefix}_end": anchor.replace(hour=0, minute=0).isoformat(),',
        "period arrondie à minuit",
    ),
    (
        "M19",
        COMMON,
        "return end > CAMPAIGN_START and not unlock.exists()",
        "return end >= CAMPAIGN_START and not unlock.exists()",
        "garde-fou en >=",
    ),
    (
        "M20",
        COMMON,
        "    del start\n    return end > CAMPAIGN_START and not unlock.exists()",
        "    return start >= CAMPAIGN_START and not unlock.exists()",
        "garde-fou sur start seul",
    ),
    (
        "M21",
        COMMON,
        "return end > CAMPAIGN_START and not unlock.exists()",
        "return end > CAMPAIGN_START",
        "garde-fou qui ignore le fichier",
    ),
    (
        "M22",
        COMMON,
        "CAMPAIGN_START = datetime(2021, 3, 1, tzinfo=UTC)",
        "CAMPAIGN_START = datetime(2021, 3, 2, tzinfo=UTC)",
        "borne du garde-fou déplacée",
    ),
    (
        "M23",
        PREFIX,
        "    anchor = manifest.anchor()\n    # 3. garde-fou 6",
        "    anchor = manifest.anchor()\n    c3bc.decision_timeframes_by_candidate(manifest)\n    # 3. garde-fou 6",
        "classmethod avant le garde-fou",
    ),
    (
        "M24",
        PREFIX,
        "    if param_problems:\n",
        "    if False:\n",
        "validation des paramètres retirée",
    ),
    (
        "M25",
        COMMON,
        "if type(value) is not int:",
        "if not isinstance(value, int):",
        "grid_levels bool accepté",
    ),
    (
        "M26",
        COMMON,
        "if not parsed.is_finite():",
        "if False:",
        "bias_1d non fini accepté par le validateur",
    ),
    (
        "M27",
        COMMON,
        'raise ProducerRefusal("decision_timeframes_refused", problems)',
        "pass",
        "refus de la classmethod rattrapé candidat par candidat",
    ),
    ("M28", COMMON, "if engine != ENGINE_GRID:", "if False:", "moteur non grid accepté"),
    (
        "M29",
        PREFIX,
        "except cc.NonFiniteValueError as exc:",
        "except KeyError as exc:",
        "NonFiniteValueError non rattrapée",
    ),
    (
        "M30",
        PREFIX,
        "        await engine.run(candidate.pair, context.manifest.window_start, context.anchor)\n",
        "        await engine.run(candidate.pair, context.manifest.window_start, context.anchor)\n        await engine.run(candidate.pair, context.manifest.window_start, context.anchor)\n",
        "run appelé deux fois",
    ),
    (
        "M31",
        PREFIX,
        "await engine.run(candidate.pair, context.manifest.window_start, context.anchor)",
        "await engine.run(candidate.pair, context.manifest.window_start, context.manifest.window_end)",
        "run jusqu'à window.end",
    ),
    (
        "M32",
        PREFIX,
        "    anchor = manifest.anchor()\n",
        "    anchor = manifest.window_end\n",
        "T pris à window.end",
    ),
    (
        "M33",
        PREFIX,
        "if recorded_manifest != manifest_sha256:",
        "if False:",
        "reprise sous un autre manifeste",
    ),
    ("M34", PREFIX, "if recorded_git != git_sha:", "if False:", "reprise sous un autre commit"),
    (
        "M35",
        COMMON,
        "        pair_costs=dict(pair_costs),\n",
        "        pair_costs=None,\n",
        "coûts du modèle de fees au lieu du manifeste",
    ),
    ("M36", COMMON, "if declared != recorded:", "if False:", "coûts non recoupés au fichier"),
    (
        "M37",
        COMMON,
        "if name != manifest.fee_model:",
        "if False:",
        "nom du modèle de fees non recoupé",
    ),
    (
        "M38",
        COMMON,
        'if effective["passed_params"] != expected:',
        "if False:",
        "contrôle passed_params retiré",
    ),
    (
        "M39",
        PREFIX,
        'if untracked or origin["tracked_tree_clean"] is not True:',
        "if False:",
        "contrôle uncommitted_tree retiré",
    ),
    ("M40", PREFIX, "    if failures:\n", "    if False:\n", "job en échec ignoré"),
    (
        "M41",
        COMMON,
        "    if not covered:\n",
        "    if False:\n",
        "série sans unité couverte acceptée",
    ),
    (
        "M42",
        COMMON,
        "if trade.forced_liquidation is not True:",
        "if not bool(trade.forced_liquidation):",
        "coercition bool( dans la source",
    ),
    (
        "M43",
        PREFIX,
        "logger = structlog.get_logger()\n",
        'logger = structlog.get_logger()\nload_dotenv(_ROOT / ".env")\n',
        ".env chargé à l'import",
    ),
    (
        "M44",
        PREFIX,
        "    return {identity: dict(entries[identity]) for identity in sorted(entries)}",
        "    return {identity: dict(entries[identity]) for identity in entries}",
        "ordre d'achèvement conservé à l'assemblage",
    ),
]

#: Mutants équivalents : la sortie est identique par construction ; ils ne peuvent pas rougir.
EQUIVALENT = {
    "M44": "le writer strict trie les clés (sort_keys=True) : l'ordre d'insertion d'observations.json ne peut pas "
    "changer le texte écrit ; l'indépendance à l'ordre d'exécution est portée par le test du pool inversé",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_tests() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", *TESTS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-300:]
    return proc.returncode, tail


def main() -> int:
    originals = {rel: (ROOT / rel).read_bytes() for rel in (COMMON, PREFIX)}
    digests = {rel: sha256(ROOT / rel) for rel in originals}
    print(f"originaux : {COMMON} {digests[COMMON]} ; {PREFIX} {digests[PREFIX]}")
    code, tail = run_tests()
    print(f"témoin (aucun mutant) : code {code} — {tail}")
    if code != 0:
        print("ARRÊT : le témoin n'est pas vert")
        return 2
    survivors: list[str] = []
    for ident, rel, old, new, what in MUTANTS:
        path = ROOT / rel
        text = originals[rel].decode("utf-8")
        count = text.count(old)
        if count != 1:
            print(f"{ident} {what} : chaîne présente {count} fois — mutant non appliqué")
            survivors.append(ident)
            continue
        path.write_text(text.replace(old, new), encoding="utf-8")
        started = time.monotonic()
        try:
            code, tail = run_tests()
        finally:
            path.write_bytes(originals[rel])
        elapsed = time.monotonic() - started
        restored = sha256(path) == digests[rel]
        failed = re.search(r"(\d+) failed", tail)
        errors = re.search(r"(\d+) error", tail)
        verdict = "ROUGE" if code != 0 else ("ÉQUIVALENT" if ident in EQUIVALENT else "SURVIVANT")
        if verdict == "SURVIVANT":
            survivors.append(ident)
        print(
            f"{ident} [{rel.split('/')[-1]}] {what} : {verdict} — "
            f"{failed.group(1) if failed else 0} échec(s), {errors.group(1) if errors else 0} erreur(s), "
            f"{elapsed:.1f} s, restauré {'oui' if restored else 'NON'}"
        )
        if not restored:
            print("ARRÊT : fichier non restauré")
            return 3
    for ident, reason in EQUIVALENT.items():
        print(f"équivalent {ident} : {reason}")
    print(f"survivants : {survivors or 'aucun'}")
    return 0 if not survivors else 1


if __name__ == "__main__":
    raise SystemExit(main())
