"""Squelette pour le rouge-avant : mêmes imports, constantes, classes et signatures ; chaque corps de fonction
(module et méthodes hors __init__ des exceptions) lève NotImplementedError."""

import ast
from pathlib import Path
import sys

src = Path(sys.argv[1]).read_text()
tree = ast.parse(src)


class Strip(ast.NodeTransformer):
    def __init__(self):
        self.depth_class = []

    def visit_ClassDef(self, node):
        self.depth_class.append(node.name)
        self.generic_visit(node)
        self.depth_class.pop()
        return node

    def _strip(self, node):
        # garder __init__ des classes d'exception (constructions nécessaires aux tests d'import)
        if self.depth_class and node.name == "__init__":
            return node
        doc = ast.get_docstring(node)
        body = []
        if doc:
            body.append(ast.Expr(ast.Constant(doc)))
        body.append(
            ast.Raise(
                exc=ast.Call(
                    func=ast.Name("NotImplementedError", ast.Load()),
                    args=[ast.Constant("squelette rouge-avant")],
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


new = Strip().visit(tree)
ast.fix_missing_locations(new)
Path(sys.argv[2]).write_text(
    "# ruff: noqa\n# SQUELETTE ROUGE-AVANT — jamais committé\n" + ast.unparse(new) + "\n"
)
