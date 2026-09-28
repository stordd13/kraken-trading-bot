"""C3b lot 4a — mutants temporaires de l'évaluateur (``c3b_evaluate.py``) et de ce que le lot touche dans
``c3b_common.py`` (``passed_params_problems`` extrait, ``designation_window_forbidden``).

Même harnais que le lot 3 (``prefix_conformite/tests/mutants.py``) : chaque mutant remplace **une** chaîne (présente
exactement une fois), lance les trois fichiers de tests des lots 3 et 4a, consigne le verdict, les tests rouges
(identifiants ``fichier::test``), la durée, puis **restaure** le fichier et vérifie son sha256. Un mutant qui ne
rougit pas est un trou des tests, sauf s'il est déclaré équivalent, avec la raison. Une durée anormale est un signal
d'herméticité (lot 2 : 579 s).

Usage (depuis la racine du dépôt, après la suite complète, jamais pendant) ::

    poetry run python results/c3b_producteur/eval_conformite/tests/mutants.py > mutants.log
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
EVAL = "scripts/audit/c3b_evaluate.py"
TESTS = [
    "tests/test_scripts/test_c3b_common.py",
    "tests/test_scripts/test_c3b_prefix.py",
    "tests/test_scripts/test_c3b_evaluate.py",
]

#: (identifiant, fichier, ancienne chaîne, nouvelle chaîne, ce que le mutant casse)
MUTANTS: list[tuple[str, str, str, str, str]] = [
    (
        "M01",
        COMMON,
        '    if effective["passed_params"] != expected:\n',
        "    if False:\n",
        "E10 extrait : divergence non vue (rouge attendu aux lots 3 ET 4a)",
    ),
    (
        "M02",
        COMMON,
        "    return end > CAMPAIGN_START\n",
        "    return end > CAMPAIGN_START and not CAMPAIGN_UNLOCK.exists()\n",
        "garde de désignation ouverte par CAMPAIGN_UNLOCK",
    ),
    (
        "M03",
        COMMON,
        "    return end > CAMPAIGN_START\n",
        "    return end >= CAMPAIGN_START\n",
        "garde de désignation en >= (borne)",
    ),
    (
        "M04",
        EVAL,
        "            proof, observed = capture_flat_start(engine, capital=manifest.capital, anchor=anchor)\n"
        "            invocation = await run_once(engine, candidate.pair, anchor, end)\n",
        "            invocation = await run_once(engine, candidate.pair, anchor, end)\n"
        "            proof, observed = capture_flat_start(engine, capital=manifest.capital, anchor=anchor)\n",
        "preuve à plat lue après run",
    ),
    (
        "M05",
        EVAL,
        "    await engine.run(pair, start, end)\n",
        "    await engine.run(pair, start, end)\n    await engine.run(pair, start, end)\n",
        "run appelé deux fois",
    ),
    (
        "M06",
        EVAL,
        "    elif balance != capital:",
        "    elif str(balance) != str(capital):",
        "cash comparé en chaînes",
    ),
    (
        "M07",
        EVAL,
        "    elif balance != capital:",
        "    elif float(balance) != float(capital):",
        "cash comparé en float",
    ),
    ("M08", EVAL, '"cash": str(capital)', '"cash": str(balance)', "cash exporté depuis le moteur"),
    ("M09", EVAL, "    if buys + sells != 0:", "    if buys != 0:", "ordres de vente ignorés"),
    ("M10", EVAL, "    if strategy_built:\n", "    if False:\n", "stratégie construite ignorée"),
    ("M11", EVAL, "    elif held != 0:", "    elif False:", "inventaire avant run ignoré"),
    ("M12", EVAL, "    first = min(stamps)", "    first = max(stamps)", "first_fill_at par max"),
    ("M13", EVAL, "    if first <= anchor:", "    if first < anchor:", "remplissage à T accepté"),
    (
        "M14",
        EVAL,
        "    if not gap <= NET_PNL_IDENTITY_TOL:",
        "    if False:",
        "identité net_pnl non contrôlée",
    ),
    (
        "M15",
        EVAL,
        '        if cell["state"] != "VERIFIED":',
        "        if False:",
        "cellule d'estampille non contrôlée",
    ),
    (
        "M16",
        EVAL,
        "    if trades > 0:\n        cell",
        "    if True:\n        cell",
        "exemption trades == 0 retirée",
    ),
    (
        "M17",
        EVAL,
        "        if start != anchor:",
        "        if False:",
        "equity_daily.start non contrôlé",
    ),
    ("M18", EVAL, "        if stop != end:", "        if False:", "equity_daily.end non contrôlé"),
    (
        "M19",
        EVAL,
        "        if len(values) != expected:",
        "        if False:",
        "longueur de la grille non contrôlée",
    ),
    (
        "M20",
        EVAL,
        "    if equity_daily is None:\n        problems.append",
        "    if False:\n        problems.append",
        "equity_daily absent non contrôlé",
    ),
    (
        "M21",
        EVAL,
        '"period": {"start": anchor.isoformat(), "end": end.isoformat()},',
        '"period": {"start": anchor.replace(hour=0).isoformat(), "end": end.isoformat()},',
        "period.start faux",
    ),
    ("M22", EVAL, '"synthetic": False,', '"synthetic": True,', "artefact déclaré synthétique"),
    ("M23", EVAL, "    if declared != anchor:", "    if False:", "T de l'ancrage non recoupé"),
    (
        "M24",
        EVAL,
        '    if mismatch:\n        raise c3bc.ProducerRefusal("anchor_inputs_mismatch", mismatch)',
        '    if False:\n        raise c3bc.ProducerRefusal("anchor_inputs_mismatch", mismatch)',
        "empreinte du manifeste de l'ancrage non recoupée",
    ),
    (
        "M25",
        EVAL,
        '    if mismatch:\n        raise c3bc.ProducerRefusal("selection_inputs_mismatch", mismatch)',
        '    if False:\n        raise c3bc.ProducerRefusal("selection_inputs_mismatch", mismatch)',
        "empreintes de la sélection non recoupées",
    ),
    ("M26", EVAL, "    if head != identity:", "    if False:", "tête du classement non recoupée"),
    (
        "M27",
        EVAL,
        "    if derived != identity:",
        "    if False:",
        "identité du retenu non dérivée",
    ),
    (
        "M28",
        EVAL,
        '    if candidate is None:\n        problems.append("selection.retained hors',
        '    if False:\n        problems.append("selection.retained hors',
        "retenu hors univers non vu",
    ),
    (
        "M29",
        EVAL,
        "        if retained is None:\n            return _refuse(",
        "        if False:\n            return _refuse(",
        "sélection vide qui continue",
    ),
    (
        "M30",
        EVAL,
        "    if args.candidate is not None and c3bc.designation_window_forbidden(manifest.window_end):",
        "    if False:",
        "garde de désignation non appelée",
    ),
    (
        "M31",
        EVAL,
        '        "metrics": {"net_pnl": net_pnl},\n    }',
        '        "metrics": {"net_pnl": net_pnl},\n        "decision_timeframes": [],\n    }',
        "clé en trop dans evaluation_run.json",
    ),
    (
        "M32",
        EVAL,
        'logger.info("evaluated", source=source["kind"], duration_s=result.duration_s)',
        'logger.info("evaluated", source=source["kind"], duration_s=result.duration_s, pair=candidate.pair)',
        "paire dans le journal",
    ),
    (
        "M33",
        EVAL,
        "            problems += c3bc.passed_params_problems(",
        "            _ = c3bc.passed_params_problems(",
        "E10 non appliqué à l'évaluation",
    ),
    (
        "M34",
        EVAL,
        'trades = cc.require_int(liquidation, "trades", where="evaluation.liquidation", minimum=0)',
        'trades = liquidation.get("trades", 0)',
        ".get( de dictionnaire (discipline de source)",
    ),
    (
        "M35",
        EVAL,
        "PROJECT_ROOT = _ROOT\n",
        'PROJECT_ROOT = _ROOT\nload_dotenv(PROJECT_ROOT / ".env")\n',
        ".env chargé à l'import",
    ),
    (
        "M36",
        EVAL,
        "NET_PNL_IDENTITY_TOL = 1e-6",
        "NET_PNL_IDENTITY_TOL = 1e-5",
        "tolérance hors texte",
    ),
]

#: Mutants équivalents : la sortie est identique par construction ; ils ne peuvent pas rougir.
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
            if (match := re.match(r"(?:FAILED|ERROR) (\S+?)(?: - |$)", line))
        }
    )
    return proc.returncode, tail, red


def main() -> int:
    originals = {rel: (ROOT / rel).read_bytes() for rel in (COMMON, EVAL)}
    digests = {rel: sha256(ROOT / rel) for rel in originals}
    print(f"originaux : {COMMON} {digests[COMMON]} ; {EVAL} {digests[EVAL]}")
    code, tail, _ = run_tests()
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
            code, tail, red = run_tests()
        finally:
            path.write_bytes(originals[rel])
        elapsed = time.monotonic() - started
        restored = sha256(path) == digests[rel]
        verdict = "ROUGE" if code != 0 else ("ÉQUIVALENT" if ident in EQUIVALENT else "SURVIVANT")
        if verdict == "SURVIVANT":
            survivors.append(ident)
        print(
            f"{ident} [{rel.split('/')[-1]}] {what} : {verdict} — {tail} — {elapsed:.1f} s, "
            f"restauré {'oui' if restored else 'NON'}"
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
