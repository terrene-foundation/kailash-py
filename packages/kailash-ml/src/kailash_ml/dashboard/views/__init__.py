# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Per-view renderers for the kailash-ml dashboard.

Each function returns a plotly figure dict (or, for non-plot views like
artifacts/models/serving, a plain dict) consumed by
:mod:`kailash_ml.dashboard.app`. Data fetch goes through the
``AbstractTrackerStore`` / ``ModelRegistry`` facades — no raw SQL.

Tenant filter applied to every view per ``rules/tenant-isolation.md`` §1:
runs whose ``tags['tenant_id']`` does not match the ``tenant_id`` kwarg
are excluded in-memory. When ``tenant_id is None`` every run is visible
(used for global-admin / tenantless contexts only).

Per W28 invariant 7, six views ship:

  * ``render_runs_view``     — list + experiment filter
  * ``render_metrics_view``  — per-run line chart
  * ``render_params_view``   — per-run table
  * ``render_artifacts_view``— per-run downloadable list (not plotly)
  * ``render_models_view``   — registry versions + aliases (not plotly)
  * ``render_serving_view``  — serve-handle health; degrades when W25
                               not wired (``available=False``).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "render_runs_view",
    "render_metrics_view",
    "render_params_view",
    "render_artifacts_view",
    "render_models_view",
    "render_serving_view",
]


# ---------------------------------------------------------------------------
# Tenant filter helper
# ---------------------------------------------------------------------------


async def _filter_by_tenant(
    tracker: Any, runs: list[dict[str, Any]], tenant_id: Optional[str]
) -> list[dict[str, Any]]:
    """Restrict ``runs`` to those whose tenant tag matches ``tenant_id``.

    When ``tenant_id is None`` the caller has not pinned a tenant scope
    — return the input unchanged (admin surface). Otherwise look up each
    run's ``tags['tenant_id']`` through ``tracker.list_tags`` and keep
    only matches.
    """
    if tenant_id is None:
        return runs
    filtered: list[dict[str, Any]] = []
    for run in runs:
        run_id = run.get("run_id") or run.get("id")
        if run_id is None:
            continue
        try:
            tags = await tracker.list_tags(str(run_id))
        except Exception:
            logger.debug("mldashboard.tags.unavailable", extra={"run_id": str(run_id)})
            continue
        if tags.get("tenant_id") == tenant_id:
            filtered.append(run)
    return filtered


# ---------------------------------------------------------------------------
# Runs view — bar of run_count per status
# ---------------------------------------------------------------------------


async def render_runs_view(
    tracker: Any,
    *,
    tenant_id: Optional[str],
    experiment: Optional[str] = None,
) -> dict[str, Any]:
    """Return a plotly bar-chart figure: run count per ``status``."""
    runs = await tracker.list_runs(experiment=experiment)
    runs = await _filter_by_tenant(tracker, runs, tenant_id)

    status_counts: dict[str, int] = {}
    for r in runs:
        st = str(r.get("status") or "UNKNOWN")
        status_counts[st] = status_counts.get(st, 0) + 1

    statuses = sorted(status_counts.keys())
    counts = [status_counts[s] for s in statuses]

    return {
        "data": [
            {
                "type": "bar",
                "x": statuses,
                "y": counts,
                "name": "runs",
            }
        ],
        "layout": {
            "title": f"Runs by status"
            + (f" — experiment={experiment}" if experiment else ""),
            "xaxis": {"title": "status"},
            "yaxis": {"title": "count"},
        },
    }


# ---------------------------------------------------------------------------
# Metrics view — per-run line chart
# ---------------------------------------------------------------------------


async def render_metrics_view(
    tracker: Any, *, run_id: str, tenant_id: Optional[str]
) -> dict[str, Any]:
    """Return a plotly line figure for every metric emitted by ``run_id``."""
    run = await tracker.get_run(run_id)
    if run is None:
        raise KeyError(run_id)

    if tenant_id is not None:
        tags = await tracker.list_tags(run_id)
        if tags.get("tenant_id") != tenant_id:
            raise KeyError(run_id)  # tenant-scoped 404

    metrics_rows = await tracker.list_metrics(run_id)

    # Partition metrics by key: {key: [(step, value), ...]}
    series: dict[str, list[tuple[int, float]]] = {}
    for row in metrics_rows:
        key = str(row.get("key") or row.get("name") or "")
        if not key:
            continue
        step = int(row.get("step") or 0)
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            continue
        series.setdefault(key, []).append((step, value))

    traces: list[dict[str, Any]] = []
    for key, points in series.items():
        points.sort()
        traces.append(
            {
                "type": "scatter",
                "mode": "lines+markers",
                "name": key,
                "x": [p[0] for p in points],
                "y": [p[1] for p in points],
            }
        )

    return {
        "data": traces,
        "layout": {
            "title": f"Metrics — run {run_id}",
            "xaxis": {"title": "step"},
            "yaxis": {"title": "value"},
        },
    }


# ---------------------------------------------------------------------------
# Params view — table
# ---------------------------------------------------------------------------


async def render_params_view(
    tracker: Any, *, run_id: str, tenant_id: Optional[str]
) -> dict[str, Any]:
    """Return a plotly table figure of the run's params."""
    run = await tracker.get_run(run_id)
    if run is None:
        raise KeyError(run_id)

    if tenant_id is not None:
        tags = await tracker.list_tags(run_id)
        if tags.get("tenant_id") != tenant_id:
            raise KeyError(run_id)

    params = run.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    keys = sorted(params.keys())
    values = [str(params[k]) for k in keys]

    return {
        "data": [
            {
                "type": "table",
                "header": {"values": ["param", "value"]},
                "cells": {"values": [keys, values]},
            }
        ],
        "layout": {"title": f"Params — run {run_id}"},
    }


# ---------------------------------------------------------------------------
# Artifacts view — downloadable link list (NOT plotly)
# ---------------------------------------------------------------------------


async def render_artifacts_view(
    tracker: Any, *, run_id: str, tenant_id: Optional[str]
) -> dict[str, Any]:
    """Return a list of artifact rows (path, size, sha256, uri)."""
    run = await tracker.get_run(run_id)
    if run is None:
        raise KeyError(run_id)

    if tenant_id is not None:
        tags = await tracker.list_tags(run_id)
        if tags.get("tenant_id") != tenant_id:
            raise KeyError(run_id)

    rows = await tracker.list_artifacts(run_id)
    artifacts = [
        {
            "path": r.get("path") or r.get("name"),
            "size": r.get("size_bytes") or r.get("size"),
            "sha256": r.get("sha256"),
            "uri": r.get("uri") or r.get("artifact_uri"),
        }
        for r in rows
    ]
    return {"artifacts": artifacts}


# ---------------------------------------------------------------------------
# Models view — registry versions + aliases (NOT plotly)
# ---------------------------------------------------------------------------


async def render_models_view(
    registry: Any, *, tenant_id: Optional[str]
) -> dict[str, Any]:
    """Return a list of models with their versions + aliases.

    Calls ``registry.list_models(tenant_id=...)`` when available; falls
    back to an empty list when the registry surface does not expose the
    enumeration method yet (degraded mode).
    """
    list_fn = getattr(registry, "list_models", None)
    if list_fn is None:
        logger.debug("mldashboard.models_view.degraded_no_list_models")
        return {"models": []}

    try:
        models = await list_fn(tenant_id=tenant_id)
    except TypeError:
        # Older registries don't accept tenant_id kwarg.
        models = await list_fn()

    out: list[dict[str, Any]] = []
    for m in models or []:
        out.append(
            {
                "name": (
                    m.get("name") if isinstance(m, dict) else getattr(m, "name", "")
                ),
                "versions": (
                    m.get("versions")
                    if isinstance(m, dict)
                    else getattr(m, "versions", [])
                ),
                "aliases": (
                    m.get("aliases")
                    if isinstance(m, dict)
                    else getattr(m, "aliases", {})
                ),
            }
        )
    return {"models": out}


# ---------------------------------------------------------------------------
# Serving view — handle health
# ---------------------------------------------------------------------------


async def render_serving_view(
    inference: Any, *, tenant_id: Optional[str]
) -> dict[str, Any]:
    """Return inference-server handle health.

    Degrades gracefully when W25 (``kailash_ml.serving.server``) has not
    wired the app's ``inference_server`` attribute — the dashboard shell
    hides the Serving panel when ``available=False``.
    """
    if inference is None:
        return {
            "available": False,
            "handles": [],
            "note": "InferenceServer not wired (W25 not active on this dashboard instance)",
        }

    list_handles = getattr(inference, "list_handles", None)
    if list_handles is None:
        return {
            "available": False,
            "handles": [],
            "note": "InferenceServer does not expose list_handles()",
        }

    try:
        handles = await list_handles(tenant_id=tenant_id)
    except TypeError:
        handles = await list_handles()
    except Exception as exc:
        logger.exception("mldashboard.serving_view.list_handles_failed")
        return {"available": False, "handles": [], "note": str(exc)}

    return {"available": True, "handles": list(handles), "note": ""}
