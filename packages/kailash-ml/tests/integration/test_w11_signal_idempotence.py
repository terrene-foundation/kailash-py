# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W11 Tier-2 integration tests — idempotent signal handler installation.

Per ``specs/ml-tracking.md`` §3.3, the SIGINT / SIGTERM handler MUST be
installed EXACTLY ONCE per process and MUST mark every currently-RUNNING
run as KILLED before propagating the signal. The install-once invariant
is the W11 todo invariant 5 (``install-once guard, chain-through on
duplicate``).

These tests run against real SQLite files on tmp_path so the full
migration-registry + backend path is exercised (not a mock).
"""
from __future__ import annotations

import signal
import threading
from pathlib import Path

import pytest
from kailash_ml.tracking import ExperimentTracker
from kailash_ml.tracking.runner import _active_runs, _process_kill_signal


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nested_runs_install_signal_handler_once(tmp_path: Path) -> None:
    """Nested ``async with track(...)`` MUST NOT re-install the handler.

    Invariant 5 from the W11 todo: install-once guard. If the handler
    were re-installed on nested enter, the inner exit's restore would
    put the outer's "previous" back, leaving the process with the
    runner's handler even though both runs exited.
    """
    if threading.current_thread() is not threading.main_thread():
        pytest.skip("signal.signal() only works on main thread")

    before = signal.getsignal(signal.SIGINT)
    db_path = tmp_path / "ml.db"
    tracker = await ExperimentTracker.create(f"sqlite:///{db_path}")
    try:
        async with tracker.track("outer") as outer:
            inside_outer = signal.getsignal(signal.SIGINT)
            # The handler is installed — it is NOT the pre-test default.
            assert inside_outer is _process_kill_signal
            assert inside_outer is not before
            async with tracker.track("inner") as inner:
                inside_inner = signal.getsignal(signal.SIGINT)
                # Install-once — inside the nested run the SAME handler
                # object is still installed. Not a second one.
                assert inside_inner is _process_kill_signal
                assert inside_inner is inside_outer
                # Both runs are active at once.
                assert len(_active_runs) == 2
                assert outer in _active_runs and inner in _active_runs
            # After inner exit: outer still active, handler still ours.
            assert len(_active_runs) == 1
            assert signal.getsignal(signal.SIGINT) is _process_kill_signal
        # After outer exit: no active runs, handler restored to pre-test state.
        assert len(_active_runs) == 0
        assert signal.getsignal(signal.SIGINT) is before
    finally:
        await tracker.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_signal_fires_marks_all_active_runs_killed(tmp_path: Path) -> None:
    """When a signal fires during nested runs, BOTH runs exit as KILLED.

    Spec §3.3 — ``mark every currently-RUNNING run owned by this
    process as KILLED with killed_reason="signal.SIGINT"`` before
    the signal propagates.
    """
    if threading.current_thread() is not threading.main_thread():
        pytest.skip("signal.signal() only works on main thread")

    db_path = tmp_path / "ml.db"
    tracker = await ExperimentTracker.create(f"sqlite:///{db_path}")
    try:
        with pytest.raises(KeyboardInterrupt):
            async with tracker.track("outer") as outer:
                async with tracker.track("inner") as inner:
                    # Synthesise a SIGINT delivery by invoking the
                    # handler directly — equivalent to what CPython
                    # does when the real signal fires.
                    _process_kill_signal(signal.SIGINT, None)
        # Every active run was marked killed via the module-level handler.
        rows = await tracker._backend.list_runs()
        by_experiment = {r["experiment"]: r for r in rows}
        assert by_experiment["outer"]["status"] == "KILLED"
        assert by_experiment["inner"]["status"] == "KILLED"
        # Reason string shape is fixed per spec §3.3.
        assert outer._killed_reason == "signal.SIGINT"
        assert inner._killed_reason == "signal.SIGINT"
    finally:
        await tracker.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_signal_handler_state_flags_track_installation(
    tmp_path: Path,
) -> None:
    """The module-level installed-flags reflect the active-list state."""
    if threading.current_thread() is not threading.main_thread():
        pytest.skip("signal.signal() only works on main thread")

    # Before any run: handlers NOT installed (or installed by an
    # earlier test that already cleaned up — the test file does not
    # assert the pre-state, only the round-trip invariant).
    db_path = tmp_path / "ml.db"
    tracker = await ExperimentTracker.create(f"sqlite:///{db_path}")
    try:
        async with tracker.track("a"):
            # Inside a run: both flags are True (SIGTERM is POSIX-only
            # but Linux + macOS + Windows all have it in cpython).
            from kailash_ml.tracking import runner as _mod

            assert _mod._sigint_installed is True
            if hasattr(signal, "SIGTERM"):
                assert _mod._sigterm_installed is True
    finally:
        await tracker.close()

    # After exit: flags reset — used as a cross-test isolation guard.
    from kailash_ml.tracking import runner as _mod

    assert _mod._sigint_installed is False
    assert _mod._sigterm_installed is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_end_run_non_context_manager_persists_row(
    tmp_path: Path,
) -> None:
    """Decision 9 parity path — explicit start/end round-trips to SQLite."""
    db_path = tmp_path / "ml.db"
    tracker = await ExperimentTracker.create(f"sqlite:///{db_path}")
    try:
        run = await tracker.start_run("mcp-style", batch_size=32)
        await tracker.end_run(run, status="FINISHED")
    finally:
        await tracker.close()

    import sqlite3

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT experiment, status, run_id FROM experiment_runs"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "mcp-style"
    assert rows[0][1] == "FINISHED"
