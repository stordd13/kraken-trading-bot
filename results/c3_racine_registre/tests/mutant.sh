#!/bin/bash
# C3 racine du registre (repris de results/c3_racine_registre/tests/mutant.sh) — vérification d'un témoin vert par mutant temporaire du code : applique au fichier une substitution
# littérale unique (ANCIEN → NOUVEAU), lance le témoin, restaure le fichier par `git checkout`, vérifie le diff
# vide. Le témoin doit ROUGIR sous le mutant et reverdir après restauration. Ajoute le constat à mutants.log.
# usage : bash mutant.sh "<étiquette>" <fichier> <fichier contenant ANCIEN> <fichier contenant NOUVEAU> <nodeid…>
set -o pipefail
set -u
unset VIRTUAL_ENV

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LABEL=${1:?étiquette}
TARGET=${2:?fichier}
OLD=${3:?ancien}
NEW=${4:?nouveau}
shift 4
LOG=results/c3_racine_registre/mutants.log
git diff --quiet -- "$TARGET" || { echo "cible déjà modifiée : ${TARGET}" >&2; exit 2; }
poetry run python - "$TARGET" "$OLD" "$NEW" <<'PY'
import pathlib, sys
target, old, new = (pathlib.Path(a) for a in sys.argv[1:4])
text = target.read_text(encoding="utf-8")
a, b = old.read_text(encoding="utf-8"), new.read_text(encoding="utf-8")
assert text.count(a) == 1, "ancien introuvable ou multiple"
target.write_text(text.replace(a, b), encoding="utf-8")
PY
poetry run pytest -q -p no:cacheprovider "$@" > /dev/null 2>&1
under=$?
git checkout -- "$TARGET"
git diff --quiet -- "$TARGET"
restored=$?
poetry run pytest -q -p no:cacheprovider "$@" > /dev/null 2>&1
after=$?
{
  echo "## ${LABEL} — $(date -u +%FT%TZ) — HEAD $(git rev-parse --short HEAD)"
  echo "cible=${TARGET} témoins=$*"
  echo "sous_mutant_exit=${under} (attendu ≠ 0) restauré_diff_vide=${restored} (attendu 0) après_exit=${after} (attendu 0)"
} >> "$LOG"
[ "$under" -ne 0 ] && [ "$restored" -eq 0 ] && [ "$after" -eq 0 ] && exit 0
exit 1
