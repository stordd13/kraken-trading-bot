#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 — archive du run compté sur le serveur (plans/plan.md § 3, D-archive ;
# réécrit d'après results/c3_racine_registre/tests/archive.sh), lancé par `bash` depuis le dépôt, seulement après un
# fetch et un verify à rc=0 (un écart = STOP : répertoire laissé en place, ni archive ni suppression).
# usage : bash archive.sh <AAAAMMJJ>
# Le run est CONSERVÉ archivé côté serveur, jamais supprimé, jamais versionné, jamais ouvert :
#  - out/ est DÉPLACÉ (`mv`, même système de fichiers, vérifié par code) vers ~/archive/c3_campagne_grid_<date>/out ;
#    aucune copie, aucun tgz, aucun sha calculé, aucun contenu lu ; puis `chmod -R a-w` (non supprimable par erreur) ;
#  - vérification par CODES SEULEMENT : liste des noms avant = après (comparée au serveur, jamais affichée), source
#    absente, aucun fichier inscriptible, aucune entrée repo/ ou .env, témoins status.txt et pilot_exit.txt présents.
#    Ni taille, ni compte de fichiers, ni sha.
#  - la SEULE suppression du chantier (décision Q3, garde A3) : le clone repo/ (code au S1, copie du .env du service,
#    copie de CAMPAIGN_UNLOCK), par `rm -rf` en LITTÉRAL ABSOLU sur le répertoire du chantier sous ~/runs, et seulement
#    si (i) tous les codes de l'archive valent 0, (ii) les témoins sont dans l'archive, (iii) aucun composant de chemin
#    nommé exactement `out` ne subsiste sous ce répertoire. Sinon refus, rien supprimé. Motif précisé de (iii) : le
#    glob littéral `*/out*` correspondrait au fichier suivi results/c3_v2_2/outillage_v2_2.md du clone.
# Jamais le répertoire du registre de campagne.
# Sortie : archive.out (codes, archived_at, rm_at) ; rc=0 ssi archivé, vérifié et clone supprimé.
set -o pipefail
set -u
DATE=${1:?date AAAAMMJJ}
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid/tests/archive.out
if ! [[ "$DATE" =~ ^[0-9]{8}$ ]]; then echo "date mal formée : $DATE" >&2; exit 2; fi

ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102 'bash -s' -- "$DATE" > "$OUT" 2>&1 <<'REMOTE'
set -o pipefail
set -u
DATE=$1
SRC=/home/bruno/runs/c3_campagne_grid/campagne/out
ARC=/home/bruno/archive/c3_campagne_grid_$DATE
fail=0
chk() { echo "$1=$2"; if [ "$2" != "0" ]; then fail=1; fi; }
echo "# archive — $(date -u +%FT%TZ)"
# préalables : pilote terminé, aucune session tmux du chantier, archive du jour absente
[ -f "$SRC/pilot_exit.txt" ]; chk pilote_termine $?
n=$(tmux ls 2> /dev/null | grep -c '^c3-campagne-grid-')
[ "$n" = "0" ]; chk tmux_chantier_absente $?
[ ! -e "$ARC" ]; chk archive_absente_avant $?
if [ "$fail" -ne 0 ]; then echo "remote_rc=1"; exit 1; fi
mkdir -p /home/bruno/archive && mkdir -m 700 "$ARC"; chk mkdir_archive $?
[ "$(stat -c %d "$SRC")" = "$(stat -c %d "$ARC")" ]; chk meme_systeme_de_fichiers $?
if [ "$fail" -ne 0 ]; then echo "remote_rc=1"; exit 1; fi
before=$(cd "$SRC" && find . -mindepth 1 | LC_ALL=C sort)
mv "$SRC" "$ARC/out"; chk deplacement $?
[ ! -e "$SRC" ]; chk source_absente $?
after=$(cd "$ARC/out" && find . -mindepth 1 | LC_ALL=C sort)
[ -n "$before" ] && [ "$before" = "$after" ]; chk liste_des_noms_egale $?
chmod -R a-w "$ARC/out"; chk lecture_seule $?
w=$(find "$ARC/out" -perm /222 | wc -l | tr -d ' ')
[ "$w" = "0" ]; chk aucun_inscriptible $?
f=$(find "$ARC" \( -name repo -o -name .env \) | wc -l | tr -d ' ')
[ "$f" = "0" ]; chk sans_repo_ni_env $?
[ -f "$ARC/out/status.txt" ] && [ -f "$ARC/out/pilot_exit.txt" ]; chk temoins_dans_l_archive $?
echo "archived_at=$(date -u +%FT%TZ)"
# la seule suppression du chantier : le clone, en littéral absolu, sous gardes (A3)
if [ "$fail" -eq 0 ]; then
  o=$(find /home/bruno/runs/c3_campagne_grid \( -name out -o -path '*/out/*' \) | wc -l | tr -d ' ')
  [ "$o" = "0" ]; chk aucun_out_sous_le_repertoire_du_chantier $?
fi
if [ "$fail" -eq 0 ]; then
  rm -rf /home/bruno/runs/c3_campagne_grid
  chk suppression_clone $?
  [ ! -e /home/bruno/runs/c3_campagne_grid ]; chk repertoire_du_chantier_absent $?
  echo "rm_at=$(date -u +%FT%TZ)"
else
  echo "suppression_clone=SKIPPED"
fi
echo "remote_rc=$fail"
exit "$fail"
REMOTE
echo "ssh_exit=$?" >> "$OUT"

if grep -qx "remote_rc=0" "$OUT" && grep -qx "ssh_exit=0" "$OUT"; then
  echo "rc=0" >> "$OUT"
  exit 0
fi
echo "rc=1" >> "$OUT"
exit 1
