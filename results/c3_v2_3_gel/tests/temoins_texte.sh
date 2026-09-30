#!/bin/bash
# C3 gel v2.3 — texte_conforme.sh mord-il ? Quatre mutants temporaires, un par comparaison, chacun doit faire sortir
# texte_conforme.sh en rc=1 sur la clé visée ; chaque fichier est restauré depuis sa copie et son sha256 revérifié.
# Lancé par `bash` depuis le dépôt, jamais pendant la suite. Sortie : temoins_texte.out ; rc=0 ssi les quatre mutants
# sont vus et l'arbre est rendu identique.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
DIR=results/c3_v2_3_gel/tests
OUT="$DIR/temoins_texte.out"
TMP=$(mktemp -d)
{
  echo "# temoins_texte — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
} > "$OUT"
FILES=(docs/protocole_c3.md docs/amendements_c3_v2.3.md docs/CONTRAINTES_POST_B4.md)
for f in "${FILES[@]}"; do cp "$f" "$TMP/$(basename "$f")"; done
before=$(shasum -a 256 "${FILES[@]}")
rc=0

mutant() {  # $1 nom, $2 fichier, $3 chaîne lue, $4 chaîne écrite, $5 clé qui doit passer à 1
  python3 - "$2" "$3" "$4" <<'PY'
import sys
path, old, new = sys.argv[1:4]
text = open(path, encoding="utf-8").read()
assert text.count(old) >= 1, f"mutant inapplicable : {old!r} absent de {path}"
open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
PY
  bash "$DIR/texte_conforme.sh" temoin > /dev/null 2>&1; r=$?
  cp "$TMP/$(basename "$2")" "$2"
  if [ "$r" -eq 1 ] && grep -q "^$5=1$" "$DIR/texte_conforme_temoin.out"; then
    echo "mutant $1 vu=0 (texte_conforme rc=$r, $5=1)" >> "$OUT"
  else
    echo "mutant $1 vu=1 (texte_conforme rc=$r) — NON VU" >> "$OUT"; rc=1
  fi
}

mutant apres_AM01_altere docs/protocole_c3.md "**brute-forçable par construction**" "**brute-forçable**" \
  protocole_egal_base_plus_apres
mutant hors_zone_B2 docs/protocole_c3.md "### B.2 Clause 1 — le portefeuille évalué démarre à plat" \
  "### B.2 Clause 1 — le portefeuille évalué démarre bien à plat" protocole_changements_localises
mutant corps_AM02_paquet docs/amendements_c3_v2.3.md "Le texte
suit le code, comportement inchangé" "Le texte
suit le code, comportement réputé inchangé" paquet_ecarts_attendus_seuls
mutant contraintes_10_2 docs/CONTRAINTES_POST_B4.md "Kill-switch live" "Kill-switch réel" \
  contraintes_egal_base_plus_phrase

rm -f "$DIR/texte_conforme_temoin.out"
after=$(shasum -a 256 "${FILES[@]}")
if [ "$before" = "$after" ]; then echo "arbre_restaure=0" >> "$OUT"; else echo "arbre_restaure=1" >> "$OUT"; rc=1; fi
rm -rf "$TMP"
echo "rc=$rc" >> "$OUT"
exit $rc
