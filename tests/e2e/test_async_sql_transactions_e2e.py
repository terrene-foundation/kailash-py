"""End-to-end tests for AsyncSQLDatabaseNode transaction functionality."""

import asyncio

import pytest
import pytest_asyncio
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests as E2E and requiring PostgreSQL
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.requires_postgres,
    pytest.mark.requires_docker,
]


class TestAsyncSQLTransactionsE2E:
    """End-to-end tests for async SQL transactions in real workflows."""

    @pytest_asyncio.fixture
    async def setup_bank_database(self):
        """Set up a banking database for testing transactions."""
        conn_string = get_postgres_connection_string()

        # Create tables
        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        await setup_node.execute_async(query="DROP TABLE IF EXISTS bank_transactions")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS bank_accounts")

        await setup_node.execute_async(
            query="""
            CREATE TABLE bank_accounts (
                account_id SERIAL PRIMARY KEY,
                account_number VARCHAR(20) UNIQUE NOT NULL,
                balance DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
                currency VARCHAR(3) DEFAULT 'USD',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        await setup_node.execute_async(
            query="""
            CREATE TABLE bank_transactions (
                transaction_id SERIAL PRIMARY KEY,
                from_account VARCHAR(20),
                to_account VARCHAR(20),
                amount DECIMAL(15, 2) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """
        )

        # Insert test accounts
        accounts = [
            ("ACC001", 10000.00),
            ("ACC002", 5000.00),
            ("ACC003", 2500.00),
        ]

        for account_num, balance in accounts:
            await setup_node.execute_async(
                query="INSERT INTO bank_accounts (account_number, balance) VALUES (:account_number, :balance)",
                params={"account_number": account_num, "balance": balance},
            )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(query="DROP TABLE IF EXISTS bank_transactions")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS bank_accounts")

    @pytest.mark.asyncio
    async def test_bank_transfer_workflow(self, setup_bank_database):
        """Test a complete bank transfer workflow with transaction safety."""
        conn_string = setup_bank_database

        # For this test, we'll use nodes directly instead of workflow builder
        # because manual transaction mode requires programmatic control

        # Create validation node
        validate_node = AsyncSQLDatabaseNode(
            name="validate_accounts",
            database_type="postgresql",
            connection_string=conn_string,
            query="""
                SELECT account_number, balance
                FROM bank_accounts
                WHERE account_number IN (:from_account, :to_account)
            """,
            transaction_mode="none",  # Read-only, no transaction needed
        )

        # Test successful transfer
        transfer_params = {
            "from_account": "ACC001",
            "to_account": "ACC002",
            "amount": 1000.00,
        }

        # Execute validation
        validation_result = await validate_node.execute_async(
            params={
                "from_account": transfer_params["from_account"],
                "to_account": transfer_params["to_account"],
            }
        )

        # Check we have both accounts
        accounts = validation_result["result"]["data"]
        assert len(accounts) == 2

        from_account = next(
            a
            for a in accounts
            if a["account_number"] == transfer_params["from_account"]
        )
        to_account = next(
            a for a in accounts if a["account_number"] == transfer_params["to_account"]
        )

        initial_from_balance = float(from_account["balance"])
        initial_to_balance = float(to_account["balance"])

        # Create transfer node
        transfer_node = AsyncSQLDatabaseNode(
            name="transfer_node",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        # Begin transaction
        await transfer_node.begin_transaction()

        try:
            # Record transaction
            await transfer_node.execute_async(
                query="""
                    INSERT INTO bank_transactions (from_account, to_account, amount, status)
                    VALUES (:from_account, :to_account, :amount, 'processing')
                    RETURNING transaction_id
                """,
                params=transfer_params,
            )

            # Debit from account
            await transfer_node.execute_async(
                query="""
                    UPDATE bank_accounts
                    SET balance = balance - :amount
                    WHERE account_number = :account_number AND balance >= :amount
                """,
                params={
                    "account_number": transfer_params["from_account"],
                    "amount": transfer_params["amount"],
                },
            )

            # Credit to account
            await transfer_node.execute_async(
                query="""
                    UPDATE bank_accounts
                    SET balance = balance + :amount
                    WHERE account_number = :account_number
                """,
                params={
                    "account_number": transfer_params["to_account"],
                    "amount": transfer_params["amount"],
                },
            )

            # Update transaction status
            await transfer_node.execute_async(
                query="""
                    UPDATE bank_transactions
                    SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                    WHERE from_account = :from_account
                    AND to_account = :to_account
                    AND status = 'processing'
                """,
                params={
                    "from_account": transfer_params["from_account"],
                    "to_account": transfer_params["to_account"],
                },
            )

            # Commit transaction
            await transfer_node.commit()

        except Exception as e:
            # Rollback on any error
            await transfer_node.rollback()
            raise e

        # Verify transfer completed
        check_node = AsyncSQLDatabaseNode(
            name="check",
            database_type="postgresql",
            connection_string=conn_string,
        )

        final_accounts = await check_node.execute_async(
            query="SELECT account_number, balance FROM bank_accounts WHERE account_number IN (:acc1, :acc2)",
            params={
                "acc1": transfer_params["from_account"],
                "acc2": transfer_params["to_account"],
            },
        )

        final_from = next(
            a
            for a in final_accounts["result"]["data"]
            if a["account_number"] == transfer_params["from_account"]
        )
        final_to = next(
            a
            for a in final_accounts["result"]["data"]
            if a["account_number"] == transfer_params["to_account"]
        )

        assert (
            float(final_from["balance"])
            == initial_from_balance - transfer_params["amount"]
        )
        assert (
            float(final_to["balance"]) == initial_to_balance + transfer_params["amount"]
        )

        # Verify transaction record
        tx_record = await check_node.execute_async(
            query="SELECT * FROM bank_transactions WHERE from_account = :from AND to_account = :to",
            params={
                "from": transfer_params["from_account"],
                "to": transfer_params["to_account"],
            },
        )

        assert len(tx_record["result"]["data"]) == 1
        assert tx_record["result"]["data"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_failed_transfer_rollback(self, setup_bank_database):
        """Test that failed transfers are properly rolled back."""
        conn_string = setup_bank_database

        # Create transfer node
        transfer_node = AsyncSQLDatabaseNode(
            name="transfer",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        # Check initial balance
        check_node = AsyncSQLDatabaseNode(
            name="check",
            database_type="postgresql",
            connection_string=conn_string,
        )

        initial_result = await check_node.execute_async(
            query="SELECT * FROM bank_accounts WHERE account_number = :acc",
            params={"acc": "ACC003"},
        )
        initial_balance = float(initial_result["result"]["data"][0]["balance"])

        # Try to transfer more than available balance
        await transfer_node.begin_transaction()

        try:
            # This should succeed
            await transfer_node.execute_async(
                query="""
                    INSERT INTO bank_transactions (from_account, to_account, amount, status)
                    VALUES (:from_account, :to_account, :amount, 'processing')
                """,
                params={
                    "from_account": "ACC003",
                    "to_account": "ACC001",
                    "amount": 5000.00,  # More than ACC003 has
                },
            )

            # This should fail due to CHECK constraint
            await transfer_node.execute_async(
                query="""
                    UPDATE bank_accounts
                    SET balance = balance - :amount
                    WHERE account_number = :account_number
                    RETURNING CASE WHEN balance < 0 THEN 1/0 ELSE balance END
                """,
                params={"account_number": "ACC003", "amount": 5000.00},
            )

            # Should not reach here
            await transfer_node.commit()
            assert False, "Should have failed due to negative balance"

        except Exception:
            # Expected failure, rollback
            await transfer_node.rollback()

        # Verify no changes were made
        final_result = await check_node.execute_async(
            query="SELECT * FROM bank_accounts WHERE account_number = :acc",
            params={"acc": "ACC003"},
        )
        final_balance = float(final_result["result"]["data"][0]["balance"])

        assert (
            initial_balance == final_balance
        ), "Balance should not have changed after rollback"

        # Verify no transaction record exists
        tx_result = await check_node.execute_async(
            query="SELECT * FROM bank_transactions WHERE from_account = :acc",
            params={"acc": "ACC003"},
        )

        assert (
            len(tx_result["result"]["data"]) == 0
        ), "Transaction record should have been rolled back"

    @pytest.mark.asyncio
    async def test_concurrent_transfer_safety(self, setup_bank_database):
        """Test that concurrent transfers maintain consistency."""
        conn_string = setup_bank_database

        # Create multiple transfer nodes
        transfer_nodes = []
        for i in range(3):
            node = AsyncSQLDatabaseNode(
                name=f"transfer_{i}",
                database_type="postgresql",
                connection_string=conn_string,
                transaction_mode="manual",
                timeout=5.0,  # Add timeout to prevent indefinite waits
            )
            transfer_nodes.append(node)

        # Function to perform a transfer
        async def do_transfer(node, from_acc, to_acc, amount):
            await node.begin_transaction()
            try:
                # First try simple SELECT to check if account exists
                balance_result = await node.execute_async(
                    query="SELECT balance FROM bank_accounts WHERE account_number = :acc",
                    params={"acc": from_acc},
                )

                # Debug the actual result structure
                if not balance_result["result"]["data"]:
                    print(f"No data returned for account {from_acc}")
                    await node.rollback()
                    return False

                balance_data = balance_result["result"]["data"][0]
                print(f"Balance data for {from_acc}: {balance_data}")
                current_balance = float(balance_data["balance"])

                if current_balance >= amount:
                    await node.execute_async(
                        query="UPDATE bank_accounts SET balance = balance - :amount WHERE account_number = :acc",
                        params={"acc": from_acc, "amount": amount},
                    )

                    await node.execute_async(
                        query="UPDATE bank_accounts SET balance = balance + :amount WHERE account_number = :acc",
                        params={"acc": to_acc, "amount": amount},
                    )

                    await node.commit()
                    return True
                else:
                    await node.rollback()
                    return False

            except Exception as e:
                await node.rollback()
                # Print error for debugging E2E test failures
                print(f"Transfer {from_acc}->{to_acc} failed: {e}")
                return False

        # Run concurrent transfers
        tasks = [
            do_transfer(transfer_nodes[0], "ACC001", "ACC002", 1000),
            do_transfer(transfer_nodes[1], "ACC001", "ACC003", 1500),
            do_transfer(transfer_nodes[2], "ACC002", "ACC001", 500),
        ]

        results = await asyncio.gather(*tasks)

        # At least some transfers should succeed
        assert any(results), "At least one transfer should succeed"

        # Verify total balance is conserved
        check_node = AsyncSQLDatabaseNode(
            name="check",
            database_type="postgresql",
            connection_string=conn_string,
        )

        total_result = await check_node.execute_async(
            query="SELECT SUM(balance) as total FROM bank_accounts"
        )

        # Original total was 10000 + 5000 + 2500 = 17500
        assert (
            float(total_result["result"]["data"][0]["total"]) == 17500.00
        ), "Total balance should be conserved"
