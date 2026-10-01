#!/bin/bash
# C3 outillage v2.3, lot 2 (repris du lot 3 v2.2) — archive d'une phase (conf | gate) sur le serveur, vérifiée avant `rm -rf`, lancé par
# `bash` depuis le dépôt (modèle : results/c3b_producteur/closure/tests/archive_gate.sh).
# usage : bash archive.sh <conf|gate> <AAAAMMJJ>
# Archive ~/archive/c3_outillage_<phase>_<date>/c3_outillage_<phase>_server_<date>.tgz : out/ seul (les trois
# exécutions ou les 24 combos, journaux, status, alembic, la copie du pilote out/pilot.sh), SANS repo/ ni .env.
# Contrôles, par CODES SEULEMENT — ni taille, ni listing, ni sha de fichier affichés ; seul le sha de l'archive l'est
# (plan D3) : liste de l'archive == liste des fichiers ; 0 entrée repo/ ou .env ; sha256sum -c de l'archive ; extraction
# et diff -rq ; cmp de la copie du pilote avec le pilote du clone ; sha256sum -c des fichiers extraits. Puis
# `rm -rf ~/runs/c3_outillage_v2_3/<phase>` seulement si tout vaut 0 (le .env copié part avec le clone), et `rmdir` du
# parent s'il est vide. files_all.sha256 et files_expected.txt restent au serveur, jamais affichés.
# Sortie : archive_<phase>.out ; le sha de l'archive dans <dest>/c3_outillage_<phase>_server_<date>.tgz.sha256 ;
# rc=0 ssi archivé, vérifié et nettoyé.
set -o pipefail
set -u
PHASE=${1:?conf ou gate}
DATE=${2:?date AAAAMMJJ}
case "$PHASE" in
  conf) DEST=results/c3_outillage_v2_3/conformite/server
    PILOT=results/c3_outillage_v2_3/conformite/server/run_conformite.sh ;;
  gate) DEST=results/c3_outillage_v2_3/gate_L5
    PILOT=results/c3_outillage_v2_3/gate_L5/run_gate.sh ;;
  *) echo "phase inconnue : $PHASE" >&2; exit 2 ;;
esac
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_outillage_v2_3/tests/archive_${PHASE}.out
NAME=c3_outillage_v2_3_${PHASE}_server_$DATE.tgz
SHAFILE=$DEST/$NAME.sha256

ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102 'bash -s' -- "$PHASE" "$DATE" "$PILOT" > "$OUT" 2>&1 <<'REMOTE'
set -o pipefail
set -u
PHASE=$1
DATE=$2
PILOT=$3
RUN=/home/bruno/runs/c3_outillage_v2_3/$PHASE
ARC=/home/bruno/archive/c3_outillage_v2_3_${PHASE}_$DATE
TGZ=$ARC/c3_outillage_v2_3_${PHASE}_server_$DATE.tgz
fail=0
chk() { echo "$1=$2"; if [ "$2" != "0" ]; then fail=1; fi; }
echo "# archive $PHASE — $(date -u +%FT%TZ)"
if [ -e "$TGZ" ]; then echo "archive_exists=1"; echo "remote_rc=1"; exit 1; fi
mkdir -p "$ARC" || exit 1
cd "$RUN" || exit 1
find out -type f | LC_ALL=C sort > "$ARC/files_expected.txt"
chk files_listed $?
echo "files_count=$(wc -l < "$ARC/files_expected.txt")"
xargs -d '\n' sha256sum < "$ARC/files_expected.txt" > "$ARC/files_all.sha256"
chk files_sha $?
tar -czf "$TGZ" -T "$ARC/files_expected.txt"
chk tar_create $?
(cd "$ARC" && sha256sum "$(basename "$TGZ")" > "$(basename "$TGZ").sha256")
chk tgz_sha $?
tar -tzf "$TGZ" | LC_ALL=C sort | diff -q - "$ARC/files_expected.txt" > /dev/null
chk list_equal $?
n=$(tar -tzf "$TGZ" | grep -cE '(^|/)repo/|(^|/)\.env$')
echo "forbidden_entries=$n"
if [ "$n" = "0" ]; then chk no_repo_no_env 0; else chk no_repo_no_env 1; fi
(cd "$ARC" && sha256sum -c --status "$(basename "$TGZ").sha256")
chk tgz_sha_check $?
TMP=$(mktemp -d)
tar -xzf "$TGZ" -C "$TMP"
chk extract $?
diff -rq "$RUN/out" "$TMP/out" > /dev/null
chk diff_out $?
cmp -s "$RUN/repo/$PILOT" "$TMP/out/pilot.sh"
chk cmp_pilot $?
(cd "$TMP" && sha256sum -c --status "$ARC/files_all.sha256")
chk extracted_sha $?
rm -rf "$TMP"
echo "tgz_sha256=$(cut -d' ' -f1 "$TGZ.sha256")"
if [ "$fail" -eq 0 ]; then
  cd /home/bruno || exit 1
  rm -rf "$RUN"
  chk rm_run $?
  echo "rm_at=$(date -u +%FT%TZ)"
  [ ! -e "$RUN" ]
  chk run_absent $?
  rmdir --ignore-fail-on-non-empty /home/bruno/runs/c3_outillage_v2_3
  echo "parent=$(if [ -e /home/bruno/runs/c3_outillage_v2_3 ]; then echo present; else echo absent; fi)"
else
  echo "rm_run=SKIPPED"
fi
echo "remote_rc=$fail"
exit "$fail"
REMOTE
echo "ssh_exit=$?" >> "$OUT"

if grep -qx "remote_rc=0" "$OUT" && grep -qx "ssh_exit=0" "$OUT"; then
  sha=$(grep -E '^tgz_sha256=' "$OUT" | cut -d= -f2)
  printf '%s  %s\n' "$sha" "$NAME" > "$SHAFILE"
  echo "rc=0" >> "$OUT"
  exit 0
fi
echo "rc=1" >> "$OUT"
exit 1
