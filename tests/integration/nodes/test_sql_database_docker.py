"""Integration tests for SQL Database nodes using real Docker containers.

These tests require external services (Docker, PostgreSQL, MySQL, Ollama)
and are properly categorized as Tier 2 integration tests.
"""

import asyncio
import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kailash.nodes.data import AsyncSQLDatabaseNode, SQLDatabaseNode

# Check if Docker services are available
POSTGRES_AVAILABLE = os.getenv("POSTGRES_TEST_URL") is not None
MYSQL_AVAILABLE = os.getenv("MYSQL_TEST_URL") is not None


def generate_test_data():
    """Generate realistic test data for database operations."""
    return [
        {
            "id": 1,
            "name": "Sarah Johnson",
            "email": "sarah.johnson@example.com",
            "department": "Engineering",
            "salary": 120000,
            "hire_date": "2022-03-15",
            "is_active": True,
        },
        {
            "id": 2,
            "name": "Michael Chen",
            "email": "michael.chen@example.com",
            "department": "Product",
            "salary": 110000,
            "hire_date": "2021-07-20",
            "is_active": True,
        },
        {
            "id": 3,
            "name": "Emily Rodriguez",
            "email": "emily.rodriguez@example.com",
            "department": "Marketing",
            "salary": 95000,
            "hire_date": "2023-01-10",
            "is_active": True,
        },
        {
            "id": 4,
            "name": "David Kim",
            "email": "david.kim@example.com",
            "department": "Engineering",
            "salary": 130000,
            "hire_date": "2020-05-01",
            "is_active": False,
        },
    ]


@pytest.mark.integration
@pytest.mark.requires_docker
class TestSQLDatabaseWithDocker:
    """Integration tests for SQL database operations with real Docker containers."""

    @pytest.mark.requires_postgres
    def test_postgres_real_connection(self):
        """Test real PostgreSQL connection and operations."""
        # Use real connection string from environment
        connection_string = os.getenv("POSTGRES_TEST_URL")
        if not connection_string:
            pytest.skip("PostgreSQL test URL not provided")

        node = SQLDatabaseNode(connection_string=connection_string)

        # Create test table
        create_table_query = """
        CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            department VARCHAR(50),
            salary DECIMAL(10, 2),
            hire_date DATE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """

        result = node.execute(query=create_table_query, operation="execute")

        # Check if table creation was successful
        assert "error" not in result or result["error"] is None

        # Insert test data
        test_data = generate_test_data()
        for employee in test_data:
            insert_query = """
            INSERT INTO employees (name, email, department, salary, hire_date, is_active)
            VALUES (:name, :email, :department, :salary, :hire_date, :is_active)
            ON CONFLICT (email) DO NOTHING;
            """

            result = node.execute(
                query=insert_query, operation="execute", parameters=employee
            )

        # Test SELECT with aggregation
        agg_query = """
        SELECT
            department,
            COUNT(*) as employee_count,
            AVG(salary) as avg_salary,
            MAX(salary) as max_salary,
            MIN(salary) as min_salary
        FROM employees
        WHERE is_active = TRUE
        GROUP BY department
        ORDER BY avg_salary DESC;
        """

        result = node.execute(query=agg_query, operation="fetch_all")

        assert "data" in result
        assert len(result["data"]) > 0
        assert all("department" in row for row in result["data"])
        assert all("avg_salary" in row for row in result["data"])

        # Verify data was inserted successfully
        result = node.execute(
            query="SELECT COUNT(*) as count FROM employees;", operation="fetch_all"
        )

        assert result["data"][0]["count"] > 0

        # Cleanup
        node.execute(query="DROP TABLE IF EXISTS employees;", operation="execute")

    def test_mysql_real_connection(self):
        """Test real MySQL connection and operations."""
        # Use real connection string from environment
        connection_string = os.getenv("MYSQL_TEST_URL")
        if not connection_string:
            pytest.skip("MySQL test URL not provided")

        node = SQLDatabaseNode(connection_string=connection_string)

        # Cleanup any existing table first
        node.execute(query="DROP TABLE IF EXISTS products;", operation="execute")

        # Create test table with MySQL syntax
        create_table_query = """
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            price DECIMAL(10, 2) NOT NULL,
            category VARCHAR(50),
            stock_quantity INT DEFAULT 0,
            is_available BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_category (category),
            INDEX idx_price (price)
        );
        """

        result = node.execute(query=create_table_query, operation="execute")

        # Check if table creation was successful
        assert "error" not in result or result["error"] is None

        # Insert product data
        products = [
            {
                "name": "Enterprise Analytics Suite",
                "description": "Advanced analytics platform for business intelligence",
                "price": 4999.99,
                "category": "Software",
                "stock_quantity": 100,
                "is_available": True,
            },
            {
                "name": "Cloud Storage Pro",
                "description": "Secure cloud storage with encryption",
                "price": 299.99,
                "category": "Infrastructure",
                "stock_quantity": 500,
                "is_available": True,
            },
            {
                "name": "API Gateway",
                "description": "High-performance API management solution",
                "price": 1999.99,
                "category": "Infrastructure",
                "stock_quantity": 50,
                "is_available": True,
            },
        ]

        for product in products:
            insert_query = """
            INSERT INTO products (name, description, price, category, stock_quantity, is_available)
            VALUES (:name, :description, :price, :category, :stock_quantity, :is_available);
            """

            result = node.execute(
                query=insert_query, operation="execute", parameters=product
            )

        # Test complex query with JSON functions (MySQL 5.7+)
        json_query = """
        SELECT
            name,
            price,
            JSON_OBJECT(
                'name', name,
                'price', price,
                'in_stock', IF(stock_quantity > 0, TRUE, FALSE)
            ) as product_json
        FROM products
        WHERE category = :category
        ORDER BY price DESC;
        """

        result = node.execute(
            query=json_query,
            operation="fetch_all",
            parameters={"category": "Infrastructure"},
        )

        assert "data" in result
        assert len(result["data"]) == 2
        assert all("product_json" in row for row in result["data"])

        # Cleanup
        node.execute(query="DROP TABLE IF EXISTS products;", operation="execute")

    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_async_postgres_operations(self):
        """Test async PostgreSQL operations with real connection."""
        connection_string = os.getenv("POSTGRES_TEST_URL")
        if not connection_string:
            pytest.skip("PostgreSQL test URL not provided")

        node = AsyncSQLDatabaseNode(connection_string=connection_string)

        # Create async table
        create_query = """
        CREATE TABLE IF NOT EXISTS async_events (
            id SERIAL PRIMARY KEY,
            event_type VARCHAR(50) NOT NULL,
            event_data JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """

        result = await node.async_run(query=create_query, operation="execute")

        # Check if table creation was successful
        assert "error" not in result or result["error"] is None

        # Insert multiple events concurrently
        events = [
            {
                "event_type": "user_login",
                "event_data": {"user_id": 1, "ip": "192.168.1.1"},
            },
            {
                "event_type": "page_view",
                "event_data": {"page": "/dashboard", "user_id": 1},
            },
            {
                "event_type": "api_call",
                "event_data": {"endpoint": "/api/users", "method": "GET"},
            },
            {
                "event_type": "user_logout",
                "event_data": {"user_id": 1, "duration": 3600},
            },
        ]

        insert_tasks = []
        for event in events:
            insert_query = """
            INSERT INTO async_events (event_type, event_data)
            VALUES (:event_type, :event_data::jsonb);
            """

            task = node.async_run(
                query=insert_query,
                operation="execute",
                params={
                    "event_type": event["event_type"],
                    "event_data": json.dumps(event["event_data"]),
                },
            )
            insert_tasks.append(task)

        # Wait for all inserts
        results = await asyncio.gather(*insert_tasks)
        assert all("error" not in r or r["error"] is None for r in results)

        # Query with JSONB operations
        jsonb_query = """
        SELECT
            event_type,
            event_data->>'user_id' as user_id,
            event_data
        FROM async_events
        WHERE event_data ? 'user_id'
        ORDER BY created_at;
        """

        result = await node.async_run(query=jsonb_query, operation="fetch_all")

        assert "result" in result
        assert "data" in result["result"]
        assert len(result["result"]["data"]) > 0
        assert all(
            "user_id" in row for row in result["result"]["data"] if row["user_id"]
        )

        # Cleanup
        await node.async_run(
            query="DROP TABLE IF EXISTS async_events;", operation="execute"
        )


@pytest.mark.integration
@pytest.mark.requires_ollama
class TestSQLWithOllamaGeneration:
    """Integration tests for SQL operations with Ollama-generated queries."""

    def test_generate_complex_queries_with_ollama(self):
        """Use Ollama to generate complex SQL queries."""
        ollama_url = os.getenv("OLLAMA_TEST_URL")
        if not ollama_url:
            pytest.skip("Ollama test URL not provided")

        from kailash.nodes.ai import LLMAgentNode

        # Create LLM agent
        generator = LLMAgentNode()

        # Generate complex analytics query
        prompt = """Generate a complex SQL query for business analytics that:
        1. Uses CTEs (WITH clauses)
        2. Includes window functions
        3. Has multiple JOINs
        4. Calculates running totals and rankings
        5. Groups by multiple columns

        The query should analyze sales data with tables: orders, customers, products.
        Return only the SQL query without explanation."""

        result = generator.execute(
            prompt=prompt,
            model="llama3.2:1b",
            api_endpoint=f"{ollama_url}/api/generate",
            temperature=0.3,
        )

        generated_query = result.get("response", "")

        # Validate the generated query structure
        assert "WITH" in generated_query or "with" in generated_query
        assert "JOIN" in generated_query or "join" in generated_query
        assert "GROUP BY" in generated_query or "group by" in generated_query

        # If we have a real database, test the generated query
        postgres_url = os.getenv("POSTGRES_TEST_URL")
        if postgres_url:
            node = SQLDatabaseNode(connection_string=postgres_url)

            # Create test schema first
            setup_queries = [
                """CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    email VARCHAR(100)
                );""",
                """CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    price DECIMAL(10,2)
                );""",
                """CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    customer_id INT REFERENCES customers(id),
                    product_id INT REFERENCES products(id),
                    quantity INT,
                    order_date DATE
                );""",
            ]

            try:
                for query in setup_queries:
                    node.execute(query=query, operation="execute")

                # Try to execute the generated query
                # (It might fail if the generated SQL is invalid, which is OK for this test)
                result = node.execute(query=generated_query, operation="fetch_all")

                if "error" not in result or result["error"] is None:
                    print("Generated query executed successfully!")

            finally:
                # Cleanup
                for table in ["orders", "products", "customers"]:
                    node.execute(
                        query=f"DROP TABLE IF EXISTS {table} CASCADE;",
                        operation="execute",
                    )
