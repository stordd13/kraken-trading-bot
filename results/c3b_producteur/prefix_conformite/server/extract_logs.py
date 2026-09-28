"""Extrait des journaux du run serveur (C3b lot 3) : événements d'orchestration et tout avertissement ou erreur.

Le brut (7,6 Mo par exécution, dont 12 752 ``strategy_tick`` et le détail des niveaux de la grille) est archivé dans
``~/archive/c3b_lot3_20260928/`` ; son sha256 est écrit en tête de l'extrait.

Usage : ``python extract_logs.py <brut.log> <extrait.log>``
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys

KEEP = {
    "job_done",
    "written",
    "database_closed",
    "grid_backtest_started",
    "grid_replay_sequence_built",
    "job_failed",
    "jobs_failed",
    "entry_controls",
    "writer_refused",
}
LINE = re.compile(r"^\S+ \S+ \[(?P<level>[a-z]+)\s*\] (?P<event>\S+)")


def main() -> int:
    raw, out = Path(sys.argv[1]), Path(sys.argv[2])
    data = raw.read_bytes()
    kept: list[str] = []
    total = 0
    for line in data.decode("utf-8").splitlines():
        total += 1
        match = LINE.match(line)
        if (
            match is None
            or match["event"] in KEEP
            or match["level"] in {"warning", "error", "critical"}
        ):
            kept.append(line)
    header = [
        f"# extrait de {raw.name} : {len(kept)} lignes gardées sur {total}",
        f"# sha256 du brut {hashlib.sha256(data).hexdigest()} (archivé, ~/archive/c3b_lot3_20260928/)",
    ]
    out.write_text("\n".join(header + kept) + "\n", encoding="utf-8")
    print(header[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
