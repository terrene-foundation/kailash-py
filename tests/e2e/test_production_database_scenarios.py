"""Production Database Scenarios E2E Tests

Simplified real-world database scenarios without complex Docker orchestration.
Uses the existing test database infrastructure.

Real-world scenarios:
- Multi-database data migration
- Cross-database analytics
- Data synchronization patterns
- Database performance optimization
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict

import pytest
import pytest_asyncio
from kailash import Workflow
from kailash.nodes.code import AsyncPythonCodeNode, PythonCodeNode
from kailash.nodes.data import AsyncSQLDatabaseNode, SQLDatabaseNode
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow import AsyncWorkflowBuilder

from tests.utils.docker_config import DATABASE_CONFIG, skip_if_no_postgres

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio, skip_if_no_postgres()]


class TestProductionDatabaseScenarios:
    """Real-world database pattern tests."""

    @pytest_asyncio.fixture(autouse=True, scope="function")
    async def setup_database(self):
        """Set up test database with required tables."""
        from kailash.nodes.data import SQLDatabaseNode

        connection_string = f"postgresql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}"

        # Create tables
        setup_node = SQLDatabaseNode(
            connection_string=connection_string, database_type="postgresql"
        )

        # Drop existing tables first
        setup_node.execute(
            operation="execute", query="DROP TABLE IF EXISTS transactions CASCADE"
        )
        setup_node.execute(
            operation="execute", query="DROP TABLE IF EXISTS legacy_users CASCADE"
        )
        setup_node.execute(
            operation="execute", query="DROP TABLE IF EXISTS users CASCADE"
        )

        # Create users table
        setup_node.execute(
            operation="execute",
            query="""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100),
                email VARCHAR(200),
                status VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                first_name VARCHAR(100),
                last_name VARCHAR(100)
            )
            """,
        )

        # Create transactions table
        setup_node.execute(
            operation="execute",
            query="""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                amount DECIMAL(10, 2),
                status VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )

        # Create legacy_users table for migration test
        setup_node.execute(
            operation="execute",
            query="""
            CREATE TABLE IF NOT EXISTS legacy_users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(200),
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                status VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
            """,
        )

        # Insert test data
        setup_node.execute(
            operation="execute",
            query="""
            INSERT INTO users (username, email, status, first_name, last_name) VALUES
            ('user1', 'user1@example.com', 'active', 'John', 'Doe'),
            ('user2', 'user2@example.com', 'active', 'Jane', 'Smith'),
            ('user3', 'user3@example.com', 'inactive', 'Bob', 'Johnson')
            ON CONFLICT DO NOTHING
            """,
        )

        # Insert legacy data
        setup_node.execute(
            operation="execute",
            query="""
            INSERT INTO legacy_users (email, first_name, last_name, status, is_active) VALUES
            ('legacy1@example.com', 'Legacy', 'User1', 'active', true),
            ('legacy2@example.com', 'Legacy', 'User2', 'active', true),
            ('invalid-email', 'Invalid', 'Email', 'active', true)
            ON CONFLICT DO NOTHING
            """,
        )

        setup_node.execute(
            operation="execute",
            query="""
            INSERT INTO transactions (user_id, amount, status) VALUES
            (1, 100.00, 'completed'),
            (1, 50.00, 'completed'),
            (2, 200.00, 'completed'),
            (2, 75.00, 'pending')
            ON CONFLICT DO NOTHING
            """,
        )

        # Yield to run the test
        yield

        # Cleanup after test
        try:
            setup_node.execute(
                operation="execute", query="DROP TABLE IF EXISTS transactions CASCADE"
            )
            setup_node.execute(
                operation="execute", query="DROP TABLE IF EXISTS legacy_users CASCADE"
            )
            setup_node.execute(
                operation="execute", query="DROP TABLE IF EXISTS users CASCADE"
            )
        except Exception:
            pass  # Ignore cleanup errors

    async def test_cross_database_analytics(self):
        """Test analytics across multiple databases.

        Real-world use case: Combining user data with transaction data
        for business intelligence reporting.
        """
        builder = AsyncWorkflowBuilder("cross_db_analytics")

        # User database query
        builder.add_node(
            "AsyncSQLDatabaseNode",
            "user_metrics",
            {
                "connection_string": f"postgresql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}",
                "query": """
                SELECT
                    COUNT(*) as total_users,
                    COUNT(CASE WHEN created_at > NOW() - INTERVAL '30 days' THEN 1 END) as new_users,
                    COUNT(CASE WHEN last_login_at > NOW() - INTERVAL '7 days' THEN 1 END) as active_users
                FROM users
            """,
            },
        )

        # Transaction database query (simulated with same DB)
        builder.add_node(
            "AsyncSQLDatabaseNode",
            "transaction_metrics",
            {
                "connection_string": f"postgresql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}",
                "query": """
                SELECT
                    COUNT(*) as total_transactions,
                    SUM(amount) as total_revenue,
                    AVG(amount) as avg_transaction_value,
                    MAX(created_at) as last_transaction_time
                FROM transactions
                WHERE status = 'completed'
            """,
            },
        )

        # Analytics aggregation
        analytics_code = """
from datetime import datetime

# user_metrics and transaction_metrics are passed as variables
user_data = user_metrics if user_metrics else {}
txn_data = transaction_metrics if transaction_metrics else {}

# Extract metrics from query results
user_results = user_data.get('result', {}).get('data', [{}])[0] if user_data.get('result', {}).get('data') else {}
txn_results = txn_data.get('result', {}).get('data', [{}])[0] if txn_data.get('result', {}).get('data') else {}

# Calculate business metrics
total_users = user_results.get('total_users', 0)
total_revenue = float(txn_results.get('total_revenue', 0) or 0)
avg_revenue_per_user = total_revenue / total_users if total_users > 0 else 0

# Create analytics report
result = {
    "user_analytics": {
        "total_users": total_users,
        "new_users_30d": user_results.get('new_users', 0),
        "active_users_7d": user_results.get('active_users', 0),
        "user_growth_rate": user_results.get('new_users', 0) / total_users if total_users > 0 else 0
    },
    "transaction_analytics": {
        "total_transactions": txn_results.get('total_transactions', 0),
        "total_revenue": total_revenue,
        "avg_transaction_value": float(txn_results.get('avg_transaction_value', 0) or 0),
        "last_transaction": str(txn_results.get('last_transaction_time', 'N/A'))
    },
    "business_metrics": {
        "avg_revenue_per_user": avg_revenue_per_user,
        "user_engagement_rate": user_results.get('active_users', 0) / total_users if total_users > 0 else 0,
        "data_quality_score": 1.0 if user_data and txn_data else 0.0
    },
    "report_timestamp": datetime.now().isoformat()
}
"""

        builder.add_node(
            "PythonCodeNode", "analytics_aggregator", {"code": analytics_code}
        )

        # Connect nodes
        builder.add_connection(
            "user_metrics", "result", "analytics_aggregator", "user_metrics"
        )
        builder.add_connection(
            "transaction_metrics",
            "result",
            "analytics_aggregator",
            "transaction_metrics",
        )

        # Build and execute
        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Validate
        assert result is not None
        analytics = result["results"]["analytics_aggregator"]["result"]
        assert "user_analytics" in analytics
        assert "transaction_analytics" in analytics
        assert "business_metrics" in analytics
        assert analytics["business_metrics"]["data_quality_score"] >= 0.0

    async def test_data_migration_with_validation(self):
        """Test data migration between databases with validation.

        Real-world use case: Migrating legacy data to new schema
        with transformation and validation.
        """
        builder = AsyncWorkflowBuilder("data_migration")

        # Extract from source
        builder.add_node(
            "AsyncSQLDatabaseNode",
            "extract_legacy",
            {
                "connection_string": f"postgresql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}",
                "query": """
                SELECT
                    id,
                    email,
                    CONCAT(first_name, ' ', last_name) as full_name,
                    created_at,
                    CASE
                        WHEN status = 'active' THEN true
                        ELSE false
                    END as is_active
                FROM legacy_users
                LIMIT 100
            """,
            },
        )

        # Transform and validate
        transform_code = """
from datetime import datetime

# legacy_data is passed as a variable
rows = legacy_data.get('result', {}).get('data', []) if legacy_data.get('result', {}).get('data') else []

transformed_records = []
validation_errors = []
skipped_count = 0

for row in rows:
    # Validate email format
    email = row.get('email', '')
    if not email or '@' not in email:
        validation_errors.append({
            'id': row.get('id'),
            'error': 'Invalid email format',
            'email': email
        })
        skipped_count += 1
        continue

    # Transform record
    transformed = {
        'user_id': row.get('id'),
        'email': email.lower().strip(),
        'display_name': row.get('full_name', 'Unknown'),
        'is_verified': row.get('is_active', False),
        'migrated_at': datetime.now().isoformat(),
        'legacy_created_at': str(row.get('created_at', ''))
    }

    transformed_records.append(transformed)

result = {
    'transformed_records': transformed_records,
    'total_processed': len(rows),
    'successful_transforms': len(transformed_records),
    'validation_errors': validation_errors,
    'skipped_count': skipped_count,
    'transformation_rate': len(transformed_records) / len(rows) if rows else 0
}
"""

        builder.add_node(
            "PythonCodeNode", "transform_validate", {"code": transform_code}
        )

        # Load to target (simulation)
        load_code = """
import json

# transform_result is passed as a variable
records = transform_result.get('transformed_records', [])

# Simulate batch insert preparation
batch_size = 50
batches = []
for i in range(0, len(records), batch_size):
    batch = records[i:i + batch_size]
    batches.append({
        'batch_id': i // batch_size + 1,
        'record_count': len(batch),
        'records': batch
    })

# Migration summary
result = {
    'migration_summary': {
        'total_records': transform_result.get('total_processed', 0),
        'migrated_records': len(records),
        'failed_records': transform_result.get('skipped_count', 0),
        'batch_count': len(batches),
        'migration_success_rate': transform_result.get('transformation_rate', 0),
        'validation_errors': len(transform_result.get('validation_errors', []))
    },
    'batch_details': [
        {'batch_id': b['batch_id'], 'count': b['record_count']}
        for b in batches
    ],
    'sample_migrated_record': records[0] if records else None
}
"""

        builder.add_node("PythonCodeNode", "load_simulator", {"code": load_code})

        # Connect nodes
        builder.add_connection(
            "extract_legacy", "result", "transform_validate", "legacy_data"
        )
        builder.add_connection(
            "transform_validate", "result", "load_simulator", "transform_result"
        )

        # Build and execute
        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Validate
        assert result is not None
        migration = result["results"]["load_simulator"]["result"]["migration_summary"]
        assert migration["total_records"] >= 0
        assert migration["migration_success_rate"] >= 0
        assert "batch_count" in migration

    async def test_database_performance_monitoring(self):
        """Test database performance monitoring and optimization.

        Real-world use case: Monitoring query performance and
        identifying optimization opportunities.
        """
        builder = AsyncWorkflowBuilder("db_performance_monitor")

        # Performance metrics collection
        perf_monitor_code = f"""
import asyncio
import asyncpg
import time
from datetime import datetime
from statistics import mean, stdev

# Test queries with different complexity
test_queries = [
    {{
        "name": "simple_select",
        "query": "SELECT 1",
        "expected_time": 0.001
    }},
    {{
        "name": "indexed_lookup",
        "query": "SELECT * FROM users WHERE id = 1",
        "expected_time": 0.01
    }},
    {{
        "name": "aggregation_query",
        "query": "SELECT COUNT(*) FROM users WHERE status = 'active'",
        "expected_time": 0.05
    }},
    {{
        "name": "join_query",
        "query": '''
            SELECT u.id, u.email, COUNT(t.id) as transaction_count
            FROM users u
            LEFT JOIN transactions t ON u.id = t.user_id
            GROUP BY u.id, u.email
            LIMIT 10
        ''',
        "expected_time": 0.1
    }}
]

performance_results = []

# Connect to database
conn = await asyncpg.connect(
    host="{DATABASE_CONFIG['host']}",
    port={DATABASE_CONFIG['port']},
    database="{DATABASE_CONFIG['database']}",
    user="{DATABASE_CONFIG['user']}",
    password="{DATABASE_CONFIG['password']}"
)

try:
    # Run each query multiple times
    for test_query in test_queries:
        query_times = []

        for _ in range(5):  # 5 iterations per query
            start_time = time.time()
            await conn.fetch(test_query["query"])
            execution_time = time.time() - start_time
            query_times.append(execution_time)

            # Small delay between queries
            await asyncio.sleep(0.01)

        # Calculate statistics
        avg_time = mean(query_times)
        std_dev = stdev(query_times) if len(query_times) > 1 else 0

        performance_results.append({{
            "query_name": test_query["name"],
            "avg_execution_time": avg_time,
            "std_deviation": std_dev,
            "min_time": min(query_times),
            "max_time": max(query_times),
            "expected_time": test_query["expected_time"],
            "performance_ratio": avg_time / test_query["expected_time"],
            "needs_optimization": avg_time > test_query["expected_time"] * 2
        }})

    # Get database statistics
    db_stats = await conn.fetchrow('''
        SELECT
            (SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active') as active_connections,
            (SELECT COUNT(*) FROM pg_stat_activity) as total_connections,
            pg_database_size(current_database()) as database_size
    ''')

    result = {{
        "performance_metrics": performance_results,
        "database_health": {{
            "active_connections": db_stats["active_connections"],
            "total_connections": db_stats["total_connections"],
            "database_size_mb": db_stats["database_size"] / (1024 * 1024),
            "queries_tested": len(performance_results),
            "optimization_needed": sum(1 for r in performance_results if r["needs_optimization"])
        }},
        "monitoring_timestamp": datetime.now().isoformat()
    }}

finally:
    await conn.close()
"""

        builder.add_node(
            "AsyncPythonCodeNode", "performance_monitor", {"code": perf_monitor_code}
        )

        # Optimization recommendations
        recommendations_code = """
# performance_data is passed as a variable
perf_data = performance_data
metrics = perf_data.get('performance_metrics', [])
db_health = perf_data.get('database_health', {})

recommendations = []

# Analyze query performance
for metric in metrics:
    if metric.get('needs_optimization'):
        query_name = metric.get('query_name', 'unknown')
        perf_ratio = metric.get('performance_ratio', 1)

        if 'join' in query_name:
            recommendations.append({
                'query': query_name,
                'issue': f'Query {perf_ratio:.1f}x slower than expected',
                'recommendation': 'Consider adding indexes on join columns',
                'priority': 'high' if perf_ratio > 5 else 'medium'
            })
        elif 'aggregation' in query_name:
            recommendations.append({
                'query': query_name,
                'issue': f'Aggregation {perf_ratio:.1f}x slower than expected',
                'recommendation': 'Consider materialized views for frequent aggregations',
                'priority': 'medium'
            })

# Database health recommendations
if db_health.get('active_connections', 0) > 50:
    recommendations.append({
        'query': 'connection_pool',
        'issue': 'High number of active connections',
        'recommendation': 'Review connection pooling configuration',
        'priority': 'high'
    })

if db_health.get('database_size_mb', 0) > 1000:
    recommendations.append({
        'query': 'database_size',
        'issue': 'Large database size may impact performance',
        'recommendation': 'Consider archiving old data or partitioning',
        'priority': 'low'
    })

result = {
    'optimization_report': {
        'total_queries_analyzed': len(metrics),
        'queries_needing_optimization': db_health.get('optimization_needed', 0),
        'recommendations': recommendations,
        'overall_health_score': 1 - (db_health.get('optimization_needed', 0) / len(metrics)) if metrics else 1.0
    },
    'performance_summary': {
        'fastest_query': min(metrics, key=lambda x: x['avg_execution_time'])['query_name'] if metrics else None,
        'slowest_query': max(metrics, key=lambda x: x['avg_execution_time'])['query_name'] if metrics else None,
        'avg_performance_ratio': sum(m['performance_ratio'] for m in metrics) / len(metrics) if metrics else 1.0
    }
}
"""

        builder.add_node(
            "PythonCodeNode", "optimization_advisor", {"code": recommendations_code}
        )

        # Connect nodes
        builder.add_connection(
            "performance_monitor", "result", "optimization_advisor", "performance_data"
        )

        # Build and execute
        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Validate
        assert result is not None

        perf_data = result["results"]["performance_monitor"]
        assert "performance_metrics" in perf_data
        assert len(perf_data["performance_metrics"]) > 0
        assert "database_health" in perf_data

        optimization = result["results"]["optimization_advisor"]["result"][
            "optimization_report"
        ]
        assert "overall_health_score" in optimization
        assert optimization["overall_health_score"] >= 0
        assert optimization["overall_health_score"] <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
