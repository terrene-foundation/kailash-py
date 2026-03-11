"""
End-to-end tests for SQL injection prevention in complete user workflows.

Tests complete scenarios from user input to database operations,
ensuring SQL injection attempts are blocked at every level.
NO MOCKING - complete scenarios with real infrastructure.
"""

import json
import os
import sqlite3
from typing import Any, Dict, List

import pytest
from dataflow import DataFlow
from nexus import Nexus

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestSQLInjectionE2EScenarios:
    """Test complete user workflows with SQL injection attempts."""

    @pytest.fixture(autouse=True)
    def setup_test_environment(self):
        """Set up test database and environment."""
        # Clean up any existing test databases
        test_files = ["test_e2e.db", "test_api.db", "test_cli.db"]
        for file in test_files:
            if os.path.exists(file):
                os.remove(file)

        yield

        # Cleanup after tests
        for file in test_files:
            if os.path.exists(file):
                os.remove(file)

    def test_user_registration_workflow_with_injection(self):
        """Test user registration workflow with SQL injection attempts."""
        # Initialize DataFlow
        db = DataFlow(database_url="sqlite:///test_e2e.db")

        @db.model
        class User:
            username: str
            email: str
            password_hash: str
            role: str = "user"
            active: bool = True

        # Create registration workflow
        workflow = WorkflowBuilder()

        # Simulate user input with various injection attempts
        malicious_inputs = [
            {
                "username": "admin'; DROP TABLE users;--",
                "email": "admin@test.com",
                "password": "password123",
            },
            {
                "username": "user' OR '1'='1",
                "email": "user@test.com",
                "password": "pass' OR '1'='1",
            },
            {
                "username": "hacker",
                "email": "hacker@test.com'); DELETE FROM users;--",
                "password": "hack123",
            },
        ]

        # Process each registration attempt
        runtime = LocalRuntime()

        for i, user_input in enumerate(malicious_inputs):
            # Add user creation node
            workflow.add_node(
                "UserCreateNode",
                f"create_user_{i}",
                {
                    "username": user_input["username"],
                    "email": user_input["email"],
                    "password_hash": f"hashed_{user_input['password']}",  # Simulate password hashing
                    "role": "user",
                },
            )

            # Add verification node
            workflow.add_node(
                "UserReadNode",
                f"verify_user_{i}",
                {"filter": {"email": user_input["email"]}},
            )

            workflow.add_connection(f"create_user_{i}", f"verify_user_{i}")

        # Execute workflow
        results, run_id = runtime.execute(workflow.build())

        # Verify all users were created safely
        conn = sqlite3.connect("test_e2e.db")
        cursor = conn.cursor()

        # Check table still exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user'"
        )
        assert cursor.fetchone() is not None, "User table was dropped!"

        # Verify malicious strings were stored as data
        cursor.execute("SELECT username FROM user WHERE email = ?", ("admin@test.com",))
        username = cursor.fetchone()[0]
        assert username == "admin'; DROP TABLE users;--"

        # Verify all users were created
        cursor.execute("SELECT COUNT(*) FROM user")
        count = cursor.fetchone()[0]
        assert count == len(malicious_inputs)

        conn.close()

    def test_ecommerce_order_workflow_with_injection(self):
        """Test e-commerce order processing with injection attempts."""
        db = DataFlow(database_url="sqlite:///test_e2e.db")

        @db.model
        class Product:
            name: str
            price: float
            stock: int
            category: str

        @db.model
        class Order:
            customer_id: int
            product_id: int
            quantity: int
            total: float
            status: str = "pending"

        # Create test products
        workflow = WorkflowBuilder()

        # Add products with injection attempts in names
        products = [
            {"name": "Laptop", "price": 999.99, "stock": 10, "category": "Electronics"},
            {
                "name": "Mouse'; UPDATE product SET price=0;--",
                "price": 29.99,
                "stock": 50,
                "category": "Electronics",
            },
            {
                "name": "Keyboard' UNION SELECT * FROM orders;",
                "price": 79.99,
                "stock": 30,
                "category": "Electronics",
            },
        ]

        workflow.add_node(
            "ProductBulkCreateNode", "create_products", {"data": products}
        )

        # Search products with injection in search query
        workflow.add_node(
            "ProductListNode",
            "search_products",
            {
                "filter": {"category": "Electronics' OR '1'='1"}
            },  # Injection attempt in filter
        )

        workflow.add_connection("create_products", "search_products")

        # Create order with injection attempts
        workflow.add_node(
            "OrderCreateNode",
            "create_order",
            {
                "customer_id": 1,
                "product_id": 1,
                "quantity": 2,
                "total": 1999.98,
                "status": "pending'; DELETE FROM product;--",  # Injection in status
            },
        )

        workflow.add_connection("search_products", "create_order")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify database integrity
        conn = sqlite3.connect("test_e2e.db")
        cursor = conn.cursor()

        # Products table should still exist with all products
        cursor.execute("SELECT COUNT(*) FROM product")
        product_count = cursor.fetchone()[0]
        assert product_count == len(products)

        # Verify product with malicious name
        cursor.execute("SELECT price FROM product WHERE name LIKE ?", ("%Mouse%",))
        price = cursor.fetchone()[0]
        assert price == 29.99  # Price not changed by injection

        # Orders should be created
        cursor.execute('SELECT COUNT(*) FROM "order"')  # order is reserved word
        order_count = cursor.fetchone()[0]
        assert order_count >= 1

        conn.close()

    def test_bulk_data_import_with_injection(self):
        """Test bulk data import scenarios with injection attempts."""
        db = DataFlow(database_url="sqlite:///test_e2e.db")

        @db.model
        class Customer:
            name: str
            email: str
            phone: str
            address: str
            credit_limit: float = 1000.0

        # Simulate CSV import with malicious data
        import_data = [
            # Normal records
            {
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "555-0001",
                "address": "123 Main St",
            },
            {
                "name": "Jane Smith",
                "email": "jane@example.com",
                "phone": "555-0002",
                "address": "456 Oak Ave",
            },
            # SQL injection attempts in various fields
            {
                "name": "Hacker'; DROP TABLE customer;--",
                "email": "hacker@evil.com",
                "phone": "555-0003",
                "address": "Evil St",
            },
            {
                "name": "Admin",
                "email": "admin@test.com' OR '1'='1",
                "phone": "555-0004",
                "address": "Admin Road",
            },
            {
                "name": "Test",
                "email": "test@test.com",
                "phone": "555-0005'; DELETE FROM customer;",
                "address": "Test Lane",
            },
            {
                "name": "Update",
                "email": "update@test.com",
                "phone": "555-0006",
                "address": "Street'); UPDATE customer SET credit_limit=999999;--",
            },
            # Unicode and special character injections
            {
                "name": "Unicode'; \u0027; DROP TABLE customer;",
                "email": "unicode@test.com",
                "phone": "555-0007",
                "address": "Unicode St",
            },
            {
                "name": "Null\x00Byte",
                "email": "null@test.com",
                "phone": "555-0008",
                "address": "Null Road",
            },
        ]

        workflow = WorkflowBuilder()

        # Bulk import
        workflow.add_node(
            "CustomerBulkCreateNode",
            "import_customers",
            {
                "data": import_data,
                "batch_size": 100,
                "conflict_resolution": "skip",
                "return_ids": True,
            },
        )

        # Verify import
        workflow.add_node(
            "CustomerListNode", "verify_import", {"filter": {}, "limit": 1000}
        )

        workflow.add_connection("import_customers", "verify_import")

        # Update credit limits with injection attempt
        workflow.add_node(
            "CustomerBulkUpdateNode",
            "update_limits",
            {
                "filter": {"credit_limit": {"$lt": 5000}},
                "update": {"credit_limit": 2000.0},
            },
        )

        workflow.add_connection("verify_import", "update_limits")

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify data integrity
        conn = sqlite3.connect("test_e2e.db")
        cursor = conn.cursor()

        # Table should exist
        cursor.execute("SELECT COUNT(*) FROM customer")
        count = cursor.fetchone()[0]
        assert count == len(import_data)

        # Check specific malicious entries were safely stored
        cursor.execute(
            "SELECT credit_limit FROM customer WHERE email = ?", ("hacker@evil.com",)
        )
        limit = cursor.fetchone()[0]
        assert limit == 1000.0  # Default limit, not modified

        # Verify no unauthorized updates
        cursor.execute("SELECT MAX(credit_limit) FROM customer")
        max_limit = cursor.fetchone()[0]
        assert max_limit == 2000.0  # Only authorized update applied

        conn.close()

    def test_api_endpoint_with_injection(self):
        """Test API endpoints handling SQL injection attempts."""
        # Create DataFlow with models
        db = DataFlow(database_url="sqlite:///test_api.db")

        @db.model
        class Article:
            title: str
            content: str
            author: str
            published: bool = False
            views: int = 0

        # Create Nexus API
        nexus = Nexus(
            title="Blog API",
            enable_api=True,
            enable_cli=False,
            enable_mcp=False,
            dataflow_integration=db,
        )

        # Simulate API requests with injection attempts
        api_requests = [
            {
                "endpoint": "/articles",
                "method": "POST",
                "data": {
                    "title": "Test Article'; DROP TABLE article;--",
                    "content": "This is a test article with SQL injection in title",
                    "author": "admin' OR '1'='1",
                },
            },
            {
                "endpoint": "/articles",
                "method": "GET",
                "params": {
                    "filter": "title LIKE '%'; DELETE FROM article;--%'",
                    "sort": "created_at DESC; DROP TABLE article;",
                },
            },
            {
                "endpoint": "/articles/bulk",
                "method": "POST",
                "data": [
                    {
                        "title": "Article 1",
                        "content": "Content 1",
                        "author": "Author 1",
                    },
                    {
                        "title": "Article 2'; UPDATE article SET published=true;",
                        "content": "Content 2",
                        "author": "Author 2",
                    },
                ],
            },
        ]

        # Process requests through workflow
        workflow = WorkflowBuilder()

        # Create articles
        workflow.add_node(
            "ArticleBulkCreateNode",
            "create_articles",
            {
                "data": [
                    {
                        "title": api_requests[0]["data"]["title"],
                        "content": api_requests[0]["data"]["content"],
                        "author": api_requests[0]["data"]["author"],
                    }
                ]
            },
        )

        # List articles (simulating API GET)
        workflow.add_node(
            "ArticleListNode",
            "list_articles",
            {"filter": {"published": False}, "order_by": ["created_at"], "limit": 10},
        )

        workflow.add_connection("create_articles", "list_articles")

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify security
        conn = sqlite3.connect("test_api.db")
        cursor = conn.cursor()

        # Table should exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='article'"
        )
        assert cursor.fetchone() is not None

        # Malicious strings should be stored as data
        cursor.execute(
            "SELECT author FROM article WHERE content LIKE ?", ("%test article%",)
        )
        author = cursor.fetchone()[0]
        assert author == "admin' OR '1'='1"

        # No unauthorized updates
        cursor.execute("SELECT COUNT(*) FROM article WHERE published = 1")
        published_count = cursor.fetchone()[0]
        assert published_count == 0  # No articles published by injection

        conn.close()

    def test_multi_tenant_injection_isolation(self):
        """Test multi-tenant scenarios with injection attempts."""
        db = DataFlow(database_url="sqlite:///test_e2e.db", multi_tenant=True)

        @db.model
        class Document:
            title: str
            content: str
            tenant_id: str
            confidential: bool = False

        workflow = WorkflowBuilder()

        # Create documents for different tenants
        tenant_a_docs = [
            {
                "title": "Public Doc A",
                "content": "Tenant A public",
                "tenant_id": "tenant_a",
            },
            {
                "title": "Secret Doc A",
                "content": "Tenant A confidential",
                "tenant_id": "tenant_a",
                "confidential": True,
            },
        ]

        tenant_b_docs = [
            {
                "title": "Public Doc B",
                "content": "Tenant B public",
                "tenant_id": "tenant_b",
            },
            {
                "title": "Injection'; SELECT * FROM document WHERE tenant_id='tenant_a';",
                "content": "Trying to access tenant A",
                "tenant_id": "tenant_b",
            },
        ]

        # Create documents
        workflow.add_node(
            "DocumentBulkCreateNode",
            "create_tenant_a",
            {"data": tenant_a_docs, "tenant_id": "tenant_a"},
        )

        workflow.add_node(
            "DocumentBulkCreateNode",
            "create_tenant_b",
            {"data": tenant_b_docs, "tenant_id": "tenant_b"},
        )

        # Try to access across tenants with injection
        workflow.add_node(
            "DocumentListNode",
            "tenant_b_access",
            {
                "filter": {
                    "tenant_id": "tenant_b' OR tenant_id='tenant_a"
                },  # Injection attempt
                "tenant_id": "tenant_b",  # Should only see tenant B
            },
        )

        workflow.add_connection("create_tenant_a", "create_tenant_b")
        workflow.add_connection("create_tenant_b", "tenant_b_access")

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify tenant isolation
        conn = sqlite3.connect("test_e2e.db")
        cursor = conn.cursor()

        # Each tenant should only see their documents
        cursor.execute(
            "SELECT COUNT(*) FROM document WHERE tenant_id = ?", ("tenant_a",)
        )
        tenant_a_count = cursor.fetchone()[0]
        assert tenant_a_count == len(tenant_a_docs)

        cursor.execute(
            "SELECT COUNT(*) FROM document WHERE tenant_id = ?", ("tenant_b",)
        )
        tenant_b_count = cursor.fetchone()[0]
        assert tenant_b_count == len(tenant_b_docs)

        # Verify injection attempt stored as data
        cursor.execute(
            "SELECT content FROM document WHERE title LIKE ?", ("%Injection%",)
        )
        content = cursor.fetchone()[0]
        assert content == "Trying to access tenant A"

        conn.close()

    def test_transaction_workflow_with_injection(self):
        """Test transaction workflows with injection attempts."""
        db = DataFlow(database_url="sqlite:///test_e2e.db")

        @db.model
        class Account:
            account_number: str
            balance: float
            owner: str
            status: str = "active"

        @db.model
        class Transaction:
            from_account: str
            to_account: str
            amount: float
            description: str
            status: str = "pending"

        workflow = WorkflowBuilder()

        # Create accounts
        accounts = [
            {"account_number": "ACC001", "balance": 10000.0, "owner": "Alice"},
            {"account_number": "ACC002", "balance": 5000.0, "owner": "Bob"},
            {
                "account_number": "ACC003",
                "balance": 1000.0,
                "owner": "Charlie'; DROP TABLE account;",
            },
        ]

        workflow.add_node(
            "AccountBulkCreateNode", "create_accounts", {"data": accounts}
        )

        # Create transaction with injection attempts
        workflow.add_node(
            "TransactionCreateNode",
            "create_transaction",
            {
                "from_account": "ACC001",
                "to_account": "ACC002'; UPDATE account SET balance=999999;--",
                "amount": 500.0,
                "description": "Payment'; DELETE FROM transaction;",
                "status": "pending",
            },
        )

        workflow.add_connection("create_accounts", "create_transaction")

        # Process transaction (with balance updates)
        workflow.add_node(
            "AccountUpdateNode",
            "update_sender",
            {
                "filter": {"account_number": "ACC001"},
                "update": {"balance": 9500.0},  # Deduct amount
            },
        )

        workflow.add_node(
            "AccountUpdateNode",
            "update_receiver",
            {
                "filter": {"account_number": "ACC002"},
                "update": {"balance": 5500.0},  # Add amount
            },
        )

        workflow.add_connection("create_transaction", "update_sender")
        workflow.add_connection("update_sender", "update_receiver")

        # Update transaction status
        workflow.add_node(
            "TransactionUpdateNode",
            "complete_transaction",
            {
                "filter": {"status": "pending"},
                "update": {"status": "completed'; DROP TABLE account;"},
            },
        )

        workflow.add_connection("update_receiver", "complete_transaction")

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify transaction integrity
        conn = sqlite3.connect("test_e2e.db")
        cursor = conn.cursor()

        # All tables should exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        assert "account" in tables
        assert "transaction" in tables

        # Verify balances are correct
        cursor.execute(
            "SELECT balance FROM account WHERE account_number = ?", ("ACC001",)
        )
        assert cursor.fetchone()[0] == 9500.0

        cursor.execute(
            "SELECT balance FROM account WHERE account_number = ?", ("ACC002",)
        )
        assert cursor.fetchone()[0] == 5500.0

        # No unauthorized balance changes
        cursor.execute("SELECT MAX(balance) FROM account")
        max_balance = cursor.fetchone()[0]
        assert max_balance < 100000  # No 999999 injection

        conn.close()

    def test_performance_under_injection_attacks(self):
        """Test system performance doesn't degrade under injection attempts."""
        import time

        db = DataFlow(database_url="sqlite:///test_e2e.db")

        @db.model
        class Log:
            timestamp: str
            level: str
            message: str
            source: str

        # Generate mix of normal and malicious log entries
        log_entries = []
        for i in range(1000):
            if i % 10 == 0:
                # Injection attempt every 10th entry
                log_entries.append(
                    {
                        "timestamp": f"2025-01-11T12:00:{i%60:02d}",
                        "level": "ERROR'; DROP TABLE log;--",
                        "message": f"Message {i}",
                        "source": "system",
                    }
                )
            else:
                # Normal entry
                log_entries.append(
                    {
                        "timestamp": f"2025-01-11T12:00:{i%60:02d}",
                        "level": "INFO",
                        "message": f"Normal log message {i}",
                        "source": "application",
                    }
                )

        workflow = WorkflowBuilder()

        # Bulk insert with timing
        workflow.add_node(
            "LogBulkCreateNode", "insert_logs", {"data": log_entries, "batch_size": 100}
        )

        # Query with injection attempt
        workflow.add_node(
            "LogListNode",
            "query_logs",
            {
                "filter": {
                    "level": "ERROR' OR '1'='1",  # Injection attempt
                    "source": "system",
                },
                "limit": 100,
            },
        )

        workflow.add_connection("insert_logs", "query_logs")

        runtime = LocalRuntime()

        # Measure execution time
        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        execution_time = time.time() - start_time

        # Performance should not degrade significantly
        assert execution_time < 5.0, f"Execution took too long: {execution_time}s"

        # Verify data integrity
        conn = sqlite3.connect("test_e2e.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM log")
        count = cursor.fetchone()[0]
        assert count == len(log_entries)
        conn.close()
