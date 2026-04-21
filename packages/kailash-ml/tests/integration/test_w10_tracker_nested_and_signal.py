# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W10 Tier-2 integration tests — real SQLite file + nested-run isolation.

Per `rules/testing.md` Tier 2: no mocking. Uses a real SQLite file on
tmp_path so the migration registry actually applies 0001 + 0002 and
the run row lands in the `experiment_runs` table.

Coverage:

- Nested runs write two distinct rows with parent_run_id wired.
- `get_current_run()` stack correctness under concurrent `async with`
  nesting.
- SIGINT / SIGTERM handlers installed on `__aenter__` and removed on
  `__aexit__` (round-trip invariant 7 from W10 todo).
"""
from __future__ import annotations

import signal
import threading
from pathlib import Path

import pytest
from kailash_ml.tracking import ExperimentTracker, get_current_run


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tracker_persists_run_to_sqlite_file(tmp_path: Path) -> None:
    """Real file-backed roundtrip — factory opens, run inserts a row."""
    db_path = tmp_path / "ml.db"
    tracker = await ExperimentTracker.create(f"sqlite:///{db_path}")
    try:
        async with tracker.track("fraud-v3", lr=0.01) as run:
            assert run.experiment == "fraud-v3"
            assert run.run_id
            await run.log_param("batch_size", 64)
    finally:
        await tracker.close()

    # Verify row persisted by re-opening the DB directly (no mocking).
    import sqlite3

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT experiment, run_id, status FROM experiment_runs"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "fraud-v3"
    # Exit was clean → COMPLETED (runner.RunStatus).
    assert rows[0][2] == "COMPLETED"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nested_runs_isolate_and_parent_wire(tmp_path: Path) -> None:
    """Parent → child nesting writes two rows; child.parent_run_id == parent.run_id."""
    db_path = tmp_path / "ml.db"
    tracker = await ExperimentTracker.create(f"sqlite:///{db_path}")
    parent_id: str = ""
    child_id: str = ""
    try:
        async with tracker.track("sweep") as parent:
            parent_id = parent.run_id
            async with tracker.track("trial") as child:
                child_id = child.run_id
                assert child.parent_run_id == parent_id
                assert get_current_run() is child
            # Parent resumes as ambient after child exit.
            assert get_current_run() is parent
    finally:
        await tracker.close()

    import sqlite3

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT run_id, parent_run_id, experiment FROM experiment_runs"
        ).fetchall()
    assert len(rows) == 2
    by_id = {r[0]: (r[1], r[2]) for r in rows}
    assert by_id[parent_id] == (None, "sweep")
    assert by_id[child_id] == (parent_id, "trial")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_signal_handlers_round_trip(tmp_path: Path) -> None:
    """Invariant 7 — SIGINT handler installed on enter, restored on exit.

    The `track()` runner installs SIGINT / SIGTERM handlers only on the
    main thread per CPython's `signal.signal` contract. We assert
    round-trip restoration: whatever was installed before entering is
    re-installed after exit.
    """
    if threading.current_thread() is not threading.main_thread():
        pytest.skip("signal.signal() only works on main thread")

    before_sigint = signal.getsignal(signal.SIGINT)
    before_sigterm = signal.getsignal(signal.SIGTERM)

    db_path = tmp_path / "ml.db"
    tracker = await ExperimentTracker.create(f"sqlite:///{db_path}")
    try:
        async with tracker.track("signal-probe") as run:
            # Inside the block, our handler is installed — it is NOT
            # the original default.
            inside_sigint = signal.getsignal(signal.SIGINT)
            assert inside_sigint is not before_sigint
            assert callable(inside_sigint)
            assert run.run_id
    finally:
        await tracker.close()

    after_sigint = signal.getsignal(signal.SIGINT)
    after_sigterm = signal.getsignal(signal.SIGTERM)
    # Handlers restored exactly to the pre-enter state.
    assert after_sigint is before_sigint
    assert after_sigterm is before_sigterm
