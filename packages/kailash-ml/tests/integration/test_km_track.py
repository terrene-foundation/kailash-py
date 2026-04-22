# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests for ``km.track()``.

Exercise the real SQLite backend on disk (no mocks) to validate:

- Round-trip of the 16 auto-capture fields per ``specs/ml-tracking.md``
  §2.4.
- Status auto-set per §3.2 (FINISHED / FAILED / KILLED) — W11 renamed
  from legacy COMPLETED per Decision 3 (4-member enum parity with kailash-rs).
- Trainable-integration wiring — device fields populated from a real
  ``TrainingResult.device`` (:class:`DeviceReport`).

All tests write to a real SQLite database in a temp dir and read back
the row through the backend's public API. This matches
``rules/testing.md`` Tier 2 (real infrastructure, no mocking).
"""
from __future__ import annotations

import asyncio
import signal
from pathlib import Path

import polars as pl
import pytest
from kailash_ml.tracking import RunStatus, SqliteTrackerStore, track

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def backend(tmp_path: Path) -> SqliteTrackerStore:
    """Real SqliteTrackerStore on a real disk file.

    Yields + closes per ``rules/testing.md`` "Fixtures Yield + Cleanup".
    """
    db_path = tmp_path / "tracker.db"
    be = SqliteTrackerStore(db_path)
    await be.initialize()
    try:
        yield be
    finally:
        await be.close()


# ---------------------------------------------------------------------------
# §2.4 auto-capture round trip
# ---------------------------------------------------------------------------


async def test_km_track_round_trip(backend: SqliteTrackerStore) -> None:
    """The 17 auto-capture fields survive a write/read round trip."""
    async with track("round-trip-exp", backend=backend, lr=0.01, depth=5) as run:
        await run.log_param("batch_size", 128)
        run_id = run.run_id
        experiment = run.experiment

    row = await backend.get_run(run_id)
    assert row is not None, "run should be persisted after context exit"

    # 17 auto-capture fields (spec §2.4)
    assert row["run_id"] == run_id
    assert row["experiment"] == experiment
    assert row["status"] == RunStatus.FINISHED
    assert row["host"] is not None and row["host"] != ""
    assert row["python_version"].startswith("3.")
    # Library/runtime versions (spec §2.4 rows 5-8) — kailash_ml always
    # populated; torch / lightning populated when importable (they are
    # base deps so always True in this test's venv). cuda_version is
    # None on non-CUDA hosts.
    assert row["kailash_ml_version"] is not None and row["kailash_ml_version"] != ""
    assert row["torch_version"] is not None and row["torch_version"].startswith("2.")
    assert row["lightning_version"] is not None
    assert "cuda_version" in row
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
    assert row["device_used"] is None
    assert row["accelerator"] is None
    assert row["precision"] is None
    assert row["device_family"] is None
    assert row["device_backend"] is None
    assert row["device_fallback_reason"] is None
    assert row["device_array_api"] is None

    # Params preserved through round trip
    assert row["params"] == {"lr": 0.01, "depth": 5, "batch_size": 128}


async def test_km_track_all_17_auto_capture_fields_present(
    backend: SqliteTrackerStore,
) -> None:
    """Explicit whitelist check: every spec §2.4 field column exists.

    Mechanical AST-style assertion — iterate the spec's 17-field list
    and assert each is a persisted column on the row. Catches a future
    refactor that silently drops a column (e.g. during the 0.14 → 1.0
    schema bump).
    """
    expected_fields = {
        # From spec §2.4 table, plus the core run_id/experiment/status
        # keys that are part of the same surface.
        "run_id",
        "experiment",
        "status",
        "parent_run_id",
        "tenant_id",
        "host",
        "python_version",
        "kailash_ml_version",
        "lightning_version",
        "torch_version",
        "cuda_version",
        "git_sha",
        "git_branch",
        "git_dirty",
        "wall_clock_start",
        "wall_clock_end",
        "duration_seconds",
        "device_used",
        "accelerator",
        "precision",
        "device_family",
        "device_backend",
        "device_fallback_reason",
        "device_array_api",
    }
    async with track("all-fields-exp", backend=backend) as run:
        run_id = run.run_id
    row = await backend.get_run(run_id)
    assert row is not None
    missing = expected_fields - set(row.keys())
    assert not missing, f"spec §2.4 fields not persisted: {sorted(missing)}"


# ---------------------------------------------------------------------------
# §2.2 status transitions
# ---------------------------------------------------------------------------


async def test_km_track_status_completed(backend: SqliteTrackerStore) -> None:
    """Clean exit -> status=FINISHED, no error fields.

    W11 renamed the terminal status from legacy ``COMPLETED`` to
    ``FINISHED`` per spec §3.2 / Decision 3. Test function name kept
    for git-blame continuity; assertion is on the 1.0.0 vocabulary.
    """
    async with track("status-completed", backend=backend) as run:
        run_id = run.run_id

    row = await backend.get_run(run_id)
    assert row["status"] == RunStatus.FINISHED
    assert row["error_type"] is None
    assert row["error_message"] is None


async def test_km_track_status_failed(backend: SqliteTrackerStore) -> None:
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


async def test_km_track_status_killed(backend: SqliteTrackerStore) -> None:
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
    backend: SqliteTrackerStore,
) -> None:
    """The process-level SIGINT handler flips every active ``_killed`` flag.

    Spec §3.3 / W11 — the handler lives at module scope
    (:func:`kailash_ml.tracking.runner._process_kill_signal`) so a
    single signal can kill every currently-RUNNING run. Exercise it
    directly to avoid racing against pytest's own SIGINT handling.
    """
    from kailash_ml.tracking.runner import _process_kill_signal

    run_id: str | None = None
    with pytest.raises(KeyboardInterrupt):
        async with track("killed-via-handler", backend=backend) as run:
            run_id = run.run_id
            # Synthesise SIGINT delivery via the module-level handler —
            # this is the exact code path CPython invokes on real signal.
            _process_kill_signal(signal.SIGINT, None)

    assert run_id is not None
    row = await backend.get_run(run_id)
    assert row["status"] == RunStatus.KILLED
    assert row["error_type"] == "KeyboardInterrupt"


# ---------------------------------------------------------------------------
# Nested runs — parent_run_id auto-propagates
# ---------------------------------------------------------------------------


async def test_km_track_nested_runs(backend: SqliteTrackerStore) -> None:
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
    backend: SqliteTrackerStore,
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
    backend: SqliteTrackerStore,
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
    backend: SqliteTrackerStore,
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
    # Top-level TrainingResult mirrors (spec §2.4 rows 11-13) — every
    # trainable adapter populates these as concrete strings (never
    # "auto"). device_used is the torch device string; accelerator is
    # the Lightning accelerator label; precision is the concrete
    # Lightning precision.
    assert row["device_used"] == result.device_used
    assert row["accelerator"] == result.accelerator
    assert row["precision"] == result.precision
    assert row["device_used"] and row["device_used"] != "auto"
    assert row["accelerator"] and row["accelerator"] != "auto"
    assert row["precision"] and row["precision"] != "auto"
