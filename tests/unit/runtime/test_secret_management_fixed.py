"""Tests for runtime secret management - verifying the bug is fixed.

This test suite verifies that the LocalRuntime now has proper secret management
capabilities and can inject secrets at runtime.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.runtime.secret_provider import (
    AWSSecretProvider,
    EnvironmentSecretProvider,
    SecretNotFoundError,
    SecretProvider,
    SecretRequirement,
    VaultSecretProvider,
)
from kailash.workflow import WorkflowBuilder


class TestSecretManagementFixed:
    """Test cases that verify the secret management bug has been fixed."""

    def test_secret_provider_interface_exists(self):
        """Test that SecretProvider interface now exists."""
        # Should not raise ImportError
        from kailash.runtime.secret_provider import SecretProvider

        # Should be an abstract base class
        assert hasattr(SecretProvider, "get_secret")
        assert hasattr(SecretProvider, "list_secrets")
        assert hasattr(SecretProvider, "get_secrets")

    def test_runtime_has_secret_management_capabilities(self):
        """Test that LocalRuntime now has secret management capabilities."""
        # Create runtime with secret provider
        secret_provider = EnvironmentSecretProvider()
        runtime = LocalRuntime(secret_provider=secret_provider)

        # Check that runtime has secret management capabilities
        assert hasattr(
            runtime, "secret_provider"
        ), "Runtime should have secret_provider attribute"
        assert (
            runtime.secret_provider is secret_provider
        ), "Runtime should store the provided secret provider"

        # Check that runtime has secret injection methods
        assert hasattr(
            runtime, "_extract_secret_requirements"
        ), "Runtime should have _extract_secret_requirements method"

        # Check that runtime constructor accepts secret-related parameters
        runtime_init_params = runtime.__init__.__code__.co_varnames
        assert (
            "secret_provider" in runtime_init_params
        ), "Runtime should accept secret_provider parameter"

    def test_environment_secret_provider_works(self):
        """Test that EnvironmentSecretProvider works correctly."""
        with patch.dict(
            os.environ,
            {
                "KAILASH_SECRET_JWT_SIGNING_KEY": "test_secret_123",
                "KAILASH_SECRET_API_KEY": "api_key_456",
            },
        ):
            provider = EnvironmentSecretProvider()

            # Test get_secret
            secret = provider.get_secret("jwt-signing-key")
            assert secret == "test_secret_123"

            # Test list_secrets
            secrets = provider.list_secrets()
            assert "jwt-signing-key" in secrets
            assert "api-key" in secrets

            # Test get_secrets with requirements
            requirements = [
                SecretRequirement("jwt-signing-key", "secret_key"),
                SecretRequirement("api-key", "api_token"),
            ]
            secrets_dict = provider.get_secrets(requirements)
            assert secrets_dict["secret_key"] == "test_secret_123"
            assert secrets_dict["api_token"] == "api_key_456"

    def test_environment_secret_provider_missing_secret(self):
        """Test that EnvironmentSecretProvider raises error for missing secrets."""
        provider = EnvironmentSecretProvider()

        with pytest.raises(SecretNotFoundError):
            provider.get_secret("nonexistent-secret")

    def test_vault_secret_provider_interface(self):
        """Test that VaultSecretProvider has correct interface."""
        # Should be able to instantiate without actual vault connection
        provider = VaultSecretProvider("http://localhost:8200", "test-token")

        # Should have required methods
        assert hasattr(provider, "get_secret")
        assert hasattr(provider, "list_secrets")
        assert hasattr(provider.__class__, "client")  # Check property exists on class

        # Client should be None until first access
        assert provider._client is None

    def test_aws_secret_provider_interface(self):
        """Test that AWSSecretProvider has correct interface."""
        # Should be able to instantiate without actual AWS connection
        provider = AWSSecretProvider("us-east-1")

        # Should have required methods
        assert hasattr(provider, "get_secret")
        assert hasattr(provider, "list_secrets")
        assert hasattr(provider.__class__, "client")  # Check property exists on class

        # Client should be None until first access
        assert provider._client is None

    def test_secret_requirement_class(self):
        """Test that SecretRequirement class works correctly."""
        req = SecretRequirement(
            "jwt-signing-key", "secret_key", version="v1", optional=False
        )

        assert req.name == "jwt-signing-key"
        assert req.parameter_name == "secret_key"
        assert req.version == "v1"
        assert req.optional is False

    def test_runtime_secret_injection_workflow(self):
        """Test that LocalRuntime can inject secrets into workflow execution."""
        # Create a mock workflow that would extract secret requirements
        mock_workflow = MagicMock()
        mock_workflow.nodes = {}  # No nodes with secret requirements

        # Create runtime with secret provider
        with patch.dict(os.environ, {"KAILASH_SECRET_TEST_KEY": "test_value"}):
            provider = EnvironmentSecretProvider()
            runtime = LocalRuntime(secret_provider=provider)

            # Test secret requirement extraction
            parameters = {"existing_param": "value"}
            requirements = runtime._extract_secret_requirements(mock_workflow)

            # Should return empty requirements since no nodes have secret requirements
            assert requirements == []

    def test_runtime_backward_compatibility(self):
        """Test that LocalRuntime maintains backward compatibility."""
        # Should work without secret provider
        runtime = LocalRuntime()
        assert runtime.secret_provider is None

        # Should work with existing parameters
        mock_workflow = MagicMock()
        mock_workflow.nodes = {}

        # Test secret requirement extraction without provider
        requirements = runtime._extract_secret_requirements(mock_workflow)

        # Should return empty requirements
        assert requirements == []

    def test_secret_requirements_extraction(self):
        """Test that runtime can extract secret requirements from workflow."""
        # Create mock nodes with secret requirements
        mock_node = MagicMock()
        mock_node.get_secret_requirements.return_value = [
            SecretRequirement("jwt-key", "secret_key"),
            SecretRequirement("api-key", "api_token"),
        ]

        mock_workflow = MagicMock()
        mock_workflow.nodes = {"node1": mock_node}

        runtime = LocalRuntime()
        requirements = runtime._extract_secret_requirements(mock_workflow)

        assert len(requirements) == 2
        assert requirements[0].name == "jwt-key"
        assert requirements[1].name == "api-key"

    def test_multiple_secret_providers(self):
        """Test that different secret providers can be used."""
        # Test with EnvironmentSecretProvider
        env_provider = EnvironmentSecretProvider()
        runtime1 = LocalRuntime(secret_provider=env_provider)
        assert isinstance(runtime1.secret_provider, EnvironmentSecretProvider)

        # Test with VaultSecretProvider
        vault_provider = VaultSecretProvider("http://localhost:8200", "token")
        runtime2 = LocalRuntime(secret_provider=vault_provider)
        assert isinstance(runtime2.secret_provider, VaultSecretProvider)

        # Test with AWSSecretProvider
        aws_provider = AWSSecretProvider("us-west-2")
        runtime3 = LocalRuntime(secret_provider=aws_provider)
        assert isinstance(runtime3.secret_provider, AWSSecretProvider)
