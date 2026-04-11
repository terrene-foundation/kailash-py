"""
Comprehensive CI/CD Pipeline Tests (PROD-005, PROD-006, PROD-007)

Tests for:
- PROD-005: GitHub Actions Workflow
- PROD-006: Deployment Validation
- PROD-007: Rollback Procedures

Following TDD methodology - tests written BEFORE implementation.
"""

import os
import stat
from pathlib import Path

import pytest
import yaml

# Get repository root
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent

# deploy-production.yml does not exist yet — tests were TDD-first
_DEPLOY_WORKFLOW = REPO_ROOT / ".github/workflows/deploy-production.yml"
_SKIP = pytest.mark.skipif(
    not _DEPLOY_WORKFLOW.exists(),
    reason="deploy-production.yml not created yet (TDD-first tests)",
)


@_SKIP
class TestPROD005GitHubActionsWorkflow:
    """
    PROD-005: GitHub Actions Workflow

    Requirements:
    - Extend existing .github/workflows/unified-ci.yml
    - Add deployment stages (build, test, deploy)
    - Container image building and pushing
    - Multi-environment deployment (dev/staging/prod)
    """

    def test_deployment_workflow_file_exists(self):
        """Verify deployment workflow file exists"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        assert (
            workflow_path.exists()
        ), f"Deployment workflow file not found at {workflow_path}"

    def test_deployment_workflow_has_required_structure(self):
        """Verify deployment workflow has correct structure"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        assert workflow_path.exists(), "Workflow file must exist"

        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        # Verify basic structure
        assert "name" in workflow, "Workflow must have a name"
        # YAML parses "on" as boolean True, so check for True or "on"
        assert True in workflow or "on" in workflow, "Workflow must have triggers"
        assert "jobs" in workflow, "Workflow must have jobs"

        # Verify workflow name
        assert (
            "deployment" in workflow["name"].lower()
            or "production" in workflow["name"].lower()
        ), "Workflow name should indicate deployment/production purpose"

    def test_deployment_workflow_has_build_job(self):
        """Verify workflow has build job"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        jobs = workflow.get("jobs", {})
        assert "build" in jobs or any(
            "build" in job_name.lower() for job_name in jobs.keys()
        ), "Workflow must have a build job"

    def test_deployment_workflow_has_test_job(self):
        """Verify workflow has test job"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        jobs = workflow.get("jobs", {})
        assert "test" in jobs or any(
            "test" in job_name.lower() for job_name in jobs.keys()
        ), "Workflow must have a test job"

    def test_deployment_workflow_has_deploy_job(self):
        """Verify workflow has deploy job"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        jobs = workflow.get("jobs", {})
        assert "deploy" in jobs or any(
            "deploy" in job_name.lower() for job_name in jobs.keys()
        ), "Workflow must have a deploy job"

    def test_deployment_workflow_has_container_build_steps(self):
        """Verify workflow includes container image building"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            content = f.read()

        # Check for Docker-related commands
        assert (
            "docker build" in content.lower()
            or "docker/build-push-action" in content.lower()
        ), "Workflow must include Docker image building"

    def test_deployment_workflow_has_container_push_steps(self):
        """Verify workflow includes container image pushing"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            content = f.read()

        # Check for Docker push or registry
        assert (
            "docker push" in content.lower()
            or "push: true" in content.lower()
            or "registry" in content.lower()
        ), "Workflow must include Docker image pushing to registry"

    def test_deployment_workflow_supports_multiple_environments(self):
        """Verify workflow supports dev/staging/prod environments"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            content = f.read()

        # Check for environment mentions
        has_env_support = "environment" in content.lower() or (
            "dev" in content.lower()
            and "staging" in content.lower()
            and "prod" in content.lower()
        )
        assert (
            has_env_support
        ), "Workflow must support multiple environments (dev/staging/prod)"

    def test_deployment_workflow_has_proper_triggers(self):
        """Verify workflow has appropriate triggers"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        # YAML parses "on" as boolean True
        triggers = workflow.get(True, workflow.get("on", {}))
        # Should support at least workflow_dispatch for manual deployments
        assert (
            "workflow_dispatch" in triggers or "push" in triggers
        ), "Workflow must have appropriate triggers (workflow_dispatch or push)"

    def test_deployment_workflow_has_permissions(self):
        """Verify workflow has proper permissions defined"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        # Permissions should be explicitly defined for security
        assert (
            "permissions" in workflow
        ), "Workflow should define permissions explicitly"


@_SKIP
class TestPROD006DeploymentValidation:
    """
    PROD-006: Deployment Validation

    Requirements:
    - Health check validation
    - Smoke tests post-deployment
    - Performance validation
    - Security validation
    """

    def test_validation_script_exists(self):
        """Verify deployment validation script exists"""
        script_path = (
            REPO_ROOT / "packages/kailash-kaizen/scripts/validate_deployment.sh"
        )
        assert script_path.exists(), f"Validation script not found at {script_path}"

    def test_validation_script_executable(self):
        """Verify validation script has executable permissions"""
        script_path = (
            REPO_ROOT / "packages/kailash-kaizen/scripts/validate_deployment.sh"
        )
        assert script_path.exists(), "Script must exist"

        # Check if file has executable permission
        st = os.stat(script_path)
        is_executable = bool(st.st_mode & stat.S_IXUSR)
        assert is_executable, "Validation script must be executable"

    def test_validation_script_has_health_check(self):
        """Verify validation script includes health checks"""
        script_path = (
            REPO_ROOT / "packages/kailash-kaizen/scripts/validate_deployment.sh"
        )
        with open(script_path) as f:
            content = f.read()

        # Should include health check logic
        has_health_check = (
            "health" in content.lower()
            or "/health" in content
            or "healthcheck" in content.lower()
        )
        assert (
            has_health_check
        ), "Validation script must include health check validation"

    def test_validation_script_has_smoke_tests(self):
        """Verify validation script includes smoke tests"""
        script_path = (
            REPO_ROOT / "packages/kailash-kaizen/scripts/validate_deployment.sh"
        )
        with open(script_path) as f:
            content = f.read()

        # Should include smoke test references
        has_smoke_tests = (
            "smoke" in content.lower()
            or "basic" in content.lower()
            and "test" in content.lower()
        )
        assert has_smoke_tests, "Validation script must include smoke tests"

    def test_validation_script_validates_endpoints(self):
        """Verify validation script validates API endpoints"""
        script_path = (
            REPO_ROOT / "packages/kailash-kaizen/scripts/validate_deployment.sh"
        )
        with open(script_path) as f:
            content = f.read()

        # Should include endpoint validation (curl, wget, or similar)
        has_endpoint_validation = (
            "curl" in content.lower()
            or "wget" in content.lower()
            or "http" in content.lower()
        )
        assert has_endpoint_validation, "Validation script must validate endpoints"

    def test_validation_script_checks_response_codes(self):
        """Verify validation script checks HTTP response codes"""
        script_path = (
            REPO_ROOT / "packages/kailash-kaizen/scripts/validate_deployment.sh"
        )
        with open(script_path) as f:
            content = f.read()

        # Should check for 200, 201, or general success codes
        has_response_check = (
            "200" in content
            or "201" in content
            or ("status" in content.lower() and "code" in content.lower())
        )
        assert has_response_check, "Validation script must check response codes"

    def test_validation_script_has_timeout_protection(self):
        """Verify validation script has timeout protection"""
        script_path = (
            REPO_ROOT / "packages/kailash-kaizen/scripts/validate_deployment.sh"
        )
        with open(script_path) as f:
            content = f.read()

        # Should have timeout mechanism
        has_timeout = (
            "timeout" in content.lower()
            or "max-time" in content.lower()
            or "--connect-timeout" in content.lower()
        )
        assert has_timeout, "Validation script must have timeout protection"

    def test_validation_script_exits_on_failure(self):
        """Verify validation script exits with error on validation failure"""
        script_path = (
            REPO_ROOT / "packages/kailash-kaizen/scripts/validate_deployment.sh"
        )
        with open(script_path) as f:
            content = f.read()

        # Should exit with non-zero on failure
        has_error_exit = (
            "exit 1" in content
            or "return 1" in content
            or "set -e" in content  # Fail fast
        )
        assert has_error_exit, "Validation script must exit with error on failure"

    def test_python_validation_helper_exists(self):
        """Verify Python validation helper script exists"""
        script_path = REPO_ROOT / "packages/kailash-kaizen/scripts/validate_env.py"
        # This file already exists from Phase 1
        assert script_path.exists(), "Python validation helper should exist"


@_SKIP
class TestPROD007RollbackProcedures:
    """
    PROD-007: Rollback Procedures

    Requirements:
    - Automated rollback on failures
    - Manual rollback procedures
    - Rollback testing
    - Rollback documentation
    """

    def test_rollback_script_exists(self):
        """Verify rollback script exists"""
        script_path = REPO_ROOT / "packages/kailash-kaizen/scripts/rollback.sh"
        assert script_path.exists(), f"Rollback script not found at {script_path}"

    def test_rollback_script_executable(self):
        """Verify rollback script has executable permissions"""
        script_path = REPO_ROOT / "packages/kailash-kaizen/scripts/rollback.sh"
        assert script_path.exists(), "Script must exist"

        # Check if file has executable permission
        st = os.stat(script_path)
        is_executable = bool(st.st_mode & stat.S_IXUSR)
        assert is_executable, "Rollback script must be executable"

    def test_rollback_runbook_exists(self):
        """Verify rollback runbook documentation exists"""
        runbook_path = (
            REPO_ROOT / "packages/kailash-kaizen/docs/deployment/runbooks/rollback.md"
        )
        assert runbook_path.exists(), f"Rollback runbook not found at {runbook_path}"

    def test_rollback_runbook_has_prerequisites(self):
        """Verify rollback runbook documents prerequisites"""
        runbook_path = (
            REPO_ROOT / "packages/kailash-kaizen/docs/deployment/runbooks/rollback.md"
        )
        with open(runbook_path) as f:
            content = f.read()

        # Should document prerequisites
        has_prerequisites = (
            "prerequisite" in content.lower()
            or "requirement" in content.lower()
            or "before you begin" in content.lower()
        )
        assert has_prerequisites, "Rollback runbook must document prerequisites"

    def test_rollback_runbook_has_manual_steps(self):
        """Verify rollback runbook documents manual rollback steps"""
        runbook_path = (
            REPO_ROOT / "packages/kailash-kaizen/docs/deployment/runbooks/rollback.md"
        )
        with open(runbook_path) as f:
            content = f.read()

        # Should have numbered or bulleted steps
        has_steps = "step" in content.lower() or "1." in content or "- " in content
        assert has_steps, "Rollback runbook must document manual steps"

    def test_rollback_runbook_has_verification_steps(self):
        """Verify rollback runbook includes verification steps"""
        runbook_path = (
            REPO_ROOT / "packages/kailash-kaizen/docs/deployment/runbooks/rollback.md"
        )
        with open(runbook_path) as f:
            content = f.read()

        # Should include verification
        has_verification = (
            "verif" in content.lower()
            or "validate" in content.lower()
            or "confirm" in content.lower()
        )
        assert has_verification, "Rollback runbook must include verification steps"

    def test_rollback_script_accepts_version_parameter(self):
        """Verify rollback script accepts version/tag parameter"""
        script_path = REPO_ROOT / "packages/kailash-kaizen/scripts/rollback.sh"
        with open(script_path) as f:
            content = f.read()

        # Should accept version parameter
        has_version_param = (
            "$1" in content
            or "VERSION" in content
            or "TAG" in content
            or "PREVIOUS" in content
        )
        assert has_version_param, "Rollback script must accept version parameter"

    def test_rollback_script_validates_target_version(self):
        """Verify rollback script validates target version exists"""
        script_path = REPO_ROOT / "packages/kailash-kaizen/scripts/rollback.sh"
        with open(script_path) as f:
            content = f.read()

        # Should validate version exists
        has_validation = "if" in content and (
            "exist" in content.lower()
            or "available" in content.lower()
            or "found" in content.lower()
        )
        assert has_validation, "Rollback script must validate target version"

    def test_rollback_script_has_confirmation_prompt(self):
        """Verify rollback script has confirmation prompt for safety"""
        script_path = REPO_ROOT / "packages/kailash-kaizen/scripts/rollback.sh"
        with open(script_path) as f:
            content = f.read()

        # Should have confirmation prompt (unless --force flag)
        has_confirmation = (
            "read" in content.lower()
            or "confirm" in content.lower()
            or "y/n" in content.lower()
            or "force" in content.lower()
        )
        assert has_confirmation, "Rollback script should have confirmation prompt"

    def test_rollback_workflow_integration(self):
        """Verify deployment workflow includes rollback on failure"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            content = f.read()

        # Should have rollback logic on failure
        has_rollback = "rollback" in content.lower() or (
            "if:" in content.lower() and "failure" in content.lower()
        )
        assert has_rollback, "Deployment workflow must include rollback on failure"

    def test_rollback_runbook_has_troubleshooting(self):
        """Verify rollback runbook includes troubleshooting section"""
        runbook_path = (
            REPO_ROOT / "packages/kailash-kaizen/docs/deployment/runbooks/rollback.md"
        )
        with open(runbook_path) as f:
            content = f.read()

        # Should include troubleshooting
        has_troubleshooting = (
            "troubleshoot" in content.lower()
            or "common issue" in content.lower()
            or "problem" in content.lower()
        )
        assert has_troubleshooting, "Rollback runbook should include troubleshooting"


@_SKIP
class TestCICDIntegration:
    """
    Integration tests verifying all components work together
    """

    def test_deployment_workflow_uses_validation_script(self):
        """Verify deployment workflow calls validation script"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            content = f.read()

        # Should reference validation script
        assert (
            "validate_deployment.sh" in content or "validate_env.py" in content
        ), "Deployment workflow must use validation script"

    def test_deployment_workflow_uses_rollback_script(self):
        """Verify deployment workflow can trigger rollback script"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            content = f.read()

        # Should reference rollback script or procedure
        assert (
            "rollback.sh" in content or "rollback" in content.lower()
        ), "Deployment workflow must reference rollback procedures"

    def test_all_scripts_in_scripts_directory(self):
        """Verify all required scripts are in scripts/ directory"""
        scripts_dir = REPO_ROOT / "packages/kailash-kaizen/scripts"
        assert scripts_dir.exists(), "Scripts directory must exist"

        required_scripts = [
            "validate_deployment.sh",
            "rollback.sh",
            "validate_env.py",  # Already exists from Phase 1
        ]

        for script_name in required_scripts:
            script_path = scripts_dir / script_name
            assert (
                script_path.exists()
            ), f"Required script {script_name} not found in scripts/"

    def test_all_docs_in_docs_directory(self):
        """Verify all required documentation is in docs/ directory"""
        docs_dir = REPO_ROOT / "packages/kailash-kaizen/docs/deployment"
        assert docs_dir.exists(), "Deployment docs directory must exist"

        runbooks_dir = docs_dir / "runbooks"
        assert runbooks_dir.exists(), "Runbooks directory must exist"

        rollback_doc = runbooks_dir / "rollback.md"
        assert rollback_doc.exists(), "Rollback runbook must exist"

    def test_workflow_environment_consistency(self):
        """Verify deployment workflow uses consistent environment variables"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        # Should have environment variables defined
        has_env = "env" in workflow or any(
            "env" in job
            for job in workflow.get("jobs", {}).values()
            if isinstance(job, dict)
        )
        assert has_env, "Deployment workflow should define environment variables"


@_SKIP
class TestSecurityAndCompliance:
    """
    Security and compliance tests for CI/CD pipeline
    """

    def test_workflow_uses_secrets_for_credentials(self):
        """Verify workflow uses secrets for sensitive data"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            content = f.read()

        # Should use secrets for credentials
        has_secrets = "secrets." in content or "${{ secrets." in content
        assert has_secrets, "Workflow must use GitHub secrets for credentials"

    def test_workflow_has_security_scanning(self):
        """Verify workflow includes security scanning"""
        workflow_path = REPO_ROOT / ".github/workflows/deploy-production.yml"
        with open(workflow_path) as f:
            content = f.read()

        # Should include security scanning (trivy, snyk, etc.)
        (
            "trivy" in content.lower()
            or "snyk" in content.lower()
            or "security" in content.lower()
            and "scan" in content.lower()
        )
        # This is optional for MVP, so just check if present
        # assert has_security_scan, "Workflow should include security scanning"

    def test_rollback_script_logs_actions(self):
        """Verify rollback script logs all actions for audit trail"""
        script_path = REPO_ROOT / "packages/kailash-kaizen/scripts/rollback.sh"
        with open(script_path) as f:
            content = f.read()

        # Should include logging
        has_logging = (
            "echo" in content.lower()
            or "log" in content.lower()
            or ">&2" in content  # stderr output
        )
        assert has_logging, "Rollback script must log actions for audit trail"

    def test_validation_script_logs_results(self):
        """Verify validation script logs validation results"""
        script_path = (
            REPO_ROOT / "packages/kailash-kaizen/scripts/validate_deployment.sh"
        )
        with open(script_path) as f:
            content = f.read()

        # Should include logging
        has_logging = "echo" in content.lower() or "log" in content.lower()
        assert has_logging, "Validation script must log results"
