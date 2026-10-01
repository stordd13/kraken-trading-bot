#!/bin/bash
# C3 racine du registre, lot 1 — les mutants du plan (plans/plan.md § 4), un à la fois, après C3 (repris de
# results/c3_outillage_v2_3/tests/mutants_lot1.sh, liste neuve). Chaque mutant est une substitution littérale unique
# d'un module de chaîne, appliquée par mutant.sh, qui lance UN tueur nommé, restaure le fichier par `git checkout`,
# vérifie le diff vide et relance le tueur (vert) ; un mutant à plusieurs tueurs est appliqué une fois par tueur, pour
# que chaque tueur nommé soit prouvé seul. M2a-c et M3a-b portent sur des modules gelés pour ce chantier (plan D3) :
# mutants temporaires seulement. Plus : `non_divulgation.sh` doit mordre sur M5 (la racine imprimée), vérifié ici par
# application, lancement et restauration.
# Usage : bash mutants.sh. Journal : results/c3_racine_registre/mutants.log ; rc=0 ssi tous tués et restaurés.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LOG=results/c3_racine_registre/mutants.log
T=results/c3_racine_registre/tests
SPECS=$(mktemp -d)
git diff --quiet -- scripts || { echo "scripts/ déjà modifié : refus" >&2; exit 2; }
echo "## mutants — début $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$LOG"
python3 - "$SPECS" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
CM = "scripts/audit/c3_common.py"
AN = "scripts/audit/c3_anchor.py"
VE = "scripts/audit/c3_verdict.py"
A = "tests/test_scripts/test_c3_anchor.py::"
V = "tests/test_scripts/test_c3_verdict.py::"
T1 = A + "test_A6_la_racine_du_registre_survit_a_l_ancrage_enregistrement_idempotence_enfant"
T4 = A + "test_R22_un_non_fini_a_la_racine_du_registre_est_un_diagnostic"
T2C = V + "test_A6_la_racine_du_registre_traverse_l_ancrage_et_l_inscription_du_verdict"
T2V = V + "test_A6_registry_inscription_preserve_les_cles_de_racine"
T3 = V + "test_A6_v23_les_instants_de_D_sont_normalises_un_instant_pas_une_graphie"

LOAD_RETURN = '    return {**root, "variants": dict(variants)}\n'
INSCRIPTION = '    updated = {**dict(raw), "variants": {**dict(variants), variant_key: new_record}}\n'
specs = [
    # --- le passthrough à l'ancrage (D1) ---
    ("M1a load_registry rend {variants} seul (état 313eb00)", AN,
     LOAD_RETURN, '    return {"variants": dict(variants)}\n', [T1, T2C]),
    ("M1b register (écriture) rend {variants: updated}", AN,
     '    return {**dict(registry), "variants": updated}, True\n', '    return {"variants": updated}, True\n',
     [T1, T2C]),
    # --- l'inscription du verdict (D3, module gelé : mutant temporaire) ---
    ("M2a registry_inscription : racine perdue", VE,
     INSCRIPTION, '    updated = {"variants": {**dict(variants), variant_key: new_record}}\n', [T2V, T2C]),
    ("M2b registry_inscription : racine réécrite par canon", VE,
     INSCRIPTION, '    updated = {**cc.canon(dict(raw)), "variants": {**dict(variants), variant_key: new_record}}\n',
     [T2V, T2C]),
    ("M2c run_verdict : registre canonicalisé au site d'écriture", VE,
     "        cc.write_json(registry, registry_update)\n",
     '        cc.write_json(registry, {**cc.canon(dict(registry_update)), "variants": registry_update["variants"]})\n',
     [T2C]),
    # --- la normalisation UTC de D (D6, module gelé : mutant temporaire) ---
    ("M3a D : la graphie du manifeste entre dans window (isoformat contourné)", CM,
     '        "window": {"start": window[0].isoformat(), "end": window[1].isoformat()},\n',
     '        "window": {\n'
     '            "start": next(v for v in (raw["window"]["start"], raw["window"]["end"]) if parse_datetime(v, where=where) == window[0]),\n'
     '            "end": next(v for v in (raw["window"]["end"], raw["deferred_evaluation"]["date"]) if parse_datetime(v, where=where) == window[1]),\n'
     '        },\n',
     [T3]),
    ("M3b parse_datetime sans astimezone(UTC)", CM,
     "    return parsed.astimezone(UTC)\n", "    return parsed\n", [T3]),
    # --- le contrôle de la racine (D2) ---
    ("M4 contrôle de la racine retiré", AN,
     "    try:\n"
     "        cc.dumps_canonical(root)\n"
     "    except ValueError:\n"
     "        raise cc.NonFiniteValueError(\n"
     '            "registre : une valeur de racine hors `variants` est non finie (§ I.1, ligne 15)"\n'
     "        ) from None\n",
     "", [T4]),
    # --- non-divulgation (D8) ---
    ("M5 load_registry imprime la racine sur stderr", AN,
     LOAD_RETURN, '    print(f"registre : racine {root}", file=sys.stderr)\n' + LOAD_RETURN, [T1]),
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
  while IFS= read -r k; do
    bash "$T/mutant.sh" "$label — tueur ${k##*::}" "$target" "$d/old" "$d/new" "$k"
    r=$?
    echo "résultat=$r (attendu 0 : tué, restauré, reverdi)" >> "$LOG"
    [ "$r" -eq 0 ] || fail=1
  done < <(python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["killers"]))' "$d/spec.json")
done
# non_divulgation.sh mord sur M5 : appliqué, lancé (rc attendu ≠ 0), restauré, relancé (rc attendu 0).
d=$(ls -d "$SPECS"/* | tail -n 1)
python3 - "scripts/audit/c3_anchor.py" "$d/old" "$d/new" <<'PY'
import pathlib, sys
target, old, new = (pathlib.Path(a) for a in sys.argv[1:4])
text = target.read_text(encoding="utf-8")
a, b = old.read_text(encoding="utf-8"), new.read_text(encoding="utf-8")
assert text.count(a) == 1
target.write_text(text.replace(a, b), encoding="utf-8")
PY
bash "$T/non_divulgation.sh" mutant_M5 > /dev/null 2>&1; under=$?
git checkout -- scripts/audit/c3_anchor.py; git diff --quiet -- scripts; restored=$?
bash "$T/non_divulgation.sh" apres_mutants > /dev/null 2>&1; after=$?
{
  echo "## M5-grep — $(date -u +%FT%TZ) — non_divulgation.sh sous M5"
  echo "sous_mutant_rc=${under} (attendu ≠ 0) restauré_diff_vide=${restored} (attendu 0) après_rc=${after} (attendu 0)"
} >> "$LOG"
{ [ "$under" -ne 0 ] && [ "$restored" -eq 0 ] && [ "$after" -eq 0 ]; } || fail=1
rm -rf "$SPECS"
git diff --quiet -- scripts || fail=1
echo "## mutants rc=$fail — fin $(date -u +%FT%TZ)" >> "$LOG"
exit $fail
