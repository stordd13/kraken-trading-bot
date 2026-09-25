"""Extrait d'un journal pytest complet : résumé final, chaque échec tronqué à sa ligne d'erreur, estampilles d'une
fenêtre, sha256 du brut (règle Bruno 25/09 : extrait dans le dépôt, brut archivé hors git).

Usage : python extract_pytest_log.py <brut.log> <début ISO Z> <fin ISO Z> > <extrait.txt>
Les numéros de ligne cités sont ceux du brut ; les codes ANSI sont retirés ; rien n'est reformulé.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import re
import sys

ANSI = re.compile(r"\x1b\[[0-9;]*m")
ISO_Z = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?Z ")
LOCAL = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) \[")
SECTION = re.compile(r"^_{3,} (test\S+) _{3,}$")
NETWORK = re.compile(r"ConnectionDoesNotExistError|Connect call failed|connection was closed")


def stamp_of(line: str, local_offset: timedelta) -> datetime | None:
    """Estampille UTC d'une ligne structlog : ISO ``Z``, ou console locale (``local_offset`` retiré)."""
    if m := ISO_Z.match(line):
        return datetime.fromisoformat(f"{m[1]}T{m[2]}+00:00")
    if m := LOCAL.match(line):
        return datetime.fromisoformat(f"{m[1]}T{m[2]}+00:00") - local_offset
    return None


def main(path: str, lo: str, hi: str) -> int:
    raw = Path(path).read_bytes()
    lines = [ANSI.sub("", s) for s in raw.decode("utf-8", errors="replace").splitlines()]
    t_lo = datetime.fromisoformat(lo.replace("Z", "+00:00")).astimezone(UTC)
    t_hi = datetime.fromisoformat(hi.replace("Z", "+00:00")).astimezone(UTC)
    offset = timedelta(hours=2)  # console structlog du Mac : Europe/Paris, UTC+2 le 2026-09-25
    out: list[str] = [
        f"# Extrait de {Path(path).name} — {len(lines)} lignes, sha256 {hashlib.sha256(raw).hexdigest()}",
        f"# Produit par extract_pytest_log.py {Path(path).name} {lo} {hi} ; numéros = lignes du brut.",
        "",
        "## 1. En-tête du brut",
    ]
    out += [f"{i + 1:>6}: {s}" for i, s in enumerate(lines[:11])]
    failed = [i for i, s in enumerate(lines) if s.startswith("FAILED ")]
    summary = [
        i for i, s in enumerate(lines) if re.search(r"\d+ (passed|failed)", s) and " in " in s
    ]
    tail = [i for i, s in enumerate(lines) if s.startswith("fin ")]
    out += ["", "## 2. Résumé final"]
    out += [f"{i + 1:>6}: {lines[i]}" for i in failed + summary + tail]
    out += ["", "## 3. Chaque échec, tronqué à sa ligne d'erreur réseau"]
    sections = [(i, m[1]) for i, s in enumerate(lines) if (m := SECTION.match(s))]
    for k, (start, name) in enumerate(sections):
        end = sections[k + 1][0] if k + 1 < len(sections) else len(lines)
        body = range(start, end)
        keep = [start]
        keep += [i for i in body if lines[i].startswith("combo = ")][:1]
        keep += [i for i in body if re.match(r"^tests/\S+:\d+: ?$", lines[i])][:1]
        keep += [i for i in body if lines[i].startswith("E ")]
        network = [i for i in body if NETWORK.search(lines[i])]
        keep += network[:1]
        out += [""] + [f"{i + 1:>6}: {lines[i][:400]}" for i in sorted(set(keep))]
        if not network:
            out.append(f"        (aucune ligne d'erreur réseau dans la section {name})")
    out += [
        "",
        f"## 4. Estampilles de {lo} à {hi} (lignes structlog, captures « INFO/ERROR » dupliquées exclues)",
    ]
    before = None
    for i, s in enumerate(lines):
        t = stamp_of(s, offset)
        if t is None:
            continue
        if t < t_lo:
            before = i
        elif t <= t_hi:
            if before is not None:
                out.append(
                    f"{before + 1:>6}: {lines[before][:400]}   <- dernière ligne avant la fenêtre"
                )
                before = None
            out.append(f"{i + 1:>6}: {s[:400]}")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:4]))
