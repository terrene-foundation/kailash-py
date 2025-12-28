"""User flow tests for Enhanced Gateway.

Tests real developer scenarios:
- Data pipeline with multiple resources
- API aggregation workflow
- ML processing pipeline
- Event-driven workflow
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from kailash.client import KailashClient, SyncKailashClient
from kailash.gateway import (
    EnhancedDurableAPIGateway,
    ResourceReference,
    SecretManager,
    WorkflowRequest,
    create_gateway_app,
)
from kailash.resources import ResourceRegistry
from kailash.workflow import AsyncWorkflowBuilder


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace for tests."""
    return tmp_path


@pytest_asyncio.fixture
async def production_gateway():
    """Create production-like gateway setup."""
    registry = ResourceRegistry()
    secret_manager = SecretManager()

    # Store production-like secrets
    await secret_manager.store_secret(
        "prod_db", {"user": "postgres", "password": "postgres"}
    )
    await secret_manager.store_secret(
        "api_keys", {"weather_api": "test_key", "news_api": "test_key"}
    )

    gateway = EnhancedDurableAPIGateway(
        resource_registry=registry,
        secret_manager=secret_manager,
        title="Production Gateway",
        description="Enterprise workflow gateway",
    )

    yield gateway

    await registry.cleanup()


@pytest.mark.e2e
class TestEnhancedGatewayUserFlows:
    """Test real-world developer workflows."""

    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    @pytest.mark.requires_redis
    async def test_data_analyst_pipeline(self, production_gateway):
        """Test: Data analyst building ETL pipeline with gateway."""
        # User story: As a data analyst, I want to:
        # 1. Extract data from multiple databases
        # 2. Transform and aggregate the data
        # 3. Cache results for fast retrieval
        # 4. Export to different formats

        # Build the ETL workflow
        etl_workflow = (
            AsyncWorkflowBuilder("customer_analytics_etl")
            # No with_database/with_cache methods - resources defined in request
            # Extract from multiple sources
            .add_async_code(
                "extract_customers",
                """
db = await get_resource("analytics_db")
async with db.acquire() as conn:
    # Create test data if needed
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            email VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW(),
            total_spent DECIMAL(10,2)
        )
    ''')

    # Insert sample data if empty
    count = await conn.fetchval("SELECT COUNT(*) FROM customers")
    if count == 0:
        await conn.execute('''
            INSERT INTO customers (name, email, total_spent) VALUES
            ('Alice Johnson', 'alice@example.com', 1250.50),
            ('Bob Smith', 'bob@example.com', 3420.75),
            ('Charlie Davis', 'charlie@example.com', 890.20),
            ('Diana Prince', 'diana@example.com', 5670.00),
            ('Eve Wilson', 'eve@example.com', 2340.60)
        ''')

    # Extract customer data
    customers = await conn.fetch('''
        SELECT id, name, email, total_spent,
               EXTRACT(EPOCH FROM created_at) as created_timestamp
        FROM customers
        ORDER BY total_spent DESC
    ''')

    result = {
        "customers": [dict(row) for row in customers],
        "count": len(customers),
        "extraction_time": time.time()
    }
""",
                required_resources=["analytics_db"],
            )
            # Transform and aggregate
            .add_async_code(
                "transform_data",
                """
import statistics

# Calculate analytics
customers_list = customers
total_revenue = sum(float(c['total_spent']) for c in customers_list)
avg_spent = statistics.mean(float(c['total_spent']) for c in customers_list) if customers_list else 0
median_spent = statistics.median(float(c['total_spent']) for c in customers_list) if customers_list else 0

# Segment customers
high_value = [c for c in customers_list if float(c['total_spent']) > 2000]
medium_value = [c for c in customers_list if 1000 <= float(c['total_spent']) <= 2000]
low_value = [c for c in customers_list if float(c['total_spent']) < 1000]

result = {
    "analytics": {
        "total_revenue": total_revenue,
        "average_spent": avg_spent,
        "median_spent": median_spent,
        "total_customers": len(customers_list)
    },
    "segments": {
        "high_value": {
            "count": len(high_value),
            "customers": high_value,
            "percentage": len(high_value) / len(customers_list) * 100 if customers_list else 0
        },
        "medium_value": {
            "count": len(medium_value),
            "customers": medium_value,
            "percentage": len(medium_value) / len(customers_list) * 100 if customers_list else 0
        },
        "low_value": {
            "count": len(low_value),
            "customers": low_value,
            "percentage": len(low_value) / len(customers_list) * 100 if customers_list else 0
        }
    },
    "transform_time": time.time()
}
""",
            )
            # Cache results
            .add_async_code(
                "cache_results",
                """
cache = await get_resource("result_cache")
import json

# Cache the analytics results
cache_key = f"customer_analytics:{int(time.time() // 3600)}"  # Hourly cache
await cache.setex(
    cache_key,
    3600,  # 1 hour TTL
    json.dumps({
        "analytics": analytics,
        "segments": {k: {**v, "customers": len(v["customers"])} for k, v in segments.items()},
        "cached_at": time.time()
    })
)

# Also cache individual segment lists
for segment_name, segment_data in segments.items():
    segment_key = f"segment:{segment_name}:customers"
    await cache.setex(
        segment_key,
        3600,
        json.dumps(segment_data["customers"])
    )

result = {
    "cache_key": cache_key,
    "cached_segments": list(segments.keys()),
    "cache_time": time.time()
}
""",
                required_resources=["result_cache"],
            )
            # Generate export formats
            .add_async_code(
                "generate_exports",
                """
import json
import csv
import io

# Generate JSON export
json_export = json.dumps({
    "generated_at": time.time(),
    "analytics": analytics,
    "segments": segments
}, indent=2)

# Generate CSV export for high-value customers
csv_buffer = io.StringIO()
writer = csv.DictWriter(
    csv_buffer,
    fieldnames=['id', 'name', 'email', 'total_spent']
)
writer.writeheader()
for customer in segments['high_value']['customers']:
    writer.writerow({
        'id': customer['id'],
        'name': customer['name'],
        'email': customer['email'],
        'total_spent': customer['total_spent']
    })

csv_export = csv_buffer.getvalue()

# Generate summary report
summary_report = f'''
Customer Analytics Report
Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}

OVERVIEW
--------
Total Customers: {analytics['total_customers']}
Total Revenue: ${analytics['total_revenue']:,.2f}
Average Spent: ${analytics['average_spent']:,.2f}
Median Spent: ${analytics['median_spent']:,.2f}

CUSTOMER SEGMENTS
-----------------
High Value (>${2000}): {segments['high_value']['count']} customers ({segments['high_value']['percentage']:.1f}%)
Medium Value ($1000-$2000): {segments['medium_value']['count']} customers ({segments['medium_value']['percentage']:.1f}%)
Low Value (<$1000): {segments['low_value']['count']} customers ({segments['low_value']['percentage']:.1f}%)
'''

result = {
    "exports": {
        "json": {"size": len(json_export), "preview": json_export[:200] + "..."},
        "csv": {"size": len(csv_export), "rows": len(segments['high_value']['customers']) + 1},
        "summary": {"size": len(summary_report), "preview": summary_report[:300] + "..."}
    },
    "export_time": time.time()
}
""",
            )
            # Connect the pipeline
            .add_connection(
                "extract_customers", "customers", "transform_data", "customers"
            )
            .add_connection("transform_data", "analytics", "cache_results", "analytics")
            .add_connection("transform_data", "segments", "cache_results", "segments")
            .add_connection(
                "transform_data", "analytics", "generate_exports", "analytics"
            )
            .add_connection(
                "transform_data", "segments", "generate_exports", "segments"
            )
            .build()
        )

        # Register the workflow
        production_gateway.register_workflow(
            "customer_analytics",
            etl_workflow,
            description="Customer analytics ETL pipeline with caching and exports",
        )

        # Execute as a data analyst would
        request = WorkflowRequest(
            inputs={},
            resources={
                "analytics_db": ResourceReference(
                    type="database",
                    config={"host": "localhost", "port": 5433, "database": "postgres"},
                    credentials_ref="prod_db",
                ),
                "result_cache": ResourceReference(
                    type="cache", config={"host": "localhost", "port": 6379}
                ),
            },
            context={
                "user": "data_analyst",
                "purpose": "monthly_report",
                "environment": "production",
            },
        )

        response = await production_gateway.execute_workflow(
            "customer_analytics", request
        )

        # Verify the pipeline worked
        assert response.status == "completed"
        assert response.error is None

        # Check results
        exports = response.result["generate_exports"]["exports"]
        assert "json" in exports
        assert "csv" in exports
        assert "summary" in exports

        # Verify caching worked
        cache_result = response.result["cache_results"]
        assert cache_result["cached_segments"] == [
            "high_value",
            "medium_value",
            "low_value",
        ]

        # Cleanup
        db = await production_gateway.resource_registry.get_resource("analytics_db")
        if db:
            async with db.acquire() as conn:
                await conn.execute("DROP TABLE IF EXISTS customers")

    @pytest.mark.asyncio
    async def test_api_integration_developer(self, production_gateway):
        """Test: Backend developer building API aggregation service."""
        # User story: As a backend developer, I want to:
        # 1. Aggregate data from multiple external APIs
        # 2. Handle rate limiting and retries
        # 3. Cache responses for performance
        # 4. Transform and combine the data

        # Build API aggregation workflow
        api_workflow = (
            AsyncWorkflowBuilder("dashboard_api_aggregator")
            # Resources defined in request
            # Fetch from multiple APIs in parallel
            .add_async_code(
                "fetch_all_data",
                """
http = await get_resource("external_apis")
cache = await get_resource("api_cache")
import json

async def fetch_with_cache(endpoint, cache_key, ttl=300):
    # Check cache first
    cached = await cache.get(cache_key)
    if cached:
        return json.loads(cached)

    # Fetch from API
    try:
        response = await http.get(f"https://jsonplaceholder.typicode.com{endpoint}")
        data = await response.json()

        # Cache the response
        await cache.setex(cache_key, ttl, json.dumps(data))
        return data
    except Exception as e:
        return {"error": str(e), "endpoint": endpoint}

# Fetch different data types in parallel
results = await asyncio.gather(
    fetch_with_cache("/users", "api:users", 600),
    fetch_with_cache("/posts?_limit=10", "api:posts", 300),
    fetch_with_cache("/comments?_limit=20", "api:comments", 300),
    fetch_with_cache("/todos?_limit=15", "api:todos", 300)
)

result = {
    "users": results[0] if isinstance(results[0], list) else [],
    "posts": results[1] if isinstance(results[1], list) else [],
    "comments": results[2] if isinstance(results[2], list) else [],
    "todos": results[3] if isinstance(results[3], list) else [],
    "fetch_time": time.time()
}
""",
                required_resources=["external_apis", "api_cache"],
            )
            # Transform and aggregate
            .add_async_code(
                "aggregate_dashboard",
                """
# Create dashboard data structure
user_map = {u['id']: u for u in users}

# Enrich posts with user info
enriched_posts = []
for post in posts[:5]:  # Top 5 posts
    enriched_post = {
        **post,
        "author": user_map.get(post['userId'], {}).get('name', 'Unknown'),
        "author_email": user_map.get(post['userId'], {}).get('email', '')
    }
    enriched_posts.append(enriched_post)

# Count comments per post
post_comments = {}
for comment in comments:
    post_id = comment.get('postId')
    if post_id:
        post_comments[post_id] = post_comments.get(post_id, 0) + 1

# Add comment counts to posts
for post in enriched_posts:
    post['comment_count'] = post_comments.get(post['id'], 0)

# Get todo statistics
todo_stats = {
    "total": len(todos),
    "completed": len([t for t in todos if t.get('completed', False)]),
    "pending": len([t for t in todos if not t.get('completed', False)])
}

# Create dashboard response
dashboard = {
    "generated_at": time.time(),
    "summary": {
        "total_users": len(users),
        "total_posts": len(posts),
        "total_comments": len(comments),
        "todo_stats": todo_stats
    },
    "recent_posts": enriched_posts,
    "active_users": [
        {
            "id": u['id'],
            "name": u['name'],
            "email": u['email'],
            "post_count": len([p for p in posts if p['userId'] == u['id']])
        }
        for u in users[:3]
    ]
}

result = {"dashboard": dashboard}
""",
            )
            # Add response caching
            .add_async_code(
                "cache_dashboard",
                """
cache = await get_resource("api_cache")
import json

# Cache the complete dashboard
dashboard_key = "dashboard:main"
await cache.setex(
    dashboard_key,
    60,  # 1 minute TTL for dashboard
    json.dumps(dashboard)
)

# Also cache individual components
await cache.setex("dashboard:summary", 300, json.dumps(dashboard["summary"]))
await cache.setex("dashboard:posts", 120, json.dumps(dashboard["recent_posts"]))

result = {
    "cached": True,
    "cache_keys": ["dashboard:main", "dashboard:summary", "dashboard:posts"],
    "ttl": 60
}
""",
                required_resources=["api_cache"],
            )
            # Connect the workflow - pass entire result between nodes
            .add_connection("fetch_all_data", None, "aggregate_dashboard", None)
            .add_connection("aggregate_dashboard", None, "cache_dashboard", None)
            .build()
        )

        # Register workflow
        production_gateway.register_workflow(
            "dashboard_api",
            api_workflow,
            description="API aggregation service for dashboard",
        )

        # Execute like a developer would
        request = WorkflowRequest(
            inputs={},
            resources={
                "external_apis": ResourceReference(
                    type="http_client", config={"timeout": 10}
                ),
                "api_cache": ResourceReference(
                    type="cache", config={"host": "localhost", "port": 6379}
                ),
            },
            context={"request_id": "dash_123", "client": "web_app"},
        )

        response = await production_gateway.execute_workflow("dashboard_api", request)

        # Verify results
        assert response.status == "completed"
        dashboard = response.result["aggregate_dashboard"]["dashboard"]
        assert "summary" in dashboard
        assert "recent_posts" in dashboard
        assert "active_users" in dashboard
        assert len(dashboard["recent_posts"]) <= 5

        # Verify caching
        cache_result = response.result["cache_dashboard"]
        assert cache_result["cached"] is True

    @pytest.mark.asyncio
    @pytest.mark.requires_ollama
    async def test_ml_engineer_pipeline(self, production_gateway, temp_workspace):
        """Test: ML engineer building inference pipeline."""
        # User story: As an ML engineer, I want to:
        # 1. Load data from various sources
        # 2. Preprocess and transform data
        # 3. Run inference using LLM
        # 4. Post-process and store results

        # Create test data file
        test_data = [
            {"id": 1, "text": "The product quality is excellent", "category": None},
            {"id": 2, "text": "Terrible customer service experience", "category": None},
            {"id": 3, "text": "Average product, nothing special", "category": None},
        ]

        data_file = temp_workspace / "sentiment_data.json"
        with open(data_file, "w") as f:
            json.dump(test_data, f)

        # Build ML pipeline
        ml_workflow = (
            AsyncWorkflowBuilder("sentiment_analysis_pipeline")
            # LLM API resource defined in request
            # Load and preprocess data
            .add_async_code(
                "load_data",
                f"""
# Load data from file
import json
with open("{data_file}", 'r') as f:
    raw_data = json.load(f)

# Preprocess text
processed_data = []
for item in raw_data:
    processed_item = {{
        "id": item["id"],
        "original_text": item["text"],
        "processed_text": item["text"].lower().strip(),
        "length": len(item["text"]),
        "word_count": len(item["text"].split())
    }}
    processed_data.append(processed_item)

result = {{
    "data": processed_data,
    "count": len(processed_data),
    "load_time": time.time()
}}
""",
            )
            # Run sentiment analysis with LLM
            .add_async_code(
                "analyze_sentiment",
                """
http = await get_resource("llm_api")
import json

async def analyze_text_sentiment(text):
    prompt = f"Analyze the sentiment of this text and respond with only one word - 'positive', 'negative', or 'neutral': {text}"

    try:
        response = await http.post("/api/generate", json={
            "model": "llama3.2:3b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "max_tokens": 10
            }
        })

        result = await response.json()
        sentiment = result.get('response', '').strip().lower()

        # Normalize response
        if 'positive' in sentiment:
            return 'positive'
        elif 'negative' in sentiment:
            return 'negative'
        else:
            return 'neutral'

    except Exception as e:
        return 'error'

# Analyze all texts
results = []
for item in data:
    sentiment = await analyze_text_sentiment(item["processed_text"])

    result_item = {
        **item,
        "sentiment": sentiment,
        "confidence": 0.85 if sentiment != 'error' else 0.0,
        "analyzed_at": time.time()
    }
    results.append(result_item)

# Calculate statistics
sentiment_counts = {'positive': 0, 'negative': 0, 'neutral': 0, 'error': 0}
for r in results:
    sentiment_counts[r['sentiment']] += 1

result = {
    "analyzed_data": results,
    "statistics": {
        "total": len(results),
        "sentiment_distribution": sentiment_counts,
        "success_rate": (len(results) - sentiment_counts['error']) / len(results) if results else 0
    },
    "analysis_time": time.time()
}
""",
                required_resources=["llm_api"],
                timeout=60,
            )
            # Store results
            .add_async_code(
                "store_results",
                f"""
# Save analysis results
import json

output_file = "{temp_workspace}/sentiment_results.json"
with open(output_file, 'w') as f:
    json.dump({{
        "results": analyzed_data,
        "statistics": statistics,
        "pipeline_metadata": {{
            "version": "1.0",
            "model": "llama3.2:3b",
            "processed_at": time.time()
        }}
    }}, f, indent=2)

# Generate summary report
summary = f'''
Sentiment Analysis Pipeline Results
===================================
Total Texts Analyzed: {{statistics['total']}}
Success Rate: {{statistics['success_rate']:.1%}}

Sentiment Distribution:
- Positive: {{statistics['sentiment_distribution']['positive']}}
- Negative: {{statistics['sentiment_distribution']['negative']}}
- Neutral: {{statistics['sentiment_distribution']['neutral']}}
- Errors: {{statistics['sentiment_distribution']['error']}}

Results saved to: {{output_file}}
'''

result = {{
    "output_file": output_file,
    "summary": summary,
    "store_time": time.time()
}}
""",
            )
            # Connect pipeline
            .add_connection("load_data", "data", "analyze_sentiment", "data")
            .add_connection(
                "analyze_sentiment", "analyzed_data", "store_results", "analyzed_data"
            )
            .add_connection(
                "analyze_sentiment", "statistics", "store_results", "statistics"
            )
            .build()
        )

        # Register workflow
        production_gateway.register_workflow(
            "sentiment_pipeline",
            ml_workflow,
            description="ML sentiment analysis pipeline with LLM",
        )

        # Execute pipeline
        request = WorkflowRequest(
            inputs={},
            resources={
                "llm_api": ResourceReference(type="http_client", config={"timeout": 30})
            },
            context={"experiment_id": "exp_001", "model_version": "llama3.2:3b"},
        )

        response = await production_gateway.execute_workflow(
            "sentiment_pipeline", request
        )

        # Verify results
        assert response.status == "completed"

        # Check output file was created
        output_file = Path(response.result["store_results"]["output_file"])
        assert output_file.exists()

        # Verify results
        with open(output_file) as f:
            results = json.load(f)

        assert "results" in results
        assert "statistics" in results
        assert len(results["results"]) == 3

        # At least some sentiments should be detected
        stats = results["statistics"]["sentiment_distribution"]
        assert (stats["positive"] + stats["negative"] + stats["neutral"]) > 0

    @pytest.mark.asyncio
    async def test_client_sdk_integration(self, production_gateway):
        """Test: Developer using client SDK to interact with gateway."""
        # Register a simple workflow
        workflow = (
            AsyncWorkflowBuilder("sdk_test")
            .add_async_code(
                "process",
                """
result = {
    "input_received": input_data,
    "resource_available": resource_name if 'resource_name' in locals() else None,
    "context": context if 'context' in locals() else {},
    "processed_at": time.time()
}
""",
            )
            .build()
        )

        production_gateway.register_workflow("sdk_test", workflow)

        # Test with sync client
        client = SyncKailashClient("http://localhost:8000")

        # Test resource helpers
        db_ref = client.database(
            host="localhost", database="testdb", credentials_ref="prod_db"
        )

        assert db_ref["type"] == "database"
        assert db_ref["config"]["host"] == "localhost"

        # Test reference syntax
        ref = client.ref("shared_cache")
        assert ref == "@shared_cache"

        # Test async client with context manager
        async with KailashClient("http://localhost:8000") as async_client:
            # Would test real execution here with running gateway
            # For now, just verify client setup
            assert async_client.base_url == "http://localhost:8000"
            assert async_client._session is not None
