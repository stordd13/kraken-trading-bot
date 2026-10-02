#!/bin/bash
# Seconde campagne C3 comptée, famille grid-atr-v4, relance unique — ARCHIVE-PRÉALABLE du run v1 arrêté
# (plans/plan.md § 2), premier pas du run après le GO de lancement : copie de results/c3_campagne_grid/tests/archive.sh,
# corps distant REMOTE identique à l'octet (gardes A3 inchangées, prouvé par archive_dryrun.sh) ; une copie, parce que
# le script v1 écrirait sa sortie dans l'arbre gelé du chantier v1. Lancé par `bash` depuis le dépôt, une seule fois.
# Il conditionne le lancement : le run v2 réutilise ~/runs/c3_campagne_grid/campagne, que launch.sh (mkdir) et le
# preflight (run_dir) refusent tant qu'il existe.
# Avant le corps, une SONDE en LECTURE SEULE (le corps reste intouché) : même périphérique pour out/ du run v1 et
# ~/archive (`stat -c %d`, forme GNU jamais exercée au serveur), forme GNU de `find -perm /222` acceptée ; deux codes
# imprimés, rien d'autre ; un écart → refus, corps non lancé, rien touché.
# Échecs, dits exactement : sonde ou préalables du corps en écart → rien touché ; écart au contrôle de système de
# fichiers du corps → un répertoire d'archive vide reste, et un nouvel essai serait refusé par sa propre garde ; écart
# après le `mv` → out/ déplacé, repo/ en place, script non rejouable (pilote_termine), preflight et lancement bloqués :
# STOP, seul un geste de Bruno débloque. Aucun de ces cas n'écrit au registre ni ne lance le run compté.
# usage : bash archive_prealable.sh   (aucun argument : la date est figée au jour du run v1, 20261001 — libre, le v1
#   n'ayant jamais archivé ; un second appel est refusé par la garde du corps, archive_absente_avant)
# Le run v1 est CONSERVÉ archivé côté serveur, jamais supprimé, jamais versionné, jamais ouvert :
#  - out/ est DÉPLACÉ (`mv`, même système de fichiers, vérifié par code) vers ~/archive/c3_campagne_grid_<date>/out ;
#    aucune copie, aucun tgz, aucun sha calculé, aucun contenu lu ; puis `chmod -R a-w` (non supprimable par erreur) ;
#  - vérification par CODES SEULEMENT : liste des noms avant = après (comparée au serveur, jamais affichée), source
#    absente, aucun fichier inscriptible, aucune entrée repo/ ou .env, témoins status.txt et pilot_exit.txt présents.
#    Ni taille, ni compte de fichiers, ni sha.
#  - la première suppression du chantier v2 (garde A3, décision Q3 du v1 reconduite) : le clone repo/ du run v1 (code
#    au S1 v1 cd4b177, copie du .env du service, copie de CAMPAIGN_UNLOCK), par `rm -rf` en LITTÉRAL ABSOLU sur le
#    répertoire du chantier sous ~/runs, et seulement
#    si (i) tous les codes de l'archive valent 0, (ii) les témoins sont dans l'archive, (iii) aucun composant de chemin
#    nommé exactement `out` ne subsiste sous ce répertoire. Sinon refus, rien supprimé. Motif précisé de (iii) : le
#    glob littéral `*/out*` correspondrait au fichier suivi results/c3_v2_2/outillage_v2_2.md du clone.
# Jamais le répertoire du registre de campagne.
# Sortie : archive_prealable.out (codes de la sonde et du corps, archived_at, rm_at) ; rc=0 ssi sonde à 0, archivé,
# vérifié et clone v1 supprimé.
set -o pipefail
set -u
DATE=20261001
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid_v2/tests/archive_prealable.out
if ! [[ "$DATE" =~ ^[0-9]{8}$ ]]; then echo "date mal formée : $DATE" >&2; exit 2; fi
if [ "$#" -ne 0 ]; then echo "aucun argument : la date est figée (20261001)" >&2; exit 2; fi

# Sonde en lecture seule (plan § 2) : deux codes, rien d'autre.
ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102 'bash -s' > "$OUT" 2>&1 <<'SONDE'
set -u
a=$(stat -c %d /home/bruno/runs/c3_campagne_grid/campagne/out 2> /dev/null)
d=/home/bruno/archive
[ -d "$d" ] || d=/home/bruno
b=$(stat -c %d "$d" 2> /dev/null)
if [ -n "$a" ] && [ "$a" = "$b" ]; then echo "sonde_meme_peripherique=0"; else echo "sonde_meme_peripherique=1"; fi
if find "$d" -maxdepth 0 -perm /222 > /dev/null 2>&1; then echo "sonde_find_perm_gnu=0"; else echo "sonde_find_perm_gnu=1"; fi
SONDE
echo "sonde_ssh_exit=$?" >> "$OUT"
if ! { grep -qx "sonde_meme_peripherique=0" "$OUT" && grep -qx "sonde_find_perm_gnu=0" "$OUT" \
  && grep -qx "sonde_ssh_exit=0" "$OUT"; }; then
  echo "corps=NON_LANCE (sonde en écart : rien touché)" >> "$OUT"
  echo "rc=1" >> "$OUT"
  exit 1
fi

ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102 'bash -s' -- "$DATE" >> "$OUT" 2>&1 <<'REMOTE'
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
