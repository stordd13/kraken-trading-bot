#!/bin/bash
# C3 v2.2 — porte de fin de chantier (critère de fin du brief), lancée par `bash` depuis le dépôt, au SHA livré,
# arbre propre. Une ligne `clé=code` par critère (0 = tenu), puis `rc`. Sortie : gate.out.
#  1. sha à trois voies : shasum du protocole = dernière ligne `**sha256 vX.Y :**` d'Adoption = protocol_descriptor ;
#  2. suite complète verte au sens CI, SANS TUNNEL (greffon gate_sans_tunnel : connexions 5432/5433 refusées au
#     seul processus pytest ; les tests base s'ignorent comme en CI), les 24 `_full` désélectionnés ; 0 échec,
#     0 XPASS ; l'ensemble des xfailed est exactement la liste de outillage_v2_2.md ; décompte des ignorés ;
#  3. ruff (src/ et la liste C3 de la CI) ; mypy src/ = 65 ;
#  4. gold : fichier inchangé depuis 8689636 et moteur/src inchangés (le test, lié à la base, s'ignore sans tunnel) ;
#  5. diff de contrôle depuis 8689636 : vide sur le code et les chemins gelés ; tout fichier changé ∈ liste close ;
#  6. livrable C3a : ses deux tests de refus passent, ses fichiers sont intacts ;
#  7. § B.8 : le test-miroir de la table est identique à 8689636 et passe ;
#  8. paquet complet ; phase1.md et outillage_v2_2.md suivis ; texte appliqué = paquet ; index § M = régénération.
set -o pipefail
set -u
unset VIRTUAL_ENV

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
BASE=8689636
OUT=results/c3_v2_2/tests/gate.out
PKG=docs/amendements_c3_v2.2.md
LOG=$(mktemp)
rc=0
say() { echo "$1" >> "$OUT"; }
mark() { say "$1=$2"; [ "$2" -eq 0 ] || rc=1; }

{
  echo "# gate — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
  echo "# arbre : $(git status --porcelain --untracked-files=no | wc -l | tr -d ' ') fichier(s) suivi(s) modifié(s)"
} > "$OUT"
if nc -z -w 2 127.0.0.1 5433 > /dev/null 2>&1; then say "tunnel_5433=ouvert (non ouvert par la porte ; neutralisé pour pytest par gate_sans_tunnel)"; else say "tunnel_5433=fermé"; fi

# 1. sha à trois voies
sha_file=$(shasum -a 256 docs/protocole_c3.md | cut -d' ' -f1)
sha_line=$(grep -oE '\*\*sha256 v[0-9]+\.[0-9]+ :\*\* `[0-9a-f]{64}`' "$PKG" | tail -n 1 | grep -oE '[0-9a-f]{64}')
sha_desc=$(poetry run python -c "import sys; sys.path.insert(0, 'scripts/audit'); import c3_common as cc; print(cc.protocol_descriptor()['sha256'])" 2>/dev/null)
say "sha_fichier=${sha_file}"
say "sha_adoption=${sha_line}"
say "sha_descripteur=${sha_desc}"
if [ -n "$sha_file" ] && [ "$sha_file" = "$sha_line" ] && [ "$sha_file" = "$sha_desc" ]; then v=0; else v=1; fi
mark sha_trois_voies "$v"

# 2. suite complète, sans tunnel
PYTHONPATH="results/c3_v2_2/tests${PYTHONPATH:+:$PYTHONPATH}" poetry run pytest -q -p no:cacheprovider -p gate_sans_tunnel \
  -rsxX -k "not test_determinism_parallel_vs_serial_full" > "$LOG" 2>&1
py=$?
say "pytest_exit=${py}"
say "resume=$(tail -n 1 "$LOG")"
mark suite_verte "$py"
if grep -qE '^(FAILED|ERROR|XPASS) ' "$LOG"; then v=1; grep -E '^(FAILED|ERROR|XPASS) ' "$LOG" >> "$OUT"; else v=0; fi
mark zero_echec_zero_xpass "$v"
say "## tests ignorés, par raison (tests base : ignorés sans tunnel, comme en CI)"
grep -E '^SKIPPED ' "$LOG" | sed -E 's/^SKIPPED \[([0-9]+)\] [^:]+(:[0-9]+)?: /\1 /' | awk '{n=$1; $1=""; c[$0]+=n} END {for (r in c) print c[r] " :" r}' | sort -rn >> "$OUT"
poetry run python - "$LOG" results/c3_v2_2/outillage_v2_2.md >> "$OUT" 2>&1 <<'PY'
import collections, re, sys
log = open(sys.argv[1], encoding="utf-8").read()
xfailed = collections.Counter(
    # l'id paramétré peut contenir des espaces : on coupe au premier crochet
    re.sub(r"\[.*$", "", m.group(1)).split("tests/test_scripts/")[-1]
    for m in re.finditer(r"^XFAIL (\S+)", log, re.MULTILINE)
)
liste = open(sys.argv[2], encoding="utf-8").read()
expected = collections.Counter()
for m in re.finditer(r"`(test_c3[a-z_]*\.py::[A-Za-z0-9_]+)`(?: \((\d+) cas\))?", liste):
    expected[m.group(1)] += int(m.group(2) or 1)
# le témoin vert d'AM-04 est cité dans la liste mais n'est pas un xfail
expected.pop("test_c3_entry.py::test_un_suffixe_de_monnaie_hors_des_positions_nommees_n_est_ni_lu_ni_refuse", None)
print(f"xfailed={sum(xfailed.values())} liste_outillage={sum(expected.values())}")
missing = expected - xfailed
extra = xfailed - expected
for k in sorted(missing):
    print(f"liste_non_xfail {k}")
for k in sorted(extra):
    print(f"xfail_hors_liste {k}")
print(f"xfail_egal_liste={0 if not missing and not extra else 1}")
PY
if grep -q '^xfail_egal_liste=0$' "$OUT"; then v=0; else v=1; fi
mark xfail_egaux_a_la_liste "$v"
say "## xfail, avec leur raison"
grep -E '^XFAIL ' "$LOG" | sed 's|tests/test_scripts/||' >> "$OUT"

# 3. ruff, mypy
RUFF_C3=(scripts/audit/_common.py scripts/audit/_db.py scripts/audit/c3*.py scripts/audit/warmup_at.py
  scripts/audit/reconstruct_1w.py tests/test_scripts/test_c3*.py tests/test_scripts/test_warmup_at.py
  tests/test_scripts/test_reconstruct_1w.py tests/test_scripts/test_audit_common.py)
poetry run ruff check src/ "${RUFF_C3[@]}" > "$LOG" 2>&1; r1=$?
poetry run ruff format --check src/ "${RUFF_C3[@]}" >> "$LOG" 2>&1; r2=$?
[ "$r1" -eq 0 ] && [ "$r2" -eq 0 ] && v=0 || { v=1; tail -n 20 "$LOG" >> "$OUT"; }
mark ruff "$v"
poetry run mypy src/ > "$LOG" 2>&1
say "mypy=$(tail -n 1 "$LOG")"
if grep -qE '^Found 65 errors in ' "$LOG"; then v=0; else v=1; fi
mark mypy_src_65 "$v"

# 4. gold
GOLD=tests/test_strategies/test_grid_atr_v4_backward_compat.py
git diff --quiet "$BASE" HEAD -- "$GOLD" src scripts/backtest.py; v=$?
mark gold_fichier_et_moteur_inchanges_depuis_8689636 "$v"
say "gold_note=le test gold est lié à la base : ignoré sans tunnel ; il passait 2/2 à ${BASE} (results/c3b_producteur/closure/tests/mypy_gold.out), et ni lui ni le moteur n'ont changé"

# 5. diff de contrôle
FROZEN=(src scripts/audit scripts/backtest.py scripts/run_p6_backtests.py scripts/run_p7_grid_search.py
  scripts/p7_grids.py scripts/compute_benchmarks.py config pyproject.toml poetry.lock
  results/c3a_entry_validation results/c3b_producteur docs/CONTRAINTES_POST_B4.md)
git diff --quiet "$BASE" HEAD -- "${FROZEN[@]}"; v=$?
mark diff_vide_chemins_geles "$v"
say "diff_src_scripts_audit=$(git diff --stat "$BASE" HEAD -- src 'scripts/audit/*.py' | wc -l | tr -d ' ') ligne(s)"
ALLOWED_RE='^(agent/AGENT_C3_AMENDEMENT_V2_2\.md|docs/amendements_c3_v2\.2\.md|docs/protocole_c3\.md|results/c3_v2_2/.*|tests/test_scripts/test_c3(b)?_[a-z_]+\.py|CLAUDE\.md|skills/backtest\.md|docs/RESEARCH_LOG\.md|PROJECT_CONTEXT\.md|ROADMAP\.md|docs/CODE_MAP\.md|results/INDEX\.md)$'
bad=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  printf '%s\n' "$f" | grep -Eq "$ALLOWED_RE" || { say "hors_liste ${f}"; bad=1; }
done < <(git diff --name-only "$BASE" HEAD)
mark fichiers_dans_liste_close "$bad"
say "## git diff --stat ${BASE} HEAD"
git diff --stat "$BASE" HEAD >> "$OUT"

# 6. livrable C3a
C3A=(tests/test_scripts/test_c3_entry.py::test_le_livrable_reel_de_C3a_reste_l_historique_v20_et_n_est_pas_rejouable_sous_v21
  tests/test_scripts/test_c3_verdict.py::test_chain_sur_le_livrable_reel_v20_s_arrete_a_l_ancrage_code_2_rien_d_ecrit)
poetry run pytest -q -p no:cacheprovider "${C3A[@]}" > "$LOG" 2>&1; v=$?
say "c3a=$(tail -n 1 "$LOG")"
mark livrable_c3a_refuse_sous_v22 "$v"

# 7. § B.8 : test-miroir identique et vert
poetry run python - "$BASE" >> "$OUT" 2>&1 <<'PY'
import ast, subprocess, sys
name = "test_la_table_B8_du_texte_est_la_liste_close_du_code"
def src(text):
    tree = ast.parse(text)
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(text, node)
old = subprocess.run(["git", "show", f"{sys.argv[1]}:tests/test_scripts/test_c3_verdict.py"], capture_output=True, text=True, check=True).stdout
new = open("tests/test_scripts/test_c3_verdict.py", encoding="utf-8").read()
print(f"miroir_B8_identique={0 if src(old) == src(new) else 1}")
PY
poetry run pytest -q -p no:cacheprovider "tests/test_scripts/test_c3_verdict.py::test_la_table_B8_du_texte_est_la_liste_close_du_code" > "$LOG" 2>&1; v=$?
if grep -q '^miroir_B8_identique=0$' "$OUT" && [ "$v" -eq 0 ]; then v=0; else v=1; fi
mark miroir_B8_identique_et_vert "$v"

# 8. paquet complet, livrables, texte, index
miss=0
for h in "## Adoption" "### Empreinte du protocole" "### Décisions de gate" "### Réserves d'application" \
    "Ligne Astra" "### Écarts de rédaction" "## Table de correspondance" "## Vérifié, sans amendement" \
    "## Ordre d'application" "## Constats de rédaction"; do
  grep -q "^${h}\|${h}" "$PKG" || { say "rubrique_absente ${h}"; miss=1; }
done
mark paquet_complet "$miss"
v=0
for f in results/c3_v2_2/phase1.md results/c3_v2_2/outillage_v2_2.md; do
  git ls-files --error-unmatch "$f" > /dev/null 2>&1 || { say "non_suivi ${f}"; v=1; }
done
mark livrables_suivis "$v"
python3 results/c3_v2_2/tests/texte_conforme.py > "$LOG" 2>&1; v=$?
say "texte_conforme=$(grep -c '^ok' "$LOG") bloc(s) ok, $(grep -c '^ABSENT' "$LOG") absent(s)"
mark texte_applique_egal_paquet "$v"
bash results/c3_v2_2/tests/index_m.sh > /dev/null 2>&1; v=$?
mark index_M_regenere "$v"

rm -f "$LOG"
say "rc=${rc}"
exit "$rc"
