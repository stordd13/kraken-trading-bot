#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 — le corps distant d'archive.sh exercé en local dans un monde
# simulé, avant de servir (plans/plan.md § 3 ; A3 : la seule suppression du chantier doit être la plus paranoïaque du
# lot, et ses gardes mordent avant d'être employées). Détail d'exécution, déclaré au STOP 1.
# Le corps est extrait d'archive.sh (entre `<<'REMOTE'` et `REMOTE`) ; dans la copie, des lignes changent, comptées :
#   `/home/bruno/` → `<monde>/home/bruno/` ; `stat -c %d` → `stat -f %d` et `-perm /222` → `-perm +222` (stat et find
#   BSD du poste ; le serveur est GNU) ; `tmux` est un faux tmux du monde.
# Monde : ~/runs/c3_campagne_grid/campagne/{out/…, repo/…} où le clone porte un `.env` simulé et le fichier
# results/c3_v2_2/outillage_v2_2.md (le motif littéral `*/out*` le prendrait ; la garde retenue ne doit pas).
# Cas : conforme (0 : out/ archivé en lecture seule, répertoire du chantier supprimé) ; `out` résiduel dans le clone
# (1 : rien supprimé) ; archive du jour déjà présente (1 : source intacte) ; pilote non terminé (1 : source intacte) ;
# session tmux du chantier encore ouverte (1 : source intacte).
# Sortie : archive_dryrun.out ; rc=0 ssi chaque cas rend son code et laisse le monde attendu.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid/tests/archive_dryrun.out
SRC=results/c3_campagne_grid/tests/archive.sh
T=$(mktemp -d) || exit 2
T=$(cd "$T" && pwd -P) || exit 2
fail=0
: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
log "# archive_dryrun — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)"

mkdir -p "$T/bin"
cat > "$T/bin/tmux" <<'SH'
#!/bin/bash
if [ "${SIM_TMUX:-}" = "ouverte" ]; then echo "c3-campagne-grid-20261001: 1 windows"; exit 0; fi
echo "no server running" >&2
exit 1
SH
chmod +x "$T/bin/tmux"
sed -n "/<<'REMOTE'\$/,/^REMOTE\$/p" "$SRC" | sed '1d;$d' > "$T/body.orig"

# cas <nom> <réglage du monde : conforme | out_residuel | archive_presente | pilote_non_termine | tmux_ouverte>
cas() {
  local name=$1 setup=$2 W=$T/$1
  local R=$W/home/bruno/runs/c3_campagne_grid/campagne A=$W/home/bruno/archive/c3_campagne_grid_20261001
  mkdir -p "$R/out/logs" "$R/out/chain" "$R/repo/results/c3_v2_2" "$W/home/bruno/archive"
  echo "status" > "$R/out/status.txt"
  echo "journal" > "$R/out/logs/chain.log"
  echo "{}" > "$R/out/chain/verdict.json"
  echo "0" > "$R/out/pilot_exit.txt"
  echo "SECRET=sim" > "$R/repo/.env"
  echo "doc" > "$R/repo/results/c3_v2_2/outillage_v2_2.md"
  case "$setup" in
    out_residuel) mkdir -p "$R/repo/out" ;;
    archive_presente) mkdir -p "$A" ;;
    pilote_non_termine) rm -f "$R/out/pilot_exit.txt" ;;
  esac
  sed -e "s|/home/bruno/|$W/home/bruno/|g" -e 's/stat -c %d/stat -f %d/g' -e 's|-perm /222|-perm +222|g' \
    "$T/body.orig" > "$W/body.sh"
  CHANGED=$(diff "$T/body.orig" "$W/body.sh" | grep -c '^>')
  local tm=fermee
  if [ "$setup" = tmux_ouverte ]; then tm=ouverte; fi
  PATH="$T/bin:$PATH" SIM_TMUX=$tm bash "$W/body.sh" 20261001 > "$W/remote.txt" 2>&1
  local r=$?
  local runs=absent arc=absent ro=non
  [ -e "$W/home/bruno/runs/c3_campagne_grid" ] && runs=present
  [ -f "$A/out/status.txt" ] && [ -f "$A/out/pilot_exit.txt" ] && arc=present
  if [ -d "$A/out" ] && [ "$(find "$A/out" -perm +222 | wc -l | tr -d ' ')" = "0" ]; then ro=oui; fi
  local src=absente
  [ -d "$R/out" ] && src=intacte
  log "cas=$name rc=$r lignes_changees=$CHANGED repertoire_chantier=$runs archive=$arc lecture_seule=$ro source=$src"
  grep -E '^(aucun_out_sous_le_repertoire_du_chantier|suppression_clone|archive_absente_avant|pilote_termine|tmux_chantier_absente)=' \
    "$W/remote.txt" | sed "s/^/  $name: /" >> "$OUT"
  RES="$r $runs $arc $ro $src"
  chmod -R u+w "$W" 2> /dev/null
}
attendu() {  # attendu <cas> <rc runs archive lecture_seule source>
  if [ "$RES" != "$2" ]; then fail=1; log "  ECART $1 : obtenu [$RES] attendu [$2]"; fi
}

cas conforme conforme; attendu conforme "0 absent present oui absente"
[ "$CHANGED" -ge 4 ] || fail=1
log "lignes_substituees_conforme=$CHANGED"
cas out_residuel out_residuel; attendu out_residuel "1 present present oui absente"
cas archive_presente archive_presente; attendu archive_presente "1 present absent non intacte"
cas pilote_non_termine pilote_non_termine; attendu pilote_non_termine "1 present absent non intacte"
cas tmux_ouverte tmux_ouverte; attendu tmux_ouverte "1 present absent non intacte"

chmod -R u+w "$T" 2> /dev/null
rm -rf "$T"
[ ! -e "$T" ]; log "temporaire_supprime=$?"
log "rc=$fail"
exit $fail
