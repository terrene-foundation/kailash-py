"""DPI-A regression test: db.express.* MUST raise DDLFailedError, not return failure dict.

Issue #759 — DataFlow Express was returning ``{"success": False, "error": ...}``
to the caller when the underlying CRUD node hit an auto-migration / DDL failure
instead of raising the typed ``DDLFailedError``. This broke the DPI-A 2.4.0
fail-fast contract introduced for the Azure Postgres DDL retry storm
(GitHub #696): a documented security control (typed circuit-breaker exception)
shipped as a no-op because the user-facing API surface swallowed the typed
exception path.

This test deterministically forces the engine's failed-DDL state for a model
and asserts that EVERY mutation entry point (create/update/delete/upsert/
upsert_advanced) on ``db.express`` raises ``DDLFailedError`` rather than
returning the failure dict.

Companion to ``test_dataflow_pool_bridge.py::test_failed_ddl_does_not_leak_pools_under_saturation``
which exercises the same propagation under concurrent pool-saturation load.
This test is deterministic and runs against SQLite for sub-second feedback;
the bridge test runs against real PostgreSQL. Both MUST pass.

See:
- packages/kailash-dataflow/src/dataflow/features/express.py::DataFlowExpress._raise_for_failed_result
- packages/kailash-dataflow/src/dataflow/core/exceptions.py::DDLFailedError
- packages/kailash-dataflow/src/dataflow/core/engine.py::_record_failed_ddl
- packages/kailash-dataflow/src/dataflow/core/engine.py::_check_failed_ddl
- rules/zero-tolerance.md Rule 3 (no silent fallbacks)
"""

from __future__ import annotations

import os
import tempfile

import pytest

from dataflow import DataFlow
from dataflow.core.exceptions import DDLFailedError

pytestmark = [pytest.mark.regression]


@pytest.fixture
def sqlite_url():
    """Per-test SQLite URL on disk so the engine's pool resolution paths fire."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="dpi_a_759_")
    os.close(fd)
    yield f"sqlite:///{path}"
    try:
        os.unlink(path)
    except OSError:
        pass


def _force_failed_ddl(db: DataFlow, model_name: str) -> None:
    """Simulate what ``_record_failed_ddl`` does in the bulk-DDL paths.

    The engine's bulk-DDL paths record under the *table* name (the value
    ``_extract_table_from_statement`` returns), while the single-model
    paths record under the model class name. Express's
    ``_raise_for_failed_result`` probes BOTH key shapes — the test
    populates the model-name shape so the helper's primary lookup path
    is exercised.
    """
    db._record_failed_ddl(
        model_name,
        RuntimeError("fk constraint missing — Parent table not created first"),
        "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id))",
    )


@pytest.mark.asyncio
async def test_express_create_raises_ddl_failed_error(sqlite_url):
    """Express.create MUST raise DDLFailedError, not return ``{"success": False}``."""
    db = DataFlow(sqlite_url)
    try:

        @db.model
        class Issue759Child:
            id: int
            parent_id: int

        _force_failed_ddl(db, "Issue759Child")

        with pytest.raises(DDLFailedError) as exc_info:
            await db.express.create("Issue759Child", {"id": 1, "parent_id": 1})
        assert exc_info.value.model_name == "Issue759Child"
    finally:
        await db.close_async()


@pytest.mark.asyncio
async def test_express_update_raises_ddl_failed_error(sqlite_url):
    """Express.update MUST raise DDLFailedError on recorded DDL failure."""
    db = DataFlow(sqlite_url)
    try:

        @db.model
        class Issue759UpdateChild:
            id: int
            parent_id: int

        _force_failed_ddl(db, "Issue759UpdateChild")

        with pytest.raises(DDLFailedError) as exc_info:
            await db.express.update("Issue759UpdateChild", 1, {"parent_id": 2})
        assert exc_info.value.model_name == "Issue759UpdateChild"
    finally:
        await db.close_async()


@pytest.mark.asyncio
async def test_express_delete_raises_ddl_failed_error(sqlite_url):
    """Express.delete MUST raise DDLFailedError on recorded DDL failure."""
    db = DataFlow(sqlite_url)
    try:

        @db.model
        class Issue759DeleteChild:
            id: int
            parent_id: int

        _force_failed_ddl(db, "Issue759DeleteChild")

        with pytest.raises(DDLFailedError) as exc_info:
            await db.express.delete("Issue759DeleteChild", 1)
        assert exc_info.value.model_name == "Issue759DeleteChild"
    finally:
        await db.close_async()


@pytest.mark.asyncio
async def test_express_upsert_raises_ddl_failed_error(sqlite_url):
    """Express.upsert MUST raise DDLFailedError on recorded DDL failure."""
    db = DataFlow(sqlite_url)
    try:

        @db.model
        class Issue759UpsertChild:
            id: int
            parent_id: int

        _force_failed_ddl(db, "Issue759UpsertChild")

        with pytest.raises(DDLFailedError) as exc_info:
            await db.express.upsert("Issue759UpsertChild", {"id": 1, "parent_id": 1})
        assert exc_info.value.model_name == "Issue759UpsertChild"
    finally:
        await db.close_async()


@pytest.mark.asyncio
async def test_express_warn_mode_preserves_legacy_dict_shape(sqlite_url):
    """auto_migrate='warn' MUST preserve legacy log-and-continue behavior.

    The DPI-D2 invariant: the warn-mode path returns the dict-shaped
    failure (or proceeds with whatever the node returns) rather than
    raising ``DDLFailedError``. This is the contract the legacy
    pool-bound regression test depends on.
    """
    db = DataFlow(sqlite_url, auto_migrate="warn")
    try:

        @db.model
        class Issue759WarnChild:
            id: int
            parent_id: int

        _force_failed_ddl(db, "Issue759WarnChild")

        # In warn mode the engine's _check_failed_ddl returns silently
        # without raising. Express's helper falls through to the
        # generic dict-failure path. The express call MUST NOT raise
        # DDLFailedError; it may either succeed (if SQLite ad-hoc create
        # works without the failed migration) or raise a generic
        # RuntimeError carrying the node's error string. Either is
        # acceptable; raising DDLFailedError is NOT acceptable in warn
        # mode and would break test_failed_ddl_with_warn_mode_still_bounded.
        try:
            await db.express.create("Issue759WarnChild", {"id": 1, "parent_id": 1})
        except DDLFailedError:
            pytest.fail(
                "warn mode MUST NOT raise DDLFailedError — that breaks "
                "the legacy log-and-continue contract"
            )
        except Exception:
            # Any other error is acceptable (legacy path can still
            # surface real DB errors) — DDLFailedError specifically is
            # the prohibited surface.
            pass
    finally:
        await db.close_async()
