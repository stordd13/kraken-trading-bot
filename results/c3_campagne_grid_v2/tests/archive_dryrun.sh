#!/bin/bash
# Seconde campagne C3 comptée, famille grid-atr-v4, relance unique (repris de results/c3_campagne_grid/tests/
# archive_dryrun.sh, étendu) — les deux scripts d'archive exercés en local avant de servir (plans/plan.md § 2 et § 4 ;
# A3 : les suppressions du chantier sont ses gestes les plus paranoïaques, leurs gardes mordent avant d'être employées).
# Détail d'exécution, déclaré au STOP 1. Aucun ssh réel n'est possible : les corps tournent en local dans un monde
# simulé ; les enveloppes tournent sous un FAUX ssh en tête de PATH (résolution vérifiée avant tout appel), avec un HOME
# temporaire et sans agent SSH (un vrai ssh, s'il était atteint, n'aurait ni clé ni hôte connu, en BatchMode).
#  1. Corps REMOTE extraits des trois scripts (v1 archive.sh, v2 archive.sh, v2 archive_prealable.sh) : égaux à l'octet.
#  2. Le corps dans un monde simulé, comme au v1 (lignes changées, comptées : `/home/bruno/` → `<monde>/home/bruno/` ;
#     `stat -c %d` → `stat -f %d` et `-perm /222` → `-perm +222`, formes BSD du poste, le serveur est GNU ; faux tmux) :
#     les cinq cas du v1 à la date 20261001 (conforme → archivé en lecture seule, répertoire du chantier supprimé ; `out`
#     résiduel → rien supprimé ; archive présente, pilote non terminé, tmux ouverte → source intacte), plus conforme_v2 à
#     la date 20261002, l'archive v1 c3_campagne_grid_20261001 préexistante en lecture seule et restée intacte. Le clone
#     simulé porte un .env simulé, results/c3_v2_2/outillage_v2_2.md (le motif `*/out*` le prendrait) et un MARQUEUR à
#     la place de la copie de CAMPAIGN_UNLOCK (aucun fichier de ce nom n'est créé, brief § 3).
#  3. La sonde SONDE d'archive_prealable.sh, extraite telle quelle, `/home/bruno/` → monde, sous un faux stat et un faux
#     find (formes GNU) : même périphérique → 0 et 0 ; périphériques distincts → sonde_meme_peripherique=1 ; find à la
#     BSD (refus de /222) → sonde_find_perm_gnu=1 ; out/ absent → sonde_meme_peripherique=1 ; ~/archive absent → repli
#     sur ~ (0 et 0).
#  4. Les enveloppes, sous faux ssh qui consigne chaque appel et ne contacte rien : archive.sh sans verify_attendu.out →
#     refus local, 0 appel ; verify_attendu.out à 4/11 → refus local, 0 appel ; à 11/11 et rc=0 → 1 appel portant la
#     date ; archive_prealable.sh, sonde en écart → 1 appel, corps non lancé ; sonde à 0 → 2 appels, le second porte la
#     date figée 20261001 ; avec un argument → refus d'usage (2), 0 appel. Les fichiers que ces cas écrivent dans le
#     chantier (archive.out, archive_prealable.out, le verify_attendu.out fabriqué) ne doivent pas exister avant (sinon
#     la partie 4 n'est pas exécutée) ; ils sont recopiés dans la sortie, préfixés, puis supprimés ; l'état
#     `git status` est comparé avant et après.
#  5. A1' (décision de Bruno au GO du plan) : la ligne `jour_lancement` du preflight, extraite telle quelle, refuse le
#     jour 20261001 (l'archive du run v2 y porterait le nom de l'archive v1) et admet 20261002.
# Sortie : archive_dryrun.out ; rc=0 ssi chaque cas rend son code et laisse le monde attendu.
# Env : DRYRUN_OUT (sortie, défaut tests/archive_dryrun.out) — employé par mutants_archive.sh.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=${DRYRUN_OUT:-results/c3_campagne_grid_v2/tests/archive_dryrun.out}
V1=results/c3_campagne_grid/tests/archive.sh
ARCH=results/c3_campagne_grid_v2/tests/archive.sh
PREA=results/c3_campagne_grid_v2/tests/archive_prealable.sh
T=$(mktemp -d) || exit 2
T=$(cd "$T" && pwd -P) || exit 2
fail=0
: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
log "# archive_dryrun — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)"

# --- 1. corps REMOTE égaux à l'octet --------------------------------------------------------------------------------
remote_body() { sed -n "/<<'REMOTE'\$/,/^REMOTE\$/p" "$1" | sed '1d;$d'; }
remote_body "$V1" > "$T/body.v1"
remote_body "$ARCH" > "$T/body.archive"
remote_body "$PREA" > "$T/body.prealable"
n=$(wc -l < "$T/body.v1" | tr -d ' ')
cmp -s "$T/body.v1" "$T/body.archive"; a=$?
cmp -s "$T/body.v1" "$T/body.prealable"; p=$?
log "corps_v1_lignes=$n corps_archive_v2_egal_v1=$a corps_prealable_egal_v1=$p"
{ [ "$n" -gt 0 ] && [ "$a" = "0" ] && [ "$p" = "0" ]; } || fail=1

# --- 2. le corps dans un monde simulé -------------------------------------------------------------------------------
mkdir -p "$T/bin"
cat > "$T/bin/tmux" <<'SH'
#!/bin/bash
if [ "${SIM_TMUX:-}" = "ouverte" ]; then echo "c3-campagne-grid-20261002: 1 windows"; exit 0; fi
echo "no server running" >&2
exit 1
SH
chmod +x "$T/bin/tmux"
snapshot() { (cd "$1" && find . -exec stat -f '%N %p %z %m' {} \; | LC_ALL=C sort); }   # noms, modes, tailles, dates

# cas <nom> <réglage : conforme | out_residuel | archive_presente | pilote_non_termine | tmux_ouverte | conforme_v2> <date>
cas() {
  local name=$1 setup=$2 date=$3 W=$T/$1
  local R=$W/home/bruno/runs/c3_campagne_grid/campagne A=$W/home/bruno/archive/c3_campagne_grid_$3
  local A1=$W/home/bruno/archive/c3_campagne_grid_20261001
  mkdir -p "$R/out/logs" "$R/out/chain" "$R/repo/results/c3_v2_2" "$R/repo/results/c3b_producteur" "$W/home/bruno/archive"
  echo "status" > "$R/out/status.txt"
  echo "journal" > "$R/out/logs/chain.log"
  echo "{}" > "$R/out/chain/verdict.json"
  echo "0" > "$R/out/pilot_exit.txt"
  echo "SECRET=sim" > "$R/repo/.env"
  echo "doc" > "$R/repo/results/c3_v2_2/outillage_v2_2.md"
  : > "$R/repo/results/c3b_producteur/SIM_MARQUEUR_UNLOCK"
  case "$setup" in
    out_residuel) mkdir -p "$R/repo/out" ;;
    archive_presente) mkdir -p "$A" ;;
    pilote_non_termine) rm -f "$R/out/pilot_exit.txt" ;;
    conforme_v2)
      mkdir -p "$A1/out"
      echo "status v1" > "$A1/out/status.txt"
      echo "1" > "$A1/out/pilot_exit.txt"
      chmod -R a-w "$A1/out"
      snapshot "$A1" > "$W/v1_avant.txt"
      ;;
  esac
  sed -e "s|/home/bruno/|$W/home/bruno/|g" -e 's/stat -c %d/stat -f %d/g' -e 's|-perm /222|-perm +222|g' \
    "$T/body.v1" > "$W/body.sh"
  CHANGED=$(diff "$T/body.v1" "$W/body.sh" | grep -c '^>')
  local tm=fermee
  if [ "$setup" = tmux_ouverte ]; then tm=ouverte; fi
  PATH="$T/bin:$PATH" SIM_TMUX=$tm bash "$W/body.sh" "$date" > "$W/remote.txt" 2>&1
  local r=$?
  local runs=absent arc=absent ro=non
  [ -e "$W/home/bruno/runs/c3_campagne_grid" ] && runs=present
  [ -f "$A/out/status.txt" ] && [ -f "$A/out/pilot_exit.txt" ] && arc=present
  if [ -d "$A/out" ] && [ "$(find "$A/out" -perm +222 | wc -l | tr -d ' ')" = "0" ]; then ro=oui; fi
  local src=absente
  [ -d "$R/out" ] && src=intacte
  log "cas=$name date=$date rc=$r lignes_changees=$CHANGED repertoire_chantier=$runs archive=$arc lecture_seule=$ro source=$src"
  grep -E '^(aucun_out_sous_le_repertoire_du_chantier|suppression_clone|archive_absente_avant|pilote_termine|tmux_chantier_absente|meme_systeme_de_fichiers)=' \
    "$W/remote.txt" | sed "s/^/  $name: /" >> "$OUT"
  RES="$r $runs $arc $ro $src"
  if [ "$setup" = conforme_v2 ]; then
    snapshot "$A1" > "$W/v1_apres.txt"
    cmp -s "$W/v1_avant.txt" "$W/v1_apres.txt"; local i=$?
    log "  $name: archive_v1_intacte=$i"
    [ "$i" = "0" ] || fail=1
  fi
  chmod -R u+w "$W" 2> /dev/null
}
attendu() {  # attendu <cas> <rc runs archive lecture_seule source>
  if [ "$RES" != "$2" ]; then fail=1; log "  ECART $1 : obtenu [$RES] attendu [$2]"; fi
}

cas conforme conforme 20261001; attendu conforme "0 absent present oui absente"
[ "$CHANGED" -ge 4 ] || fail=1
log "lignes_substituees_conforme=$CHANGED"
cas out_residuel out_residuel 20261001; attendu out_residuel "1 present present oui absente"
cas archive_presente archive_presente 20261001; attendu archive_presente "1 present absent non intacte"
cas pilote_non_termine pilote_non_termine 20261001; attendu pilote_non_termine "1 present absent non intacte"
cas tmux_ouverte tmux_ouverte 20261001; attendu tmux_ouverte "1 present absent non intacte"
cas conforme_v2 conforme_v2 20261002; attendu conforme_v2 "0 absent present oui absente"

# --- 3. la sonde d'archive_prealable.sh -----------------------------------------------------------------------------
sed -n "/<<'SONDE'\$/,/^SONDE\$/p" "$PREA" | sed '1d;$d' > "$T/sonde.orig"
mkdir -p "$T/gnu"
cat > "$T/gnu/stat" <<'SH'
#!/bin/bash
# faux stat GNU : `stat -c %d <chemin>` seulement ; périphérique 1, ou 2 pour ~/archive et ~ si SIM_DEV=distincts
[ "$1" = "-c" ] && [ "$2" = "%d" ] || exit 1
[ -e "$3" ] || exit 1
case "$3" in
  */home/bruno/archive | */home/bruno) if [ "${SIM_DEV:-}" = distincts ]; then echo 2; else echo 1; fi ;;
  *) echo 1 ;;
esac
SH
cat > "$T/gnu/find" <<'SH'
#!/bin/bash
# faux find : accepte la forme GNU `-perm /222`, sauf SIM_FIND=bsd (refus, comme le find BSD)
if [ "${SIM_FIND:-}" = bsd ]; then echo "find: -perm: /222: illegal mode string" >&2; exit 1; fi
[ -e "$1" ] || exit 1
exit 0
SH
chmod +x "$T/gnu/stat" "$T/gnu/find"
sonde() {  # sonde <nom> <réglage : ok | distincts | bsd | out_absent | sans_archive> <attendu : deux codes>
  local W=$T/sonde_$1
  mkdir -p "$W/home/bruno/runs/c3_campagne_grid/campagne/out" "$W/home/bruno/archive"
  case "$2" in
    out_absent) rmdir "$W/home/bruno/runs/c3_campagne_grid/campagne/out" ;;
    sans_archive) rmdir "$W/home/bruno/archive" ;;
  esac
  sed -e "s|/home/bruno/|$W/home/bruno/|g" -e "s|=/home/bruno\$|=$W/home/bruno|" "$T/sonde.orig" > "$W/sonde.sh"
  local dev="" fnd=""
  [ "$2" = distincts ] && dev=distincts
  [ "$2" = bsd ] && fnd=bsd
  PATH="$T/gnu:$PATH" SIM_DEV=$dev SIM_FIND=$fnd bash "$W/sonde.sh" > "$W/sortie.txt" 2>&1
  local r=$? got
  got=$(tr '\n' ' ' < "$W/sortie.txt" | sed 's/ $//')
  log "sonde=$1 rc=$r sortie=[$got]"
  if [ "$got" != "$3" ] || [ "$r" != "0" ]; then fail=1; log "  ECART sonde $1 : attendu [$3]"; fi
}
sonde ok ok "sonde_meme_peripherique=0 sonde_find_perm_gnu=0"
sonde peripheriques_distincts distincts "sonde_meme_peripherique=1 sonde_find_perm_gnu=0"
sonde find_bsd bsd "sonde_meme_peripherique=0 sonde_find_perm_gnu=1"
sonde out_absent out_absent "sonde_meme_peripherique=1 sonde_find_perm_gnu=0"
sonde sans_archive sans_archive "sonde_meme_peripherique=0 sonde_find_perm_gnu=0"

# --- 4. les enveloppes, sous faux ssh -------------------------------------------------------------------------------
AOUT=results/c3_campagne_grid_v2/tests/archive.out
POUT=results/c3_campagne_grid_v2/tests/archive_prealable.out
VOUT=results/c3_campagne_grid_v2/server/verify_attendu.out
mkdir -p "$T/fakessh" "$T/home"
cat > "$T/fakessh/ssh" <<'SH'
#!/bin/bash
# faux ssh : consigne l'appel (arguments), lit et jette l'entrée standard, ne contacte rien
echo "$*" >> "$SIM_SSH_LOG"
cat > /dev/null
n=$(wc -l < "$SIM_SSH_LOG" | tr -d ' ')
case "${SIM_SSH_MODE:-}" in
  sonde_ok) if [ "$n" = "1" ]; then printf 'sonde_meme_peripherique=0\nsonde_find_perm_gnu=0\n'; exit 0; fi ;;
  sonde_ko) if [ "$n" = "1" ]; then printf 'sonde_meme_peripherique=1\nsonde_find_perm_gnu=0\n'; exit 0; fi ;;
esac
exit 97
SH
chmod +x "$T/fakessh/ssh"
resolved=$(PATH="$T/fakessh:$PATH" command -v ssh)
if [ "$resolved" != "$T/fakessh/ssh" ]; then
  log "faux_ssh_resolu=1 (partie 4 non exécutée)"; fail=1
elif [ -e "$AOUT" ] || [ -e "$POUT" ] || [ -e "$VOUT" ]; then
  log "sorties_du_chantier_deja_presentes=1 (partie 4 non exécutée, rien écrasé)"; fail=1
else
  log "faux_ssh_resolu=0 sorties_du_chantier_absentes_avant=0"
  BEFORE=$(git status --porcelain --untracked-files=all | grep -v " $OUT\$")
  # enveloppe <nom> <mode du faux ssh> <contenu de verify_attendu.out ou -> <attendu rc> <attendu appels> <motif du
  #   dernier appel ou -> <script> [arguments…]
  enveloppe() {
    local name=$1 mode=$2 vcontent=$3 want_rc=$4 want_calls=$5 want_last=$6 script=$7
    shift 7
    local L=$T/ssh_$name.log
    : > "$L"
    if [ "$vcontent" != "-" ]; then printf '%b' "$vcontent" > "$VOUT"; fi
    env -u SSH_AUTH_SOCK HOME="$T/home" PATH="$T/fakessh:$PATH" SIM_SSH_LOG="$L" SIM_SSH_MODE="$mode" \
      bash "$script" "$@" > "$T/env_$name.txt" 2>&1
    local r=$? calls last ok=0
    calls=$(wc -l < "$L" | tr -d ' ')
    last=$(tail -n 1 "$L")
    log "enveloppe=$name rc=$r appels_ssh=$calls"
    for f in "$AOUT" "$POUT"; do
      if [ -f "$f" ]; then sed "s/^/  $name: $(basename "$f"): /" "$f" >> "$OUT"; rm -f "$f"; fi
    done
    rm -f "$VOUT"
    [ "$r" = "$want_rc" ] || ok=1
    [ "$calls" = "$want_calls" ] || ok=1
    if [ "$want_last" != "-" ]; then
      case "$last" in *"$want_last"*) ;; *) ok=1 ;; esac
      log "  $name: dernier_appel_porte=[$want_last] $([ "$ok" = 0 ] && echo oui || echo NON)"
    fi
    if [ "$ok" != "0" ]; then fail=1; log "  ECART enveloppe $name : attendu rc=$want_rc appels=$want_calls"; fi
  }
  enveloppe archive_sans_verify - - 1 0 - "$ARCH" 20261002
  enveloppe archive_verify_4_sur_11 - "4/11 items vérifiables tenus\nrc=1\n" 1 0 - "$ARCH" 20261002
  enveloppe archive_verify_11_sur_11 - "11/11 items vérifiables tenus\nrc=0\n" 1 1 "-- 20261002" "$ARCH" 20261002
  enveloppe prealable_sonde_en_ecart sonde_ko - 1 1 - "$PREA"
  enveloppe prealable_sonde_a_0 sonde_ok - 1 2 "-- 20261001" "$PREA"
  enveloppe prealable_avec_argument - - 2 0 - "$PREA" 20261002
  AFTER=$(git status --porcelain --untracked-files=all | grep -v " $OUT\$")
  if [ "$AFTER" = "$BEFORE" ]; then log "etat_git_restaure=0"; else log "etat_git_restaure=1"; fail=1; fi
fi

# --- 5. A1' : la ligne jour_lancement du preflight -----------------------------------------------------------------
grep -E '^if \[ "\$DAY" -ge 20261002 \]; then' results/c3_campagne_grid_v2/tests/preflight.sh > "$T/a1.sh"
n=$(wc -l < "$T/a1.sh" | tr -d ' ')
log "a1_lignes_extraites=$n attendu=1"
[ "$n" = "1" ] || fail=1
jour() {  # jour <AAAAMMJJ> <attendu : sortie> <attendu : ok>
  local got
  got=$(DAY=$1 bash -c 'set -u; ok=0; . "$0"; echo "ok=$ok"' "$T/a1.sh" | tr '\n' ' ' | sed 's/ $//')
  log "a1 jour=$1 sortie=[$got]"
  [ "$got" = "$2 ok=$3" ] || { fail=1; log "  ECART a1 $1 : attendu [$2 ok=$3]"; }
}
jour 20261001 "jour_lancement=REFUSE 20261001" 1
jour 20261002 "jour_lancement=20261002" 0

chmod -R u+w "$T" 2> /dev/null
rm -rf "$T"
[ ! -e "$T" ]; log "temporaire_supprime=$?"
log "rc=$fail"
exit $fail
