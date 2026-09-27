"""``scripts/audit/_common.py`` et ``scripts/audit/_db.py`` — helpers partagés des scripts d'audit (C3b lot 2).

Brief : ``agent/AGENT_C3B_PRODUCTEUR.md`` § « Lot 2 ». Dette 22 : ``PROJECT_CONTEXT.md`` § 9. Décisions du 2026-09-27 :
``_common`` reste pur et ``ReadOnlyDatabaseManager`` vit dans ``_db`` ; une clé de dictionnaire qui n'est pas une
``str`` est refusée ; ``parse_now`` et ``read_json`` restent ceux de ``c3_common``. Les attendus viennent du texte,
appui cité dans chaque test — jamais de l'implémentation. Aucun test ne touche la base.
"""

# ruff: noqa: E402
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import ModuleType
from typing import Any

import pytest
import structlog

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts" / "audit"))

import _common as ac
import _db as adb
import reconstruct_1w as r1w
import warmup_at as wa

from krakenbot.core.database import DatabaseManager

#: Les en-têtes de provenance **publiés** par les deux scripts avant le lot 2 — la forme à conserver.
PUBLISHED_HEADERS = (
    "results/sol_d2_1w_modes/warmup_2021-03-01.json",
    "results/reconstruction_1w_2022_2025/check_report.json",
    "results/reconstruction_1w_2022_2025/write_report.json",
)
#: Où chaque définition partagée a le droit d'exister (brief § Lot 2, critère de fin ; ``_db`` : décision du 27/09).
SINGLE_DEFINITIONS = {
    "git_provenance": "scripts/audit/_common.py",
    "write_json_strict": "scripts/audit/_common.py",
    "ReadOnlyDatabaseManager": "scripts/audit/_db.py",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        [
            "git",
            "-c",
            "user.name=lot2",
            "-c",
            "user.email=lot2@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Un dépôt git jetable : deux scripts suivis, un commit, tree propre."""
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    _git(root, "init", "--quiet")
    _git(root, "checkout", "--quiet", "-b", "lot2")
    (root / "scripts" / "a.py").write_bytes(b"A = 1\n")
    (root / "scripts" / "b.py").write_bytes(b"B = 2\n")
    _git(root, "add", "scripts/a.py", "scripts/b.py")
    _git(root, "commit", "--quiet", "-m", "init")
    return root


# ---------------------------------------------------------------------------
# git_provenance
# ---------------------------------------------------------------------------


def test_git_provenance_hashes_the_script_it_is_given(repo: Path) -> None:
    """Brief § Lot 2 : « ``git_provenance(script_path)`` paramétrée par le chemin haché (les deux copies
    divergeaient là) » — le sha256 est celui du script nommé, pas d'un script fixe."""
    first = ac.git_provenance("scripts/a.py", root=repo)
    second = ac.git_provenance("scripts/b.py", root=repo)
    assert first["script"] == "scripts/a.py"
    assert second["script"] == "scripts/b.py"
    assert first["script_sha256"] == _sha256(b"A = 1\n")
    assert second["script_sha256"] == _sha256(b"B = 2\n")
    assert first["git_sha"] == second["git_sha"] == _git(repo, "rev-parse", "HEAD")
    assert first["branch"] == "lot2"


def test_provenance_keys_are_those_of_the_published_headers(repo: Path) -> None:
    """La forme ne change pas : les clés sont celles des en-têtes que les deux scripts ont publiés, moins
    ``provisional`` que chaque ``main`` ajoute après coup (``warmup_at.py``, ``reconstruct_1w.py`` : « en-tête
    marqué provisoire »)."""
    produced = set(ac.git_provenance("scripts/a.py", root=repo))
    for relpath in PUBLISHED_HEADERS:
        published = json.loads((_PROJECT_ROOT / relpath).read_text(encoding="utf-8"))["provenance"]
        assert set(published) - {"provisional"} == produced, relpath


def test_a_clean_tree_is_clean_and_a_dirty_tree_is_not(repo: Path) -> None:
    """Docstrings des deux scripts : « le tree **suivi** doit être propre et le script committé, pour que le git
    sha de l'en-tête soit réel ». Un fichier non suivi ne salit pas le tree suivi ; une modification d'un fichier
    suivi le salit, même si ce n'est pas le script haché ; un script non suivi n'est pas committé."""
    clean = ac.git_provenance("scripts/a.py", root=repo)
    assert clean["script_tracked"] is True
    assert clean["tracked_tree_clean"] is True

    (repo / "scripts" / "c.py").write_bytes(b"C = 3\n")
    assert ac.git_provenance("scripts/a.py", root=repo)["tracked_tree_clean"] is True
    untracked = ac.git_provenance("scripts/c.py", root=repo)
    assert untracked["script_tracked"] is False
    assert untracked["script_sha256"] == _sha256(b"C = 3\n")

    (repo / "scripts" / "b.py").write_bytes(b"B = 20\n")
    dirty = ac.git_provenance("scripts/a.py", root=repo)
    assert dirty["script_tracked"] is True
    assert dirty["tracked_tree_clean"] is False


@pytest.mark.parametrize(
    ("module", "argv", "relpath"),
    [
        (wa, [], "scripts/audit/warmup_at.py"),
        (r1w, ["check"], "scripts/audit/reconstruct_1w.py"),
    ],
    ids=["warmup_at", "reconstruct_1w"],
)
def test_a_dirty_tree_is_refused_as_uncommitted_tree(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    argv: list[str],
    relpath: str,
) -> None:
    """Brief § Lot 2 : « ``git_provenance`` sur un arbre sale → ``uncommitted_tree`` ». Codes de sortie des deux
    scripts : « 2 usage, […] tree non propre […] — rien n'est écrit ». Chaque script passe **son** chemin
    (liste close du brief), c'est ce qui était écrit en dur dans chaque copie."""
    (repo / "scripts" / "b.py").write_bytes(b"B = 20\n")
    dirty = ac.git_provenance("scripts/a.py", root=repo)
    asked: list[str] = []

    def provenance(script_relpath: str) -> dict[str, Any]:
        asked.append(script_relpath)
        return dict(dirty)

    monkeypatch.setattr(module, "git_provenance", provenance)
    output = tmp_path / "out" / "artefact.json"
    with structlog.testing.capture_logs() as logs:
        code = module.main([*argv, "--output", str(output)])
    assert code == 2
    assert asked == [relpath]
    assert [entry["event"] for entry in logs] == ["uncommitted_tree"]
    assert not output.parent.exists()


# ---------------------------------------------------------------------------
# Une définition, un seul endroit
# ---------------------------------------------------------------------------


def test_the_scripts_use_the_shared_objects() -> None:
    """Brief § Lot 2 : « ``warmup_at`` et ``reconstruct_1w`` sans copie locale »."""
    assert wa.git_provenance is ac.git_provenance
    assert wa.write_json_strict is ac.write_json_strict
    assert wa.ReadOnlyDatabaseManager is adb.ReadOnlyDatabaseManager
    assert r1w.git_provenance is ac.git_provenance
    assert r1w.write_json_strict is ac.write_json_strict


def test_each_shared_definition_exists_in_one_place() -> None:
    """Critère de fin du lot 2 : « grep : aucune définition de ``git_provenance`` / ``write_json_strict`` /
    ``ReadOnlyDatabaseManager`` hors ``_common.py`` » — amendé le 27/09 : la classe vit dans ``_db.py``."""
    names = "|".join(SINGLE_DEFINITIONS)
    pattern = re.compile(rf"^[ \t]*(?:async[ \t]+def|def|class)[ \t]+({names})\b", re.MULTILINE)
    found: dict[str, list[str]] = {name: [] for name in SINGLE_DEFINITIONS}
    for folder in ("scripts", "src", "tests", "results"):
        for path in sorted((_PROJECT_ROOT / folder).rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in pattern.finditer(text):
                found[match.group(1)].append(path.relative_to(_PROJECT_ROOT).as_posix())
    assert found == {name: [where] for name, where in SINGLE_DEFINITIONS.items()}


# ---------------------------------------------------------------------------
# ReadOnlyDatabaseManager
# ---------------------------------------------------------------------------


def test_read_only_manager_asks_postgres_for_read_only_transactions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``warmup_at.py`` (conventions) : « lecture seule **garantie par Postgres** (``default_transaction_read_only
    = on`` posé à la connexion) ». Le manager est celui que les chargeurs du moteur attendent, déjà initialisé."""
    url = "postgresql+asyncpg://reader:secret@localhost:5433/krakenbot"
    engine = object()
    factory = object()
    seen: dict[str, Any] = {}

    def create_engine(target: str, **kwargs: Any) -> object:
        seen["url"] = target
        seen["engine_kwargs"] = kwargs
        return engine

    def sessionmaker(**kwargs: Any) -> object:
        seen["factory_kwargs"] = kwargs
        return factory

    monkeypatch.setattr(adb, "create_async_engine", create_engine)
    monkeypatch.setattr(adb, "async_sessionmaker", sessionmaker)
    manager = adb.ReadOnlyDatabaseManager(url)
    assert isinstance(manager, DatabaseManager)
    assert seen["url"] == url
    assert seen["engine_kwargs"] == {
        "connect_args": {"server_settings": {"default_transaction_read_only": "on"}}
    }
    assert seen["factory_kwargs"]["bind"] is engine
    assert manager.engine is engine
    assert manager.session_factory is factory


# ---------------------------------------------------------------------------
# Pureté à l'import
# ---------------------------------------------------------------------------


def _import_probe(module: str) -> dict[str, Any]:
    """Importe ``module`` dans un interpréteur neuf ; rend ce qu'il a chargé et ce qu'il a changé à l'environnement."""
    probe = (
        "import importlib, json, os, sys\n"
        "root = sys.argv[1]\n"
        "sys.path[:0] = [root + '/scripts/audit', root + '/scripts', root + '/src', root]\n"
        "before = dict(os.environ)\n"
        "importlib.import_module(sys.argv[2])\n"
        "print(json.dumps({\n"
        "    'environ': sorted(k for k in os.environ if before.get(k) != os.environ[k]),\n"
        "    'modules': sorted(sys.modules),\n"
        "}))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    proc = subprocess.run(
        [sys.executable, "-c", probe, str(_PROJECT_ROOT), module],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    loaded: dict[str, Any] = json.loads(proc.stdout.strip().splitlines()[-1])
    return loaded


def _loaded(modules: list[str], package: str) -> list[str]:
    return [name for name in modules if name == package or name.startswith(package + ".")]


def test_common_is_pure_at_import() -> None:
    """Décision du 27/09 : « ``_common.py`` pur » — bibliothèque standard seule, et la règle B4.2 (rien n'est
    changé à l'environnement à l'import)."""
    loaded = _import_probe("_common")
    assert loaded["environ"] == []
    for package in ("krakenbot", "sqlalchemy", "structlog", "numpy", "_db"):
        assert _loaded(loaded["modules"], package) == [], package
