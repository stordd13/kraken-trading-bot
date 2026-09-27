"""Helpers partagés des scripts d'audit — écriture JSON stricte, provenance git.

Brief : ``agent/AGENT_C3B_PRODUCTEUR.md`` § « Lot 2 ». Ce module est la **définition unique** de
``write_json_strict`` et de ``git_provenance`` : ``warmup_at`` et ``reconstruct_1w`` en portaient chacun une
copie, qui ne différaient que par le chemin du script haché.

Module **pur** : bibliothèque standard seule, aucun import ``krakenbot`` ni ``sqlalchemy``, aucun effet de bord à
l'import. La chaîne C3 l'importe (``c3_common``) ; ce qui touche la base vit dans ``_db.py``, que la chaîne
n'importe jamais.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Sorties
# ---------------------------------------------------------------------------


def write_json_strict(path: Path, payload: Any) -> str:
    """JSON indenté, clés triées, **sans** ``default`` : une valeur non native lève (dette 22)."""
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Provenance git
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def git_provenance(script_relpath: str, *, root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """L'en-tête de provenance d'un script : le commit, la branche, et le sha256 **du script nommé**.

    ``script_relpath`` est relatif à ``root`` (la racine du dépôt) ; c'est lui qui est haché et dont le suivi
    par git est vérifié. L'appelant refuse (``uncommitted_tree``, code 2) quand ``script_tracked`` ou
    ``tracked_tree_clean`` est faux : le git sha d'un en-tête doit être réel.
    """
    script = root / script_relpath
    return {
        "git_sha": _git(root, "rev-parse", "HEAD").stdout.strip(),
        "branch": _git(root, "branch", "--show-current").stdout.strip(),
        "script": script_relpath,
        "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        "script_tracked": _git(root, "ls-files", "--error-unmatch", script_relpath).returncode == 0,
        "tracked_tree_clean": _git(
            root, "status", "--porcelain", "--untracked-files=no"
        ).stdout.strip()
        == "",
    }
