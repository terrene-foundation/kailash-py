# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Plotly-based views for the kailash-ml dashboard.

Each view function in ``kailash_ml.dashboard.views`` renders a plotly
figure as JSON. The top-level ``build_plotly_view_routes`` attaches those
renderers as Starlette routes on ``app``. This module intentionally
separates "data fetch" (from the tracker / registry via
:mod:`kailash_ml.dashboard.views`) from "HTTP glue" (Starlette routes).

Views delivered per W28 invariants:
  - Runs — list + filter by tenant / experiment
  - Metrics — per-run line chart
  - Params — table
  - Artifacts — downloadable links
  - Models — versions + aliases
  - Serving — handle health (degrades gracefully when W25 not merged)

Every view applies the tenant filter captured on ``app.state.tenant_id``
per ``rules/tenant-isolation.md`` §1.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from kailash_ml.dashboard.views import (
    render_artifacts_view,
    render_metrics_view,
    render_models_view,
    render_params_view,
    render_runs_view,
    render_serving_view,
)

logger = logging.getLogger(__name__)

__all__ = ["build_plotly_view_routes", "render_plotly_view"]


# ---------------------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------------------


def _json_response(payload: Any, status_code: int = 200) -> Any:
    """Return a Starlette ``JSONResponse`` with a plotly-safe encoder."""
    from starlette.responses import JSONResponse

    return JSONResponse(payload, status_code=status_code)


def _effective_tenant_id(request: Any) -> str | None:
    """Resolve the tenant_id for THIS request per spec §3.1 + §10.

    Precedence:
      1. Explicit ``?tenant_id=`` query param (only honored when the
         dashboard was constructed without a pinned tenant_id, or when
         the values match — prevents cross-tenant query escalation).
      2. The dashboard instance's pinned ``tenant_id`` (CLI flag, kwarg).
      3. Ambient ``kailash_ml.tracking.get_current_tenant_id()`` — the
         contextvar set by the active ``km.track(...)`` scope.

    Per ``rules/tenant-isolation.md`` §1, tenant filtering applies to
    every view regardless of whether the backing tables carry a
    ``tenant_id`` column yet; views MUST filter in-memory on the
    ``Run.tags["tenant_id"]`` projection when the storage schema does
    not yet expose the dimension natively.
    """
    pinned = getattr(request.app.state, "tenant_id", None)
    if pinned is not None:
        explicit = request.query_params.get("tenant_id")
        if explicit is not None and explicit != pinned:
            # Honor pinned — cross-tenant escalation attempts return 403
            return None  # caller will raise
        return pinned

    explicit = request.query_params.get("tenant_id")
    if explicit:
        return explicit

    try:
        from kailash_ml.tracking import get_current_tenant_id

        ambient = get_current_tenant_id()
        if ambient:
            return ambient
    except Exception:
        logger.debug("mldashboard.tenant.ambient_unavailable", exc_info=True)

    return None


def _assert_tenant_access(request: Any) -> tuple[bool, Any]:
    """Enforce pinned-tenant access. Returns ``(ok, error_response)``."""
    pinned = getattr(request.app.state, "tenant_id", None)
    explicit = request.query_params.get("tenant_id")
    if pinned is not None and explicit is not None and explicit != pinned:
        from starlette.responses import JSONResponse

        return False, JSONResponse(
            {
                "error": "tenant_mismatch",
                "message": (
                    "request tenant_id does not match dashboard's pinned "
                    "tenant scope"
                ),
            },
            status_code=403,
        )
    return True, None


# ---------------------------------------------------------------------------
# Plotly view renderer
# ---------------------------------------------------------------------------


def render_plotly_view(view_name: str, fig_dict: dict[str, Any]) -> dict[str, Any]:
    """Wrap a plotly figure dict for the dashboard's view envelope.

    Output schema::

        {"view": "runs", "figure": {plotly json}, "tenant_id": "...",
         "rendered_at": "<iso8601>"}

    The HTML shell fetches ``/view/<name>`` and renders
    ``response.figure`` via ``plotly.js``.
    """
    from datetime import datetime, timezone

    return {
        "view": view_name,
        "figure": fig_dict,
        "rendered_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Route handlers — each delegates to kailash_ml.dashboard.views
# ---------------------------------------------------------------------------


async def _runs_view(request: Any) -> Any:
    ok, err = _assert_tenant_access(request)
    if not ok:
        return err

    tenant_id = _effective_tenant_id(request)
    experiment = request.query_params.get("experiment")

    tracker = request.app.state.tracker
    try:
        fig = await render_runs_view(
            tracker, tenant_id=tenant_id, experiment=experiment
        )
    except Exception as exc:
        logger.exception("mldashboard.runs_view.error")
        return _json_response(
            {"error": "view_failed", "message": str(exc)}, status_code=500
        )

    payload = render_plotly_view("runs", fig)
    payload["tenant_id"] = tenant_id
    return _json_response(payload)


async def _metrics_view(request: Any) -> Any:
    ok, err = _assert_tenant_access(request)
    if not ok:
        return err

    tenant_id = _effective_tenant_id(request)
    run_id = request.path_params.get("run_id")
    if not run_id:
        return _json_response(
            {"error": "missing_run_id", "message": "run_id path parameter required"},
            status_code=400,
        )

    tracker = request.app.state.tracker
    try:
        fig = await render_metrics_view(tracker, run_id=run_id, tenant_id=tenant_id)
    except KeyError:
        return _json_response(
            {"error": "run_not_found", "run_id": run_id}, status_code=404
        )
    except Exception as exc:
        logger.exception("mldashboard.metrics_view.error")
        return _json_response(
            {"error": "view_failed", "message": str(exc)}, status_code=500
        )

    payload = render_plotly_view("metrics", fig)
    payload["tenant_id"] = tenant_id
    payload["run_id"] = run_id
    return _json_response(payload)


async def _params_view(request: Any) -> Any:
    ok, err = _assert_tenant_access(request)
    if not ok:
        return err

    tenant_id = _effective_tenant_id(request)
    run_id = request.path_params.get("run_id")
    if not run_id:
        return _json_response(
            {"error": "missing_run_id", "message": "run_id path parameter required"},
            status_code=400,
        )

    tracker = request.app.state.tracker
    try:
        fig = await render_params_view(tracker, run_id=run_id, tenant_id=tenant_id)
    except KeyError:
        return _json_response(
            {"error": "run_not_found", "run_id": run_id}, status_code=404
        )
    except Exception as exc:
        logger.exception("mldashboard.params_view.error")
        return _json_response(
            {"error": "view_failed", "message": str(exc)}, status_code=500
        )

    payload = render_plotly_view("params", fig)
    payload["tenant_id"] = tenant_id
    payload["run_id"] = run_id
    return _json_response(payload)


async def _artifacts_view(request: Any) -> Any:
    ok, err = _assert_tenant_access(request)
    if not ok:
        return err

    tenant_id = _effective_tenant_id(request)
    run_id = request.path_params.get("run_id")
    if not run_id:
        return _json_response(
            {"error": "missing_run_id", "message": "run_id path parameter required"},
            status_code=400,
        )

    tracker = request.app.state.tracker
    try:
        result = await render_artifacts_view(
            tracker, run_id=run_id, tenant_id=tenant_id
        )
    except KeyError:
        return _json_response(
            {"error": "run_not_found", "run_id": run_id}, status_code=404
        )
    except Exception as exc:
        logger.exception("mldashboard.artifacts_view.error")
        return _json_response(
            {"error": "view_failed", "message": str(exc)}, status_code=500
        )

    # Artifacts view returns a list of downloadable-link rows, not a plotly
    # figure — wrap in a non-figure envelope so the shell renders as a
    # table instead of a plot.
    return _json_response(
        {
            "view": "artifacts",
            "tenant_id": tenant_id,
            "run_id": run_id,
            "artifacts": result["artifacts"],
        }
    )


async def _models_view(request: Any) -> Any:
    ok, err = _assert_tenant_access(request)
    if not ok:
        return err

    tenant_id = _effective_tenant_id(request)
    registry = getattr(request.app.state, "registry", None)
    if registry is None:
        return _json_response(
            {
                "view": "models",
                "tenant_id": tenant_id,
                "models": [],
                "note": "model registry not configured",
            }
        )

    try:
        result = await render_models_view(registry, tenant_id=tenant_id)
    except Exception as exc:
        logger.exception("mldashboard.models_view.error")
        return _json_response(
            {"error": "view_failed", "message": str(exc)}, status_code=500
        )

    return _json_response(
        {"view": "models", "tenant_id": tenant_id, "models": result["models"]}
    )


async def _serving_view(request: Any) -> Any:
    ok, err = _assert_tenant_access(request)
    if not ok:
        return err

    tenant_id = _effective_tenant_id(request)
    inference = getattr(request.app.state, "inference_server", None)

    try:
        result = await render_serving_view(inference, tenant_id=tenant_id)
    except Exception as exc:
        logger.exception("mldashboard.serving_view.error")
        return _json_response(
            {"error": "view_failed", "message": str(exc)}, status_code=500
        )

    return _json_response(
        {
            "view": "serving",
            "tenant_id": tenant_id,
            "available": result["available"],
            "handles": result["handles"],
            "note": result.get("note", ""),
        }
    )


# ---------------------------------------------------------------------------
# Route attachment
# ---------------------------------------------------------------------------


def build_plotly_view_routes() -> list[Any]:
    """Build the Starlette routes that expose plotly-rendered views.

    The routes are mounted under ``/view/<name>`` to keep them clearly
    separated from the raw JSON API at ``/api/...`` (which is consumed
    by the single-page shell directly). Both surfaces coexist:

      - ``/api/runs``                     — raw JSON (existing)
      - ``/view/runs``                    — plotly-rendered figure JSON
      - ``/view/runs/<id>/metrics``       — plotly line chart
      - ``/view/runs/<id>/params``        — plotly table
      - ``/view/runs/<id>/artifacts``     — artifact link list
      - ``/view/models``                  — model registry table
      - ``/view/serving``                 — serve-handle health
    """
    from starlette.routing import Route

    return [
        Route("/view/runs", _runs_view, methods=["GET"]),
        Route("/view/runs/{run_id}/metrics", _metrics_view, methods=["GET"]),
        Route("/view/runs/{run_id}/params", _params_view, methods=["GET"]),
        Route("/view/runs/{run_id}/artifacts", _artifacts_view, methods=["GET"]),
        Route("/view/models", _models_view, methods=["GET"]),
        Route("/view/serving", _serving_view, methods=["GET"]),
    ]
