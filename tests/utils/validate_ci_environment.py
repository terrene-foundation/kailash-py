#!/usr/bin/env python3
"""Validate CI environment has all required Docker services running."""

import subprocess
import sys
import time

import requests


def check_command_exists(command):
    """Check if a command exists."""
    try:
        subprocess.run([command, "--version"], capture_output=True, check=True)
        return True
    except:
        return False


def check_docker_running():
    """Check if Docker is running."""
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False


def check_container_running(container_name_pattern):
    """Check if a container matching the pattern is running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return any(container_name_pattern in line for line in result.stdout.split("\n"))
    except:
        return False


def check_postgres():
    """Check if PostgreSQL is accessible."""
    try:
        # Try to connect to PostgreSQL
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
        return result.returncode == 0
    except:
        return False


def check_redis():
    """Check if Redis is accessible."""
    try:
        result = subprocess.run(
            ["docker", "exec", "kailash_test_redis", "redis-cli", "ping"],
            capture_output=True,
            text=True,
        )
        return "PONG" in result.stdout
    except:
        return False


def check_ollama():
    """Check if Ollama is accessible."""
    try:
        response = requests.get("http://localhost:11435/api/tags", timeout=5)
        return response.status_code == 200
    except:
        return False


def main():
    """Main validation function."""
    print("🔍 Validating CI Docker environment...")

    all_good = True

    # Check Docker
    if not check_docker_running():
        print("❌ Docker is not running")
        all_good = False
    else:
        print("✅ Docker is running")

    # Check containers
    services = [
        ("PostgreSQL", "postgres", check_postgres),
        ("Redis", "redis", check_redis),
        ("Ollama", "ollama", check_ollama),
    ]

    for service_name, container_pattern, check_func in services:
        if check_container_running(container_pattern):
            print(f"✅ {service_name} container is running")

            # Additional health check
            if check_func():
                print(f"✅ {service_name} is healthy and accessible")
            else:
                print(f"⚠️  {service_name} container is running but not accessible")
                # Don't fail on Ollama accessibility issues
                if service_name != "Ollama":
                    all_good = False
        else:
            print(f"❌ {service_name} container is not running")
            all_good = False

    # Summary
    if all_good:
        print("\n✅ All Docker services are ready for testing!")
        return 0
    else:
        print("\n❌ Some Docker services are not ready")
        print("\nTo set up locally, run:")
        print("  python tests/setup_local_docker.py")
        return 1


if __name__ == "__main__":
    sys.exit(main())
