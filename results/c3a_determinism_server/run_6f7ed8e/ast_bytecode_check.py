"""Executable-equivalence proof for a Python module at two revisions.

Compares the two files with every docstring (module, class, function) stripped: AST dump, then
module bytecode compiled from that stripped AST. Exit 0 when both are identical, 1 otherwise.
Used at the C3a pre-merge gate (§ L.5) for scripts/audit/c3_verdict.py, 2b62530 vs 6f7ed8e:
commit acaeaf6 changed docstrings and one comment only.
"""

import ast
import hashlib
import sys


def strip(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            first = body[0] if body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return tree


def main(path_a: str, path_b: str) -> int:
    with open(path_a, encoding="utf-8") as fa, open(path_b, encoding="utf-8") as fb:
        src_a, src_b = fa.read(), fb.read()
    tree_a, tree_b = strip(ast.parse(src_a)), strip(ast.parse(src_b))
    dump_a = ast.dump(tree_a, include_attributes=False)
    dump_b = ast.dump(tree_b, include_attributes=False)
    code_a = compile(tree_a, "<a>", "exec").co_code
    code_b = compile(tree_b, "<b>", "exec").co_code
    print(f"file A: {path_a}  sha256(src)={hashlib.sha256(src_a.encode()).hexdigest()[:16]}")
    print(f"file B: {path_b}  sha256(src)={hashlib.sha256(src_b.encode()).hexdigest()[:16]}")
    print(f"AST without docstrings identical : {dump_a == dump_b}")
    print(f"  sha256(AST A) = {hashlib.sha256(dump_a.encode()).hexdigest()[:16]}")
    print(f"  sha256(AST B) = {hashlib.sha256(dump_b.encode()).hexdigest()[:16]}")
    print(f"module bytecode (co_code) identical : {code_a == code_b}")
    return 0 if (dump_a == dump_b and code_a == code_b) else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: ast_bytecode_check.py <file_at_rev_A> <file_at_rev_B>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
