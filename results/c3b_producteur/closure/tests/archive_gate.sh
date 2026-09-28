#!/bin/bash
# C3b clôture — archive de la porte § L.5 sur le serveur, vérifiée avant `rm -rf`, lancé par `bash` depuis le dépôt.
# usage : bash archive_gate.sh <AAAAMMJJ>
# Archive ~/archive/c3b_gate_<date>/c3b_gate_server_<date>.tgz : out/ et le pilote, SANS repo/ ni .env. Contrôles
# (codes seulement, rien d'affiché des fichiers) : liste de l'archive == liste des fichiers ; 0 entrée repo/ ou .env ;
# sha256sum -c de l'archive ; extraction et diff -rq ; cmp du pilote ; sha256sum -c des fichiers extraits. Puis
# `rm -rf ~/runs/c3b_gate` seulement si tout vaut 0 (le .env copié part avec le clone). files_all.sha256 et
# files_expected.txt restent au serveur. Sortie : archive_gate.out, rc=0 si archivé, vérifié et nettoyé.
set -o pipefail
set -u

DATE=${1:?date AAAAMMJJ}
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3b_producteur/closure/tests/archive_gate.out
SHAFILE=results/c3b_producteur/closure/gate_L5/c3b_gate_server_$DATE.tgz.sha256

ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102 'bash -s' -- "$DATE" > "$OUT" 2>&1 <<'REMOTE'
set -o pipefail
set -u
DATE=$1
RUN=/home/bruno/runs/c3b_gate
ARC=/home/bruno/archive/c3b_gate_$DATE
TGZ=$ARC/c3b_gate_server_$DATE.tgz
fail=0
chk() { echo "$1=$2"; if [ "$2" != "0" ]; then fail=1; fi; }
echo "# archive_gate — $(date -u +%FT%TZ)"
if [ -e "$TGZ" ]; then echo "archive_exists=1"; echo "remote_rc=1"; exit 1; fi
mkdir -p "$ARC" || exit 1
cd "$RUN" || exit 1
find out run_c3b_gate.sh -type f | LC_ALL=C sort > "$ARC/files_expected.txt"
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
cmp -s "$RUN/run_c3b_gate.sh" "$TMP/run_c3b_gate.sh"
chk cmp_pilot $?
(cd "$TMP" && sha256sum -c --status "$ARC/files_all.sha256")
chk extracted_sha $?
rm -rf "$TMP"
echo "tgz_sha256=$(cut -d' ' -f1 "$TGZ.sha256")"
echo "tgz_size=$(du -h "$TGZ" | cut -f1)"
if [ "$fail" -eq 0 ]; then
  rm -rf "$RUN"
  chk rm_run $?
  echo "rm_at=$(date -u +%FT%TZ)"
  [ ! -e "$RUN" ]
  chk run_absent $?
else
  echo "rm_run=SKIPPED"
fi
echo "remote_rc=$fail"
exit "$fail"
REMOTE
echo "ssh_exit=$?" >> "$OUT"

if grep -qx "remote_rc=0" "$OUT" && grep -qx "ssh_exit=0" "$OUT"; then
  sha=$(grep -E '^tgz_sha256=' "$OUT" | cut -d= -f2)
  printf '%s  %s\n' "$sha" "c3b_gate_server_$DATE.tgz" > "$SHAFILE"
  echo "rc=0" >> "$OUT"
  exit 0
fi
echo "rc=1" >> "$OUT"
exit 1
