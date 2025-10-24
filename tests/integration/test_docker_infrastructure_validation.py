#!/usr/bin/env python3
"""
Quick infrastructure validation script for Docker test environment.
This script validates that all required services are working properly.
"""

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict

import psycopg2
import pytest
import requests

from tests.utils.docker_config import DATABASE_CONFIG, OLLAMA_CONFIG, REDIS_CONFIG

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    try:
        import redis.asyncio as redis_async

        redis = redis_async
        REDIS_AVAILABLE = True
    except ImportError:
        REDIS_AVAILABLE = False
        print("⚠️  Redis not available - some tests will be skipped")


@pytest.mark.asyncio
async def test_postgres():
    """Test PostgreSQL connectivity and basic operations."""
    print("🐘 Testing PostgreSQL...")
    try:
        conn = psycopg2.connect(
            host=DATABASE_CONFIG["host"],
            port=DATABASE_CONFIG["port"],
            database=DATABASE_CONFIG["database"],
            user=DATABASE_CONFIG["user"],
            password=DATABASE_CONFIG["password"],
        )
        cursor = conn.cursor()

        # Test basic query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"   ✅ PostgreSQL connected: {version[:50]}...")

        # Test table existence
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'public'
        """
        )
        table_count = cursor.fetchone()[0]
        print(f"   ✅ Database has {table_count} tables")

        # Test create table and insert
        cursor.execute(
            """
            CREATE TEMPORARY TABLE test_infrastructure (
                id SERIAL PRIMARY KEY,
                test_data TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """
        )
        cursor.execute(
            "INSERT INTO test_infrastructure (test_data) VALUES (%s)", ("test_value",)
        )
        cursor.execute("SELECT test_data FROM test_infrastructure WHERE id = 1")
        result = cursor.fetchone()[0]
        assert result == "test_value"
        print("   ✅ Write/Read operations working")

        conn.commit()
        cursor.close()
        conn.close()
        print("   ✅ PostgreSQL test passed")

    except Exception as e:
        print(f"   ❌ PostgreSQL error: {e}")
        pytest.fail(f"PostgreSQL test failed: {e}")


@pytest.mark.asyncio
async def test_redis():
    """Test Redis connectivity and basic operations."""
    if not REDIS_AVAILABLE:
        print("⚠️  Skipping Redis test - library not available")
        pytest.skip("Redis library not available")

    print("🔴 Testing Redis...")
    try:
        client = redis.Redis(
            host=REDIS_CONFIG["host"], port=REDIS_CONFIG["port"], decode_responses=True
        )

        # Test connection
        ping_result = client.ping()
        print(f"   ✅ Redis connected: ping = {ping_result}")

        # Test basic operations
        test_key = f"test_infrastructure_{int(time.time())}"
        client.set(test_key, "test_value", ex=60)
        result = client.get(test_key)
        assert result == "test_value"
        print("   ✅ Set/Get operations working")

        # Test expiration
        client.expire(test_key, 1)
        time.sleep(1.1)
        result = client.get(test_key)
        assert result is None
        print("   ✅ TTL/Expiration working")

        client.close()
        print("   ✅ Redis test passed")

    except Exception as e:
        print(f"   ❌ Redis error: {e}")
        pytest.fail(f"Redis test failed: {e}")


@pytest.mark.asyncio
async def test_ollama():
    """Test Ollama connectivity and model availability."""
    print("🦙 Testing Ollama...")
    try:
        # Test API health
        response = requests.get(f"{OLLAMA_CONFIG['base_url']}/api/tags", timeout=10)
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}")

        models = response.json()
        print(f"   ✅ Ollama connected: {len(models['models'])} models available")

        # Check for test model
        model_names = [model["name"] for model in models["models"]]
        if "llama3.2:1b" in model_names:
            print("   ✅ Test model (llama3.2:1b) available")
        else:
            print(f"   ⚠️  Test model not found. Available: {model_names}")

        # Test simple generation
        generate_data = {
            "model": "llama3.2:1b",
            "prompt": "Hello, testing infrastructure. Respond with 'OK' only.",
            "stream": False,
        }

        response = requests.post(
            f"{OLLAMA_CONFIG['base_url']}/api/generate", json=generate_data, timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            generated_text = result.get("response", "").strip()
            print(f"   ✅ Model generation working: '{generated_text[:50]}...'")
        else:
            print(f"   ⚠️  Model generation failed: HTTP {response.status_code}")

        print("   ✅ Ollama test passed")

    except Exception as e:
        print(f"   ❌ Ollama error: {e}")
        pytest.fail(f"Ollama test failed: {e}")


@pytest.mark.asyncio
async def test_integration():
    """Test cross-service integration scenario."""
    print("🔗 Testing Integration...")
    try:
        # Create a test workflow that uses all services
        test_id = f"integration_test_{int(time.time())}"

        # 1. Store test data in Redis
        if REDIS_AVAILABLE:
            client = redis.Redis(
                host=REDIS_CONFIG["host"],
                port=REDIS_CONFIG["port"],
                decode_responses=True,
            )
            client.set(f"test:{test_id}", json.dumps({"status": "started"}), ex=300)
            print("   ✅ Data cached in Redis")
            client.close()

        # 2. Store workflow metadata in PostgreSQL
        conn = psycopg2.connect(
            host=DATABASE_CONFIG["host"],
            port=DATABASE_CONFIG["port"],
            database=DATABASE_CONFIG["database"],
            user=DATABASE_CONFIG["user"],
            password=DATABASE_CONFIG["password"],
        )
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS test_workflows (
                id TEXT PRIMARY KEY,
                status TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """
        )
        cursor.execute(
            "INSERT INTO test_workflows (id, status) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET status = %s",
            (test_id, "running", "running"),
        )
        conn.commit()
        print("   ✅ Workflow logged in PostgreSQL")

        # 3. Use Ollama for processing simulation
        generate_data = {
            "model": "llama3.2:1b",
            "prompt": "Say 'Integration test successful' in exactly those words:",
            "stream": False,
        }

        response = requests.post(
            f"{OLLAMA_CONFIG['base_url']}/api/generate", json=generate_data, timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            ai_result = result.get("response", "").strip()
            print(f"   ✅ AI processing completed: '{ai_result[:50]}...'")

        # 4. Update final status
        cursor.execute(
            "UPDATE test_workflows SET status = %s WHERE id = %s",
            ("completed", test_id),
        )
        conn.commit()

        if REDIS_AVAILABLE:
            client = redis.Redis(
                host=REDIS_CONFIG["host"],
                port=REDIS_CONFIG["port"],
                decode_responses=True,
            )
            client.set(f"test:{test_id}", json.dumps({"status": "completed"}), ex=300)
            client.close()

        print("   ✅ Integration test completed successfully")

        cursor.close()
        conn.close()
        print("   ✅ Integration test passed")

    except Exception as e:
        print(f"   ❌ Integration test error: {e}")
        pytest.fail(f"Integration test failed: {e}")


async def main():
    """Run all infrastructure tests."""
    print("🚀 Starting Docker Infrastructure Validation")
    print("=" * 50)

    results = []

    # Test individual services
    results.append(await test_postgres())
    results.append(await test_redis())
    results.append(await test_ollama())
    results.append(await test_integration())

    print("\n" + "=" * 50)

    if all(results):
        print("✅ All infrastructure tests passed!")
        print("🎉 Docker environment is ready for pytest")
        return 0
    else:
        failed_tests = sum(1 for r in results if not r)
        print(f"❌ {failed_tests} infrastructure tests failed")
        print("🔧 Please check Docker containers and configuration")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
