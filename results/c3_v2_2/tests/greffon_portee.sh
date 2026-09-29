#!/usr/bin/env bash
# Portée du greffon gate_sans_tunnel (question de Bruno au STOP 2) : il ne doit être chargé que par gate.sh.
#   1. aucun fichier hors results/c3_v2_2/ ne le nomme (conftest, config pytest du dépôt, CI) ;
#   2. une invocation pytest ordinaire ne l'enregistre pas (--trace-config), et le témoin (-p + PYTHONPATH de gate.sh)
#      l'enregistre, ce qui prouve que l'observation le verrait ;
#   3. il n'est pas importable depuis la racine du dépôt sans le PYTHONPATH de gate.sh ;
#   4. pytest ne le collecte pas, même lancé sur son propre répertoire (python_files = test_*.py).
# Collecte seule, sur un fichier sans base : aucun test exécuté, aucune connexion.
set -u
set -o pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2
OUT=results/c3_v2_2/tests/greffon_portee.out
LOG=$(mktemp)
rc=0
say() { printf '%s\n' "$1" | tee -a "$OUT"; }
mark() { say "$1=$2"; if [ "$2" != "0" ]; then rc=1; fi; }
: > "$OUT"
say "# greffon_portee — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "# HEAD $(git rev-parse --short HEAD) branche $(git branch --show-current)"
say "chemin=results/c3_v2_2/tests/gate_sans_tunnel.py"

# 1. qui le nomme
hors=$(git grep -l "gate_sans_tunnel" -- . ':!results/c3_v2_2/' | wc -l | tr -d ' ')
say "fichiers_suivis_hors_chantier_qui_le_nomment=${hors}"
if [ "$hors" = "0" ]; then v=0; else v=1; fi
mark aucun_nommage_hors_chantier "$v"
if git grep -n "gate_sans_tunnel" -- pyproject.toml tests/conftest.py .github > /dev/null 2>&1; then v=1; else v=0; fi
mark absent_config_pytest_conftest_ci "$v"

# 2. invocation ordinaire contre témoin
poetry run pytest --trace-config --co -q -p no:cacheprovider tests/test_scripts/test_c3_common.py > "$LOG" 2>&1
co=$?
if grep -q "gate_sans_tunnel" "$LOG"; then v=1; else v=0; fi
say "collecte_ordinaire_exit=${co}"
mark non_enregistre_invocation_ordinaire "$v"
PYTHONPATH="results/c3_v2_2/tests${PYTHONPATH:+:$PYTHONPATH}" poetry run pytest --trace-config --co -q -p no:cacheprovider \
  -p gate_sans_tunnel tests/test_scripts/test_c3_common.py > "$LOG" 2>&1
if grep -q "gate_sans_tunnel" "$LOG"; then v=0; else v=1; fi
mark temoin_enregistre_sous_gate_sh "$v"

# 3. import depuis la racine, sans le PYTHONPATH de gate.sh
if env -u PYTHONPATH poetry run python -c "import gate_sans_tunnel" > /dev/null 2>&1; then v=1; else v=0; fi
mark non_importable_hors_gate_sh "$v"

# 4. collecte du répertoire du greffon
poetry run pytest --co -q -p no:cacheprovider results/c3_v2_2/tests/ > "$LOG" 2>&1
say "collecte_repertoire=$(tail -n 1 "$LOG")"
if grep -q "gate_sans_tunnel" "$LOG"; then v=1; else v=0; fi
mark non_collecte "$v"

rm -f "$LOG"
say "rc=${rc}"
exit "$rc"
