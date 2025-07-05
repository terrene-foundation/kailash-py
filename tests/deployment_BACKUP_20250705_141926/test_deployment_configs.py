#!/usr/bin/env python3
"""
Quick MCP Deployment Configuration Validation

This lightweight test validates deployment configurations without Docker builds.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DeploymentConfigValidator:
    """Lightweight deployment configuration validator"""

    def __init__(self, project_root: str = None):
        self.project_root = (
            Path(project_root) if project_root else Path(__file__).parent.parent.parent
        )
        self.issues = []
        self.warnings = []

    def validate_dockerfile(self, dockerfile_path: str) -> Dict[str, Any]:
        """Validate Dockerfile configuration"""
        issues = []
        warnings = []

        full_path = self.project_root / dockerfile_path
        if not full_path.exists():
            issues.append(f"Dockerfile not found: {dockerfile_path}")
            return {"issues": issues, "warnings": warnings}

        try:
            with open(full_path, "r") as f:
                content = f.read()

            # Check for required instructions
            required_instructions = ["FROM", "WORKDIR", "COPY", "EXPOSE", "CMD"]
            for instruction in required_instructions:
                if instruction not in content:
                    warnings.append(f"Missing {instruction} instruction")

            # Check for security best practices
            if "USER root" in content or "USER 0" in content:
                warnings.append("Running as root user (security risk)")

            if "USER" not in content:
                warnings.append("No USER instruction found (should run as non-root)")

            # Check for HEALTHCHECK
            if "HEALTHCHECK" not in content:
                warnings.append("Missing HEALTHCHECK instruction")

            # Check for cleanup
            if (
                "apt-get update" in content
                and "rm -rf /var/lib/apt/lists/*" not in content
            ):
                warnings.append("apt cache not cleaned up")

            if "pip install" in content and "--no-cache-dir" not in content:
                warnings.append("pip cache not disabled")

        except Exception as e:
            issues.append(f"Error reading Dockerfile: {str(e)}")

        return {"issues": issues, "warnings": warnings}

    def validate_docker_compose(self, compose_path: str) -> Dict[str, Any]:
        """Validate Docker Compose configuration"""
        issues = []
        warnings = []

        full_path = self.project_root / compose_path
        if not full_path.exists():
            issues.append(f"Docker Compose file not found: {compose_path}")
            return {"issues": issues, "warnings": warnings}

        try:
            with open(full_path, "r") as f:
                compose_config = yaml.safe_load(f)

            # Check basic structure
            if "services" not in compose_config:
                issues.append("Missing 'services' section")
                return {"issues": issues, "warnings": warnings}

            services = compose_config["services"]

            for service_name, service_config in services.items():
                # Check for health checks
                if "healthcheck" not in service_config:
                    warnings.append(f"Service '{service_name}' missing healthcheck")

                # Check for restart policy
                if "restart" not in service_config:
                    warnings.append(f"Service '{service_name}' missing restart policy")

                # Check for resource limits
                if (
                    "deploy" not in service_config
                    or "resources" not in service_config.get("deploy", {})
                ):
                    warnings.append(f"Service '{service_name}' missing resource limits")

                # Check for hardcoded secrets
                env_vars = service_config.get("environment", [])
                if isinstance(env_vars, dict):
                    env_vars = [f"{k}={v}" for k, v in env_vars.items()]

                for env_var in env_vars:
                    if isinstance(env_var, str) and "=" in env_var:
                        key, value = env_var.split("=", 1)
                        if any(
                            secret in key.lower()
                            for secret in ["password", "secret", "key", "token"]
                        ):
                            if not value.startswith("${"):
                                warnings.append(
                                    f"Service '{service_name}' has hardcoded secret: {key}"
                                )

        except yaml.YAMLError as e:
            issues.append(f"YAML syntax error: {str(e)}")
        except Exception as e:
            issues.append(f"Error reading Docker Compose file: {str(e)}")

        return {"issues": issues, "warnings": warnings}

    def validate_required_files(
        self, app_path: str, required_files: List[str]
    ) -> Dict[str, Any]:
        """Validate required files exist"""
        issues = []
        warnings = []

        for file_path in required_files:
            full_path = self.project_root / file_path
            if not full_path.exists():
                issues.append(f"Required file missing: {file_path}")

        return {"issues": issues, "warnings": warnings}

    def validate_app_deployment(
        self,
        app_name: str,
        app_path: str,
        dockerfile_path: str,
        compose_path: str = None,
        required_files: List[str] = None,
    ) -> Dict[str, Any]:
        """Validate a complete app deployment configuration"""
        result = {
            "name": app_name,
            "path": app_path,
            "issues": [],
            "warnings": [],
            "status": "unknown",
        }

        # Validate required files
        if required_files:
            file_result = self.validate_required_files(app_path, required_files)
            result["issues"].extend(file_result["issues"])
            result["warnings"].extend(file_result["warnings"])

        # Validate Dockerfile
        dockerfile_result = self.validate_dockerfile(dockerfile_path)
        result["issues"].extend(dockerfile_result["issues"])
        result["warnings"].extend(dockerfile_result["warnings"])

        # Validate Docker Compose
        if compose_path:
            compose_result = self.validate_docker_compose(compose_path)
            result["issues"].extend(compose_result["issues"])
            result["warnings"].extend(compose_result["warnings"])

        # Determine status
        if result["issues"]:
            result["status"] = "failed"
        elif result["warnings"]:
            result["status"] = "warnings"
        else:
            result["status"] = "passed"

        return result

    def validate_all_deployments(self) -> Dict[str, Any]:
        """Validate all MCP deployment configurations"""

        deployments = [
            {
                "name": "mcp-basic",
                "app_path": "apps/mcp",
                "dockerfile_path": "apps/mcp/Dockerfile",
                "compose_path": "apps/mcp/docker-compose.yml",
                "required_files": ["apps/mcp/requirements.txt", "apps/mcp/main.py"],
            },
            {
                "name": "mcp-ai-assistant",
                "app_path": "apps/mcp_ai_assistant",
                "dockerfile_path": "apps/mcp_ai_assistant/Dockerfile",
                "compose_path": "apps/mcp_ai_assistant/docker-compose.yml",
                "required_files": ["apps/mcp_ai_assistant/requirements.txt"],
            },
            {
                "name": "mcp-tools-server",
                "app_path": "apps/mcp_tools_server",
                "dockerfile_path": "apps/mcp_tools_server/Dockerfile",
                "compose_path": "apps/mcp_tools_server/docker-compose.yml",
                "required_files": ["apps/mcp_tools_server/requirements.txt"],
            },
            {
                "name": "mcp-data-pipeline",
                "app_path": "apps/mcp_data_pipeline",
                "dockerfile_path": "apps/mcp_data_pipeline/Dockerfile",
                "compose_path": "apps/mcp_data_pipeline/docker-compose.yml",
                "required_files": ["apps/mcp_data_pipeline/requirements.txt"],
            },
            {
                "name": "mcp-enterprise-gateway",
                "app_path": "apps/mcp_enterprise_gateway",
                "dockerfile_path": "apps/mcp_enterprise_gateway/Dockerfile",
                "compose_path": "apps/mcp_enterprise_gateway/docker-compose.yml",
                "required_files": ["apps/mcp_enterprise_gateway/requirements.txt"],
            },
            {
                "name": "mcp-integration-patterns",
                "app_path": "apps/mcp_integration_patterns/production/docker_deployment",
                "dockerfile_path": "apps/mcp_integration_patterns/production/docker_deployment/Dockerfile.kailash-server",
                "compose_path": "apps/mcp_integration_patterns/production/docker_deployment/docker-compose.yml",
                "required_files": [
                    "apps/mcp_integration_patterns/production/docker_deployment/requirements.txt"
                ],
            },
        ]

        results = {
            "total": len(deployments),
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "deployments": [],
        }

        for deployment in deployments:
            logger.info(f"Validating {deployment['name']}...")

            result = self.validate_app_deployment(
                deployment["name"],
                deployment["app_path"],
                deployment["dockerfile_path"],
                deployment.get("compose_path"),
                deployment.get("required_files", []),
            )

            results["deployments"].append(result)

            if result["status"] == "passed":
                results["passed"] += 1
                logger.info(f"✅ {deployment['name']}: PASSED")
            elif result["status"] == "warnings":
                results["warnings"] += 1
                logger.warning(
                    f"⚠️ {deployment['name']}: WARNINGS ({len(result['warnings'])} warnings)"
                )
            else:
                results["failed"] += 1
                logger.error(
                    f"❌ {deployment['name']}: FAILED ({len(result['issues'])} issues)"
                )

        return results

    def generate_report(self, results: Dict[str, Any]) -> str:
        """Generate validation report"""
        report = [
            "# MCP Deployment Configuration Validation Report",
            f"Generated: {os.popen('date').read().strip()}",
            "",
            "## Summary",
            f"- Total deployments: {results['total']}",
            f"- Passed: {results['passed']}",
            f"- With warnings: {results['warnings']}",
            f"- Failed: {results['failed']}",
            "",
            "## Results",
            "",
        ]

        for deployment in results["deployments"]:
            status_emoji = {"passed": "✅", "warnings": "⚠️", "failed": "❌"}
            emoji = status_emoji.get(deployment["status"], "❓")

            report.append(f"### {emoji} {deployment['name']}")
            report.append(f"**Path:** {deployment['path']}")
            report.append(f"**Status:** {deployment['status']}")

            if deployment["issues"]:
                report.append("**Issues:**")
                for issue in deployment["issues"]:
                    report.append(f"- {issue}")

            if deployment["warnings"]:
                report.append("**Warnings:**")
                for warning in deployment["warnings"]:
                    report.append(f"- {warning}")

            report.append("")

        if results["failed"] > 0:
            report.extend(
                [
                    "## Recommendations",
                    "",
                    "### Critical Issues",
                    "The following deployments have critical issues that must be fixed:",
                    "",
                ]
            )

            for deployment in results["deployments"]:
                if deployment["status"] == "failed":
                    report.append(f"**{deployment['name']}:**")
                    for issue in deployment["issues"]:
                        report.append(f"- {issue}")
                    report.append("")

        if results["warnings"] > 0:
            report.extend(
                [
                    "### Improvement Recommendations",
                    "The following deployments have configuration warnings:",
                    "",
                ]
            )

            for deployment in results["deployments"]:
                if deployment["status"] == "warnings":
                    report.append(
                        f"**{deployment['name']}:** {len(deployment['warnings'])} warnings"
                    )

        return "\n".join(report)


def main():
    """Main function"""
    validator = DeploymentConfigValidator()

    logger.info("Starting MCP deployment configuration validation")
    results = validator.validate_all_deployments()

    # Generate report
    report = validator.generate_report(results)

    # Save report
    report_file = "deployment_config_validation_report.md"
    with open(report_file, "w") as f:
        f.write(report)

    logger.info(f"Report saved to {report_file}")

    # Print summary
    logger.info("\n=== Validation Summary ===")
    logger.info(f"Total: {results['total']}")
    logger.info(f"Passed: {results['passed']}")
    logger.info(f"Warnings: {results['warnings']}")
    logger.info(f"Failed: {results['failed']}")

    if results["failed"] > 0:
        logger.error("Some deployments have critical issues!")
        sys.exit(1)
    else:
        logger.info("All deployments passed basic validation!")
        sys.exit(0)


if __name__ == "__main__":
    main()
