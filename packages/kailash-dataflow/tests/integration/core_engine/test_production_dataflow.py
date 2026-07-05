"""
Comprehensive integration tests for production DataFlow with real databases.

Tier-2 integration suite exercising the REAL ``dataflow.core.engine.DataFlow``
against real infrastructure. Converted from a MOCK engine
(``DataFlowProductionEngine``) under issue #1503 — the mock returned hardcoded
rows so every "verify data in database" assertion passed without real
persistence, a NO-MOCKING (tests/CLAUDE.md §2, rules/testing.md Tier-2)
violation.

Real-infrastructure policy:

- **PostgreSQL** via ``IntegrationTestSuite`` (port 5434, db ``kailash_test``).
  Write read-backs run through a real asyncpg connection acquired from the
  suite pool (``test_suite.get_connection()``) — a *separate* connection from
  DataFlow's own pool, proving cross-connection persistence.
- **SQLite** is file-backed via ``tempfile`` (NOT ``:memory:`` — DataFlow's
  migration pool opens multiple short-lived connections and bare ``:memory:``
  gives each its own database, breaking the migration handshake). DataFlow's
  SQLite pool connection is NOT visible to a fresh ``sqlite3.connect(path)``
  client (documented multi-connection caveat, tests/CLAUDE.md), so SQLite
  read-backs go through DataFlow READ/LIST nodes — still a real query against
  the same file through the engine (State Persistence Verification).
- **MySQL** is gated by a live-connection probe (suite convention, port 3307);
  it SKIPS when MySQL is absent from the environment (acceptable
  cannot-execute-in-this-env skip, NOT a mock, NOT a masked failure).

Observed real node return contract (no ``success``/``data`` wrapper — the mock's
shape was fiction):

- CreateNode  → flat record dict; PG/MySQL include ``id``; SQLite returns
  ``rows_affected`` with NO ``id`` (capture id from a subsequent LIST).
- ReadNode    → flat record dict + ``found``; not-found sets ``error``.
- ListNode    → ``{"records": [...], "count": N, "limit": ...}``.
- UpdateNode  → flat updated record + ``updated`` (SQLite may not echo changed
  columns flat — verify via read-back).
- DeleteNode  → ``{"id": ..., "deleted": True}``.
- Bulk*Node   → ``{"success": True, "processed": N, "inserted"/"updated": N,
  "operation": ...}``.

Success is the ABSENCE of an ``error`` key (the ``test_sqlite_integration``
reference-test convention), never a mock ``success is True`` flag.
"""

import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import WorkflowValidationError
from kailash.workflow.builder import WorkflowBuilder

# REAL production engine (NOT the tests.fixtures mock).
from dataflow import DataFlow

from tests.infrastructure.test_harness import IntegrationTestSuite

try:
    import pymysql

    PYMYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover - env-dependent
    PYMYSQL_AVAILABLE = False


# --------------------------------------------------------------------------- #
# MySQL availability probe (suite convention — real connection, no mock).
# --------------------------------------------------------------------------- #
def _mysql_url() -> str:
    """Resolve the MySQL test URL (env override → SDK Docker default 3307)."""
    return os.getenv(
        "TEST_MYSQL_URL",
        os.getenv(
            "MYSQL_URL",
            "mysql://kailash_test:test_password@localhost:3307/kailash_test",
        ),
    )


def _is_mysql_available() -> bool:
    """True only when a real MySQL server answers on the test port."""
    if not PYMYSQL_AVAILABLE:
        return False
    try:
        conn = pymysql.connect(
            host="localhost",
            port=3307,
            database="kailash_test",
            user="kailash_test",
            password="test_password",
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with real infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Context-managed LocalRuntime for workflow execution (auto-cleanup)."""
    with LocalRuntime() as rt:
        yield rt


class TestProductionDataFlowRealDatabase:
    """Test the real DataFlow engine with real database operations — no mocks."""

    # ------------------------------------------------------------------ #
    # Shared CRUD cycle — real writes, every write verified with a read-back.
    # ------------------------------------------------------------------ #
    async def _run_crud_cycle(self, db, runtime, *, dialect, test_suite=None):
        """Full CRUD cycle against the real engine with real read-backs."""

        @db.model
        class TestProduct:
            name: str
            price: float
            category: str = "general"
            active: bool = True

        await db.initialize()
        table = db._get_table_name("TestProduct")

        # For PostgreSQL, ensure a clean slate and read back through a
        # SEPARATE real connection from the suite pool.
        if dialect == "postgresql":
            await db.ensure_table_exists("TestProduct")
            async with test_suite.get_connection() as conn:
                await conn.execute(f"DELETE FROM {table}")

        async def read_back(pid):
            """Return the persisted row as a dict, or None if absent.

            PostgreSQL: SELECT via a separate asyncpg connection (proves the
            write is visible cross-connection). SQLite/MySQL: DataFlow READ
            node against the same file/db through the engine — a fresh
            sqlite3 client cannot see DataFlow's pooled connection.
            """
            if dialect == "postgresql":
                async with test_suite.get_connection() as conn:
                    row = await conn.fetchrow(
                        f"SELECT id, name, price, category, active "
                        f"FROM {table} WHERE id = $1",
                        pid,
                    )
                    return dict(row) if row else None
            w = WorkflowBuilder()
            w.add_node("TestProductReadNode", "rb", {"id": pid})
            r, _ = runtime.execute(w.build())
            res = r["rb"]
            return None if res.get("error") else res

        # ---- CREATE -------------------------------------------------- #
        w = WorkflowBuilder()
        w.add_node(
            "TestProductCreateNode",
            "create_product",
            {"name": "Test Laptop", "price": 999.99, "category": "electronics"},
        )
        cr, _ = runtime.execute(w.build())
        assert not cr["create_product"].get(
            "error"
        ), f"CREATE failed in {dialect}: {cr['create_product'].get('error')}"

        # Capture id: PG/MySQL return it on create; SQLite does not — read
        # it back from a LIST (real query).
        product_id = cr["create_product"].get("id")
        if product_id is None:
            w = WorkflowBuilder()
            w.add_node(
                "TestProductListNode",
                "seed_list",
                {"filter": {"category": "electronics"}, "limit": 50},
            )
            lr, _ = runtime.execute(w.build())
            records = lr["seed_list"]["records"]
            assert records, f"created product not listed in {dialect}"
            product_id = records[0]["id"]
        assert product_id is not None

        # Verify CREATE persisted (read-back).
        persisted = await read_back(product_id)
        assert persisted is not None, f"product not persisted in {dialect}"
        assert persisted["name"] == "Test Laptop"
        assert abs(float(persisted["price"]) - 999.99) < 0.01
        assert persisted["category"] == "electronics"

        # ---- READ (node) --------------------------------------------- #
        w = WorkflowBuilder()
        w.add_node("TestProductReadNode", "read_product", {"id": product_id})
        rr, _ = runtime.execute(w.build())
        assert not rr["read_product"].get(
            "error"
        ), f"READ failed in {dialect}: {rr['read_product'].get('error')}"
        assert rr["read_product"]["name"] == "Test Laptop"

        # ---- UPDATE (filter + fields) -------------------------------- #
        w = WorkflowBuilder()
        w.add_node(
            "TestProductUpdateNode",
            "update_product",
            {
                "filter": {"id": product_id},
                "fields": {"price": 899.99, "active": False},
            },
        )
        ur, _ = runtime.execute(w.build())
        assert not ur["update_product"].get(
            "error"
        ), f"UPDATE failed in {dialect}: {ur['update_product'].get('error')}"

        # Verify UPDATE persisted (read-back — the UpdateNode may not echo
        # changed columns flat on every dialect, so the read-back is the
        # authoritative State-Persistence check).
        persisted = await read_back(product_id)
        assert persisted is not None
        assert abs(float(persisted["price"]) - 899.99) < 0.01
        assert persisted["active"] in (False, 0)

        # ---- LIST ---------------------------------------------------- #
        w = WorkflowBuilder()
        w.add_node(
            "TestProductListNode",
            "list_products",
            {"filter": {"category": "electronics"}, "limit": 50},
        )
        lr, _ = runtime.execute(w.build())
        assert not lr["list_products"].get(
            "error"
        ), f"LIST failed in {dialect}: {lr['list_products'].get('error')}"
        products = lr["list_products"]["records"]
        assert any(p["id"] == product_id for p in products)

        # ---- DELETE -------------------------------------------------- #
        w = WorkflowBuilder()
        w.add_node("TestProductDeleteNode", "delete_product", {"id": product_id})
        dr, _ = runtime.execute(w.build())
        assert not dr["delete_product"].get(
            "error"
        ), f"DELETE failed in {dialect}: {dr['delete_product'].get('error')}"

        # Verify DELETE persisted (read-back returns None).
        assert (
            await read_back(product_id)
        ) is None, f"product still present after delete in {dialect}"

    @pytest.mark.requires_postgres
    async def test_postgresql_crud_operations(self, test_suite, runtime):
        """Complete CRUD cycle with real PostgreSQL + cross-connection read-backs."""
        db = DataFlow(test_suite.config.url)
        try:
            await self._run_crud_cycle(
                db, runtime, dialect="postgresql", test_suite=test_suite
            )
        finally:
            await db.close_async()

    @pytest.mark.requires_mysql
    @pytest.mark.skipif(
        not _is_mysql_available(),
        reason="MySQL not available on port 3307 — real infra absent "
        "(cannot-execute-in-this-env skip; NOT mocked). Start Docker MySQL to run.",
    )
    async def test_mysql_crud_operations(self, runtime):
        """Complete CRUD cycle with real MySQL (skips when MySQL is absent)."""
        db = DataFlow(_mysql_url())
        try:
            await self._run_crud_cycle(db, runtime, dialect="mysql")
        finally:
            await db.close_async()

    async def test_sqlite_crud_operations(self, runtime):
        """Complete CRUD cycle with real file-backed SQLite + node read-backs."""
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = DataFlow(f"sqlite:///{db_path}")
        try:
            await self._run_crud_cycle(db, runtime, dialect="sqlite")
        finally:
            await db.close_async()
            if os.path.exists(db_path):
                os.unlink(db_path)

    @pytest.mark.requires_postgres
    async def test_bulk_operations_real_database(self, test_suite, runtime):
        """Bulk create/update against real PostgreSQL, verified with read-backs."""
        db = DataFlow(test_suite.config.url)
        try:

            @db.model
            class BulkTestModel:
                name: str
                value: int
                category: str = "test"

            await db.initialize()
            table = db._get_table_name("BulkTestModel")
            await db.ensure_table_exists("BulkTestModel")
            async with test_suite.get_connection() as conn:
                await conn.execute(f"DELETE FROM {table}")

            n_rows = 200
            bulk_data = [
                {"name": f"Item_{i}", "value": i, "category": f"cat_{i % 5}"}
                for i in range(n_rows)
            ]

            # ---- BULK CREATE ---------------------------------------- #
            w = WorkflowBuilder()
            w.add_node(
                "BulkTestModelBulkCreateNode",
                "bulk_create",
                {"data": bulk_data, "batch_size": 100},
            )
            start = time.time()
            br, _ = runtime.execute(w.build())
            elapsed = time.time() - start

            bc = br["bulk_create"]
            assert not bc.get("error"), f"BULK CREATE failed: {bc.get('error')}"
            assert bc["success"] is True
            assert bc["processed"] == n_rows
            assert bc["inserted"] == n_rows

            # Read-back: real row count via a separate connection.
            async with test_suite.get_connection() as conn:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            assert count == n_rows, f"expected {n_rows} rows, found {count}"
            assert elapsed > 0

            # ---- BULK UPDATE ---------------------------------------- #
            expected_updated = sum(1 for i in range(n_rows) if i % 5 == 0)
            w = WorkflowBuilder()
            w.add_node(
                "BulkTestModelBulkUpdateNode",
                "bulk_update",
                {
                    "filter": {"category": "cat_0"},
                    "fields": {"value": 9999},
                    "batch_size": 50,
                },
            )
            ur, _ = runtime.execute(w.build())
            bu = ur["bulk_update"]
            assert not bu.get("error"), f"BULK UPDATE failed: {bu.get('error')}"
            assert bu["success"] is True

            # Read-back: verify exactly the cat_0 rows were updated.
            async with test_suite.get_connection() as conn:
                updated = await conn.fetchval(
                    f"SELECT COUNT(*) FROM {table} WHERE value = 9999"
                )
            assert (
                updated == expected_updated
            ), f"expected {expected_updated} updated rows, found {updated}"
        finally:
            await db.close_async()

    @pytest.mark.requires_postgres
    async def test_security_features_real_database(self, test_suite, runtime):
        """Real multi-tenant isolation + input-sanitizer behavior on PostgreSQL."""
        db = DataFlow(test_suite.config.url, multi_tenant=True, audit_logging=True)
        try:

            @db.model
            class SecureModel:
                name: str
                sensitive_data: str

            await db.initialize()
            table = db._get_table_name("SecureModel")
            await db.ensure_table_exists("SecureModel")
            async with test_suite.get_connection() as conn:
                await conn.execute(f"DELETE FROM {table}")

            # Real tenant binding: register + switch() (the canonical
            # contextvar path the QueryInterceptor reads — NOT the legacy
            # set_tenant_context() dict; see rules/tenant-isolation.md Rule 6).
            ctx = db.tenant_context
            ctx.register_tenant("tenant_a", "Tenant A")
            ctx.register_tenant("tenant_b", "Tenant B")

            # ---- TENANT ISOLATION ----------------------------------- #
            with ctx.switch("tenant_a"):
                w = WorkflowBuilder()
                w.add_node(
                    "SecureModelCreateNode",
                    "create_a",
                    {"name": "Tenant A Data", "sensitive_data": "Secret A"},
                )
                ra, _ = runtime.execute(w.build())
                assert not ra["create_a"].get("error")
                tenant_a_id = ra["create_a"].get("id")
                assert tenant_a_id is not None

            with ctx.switch("tenant_b"):
                w = WorkflowBuilder()
                w.add_node(
                    "SecureModelCreateNode",
                    "create_b",
                    {"name": "Tenant B Data", "sensitive_data": "Secret B"},
                )
                rb, _ = runtime.execute(w.build())
                assert not rb["create_b"].get("error")

            # Tenant A must see ONLY tenant A data.
            with ctx.switch("tenant_a"):
                w = WorkflowBuilder()
                w.add_node("SecureModelListNode", "list_a", {})
                la, _ = runtime.execute(w.build())
                tenant_a_rows = la["list_a"]["records"]
            assert len(tenant_a_rows) == 1, f"tenant leak: {tenant_a_rows}"
            assert tenant_a_rows[0]["id"] == tenant_a_id
            assert tenant_a_rows[0]["name"] == "Tenant A Data"

            # Read-back: tenant_id column persisted correctly (separate conn).
            async with test_suite.get_connection() as conn:
                stored_tenant = await conn.fetchval(
                    f"SELECT tenant_id FROM {table} WHERE id = $1", tenant_a_id
                )
            assert stored_tenant == "tenant_a"

            # ---- INJECTION SANITIZER -------------------------------- #
            # The real engine does NOT raise on a keyword-sequence payload; it
            # token-replaces dangerous sequences with grep-able sentinels
            # (STATEMENT_BLOCKED / COMMENT_BLOCKED) per security.md
            # § Sanitizer Contract Rule 1. The table survives; the payload is
            # neutralized in storage.
            with ctx.switch("tenant_a"):
                w = WorkflowBuilder()
                w.add_node(
                    "SecureModelCreateNode",
                    "malicious",
                    {
                        "name": "'; DROP TABLE secure_models; --",
                        "sensitive_data": "malicious",
                    },
                )
                mr, _ = runtime.execute(w.build())
            assert not mr["malicious"].get(
                "error"
            ), "sanitizer should neutralize, not error, on the payload"

            async with test_suite.get_connection() as conn:
                # Table still exists and was NOT dropped.
                total = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                stored_names = await conn.fetch(
                    f"SELECT name FROM {table} WHERE name LIKE '%BLOCKED%'"
                )
            assert total >= 2, "table compromised by injection"
            assert stored_names, "dangerous payload was not token-replaced"
            neutralized = stored_names[0]["name"]
            assert "STATEMENT_BLOCKED" in neutralized
            assert "DROP TABLE" not in neutralized
        finally:
            await db.close_async()

    @pytest.mark.performance
    @pytest.mark.requires_postgres
    async def test_performance_benchmarks(self, test_suite, runtime):
        """Real latency/throughput measurement on PostgreSQL with persistence proof.

        Thresholds are calibrated to REAL engine behavior (per-operation
        workflow construction + a real INSERT), not the removed mock's
        instant returns. The load-bearing assertion is real persistence
        (row-count read-back); the latency ceiling is a generous regression
        guard, not the mock-era p95<50ms / avg<20ms fiction.
        """
        db = DataFlow(test_suite.config.url)
        try:

            @db.model
            class PerformanceTest:
                name: str
                value: int

            await db.initialize()
            table = db._get_table_name("PerformanceTest")
            await db.ensure_table_exists("PerformanceTest")
            async with test_suite.get_connection() as conn:
                await conn.execute(f"DELETE FROM {table}")

            # ---- Sequential latency -------------------------------- #
            n_seq = 30
            latencies = []
            for i in range(n_seq):
                w = WorkflowBuilder()
                w.add_node(
                    "PerformanceTestCreateNode",
                    "create",
                    {"name": f"Perf {i}", "value": i},
                )
                start = time.time()
                r, _ = runtime.execute(w.build())
                latencies.append((time.time() - start) * 1000)
                assert not r["create"].get("error")

            latencies.sort()
            p50 = latencies[len(latencies) // 2]
            p95 = latencies[int(len(latencies) * 0.95)]
            avg = sum(latencies) / len(latencies)
            print(
                f"\nReal single-op latency (ms): avg={avg:.1f} "
                f"p50={p50:.1f} p95={p95:.1f}"
            )
            # Generous ceiling — real avg observed ~40ms; guards against an
            # order-of-magnitude regression, not the mock-era 20ms fiction.
            assert avg < 500, f"avg latency {avg:.1f}ms — order-of-magnitude regression"

            # ---- Concurrent operations ----------------------------- #
            def concurrent_op(thread_id: int):
                w = WorkflowBuilder()
                w.add_node(
                    "PerformanceTestCreateNode",
                    "create",
                    {"name": f"Concurrent {thread_id}", "value": 1000 + thread_id},
                )
                with LocalRuntime() as rt:
                    res, _ = rt.execute(w.build())
                return res["create"].get("error") is None

            n_conc = 10
            start = time.time()
            with ThreadPoolExecutor(max_workers=n_conc) as executor:
                oks = list(executor.map(concurrent_op, range(n_conc)))
            total_time = time.time() - start
            assert all(oks), "some concurrent operations failed"
            throughput = n_conc / total_time
            print(f"Concurrent throughput: {throughput:.1f} ops/sec")
            assert throughput > 0

            # ---- Persistence proof (read-back) --------------------- #
            async with test_suite.get_connection() as conn:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            assert (
                count == n_seq + n_conc
            ), f"expected {n_seq + n_conc} persisted rows, found {count}"
        finally:
            await db.close_async()

    async def test_error_handling_real_database(self, runtime):
        """Real validation/error behavior on file-backed SQLite."""
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = DataFlow(f"sqlite:///{db_path}")
        try:

            @db.model
            class ErrorTestModel:
                name: str
                value: int

            await db.initialize()

            # Missing required field → WorkflowValidationError (raised at
            # workflow.validate, before the node runs).
            with pytest.raises(WorkflowValidationError):
                w = WorkflowBuilder()
                w.add_node("ErrorTestModelCreateNode", "create", {"name": "Test"})
                runtime.execute(w.build())

            # Invalid type (str for int) → WorkflowValidationError.
            with pytest.raises(WorkflowValidationError):
                w = WorkflowBuilder()
                w.add_node(
                    "ErrorTestModelCreateNode",
                    "create",
                    {"name": "Test", "value": "not_an_integer"},
                )
                runtime.execute(w.build())

            # Read a non-existent record → no raise; result carries an error
            # marker and no record fields (the engine surfaces not-found in
            # the result, it does not throw).
            w = WorkflowBuilder()
            w.add_node("ErrorTestModelReadNode", "read", {"id": 99999})
            r, _ = runtime.execute(w.build())
            assert r["read"].get("error") is not None
            assert r["read"].get("found") in (None, False)
            assert r["read"].get("name") is None
        finally:
            await db.close_async()
            if os.path.exists(db_path):
                os.unlink(db_path)

    async def test_health_check_real_database(self, runtime):
        """Real health-check shape on file-backed SQLite."""
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = DataFlow(f"sqlite:///{db_path}")
        try:

            @db.model
            class HealthProbe:
                name: str

            await db.initialize()

            health = db.health_check()

            # Real engine health contract (NOT the mock's nested
            # components.database.status/url/pool_size shape).
            assert health["status"] in ("healthy", "degraded", "unhealthy")
            assert health["database"] == "connected"
            assert "models_registered" in health
            assert "components" in health
            assert health["components"]["database"] == "ok"
        finally:
            await db.close_async()
            if os.path.exists(db_path):
                os.unlink(db_path)
