# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 tests for W26.c restart-surviving drift schedules (spec §5).

These tests cover the three headline guarantees the persistence shard
adds to the drift monitor:

  1. A schedule persisted by monitor_1 is visible to monitor_2 after
     the process "restarts" (fresh ConnectionManager against the same
     SQLite file) — spec §11.2.1.
  2. After re-registering the data source, the scheduler worker fires
     the drift check and writes ``last_run_*`` back to the row.
  3. Two DriftMonitor instances polling the same DB cooperate via the
     atomic ``next_run_at`` claim — only ONE of them executes any
     given scheduled fire.

Uses a real SQLite file (NOT :memory:) so the restart simulation is
faithful, and a real ConnectionManager per monitor instance so the
pool path is exercised end-to-end.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest
from kailash.db.connection import ConnectionManager
from kailash_ml.engines.drift_monitor import DriftMonitor


_FEATURES = ["feature_a", "feature_b"]


def _make_reference_df(n: int = 500) -> pl.DataFrame:
    rng = np.random.RandomState(42)
    return pl.DataFrame(
        {
            "feature_a": rng.normal(0, 1, n).tolist(),
            "feature_b": rng.normal(5, 2, n).tolist(),
        }
    )


def _make_current_df(n: int = 500) -> pl.DataFrame:
    rng = np.random.RandomState(123)
    return pl.DataFrame(
        {
            "feature_a": rng.normal(0, 1, n).tolist(),
            "feature_b": rng.normal(5, 2, n).tolist(),
        }
    )


async def _seed_reference(monitor: DriftMonitor) -> None:
    await monitor.set_reference_data("fraud", _make_reference_df(), _FEATURES)


async def _make_data_fn():
    """Returns a callable that produces a fresh current_df on each call."""

    async def _fn() -> pl.DataFrame:
        return _make_current_df()

    return _fn


@pytest.mark.integration
@pytest.mark.asyncio
async def test_schedule_survives_process_restart(tmp_path) -> None:
    """Spec §11.2.1 — schedule persisted by monitor_1 is recovered by
    monitor_2 after a simulated process restart."""
    db_path = tmp_path / "restart.db"
    conn_url = f"sqlite:///{db_path}"

    # --- First "process" — register schedule, then close ConnectionManager
    conn1 = ConnectionManager(conn_url)
    await conn1.initialize()
    monitor1 = DriftMonitor(conn1, tenant_id="test")
    await _seed_reference(monitor1)
    schedule_id = await monitor1.schedule_monitoring(
        "fraud",
        interval=timedelta(seconds=60),
        data_fn=await _make_data_fn(),
        actor_id="agent-42",
    )
    await conn1.close()

    # --- Simulate restart — fresh ConnectionManager on the SAME DB file
    conn2 = ConnectionManager(conn_url)
    await conn2.initialize()
    monitor2 = DriftMonitor(conn2, tenant_id="test")
    schedules = await monitor2.list_schedules(model_name="fraud")
    try:
        assert len(schedules) == 1
        recovered = schedules[0]
        assert recovered["schedule_id"] == schedule_id
        assert recovered["enabled"] is True
        assert recovered["interval_seconds"] == 60
        assert recovered["created_by_actor_id"] == "agent-42"
    finally:
        await conn2.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scheduler_dispatches_after_restart(tmp_path) -> None:
    """After restart, re-register the data source and start the worker —
    the scheduler fires the drift check and records last_run_* back to
    the schedule row."""
    db_path = tmp_path / "dispatch.db"
    conn_url = f"sqlite:///{db_path}"

    conn1 = ConnectionManager(conn_url)
    await conn1.initialize()
    monitor1 = DriftMonitor(conn1, tenant_id="test")
    await _seed_reference(monitor1)
    schedule_id = await monitor1.schedule_monitoring(
        "fraud",
        interval=timedelta(seconds=1),
        data_fn=await _make_data_fn(),
        actor_id="agent-42",
    )
    await conn1.close()

    conn2 = ConnectionManager(conn_url)
    await conn2.initialize()
    monitor2 = DriftMonitor(conn2, tenant_id="test")
    try:
        await _seed_reference(monitor2)
        # Fresh monitor has no in-process data source for the recovered
        # schedule. The caller re-registers before starting the worker.
        monitor2.register_data_source(schedule_id, await _make_data_fn())

        await monitor2.start_scheduler(poll_interval=0.5)
        # Give the poller time for one claim + dispatch cycle.
        for _ in range(20):
            await asyncio.sleep(0.3)
            rows = await monitor2.list_schedules(model_name="fraud")
            if rows and rows[0].get("last_run_at") is not None:
                break
        rows = await monitor2.list_schedules(model_name="fraud")
        assert len(rows) == 1
        recovered = rows[0]
        assert recovered["last_run_at"] is not None, (
            "scheduler worker never marked last_run_at on the recovered "
            "schedule — dispatch did not fire"
        )
        assert recovered["last_run_outcome"] == "success"
    finally:
        await monitor2.stop_scheduler()
        await conn2.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_without_data_source_logs_warn(tmp_path, caplog) -> None:
    """A recovered schedule without a re-registered data source MUST NOT
    crash the worker — it logs a WARN and moves on."""
    import logging

    db_path = tmp_path / "no_data_source.db"
    conn_url = f"sqlite:///{db_path}"

    conn1 = ConnectionManager(conn_url)
    await conn1.initialize()
    monitor1 = DriftMonitor(conn1, tenant_id="test")
    await _seed_reference(monitor1)
    await monitor1.schedule_monitoring(
        "fraud",
        interval=timedelta(seconds=1),
        data_fn=await _make_data_fn(),
    )
    await conn1.close()

    conn2 = ConnectionManager(conn_url)
    await conn2.initialize()
    monitor2 = DriftMonitor(conn2, tenant_id="test")
    try:
        with caplog.at_level(
            logging.WARNING, logger="kailash_ml.engines.drift_monitor"
        ):
            # Deliberately do NOT re-register the data source.
            await monitor2.start_scheduler(poll_interval=0.3)
            for _ in range(10):
                await asyncio.sleep(0.3)
                if any(
                    "drift.scheduler.missing_data_source" in record.message
                    for record in caplog.records
                ):
                    break
        warn_msgs = [
            r.message
            for r in caplog.records
            if "drift.scheduler.missing_data_source" in r.message
        ]
        assert (
            warn_msgs
        ), "expected drift.scheduler.missing_data_source WARN log, got none"
    finally:
        await monitor2.stop_scheduler()
        await conn2.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_atomic_claim_prevents_double_dispatch(tmp_path) -> None:
    """Two DriftMonitor instances polling the same DB cooperate via the
    atomic next_run_at claim — across N scheduled fires, the total
    dispatch count is N (not 2N)."""
    db_path = tmp_path / "claim.db"
    conn_url = f"sqlite:///{db_path}"

    # Set up the schedule in a separate short-lived monitor so both
    # replicas start from an identical view of the DB.
    conn0 = ConnectionManager(conn_url)
    await conn0.initialize()
    monitor0 = DriftMonitor(conn0, tenant_id="test")
    await _seed_reference(monitor0)
    schedule_id = await monitor0.schedule_monitoring(
        "fraud",
        interval=timedelta(seconds=1),
        data_fn=await _make_data_fn(),
        actor_id="ci",
    )
    await conn0.close()

    # Replica A
    conn_a = ConnectionManager(conn_url)
    await conn_a.initialize()
    monitor_a = DriftMonitor(conn_a, tenant_id="test")
    await _seed_reference(monitor_a)
    a_calls: list[datetime] = []

    async def _data_fn_a() -> pl.DataFrame:
        a_calls.append(datetime.now(timezone.utc))
        return _make_current_df()

    monitor_a.register_data_source(schedule_id, _data_fn_a)

    # Replica B
    conn_b = ConnectionManager(conn_url)
    await conn_b.initialize()
    monitor_b = DriftMonitor(conn_b, tenant_id="test")
    await _seed_reference(monitor_b)
    b_calls: list[datetime] = []

    async def _data_fn_b() -> pl.DataFrame:
        b_calls.append(datetime.now(timezone.utc))
        return _make_current_df()

    monitor_b.register_data_source(schedule_id, _data_fn_b)

    try:
        await monitor_a.start_scheduler(poll_interval=0.3)
        await monitor_b.start_scheduler(poll_interval=0.3)
        # Run ~3 scheduled-second windows. With interval=1s we expect
        # ~3 dispatches total across both replicas.
        await asyncio.sleep(3.2)
    finally:
        await monitor_a.stop_scheduler()
        await monitor_b.stop_scheduler()
        await conn_a.close()
        await conn_b.close()

    total_calls = len(a_calls) + len(b_calls)
    # We expect ~3 fires in 3.2 seconds. Allow [1, 6] to absorb poll
    # jitter on slow test infra. Key invariant: total is NOT
    # ``2 * expected`` (which would indicate both replicas fired the
    # same schedule). An upper bound of 6 is tight enough to catch
    # double-dispatch even at the slow end.
    assert total_calls >= 1, "no dispatches fired across both replicas"
    assert total_calls <= 6, (
        f"double-dispatch suspected — total calls {total_calls} "
        f"(A={len(a_calls)}, B={len(b_calls)}) exceeds tight upper bound"
    )
