"""Regression test — ``import kaizen.monitoring`` must not require FastAPI.

Bug: ``kaizen/monitoring/dashboard.py`` eagerly ran
``from fastapi import FastAPI, WebSocket, WebSocketDisconnect`` (and built a
module-scope ``app = FastAPI(...)``) at import time, and
``kaizen/monitoring/__init__.py`` eagerly imported ``app`` from it. FastAPI is
an OPTIONAL dependency (the ``server`` extra), so on a bare
``pip install kailash-kaizen`` — no ``[server]`` extra — the very first
``import kaizen.monitoring`` raised ``ModuleNotFoundError: No module named
'fastapi'``, taking down every consumer of the monitoring package (metrics
collection, analytics, alerting) even though only the dashboard needs FastAPI.

Fix: the FastAPI surface is built lazily. ``import kaizen.monitoring`` succeeds
without FastAPI; the ``app`` object and ``create_dashboard_app()`` import
FastAPI only when actually used, raising a typed, actionable
``MonitoringDependencyError`` (an ``ImportError`` subclass) that names the
remedy (``pip install 'kailash-kaizen[server]'``) instead of a silent no-op.

These tests exercise the REAL fastapi-absent path by spawning a subprocess that
blocks ``fastapi`` via a ``sys.meta_path`` finder BEFORE importing kaizen. The
child inherits the parent's kaizen resolution (via ``kaizen.__file__``), so it
verifies whatever ``kaizen`` the test runner loaded — no hard-coded paths.
Deterministic, offline, no network/DB.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import kaizen

# Directory that must be on PYTHONPATH for the child to import the SAME kaizen
# the parent test process resolved (worktree src in-worktree, installed pkg in CI).
_KAIZEN_SRC_DIR = str(Path(kaizen.__file__).resolve().parent.parent)


def _run_child(script: str) -> subprocess.CompletedProcess:
    """Run ``script`` in a subprocess with FastAPI blocked and kaizen importable."""
    env = os.environ.copy()
    env["PYTHONPATH"] = _KAIZEN_SRC_DIR + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


# Prologue installs a meta-path finder that makes ``import fastapi`` (and any
# submodule) raise ModuleNotFoundError, simulating a bare install with no
# ``[server]`` extra.
_BLOCK_FASTAPI = """
import sys

class _BlockFastapi:
    def find_spec(self, name, path=None, target=None):
        if name == "fastapi" or name.startswith("fastapi."):
            raise ModuleNotFoundError(f"No module named {name!r} (blocked by test)")
        return None

for _m in [m for m in sys.modules if m == "fastapi" or m.startswith("fastapi.")]:
    del sys.modules[_m]
sys.meta_path.insert(0, _BlockFastapi())
"""


@pytest.mark.regression
def test_import_kaizen_monitoring_without_fastapi_succeeds():
    """``import kaizen.monitoring`` must succeed when FastAPI is unavailable."""
    script = (
        _BLOCK_FASTAPI
        + """
try:
    import fastapi  # must be blocked
except ImportError:
    pass
else:
    raise SystemExit("PRECONDITION FAIL: fastapi was importable, block ineffective")

import kaizen.monitoring  # the bug: this used to raise ModuleNotFoundError
from kaizen.monitoring import (
    MetricsCollector,
    AnalyticsAggregator,
    AlertManager,
    PerformanceDashboard,
    create_dashboard_app,
    MonitoringDependencyError,
)
print("IMPORT_OK")
"""
    )
    result = _run_child(script)
    assert result.returncode == 0, (
        f"import kaizen.monitoring failed without fastapi.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "IMPORT_OK" in result.stdout, result.stdout


@pytest.mark.regression
def test_building_dashboard_without_fastapi_raises_typed_error():
    """Building the dashboard without FastAPI raises a typed error naming the extra."""
    script = (
        _BLOCK_FASTAPI
        + """
import kaizen.monitoring
from kaizen.monitoring import create_dashboard_app, MonitoringDependencyError

# The factory must raise the typed error (not silently no-op, not a bare
# ModuleNotFoundError with no remedy).
try:
    create_dashboard_app()
except MonitoringDependencyError as exc:
    msg = str(exc)
    assert "kailash-kaizen[server]" in msg, f"remedy missing from message: {msg!r}"
    assert "FastAPI" in msg, f"dependency name missing from message: {msg!r}"
else:
    raise SystemExit("FAIL: create_dashboard_app() did not raise without fastapi")

# MonitoringDependencyError is an ImportError subclass so existing handlers catch it.
assert issubclass(MonitoringDependencyError, ImportError)

# Accessing the lazy ``app`` attribute must raise the same typed error.
try:
    kaizen.monitoring.app
except MonitoringDependencyError:
    pass
else:
    raise SystemExit("FAIL: kaizen.monitoring.app access did not raise without fastapi")

print("TYPED_ERROR_OK")
"""
    )
    result = _run_child(script)
    assert result.returncode == 0, (
        f"dashboard-build typed-error check failed.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "TYPED_ERROR_OK" in result.stdout, result.stdout


@pytest.mark.regression
def test_dashboard_functional_when_fastapi_present():
    """When FastAPI IS installed, the dashboard app builds and exposes its routes."""
    pytest.importorskip("fastapi", reason="dashboard functional path needs FastAPI")

    from kaizen.monitoring import create_dashboard_app

    app = create_dashboard_app()
    # FastAPI app exposes the dashboard routes registered by the factory.
    paths = {route.path for route in app.routes}
    assert {"/", "/ws", "/metrics", "/health"} <= paths, paths
