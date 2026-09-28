"""Mutants temporaires du lot 2 — chaque mutant est appliqué, testé, puis chaque fichier touché est restauré et
son sha256 vérifié identique à l'original. Usage : python mutants.py <log>.

Un mutant est une liste de remplacements ``(fichier, ancien, nouveau)`` ; chaque ``ancien`` doit apparaître
exactement une fois, sinon le mutant est déclaré NON appliqué et le run échoue. Les fragments de code sont écrits
sur une seule ligne (``\\n`` échappés) : ce fichier est lui-même lu par le test de définition unique.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
COMMON = "scripts/audit/_common.py"
DB = "scripts/audit/_db.py"
C3_COMMON = "scripts/audit/c3_common.py"
WARMUP = "scripts/audit/warmup_at.py"
R1W = "scripts/audit/reconstruct_1w.py"
FX = "tests/test_scripts/test_c3_common.py"
VERDICT = "tests/test_scripts/test_c3_verdict.py"

UNIT = ["tests/test_scripts/test_audit_common.py"]
C3 = [
    "tests/test_scripts/test_c3_continuity.py",
    "tests/test_scripts/test_c3_verdict.py",
]

Edit = tuple[str, str, str]
MUTANTS: list[tuple[str, list[Edit], list[str]]] = [
    (
        "M1 sous-type de float accepté (isinstance)",
        [(COMMON, "    if kind is float:\n", "    if isinstance(value, float):\n")],
        UNIT,
    ),
    (
        "M2 parcours retiré, default=str rétabli",
        [
            (COMMON, '    _check(payload, "")\n    encoded = (', "    encoded = ("),
            (COMMON, "default=_refuse,", "default=str,"),
        ],
        UNIT,
    ),
    (
        "M3 flottant non fini accepté (allow_nan=True)",
        [
            (COMMON, "        if not math.isfinite(value):\n", "        if False:\n"),
            (COMMON, "allow_nan=False,", "allow_nan=True,"),
        ],
        UNIT,
    ),
    (
        "M4 index de liste omis du chemin",
        [(COMMON, '_check(item, f"{path}[{index}]")', "_check(item, path)")],
        UNIT,
    ),
    (
        "M5 clé non str acceptée",
        [(COMMON, "            if type(key) is not str:\n", "            if False:\n")],
        UNIT,
    ),
    ("M6a indent=4", [(COMMON, "indent=2,", "indent=4,")], UNIT),
    ("M6b sort_keys=False", [(COMMON, "sort_keys=True,", "sort_keys=False,")], UNIT),
    ("M6c sans saut de ligne final", [(COMMON, '        + "\\n"\n', '        + ""\n')], UNIT),
    ("M6d ensure_ascii=True", [(COMMON, "ensure_ascii=False,", "ensure_ascii=True,")], UNIT),
    (
        "M7 répertoire créé avant la validation",
        [
            (
                COMMON,
                '    _check(payload, "")\n    encoded = (',
                '    Path(path).parent.mkdir(parents=True, exist_ok=True)\n    _check(payload, "")\n    encoded = (',
            )
        ],
        UNIT,
    ),
    (
        "M8 c3_common.write_json revient au writer du rejeu",
        [(C3_COMMON, "write_json = _common.write_json_strict", "write_json = rc.write_json")],
        UNIT,
    ),
    (
        "M9 git_provenance hache un chemin constant",
        [(COMMON, "    script = root / script_relpath\n", '    script = root / "scripts/a.py"\n')],
        UNIT,
    ),
    (
        "M10a tracked_tree_clean forcé vrai",
        [
            (
                COMMON,
                '        ).stdout.strip()\n        == "",',
                "        ).stdout.strip()\n        is not None,",
            )
        ],
        UNIT,
    ),
    (
        "M10b script_tracked forcé vrai",
        [(COMMON, "script_relpath).returncode == 0,", "script_relpath).returncode >= 0,")],
        UNIT,
    ),
    (
        "M11 ReadOnlyDatabaseManager sans lecture seule",
        [
            (
                DB,
                'url, connect_args={"server_settings": {"default_transaction_read_only": "on"}}',
                "url",
            )
        ],
        UNIT,
    ),
    (
        "M12 _common importe _db",
        [(COMMON, "import subprocess\n", "import subprocess\n\nimport _db  # noqa: F401\n")],
        UNIT,
    ),
    (
        "M13 warmup_at passe le chemin d'un autre script",
        [
            (
                WARMUP,
                "provenance = git_provenance(SCRIPT_RELPATH)",
                'provenance = git_provenance("scripts/audit/reconstruct_1w.py")',
            )
        ],
        UNIT,
    ),
    (
        "M14 copie locale réintroduite dans reconstruct_1w",
        [
            (
                R1W,
                'if __name__ == "__main__":',
                'def write_json_strict(path: Any, payload: Any) -> str:\n    return ""\n\n\nif __name__ == "__main__":',
            )
        ],
        UNIT,
    ),
    (
        "M15 fixtures témoin en np.float64 (tests unitaires)",
        [
            (
                FX,
                "return np.random.default_rng(11).normal(0.0005, 0.002, n).tolist()",
                "return list(np.random.default_rng(11).normal(0.0005, 0.002, n))",
            )
        ],
        UNIT,
    ),
    (
        "M16 fixtures témoin en np.float64 (tests C3 qui écrivent une évaluation)",
        [
            (
                FX,
                "return np.random.default_rng(11).normal(0.0005, 0.002, n).tolist()",
                "return list(np.random.default_rng(11).normal(0.0005, 0.002, n))",
            )
        ],
        C3,
    ),
    (
        "M17 site adverse :796 par le writer strict (tests C3)",
        [
            (
                VERDICT,
                'rc.write_json(paths["evaluation"], artifacts["evaluation"])',
                'cc.write_json(paths["evaluation"], artifacts["evaluation"])',
            )
        ],
        C3,
    ),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(tests: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["poetry", "run", "pytest", *tests, "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=None,
    )


def main() -> int:
    log = Path(sys.argv[1])
    touched = sorted({relpath for _, edits, _ in MUTANTS for relpath, _, _ in edits})
    originals = {relpath: (ROOT / relpath).read_bytes() for relpath in touched}
    shas = {relpath: sha(ROOT / relpath) for relpath in touched}
    lines = [f"original sha256 {shas[relpath]} {relpath}" for relpath in touched]
    all_red = True
    try:
        for name, edits, tests in MUTANTS:
            texts = {relpath: originals[relpath].decode() for relpath, _, _ in edits}
            applied = True
            for relpath, old, new in edits:
                count = texts[relpath].count(old)
                if count != 1:
                    lines.append(
                        f"{name}: motif trouvé {count} fois dans {relpath} — mutant NON appliqué"
                    )
                    applied = False
                    break
                texts[relpath] = texts[relpath].replace(old, new)
            if not applied:
                all_red = False
                continue
            for relpath, text in texts.items():
                (ROOT / relpath).write_text(text, encoding="utf-8")
            proc = run(tests)
            for relpath in texts:
                (ROOT / relpath).write_bytes(originals[relpath])
            restored = all(sha(ROOT / relpath) == shas[relpath] for relpath in texts)
            summary = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "?"
            killers = sorted(
                {
                    m.group(1)
                    for m in re.finditer(r"^(?:FAILED|ERROR) \S+?::(\w+)", proc.stdout, re.M)
                }
            )
            shown = killers if len(killers) <= 8 else [*killers[:8], f"… {len(killers)} fonctions"]
            red = proc.returncode != 0
            all_red &= red and restored
            lines.append(
                f"{name}: exit {proc.returncode} {'ROUGE' if red else 'VERT (mutant survivant)'} — "
                f"{summary} — tué par {shown} — restauré {restored}"
            )
    finally:
        for relpath, data in originals.items():
            (ROOT / relpath).write_bytes(data)
    for relpath in touched:
        lines.append(
            f"final sha256 {sha(ROOT / relpath)} identique {sha(ROOT / relpath) == shas[relpath]} {relpath}"
        )
    lines.append(f"tous rouges et restaurés : {all_red}")
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if all_red else 1


if __name__ == "__main__":
    raise SystemExit(main())
