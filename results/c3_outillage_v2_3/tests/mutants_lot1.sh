#!/bin/bash
# C3 outillage v2.3, lot 1 — les mutants du plan (plans/lot1.md § 3), un à la fois, après C4 : chaque mutant est une
# substitution littérale unique d'un des trois modules, appliquée par mutant.sh, qui lance les tueurs nommés, restaure
# le fichier par `git checkout`, vérifie le diff vide et relance les tueurs (verts). Plus : `non_divulgation.sh` doit
# mordre sur M15d (le digest du registre rétabli), vérifié ici par application, lancement et restauration.
# Usage : bash mutants_lot1.sh. Journal : results/c3_outillage_v2_3/mutants.log ; rc=0 ssi tous tués et restaurés.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LOG=results/c3_outillage_v2_3/mutants.log
T=results/c3_outillage_v2_3/tests
SPECS=$(mktemp -d)
git diff --quiet -- scripts || { echo "scripts/ déjà modifié : refus" >&2; exit 2; }
echo "## mutants_lot1 — début $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$LOG"
python3 - "$SPECS" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
CM = "scripts/audit/c3_common.py"
AN = "scripts/audit/c3_anchor.py"
VE = "scripts/audit/c3_verdict.py"
A = "tests/test_scripts/test_c3_anchor.py::"
C = "tests/test_scripts/test_c3_common.py::"
V = "tests/test_scripts/test_c3_verdict.py::"
X1 = A + "test_X1_un_manifeste_sans_date_d_evaluation_differee_est_refuse_a_l_etape_1"
X2 = A + "test_X2_une_date_trop_proche_ou_illisible_est_refusee_365_jours_exactement_passent"
X6 = A + "test_R17_temoin_sur_une_famille_close_l_empreinte_differee_attendue_est_acceptee"
R17ADV = A + "test_R17_sur_une_famille_close_une_autre_empreinte_que_la_differee_est_refusee"
N2 = A + "test_A6_v23_sur_une_famille_close_le_descripteur_entrant_suit_la_regle_du_run_differe"
X8 = C + "test_X8_load_manifest_lit_la_date_differee_et_refuse_toute_forme_invalide"
X3 = V + "test_X3_l_issue_qui_ouvre_la_voie_inscrit_la_date_du_manifeste_et_l_empreinte_du_descripteur"
X4 = V + "test_X4_une_issue_qui_n_ouvre_pas_la_voie_n_inscrit_aucune_evaluation_differee"
X5 = V + "test_X5_le_descripteur_est_derive_champ_par_champ_selon_le_tableau_du_texte"
X7 = V + "test_X7_le_verdict_d_une_variante_differee_n_inscrit_jamais_d_evaluation_differee"
N1 = V + "test_A6_v23_le_predicat_d_ouverture_suit_le_10_1_conjonctif_par_conjonctif"
N3 = V + "test_A6_v23_une_evaluation_differee_inscrite_differente_est_une_violation_sans_empreinte_imprimee"
N4 = V + "test_A6_v23_tout_champ_hors_de_la_table_est_hors_engagement"

W = 'where=f"{where}.data"'
specs = [
    # --- la clé du manifeste (D3) ---
    ("M1 load_manifest lit le bloc en optionnel (absent → date par défaut)", CM,
     '    deferred_block = require_mapping(raw, "deferred_evaluation", where=where)\n'
     '    deferred_date = require_datetime(deferred_block, "date", where=f"{where}.deferred_evaluation")\n',
     '    deferred_block = optional_mapping(raw, "deferred_evaluation", where=where)\n'
     '    deferred_date = (\n'
     '        require_datetime(deferred_block, "date", where=f"{where}.deferred_evaluation")\n'
     '        if deferred_block is not None\n'
     '        else end + timedelta(days=DEFERRED_MIN_DAYS)\n'
     '    )\n',
     [X1, X8]),
    ("M2 borne >= 365 j devenue > 365 j", AN,
     "    if gap < timedelta(days=cc.DEFERRED_MIN_DAYS):\n",
     "    if gap <= timedelta(days=cc.DEFERRED_MIN_DAYS):\n", [X2]),
    ("M3 borne 365 → 364", CM, "DEFERRED_MIN_DAYS = 365\n", "DEFERRED_MIN_DAYS = 364\n", [X2]),
    ("M4 contrôle de la date retiré de l'étape 1", AN,
     "        assert_deferred_date(manifest)\n", "        pass  # mutant M4\n", [X2]),
    # --- le prédicat d'ouverture (D4) ---
    ("M5 prédicat : conjonctif issue/raison retiré", VE,
     "    if (decision.issue, decision.reason) != DEFERRED_WAY_ISSUE:\n        return False\n", "", [X4, N1]),
    ("M6a prédicat : Q1 ignoré", VE,
     "all(decision.gates[q] is True for q in GATES_Q)",
     'all(decision.gates[q] is True for q in GATES_Q if q != "Q1")', [N1]),
    ("M6b prédicat : Q2 ignoré", VE,
     "all(decision.gates[q] is True for q in GATES_Q)",
     'all(decision.gates[q] is True for q in GATES_Q if q != "Q2")', [N1]),
    ("M6c prédicat : Q3 ignoré", VE,
     "all(decision.gates[q] is True for q in GATES_Q)",
     'all(decision.gates[q] is True for q in GATES_Q if q != "Q3")', [N1]),
    ("M7 prédicat : Δ̂ ignoré", VE,
     "    return all(\n"
     '        decision.delta_hat[combination.split(":", 1)[1]] > 0 for combination in cc.COMBINATIONS\n'
     "    )\n",
     "    return True\n", [N1]),
    ("M8 prédicat : Δ̂ > 0 devenu Δ̂ >= 0", VE,
     "[1]] > 0 for combination", "[1]] >= 0 for combination", [N1]),
    # --- la dérivation de D : chaque champ omis (M9), non restreint ou d'une autre source (M10) ---
    ("M9.1 D : deferred_evaluation_of omis", CM, '        "deferred_evaluation_of": of,\n', "", [X5]),
    ("M9.2 D : family omis", CM, '        "family": require_str(raw, "family", where=where),\n', "", [X5]),
    ("M9.3 D : window omis", CM,
     '        "window": {"start": window[0].isoformat(), "end": window[1].isoformat()},\n', "", [X5]),
    ("M9.4 D : candidate omis", CM,
     '        "candidate": {"strategy": strategy, "pair": pair, "params": copy.deepcopy(dict(params))},\n', "",
     [X5]),
    ("M9.5 D : data omis", CM,
     '        "data": {\n'
     f'            key: copy.deepcopy(_require(data, key, {W}))\n'
     '            for key in ("exchange", "exec_interval", "timeframes")\n'
     '        },\n', "", [X5]),
    ("M9.6 D : engines omis", CM,
     '        "engines": {strategy: require_str(block, "engine", where=f"{where}.strategies.{strategy}")},\n', "",
     [X5]),
    ("M9.7 D : decision_timeframes omis", CM, '        "decision_timeframes": sorted(effective),\n', "", [X5]),
    ("M9.8 D : fees omis", CM,
     '        "fees": {\n'
     '            "model": _require(fees, "model", where=f"{where}.fees"),\n'
     '            "taker": _require(fees, "taker", where=f"{where}.fees"),\n'
     '            "pair_costs": {pair: copy.deepcopy(dict(costs))},\n'
     '            "pair_costs_file": _require(fees, "pair_costs_file", where=f"{where}.fees"),\n'
     '        },\n', "", [X5]),
    ("M9.9 D : min_order_quote omis", CM,
     '        "min_order_quote": _require(raw, "min_order_quote", where=where),\n', "", [X5]),
    ("M9.10 D : universe_provenance omis", CM, '        "universe_provenance": provenance,\n', "", [X5]),
    ("M10a D : engines non restreint", CM,
     '        "engines": {strategy: require_str(block, "engine", where=f"{where}.strategies.{strategy}")},\n',
     '        "engines": {\n'
     '            name: require_str(require_mapping(require_mapping(raw, "strategies", where=where), name, where=where), "engine", where=where)\n'
     '            for name in require_mapping(raw, "strategies", where=where)\n'
     '        },\n', [X5]),
    ("M10b D : pair_costs non restreint", CM,
     '            "pair_costs": {pair: copy.deepcopy(dict(costs))},\n',
     '            "pair_costs": copy.deepcopy(dict(require_mapping(fees, "pair_costs", where=where))),\n', [X5, X6]),
    ("M10c D : decision_timeframes non trié", CM,
     '        "decision_timeframes": sorted(effective),\n', '        "decision_timeframes": list(effective),\n',
     [X5, X6]),
    ("M10d D : surcharge par candidat ignorée", CM,
     "        if override is not None\n", "        if False and override is not None\n", [X5]),
    ("M10e D au verdict : provenance de la campagne au lieu de clean", CM,
     "        provenance=PROVENANCE_CLEAN,\n",
     '        provenance=require_str(require_mapping(campaign, "universe", where=where), "provenance", where=where),\n',
     [N4]),
    ("M10f D : data entier (clés hors table comprises)", CM,
     '        "data": {\n'
     f'            key: copy.deepcopy(_require(data, key, {W}))\n'
     '            for key in ("exchange", "exec_interval", "timeframes")\n'
     '        },\n',
     '        "data": copy.deepcopy(dict(data)),\n', [N4]),
    ("M10g D : research_log_entry ajouté", CM,
     '        "universe_provenance": provenance,\n    }\n',
     '        "universe_provenance": provenance,\n'
     '        "research_log_entry": _require(raw, "research_log_entry", where=where),\n    }\n', [X5, N4]),
    # --- la re-dérivation au run différé (D6) ---
    ("M11a run : of = sig(entrant)", CM,
     '        of=require_str(parent, "variant_key", where=f"{where}.parent"),\n', "        of=sig(incoming),\n", [X6]),
    ("M11b run : fenêtre depuis la date différée de l'entrant", CM,
     '            require_datetime(window, "start", where=f"{where}.window"),\n'
     '            require_datetime(window, "end", where=f"{where}.window"),\n',
     '            require_datetime(window, "end", where=f"{where}.window"),\n'
     '            require_datetime(require_mapping(incoming, "deferred_evaluation", where=where), "date", where=where),\n',
     [X6]),
    ("M11c run : provenance constante clean", CM,
     "        provenance=require_str(\n"
     '            universe, "provenance", where=f"{where}.universe", allowed=PROVENANCES\n'
     "        ),\n",
     "        provenance=PROVENANCE_CLEAN,\n", [N2]),
    ("M11d run : premier candidat au lieu de l'unique", CM,
     "    if len(candidates) != 1:\n        return None\n    (only,) = candidates\n",
     "    if len(candidates) < 1:\n        return None\n    only = candidates[0]\n", [N2]),
    # --- la comparaison à l'ancrage (D6) ---
    ("M12a ancrage : empreinte brute (état v2.2)", AN,
     "            if descriptor is not None and cc.sig(descriptor) in deferred_keys:\n",
     "            if key in deferred_keys:\n", [X6]),
    ("M12b ancrage : tout accepté sur famille close", AN,
     "    if counted:\n        if deferred_keys:\n", "    if counted:\n        return\n        if deferred_keys:\n",
     [R17ADV]),
    # --- l'inscription (D5) ---
    ("M13 garde « une fois par famille » retirée", VE,
     "    if deferred is not None and _family_carries_deferred(\n"
     "        variants, family=family, variant_key=variant_key\n"
     "    ):\n"
     "        deferred = None\n", "", [X7]),
    ("M14 bloc différé ignoré à la réinscription", VE,
     "        elif (existing_deferred is None) != (deferred is None) or (\n",
     "        elif False and ((existing_deferred is None) != (deferred is None)) or False and (\n", [N3]),
    # --- non-divulgation (D7, D13) ---
    ("M15a ancrage : empreinte dérivée imprimée dans le refus", AN,
     '(variante {key[:16]}) "\n',
     '(variante {key[:16]}, {cc.sig(cc.deferred_descriptor_at_run(incoming) or {})[:16]}) "\n', [N2]),
    ("M15b verdict : bloc différé interpolé dans la violation de discordance", VE,
     '                "celle de ce verdict — valeurs non imprimées',
     '                f"celle de ce verdict {dict(existing_deferred)} — valeurs non imprimées', [N3]),
    ("M15c verdict : bloc différé imprimé sur la ligne d'inscription", VE,
     '        print(f"written {registry} (issue inscrite, § A.6)")\n',
     '        print(f"written {registry} (issue inscrite, § A.6) {registry_update[\'variants\']}")\n', [X3]),
    ("M15d verdict : digest du registre rétabli (D13)", VE,
     "        cc.write_json(registry, registry_update)\n"
     '        print(f"written {registry} (issue inscrite, § A.6)")\n',
     "        registry_digest = cc.write_json(registry, registry_update)\n"
     '        print(f"written {registry} sha256 {registry_digest} (issue inscrite, § A.6)")\n', [N3]),
]
for i, (label, target, old, new, killers) in enumerate(specs):
    d = out / f"{i:02d}"
    d.mkdir()
    (d / "old").write_text(old, encoding="utf-8")
    (d / "new").write_text(new, encoding="utf-8")
    (d / "spec.json").write_text(json.dumps({"label": label, "target": target, "killers": killers}), encoding="utf-8")
PY
fail=0
for d in "$SPECS"/*; do
  label=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["label"])' "$d/spec.json")
  target=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["target"])' "$d/spec.json")
  killers=()
  while IFS= read -r k; do killers+=("$k"); done < <(python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["killers"]))' "$d/spec.json")
  bash "$T/mutant.sh" "$label" "$target" "$d/old" "$d/new" "${killers[@]}"
  r=$?
  echo "résultat=$r (attendu 0 : tué, restauré, reverdi)" >> "$LOG"
  [ "$r" -eq 0 ] || fail=1
done
# non_divulgation.sh mord sur M15d : appliqué, lancé (rc attendu ≠ 0), restauré, relancé (rc attendu 0).
d=$(ls -d "$SPECS"/* | tail -n 1)
python3 - "scripts/audit/c3_verdict.py" "$d/old" "$d/new" <<'PY'
import pathlib, sys
target, old, new = (pathlib.Path(a) for a in sys.argv[1:4])
text = target.read_text(encoding="utf-8")
a, b = old.read_text(encoding="utf-8"), new.read_text(encoding="utf-8")
assert text.count(a) == 1
target.write_text(text.replace(a, b), encoding="utf-8")
PY
bash "$T/non_divulgation.sh" mutant_M15d > /dev/null 2>&1; under=$?
git checkout -- scripts/audit/c3_verdict.py; git diff --quiet -- scripts; restored=$?
bash "$T/non_divulgation.sh" apres_mutants > /dev/null 2>&1; after=$?
{
  echo "## M15d-grep — $(date -u +%FT%TZ) — non_divulgation.sh sous M15d"
  echo "sous_mutant_rc=${under} (attendu ≠ 0) restauré_diff_vide=${restored} (attendu 0) après_rc=${after} (attendu 0)"
} >> "$LOG"
{ [ "$under" -ne 0 ] && [ "$restored" -eq 0 ] && [ "$after" -eq 0 ]; } || fail=1
rm -rf "$SPECS"
git diff --quiet -- scripts || fail=1
echo "## mutants_lot1 rc=$fail — fin $(date -u +%FT%TZ)" >> "$LOG"
exit $fail
