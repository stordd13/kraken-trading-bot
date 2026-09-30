#!/bin/bash
# C3 gel v2.3 — le texte appliqué est le texte approuvé (brief § 4.1), aux décisions du STOP du gel près (G-1, G-4, G-6,
# G-7 ; section « Adoption » du paquet). Lancé par `bash` depuis le dépôt. Usage : bash texte_conforme.sh <étiquette>.
# Sortie : texte_conforme_<étiquette>.out. Comparaisons à espaces normalisés (marques de citation `>` retirées) :
#  A. protocole : texte(662c104) + blocs « Après » du paquet + G-1 et G-4 == texte courant ; chaque ancre trouvée une
#     fois ; toute ligne changée tombe dans l'en-tête, le § A.6 ou le § I.1 ;
#  B. CONTRAINTES § 10.1 : phrase « Avant » remplacée par la phrase compagnon, rien d'autre, lignes changées au § 10.1 ;
#  C. paquet adopté contre le draft `agent/amendements_c3_v2_3_draft.md` (hors section « Adoption » ajoutée et section
#     « Empreinte » retirée) : les seuls écarts sont le statut, les deux renvois § A.5 → § A.6 (G-1) et la ligne
#     `engines` corrigée suivie de la ligne `decision_timeframes` (G-6, G-7), égales à celles du protocole ;
#  D. index § M : la régénération (méthode v2.2, results/c3_v2_2/tests/index_m.py) égale la table du texte.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LABEL="${1:?étiquette}"
BASE=662c104ef8cb5a9b5c7fb04452f7af817cb5a87a
DIR=results/c3_v2_3_gel/tests
OUT="$DIR/texte_conforme_${LABEL}.out"
TMP=$(mktemp -d)
{
  echo "# texte_conforme — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base $BASE"
} > "$OUT"
git show "$BASE:docs/protocole_c3.md" > "$TMP/protocole_base.md" || exit 2
git show "$BASE:docs/CONTRAINTES_POST_B4.md" > "$TMP/contraintes_base.md" || exit 2
rc=0
python3 - "$TMP" >> "$OUT" <<'PY' || rc=1
import difflib
import re
import sys
from pathlib import Path

tmp = Path(sys.argv[1])
bad = 0


def say(line: str) -> None:
    print(line)


def check(key: str, ok: bool) -> None:
    global bad
    say(f"{key}={0 if ok else 1}")
    bad |= not ok


def norm(text: str) -> str:
    lines = [re.sub(r"^\s*>\s?", "", line) for line in text.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def replace_once(text: str, old: str, new: str, key: str) -> str:
    n = text.count(old)
    check(f"ancre_{key}_trouvee_une_fois", n == 1)
    return text.replace(old, new, 1)


def first_diff(a: str, b: str) -> str:
    i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return f"premier écart au caractère {i} : attendu «{a[max(0, i - 60):i + 60]}» / lu «{b[max(0, i - 60):i + 60]}»"


def sections_touched(old: list[str], new: list[str]) -> list[str]:
    heads = []
    current = "en-tête"
    for line in new:
        if line.startswith("## ") or line.startswith("### "):
            current = line.split(" —")[0][:40]
        heads.append(current)
    touched = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag != "equal":
            touched.append(heads[min(j1, len(heads) - 1)])
    return touched


pkg = Path("docs/amendements_c3_v2.3.md").read_text(encoding="utf-8")
draft = Path("agent/amendements_c3_v2_3_draft.md").read_text(encoding="utf-8")


def quote_groups(section: str) -> list[list[str]]:
    groups, cur = [], []
    for line in section.splitlines():
        if line.startswith(">"):
            cur.append(line)
        elif cur:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


am01 = pkg.split("## AM-01", 1)[1].split("\n## ", 1)[0]
am02 = pkg.split("## AM-02", 1)[1].split("\n## ", 1)[0]
adoption = pkg.split("## Adoption", 1)[1].split("\n## ", 1)[0]
g = quote_groups(am01)
say(f"am01_citations={len(g)} (attendu 5 : avant 1, avant 2, CONTRAINTES avant, après, CONTRAINTES après)")
check("am01_cinq_citations", len(g) == 5)
avant1, avant2, c_avant, apres, c_apres = ("\n".join(x) for x in g)
bullets: list[list[str]] = []
for line in g[3]:
    if re.match(r"^>\s?- ", line):
        bullets.append([])
    if bullets:
        bullets[-1].append(line)
say(f"apres_puces={len(bullets)} (attendu 5)")
check("apres_cinq_puces", len(bullets) == 5)
apres_123 = norm("\n".join(sum(bullets[:3], [])))
apres_45 = norm("\n".join(sum(bullets[3:], [])))
row_10ter = norm("\n".join(quote_groups(am02)[0]))
phrase = norm(re.search(r"Une phrase sous la table : « (.*?) »", am02, re.S).group(1))
g4 = norm(re.search(r"avant v2\.2 : « (.*?) » \|", adoption).group(1))
g1 = norm(re.search(r"insertion « (.*?) » avant « et le \*\*sha256 de ce document\*\* »", adoption).group(1))

# A. protocole
old_p = (tmp / "protocole_base.md").read_text(encoding="utf-8")
new_p = Path("docs/protocole_c3.md").read_text(encoding="utf-8")
exp = norm(old_p)
anchor = "**Révision v2.2 — amendée le 2026-09-29.**"
exp = replace_once(exp, anchor, f"{g4} {anchor}", "AM00_entete_G4")
tail = "(§ F.2) ; et le **sha256 de ce document**."
exp = replace_once(exp, tail, f"(§ F.2) ; {g1} et le **sha256 de ce document**.", "G1_liste_A6")
exp = replace_once(exp, norm(avant1), apres_123, "AM01_avant1")
exp = replace_once(exp, norm(avant2), apres_45, "AM01_avant2")
row_10bis = norm(next(line for line in old_p.splitlines() if line.startswith("| 10 bis |")))
row_15 = norm(next(line for line in old_p.splitlines() if line.startswith("| 15 |")))
exp = replace_once(exp, row_10bis, f"{row_10bis} {row_10ter}", "AM02_ligne_10ter")
exp = replace_once(exp, row_15, f"{row_15} {phrase}", "AM02_phrase")
ok = norm(new_p) == exp
check("protocole_egal_base_plus_apres", ok)
if not ok:
    say(first_diff(exp, norm(new_p)))
touched = sections_touched(old_p.splitlines(), new_p.splitlines())
say(f"protocole_blocs_changes={len(touched)} sections={sorted(set(touched))}")
check(
    "protocole_changements_localises",
    all(s == "en-tête" or s.startswith(("### A.6 ", "### I.1 ")) for s in touched),
)

# B. CONTRAINTES § 10.1
old_c = (tmp / "contraintes_base.md").read_text(encoding="utf-8")
new_c = Path("docs/CONTRAINTES_POST_B4.md").read_text(encoding="utf-8")
exp_c = replace_once(norm(old_c), norm(c_avant), norm(c_apres), "CONTRAINTES_phrase")
ok = norm(new_c) == exp_c
check("contraintes_egal_base_plus_phrase", ok)
if not ok:
    say(first_diff(exp_c, norm(new_c)))
touched = sections_touched(old_c.splitlines(), new_c.splitlines())
say(f"contraintes_blocs_changes={len(touched)} sections={sorted(set(touched))}")
check("contraintes_changements_au_10_1", set(touched) == {"### 10.1 Clôture de famille"})

# C. paquet adopté contre le draft
a_lines = pkg.splitlines()
i = a_lines.index("## Adoption — 2026-09-30")
j = next(k for k in range(i + 1, len(a_lines)) if a_lines[k].startswith("## "))
adopted = a_lines[:i] + a_lines[j:]
d_lines = draft.splitlines()
e = d_lines.index("## Empreinte du protocole (à remplir au gel)")
drafted = d_lines[: e - 1 if not d_lines[e - 1].strip() else e]
proto_rows = {
    key: norm(next(line for line in new_p.splitlines() if line.strip().startswith(f"| `{key}` |")))
    for key in ("engines", "decision_timeframes")
}
kinds: list[str] = []
for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, drafted, adopted, autojunk=False).get_opcodes():
    if tag == "equal":
        continue
    old, new = drafted[i1:i2], adopted[j1:j2]
    if any("**Statut : PROPOSÉ" in x for x in old) and norm("\n".join(old)).replace(
        "**Statut : PROPOSÉ — draft du 2026-09-30 pour relecture (Bruno), gel ensuite.**",
        "**Statut : ADOPTÉ le 2026-09-30** (Bruno).",
    ) == norm("\n".join(new)):
        kinds.append("statut")
    elif len(old) == len(new) == 1 and old[0].count("§ A.5") == 1 and old[0].replace("§ A.5", "§ A.6") == new[0]:
        kinds.append("renvoi_A5_A6")
    elif (
        len(old) == 1
        and old[0] == ">   | `engines` | le bloc `engines` du manifeste | idem |"
        and len(new) == 2
        and norm(new[0]) == proto_rows["engines"]
        and norm(new[1]) == proto_rows["decision_timeframes"]
    ):
        kinds.append("descripteur_G6_G7")
    else:
        kinds.append("non_attendu")
        say(f"ecart_non_attendu draft l.{i1 + 1}-{i2} / paquet l.{j1 + 1}-{j2}")
say(f"ecarts_au_draft={sorted(kinds)}")
check("paquet_ecarts_attendus_seuls", sorted(kinds) == ["descripteur_G6_G7", "renvoi_A5_A6", "renvoi_A5_A6", "statut"])
check("paquet_sans_section_empreinte_du_draft", "## Empreinte du protocole (à remplir au gel)" not in a_lines)
sys.exit(1 if bad else 0)
PY

# D. index § M
python3 results/c3_v2_2/tests/index_m.py docs/protocole_c3.md > "$TMP/regen.txt" 2>> "$OUT" || rc=1
python3 - > "$TMP/table.txt" <<'PY'
t = open("docs/protocole_c3.md", encoding="utf-8").read().split("## § M.", 1)[1]
print("\n".join(line for line in t.splitlines() if line.startswith("| `")))
PY
if diff -q "$TMP/regen.txt" "$TMP/table.txt" > /dev/null; then
  echo "index_M_regenere_egal=0 ($(wc -l < "$TMP/table.txt" | tr -d ' ') symboles)" >> "$OUT"
else
  echo "index_M_regenere_egal=1" >> "$OUT"; diff "$TMP/regen.txt" "$TMP/table.txt" >> "$OUT"; rc=1
fi
rm -rf "$TMP"
echo "rc=$rc" >> "$OUT"
exit $rc
