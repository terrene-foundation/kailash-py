"""Integration tests for SQLDatabaseNode with PostgreSQL.

These tests require a real PostgreSQL database connection via Docker.
"""

import json
from datetime import datetime
from decimal import Decimal

import pytest
from kailash.nodes.data import SQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError


@pytest.mark.integration
@pytest.mark.requires_postgres
class TestSQLDatabaseNodePostgreSQL:
    """Test SQLDatabaseNode with real PostgreSQL database."""

    @pytest.fixture(scope="class")
    def postgres_config(self):
        """PostgreSQL configuration for tests."""
        return {
            "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
            "pool_size": 5,
            "max_overflow": 10,
        }

    @pytest.fixture(scope="class", autouse=True)
    def postgres_setup(self, postgres_config):
        """Setup PostgreSQL test database."""
        # Setup test data
        from sqlalchemy import create_engine, text

        engine = create_engine(postgres_config["connection_string"])

        with engine.connect() as conn:
            # Drop and create tables
            conn.execute(text("DROP TABLE IF EXISTS test_orders CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS test_users CASCADE"))

            # Create test tables with PostgreSQL specific features
            conn.execute(
                text(
                    """
                CREATE TABLE test_users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(100) UNIQUE,
                    age INTEGER,
                    active BOOLEAN DEFAULT TRUE,
                    balance NUMERIC(10, 2),
                    metadata JSONB,
                    tags TEXT[],
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
                )
            )

            conn.execute(
                text(
                    """
                CREATE TABLE test_orders (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES test_users(id),
                    product VARCHAR(200),
                    quantity INTEGER,
                    price NUMERIC(10, 2),
                    order_date DATE,
                    status VARCHAR(50) DEFAULT 'pending'
                )
            """
                )
            )

            # Insert test data
            conn.execute(
                text(
                    """
                INSERT INTO test_users (name, email, age, balance, metadata, tags) VALUES
                ('Alice', 'alice@example.com', 30, 1000.50, '{"vip": true, "level": 5}'::jsonb, ARRAY['premium', 'early_adopter']),
                ('Bob', 'bob@example.com', 25, 500.00, '{"vip": false}'::jsonb, ARRAY['regular']),
                ('Charlie', 'charlie@example.com', 35, 1500.75, '{"vip": true, "level": 3}'::jsonb, ARRAY['premium'])
            """
                )
            )

            conn.execute(
                text(
                    """
                INSERT INTO test_orders (user_id, product, quantity, price, order_date) VALUES
                (1, 'Laptop', 1, 999.99, '2024-01-15'),
                (1, 'Mouse', 2, 29.99, '2024-01-16'),
                (2, 'Keyboard', 1, 79.99, '2024-01-17')
            """
                )
            )

            conn.commit()

        yield

        # Cleanup
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS test_orders CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS test_users CASCADE"))
            conn.commit()

    def test_basic_queries(self, postgres_config):
        """Test basic PostgreSQL queries."""
        node = SQLDatabaseNode(**postgres_config)

        # Test SELECT
        result = node.execute(query="SELECT * FROM test_users ORDER BY id")
        assert "data" in result
        assert len(result["data"]) == 3
        assert result["data"][0]["name"] == "Alice"

        # Test aggregate
        count_result = node.execute(
            query="SELECT COUNT(*) as total FROM test_users WHERE active = TRUE"
        )
        assert count_result["data"][0]["total"] == 3

    def test_jsonb_operations(self, postgres_config):
        """Test PostgreSQL JSONB operations."""
        node = SQLDatabaseNode(**postgres_config)

        # Query JSONB data
        vip_result = node.execute(
            query="""
            SELECT name, metadata->>'vip' as is_vip,
                   (metadata->>'level')::int as level
            FROM test_users
            WHERE metadata->>'vip' = 'true'
            ORDER BY name
        """
        )
        assert len(vip_result["data"]) == 2
        assert vip_result["data"][0]["name"] == "Alice"
        assert vip_result["data"][0]["level"] == 5

        # Update JSONB
        update_result = node.execute(
            query="""
            UPDATE test_users
            SET metadata = jsonb_set(metadata, '{level}', '10'::jsonb)
            WHERE email = :email
        """,
            parameters={"email": "alice@example.com"},
        )
        assert update_result["row_count"] == 1

    def test_array_operations(self, postgres_config):
        """Test PostgreSQL array operations."""
        node = SQLDatabaseNode(**postgres_config)

        # Query array data
        premium_result = node.execute(
            query="""
            SELECT name, tags
            FROM test_users
            WHERE 'premium' = ANY(tags)
            ORDER BY name
        """
        )
        assert len(premium_result["data"]) == 2

        # Array aggregation
        all_tags_result = node.execute(
            query="""
            SELECT array_agg(DISTINCT tag) as all_tags
            FROM test_users, unnest(tags) as tag
        """
        )
        tags = all_tags_result["data"][0]["all_tags"]
        assert "premium" in tags
        assert "regular" in tags

    def test_cte_and_window_functions(self, postgres_config):
        """Test PostgreSQL CTEs and window functions."""
        node = SQLDatabaseNode(**postgres_config)

        # CTE example
        cte_result = node.execute(
            query="""
            WITH user_orders AS (
                SELECT u.name, COUNT(o.id) as order_count,
                       SUM(o.quantity * o.price) as total_spent
                FROM test_users u
                LEFT JOIN test_orders o ON u.id = o.user_id
                GROUP BY u.id, u.name
            )
            SELECT * FROM user_orders
            WHERE order_count > 0
            ORDER BY total_spent DESC
        """
        )
        assert len(cte_result["data"]) == 2

        # Window function example
        window_result = node.execute(
            query="""
            SELECT name, balance,
                   RANK() OVER (ORDER BY balance DESC) as wealth_rank,
                   AVG(balance) OVER () as avg_balance
            FROM test_users
            ORDER BY wealth_rank
        """
        )
        assert window_result["data"][0]["wealth_rank"] == 1
        assert window_result["data"][0]["name"] == "Charlie"

    def test_transactions(self, postgres_config):
        """Test PostgreSQL transaction handling."""
        node = SQLDatabaseNode(**postgres_config)

        # Test RETURNING clause
        insert_result = node.execute(
            query="""
            INSERT INTO test_users (name, email, age, balance)
            VALUES (:name, :email, :age, :balance)
            RETURNING id, name
        """,
            parameters={
                "name": "David",
                "email": "david@example.com",
                "age": 28,
                "balance": 750.25,
            },
        )
        assert insert_result["row_count"] == 1
        assert insert_result["data"][0]["name"] == "David"
        new_id = insert_result["data"][0]["id"]

        # Clean up
        node.execute(
            query="DELETE FROM test_users WHERE id = :id", parameters={"id": new_id}
        )

    def test_full_text_search(self, postgres_config):
        """Test PostgreSQL full-text search capabilities."""
        node = SQLDatabaseNode(**postgres_config)

        # Add a text search column
        node.execute(
            query="ALTER TABLE test_orders ADD COLUMN IF NOT EXISTS search_vector tsvector"
        )

        node.execute(
            query="""
            UPDATE test_orders
            SET search_vector = to_tsvector('english', product)
        """
        )

        # Perform text search
        search_result = node.execute(
            query="""
            SELECT product
            FROM test_orders
            WHERE search_vector @@ plainto_tsquery('english', 'laptop')
        """
        )
        assert len(search_result["data"]) == 1
        assert search_result["data"][0]["product"] == "Laptop"

    def test_upsert_operations(self, postgres_config):
        """Test PostgreSQL UPSERT (INSERT ... ON CONFLICT)."""
        node = SQLDatabaseNode(**postgres_config)

        # Initial insert
        upsert_result = node.execute(
            query="""
            INSERT INTO test_users (email, name, age, balance)
            VALUES (:email, :name, :age, :balance)
            ON CONFLICT (email)
            DO UPDATE SET
                name = EXCLUDED.name,
                age = EXCLUDED.age,
                balance = test_users.balance + EXCLUDED.balance
            RETURNING *
        """,
            parameters={
                "email": "alice@example.com",
                "name": "Alice Updated",
                "age": 31,
                "balance": 100.00,
            },
        )

        assert upsert_result["row_count"] >= 1
        assert upsert_result["data"][0]["name"] == "Alice Updated"
        assert float(upsert_result["data"][0]["balance"]) == 1100.50  # Original + 100

    def test_custom_types_and_enums(self, postgres_config):
        """Test PostgreSQL custom types and enums."""
        node = SQLDatabaseNode(**postgres_config)

        # Create enum type
        try:
            node.execute(query="DROP TYPE IF EXISTS order_status CASCADE")
        except:
            pass

        node.execute(
            query="CREATE TYPE order_status AS ENUM ('pending', 'processing', 'shipped', 'delivered')"
        )

        # Use enum in query
        status_result = node.execute(
            query="""
            SELECT DISTINCT status::text as status
            FROM test_orders
            ORDER BY status
        """
        )
        assert status_result["data"][0]["status"] == "pending"

        # Clean up
        node.execute(query="DROP TYPE order_status CASCADE")

    def test_postgres_specific_functions(self, postgres_config):
        """Test PostgreSQL-specific functions."""
        node = SQLDatabaseNode(**postgres_config)

        # Test generate_series
        series_result = node.execute(
            query="""
            SELECT generate_series(1, 5) as num
        """
        )
        assert len(series_result["data"]) == 5

        # Test array operations
        array_result = node.execute(
            query="SELECT ARRAY[1,2,3] as numbers", result_format="dict"
        )
        assert len(array_result["data"]) == 1
        assert "numbers" in array_result["data"][0]
