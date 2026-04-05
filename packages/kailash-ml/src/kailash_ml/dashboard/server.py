# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dashboard server -- Starlette ASGI app serving API + embedded HTML UI.

Provides JSON API endpoints backed by ExperimentTracker and ModelRegistry
engines, plus a single-page HTML dashboard at ``/``.

Both ``starlette`` and ``uvicorn`` are lazy-imported (available via kailash
core dependencies).
"""
from __future__ import annotations

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


async def _overview(request: Any) -> Any:
    """GET /api/overview -- aggregate stats for the overview dashboard."""
    tracker = request.app.state.tracker
    registry = request.app.state.registry
    feature_store = request.app.state.feature_store
    drift_monitor = request.app.state.drift_monitor

    stats: dict[str, Any] = {
        "total_experiments": 0,
        "total_runs": 0,
        "running_runs": 0,
        "completed_runs": 0,
        "failed_runs": 0,
        "total_models": 0,
        "production_models": 0,
        "total_features": 0,
        "drift_alerts": 0,
        "active_drift_monitors": 0,
    }

    try:
        experiments = await tracker.list_experiments()
        stats["total_experiments"] = len(experiments)
        for exp in experiments:
            try:
                runs = await tracker.list_runs(exp.name)
                stats["total_runs"] += len(runs)
                for r in runs:
                    status = r.status.upper() if r.status else ""
                    if status == "RUNNING":
                        stats["running_runs"] += 1
                    elif status == "COMPLETED":
                        stats["completed_runs"] += 1
                    elif status == "FAILED":
                        stats["failed_runs"] += 1
            except Exception:
                pass
    except Exception:
        logger.debug("Failed to count experiments/runs for overview.", exc_info=True)

    if registry is not None:
        try:
            models = await registry.list_models()
            stats["total_models"] = len(models)
            for model in models:
                try:
                    versions = await registry.get_model_versions(model["name"])
                    for v in versions:
                        if v.stage == "production":
                            stats["production_models"] += 1
                except Exception:
                    pass
        except Exception:
            logger.debug("Failed to count models for overview.", exc_info=True)

    if feature_store is not None:
        try:
            schemas = await feature_store.list_schemas()
            stats["total_features"] = len(schemas)
        except Exception:
            logger.debug("Failed to count features for overview.", exc_info=True)

    if drift_monitor is not None:
        try:
            stats["active_drift_monitors"] = len(drift_monitor.active_schedules)
        except Exception:
            logger.debug("Failed to count drift monitors for overview.", exc_info=True)

    return _json_response(stats)


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
    except RunNotFoundError:
        return _error_response("One or more run IDs not found.", 404)

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


async def _list_features(request: Any) -> Any:
    """GET /api/features -- list all registered feature schemas."""
    feature_store = request.app.state.feature_store
    if feature_store is None:
        return _json_response([])

    try:
        schemas = await feature_store.list_schemas()
    except Exception:
        logger.exception("Failed to list feature schemas.")
        return _error_response("Internal server error", 500)

    return _json_response(schemas)


async def _get_drift_history(request: Any) -> Any:
    """GET /api/drift/{model_name} -- drift report history for a model."""
    drift_monitor = request.app.state.drift_monitor
    if drift_monitor is None:
        return _json_response([])

    model_name = request.path_params["model_name"]

    try:
        limit = max(1, min(int(request.query_params.get("limit", "50")), 1000))
    except (ValueError, TypeError):
        return _error_response("Invalid 'limit' parameter.", 400)

    try:
        history = await drift_monitor.get_drift_history(model_name, limit=limit)
    except Exception:
        logger.exception("Failed to get drift history.")
        return _error_response("Internal server error", 500)

    return _json_response(history)


async def _list_drift_models(request: Any) -> Any:
    """GET /api/drift -- list models with drift monitoring data."""
    drift_monitor = request.app.state.drift_monitor
    if drift_monitor is None:
        return _json_response([])

    try:
        active = drift_monitor.active_schedules
    except Exception:
        active = []

    # Get all models from registry that might have drift data
    registry = request.app.state.registry
    model_names: list[str] = []
    if registry is not None:
        try:
            models = await registry.list_models()
            model_names = [m["name"] for m in models]
        except Exception:
            pass

    # Add active monitors that might not be in registry
    for name in active:
        if name not in model_names:
            model_names.append(name)

    result = []
    for name in model_names:
        entry: dict[str, Any] = {
            "model_name": name,
            "active_monitoring": name in active,
            "latest_report": None,
        }
        try:
            history = await drift_monitor.get_drift_history(name, limit=1)
            if history:
                entry["latest_report"] = history[0]
        except Exception:
            pass
        result.append(entry)

    return _json_response(result)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    tracker: Any,
    registry: Any | None = None,
    feature_store: Any | None = None,
    drift_monitor: Any | None = None,
) -> Any:
    """Create the Starlette ASGI application.

    Parameters
    ----------
    tracker:
        An initialized :class:`~kailash_ml.engines.experiment_tracker.ExperimentTracker`.
    registry:
        An optional :class:`~kailash_ml.engines.model_registry.ModelRegistry`.
    feature_store:
        An optional :class:`~kailash_ml.engines.feature_store.FeatureStore`.
    drift_monitor:
        An optional :class:`~kailash_ml.engines.drift_monitor.DriftMonitor`.

    Returns
    -------
    starlette.applications.Starlette
        The ASGI application.
    """
    from starlette.applications import Starlette
    from starlette.routing import Route

    routes = [
        Route("/", _index, methods=["GET"]),
        Route("/api/overview", _overview, methods=["GET"]),
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
        Route("/api/features", _list_features, methods=["GET"]),
        Route("/api/drift", _list_drift_models, methods=["GET"]),
        Route("/api/drift/{model_name:path}", _get_drift_history, methods=["GET"]),
    ]

    app = Starlette(routes=routes)
    app.state.tracker = tracker
    app.state.registry = registry
    app.state.feature_store = feature_store
    app.state.drift_monitor = drift_monitor

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
        self._feature_store: Any | None = None
        self._drift_monitor: Any | None = None
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

        # Initialize optional engines -- feature store and drift monitor share
        # the same connection but are only available when their tables exist.
        try:
            from kailash_ml.engines.feature_store import FeatureStore

            self._feature_store = FeatureStore(self._conn)
            await self._feature_store.initialize()
        except Exception:
            logger.debug("FeatureStore not available for dashboard.", exc_info=True)
            self._feature_store = None

        try:
            from kailash_ml.engines.drift_monitor import DriftMonitor

            self._drift_monitor = DriftMonitor(self._conn)
        except Exception:
            logger.debug("DriftMonitor not available for dashboard.", exc_info=True)
            self._drift_monitor = None

        self._app = create_app(
            self._tracker,
            self._registry,
            self._feature_store,
            self._drift_monitor,
        )

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
        if self._drift_monitor is not None:
            try:
                await self._drift_monitor.shutdown()
            except Exception:
                pass
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
