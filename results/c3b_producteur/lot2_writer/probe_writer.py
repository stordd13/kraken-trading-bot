"""Sonde du lot 2 — ce que les 932 tests C3 écrivent, par quel writer, avec quels types.

Lecture seule pour le dépôt : la sonde enveloppe ``c3_common.write_json`` et ``rejeu_common.write_json`` en mémoire,
laisse l'écriture se faire telle quelle, puis relève pour chaque fichier écrit son sha256 et, pour chaque payload,
les valeurs qui ne sont pas d'un type JSON exact. Elle n'écrit que son propre rapport.

Usage : python probe_writer.py <rapport.json> <basetemp>

``basetemp`` est passé à pytest (``--basetemp``) pour que les chemins temporaires, que certains artefacts
recopient, soient identiques d'un run à l'autre. La clé d'une écriture est ``test | rang | nom du fichier`` :
elle ne dépend d'aucun numéro de ligne, donc elle survit à une édition des fichiers de test.
"""

from __future__ import annotations

import collections
import glob
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(ROOT / "scripts" / "audit"),
    str(ROOT / "scripts"),
    str(ROOT / "src"),
    str(ROOT),
]

import c3_common as cc  # noqa: E402
import pytest  # noqa: E402
import rejeu_common as rc  # noqa: E402

EXACT_SCALARS = (str, int, float, bool, type(None))

writes: dict[str, dict[str, Any]] = {}
findings: collections.Counter[tuple[str, str, str, str, str]] = collections.Counter()
calls: collections.Counter[tuple[str, str, str]] = collections.Counter()
state: dict[str, Any] = {"node": "?", "rank": 0}


def walk(value: Any, path: str, out: list[tuple[str, str]]) -> None:
    kind = type(value)
    if kind in EXACT_SCALARS:
        if kind is float and not math.isfinite(value):
            out.append((path, "float non fini"))
        return
    if isinstance(value, dict):
        if kind is not dict:
            out.append((path, f"sous-type de dict {kind.__module__}.{kind.__name__}"))
        for key, item in value.items():
            if type(key) is not str:
                out.append((path, f"clé {type(key).__module__}.{type(key).__name__}"))
            walk(item, f"{path}.{key}" if path else str(key), out)
        return
    if isinstance(value, (list, tuple)):
        if kind not in (list, tuple):
            out.append((path, f"sous-type de séquence {kind.__module__}.{kind.__name__}"))
        for index, item in enumerate(value):
            walk(item, f"{path}[{index}]", out)
        return
    out.append((path, f"{kind.__module__}.{kind.__name__}"))


def recorder(original: Any, via: str) -> Any:
    def probe(path: Any, payload: Any) -> Any:
        frame = sys._getframe(1)
        source = Path(frame.f_code.co_filename)
        origin = "test" if "tests" in source.parts else "production"
        caller = f"{source.name}:{frame.f_code.co_name}"
        calls[(origin, caller, via)] += 1
        found: list[tuple[str, str]] = []
        walk(payload, "", found)
        for where, kind in found:
            findings[(origin, caller, via, re.sub(r"\[\d+\]", "[*]", where), kind)] += 1
        state["rank"] += 1
        key = f"{state['node']} | {state['rank']:03d} | {Path(path).name}"
        entry: dict[str, Any] = {"origin": origin, "caller": caller, "via": via}
        try:
            result = original(path, payload)
        except (TypeError, ValueError) as exc:
            entry["refused"] = f"{type(exc).__name__}: {exc}"
            writes[key] = entry
            raise
        entry["sha256"] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        writes[key] = entry
        return result

    return probe


class Plugin:
    def pytest_runtest_setup(self, item: Any) -> None:
        state["node"] = item.nodeid
        state["rank"] = 0


def main() -> int:
    report = Path(sys.argv[1])
    basetemp = Path(sys.argv[2])
    rc_original = rc.write_json
    cc_original = cc.write_json
    rc.write_json = recorder(rc_original, "rc")
    cc.write_json = recorder(cc_original, "cc")
    files = sorted(glob.glob(str(ROOT / "tests" / "test_scripts" / "test_c3_*.py")))
    code = pytest.main(
        [*files, "-q", "--no-header", "-p", "no:cacheprovider", f"--basetemp={basetemp}"],
        plugins=[Plugin()],
    )
    payload = {
        "pytest_exit": int(code),
        "cc_write_json_is_rc_write_json": cc_original is rc_original,
        "n_writes": len(writes),
        "n_tests_writing": len({key.split(" | ")[0] for key in writes}),
        "calls": [
            {"origin": origin, "caller": caller, "via": via, "n": n}
            for (origin, caller, via), n in sorted(calls.items())
        ],
        "findings": [
            {"origin": origin, "caller": caller, "via": via, "path": where, "kind": kind, "n": n}
            for (origin, caller, via, where, kind), n in sorted(findings.items())
        ],
        "writes": writes,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"pytest_exit={int(code)} écritures={len(writes)} constats={len(findings)}")
    for row in payload["findings"]:
        print("  ", row)
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
