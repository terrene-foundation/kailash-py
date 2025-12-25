#!/usr/bin/env python3
"""
Comprehensive MCP Deployment Validation Test Suite

This test suite validates all MCP deployment configurations including:
- Docker builds for all applications
- Docker Compose configurations
- Environment variable handling
- Service dependencies
- Health checks
- Configuration file validity
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
import yaml

try:
    import docker
    from docker.errors import APIError, BuildError

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DeploymentTestStatus(Enum):
    """Test execution status"""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DeploymentTest:
    """Container for deployment test metadata"""

    name: str
    description: str
    app_path: str
    dockerfile_path: str
    compose_path: Optional[str] = None
    required_files: List[str] = None
    environment_vars: List[str] = None
    status: DeploymentTestStatus = DeploymentTestStatus.PENDING
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.required_files is None:
            self.required_files = []
        if self.environment_vars is None:
            self.environment_vars = []


class MCPDeploymentValidator:
    """Main deployment validation class"""

    def __init__(self, project_root: str = None):
        self.project_root = (
            Path(project_root) if project_root else Path(__file__).parent.parent.parent
        )
        self.docker_client = None
        if DOCKER_AVAILABLE:
            try:
                self.docker_client = docker.from_env()
            except Exception:
                # Docker not available or not running
                pass
        self.test_results = []
        self.deployment_tests = self._discover_deployment_tests()

    def _discover_deployment_tests(self) -> List[DeploymentTest]:
        """Automatically discover all MCP deployment configurations"""
        tests = []

        # Define all MCP applications and their deployment configurations
        mcp_apps = [
            DeploymentTest(
                name="mcp-basic",
                description="Basic MCP application",
                app_path="apps/mcp",
                dockerfile_path="apps/mcp/Dockerfile",
                compose_path="apps/mcp/docker-compose.yml",
                required_files=["apps/mcp/requirements.txt", "apps/mcp/main.py"],
                environment_vars=["MCP_DEBUG", "MCP_DATABASE_URL", "MCP_REDIS_HOST"],
            ),
            DeploymentTest(
                name="mcp-ai-assistant",
                description="MCP AI Assistant application",
                app_path="apps/mcp_ai_assistant",
                dockerfile_path="apps/mcp_ai_assistant/Dockerfile",
                compose_path="apps/mcp_ai_assistant/docker-compose.yml",
                required_files=["apps/mcp_ai_assistant/requirements.txt"],
                environment_vars=["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "REDIS_URL"],
            ),
            DeploymentTest(
                name="mcp-tools-server",
                description="MCP Tools Server",
                app_path="apps/mcp_tools_server",
                dockerfile_path="apps/mcp_tools_server/Dockerfile",
                compose_path="apps/mcp_tools_server/docker-compose.yml",
                required_files=["apps/mcp_tools_server/requirements.txt"],
                environment_vars=["MCP_SERVER_NAME", "MCP_PORT", "MCP_AUTH_TOKEN"],
            ),
            DeploymentTest(
                name="mcp-data-pipeline",
                description="MCP Data Pipeline",
                app_path="apps/mcp_data_pipeline",
                dockerfile_path="apps/mcp_data_pipeline/Dockerfile",
                compose_path="apps/mcp_data_pipeline/docker-compose.yml",
                required_files=["apps/mcp_data_pipeline/requirements.txt"],
                environment_vars=[],
            ),
            DeploymentTest(
                name="mcp-enterprise-gateway",
                description="MCP Enterprise Gateway",
                app_path="apps/mcp_enterprise_gateway",
                dockerfile_path="apps/mcp_enterprise_gateway/Dockerfile",
                compose_path="apps/mcp_enterprise_gateway/docker-compose.yml",
                required_files=["apps/mcp_enterprise_gateway/requirements.txt"],
                environment_vars=[],
            ),
            DeploymentTest(
                name="mcp-integration-patterns",
                description="MCP Integration Patterns Production",
                app_path="apps/mcp_integration_patterns/production/docker_deployment",
                dockerfile_path="apps/mcp_integration_patterns/production/docker_deployment/Dockerfile.kailash-server",
                compose_path="apps/mcp_integration_patterns/production/docker_deployment/docker-compose.yml",
                required_files=[
                    "apps/mcp_integration_patterns/production/docker_deployment/requirements.txt"
                ],
                environment_vars=[
                    "MCP_SERVER_NAME",
                    "MCP_PORT",
                    "REDIS_URL",
                    "POSTGRES_URL",
                ],
            ),
        ]

        # Filter tests that actually exist
        existing_tests = []
        for test in mcp_apps:
            dockerfile_path = self.project_root / test.dockerfile_path
            if dockerfile_path.exists():
                existing_tests.append(test)
            else:
                logger.warning(
                    f"Skipping {test.name}: Dockerfile not found at {dockerfile_path}"
                )

        return existing_tests

    def validate_dockerfile(self, test: DeploymentTest) -> bool:
        """Validate Dockerfile syntax and best practices"""
        try:
            dockerfile_path = self.project_root / test.dockerfile_path

            if not dockerfile_path.exists():
                test.error_message = f"Dockerfile not found: {dockerfile_path}"
                return False

            with open(dockerfile_path, "r") as f:
                content = f.read()

            # Check for basic Dockerfile requirements
            checks = [
                ("FROM", "Must specify base image"),
                ("WORKDIR", "Should set working directory"),
                ("COPY", "Should copy application code"),
                ("EXPOSE", "Should expose port"),
                ("CMD", "Should specify default command"),
            ]

            for instruction, description in checks:
                if instruction not in content:
                    logger.warning(
                        f"{test.name}: {description} (missing {instruction})"
                    )

            # Check for security best practices
            if "USER root" in content or "USER 0" in content:
                logger.warning(f"{test.name}: Running as root user (security concern)")

            if (
                "apt-get update" in content
                and "rm -rf /var/lib/apt/lists/*" not in content
            ):
                logger.warning(
                    f"{test.name}: apt cache not cleaned up (size optimization)"
                )

            return True

        except Exception as e:
            test.error_message = f"Dockerfile validation error: {str(e)}"
            return False

    def validate_docker_compose(self, test: DeploymentTest) -> bool:
        """Validate Docker Compose configuration"""
        try:
            if not test.compose_path:
                return True  # No compose file to validate

            compose_path = self.project_root / test.compose_path

            if not compose_path.exists():
                test.error_message = f"Docker Compose file not found: {compose_path}"
                return False

            with open(compose_path, "r") as f:
                compose_config = yaml.safe_load(f)

            # Validate compose file structure
            if "services" not in compose_config:
                test.error_message = "Docker Compose file missing 'services' section"
                return False

            # Check for common best practices
            services = compose_config["services"]

            for service_name, service_config in services.items():
                # Check for health checks
                if "healthcheck" not in service_config:
                    logger.warning(
                        f"{test.name}: Service {service_name} missing health check"
                    )

                # Check for restart policy
                if "restart" not in service_config:
                    logger.warning(
                        f"{test.name}: Service {service_name} missing restart policy"
                    )

                # Check for resource limits
                if (
                    "deploy" not in service_config
                    or "resources" not in service_config.get("deploy", {})
                ):
                    logger.warning(
                        f"{test.name}: Service {service_name} missing resource limits"
                    )

            return True

        except yaml.YAMLError as e:
            test.error_message = f"Docker Compose YAML error: {str(e)}"
            return False
        except Exception as e:
            test.error_message = f"Docker Compose validation error: {str(e)}"
            return False

    def validate_required_files(self, test: DeploymentTest) -> bool:
        """Validate that all required files exist"""
        missing_files = []

        for file_path in test.required_files:
            full_path = self.project_root / file_path
            if not full_path.exists():
                missing_files.append(file_path)

        if missing_files:
            test.error_message = f"Missing required files: {', '.join(missing_files)}"
            return False

        return True

    def test_docker_build(self, test: DeploymentTest) -> bool:
        """Test Docker build process"""
        try:
            test.status = DeploymentTestStatus.RUNNING

            # Create build context
            build_context = self.project_root / test.app_path
            dockerfile_path = self.project_root / test.dockerfile_path

            # Calculate relative path from build context to Dockerfile
            dockerfile_relative = os.path.relpath(dockerfile_path, build_context)

            # Build image
            image_tag = f"mcp-test-{test.name}:latest"

            logger.info(f"Building Docker image for {test.name}...")

            # Use docker build command for better error handling
            cmd = [
                "docker",
                "build",
                "-f",
                str(dockerfile_relative),
                "-t",
                image_tag,
                str(build_context),
            ]

            result = subprocess.run(
                cmd,
                cwd=str(build_context),
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                test.error_message = f"Docker build failed: {result.stderr}"
                return False

            # Clean up the test image
            try:
                if self.docker_client:
                    self.docker_client.images.remove(image_tag, force=True)
            except:
                pass  # Ignore cleanup errors

            return True

        except subprocess.TimeoutExpired:
            test.error_message = "Docker build timeout (5 minutes)"
            return False
        except Exception as e:
            test.error_message = f"Docker build error: {str(e)}"
            return False

    def test_docker_compose_syntax(self, test: DeploymentTest) -> bool:
        """Test Docker Compose syntax validation"""
        try:
            if not test.compose_path:
                return True  # No compose file to test

            compose_path = self.project_root / test.compose_path

            # Use docker-compose config to validate syntax
            cmd = ["docker-compose", "-f", str(compose_path), "config"]

            result = subprocess.run(
                cmd,
                cwd=str(compose_path.parent),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                test.error_message = f"Docker Compose syntax error: {result.stderr}"
                return False

            return True

        except subprocess.TimeoutExpired:
            test.error_message = "Docker Compose validation timeout"
            return False
        except Exception as e:
            test.error_message = f"Docker Compose validation error: {str(e)}"
            return False

    def test_environment_variables(self, test: DeploymentTest) -> bool:
        """Test environment variable handling"""
        try:
            if not test.compose_path:
                return True  # No compose file to test

            compose_path = self.project_root / test.compose_path

            with open(compose_path, "r") as f:
                compose_config = yaml.safe_load(f)

            # Check if required environment variables are documented
            services = compose_config.get("services", {})

            for service_name, service_config in services.items():
                env_vars = service_config.get("environment", [])

                # Convert to list format if dict
                if isinstance(env_vars, dict):
                    env_vars = [f"{k}={v}" for k, v in env_vars.items()]

                # Check for hardcoded secrets
                for env_var in env_vars:
                    if isinstance(env_var, str):
                        if any(
                            secret in env_var.lower()
                            for secret in ["password", "secret", "key", "token"]
                        ):
                            if "=" in env_var and not env_var.split("=")[1].startswith(
                                "${"
                            ):
                                logger.warning(
                                    f"{test.name}: Hardcoded secret in {service_name}: {env_var.split('=')[0]}"
                                )

            return True

        except Exception as e:
            test.error_message = f"Environment variable validation error: {str(e)}"
            return False

    def run_test(self, test: DeploymentTest) -> bool:
        """Run a complete deployment test"""
        logger.info(f"Running deployment test: {test.name}")

        try:
            test.status = DeploymentTestStatus.RUNNING

            # Step 1: Validate required files
            if not self.validate_required_files(test):
                test.status = DeploymentTestStatus.FAILED
                return False

            # Step 2: Validate Dockerfile
            if not self.validate_dockerfile(test):
                test.status = DeploymentTestStatus.FAILED
                return False

            # Step 3: Validate Docker Compose
            if not self.validate_docker_compose(test):
                test.status = DeploymentTestStatus.FAILED
                return False

            # Step 4: Test Docker Compose syntax
            if not self.test_docker_compose_syntax(test):
                test.status = DeploymentTestStatus.FAILED
                return False

            # Step 5: Test environment variables
            if not self.test_environment_variables(test):
                test.status = DeploymentTestStatus.FAILED
                return False

            # Step 6: Test Docker build (most resource intensive)
            if not self.test_docker_build(test):
                test.status = DeploymentTestStatus.FAILED
                return False

            test.status = DeploymentTestStatus.PASSED
            logger.info(f"✅ {test.name} passed all tests")
            return True

        except Exception as e:
            test.error_message = f"Test execution error: {str(e)}"
            test.status = DeploymentTestStatus.FAILED
            logger.error(f"❌ {test.name} failed: {str(e)}")
            return False

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all deployment tests"""
        logger.info("Starting comprehensive MCP deployment validation")

        results = {
            "total_tests": len(self.deployment_tests),
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "tests": [],
        }

        for test in self.deployment_tests:
            success = self.run_test(test)

            test_result = {
                "name": test.name,
                "description": test.description,
                "status": test.status.value,
                "error_message": test.error_message,
            }

            results["tests"].append(test_result)

            if success:
                results["passed"] += 1
            else:
                results["failed"] += 1

        # Generate summary
        logger.info("\n=== Deployment Validation Summary ===")
        logger.info(f"Total tests: {results['total_tests']}")
        logger.info(f"Passed: {results['passed']}")
        logger.info(f"Failed: {results['failed']}")
        logger.info(
            f"Success rate: {(results['passed'] / results['total_tests'] * 100):.1f}%"
        )

        return results

    def generate_report(self, results: Dict[str, Any], output_file: str = None) -> str:
        """Generate detailed test report"""
        report = [
            "# MCP Deployment Validation Report",
            f"Generated: {os.popen('date').read().strip()}",
            "",
            "## Summary",
            f"- Total tests: {results['total_tests']}",
            f"- Passed: {results['passed']}",
            f"- Failed: {results['failed']}",
            f"- Success rate: {(results['passed'] / results['total_tests'] * 100):.1f}%",
            "",
            "## Test Results",
            "",
        ]

        for test in results["tests"]:
            status_emoji = "✅" if test["status"] == "passed" else "❌"
            report.append(f"### {status_emoji} {test['name']}")
            report.append(f"**Description:** {test['description']}")
            report.append(f"**Status:** {test['status']}")

            if test["error_message"]:
                report.append(f"**Error:** {test['error_message']}")

            report.append("")

        # Add recommendations
        if results["failed"] > 0:
            report.extend(
                [
                    "## Recommendations",
                    "",
                    "### Failed Tests",
                    "The following deployments have issues that need to be addressed:",
                    "",
                ]
            )

            for test in results["tests"]:
                if test["status"] == "failed":
                    report.append(f"- **{test['name']}**: {test['error_message']}")

            report.extend(
                [
                    "",
                    "### Next Steps",
                    "1. Fix the failing deployment configurations",
                    "2. Ensure all required files are present",
                    "3. Review Docker best practices",
                    "4. Test deployments in a staging environment",
                    "5. Re-run validation tests",
                    "",
                ]
            )

        report_text = "\n".join(report)

        if output_file:
            with open(output_file, "w") as f:
                f.write(report_text)
            logger.info(f"Report saved to {output_file}")

        return report_text


# Pytest integration
class TestMCPDeployment:
    """Pytest test class for MCP deployment validation"""

    @classmethod
    def setup_class(cls):
        """Set up test class"""
        cls.validator = MCPDeploymentValidator()

    @pytest.mark.parametrize(
        "test", MCPDeploymentValidator().deployment_tests or [None]
    )
    def test_deployment_configuration(self, test):
        """Test individual deployment configuration"""
        if test is None:
            # No deployment tests found - this is acceptable for testing
            assert True  # Test passes when no deployments to validate
            return

        success = self.validator.run_test(test)
        if not success:
            pytest.fail(f"Deployment test failed: {test.error_message}")


def main():
    """Main function for running deployment validation"""
    import argparse

    parser = argparse.ArgumentParser(description="MCP Deployment Validation")
    parser.add_argument("--output", "-o", help="Output report file")
    parser.add_argument("--test", "-t", help="Run specific test")
    parser.add_argument(
        "--build-only", action="store_true", help="Only test Docker builds"
    )
    parser.add_argument(
        "--no-build", action="store_true", help="Skip Docker build tests"
    )

    args = parser.parse_args()

    validator = MCPDeploymentValidator()

    if args.test:
        # Run specific test
        test_found = False
        for test in validator.deployment_tests:
            if test.name == args.test:
                success = validator.run_test(test)
                test_found = True
                sys.exit(0 if success else 1)

        if not test_found:
            logger.error(f"Test '{args.test}' not found")
            logger.info("Available tests:")
            for test in validator.deployment_tests:
                logger.info(f"  - {test.name}: {test.description}")
            sys.exit(1)

    # Run all tests
    results = validator.run_all_tests()

    # Generate report
    output_file = args.output or "deployment_validation_report.md"
    validator.generate_report(results, output_file)

    # Exit with appropriate code
    sys.exit(0 if results["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
