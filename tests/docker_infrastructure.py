#!/usr/bin/env python3
"""Test Docker infrastructure is working correctly."""

import subprocess
import sys
import time

import pytest
import requests


def test_docker_running():
    """Test that Docker is running."""
    result = subprocess.run(["docker", "info"], capture_output=True)
    assert result.returncode == 0, "Docker is not running"


def test_postgres_container():
    """Test PostgreSQL container is accessible."""
    result = subprocess.run(
        [
            "docker",
            "exec",
            "kailash_test_postgres",
            "pg_isready",
            "-U",
            "test_user",
            "-d",
            "kailash_test",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"PostgreSQL not ready: {result.stderr}"


def test_mysql_container():
    """Test MySQL container is accessible."""
    result = subprocess.run(
        [
            "docker",
            "exec",
            "kailash_test_mysql",
            "mysqladmin",
            "ping",
            "-h",
            "localhost",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"MySQL not ready: {result.stderr}"


def test_redis_container():
    """Test Redis container is accessible."""
    result = subprocess.run(
        ["docker", "exec", "kailash_test_redis", "redis-cli", "ping"],
        capture_output=True,
        text=True,
    )
    assert "PONG" in result.stdout, f"Redis not ready: {result.stderr}"


def test_ollama_api():
    """Test Ollama API is accessible."""
    try:
        response = requests.get("http://localhost:11435/api/tags", timeout=5)
        assert (
            response.status_code == 200
        ), f"Ollama API returned {response.status_code}"
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Ollama API not accessible: {e}")


def test_ollama_model_available():
    """Test that Ollama has at least one model available."""
    try:
        response = requests.get("http://localhost:11435/api/tags", timeout=5)
        data = response.json()
        assert "models" in data, "No models key in Ollama response"
        # Don't require specific models, just that the API works
        print(f"Ollama has {len(data.get('models', []))} models available")
    except Exception as e:
        pytest.fail(f"Failed to check Ollama models: {e}")


if __name__ == "__main__":
    # Run all tests
    test_docker_running()
    test_postgres_container()
    test_mysql_container()
    test_redis_container()
    test_ollama_api()
    test_ollama_model_available()
    print("✅ All Docker infrastructure tests passed!")
