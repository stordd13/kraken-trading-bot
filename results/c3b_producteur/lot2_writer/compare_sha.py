"""Compare deux rapports de ``probe_writer.py`` : mêmes écritures, mêmes sha256.

Usage : python compare_sha.py <avant.json> <apres.json> [<instables.json>]

Le troisième argument, facultatif, est un second rapport pris dans le **même état** que ``avant`` : les clés
dont le sha256 diffère entre ces deux-là sont instables d'un run à l'autre (horodatage non injecté), donc
hors d'état de prouver quoi que ce soit. Elles sont comptées, nommées, et exclues de l'égalité.
Code de sortie : 0 si toutes les écritures stables sont identiques, 1 sinon.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


def load(path: str) -> dict[str, dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    writes: dict[str, dict[str, Any]] = data["writes"]
    return writes


def main() -> int:
    before = load(sys.argv[1])
    after = load(sys.argv[2])
    unstable: set[str] = set()
    if len(sys.argv) > 3:
        twin = load(sys.argv[3])
        unstable = {
            key
            for key in before
            if key not in twin or twin[key].get("sha256") != before[key].get("sha256")
        }
        unstable |= set(twin) - set(before)
    missing = sorted(set(before) - set(after))
    extra = sorted(set(after) - set(before))
    refused = sorted(key for key, entry in after.items() if "refused" in entry)
    compared = sorted((set(before) & set(after)) - unstable)
    different = [key for key in compared if before[key].get("sha256") != after[key].get("sha256")]
    by_origin: dict[str, int] = {}
    for key in compared:
        origin = str(before[key]["origin"])
        by_origin[origin] = by_origin.get(origin, 0) + 1
    print(f"écritures avant={len(before)} après={len(after)}")
    print(f"instables d'un run à l'autre (exclues)={len(unstable)}")
    for key in sorted(unstable)[:20]:
        print("   instable :", key)
    print(f"comparées={len(compared)} par origine={by_origin}")
    print(
        f"absentes après={len(missing)} nouvelles après={len(extra)} refusées après={len(refused)}"
    )
    print(f"sha256 différents={len(different)}")
    for key in (missing + extra + refused + different)[:40]:
        print("   écart :", key)
    ok = not (missing or extra or refused or different)
    print("IDENTITÉ", "OK" if ok else "EN ÉCHEC")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
