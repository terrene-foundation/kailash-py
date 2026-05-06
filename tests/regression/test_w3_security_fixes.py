# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for W3 security/hardening fixes.

Covers:

- S1 (CRITICAL): workflow_blob is JSON, NOT pickle. Pickled payloads on a
  queue accessible to arbitrary INSERT actors are RCE per
  ``rules/security.md`` § "No arbitrary-code execution on user input".
  The JSON contract structurally prevents the class — deserializing JSON
  produces only Python primitives, no callable / class-instance pivot.
- S2 (HIGH): _fire_times bounded by OrderedDict + LRU eviction at
  MAX_FIRE_TIMES per ``rules/infrastructure-sql.md`` Rule 7. Plus
  cancel() cleanup closes the leak window for jobs cancelled while
  APScheduler considered them in-flight.

Per ``rules/testing.md`` § "Regression Testing", every bug fix MUST land
a regression test before merge. Per § "Behavioral Regression Tests Over
Source-Grep", these tests CALL the function and assert raise/return
behavior — not grep source for literal substrings.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pickle
import socket
from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator
from urllib.parse import urlparse

import pytest

from kailash.runtime.dispatcher import Task, compute_task_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# S1 (CRITICAL) — workflow_blob is JSON, NOT pickle
# ---------------------------------------------------------------------------


class _JsonSerializableWorkflow:
    """Minimal workflow stand-in providing the to_dict() contract."""

    def __init__(self, name: str = "wf") -> None:
        self.name = name

    def to_dict(self) -> dict:
        return {"name": self.name, "shape": "json-serializable-stub"}


class _JsonBuilder:
    def __init__(self, name: str = "wf") -> None:
        self.name = name

    def build(self) -> _JsonSerializableWorkflow:
        return _JsonSerializableWorkflow(self.name)


# Real APScheduler is required for the scheduler to instantiate. Skip the
# regression set if the optional dependency is absent.
apscheduler = pytest.importorskip(
    "apscheduler", reason="WorkflowScheduler regression requires APScheduler"
)


# ---------------------------------------------------------------------------
# Real-DB infrastructure (per rules/testing.md Tier 2 — NO mocking)
# ---------------------------------------------------------------------------


PG_URL = os.environ.get(
    "TEST_PG_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)
SQLITE_URL = "sqlite:///:memory:"


def _is_pg_available() -> bool:
    parsed = urlparse(PG_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except (OSError, ConnectionRefusedError, TimeoutError):
        return False


@pytest.fixture(params=["sqlite", "pg"])
async def conn(
    request: pytest.FixtureRequest,
):
    from kailash.db.connection import ConnectionManager

    dialect = request.param
    if dialect == "sqlite":
        url = SQLITE_URL
    elif dialect == "pg":
        if not _is_pg_available():
            pytest.skip(f"PostgreSQL not available at {PG_URL}")
        url = PG_URL
    else:
        raise ValueError(dialect)

    mgr = ConnectionManager(url)
    await mgr.initialize()
    yield mgr
    try:
        await mgr.execute("DROP TABLE IF EXISTS kailash_task_queue")
    except Exception:  # pragma: no cover - defensive cleanup
        logger.debug("regression cleanup drop failed", exc_info=True)
    await mgr.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.asyncio
async def test_workflow_blob_is_json_not_pickle(conn) -> None:
    """The persisted queue row carries a JSON workflow_blob, NOT pickle.

    S1 (CRITICAL): a pickled queue payload is RCE — anyone with INSERT
    privilege on the queue table executes arbitrary code on the worker.
    The JSON contract is the structural defense.

    Verification:
    1. Schedule a fire through a real ``WorkflowScheduler`` -> real
       ``SQLTaskQueueDispatcher`` -> real DB.
    2. Read the persisted ``payload``; confirm ``workflow_blob_json``
       decodes as JSON and produces a plain Python dict.
    3. Confirm ``pickle.loads`` on the bytes raises (so an attacker
       supplying pickle bytes cannot impersonate the JSON contract).
    """
    from kailash.infrastructure.task_queue import SQLTaskQueueDispatcher
    from kailash.runtime.scheduler import WorkflowScheduler

    dispatcher = SQLTaskQueueDispatcher(conn)
    await dispatcher.initialize()

    scheduler = WorkflowScheduler(job_store_path=None, dispatch_via=dispatcher)
    fixed_ft = datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)
    scheduler._planned_fire_time = lambda sid: fixed_ft

    builder = _JsonBuilder("regression-json")
    await scheduler._execute_workflow(builder, schedule_id="sched-json-regression")

    expected_task_id = compute_task_id("sched-json-regression", fixed_ft)
    rows = await conn.fetch(
        "SELECT payload FROM kailash_task_queue WHERE task_id = ?",
        expected_task_id,
    )
    assert len(rows) == 1, "scheduler MUST have persisted the row through dispatcher"

    raw_payload = rows[0]["payload"]
    payload = (
        json.loads(raw_payload)
        if isinstance(raw_payload, (str, bytes))
        else raw_payload
    )

    # The outer payload MUST be a plain JSON dict.
    assert isinstance(payload, dict)
    blob_json = payload["workflow_blob_json"]
    assert isinstance(blob_json, str), "workflow_blob_json MUST be a JSON string"

    # Decoding the inner blob MUST yield a plain dict (no class-instance
    # pivot, no callable). This is what makes the queue payload safe.
    blob_bytes = blob_json.encode("utf-8")
    workflow_dict = json.loads(blob_bytes.decode("utf-8"))
    assert isinstance(workflow_dict, dict)
    assert workflow_dict["name"] == "regression-json"

    # And the bytes MUST NOT be a valid pickle envelope. If they were,
    # an attacker's payload could masquerade as JSON-shaped while
    # smuggling a pickle stream the worker would deserialize.
    with pytest.raises((pickle.UnpicklingError, EOFError, KeyError, ValueError)):
        pickle.loads(blob_bytes)


# ---------------------------------------------------------------------------
# S2 (HIGH) — _fire_times bounded + cancel() cleanup
# ---------------------------------------------------------------------------


def _stub_submit_event(job_id: str, run_time: datetime):
    class _Stub:
        pass

    e = _Stub()
    e.job_id = job_id
    e.scheduled_run_times = [run_time]
    return e


def _stub_done_event(job_id: str):
    class _Stub:
        pass

    e = _Stub()
    e.job_id = job_id
    return e


@pytest.mark.regression
def test_fire_times_lru_eviction() -> None:
    """When MAX_FIRE_TIMES is exceeded, oldest entries are evicted.

    S2 (HIGH): plain Dict grew without bound when EVENT_JOB_EXECUTED |
    EVENT_JOB_ERROR didn't fire (cancelled mid-flight, listener
    exception). OrderedDict + LRU eviction is the safety net.
    """
    from kailash.runtime import scheduler as scheduler_mod
    from kailash.runtime.scheduler import WorkflowScheduler

    sched = WorkflowScheduler(job_store_path=None)

    # Pin the bound tightly so the test is fast and deterministic.
    monkey_max = 5
    scheduler_mod.MAX_FIRE_TIMES = monkey_max
    try:
        base = datetime(2026, 5, 7, 0, 0, 0, tzinfo=UTC)
        # Submit (monkey_max + 3) entries WITHOUT pairing each with a done
        # event — simulates the leak path.
        for i in range(monkey_max + 3):
            sched._on_job_submitted(
                _stub_submit_event(f"sched-lru-{i}", base + timedelta(seconds=i))
            )

        # Bound MUST hold.
        assert len(sched._fire_times) == monkey_max
        # Eviction MUST be FIFO (oldest first) — the first 3 entries are gone.
        evicted = {f"sched-lru-{i}" for i in range(3)}
        retained = {f"sched-lru-{i}" for i in range(3, monkey_max + 3)}
        assert evicted.isdisjoint(set(sched._fire_times.keys()))
        assert retained == set(sched._fire_times.keys())
    finally:
        scheduler_mod.MAX_FIRE_TIMES = 10_000


@pytest.mark.regression
@pytest.mark.asyncio
async def test_cancel_cleans_fire_times() -> None:
    """cancel(schedule_id) MUST drop the entry from _fire_times.

    Closes the leak window when a job is cancelled while APScheduler
    considered it in-flight (the EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
    listener may not fire under cancellation).

    Async test because ``AsyncIOScheduler.start()`` requires a running
    event loop.
    """
    from kailash.runtime.scheduler import WorkflowScheduler

    sched = WorkflowScheduler(job_store_path=None)
    sched.start()
    try:
        # Schedule a real job so cancel() has something to remove from
        # APScheduler. The stub fire-time entry is the part the
        # regression checks.
        builder = _JsonBuilder("cancel-cleanup")
        sid = sched.schedule_interval(builder, seconds=60)
        sched._on_job_submitted(
            _stub_submit_event(sid, datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC))
        )
        assert sid in sched._fire_times

        sched.cancel(sid)

        assert sid not in sched._fire_times, (
            "cancel() MUST drop _fire_times entry to close the leak window "
            "for jobs cancelled while APScheduler considered them in-flight"
        )
    finally:
        sched.shutdown(wait=False)
