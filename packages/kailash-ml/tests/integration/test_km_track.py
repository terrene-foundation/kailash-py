# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests for ``km.track()``.

Exercise the real SQLite backend on disk (no mocks) to validate:

- Round-trip of the 16 auto-capture fields per ``specs/ml-tracking.md``
  §2.4.
- Status auto-set per §2.2 (COMPLETED / FAILED / KILLED).
- Trainable-integration wiring — device fields populated from a real
  ``TrainingResult.device`` (:class:`DeviceReport`).

All tests write to a real SQLite database in a temp dir and read back
the row through the backend's public API. This matches
``rules/testing.md`` Tier 2 (real infrastructure, no mocking).
"""
from __future__ import annotations

import asyncio
import os
import signal
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import polars as pl
import pytest

import kailash_ml as km
from kailash_ml._device_report import DeviceReport
from kailash_ml._result import TrainingResult
from kailash_ml.tracking import (
    ExperimentRun,
    RunStatus,
    SQLiteTrackerBackend,
    track,
)


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def backend(tmp_path: Path) -> SQLiteTrackerBackend:
    """Real SQLiteTrackerBackend on a real disk file.

    Yields + closes per ``rules/testing.md`` "Fixtures Yield + Cleanup".
    """
    db_path = tmp_path / "tracker.db"
    be = SQLiteTrackerBackend(db_path)
    await be.initialize()
    try:
        yield be
    finally:
        await be.close()


# ---------------------------------------------------------------------------
# §2.4 auto-capture round trip
# ---------------------------------------------------------------------------


async def test_km_track_round_trip(backend: SQLiteTrackerBackend) -> None:
    """The 16 auto-capture fields survive a write/read round trip."""
    async with track("round-trip-exp", backend=backend, lr=0.01, depth=5) as run:
        await run.log_param("batch_size", 128)
        run_id = run.run_id
        experiment = run.experiment

    row = await backend.get_run(run_id)
    assert row is not None, "run should be persisted after context exit"

    # 16 auto-capture fields (spec §2.4)
    assert row["run_id"] == run_id
    assert row["experiment"] == experiment
    assert row["status"] == RunStatus.COMPLETED
    assert row["host"] is not None and row["host"] != ""
    assert row["python_version"].startswith("3.")
    # git fields — tolerate absence in CI / non-git checkouts
    assert "git_sha" in row
    assert "git_branch" in row
    assert "git_dirty" in row
    assert row["wall_clock_start"] is not None
    assert row["wall_clock_end"] is not None
    assert row["duration_seconds"] is not None and row["duration_seconds"] >= 0.0
    # tenant_id may be None in single-tenant mode
    assert "tenant_id" in row
    # parent_run_id explicitly None for a top-level run
    assert row["parent_run_id"] is None
    # device fields None until attach_training_result is called
    assert row["device_family"] is None
    assert row["device_backend"] is None
    assert row["device_fallback_reason"] is None
    assert row["device_array_api"] is None

    # Params preserved through round trip
    assert row["params"] == {"lr": 0.01, "depth": 5, "batch_size": 128}


# ---------------------------------------------------------------------------
# §2.2 status transitions
# ---------------------------------------------------------------------------


async def test_km_track_status_completed(backend: SQLiteTrackerBackend) -> None:
    """Clean exit -> status=COMPLETED, no error fields."""
    async with track("status-completed", backend=backend) as run:
        run_id = run.run_id

    row = await backend.get_run(run_id)
    assert row["status"] == RunStatus.COMPLETED
    assert row["error_type"] is None
    assert row["error_message"] is None


async def test_km_track_status_failed(backend: SQLiteTrackerBackend) -> None:
    """Raise inside body -> status=FAILED, exc captured."""
    run_id: str | None = None
    with pytest.raises(RuntimeError, match="training diverged"):
        async with track("status-failed", backend=backend) as run:
            run_id = run.run_id
            raise RuntimeError("training diverged")

    assert run_id is not None
    row = await backend.get_run(run_id)
    assert row["status"] == RunStatus.FAILED
    assert row["error_type"] == "RuntimeError"
    assert row["error_message"] is not None
    assert "training diverged" in row["error_message"]


async def test_km_track_status_killed(backend: SQLiteTrackerBackend) -> None:
    """KeyboardInterrupt inside body -> status=KILLED.

    Per ``specs/ml-tracking.md`` §2.2 the context manager MUST record
    ``KILLED`` when the run is interrupted by SIGINT. We verify the
    status transition by raising ``KeyboardInterrupt`` directly — the
    same exception shape that Python's default SIGINT handler raises.
    Delivering a real SIGINT under pytest would require disabling
    pytest's own interrupt handling, which exceeds the scope of this
    test's contract.
    """
    run_id: str | None = None
    with pytest.raises(KeyboardInterrupt):
        async with track("status-killed", backend=backend) as run:
            run_id = run.run_id
            raise KeyboardInterrupt()

    assert run_id is not None
    row = await backend.get_run(run_id)
    assert row["status"] == RunStatus.KILLED
    assert row["error_type"] == "KeyboardInterrupt"


async def test_km_track_status_killed_via_signal_handler(
    backend: SQLiteTrackerBackend,
) -> None:
    """The installed SIGINT handler flips the ``_killed`` flag.

    Direct unit-level exercise of :meth:`ExperimentRun._on_kill_signal`
    — proves the handler is wired to the `_killed` flag and raises
    ``KeyboardInterrupt``. Complements the status test above; keeps
    real signal delivery out of the pytest main loop where it would
    collide with pytest's own handlers.
    """
    run_id: str | None = None
    with pytest.raises(KeyboardInterrupt):
        async with track("killed-via-handler", backend=backend) as run:
            run_id = run.run_id
            # The SIGINT handler we install ends up calling
            # _on_kill_signal(signum, frame) — exercise it directly.
            run._on_kill_signal(signal.SIGINT, None)

    assert run_id is not None
    row = await backend.get_run(run_id)
    assert row["status"] == RunStatus.KILLED
    assert row["error_type"] == "KeyboardInterrupt"


# ---------------------------------------------------------------------------
# Nested runs — parent_run_id auto-propagates
# ---------------------------------------------------------------------------


async def test_km_track_nested_runs(backend: SQLiteTrackerBackend) -> None:
    """Child run's parent_run_id matches the enclosing run."""
    parent_id: str | None = None
    child_id: str | None = None
    async with track("outer", backend=backend) as parent:
        parent_id = parent.run_id
        async with track("inner", backend=backend) as child:
            child_id = child.run_id
            assert child.parent_run_id == parent.run_id

    prow = await backend.get_run(parent_id)
    crow = await backend.get_run(child_id)
    assert prow["parent_run_id"] is None
    assert crow["parent_run_id"] == parent_id


# ---------------------------------------------------------------------------
# Tenant propagation from env
# ---------------------------------------------------------------------------


async def test_km_track_tenant_from_env(
    backend: SQLiteTrackerBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``KAILASH_TENANT_ID`` env var populates ``tenant_id`` when no kwarg."""
    monkeypatch.setenv("KAILASH_TENANT_ID", "acme-tenant-42")
    async with track("tenant-exp", backend=backend) as run:
        run_id = run.run_id
        assert run.tenant_id == "acme-tenant-42"
    row = await backend.get_run(run_id)
    assert row["tenant_id"] == "acme-tenant-42"


async def test_km_track_tenant_explicit_overrides_env(
    backend: SQLiteTrackerBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit ``tenant_id=`` kwarg wins over the env var."""
    monkeypatch.setenv("KAILASH_TENANT_ID", "env-tenant")
    async with track("tenant-exp", backend=backend, tenant_id="explicit-tenant") as run:
        run_id = run.run_id
    row = await backend.get_run(run_id)
    assert row["tenant_id"] == "explicit-tenant"


# ---------------------------------------------------------------------------
# DeviceReport integration — Trainable fit path round-trip
# ---------------------------------------------------------------------------


async def test_km_track_integrates_trainable_device_report(
    backend: SQLiteTrackerBackend,
) -> None:
    """Attaching a real ``TrainingResult`` populates device fields.

    Uses a real :class:`SklearnTrainable` from the Phase 1 Trainable
    set so the DeviceReport is the production adapter output, not a
    hand-crafted object.
    """
    from kailash_ml.trainable import SklearnTrainable

    # Minimal labelled data for the sklearn adapter
    data = pl.DataFrame(
        {
            "f1": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            "f2": [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
            "target": [0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
        }
    )
    trainable = SklearnTrainable(target="target")

    async with track("trainable-integration", backend=backend) as run:
        # fit() is synchronous in the sklearn adapter — run it in a
        # thread so we don't block the event loop (Tier 2: no mocks).
        result = await asyncio.to_thread(trainable.fit, data)
        run.attach_training_result(result)
        run_id = run.run_id

    row = await backend.get_run(run_id)
    # device_backend must be populated from DeviceReport / device_used
    assert row["device_backend"] is not None and row["device_backend"] != ""
    # device_family MUST be set — SklearnTrainable declares family_name="sklearn"
    assert row["device_family"] == "sklearn"
    # device_array_api is a bool: True when Array API engaged, False
    # otherwise. The sklearn adapter populates it deterministically.
    assert row["device_array_api"] in {True, False}
