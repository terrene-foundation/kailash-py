"""Tests for production Dockerfile.

PROD-001: Containerization - Production-ready Dockerfile
Following TDD methodology - Tests written FIRST before implementation.
"""

import os
import subprocess
import time


class TestDockerfile:
    """Test suite for production Dockerfile (PROD-001)."""

    def test_dockerfile_exists(self):
        """PROD-001.1: Dockerfile exists in project root."""
        dockerfile_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "Dockerfile"
        )
        assert os.path.exists(dockerfile_path), "Dockerfile must exist in project root"

    def test_docker_image_builds(self):
        """PROD-001.2: Docker image builds successfully."""
        project_root = os.path.join(os.path.dirname(__file__), "..", "..")

        result = subprocess.run(
            ["docker", "build", "-t", "kaizen-test:latest", "."],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=project_root,
        )
        assert result.returncode == 0, f"Docker build failed: {result.stderr}"

    def test_docker_image_size(self):
        """PROD-001.3: Docker image size is under 2GB (realistic for AI framework with scipy/numpy/pandas)."""
        project_root = os.path.join(os.path.dirname(__file__), "..", "..")

        # Build image first
        subprocess.run(
            ["docker", "build", "-t", "kaizen-test:latest", "."],
            check=True,
            cwd=project_root,
            capture_output=True,
        )

        # Check image size
        result = subprocess.run(
            ["docker", "images", "kaizen-test:latest", "--format", "{{.Size}}"],
            capture_output=True,
            text=True,
        )
        size_str = result.stdout.strip()

        # Parse size (e.g., "456MB" or "1.2GB")
        if "GB" in size_str:
            size_mb = float(size_str.replace("GB", "")) * 1024
        else:
            size_mb = float(size_str.replace("MB", ""))

        # Note: Kailash SDK includes scipy, numpy, pandas, matplotlib, sklearn
        # which makes <500MB unrealistic. 2GB is reasonable for production AI framework.
        assert size_mb < 2048, f"Image size {size_mb}MB exceeds 2GB limit"

    def test_docker_runs_as_non_root(self):
        """PROD-001.4: Container runs as non-root user."""
        project_root = os.path.join(os.path.dirname(__file__), "..", "..")

        # Build and run container
        subprocess.run(
            ["docker", "build", "-t", "kaizen-test:latest", "."],
            check=True,
            cwd=project_root,
            capture_output=True,
        )

        result = subprocess.run(
            ["docker", "run", "--rm", "kaizen-test:latest", "whoami"],
            capture_output=True,
            text=True,
        )

        user = result.stdout.strip()
        assert user != "root", f"Container running as root user: {user}"
        assert user == "kaizen", f"Expected user 'kaizen', got '{user}'"

    def test_docker_health_check(self):
        """PROD-001.5: Docker health check is configured."""
        project_root = os.path.join(os.path.dirname(__file__), "..", "..")

        # Build image
        subprocess.run(
            ["docker", "build", "-t", "kaizen-test:latest", "."],
            check=True,
            cwd=project_root,
            capture_output=True,
        )

        # Inspect image for HEALTHCHECK
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "kaizen-test:latest",
                "--format",
                "{{.Config.Healthcheck}}",
            ],
            capture_output=True,
            text=True,
        )

        healthcheck = result.stdout.strip()
        assert healthcheck != "<nil>", "HEALTHCHECK not configured in Dockerfile"
        assert healthcheck != "", "HEALTHCHECK is empty"

    def test_docker_compose_up(self):
        """PROD-001.6: Docker Compose stack starts successfully."""
        project_root = os.path.join(os.path.dirname(__file__), "..", "..")

        # Start docker-compose
        result = subprocess.run(
            ["docker-compose", "-f", "docker-compose.yml", "up", "-d"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=project_root,
        )

        assert result.returncode == 0, f"docker-compose up failed: {result.stderr}"

        # Wait for services to be healthy
        time.sleep(10)

        # Check services are running
        result = subprocess.run(
            ["docker-compose", "ps", "--services", "--filter", "status=running"],
            capture_output=True,
            text=True,
            cwd=project_root,
        )

        running_services = result.stdout.strip().split("\n")
        assert "kaizen" in running_services, "Kaizen service not running"

        # Cleanup
        subprocess.run(
            ["docker-compose", "down"], capture_output=True, cwd=project_root
        )
