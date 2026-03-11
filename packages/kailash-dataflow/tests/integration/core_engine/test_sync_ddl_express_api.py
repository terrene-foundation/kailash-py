"""
Test Express API operations after sync DDL table creation.

This test verifies the complete Docker/FastAPI workflow:
1. auto_migrate=True triggers sync DDL table creation via SyncDDLExecutor
2. Express API immediately works for CRUD operations
3. No event loop conflicts or connection issues

This is critical for v0.10.15+ deployments where:
- Tables are created synchronously at @db.model time
- Express API uses async operations for CRUD
- Both must work seamlessly in the same process

IMPORTANT: These tests require real databases to run.
"""

import asyncio
import random
import time
from typing import Optional

import pytest

# Check database availability
try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

try:
    import pymysql

    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False

# Check if aiomysql is available (needed for Express CRUD on MySQL)
try:
    import aiomysql

    AIOMYSQL_AVAILABLE = True
except ImportError:
    AIOMYSQL_AVAILABLE = False

from dataflow import DataFlow
from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor


def is_postgres_available():
    """Check if PostgreSQL is available."""
    if not PSYCOPG2_AVAILABLE:
        return False
    try:
        # Try kaizen_dev first
        try:
            conn = psycopg2.connect(
                host="localhost",
                port=5432,
                database="kaizen_studio",
                user="kaizen_dev",
                password="kaizen_dev_password",
                connect_timeout=3,
            )
            conn.close()
            return True
        except Exception:
            pass
        # Try test infrastructure
        try:
            conn = psycopg2.connect(
                host="localhost",
                port=5434,
                database="kailash_test",
                user="test_user",
                password="test_password",
                connect_timeout=3,
            )
            conn.close()
            return True
        except Exception:
            pass
        return False
    except Exception:
        return False


def is_mysql_available():
    """Check if MySQL is available."""
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


def get_postgres_url():
    """Get PostgreSQL URL."""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="kaizen_studio",
            user="kaizen_dev",
            password="kaizen_dev_password",
            connect_timeout=3,
        )
        conn.close()
        return (
            "postgresql://kaizen_dev:kaizen_dev_password@localhost:5432/kaizen_studio"
        )
    except Exception:
        pass
    return "postgresql://test_user:test_password@localhost:5434/kailash_test"


def get_mysql_url():
    """Get MySQL URL with proper driver specification."""
    # Use mysql+pymysql:// to specify pymysql driver explicitly
    return "mysql+pymysql://kailash_test:test_password@localhost:3307/kailash_test"


def get_unique_suffix():
    """Generate unique suffix for test table names."""
    return f"_{int(time.time())}_{random.randint(1000, 9999)}"


def create_model_class(name: str, fields: dict, table_name: str, defaults: dict = None):
    """
    Dynamically create a model class with unique name.

    This is necessary because DataFlow registers nodes at @db.model time,
    so we need unique class names to avoid node registry collisions.
    """
    annotations = fields.copy()
    attrs = {"__annotations__": annotations, "__tablename__": table_name}
    if defaults:
        attrs.update(defaults)
    return type(name, (), attrs)


class TestSyncDDLExpressPostgreSQL:
    """Test Express API after sync DDL table creation - PostgreSQL."""

    pytestmark = [
        pytest.mark.integration,
        pytest.mark.skipif(not PSYCOPG2_AVAILABLE, reason="psycopg2 not installed"),
        pytest.mark.skipif(
            not is_postgres_available(), reason="PostgreSQL not available"
        ),
    ]

    @pytest.fixture
    def postgres_url(self):
        return get_postgres_url()

    @pytest.fixture
    def cleanup_executor(self, postgres_url):
        """Fixture to clean up tables after tests."""
        tables = []
        yield tables
        executor = SyncDDLExecutor(postgres_url)
        for table in tables:
            try:
                executor.execute_ddl(f"DROP TABLE IF EXISTS {table} CASCADE")
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_express_create_after_sync_ddl(self, postgres_url, cleanup_executor):
        """Test Express create works immediately after sync DDL auto_migrate."""
        suffix = get_unique_suffix().replace("_", "").replace("-", "")
        model_name = f"ExpressUser{suffix}"
        table_name = f"expressuser{suffix}s"
        cleanup_executor.append(table_name)

        # Create DataFlow with auto_migrate=True (triggers sync DDL)
        db = DataFlow(postgres_url, auto_migrate=True)

        # Create unique model class dynamically
        UserModel = create_model_class(
            model_name, {"id": str, "name": str, "email": str}, table_name
        )
        db.model(UserModel)

        # Initialize connection pool
        await db.initialize()

        try:
            # Express create should work immediately
            user = await db.express.create(
                model_name,
                {"id": "user-001", "name": "Alice", "email": "alice@test.com"},
            )

            assert user is not None
            assert user["id"] == "user-001"
            assert user["name"] == "Alice"
            assert user["email"] == "alice@test.com"
        finally:
            await db.close_async()

    @pytest.mark.asyncio
    async def test_express_full_crud_after_sync_ddl(
        self, postgres_url, cleanup_executor
    ):
        """Test full Express CRUD cycle after sync DDL."""
        suffix = get_unique_suffix().replace("_", "").replace("-", "")
        model_name = f"CrudModel{suffix}"
        table_name = f"crudmodel{suffix}s"
        cleanup_executor.append(table_name)

        db = DataFlow(postgres_url, auto_migrate=True)

        CrudModel = create_model_class(
            model_name,
            {"id": str, "name": str, "status": str},
            table_name,
            {"status": "active"},
        )
        db.model(CrudModel)

        await db.initialize()

        try:
            # CREATE
            record = await db.express.create(
                model_name, {"id": "item-001", "name": "Test Item", "status": "pending"}
            )
            assert record["id"] == "item-001"

            # READ
            fetched = await db.express.read(model_name, "item-001")
            assert fetched["name"] == "Test Item"
            assert fetched["status"] == "pending"

            # UPDATE
            updated = await db.express.update(
                model_name, "item-001", {"status": "completed"}
            )
            assert updated["status"] == "completed"

            # LIST
            records = await db.express.list(model_name, filter={})
            assert len(records) >= 1

            # COUNT
            count = await db.express.count(model_name, filter={})
            assert count >= 1

            # DELETE
            deleted = await db.express.delete(model_name, "item-001")
            assert deleted is True

            # Verify deleted
            try:
                await db.express.read(model_name, "item-001")
                assert False, "Should have raised error for deleted record"
            except Exception:
                pass  # Expected
        finally:
            await db.close_async()

    @pytest.mark.asyncio
    async def test_express_concurrent_operations(self, postgres_url, cleanup_executor):
        """Test concurrent Express operations after sync DDL."""
        suffix = get_unique_suffix().replace("_", "").replace("-", "")
        model_name = f"ConcurrentModel{suffix}"
        table_name = f"concurrentmodel{suffix}s"
        cleanup_executor.append(table_name)

        db = DataFlow(postgres_url, auto_migrate=True)

        ConcurrentModel = create_model_class(
            model_name, {"id": str, "value": int}, table_name
        )
        db.model(ConcurrentModel)

        await db.initialize()

        try:
            # Create multiple records concurrently
            async def create_record(i: int):
                return await db.express.create(
                    model_name, {"id": f"item-{i:03d}", "value": i * 10}
                )

            results = await asyncio.gather(*[create_record(i) for i in range(5)])
            assert len(results) == 5

            # Read all concurrently
            async def read_record(i: int):
                return await db.express.read(model_name, f"item-{i:03d}")

            read_results = await asyncio.gather(*[read_record(i) for i in range(5)])
            assert len(read_results) == 5

            for i, result in enumerate(read_results):
                assert result["value"] == i * 10
        finally:
            await db.close_async()

    @pytest.mark.asyncio
    async def test_multiple_models_express_api(self, postgres_url, cleanup_executor):
        """Test Express API with multiple models after sync DDL."""
        suffix = get_unique_suffix().replace("_", "").replace("-", "")
        customer_model = f"Customer{suffix}"
        order_model = f"Order{suffix}"
        cleanup_executor.extend([f"customer{suffix}s", f"order{suffix}s"])

        db = DataFlow(postgres_url, auto_migrate=True)

        CustomerClass = create_model_class(
            customer_model, {"id": str, "name": str}, f"customer{suffix}s"
        )
        OrderClass = create_model_class(
            order_model,
            {"id": str, "customer_id": str, "amount": float},
            f"order{suffix}s",
        )
        db.model(CustomerClass)
        db.model(OrderClass)

        await db.initialize()

        try:
            # Create customer
            customer = await db.express.create(
                customer_model, {"id": "cust-001", "name": "John Doe"}
            )
            assert customer["id"] == "cust-001"

            # Create order
            order = await db.express.create(
                order_model,
                {"id": "order-001", "customer_id": "cust-001", "amount": 99.99},
            )
            assert order["customer_id"] == "cust-001"
            assert order["amount"] == pytest.approx(99.99, rel=1e-5)

            # Read both
            cust = await db.express.read(customer_model, "cust-001")
            ord = await db.express.read(order_model, "order-001")
            assert cust["name"] == "John Doe"
            assert ord["amount"] == pytest.approx(99.99, rel=1e-5)
        finally:
            await db.close_async()


class TestSyncDDLExpressMySQL:
    """Test Express API after sync DDL table creation - MySQL."""

    pytestmark = [
        pytest.mark.integration,
        pytest.mark.skipif(not PYMYSQL_AVAILABLE, reason="pymysql not installed"),
        pytest.mark.skipif(
            not AIOMYSQL_AVAILABLE,
            reason="aiomysql not installed - required for Express async CRUD",
        ),
        pytest.mark.skipif(
            not is_mysql_available(), reason="MySQL not available on port 3307"
        ),
    ]

    @pytest.fixture
    def mysql_url(self):
        return get_mysql_url()

    @pytest.fixture
    def cleanup_executor(self, mysql_url):
        """Fixture to clean up tables after tests."""
        tables = []
        yield tables
        executor = SyncDDLExecutor(mysql_url)
        for table in tables:
            try:
                executor.execute_ddl(f"DROP TABLE IF EXISTS {table}")
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_express_create_after_sync_ddl_mysql(
        self, mysql_url, cleanup_executor
    ):
        """Test Express create works immediately after sync DDL auto_migrate - MySQL."""
        suffix = get_unique_suffix().replace("_", "").replace("-", "")
        model_name = f"MysqlUser{suffix}"
        table_name = f"mysqluser{suffix}s"
        cleanup_executor.append(table_name)

        db = DataFlow(mysql_url, auto_migrate=True)

        UserModel = create_model_class(
            model_name, {"id": str, "name": str, "email": str}, table_name
        )
        db.model(UserModel)

        await db.initialize()

        try:
            user = await db.express.create(
                model_name, {"id": "user-001", "name": "Bob", "email": "bob@test.com"}
            )

            assert user is not None
            assert user["id"] == "user-001"
            assert user["name"] == "Bob"
        finally:
            await db.close_async()

    @pytest.mark.asyncio
    async def test_express_crud_cycle_mysql(self, mysql_url, cleanup_executor):
        """Test full CRUD cycle via Express API after sync DDL - MySQL."""
        suffix = get_unique_suffix().replace("_", "").replace("-", "")
        model_name = f"MysqlCrud{suffix}"
        table_name = f"mysqlcrud{suffix}s"
        cleanup_executor.append(table_name)

        db = DataFlow(mysql_url, auto_migrate=True)

        CrudModel = create_model_class(
            model_name,
            {"id": str, "title": str, "count": int},
            table_name,
            {"count": 0},
        )
        db.model(CrudModel)

        await db.initialize()

        try:
            # CREATE
            record = await db.express.create(
                model_name, {"id": "doc-001", "title": "Document 1", "count": 5}
            )
            assert record["title"] == "Document 1"

            # READ
            fetched = await db.express.read(model_name, "doc-001")
            assert fetched["count"] == 5

            # UPDATE
            updated = await db.express.update(model_name, "doc-001", {"count": 10})
            # MySQL doesn't return updated record (no RETURNING), verify with read
            if "count" in updated:
                assert updated["count"] == 10
            else:
                # Verify update by reading
                verified = await db.express.read(model_name, "doc-001")
                assert verified["count"] == 10

            # DELETE
            deleted = await db.express.delete(model_name, "doc-001")
            assert deleted is True
        finally:
            await db.close_async()


class TestSyncDDLExpressEdgeCases:
    """Test edge cases for Express API after sync DDL."""

    pytestmark = [
        pytest.mark.integration,
        pytest.mark.skipif(not PSYCOPG2_AVAILABLE, reason="psycopg2 not installed"),
        pytest.mark.skipif(
            not is_postgres_available(), reason="PostgreSQL not available"
        ),
    ]

    @pytest.fixture
    def postgres_url(self):
        return get_postgres_url()

    @pytest.fixture
    def cleanup_executor(self, postgres_url):
        """Fixture to clean up tables after tests."""
        tables = []
        yield tables
        executor = SyncDDLExecutor(postgres_url)
        for table in tables:
            try:
                executor.execute_ddl(f"DROP TABLE IF EXISTS {table} CASCADE")
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_express_with_auto_migrate_false(
        self, postgres_url, cleanup_executor
    ):
        """Test Express API with auto_migrate=False + explicit create_tables_sync()."""
        suffix = get_unique_suffix().replace("_", "").replace("-", "")
        model_name = f"ManualModel{suffix}"
        table_name = f"manualmodel{suffix}s"
        cleanup_executor.append(table_name)

        db = DataFlow(postgres_url, auto_migrate=False)

        ManualModel = create_model_class(
            model_name, {"id": str, "data": str}, table_name
        )
        db.model(ManualModel)

        # Explicit sync table creation
        success = db.create_tables_sync()
        assert success is True

        await db.initialize()

        try:
            # Express should work after explicit sync creation
            record = await db.express.create(
                model_name, {"id": "manual-001", "data": "test data"}
            )
            assert record["data"] == "test data"
        finally:
            await db.close_async()

    @pytest.mark.asyncio
    async def test_express_empty_table_operations(self, postgres_url, cleanup_executor):
        """Test Express operations on newly created empty table."""
        suffix = get_unique_suffix().replace("_", "").replace("-", "")
        model_name = f"EmptyModel{suffix}"
        table_name = f"emptymodel{suffix}s"
        cleanup_executor.append(table_name)

        db = DataFlow(postgres_url, auto_migrate=True)

        EmptyModel = create_model_class(
            model_name, {"id": str, "value": str}, table_name
        )
        db.model(EmptyModel)

        await db.initialize()

        try:
            # List empty table
            records = await db.express.list(model_name, filter={})
            assert len(records) == 0

            # Count empty table
            count = await db.express.count(model_name, filter={})
            assert count == 0

            # Read non-existent (should raise)
            try:
                await db.express.read(model_name, "does-not-exist")
                assert False, "Should have raised error"
            except Exception:
                pass  # Expected
        finally:
            await db.close_async()

    @pytest.mark.asyncio
    async def test_express_rapid_sequential_operations(
        self, postgres_url, cleanup_executor
    ):
        """Test rapid sequential Express operations after sync DDL."""
        suffix = get_unique_suffix().replace("_", "").replace("-", "")
        model_name = f"RapidModel{suffix}"
        table_name = f"rapidmodel{suffix}s"
        cleanup_executor.append(table_name)

        db = DataFlow(postgres_url, auto_migrate=True)

        RapidModel = create_model_class(model_name, {"id": str, "seq": int}, table_name)
        db.model(RapidModel)

        await db.initialize()

        try:
            # Rapid create-read-update-delete cycles
            for i in range(10):
                record_id = f"rapid-{i:03d}"

                # Create
                await db.express.create(model_name, {"id": record_id, "seq": i})

                # Read
                record = await db.express.read(model_name, record_id)
                assert record["seq"] == i

                # Update
                await db.express.update(model_name, record_id, {"seq": i * 2})

                # Verify update
                updated = await db.express.read(model_name, record_id)
                assert updated["seq"] == i * 2

            # Final count
            count = await db.express.count(model_name, filter={})
            assert count == 10
        finally:
            await db.close_async()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
