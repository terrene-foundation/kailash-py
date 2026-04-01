# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dashboard server -- Starlette ASGI app serving API + embedded HTML UI.

Provides JSON API endpoints backed by ExperimentTracker and ModelRegistry
engines, plus a single-page HTML dashboard at ``/``.

Both ``starlette`` and ``uvicorn`` are lazy-imported (available via kailash
core dependencies).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["create_app", "DashboardApp"]

# ---------------------------------------------------------------------------
# Template directory
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).parent / "templates"


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def _json_response(
    data: Any,
    status_code: int = 200,
) -> Any:
    """Return a Starlette JSONResponse."""
    from starlette.responses import JSONResponse

    return JSONResponse(data, status_code=status_code)


def _error_response(message: str, status_code: int = 400) -> Any:
    """Return a JSON error response."""
    return _json_response({"error": message}, status_code=status_code)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


async def _index(request: Any) -> Any:
    """Serve the main dashboard HTML page."""
    from starlette.responses import HTMLResponse

    html_path = _TEMPLATE_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


async def _list_experiments(request: Any) -> Any:
    """GET /api/experiments -- list all experiments with run counts."""
    tracker = request.app.state.tracker

    experiments = await tracker.list_experiments()
    result = []
    for exp in experiments:
        # Count runs per experiment
        try:
            runs = await tracker.list_runs(exp.name)
            run_count = len(runs)
            latest_run_status = runs[0].status if runs else None
        except Exception:
            run_count = 0
            latest_run_status = None

        entry = exp.to_dict()
        entry["run_count"] = run_count
        entry["latest_run_status"] = latest_run_status
        result.append(entry)

    return _json_response(result)


async def _list_runs(request: Any) -> Any:
    """GET /api/experiments/{name}/runs -- list runs for an experiment."""
    from kailash_ml.engines.experiment_tracker import ExperimentNotFoundError

    tracker = request.app.state.tracker
    name = request.path_params["name"]

    try:
        runs = await tracker.list_runs(name)
    except ExperimentNotFoundError:
        return _error_response(f"Experiment '{name}' not found.", 404)

    return _json_response([r.to_dict() for r in runs])


async def _get_run(request: Any) -> Any:
    """GET /api/runs/{run_id} -- get run details."""
    from kailash_ml.engines.experiment_tracker import RunNotFoundError

    tracker = request.app.state.tracker
    run_id = request.path_params["run_id"]

    try:
        run = await tracker.get_run(run_id)
    except RunNotFoundError:
        return _error_response(f"Run '{run_id}' not found.", 404)

    return _json_response(run.to_dict())


async def _get_metric_history(request: Any) -> Any:
    """GET /api/runs/{run_id}/metrics/{key} -- metric history for charts."""
    from kailash_ml.engines.experiment_tracker import RunNotFoundError

    tracker = request.app.state.tracker
    run_id = request.path_params["run_id"]
    key = request.path_params["key"]

    try:
        history = await tracker.get_metric_history(run_id, key)
    except RunNotFoundError:
        return _error_response(f"Run '{run_id}' not found.", 404)

    return _json_response([m.to_dict() for m in history])


async def _compare_runs(request: Any) -> Any:
    """GET /api/compare?run_ids=id1,id2,id3 -- compare runs."""
    from kailash_ml.engines.experiment_tracker import RunNotFoundError

    tracker = request.app.state.tracker
    run_ids_param = request.query_params.get("run_ids", "")
    if not run_ids_param:
        return _error_response("Missing 'run_ids' query parameter.", 400)

    run_ids = [rid.strip() for rid in run_ids_param.split(",") if rid.strip()]
    if len(run_ids) < 2:
        return _error_response("At least 2 run IDs required for comparison.", 400)

    try:
        comparison = await tracker.compare_runs(run_ids)
    except RunNotFoundError as exc:
        return _error_response(str(exc), 404)

    return _json_response(comparison.to_dict())


async def _delete_run(request: Any) -> Any:
    """DELETE /api/runs/{run_id} -- delete a run."""
    from kailash_ml.engines.experiment_tracker import RunNotFoundError

    tracker = request.app.state.tracker
    run_id = request.path_params["run_id"]

    try:
        await tracker.delete_run(run_id)
    except RunNotFoundError:
        return _error_response(f"Run '{run_id}' not found.", 404)

    return _json_response({"deleted": run_id})


async def _list_models(request: Any) -> Any:
    """GET /api/models -- list registered models."""
    registry = request.app.state.registry
    if registry is None:
        return _json_response([])

    models = await registry.list_models()
    # list_models returns list[dict] already
    return _json_response(models)


async def _list_model_versions(request: Any) -> Any:
    """GET /api/models/{name}/versions -- model version history."""
    from kailash_ml.engines.model_registry import ModelNotFoundError

    registry = request.app.state.registry
    if registry is None:
        return _error_response("Model registry not configured.", 404)

    name = request.path_params["name"]

    try:
        versions = await registry.get_model_versions(name)
    except ModelNotFoundError:
        return _error_response(f"Model '{name}' not found.", 404)

    return _json_response([v.to_dict() for v in versions])


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    tracker: Any,
    registry: Any | None = None,
) -> Any:
    """Create the Starlette ASGI application.

    Parameters
    ----------
    tracker:
        An initialized :class:`~kailash_ml.engines.experiment_tracker.ExperimentTracker`.
    registry:
        An optional :class:`~kailash_ml.engines.model_registry.ModelRegistry`.

    Returns
    -------
    starlette.applications.Starlette
        The ASGI application.
    """
    from starlette.applications import Starlette
    from starlette.routing import Route

    routes = [
        Route("/", _index, methods=["GET"]),
        Route("/api/experiments", _list_experiments, methods=["GET"]),
        Route("/api/experiments/{name:path}/runs", _list_runs, methods=["GET"]),
        Route("/api/runs/{run_id}", _get_run, methods=["GET"]),
        Route(
            "/api/runs/{run_id}/metrics/{key:path}",
            _get_metric_history,
            methods=["GET"],
        ),
        Route("/api/runs/{run_id}", _delete_run, methods=["DELETE"]),
        Route("/api/compare", _compare_runs, methods=["GET"]),
        Route("/api/models", _list_models, methods=["GET"]),
        Route(
            "/api/models/{name:path}/versions", _list_model_versions, methods=["GET"]
        ),
    ]

    app = Starlette(routes=routes)
    app.state.tracker = tracker
    app.state.registry = registry

    return app


# ---------------------------------------------------------------------------
# DashboardApp -- high-level wrapper
# ---------------------------------------------------------------------------


class DashboardApp:
    """Convenience wrapper that owns ConnectionManager + engines + Starlette app.

    This is used by :class:`~kailash_ml.dashboard.MLDashboard` to create the
    full application stack from a database URL.
    """

    def __init__(
        self,
        db_url: str,
        artifact_root: str = "./mlartifacts",
    ) -> None:
        self._db_url = db_url
        self._artifact_root = artifact_root
        self._conn: Any | None = None
        self._tracker: Any | None = None
        self._registry: Any | None = None
        self._app: Any | None = None

    async def initialize(self) -> None:
        """Initialize database connection, engines, and Starlette app."""
        from kailash.db.connection import ConnectionManager
        from kailash_ml.engines.experiment_tracker import ExperimentTracker
        from kailash_ml.engines.model_registry import ModelRegistry

        self._conn = ConnectionManager(self._db_url)
        await self._conn.initialize()

        self._tracker = ExperimentTracker(self._conn, artifact_root=self._artifact_root)
        self._registry = ModelRegistry(self._conn)

        self._app = create_app(self._tracker, self._registry)

    @property
    def app(self) -> Any:
        """The Starlette ASGI application. Available after ``initialize()``."""
        if self._app is None:
            raise RuntimeError("DashboardApp not initialized. Call initialize() first.")
        return self._app

    @property
    def tracker(self) -> Any:
        """The ExperimentTracker engine."""
        if self._tracker is None:
            raise RuntimeError("DashboardApp not initialized. Call initialize() first.")
        return self._tracker

    @property
    def registry(self) -> Any:
        """The ModelRegistry engine."""
        if self._registry is None:
            raise RuntimeError("DashboardApp not initialized. Call initialize() first.")
        return self._registry

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
