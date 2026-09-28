"""Extrait des journaux du run serveur (C3b lot 4a) : événements d'orchestration, lignes hors structlog (pilote,
alembic, sorties des contrôles) et tout avertissement ou erreur.

Même règle que l'extracteur du lot 3 (``prefix_conformite/server/extract_logs.py``), avec les événements du temps 3.
Le brut (``strategy_tick`` et détail des niveaux de la grille) est archivé dans ``~/archive/c3b_lot4a_20260928/`` ;
son sha256 est écrit en tête de l'extrait. Les journaux du chemin sélection ne sont **jamais** extraits : ils restent
dans l'archive, non lus.

Usage : ``python extract_logs.py <brut.log> <extrait.log>``
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys

KEEP = {
    "evaluated",
    "written",
    "database_closed",
    "grid_backtest_started",
    "grid_replay_sequence_built",
    "grid_terminal_liquidation",
    "flat_start_proof",
    "first_fill_at",
    "evaluation_controls",
    "engine_failed",
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
        f"# sha256 du brut {hashlib.sha256(data).hexdigest()} (archivé, ~/archive/c3b_lot4a_20260928/)",
    ]
    out.write_text("\n".join(header + kept) + "\n", encoding="utf-8")
    print(header[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
