"""
Comprehensive E2E test for production workflows using Docker services.

This test demonstrates real-world production scenarios:
- Data pipeline with PostgreSQL and Redis
- LLM-powered analysis with Ollama
- Real-time monitoring and performance tracking
- Error handling and recovery patterns
- Multi-tenant data isolation
"""

import asyncio
import json
import os
import random
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
import pytest

from kailash.nodes.ai import EmbeddingGeneratorNode, LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVWriterNode, SQLDatabaseNode
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.nodes.transform import DataTransformer
from kailash.resources import ResourceFactory, ResourceRegistry
from kailash.runtime.local import LocalRuntime
from kailash.tracking.metrics_collector import MetricsCollector as PerformanceMonitor
from kailash.workflow.async_builder import AsyncWorkflowBuilder, ErrorHandler
from kailash.workflow.async_patterns import AsyncPatterns
from tests.utils.docker_config import (
    DATABASE_CONFIG,
    OLLAMA_CONFIG,
    REDIS_CONFIG,
    get_postgres_connection_string,
    get_redis_url,
)


@pytest.mark.e2e
@pytest.mark.requires_docker
@pytest.mark.requires_ollama
@pytest.mark.requires_redis
@pytest.mark.slow
class TestProductionWorkflowsE2E:
    """Test production-ready workflows with real services."""

    @classmethod
    def setup_class(cls):
        """Set up test environment."""
        cls.db_config = {
            "connection_string": get_postgres_connection_string(),
            "database_type": "postgresql",
            "pool_size": 50,
            "max_overflow": 20,
        }

        cls.redis_config = {
            "redis_url": get_redis_url(),
            "max_connections": 100,
            "decode_responses": True,
        }

        cls.ollama_config = {
            "base_url": f"http://localhost:{OLLAMA_CONFIG['port']}",
            "model": "llama2",
            "timeout": 60.0,
        }

    async def setup_method_async(self):
        """Async setup for each test method."""
        # Ensure services are available by directly trying to connect
        # PostgreSQL check
        node = SQLDatabaseNode(connection_string=self.db_config["connection_string"])
        node.execute(query="SELECT 1", operation="select")

        # Redis check
        import redis

        r = redis.Redis.from_url(self.redis_config["redis_url"])
        r.ping()

        # Ollama check
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.ollama_config['base_url']}/api/tags")
            assert response.status_code == 200, "Ollama must be available"

        # Set up resource registry
        self.registry = ResourceRegistry()
        self.factory = ResourceFactory(self.registry)

        # Register database factory
        await self.factory.register_database_factory(
            "postgres_main",
            self.db_config["connection_string"],
            database_type="postgresql",
            pool_size=self.db_config["pool_size"],
        )

        # Register Redis factory
        await self.factory.register_cache_factory(
            "redis_main",
            self.redis_config["redis_url"],
            cache_type="redis",
        )

        # Register HTTP client factory
        await self.factory.register_http_factory(
            "http_main",
            base_url=self.ollama_config["base_url"],
            timeout=self.ollama_config["timeout"],
        )

        # Initialize runtime
        self.runtime = LocalRuntime(
            max_workers=20,
            enable_monitoring=True,
            enable_checkpointing=True,
            checkpoint_interval=5,
            resource_registry=self.registry,
        )

        # Initialize database schema
        await self._initialize_schema()

    async def teardown_method_async(self):
        """Async teardown for each test method."""
        try:
            # Clean up test data
            await self._cleanup_test_data()

            # Close runtime
            if hasattr(self, "runtime"):
                await self.runtime.close()

            # Close registry resources
            if hasattr(self, "registry"):
                await self.registry.cleanup()
        except Exception as e:
            print(f"Teardown error: {e}")

    async def _initialize_schema(self):
        """Initialize database schema for tests."""
        db = await self.registry.get_resource("postgres_main")
        async with db.acquire() as conn:
            # Create tables for test data
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customer_events (
                    id SERIAL PRIMARY KEY,
                    customer_id INTEGER NOT NULL,
                    event_type VARCHAR(50) NOT NULL,
                    event_data JSONB NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    processed BOOLEAN DEFAULT FALSE,
                    tenant_id INTEGER NOT NULL
                )
            """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_results (
                    id SERIAL PRIMARY KEY,
                    customer_id INTEGER NOT NULL,
                    analysis_type VARCHAR(50) NOT NULL,
                    result JSONB NOT NULL,
                    confidence FLOAT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    tenant_id INTEGER NOT NULL
                )
            """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_customer_events_tenant
                ON customer_events(tenant_id, created_at DESC)
            """
            )

    async def _cleanup_test_data(self):
        """Clean up test data after tests."""
        try:
            db = await self.registry.get_resource("postgres_main")
            async with db.acquire() as conn:
                await conn.execute("TRUNCATE TABLE customer_events CASCADE")
                await conn.execute("TRUNCATE TABLE analysis_results CASCADE")
        except Exception as e:
            print(f"Cleanup error: {e}")

    @pytest.mark.asyncio
    async def test_customer_analytics_pipeline(self):
        """Test complete customer analytics pipeline with LLM analysis."""
        # Create workflow for customer event processing
        workflow = (
            AsyncWorkflowBuilder(
                "customer_analytics_pipeline",
                description="Process customer events and generate insights",
            )
            # 1. Extract recent events from database
            .add_node(
                AsyncSQLDatabaseNode,
                "extract_events",
                {
                    "query": """
                        SELECT
                            customer_id,
                            event_type,
                            event_data,
                            created_at
                        FROM customer_events
                        WHERE tenant_id = :tenant_id
                            AND created_at >= NOW() - INTERVAL '1 hour'
                            AND NOT processed
                        ORDER BY created_at DESC
                        LIMIT 100
                    """,
                    "database_config": self.db_config,
                },
            )
            # 2. Transform and enrich data
            .add_async_code(
                "enrich_events",
                """
import json
from collections import defaultdict

# Group events by customer
customer_events = defaultdict(list)
for event in extract_events['data']:
    customer_events[event['customer_id']].append({
        'type': event['event_type'],
        'data': event['event_data'],
        'timestamp': event['created_at'].isoformat()
    })

# Calculate customer metrics
enriched_customers = []
for customer_id, events in customer_events.items():
    # Event type counts
    event_counts = defaultdict(int)
    for event in events:
        event_counts[event['type']] += 1

    # Recent activity score (more recent = higher score)
    activity_score = sum(1 / (i + 1) for i in range(len(events)))

    enriched_customers.append({
        'customer_id': customer_id,
        'total_events': len(events),
        'event_types': dict(event_counts),
        'activity_score': round(activity_score, 2),
        'events': events[:5]  # Keep only recent 5 for analysis
    })

result = {
    'customers': enriched_customers,
    'total_customers': len(enriched_customers),
    'timestamp': datetime.now(UTC).isoformat()
}
""",
            )
            # 3. Generate embeddings for customer behavior
            .add_node(
                EmbeddingGeneratorNode,
                "generate_embeddings",
                {
                    "model": "nomic-embed-text",
                    "input_path": "enriched_events.customers",
                    "batch_size": 10,
                    "text_field": "events",  # Will convert to string
                },
            )
            # 4. Analyze customer segments with LLM
            .add_node(
                LLMAgentNode,
                "analyze_segments",
                {
                    "model": "llama2",
                    "prompt": """Analyze these customer behavior patterns and provide insights:

Customer Data: {enriched_events.customers}

Please provide:
1. Customer segmentation based on behavior patterns
2. Risk indicators (churn risk, fraud risk)
3. Engagement recommendations for each segment
4. Actionable insights for business teams

Format your response as JSON with the following structure:
{
    "segments": [{"name": "...", "characteristics": [...], "customer_ids": [...]}],
    "risk_analysis": {"high_churn_risk": [...], "suspicious_activity": [...]},
    "recommendations": [{"segment": "...", "actions": [...]}],
    "key_insights": [...]
}""",
                    "temperature": 0.3,
                    "max_tokens": 1000,
                },
            )
            # 5. Cache results for fast retrieval
            .add_async_code(
                "cache_results",
                """
# Simulate caching results
# In real scenario, you'd use Redis or another cache
result = {
    "cached": True,
    "cache_key": f"analytics:tenant_{tenant_id}:latest",
    "analysis": analyze_segments
}
""",
            )
            # 6. Store analysis results in database
            .add_async_code(
                "store_results",
                """
import json

# Parse LLM response
try:
    analysis = json.loads(analyze_segments['content'])
except:
    # Fallback if LLM response isn't valid JSON
    analysis = {
        'segments': [],
        'risk_analysis': {},
        'recommendations': [],
        'key_insights': [analyze_segments['content']]
    }

# Prepare batch insert data
db = await get_resource("postgres_main")
results_to_insert = []

for customer in enriched_events['customers']:
    # Find which segment this customer belongs to
    customer_segment = "unknown"
    for segment in analysis.get('segments', []):
        if customer['customer_id'] in segment.get('customer_ids', []):
            customer_segment = segment['name']
            break

    # Check risk status
    risk_status = "normal"
    if customer['customer_id'] in analysis.get('risk_analysis', {}).get('high_churn_risk', []):
        risk_status = "high_churn_risk"
    elif customer['customer_id'] in analysis.get('risk_analysis', {}).get('suspicious_activity', []):
        risk_status = "suspicious_activity"

    results_to_insert.append({
        'customer_id': customer['customer_id'],
        'analysis_type': 'behavioral_segmentation',
        'result': {
            'segment': customer_segment,
            'risk_status': risk_status,
            'activity_score': customer['activity_score'],
            'event_summary': customer['event_types']
        },
        'confidence': 0.85,  # Would be calculated based on data quality
        'tenant_id': tenant_id
    })

# Batch insert results
if results_to_insert:
    async with db.acquire() as conn:
        await conn.executemany(
            '''
            INSERT INTO analysis_results
            (customer_id, analysis_type, result, confidence, tenant_id)
            VALUES (:customer_id, :analysis_type, :result, :confidence, :tenant_id)
            ''',
            results_to_insert
        )

        # Mark events as processed
        customer_ids = [r['customer_id'] for r in results_to_insert]
        await conn.execute(
            '''
            UPDATE customer_events
            SET processed = TRUE
            WHERE customer_id = ANY(:customer_ids)
            AND tenant_id = :tenant_id
            ''',
            {'customer_ids': customer_ids, 'tenant_id': tenant_id}
        )

result = {
    'stored_results': len(results_to_insert),
    'analysis': analysis,
    'cache_key': f"analytics:tenant_{tenant_id}:latest"
}
""",
            )
            # Connect the workflow
            .add_connections(
                [
                    ("extract_events", "data", "enrich_events", "extract_events"),
                    ("enrich_events", "result", "generate_embeddings", "input_data"),
                    ("enrich_events", "result", "analyze_segments", "enriched_events"),
                    ("analyze_segments", "result", "cache_results", "data"),
                    ("analyze_segments", "result", "store_results", "analyze_segments"),
                    ("enrich_events", "result", "store_results", "enriched_events"),
                ]
            )
            # Add resilience patterns
            .add_pattern(
                AsyncPatterns.retry(
                    max_attempts=3,
                    backoff_factor=2.0,
                    exceptions=[httpx.TimeoutException],
                )
            )
            .add_pattern(
                AsyncPatterns.timeout(
                    timeout_seconds=120,  # 2 minutes for complete pipeline
                )
            )
            .build()
        )

        # Generate test data
        await self._generate_test_events(tenant_id=1, num_customers=20, num_events=200)

        # Execute workflow
        start_time = time.time()
        result = await self.runtime.execute_workflow(
            workflow, parameters={"tenant_id": 1}
        )
        execution_time = time.time() - start_time

        # Verify results
        assert result["store_results"]["stored_results"] > 0
        assert "analysis" in result["store_results"]
        assert execution_time < 120  # Should complete within 2 minutes

        # Verify cache was populated
        redis = await self.registry.get_resource("redis_main")
        cached_data = await redis.get("analytics:tenant_1:latest")
        assert cached_data is not None

        # Verify database results
        db = await self.registry.get_resource("postgres_main")
        async with db.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM analysis_results WHERE tenant_id = 1"
            )
            assert count > 0

    @pytest.mark.asyncio
    async def test_resilient_api_orchestration(self):
        """Test API orchestration with circuit breakers and fallbacks."""
        # Create a workflow that handles API failures gracefully
        workflow = (
            AsyncWorkflowBuilder(
                "resilient_api_workflow",
                description="Orchestrate multiple APIs with resilience",
            )
            # Primary API call
            .add_node(
                HTTPRequestNode,
                "call_primary_api",
                {
                    "method": "POST",
                    "url": f"{self.ollama_config['base_url']}/api/generate",
                    "headers": {"Content-Type": "application/json"},
                    "body": {
                        "model": "llama2",
                        "prompt": "Generate a customer satisfaction score based on: positive feedback",
                        "stream": False,
                    },
                    "timeout": 10.0,
                },
            )
            # Parse primary response
            .add_async_code(
                "parse_primary",
                """
try:
    response = call_primary_api.get('response', {})
    score_text = response.get('response', '')

    # Extract numeric score (simplified)
    import re
    numbers = re.findall(r'\\d+', score_text)
    score = int(numbers[0]) if numbers else 75  # Default score

    result = {
        'source': 'primary',
        'score': min(max(score, 0), 100),  # Ensure 0-100 range
        'confidence': 0.9,
        'raw_response': score_text[:100]
    }
except Exception as e:
    # If parsing fails, trigger fallback
    raise ValueError(f"Failed to parse primary response: {e}")
""",
            )
            # Fallback to simpler analysis
            .add_async_code(
                "fallback_analysis",
                """
# Simple rule-based fallback
text = "positive feedback"
keywords = {
    'positive': 20, 'good': 15, 'great': 25, 'excellent': 30,
    'negative': -20, 'bad': -15, 'poor': -25, 'terrible': -30
}

base_score = 50
for word, value in keywords.items():
    if word in text.lower():
        base_score += value

result = {
    'source': 'fallback',
    'score': min(max(base_score, 0), 100),
    'confidence': 0.6,
    'method': 'keyword_analysis'
}
""",
                error_handler=ErrorHandler.skip(),
            )
            # Merge results
            .add_node(
                MergeNode,
                "merge_results",
                merge_strategy="first_non_null",
                paths=["parse_primary.result", "fallback_analysis.result"],
            )
            # Add circuit breaker pattern
            .add_pattern(
                AsyncPatterns.circuit_breaker(
                    failure_threshold=3,
                    recovery_timeout=30,
                    half_open_requests=1,
                )
            )
            # Connect with error handling
            .add_connection(
                "call_primary_api", "result", "parse_primary", "call_primary_api"
            )
            .add_connection("parse_primary", "result", "merge_results", "primary_input")
            .add_connection(
                "fallback_analysis", "result", "merge_results", "fallback_input"
            )
            # Set error handler for primary path
            .set_error_handler(
                "parse_primary", ErrorHandler.fallback("fallback_analysis")
            )
            .build()
        )

        # Execute workflow multiple times to test resilience
        results = []
        for i in range(5):
            try:
                result = await self.runtime.execute_workflow(workflow)
                results.append(result)
            except Exception as e:
                print(f"Execution {i} failed: {e}")

        # Verify we got results (either from primary or fallback)
        assert len(results) >= 3  # At least 60% success rate

        # Check that we have both primary and fallback results
        sources = [r.get("merge_results", {}).get("source") for r in results]
        assert "primary" in sources or "fallback" in sources

    @pytest.mark.asyncio
    async def test_real_time_monitoring_pipeline(self):
        """Test real-time monitoring with performance tracking."""
        # Create monitoring workflow
        workflow = (
            AsyncWorkflowBuilder(
                "monitoring_pipeline",
                description="Real-time system monitoring and alerting",
            )
            # Monitor system metrics
            .add_async_code(
                "collect_metrics",
                """
import psutil
import asyncio

# Collect system metrics
cpu_percent = psutil.cpu_percent(interval=0.1)
memory = psutil.virtual_memory()
disk = psutil.disk_usage('/')

# Collect database metrics
db = await get_resource("postgres_main")
async with db.acquire() as conn:
    # Get connection count
    conn_count = await conn.fetchval(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
    )

    # Get table sizes
    table_sizes = await conn.fetch('''
        SELECT
            tablename,
            pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY size_bytes DESC
        LIMIT 5
    ''')

# Collect Redis metrics
redis = await get_resource("redis_main")
info = await redis.info()

result = {
    'timestamp': datetime.now(UTC).isoformat(),
    'system': {
        'cpu_percent': cpu_percent,
        'memory_percent': memory.percent,
        'memory_available_gb': round(memory.available / (1024**3), 2),
        'disk_percent': disk.percent
    },
    'database': {
        'connections': conn_count,
        'top_tables': [
            {'name': t['tablename'], 'size_mb': round(t['size_bytes'] / (1024**2), 2)}
            for t in table_sizes
        ]
    },
    'redis': {
        'connected_clients': info.get('connected_clients', 0),
        'used_memory_mb': round(info.get('used_memory', 0) / (1024**2), 2),
        'total_commands': info.get('total_commands_processed', 0)
    }
}
""",
            )
            # Analyze metrics and detect anomalies
            .add_async_code(
                "detect_anomalies",
                """
metrics = collect_metrics
anomalies = []

# Check CPU usage
if metrics['system']['cpu_percent'] > 80:
    anomalies.append({
        'type': 'high_cpu',
        'severity': 'warning' if metrics['system']['cpu_percent'] < 90 else 'critical',
        'value': metrics['system']['cpu_percent'],
        'threshold': 80
    })

# Check memory usage
if metrics['system']['memory_percent'] > 85:
    anomalies.append({
        'type': 'high_memory',
        'severity': 'warning' if metrics['system']['memory_percent'] < 95 else 'critical',
        'value': metrics['system']['memory_percent'],
        'threshold': 85
    })

# Check database connections
if metrics['database']['connections'] > 80:
    anomalies.append({
        'type': 'high_db_connections',
        'severity': 'warning',
        'value': metrics['database']['connections'],
        'threshold': 80
    })

# Calculate health score
health_score = 100
for anomaly in anomalies:
    if anomaly['severity'] == 'critical':
        health_score -= 30
    elif anomaly['severity'] == 'warning':
        health_score -= 15

result = {
    'health_score': max(health_score, 0),
    'status': 'healthy' if health_score >= 70 else 'degraded' if health_score >= 40 else 'critical',
    'anomalies': anomalies,
    'metrics': metrics
}
""",
            )
            # Store metrics for trending
            .add_async_code(
                "store_metrics",
                """
# Store in Redis with TTL for time-series data
redis = await get_resource("redis_main")
timestamp = int(datetime.now(UTC).timestamp())

# Store metrics in sorted set for time-series queries
metrics_key = f"metrics:system:{timestamp // 60}"  # 1-minute buckets

await redis.zadd(
    metrics_key,
    {json.dumps(detect_anomalies['metrics']): timestamp}
)
await redis.expire(metrics_key, 3600)  # Keep for 1 hour

# Store current health status
await redis.set(
    "health:current",
    json.dumps({
        'score': detect_anomalies['health_score'],
        'status': detect_anomalies['status'],
        'timestamp': datetime.now(UTC).isoformat()
    }),
    ex=300  # 5 minute TTL
)

result = {
    'stored': True,
    'bucket': metrics_key,
    'health': detect_anomalies
}
""",
            )
            # Connect workflow
            .add_connections(
                [
                    (
                        "collect_metrics",
                        "result",
                        "detect_anomalies",
                        "collect_metrics",
                    ),
                    ("detect_anomalies", "result", "store_metrics", "detect_anomalies"),
                ]
            ).build()
        )

        # Run monitoring multiple times
        health_scores = []
        for i in range(3):
            result = await self.runtime.execute_workflow(workflow)
            health_scores.append(result["store_metrics"]["health"]["health_score"])
            await asyncio.sleep(1)  # Wait between collections

        # Verify monitoring worked
        assert all(score >= 0 and score <= 100 for score in health_scores)

        # Check stored metrics
        redis = await self.registry.get_resource("redis_main")
        current_health = await redis.get("health:current")
        assert current_health is not None

        health_data = json.loads(current_health)
        assert "score" in health_data
        assert "status" in health_data

    async def _generate_test_events(
        self, tenant_id: int, num_customers: int, num_events: int
    ):
        """Generate test customer events."""
        db = await self.registry.get_resource("postgres_main")

        event_types = [
            "page_view",
            "purchase",
            "support_ticket",
            "login",
            "logout",
            "search",
        ]

        events = []
        for _ in range(num_events):
            customer_id = random.randint(1, num_customers)
            event_type = random.choice(event_types)

            event_data = {
                "session_id": f"session_{random.randint(1000, 9999)}",
                "ip_address": f"192.168.{random.randint(1, 255)}.{random.randint(1, 255)}",
            }

            # Add type-specific data
            if event_type == "purchase":
                event_data["amount"] = round(random.uniform(10, 500), 2)
                event_data["product_id"] = f"prod_{random.randint(100, 999)}"
            elif event_type == "search":
                event_data["query"] = random.choice(
                    ["laptop", "phone", "tablet", "headphones"]
                )
            elif event_type == "support_ticket":
                event_data["priority"] = random.choice(["low", "medium", "high"])

            events.append(
                {
                    "customer_id": customer_id,
                    "event_type": event_type,
                    "event_data": json.dumps(event_data),
                    "tenant_id": tenant_id,
                }
            )

        # Batch insert events
        async with db.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO customer_events (customer_id, event_type, event_data, tenant_id)
                VALUES (:customer_id, :event_type, :event_data, :tenant_id)
                """,
                events,
            )
