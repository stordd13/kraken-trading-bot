"""C3b — producteur, temps 1 : le préfixe ``[début, T]`` de chaque candidat du manifeste.

Brief : ``agent/AGENT_C3B_PRODUCTEUR.md`` § « Lot 3 ». Outillage **hors chaîne** (§ L.1, ligne 0) : depuis le
manifeste **seul**, un run unique par candidat sur ``[début, T]``, ``T = manifest.anchor()`` recalculé (jamais un
paramètre), et les trois entrées que la chaîne lit :

* ``observations.json`` — ``{identité canonique: entrée}`` (``c3b_common.observation_entry``) ;
* ``coverage.json`` — l'artefact de couverture du § A.7 sur ``[début, T]`` ;
* ``candles.json`` — l'export de bougies du § L.1 que ``c3_benchmark`` lit ;

plus ``prefix_run.json``, la provenance, **à part** : aucun des trois fichiers lus par la chaîne n'en porte.

Ordre des contrôles — tout ce qui précède la lecture en base est pur, et un refus n'écrit rien :

1. ``--now`` (``cc.parse_now``) ; 2. manifeste (``cc.read_json`` + ``cc.load_manifest``, mêmes refus que la
   chaîne) ; 3. **garde-fou 6** (fenêtre au-delà du 2021-03-01 sans ``CAMPAIGN_UNLOCK``) ; 4. paramètres
   (``grid_levels`` entier, ``bias_1d`` fini) ; 5. ``decision_timeframes`` de chaque candidat ; 6. modèle de fees
   et coûts par paire ; 7. arbre git committé ; 8. répertoire de sortie (aucun artefact final déjà là, partiels
   du même manifeste et du même commit seulement) ; 9. ``DATABASE_URL`` puis lecture seule assertée, couverture
   et bougies ; 10. un job par candidat — ``engine.run`` appelé **une fois** ; 11. contrôles internes des
   entrées ; 12. écriture en deux temps (temporaires puis renommage).

Usage::

    poetry run python scripts/audit/c3b_prefix.py \\
        --manifest results/c3b_producteur/prefix_conformite/manifest.json \\
        --output-dir ~/runs/c3b_prefix/out/run1 --workers 4 --now 2026-09-28T00:00:00+00:00

Codes de sortie : 0 ok ; 2 refus d'entrée (rien de lancé ou rien d'écrit au-delà des partiels) ; 3 contrôle interne
en échec ou job en échec. Jamais les codes du § I.1, qui appartiennent à la chaîne.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import multiprocessing
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

from _common import git_provenance  # noqa: E402
from _db import ReadOnlyDatabaseManager  # noqa: E402
import c3_common as cc  # noqa: E402
import c3b_common as c3bc  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
import structlog  # noqa: E402

import krakenbot  # noqa: E402
from krakenbot.config.settings import get_settings  # noqa: E402

logger = structlog.get_logger()

PROJECT_ROOT = _ROOT
SCRIPT_RELPATH = "scripts/audit/c3b_prefix.py"
COMMON_RELPATH = "scripts/audit/c3b_common.py"
SCHEMA = "c3b_prefix_run/1"
OBSERVATIONS = "observations.json"
COVERAGE = "coverage.json"
CANDLES = "candles.json"
RUN = "prefix_run.json"
FINAL_ARTEFACTS: tuple[str, ...] = (OBSERVATIONS, COVERAGE, CANDLES, RUN)
PARTIAL_DIR = "partial"
#: Délai par job, comme le runner P7 (``run_p7_grid_search.py:99``, ``:916``) ; il ne remplace pas tmux.
JOB_TIMEOUT_S = 3600


@dataclass(frozen=True)
class RunContext:
    """Ce qu'un job reçoit (picklable pour ``spawn``) : le manifeste typé, ``T``, les coûts, l'URL."""

    manifest: cc.Manifest
    anchor: datetime
    pair_costs: Mapping[str, Any]
    url: str


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


async def _run_candidate(
    context: RunContext, candidate: cc.Candidate, decision_timeframes: Sequence[str]
) -> dict[str, Any]:
    """Un candidat : son gestionnaire de base en lecture seule, son moteur, **un seul** ``run(pair, début, T)``,
    puis l'export. ``get_settings()`` n'est que le porteur de configuration du moteur (comme le runner P7,
    ``:692``) ; l'URL de la base vient toujours de ``DATABASE_URL``."""
    settings = get_settings()
    db = ReadOnlyDatabaseManager(context.url)
    try:
        engine = c3bc.build_engine(settings, db, context.manifest, candidate, context.pair_costs)
        await engine.run(candidate.pair, context.manifest.window_start, context.anchor)
        return c3bc.export_engine(
            engine,
            manifest=context.manifest,
            candidate=candidate,
            anchor=context.anchor,
            decision_timeframes=decision_timeframes,
            pair_costs=context.pair_costs[candidate.pair],
        )
    finally:
        await db.close_db()


def run_job(
    context: RunContext, candidate: cc.Candidate, decision_timeframes: Sequence[str]
) -> dict[str, Any]:
    """Point d'entrée d'un worker (premier niveau, picklable). Rien ne remonte à travers le pool : toute
    exception devient un statut ``failed`` (même règle que ``run_p7_grid_search.run_single_backtest_job``)."""
    started = time.monotonic()
    try:
        entry = asyncio.run(_run_candidate(context, candidate, decision_timeframes))
    except BaseException as exc:  # noqa: BLE001 - un worker ne laisse rien remonter à travers le pool
        return {
            "status": "failed",
            "identity": candidate.identity,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    return {
        "status": "ok",
        "identity": candidate.identity,
        "entry": entry,
        "duration_s": round(time.monotonic() - started, 3),
    }


def _spawn_pool(workers: int) -> Any:
    return multiprocessing.get_context("spawn").Pool(processes=workers)


def run_jobs(
    context: RunContext,
    pending: Sequence[tuple[cc.Candidate, Sequence[str]]],
    *,
    workers: int,
    on_result: Callable[[dict[str, Any]], None],
    pool_factory: Callable[[int], Any] | None = None,
) -> None:
    """Les jobs, dans l'ordre donné (paire puis identité). ``workers == 1`` : dans le processus ; sinon un pool
    ``spawn`` (``apply_async`` puis ``get(timeout)``, comme le runner P7). L'ordre d'achèvement ne change pas la
    sortie : l'assemblage indexe par identité. La fabrique est résolue à l'appel (``_spawn_pool`` par défaut)."""
    if workers == 1:
        for candidate, timeframes in pending:
            on_result(run_job(context, candidate, timeframes))
        return
    factory = pool_factory if pool_factory is not None else _spawn_pool
    with factory(workers) as pool:
        handles = [
            (candidate, pool.apply_async(run_job, (context, candidate, timeframes)))
            for candidate, timeframes in pending
        ]
        for candidate, handle in handles:
            try:
                result = handle.get(timeout=JOB_TIMEOUT_S)
            except multiprocessing.TimeoutError:
                result = {
                    "status": "failed",
                    "identity": candidate.identity,
                    "error": f"délai de {JOB_TIMEOUT_S} s dépassé",
                    "traceback": "",
                }
            on_result(result)


def assemble(entries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """``observations.json`` : indexé par identité canonique (§ A.2), dans l'ordre des identités."""
    return {identity: dict(entries[identity]) for identity in sorted(entries)}


# ---------------------------------------------------------------------------
# Provenance et répertoire de sortie
# ---------------------------------------------------------------------------


def provenance() -> dict[str, Any]:
    """Le commit, la branche et le sha des deux scripts du producteur ; refus si l'un n'est pas suivi ou si
    l'arbre suivi n'est pas propre (``uncommitted_tree``, comme ``warmup_at``)."""
    script = git_provenance(SCRIPT_RELPATH)
    common = git_provenance(COMMON_RELPATH)
    return {
        "git_sha": script["git_sha"],
        "branch": script["branch"],
        "tracked_tree_clean": script["tracked_tree_clean"] and common["tracked_tree_clean"],
        "scripts": {
            SCRIPT_RELPATH: {
                "sha256": script["script_sha256"],
                "tracked": script["script_tracked"],
            },
            COMMON_RELPATH: {
                "sha256": common["script_sha256"],
                "tracked": common["script_tracked"],
            },
        },
    }


def read_partials(
    directory: Path, *, manifest_sha256: str, git_sha: str
) -> dict[str, dict[str, Any]]:
    """Les partiels d'une exécution interrompue, **seulement** s'ils portent le même sha de manifeste et le même
    commit : un partiel d'un autre manifeste ou d'un autre instrument est un refus, jamais une reprise."""
    partial_dir = directory / PARTIAL_DIR
    if not partial_dir.is_dir():
        return {}
    found: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for path in sorted(partial_dir.glob("*.json")):
        raw = cc.read_json(path)
        where = f"{PARTIAL_DIR}/{path.name}"
        try:
            recorded_manifest = cc.require_str(raw, "manifest_sha256", where=where)
            recorded_git = cc.require_str(raw, "git_sha", where=where)
            identity = cc.require_str(raw, "identity", where=where)
            cc.require_mapping(raw, "entry", where=where)
            cc.require_float(raw, "duration_s", where=where)
        except cc.MissingEvidenceError as exc:
            problems.append(str(exc))
            continue
        if recorded_manifest != manifest_sha256:
            problems.append(
                f"{where}: manifeste {recorded_manifest[:16]} != {manifest_sha256[:16]}"
            )
        if recorded_git != git_sha:
            problems.append(f"{where}: commit {recorded_git[:12]} != {git_sha[:12]}")
        found[identity] = dict(raw)
    if problems:
        raise c3bc.ProducerRefusal("partial_mismatch", problems)
    return found


# ---------------------------------------------------------------------------
# Lectures en base : couverture, dérivées, bougies
# ---------------------------------------------------------------------------


async def collect(url: str, manifest: cc.Manifest, anchor: datetime) -> dict[str, Any]:
    """Le seul endroit du processus principal qui touche la base, par un gestionnaire en lecture seule."""
    db = ReadOnlyDatabaseManager(url)
    try:
        probe = await c3bc.probe_database(db)
        start = manifest.window_start
        observed: dict[str, dict[int, list[datetime]]] = {}
        closes: dict[str, dict[str, Any]] = {}
        for pair in manifest.pairs:
            observed[pair] = {}
            for interval in cc.D1_INTERVALS:
                observed[pair][interval] = await c3bc.fetch_stamps(
                    db,
                    exchange=manifest.exchange,
                    pair=pair,
                    interval=interval,
                    start=start,
                    end=anchor,
                )
            closes[pair] = {
                "exec": await c3bc.fetch_closes(
                    db,
                    exchange=manifest.exchange,
                    pair=pair,
                    interval=manifest.exec_interval,
                    start=start,
                    end=anchor,
                ),
                "daily": await c3bc.fetch_closes(
                    db,
                    exchange=manifest.exchange,
                    pair=pair,
                    interval=c3bc.DAILY_INTERVAL,
                    start=start,
                    end=anchor,
                ),
            }
        derived = await c3bc.fetch_derived_stamps(
            db,
            exchange=manifest.exchange,
            pairs=manifest.pairs,
            intervals=cc.D1_INTERVALS,
            start=start,
            end=anchor,
        )
    finally:
        await db.close_db()
    return {"probe": probe, "observed": observed, "closes": closes, "derived": derived}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _workers(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("--workers doit être >= 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=_workers, default=1)
    parser.add_argument("--now", default=None, help="ISO UTC — n'entre que dans prefix_run.json")
    return parser


def _refuse(reason: str, problems: Sequence[str]) -> int:
    logger.error(reason, problems=list(problems))
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    # 1. --now
    try:
        now = cc.parse_now(args.now)
    except ValueError as exc:
        return _refuse("invalid_now", [str(exc)])
    # 2. manifeste — mêmes refus que la chaîne
    try:
        raw = cc.read_json(args.manifest)
    except (OSError, ValueError) as exc:
        return _refuse("manifest_unreadable", [f"{args.manifest}: {exc}"])
    try:
        manifest = cc.load_manifest(raw)
    except cc.NonFiniteValueError as exc:
        return _refuse("manifest_refused", [str(exc), *c3bc.non_finite_paths(raw)])
    except (cc.MissingEvidenceError, cc.InvalidValueError) as exc:
        return _refuse("manifest_refused", [str(exc)])
    anchor = manifest.anchor()
    # 3. garde-fou 6 — avant toute autre lecture de candidat
    if c3bc.campaign_window_locked(
        manifest.window_start, manifest.window_end, unlock=c3bc.CAMPAIGN_UNLOCK
    ):
        return _refuse(
            "campaign_window_locked",
            [
                f"fenêtre [{manifest.window_start.isoformat()}, {manifest.window_end.isoformat()}] au-delà "
                f"du {c3bc.CAMPAIGN_START.isoformat()} et {c3bc.CAMPAIGN_UNLOCK} absent (garde-fou 6)"
            ],
        )
    # 4. paramètres, 5. séries de décision, 6. fees et coûts
    param_problems = c3bc.validate_params([candidate.params for candidate in manifest.candidates])
    if param_problems:
        return _refuse("invalid_params", param_problems)
    try:
        timeframes = c3bc.decision_timeframes_by_candidate(manifest)
        c3bc.check_fee_model(manifest)
        pair_costs = c3bc.engine_pair_costs(manifest)
    except c3bc.ProducerRefusal as exc:
        return _refuse(exc.reason, exc.problems)
    # 7. arbre committé
    origin = provenance()
    untracked = [path for path, info in origin["scripts"].items() if info["tracked"] is not True]
    if untracked or origin["tracked_tree_clean"] is not True:
        return _refuse(
            "uncommitted_tree",
            [f"scripts non suivis {untracked}, arbre suivi propre {origin['tracked_tree_clean']}"],
        )
    # 8. répertoire de sortie
    manifest_sha256 = cc.file_sha256(args.manifest)
    present = [name for name in FINAL_ARTEFACTS if (args.output_dir / name).exists()]
    if present:
        return _refuse("output_dir_not_empty", [f"{args.output_dir}: {present} déjà présent(s)"])
    try:
        partials = read_partials(
            args.output_dir, manifest_sha256=manifest_sha256, git_sha=origin["git_sha"]
        )
    except c3bc.ProducerRefusal as exc:
        return _refuse(exc.reason, exc.problems)
    except (OSError, ValueError) as exc:
        return _refuse("partial_mismatch", [str(exc)])
    # 9. base : URL, lecture seule assertée, couverture et bougies
    load_dotenv(PROJECT_ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        return _refuse("database_url_missing", ["DATABASE_URL absente (jamais Settings())"])
    try:
        collected = asyncio.run(collect(url, manifest, anchor))
    except Exception as exc:  # noqa: BLE001 - base injoignable ou lecture seule non assertée = refus
        return _refuse("database_read_failed", [f"{type(exc).__name__}: {exc}"])
    try:
        coverage = c3bc.coverage_artefact(
            collected["observed"], collected["derived"], start=manifest.window_start, end=anchor
        )
        candles = c3bc.candles_artefact(
            collected["closes"],
            start=manifest.window_start,
            end=anchor,
            exec_interval=manifest.exec_interval,
        )
    except c3bc.ProducerRefusal as exc:
        return _refuse(exc.reason, exc.problems)
    except c3bc.ProducerControlError as exc:
        logger.error(exc.control, problems=exc.problems)
        return 3
    # 10. jobs
    context = RunContext(manifest=manifest, anchor=anchor, pair_costs=pair_costs, url=url)
    ordered = sorted(manifest.candidates, key=lambda c: (c.pair, c.identity))
    entries: dict[str, dict[str, Any]] = {}
    runs: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    for candidate in ordered:
        if candidate.identity in partials:
            partial = partials[candidate.identity]
            entries[candidate.identity] = dict(partial["entry"])
            runs[candidate.identity] = {"duration_s": partial["duration_s"], "resumed": True}
    pending = [
        (candidate, timeframes[candidate.identity])
        for candidate in ordered
        if candidate.identity not in entries
    ]

    def on_result(result: dict[str, Any]) -> None:
        identity = result["identity"]
        if result["status"] != "ok":
            failures.append(result)
            logger.error("job_failed", identity=identity, error=result["error"])
            return
        c3bc.write_json_atomic(
            args.output_dir / PARTIAL_DIR / f"{identity}.json",
            {
                "manifest_sha256": manifest_sha256,
                "git_sha": origin["git_sha"],
                "identity": identity,
                "entry": result["entry"],
                "duration_s": result["duration_s"],
            },
        )
        entries[identity] = result["entry"]
        runs[identity] = {"duration_s": result["duration_s"], "resumed": False}
        logger.info("job_done", identity=identity, duration_s=result["duration_s"])

    run_jobs(context, pending, workers=args.workers, on_result=on_result)
    if failures:
        logger.error("jobs_failed", failed=[f["identity"] for f in failures])
        for failure in failures:
            print(failure["traceback"], file=sys.stderr)
        return 3
    # 11. contrôles internes des entrées
    control_problems: list[str] = []
    for identity in sorted(entries):
        control_problems += c3bc.entry_controls(entries[identity], manifest=manifest, anchor=anchor)
    if control_problems:
        logger.error("entry_controls", problems=control_problems)
        return 3
    # 12. écriture en deux temps
    observations = assemble(entries)
    staged: list[tuple[Path, Path]] = []
    try:
        digests: dict[str, str] = {}
        for name, payload in (
            (OBSERVATIONS, observations),
            (COVERAGE, coverage),
            (CANDLES, candles),
        ):
            tmp, digests[name] = c3bc.stage_json(args.output_dir / name, payload)
            staged.append((tmp, args.output_dir / name))
        run_payload = {
            "schema": SCHEMA,
            "generated_at": now.isoformat(),
            "argv": list(sys.argv if argv is None else ["c3b_prefix.py", *argv]),
            "provenance": origin,
            "manifest": {
                "path": str(args.manifest),
                "sha256": manifest_sha256,
                "variant_key": cc.sig(raw),
            },
            "window": {
                "start": manifest.window_start.isoformat(),
                "end": manifest.window_end.isoformat(),
            },
            "anchor": anchor.isoformat(),
            "prefix_segment": manifest.prefix_segment,
            "database": {"url": c3bc.masked_url(url), **collected["probe"]},
            "environment": cc.replay_environment(),
            "interpreter": {"executable": sys.executable, "krakenbot": str(krakenbot.__file__)},
            "outputs": digests,
            "candidates": [
                {
                    "identity": candidate.identity,
                    "strategy": candidate.strategy,
                    "pair": candidate.pair,
                    "decision_timeframes": timeframes[candidate.identity],
                    **runs[candidate.identity],
                }
                for candidate in ordered
            ],
            "derived_stamps": {
                pair: {
                    str(interval): [stamp.isoformat() for stamp in stamps]
                    for interval, stamps in collected["derived"][pair].items()
                }
                for pair in sorted(collected["derived"])
            },
            "workers": args.workers,
        }
        tmp, run_digest = c3bc.stage_json(args.output_dir / RUN, run_payload)
        staged.append((tmp, args.output_dir / RUN))
    except (TypeError, ValueError) as exc:
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)
        logger.error("writer_refused", error=str(exc))
        return 3
    for tmp, final in staged:
        os.replace(tmp, final)
    for name, digest in (*digests.items(), (RUN, run_digest)):
        logger.info("written", path=str(args.output_dir / name), sha256=digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
