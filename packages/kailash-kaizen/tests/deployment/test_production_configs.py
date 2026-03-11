"""Tests for production configurations and deployments.

PROD-002: Environment Configuration Management
PROD-003: Example Deployments
PROD-004: Kubernetes Manifests

Following TDD methodology - Tests written FIRST before implementation.
"""

import subprocess
from pathlib import Path

import pytest
import yaml


# Helper to get project root
def get_project_root():
    """Get absolute path to project root."""
    return Path(__file__).parent.parent.parent.resolve()


class TestEnvironmentConfigs:
    """Test PROD-002: Environment configuration management."""

    def test_env_example_exists(self):
        """PROD-002.1: .env.example template exists."""
        project_root = get_project_root()
        env_example = project_root / ".env.example"
        assert env_example.exists(), ".env.example must exist in project root"

    def test_env_configs_exist(self):
        """PROD-002.2: Config files exist for all environments."""
        project_root = get_project_root()

        assert (
            project_root / "config" / "dev.env"
        ).exists(), "config/dev.env must exist"
        assert (
            project_root / "config" / "staging.env"
        ).exists(), "config/staging.env must exist"
        assert (
            project_root / "config" / "prod.env"
        ).exists(), "config/prod.env must exist"

    def test_env_configs_have_required_vars(self):
        """PROD-002.3: Environment configs contain all required variables."""
        project_root = get_project_root()

        # Core required variables for any Kaizen deployment
        required_vars = [
            "KAIZEN_ENV",  # Environment name (dev/staging/prod)
            "LOG_LEVEL",  # Logging level
            "OPENAI_API_KEY",  # LLM provider key
            "ANTHROPIC_API_KEY",  # Alternative LLM provider
        ]

        env_files = [
            project_root / "config" / "dev.env",
            project_root / "config" / "staging.env",
            project_root / "config" / "prod.env",
        ]

        for env_file in env_files:
            with open(env_file) as f:
                content = f.read()
                for var in required_vars:
                    assert var in content, f"{var} missing in {env_file.name}"

    def test_env_example_has_all_variables(self):
        """PROD-002.4: .env.example contains all possible variables."""
        project_root = get_project_root()

        # All variables that should be documented
        all_vars = [
            "KAIZEN_ENV",
            "LOG_LEVEL",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "DATABASE_URL",
            "REDIS_URL",
            "MAX_WORKERS",
            "TIMEOUT",
        ]

        env_example = project_root / ".env.example"
        with open(env_example) as f:
            content = f.read()
            for var in all_vars:
                assert var in content, f"{var} missing in .env.example"

    def test_env_configs_no_secrets(self):
        """PROD-002.5: Config files don't contain real secrets."""
        project_root = get_project_root()

        env_files = [
            project_root / "config" / "dev.env",
            project_root / "config" / "staging.env",
            project_root / "config" / "prod.env",
        ]

        # Patterns that indicate real secrets

        for env_file in env_files:
            with open(env_file) as f:
                content = f.read()
                # Should use placeholders like "your-key-here" or "${VAR_NAME}"
                assert (
                    "your-" in content.lower() or "${" in content
                ), f"{env_file.name} should use placeholders for secrets"

    def test_env_validation_script_exists(self):
        """PROD-002.6: Environment validation script exists."""
        project_root = get_project_root()
        validate_script = project_root / "scripts" / "validate_env.py"
        assert validate_script.exists(), "scripts/validate_env.py must exist"

    def test_env_validation_script_works(self):
        """PROD-002.7: Environment validation script validates configs."""
        project_root = get_project_root()

        result = subprocess.run(
            ["python", "scripts/validate_env.py", "--env", "dev"],
            capture_output=True,
            text=True,
            cwd=project_root,
        )

        assert result.returncode == 0, f"Validation failed: {result.stderr}"
        assert (
            "VALID" in result.stdout or "OK" in result.stdout
        ), "Validation script should confirm config is valid"


class TestExampleDeployments:
    """Test PROD-003: Example deployment scenarios."""

    def test_deployment_examples_directory_exists(self):
        """PROD-003.1: Deployment examples directory exists."""
        project_root = get_project_root()
        examples_dir = project_root / "examples" / "deployment"
        assert examples_dir.exists(), "examples/deployment/ must exist"

    def test_qa_agent_example_exists(self):
        """PROD-003.2: Simple QA agent deployment example exists."""
        project_root = get_project_root()
        qa_dir = project_root / "examples" / "deployment" / "simple-qa"

        assert qa_dir.exists(), "examples/deployment/simple-qa/ must exist"
        assert (qa_dir / "docker-compose.yml").exists(), "docker-compose.yml must exist"
        assert (qa_dir / "README.md").exists(), "README.md must exist"
        assert (qa_dir / ".env.example").exists(), ".env.example must exist"

    def test_multi_agent_example_exists(self):
        """PROD-003.3: Multi-agent deployment example exists."""
        project_root = get_project_root()
        multi_dir = project_root / "examples" / "deployment" / "multi-agent"

        assert multi_dir.exists(), "examples/deployment/multi-agent/ must exist"
        assert (
            multi_dir / "docker-compose.yml"
        ).exists(), "docker-compose.yml must exist"
        assert (multi_dir / "README.md").exists(), "README.md must exist"

    def test_rag_agent_example_exists(self):
        """PROD-003.4: RAG agent deployment example exists."""
        project_root = get_project_root()
        rag_dir = project_root / "examples" / "deployment" / "rag-agent"

        assert rag_dir.exists(), "examples/deployment/rag-agent/ must exist"
        assert (
            rag_dir / "docker-compose.yml"
        ).exists(), "docker-compose.yml must exist"
        assert (rag_dir / "README.md").exists(), "README.md must exist"

    def test_mcp_integration_example_exists(self):
        """PROD-003.5: MCP integration deployment example exists."""
        project_root = get_project_root()
        mcp_dir = project_root / "examples" / "deployment" / "mcp-integration"

        assert mcp_dir.exists(), "examples/deployment/mcp-integration/ must exist"
        assert (
            mcp_dir / "docker-compose.yml"
        ).exists(), "docker-compose.yml must exist"
        assert (mcp_dir / "README.md").exists(), "README.md must exist"

    def test_qa_agent_compose_valid(self):
        """PROD-003.6: QA agent docker-compose.yml is valid YAML."""
        project_root = get_project_root()
        compose_file = (
            project_root
            / "examples"
            / "deployment"
            / "simple-qa"
            / "docker-compose.yml"
        )

        with open(compose_file) as f:
            data = yaml.safe_load(f)
            assert "services" in data, "docker-compose.yml must have services"
            assert (
                "kaizen" in data["services"] or "qa-agent" in data["services"]
            ), "Must have kaizen or qa-agent service"

    def test_qa_agent_readme_has_instructions(self):
        """PROD-003.7: QA agent README has deployment instructions."""
        project_root = get_project_root()
        readme = project_root / "examples" / "deployment" / "simple-qa" / "README.md"

        with open(readme) as f:
            content = f.read()
            assert (
                "docker-compose up" in content.lower()
            ), "README must have docker-compose up command"
            assert (
                "environment" in content.lower() or "env" in content.lower()
            ), "README must mention environment configuration"

    @pytest.mark.slow
    def test_qa_agent_deployment_builds(self):
        """PROD-003.8: QA agent deployment builds successfully."""
        project_root = get_project_root()
        qa_dir = project_root / "examples" / "deployment" / "simple-qa"

        result = subprocess.run(
            ["docker-compose", "build"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=qa_dir,
        )

        assert result.returncode == 0, f"docker-compose build failed: {result.stderr}"

    @pytest.mark.slow
    def test_multi_agent_deployment_builds(self):
        """PROD-003.9: Multi-agent deployment builds successfully."""
        project_root = get_project_root()
        multi_dir = project_root / "examples" / "deployment" / "multi-agent"

        result = subprocess.run(
            ["docker-compose", "build"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=multi_dir,
        )

        assert result.returncode == 0, f"docker-compose build failed: {result.stderr}"


class TestKubernetesManifests:
    """Test PROD-004: Kubernetes deployment manifests."""

    def test_k8s_directory_exists(self):
        """PROD-004.1: Kubernetes manifests directory exists."""
        project_root = get_project_root()
        k8s_dir = project_root / "k8s"
        assert k8s_dir.exists(), "k8s/ directory must exist"

    def test_k8s_manifests_exist(self):
        """PROD-004.2: All required Kubernetes manifests exist."""
        project_root = get_project_root()
        k8s_dir = project_root / "k8s"

        assert (k8s_dir / "deployment.yaml").exists(), "k8s/deployment.yaml must exist"
        assert (k8s_dir / "service.yaml").exists(), "k8s/service.yaml must exist"
        assert (k8s_dir / "configmap.yaml").exists(), "k8s/configmap.yaml must exist"

    def test_deployment_manifest_valid_yaml(self):
        """PROD-004.3: Deployment manifest is valid YAML."""
        project_root = get_project_root()
        deployment = project_root / "k8s" / "deployment.yaml"

        with open(deployment) as f:
            docs = list(yaml.safe_load_all(f))
            assert len(docs) > 0, "deployment.yaml is empty"

            for doc in docs:
                assert "apiVersion" in doc, "deployment.yaml missing apiVersion"
                assert "kind" in doc, "deployment.yaml missing kind"
                assert doc["kind"] == "Deployment", "Must be a Deployment kind"

    def test_service_manifest_valid_yaml(self):
        """PROD-004.4: Service manifest is valid YAML."""
        project_root = get_project_root()
        service = project_root / "k8s" / "service.yaml"

        with open(service) as f:
            docs = list(yaml.safe_load_all(f))
            assert len(docs) > 0, "service.yaml is empty"

            for doc in docs:
                assert "apiVersion" in doc, "service.yaml missing apiVersion"
                assert "kind" in doc, "service.yaml missing kind"
                assert doc["kind"] == "Service", "Must be a Service kind"

    def test_configmap_manifest_valid_yaml(self):
        """PROD-004.5: ConfigMap manifest is valid YAML."""
        project_root = get_project_root()
        configmap = project_root / "k8s" / "configmap.yaml"

        with open(configmap) as f:
            docs = list(yaml.safe_load_all(f))
            assert len(docs) > 0, "configmap.yaml is empty"

            for doc in docs:
                assert "apiVersion" in doc, "configmap.yaml missing apiVersion"
                assert "kind" in doc, "configmap.yaml missing kind"
                assert doc["kind"] == "ConfigMap", "Must be a ConfigMap kind"

    def test_deployment_has_resource_limits(self):
        """PROD-004.6: Deployment has resource limits configured."""
        project_root = get_project_root()
        deployment = project_root / "k8s" / "deployment.yaml"

        with open(deployment) as f:
            doc = yaml.safe_load(f)

            containers = doc["spec"]["template"]["spec"]["containers"]
            assert len(containers) > 0, "Deployment must have at least one container"

            for container in containers:
                assert (
                    "resources" in container
                ), f"Container {container['name']} missing resources"
                assert (
                    "limits" in container["resources"]
                ), f"Container {container['name']} missing resource limits"
                assert (
                    "requests" in container["resources"]
                ), f"Container {container['name']} missing resource requests"

    def test_deployment_has_health_probes(self):
        """PROD-004.7: Deployment has health probes configured."""
        project_root = get_project_root()
        deployment = project_root / "k8s" / "deployment.yaml"

        with open(deployment) as f:
            doc = yaml.safe_load(f)

            containers = doc["spec"]["template"]["spec"]["containers"]

            for container in containers:
                # At least one probe should be configured
                has_liveness = "livenessProbe" in container
                has_readiness = "readinessProbe" in container

                assert (
                    has_liveness or has_readiness
                ), f"Container {container['name']} should have health probes"

    def test_deployment_uses_configmap(self):
        """PROD-004.8: Deployment references ConfigMap for configuration."""
        project_root = get_project_root()
        deployment = project_root / "k8s" / "deployment.yaml"

        with open(deployment) as f:
            doc = yaml.safe_load(f)

            # Check if deployment uses envFrom or env with configMapRef
            spec = doc["spec"]["template"]["spec"]
            containers = spec["containers"]

            uses_configmap = False
            for container in containers:
                if "envFrom" in container:
                    for env_source in container["envFrom"]:
                        if "configMapRef" in env_source:
                            uses_configmap = True
                            break

                if "env" in container:
                    for env_var in container["env"]:
                        if (
                            "valueFrom" in env_var
                            and "configMapKeyRef" in env_var["valueFrom"]
                        ):
                            uses_configmap = True
                            break

            assert (
                uses_configmap
            ), "Deployment should reference ConfigMap for configuration"

    def test_k8s_readme_exists(self):
        """PROD-004.9: Kubernetes deployment README exists."""
        project_root = get_project_root()
        k8s_readme = project_root / "k8s" / "README.md"
        assert k8s_readme.exists(), "k8s/README.md must exist"

    def test_k8s_readme_has_instructions(self):
        """PROD-004.10: Kubernetes README has deployment instructions."""
        project_root = get_project_root()
        k8s_readme = project_root / "k8s" / "README.md"

        with open(k8s_readme) as f:
            content = f.read()
            assert "kubectl apply" in content, "README must have kubectl apply command"
            assert "namespace" in content.lower(), "README should mention namespace"
            assert (
                "configmap" in content.lower()
            ), "README should mention ConfigMap setup"
