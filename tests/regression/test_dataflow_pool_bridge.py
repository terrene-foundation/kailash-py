"""DPI-D2 Bridge regression tests: pool count bounded under DDL failure saturation.

Proves that the kailash core pool registry (DPI-B, kailash>=2.12.0) and
the dataflow fail-fast DDL error surface (DPI-A, kailash-dataflow 2.4.0)
work together correctly:

- DDL failures raise DDLFailedError (not silent continues)
- Pool count stays bounded even when many DataFlow instances hit DDL failures

These tests require a live PostgreSQL instance and are skipped automatically
when Docker services are not available.

Why every instance gets its OWN event loop
------------------------------------------
Both tests used to drive ten ``DataFlow`` instances through a single
``asyncio.gather`` on ONE event loop against ONE DSN. ``_generate_pool_key``
keys the process-wide registry on ``id(get_running_loop())`` plus the
connection string, so ten instances sharing both collapse to a handful of
registry entries — measured on this tree, ``pool_count()`` reached **2**
against a configured cap of **5**. The ``<= 5`` assertions below could not
fail no matter what the registry did, so BOTH tests passed identically with
the issue #2075 slot release disabled: they were vacuous.

Ten CONCURRENT loops is the shape the process-wide cap actually exists to
bound (one pool per worker loop, the JourneyMate / #2211 saturation class),
and it puts the registry under genuine pressure.

Why a REAL query and a RETAINED adapter are both required
---------------------------------------------------------
Ten concurrent loops alone were NOT enough, and an earlier revision of this
file that stopped there was still vacuous. Two further measurements:

* In fail-fast mode the DDL circuit breaker fires at the HEAD of every model
  access, so ``express.create`` raised before any connection was opened —
  ``_disposal_barrier`` was entered **0** times and ``pool_count()`` was 0
  both with and without the fix. A test for a POOL leak that never opens a
  pool cannot fail. Each instance therefore issues one real ``express.list``
  BEFORE the synthetic failure is recorded, which is what registers a pool.
* ``_PROCESS_POOL_REGISTRY`` is a ``WeakValueDictionary``, so an adapter that
  nothing references is evicted by garbage collection whether or not the
  #2075 slot release ran. Retaining the ``DataFlow`` wrapper is not enough —
  it drops its adapter on close. Each worker therefore retains the ADAPTER
  objects registered under ITS OWN loop id (the leading segment of
  ``_generate_pool_key``) and hands them back to the test, so a surviving
  slot is attributable to the registry and never to GC timing. This is the
  technique ``test_issue_2075_pool_registry_lifecycle.py`` uses
  (``kept.append(node._adapter)``).

Measured on this tree, at the assertion point, with the #2075
``_unregister_pool`` call in ``_disposal_barrier`` neutralised in-process
(mutation proven to reach the code by a per-caller call counter):
``pool_count()`` = **10** for both tests, i.e. the cap of 5 is breached and
both assertions RED. With the fix in place: **0**.
"""

import asyncio
import concurrent.futures
import random

import pytest

try:
    from tests.utils.docker_config import (
        DATABASE_CONFIG,
        ensure_docker_services,
        get_postgres_connection_string,
    )
except ImportError:
    pytest.skip(
        "docker_config not available — skipping DPI-D2 bridge tests",
        allow_module_level=True,
    )

from kailash.nodes.data.async_sql import (
    _PROCESS_POOL_REGISTRY,
    AsyncSQLDatabaseNode,
    set_pool_defaults,
)

pytestmark = [
    pytest.mark.regression,
    pytest.mark.integration,
    pytest.mark.requires_docker,
]

# Number of concurrent DataFlow instances driven at the registry, and the
# cap they are driven against. INSTANCE_COUNT must exceed POOL_CAP or the
# bound is untestable by construction (the vacuity these tests carried).
INSTANCE_COUNT = 10
POOL_CAP = 5
assert INSTANCE_COUNT > POOL_CAP, "saturation requires more instances than the cap"


def _run_each_on_its_own_event_loop(coro_factory, count=INSTANCE_COUNT):
    """Run ``count`` coroutines CONCURRENTLY, each on a private event loop.

    ``asyncio.run`` per worker thread gives every instance a distinct
    ``id(get_running_loop())``, which is the leading segment of
    ``_generate_pool_key`` — so the registry sees ``count`` distinct pool
    keys rather than one shared key. ``max_workers=count`` is explicit (not
    ``asyncio.to_thread``'s CPU-derived default) so all ``count`` loops are
    genuinely alive at the same moment on any machine; sequential loops get
    their ``id()`` recycled and collapse back to a single key — measured
    here as ``pool_count()`` = 1 even with the fix disabled, which would
    reintroduce the vacuity.

    Returns the list of per-instance observation dicts, ordered by index.
    Exceptions from a worker propagate out of ``future.result()``.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
        futures = [
            executor.submit(lambda i=i: asyncio.run(coro_factory(i)))
            for i in range(count)
        ]
        return [f.result() for f in futures]


def _retain_pool_adapters_for_this_loop():
    """Return STRONG references to every pool adapter registered on this loop.

    ``_PROCESS_POOL_REGISTRY`` is a ``WeakValueDictionary``: an entry whose
    adapter has no other referent disappears on garbage collection, which is
    indistinguishable at ``pool_count()`` from the #2075 slot release actually
    running. Holding the adapters across the assertion removes that second
    explanation — a slot still occupied at the end is occupied because the
    registry never freed it.

    ``_generate_pool_key`` leads with ``id(get_running_loop())``, so filtering
    on this loop's id claims only the adapters this worker caused to be
    created, never a sibling worker's (the registry is process-wide and ten
    workers register into it concurrently).
    """
    prefix = f"{id(asyncio.get_running_loop())}|"
    return [
        adapter
        for key, adapter in list(_PROCESS_POOL_REGISTRY.items())
        if key.startswith(prefix)
    ]


@pytest.fixture(autouse=True)
def _verify_docker_services():
    """Skip the test if the required services aren't running.

    Issue #2079: this fixture used to call ``ensure_docker_services()`` and
    DISCARD the result. That helper does not raise — it prints and returns
    False — so the fixture named "verify" verified nothing, and the tests ran
    against whatever partial environment happened to be up. On CI that made
    ``test_failed_ddl_with_warn_mode_still_bounded`` report FAILED, which read
    as a fixture-phase error but was actually ``[XPASS(strict)]``: the test
    passed because its #2075 pool leak never fired without the full stack.

    Both sibling files (``test_issue_697_pool_leak.py``,
    ``test_issue_953_async_sql_pool_tracking.py``) already check the return
    value; this brings the third into line.
    """
    services_ok = asyncio.run(ensure_docker_services())
    if not services_ok:
        pytest.skip("Required Docker services not available. Run './test-env up'")


@pytest.fixture
def pg_dsn():
    """Return the PostgreSQL connection string for the test database."""
    return get_postgres_connection_string()


@pytest.fixture
def id_base():
    """A per-run id offset so repeat runs do not collide on the PK.

    The tables these tests write to persist between runs. Fixed ids made
    every instance after the first run fail with ``duplicate key value
    violates unique constraint`` — a failure class that has nothing to do
    with DDL, and which masked what the tests claim to measure.
    """
    return random.randrange(10**9, 2 * 10**9)


def test_failed_ddl_does_not_leak_pools_under_saturation(pg_dsn, id_base):
    """Pool count stays bounded when 10 DataFlow instances hit a DDL failure.

    Each instance pre-records a DDL failure and then calls ``express.create``
    under the default ``auto_migrate=True`` (fail-fast) mode. The test
    verifies:
    1. Every access raises DDLFailedError (fail-fast, default auto_migrate=True).
    2. Pool count never exceeds the configured cap of 5.

    This is the cross-layer assertion for DPI-A (DDLFailedError) +
    DPI-B (_PROCESS_POOL_REGISTRY cap via pool_count()).

    The ten instances run on ten CONCURRENT event loops (see the module
    docstring): on one shared loop the registry only ever reached 2 entries
    against the cap of 5, so assertion 2 was unfalsifiable.
    """
    from dataflow import DataFlow
    from dataflow.core.exceptions import DDLFailedError

    # Keep pool cap tight so leaks are detectable.
    set_pool_defaults(max_pool_count_per_process=POOL_CAP, idle_timeout=30)

    instances = []

    async def _attempt_access(i: int) -> dict:
        db = DataFlow(pg_dsn)
        instances.append(db)

        @db.model
        class DpiD2Child:
            id: int
            parent_id: int  # synthetic DDL failure recorded below

        # Open a REAL pool on this loop BEFORE the circuit breaker closes the
        # model off. In fail-fast mode `_check_failed_ddl` runs at the head of
        # every model access, so once the synthetic failure below is recorded
        # `express.create` raises without ever connecting — measured on this
        # tree, `_disposal_barrier` was entered 0 times and `pool_count()` was
        # 0 with the #2075 fix both enabled and disabled. A pool-leak test that
        # never opens a pool is vacuous by construction.
        await db.express.list("DpiD2Child", limit=1)
        adapters = _retain_pool_adapters_for_this_loop()

        # Issue #759 (DPI-A): Pre-record a synthetic DDL failure on this
        # instance so the next express.create exercises the fail-fast
        # circuit breaker deterministically. The model definition carries
        # no real FK declaration — DataFlow's DDL generator emits no
        # REFERENCES clause — so an "FK-misordered model" never actually
        # failed any DDL here. Pre-recording is the sibling technique used
        # by test_issue_759_express_propagates_ddl_failure.py.
        db._record_failed_ddl(
            "DpiD2Child",
            RuntimeError("synthetic FK-misordered DDL failure"),
            "CREATE TABLE dpi_d2_children (id SERIAL PRIMARY KEY, parent_id INTEGER REFERENCES dpi_d2_parent(id))",
        )

        observed = {
            "ddl_failed_error": False,
            "other_error": None,
            # Returned so the strong references outlive `asyncio.run` and are
            # still held when the bound below is asserted.
            "adapters": adapters,
        }
        # Trigger express.create — MUST raise DDLFailedError per DPI-A.
        try:
            await db.express.create("DpiD2Child", {"id": id_base + i, "parent_id": 1})
        except DDLFailedError:
            observed["ddl_failed_error"] = True
        except Exception as exc:  # noqa: BLE001 - classified, not swallowed
            observed["other_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            # close() is sync (returns None); close_async() is the awaitable
            # cleanup (rules/patterns.md § Async Resource Cleanup).
            await db.close_async()
        return observed

    results = _run_each_on_its_own_event_loop(_attempt_access)

    # The bound below reads `pool_count()`, which is only under pressure if
    # pools were genuinely created. Without this guard a connection that never
    # happened reads identically to a slot that was correctly released.
    assert all(r["adapters"] for r in results), (
        "No pool adapter was registered on "
        f"{len([r for r in results if not r['adapters']])} of {INSTANCE_COUNT} "
        "loops — the pool-count bound below would be unfalsifiable"
    )

    # Pool count MUST remain bounded even under failure saturation.
    assert AsyncSQLDatabaseNode.pool_count() <= POOL_CAP, (
        f"Pool leaked: pool_count()={AsyncSQLDatabaseNode.pool_count()} > {POOL_CAP} "
        f"after {INSTANCE_COUNT} DDL-failing DataFlow instances"
    )

    # DPI-A propagation: every instance pre-recorded a DDL failure, so in
    # fail-fast mode every express.create MUST surface the typed
    # DDLFailedError rather than the legacy success-False dict.
    ddl_errors = [r for r in results if r["ddl_failed_error"]]
    assert len(ddl_errors) == INSTANCE_COUNT, (
        f"Expected DDLFailedError on all {INSTANCE_COUNT} instances, got "
        f"{len(ddl_errors)}; other errors: "
        f"{[r['other_error'] for r in results if r['other_error']]}. "
        "Check DPI-A propagation in "
        "dataflow.features.express.DataFlowExpress._raise_for_failed_result"
    )


def test_failed_ddl_with_warn_mode_still_bounded(pg_dsn, id_base):
    """Pool count stays bounded in legacy auto_migrate='warn' mode too.

    Warn mode (auto_migrate='warn') logs and continues rather than raising.
    The pool registry cap still applies — warn mode MUST NOT cause unbounded
    pool growth under DDL failure saturation.

    Issue #2075: the ``xfail`` this carried is REMOVED. The leak was that
    ``_PROCESS_POOL_REGISTRY`` is a ``WeakValueDictionary``, so a slot was
    freed only when the adapter OBJECT was garbage-collected — never when the
    pool closed. Slot release is now driven explicitly at
    ``_disposal_barrier``, which every adapter ``disconnect()`` enters.

    Two defects that made this test vacuous are fixed here:

    * It never exercised a DDL failure at all. The model declares no real FK
      (DataFlow emits no REFERENCES clause for a bare ``parent_id: int``),
      and the table ``dpi_d2_warn_children`` already exists in the test
      database — so DDL SUCCEEDED and all ten instances instead failed with
      ``duplicate key value violates unique constraint``. The test named for
      a DDL-failure pool leak was measuring duplicate-key handling. It now
      pre-records a real ``FailedDDLRecord`` (the sibling technique) and
      asserts the warn escape hatch in ``_check_failed_ddl`` is the branch
      actually taken, with per-run unique ids removing the duplicate-key
      confound entirely.
    * Ten instances shared one event loop and one DSN, so the registry
      reached 2 entries against a cap of 5 and the bound below was
      unfalsifiable. They now run on ten concurrent loops.
    """
    from dataflow import DataFlow
    from dataflow.core.exceptions import DDLFailedError

    # Same tight pool cap.
    set_pool_defaults(max_pool_count_per_process=POOL_CAP, idle_timeout=30)

    instances = []

    async def _attempt_access_warn(i: int) -> dict:
        # auto_migrate="warn" is the legacy string sentinel for log-and-continue.
        db = DataFlow(pg_dsn, auto_migrate="warn")
        instances.append(db)

        @db.model
        class DpiD2WarnChild:
            id: int
            parent_id: int

        # Open a REAL pool on this loop first (see the fail-fast sibling and
        # the module docstring): the registry cannot be under pressure from an
        # instance that never connected.
        await db.express.list("DpiD2WarnChild", limit=1)
        adapters = _retain_pool_adapters_for_this_loop()

        # Force the DDL-FAILURE state this test is named for. Same technique
        # as the fail-fast sibling above; what differs is the CONTRACT being
        # asserted — warn mode must record the failure and continue, where
        # fail-fast raises.
        db._record_failed_ddl(
            "DpiD2WarnChild",
            RuntimeError("synthetic FK-misordered DDL failure"),
            "CREATE TABLE dpi_d2_warn_children (id SERIAL PRIMARY KEY, "
            "parent_id INTEGER REFERENCES dpi_d2_warn_parent(id))",
        )

        observed = {
            "ddl_recorded": "DpiD2WarnChild" in db._failed_table_creations,
            "warn_escape_hatch_taken": False,
            "ddl_failed_error": False,
            "other_error": None,
            # Strong refs, so a surviving registry slot cannot be blamed on
            # (or hidden by) WeakValueDictionary GC timing.
            "adapters": adapters,
        }

        # The warn contract: the circuit breaker at the head of every model
        # access sees the recorded failure and returns WITHOUT raising. In
        # fail-fast mode the identical call raises DDLFailedError; that
        # divergence is what proves this is the warn branch and not an
        # incidental success.
        try:
            db._check_failed_ddl("DpiD2WarnChild")
            observed["warn_escape_hatch_taken"] = True
        except DDLFailedError:
            observed["warn_escape_hatch_taken"] = False

        try:
            await db.express.create(
                "DpiD2WarnChild", {"id": id_base + i, "parent_id": 1}
            )
        except DDLFailedError:
            observed["ddl_failed_error"] = True
        except Exception as exc:  # noqa: BLE001 - classified, not swallowed
            observed["other_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            # close() is sync (returns None); close_async() is the awaitable
            # cleanup (rules/patterns.md § Async Resource Cleanup).
            await db.close_async()
        return observed

    results = _run_each_on_its_own_event_loop(_attempt_access_warn)

    # The path under test really is the DDL-failure path, in warn mode.
    assert all(r["ddl_recorded"] for r in results), (
        "Expected a recorded FailedDDLRecord on every warn-mode instance; "
        "without it this test measures nothing about DDL failure"
    )
    assert all(r["warn_escape_hatch_taken"] for r in results), (
        "auto_migrate='warn' MUST log-and-continue past a recorded DDL "
        "failure; _check_failed_ddl raised instead"
    )
    assert not any(r["ddl_failed_error"] for r in results), (
        "warn mode MUST NOT raise DDLFailedError — that is the fail-fast "
        "contract, asserted by the sibling test"
    )
    # The duplicate-key failure class is what this test used to measure by
    # accident. Per-run unique ids remove it; assert it stays removed.
    duplicate_key = [
        r["other_error"]
        for r in results
        if r["other_error"] and "duplicate key" in r["other_error"]
    ]
    assert not duplicate_key, (
        f"duplicate-key failures resurfaced ({len(duplicate_key)}): "
        f"{duplicate_key[:2]}. This test must exercise the warn/DDL-failure "
        "path, not PK collision with rows left by a previous run"
    )

    assert all(r["adapters"] for r in results), (
        "No pool adapter was registered on "
        f"{len([r for r in results if not r['adapters']])} of {INSTANCE_COUNT} "
        "warn-mode loops — the pool-count bound below would be unfalsifiable"
    )

    # Pool count MUST remain bounded regardless of auto_migrate mode.
    # The assertion is UNCHANGED from when this was xfail'd per #2075; only
    # the marker went. The bound was always correct — it was the registry's
    # object-lifetime slot accounting that was wrong.
    assert AsyncSQLDatabaseNode.pool_count() <= POOL_CAP, (
        f"Pool leaked in warn mode: pool_count()={AsyncSQLDatabaseNode.pool_count()} "
        f"> {POOL_CAP} after {INSTANCE_COUNT} DDL-failing DataFlow instances "
        "with auto_migrate='warn'"
    )
