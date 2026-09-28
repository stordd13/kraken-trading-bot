"""C3b lot 4b — squelette pour le rouge-avant : ``c3b_evaluate.py`` au tip 4b, où **seules les fonctions nouvelles du
lot** lèvent ``NotImplementedError`` (le code du lot 4a, le parseur et ``main`` restent intacts). Jamais committé
comme code : il est écrit à la place du fichier le temps d'un passage de tests, puis le fichier est restauré et son
sha vérifié.

Usage : ``python make_skeleton_4b.py <source> <sortie>``
"""

import ast
from pathlib import Path
import sys

#: Les fonctions ajoutées par le lot 4b (plan § 2, « Fonctions nouvelles »).
NEW_4B = {
    "replay_inputs",
    "prefix_lambdas",
    "read_evaluation_closes",
    "evaluation_comparator",
    "evaluation_series",
    "f2_block",
    "evaluation_artefact",
    "sensitivity_payload",
}


class Strip(ast.NodeTransformer):
    def _strip(self, node):
        if node.name not in NEW_4B:
            return node
        doc = ast.get_docstring(node)
        body = [ast.Expr(ast.Constant(doc))] if doc else []
        body.append(
            ast.Raise(
                exc=ast.Call(
                    func=ast.Name("NotImplementedError", ast.Load()),
                    args=[ast.Constant("squelette rouge-avant 4b")],
                    keywords=[],
                ),
                cause=None,
            )
        )
        node.body = body
        return node

    def visit_FunctionDef(self, node):
        return self._strip(node)

    def visit_AsyncFunctionDef(self, node):
        return self._strip(node)


tree = Strip().visit(ast.parse(Path(sys.argv[1]).read_text(encoding="utf-8")))
ast.fix_missing_locations(tree)
stripped = sorted(
    n.name
    for n in ast.walk(tree)
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in NEW_4B
)
assert stripped == sorted(NEW_4B), stripped
Path(sys.argv[2]).write_text(
    "# ruff: noqa\n# SQUELETTE ROUGE-AVANT 4b — jamais committé\n" + ast.unparse(tree) + "\n",
    encoding="utf-8",
)
