"""Issue #1083 follow-up — `TransactionScope.execute_raw` write-protection
enforcement (same-bug-class with #1050/#1058).

Surfaced 2026-05-18 by the multi-agent /redteam Round 2 against the
#1083 closure. R2 (pact-specialist pentest axis) found that
`TransactionScope.execute_raw(sql, params)` was the 4th DataFlow write
surface NOT routed through `WriteProtectionEngine.check_operation`
(spec invariant I1). Without this fix a caller with `read_only_mode=True`
could `DELETE FROM users WHERE id = $1` through
`async with db.transactions.begin() as tx: await tx.execute_raw(...)`.

The fix wires `TransactionScope.execute_raw` (async) and
`SyncTransactionScope.execute_raw` (sync) through a shared helper
`_execute_raw_with_protection` that classifies the raw SQL by leading
keyword and calls `check_operation` BEFORE dispatching to the
underlying connection. SELECT/WITH/SHOW/EXPLAIN route as "read"
(always allowed under read-only); INSERT/UPDATE/DELETE/UPSERT route
to their existing OperationType values; DDL falls through to
CUSTOM_QUERY (BLOCKED under read_only_global / production_safe).

Invariant pinned: every DataFlow mutation surface that takes raw SQL
MUST route through `check_operation` before touching the connection
(spec invariant I1 extended to the transactions surface).

Tier-2 infrastructure (NO mocking — `rules/testing.md` § Tier 2):
file-backed SQLite via `tempfile.mkdtemp()` + `sqlite:///<tmp>/test.db`
per the migration-pool handshake constraint at
`packages/kailash-dataflow/tests/CLAUDE.md`. The transactions surface
is dialect-agnostic; SQLite alone proves the check fires before the
underlying connection executes (the same fix code path runs on asyncpg).

State-persistence verification: reads ARE allowed under read-only
(spec invariant I7), so a read-back AFTER the block + AFTER releasing
the transaction-scope confirms the row's pre-block value survived.
"""

import socket
import tempfile
from typing import Iterator

import pytest

from dataflow.core.protected_engine import ProtectedDataFlow
from dataflow.core.protection import ProtectionViolation

# PostgreSQL test infra — shared SDK Docker on port 5434 per
# `packages/kailash-dataflow/tests/CLAUDE.md`. Async TransactionManager
# requires asyncpg-backed connection_pool; SQLite is not supported on
# that surface today, so async tests SKIP cleanly when PG is unreachable
# (mirrors the dialect-skip pattern in test_issue_1050_*.py). Sync tests
# use SyncTransactionManager which DOES own aiosqlite lifecycle and
# runs against file-SQLite without PG.
PG_URL = "postgresql://test_user:test_password@localhost:5434/kailash_test"


def _pg_reachable() -> bool:
    """Probe the shared SDK Docker PostgreSQL on port 5434."""
    try:
        with socket.create_connection(("localhost", 5434), timeout=1):
            return True
    except (OSError, socket.timeout):
        return False


_pg_available = _pg_reachable()


@pytest.fixture
def sqlite_url() -> Iterator[str]:
    """file-backed SQLite URL — bare ``:memory:`` breaks DataFlow's
    multi-connection migration handshake; see
    ``packages/kailash-dataflow/tests/CLAUDE.md``.
    """
    tmpdir = tempfile.mkdtemp(prefix="issue1083_followup_txn_raw_")
    yield f"sqlite:///{tmpdir}/test.db"


@pytest.mark.integration
@pytest.mark.timeout(30)
@pytest.mark.skipif(
    not _pg_available,
    reason="async TransactionManager requires asyncpg pool; PG on port 5434 unreachable",
)
class TestTransactionsExecuteRawProtection:
    """Issue #1083 follow-up — TransactionScope.execute_raw enforcement.

    PG-only because async TransactionManager has no SQLite path today;
    SyncTransactionManager (below) covers the same fix on aiosqlite.
    """

    @pytest.mark.asyncio
    async def test_async_execute_raw_blocks_delete_under_read_only(self):
        """`tx.execute_raw("DELETE FROM ...")` MUST raise ProtectionViolation
        under read-only AND the row MUST survive the block.
        """
        db = ProtectedDataFlow(database_url=PG_URL, enable_protection=True)

        @db.model  # noqa: B903
        class _DocAsync:
            id: str
            title: str

        try:
            await db.initialize()

            seed = await db.express.create(
                "_DocAsync", {"id": "seed-1", "title": "original"}
            )
            assert seed["id"] == "seed-1"

            db.enable_read_only_mode("issue #1083 follow-up txn raw delete")

            # The bypass surface: raw DELETE through transactions.
            with pytest.raises(ProtectionViolation):
                async with db.transactions.begin() as tx:
                    await tx.execute_raw(
                        "DELETE FROM _docasync WHERE id = ?", ["seed-1"]
                    )

            # READ is allowed under read-only (spec invariant I7) —
            # read-back confirms the row survived the block.
            row = await db.express.read("_DocAsync", "seed-1")
            assert row is not None
            assert row["title"] == "original"
        finally:
            await db.close_async()

    @pytest.mark.asyncio
    async def test_async_execute_raw_blocks_update_under_read_only(self):
        """`tx.execute_raw("UPDATE ...")` MUST raise ProtectionViolation
        under read-only AND the original value MUST survive.
        """
        db = ProtectedDataFlow(database_url=PG_URL, enable_protection=True)

        @db.model  # noqa: B903
        class _DocUpd:
            id: str
            title: str

        try:
            await db.initialize()
            await db.express.create("_DocUpd", {"id": "seed-1", "title": "original"})

            db.enable_read_only_mode("issue #1083 follow-up txn raw update")

            with pytest.raises(ProtectionViolation):
                async with db.transactions.begin() as tx:
                    await tx.execute_raw(
                        "UPDATE _docupd SET title = ? WHERE id = ?",
                        ["MUTATED", "seed-1"],
                    )

            row = await db.express.read("_DocUpd", "seed-1")
            assert row is not None
            assert row["title"] == "original"
        finally:
            await db.close_async()

    @pytest.mark.asyncio
    async def test_async_execute_raw_allows_select_under_read_only(self):
        """SELECT through `tx.execute_raw(...)` MUST be allowed under
        read-only — the classifier maps SELECT to "read" which
        WriteProtectionEngine permits (spec invariant I7).
        """
        db = ProtectedDataFlow(database_url=PG_URL, enable_protection=True)

        @db.model  # noqa: B903
        class _DocRead:
            id: str
            title: str

        try:
            await db.initialize()
            await db.express.create("_DocRead", {"id": "seed-1", "title": "original"})

            db.enable_read_only_mode("issue #1083 follow-up txn raw select")

            # MUST NOT raise — proves SELECT routes through the
            # classifier as "read" and not as a write.
            async with db.transactions.begin() as tx:
                rows = await tx.execute_raw(
                    "SELECT id, title FROM _docread WHERE id = ?", ["seed-1"]
                )
            assert rows is not None
        finally:
            await db.close_async()

    @pytest.mark.asyncio
    async def test_async_execute_raw_works_when_protection_disabled(self):
        """Sanity — the new protection wiring does NOT regress the
        un-protected DataFlow path. Construction with
        ``enable_protection=False`` lets every raw SQL through.
        """
        db = ProtectedDataFlow(database_url=PG_URL, enable_protection=False)

        @db.model  # noqa: B903
        class _DocOff:
            id: str
            title: str

        try:
            await db.initialize()
            await db.express.create("_DocOff", {"id": "seed-1", "title": "original"})

            async with db.transactions.begin() as tx:
                await tx.execute_raw(
                    "UPDATE _docoff SET title = ? WHERE id = ?",
                    ["MUTATED", "seed-1"],
                )

            row = await db.express.read("_DocOff", "seed-1")
            assert row is not None
            assert row["title"] == "MUTATED"
        finally:
            await db.close_async()


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestSyncTransactionsExecuteRawProtection:
    """Issue #1083 follow-up — SyncTransactionScope.execute_raw enforcement.

    Sync surface mirrors the async surface; the same
    `_execute_raw_with_protection` helper enforces the contract via the
    BG-loop event submitter.
    """

    @pytest.mark.asyncio
    async def test_sync_execute_raw_blocks_delete_under_read_only(self, sqlite_url):
        """`tx.execute_raw("DELETE FROM ...")` through the sync scope MUST
        raise ProtectionViolation under read-only.
        """
        db = ProtectedDataFlow(database_url=sqlite_url, enable_protection=True)

        @db.model  # noqa: B903
        class _DocSync:
            id: str
            title: str

        try:
            await db.initialize()
            await db.express.create("_DocSync", {"id": "seed-1", "title": "original"})

            db.enable_read_only_mode("issue #1083 follow-up txn raw sync delete")

            with pytest.raises(ProtectionViolation):
                with db.transactions_sync.begin() as tx:
                    tx.execute_raw("DELETE FROM _docsync WHERE id = ?", ["seed-1"])

            row = await db.express.read("_DocSync", "seed-1")
            assert row is not None
            assert row["title"] == "original"
        finally:
            await db.close_async()
