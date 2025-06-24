"""
Integration tests for AsyncLocalRuntime with real Docker services and Ollama.

Tests end-to-end workflows using:
- Real PostgreSQL database via Docker
- Real Redis cache via Docker
- Real Ollama LLM service
- Actual file operations
- Network requests to real services
"""

import asyncio
import csv
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

import pytest
import pytest_asyncio

# Check Redis availability
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    try:
        import aioredis

        REDIS_AVAILABLE = True
    except ImportError:
        REDIS_AVAILABLE = False

# Check Ollama availability
try:
    import requests

    response = requests.get("http://localhost:11435/api/tags", timeout=1)
    OLLAMA_AVAILABLE = response.status_code == 200
except:
    OLLAMA_AVAILABLE = False

from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.code import AsyncPythonCodeNode
from kailash.nodes.data import CSVReaderNode
from kailash.resources import (
    CacheFactory,
    DatabasePoolFactory,
    HttpClientFactory,
    ResourceRegistry,
)
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow import AsyncWorkflowBuilder


@pytest_asyncio.fixture(scope="session")
async def docker_services():
    """Setup Docker services for integration testing."""
    # Import docker config to use actual running services
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from utils.docker_config import (
        DATABASE_CONFIG,
        OLLAMA_CONFIG,
        REDIS_CONFIG,
        ensure_docker_services,
    )

    # Docker services are running, verified manually

    services = {
        "postgres": {
            "host": DATABASE_CONFIG["host"],
            "port": DATABASE_CONFIG["port"],
            "database": DATABASE_CONFIG["database"],
            "user": DATABASE_CONFIG["user"],
            "password": DATABASE_CONFIG["password"],
        },
        "redis": {"host": REDIS_CONFIG["host"], "port": REDIS_CONFIG["port"], "db": 0},
        "ollama": {
            "host": OLLAMA_CONFIG["host"],
            "port": OLLAMA_CONFIG["port"],
            "model": "llama2",
        },
    }

    yield services


@pytest_asyncio.fixture
async def resource_registry(docker_services):
    """Create resource registry with real Docker services."""
    registry = ResourceRegistry(enable_metrics=True)

    # Real PostgreSQL connection
    registry.register_factory(
        "postgres_db",
        DatabasePoolFactory(
            backend="postgresql",
            host=docker_services["postgres"]["host"],
            port=docker_services["postgres"]["port"],
            database=docker_services["postgres"]["database"],
            user=docker_services["postgres"]["user"],
            password=docker_services["postgres"]["password"],
            min_size=2,
            max_size=10,
        ),
    )

    # Real Redis cache or memory fallback
    try:
        registry.register_factory(
            "redis_cache",
            CacheFactory(
                backend="redis",
                host=docker_services["redis"]["host"],
                port=docker_services["redis"]["port"],
                db=docker_services["redis"]["db"],
            ),
        )
    except Exception:
        # Fallback to memory cache if Redis is not available
        registry.register_factory(
            "redis_cache",
            CacheFactory(backend="memory"),
        )

    # HTTP client for external APIs
    registry.register_factory(
        "http_client",
        HttpClientFactory(base_url="https://jsonplaceholder.typicode.com", timeout=30),
    )

    # Ollama HTTP client
    registry.register_factory(
        "ollama_client",
        HttpClientFactory(
            base_url=f"http://{docker_services['ollama']['host']}:{docker_services['ollama']['port']}",
            timeout=60,
        ),
    )

    return registry


@pytest.fixture
def test_data_files():
    """Create test data files for integration testing."""
    temp_dir = tempfile.mkdtemp()

    # Create test CSV file
    csv_file = Path(temp_dir) / "test_data.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "email", "age", "city"])
        writer.writerows(
            [
                [1, "Alice Johnson", "alice@example.com", 28, "New York"],
                [2, "Bob Smith", "bob@example.com", 35, "Los Angeles"],
                [3, "Carol Brown", "carol@example.com", 42, "Chicago"],
                [4, "David Wilson", "david@example.com", 31, "Houston"],
                [5, "Eva Davis", "eva@example.com", 26, "Phoenix"],
            ]
        )

    # Create JSON test data
    json_file = Path(temp_dir) / "test_config.json"
    with open(json_file, "w") as f:
        json.dump(
            {
                "processing_rules": {
                    "min_age": 25,
                    "required_fields": ["name", "email"],
                    "city_mapping": {"New York": "NYC", "Los Angeles": "LA"},
                },
                "output_format": "enhanced_csv",
            },
            f,
        )

    yield {"csv_file": str(csv_file), "json_file": str(json_file), "temp_dir": temp_dir}

    # Cleanup
    import shutil

    shutil.rmtree(temp_dir)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.requires_redis
@pytest.mark.slow
class TestAsyncRuntimeRealWorld:
    """Integration tests with real services and data."""

    async def test_database_etl_pipeline(self, resource_registry, test_data_files):
        """Test ETL pipeline with real database operations."""
        runtime = AsyncLocalRuntime(
            resource_registry=resource_registry,
            max_concurrent_nodes=5,
            enable_analysis=True,
            enable_profiling=True,
        )

        # Setup database schema
        setup_node = AsyncPythonCodeNode(
            code="""
# Setup test table
db = await get_resource("postgres_db")

async with db.acquire() as conn:
    # Drop table if exists and create new one
    await conn.execute("DROP TABLE IF EXISTS users")
    await conn.execute('''
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            age INTEGER,
            city VARCHAR(50),
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

result = {"table_created": True}
"""
        )

        # Read CSV data
        csv_reader = CSVReaderNode(file_path=test_data_files["csv_file"])

        # Process and validate data
        processor_node = AsyncPythonCodeNode(
            code="""
import re

processed_users = []
for row in data:
    # Validate email
    email_pattern = r'^[\\w\\.-]+@[\\w\\.-]+\\.\\w+$'
    if not re.match(email_pattern, row.get('email', '')):
        continue

    # Validate age
    try:
        age = int(row.get('age', 0))
        if age < 18 or age > 120:
            continue
    except (ValueError, TypeError):
        continue

    # Clean and enhance data
    processed_users.append({
        'name': row['name'].strip(),
        'email': row['email'].lower().strip(),
        'age': age,
        'city': row['city'].strip()
    })

result = {"processed_users": processed_users, "count": len(processed_users)}
"""
        )

        # Insert into database
        db_insert_node = AsyncPythonCodeNode(
            code="""
db = await get_resource("postgres_db")
inserted_count = 0

# Access processed_users from the input
processed_users = input.get("processed_users", [])

async with db.acquire() as conn:
    for user in processed_users:
        try:
            await conn.execute(
                "INSERT INTO users (name, email, age, city) VALUES ($1, $2, $3, $4)",
                user['name'], user['email'], user['age'], user['city']
            )
            inserted_count += 1
        except Exception as e:
            # Skip duplicate emails or other constraint violations
            continue

result = {"inserted_count": inserted_count}
"""
        )

        # Verify data with aggregation
        verification_node = AsyncPythonCodeNode(
            code="""
db = await get_resource("postgres_db")

async with db.acquire() as conn:
    # Get basic counts
    total_count = await conn.fetchval("SELECT COUNT(*) FROM users")

    # Get age statistics
    age_stats = await conn.fetchrow(
        "SELECT AVG(age)::numeric(5,2) as avg_age, MIN(age) as min_age, MAX(age) as max_age FROM users"
    )

    # Get city distribution
    city_dist = await conn.fetch(
        "SELECT city, COUNT(*) as count FROM users GROUP BY city ORDER BY count DESC"
    )

result = {
    "total_users": total_count,
    "age_stats": dict(age_stats),
    "city_distribution": [dict(row) for row in city_dist],
    "verification_complete": True
}
"""
        )

        # Build workflow
        builder = AsyncWorkflowBuilder("database_etl_pipeline")
        builder.add_node(setup_node, "setup")
        builder.add_node(csv_reader, "read_csv")
        builder.add_node(processor_node, "process")
        builder.add_node(db_insert_node, "insert")
        builder.add_node(verification_node, "verify")
        builder.add_connection("setup", "result", "read_csv", "input")
        builder.add_connection("read_csv", "data", "process", "data")
        builder.add_connection("process", "result", "insert", "input")
        builder.add_connection("insert", "result", "verify", "input")
        workflow = builder.build()

        # Execute workflow
        start_time = time.time()
        result = await runtime.execute_workflow_async(workflow, {})
        execution_time = time.time() - start_time

        # Verify results
        assert len(result["errors"]) == 0, f"Workflow had errors: {result['errors']}"

        setup_result = result["results"]["setup"]
        assert setup_result["table_created"] is True

        process_result = result["results"]["process"]
        assert process_result["count"] > 0

        insert_result = result["results"]["insert"]
        assert insert_result["inserted_count"] > 0

        verify_result = result["results"]["verify"]
        assert verify_result["total_users"] == insert_result["inserted_count"]
        assert verify_result["age_stats"]["avg_age"] > 0
        assert len(verify_result["city_distribution"]) > 0

        # Verify performance metrics if available
        if "metrics" in result and hasattr(result["metrics"], "resource_access_count"):
            metrics = result["metrics"]
            if "postgres_db" in metrics.resource_access_count:
                assert (
                    metrics.resource_access_count["postgres_db"] >= 4
                )  # Each node accessed DB

        assert execution_time < 10  # Should complete reasonably quickly

        print(f"ETL Pipeline completed in {execution_time:.2f}s")
        print(f"Processed {verify_result['total_users']} users")
        print(f"Average age: {verify_result['age_stats']['avg_age']}")

        await runtime.cleanup()

    @pytest.mark.requires_redis
    @pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available")
    async def test_api_aggregation_with_caching(self, resource_registry):
        """Test API data aggregation with Redis caching."""
        runtime = AsyncLocalRuntime(
            resource_registry=resource_registry,
            max_concurrent_nodes=4,
            enable_profiling=True,
        )

        # Fetch user data from API
        user_fetcher = AsyncPythonCodeNode(
            code="""
import json

http = await get_resource("http_client")
cache = await get_resource("redis_cache")

# Check cache first
cache_key = f"user_data_{user_id}"
try:
    cached_data = await cache.get(cache_key)
    if cached_data:
        user_data = json.loads(cached_data) if isinstance(cached_data, str) else cached_data
        source = "cache"
    else:
        cached_data = None
except Exception:
    cached_data = None

if not cached_data:
    # Fetch from API
    async with http.get(f"/users/{user_id}") as response:
        if response.status == 200:
            user_data = await response.json()
            # Cache for 5 minutes
            try:
                # Try setex for Redis, fallback to set for memory cache
                if hasattr(cache, 'setex'):
                    await cache.setex(cache_key, 300, json.dumps(user_data))
                else:
                    await cache.set(cache_key, user_data)
            except Exception:
                pass  # Ignore cache errors
            source = "api"
        else:
            user_data = None
            source = "error"

result = {"user_data": user_data, "source": source}
"""
        )

        # Fetch posts for user
        posts_fetcher = AsyncPythonCodeNode(
            code="""
import json

http = await get_resource("http_client")
cache = await get_resource("redis_cache")

cache_key = f"user_posts_{user_id}"
try:
    cached_posts = await cache.get(cache_key)
    if cached_posts:
        posts_data = json.loads(cached_posts) if isinstance(cached_posts, str) else cached_posts
        source = "cache"
    else:
        cached_posts = None
except Exception:
    cached_posts = None

if not cached_posts:
    async with http.get(f"/users/{user_id}/posts") as response:
        if response.status == 200:
            posts_data = await response.json()
            try:
                if hasattr(cache, 'setex'):
                    await cache.setex(cache_key, 300, json.dumps(posts_data))
                else:
                    await cache.set(cache_key, posts_data)
            except Exception:
                pass
            source = "api"
        else:
            posts_data = []
            source = "error"

result = {"posts_data": posts_data, "source": source}
"""
        )

        # Fetch todos for user
        todos_fetcher = AsyncPythonCodeNode(
            code="""
import json

http = await get_resource("http_client")
cache = await get_resource("redis_cache")

cache_key = f"user_todos_{user_id}"
try:
    cached_todos = await cache.get(cache_key)
    if cached_todos:
        todos_data = json.loads(cached_todos) if isinstance(cached_todos, str) else cached_todos
        source = "cache"
    else:
        cached_todos = None
except Exception:
    cached_todos = None

if not cached_todos:
    async with http.get(f"/users/{user_id}/todos") as response:
        if response.status == 200:
            todos_data = await response.json()
            try:
                if hasattr(cache, 'setex'):
                    await cache.setex(cache_key, 300, json.dumps(todos_data))
                else:
                    await cache.set(cache_key, todos_data)
            except Exception:
                pass
            source = "api"
        else:
            todos_data = []
            source = "error"

result = {"todos_data": todos_data, "source": source}
"""
        )

        # Aggregate all data
        aggregator = AsyncPythonCodeNode(
            code="""
# Extract data from results
user_data = user_result.get("user_data", {})
user_source = user_result.get("source", "error")
posts_data = posts_result.get("posts_data", [])
posts_source = posts_result.get("source", "error")
todos_data = todos_result.get("todos_data", [])
todos_source = todos_result.get("source", "error")

# Combine all data sources
profile = {
    "user_info": user_data,
    "content_stats": {
        "total_posts": len(posts_data),
        "total_todos": len(todos_data),
        "completed_todos": len([t for t in todos_data if t.get("completed", False)])
    },
    "data_sources": {
        "user_source": user_source,
        "posts_source": posts_source,
        "todos_source": todos_source
    }
}

# Add some analytics
if posts_data:
    avg_title_length = sum(len(p.get("title", "")) for p in posts_data) / len(posts_data)
    profile["analytics"] = {
        "avg_post_title_length": round(avg_title_length, 2),
        "productivity_score": profile["content_stats"]["completed_todos"] / max(1, profile["content_stats"]["total_todos"]) * 100
    }

result = {"profile": profile}
"""
        )

        # Build workflow - all fetchers run in parallel
        builder = AsyncWorkflowBuilder("api_aggregation")
        builder.add_node(user_fetcher, "fetch_user")
        builder.add_node(posts_fetcher, "fetch_posts")
        builder.add_node(todos_fetcher, "fetch_todos")
        builder.add_node(aggregator, "aggregate")
        # Use single connections with result pass-through
        builder.add_connection("fetch_user", "result", "aggregate", "user_result")
        builder.add_connection("fetch_posts", "result", "aggregate", "posts_result")
        builder.add_connection("fetch_todos", "result", "aggregate", "todos_result")
        workflow = builder.build()

        # Test with different user IDs to verify caching
        for user_id in [1, 2, 1]:  # Second call to user 1 should hit cache
            start_time = time.time()
            result = await runtime.execute_workflow_async(
                workflow, {"user_id": user_id}
            )
            execution_time = time.time() - start_time

            assert len(result["errors"]) == 0

            profile = result["results"]["aggregate"]["profile"]
            assert profile["user_info"] is not None
            assert "content_stats" in profile
            assert "data_sources" in profile

            print(f"User {user_id} profile aggregated in {execution_time:.2f}s")
            print(f"  Sources: {profile['data_sources']}")
            print(f"  Posts: {profile['content_stats']['total_posts']}")
            print(
                f"  Todos: {profile['content_stats']['total_todos']} ({profile['content_stats']['completed_todos']} completed)"
            )

            # Second call to user 1 should be faster due to caching
            if user_id == 1:
                if "first_call_time" not in locals():
                    first_call_time = execution_time
                else:
                    assert execution_time < first_call_time  # Should be faster

        await runtime.cleanup()

    @pytest.mark.requires_ollama
    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    async def test_llm_enhanced_data_processing(
        self, resource_registry, test_data_files
    ):
        """Test data processing enhanced with LLM analysis via Ollama."""
        runtime = AsyncLocalRuntime(
            resource_registry=resource_registry,
            max_concurrent_nodes=3,
            enable_profiling=True,
        )

        # Read and prepare data using async file operations
        data_reader = AsyncPythonCodeNode(
            code=f"""
import aiofiles
import json

# Read CSV data asynchronously
users = []
async with aiofiles.open("{test_data_files['csv_file']}", mode='r') as f:
    content = await f.read()
    lines = content.strip().split('\\n')

    # Parse CSV manually (header + rows)
    if lines:
        # Split headers properly
        headers = [h.strip() for h in lines[0].split(',')]
        for line in lines[1:]:
            # Split values properly
            values = [v.strip() for v in line.split(',')]
            if len(values) == len(headers):
                user = dict(zip(headers, values))
                users.append(user)

result = {{"users": users, "count": len(users)}}
"""
        )

        # Generate synthetic user descriptions using LLM
        llm_enhancer = AsyncPythonCodeNode(
            code="""
import json

ollama = await get_resource("ollama_client")
enhanced_users = []

# Handle case where users might be None due to workflow builder issue
if users is None:
    users = []

# users variable should be available from workflow connection
for user in users:
    # Create prompt for user description
    prompt = f'''Generate a brief professional description for a person with the following details:
Name: {user['name']}
Age: {user['age']}
City: {user['city']}
Email: {user['email']}

Write a 2-3 sentence professional bio that could be used on a company website or LinkedIn profile. Focus on potential expertise areas based on their location and demographics.'''

    try:
        # Call Ollama API
        async with ollama.post("/api/generate", json={
            "model": "llama2",
            "prompt": prompt,
            "stream": False
        }) as response:
            if response.status == 200:
                result_data = await response.json()
                description = result_data.get("response", "").strip()
            else:
                description = f"Professional based in {user['city']} with expertise in their field."
    except Exception as e:
        # Fallback description if LLM fails
        description = f"Experienced professional based in {user['city']}."

    enhanced_user = user.copy()
    enhanced_user['ai_description'] = description
    enhanced_user['enhancement_source'] = 'llm' if 'Professional based in' not in description else 'fallback'
    enhanced_users.append(enhanced_user)

result = {"enhanced_users": enhanced_users, "llm_enhanced_count": len([u for u in enhanced_users if u['enhancement_source'] == 'llm'])}
"""
        )

        # Analyze and categorize enhanced data
        analyzer = AsyncPythonCodeNode(
            code="""
import re
from collections import Counter

# Handle case where enhanced_users might be None
if enhanced_users is None:
    enhanced_users = []

# Analyze enhanced user data
analysis = {
    "total_users": len(enhanced_users),
    "llm_success_rate": sum(1 for u in enhanced_users if u['enhancement_source'] == 'llm') / max(1, len(enhanced_users)) * 100,
    "age_groups": {},
    "city_distribution": {},
    "description_keywords": []
}

# Age group analysis
for user in enhanced_users:
    age = int(user['age'])
    if age < 30:
        age_group = "20s"
    elif age < 40:
        age_group = "30s"
    elif age < 50:
        age_group = "40s"
    else:
        age_group = "50+"

    analysis["age_groups"][age_group] = analysis["age_groups"].get(age_group, 0) + 1

# City analysis
for user in enhanced_users:
    city = user['city']
    analysis["city_distribution"][city] = analysis["city_distribution"].get(city, 0) + 1

# Extract keywords from AI descriptions
all_descriptions = " ".join(u['ai_description'] for u in enhanced_users)
# Simple keyword extraction (in real scenario, might use NLP library)
words = re.findall(r'\\b\\w{4,}\\b', all_descriptions.lower())
common_words = Counter(words).most_common(10)
analysis["description_keywords"] = [{"word": word, "count": count} for word, count in common_words]

result = {"analysis": analysis, "enhanced_users": enhanced_users}
"""
        )

        # Build workflow
        builder = AsyncWorkflowBuilder("llm_processing")
        builder.add_node(data_reader, "read_data")
        builder.add_node(llm_enhancer, "llm_enhance")
        builder.add_node(analyzer, "analyze")
        builder.add_connection("read_data", "result.users", "llm_enhance", "users")
        builder.add_connection(
            "llm_enhance", "result.enhanced_users", "analyze", "enhanced_users"
        )
        workflow = builder.build()

        # Execute workflow
        start_time = time.time()
        result = await runtime.execute_workflow_async(workflow, {})
        execution_time = time.time() - start_time

        # Verify results
        assert len(result["errors"]) == 0

        read_result = result["results"]["read_data"]
        assert read_result["count"] > 0

        enhance_result = result["results"]["llm_enhance"]
        assert len(enhance_result["enhanced_users"]) == read_result["count"]

        analysis_result = result["results"]["analyze"]
        analysis = analysis_result["analysis"]

        assert analysis["total_users"] > 0
        assert 0 <= analysis["llm_success_rate"] <= 100
        assert len(analysis["age_groups"]) > 0
        assert len(analysis["city_distribution"]) > 0

        print(f"LLM Enhancement completed in {execution_time:.2f}s")
        print(f"  Enhanced {analysis['total_users']} users")
        print(f"  LLM success rate: {analysis['llm_success_rate']:.1f}%")
        print(f"  Age groups: {analysis['age_groups']}")
        print(
            f"  Top keywords: {[kw['word'] for kw in analysis['description_keywords'][:5]]}"
        )

        await runtime.cleanup()

    @pytest.mark.requires_redis
    @pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available")
    async def test_real_time_data_pipeline(self, resource_registry, test_data_files):
        """Test real-time data processing pipeline with streaming and caching."""
        runtime = AsyncLocalRuntime(
            resource_registry=resource_registry,
            max_concurrent_nodes=6,
            enable_analysis=True,
            enable_profiling=True,
        )

        # Simulate sensor data ingestion
        sensor_simulator = AsyncPythonCodeNode(
            code="""
import random
import time
import json

# Simulate multiple sensor readings
sensors = ["temp_01", "temp_02", "humidity_01", "pressure_01"]
readings = []

for sensor_id in sensors:
    for i in range(10):  # 10 readings per sensor
        reading = {
            "sensor_id": sensor_id,
            "timestamp": time.time() - (9-i) * 60,  # Last 10 minutes
            "value": random.uniform(15, 35) if "temp" in sensor_id
                    else random.uniform(30, 80) if "humidity" in sensor_id
                    else random.uniform(980, 1020),  # pressure
            "unit": "celsius" if "temp" in sensor_id
                   else "percent" if "humidity" in sensor_id
                   else "hPa"
        }
        readings.append(reading)

result = {"readings": readings, "sensor_count": len(sensors), "total_readings": len(readings)}
"""
        )

        # Process readings in real-time
        processor = AsyncPythonCodeNode(
            code="""
import statistics
from collections import defaultdict

# Initialize readings from input if not provided
if 'readings' not in locals():
    readings = input.get('readings', [])

# Group readings by sensor
sensor_data = defaultdict(list)
for reading in readings:
    sensor_data[reading["sensor_id"]].append(reading)

processed_sensors = {}
anomalies = []

for sensor_id, sensor_readings in sensor_data.items():
    values = [r["value"] for r in sensor_readings]

    # Calculate statistics
    stats = {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0,
        "min": min(values),
        "max": max(values),
        "count": len(values)
    }

    # Detect anomalies (values > 2 standard deviations from mean)
    if stats["stdev"] > 0:
        threshold = 2 * stats["stdev"]
        sensor_anomalies = []
        for reading in sensor_readings:
            if abs(reading["value"] - stats["mean"]) > threshold:
                anomaly = reading.copy()
                anomaly["deviation"] = abs(reading["value"] - stats["mean"])
                sensor_anomalies.append(anomaly)

        if sensor_anomalies:
            anomalies.extend(sensor_anomalies)

    processed_sensors[sensor_id] = {
        "stats": stats,
        "anomaly_count": len([a for a in anomalies if a["sensor_id"] == sensor_id])
    }

result = {
    "processed_sensors": processed_sensors,
    "anomalies": anomalies,
    "total_anomalies": len(anomalies)
}
"""
        )

        # Cache processed data
        cache_updater = AsyncPythonCodeNode(
            code="""
import json
import time

cache = await get_resource("redis_cache")

# Initialize variables from input if not defined
if 'processed_sensors' not in locals():
    processed_sensors = input.get('processed_sensors', {})
if 'anomalies' not in locals():
    anomalies = input.get('anomalies', [])

# Cache sensor statistics
for sensor_id, sensor_info in processed_sensors.items():
    cache_key = f"sensor_stats:{sensor_id}"
    try:
        if hasattr(cache, 'setex'):
            await cache.setex(cache_key, 3600, json.dumps(sensor_info))  # 1 hour TTL
        else:
            await cache.set(cache_key, sensor_info)
    except Exception:
        pass

# Cache anomalies
if anomalies:
    anomaly_key = "recent_anomalies"
    try:
        if hasattr(cache, 'setex'):
            await cache.setex(anomaly_key, 1800, json.dumps(anomalies))  # 30 min TTL
        else:
            await cache.set(anomaly_key, anomalies)
    except Exception:
        pass

# Store aggregated metrics
metrics = {
    "total_sensors": len(processed_sensors),
    "total_anomalies": len(anomalies),
    "last_update": time.time()
}
try:
    if hasattr(cache, 'setex'):
        await cache.setex("sensor_metrics", 3600, json.dumps(metrics))
    else:
        await cache.set("sensor_metrics", metrics)
except Exception:
    pass

result = {"cached_sensors": len(processed_sensors), "cached_anomalies": len(anomalies)}
"""
        )

        # Generate alerts for anomalies
        alert_generator = AsyncPythonCodeNode(
            code="""
# Initialize anomalies from input if not provided
if 'anomalies' not in locals():
    anomalies = input.get('anomalies', [])

alerts = []

for anomaly in anomalies:
    alert = {
        "alert_id": f"anomaly_{anomaly['sensor_id']}_{int(anomaly['timestamp'])}",
        "sensor_id": anomaly["sensor_id"],
        "alert_type": "anomaly_detected",
        "value": anomaly["value"],
        "expected_range": f"{anomaly['value'] - anomaly['deviation']:.2f} - {anomaly['value'] + anomaly['deviation']:.2f}",
        "severity": "high" if anomaly["deviation"] > 5 else "medium",
        "timestamp": anomaly["timestamp"]
    }
    alerts.append(alert)

result = {"alerts": alerts, "high_severity_count": len([a for a in alerts if a["severity"] == "high"])}
"""
        )

        # Store results in database
        db_storage = AsyncPythonCodeNode(
            code="""
# Initialize variables from input if not provided
if 'readings' not in locals():
    readings = input.get('readings', [])
if 'anomalies' not in locals():
    anomalies = input.get('anomalies', [])

db = await get_resource("postgres_db")

# Ensure tables exist
async with db.acquire() as conn:
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id SERIAL PRIMARY KEY,
            sensor_id VARCHAR(50),
            timestamp FLOAT,
            value FLOAT,
            unit VARCHAR(20),
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    await conn.execute('''
        CREATE TABLE IF NOT EXISTS sensor_anomalies (
            id SERIAL PRIMARY KEY,
            sensor_id VARCHAR(50),
            timestamp FLOAT,
            value FLOAT,
            deviation FLOAT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

# Store readings
stored_readings = 0
async with db.acquire() as conn:
    for reading in readings:
        await conn.execute(
            "INSERT INTO sensor_readings (sensor_id, timestamp, value, unit) VALUES ($1, $2, $3, $4)",
            reading["sensor_id"], reading["timestamp"], reading["value"], reading["unit"]
        )
        stored_readings += 1

# Store anomalies
stored_anomalies = 0
async with db.acquire() as conn:
    for anomaly in anomalies:
        await conn.execute(
            "INSERT INTO sensor_anomalies (sensor_id, timestamp, value, deviation) VALUES ($1, $2, $3, $4)",
            anomaly["sensor_id"], anomaly["timestamp"], anomaly["value"], anomaly["deviation"]
        )
        stored_anomalies += 1

result = {"stored_readings": stored_readings, "stored_anomalies": stored_anomalies}
"""
        )

        # Build real-time pipeline
        builder = AsyncWorkflowBuilder("realtime_pipeline")
        builder.add_node(sensor_simulator, "simulate")
        builder.add_node(processor, "process")
        builder.add_node(cache_updater, "cache")
        builder.add_node(alert_generator, "alert")
        builder.add_node(db_storage, "store")
        builder.add_connection("simulate", "result.readings", "process", "readings")
        builder.add_connection(
            "process", "result.processed_sensors", "cache", "processed_sensors"
        )
        builder.add_connection("process", "result.anomalies", "cache", "anomalies")
        builder.add_connection("process", "result.anomalies", "alert", "anomalies")
        builder.add_connection("simulate", "result.readings", "store", "readings")
        builder.add_connection("process", "result.anomalies", "store", "anomalies")
        workflow = builder.build()

        # Execute pipeline
        start_time = time.time()
        result = await runtime.execute_workflow_async(workflow, {})
        execution_time = time.time() - start_time

        # Verify results
        assert len(result["errors"]) == 0

        simulate_result = result["results"]["simulate"]
        assert simulate_result["total_readings"] == 40  # 4 sensors * 10 readings

        process_result = result["results"]["process"]
        assert len(process_result["processed_sensors"]) == 4

        cache_result = result["results"]["cache"]
        assert cache_result["cached_sensors"] == 4

        store_result = result["results"]["store"]
        assert store_result["stored_readings"] == 40

        print(f"Real-time pipeline completed in {execution_time:.2f}s")
        print(
            f"  Processed {simulate_result['total_readings']} readings from {simulate_result['sensor_count']} sensors"
        )
        print(f"  Detected {process_result['total_anomalies']} anomalies")
        print(
            f"  Generated {result['results']['alert']['high_severity_count']} high-severity alerts"
        )

        # Verify performance
        if "metrics" in result and hasattr(result["metrics"], "resource_access_count"):
            metrics = result["metrics"]
            assert metrics.resource_access_count["postgres_db"] >= 2
            # Only check Redis if actually using Redis (not memory cache)
            if "redis_cache" in metrics.resource_access_count:
                assert metrics.resource_access_count["redis_cache"] >= 1
        assert execution_time < 15  # Should complete within reasonable time

        await runtime.cleanup()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "integration"])
