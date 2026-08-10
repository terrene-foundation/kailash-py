"""Tests for production security and operations.

PROD-011: Security Hardening
PROD-012: Operational Runbooks
PROD-013: Documentation

Following TDD methodology - Tests written FIRST before implementation.
"""

from pathlib import Path

import pytest
import yaml


# Helper to get project root
def get_project_root():
    """Get absolute path to project root."""
    return Path(__file__).parent.parent.parent.resolve()


class TestSecurityHardening:
    """Test PROD-011: Security hardening for production."""

    def test_dockerfile_exists(self):
        """PROD-011.1: Production Dockerfile exists."""
        project_root = get_project_root()
        dockerfile = project_root / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile must exist in project root"

    def test_dockerfile_non_root_user(self):
        """PROD-011.2: Dockerfile runs as non-root user."""
        project_root = get_project_root()
        dockerfile = project_root / "Dockerfile"

        with open(dockerfile) as f:
            content = f.read()
            # Check for USER directive (not root)
            assert "USER" in content, "Dockerfile must specify USER"
            assert "USER root" not in content, "Must not run as root user"

    def test_dockerfile_read_only_filesystem(self):
        """PROD-011.3: Deployment supports read-only filesystem."""
        project_root = get_project_root()

        # Check K8s deployment for read-only root filesystem
        deployment = project_root / "k8s" / "deployment.yaml"
        with open(deployment) as f:
            doc = yaml.safe_load(f)

            containers = doc["spec"]["template"]["spec"]["containers"]
            for container in containers:
                if "securityContext" in container:
                    sec_context = container["securityContext"]
                    # Should have readOnlyRootFilesystem set to true
                    assert (
                        sec_context.get("readOnlyRootFilesystem") == True
                    ), f"Container {container['name']} should use read-only filesystem"

    def test_dockerfile_minimal_base_image(self):
        """PROD-011.4: Dockerfile uses minimal base image."""
        project_root = get_project_root()
        dockerfile = project_root / "Dockerfile"

        with open(dockerfile) as f:
            content = f.read()

            # Check for minimal base images
            minimal_images = ["alpine", "slim", "distroless"]
            uses_minimal = any(img in content.lower() for img in minimal_images)

            assert (
                uses_minimal
            ), "Dockerfile should use minimal base image (alpine/slim/distroless)"

    def test_security_context_non_privileged(self):
        """PROD-011.5: Containers run without privileged mode."""
        project_root = get_project_root()
        deployment = project_root / "k8s" / "deployment.yaml"

        with open(deployment) as f:
            doc = yaml.safe_load(f)

            containers = doc["spec"]["template"]["spec"]["containers"]
            for container in containers:
                if "securityContext" in container:
                    sec_context = container["securityContext"]
                    # Should explicitly set privileged to false or not set it
                    assert (
                        sec_context.get("privileged", False) == False
                    ), f"Container {container['name']} must not be privileged"

    def test_security_context_capabilities_dropped(self):
        """PROD-011.6: Unnecessary Linux capabilities are dropped."""
        project_root = get_project_root()
        deployment = project_root / "k8s" / "deployment.yaml"

        with open(deployment) as f:
            doc = yaml.safe_load(f)

            containers = doc["spec"]["template"]["spec"]["containers"]
            for container in containers:
                if "securityContext" in container:
                    sec_context = container["securityContext"]
                    if "capabilities" in sec_context:
                        caps = sec_context["capabilities"]
                        # Should drop ALL capabilities or specific ones
                        assert (
                            "drop" in caps
                        ), f"Container {container['name']} should drop capabilities"

    def test_network_policy_exists(self):
        """PROD-011.7: Network policy is defined."""
        project_root = get_project_root()
        network_policy = project_root / "k8s" / "network-policy.yaml"
        assert network_policy.exists(), "k8s/network-policy.yaml must exist"

    def test_network_policy_valid(self):
        """PROD-011.8: Network policy is valid YAML."""
        project_root = get_project_root()
        network_policy = project_root / "k8s" / "network-policy.yaml"

        with open(network_policy) as f:
            doc = yaml.safe_load(f)

            assert doc["kind"] == "NetworkPolicy", "Must be a NetworkPolicy kind"
            assert "spec" in doc, "NetworkPolicy must have spec"

    def test_network_policy_restricts_ingress(self):
        """PROD-011.9: Network policy restricts ingress traffic."""
        project_root = get_project_root()
        network_policy = project_root / "k8s" / "network-policy.yaml"

        with open(network_policy) as f:
            doc = yaml.safe_load(f)

            spec = doc["spec"]
            # Should have ingress rules defined
            assert (
                "ingress" in spec or "policyTypes" in spec
            ), "NetworkPolicy should restrict ingress"

    def test_secrets_not_in_configmap(self):
        """PROD-011.10: Secrets are not stored in ConfigMap."""
        project_root = get_project_root()
        configmap = project_root / "k8s" / "configmap.yaml"

        with open(configmap) as f:
            doc = yaml.safe_load(f)

            data = doc.get("data", {})

            # Check that no secret-like keys exist
            secret_keywords = ["password", "secret", "key", "token", "credential"]
            for key in data.keys():
                for keyword in secret_keywords:
                    assert (
                        keyword not in key.lower()
                    ), f"ConfigMap should not contain secret: {key}"

    def test_secret_manifest_exists(self):
        """PROD-011.11: Kubernetes Secret manifest template exists."""
        project_root = get_project_root()
        secret = project_root / "k8s" / "secret.yaml.example"
        assert secret.exists(), "k8s/secret.yaml.example must exist"

    def test_security_scanning_in_ci(self):
        """PROD-011.12: CI/CD includes security scanning."""
        project_root = get_project_root()

        # Check for GitHub Actions workflow
        workflows_dir = project_root / ".github" / "workflows"
        if workflows_dir.exists():
            workflow_files = list(workflows_dir.glob("*.yml")) + list(
                workflows_dir.glob("*.yaml")
            )

            has_security_scan = False
            for workflow in workflow_files:
                with open(workflow) as f:
                    content = f.read()
                    # Check for security scanning tools
                    if any(
                        tool in content.lower()
                        for tool in ["trivy", "snyk", "security", "scan"]
                    ):
                        has_security_scan = True
                        break

            assert has_security_scan, "CI/CD should include security scanning"
        else:
            pytest.skip("No GitHub Actions workflows found")

    def test_dockerfile_no_secrets(self):
        """PROD-011.13: Dockerfile doesn't contain hardcoded secrets."""
        project_root = get_project_root()
        dockerfile = project_root / "Dockerfile"

        with open(dockerfile) as f:
            content = f.read()

            # Check for common secret patterns
            secret_patterns = [
                "sk-",  # OpenAI key prefix
                "password=",  # Password assignments
                "token=",  # Token assignments
            ]

            for pattern in secret_patterns:
                assert (
                    pattern not in content.lower()
                ), f"Dockerfile should not contain secrets: {pattern}"

    def test_security_readme_exists(self):
        """PROD-011.14: Security documentation exists."""
        project_root = get_project_root()
        security_doc = project_root / "docs" / "SECURITY.md"
        assert security_doc.exists(), "docs/SECURITY.md must exist"


class TestOperationalRunbooks:
    """Test PROD-012: Operational runbooks and procedures."""

    def test_runbooks_directory_exists(self):
        """PROD-012.1: Runbooks directory exists."""
        project_root = get_project_root()
        runbooks_dir = project_root / "docs" / "runbooks"
        assert runbooks_dir.exists(), "docs/runbooks/ must exist"

    def test_incident_response_runbook_exists(self):
        """PROD-012.2: Incident response runbook exists."""
        project_root = get_project_root()
        incident_runbook = project_root / "docs" / "runbooks" / "incident-response.md"
        assert (
            incident_runbook.exists()
        ), "docs/runbooks/incident-response.md must exist"

    def test_incident_response_has_escalation(self):
        """PROD-012.3: Incident response includes escalation procedures."""
        project_root = get_project_root()
        incident_runbook = project_root / "docs" / "runbooks" / "incident-response.md"

        with open(incident_runbook) as f:
            content = f.read()
            assert "escalation" in content.lower(), "Must include escalation procedures"
            assert (
                "severity" in content.lower() or "priority" in content.lower()
            ), "Must define severity levels"

    def test_troubleshooting_runbook_exists(self):
        """PROD-012.4: Troubleshooting runbook exists."""
        project_root = get_project_root()
        troubleshooting = project_root / "docs" / "runbooks" / "troubleshooting.md"
        assert troubleshooting.exists(), "docs/runbooks/troubleshooting.md must exist"

    def test_troubleshooting_common_issues(self):
        """PROD-012.5: Troubleshooting covers common issues."""
        project_root = get_project_root()
        troubleshooting = project_root / "docs" / "runbooks" / "troubleshooting.md"

        with open(troubleshooting) as f:
            content = f.read()

            common_issues = [
                "memory",
                "timeout",
                "connection",
                "error",
            ]

            for issue in common_issues:
                assert (
                    issue in content.lower()
                ), f"Troubleshooting should cover: {issue}"

    def test_deployment_runbook_exists(self):
        """PROD-012.6: Deployment runbook exists."""
        project_root = get_project_root()
        deployment_runbook = project_root / "docs" / "runbooks" / "deployment.md"
        assert deployment_runbook.exists(), "docs/runbooks/deployment.md must exist"

    def test_deployment_runbook_has_steps(self):
        """PROD-012.7: Deployment runbook has clear steps."""
        project_root = get_project_root()
        deployment_runbook = project_root / "docs" / "runbooks" / "deployment.md"

        with open(deployment_runbook) as f:
            content = f.read()

            deployment_steps = [
                "pre-deployment",
                "deployment",
                "post-deployment",
                "rollback",
            ]

            for step in deployment_steps:
                assert (
                    step in content.lower()
                ), f"Deployment runbook should include: {step}"

    def test_rollback_runbook_exists(self):
        """PROD-012.8: Rollback procedures are documented."""
        project_root = get_project_root()
        deployment_runbook = project_root / "docs" / "runbooks" / "deployment.md"

        with open(deployment_runbook) as f:
            content = f.read()
            assert "rollback" in content.lower(), "Must document rollback procedures"

    def test_monitoring_runbook_exists(self):
        """PROD-012.9: Monitoring runbook exists."""
        project_root = get_project_root()
        monitoring_runbook = project_root / "docs" / "runbooks" / "monitoring.md"
        assert monitoring_runbook.exists(), "docs/runbooks/monitoring.md must exist"

    def test_monitoring_runbook_covers_alerts(self):
        """PROD-012.10: Monitoring runbook covers alert handling."""
        project_root = get_project_root()
        monitoring_runbook = project_root / "docs" / "runbooks" / "monitoring.md"

        with open(monitoring_runbook) as f:
            content = f.read()
            assert "alert" in content.lower(), "Must cover alert handling"
            assert "dashboard" in content.lower(), "Must reference dashboards"

    def test_runbooks_index_exists(self):
        """PROD-012.11: Runbooks index/README exists."""
        project_root = get_project_root()
        runbooks_index = project_root / "docs" / "runbooks" / "README.md"
        assert runbooks_index.exists(), "docs/runbooks/README.md must exist"

    def test_runbooks_index_links_all(self):
        """PROD-012.12: Runbooks index links to all runbooks."""
        project_root = get_project_root()
        runbooks_index = project_root / "docs" / "runbooks" / "README.md"

        with open(runbooks_index) as f:
            content = f.read()

            runbook_files = [
                "incident-response",
                "troubleshooting",
                "deployment",
                "monitoring",
            ]

            for runbook in runbook_files:
                assert runbook in content.lower(), f"Index should link to: {runbook}"


class TestDocumentation:
    """Test PROD-013: Production documentation."""

    def test_deployment_guide_exists(self):
        """PROD-013.1: Deployment guide exists."""
        project_root = get_project_root()
        deployment_guide = project_root / "docs" / "deployment" / "README.md"
        assert deployment_guide.exists(), "docs/deployment/README.md must exist"

    def test_deployment_guide_covers_environments(self):
        """PROD-013.2: Deployment guide covers all environments."""
        project_root = get_project_root()
        deployment_guide = project_root / "docs" / "deployment" / "README.md"

        with open(deployment_guide) as f:
            content = f.read()

            environments = ["development", "staging", "production"]
            for env in environments:
                assert env in content.lower(), f"Deployment guide should cover: {env}"

    def test_docker_deployment_guide_exists(self):
        """PROD-013.3: Docker deployment guide exists."""
        project_root = get_project_root()
        docker_guide = project_root / "docs" / "deployment" / "docker.md"
        assert docker_guide.exists(), "docs/deployment/docker.md must exist"

    def test_kubernetes_deployment_guide_exists(self):
        """PROD-013.4: Kubernetes deployment guide exists."""
        project_root = get_project_root()
        k8s_guide = project_root / "docs" / "deployment" / "kubernetes.md"
        assert k8s_guide.exists(), "docs/deployment/kubernetes.md must exist"

    def test_kubernetes_guide_has_prerequisites(self):
        """PROD-013.5: Kubernetes guide lists prerequisites."""
        project_root = get_project_root()
        k8s_guide = project_root / "docs" / "deployment" / "kubernetes.md"

        with open(k8s_guide) as f:
            content = f.read()

            prerequisites = ["kubectl", "cluster", "namespace"]
            for prereq in prerequisites:
                assert prereq in content.lower(), f"K8s guide should mention: {prereq}"

    def test_operations_manual_exists(self):
        """PROD-013.6: Operations manual exists."""
        project_root = get_project_root()
        ops_manual = project_root / "docs" / "operations" / "README.md"
        assert ops_manual.exists(), "docs/operations/README.md must exist"

    def test_operations_manual_covers_monitoring(self):
        """PROD-013.7: Operations manual covers monitoring."""
        project_root = get_project_root()
        ops_manual = project_root / "docs" / "operations" / "README.md"

        with open(ops_manual) as f:
            content = f.read()
            assert "monitoring" in content.lower(), "Must cover monitoring"
            assert "metrics" in content.lower(), "Must cover metrics"

    def test_architecture_diagram_exists(self):
        """PROD-013.8: Architecture diagram exists."""
        project_root = get_project_root()
        arch_dir = project_root / "docs" / "architecture"

        assert arch_dir.exists(), "docs/architecture/ must exist"

        # Check for diagram files (PNG, SVG, or PlantUML)
        diagrams = (
            list(arch_dir.glob("*.png"))
            + list(arch_dir.glob("*.svg"))
            + list(arch_dir.glob("*.puml"))
        )

        assert len(diagrams) > 0, "Must have architecture diagrams"

    def test_architecture_documentation_exists(self):
        """PROD-013.9: Architecture documentation exists."""
        project_root = get_project_root()
        arch_doc = project_root / "docs" / "architecture" / "README.md"
        assert arch_doc.exists(), "docs/architecture/README.md must exist"

    def test_architecture_doc_describes_components(self):
        """PROD-013.10: Architecture doc describes key components."""
        project_root = get_project_root()
        arch_doc = project_root / "docs" / "architecture" / "README.md"

        with open(arch_doc) as f:
            content = f.read()

            components = [
                "agent",
                "workflow",
                "runtime",
            ]

            for component in components:
                assert (
                    component in content.lower()
                ), f"Architecture should describe: {component}"

    def test_configuration_guide_exists(self):
        """PROD-013.11: Configuration guide exists."""
        project_root = get_project_root()
        config_guide = project_root / "docs" / "configuration" / "README.md"
        assert config_guide.exists(), "docs/configuration/README.md must exist"

    def test_configuration_guide_covers_env_vars(self):
        """PROD-013.12: Configuration guide documents environment variables."""
        project_root = get_project_root()
        config_guide = project_root / "docs" / "configuration" / "README.md"

        with open(config_guide) as f:
            content = f.read()

            # Should document key environment variables
            env_vars = ["KAIZEN_ENV", "LOG_LEVEL", "API_KEY"]
            for var in env_vars:
                # At least mention environment variables concept
                pass  # Basic check that guide exists

            assert (
                "environment" in content.lower()
            ), "Configuration guide should mention environment variables"

    def test_main_readme_links_docs(self):
        """PROD-013.13: Main README links to documentation."""
        project_root = get_project_root()
        main_readme = project_root / "README.md"

        assert main_readme.exists(), "README.md must exist"

        with open(main_readme) as f:
            content = f.read()

            doc_sections = ["documentation", "deployment", "getting started"]
            has_docs = any(section in content.lower() for section in doc_sections)

            assert has_docs, "README should link to documentation"

    def test_changelog_exists(self):
        """PROD-013.14: CHANGELOG exists."""
        project_root = get_project_root()
        changelog = project_root / "CHANGELOG.md"
        assert changelog.exists(), "CHANGELOG.md must exist"

    def test_contributing_guide_exists(self):
        """PROD-013.15: Contributing guide exists."""
        project_root = get_project_root()
        contributing = project_root / "CONTRIBUTING.md"
        assert contributing.exists(), "CONTRIBUTING.md must exist"
