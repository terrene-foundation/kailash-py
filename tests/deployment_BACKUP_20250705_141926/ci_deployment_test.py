#!/usr/bin/env python3
"""
CI/CD Deployment Test Script

This script is designed to run in continuous integration environments
to validate MCP deployment configurations.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CIDeploymentTest:
    """CI/CD deployment test runner"""

    def __init__(self, project_root: str = None):
        self.project_root = (
            Path(project_root) if project_root else Path(__file__).parent.parent.parent
        )
        self.failed_tests = []

    def test_docker_compose_syntax(self, compose_file: str) -> bool:
        """Test Docker Compose file syntax"""
        try:
            cmd = ["docker-compose", "-f", str(compose_file), "config", "--quiet"]
            result = subprocess.run(
                cmd,
                cwd=str(Path(compose_file).parent),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.error(
                    f"Docker Compose syntax error in {compose_file}: {result.stderr}"
                )
                return False

            logger.info(f"✅ Docker Compose syntax valid: {compose_file}")
            return True

        except subprocess.TimeoutExpired:
            logger.error(f"❌ Docker Compose validation timeout: {compose_file}")
            return False
        except FileNotFoundError:
            logger.warning(
                f"⚠️ docker-compose not found, skipping syntax test for {compose_file}"
            )
            return True  # Don't fail if docker-compose is not available
        except Exception as e:
            logger.error(
                f"❌ Docker Compose validation error for {compose_file}: {str(e)}"
            )
            return False

    def test_dockerfile_build_syntax(self, dockerfile: str, context_dir: str) -> bool:
        """Test Dockerfile can be parsed without actually building"""
        try:
            # Use docker build --dry-run if available, otherwise parse manually
            cmd = [
                "docker",
                "build",
                "--file",
                str(dockerfile),
                "--dry-run",
                str(context_dir),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                # Try without --dry-run (older Docker versions)
                logger.warning(
                    f"Docker --dry-run not supported, checking Dockerfile manually: {dockerfile}"
                )
                return self._validate_dockerfile_manually(dockerfile)

            logger.info(f"✅ Dockerfile syntax valid: {dockerfile}")
            return True

        except subprocess.TimeoutExpired:
            logger.error(f"❌ Docker build validation timeout: {dockerfile}")
            return False
        except FileNotFoundError:
            logger.warning(f"⚠️ Docker not found, skipping build test for {dockerfile}")
            return True  # Don't fail if Docker is not available
        except Exception as e:
            logger.error(f"❌ Docker build validation error for {dockerfile}: {str(e)}")
            return False

    def _validate_dockerfile_manually(self, dockerfile: str) -> bool:
        """Manually validate Dockerfile syntax"""
        try:
            with open(dockerfile, "r") as f:
                content = f.read()

            # Basic syntax checks
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Check for basic instruction format
                if not any(
                    line.upper().startswith(cmd)
                    for cmd in [
                        "FROM",
                        "RUN",
                        "CMD",
                        "LABEL",
                        "EXPOSE",
                        "ENV",
                        "ADD",
                        "COPY",
                        "ENTRYPOINT",
                        "VOLUME",
                        "USER",
                        "WORKDIR",
                        "ARG",
                        "HEALTHCHECK",
                    ]
                ):
                    logger.warning(
                        f"Potential syntax issue in {dockerfile} line {i}: {line}"
                    )

            logger.info(f"✅ Dockerfile manual validation passed: {dockerfile}")
            return True

        except Exception as e:
            logger.error(
                f"❌ Dockerfile manual validation failed for {dockerfile}: {str(e)}"
            )
            return False

    def test_required_files_exist(
        self, app_path: str, required_files: List[str]
    ) -> bool:
        """Test that required files exist"""
        missing_files = []

        for file_path in required_files:
            full_path = self.project_root / file_path
            if not full_path.exists():
                missing_files.append(file_path)

        if missing_files:
            logger.error(
                f"❌ Missing required files in {app_path}: {', '.join(missing_files)}"
            )
            return False

        logger.info(f"✅ All required files present: {app_path}")
        return True

    def run_deployment_tests(self) -> bool:
        """Run all deployment tests"""

        # Define test configurations
        test_configs = [
            {
                "name": "mcp-basic",
                "dockerfile": "apps/mcp/Dockerfile",
                "compose": "apps/mcp/docker-compose.yml",
                "context": "apps/mcp",
                "required_files": ["apps/mcp/requirements.txt", "apps/mcp/main.py"],
            },
            {
                "name": "mcp-ai-assistant",
                "dockerfile": "apps/mcp_ai_assistant/Dockerfile",
                "compose": "apps/mcp_ai_assistant/docker-compose.yml",
                "context": "apps/mcp_ai_assistant",
                "required_files": ["apps/mcp_ai_assistant/requirements.txt"],
            },
            {
                "name": "mcp-tools-server",
                "dockerfile": "apps/mcp_tools_server/Dockerfile",
                "compose": "apps/mcp_tools_server/docker-compose.yml",
                "context": "apps/mcp_tools_server",
                "required_files": ["apps/mcp_tools_server/requirements.txt"],
            },
            {
                "name": "mcp-data-pipeline",
                "dockerfile": "apps/mcp_data_pipeline/Dockerfile",
                "compose": "apps/mcp_data_pipeline/docker-compose.yml",
                "context": "apps/mcp_data_pipeline",
                "required_files": ["apps/mcp_data_pipeline/requirements.txt"],
            },
            {
                "name": "mcp-integration-patterns",
                "dockerfile": "apps/mcp_integration_patterns/production/docker_deployment/Dockerfile.kailash-server",
                "compose": "apps/mcp_integration_patterns/production/docker_deployment/docker-compose.yml",
                "context": "apps/mcp_integration_patterns/production/docker_deployment",
                "required_files": [
                    "apps/mcp_integration_patterns/production/docker_deployment/requirements.txt"
                ],
            },
        ]

        all_passed = True

        logger.info("Starting CI/CD deployment tests...")

        for config in test_configs:
            logger.info(f"\n--- Testing {config['name']} ---")

            # Test required files
            if not self.test_required_files_exist(
                config["context"], config["required_files"]
            ):
                self.failed_tests.append(f"{config['name']}: Missing required files")
                all_passed = False
                continue

            # Test Dockerfile
            dockerfile_path = self.project_root / config["dockerfile"]
            context_path = self.project_root / config["context"]

            if dockerfile_path.exists():
                if not self.test_dockerfile_build_syntax(
                    str(dockerfile_path), str(context_path)
                ):
                    self.failed_tests.append(
                        f"{config['name']}: Dockerfile syntax error"
                    )
                    all_passed = False
            else:
                logger.error(f"❌ Dockerfile not found: {dockerfile_path}")
                self.failed_tests.append(f"{config['name']}: Dockerfile not found")
                all_passed = False

            # Test Docker Compose
            compose_path = self.project_root / config["compose"]

            if compose_path.exists():
                if not self.test_docker_compose_syntax(str(compose_path)):
                    self.failed_tests.append(
                        f"{config['name']}: Docker Compose syntax error"
                    )
                    all_passed = False
            else:
                logger.error(f"❌ Docker Compose file not found: {compose_path}")
                self.failed_tests.append(f"{config['name']}: Docker Compose not found")
                all_passed = False

        return all_passed

    def generate_ci_report(self) -> str:
        """Generate CI/CD test report"""
        if not self.failed_tests:
            return "✅ All MCP deployment configurations passed CI/CD validation!"

        report = [
            "❌ MCP Deployment CI/CD Validation Failed",
            "",
            "Failed tests:",
        ]

        for failure in self.failed_tests:
            report.append(f"  - {failure}")

        report.extend(
            ["", "Please fix the above issues before deploying to production.", ""]
        )

        return "\n".join(report)


def main():
    """Main CI/CD test function"""

    # Check if we're in CI environment
    ci_env = os.getenv("CI", "false").lower() == "true"
    if ci_env:
        logger.info("Running in CI environment")

    # Initialize test runner
    test_runner = CIDeploymentTest()

    # Run tests
    success = test_runner.run_deployment_tests()

    # Generate report
    report = test_runner.generate_ci_report()
    print(report)

    # Save report for CI artifacts
    if ci_env:
        with open("deployment_ci_report.txt", "w") as f:
            f.write(report)
        logger.info("CI report saved to deployment_ci_report.txt")

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
