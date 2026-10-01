#!/bin/bash
# C3 racine du registre, lot 1 (repris de results/c3_outillage_v2_3/tests/non_divulgation.sh, plan D8) — non-divulgation
# (§ A.6 v2.3 : l'empreinte différée « n'est jamais imprimée hors registre » ; runbook § 4 : ni contenu, ni digest, ni
# taille du registre) : contrôle STATIQUE, complément des contrôles comportementaux (X3, N2, N3 ; T1, T2-chaîne).
# Par l'AST des trois modules du lot (scripts/audit/c3_common.py, c3_anchor.py, c3_verdict.py), au fichier entier :
#  1. aucune valeur interpolée — champ `{…}` d'une f-string, argument de `%` ou de `.format` — dont l'expression nomme
#     l'évaluation différée ou son descripteur (identifiant qui contient `deferred` ou `descriptor` — convention de
#     nommage du lot : tout objet qui porte l'empreinte ou le descripteur a l'un de ces deux mots dans son nom ; le
#     triplet du verdict v2.2, `inscription`, n'en fait pas partie ; exceptions nommées, publiques par construction :
#     `deferred_evaluation_date`, la date déclarée au manifeste, et `DEFERRED_MIN_DAYS`, la borne de 365 jours) : un
#     message peut dire « l'empreinte n'est pas celle inscrite », jamais la porter ;
#  2. aucune impression du digest du registre (D13, décision de Bruno du 30/09) : aucun appel `print` dont une valeur
#     interpolée nomme à la fois le registre et un digest (`registry` et `digest` ou `sha`) ;
#  3. aucun appel de journalisation (`logging`, `structlog`, `logger`, `log.`) dans ces modules ;
#  4. (plan D8) les lignes AJOUTÉES depuis 313eb00 aux trois modules (`git diff -U0`) ne contiennent ni `print(`, ni appel
#     de journalisation, ni interpolation (préfixe f-string, `.format(`, `%` sur une chaîne) : le passthrough de la racine
#     ne dit rien de la racine, dans aucun message.
# Usage : bash non_divulgation.sh <étiquette>. Sortie : non_divulgation_<étiquette>.out ; rc=0 ssi aucun site.
set -o pipefail
set -u
unset VIRTUAL_ENV
LABEL="${1:?étiquette}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_racine_registre/tests/non_divulgation_${LABEL}.out
{
  echo "# non_divulgation — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
  echo "# fichiers suivis modifiés (non commités) : $(git status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
} > "$OUT"
python3 - >> "$OUT" <<'PY'
import ast
import re
import sys

FILES = ["scripts/audit/c3_common.py", "scripts/audit/c3_anchor.py", "scripts/audit/c3_verdict.py"]
DEFERRED = re.compile(r"deferred|descriptor", re.IGNORECASE)
PUBLIC = {"deferred_evaluation_date", "DEFERRED_MIN_DAYS"}
REGISTRY = re.compile(r"registry", re.IGNORECASE)
DIGEST = re.compile(r"digest|sha", re.IGNORECASE)
LOGGING = re.compile(r"^(logging|structlog|logger|log)$")


def names(node: ast.AST) -> list[str]:
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            out.append(sub.id)
        elif isinstance(sub, ast.Attribute):
            out.append(sub.attr)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str) and sub is not node:
            out.append(sub.value)
    return out


def interpolated(node: ast.AST) -> list[ast.AST]:
    """Les expressions interpolées d'un nœud : champs d'f-string, opérande droite d'un `%` sur chaîne, arguments de
    `.format`."""
    found = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.FormattedValue):
            found.append(sub.value)
        elif isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Mod) and isinstance(sub.left, (ast.Constant, ast.JoinedStr)):
            found.append(sub.right)
        elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "format":
            found.extend(sub.args)
            found.extend(k.value for k in sub.keywords)
    return found


bad = 0
seen: set[tuple[str, int, str]] = set()


def report(kind: str, path: str, line: int, what: list[str]) -> None:
    global bad
    key = (kind, path, line)
    if key not in seen:
        seen.add(key)
        print(f"{kind} {path}:{line} {sorted(set(what))}")
    bad = 1


for path in FILES:
    tree = ast.parse(open(path, encoding="utf-8").read())
    n_f = n_print = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            n_f += 1
        for expr in interpolated(node) if isinstance(node, (ast.JoinedStr, ast.BinOp, ast.Call)) else []:
            hits = [n for n in names(expr) if DEFERRED.search(n) and n not in PUBLIC]
            if hits:
                report("interpolation_differee", path, expr.lineno, hits)
        if isinstance(node, ast.Call):
            func = node.func
            fname = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            base = func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else ""
            if LOGGING.match(base) or LOGGING.match(fname):
                report("journalisation", path, node.lineno, [f"{base}.{fname}"])
            if fname == "print":
                n_print += 1
                for arg in node.args:
                    for expr in interpolated(arg) + ([arg] if not isinstance(arg, (ast.Constant, ast.JoinedStr)) else []):
                        ids = names(expr)
                        if any(REGISTRY.search(i) for i in ids) and any(DIGEST.search(i) for i in ids):
                            report("digest_du_registre_imprime", path, node.lineno, ids)
    print(f"module {path} : f-strings={n_f} print={n_print}")
# 4. lignes ajoutées depuis la base (plan D8)
import subprocess

BASE = "313eb00c2019b98cf20fb81ac8327f7b9d1e920a"
ADDED_BAD = re.compile(
    r"\bprint\(|\b(logging|structlog|logger|log)\.|(^|[^A-Za-z0-9_])[rRbB]?[fF][rRbB]?[\"']|\.format\(|[\"']\s*%\s*[\w(]"
)
diff = subprocess.run(["git", "diff", "-U0", BASE, "--", *FILES], capture_output=True, text=True, check=True).stdout
n_added = 0
current = ""
for line in diff.splitlines():
    if line.startswith("+++ "):
        current = line[6:] if line.startswith("+++ b/") else line[4:]
        continue
    if not line.startswith("+"):
        continue
    n_added += 1
    code = line[1:]
    if code.lstrip().startswith("#"):
        continue
    if ADDED_BAD.search(code):
        report("ligne_ajoutee_qui_imprime_ou_interpole", current, 0, [code.strip()[:120]])
print(f"lignes_ajoutees_depuis_313eb00={n_added}")
print(f"sites={len(seen)}")
sys.exit(bad)
PY
rc=$?
echo "rc=$rc" >> "$OUT"
exit $rc
