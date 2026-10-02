#!/bin/bash
# Seconde campagne C3 comptée, famille grid-atr-v4, relance unique (repris de results/c3_campagne_grid/tests/pilot_dryrun.sh) —
# le pilote du run compté exercé en local dans un monde simulé, sans base, sans serveur, sans registre réel, avant
# S1 (plans/plan.md § 6) : une panne du pilote se voit ici, pas sur le serveur.
#
# Monde simulé, dans un répertoire temporaire hors du dépôt, supprimé ensuite :
#  - un clone local du dépôt (HEAD courant), où le pilote et le manifeste de l'arbre de travail sont committés dans
#    le clone seulement ; dans la copie du pilote, SIX lignes changent, comptées : SERVICE, PY, RUN (chemins du monde
#    simulé), les deux lignes `--registry` (un registre simulé du monde, jamais le registre de campagne, dont le chemin
#    est construit ici), et la ligne UNLOCK= qui pointe un MARQUEUR DE SIMULATION — aucun fichier nommé
#    CAMPAIGN_UNLOCK n'est créé, même temporairement (brief § 3) ;
#  - un « service » : dépôt git jetable portant poetry.lock et pyproject.toml de HEAD ;
#  - un faux interpréteur (Python, stdlib) : `-V`, `-c import krakenbot`, `-m alembic current`, `-` (heredoc, exécuté
#    pour de vrai), et les sept scripts ; l'ancrage simulé inscrit au registre simulé (new_entry vrai s'il est neuf),
#    la chaîne simulée publie la chaîne § L.2 sur stdout, la ligne « issue inscrite » de forme fixe, et inscrit l'issue
#    au registre simulé ;
#  - un faux `systemctl` (active, NRestarts=0).
# Simulations : conforme (0) ; triplet « meilleur » (1) ; forme de refus à l'évaluation (1, chaîne NOT_RUN, registre
# simulé sans verdict) ; échec du préfixe (1, ancrage NOT_RUN, registre simulé jamais créé) ; violation de chaîne (1) ;
# variante déjà au registre, new_entry faux (1) ; SHA faux (2) ; sans marqueur (2).
# Limite dite : bash local 3.2, serveur bash 5 ; seules des constructions portables sont employées.
# Limite dite (v2) : le registre simulé part absent, comme au v1, alors que le registre réel porte la variante v1 —
# le pilote ne lit jamais le registre, son comportement n'en dépend pas ; la parenté (refus sur registre vide,
# inscription nouvelle sur registre portant v1, idempotence) est prouvée par manifest_check.sh avec c3_anchor lui-même.
# Env : DRYRUN_OUT (sortie, défaut tests/pilot_dryrun.out) ; DRYRUN_KEEP (répertoire où déposer status.txt,
# alembic_*.txt, pilot_exit.txt et sim.env de la simulation conforme — témoin de verify_adverse.sh).
# rc=0 ssi les huit simulations rendent leur code attendu et portent leurs marqueurs.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=${DRYRUN_OUT:-results/c3_campagne_grid_v2/tests/pilot_dryrun.out}
SELF=results/c3_campagne_grid_v2/server/run_campagne.sh
MANIFEST=results/c3_campagne_grid_v2/manifest.json
C3=$(printf 'c%s' 3)
REG_FULL="/home/bruno/${C3}/regis$(printf 'try')/variants.json"
T=$(mktemp -d) || exit 2
T=$(cd "$T" && pwd -P) || exit 2
fail=0
: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
log "# pilot_dryrun — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)"
log "bash_local=$(bash --version | head -n 1)"

# --- faux systemctl, faux interpréteur -----------------------------------------------------------------------------
mkdir -p "$T/bin"
cat > "$T/bin/systemctl" <<'SH'
#!/bin/bash
case "$1" in
  is-active) echo active ;;
  show) echo "NRestarts=0" ;;
  *) exit 1 ;;
esac
SH
cat > "$T/bin/fakepy" <<'PY'
#!/usr/bin/env python3
import json
import os
import random
import sys

sys.stdout.reconfigure(encoding="utf-8")
args = sys.argv[1:]
dev = os.environ.get("SIM_DEVIATION", "")
src = os.environ.get("PYTHONPATH", "")


def opt(name):
    return args[args.index(name) + 1] if name in args else None


def dump(path, payload):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


kb = f"{src}/krakenbot/__init__.py"
if args[:1] == ["-V"]:
    print("Python 3.12.3")
elif args[:1] == ["-c"]:
    if "socket" in args[1]:
        sys.exit(0)
    print(kb)
elif args[:2] == ["-m", "alembic"]:
    print("INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.")
    print("INFO  [alembic.runtime.migration] Will assume transactional DDL.")
    print("c3bd1e7a0001 (head)")
elif args[:1] == ["-"]:
    code = sys.stdin.read()
    sys.argv = ["-", *args[1:]]
    exec(compile(code, "<stdin>", "exec"), {"__name__": "__main__"})
else:
    script = os.path.basename(args[0])
    if script == "c3b_prefix.py":
        if dev == "prefix_echec":
            print("2026-10-01T00:00:00Z [error    ] job_failed                     identity=x")
            sys.exit(3)
        out = opt("--output-dir")
        for name in ("observations", "coverage", "candles"):
            dump(f"{out}/{name}.json", {"sim": name, "manifest": opt("--manifest")})
        dump(f"{out}/partial/x.json", {"duration_s": random.random()})
        dump(f"{out}/prefix_run.json", {"interpreter": {"krakenbot": kb}, "duration_s": random.random()})
        print("2026-10-01T00:00:00Z [info     ] job_done                       identity=x")
    elif script == "c3_anchor.py":
        reg = opt("--registry")
        registry = load(reg) if os.path.exists(reg) else {"salt": "sim", "variants": {}}
        new = "k" not in registry["variants"]
        if new:
            registry["variants"]["k"] = {"family": "sim"}
            dump(reg, registry)
        dump(opt("--output"), {"sim": "anchor", "registry": {"path": reg, "new_entry": new}})
        print(f"variante k (sim) — {'nouvelle au registre' if new else 'déjà au registre, idempotent'}")
    elif script == "c3_entry.py":
        dump(opt("--output"), {"sim": "entry", "observations": {"path": opt("--observations")}})
        with open(opt("--markdown"), "w", encoding="utf-8") as handle:
            handle.write(f"entry {opt('--observations')}\n")
    elif script == "c3_benchmark.py":
        dump(opt("--output"), {"sim": "benchmark", "anchor": opt("--anchor")})
    elif script == "c3_select.py":
        dump(opt("--output"), {"sim": "selection", "benchmark": opt("--benchmark")})
        with open(opt("--markdown"), "w", encoding="utf-8") as handle:
            handle.write(f"selection {opt('--coverage')}\n")
    elif script == "c3b_evaluate.py":
        out = opt("--output-dir")
        dump(f"{out}/evaluation.json", {"sim": "evaluation", "selection": opt("--selection")})
        for name in ("benchmark_eval", "candles_eval", "evaluation_sensitivity"):
            dump(f"{out}/{name}.json", {"sim": name})
        dump(f"{out}/evaluation_run_provenance.json", {"interpreter": {"krakenbot": kb}, "duration_s": random.random()})
        event = "refusal_form_written" if dev == "forme_de_refus" else "evaluated"
        print(f"2026-10-01T00:00:00Z [info     ] {event:<30} source=selection")
    elif script == "c3_verdict.py" and args[1:2] == ["chain"]:
        out = opt("--out-dir")
        reg = opt("--registry")
        registry = load(reg)
        dump(f"{out}/anchor.json", {"sim": "chain-anchor", "registry": {"path": reg, "new_entry": "k" not in registry["variants"]}})
        for name in ("entry", "benchmark", "selection", "continuity"):
            dump(f"{out}/{name}.json", {"sim": f"chain-{name}", "evaluation": opt("--evaluation")})
        for name in ("entry", "selection"):
            with open(f"{out}/{name}.md", "w", encoding="utf-8") as handle:
                handle.write(f"chain {name}\n")
        steps = [{"name": s, "exit_code": 0} for s in ("anchor", "entry", "benchmark", "select", "continuity")]
        bad = dev == "chain_violation"
        violations = ["rejeu {21:dd} : simulé"] if bad else []
        dump(f"{out}/verdict.json", {"violations": violations, "chain": {"verified": not bad, "steps": steps}})
        if bad:
            print("ARTEFACT INVALIDE — aucun verdict, aucune chaîne citable")
            print("VIOLATION rejeu {21:dd} : simulé", file=sys.stderr)
            sys.exit(1)
        issue, reason = ("validé", "-") if dev == "triplet_meilleur" else ("inconclusif", "P_PROVENANCE")
        print(
            f"C3_{opt('--campaign')} | verdict={issue} | raison={reason} | selection=0123456789abcdef"
            " | statut_selection=SÉLECTION_DESCRIPTIVE | continuite=VÉRIFIÉE | variante=0123456789abcdef"
            " | provenance=contaminated | protocole=d030ab239de317f6 | observations=0123456789abcdef"
        )
        print("")
        print(f"written {out}/verdict.json sha256 " + "0" * 64)
        registry["variants"]["k"]["verdict"] = {"issue": issue, "raison": reason, "compte": False}
        dump(reg, registry)
        print(f"written {reg} (issue inscrite, § A.6)")
    else:
        print(f"fakepy: script inconnu {args}", file=sys.stderr)
        sys.exit(9)
PY
chmod +x "$T/bin/systemctl" "$T/bin/fakepy"

# --- service jetable ------------------------------------------------------------------------------------------------
mkdir -p "$T/service"
git -C "$T/service" init -q
git show HEAD:poetry.lock > "$T/service/poetry.lock"
git show HEAD:pyproject.toml > "$T/service/pyproject.toml"
git -C "$T/service" add poetry.lock pyproject.toml
git -C "$T/service" -c user.name=sim -c user.email=sim@localhost commit -q -m service

# simulate <nom> <déviation> <sha : HEAD | faux> <marqueur : oui | non> [variante déjà au registre : oui | non]
# -> code du pilote ; monde neuf à chaque fois
simulate() {
  local name=$1 deviation=$2 which=$3 marker=$4 prereg=${5:-non}
  local run=$T/$name/runs/c3_campagne_grid/campagne
  local reg=$T/$name/registre_simule/variants.json
  mkdir -p "$run/out" "$(dirname "$reg")"
  git clone -q "$ROOT" "$run/repo" || return 90
  mkdir -p "$(dirname "$run/repo/$MANIFEST")" "$(dirname "$run/repo/$SELF")"
  cp "$MANIFEST" "$run/repo/$MANIFEST"
  sed -e "s|^SERVICE=/home/bruno/apps/kraken-trading-bot\$|SERVICE=$T/service|" \
    -e "s|^PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python\$|PY=$T/bin/fakepy|" \
    -e "s|^RUN=/home/bruno/runs/c3_campagne_grid/campagne\$|RUN=$run|" \
    -e "s|^UNLOCK=results/c3b_producteur/CAMPAIGN_UNLOCK\$|UNLOCK=results/c3b_producteur/SIM_MARQUEUR_UNLOCK|" \
    -e "s|--registry ${REG_FULL} |--registry ${reg} |" "$SELF" > "$run/repo/$SELF"
  CHANGED=$(diff "$SELF" "$run/repo/$SELF" | grep -c '^>')
  git -C "$run/repo" add "$MANIFEST" "$SELF"
  git -C "$run/repo" -c user.name=sim -c user.email=sim@localhost commit -q -m "sim"
  touch "$run/repo/.env"
  if [ "$marker" = oui ]; then : > "$run/repo/results/c3b_producteur/SIM_MARQUEUR_UNLOCK"; fi
  if [ "$prereg" = oui ]; then printf '{"salt": "sim", "variants": {"k": {"family": "sim"}}}\n' > "$reg"; fi
  local sha
  sha=$(git -C "$run/repo" rev-parse HEAD)
  if [ "$which" = faux ]; then sha=0000000000000000000000000000000000000000; fi
  (cd "$run/repo" && PATH="$T/bin:$PATH" SIM_DEVIATION="$deviation" \
    bash "$run/repo/$SELF" "$sha" > "$T/$name/stdout.txt" 2>&1)
  local r=$?
  echo "$r" > "$run/out/pilot_exit.txt"
  SIM_RUN=$run
  SIM_REG=$reg
  SIM_SHA=$(git -C "$run/repo" rev-parse HEAD)
  return $r
}
st() { grep -E "^$2=" "$1/out/status.txt" 2> /dev/null | head -n 1; }   # la ligne de status d'une clé
has() { grep -qxF -- "$2" "$1/out/status.txt" || { fail=1; log "marqueur_absent $2"; }; }   # marqueur exigé
has_re() { grep -qE -- "$2" "$1/out/status.txt" || { fail=1; log "marqueur_absent $2"; }; }  # marqueur exigé (motif)
reg_state() {  # absent | sans_verdict | avec_verdict
  if [ ! -f "$1" ]; then echo absent; return; fi
  python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); print("avec_verdict" if "verdict" in d["variants"]["k"] else "sans_verdict")' "$1"
}
expect_rc() {  # expect_rc <nom> <code obtenu> <code attendu>
  log "sim_${1}_exit=$2 attendu=$3"
  [ "$2" = "$3" ] || fail=1
}

# 1. conforme
simulate conforme "" HEAD oui; r=$?
log "pilote_lignes_changees=$CHANGED (attendu 6 : SERVICE, PY, RUN, UNLOCK, les deux --registry)"
[ "$CHANGED" = "6" ] || fail=1
expect_rc conforme "$r" 0
for k in halted_at issue raison selection_descriptive registry_new_entry_pre registry_new_entry_chain issue_inscrite \
  chain_verified chain_steps eval prefix; do
  log "sim_conforme_$(st "$SIM_RUN" "$k" | sed 's/ at=.*//')"
done
for m in "halted_at=-" "issue=inconclusif" "raison=P_PROVENANCE" "selection_descriptive=true" \
  "registry_new_entry_pre=true" "registry_new_entry_chain=false" "issue_inscrite=true" "chain_verified=true" \
  "chain_steps=anchor:0,entry:0,benchmark:0,select:0,continuity:0" "campaign_unlock_after=present"; do
  has "$SIM_RUN" "$m"
done
s=$(reg_state "$SIM_REG"); log "sim_conforme_registre_simule=$s"; [ "$s" = avec_verdict ] || { fail=1; log "registre_simule_inattendu conforme"; }
if [ -n "${DRYRUN_KEEP:-}" ]; then
  mkdir -p "$DRYRUN_KEEP"
  cp "$SIM_RUN/out/status.txt" "$SIM_RUN/out/alembic_before.txt" "$SIM_RUN/out/alembic_after.txt" \
    "$SIM_RUN/out/pilot_exit.txt" "$DRYRUN_KEEP/"
  {
    echo "SIM_SHA=$SIM_SHA"
    echo "SIM_PILOT_SHA=$(sha256sum "$SIM_RUN/repo/$SELF" | cut -d' ' -f1)"
  } > "$DRYRUN_KEEP/sim.env"
fi

# 2. triplet « meilleur » : un écart, jamais une bonne surprise
simulate triplet_meilleur triplet_meilleur HEAD oui; r=$?
expect_rc triplet_meilleur "$r" 1
for k in issue raison halted_at; do log "sim_triplet_meilleur_$(st "$SIM_RUN" "$k")"; done
has "$SIM_RUN" "issue=validé"; has "$SIM_RUN" "raison=-"; has "$SIM_RUN" "halted_at=extract"

# 3. forme de refus à l'évaluation : arrêt avant la chaîne, aucune issue inscrite
simulate forme_de_refus forme_de_refus HEAD oui; r=$?
expect_rc forme_de_refus "$r" 1
for k in eval chain halted_at; do log "sim_forme_de_refus_$(st "$SIM_RUN" "$k" | sed 's/ at=.*//')"; done
has "$SIM_RUN" "chain=NOT_RUN"; has "$SIM_RUN" "halted_at=eval"
has_re "$SIM_RUN" '^eval=0 event=refusal_form_written '
s=$(reg_state "$SIM_REG"); log "sim_forme_de_refus_registre_simule=$s"; [ "$s" = sans_verdict ] || { fail=1; log "registre_simule_inattendu forme_de_refus"; }

# 4. échec du préfixe : l'ancrage ne tourne pas, le registre simulé n'est jamais créé
simulate prefix_echec prefix_echec HEAD oui; r=$?
expect_rc prefix_echec "$r" 1
for k in prefix pre_anchor halted_at; do log "sim_prefix_echec_$(st "$SIM_RUN" "$k" | sed 's/ at=.*//')"; done
has "$SIM_RUN" "pre_anchor=NOT_RUN"; has "$SIM_RUN" "halted_at=prefix"
has_re "$SIM_RUN" '^prefix=3 event=job_failed '
s=$(reg_state "$SIM_REG"); log "sim_prefix_echec_registre_simule=$s"; [ "$s" = absent ] || { fail=1; log "registre_simule_inattendu prefix_echec"; }

# 5. violation de chaîne
simulate chain_violation chain_violation HEAD oui; r=$?
expect_rc chain_violation "$r" 1
for k in chain chain_verified replay_violations_empty issue halted_at; do
  log "sim_chain_violation_$(st "$SIM_RUN" "$k" | sed 's/ at=.*//')"
done
has "$SIM_RUN" "chain_verified=false"; has "$SIM_RUN" "issue=absent"; has "$SIM_RUN" "halted_at=chain"

# 6. variante déjà au registre : new_entry faux à l'ancrage autonome, arrêt aussitôt
simulate new_entry_faux "" HEAD oui oui; r=$?
expect_rc new_entry_faux "$r" 1
for k in registry_new_entry_pre pre_entry halted_at; do log "sim_new_entry_faux_$(st "$SIM_RUN" "$k")"; done
has "$SIM_RUN" "registry_new_entry_pre=false"; has "$SIM_RUN" "pre_entry=NOT_RUN"
has "$SIM_RUN" "halted_at=registry_new_entry_pre"

# 7. garde : SHA passé ≠ HEAD
simulate guard_head "" faux oui; r=$?
expect_rc guard_head "$r" 2
log "sim_guard_head_$(st "$SIM_RUN" guard | cut -d' ' -f1)"

# 8. garde : marqueur de simulation (rôle de CAMPAIGN_UNLOCK) absent du clone
simulate sans_marqueur "" HEAD non; r=$?
expect_rc sans_marqueur "$r" 2
log "sim_sans_marqueur_$(st "$SIM_RUN" guard)"
has "$SIM_RUN" "guard=REFUSED campaign_unlock_absent"

rm -rf "$T"
[ ! -e "$T" ]; log "temporaire_supprime=$?"
log "rc=$fail"
exit $fail
