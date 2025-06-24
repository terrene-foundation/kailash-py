#!/usr/bin/env python3
"""Setup local Docker infrastructure for running all tests.

This script sets up PostgreSQL, MySQL, Redis, and Ollama containers
to enable running the currently skipped tests.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests


def run_command(cmd, check=True):
    """Run a shell command and return the output."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result


def check_docker():
    """Check if Docker is available and running."""
    result = run_command("docker info", check=False)
    if result.returncode != 0:
        print("Error: Docker is not running or not installed.")
        print("Please start Docker Desktop or install Docker.")
        return False
    return True


def check_container_running(container_name):
    """Check if a container is already running."""
    result = run_command(
        f"docker ps --filter name={container_name} --format '{{{{.Names}}}}'",
        check=False,
    )
    return container_name in result.stdout


def wait_for_postgres(
    host="localhost",
    port=5434,
    user="test_user",
    password="test_password",
    database="kailash_test",
):
    """Wait for PostgreSQL to be ready."""
    print("Waiting for PostgreSQL to be ready...")
    for i in range(30):
        result = run_command(
            f"docker exec kailash_test_postgres pg_isready -h localhost -p 5432 -U {user} -d {database}",
            check=False,
        )
        if result.returncode == 0:
            print("PostgreSQL is ready!")
            return True
        time.sleep(1)
    return False


def wait_for_mysql(host="localhost", port=3307, user="root", password="test_password"):
    """Wait for MySQL to be ready."""
    print("Waiting for MySQL to be ready...")
    for i in range(30):
        result = run_command(
            f"docker exec kailash_test_mysql mysql -h localhost -u {user} -p{password} -e 'SELECT 1'",
            check=False,
        )
        if result.returncode == 0:
            print("MySQL is ready!")
            return True
        time.sleep(1)
    return False


def wait_for_redis(host="localhost", port=6380):
    """Wait for Redis to be ready."""
    print("Waiting for Redis to be ready...")
    for i in range(30):
        result = run_command(
            "docker exec kailash_test_redis redis-cli ping", check=False
        )
        if "PONG" in result.stdout:
            print("Redis is ready!")
            return True
        time.sleep(1)
    return False


def wait_for_ollama(base_url="http://localhost:11435"):
    """Wait for Ollama to be ready."""
    print("Waiting for Ollama to be ready...")
    for i in range(30):
        try:
            response = requests.get(f"{base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                print("Ollama is ready!")
                return True
        except:
            pass
        time.sleep(1)
    return False


def setup_postgres():
    """Setup PostgreSQL container for testing."""
    if check_container_running("kailash_test_postgres"):
        print("PostgreSQL container already running.")
        return True

    print("Starting PostgreSQL container...")
    run_command(
        "docker run -d "
        "--name kailash_test_postgres "
        "-e POSTGRES_DB=kailash_test "
        "-e POSTGRES_USER=test_user "
        "-e POSTGRES_PASSWORD=test_password "
        '-e POSTGRES_INITDB_ARGS="-c shared_buffers=256MB -c max_connections=200" '
        "-p 5434:5432 "
        "--health-cmd 'pg_isready -U test_user -d kailash_test' "
        "--health-interval 10s "
        "--health-timeout 5s "
        "--health-retries 5 "
        "postgres:15"
    )

    if not wait_for_postgres():
        print("Failed to start PostgreSQL")
        return False

    # Create test database and schema
    print("Setting up test database...")
    run_command(
        "docker exec kailash_test_postgres psql -U test_user -d kailash_test -c "
        "'CREATE SCHEMA IF NOT EXISTS public;'"
    )

    return True


def setup_mysql():
    """Setup MySQL container for testing."""
    if check_container_running("kailash_test_mysql"):
        print("MySQL container already running.")
        return True

    print("Starting MySQL container...")
    run_command(
        "docker run -d "
        "--name kailash_test_mysql "
        "-e MYSQL_ROOT_PASSWORD=test_password "
        "-e MYSQL_DATABASE=kailash_test "
        "-e MYSQL_USER=kailash_test "
        "-e MYSQL_PASSWORD=test_password "
        "-p 3307:3306 "
        "mysql:8.0"
    )

    if not wait_for_mysql():
        print("Failed to start MySQL")
        return False

    return True


def setup_redis():
    """Setup Redis container for testing."""
    if check_container_running("kailash_test_redis"):
        print("Redis container already running.")
        return True

    print("Starting Redis container...")
    run_command(
        "docker run -d "
        "--name kailash_test_redis "
        "-p 6380:6379 "
        "--health-cmd 'redis-cli ping' "
        "--health-interval 10s "
        "--health-timeout 5s "
        "--health-retries 5 "
        "redis:7-alpine "
        "redis-server "
        "--maxmemory 1gb "
        "--maxmemory-policy allkeys-lru "
        '--save "" '
        "--appendonly no"
    )

    if not wait_for_redis():
        print("Failed to start Redis")
        return False

    return True


def setup_ollama():
    """Setup Ollama container for testing."""
    if check_container_running("kailash_test_ollama"):
        print("Ollama container already running.")
        return True

    print("Starting Ollama container...")
    run_command(
        "docker run -d "
        "--name kailash_test_ollama "
        "-p 11435:11434 "
        "-v ollama_test_models:/root/.ollama "
        "ollama/ollama:latest"
    )

    if not wait_for_ollama():
        print("Failed to start Ollama")
        return False

    # Pull a small model for testing
    print("Pulling test model (this may take a few minutes)...")
    try:
        response = requests.post(
            "http://localhost:11435/api/pull",
            json={"name": "llama3.2:1b"},  # Small 1B parameter model
            timeout=300,
        )
        if response.status_code == 200:
            print("Test model pulled successfully!")
        else:
            print(f"Warning: Failed to pull model: {response.text}")
    except Exception as e:
        print(f"Warning: Failed to pull model: {e}")

    return True


def generate_test_data_with_ollama():
    """Generate test data using Ollama."""
    print("\nGenerating test data with Ollama...")

    try:
        # Generate test API responses
        response = requests.post(
            "http://localhost:11435/api/generate",
            json={
                "model": "llama3.2:1b",
                "prompt": "Generate a JSON response for a user API with fields: id, name, email, role. Make it realistic.",
                "stream": False,
            },
            timeout=30,
        )

        if response.status_code == 200:
            generated = response.json()
            print(f"Generated API response: {generated.get('response', '')[:200]}...")

        # Generate test SQL data
        response = requests.post(
            "http://localhost:11435/api/generate",
            json={
                "model": "llama3.2:1b",
                "prompt": "Generate SQL INSERT statements for a users table with columns: id, name, email, created_at. Create 5 realistic users.",
                "stream": False,
            },
            timeout=30,
        )

        if response.status_code == 200:
            generated = response.json()
            print(f"Generated SQL data: {generated.get('response', '')[:200]}...")

    except Exception as e:
        print(f"Warning: Failed to generate test data: {e}")


def setup_environment_variables():
    """Setup environment variables for testing."""
    env_vars = {
        "POSTGRES_TEST_URL": "postgresql://test_user:test_password@localhost:5434/kailash_test",
        "MYSQL_TEST_URL": "mysql://kailash_test:test_password@localhost:3307/kailash_test",
        "REDIS_TEST_URL": "redis://localhost:6380",
        "OLLAMA_TEST_URL": "http://localhost:11435",
        "TEST_DOCKER_AVAILABLE": "true",
    }

    print("\nEnvironment variables for testing:")
    for key, value in env_vars.items():
        print(f"export {key}={value}")
        os.environ[key] = value

    # Write to .env.test file
    env_file = Path(".env.test")
    with open(env_file, "w") as f:
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")
    print(f"\nEnvironment variables written to {env_file}")


def main():
    """Main setup function."""
    print("=== Kailash SDK Test Infrastructure Setup ===\n")

    if not check_docker():
        return 1

    # Setup all containers
    services = [
        ("PostgreSQL", setup_postgres),
        ("MySQL", setup_mysql),
        ("Redis", setup_redis),
        ("Ollama", setup_ollama),
    ]

    for service_name, setup_func in services:
        print(f"\n--- Setting up {service_name} ---")
        if not setup_func():
            print(f"Failed to setup {service_name}")
            return 1

    # Generate test data
    generate_test_data_with_ollama()

    # Setup environment variables
    setup_environment_variables()

    print("\n=== Setup Complete! ===")
    print("\nYou can now run all tests including the previously skipped ones:")
    print("  pytest tests/unit/ -v")
    print("\nTo stop all test containers:")
    print(
        "  docker stop kailash_test_postgres kailash_test_mysql kailash_test_redis kailash_test_ollama"
    )
    print(
        "  docker rm kailash_test_postgres kailash_test_mysql kailash_test_redis kailash_test_ollama"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
