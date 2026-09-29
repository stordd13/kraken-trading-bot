"""C3 v2.2 — extrait du paquet `docs/amendements_c3_v2.2.md` le bloc cité qui suit un en-tête « **Après (…)** »
d'un amendement, sans le préfixe de citation : le texte appliqué au protocole est celui du paquet, au caractère près.

usage (bibliothèque) : ``apres(am, entete)`` → texte ; ``apres(am, entete, n=k)`` pour la k-ième occurrence.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[3] / "docs" / "amendements_c3_v2.2.md"


def section(am: str) -> list[str]:
    lines = PACKAGE.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"## {am} "))
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines)
    )
    return lines[start:end]


def apres(am: str, entete: str, *, n: int = 1) -> str:
    lines = section(am)
    hits = [i for i, line in enumerate(lines) if line.startswith(f"**Après ({entete}")]
    assert len(hits) >= n, f"{am} : en-tête « Après ({entete} » introuvable"
    i = hits[n - 1] + 1
    while i < len(lines) and not lines[i].startswith(">"):
        i += 1
    out: list[str] = []
    while i < len(lines) and lines[i].startswith(">"):
        line = lines[i]
        out.append(line[2:] if line.startswith("> ") else line[1:])
        i += 1
    return "\n".join(out) + "\n"
