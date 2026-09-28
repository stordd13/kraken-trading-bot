"""Mutants temporaires du lot 1 — chaque mutant est appliqué au fichier src, testé, puis le fichier est restauré et
son sha256 vérifié identique à l'original. Usage : python mutants.py <log>."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path("/Users/stordd/doc/GitHub/kraken-trading-bot")
SRC = ROOT / "src/krakenbot/strategies/grok_grid_atr_adaptive_v4.py"
TEST = "tests/test_strategies/test_grid_v4_decision_timeframes.py"

MUTANTS: dict[str, tuple[str, str]] = {
    "M1 forme fermée bias_1d != 0": (
        "if bear_1d or len(splits) > 1:",
        "if bear_1d or bias_1d != 0:",
    ),
    "M2 1d ssi bear_1d seul": (
        "if bear_1d or len(splits) > 1:",
        "if bear_1d:",
    ),
    "M3 1w inconditionnel": (
        'if pause_1w:\n            timeframes.add("1w")',
        'if True:\n            timeframes.add("1w")',
    ),
    "M4 grid_levels non coercé": (
        'grid_levels = int(params.get("grid_levels", 12))',
        'grid_levels = params.get("grid_levels", 12)',
    ),
    "M5 bool(...) au lieu du refus": (
        "if type(pause_1w) is not bool:\n            raise TypeError(",
        "pause_1w = bool(pause_1w)\n        if False:\n            raise TypeError(",
    ),
    "M6 sortie non triée": (
        "return tuple(sorted(timeframes))",
        "return tuple(sorted(timeframes, reverse=True))",
    ),
    "M7 mode invalide non refusé": (
        'if bear_protection_mode is not None:\n            if bear_protection_mode == "none":\n                pause_1w',
        'if bear_protection_mode in ("none", "1w_only", "1d_only"):\n            if bear_protection_mode == "none":\n                pause_1w',
    ),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    log = Path(sys.argv[1])
    original = SRC.read_bytes()
    original_sha = sha(SRC)
    lines = [f"original sha256 {original_sha}"]
    all_red = True
    try:
        for name, (old, new) in MUTANTS.items():
            text = original.decode()
            count = text.count(old)
            if count != 1:
                lines.append(f"{name}: motif trouvé {count} fois — mutant NON appliqué")
                all_red = False
                continue
            SRC.write_text(text.replace(old, new), encoding="utf-8")
            proc = subprocess.run(
                ["poetry", "run", "pytest", TEST, "-q", "--tb=no", "-p", "no:cacheprovider"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            SRC.write_bytes(original)
            restored = sha(SRC) == original_sha
            summary = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "?"
            killers = sorted(
                {m.group(1) for m in re.finditer(r"^FAILED \S+::(\w+)", proc.stdout, re.M)}
            )
            red = proc.returncode != 0
            all_red &= red and restored
            lines.append(
                f"{name}: exit {proc.returncode} {'ROUGE' if red else 'VERT (mutant survivant)'} — "
                f"{summary} — tué par {killers} — restauré {restored}"
            )
    finally:
        SRC.write_bytes(original)
    lines.append(f"final sha256 {sha(SRC)} identique {sha(SRC) == original_sha}")
    lines.append(f"tous rouges et restaurés : {all_red}")
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if all_red else 1


if __name__ == "__main__":
    raise SystemExit(main())
