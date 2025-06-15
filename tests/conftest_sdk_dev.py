"""
SDK Development Infrastructure Auto-Start for Tests

This module ensures the SDK development infrastructure is running
when tests are executed with SDK_DEV_MODE=true.
"""

import os
import subprocess
import time
from pathlib import Path

import pytest
import requests


def is_sdk_dev_running():
    """Check if SDK development infrastructure is running."""
    try:
        response = requests.get("http://localhost:8889/health", timeout=1)
        return response.status_code == 200
    except:
        return False


def start_sdk_dev_infrastructure():
    """Start SDK development infrastructure if not running."""
    if is_sdk_dev_running():
        print("✓ SDK development infrastructure is already running")
        return True

    print("Starting SDK development infrastructure...")
    project_root = Path(__file__).parent.parent
    docker_dir = project_root / "docker"

    try:
        # Check if Docker is running
        subprocess.run(["docker", "info"], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        print("⚠️  Docker is not running. Please start Docker first.")
        return False

    # Start infrastructure
    cmd = ["docker", "compose", "-f", "docker-compose.sdk-dev.yml", "up", "-d"]
    result = subprocess.run(cmd, cwd=docker_dir, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Failed to start infrastructure: {result.stderr}")
        return False

    # Wait for services to be ready
    print("Waiting for services to be ready...")
    max_retries = 30
    for i in range(max_retries):
        if is_sdk_dev_running():
            print("✓ SDK development infrastructure is ready")
            return True
        time.sleep(2)
        if i % 5 == 0:
            print(f"  Still waiting... ({i}/{max_retries})")

    print("⚠️  Timeout waiting for infrastructure to start")
    return False


def pytest_configure(config):
    """Configure pytest to start SDK infrastructure if needed and register custom markers."""
    # Start SDK infrastructure if needed
    if os.getenv("SDK_DEV_MODE") == "true":
        if not start_sdk_dev_infrastructure():
            pytest.exit("Failed to start SDK development infrastructure", 1)

    # Register custom markers
    config.addinivalue_line(
        "markers",
        "requires_infrastructure: mark test as requiring SDK development infrastructure",
    )
    config.addinivalue_line("markers", "requires_kafka: mark test as requiring Kafka")
    config.addinivalue_line(
        "markers", "requires_mongodb: mark test as requiring MongoDB"
    )
    config.addinivalue_line(
        "markers", "requires_qdrant: mark test as requiring Qdrant vector database"
    )


def pytest_collection_modifyitems(config, items):
    """Mark tests that require infrastructure."""
    for item in items:
        # Add marker for tests that need infrastructure
        if any(
            marker in item.keywords
            for marker in ["requires_kafka", "requires_mongodb", "requires_qdrant"]
        ):
            item.add_marker(pytest.mark.requires_infrastructure)


@pytest.fixture(scope="session")
def sdk_infrastructure():
    """Fixture that ensures SDK infrastructure is available."""
    if os.getenv("SDK_DEV_MODE") != "true":
        pytest.skip(
            "SDK development infrastructure not enabled (set SDK_DEV_MODE=true)"
        )

    if not is_sdk_dev_running():
        pytest.skip("SDK development infrastructure is not running")

    # Load environment variables
    env_file = Path(__file__).parent.parent / "sdk-users" / ".env.sdk-dev"
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file)

    return {
        "postgres": os.getenv("TRANSACTION_DB"),
        "mongodb": os.getenv("MONGO_URL"),
        "kafka": os.getenv("KAFKA_BROKERS"),
        "qdrant": "http://localhost:6333",
        "ollama": os.getenv("OLLAMA_HOST"),
        "mock_api": os.getenv("WEBHOOK_API"),
        "mcp_server": os.getenv("MCP_SERVER_URL"),
    }
