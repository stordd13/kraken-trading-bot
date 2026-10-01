#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 — le schéma des observations, TIRÉ DU CODE À S1 par l'AST, et
# épinglé à sa copie SCHEMA dans le corps Python de tests/diagnostic_entry.sh (règle agent 3 : recopié, épinglé).
# Définition : les clés que c3_entry lit sur les observations — deuxième argument des accesseurs `cc.require_*`,
# `cc.nullable_*`, `cc.optional_*` dans les fonctions qui lisent les observations (méthodes de Context, _liquidation_form,
# _segment_form, a01_form, a02_d5, a03_bounds, a04_identities, a06_warmup, a08_d2), et des accesseurs de
# c3_common.warmup_sufficient, qu'elles appellent sur les blocs d'amorçage. a07_coverage (artefact de couverture) et main
# (manifeste, ancre) n'en sont pas. Une clé est : un littéral ; une variable de boucle `for` sur un tuple ou une liste
# de littéraux ou de f-chaînes résolubles ; une f-chaîne résoluble par des liaisons locales constantes (`base = "base"`).
# Toute autre clé est une donnée (identité, segment, série) : listée « dynamique », jamais un champ.
# Le contrôle naît adverse : la copie SCHEMA privée d'une clé, puis augmentée d'une clé étrangère, doit le faire échouer.
# Sortie : schema_observations.out ; rc=0 ssi l'extraction égale la copie et les deux mutants mordent.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid/tests/schema_observations.out
SRC=results/c3_campagne_grid/tests/diagnostic_entry.sh
T=$(mktemp -d) || exit 2
sed -n "/<<'PYEOF'\$/,/^PYEOF\$/p" "$SRC" | sed '1d;$d' > "$T/body.py"
: > "$OUT"
echo "# schema_observations — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
python3 - "$T/body.py" >> "$OUT" 2>&1 <<'PY'
import ast
import re
import sys

ACCESSOR = re.compile(r"(require|nullable|optional)_[a-z_]+")
TARGETS = {
    "scripts/audit/c3_entry.py": {
        "entry", "matched_candidate", "decision_timeframes", "_liquidation_form", "_segment_form", "a01_form",
        "a02_d5", "a03_bounds", "a04_identities", "a06_warmup", "a08_d2",
    },
    "scripts/audit/c3_common.py": {"warmup_sufficient"},
}


def accessor_name(func):
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "cc":
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def resolve(node, env):
    """Une clé en chaîne si elle est résoluble statiquement, sinon None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name) and value.value.id in env:
                parts.append(env[value.value.id])
            else:
                return None
        return "".join(parts)
    return None


keys, dynamic = set(), set()
for path, names in TARGETS.items():
    tree = ast.parse(open(path, encoding="utf-8").read())
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or fn.name not in names:
            continue
        env, loops = {}, {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                value = resolve(node.value, env)
                if value is not None:
                    env[node.targets[0].id] = value
        for node in ast.walk(fn):
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and isinstance(node.iter, (ast.Tuple, ast.List)):
                loops[node.target.id] = [resolve(element, env) for element in node.iter.elts]
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call) or len(node.args) < 2:
                continue
            name = accessor_name(node.func)
            if name is None or not ACCESSOR.fullmatch(name):
                continue
            arg = node.args[1]
            if isinstance(arg, ast.Name) and arg.id in loops:
                for value in loops[arg.id]:
                    (keys.add(value) if value is not None else dynamic.add(f"{fn.name}:{arg.id}"))
                continue
            value = resolve(arg, env)
            if value is not None:
                keys.add(value)
            else:
                dynamic.add(f"{fn.name}:{ast.unparse(arg)}")

body = ast.parse(open(sys.argv[1], encoding="utf-8").read())
copy = None
for node in body.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SCHEMA" for t in node.targets):
        copy = ast.literal_eval(node.value)
copy_set = set(copy or ())
print(f"schema_extrait_n={len(keys)}")
print("schema_extrait=" + ",".join(sorted(keys)))
print("cles_dynamiques=" + ",".join(sorted(dynamic)))
print(f"copie_n={len(copy_set)} copie_triee={'0' if copy is not None and list(copy) == sorted(copy) else '1'} "
      f"copie_sans_doublon={'0' if copy is not None and len(copy) == len(copy_set) else '1'}")
print(f"copie_moins_extrait={','.join(sorted(copy_set - keys)) or '-'}")
print(f"extrait_moins_copie={','.join(sorted(keys - copy_set)) or '-'}")
ok = copy is not None and copy_set == keys and list(copy) == sorted(copy) and len(copy) == len(copy_set)
print(f"copie_egale_extrait={'0' if ok else '1'}")
some = sorted(keys)[0]
bites1 = (copy_set - {some}) != keys
bites2 = (copy_set | {"zz_cle_etrangere"}) != keys
print(f"mutant_cle_retiree_mord={'0' if bites1 else '1'} mutant_cle_ajoutee_mord={'0' if bites2 else '1'}")
sys.exit(0 if ok and bites1 and bites2 else 1)
PY
r=$?
rm -rf "$T"
echo "rc=$r" >> "$OUT"
exit $r
