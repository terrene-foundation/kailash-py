"""Unit tests for QueryRouterNode."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.nodes.data.query_router import (
    ConnectionInfo,
    QueryClassifier,
    QueryFingerprint,
    QueryRouterNode,
    QueryType,
    RoutingDecisionEngine,
)


class TestQueryClassifier:
    """Test query classification functionality."""

    @pytest.fixture
    def classifier(self):
        return QueryClassifier()

    def test_classify_simple_select(self, classifier):
        """Test classification of simple SELECT queries."""
        queries = [
            "SELECT * FROM users",
            "SELECT id, name FROM products WHERE active = true",
            "select email from customers where id = 1",
        ]

        for query in queries:
            assert classifier.classify(query) == QueryType.READ_SIMPLE

    def test_classify_complex_select(self, classifier):
        """Test classification of complex SELECT queries."""
        queries = [
            "SELECT u.*, o.* FROM users u JOIN orders o ON u.id = o.user_id",
            "SELECT COUNT(*) FROM sales GROUP BY region HAVING COUNT(*) > 10",
            "SELECT * FROM orders UNION SELECT * FROM archived_orders",
        ]

        for query in queries:
            assert classifier.classify(query) == QueryType.READ_COMPLEX

    def test_classify_write_queries(self, classifier):
        """Test classification of write queries."""
        # Simple writes
        simple_writes = [
            "INSERT INTO users (name, email) VALUES ('John', 'john@example.com')",
            "UPDATE products SET price = 100 WHERE id = 1",
            "DELETE FROM logs WHERE created_at < '2024-01-01'",
        ]

        for query in simple_writes:
            assert classifier.classify(query) == QueryType.WRITE_SIMPLE

        # Bulk writes
        bulk_writes = [
            "INSERT INTO users (name) VALUES ('A'), ('B'), ('C')",
            "COPY users FROM '/tmp/users.csv'",
        ]

        for query in bulk_writes:
            assert classifier.classify(query) == QueryType.WRITE_BULK

    def test_classify_ddl_queries(self, classifier):
        """Test classification of DDL queries."""
        queries = [
            "CREATE TABLE users (id INT PRIMARY KEY)",
            "ALTER TABLE products ADD COLUMN description TEXT",
            "DROP INDEX idx_users_email",
            "TRUNCATE TABLE logs",
        ]

        for query in queries:
            assert classifier.classify(query) == QueryType.DDL

    def test_classify_transaction_queries(self, classifier):
        """Test classification of transaction queries."""
        queries = [
            "BEGIN",
            "START TRANSACTION",
            "COMMIT",
            "ROLLBACK",
        ]

        for query in queries:
            assert classifier.classify(query) == QueryType.TRANSACTION

    def test_fingerprint_creation(self, classifier):
        """Test query fingerprint creation."""
        query = "SELECT * FROM users WHERE id = 123 AND name = 'John'"
        fingerprint = classifier.fingerprint(query, [123, "John"])

        assert fingerprint.query_type == QueryType.READ_SIMPLE
        assert fingerprint.is_read_only is True
        assert "users" in fingerprint.tables
        assert "?" in fingerprint.template  # Parameters normalized
        assert fingerprint.complexity_score < 0.5  # Simple query

    def test_extract_tables(self, classifier):
        """Test table extraction from queries."""
        test_cases = [
            ("SELECT * FROM users", {"users"}),
            (
                "SELECT * FROM users u JOIN orders o ON u.id = o.user_id",
                {"users", "orders"},
            ),
            ("INSERT INTO products (name) VALUES ('test')", {"products"}),
            ("UPDATE customers SET active = false", {"customers"}),
            ("DELETE FROM logs WHERE old = true", {"logs"}),
        ]

        for query, expected_tables in test_cases:
            fingerprint = classifier.fingerprint(query)
            assert fingerprint.tables == expected_tables


class TestRoutingDecisionEngine:
    """Test routing decision engine."""

    @pytest.fixture
    def engine(self):
        return RoutingDecisionEngine(health_threshold=50.0)

    @pytest.fixture
    def connections(self):
        """Create test connections."""
        return [
            ConnectionInfo(
                connection_id="conn1",
                health_score=90.0,
                current_load=2,
                capabilities={"read", "write"},
                avg_latency_ms=10.0,
                last_used=datetime.now(),
            ),
            ConnectionInfo(
                connection_id="conn2",
                health_score=70.0,
                current_load=5,
                capabilities={"read"},
                avg_latency_ms=20.0,
                last_used=datetime.now(),
            ),
            ConnectionInfo(
                connection_id="conn3",
                health_score=40.0,  # Below threshold
                current_load=1,
                capabilities={"read", "write"},
                avg_latency_ms=50.0,
                last_used=datetime.now(),
            ),
        ]

    def test_route_read_query(self, engine, connections):
        """Test routing of read queries."""
        fingerprint = QueryFingerprint(
            template="SELECT * FROM users",
            query_type=QueryType.READ_SIMPLE,
            tables={"users"},
            is_read_only=True,
            complexity_score=0.1,
        )

        decision = engine.select_connection(fingerprint, connections)

        # Should select healthy connection with lower load
        assert decision.connection_id in ["conn1", "conn2"]
        assert decision.confidence > 0.5
        assert len(decision.alternatives) > 0

    def test_route_write_query(self, engine, connections):
        """Test routing of write queries."""
        fingerprint = QueryFingerprint(
            template="INSERT INTO users VALUES (?)",
            query_type=QueryType.WRITE_SIMPLE,
            tables={"users"},
            is_read_only=False,
            complexity_score=0.2,
        )

        decision = engine.select_connection(fingerprint, connections)

        # Should select healthy write-capable connection
        assert decision.connection_id == "conn1"  # Highest health with write capability
        assert "primary_write" in decision.decision_factors["strategy"]

    def test_transaction_affinity(self, engine, connections):
        """Test transaction connection affinity."""
        fingerprint = QueryFingerprint(
            template="SELECT * FROM users",
            query_type=QueryType.READ_SIMPLE,
            tables={"users"},
            is_read_only=True,
            complexity_score=0.1,
        )

        # With transaction context, must use same connection
        decision = engine.select_connection(
            fingerprint, connections, transaction_context="conn2"
        )

        assert decision.connection_id == "conn2"
        assert decision.confidence == 1.0
        assert decision.decision_factors["reason"] == "transaction_affinity"

    def test_no_healthy_connections(self, engine, connections):
        """Test behavior when no healthy connections available."""
        # Set all connections unhealthy
        for conn in connections:
            conn.health_score = 30.0

        fingerprint = QueryFingerprint(
            template="SELECT * FROM users",
            query_type=QueryType.READ_SIMPLE,
            tables={"users"},
            is_read_only=True,
            complexity_score=0.1,
        )

        # Should still make a decision
        decision = engine.select_connection(fingerprint, connections)
        assert decision.connection_id in ["conn1", "conn2", "conn3"]


class TestQueryRouterNode:
    """Test QueryRouterNode integration."""

    @pytest.fixture
    def router_config(self):
        return {
            "name": "test_router",
            "connection_pool": "test_pool",
            "enable_read_write_split": True,
            "cache_size": 100,
            "pattern_learning": True,
            "health_threshold": 50.0,
        }

    @pytest.fixture
    def mock_runtime(self):
        """Create mock runtime with pool node."""
        runtime = MagicMock()
        pool_node = AsyncMock()
        runtime.get_node.return_value = pool_node
        return runtime, pool_node

    @pytest.mark.asyncio
    async def test_basic_query_routing(self, router_config, mock_runtime):
        """Test basic query routing functionality."""
        runtime, pool_node = mock_runtime

        # Configure pool node responses
        pool_node.process.side_effect = [
            # get_status response
            {
                "connections": {
                    "conn1": {
                        "health_score": 90,
                        "active_queries": 0,
                        "capabilities": ["read", "write"],
                        "avg_latency_ms": 10,
                        "last_used": datetime.now().isoformat(),
                    }
                }
            },
            # execute response
            {
                "success": True,
                "data": [{"id": 1, "name": "Test"}],
                "execution_time": 0.05,
            },
        ]

        router = QueryRouterNode(**router_config)
        router.runtime = runtime

        # Route a simple query
        result = await router.process(
            {"query": "SELECT * FROM users WHERE id = ?", "parameters": [1]}
        )

        assert result["success"] is True
        assert result["data"] == [{"id": 1, "name": "Test"}]
        assert "routing_metadata" in result
        assert result["routing_metadata"]["query_type"] == "read_simple"

    @pytest.mark.asyncio
    async def test_transaction_handling(self, router_config, mock_runtime):
        """Test transaction command handling."""
        runtime, pool_node = mock_runtime

        # Configure pool node responses
        pool_node.process.side_effect = [
            # get_status for BEGIN
            {
                "connections": {
                    "conn1": {
                        "health_score": 90,
                        "active_queries": 0,
                        "capabilities": ["read", "write"],
                        "avg_latency_ms": 10,
                        "last_used": datetime.now().isoformat(),
                    }
                }
            },
            # execute BEGIN response
            {"success": True, "data": None},
        ]

        router = QueryRouterNode(**router_config)
        router.runtime = runtime

        # Start transaction
        result = await router.process({"query": "BEGIN", "session_id": "test_session"})

        assert result["transaction_started"] is True
        assert result["connection_id"] == "conn1"
        assert "test_session" in router.active_transactions

    @pytest.mark.asyncio
    async def test_prepared_statement_caching(self, router_config, mock_runtime):
        """Test prepared statement caching."""
        runtime, pool_node = mock_runtime

        # Configure pool node responses
        pool_node.process.side_effect = [
            # First query - get_status
            {
                "connections": {
                    "conn1": {
                        "health_score": 90,
                        "active_queries": 0,
                        "capabilities": ["read", "write"],
                        "avg_latency_ms": 10,
                        "last_used": datetime.now().isoformat(),
                    }
                }
            },
            # First query - execute with prepared statement
            {
                "success": True,
                "data": [{"count": 10}],
                "execution_time": 0.05,
                "prepared_statement_name": "stmt_12345",
            },
            # Second query - get_status
            {
                "connections": {
                    "conn1": {
                        "health_score": 90,
                        "active_queries": 0,
                        "capabilities": ["read", "write"],
                        "avg_latency_ms": 10,
                        "last_used": datetime.now().isoformat(),
                    }
                }
            },
            # Second query - execute (should use cached statement)
            {"success": True, "data": [{"count": 20}], "execution_time": 0.02},
        ]

        router = QueryRouterNode(**router_config)
        router.runtime = runtime

        # Execute same query twice
        query = "SELECT COUNT(*) FROM users WHERE active = ?"

        result1 = await router.process({"query": query, "parameters": [True]})

        result2 = await router.process({"query": query, "parameters": [False]})

        # Check cache behavior
        assert router.metrics["cache_misses"] == 1
        assert router.metrics["cache_hits"] == 1

        # Second execution should be faster (cached)
        assert result2["routing_metadata"]["cache_hit"] is True

    @pytest.mark.asyncio
    async def test_error_handling(self, router_config, mock_runtime):
        """Test error handling in query routing."""
        runtime, pool_node = mock_runtime

        router = QueryRouterNode(**router_config)
        router.runtime = runtime

        # Test missing query
        with pytest.raises(Exception, match="Query routing failed"):
            await router.process({})

        # Test missing connection pool
        runtime.get_node.return_value = None

        with pytest.raises(Exception, match="Connection pool .* not found"):
            await router.process({"query": "SELECT 1"})

    def test_query_classifier_caching(self):
        """Test that query classifier caches results."""
        classifier = QueryClassifier()

        # Same query should hit cache
        query = "SELECT * FROM users WHERE id = ?"

        # First classification
        type1 = classifier.classify(query)
        initial_cache_size = len(classifier.classification_cache)

        # Second classification (should hit cache)
        type2 = classifier.classify(query)
        final_cache_size = len(classifier.classification_cache)

        assert type1 == type2
        assert initial_cache_size == final_cache_size

    def test_connection_score_calculation(self):
        """Test connection scoring algorithm."""
        engine = RoutingDecisionEngine()

        # High-scoring connection
        good_conn = ConnectionInfo(
            connection_id="good",
            health_score=95.0,
            current_load=1,
            capabilities={"read", "write"},
            avg_latency_ms=5.0,
            last_used=datetime.now(),
        )

        # Low-scoring connection
        bad_conn = ConnectionInfo(
            connection_id="bad",
            health_score=60.0,
            current_load=8,
            capabilities={"read", "write"},
            avg_latency_ms=80.0,
            last_used=datetime.now(),
        )

        fingerprint = QueryFingerprint(
            template="SELECT * FROM users",
            query_type=QueryType.READ_SIMPLE,
            tables={"users"},
            is_read_only=True,
            complexity_score=0.1,
        )

        good_score = engine._calculate_connection_score(good_conn, fingerprint)
        bad_score = engine._calculate_connection_score(bad_conn, fingerprint)

        assert good_score > bad_score
        assert 0 <= good_score <= 1
        assert 0 <= bad_score <= 1
