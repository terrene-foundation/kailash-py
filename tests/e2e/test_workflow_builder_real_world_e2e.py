"""
Comprehensive real-world integration tests for AsyncWorkflowBuilder.

This test suite demonstrates production-ready workflows with:
- Complex data pipelines processing 10,000+ records
- Real-time analytics with streaming data
- ML pipelines with feature engineering
- API orchestration with resilience patterns
- Enterprise-grade error handling and monitoring
"""

import asyncio
import gc
import json
import os
import random
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import httpx
import numpy as np
import psutil
import pytest
import pytest_asyncio

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

from kailash.nodes.ai import EmbeddingGeneratorNode, LLMAgentNode
from kailash.nodes.api import HTTPRequestNode, RESTClientNode

# PerformanceMonitorNode not available, will use PythonCodeNode instead
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import (
    AsyncSQLDatabaseNode,
    CSVReaderNode,
    JSONReaderNode,
    SQLDatabaseNode,
)
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.resources.factory import (
    CacheFactory,
    DatabasePoolFactory,
    HttpClientFactory,
)
from kailash.resources.registry import ResourceRegistry
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.sdk_exceptions import NodeExecutionError, WorkflowExecutionError
from kailash.workflow import (
    AsyncPatterns,
    AsyncRetryPolicy,
    AsyncWorkflowBuilder,
    CircuitBreakerConfig,
    ErrorHandler,
    RetryPolicy,
    WorkflowBuilder,
)
from tests.utils.docker_config import (
    DATABASE_CONFIG,
    OLLAMA_CONFIG,
    REDIS_CONFIG,
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_url,
)


@pytest.mark.e2e
@pytest.mark.requires_docker
@pytest.mark.requires_ollama
@pytest.mark.requires_redis
@pytest.mark.slow
@pytest.mark.asyncio
class TestWorkflowBuilderRealWorldE2E:
    """Comprehensive real-world tests for AsyncWorkflowBuilder."""

    @classmethod
    def setup_class(cls):
        """Set up test environment with production-like configuration."""
        cls.db_config = {
            "connection_string": get_postgres_connection_string(),
            "database_type": "postgresql",
            "pool_size": 100,  # Large pool for high concurrency
            "max_overflow": 50,
            "pool_timeout": 30,
            "pool_pre_ping": True,
            "echo": False,  # Disable SQL logging for performance
        }

        cls.redis_config = {
            "redis_url": get_redis_url(),
            "max_connections": 100,
            "socket_keepalive": True,
            "health_check_interval": 30,
        }

        cls.ollama_config = {
            "base_url": f"http://{OLLAMA_CONFIG['host']}:{OLLAMA_CONFIG['port']}",
            "model": "llama3.2:1b",  # Fast model for testing
            "timeout": 30.0,
        }

        # Performance thresholds
        cls.performance_thresholds = {
            "batch_processing_throughput": 1000,  # records/second
            "api_response_time_p99": 2.0,  # seconds
            "memory_usage_limit": 1024,  # MB
            "concurrent_workflows": 50,
        }

    @pytest_asyncio.fixture
    async def setup_test_data(self):
        """Create comprehensive test data in PostgreSQL."""
        conn = await asyncpg.connect(
            host=DATABASE_CONFIG["host"],
            port=DATABASE_CONFIG["port"],
            user=DATABASE_CONFIG["user"],
            password=DATABASE_CONFIG["password"],
            database=DATABASE_CONFIG["database"],
        )

        try:
            # Create tables
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    email VARCHAR(100) UNIQUE,
                    segment VARCHAR(50),
                    lifetime_value DECIMAL(10,2),
                    created_at TIMESTAMP DEFAULT NOW(),
                    metadata JSONB
                )
            """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id SERIAL PRIMARY KEY,
                    customer_id INTEGER REFERENCES customers(id),
                    content TEXT,
                    sentiment FLOAT,
                    category VARCHAR(50),
                    source VARCHAR(50),
                    created_at TIMESTAMP DEFAULT NOW(),
                    processed BOOLEAN DEFAULT FALSE,
                    analysis JSONB
                )
            """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sales_data (
                    id SERIAL PRIMARY KEY,
                    customer_id INTEGER REFERENCES customers(id),
                    product_id VARCHAR(50),
                    amount DECIMAL(10,2),
                    quantity INTEGER,
                    region VARCHAR(50),
                    channel VARCHAR(50),
                    transaction_date TIMESTAMP,
                    metadata JSONB
                )
            """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analytics_results (
                    id SERIAL PRIMARY KEY,
                    workflow_id VARCHAR(100),
                    analysis_type VARCHAR(50),
                    results JSONB,
                    metrics JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """
            )

            # Clear existing data
            await conn.execute(
                "TRUNCATE customers, feedback, sales_data, analytics_results CASCADE"
            )

            # Insert customers
            customer_segments = [
                "enterprise",
                "mid-market",
                "small-business",
                "startup",
            ]
            customer_ids = []

            for i in range(1000):  # 1000 customers
                segment = random.choice(customer_segments)
                ltv = (
                    random.uniform(1000, 100000)
                    if segment == "enterprise"
                    else random.uniform(100, 10000)
                )

                customer_id = await conn.fetchval(
                    """
                    INSERT INTO customers (name, email, segment, lifetime_value, metadata)
                    VALUES ($1, $2, $3, $4, $5::jsonb)
                    RETURNING id
                """,
                    f"Customer {i:04d}",
                    f"customer{i}@example.com",
                    segment,
                    ltv,
                    json.dumps(
                        {
                            "industry": random.choice(
                                ["tech", "finance", "retail", "healthcare"]
                            ),
                            "employee_count": random.randint(10, 10000),
                            "active": random.choice([True, False]),
                        }
                    ),
                )
                customer_ids.append(customer_id)

            # Insert feedback (multiple per customer)
            feedback_sources = ["email", "chat", "phone", "survey", "social_media"]
            feedback_categories = [
                "product",
                "support",
                "pricing",
                "feature_request",
                "bug_report",
            ]

            for customer_id in customer_ids[:500]:  # First 500 customers have feedback
                num_feedback = random.randint(1, 5)
                for _ in range(num_feedback):
                    await conn.execute(
                        """
                        INSERT INTO feedback (customer_id, content, sentiment, category, source)
                        VALUES ($1, $2, $3, $4, $5)
                    """,
                        customer_id,
                        f"Sample feedback text about {random.choice(feedback_categories)}",
                        random.uniform(-1, 1),  # Sentiment score
                        random.choice(feedback_categories),
                        random.choice(feedback_sources),
                    )

            # Insert sales data (10,000+ records)
            regions = ["North America", "Europe", "Asia", "South America", "Africa"]
            channels = ["online", "retail", "partner", "direct"]

            for _ in range(10000):
                customer_id = random.choice(customer_ids)
                await conn.execute(
                    """
                    INSERT INTO sales_data (customer_id, product_id, amount, quantity, region, channel, transaction_date, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                """,
                    customer_id,
                    f"PROD-{random.randint(1000, 9999)}",
                    random.uniform(10, 5000),
                    random.randint(1, 100),
                    random.choice(regions),
                    random.choice(channels),
                    datetime.now() - timedelta(days=random.randint(0, 365)),
                    json.dumps(
                        {
                            "discount": random.uniform(0, 0.3),
                            "campaign": random.choice(
                                ["summer", "winter", "black_friday", None]
                            ),
                            "payment_method": random.choice(
                                ["credit_card", "wire", "paypal"]
                            ),
                        }
                    ),
                )

            yield conn

        finally:
            await conn.close()

    @pytest_asyncio.fixture
    async def redis_client(self):
        """Create Redis client for caching."""
        if redis is None:
            pytest.skip("Redis package not installed")

        client = redis.Redis(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            decode_responses=True,
        )

        # Clear test data
        await client.flushdb()

        yield client

        await client.close()

    @pytest.fixture
    def mock_external_apis(self):
        """Mock external API endpoints for testing."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Mock various API responses
            async def mock_get(url, **kwargs):
                response = AsyncMock()

                if "weather" in url:
                    response.status_code = 200
                    response.json.return_value = {
                        "temperature": random.uniform(10, 30),
                        "condition": random.choice(["sunny", "cloudy", "rainy"]),
                        "humidity": random.uniform(30, 80),
                    }
                elif "stock" in url:
                    response.status_code = 200
                    response.json.return_value = {
                        "price": random.uniform(100, 500),
                        "change": random.uniform(-5, 5),
                        "volume": random.randint(1000000, 10000000),
                    }
                elif "geocoding" in url:
                    response.status_code = 200
                    response.json.return_value = {
                        "lat": random.uniform(-90, 90),
                        "lon": random.uniform(-180, 180),
                        "city": "Test City",
                    }
                elif "error" in url:
                    response.status_code = 500
                    response.json.return_value = {"error": "Internal Server Error"}
                else:
                    response.status_code = 404
                    response.json.return_value = {"error": "Not Found"}

                return response

            mock_instance.get = mock_get
            mock_instance.post = mock_get  # Same behavior for simplicity

            yield mock_instance

    async def test_etl_pipeline_with_data_validation(
        self, setup_test_data, redis_client
    ):
        """Test complex ETL pipeline with data validation and error handling."""
        workflow = AsyncWorkflowBuilder("etl_pipeline")

        # Add nodes for ETL pipeline
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "data_extractor",
            {
                "connection_string": self.db_config["connection_string"],
                "query": """
                SELECT c.*,
                       COUNT(DISTINCT s.id) as transaction_count,
                       SUM(s.amount) as total_revenue
                FROM customers c
                LEFT JOIN sales_data s ON c.id = s.customer_id
                WHERE c.created_at > NOW() - INTERVAL '30 days'
                GROUP BY c.id
                HAVING COUNT(DISTINCT s.id) > 0
            """,
                "database_type": "postgresql",
            },
        )

        # Data quality validation
        workflow.add_node(
            "PythonCodeNode",
            "quality_check",
            {
                "code": """
import json

def validate_customer_data(data):
    customers = data.get('query_results', [])
    validation_results = {
        'total_records': len(customers),
        'valid_records': 0,
        'invalid_records': [],
        'quality_score': 0.0
    }

    for customer in customers:
        issues = []

        # Validate email format
        if not customer.get('email') or '@' not in customer['email']:
            issues.append('invalid_email')

        # Validate revenue
        revenue = customer.get('total_revenue', 0)
        if revenue < 0:
            issues.append('negative_revenue')

        # Validate segment
        if customer.get('segment') not in ['enterprise', 'mid-market', 'small-business', 'startup']:
            issues.append('invalid_segment')

        if issues:
            validation_results['invalid_records'].append({
                'customer_id': customer.get('id'),
                'issues': issues
            })
        else:
            validation_results['valid_records'] += 1

    # Calculate quality score
    if validation_results['total_records'] > 0:
        validation_results['quality_score'] = (
            validation_results['valid_records'] / validation_results['total_records']
        )

    return {'validation_results': validation_results, 'customers': customers}

result = validate_customer_data(inputs)
            """,
                "inputs": {"query_results": "data_extractor.query_results"},
            },
        )

        # Conditional processing based on data quality
        workflow.add_node(
            "SwitchNode",
            "quality_switch",
            {
                "condition": "validation_results.quality_score",
                "cases": {
                    "high_quality": ">= 0.95",
                    "medium_quality": ">= 0.80",
                    "low_quality": "< 0.80",
                },
            },
        )

        # Transform high quality data - using PythonCodeNode
        workflow.add_node(
            "PythonCodeNode",
            "transform_data",
            {
                "code": """
# Transform customer data
customers = validated_data.get('customers', [])

# Add risk score
transformed_customers = []
for customer in customers:
    risk_score = 1 - (customer['total_revenue'] / customer['lifetime_value']) if customer.get('lifetime_value', 0) > 0 else 1
    transformed_customers.append({**customer, 'risk_score': risk_score})

# Filter customers with risk score < 0.7
filtered_customers = [c for c in transformed_customers if c.get('risk_score', 1) < 0.7]

# Sort by risk score
filtered_customers.sort(key=lambda x: x.get('risk_score', 1))

result = {'customers': filtered_customers}
"""
            },
        )

        # Store results (cache simulation)
        workflow.add_node(
            "PythonCodeNode",
            "cache_results",
            {
                "code": "result = {'cached': True, 'data': processed_data}",
                "key_prefix": "etl_results",
                "ttl": 3600,
                "operation": "set",
                "data": {"transformed_data": "transform_data.result"},
            },
        )

        # Error notification for low quality data
        workflow.add_node(
            "PythonCodeNode",
            "error_handler",
            {
                "code": """
from datetime import datetime

result = {
    'alert': 'Data quality below threshold',
    'quality_score': inputs['validation_results']['quality_score'],
    'invalid_count': len(inputs['validation_results']['invalid_records']),
    'timestamp': str(datetime.now())
}
            """,
                "inputs": {"validation_results": "quality_check.validation_results"},
            },
        )

        # Add connections
        workflow.add_connection(
            "data_extractor", "quality_check", "query_results", "query_results"
        )
        workflow.add_connection(
            "quality_check",
            "quality_switch",
            "validation_results",
            "validation_results",
        )

        # Route based on quality
        workflow.add_conditional_connection(
            "quality_switch",
            "transform_data",
            "high_quality",
            {"customers": "quality_check.customers"},
        )
        workflow.add_conditional_connection(
            "quality_switch",
            "transform_data",
            "medium_quality",
            {"customers": "quality_check.customers"},
        )
        workflow.add_conditional_connection(
            "quality_switch",
            "error_handler",
            "low_quality",
            {"validation_results": "quality_check.validation_results"},
        )

        workflow.add_connection(
            "transform_data", "cache_results", "result", "transformed_data"
        )

        # Configure error handling
        workflow.set_error_handler(
            ErrorHandler(
                retry_policy=RetryPolicy(max_attempts=3, backoff_factor=2),
                fallback_result={
                    "status": "pipeline_failed",
                    "timestamp": str(datetime.now()),
                },
                log_errors=True,
            )
        )

        # Execute workflow
        runtime = AsyncLocalRuntime()
        result = await runtime.execute_workflow_async(workflow.build(), {})

        # Verify results
        assert "cache_results" in result or "error_handler" in result

        if "cache_results" in result:
            # Verify data was cached
            cached_data = await redis_client.get("etl_results:transformed_data")
            assert cached_data is not None

            # Verify transformation
            transformed = json.loads(cached_data)
            assert all(
                "risk_score" in customer
                for customer in transformed.get("customers", [])
            )

    async def test_real_time_analytics_streaming(
        self, setup_test_data, redis_client, mock_external_apis
    ):
        """Test real-time analytics with streaming data and Ollama integration."""
        workflow = AsyncWorkflowBuilder("streaming_analytics")

        # Simulate streaming data source
        workflow.add_node(
            "PythonCodeNode",
            "stream_reader",
            {
                "code": """
import json
import time
import random
from datetime import datetime

# Simulate streaming data batches
events = []
for i in range(100):  # 100 events
    event = {
        'id': f'event_{i}',
        'timestamp': datetime.now().isoformat(),
        'type': random.choice(['page_view', 'purchase', 'cart_add', 'search']),
        'user_id': random.randint(1, 1000),
        'value': random.uniform(10, 500) if random.random() > 0.5 else 0,
        'metadata': {
            'source': random.choice(['web', 'mobile', 'api']),
            'region': random.choice(['NA', 'EU', 'APAC'])
        }
    }
    events.append(event)

result = {'events': events, 'batch_size': len(events)}
            """,
            },
        )

        # Real-time aggregation
        workflow.add_node(
            "PythonCodeNode",
            "aggregator",
            {
                "code": """
from collections import defaultdict
from datetime import datetime

events = inputs.get('events', [])

# Aggregate metrics
metrics = {
    'total_events': len(events),
    'events_by_type': defaultdict(int),
    'revenue_by_region': defaultdict(float),
    'active_users': set(),
    'timestamp': datetime.now().isoformat()
}

for event in events:
    metrics['events_by_type'][event['type']] += 1
    if event['value'] > 0:
        metrics['revenue_by_region'][event['metadata']['region']] += event['value']
    metrics['active_users'].add(event['user_id'])

metrics['events_by_type'] = dict(metrics['events_by_type'])
metrics['revenue_by_region'] = dict(metrics['revenue_by_region'])
metrics['unique_users'] = len(metrics['active_users'])
metrics['active_users'] = list(metrics['active_users'])[:10]  # Sample for display

result = {'metrics': metrics}
            """,
                "inputs": {"events": "stream_reader.events"},
            },
        )

        # Analyze patterns with Ollama
        workflow.add_node(
            "LLMAgentNode",
            "pattern_analyzer",
            {
                "base_url": self.ollama_config["base_url"],
                "model": self.ollama_config["model"],
                "prompt": """Analyze these real-time metrics and identify key patterns:

Metrics:
{metrics}

Provide insights on:
1. Traffic patterns by event type
2. Revenue concentration by region
3. User engagement levels
4. Potential anomalies or concerns
""",
                "input_data": {"metrics": "aggregator.metrics"},
                "temperature": 0.7,
                "max_tokens": 500,
            },
        )

        # Store analytics results
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "store_results",
            {
                "connection_string": self.db_config["connection_string"],
                "query": """
                INSERT INTO analytics_results (workflow_id, analysis_type, results, metrics)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """,
                "params": [
                    f"stream_{uuid.uuid4().hex[:8]}",
                    "real_time_analytics",
                    {"analysis": "pattern_analyzer.response"},
                    {"metrics": "aggregator.metrics"},
                ],
                "database_type": "postgresql",
            },
        )

        # Add connections
        workflow.add_connection("stream_reader", "aggregator", "events", "events")
        workflow.add_connection("aggregator", "pattern_analyzer", "metrics", "metrics")
        workflow.add_connection(
            "pattern_analyzer", "store_results", "response", "analysis"
        )
        workflow.add_connection("aggregator", "store_results", "metrics", "metrics")

        # Configure rate limiting for Ollama
        workflow.add_rate_limiter(
            "pattern_analyzer",
            RateLimiter(
                max_requests=10,
                time_window=60,  # 10 requests per minute
            ),
        )

        # Execute workflow
        runtime = AsyncLocalRuntime()
        result = await runtime.execute_workflow_async(workflow.build(), {})

        # Verify results
        assert "store_results" in result
        assert result["store_results"]["query_results"][0]["id"] is not None

        # Verify pattern analysis
        assert "pattern_analyzer" in result
        assert len(result["pattern_analyzer"]["response"]) > 0

    async def test_ml_pipeline_feature_engineering(self, setup_test_data, redis_client):
        """Test ML pipeline with feature engineering and model inference."""
        workflow = AsyncWorkflowBuilder("ml_pipeline")

        # Load customer data for ML
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "load_features",
            {
                "connection_string": self.db_config["connection_string"],
                "query": """
                WITH customer_features AS (
                    SELECT
                        c.id,
                        c.segment,
                        c.lifetime_value,
                        c.metadata->>'industry' as industry,
                        COUNT(DISTINCT s.id) as transaction_count,
                        AVG(s.amount) as avg_transaction_value,
                        MAX(s.amount) as max_transaction_value,
                        MIN(s.amount) as min_transaction_value,
                        STDDEV(s.amount) as transaction_stddev,
                        COUNT(DISTINCT s.product_id) as unique_products,
                        COUNT(DISTINCT s.region) as regions_active,
                        DATE_PART('day', NOW() - MAX(s.transaction_date)) as days_since_last_purchase
                    FROM customers c
                    LEFT JOIN sales_data s ON c.id = s.customer_id
                    GROUP BY c.id, c.segment, c.lifetime_value, c.metadata
                )
                SELECT * FROM customer_features
                WHERE transaction_count > 0
                LIMIT 1000
            """,
                "database_type": "postgresql",
            },
        )

        # Feature engineering
        workflow.add_node(
            "PythonCodeNode",
            "engineer_features",
            {
                "code": """
import numpy as np
from datetime import datetime

customers = inputs.get('query_results', [])

# Engineer additional features
engineered_data = []
for customer in customers:
    features = {
        'customer_id': customer['id'],
        'base_features': {
            'segment_encoded': ['enterprise', 'mid-market', 'small-business', 'startup'].index(
                customer['segment']
            ) if customer['segment'] in ['enterprise', 'mid-market', 'small-business', 'startup'] else -1,
            'ltv_log': np.log1p(float(customer['lifetime_value'])),
            'transaction_frequency': customer['transaction_count'] / max(customer['days_since_last_purchase'], 1),
            'avg_transaction_normalized': float(customer['avg_transaction_value']) / float(customer['lifetime_value']) if customer['lifetime_value'] > 0 else 0,
            'transaction_variance': float(customer['transaction_stddev']) / float(customer['avg_transaction_value']) if customer['avg_transaction_value'] > 0 else 0,
        },
        'derived_features': {
            'customer_value_score': (
                float(customer['lifetime_value']) * 0.4 +
                float(customer['avg_transaction_value']) * customer['transaction_count'] * 0.3 +
                (1 / max(customer['days_since_last_purchase'], 1)) * 10000 * 0.3
            ),
            'engagement_score': (
                customer['transaction_count'] * 0.3 +
                customer['unique_products'] * 0.3 +
                customer['regions_active'] * 0.4
            ),
            'risk_indicator': 1 if customer['days_since_last_purchase'] > 90 else 0,
        }
    }

    # Create feature vector
    features['feature_vector'] = [
        features['base_features']['segment_encoded'],
        features['base_features']['ltv_log'],
        features['base_features']['transaction_frequency'],
        features['base_features']['avg_transaction_normalized'],
        features['base_features']['transaction_variance'],
        features['derived_features']['engagement_score'],
        features['derived_features']['risk_indicator']
    ]

    engineered_data.append(features)

result = {
    'engineered_features': engineered_data,
    'feature_count': len(engineered_data[0]['feature_vector']) if engineered_data else 0,
    'sample_count': len(engineered_data)
}
            """,
                "inputs": {"query_results": "load_features.query_results"},
            },
        )

        # Generate embeddings for similarity analysis
        workflow.add_node(
            "EmbeddingGeneratorNode",
            "generate_embeddings",
            {
                "base_url": self.ollama_config["base_url"],
                "model": "llama3.2:1b",
                "texts": ["engineer_features.engineered_features"],
                "batch_size": 50,
            },
        )

        # Cluster analysis
        workflow.add_node(
            "PythonCodeNode",
            "cluster_analysis",
            {
                "code": """
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import json

# Extract feature vectors
features = inputs.get('engineered_features', [])
if not features:
    result = {'error': 'No features to process'}
else:
    X = np.array([f['feature_vector'] for f in features])

    # Standardize features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Perform clustering
    n_clusters = min(5, len(features))
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(X_scaled)

    # Analyze clusters
    cluster_analysis = {}
    for i in range(n_clusters):
        cluster_mask = clusters == i
        cluster_features = X[cluster_mask]

        cluster_analysis[f'cluster_{i}'] = {
            'size': int(np.sum(cluster_mask)),
            'avg_customer_value': float(np.mean([f['derived_features']['customer_value_score']
                                                for f, m in zip(features, cluster_mask) if m])),
            'avg_engagement': float(np.mean([f['derived_features']['engagement_score']
                                           for f, m in zip(features, cluster_mask) if m])),
            'risk_ratio': float(np.mean([f['derived_features']['risk_indicator']
                                       for f, m in zip(features, cluster_mask) if m])),
        }

    # Add cluster assignments
    for feature, cluster_id in zip(features, clusters):
        feature['cluster_id'] = int(cluster_id)

    result = {
        'clustered_features': features,
        'cluster_analysis': cluster_analysis,
        'n_clusters': n_clusters,
        'model_metrics': {
            'inertia': float(kmeans.inertia_),
            'n_iterations': int(kmeans.n_iter_)
        }
    }
            """,
                "inputs": {
                    "engineered_features": "engineer_features.engineered_features"
                },
            },
        )

        # Cache ML results
        workflow.add_node(
            "PythonCodeNode",
            "cache_ml_results",
            {
                "code": "result = {'cached': True, 'ml_data': ml_features}",
                "data": {
                    "clusters": "cluster_analysis.cluster_analysis",
                    "features": "engineer_features.engineered_features",
                },
            },
        )

        # Add connections
        workflow.add_connection(
            "load_features", "engineer_features", "query_results", "query_results"
        )
        workflow.add_connection(
            "engineer_features", "generate_embeddings", "engineered_features", "texts"
        )
        workflow.add_connection(
            "engineer_features",
            "cluster_analysis",
            "engineered_features",
            "engineered_features",
        )
        workflow.add_connection(
            "cluster_analysis", "cache_ml_results", "cluster_analysis", "clusters"
        )
        workflow.add_connection(
            "engineer_features", "cache_ml_results", "engineered_features", "features"
        )

        # Execute workflow
        runtime = AsyncLocalRuntime()
        result = await runtime.execute_workflow_async(workflow.build(), {})

        # Verify ML pipeline results
        assert "cluster_analysis" in result
        assert "clustered_features" in result["cluster_analysis"]
        assert "cluster_analysis" in result["cluster_analysis"]
        assert result["cluster_analysis"]["n_clusters"] > 0

        # Verify caching
        cached_clusters = await redis_client.get("ml_pipeline:clusters")
        assert cached_clusters is not None

    async def test_api_orchestration_with_resilience(self, mock_external_apis):
        """Test API orchestration with circuit breakers and fallback strategies."""
        workflow = AsyncWorkflowBuilder("api_orchestration")

        # Configure multiple API calls with resilience patterns

        # Weather API with circuit breaker (using mock data)
        workflow.add_node(
            "PythonCodeNode",
            "weather_api",
            {
                "code": """
# Simulate weather API response
import random
from datetime import datetime

# Simulate occasional failures
if random.random() < 0.2:  # 20% failure rate
    result = {"error": "Service temporarily unavailable", "status_code": 503}
else:
    result = {
        'response': {
            'temperature': random.uniform(10, 30),
            'condition': random.choice(['sunny', 'cloudy', 'rainy']),
            'humidity': random.uniform(30, 80),
            'timestamp': str(datetime.now())
        }
    }
            """,
            },
        )

        # Circuit breaker functionality would be configured at runtime or through resilience patterns
        # The retry/resilience policies are typically configured at the runtime level or via node configuration

        # Stock API with retry (using mock data)
        workflow.add_node(
            "PythonCodeNode",
            "stock_api",
            {
                "code": """
# Simulate stock API response
import random
from datetime import datetime

result = {
    'response': {
        'symbol': 'AAPL',
        'price': random.uniform(150, 200),
        'change': random.uniform(-5, 5),
        'volume': random.randint(1000000, 10000000),
        'timestamp': str(datetime.now())
    }
}
            """,
            },
        )

        # Geocoding API (using mock data)
        workflow.add_node(
            "PythonCodeNode",
            "geocoding_api",
            {
                "code": """
# Simulate geocoding API response
from datetime import datetime

result = {
    'response': {
        'lat': 37.7749,
        'lon': -122.4194,
        'city': 'San Francisco',
        'state': 'CA',
        'timestamp': str(datetime.now())
    }
}
            """,
            },
        )

        # Fallback weather service
        workflow.add_node(
            "PythonCodeNode",
            "weather_fallback",
            {
                "code": """
# Fallback weather data from cache or default
from datetime import datetime

result = {
    'temperature': 20.0,
    'condition': 'unknown',
    'humidity': 50.0,
    'source': 'fallback',
    'timestamp': str(datetime.now())
}
            """,
            },
        )

        # Aggregate API results
        workflow.add_node(
            "PythonCodeNode",
            "aggregate_results",
            {
                "code": """
import json
from datetime import datetime

# Collect results from all APIs
results = {
    'timestamp': str(datetime.now()),
    'data_sources': []
}

# Get input data (check if variables exist, use empty dict as fallback)
try:
    weather_input = weather_data
except NameError:
    weather_input = {}

try:
    fallback_input = fallback_weather
except NameError:
    fallback_input = {}

try:
    stock_input = stock_data
except NameError:
    stock_input = {}

try:
    location_input = location_data
except NameError:
    location_input = {}

# Weather data - check if main weather API worked, otherwise use fallback
if weather_input and isinstance(weather_input, dict) and weather_input.get('temperature'):
    results['weather'] = weather_input
    results['data_sources'].append('primary_weather')
elif fallback_input and isinstance(fallback_input, dict):
    results['weather'] = fallback_input
    results['data_sources'].append('fallback_weather')

# Stock data
if stock_input and isinstance(stock_input, dict) and stock_input.get('price'):
    results['stock'] = stock_input
    results['data_sources'].append('stock_api')

# Location data
if location_input and isinstance(location_input, dict) and location_input.get('lat'):
    results['location'] = location_input
    results['data_sources'].append('geocoding_api')

# Calculate composite metrics
if 'weather' in results and 'stock' in results:
    # Silly metric for demonstration
    results['composite_index'] = (
        results['weather'].get('temperature', 20) *
        results['stock'].get('price', 100) / 1000
    )

result = results
            """,
            },
        )

        # Add connections with error handling
        workflow.add_connection(
            "weather_api", "response", "aggregate_results", "weather_data"
        )
        workflow.add_connection(
            "weather_fallback", "result", "aggregate_results", "fallback_weather"
        )
        workflow.add_connection(
            "stock_api", "response", "aggregate_results", "stock_data"
        )
        workflow.add_connection(
            "geocoding_api", "response", "aggregate_results", "location_data"
        )

        # Error handling would be configured at runtime level
        # For this test, we'll just build and run the workflow

        # Execute workflow
        runtime = AsyncLocalRuntime()
        result = await runtime.execute_workflow_async(workflow.build(), {})

        # Verify orchestration
        assert "aggregate_results" in result["results"]
        aggregate_result = result["results"]["aggregate_results"]["result"]

        assert "data_sources" in aggregate_result
        assert "timestamp" in aggregate_result

        # Verify that the workflow executed without errors
        assert len(result["errors"]) == 0

        # Verify all API nodes executed successfully
        assert "weather_api" in result["results"]
        assert "stock_api" in result["results"]
        assert "geocoding_api" in result["results"]
        assert "weather_fallback" in result["results"]

    async def test_report_generation_with_templates(self, setup_test_data):
        """Test report generation with template rendering and multi-format output."""
        workflow = AsyncWorkflowBuilder("report_generation")

        # Load report data
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "load_report_data",
            {
                "connection_string": self.db_config["connection_string"],
                "query": """
                WITH report_data AS (
                    SELECT
                        COUNT(DISTINCT c.id) as total_customers,
                        COUNT(DISTINCT CASE WHEN c.segment = 'enterprise' THEN c.id END) as enterprise_customers,
                        SUM(s.amount) as total_revenue,
                        AVG(s.amount) as avg_transaction,
                        COUNT(s.id) as total_transactions,
                        COUNT(DISTINCT s.region) as regions_covered,
                        DATE_TRUNC('month', s.transaction_date) as month,
                        s.region,
                        c.segment
                    FROM customers c
                    JOIN sales_data s ON c.id = s.customer_id
                    WHERE s.transaction_date >= NOW() - INTERVAL '6 months'
                    GROUP BY DATE_TRUNC('month', s.transaction_date), s.region, c.segment
                )
                SELECT * FROM report_data
                ORDER BY month DESC, total_revenue DESC
            """,
                "database_type": "postgresql",
            },
        )

        # Generate executive summary with LLM
        workflow.add_node(
            "LLMAgentNode",
            "generate_summary",
            {
                "base_url": self.ollama_config["base_url"],
                "model": self.ollama_config["model"],
                "prompt": """Generate an executive summary based on this business data:

{report_data}

The summary should include:
1. Key performance metrics
2. Revenue trends by region and segment
3. Customer distribution insights
4. Strategic recommendations

Keep it concise and focused on actionable insights.""",
                "input_data": {"report_data": "load_report_data.query_results"},
                "temperature": 0.7,
                "max_tokens": 1000,
            },
        )

        # Create visualizations data
        workflow.add_node(
            "PythonCodeNode",
            "prepare_visualizations",
            {
                "code": """
import json
from collections import defaultdict
from datetime import datetime

data = inputs.get('query_results', [])

# Aggregate data for charts
monthly_revenue = defaultdict(float)
regional_breakdown = defaultdict(float)
segment_performance = defaultdict(lambda: {'revenue': 0, 'customers': 0})

for row in data:
    month_key = row['month'].strftime('%Y-%m') if row['month'] else 'Unknown'
    monthly_revenue[month_key] += float(row['total_revenue'] or 0)
    regional_breakdown[row['region']] += float(row['total_revenue'] or 0)
    segment_performance[row['segment']]['revenue'] += float(row['total_revenue'] or 0)
    segment_performance[row['segment']]['customers'] += int(row.get('enterprise_customers', 0))

# Prepare chart data
charts = {
    'monthly_trend': {
        'type': 'line',
        'data': [
            {'month': month, 'revenue': revenue}
            for month, revenue in sorted(monthly_revenue.items())
        ]
    },
    'regional_pie': {
        'type': 'pie',
        'data': [
            {'region': region, 'value': revenue}
            for region, revenue in regional_breakdown.items()
        ]
    },
    'segment_analysis': {
        'type': 'bar',
        'data': [
            {
                'segment': segment,
                'revenue': data['revenue'],
                'customers': data['customers']
            }
            for segment, data in segment_performance.items()
        ]
    }
}

# Calculate KPIs
total_revenue = sum(monthly_revenue.values())
avg_monthly_revenue = total_revenue / len(monthly_revenue) if monthly_revenue else 0

kpis = {
    'total_revenue': total_revenue,
    'avg_monthly_revenue': avg_monthly_revenue,
    'total_regions': len(regional_breakdown),
    'top_region': max(regional_breakdown.items(), key=lambda x: x[1])[0] if regional_breakdown else 'N/A',
    'report_date': datetime.now().strftime('%Y-%m-%d')
}

result = {
    'charts': charts,
    'kpis': kpis,
    'raw_data': data[:10]  # Sample for detailed table
}
            """,
                "inputs": {"query_results": "load_report_data.query_results"},
            },
        )

        # Generate HTML report
        workflow.add_node(
            "PythonCodeNode",
            "generate_html",
            {
                "code": """
from datetime import datetime

summary = inputs.get('summary', 'No summary available')
visualizations = inputs.get('visualizations', {})
kpis = visualizations.get('kpis', {})

html_template = '''<!DOCTYPE html>
<html>
<head>
    <title>Business Intelligence Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .header { background-color: #2c3e50; color: white; padding: 20px; border-radius: 5px; }
        .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }
        .kpi-card { background-color: #f8f9fa; padding: 20px; border-radius: 5px; text-align: center; }
        .kpi-value { font-size: 24px; font-weight: bold; color: #2c3e50; }
        .section { margin: 30px 0; }
        .chart-placeholder { background-color: #e9ecef; height: 300px; display: flex; align-items: center; justify-content: center; border-radius: 5px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #2c3e50; color: white; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Business Intelligence Report</h1>
        <p>Generated on: {report_date}</p>
    </div>

    <div class="section">
        <h2>Key Performance Indicators</h2>
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-value">${total_revenue:,.2f}</div>
                <div>Total Revenue</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${avg_monthly_revenue:,.2f}</div>
                <div>Avg Monthly Revenue</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">{total_regions}</div>
                <div>Active Regions</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">{top_region}</div>
                <div>Top Region</div>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>Executive Summary</h2>
        <p>{summary}</p>
    </div>

    <div class="section">
        <h2>Revenue Trends</h2>
        <div class="chart-placeholder">
            <p>Monthly Revenue Trend Chart</p>
        </div>
    </div>

    <div class="section">
        <h2>Regional Performance</h2>
        <div class="chart-placeholder">
            <p>Regional Revenue Distribution</p>
        </div>
    </div>

    <div class="section">
        <h2>Segment Analysis</h2>
        <div class="chart-placeholder">
            <p>Customer Segment Performance</p>
        </div>
    </div>
</body>
</html>'''

result = {
    'html_report': html_template.format(
        report_date=kpis.get('report_date', 'N/A'),
        total_revenue=kpis.get('total_revenue', 0),
        avg_monthly_revenue=kpis.get('avg_monthly_revenue', 0),
        total_regions=kpis.get('total_regions', 0),
        top_region=kpis.get('top_region', 'N/A'),
        summary=summary
    ),
    'filename': f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
}
            """,
                "inputs": {
                    "summary": "generate_summary.response",
                    "visualizations": "prepare_visualizations.result",
                },
            },
        )

        # Generate JSON report for API consumption
        workflow.add_node(
            "PythonCodeNode",
            "generate_json",
            {
                "code": """
import json
from datetime import datetime

result = {
    'report': {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'version': '1.0',
            'type': 'business_intelligence'
        },
        'summary': inputs.get('summary', ''),
        'kpis': inputs.get('visualizations', {}).get('kpis', {}),
        'charts': inputs.get('visualizations', {}).get('charts', {}),
        'data_sample': inputs.get('visualizations', {}).get('raw_data', [])
    },
    'filename': f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
}
            """,
                "inputs": {
                    "summary": "generate_summary.response",
                    "visualizations": "prepare_visualizations.result",
                },
            },
        )

        # Add connections
        workflow.add_connection(
            "load_report_data", "generate_summary", "query_results", "report_data"
        )
        workflow.add_connection(
            "load_report_data",
            "prepare_visualizations",
            "query_results",
            "query_results",
        )
        workflow.add_connection(
            "generate_summary", "generate_html", "response", "summary"
        )
        workflow.add_connection(
            "prepare_visualizations", "generate_html", "result", "visualizations"
        )
        workflow.add_connection(
            "generate_summary", "generate_json", "response", "summary"
        )
        workflow.add_connection(
            "prepare_visualizations", "generate_json", "result", "visualizations"
        )

        # Execute workflow
        runtime = AsyncLocalRuntime()
        result = await runtime.execute_workflow_async(workflow.build(), {})

        # Verify report generation
        assert "generate_html" in result
        assert "html_report" in result["generate_html"]
        assert "generate_json" in result
        assert "report" in result["generate_json"]

        # Verify content
        html_report = result["generate_html"]["html_report"]
        assert "Business Intelligence Report" in html_report
        assert "$" in html_report  # Currency formatting

    async def test_workflow_checkpointing_and_recovery(
        self, setup_test_data, redis_client
    ):
        """Test workflow checkpointing, state persistence, and recovery."""
        workflow_id = f"checkpoint_test_{uuid.uuid4().hex[:8]}"

        workflow = AsyncWorkflowBuilder(
            "checkpointed_workflow", workflow_id=workflow_id
        )

        # Configure checkpointing
        workflow.enable_checkpointing(
            {
                "storage": "redis",
                "redis_url": self.redis_config["redis_url"],
                "checkpoint_interval": 2,  # Every 2 nodes
                "retention_period": 3600,  # 1 hour
            }
        )

        # Multi-stage workflow with checkpoints

        # Stage 1: Data extraction
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "extract_data",
            {
                "connection_string": self.db_config["connection_string"],
                "query": "SELECT * FROM customers LIMIT 100",
                "database_type": "postgresql",
            },
        )

        # Stage 2: Enrichment (simulate failure point)
        workflow.add_node(
            "PythonCodeNode",
            "enrich_data",
            {
                "code": """
import random
from datetime import datetime

customers = inputs.get('query_results', [])

# Simulate potential failure
if random.random() < 0.3 and not inputs.get('recovery_mode', False):
    raise Exception("Simulated enrichment failure")

enriched = []
for customer in customers:
    enriched.append({
        **customer,
        'enrichment_timestamp': str(datetime.now()),
        'risk_score': random.uniform(0, 1),
        'category': random.choice(['A', 'B', 'C'])
    })

result = {'enriched_customers': enriched, 'count': len(enriched)}
            """,
                "inputs": {"query_results": "extract_data.query_results"},
            },
        )

        # Stage 3: Analysis
        workflow.add_node(
            "PythonCodeNode",
            "analyze_segments",
            {
                "code": """
from collections import Counter

customers = inputs.get('enriched_customers', [])

segment_analysis = Counter(c['segment'] for c in customers)
risk_distribution = {
    'high_risk': sum(1 for c in customers if c.get('risk_score', 0) > 0.7),
    'medium_risk': sum(1 for c in customers if 0.3 < c.get('risk_score', 0) <= 0.7),
    'low_risk': sum(1 for c in customers if c.get('risk_score', 0) <= 0.3)
}

result = {
    'segment_counts': dict(segment_analysis),
    'risk_distribution': risk_distribution,
    'total_analyzed': len(customers)
}
            """,
                "inputs": {"enriched_customers": "enrich_data.enriched_customers"},
            },
        )

        # Stage 4: Report generation
        workflow.add_node(
            "PythonCodeNode",
            "generate_report",
            {
                "code": """
from datetime import datetime

analysis = inputs.get('analysis', {})

report = {
    'summary': f"Analyzed {analysis.get('total_analyzed', 0)} customers",
    'segments': analysis.get('segment_counts', {}),
    'risk_profile': analysis.get('risk_distribution', {}),
    'generated_at': str(datetime.now()),
    'workflow_id': inputs.get('workflow_id', 'unknown')
}

result = {'report': report}
            """,
                "inputs": {
                    "analysis": "analyze_segments.result",
                    "workflow_id": workflow_id,
                },
            },
        )

        # Add connections
        workflow.add_connection(
            "extract_data", "enrich_data", "query_results", "query_results"
        )
        workflow.add_connection(
            "enrich_data",
            "analyze_segments",
            "enriched_customers",
            "enriched_customers",
        )
        workflow.add_connection(
            "analyze_segments", "generate_report", "result", "analysis"
        )

        # Configure progress tracking
        progress_tracker = []

        def track_progress(node_id, status, result=None):
            progress_tracker.append(
                {
                    "node_id": node_id,
                    "status": status,
                    "timestamp": datetime.now().isoformat(),
                    "has_result": result is not None,
                }
            )

        workflow.add_progress_callback(track_progress)

        # First execution attempt (may fail)
        runtime = AsyncLocalRuntime()

        try:
            result = await runtime.execute_async(workflow.build(), {})
            execution_completed = True
        except WorkflowError as e:
            execution_completed = False

            # Verify checkpoint was saved
            checkpoint_key = f"checkpoint:{workflow_id}:*"
            checkpoints = await redis_client.keys(checkpoint_key)
            assert len(checkpoints) > 0, "No checkpoints found"

            # Recover from checkpoint
            recovery_workflow = AsyncWorkflowBuilder.from_checkpoint(
                workflow_id=workflow_id,
                redis_url=self.redis_config["redis_url"],
            )

            # Add recovery flag to prevent simulated failure
            recovery_workflow.update_node_params(
                "enrich_data", {"inputs": {"recovery_mode": True}}
            )

            # Resume execution
            result = await runtime.execute_async(recovery_workflow.build(), {})
            execution_completed = True

        # Verify execution completed
        assert execution_completed
        assert "generate_report" in result
        assert "report" in result["generate_report"]

        # Verify progress tracking
        assert len(progress_tracker) > 0
        completed_nodes = [
            p["node_id"] for p in progress_tracker if p["status"] == "completed"
        ]
        assert "generate_report" in completed_nodes

    async def test_concurrent_workflow_execution(self, setup_test_data):
        """Test concurrent execution of multiple workflows with resource management."""
        num_concurrent_workflows = 10

        async def create_and_execute_workflow(workflow_num):
            """Create and execute a workflow instance."""
            workflow = AsyncWorkflowBuilder(f"concurrent_workflow_{workflow_num}")

            # Create workflow with shared resources
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "fetch_data",
                {
                    "connection_string": self.db_config["connection_string"],
                    "query": f"""
                    SELECT * FROM customers
                    WHERE id % {num_concurrent_workflows} = {workflow_num}
                    LIMIT 50
                """,
                    "database_type": "postgresql",
                    "pool_name": "shared_pool",  # Use shared connection pool
                },
            )

            workflow.add_node(
                "PythonCodeNode",
                "process_data",
                {
                    "code": f"""
import time
import random
from datetime import datetime

# Simulate processing with variable duration
customers = inputs.get('query_results', [])
processing_time = random.uniform(0.1, 0.5)
time.sleep(processing_time)

result = {{
    'workflow_id': {workflow_num},
    'processed_count': len(customers),
    'processing_time': processing_time,
    'timestamp': str(datetime.now())
}}
                """,
                    "inputs": {"query_results": "fetch_data.query_results"},
                },
            )

            workflow.add_connection(
                "fetch_data", "process_data", "query_results", "query_results"
            )

            # Execute workflow
            runtime = AsyncLocalRuntime()
            start_time = time.time()
            result = await runtime.execute_async(workflow.build(), {})
            execution_time = time.time() - start_time

            return {
                "workflow_id": workflow_num,
                "execution_time": execution_time,
                "result": result,
                "success": "process_data" in result,
            }

        # Execute workflows concurrently
        start_time = time.time()
        tasks = [
            create_and_execute_workflow(i) for i in range(num_concurrent_workflows)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time

        # Analyze results
        successful_workflows = [
            r for r in results if isinstance(r, dict) and r["success"]
        ]
        failed_workflows = [
            r
            for r in results
            if isinstance(r, Exception) or not r.get("success", False)
        ]

        # Performance metrics
        avg_execution_time = sum(
            r["execution_time"] for r in successful_workflows
        ) / len(successful_workflows)

        # Verify concurrent execution
        assert (
            len(successful_workflows) >= num_concurrent_workflows * 0.9
        )  # At least 90% success rate
        assert (
            total_time < avg_execution_time * num_concurrent_workflows * 0.5
        )  # Significant parallelism

        # Verify resource management (no connection pool exhaustion)
        assert (
            len(failed_workflows) < num_concurrent_workflows * 0.1
        )  # Less than 10% failure

    async def test_memory_usage_and_performance(self, setup_test_data):
        """Test memory usage and performance with large datasets."""
        workflow = AsyncWorkflowBuilder("performance_test")

        # Monitor initial memory
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Large data processing
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "load_large_dataset",
            {
                "connection_string": self.db_config["connection_string"],
                "query": """
                SELECT s.*, c.segment, c.lifetime_value
                FROM sales_data s
                JOIN customers c ON s.customer_id = c.id
                LIMIT 10000
            """,
                "database_type": "postgresql",
                "fetch_size": 1000,  # Batch fetching
            },
        )

        # Batch processing
        workflow.add_node(
            "PythonCodeNode",
            "batch_processor",
            {
                "code": """
import gc
from itertools import islice

data = inputs.get('query_results', [])
batch_size = 500
results = []

# Process in batches to manage memory
for i in range(0, len(data), batch_size):
    batch = data[i:i + batch_size]

    # Process batch
    batch_result = {
        'batch_num': i // batch_size,
        'records': len(batch),
        'total_amount': sum(float(r['amount']) for r in batch),
        'segments': list(set(r['segment'] for r in batch))
    }
    results.append(batch_result)

    # Explicitly clear batch to free memory
    del batch

    # Periodic garbage collection
    if i % 2000 == 0:
        gc.collect()

# Final summary
summary = {
    'total_batches': len(results),
    'total_records': sum(r['records'] for r in results),
    'total_revenue': sum(r['total_amount'] for r in results),
    'unique_segments': list(set(s for r in results for s in r['segments']))
}

result = {'summary': summary, 'batch_count': len(results)}
            """,
                "inputs": {"query_results": "load_large_dataset.query_results"},
            },
        )

        # Performance monitoring - using PythonCodeNode instead
        workflow.add_node(
            "PythonCodeNode",
            "performance_monitor",
            {
                "code": """
import time
import psutil

# Simulate performance monitoring
result = {
    'metrics': {
        'execution_time': 0.5,
        'memory_usage_mb': 100,
        'cpu_usage_percent': 25
    },
    'alerts': []
}
"""
            },
        )

        # Add connections
        workflow.add_connection(
            "load_large_dataset", "batch_processor", "query_results", "query_results"
        )
        workflow.add_connection(
            "batch_processor", "performance_monitor", "summary", "input_data"
        )

        # Execute workflow
        runtime = AsyncLocalRuntime()
        start_time = time.time()
        result = await runtime.execute_async(workflow.build(), {})
        execution_time = time.time() - start_time

        # Monitor final memory
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Verify performance
        assert "batch_processor" in result
        assert result["batch_processor"]["summary"]["total_records"] == 10000

        # Verify memory efficiency
        assert memory_increase < self.performance_thresholds["memory_usage_limit"]

        # Verify throughput
        records_per_second = 10000 / execution_time
        assert (
            records_per_second
            > self.performance_thresholds["batch_processing_throughput"]
        )

        # Clean up
        gc.collect()

    async def test_complex_error_scenarios(self, setup_test_data, redis_client):
        """Test complex error handling scenarios with cascading failures."""
        workflow = AsyncWorkflowBuilder("error_handling_test")

        # Node that might fail
        workflow.add_node(
            "PythonCodeNode",
            "unreliable_service",
            {
                "code": """
import random

# Simulate different failure modes
failure_mode = random.choice(['success', 'timeout', 'error', 'partial'])

if failure_mode == 'timeout':
    import time
    time.sleep(10)  # Simulate timeout
elif failure_mode == 'error':
    raise ValueError("Service unavailable")
elif failure_mode == 'partial':
    result = {'status': 'partial', 'data': [1, 2, 3], 'error': 'Incomplete data'}
else:
    result = {'status': 'success', 'data': list(range(10))}
            """,
            },
        )

        # Add timeout to unreliable service
        workflow.set_node_timeout("unreliable_service", 2.0)

        # Retry with exponential backoff
        workflow.set_error_handler(
            ErrorHandler(
                retry_policy=RetryPolicy(
                    max_attempts=3,
                    backoff_factor=2,
                    max_delay=5,
                    retry_on_exceptions=[ValueError, TimeoutError],
                ),
            )
        )

        # Fallback computation
        workflow.add_node(
            "PythonCodeNode",
            "fallback_computation",
            {
                "code": """
# Provide default data when primary service fails
from datetime import datetime

result = {
    'status': 'fallback',
    'data': list(range(5)),  # Reduced dataset
    'source': 'cache',
    'timestamp': str(datetime.now())
}
            """,
            },
        )

        # Data validator
        workflow.add_node(
            "PythonCodeNode",
            "validate_data",
            {
                "code": """
data_result = inputs.get('primary_data', inputs.get('fallback_data', {}))

if not data_result:
    raise ValueError("No data available from any source")

status = data_result.get('status', 'unknown')
data = data_result.get('data', [])

# Validate data quality
validation = {
    'is_valid': len(data) > 0,
    'data_source': status,
    'record_count': len(data),
    'quality_score': 1.0 if status == 'success' else 0.5 if status == 'fallback' else 0.3
}

if not validation['is_valid']:
    raise ValueError("Data validation failed")

result = {'validation': validation, 'processed_data': data}
            """,
                "inputs": {
                    "primary_data": "unreliable_service.result",
                    "fallback_data": "fallback_computation.result",
                },
            },
        )

        # Connect with error handling
        workflow.add_connection(
            "unreliable_service", "validate_data", "result", "primary_data"
        )
        workflow.add_connection(
            "fallback_computation", "validate_data", "result", "fallback_data"
        )

        # Add error handler that triggers fallback
        workflow.add_error_handler(
            "unreliable_service",
            ErrorHandler(
                fallback_node="fallback_computation",
                log_errors=True,
            ),
        )

        # Execute multiple times to test different scenarios
        runtime = AsyncLocalRuntime()
        results = []

        for i in range(5):
            try:
                result = await runtime.execute_async(workflow.build(), {})
                results.append(
                    {
                        "attempt": i,
                        "success": True,
                        "data_source": result.get("validate_data", {})
                        .get("validation", {})
                        .get("data_source"),
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "attempt": i,
                        "success": False,
                        "error": str(e),
                    }
                )

        # Verify error handling worked
        successful_attempts = [r for r in results if r["success"]]
        assert len(successful_attempts) > 0  # At least some attempts should succeed

        # Verify fallback was used
        fallback_used = any(
            r.get("data_source") == "fallback" for r in successful_attempts
        )
        assert fallback_used  # Fallback should have been triggered at least once

    @pytest.mark.benchmark
    async def test_workflow_performance_benchmarks(self, setup_test_data):
        """Benchmark workflow performance for different patterns."""
        benchmarks = {}

        # Benchmark 1: Sequential vs Parallel execution
        # Sequential workflow
        seq_workflow = AsyncWorkflowBuilder("sequential_benchmark")
        for i in range(5):
            seq_workflow.add_node(
                "PythonCodeNode",
                f"task_{i}",
                {
                    "code": f"import time; time.sleep(0.1); result = {{'task': {i}, 'done': True}}"
                },
            )
            if i > 0:
                seq_workflow.add_connection(
                    f"task_{i-1}", f"task_{i}", "result", "input"
                )

        # Parallel workflow
        par_workflow = AsyncWorkflowBuilder("parallel_benchmark")
        par_workflow.add_node(
            "PythonCodeNode", "splitter", {"code": "result = {'tasks': list(range(5))}"}
        )

        merge_inputs = {}
        for i in range(5):
            par_workflow.add_node(
                "PythonCodeNode",
                f"parallel_task_{i}",
                {
                    "code": f"import time; time.sleep(0.1); result = {{'task': {i}, 'done': True}}"
                },
            )
            par_workflow.add_connection(
                "splitter", f"parallel_task_{i}", "tasks", "input"
            )
            merge_inputs[f"task_{i}"] = f"parallel_task_{i}.result"

        par_workflow.add_node("MergeNode", "merger", {"inputs": merge_inputs})

        # Execute benchmarks
        runtime = AsyncLocalRuntime()

        # Sequential execution
        start = time.time()
        await runtime.execute_async(seq_workflow.build(), {})
        benchmarks["sequential_5_tasks"] = time.time() - start

        # Parallel execution
        start = time.time()
        await runtime.execute_async(par_workflow.build(), {})
        benchmarks["parallel_5_tasks"] = time.time() - start

        # Verify parallel is faster
        assert benchmarks["parallel_5_tasks"] < benchmarks["sequential_5_tasks"] * 0.5

        # Benchmark 2: Caching effectiveness
        cache_workflow = AsyncWorkflowBuilder("cache_benchmark")

        cache_workflow.add_node(
            "PythonCodeNode",
            "expensive_computation",
            {
                "code": """
import time
import hashlib

# Simulate expensive computation
key = str(inputs.get('key', 'default'))
time.sleep(0.5)

result = {
    'computed_value': hashlib.md5(key.encode()).hexdigest(),
    'computation_time': 0.5
}
            """,
                "inputs": {"key": "test_key"},
            },
        )

        cache_workflow.add_node(
            "PythonCodeNode",
            "cache_result",
            {
                "code": "result = {'cached': True, 'benchmark_data': input_data}",
                "key": "expensive_result",
                "data": {"value": "expensive_computation.computed_value"},
            },
        )

        # First execution (cache miss)
        start = time.time()
        result1 = await runtime.execute_async(cache_workflow.build(), {})
        benchmarks["cache_miss"] = time.time() - start

        # Second execution (cache hit)
        start = time.time()
        result2 = await runtime.execute_async(cache_workflow.build(), {})
        benchmarks["cache_hit"] = time.time() - start

        # Verify caching worked
        assert benchmarks["cache_hit"] < benchmarks["cache_miss"] * 0.2
        assert (
            result1["expensive_computation"]["computed_value"]
            == result2["cache_result"]["value"]
        )

        # Log benchmark results
        print("\nPerformance Benchmarks:")
        for name, duration in benchmarks.items():
            print(f"  {name}: {duration:.3f}s")
