# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 regression for issue #953 — LocalRuntime tracks AsyncSQL pools
its persistent loop creates so the outer-loop-running cleanup branch in
``_cleanup_event_loop`` emits a WARN naming the leak when the mixed-mode
pattern (sync execute → outer-async ``__exit__``) leaves persistent-loop-
owned pools that NEITHER cleanup path reaches.

Sibling of issue #942 (PR #966) which fixed the wait_for-coroutine-leak
on the same ``_cleanup_event_loop`` path. #942 closed the warning;
#953 surfaces the residual leak signal that #942's outer-loop skip
necessarily defers.

Reproduces the mixed-mode pattern from the issue body:

    rt = LocalRuntime()
    rt.execute(sync_workflow_using_asyncsql)   # creates pool on rt._persistent_loop

    async def outer():
        with rt:
            rt.execute(async_workflow)          # outer loop running
        # __exit__ skips disposal; persistent-loop pool stays in _shared_pools

    asyncio.run(outer())
    # AsyncSQLDatabaseNode._shared_pools still holds the orphaned entry

Per acceptance criteria in issue #953:

    (a) post-init, ``runtime._created_async_sql_pools`` is non-empty
        (the runtime tracked the persistent-loop-owned pool)
    (b) post-exit from outer loop, the WARN log is emitted
        (operators can see the leak signal)
    (c) NB: cannot assert pools cleaned to zero — that's the residual
        leak this issue acknowledges; the WARN is the operational signal
        the issue mandates as the fix.

NO MOCKING per ``rules/testing.md`` § Tier 2 — every test runs against
the real ``kailash_test_postgres`` Docker container via the same harness
sibling regression tests (#697, #942) use.
"""

from __future__ import annotations

import asyncio
import logging
import warnings

import pytest

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Skip the whole module if Docker / PG isn't available — match other
# regression tests' guards.
try:
    from tests.utils.docker_config import (
        ensure_docker_services,
        get_postgres_connection_string,
    )
except ImportError:  # pragma: no cover
    pytest.skip("docker_config not available", allow_module_level=True)


pytestmark = [
    pytest.mark.regression,
    pytest.mark.integration,
    pytest.mark.requires_docker,
]


@pytest.fixture(autouse=True)
def _verify_docker_services():
    """Skip the test if PG isn't running. Mirrors sibling regression tests."""
    services_ok = asyncio.run(ensure_docker_services())
    if not services_ok:
        pytest.skip("Required Docker services not available. Run './test-env up'")


@pytest.fixture
def pg_dsn():
    """PostgreSQL connection string from the docker_config helper."""
    return get_postgres_connection_string()


@pytest.fixture(autouse=True)
def _reset_shared_pools():
    """Reset class-level pool state between tests so prior runs don't
    pollute the assertions in this file.

    ``AsyncSQLDatabaseNode._shared_pools`` is process-wide; sibling test
    files (e.g. test_issue_697_pool_leak) can leave entries that this
    test would otherwise observe as "ours". Clearing pre-test is
    sufficient because the test runs synchronously and is the only
    populator within its body.
    """
    AsyncSQLDatabaseNode._shared_pools.clear()
    yield
    # Clear post-test as well so we don't poison sibling tests.
    AsyncSQLDatabaseNode._shared_pools.clear()


def _build_async_sql_workflow(pg_dsn: str) -> "WorkflowBuilder":
    """Build a minimal workflow whose execution triggers AsyncSQL pool
    init on the runtime's persistent loop.

    The workflow runs a single ``SELECT 1`` against real Postgres,
    which is enough to drive ``AsyncSQLDatabaseNode`` through pool
    acquisition and bind the reaper task to whichever loop the runtime
    chose. The 4-parameter ``add_node`` call matches the canonical
    pattern from ``rules/patterns.md``.
    """
    wf = WorkflowBuilder()
    wf.add_node(
        "AsyncSQLDatabaseNode",
        "select_one",
        {
            "connection_string": pg_dsn,
            "database_type": "postgresql",
            "query": "SELECT 1 AS ok",
            "pool_size": 2,
            "max_pool_size": 4,
        },
    )
    return wf


@pytest.mark.asyncio
async def test_localruntime_tracks_persistent_loop_async_sql_pools(
    pg_dsn: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Acceptance criteria (a) and (b) of issue #953.

    Scenario: caller uses the same ``LocalRuntime`` instance synchronously
    FIRST (creating pools whose reaper tasks bind to the persistent
    loop), then re-enters ``__exit__`` from inside an outer async loop.

    Pre-fix: ``__exit__`` correctly skips disposal (the #942 fix
    deferred this to the outer loop), BUT operators got zero signal
    that persistent-loop-owned pools were stranded. The leak class is
    invisible.

    Post-fix:
      (a) ``runtime._created_async_sql_pools`` is non-empty after the
          sync execute() — the runtime tracked the pool key.
      (b) Exiting the runtime's context manager from inside the outer
          async loop emits a WARN-level log naming the orphaned-pool
          count (per ``rules/observability.md`` Rule 5).

    The pool count is NOT asserted to zero: per the issue body, that's
    the residual leak this PR acknowledges. The WARN is the fix.
    """
    runtime = LocalRuntime()
    wf = _build_async_sql_workflow(pg_dsn)

    # === Step 1: sync execute() on a synchronous thread (no outer loop) ===
    # Drive the runtime synchronously from inside this async test by
    # delegating through ``run_in_executor`` so the runtime sees NO
    # running loop and takes the persistent-loop path (the only path
    # that binds the pool to ``runtime._persistent_loop``). This
    # mirrors how production callers (workers, batch scripts) reach
    # the persistent-loop execute() path.
    def _drive_sync_execute() -> tuple:
        # The "no context manager" DeprecationWarning is the EXACT
        # mixed-mode pattern this test exercises (per issue #953
        # reproducer: ``rt.execute(...)`` before ``with rt:``). The
        # deprecation is the intent here; suppress only this specific
        # warning class so the test focuses on the leak signal.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=".*without context manager or explicit close.*",
                category=DeprecationWarning,
            )
            results, run_id = runtime.execute(wf.build())
        return results, run_id

    loop = asyncio.get_running_loop()
    results, run_id = await loop.run_in_executor(None, _drive_sync_execute)

    # Sanity: the query did run end-to-end against real Postgres.
    # AsyncSQLDatabaseNode returns the node body inside the per-node
    # dict; the exact key structure is internal (and varies by mode),
    # so we only assert the workflow completed (run_id present) and
    # that this node produced a non-empty result object — issue #953
    # is about pool tracking, NOT about the AsyncSQL result schema.
    assert run_id is not None
    assert "select_one" in results
    assert results["select_one"]  # non-empty per-node result

    # === Acceptance criterion (a) ===
    # The runtime MUST have recorded at least one pool key bound to its
    # persistent loop. The snapshot helper fires at the end of every
    # _persistent_loop.run_until_complete via the ``finally`` block.
    assert (
        runtime._persistent_loop is not None
    ), "sync execute() should have created the persistent loop"
    # Diagnostic: surface observed state so the snapshot filter can be
    # debugged from CI logs when the assertion below fires.
    print(
        f"DEBUG: persistent_loop_id={id(runtime._persistent_loop)} "
        f"shared_pools={list(AsyncSQLDatabaseNode._shared_pools.keys())!r} "
        f"tracked={runtime._created_async_sql_pools!r}",
        flush=True,
    )
    assert len(runtime._created_async_sql_pools) >= 1, (
        "issue #953 acceptance (a): runtime MUST track AsyncSQL pool "
        "keys created on its persistent loop. Got: "
        f"{runtime._created_async_sql_pools!r} "
        f"shared_pools_keys={list(AsyncSQLDatabaseNode._shared_pools.keys())!r}"
    )
    # Every tracked key MUST carry our persistent loop's id prefix —
    # confirms the snapshot helper filtered correctly (issue #953 cares
    # ONLY about pools bound to OUR loop).
    loop_id_prefix = f"{id(runtime._persistent_loop)}|"
    untagged = [
        k for k in runtime._created_async_sql_pools if not k.startswith(loop_id_prefix)
    ]
    assert not untagged, (
        "tracked pool keys MUST all be bound to the persistent loop; "
        f"found {len(untagged)} foreign keys: {untagged!r}"
    )

    # === Step 2: re-enter __exit__ from INSIDE this outer async loop ===
    # This is the failure-mode reproducer. The outer loop is THIS
    # pytest-asyncio loop; ``with runtime:`` ... ``__exit__`` will see
    # ``asyncio.get_running_loop()`` succeed and take the skip branch
    # in ``_cleanup_event_loop``. Pre-fix that branch logged DEBUG;
    # post-fix it emits WARN with the orphan count.

    # Capture all logs at DEBUG level on the runtime's logger so we can
    # observe the new WARN line. ``caplog`` is the standard pytest
    # capture; ``propagate=True`` is the default but set explicitly so
    # the logger's records reach caplog regardless of upstream config.
    runtime_logger = logging.getLogger("kailash.runtime.local")
    runtime_logger.propagate = True
    with caplog.at_level(logging.DEBUG, logger="kailash.runtime.local"):
        # The context manager protocol routes through __enter__ /
        # __exit__ → close() → _cleanup_event_loop(). __exit__ runs
        # inside the active asyncio loop driving this test, so the
        # outer-running-loop branch fires.
        with runtime:
            # The body intentionally does NO work — the issue is about
            # the MIXED MODE itself (sync execute pre-context, then
            # async __exit__). The runtime carries the pre-context
            # tracking set into the cleanup path.
            pass

    # === Acceptance criterion (b) ===
    # The WARN-level log MUST have been emitted, naming the orphan
    # count and the rule_id sentinel (
    # ``localruntime.async_sql_pools_orphaned``) so operators can
    # grep for the signal. Per rules/observability.md MUST Rule 5
    # operators MUST be able to surface this WARN at default log level.
    warn_records = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING
        and "localruntime.async_sql_pools_orphaned" in r.getMessage()
    ]
    assert warn_records, (
        "issue #953 acceptance (b): exiting LocalRuntime context from "
        "inside an outer async loop with persistent-loop-owned pools "
        "MUST emit a WARN naming the orphan signal. Captured WARN "
        f"records: {[r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]!r}"
    )
    # The WARN MUST include the orphan count for operational triage.
    warn_msg = warn_records[0].getMessage()
    assert (
        "AsyncSQL pool(s)" in warn_msg
    ), f"WARN MUST name the resource (AsyncSQL pool); got: {warn_msg!r}"
    assert "issue #953" in warn_msg, (
        f"WARN MUST reference issue #953 so operators can cross-link; "
        f"got: {warn_msg!r}"
    )

    # === Credential-safety invariant (rules/security.md § No secrets in logs) ===
    # Pool keys can contain connection strings with credentials. The WARN
    # path MUST log ONLY the count + loop_ids, NEVER raw pool keys.
    # Sanity-check: the Postgres password from the test DSN MUST NOT
    # appear in any captured WARN record.
    from urllib.parse import urlparse

    parsed_dsn = urlparse(pg_dsn)
    if parsed_dsn.password:
        for record in caplog.records:
            assert parsed_dsn.password not in record.getMessage(), (
                "WARN path leaked Postgres password — rules/security.md § "
                "'No secrets in logs' violated. Record: "
                f"{record.getMessage()!r}"
            )


@pytest.mark.asyncio
async def test_localruntime_no_warn_when_no_persistent_pools(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Negative case: when the runtime created NO AsyncSQL pools on its
    persistent loop (e.g., a pure-PythonCodeNode workflow), the
    outer-loop-skip branch in ``_cleanup_event_loop`` MUST NOT emit the
    leak WARN — the leak signal applies only when there's something to
    leak.

    Same context-manager-from-outer-loop pattern as the positive case
    above, but the workflow body never touches AsyncSQL, so
    ``runtime._created_async_sql_pools`` stays empty and the WARN is
    suppressed. This guards against false-positive WARN spam for the
    common case of LocalRuntime used in async tests without DB nodes.
    """
    runtime = LocalRuntime()
    wf = WorkflowBuilder()
    wf.add_node(
        "PythonCodeNode",
        "noop",
        {"code": "result = {'ok': True}"},
    )

    # Drive sync execute from a thread (no outer loop visible to the
    # runtime, so it takes the persistent-loop path). The
    # no-context-manager DeprecationWarning is the same intentional
    # pattern the positive test exercises; suppress only that class.
    def _drive_sync_execute() -> None:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=".*without context manager or explicit close.*",
                category=DeprecationWarning,
            )
            runtime.execute(wf.build())

    await asyncio.get_running_loop().run_in_executor(None, _drive_sync_execute)

    # Persistent loop was created, but NO AsyncSQL pools were touched.
    assert runtime._persistent_loop is not None
    assert runtime._created_async_sql_pools == set(), (
        "PythonCodeNode-only workflow MUST NOT populate the AsyncSQL "
        "pool tracking set"
    )

    # __exit__ from this outer async loop hits the skip branch; the
    # empty tracking set MUST suppress the leak WARN.
    with caplog.at_level(logging.DEBUG, logger="kailash.runtime.local"):
        with runtime:
            pass

    leak_warns = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING
        and "localruntime.async_sql_pools_orphaned" in r.getMessage()
    ]
    assert not leak_warns, (
        "leak WARN MUST NOT fire when no AsyncSQL pools were tracked; "
        f"got: {[r.getMessage() for r in leak_warns]!r}"
    )
