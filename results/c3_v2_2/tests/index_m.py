"""C3 v2.2, AM-12 — régénère la table « symbole → sites de référence » du § M depuis le texte du protocole.

Méthode : le texte est découpé en sections (titres `### X.Y` et `## § X.`) ; les sections d'historique
d'amendements (avant `## § 0.`) et le § M lui-même sont exclus ; un symbole est cité par une section s'il y
apparaît comme mot entier. Le site de définition est lu dans la table existante du § M ; les sites de référence
sont toutes les autres sections qui citent le symbole, dans l'ordre du document.

usage : python index_m.py <protocole.md>   → imprime les lignes de table, et `VIDE <symbole>` pour toute colonne
de références vide (règle de lecture du § M : une porte que rien n'applique).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HEAD = re.compile(r"^(?:### (?P<sub>[0-9A-Z]+(?:\.[0-9]+)?(?: bis)?) |## § (?P<top>[0-9A-Z]+)\. )")
ROW = re.compile(r"^\| `(?P<sym>[^`]+)` \| (?P<site>§ [^|]+?) \| (?P<refs>[^|]*)\|$")


def sections(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    current: str | None = None
    buf: list[str] = []
    started = False
    for line in text.splitlines():
        m = HEAD.match(line)
        if line.startswith("## § 0."):
            started = True
        if m and started:
            if current is not None:
                out.append((current, "\n".join(buf)))
            current = "§ " + (m.group("sub") or m.group("top"))
            buf = []
            continue
        if started and current is not None:
            buf.append(line)
    if current is not None:
        out.append((current, "\n".join(buf)))
    return [(s, body) for s, body in out if s != "§ M"]


def main(path: str) -> int:
    text = Path(path).read_text(encoding="utf-8")
    secs = sections(text)
    order = [s for s, _ in secs]
    m_block = text.split("## § M.", 1)[1]
    rows = [ROW.match(line) for line in m_block.splitlines()]
    rows = [r for r in rows if r is not None]
    empty = 0
    for r in rows:
        sym, site = r.group("sym"), r.group("site").strip()
        pat = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(sym)}(?![A-Za-z0-9_])")
        refs: list[str] = []
        for s, body in secs:
            base = s.split(" bis")[0]
            if base == site or s == site:
                continue
            if pat.search(body) and s not in refs:
                refs.append(s)
        refs.sort(key=order.index)
        print(f"| `{sym}` | {site} | {', '.join(refs)} |")
        if not refs:
            print(f"VIDE {sym}")
            empty += 1
    return 1 if empty else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
