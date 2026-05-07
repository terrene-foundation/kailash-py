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


# ---------------------------------------------------------------------------
# HIGH (post-fix) — workflow_blob size cap (DoS via OOM)
# ---------------------------------------------------------------------------


class _OversizedJsonWorkflow:
    """Workflow stub whose to_dict() returns a payload larger than the cap.

    The default 8 MiB cap is enforced via `MAX_WORKFLOW_BLOB_BYTES`. To test
    the boundary without burning 8 MiB of memory in the test process, the
    test monkeypatches the cap to a small value.
    """

    def __init__(self, payload_bytes: int) -> None:
        self._padding = "x" * payload_bytes

    def to_dict(self) -> dict:
        return {"name": "oversized", "padding": self._padding}


class _OversizedBuilder:
    def __init__(self, payload_bytes: int) -> None:
        self._payload_bytes = payload_bytes

    def build(self) -> _OversizedJsonWorkflow:
        return _OversizedJsonWorkflow(self._payload_bytes)


class _StubDispatcher:
    """In-memory Dispatcher stub for unit tests of the dispatch path.

    Records every enqueued Task so assertions can confirm the producer
    boundary serialized correctly. Conformant with the
    ``kailash.runtime.dispatcher.Dispatcher`` ABC's enqueue contract.
    """

    def __init__(self) -> None:
        from typing import List

        from kailash.runtime.dispatcher import Task

        self.enqueued: List[Task] = []

    async def enqueue(self, task) -> None:
        self.enqueued.append(task)


def _prime_fire_time(sched, schedule_id: str, fire_time: datetime) -> None:
    """Populate _fire_times so _dispatch_to_queue's _planned_fire_time call resolves.

    Mirrors the EVENT_JOB_SUBMITTED listener's recording (see
    scheduler._on_job_submitted) without needing APScheduler to actually
    fire — keeps the test fast + deterministic.
    """
    sched._fire_times[schedule_id] = fire_time


@pytest.mark.regression
@pytest.mark.asyncio
async def test_workflow_blob_size_cap_rejects_oversized() -> None:
    """workflow_blob exceeding MAX_WORKFLOW_BLOB_BYTES MUST raise ValueError.

    Producer-boundary cap. A workflow whose to_dict() output exceeds the
    cap is refused BEFORE the Task is constructed and BEFORE the
    dispatcher's enqueue is invoked.

    Why the regression: an unbounded workflow_blob OOMs every dequeueing
    worker on json.loads. The cap is the structural defense.
    """
    from kailash.runtime import scheduler as scheduler_mod

    original_cap = scheduler_mod.MAX_WORKFLOW_BLOB_BYTES
    scheduler_mod.MAX_WORKFLOW_BLOB_BYTES = 1024  # 1 KiB for fast test
    try:
        builder = _OversizedBuilder(payload_bytes=2000)
        sched = scheduler_mod.WorkflowScheduler(job_store_path=None)
        sched._dispatcher = _StubDispatcher()
        _prime_fire_time(
            sched, "sched-test", datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)
        )
        try:
            with pytest.raises(ValueError, match="MAX_WORKFLOW_BLOB_BYTES"):
                await sched._dispatch_to_queue(
                    workflow_builder=builder,
                    schedule_id="sched-test",
                    run_id="run-test-1",
                )
        finally:
            sched.shutdown(wait=False)
    finally:
        scheduler_mod.MAX_WORKFLOW_BLOB_BYTES = original_cap


@pytest.mark.regression
@pytest.mark.asyncio
async def test_workflow_blob_under_cap_dispatches_normally() -> None:
    """workflow_blob under the cap MUST dispatch without raising.

    Sanity check that the cap does not regress the normal path.
    """
    from kailash.runtime import scheduler as scheduler_mod

    builder = _JsonBuilder("under-cap")
    sched = scheduler_mod.WorkflowScheduler(job_store_path=None)
    stub = _StubDispatcher()
    sched._dispatcher = stub
    _prime_fire_time(
        sched, "sched-under-cap", datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)
    )
    try:
        await sched._dispatch_to_queue(
            workflow_builder=builder,
            schedule_id="sched-under-cap",
            run_id="run-under-cap-1",
        )
        assert len(stub.enqueued) == 1
        blob = stub.enqueued[0].workflow_blob
        decoded = json.loads(blob.decode("utf-8"))
        assert decoded["name"] == "under-cap"
    finally:
        sched.shutdown(wait=False)


# ---------------------------------------------------------------------------
# MEDIUM (post-fix) — task_id charset + length validation
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_validate_task_id_rejects_oversized() -> None:
    """task_id longer than MAX_TASK_ID_LEN MUST raise ValueError."""
    from kailash.infrastructure.task_queue import MAX_TASK_ID_LEN, _validate_task_id

    too_long = "a" * (MAX_TASK_ID_LEN + 1)
    with pytest.raises(ValueError, match="length"):
        _validate_task_id(too_long)


@pytest.mark.regression
def test_validate_task_id_rejects_empty() -> None:
    """Empty task_id MUST raise — empty PK is undefined behavior."""
    from kailash.infrastructure.task_queue import _validate_task_id

    with pytest.raises(ValueError, match="length"):
        _validate_task_id("")


@pytest.mark.regression
def test_validate_task_id_rejects_invalid_charset() -> None:
    """task_id with characters outside [a-zA-Z0-9_-] MUST raise."""
    from kailash.infrastructure.task_queue import _validate_task_id

    for bad in ["with space", "semi;colon", "back\\slash", "../../etc/passwd"]:
        with pytest.raises(ValueError, match="must match"):
            _validate_task_id(bad)


@pytest.mark.regression
def test_validate_task_id_rejects_non_string() -> None:
    """Non-string task_id MUST raise typed error."""
    from kailash.infrastructure.task_queue import _validate_task_id

    for bad in [42, None, b"bytes", ["list"], {"dict": 1}]:
        with pytest.raises(ValueError, match="must be str"):
            _validate_task_id(bad)


@pytest.mark.regression
def test_validate_task_id_accepts_uuid_and_compute_task_id() -> None:
    """The two paths that produce real task_ids in production MUST pass.

    Sanity check: uuid.uuid4() (caller-omitted task_id default) and
    compute_task_id() (W3 dispatcher path) both produce task_ids that
    pass validation.
    """
    import uuid

    from kailash.infrastructure.task_queue import _validate_task_id
    from kailash.runtime.dispatcher import compute_task_id

    # uuid4 → 36 chars, hex + dashes
    _validate_task_id(str(uuid.uuid4()))

    # compute_task_id → 32 hex chars
    fire_time = datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)
    _validate_task_id(compute_task_id("schedule-abc", fire_time))


# ---------------------------------------------------------------------------
# MEDIUM (post-fix) — soft_row_cap dispatcher constructor + WARN
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_soft_row_cap_rejects_non_positive() -> None:
    """SQLTaskQueueDispatcher MUST refuse soft_row_cap <= 0.

    Defense against caller passing 0 or a negative integer expecting it
    to mean "unbounded" — None is the documented unbounded sentinel.
    """
    from kailash.infrastructure.task_queue import SQLTaskQueueDispatcher

    class _DummyConn:
        pass

    for bad in [0, -1, -1000]:
        with pytest.raises(ValueError, match="soft_row_cap"):
            SQLTaskQueueDispatcher(_DummyConn(), soft_row_cap=bad)


@pytest.mark.regression
def test_soft_row_cap_default_is_none() -> None:
    """The default soft_row_cap MUST be None (no cap → no WARN).

    Backwards compatibility: existing callers of
    SQLTaskQueueDispatcher(conn) pre-cap MUST continue to work
    unchanged.
    """
    from kailash.infrastructure.task_queue import SQLTaskQueueDispatcher

    class _DummyConn:
        pass

    dispatcher = SQLTaskQueueDispatcher(_DummyConn())
    assert dispatcher._soft_row_cap is None


# ---------------------------------------------------------------------------
# LOW (post-fix) — discriminator dispatch (Workflow isinstance check)
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_workflow_without_to_dict_raises_typeerror() -> None:
    """Workflow stub without to_dict() MUST raise TypeError, not silently fall back.

    Per zero-tolerance Rule 3 — silent fallback is BLOCKED. The dispatch
    path refuses unknown workflow shapes rather than pickling them.
    """
    from kailash.runtime.scheduler import WorkflowScheduler

    class _NoToDict:
        pass

    class _NoToDictBuilder:
        def build(self) -> _NoToDict:
            return _NoToDict()

    sched = WorkflowScheduler(job_store_path=None)
    sched._dispatcher = _StubDispatcher()
    _prime_fire_time(
        sched, "sched-no-to-dict", datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)
    )
    try:
        with pytest.raises(TypeError, match="to_dict"):
            await sched._dispatch_to_queue(
                workflow_builder=_NoToDictBuilder(),
                schedule_id="sched-no-to-dict",
                run_id="run-no-to-dict-1",
            )
    finally:
        sched.shutdown(wait=False)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_real_workflow_isinstance_path_dispatches() -> None:
    """A real kailash.workflow.graph.Workflow instance MUST take the
    isinstance branch and dispatch successfully.

    The discriminator-first dispatch (Rule 3d sibling) means real
    Workflow instances skip the duck-type fallback and go straight to
    to_dict(). This test confirms the canonical path stays green.
    """
    from kailash.runtime.scheduler import WorkflowScheduler
    from kailash.workflow.builder import WorkflowBuilder

    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "noop", {"code": "result = {}"})

    sched = WorkflowScheduler(job_store_path=None)
    stub = _StubDispatcher()
    sched._dispatcher = stub
    _prime_fire_time(
        sched, "sched-real-workflow", datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)
    )
    try:
        await sched._dispatch_to_queue(
            workflow_builder=builder,
            schedule_id="sched-real-workflow",
            run_id="run-real-1",
        )
        assert len(stub.enqueued) == 1
        # Confirm round-trip parses through json.loads (canonical contract).
        blob = stub.enqueued[0].workflow_blob
        decoded = json.loads(blob.decode("utf-8"))
        assert "nodes" in decoded
    finally:
        sched.shutdown(wait=False)
