"""End-to-end tests for AsyncSQLDatabaseNode transaction scenarios."""

from datetime import datetime

import pytest
import pytest_asyncio

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError
from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests as requiring postgres and as e2e tests
pytestmark = [pytest.mark.e2e, pytest.mark.requires_postgres]


class TestAsyncSQLTransactionScenarios:
    """End-to-end transaction scenarios testing real-world use cases."""

    @pytest_asyncio.fixture
    async def e2e_database_setup(self):
        """Set up comprehensive test database for e2e scenarios."""
        conn_string = get_postgres_connection_string()

        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        # Create multiple tables for complex scenarios
        await setup_node.execute_async(query="DROP TABLE IF EXISTS orders CASCADE")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS order_items CASCADE")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS inventory CASCADE")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS audit_log CASCADE")

        # Orders table
        await setup_node.execute_async(
            query="""
            CREATE TABLE orders (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                total_amount DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                version INTEGER DEFAULT 1
            )
        """
        )

        # Order items table
        await setup_node.execute_async(
            query="""
            CREATE TABLE order_items (
                id SERIAL PRIMARY KEY,
                order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price DECIMAL(10, 2) NOT NULL,
                total_price DECIMAL(10, 2) NOT NULL
            )
        """
        )

        # Inventory table
        await setup_node.execute_async(
            query="""
            CREATE TABLE inventory (
                product_id INTEGER PRIMARY KEY,
                available_quantity INTEGER NOT NULL CHECK (available_quantity >= 0),
                reserved_quantity INTEGER NOT NULL DEFAULT 0,
                last_updated TIMESTAMP DEFAULT NOW()
            )
        """
        )

        # Audit log table
        await setup_node.execute_async(
            query="""
            CREATE TABLE audit_log (
                id SERIAL PRIMARY KEY,
                table_name VARCHAR(50) NOT NULL,
                operation VARCHAR(20) NOT NULL,
                record_id INTEGER,
                old_values JSONB,
                new_values JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """
        )

        # Insert test inventory
        await setup_node.execute_async(
            query="""
            INSERT INTO inventory (product_id, available_quantity) VALUES
            (1, 100),
            (2, 50),
            (3, 25)
        """
        )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(query="DROP TABLE IF EXISTS orders CASCADE")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS order_items CASCADE")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS inventory CASCADE")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS audit_log CASCADE")
        await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_complex_order_processing_transaction(self, e2e_database_setup):
        """Test complex order processing with multiple tables and validation."""
        conn_string = e2e_database_setup

        node = AsyncSQLDatabaseNode(
            name="order_processor",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        try:
            # Begin transaction for order processing
            await node.begin_transaction()

            # Step 1: Create order
            order_result = await node.execute_async(
                query="""
                    INSERT INTO orders (customer_id, status)
                    VALUES (:customer_id, :status)
                    RETURNING id
                """,
                params={"customer_id": 12345, "status": "processing"},
            )

            order_id = order_result["result"]["data"][0]["id"]

            # Step 2: Add order items and update inventory
            order_items = [
                {"product_id": 1, "quantity": 5, "unit_price": 10.00},
                {"product_id": 2, "quantity": 3, "unit_price": 25.00},
                {"product_id": 3, "quantity": 2, "unit_price": 50.00},
            ]

            total_amount = 0.00

            for item in order_items:
                # Check inventory availability
                inventory_result = await node.execute_async(
                    query="SELECT available_quantity FROM inventory WHERE product_id = :product_id",
                    params={"product_id": item["product_id"]},
                )

                available = inventory_result["result"]["data"][0]["available_quantity"]
                if available < item["quantity"]:
                    raise Exception(
                        f"Insufficient inventory for product {item['product_id']}"
                    )

                # Update inventory (reserve quantity)
                await node.execute_async(
                    query="""
                        UPDATE inventory
                        SET available_quantity = available_quantity - :quantity,
                            reserved_quantity = reserved_quantity + :quantity,
                            last_updated = NOW()
                        WHERE product_id = :product_id
                    """,
                    params={
                        "product_id": item["product_id"],
                        "quantity": item["quantity"],
                    },
                )

                # Add order item
                item_total = item["quantity"] * item["unit_price"]
                await node.execute_async(
                    query="""
                        INSERT INTO order_items (order_id, product_id, quantity, unit_price, total_price)
                        VALUES (:order_id, :product_id, :quantity, :unit_price, :total_price)
                    """,
                    params={
                        "order_id": order_id,
                        "product_id": item["product_id"],
                        "quantity": item["quantity"],
                        "unit_price": item["unit_price"],
                        "total_price": item_total,
                    },
                )

                total_amount += item_total

            # Step 3: Update order total
            await node.execute_async(
                query="UPDATE orders SET total_amount = :total WHERE id = :order_id",
                params={"total": total_amount, "order_id": order_id},
            )

            # Step 4: Log audit trail
            await node.execute_async(
                query="""
                    INSERT INTO audit_log (table_name, operation, record_id, new_values)
                    VALUES (:table_name, :operation, :record_id, :new_values)
                """,
                params={
                    "table_name": "orders",
                    "operation": "CREATE",
                    "record_id": order_id,
                    "new_values": {
                        "customer_id": 12345,
                        "total_amount": float(total_amount),
                        "status": "processing",
                    },
                },
            )

            # Commit the entire transaction
            await node.commit()

            # Verify the complete order was created
            verify_result = await node.execute_async(
                query="""
                    SELECT o.id, o.total_amount, o.status, COUNT(oi.id) as item_count
                    FROM orders o
                    LEFT JOIN order_items oi ON o.id = oi.order_id
                    WHERE o.id = :order_id
                    GROUP BY o.id, o.total_amount, o.status
                """,
                params={"order_id": order_id},
            )

            order_data = verify_result["result"]["data"][0]
            assert order_data["total_amount"] == 225.00  # 5*10 + 3*25 + 2*50
            assert order_data["item_count"] == 3
            assert order_data["status"] == "processing"

            # Verify inventory was updated
            inventory_result = await node.execute_async(
                query="SELECT product_id, available_quantity, reserved_quantity FROM inventory ORDER BY product_id"
            )

            inventory_data = inventory_result["result"]["data"]
            assert inventory_data[0]["available_quantity"] == 95  # 100 - 5
            assert inventory_data[0]["reserved_quantity"] == 5
            assert inventory_data[1]["available_quantity"] == 47  # 50 - 3
            assert inventory_data[1]["reserved_quantity"] == 3
            assert inventory_data[2]["available_quantity"] == 23  # 25 - 2
            assert inventory_data[2]["reserved_quantity"] == 2

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_order_processing_with_rollback_on_insufficient_inventory(
        self, e2e_database_setup
    ):
        """Test order processing rollback when inventory is insufficient."""
        conn_string = e2e_database_setup

        node = AsyncSQLDatabaseNode(
            name="order_processor",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        try:
            # Begin transaction
            await node.begin_transaction()

            # Create order
            order_result = await node.execute_async(
                query="INSERT INTO orders (customer_id, status) VALUES (:customer_id, :status) RETURNING id",
                params={"customer_id": 54321, "status": "processing"},
            )

            order_id = order_result["result"]["data"][0]["id"]

            # Try to order more than available (should cause rollback)
            try:
                # First item - valid
                await node.execute_async(
                    query="""
                        UPDATE inventory
                        SET available_quantity = available_quantity - :quantity
                        WHERE product_id = :product_id
                    """,
                    params={"product_id": 1, "quantity": 10},
                )

                await node.execute_async(
                    query="""
                        INSERT INTO order_items (order_id, product_id, quantity, unit_price, total_price)
                        VALUES (:order_id, :product_id, :quantity, :unit_price, :total_price)
                    """,
                    params={
                        "order_id": order_id,
                        "product_id": 1,
                        "quantity": 10,
                        "unit_price": 15.00,
                        "total_price": 150.00,
                    },
                )

                # Second item - exceeds inventory (should trigger rollback)
                inventory_check = await node.execute_async(
                    query="SELECT available_quantity FROM inventory WHERE product_id = :product_id",
                    params={"product_id": 2},
                )

                available = inventory_check["result"]["data"][0]["available_quantity"]
                if available < 100:  # Trying to order 100, but only 50 available
                    raise Exception("Insufficient inventory")

            except Exception:
                # Rollback the transaction
                await node.rollback()

                # Verify rollback worked
                order_check = await node.execute_async(
                    query="SELECT COUNT(*) as count FROM orders WHERE id = :order_id",
                    params={"order_id": order_id},
                )

                assert order_check["result"]["data"][0]["count"] == 0

                # Verify inventory unchanged
                inventory_result = await node.execute_async(
                    query="SELECT available_quantity FROM inventory WHERE product_id = 1"
                )

                assert (
                    inventory_result["result"]["data"][0]["available_quantity"] == 100
                )  # Unchanged

                return  # Test passed

            # Should not reach here
            assert False, "Transaction should have been rolled back"

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_concurrent_order_processing(self, e2e_database_setup):
        """Pin real transaction isolation under row-lock contention (issue #1504).

        This pins the ACTUAL PostgreSQL behavior when two manual transactions
        contend on the same inventory row, which the previous version of this
        test asserted incorrectly (it expected ``count == 2``):

        1. node1 and node2 each INSERT their own order row (separate rows).
        2. node1 reserves stock on ``product_id=3``, taking a row-level write lock.
        3. node2 tries to reserve the same row. Because node2 set a small
           ``lock_timeout``, PostgreSQL CANCELS the blocked UPDATE
           ("canceling statement due to lock timeout"). A cancelled statement
           puts node2's transaction into the ABORTED state (SQLSTATE 25P02).
        4. node2's later ``commit()`` on an aborted transaction returns without
           raising, but PostgreSQL treats COMMIT-on-aborted as a ROLLBACK — so
           node2's order2 INSERT is discarded along with its failed UPDATE.

        Correct isolation outcome therefore is: ONLY node1's order persists,
        node2's order is lost, and inventory reflects only node1's committed
        reservation (25 - 20 = 5). The SDK behavior is correct; the old
        ``count == 2`` assertion was the bug.

        Determinism/speed: node2 sets ``SET LOCAL lock_timeout = '1s'`` so the
        contended UPDATE fails in ~1s instead of blocking on the 60s server-side
        ``statement_timeout``. The old test leaned on that 60s wait (+ the node's
        internal timeout retries), which is why it ran ~62s. This runs in ~2s.
        """
        conn_string = e2e_database_setup

        # Two independent connections/transactions contending on one row.
        node1 = AsyncSQLDatabaseNode(
            name="processor1",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
            timeout=10.0,
        )

        node2 = AsyncSQLDatabaseNode(
            name="processor2",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
            timeout=10.0,
        )

        try:
            # Start both transactions
            await node1.begin_transaction()
            await node2.begin_transaction()

            # Each processor creates its own order row (distinct rows, no contention yet)
            order1_result = await node1.execute_async(
                query="INSERT INTO orders (customer_id, status) VALUES (:customer_id, :status) RETURNING id",
                params={"customer_id": 11111, "status": "processing"},
            )
            order1_id = order1_result["result"]["data"][0]["id"]

            order2_result = await node2.execute_async(
                query="INSERT INTO orders (customer_id, status) VALUES (:customer_id, :status) RETURNING id",
                params={"customer_id": 22222, "status": "processing"},
            )
            order2_id = order2_result["result"]["data"][0]["id"]

            # Both see the same initial inventory (product_id=3, available=25)
            inventory1 = await node1.execute_async(
                query="SELECT available_quantity FROM inventory WHERE product_id = :product_id",
                params={"product_id": 3},
            )
            inventory2 = await node2.execute_async(
                query="SELECT available_quantity FROM inventory WHERE product_id = :product_id",
                params={"product_id": 3},
            )
            assert inventory1["result"]["data"][0]["available_quantity"] == 25
            assert inventory2["result"]["data"][0]["available_quantity"] == 25

            # Bound node2's lock wait so the contended UPDATE fails fast (deterministic
            # ~1s) instead of blocking on the 60s server-side statement_timeout. LOCAL
            # scope means it applies only to node2's active transaction.
            await node2.execute_async(query="SET LOCAL lock_timeout = '1s'")

            # node1 reserves 20 units, taking a row-level write lock on product_id=3.
            await node1.execute_async(
                query="""
                    UPDATE inventory
                    SET available_quantity = available_quantity - :quantity
                    WHERE product_id = :product_id AND available_quantity >= :quantity
                """,
                params={"product_id": 3, "quantity": 20},
            )

            # node2 tries to reserve the same row. It blocks on node1's lock, hits its
            # 1s lock_timeout, PostgreSQL cancels the statement, and node2's transaction
            # enters the ABORTED state. The node's retry then surfaces
            # "current transaction is aborted" as a NodeExecutionError.
            with pytest.raises(NodeExecutionError):
                await node2.execute_async(
                    query="""
                        UPDATE inventory
                        SET available_quantity = available_quantity - :quantity
                        WHERE product_id = :product_id AND available_quantity >= :quantity
                    """,
                    params={"product_id": 3, "quantity": 15},
                )

            # node1 commits normally, releasing its lock and persisting its reservation.
            await node1.commit()

            # node2.commit() on an ABORTED transaction returns WITHOUT raising, but
            # PostgreSQL applies COMMIT-on-aborted as a ROLLBACK. This must not raise —
            # pinning that the SDK forwards PostgreSQL's silent-rollback-on-commit.
            await node2.commit()

            # --- Read-back verification (every write verified with a read) ---

            # order1 persisted; order2 was discarded with node2's aborted transaction.
            order1_check = await node1.execute_async(
                query="SELECT COUNT(*) as count FROM orders WHERE id = :order_id",
                params={"order_id": order1_id},
            )
            order2_check = await node1.execute_async(
                query="SELECT COUNT(*) as count FROM orders WHERE id = :order_id",
                params={"order_id": order2_id},
            )
            assert (
                order1_check["result"]["data"][0]["count"] == 1
            ), "node1's committed order must persist"
            assert order2_check["result"]["data"][0]["count"] == 0, (
                "node2's order must be lost: its transaction aborted on lock timeout, "
                "so commit()=rollback discarded the order2 INSERT (issue #1504)"
            )

            # Exactly one of the two contended orders survived.
            orders_result = await node1.execute_async(
                query="SELECT COUNT(*) as count FROM orders WHERE id IN (:id1, :id2)",
                params={"id1": order1_id, "id2": order2_id},
            )
            assert orders_result["result"]["data"][0]["count"] == 1

            # Inventory reflects ONLY node1's committed reservation (25 - 20 = 5).
            # node2's UPDATE never applied — it rolled back with the aborted transaction.
            final_inventory = await node1.execute_async(
                query="SELECT available_quantity FROM inventory WHERE product_id = :product_id",
                params={"product_id": 3},
            )
            assert final_inventory["result"]["data"][0]["available_quantity"] == 5

        finally:
            await node1.cleanup()
            await node2.cleanup()

    @pytest.mark.asyncio
    async def test_long_running_transaction_with_multiple_operations(
        self, e2e_database_setup
    ):
        """Test long-running transaction with many operations."""
        conn_string = e2e_database_setup

        node = AsyncSQLDatabaseNode(
            name="bulk_processor",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        try:
            await node.begin_transaction()

            # Create multiple orders with items
            order_ids = []

            for customer_id in range(1000, 1010):  # 10 customers
                # Create order
                order_result = await node.execute_async(
                    query="INSERT INTO orders (customer_id, status) VALUES (:customer_id, :status) RETURNING id",
                    params={"customer_id": customer_id, "status": "bulk_processing"},
                )

                order_id = order_result["result"]["data"][0]["id"]
                order_ids.append(order_id)

                # Add 2-3 items per order
                items_data = []
                for i in range(2):
                    items_data.append(
                        {
                            "order_id": order_id,
                            "product_id": (i % 3)
                            + 1,  # Rotate through products 1, 2, 3
                            "quantity": 1,
                            "unit_price": 20.00 + i * 5,
                            "total_price": 20.00 + i * 5,
                        }
                    )

                # Batch insert order items
                await node.execute_many_async(
                    query="""
                        INSERT INTO order_items (order_id, product_id, quantity, unit_price, total_price)
                        VALUES (:order_id, :product_id, :quantity, :unit_price, :total_price)
                    """,
                    params_list=items_data,
                )

                # Update order total
                total = sum(item["total_price"] for item in items_data)
                await node.execute_async(
                    query="UPDATE orders SET total_amount = :total WHERE id = :order_id",
                    params={"total": total, "order_id": order_id},
                )

            # Batch audit log entries
            audit_entries = [
                {
                    "table_name": "orders",
                    "operation": "BULK_CREATE",
                    "record_id": order_id,
                    "new_values": {
                        "customer_id": 1000 + i,
                        "status": "bulk_processing",
                    },
                }
                for i, order_id in enumerate(order_ids)
            ]

            await node.execute_many_async(
                query="""
                    INSERT INTO audit_log (table_name, operation, record_id, new_values)
                    VALUES (:table_name, :operation, :record_id, :new_values)
                """,
                params_list=audit_entries,
            )

            # Commit the large transaction
            await node.commit()

            # Verify all data was committed
            orders_count = await node.execute_async(
                query="SELECT COUNT(*) as count FROM orders WHERE status = :status",
                params={"status": "bulk_processing"},
            )

            assert orders_count["result"]["data"][0]["count"] == 10

            items_count = await node.execute_async(
                query="""
                    SELECT COUNT(*) as count
                    FROM order_items oi
                    JOIN orders o ON oi.order_id = o.id
                    WHERE o.status = :status
                """,
                params={"status": "bulk_processing"},
            )

            assert (
                items_count["result"]["data"][0]["count"] == 20
            )  # 10 orders * 2 items each

            audit_count = await node.execute_async(
                query="SELECT COUNT(*) as count FROM audit_log WHERE operation = :operation",
                params={"operation": "BULK_CREATE"},
            )

            assert audit_count["result"]["data"][0]["count"] == 10

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_transaction_with_mixed_modes(self, e2e_database_setup):
        """Test mixed transaction modes in different operations."""
        conn_string = e2e_database_setup

        # Auto transaction node for simple operations
        auto_node = AsyncSQLDatabaseNode(
            name="auto_processor",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="auto",
        )

        # Manual transaction node for complex operations
        manual_node = AsyncSQLDatabaseNode(
            name="manual_processor",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        # None transaction node for immediate commits
        none_node = AsyncSQLDatabaseNode(
            name="none_processor",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="none",
        )

        try:
            # Use auto mode for simple audit logging
            await auto_node.execute_async(
                query="""
                    INSERT INTO audit_log (table_name, operation, new_values)
                    VALUES (:table_name, :operation, :new_values)
                """,
                params={
                    "table_name": "mixed_mode_test",
                    "operation": "START",
                    "new_values": {"timestamp": datetime.now().isoformat()},
                },
            )

            # Use manual mode for complex order creation
            await manual_node.begin_transaction()

            order_result = await manual_node.execute_async(
                query="INSERT INTO orders (customer_id, status) VALUES (:customer_id, :status) RETURNING id",
                params={"customer_id": 99999, "status": "mixed_mode"},
            )

            order_id = order_result["result"]["data"][0]["id"]

            # Add items in same manual transaction
            await manual_node.execute_async(
                query="""
                    INSERT INTO order_items (order_id, product_id, quantity, unit_price, total_price)
                    VALUES (:order_id, :product_id, :quantity, :unit_price, :total_price)
                """,
                params={
                    "order_id": order_id,
                    "product_id": 1,
                    "quantity": 5,
                    "unit_price": 30.00,
                    "total_price": 150.00,
                },
            )

            # Commit manual transaction
            await manual_node.commit()

            # Use none mode for immediate inventory update
            await none_node.execute_async(
                query="""
                    UPDATE inventory
                    SET last_updated = NOW()
                    WHERE product_id = :product_id
                """,
                params={"product_id": 1},
            )

            # Use auto mode for final audit
            await auto_node.execute_async(
                query="""
                    INSERT INTO audit_log (table_name, operation, record_id, new_values)
                    VALUES (:table_name, :operation, :record_id, :new_values)
                """,
                params={
                    "table_name": "mixed_mode_test",
                    "operation": "COMPLETE",
                    "record_id": order_id,
                    "new_values": {"total_amount": 150.00},
                },
            )

            # Verify all operations completed
            order_check = await auto_node.execute_async(
                query="SELECT * FROM orders WHERE id = :order_id",
                params={"order_id": order_id},
            )

            assert order_check["result"]["data"][0]["status"] == "mixed_mode"

            audit_check = await auto_node.execute_async(
                query="SELECT COUNT(*) as count FROM audit_log WHERE table_name = :table_name",
                params={"table_name": "mixed_mode_test"},
            )

            assert audit_check["result"]["data"][0]["count"] == 2  # START and COMPLETE

        finally:
            await auto_node.cleanup()
            await manual_node.cleanup()
            await none_node.cleanup()
