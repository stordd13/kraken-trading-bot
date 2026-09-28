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
import math
from pathlib import Path
import subprocess
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Sorties
# ---------------------------------------------------------------------------


#: Les scalaires JSON, au **type exact** : un sous-type (``numpy.float64`` est un ``float``) n'en est pas un.
_JSON_SCALARS: tuple[type, ...] = (str, int, bool, type(None))
_ROOT_LABEL = "<racine>"


def _type_name(kind: type) -> str:
    module = kind.__module__
    return kind.__qualname__ if module == "builtins" else f"{module}.{kind.__qualname__}"


def _refuse(value: Any) -> Any:
    """Le ``default`` de ``json.dumps``. ``_check`` a déjà tout refusé : il n'est atteint que si le parcours et
    l'encodeur divergent, et alors il lève au lieu de convertir."""
    raise TypeError(f"type {_type_name(type(value))} non JSON")


def _check(value: Any, path: str) -> None:
    """Lève en nommant le chemin (``a.b[3].c``) de la première valeur que JSON ne sait pas écrire telle quelle."""
    kind = type(value)
    where = path or _ROOT_LABEL
    if kind is float:
        if not math.isfinite(value):
            raise ValueError(f"{where}: flottant non fini ({value!r}) — JSON n'a ni NaN ni infini")
        return
    if kind in _JSON_SCALARS:
        return
    if kind is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError(
                    f"{where}: clé {key!r} de type {_type_name(type(key))} — une clé JSON est une "
                    "str, conversion explicite exigée au site d'écriture"
                )
            _check(item, f"{path}.{key}" if path else key)
        return
    if kind is list or kind is tuple:
        for index, item in enumerate(value):
            _check(item, f"{path}[{index}]")
        return
    raise TypeError(
        f"{where}: type {_type_name(kind)} non JSON — conversion explicite exigée au site d'écriture"
    )


def write_json_strict(path: Path, payload: Any) -> str:
    """Écrit du JSON indenté à clés triées et rend le sha256 du texte écrit (dette 22).

    Le payload est parcouru **avant** toute écriture, en types exacts : ``str``, ``int``, ``float``, ``bool``,
    ``None``, ``dict`` à clés ``str``, ``list`` et ``tuple``. Tout autre type, sous-types compris (``Decimal``,
    ``datetime``, tout type numpy), lève ``TypeError`` ; un flottant non fini lève ``ValueError``. Le message
    commence par le chemin de la valeur. La conversion (``Decimal`` → ``str``, ``datetime`` → ISO) se fait au
    site d'écriture, jamais ici. Sur refus rien n'est créé, pas même le répertoire.

    Sur un payload JSON pur, le texte est celui de ``rejeu_common.write_json`` : la forme ne change pas.
    """
    _check(payload, "")
    encoded = (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            default=_refuse,
        )
        + "\n"
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
