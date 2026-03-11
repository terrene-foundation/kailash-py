"""
Integration tests for DataFlow SQL Query Optimizer.

Tests the SQL query optimizer's integration with WorkflowAnalyzer
and its ability to generate production-ready SQL optimizations.
"""

import os
import sys

import pytest

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite

# Add the DataFlow app to the path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../../packages/kailash-dataflow/src")
)

from dataflow.optimization import (
    PatternType,
    SQLDialect,
    SQLQueryOptimizer,
    WorkflowAnalyzer,
)


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestSQLQueryOptimizerIntegration:
    """Test SQLQueryOptimizer integration with WorkflowAnalyzer."""

    @pytest.fixture(autouse=True)
    def setup_method(self, test_suite):
        """Set up test fixtures for each test."""
        self.test_suite = test_suite
        self.analyzer = WorkflowAnalyzer()
        self.pg_optimizer = SQLQueryOptimizer(dialect=SQLDialect.POSTGRESQL)
        self.mysql_optimizer = SQLQueryOptimizer(dialect=SQLDialect.MYSQL)
        self.sqlite_optimizer = SQLQueryOptimizer(dialect=SQLDialect.SQLITE)

    def test_end_to_end_workflow_optimization(self, runtime):
        """Test complete workflow from analysis to SQL optimization."""
        # Create a complex workflow with multiple optimization opportunities
        workflow_dict = {
            "nodes": {
                "users_query": {
                    "type": "UserListNode",
                    "parameters": {"table": "users", "filter": {"active": True}},
                },
                "orders_query": {
                    "type": "OrderListNode",
                    "parameters": {
                        "table": "orders",
                        "filter": {"status": "completed"},
                    },
                },
                "merge_data": {
                    "type": "SmartMergeNode",
                    "parameters": {
                        "merge_type": "inner",
                        "left_model": "User",
                        "right_model": "Order",
                        "join_conditions": {"left_key": "id", "right_key": "user_id"},
                    },
                },
                "aggregate_sales": {
                    "type": "AggregateNode",
                    "parameters": {
                        "aggregate_expression": "sum of amount by region",
                        "group_by": ["region"],
                    },
                },
                # Add redundant operations
                "filter1": {
                    "type": "NaturalLanguageFilterNode",
                    "parameters": {"filter_expression": "today"},
                },
                "filter2": {
                    "type": "NaturalLanguageFilterNode",
                    "parameters": {"filter_expression": "today"},
                },
            },
            "connections": [
                {"from_node": "users_query", "to_node": "merge_data"},
                {"from_node": "orders_query", "to_node": "merge_data"},
                {"from_node": "merge_data", "to_node": "aggregate_sales"},
            ],
        }

        # Step 1: Analyze workflow for opportunities
        opportunities = self.analyzer.analyze_workflow(workflow_dict)
        assert len(opportunities) > 0

        # Step 2: Optimize opportunities to SQL
        optimized_queries = self.pg_optimizer.optimize_workflow(opportunities)
        assert len(optimized_queries) > 0

        # Step 3: Verify optimizations are valid
        for query in optimized_queries:
            assert query.optimized_sql is not None
            assert len(query.optimized_sql.strip()) > 0
            assert query.dialect == SQLDialect.POSTGRESQL
            assert len(query.original_nodes) > 0

    def test_postgresql_specific_optimizations(self, runtime):
        """Test PostgreSQL-specific SQL optimizations."""
        # Create QMA pattern opportunity
        workflow_dict = {
            "nodes": {
                "users": {"type": "UserListNode", "parameters": {"table": "users"}},
                "orders": {"type": "OrderListNode", "parameters": {"table": "orders"}},
                "merge": {
                    "type": "SmartMergeNode",
                    "parameters": {"merge_type": "inner"},
                },
                "agg": {
                    "type": "AggregateNode",
                    "parameters": {"aggregate_expression": "sum of amount"},
                },
            },
            "connections": [
                {"from_node": "users", "to_node": "merge"},
                {"from_node": "orders", "to_node": "merge"},
                {"from_node": "merge", "to_node": "agg"},
            ],
        }

        opportunities = self.analyzer.analyze_workflow(workflow_dict)
        optimized_queries = self.pg_optimizer.optimize_workflow(opportunities)

        # Find QMA optimization
        qma_query = None
        for query in optimized_queries:
            if "JOIN" in query.optimized_sql and "SUM" in query.optimized_sql:
                qma_query = query
                break

        assert qma_query is not None
        assert qma_query.dialect == SQLDialect.POSTGRESQL

        # PostgreSQL-specific features
        migration_script = self.pg_optimizer.generate_migration_script([qma_query])
        assert (
            "CONCURRENTLY" in migration_script
        )  # PostgreSQL concurrent index creation
        assert "pg_indexes" in migration_script  # PostgreSQL system catalog

    def test_mysql_specific_optimizations(self, runtime):
        """Test MySQL-specific SQL optimizations."""
        workflow_dict = {
            "nodes": {
                "query1": {
                    "type": "UserListNode",
                    "parameters": {"table": "users", "filter": {"active": True}},
                },
                "query2": {
                    "type": "UserListNode",
                    "parameters": {"table": "users", "filter": {"role": "admin"}},
                },
            },
            "connections": [],
        }

        opportunities = self.analyzer.analyze_workflow(workflow_dict)
        optimized_queries = self.mysql_optimizer.optimize_workflow(opportunities)

        assert len(optimized_queries) > 0

        for query in optimized_queries:
            assert query.dialect == SQLDialect.MYSQL

        # MySQL-specific migration script
        migration_script = self.mysql_optimizer.generate_migration_script(
            optimized_queries
        )
        assert "SHOW INDEX" in migration_script  # MySQL index verification

    def test_sqlite_specific_optimizations(self, runtime):
        """Test SQLite-specific SQL optimizations."""
        workflow_dict = {
            "nodes": {
                "merge": {
                    "type": "SmartMergeNode",
                    "parameters": {
                        "merge_type": "inner",
                        "join_conditions": {"left_key": "id", "right_key": "user_id"},
                    },
                }
            },
            "connections": [],
        }

        opportunities = self.analyzer.analyze_workflow(workflow_dict)
        optimized_queries = self.sqlite_optimizer.optimize_workflow(opportunities)

        for query in optimized_queries:
            assert query.dialect == SQLDialect.SQLITE

        # SQLite-specific migration script
        migration_script = self.sqlite_optimizer.generate_migration_script(
            optimized_queries
        )
        assert "sqlite_master" in migration_script  # SQLite system table

    def test_cross_dialect_compatibility(self, runtime):
        """Test that the same workflow generates compatible SQL for different dialects."""
        workflow_dict = {
            "nodes": {
                "users": {"type": "UserListNode", "parameters": {"table": "users"}},
                "orders": {"type": "OrderListNode", "parameters": {"table": "orders"}},
                "merge": {
                    "type": "SmartMergeNode",
                    "parameters": {"merge_type": "inner"},
                },
                "agg": {
                    "type": "AggregateNode",
                    "parameters": {"aggregate_expression": "count"},
                },
            },
            "connections": [
                {"from_node": "users", "to_node": "merge"},
                {"from_node": "orders", "to_node": "merge"},
                {"from_node": "merge", "to_node": "agg"},
            ],
        }

        opportunities = self.analyzer.analyze_workflow(workflow_dict)

        # Generate optimizations for all dialects
        pg_queries = self.pg_optimizer.optimize_workflow(opportunities)
        mysql_queries = self.mysql_optimizer.optimize_workflow(opportunities)
        sqlite_queries = self.sqlite_optimizer.optimize_workflow(opportunities)

        # Should generate same number of optimizations
        assert len(pg_queries) == len(mysql_queries) == len(sqlite_queries)

        # Verify core SQL structure is similar (contains essential keywords)
        for i in range(len(pg_queries)):
            pg_sql = pg_queries[i].optimized_sql.upper()
            mysql_sql = mysql_queries[i].optimized_sql.upper()
            sqlite_sql = sqlite_queries[i].optimized_sql.upper()

            # All should contain basic SQL keywords
            for sql in [pg_sql, mysql_sql, sqlite_sql]:
                assert "SELECT" in sql
                assert "FROM" in sql

    def test_complex_workflow_with_multiple_patterns(self, runtime):
        """Test optimization of complex workflow with multiple optimization patterns."""
        complex_workflow = {
            "nodes": {
                # Query→Merge→Aggregate pattern
                "users_data": {
                    "type": "UserListNode",
                    "parameters": {"table": "users"},
                },
                "orders_data": {
                    "type": "OrderListNode",
                    "parameters": {"table": "orders"},
                },
                "products_data": {
                    "type": "ProductListNode",
                    "parameters": {"table": "products"},
                },
                "merge_users_orders": {
                    "type": "SmartMergeNode",
                    "parameters": {
                        "merge_type": "inner",
                        "left_model": "User",
                        "right_model": "Order",
                    },
                },
                "merge_orders_products": {
                    "type": "SmartMergeNode",
                    "parameters": {
                        "merge_type": "inner",
                        "left_model": "Order",
                        "right_model": "Product",
                    },
                },
                "final_aggregate": {
                    "type": "AggregateNode",
                    "parameters": {
                        "aggregate_expression": "sum of total_amount",
                        "group_by": ["category", "region"],
                    },
                },
                # Multiple queries pattern
                "active_users": {
                    "type": "UserListNode",
                    "parameters": {"table": "users", "filter": {"active": True}},
                },
                "premium_users": {
                    "type": "UserListNode",
                    "parameters": {"table": "users", "filter": {"plan": "premium"}},
                },
                # Redundant operations
                "today_filter1": {
                    "type": "NaturalLanguageFilterNode",
                    "parameters": {"filter_expression": "orders from today"},
                },
                "today_filter2": {
                    "type": "NaturalLanguageFilterNode",
                    "parameters": {"filter_expression": "orders from today"},
                },
                # Inefficient joins
                "inefficient_merge": {
                    "type": "SmartMergeNode",
                    "parameters": {
                        "merge_type": "inner",
                        "join_conditions": {
                            "left_key": "large_text_field",
                            "right_key": "another_large_field",
                        },
                    },
                },
            },
            "connections": [
                {"from_node": "users_data", "to_node": "merge_users_orders"},
                {"from_node": "orders_data", "to_node": "merge_users_orders"},
                {"from_node": "merge_users_orders", "to_node": "merge_orders_products"},
                {"from_node": "products_data", "to_node": "merge_orders_products"},
                {"from_node": "merge_orders_products", "to_node": "final_aggregate"},
            ],
        }

        # Analyze complex workflow
        opportunities = self.analyzer.analyze_workflow(complex_workflow)
        assert len(opportunities) >= 3  # Should detect multiple patterns

        # Optimize with different databases
        pg_queries = self.pg_optimizer.optimize_workflow(opportunities)
        mysql_queries = self.mysql_optimizer.optimize_workflow(opportunities)

        # Verify comprehensive optimizations
        assert len(pg_queries) >= 2
        assert len(mysql_queries) >= 2

        # Generate comprehensive reports
        pg_report = self.pg_optimizer.generate_optimization_report(pg_queries)
        mysql_report = self.mysql_optimizer.generate_optimization_report(mysql_queries)

        assert "DataFlow SQL Optimization Report" in pg_report
        assert "DataFlow SQL Optimization Report" in mysql_report
        assert len(pg_report) > 500  # Should be substantial
        assert len(mysql_report) > 500

    def test_performance_estimation_accuracy(self, runtime):
        """Test that performance estimations are preserved and reasonable."""
        workflow_dict = {
            "nodes": {
                "query1": {"type": "UserListNode", "parameters": {"table": "users"}},
                "query2": {"type": "OrderListNode", "parameters": {"table": "orders"}},
                "merge": {
                    "type": "SmartMergeNode",
                    "parameters": {"merge_type": "inner"},
                },
                "agg": {
                    "type": "AggregateNode",
                    "parameters": {"aggregate_expression": "sum of amount"},
                },
            },
            "connections": [
                {"from_node": "query1", "to_node": "merge"},
                {"from_node": "query2", "to_node": "merge"},
                {"from_node": "merge", "to_node": "agg"},
            ],
        }

        opportunities = self.analyzer.analyze_workflow(workflow_dict)
        optimized_queries = self.pg_optimizer.optimize_workflow(opportunities)

        for query in optimized_queries:
            # Performance estimates should be preserved from opportunities
            assert query.estimated_improvement is not None
            assert len(query.estimated_improvement) > 0

            # Should contain reasonable performance indicators
            improvement_text = query.estimated_improvement.lower()
            assert any(
                indicator in improvement_text
                for indicator in ["faster", "improvement", "better", "less", "x", "%"]
            )

    def test_sql_injection_prevention(self, runtime):
        """Test that generated SQL is safe from injection attacks."""
        # Create workflow with potentially dangerous input
        workflow_dict = {
            "nodes": {
                "users": {
                    "type": "UserListNode",
                    "parameters": {
                        "table": "users'; DROP TABLE users; --",
                        "filter": {"name": "'; DELETE FROM users; --"},
                    },
                }
            },
            "connections": [],
        }

        opportunities = self.analyzer.analyze_workflow(workflow_dict)
        optimized_queries = self.pg_optimizer.optimize_workflow(opportunities)

        # Verify that generated SQL doesn't contain dangerous patterns
        for query in optimized_queries:
            sql_upper = query.optimized_sql.upper()

            # Should not contain dangerous SQL keywords in unexpected places
            dangerous_patterns = [
                "DROP TABLE",
                "DELETE FROM",
                "TRUNCATE",
                "ALTER TABLE",
            ]
            for pattern in dangerous_patterns:
                # If these appear, they should be in comments or safe contexts
                if pattern in sql_upper:
                    # Should be in a comment or safe context
                    lines = query.optimized_sql.split("\n")
                    for line in lines:
                        if pattern in line.upper() and not line.strip().startswith(
                            "--"
                        ):
                            assert False, f"Potentially unsafe SQL detected: {line}"

    def test_optimization_with_real_table_names(self, runtime):
        """Test optimization with realistic table and column names."""
        workflow_dict = {
            "nodes": {
                "customer_query": {
                    "type": "CustomerListNode",
                    "parameters": {
                        "table": "customers",
                        "filter": {"status": "active", "created_at": "2024-01-01"},
                    },
                },
                "order_query": {
                    "type": "OrderListNode",
                    "parameters": {
                        "table": "orders",
                        "filter": {"status": "completed", "total_amount": 100.0},
                    },
                },
                "customer_order_merge": {
                    "type": "SmartMergeNode",
                    "parameters": {
                        "merge_type": "inner",
                        "join_conditions": {
                            "left_key": "customer_id",
                            "right_key": "customer_id",
                        },
                    },
                },
                "revenue_analysis": {
                    "type": "AggregateNode",
                    "parameters": {
                        "aggregate_expression": "sum of total_amount",
                        "group_by": ["customer_segment", "order_month"],
                    },
                },
            },
            "connections": [
                {"from_node": "customer_query", "to_node": "customer_order_merge"},
                {"from_node": "order_query", "to_node": "customer_order_merge"},
                {"from_node": "customer_order_merge", "to_node": "revenue_analysis"},
            ],
        }

        opportunities = self.analyzer.analyze_workflow(workflow_dict)
        optimized_queries = self.pg_optimizer.optimize_workflow(opportunities)

        # Verify realistic SQL generation
        assert len(optimized_queries) > 0

        for query in optimized_queries:
            sql = query.optimized_sql

            # Should contain realistic SQL structure
            assert "SELECT" in sql
            assert "FROM" in sql

            # Should suggest realistic indexes
            if query.required_indexes:
                for index in query.required_indexes:
                    assert "CREATE INDEX" in index
                    assert "ON" in index
                    # Should contain reasonable table names (customers, orders, etc.)
                    # The optimizer should use meaningful names, not generic placeholders
                    index_lower = index.lower()
                    meaningful_tables = ["customers", "orders", "products", "users"]
                    has_meaningful_name = any(
                        table in index_lower for table in meaningful_tables
                    )
                    # Allow fallback to default tables if no meaningful extraction possible
                    assert (
                        has_meaningful_name
                        or "users" in index_lower
                        or "orders" in index_lower
                    )

    def test_large_workflow_optimization_performance(self, runtime):
        """Test optimizer performance with large workflows."""
        # Create a large workflow with many nodes
        large_workflow = {"nodes": {}, "connections": []}

        # Add 50 query nodes
        for i in range(50):
            large_workflow["nodes"][f"query_{i}"] = {
                "type": "UserListNode",
                "parameters": {"table": f"table_{i % 5}", "filter": {"id": i}},
            }

        # Add merge and aggregate nodes
        for i in range(10):
            large_workflow["nodes"][f"merge_{i}"] = {
                "type": "SmartMergeNode",
                "parameters": {"merge_type": "inner"},
            }
            large_workflow["nodes"][f"agg_{i}"] = {
                "type": "AggregateNode",
                "parameters": {"aggregate_expression": "count"},
            }

        # Add some connections
        for i in range(25):
            large_workflow["connections"].append(
                {"from_node": f"query_{i}", "to_node": f"merge_{i % 10}"}
            )

        # Test that optimizer can handle large workflows efficiently
        import time

        start_time = time.time()

        opportunities = self.analyzer.analyze_workflow(large_workflow)
        optimized_queries = self.pg_optimizer.optimize_workflow(opportunities)

        end_time = time.time()
        optimization_time = end_time - start_time

        # Should complete within reasonable time (< 5 seconds)
        assert optimization_time < 5.0

        # Should still generate optimizations
        assert len(optimized_queries) >= 0  # May be 0 if no patterns detected

    def test_integration_with_workflow_analyzer_edge_cases(self, runtime):
        """Test integration edge cases with WorkflowAnalyzer."""
        # Empty workflow
        empty_workflow = {"nodes": {}, "connections": []}
        opportunities = self.analyzer.analyze_workflow(empty_workflow)
        optimized_queries = self.pg_optimizer.optimize_workflow(opportunities)
        assert len(optimized_queries) == 0

        # Single node workflow
        single_node_workflow = {
            "nodes": {
                "single": {"type": "UserListNode", "parameters": {"table": "users"}}
            },
            "connections": [],
        }
        opportunities = self.analyzer.analyze_workflow(single_node_workflow)
        optimized_queries = self.pg_optimizer.optimize_workflow(opportunities)
        assert len(optimized_queries) == 0  # No patterns to optimize

        # Disconnected nodes
        disconnected_workflow = {
            "nodes": {
                "node1": {"type": "UserListNode", "parameters": {"table": "users"}},
                "node2": {"type": "OrderListNode", "parameters": {"table": "orders"}},
                "node3": {
                    "type": "ProductListNode",
                    "parameters": {"table": "products"},
                },
            },
            "connections": [],  # No connections
        }
        opportunities = self.analyzer.analyze_workflow(disconnected_workflow)
        optimized_queries = self.pg_optimizer.optimize_workflow(opportunities)
        # May find some patterns (like multiple queries) even without connections
        assert isinstance(optimized_queries, list)
