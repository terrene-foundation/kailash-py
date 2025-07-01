"""
Production-grade Docker integration tests for async testing framework.

These tests use real Docker containers with PostgreSQL and Redis to validate
the testing framework under realistic production conditions.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from kailash.testing import (
    AsyncAssertions,
    AsyncTestUtils,
    AsyncWorkflowFixtures,
    AsyncWorkflowTestCase,
)
from kailash.workflow import AsyncWorkflowBuilder

# Mark all tests as docker-dependent and slow
pytestmark = [pytest.mark.docker, pytest.mark.slow]


@pytest.mark.asyncio
class TestDockerProductionIntegration:
    """Production-grade Docker integration tests."""

    async def test_real_postgresql_etl_pipeline(self):
        """Test complete ETL pipeline with real PostgreSQL database."""

        class PostgreSQLETLTest(AsyncWorkflowTestCase):
            async def setUp(self):
                await super().setUp()

                # Create real PostgreSQL database
                self.test_db = await AsyncWorkflowFixtures.create_test_database(
                    engine="postgresql",
                    database="etl_test_db",
                    user="etl_user",
                    password="etl_pass123",
                )

                # Create connection
                try:
                    import asyncpg

                    self.db_conn = await asyncpg.connect(self.test_db.connection_string)
                    await self.create_test_resource("db", lambda: self.db_conn)

                    # Set up test schema and data
                    await self._setup_test_data()
                except ImportError:
                    raise ImportError(
                        "asyncpg must be installed for PostgreSQL testing"
                    )

            async def _setup_test_data(self):
                """Set up realistic test data."""
                # Create tables
                await self.db_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS raw_sales (
                        id SERIAL PRIMARY KEY,
                        transaction_date TIMESTAMP,
                        customer_id INTEGER,
                        product_id INTEGER,
                        quantity INTEGER,
                        unit_price DECIMAL(10,2),
                        region VARCHAR(50),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                await self.db_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS customers (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100),
                        email VARCHAR(100),
                        tier VARCHAR(20),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                await self.db_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS products (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100),
                        category VARCHAR(50),
                        cost DECIMAL(10,2),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                await self.db_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sales_summary (
                        id SERIAL PRIMARY KEY,
                        date DATE,
                        region VARCHAR(50),
                        total_revenue DECIMAL(12,2),
                        total_transactions INTEGER,
                        avg_transaction_value DECIMAL(10,2),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                # Insert test data
                customers_data = [
                    (1, "John Smith", "john@example.com", "premium"),
                    (2, "Jane Doe", "jane@example.com", "standard"),
                    (3, "Bob Wilson", "bob@example.com", "premium"),
                    (4, "Alice Brown", "alice@example.com", "standard"),
                    (5, "Charlie Davis", "charlie@example.com", "premium"),
                ]

                products_data = [
                    (1, "Laptop Pro", "Electronics", 800.00),
                    (2, "Wireless Mouse", "Electronics", 25.00),
                    (3, "Office Chair", "Furniture", 150.00),
                    (4, 'Monitor 27"', "Electronics", 300.00),
                    (5, "Desk Lamp", "Furniture", 45.00),
                ]

                sales_data = [
                    ("2024-01-15 10:30:00", 1, 1, 1, 1299.99, "North"),
                    ("2024-01-15 11:45:00", 2, 2, 2, 29.99, "South"),
                    ("2024-01-15 14:20:00", 3, 3, 1, 159.99, "East"),
                    ("2024-01-15 16:10:00", 1, 4, 1, 349.99, "North"),
                    ("2024-01-16 09:15:00", 4, 1, 1, 1299.99, "West"),
                    ("2024-01-16 12:30:00", 5, 5, 3, 49.99, "North"),
                    ("2024-01-16 15:45:00", 2, 2, 5, 29.99, "South"),
                    ("2024-01-17 08:00:00", 3, 4, 1, 349.99, "East"),
                    ("2024-01-17 13:20:00", 1, 3, 2, 159.99, "North"),
                    ("2024-01-17 17:30:00", 4, 1, 1, 1299.99, "West"),
                ]

                # Insert customers
                await self.db_conn.executemany(
                    "INSERT INTO customers (id, name, email, tier) VALUES ($1, $2, $3, $4)",
                    customers_data,
                )

                # Insert products
                await self.db_conn.executemany(
                    "INSERT INTO products (id, name, category, cost) VALUES ($1, $2, $3, $4)",
                    products_data,
                )

                # Insert sales
                await self.db_conn.executemany(
                    "INSERT INTO raw_sales (transaction_date, customer_id, product_id, quantity, unit_price, region) VALUES ($1, $2, $3, $4, $5, $6)",
                    sales_data,
                )

            async def test_production_etl_pipeline(self):
                """Test production-grade ETL pipeline with complex transformations."""
                workflow = (
                    AsyncWorkflowBuilder("production_etl")
                    .add_async_code(
                        "extract_sales",
                        """
# Extract raw sales data with joins
db = await get_resource("db")

query = '''
    SELECT
        rs.id,
        rs.transaction_date,
        rs.quantity,
        rs.unit_price,
        rs.region,
        c.name as customer_name,
        c.tier as customer_tier,
        p.name as product_name,
        p.category as product_category,
        p.cost as product_cost
    FROM raw_sales rs
    JOIN customers c ON rs.customer_id = c.id
    JOIN products p ON rs.product_id = p.id
    WHERE rs.transaction_date >= '2024-01-15'
    ORDER BY rs.transaction_date
'''

sales_data = await db.fetch(query)
result = {
    "raw_sales": [dict(row) for row in sales_data],
    "extracted_count": len(sales_data)
}
""",
                    )
                    .add_async_code(
                        "transform_calculate_metrics",
                        """
# Transform and calculate business metrics
import decimal
from datetime import datetime

transformed_sales = []
daily_summaries = {}

for sale in raw_sales:
    # Calculate revenue and profit
    revenue = float(sale['quantity']) * float(sale['unit_price'])
    profit_margin = 0.3 if sale['customer_tier'] == 'premium' else 0.2
    profit = revenue * profit_margin

    # Enhanced sale record
    enhanced_sale = {
        'id': sale['id'],
        'date': sale['transaction_date'].date(),
        'revenue': revenue,
        'profit': profit,
        'region': sale['region'],
        'customer_tier': sale['customer_tier'],
        'product_category': sale['product_category']
    }
    transformed_sales.append(enhanced_sale)

    # Aggregate daily summaries by region
    date_key = enhanced_sale['date']
    region_key = f"{date_key}_{sale['region']}"

    if region_key not in daily_summaries:
        daily_summaries[region_key] = {
            'date': date_key,
            'region': sale['region'],
            'total_revenue': 0.0,
            'total_profit': 0.0,
            'transaction_count': 0,
            'premium_customers': 0
        }

    summary = daily_summaries[region_key]
    summary['total_revenue'] += revenue
    summary['total_profit'] += profit
    summary['transaction_count'] += 1

    if sale['customer_tier'] == 'premium':
        summary['premium_customers'] += 1

# Calculate average transaction values
for summary in daily_summaries.values():
    if summary['transaction_count'] > 0:
        summary['avg_transaction_value'] = summary['total_revenue'] / summary['transaction_count']
    else:
        summary['avg_transaction_value'] = 0.0

result = {
    "transformed_sales": transformed_sales,
    "daily_summaries": list(daily_summaries.values()),
    "transformation_metrics": {
        "total_revenue": sum(s['total_revenue'] for s in daily_summaries.values()),
        "total_profit": sum(s['total_profit'] for s in daily_summaries.values()),
        "unique_regions": len(set(s['region'] for s in daily_summaries.values())),
        "date_range": len(set(s['date'] for s in daily_summaries.values()))
    }
}
""",
                    )
                    .add_async_code(
                        "load_to_warehouse",
                        """
# Load transformed data to warehouse tables
db = await get_resource("db")

# Clear existing summary data for the date range
await db.execute("DELETE FROM sales_summary WHERE date >= '2024-01-15'")

# Insert daily summaries
insert_count = 0
for summary in daily_summaries:
    await db.execute('''
        INSERT INTO sales_summary (date, region, total_revenue, total_transactions, avg_transaction_value)
        VALUES ($1, $2, $3, $4, $5)
    ''',
    summary['date'],
    summary['region'],
    summary['total_revenue'],
    summary['transaction_count'],
    summary['avg_transaction_value']
    )
    insert_count += 1

# Verify the load
verification_query = '''
    SELECT COUNT(*) as loaded_records,
           SUM(total_revenue) as total_revenue,
           AVG(avg_transaction_value) as avg_transaction_value
    FROM sales_summary
    WHERE date >= '2024-01-15'
'''

verification = await db.fetchrow(verification_query)

result = {
    "records_loaded": insert_count,
    "load_verification": dict(verification),
    "load_status": "success" if insert_count > 0 else "failed"
}
""",
                    )
                    .add_connection(
                        "extract_sales",
                        "raw_sales",
                        "transform_calculate_metrics",
                        "raw_sales",
                    )
                    .add_connection(
                        "transform_calculate_metrics",
                        "daily_summaries",
                        "load_to_warehouse",
                        "daily_summaries",
                    )
                    .build()
                )

                # Execute ETL pipeline with performance monitoring
                start_time = time.time()

                async with self.assert_time_limit(30.0):  # Production SLA
                    result = await self.execute_workflow(workflow, {})

                execution_time = time.time() - start_time

                # Comprehensive assertions
                self.assert_workflow_success(result)

                # Verify extraction
                extract_output = result.get_output("extract_sales")
                assert (
                    extract_output["extracted_count"] >= 10
                ), "Should extract substantial data"

                # Verify transformation
                transform_output = result.get_output("transform_calculate_metrics")
                metrics = transform_output["transformation_metrics"]
                assert metrics["total_revenue"] > 0, "Should calculate revenue"
                assert metrics["total_profit"] > 0, "Should calculate profit"
                assert metrics["unique_regions"] >= 3, "Should process multiple regions"

                # Verify loading
                load_output = result.get_output("load_to_warehouse")
                assert load_output["load_status"] == "success", "Load should succeed"
                assert load_output["records_loaded"] > 0, "Should load records"

                # Performance assertion
                assert (
                    execution_time < 10.0
                ), f"ETL should complete quickly: {execution_time:.2f}s"

                # Data quality validation
                verification = load_output["load_verification"]
                assert verification["loaded_records"] > 0, "Should have loaded records"
                assert verification["total_revenue"] > 0, "Revenue should be positive"

            async def tearDown(self):
                """Clean up database resources."""
                if hasattr(self, "db_conn"):
                    await self.db_conn.close()
                if hasattr(self, "test_db"):
                    await self.test_db.cleanup()
                await super().tearDown()

        async with PostgreSQLETLTest("postgresql_etl_test") as test:
            await test.test_production_etl_pipeline()

    async def test_redis_caching_performance_pipeline(self):
        """Test high-performance caching pipeline with real Redis."""

        class RedisCachingTest(AsyncWorkflowTestCase):
            async def setUp(self):
                await super().setUp()

                # Create real Redis instance
                import docker

                client = docker.from_env()

                # Start Redis container
                self.redis_container = client.containers.run(
                    "redis:7-alpine",
                    ports={"6379/tcp": None},
                    detach=True,
                    remove=False,
                )

                # Get assigned port
                self.redis_container.reload()
                redis_port = int(self.redis_container.ports["6379/tcp"][0]["HostPort"])

                # Wait for Redis to be ready
                await asyncio.sleep(2)

                import aioredis

                self.redis_client = aioredis.from_url(f"redis://localhost:{redis_port}")
                await self.create_test_resource("cache", lambda: self.redis_client)

            async def test_high_throughput_caching_workflow(self):
                """Test high-throughput caching with real Redis."""
                workflow = (
                    AsyncWorkflowBuilder("redis_performance")
                    .add_async_code(
                        "generate_cache_data",
                        """
# Generate substantial test data for caching
import json
import random
from datetime import datetime, timedelta

# Generate 1000 cache entries
cache_entries = []
base_date = datetime.now()

for i in range(1000):
    entry = {
        "id": f"item_{i:04d}",
        "timestamp": (base_date - timedelta(hours=random.randint(0, 72))).isoformat(),
        "data": {
            "value": random.randint(1, 10000),
            "category": random.choice(["A", "B", "C", "D"]),
            "metadata": {
                "processed": random.choice([True, False]),
                "score": round(random.uniform(0, 100), 2),
                "tags": [f"tag_{random.randint(1, 20)}" for _ in range(random.randint(1, 5))]
            }
        }
    }
    cache_entries.append(entry)

result = {
    "cache_entries": cache_entries,
    "entry_count": len(cache_entries)
}
""",
                    )
                    .add_async_code(
                        "bulk_cache_operations",
                        """
# Perform bulk caching operations
import json
import asyncio

cache = await get_resource("cache")

# Performance tracking
start_time = asyncio.get_event_loop().time()

# Bulk SET operations with pipeline
pipe = cache.pipeline()
for entry in cache_entries:
    key = f"perf_test:{entry['id']}"
    value = json.dumps(entry['data'])
    pipe.setex(key, 3600, value)  # 1 hour TTL

# Execute pipeline
await pipe.execute()

set_time = asyncio.get_event_loop().time() - start_time

# Bulk GET operations
get_start = asyncio.get_event_loop().time()
keys = [f"perf_test:item_{i:04d}" for i in range(1000)]

# Use pipeline for bulk gets
pipe = cache.pipeline()
for key in keys:
    pipe.get(key)

cached_values = await pipe.execute()
get_time = asyncio.get_event_loop().time() - get_start

# Validate retrieved data
valid_retrievals = sum(1 for val in cached_values if val is not None)

result = {
    "operations_completed": len(cache_entries),
    "set_time_seconds": set_time,
    "get_time_seconds": get_time,
    "set_ops_per_second": len(cache_entries) / set_time if set_time > 0 else 0,
    "get_ops_per_second": len(keys) / get_time if get_time > 0 else 0,
    "valid_retrievals": valid_retrievals,
    "cache_hit_rate": valid_retrievals / len(keys) if keys else 0,
    "total_test_time": set_time + get_time
}
""",
                    )
                    .add_async_code(
                        "cache_analytics",
                        """
# Analyze cache performance and data patterns
import json

cache = await get_resource("cache")

# Get cache statistics
info = await cache.info()
memory_usage = info.get('used_memory_human', 'unknown')
total_keys = info.get('db0', {}).get('keys', 0) if 'db0' in info else 0

# Sample some cached data for analysis
sample_keys = [f"perf_test:item_{i:04d}" for i in range(0, 100, 10)]
sample_data = []

pipe = cache.pipeline()
for key in sample_keys:
    pipe.get(key)

sample_values = await pipe.execute()

for i, value in enumerate(sample_values):
    if value:
        try:
            data = json.loads(value)
            sample_data.append({
                "key": sample_keys[i],
                "category": data.get("category"),
                "score": data.get("metadata", {}).get("score", 0),
                "processed": data.get("metadata", {}).get("processed", False)
            })
        except json.JSONDecodeError:
            pass

# Calculate analytics
categories = {}
total_score = 0
processed_count = 0

for item in sample_data:
    cat = item["category"]
    categories[cat] = categories.get(cat, 0) + 1
    total_score += item["score"]
    if item["processed"]:
        processed_count += 1

result = {
    "redis_memory_usage": memory_usage,
    "total_keys_in_db": total_keys,
    "sample_size": len(sample_data),
    "category_distribution": categories,
    "average_score": total_score / len(sample_data) if sample_data else 0,
    "processed_percentage": (processed_count / len(sample_data) * 100) if sample_data else 0,
    "performance_summary": {
        "set_ops_per_sec": set_ops_per_second,
        "get_ops_per_sec": get_ops_per_second,
        "cache_hit_rate": cache_hit_rate,
        "total_operations": operations_completed * 2  # SET + GET
    }
}
""",
                    )
                    .add_connection(
                        "generate_cache_data",
                        "cache_entries",
                        "bulk_cache_operations",
                        "cache_entries",
                    )
                    .add_connection(
                        "bulk_cache_operations",
                        "result",
                        "cache_analytics",
                        "performance_data",
                    )
                    .build()
                )

                # Execute with strict performance requirements
                async with self.assert_time_limit(15.0):  # High-performance requirement
                    result = await self.execute_workflow(workflow, {})

                # Comprehensive performance assertions
                self.assert_workflow_success(result)

                # Verify data generation
                generate_output = result.get_output("generate_cache_data")
                assert (
                    generate_output["entry_count"] == 1000
                ), "Should generate 1000 entries"

                # Verify cache performance
                cache_output = result.get_output("bulk_cache_operations")
                assert (
                    cache_output["operations_completed"] == 1000
                ), "Should complete all operations"
                assert (
                    cache_output["set_ops_per_second"] > 100
                ), "Should achieve >100 SET ops/sec"
                assert (
                    cache_output["get_ops_per_second"] > 100
                ), "Should achieve >100 GET ops/sec"
                assert (
                    cache_output["cache_hit_rate"] > 0.99
                ), "Should have >99% hit rate"

                # Verify analytics
                analytics_output = result.get_output("cache_analytics")
                assert analytics_output["sample_size"] > 0, "Should analyze sample data"
                assert (
                    "category_distribution" in analytics_output
                ), "Should analyze categories"
                assert (
                    analytics_output["performance_summary"]["total_operations"] == 2000
                ), "Should track all ops"

                # Performance requirements for production
                perf = analytics_output["performance_summary"]
                assert (
                    perf["set_ops_per_sec"] > 50
                ), f"SET performance too low: {perf['set_ops_per_sec']}"
                assert (
                    perf["get_ops_per_sec"] > 50
                ), f"GET performance too low: {perf['get_ops_per_sec']}"

            async def tearDown(self):
                """Clean up Redis resources."""
                if hasattr(self, "redis_client"):
                    await self.redis_client.aclose()
                if hasattr(self, "redis_container"):
                    self.redis_container.stop()
                    self.redis_container.remove()
                await super().tearDown()

        async with RedisCachingTest("redis_caching_test") as test:
            await test.test_high_throughput_caching_workflow()

    async def test_multi_database_migration_workflow(self):
        """Test complex multi-database migration with PostgreSQL and Redis."""

        class MultiDatabaseMigrationTest(AsyncWorkflowTestCase):
            async def setUp(self):
                await super().setUp()

                # Set up PostgreSQL source
                self.source_db = await AsyncWorkflowFixtures.create_test_database(
                    engine="postgresql",
                    database="source_db",
                    user="source_user",
                    password="source_pass",
                )

                # Set up PostgreSQL target
                self.target_db = await AsyncWorkflowFixtures.create_test_database(
                    engine="postgresql",
                    database="target_db",
                    user="target_user",
                    password="target_pass",
                )

                import asyncpg

                import docker

                # Connect to databases
                self.source_conn = await asyncpg.connect(
                    self.source_db.connection_string
                )
                self.target_conn = await asyncpg.connect(
                    self.target_db.connection_string
                )

                # Set up Redis for caching
                client = docker.from_env()
                self.redis_container = client.containers.run(
                    "redis:7-alpine",
                    ports={"6379/tcp": None},
                    detach=True,
                    remove=False,
                )

                self.redis_container.reload()
                redis_port = int(self.redis_container.ports["6379/tcp"][0]["HostPort"])
                await asyncio.sleep(2)

                import aioredis

                self.redis_client = aioredis.from_url(f"redis://localhost:{redis_port}")

                # Register resources
                await self.create_test_resource("source_db", lambda: self.source_conn)
                await self.create_test_resource("target_db", lambda: self.target_conn)
                await self.create_test_resource("cache", lambda: self.redis_client)

                # Set up source data
                await self._setup_migration_data()

            async def _setup_migration_data(self):
                """Set up complex source data for migration."""
                # Create source schema
                await self.source_conn.execute(
                    """
                    CREATE TABLE users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(50) UNIQUE,
                        email VARCHAR(100),
                        profile_data JSONB,
                        created_at TIMESTAMP DEFAULT NOW(),
                        last_login TIMESTAMP
                    )
                """
                )

                await self.source_conn.execute(
                    """
                    CREATE TABLE user_activities (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id),
                        activity_type VARCHAR(50),
                        activity_data JSONB,
                        timestamp TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                # Create target schema with different structure
                await self.target_conn.execute(
                    """
                    CREATE TABLE migrated_users (
                        user_id INTEGER PRIMARY KEY,
                        username VARCHAR(50),
                        email VARCHAR(100),
                        profile_summary TEXT,
                        account_status VARCHAR(20),
                        migration_timestamp TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                await self.target_conn.execute(
                    """
                    CREATE TABLE user_engagement_summary (
                        user_id INTEGER,
                        total_activities INTEGER,
                        activity_types TEXT[],
                        first_activity TIMESTAMP,
                        last_activity TIMESTAMP,
                        engagement_score DECIMAL(5,2),
                        migration_timestamp TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                # Insert test data
                users_data = [
                    (
                        "alice_dev",
                        "alice@dev.com",
                        '{"role": "developer", "skills": ["python", "sql"], "level": "senior"}',
                    ),
                    (
                        "bob_manager",
                        "bob@mgmt.com",
                        '{"role": "manager", "team": "engineering", "reports": 5}',
                    ),
                    (
                        "charlie_analyst",
                        "charlie@data.com",
                        '{"role": "analyst", "tools": ["excel", "python"], "certified": true}',
                    ),
                    (
                        "diana_designer",
                        "diana@design.com",
                        '{"role": "designer", "portfolio": "https://diana.design", "awards": 2}',
                    ),
                    (
                        "eve_intern",
                        "eve@intern.com",
                        '{"role": "intern", "school": "Tech University", "graduation": "2025"}',
                    ),
                ]

                for username, email, profile in users_data:
                    await self.source_conn.execute(
                        "INSERT INTO users (username, email, profile_data) VALUES ($1, $2, $3)",
                        username,
                        email,
                        profile,
                    )

                # Insert activities
                activities = [
                    (1, "login", '{"ip": "192.168.1.1", "device": "laptop"}'),
                    (1, "code_commit", '{"repo": "main_app", "lines": 150}'),
                    (1, "code_review", '{"reviewed": 3, "approved": 2}'),
                    (2, "meeting", '{"type": "standup", "duration": 30}'),
                    (2, "approval", '{"document": "budget_2024", "amount": 50000}'),
                    (3, "report_generated", '{"type": "weekly", "format": "pdf"}'),
                    (3, "data_analysis", '{"dataset": "sales_q4", "insights": 12}'),
                    (4, "design_upload", '{"file": "new_logo.svg", "version": "v2.1"}'),
                    (
                        4,
                        "client_presentation",
                        '{"client": "TechCorp", "feedback": "positive"}',
                    ),
                    (
                        5,
                        "training_completed",
                        '{"course": "Python Basics", "score": 85}',
                    ),
                ]

                for user_id, activity_type, activity_data in activities:
                    await self.source_conn.execute(
                        "INSERT INTO user_activities (user_id, activity_type, activity_data) VALUES ($1, $2, $3)",
                        user_id,
                        activity_type,
                        activity_data,
                    )

            async def test_complex_migration_pipeline(self):
                """Test complex multi-database migration with transformations."""
                workflow = (
                    AsyncWorkflowBuilder("multi_db_migration")
                    .add_async_code(
                        "extract_source_data",
                        """
# Extract and enrich data from source database
import json

source_db = await get_resource("source_db")
cache = await get_resource("cache")

# Extract users with activity aggregation
user_query = '''
    SELECT
        u.id,
        u.username,
        u.email,
        u.profile_data,
        u.created_at,
        COUNT(ua.id) as activity_count,
        ARRAY_AGG(DISTINCT ua.activity_type) as activity_types,
        MIN(ua.timestamp) as first_activity,
        MAX(ua.timestamp) as last_activity
    FROM users u
    LEFT JOIN user_activities ua ON u.id = ua.user_id
    GROUP BY u.id, u.username, u.email, u.profile_data, u.created_at
    ORDER BY u.id
'''

users = await source_db.fetch(user_query)

# Cache user data for potential rollback
enriched_users = []
for user in users:
    user_dict = dict(user)
    user_dict['profile_data'] = dict(user_dict['profile_data']) if user_dict['profile_data'] else {}
    enriched_users.append(user_dict)

    # Cache individual user data
    cache_key = f"migration:user:{user_dict['id']}"
    await cache.setex(cache_key, 3600, json.dumps(user_dict, default=str))

# Cache the full dataset
await cache.setex("migration:users:backup", 3600, json.dumps(enriched_users, default=str))

result = {
    "users": enriched_users,
    "extracted_count": len(enriched_users),
    "cached_backup": True
}
""",
                    )
                    .add_async_code(
                        "transform_for_target",
                        """
# Transform data for target schema
import json
from datetime import datetime

cache = await get_resource("cache")
transformed_users = []
engagement_summaries = []

for user in users:
    # Transform user data
    profile = user['profile_data']

    # Create profile summary
    role = profile.get('role', 'unknown')
    if role == 'developer':
        skills = ', '.join(profile.get('skills', []))
        summary = f"Developer with skills: {skills}"
    elif role == 'manager':
        team = profile.get('team', 'unknown')
        reports = profile.get('reports', 0)
        summary = f"Manager of {team} team with {reports} reports"
    elif role == 'analyst':
        tools = ', '.join(profile.get('tools', []))
        certified = "certified" if profile.get('certified') else "not certified"
        summary = f"Analyst using {tools}, {certified}"
    elif role == 'designer':
        awards = profile.get('awards', 0)
        summary = f"Designer with {awards} awards"
    else:
        summary = f"Role: {role}"

    # Determine account status based on activity
    activity_count = user['activity_count'] or 0
    if activity_count >= 5:
        status = 'highly_active'
    elif activity_count >= 2:
        status = 'active'
    elif activity_count >= 1:
        status = 'low_activity'
    else:
        status = 'inactive'

    transformed_user = {
        'user_id': user['id'],
        'username': user['username'],
        'email': user['email'],
        'profile_summary': summary,
        'account_status': status
    }
    transformed_users.append(transformed_user)

    # Create engagement summary
    engagement_score = min(100.0, activity_count * 15.0)  # Cap at 100

    engagement = {
        'user_id': user['id'],
        'total_activities': activity_count,
        'activity_types': user['activity_types'] or [],
        'first_activity': user['first_activity'],
        'last_activity': user['last_activity'],
        'engagement_score': engagement_score
    }
    engagement_summaries.append(engagement)

# Cache transformed data
await cache.setex("migration:transformed_users", 3600, json.dumps(transformed_users, default=str))
await cache.setex("migration:engagement_summaries", 3600, json.dumps(engagement_summaries, default=str))

result = {
    "transformed_users": transformed_users,
    "engagement_summaries": engagement_summaries,
    "transformation_stats": {
        "total_users": len(transformed_users),
        "highly_active": len([u for u in transformed_users if u['account_status'] == 'highly_active']),
        "active": len([u for u in transformed_users if u['account_status'] == 'active']),
        "low_activity": len([u for u in transformed_users if u['account_status'] == 'low_activity']),
        "inactive": len([u for u in transformed_users if u['account_status'] == 'inactive'])
    }
}
""",
                    )
                    .add_async_code(
                        "load_to_target",
                        """
# Load transformed data to target database with validation
import asyncio

target_db = await get_resource("target_db")
cache = await get_resource("cache")

# Begin transaction for atomicity
async with target_db.transaction():
    # Load users
    users_loaded = 0
    for user in transformed_users:
        await target_db.execute('''
            INSERT INTO migrated_users (user_id, username, email, profile_summary, account_status)
            VALUES ($1, $2, $3, $4, $5)
        ''',
        user['user_id'],
        user['username'],
        user['email'],
        user['profile_summary'],
        user['account_status']
        )
        users_loaded += 1

    # Load engagement summaries
    engagement_loaded = 0
    for engagement in engagement_summaries:
        await target_db.execute('''
            INSERT INTO user_engagement_summary
            (user_id, total_activities, activity_types, first_activity, last_activity, engagement_score)
            VALUES ($1, $2, $3, $4, $5, $6)
        ''',
        engagement['user_id'],
        engagement['total_activities'],
        engagement['activity_types'],
        engagement['first_activity'],
        engagement['last_activity'],
        engagement['engagement_score']
        )
        engagement_loaded += 1

# Validate migration
validation_query = '''
    SELECT
        COUNT(*) as user_count,
        COUNT(DISTINCT account_status) as status_types,
        AVG(u.user_id) as avg_user_id,
        AVG(e.engagement_score) as avg_engagement
    FROM migrated_users u
    JOIN user_engagement_summary e ON u.user_id = e.user_id
'''

validation_result = dict(await target_db.fetchrow(validation_query))

# Cache migration results
migration_summary = {
    "users_loaded": users_loaded,
    "engagement_loaded": engagement_loaded,
    "validation": validation_result,
    "migration_timestamp": datetime.now().isoformat()
}

await cache.setex("migration:summary", 3600, json.dumps(migration_summary, default=str))

result = {
    "load_status": "success",
    "users_migrated": users_loaded,
    "engagement_records": engagement_loaded,
    "validation_results": validation_result,
    "data_integrity_check": {
        "users_match": users_loaded == len(transformed_users),
        "engagement_match": engagement_loaded == len(engagement_summaries),
        "all_users_have_engagement": validation_result['user_count'] == users_loaded
    }
}
""",
                    )
                    .add_connection(
                        "extract_source_data", "users", "transform_for_target", "users"
                    )
                    .add_connection(
                        "transform_for_target",
                        "transformed_users",
                        "load_to_target",
                        "transformed_users",
                    )
                    .add_connection(
                        "transform_for_target",
                        "engagement_summaries",
                        "load_to_target",
                        "engagement_summaries",
                    )
                    .build()
                )

                # Execute migration with timeout
                async with self.assert_time_limit(45.0):
                    result = await self.execute_workflow(workflow, {})

                # Comprehensive migration validation
                self.assert_workflow_success(result)

                # Verify extraction
                extract_output = result.get_output("extract_source_data")
                assert extract_output["extracted_count"] == 5, "Should extract 5 users"
                assert extract_output["cached_backup"], "Should cache backup"

                # Verify transformation
                transform_output = result.get_output("transform_for_target")
                stats = transform_output["transformation_stats"]
                assert stats["total_users"] == 5, "Should transform all users"
                assert (
                    stats["highly_active"]
                    + stats["active"]
                    + stats["low_activity"]
                    + stats["inactive"]
                    == 5
                )

                # Verify loading
                load_output = result.get_output("load_to_target")
                assert (
                    load_output["load_status"] == "success"
                ), "Migration should succeed"
                assert load_output["users_migrated"] == 5, "Should migrate all users"
                assert (
                    load_output["engagement_records"] == 5
                ), "Should create engagement records"

                # Data integrity checks
                integrity = load_output["data_integrity_check"]
                assert integrity["users_match"], "User counts should match"
                assert integrity["engagement_match"], "Engagement counts should match"
                assert integrity[
                    "all_users_have_engagement"
                ], "All users should have engagement data"

                # Validation results
                validation = load_output["validation_results"]
                assert validation["user_count"] == 5, "Should have 5 users in target"
                assert (
                    validation["avg_engagement"] > 0
                ), "Should have positive engagement scores"

            async def tearDown(self):
                """Clean up all database resources."""
                if hasattr(self, "source_conn"):
                    await self.source_conn.close()
                if hasattr(self, "target_conn"):
                    await self.target_conn.close()
                if hasattr(self, "redis_client"):
                    await self.redis_client.aclose()
                if hasattr(self, "source_db"):
                    await self.source_db.cleanup()
                if hasattr(self, "target_db"):
                    await self.target_db.cleanup()
                if hasattr(self, "redis_container"):
                    self.redis_container.stop()
                    self.redis_container.remove()
                await super().tearDown()

        async with MultiDatabaseMigrationTest("multi_db_migration_test") as test:
            await test.test_complex_migration_pipeline()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
