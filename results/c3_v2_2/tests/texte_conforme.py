"""C3 v2.2 — le texte appliqué est celui du paquet : chaque bloc cité « **Après (…)** » des amendements se retrouve
dans `docs/protocole_c3.md`, espaces normalisés (seule la mise en page peut différer). Un bloc qui porte « […] »
est vérifié morceau par morceau ; la date d'adoption remplace « <date d'adoption> ». AM-12 (index régénéré) est
vérifié par index_m.sh ; AM-07 est un renvoi.

usage : python texte_conforme.py → une ligne `ok|ABSENT <AM> <en-tête>` par bloc ; code 0 ssi aucun ABSENT.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "docs" / "amendements_c3_v2.2.md"
PROTOCOL = ROOT / "docs" / "protocole_c3.md"
ADOPTION_DATE = "2026-09-29"


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def blocks() -> list[tuple[str, str, str]]:
    lines = PACKAGE.read_text(encoding="utf-8").splitlines()
    out: list[tuple[str, str, str]] = []
    am = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^## (AM-\d\d) ", line)
        if m:
            am = m.group(1)
        elif line.startswith("## "):
            am = ""
        if am and am not in ("AM-07", "AM-12") and line.startswith("**Après"):
            head = line.split("**")[1]
            j = i + 1
            while j < len(lines) and not lines[j].startswith(">") and not lines[j].startswith("**"):
                j += 1
            quoted: list[str] = []
            while j < len(lines) and lines[j].startswith(">"):
                quoted.append(lines[j][2:] if lines[j].startswith("> ") else lines[j][1:])
                j += 1
            if quoted:
                out.append((am, head, "\n".join(quoted)))
            i = j
            continue
        i += 1
    return out


def unquote(text: str) -> str:
    """Retire les marqueurs de citation en début de ligne (en-tête, notes du § A.8) avant la comparaison."""
    return "\n".join(re.sub(r"^>\s?", "", line) for line in text.splitlines())


def main() -> int:
    protocol = norm(unquote(PROTOCOL.read_text(encoding="utf-8")))
    absent = 0
    for am, head, text in blocks():
        text = text.replace("<date d'adoption>", ADOPTION_DATE)
        text = text.replace("*(la suite est inchangée)*", "")
        pieces = [norm(unquote(p)) for p in text.split("[…]") if norm(p)]
        ok = all(p in protocol for p in pieces)
        print(f"{'ok' if ok else 'ABSENT'} {am} {head}")
        absent += 0 if ok else 1
    return 1 if absent else 0


if __name__ == "__main__":
    sys.exit(main())
