#!/bin/bash
# Seconde campagne C3 comptée, famille grid-atr-v4, relance unique (repris de results/c3_campagne_grid/tests/table_10_1.sh) —
# la table du § 10.1 de docs/CONTRAINTES_POST_B4.md, recopiée DU
# TEXTE dans server/verify_attendu.py (COUNTED_10_1, CONDITIONAL_10_1) pour dériver « compté » sans lire le registre
# (décision Q1 de Bruno au chantier v1, reconduite), est épinglée aux constantes du code (c3_verdict.COUNTED, UNCOUNTED_IF_REMOVED_BY) par un
# contrôle d'égalité — règle agent 3 : la table du texte est recopiée et épinglée au code, jamais l'inverse.
# Correspondance des clés : la chaîne § L.2 écrit `raison=-` là où le code tient `None` (validé, réfuté) ; la ligne
# conditionnelle du texte (A_NO_ADMISSIBLE_CANDIDATE, retrait par D1, D2 ou D6) correspond à une clé de COUNTED à
# vrai (la branche « aucun retrait ») ET à l'entrée de même raison de UNCOUNTED_IF_REMOVED_BY.
# Le contrôle naît adverse (règle agent 1) : deux mutants de la recopie (P_PROVENANCE basculé à compté ; la ligne
# conditionnelle retirée) doivent le faire échouer. Rien n'est lu hors du code et du vérificateur ; aucune base.
# Sortie : table_10_1.out ; rc=0 ssi la recopie égale le code, chaque mutant mord, et (inconclusif, P_PROVENANCE)
# dérive « non compté ».
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid_v2/tests/table_10_1.out
: > "$OUT"
echo "# table_10_1 — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
poetry run python - >> "$OUT" 2>&1 <<'PY'
import importlib.util
import sys

sys.path.insert(0, "scripts/audit")
import c3_verdict as cv  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "verify_attendu", "results/c3_campagne_grid_v2/server/verify_attendu.py"
)
va = importlib.util.module_from_spec(spec)
spec.loader.exec_module(va)


def from_code():
    """La table du code, aux clés de la chaîne § L.2 : (table inconditionnelle, lignes conditionnelles)."""
    table, conditional = {}, {}
    for (issue, reason), value in cv.COUNTED.items():
        key = (issue, "-" if reason is None else reason)
        if reason in cv.UNCOUNTED_IF_REMOVED_BY:
            if value is not True:
                return None
            conditional[key] = tuple(cv.UNCOUNTED_IF_REMOVED_BY[reason])
        else:
            table[key] = value
    return table, conditional


def equal(text_table, text_conditional):
    return from_code() == (dict(text_table), dict(text_conditional))


ok = equal(va.COUNTED_10_1, va.CONDITIONAL_10_1)
print(f"lignes_texte={len(va.COUNTED_10_1)} conditionnelles={len(va.CONDITIONAL_10_1)} cles_code={len(cv.COUNTED)}")
print(f"recopie_egale_code={'0' if ok else '1'}")
m1 = dict(va.COUNTED_10_1)
m1[("inconclusif", "P_PROVENANCE")] = True
bites1 = not equal(m1, va.CONDITIONAL_10_1)
print(f"mutant_P_PROVENANCE_compte_mord={'0' if bites1 else '1'}")
bites2 = not equal(va.COUNTED_10_1, {})
print(f"mutant_ligne_conditionnelle_retiree_mord={'0' if bites2 else '1'}")
derived = va.counted("inconclusif", "P_PROVENANCE")
print(f"derive_inconclusif_P_PROVENANCE={derived}")
print(f"derive_inconclusif_A_NO_ADMISSIBLE_CANDIDATE={va.counted('inconclusif', 'A_NO_ADMISSIBLE_CANDIDATE')}")
sys.exit(0 if ok and bites1 and bites2 and derived is False else 1)
PY
r=$?
echo "rc=$r" >> "$OUT"
exit $r
