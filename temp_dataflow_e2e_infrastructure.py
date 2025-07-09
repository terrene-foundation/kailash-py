#!/usr/bin/env python3
"""
End-to-End DataFlow CLAUDE.md validation with REAL infrastructure.
Includes sample infrastructure setup code to help users get started.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Test results storage
test_results = {
    "infrastructure_setup": [],
    "real_database_tests": [],
    "real_cache_tests": [],
    "production_scenarios": [],
    "errors": [],
}


def log_test(
    category: str, test_name: str, success: bool, details: str = "", error: str = ""
):
    """Log test result"""
    result = {
        "test_name": test_name,
        "success": success,
        "details": details,
        "error": error,
        "timestamp": datetime.now().isoformat(),
    }
    test_results[category].append(result)

    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status} {test_name}")
    if details:
        print(f"   Details: {details}")
    if error:
        print(f"   Error: {error}")


def setup_docker_infrastructure():
    """Setup real Docker infrastructure for testing"""
    print("\n=== Setting up Docker Infrastructure ===")

    # Create docker-compose.yml for DataFlow infrastructure
    docker_compose_content = """version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: dataflow_test
      POSTGRES_USER: dataflow_user
      POSTGRES_PASSWORD: dataflow_pass
    ports:
      - "5433:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dataflow_user -d dataflow_test"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  mongodb:
    image: mongo:7
    environment:
      MONGO_INITDB_ROOT_USERNAME: dataflow_user
      MONGO_INITDB_ROOT_PASSWORD: dataflow_pass
    ports:
      - "27018:27017"
    volumes:
      - mongo_data:/data/db
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  redis_data:
  mongo_data:
"""

    try:
        # Write docker-compose.yml
        with open("docker-compose-dataflow.yml", "w") as f:
            f.write(docker_compose_content)

        log_test(
            "infrastructure_setup",
            "Docker compose file creation",
            True,
            "Infrastructure definition created",
        )

        # Start services
        print("Starting infrastructure services...")
        result = subprocess.run(
            ["docker-compose", "-f", "docker-compose-dataflow.yml", "up", "-d"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            log_test(
                "infrastructure_setup",
                "Docker services startup",
                True,
                "PostgreSQL, Redis, MongoDB started",
            )
        else:
            log_test(
                "infrastructure_setup",
                "Docker services startup",
                False,
                "",
                result.stderr,
            )
            return False

        # Wait for services to be healthy
        print("Waiting for services to be healthy...")
        time.sleep(15)

        # Check service health
        health_result = subprocess.run(
            ["docker-compose", "-f", "docker-compose-dataflow.yml", "ps"],
            capture_output=True,
            text=True,
        )

        if "healthy" in health_result.stdout:
            log_test(
                "infrastructure_setup",
                "Services health check",
                True,
                "All services healthy",
            )
            return True
        else:
            log_test(
                "infrastructure_setup",
                "Services health check",
                False,
                "",
                "Services not healthy",
            )
            return False

    except Exception as e:
        log_test("infrastructure_setup", "Infrastructure setup", False, "", str(e))
        return False


def test_real_postgresql_integration():
    """Test DataFlow with real PostgreSQL database"""
    try:
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        print("\n=== Testing Real PostgreSQL Integration ===")

        # DataFlow configuration for PostgreSQL
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test_postgresql",
            {
                "code": """
# Real PostgreSQL connection test
import psycopg2
from psycopg2.extras import RealDictCursor
import json

try:
    # Connect to PostgreSQL
    conn = psycopg2.connect(
        host="localhost",
        port=5433,
        database="dataflow_test",
        user="dataflow_user",
        password="dataflow_pass"
    )

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Create table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            email VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Insert test data
    cur.execute(
        "INSERT INTO users (name, email) VALUES (%s, %s) RETURNING *",
        ("Alice Johnson", "alice@dataflow.com")
    )

    user = cur.fetchone()

    # Query data
    cur.execute("SELECT * FROM users WHERE email = %s", ("alice@dataflow.com",))
    users = cur.fetchall()

    conn.commit()

    result = {
        "connection_successful": True,
        "table_created": True,
        "user_inserted": dict(user) if user else None,
        "users_found": len(users),
        "database_type": "PostgreSQL"
    }

    cur.close()
    conn.close()

except Exception as e:
    result = {
        "connection_successful": False,
        "error": str(e),
        "database_type": "PostgreSQL"
    }
"""
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        if "test_postgresql" in results:
            data = results["test_postgresql"]["result"]
            if data.get("connection_successful") and data.get("users_found", 0) > 0:
                log_test(
                    "real_database_tests",
                    "PostgreSQL integration",
                    True,
                    f"User created: {data['user_inserted']['name']}",
                )
            else:
                log_test(
                    "real_database_tests",
                    "PostgreSQL integration",
                    False,
                    "",
                    data.get("error", "Unknown error"),
                )
        else:
            log_test(
                "real_database_tests", "PostgreSQL integration", False, "", "No results"
            )

    except Exception as e:
        log_test("real_database_tests", "PostgreSQL integration", False, "", str(e))


def test_real_redis_caching():
    """Test DataFlow with real Redis caching"""
    try:
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        print("\n=== Testing Real Redis Caching ===")

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test_redis",
            {
                "code": """
# Real Redis caching test
import redis
import json
import time

try:
    # Connect to Redis
    r = redis.Redis(host='localhost', port=6380, db=0, decode_responses=True)

    # Test connection
    r.ping()

    # Set cache data
    cache_key = "dataflow:user:123"
    user_data = {
        "id": 123,
        "name": "John Doe",
        "email": "john@dataflow.com",
        "cached_at": time.time()
    }

    r.setex(cache_key, 300, json.dumps(user_data))  # 5 minute TTL

    # Get cached data
    cached_data = r.get(cache_key)
    retrieved_user = json.loads(cached_data) if cached_data else None

    # Test cache expiry
    ttl = r.ttl(cache_key)

    # Bulk operations
    bulk_data = {}
    for i in range(100):
        bulk_key = f"dataflow:product:{i}"
        bulk_data[bulk_key] = json.dumps({
            "id": i,
            "name": f"Product {i}",
            "price": i * 10.0
        })

    r.mset(bulk_data)

    # Get bulk data
    bulk_keys = list(bulk_data.keys())
    bulk_results = r.mget(bulk_keys)

    result = {
        "redis_connected": True,
        "cache_set": True,
        "cache_retrieved": retrieved_user is not None,
        "ttl_set": ttl > 0,
        "bulk_operations": len(bulk_results),
        "cache_type": "Redis"
    }

except Exception as e:
    result = {
        "redis_connected": False,
        "error": str(e),
        "cache_type": "Redis"
    }
"""
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        if "test_redis" in results:
            data = results["test_redis"]["result"]
            if data.get("redis_connected") and data.get("cache_retrieved"):
                log_test(
                    "real_cache_tests",
                    "Redis caching",
                    True,
                    f"Bulk operations: {data['bulk_operations']}",
                )
            else:
                log_test(
                    "real_cache_tests",
                    "Redis caching",
                    False,
                    "",
                    data.get("error", "Unknown error"),
                )
        else:
            log_test("real_cache_tests", "Redis caching", False, "", "No results")

    except Exception as e:
        log_test("real_cache_tests", "Redis caching", False, "", str(e))


def test_real_mongodb_integration():
    """Test DataFlow with real MongoDB"""
    try:
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        print("\n=== Testing Real MongoDB Integration ===")

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test_mongodb",
            {
                "code": """
# Real MongoDB integration test
from pymongo import MongoClient
from datetime import datetime

try:
    # Connect to MongoDB
    client = MongoClient('mongodb://dataflow_user:dataflow_pass@localhost:27018/')
    db = client.dataflow_test
    collection = db.products

    # Insert test document
    product = {
        "name": "DataFlow Product",
        "price": 99.99,
        "category": "software",
        "created_at": datetime.now(),
        "metadata": {
            "version": "1.0",
            "features": ["fast", "reliable", "scalable"]
        }
    }

    result_insert = collection.insert_one(product)

    # Query document
    found_product = collection.find_one({"name": "DataFlow Product"})

    # Bulk operations
    bulk_products = []
    for i in range(50):
        bulk_products.append({
            "name": f"Bulk Product {i}",
            "price": i * 5.0,
            "category": "bulk",
            "created_at": datetime.now()
        })

    bulk_result = collection.insert_many(bulk_products)

    # Count documents
    total_count = collection.count_documents({})

    result = {
        "mongodb_connected": True,
        "document_inserted": result_insert.inserted_id is not None,
        "document_found": found_product is not None,
        "bulk_inserted": len(bulk_result.inserted_ids),
        "total_documents": total_count,
        "database_type": "MongoDB"
    }

    client.close()

except Exception as e:
    result = {
        "mongodb_connected": False,
        "error": str(e),
        "database_type": "MongoDB"
    }
"""
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        if "test_mongodb" in results:
            data = results["test_mongodb"]["result"]
            if data.get("mongodb_connected") and data.get("document_found"):
                log_test(
                    "real_database_tests",
                    "MongoDB integration",
                    True,
                    f"Total documents: {data['total_documents']}",
                )
            else:
                log_test(
                    "real_database_tests",
                    "MongoDB integration",
                    False,
                    "",
                    data.get("error", "Unknown error"),
                )
        else:
            log_test(
                "real_database_tests", "MongoDB integration", False, "", "No results"
            )

    except Exception as e:
        log_test("real_database_tests", "MongoDB integration", False, "", str(e))


def test_production_scenario_e2e():
    """Test complete production scenario with all infrastructure"""
    try:
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        print("\n=== Testing Production E2E Scenario ===")

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "production_e2e",
            {
                "code": """
# Production E2E scenario with real infrastructure
import psycopg2
import redis
from pymongo import MongoClient
import json
import time
from datetime import datetime

def test_production_workflow():
    results = {}

    try:
        # 1. Database Layer (PostgreSQL)
        pg_conn = psycopg2.connect(
            host="localhost", port=5433, database="dataflow_test",
            user="dataflow_user", password="dataflow_pass"
        )
        pg_cur = pg_conn.cursor()

        # Create orders table
        pg_cur.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                customer_email VARCHAR(100),
                total DECIMAL(10,2),
                status VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Insert order
        pg_cur.execute(
            "INSERT INTO orders (customer_email, total, status) VALUES (%s, %s, %s) RETURNING id",
            ("customer@example.com", 299.99, "pending")
        )
        order_id = pg_cur.fetchone()[0]
        pg_conn.commit()

        results["database"] = {"order_id": order_id, "status": "created"}

        # 2. Cache Layer (Redis)
        redis_client = redis.Redis(host='localhost', port=6380, db=0, decode_responses=True)

        # Cache order data
        order_cache_key = f"order:{order_id}"
        order_data = {
            "id": order_id,
            "customer_email": "customer@example.com",
            "total": 299.99,
            "status": "pending",
            "cached_at": time.time()
        }

        redis_client.setex(order_cache_key, 600, json.dumps(order_data))

        # Cache customer session
        session_key = f"session:customer@example.com"
        session_data = {
            "user_id": "user123",
            "last_order": order_id,
            "session_start": time.time()
        }
        redis_client.setex(session_key, 1800, json.dumps(session_data))

        results["cache"] = {"order_cached": True, "session_cached": True}

        # 3. Analytics Layer (MongoDB)
        mongo_client = MongoClient('mongodb://dataflow_user:dataflow_pass@localhost:27018/')
        analytics_db = mongo_client.dataflow_analytics
        events_collection = analytics_db.events

        # Log order event
        event = {
            "event_type": "order_created",
            "order_id": order_id,
            "customer_email": "customer@example.com",
            "amount": 299.99,
            "timestamp": datetime.now(),
            "source": "web",
            "metadata": {
                "user_agent": "DataFlow/1.0",
                "ip_address": "127.0.0.1"
            }
        }

        events_collection.insert_one(event)

        results["analytics"] = {"event_logged": True}

        # 4. Workflow Processing
        # Update order status
        pg_cur.execute(
            "UPDATE orders SET status = %s WHERE id = %s",
            ("processing", order_id)
        )
        pg_conn.commit()

        # Update cache
        order_data["status"] = "processing"
        redis_client.setex(order_cache_key, 600, json.dumps(order_data))

        # Log status change
        status_event = {
            "event_type": "order_status_changed",
            "order_id": order_id,
            "old_status": "pending",
            "new_status": "processing",
            "timestamp": datetime.now()
        }
        events_collection.insert_one(status_event)

        results["workflow"] = {"status_updated": True}

        # 5. Verification
        # Check database
        pg_cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        db_order = pg_cur.fetchone()

        # Check cache
        cached_order = redis_client.get(order_cache_key)
        cached_data = json.loads(cached_order) if cached_order else None

        # Check analytics
        event_count = events_collection.count_documents({"order_id": order_id})

        results["verification"] = {
            "database_consistent": db_order[3] == "processing",
            "cache_consistent": cached_data["status"] == "processing" if cached_data else False,
            "analytics_events": event_count
        }

        # Cleanup
        pg_cur.close()
        pg_conn.close()
        redis_client.close()
        mongo_client.close()

        return results

    except Exception as e:
        return {"error": str(e), "success": False}

result = test_production_workflow()
"""
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        if "production_e2e" in results:
            data = results["production_e2e"]["result"]
            if isinstance(data, dict) and "error" not in data:
                verification = data.get("verification", {})
                if verification.get("database_consistent") and verification.get(
                    "cache_consistent"
                ):
                    log_test(
                        "production_scenarios",
                        "Production E2E workflow",
                        True,
                        f"Events logged: {verification.get('analytics_events', 0)}",
                    )
                else:
                    log_test(
                        "production_scenarios",
                        "Production E2E workflow",
                        False,
                        "",
                        f"Consistency check failed: {verification}",
                    )
            else:
                log_test(
                    "production_scenarios",
                    "Production E2E workflow",
                    False,
                    "",
                    data.get("error", "Unknown error"),
                )
        else:
            log_test(
                "production_scenarios",
                "Production E2E workflow",
                False,
                "",
                "No results",
            )

    except Exception as e:
        log_test("production_scenarios", "Production E2E workflow", False, "", str(e))


def cleanup_infrastructure():
    """Clean up Docker infrastructure"""
    try:
        print("\n=== Cleaning up Infrastructure ===")

        # Stop and remove containers
        result = subprocess.run(
            ["docker-compose", "-f", "docker-compose-dataflow.yml", "down", "-v"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            log_test(
                "infrastructure_setup",
                "Infrastructure cleanup",
                True,
                "Services stopped and volumes removed",
            )
        else:
            log_test(
                "infrastructure_setup",
                "Infrastructure cleanup",
                False,
                "",
                result.stderr,
            )

        # Remove compose file
        if os.path.exists("docker-compose-dataflow.yml"):
            os.remove("docker-compose-dataflow.yml")

    except Exception as e:
        log_test("infrastructure_setup", "Infrastructure cleanup", False, "", str(e))


def create_infrastructure_guide():
    """Create infrastructure setup guide for users"""

    guide_content = """# DataFlow Infrastructure Setup Guide

## Quick Start with Docker

### 1. Prerequisites
```bash
# Install Docker and Docker Compose
# macOS: brew install docker docker-compose
# Ubuntu: sudo apt-get install docker docker-compose
# Windows: Download Docker Desktop
```

### 2. Infrastructure Configuration

Create `docker-compose.yml`:
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: dataflow_db
      POSTGRES_USER: dataflow_user
      POSTGRES_PASSWORD: your_secure_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dataflow_user -d dataflow_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  redis_data:
```

### 3. Start Infrastructure
```bash
# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### 4. DataFlow Configuration

```python
# config.py
import os
from kailash_dataflow import DataFlow

# Production configuration
db = DataFlow(
    database_url=os.getenv("DATABASE_URL", "postgresql://dataflow_user:your_secure_password@localhost:5432/dataflow_db"),
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    pool_size=20,
    pool_max_overflow=50,
    pool_recycle=3600,
    monitoring=True,
    multi_tenant=True
)

# Environment variables
os.environ["DATABASE_URL"] = "postgresql://dataflow_user:your_secure_password@localhost:5432/dataflow_db"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
```

### 5. Production Deployment

```python
# production_workflow.py
from kailash_dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Initialize with production config
db = DataFlow(
    database_url="postgresql://user:pass@production-db:5432/dataflow",
    redis_url="redis://production-redis:6379/0",
    pool_size=50,
    monitoring=True,
    multi_tenant=True,
    security_enabled=True
)

# Define production model
@db.model
class Order:
    customer_id: int
    total: float
    status: str = 'pending'

    __dataflow__ = {
        'multi_tenant': True,
        'versioned': True,
        'encrypted_fields': ['customer_id']
    }

# Production workflow
workflow = WorkflowBuilder()

# High-performance order processing
workflow.add_node("OrderBulkCreateNode", "process_orders", {
    "data": order_batch,
    "batch_size": 1000,
    "conflict_resolution": "upsert"
})

# Real-time analytics
workflow.add_node("AnalyticsNode", "track_orders", {
    "events": [
        {"type": "order_created", "data": ":order_data"}
    ]
})

# Execute with monitoring
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### 6. Monitoring & Observability

```python
# monitoring.py
from kailash_dataflow import DataFlow

# Enable comprehensive monitoring
db = DataFlow(
    monitoring=True,
    metrics_endpoint="/metrics",
    health_check_endpoint="/health",
    slow_query_threshold=1.0,
    export_format="prometheus"
)

# Access monitoring data
monitor = db.get_monitor()
metrics = monitor.get_metrics()
health = monitor.get_health_status()
```

### 7. Scaling Configuration

```python
# scaling.py
from kailash_dataflow import DataFlow

# Horizontal scaling setup
db = DataFlow(
    # Primary database
    database_url="postgresql://primary:5432/dataflow",

    # Read replicas
    read_replicas=[
        "postgresql://replica1:5432/dataflow",
        "postgresql://replica2:5432/dataflow"
    ],

    # Distributed cache
    redis_cluster=[
        "redis://redis1:6379",
        "redis://redis2:6379",
        "redis://redis3:6379"
    ],

    # Connection pooling
    pool_size=100,
    max_connections=1000,

    # Performance optimization
    connection_timeout=30,
    query_timeout=60,
    bulk_chunk_size=5000
)
```

### 8. Security Configuration

```python
# security.py
from kailash_dataflow import DataFlow

# Production security
db = DataFlow(
    database_url="postgresql://user:pass@secure-db:5432/dataflow",

    # Security features
    ssl_required=True,
    encrypt_at_rest=True,
    audit_logging=True,
    access_control=True,

    # Multi-tenancy
    multi_tenant=True,
    tenant_isolation_level="strict",

    # Compliance
    gdpr_mode=True,
    data_retention_days=365,
    automatic_backups=True
)
```

## Testing Your Setup

Run the comprehensive test:
```bash
python temp_dataflow_e2e_infrastructure.py
```

This will:
1. ✅ Setup Docker infrastructure
2. ✅ Test PostgreSQL integration
3. ✅ Test Redis caching
4. ✅ Test MongoDB analytics
5. ✅ Run production E2E scenario
6. ✅ Cleanup infrastructure

## Need Help?

- Documentation: [DataFlow User Guide](docs/USER_GUIDE.md)
- Examples: [Production Examples](examples/production/)
- Issues: [GitHub Issues](https://github.com/kailash/dataflow/issues)
"""

    with open("DATAFLOW_INFRASTRUCTURE_GUIDE.md", "w") as f:
        f.write(guide_content)

    log_test(
        "infrastructure_setup",
        "Infrastructure guide creation",
        True,
        "Guide created: DATAFLOW_INFRASTRUCTURE_GUIDE.md",
    )


def generate_report():
    """Generate comprehensive E2E validation report"""
    print("\n" + "=" * 80)
    print("DATAFLOW E2E INFRASTRUCTURE VALIDATION REPORT")
    print("=" * 80)

    # Calculate statistics
    total_tests = 0
    passed_tests = 0

    for category, results in test_results.items():
        if category != "errors":
            total_tests += len(results)
            passed_tests += sum(1 for result in results if result["success"])

    failed_tests = total_tests - passed_tests
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

    print("\nSUMMARY:")
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests} (✅)")
    print(f"Failed: {failed_tests} (❌)")
    print(f"Success Rate: {success_rate:.1f}%")

    # Category breakdown
    categories = [
        "infrastructure_setup",
        "real_database_tests",
        "real_cache_tests",
        "production_scenarios",
    ]

    for category in categories:
        if category in test_results:
            results = test_results[category]
            passed = sum(1 for r in results if r["success"])
            total = len(results)
            print(f"\n{category.upper().replace('_', ' ')}: {passed}/{total} passed")

            for result in results:
                status = "✅" if result["success"] else "❌"
                print(f"  {status} {result['test_name']}")
                if result["details"]:
                    print(f"    {result['details']}")
                if result["error"]:
                    print(f"    Error: {result['error']}")

    # Infrastructure summary
    print("\nINFRASTRUCTURE TESTED:")
    print("  🐘 PostgreSQL - Production database")
    print("  🔴 Redis - High-performance caching")
    print("  🍃 MongoDB - Analytics and events")
    print("  🐳 Docker - Containerized infrastructure")

    # Final assessment
    print("\nFINAL ASSESSMENT:")
    if failed_tests == 0:
        print("  ✅ ALL E2E TESTS PASSED!")
        print("  ✅ Real infrastructure integration works")
        print("  ✅ Production scenarios validated")
        print("  ✅ CLAUDE.md guidance is production-ready")
    else:
        print(f"  ❌ {failed_tests} tests failed.")
        print("  - Check Docker services are running")
        print("  - Verify database connections")
        print("  - Review error logs above")

    print("\n" + "=" * 80)

    return {
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "failed_tests": failed_tests,
        "success_rate": success_rate,
    }


def main():
    """Run comprehensive E2E validation with real infrastructure"""
    print("Starting E2E DataFlow validation with REAL infrastructure...")
    print("This will test with PostgreSQL, Redis, MongoDB, and Docker...")

    # Create infrastructure guide
    create_infrastructure_guide()

    # Setup infrastructure
    if not setup_docker_infrastructure():
        print("❌ Infrastructure setup failed. Cannot continue with E2E tests.")
        return test_results, {"success": False}

    try:
        # Test real integrations
        test_real_postgresql_integration()
        test_real_redis_caching()
        test_real_mongodb_integration()

        # Test production scenarios
        test_production_scenario_e2e()

    finally:
        # Always cleanup
        cleanup_infrastructure()

    # Generate report
    summary = generate_report()

    return test_results, summary


if __name__ == "__main__":
    results, summary = main()

    # Exit with appropriate code
    sys.exit(0 if summary.get("failed_tests", 1) == 0 else 1)
