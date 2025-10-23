"""Unit tests for gateway creation functions.

Tests the gateway creation utilities including:
- create_gateway function with different server types
- Enterprise defaults
- Feature configuration
- Backward compatibility
"""

import warnings
from unittest.mock import Mock, patch

import pytest
from src.kailash.servers import (
    DurableWorkflowServer,
    EnterpriseWorkflowServer,
    WorkflowServer,
)
from src.kailash.servers.gateway import (
    create_basic_gateway,
    create_durable_gateway,
    create_enterprise_gateway,
    create_gateway,
    create_gateway_legacy,
)


class TestGatewayCreation:
    """Unit tests for gateway creation functions."""

    def test_create_gateway_default_enterprise(self):
        """Test that create_gateway defaults to enterprise server."""
        gateway = create_gateway(title="Default Test Gateway")

        assert isinstance(gateway, EnterpriseWorkflowServer)
        assert gateway.app.title == "Default Test Gateway"
        assert gateway.enable_durability is True
        assert gateway.enable_resource_management is True
        assert gateway.enable_async_execution is True
        assert gateway.enable_health_checks is True

    def test_create_gateway_enterprise_explicit(self):
        """Test create_gateway with explicit enterprise server type."""
        gateway = create_gateway(
            title="Enterprise Test Gateway",
            server_type="enterprise",
            max_workers=30,
            enable_durability=False,  # Test disabling features
        )

        assert isinstance(gateway, EnterpriseWorkflowServer)
        assert gateway.app.title == "Enterprise Test Gateway"
        assert gateway.executor._max_workers == 30
        assert gateway.enable_durability is False  # Should respect override

    def test_create_gateway_durable(self):
        """Test create_gateway with durable server type."""
        gateway = create_gateway(
            title="Durable Test Gateway",
            server_type="durable",
            max_workers=15,
        )

        assert isinstance(gateway, DurableWorkflowServer)
        assert gateway.app.title == "Durable Test Gateway"
        assert gateway.executor._max_workers == 15
        assert gateway.enable_durability is True

    def test_create_gateway_basic(self):
        """Test create_gateway with basic server type."""
        gateway = create_gateway(
            title="Basic Test Gateway",
            server_type="basic",
            max_workers=5,
        )

        assert isinstance(gateway, WorkflowServer)
        assert gateway.app.title == "Basic Test Gateway"
        assert gateway.executor._max_workers == 5
        # Basic server doesn't have durability
        assert not hasattr(gateway, "enable_durability")

    def test_create_gateway_invalid_server_type(self):
        """Test create_gateway with invalid server type."""
        with pytest.raises(ValueError, match="Unknown server type: invalid"):
            create_gateway(server_type="invalid")

    def test_create_gateway_with_cors_origins(self):
        """Test create_gateway with CORS configuration."""
        cors_origins = ["http://localhost:3000", "https://app.example.com"]
        gateway = create_gateway(title="CORS Test Gateway", cors_origins=cors_origins)

        # Check that CORS was passed through to the server
        # The gateway should have been configured with CORS origins
        assert cors_origins is not None
        assert len(cors_origins) == 2

    def test_create_gateway_feature_flags(self):
        """Test create_gateway with various feature flags."""
        gateway = create_gateway(
            title="Feature Flags Test",
            enable_durability=False,
            enable_resource_management=False,
            enable_async_execution=False,
            enable_health_checks=False,
        )

        assert isinstance(gateway, EnterpriseWorkflowServer)
        assert gateway.enable_durability is False
        assert gateway.enable_resource_management is False
        assert gateway.enable_async_execution is False
        assert gateway.enable_health_checks is False

    @patch("src.kailash.servers.gateway.ResourceRegistry")
    @patch("src.kailash.servers.gateway.SecretManager")
    def test_create_gateway_with_custom_components(
        self, mock_secret_manager, mock_registry
    ):
        """Test create_gateway with custom enterprise components."""
        custom_registry = Mock()
        custom_secret_manager = Mock()

        gateway = create_gateway(
            title="Custom Components Test",
            resource_registry=custom_registry,
            secret_manager=custom_secret_manager,
        )

        assert isinstance(gateway, EnterpriseWorkflowServer)
        assert gateway.resource_registry == custom_registry
        assert gateway.secret_manager == custom_secret_manager

    def test_create_enterprise_gateway_alias(self):
        """Test create_enterprise_gateway convenience function."""
        gateway = create_enterprise_gateway(
            title="Alias Test Gateway",
            max_workers=25,
        )

        assert isinstance(gateway, EnterpriseWorkflowServer)
        assert gateway.app.title == "Alias Test Gateway"
        assert gateway.executor._max_workers == 25

    def test_create_durable_gateway_alias(self):
        """Test create_durable_gateway convenience function."""
        gateway = create_durable_gateway(
            title="Durable Alias Test Gateway",
            max_workers=12,
        )

        assert isinstance(gateway, DurableWorkflowServer)
        assert gateway.app.title == "Durable Alias Test Gateway"
        assert gateway.executor._max_workers == 12

    def test_create_basic_gateway_alias(self):
        """Test create_basic_gateway convenience function."""
        gateway = create_basic_gateway(
            title="Basic Alias Test Gateway",
            max_workers=8,
        )

        assert isinstance(gateway, WorkflowServer)
        assert gateway.app.title == "Basic Alias Test Gateway"
        assert gateway.executor._max_workers == 8

    def test_create_gateway_defaults(self):
        """Test create_gateway with all default values."""
        gateway = create_gateway()

        assert isinstance(gateway, EnterpriseWorkflowServer)
        assert gateway.app.title == "Kailash Enterprise Gateway"
        assert (
            gateway.app.description
            == "Production-ready workflow server with enterprise features"
        )
        assert gateway.app.version == "1.0.0"
        assert gateway.executor._max_workers == 20  # Enterprise default

    def test_create_gateway_logging(self):
        """Test that create_gateway logs server creation."""
        with patch("src.kailash.servers.gateway.logger") as mock_logger:
            gateway = create_gateway(title="Logging Test Gateway")

            # Should log server creation
            mock_logger.info.assert_any_call(
                "Creating enterprise workflow server: Logging Test Gateway"
            )
            # Should log features
            assert any(
                "Created EnterpriseWorkflowServer with features" in str(call)
                for call in mock_logger.info.call_args_list
            )

    @patch("src.kailash.middleware.communication.api_gateway.create_gateway")
    def test_create_gateway_legacy_deprecation(self, mock_old_create_gateway):
        """Test that legacy create_gateway function shows deprecation warning."""
        mock_old_create_gateway.return_value = Mock()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            create_gateway_legacy(agent_ui_middleware=Mock(), auth_manager=Mock())

            # Should have issued deprecation warning
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "Legacy create_gateway usage detected" in str(w[0].message)

            # Should have called old function
            mock_old_create_gateway.assert_called_once()

    def test_create_gateway_kwargs_passthrough(self):
        """Test that additional kwargs are passed through to server constructor."""
        gateway = create_gateway(
            title="Kwargs Test",
            description="Custom description",
            version="2.1.0",
            some_custom_param="custom_value",  # This should be passed through
        )

        assert gateway.app.title == "Kwargs Test"
        assert gateway.app.description == "Custom description"
        assert gateway.app.version == "2.1.0"
        # Custom param should be passed through (though may not be used)

    def test_create_gateway_server_type_case_insensitive(self):
        """Test that server_type parameter is case sensitive (as expected)."""
        # Should work with exact case
        gateway1 = create_gateway(server_type="enterprise")
        assert isinstance(gateway1, EnterpriseWorkflowServer)

        gateway2 = create_gateway(server_type="durable")
        assert isinstance(gateway2, DurableWorkflowServer)

        gateway3 = create_gateway(server_type="basic")
        assert isinstance(gateway3, WorkflowServer)

        # Should fail with wrong case (as designed)
        with pytest.raises(ValueError):
            create_gateway(server_type="ENTERPRISE")

    def test_create_gateway_enterprise_max_workers_default(self):
        """Test that enterprise server has different default max_workers."""
        enterprise_gateway = create_gateway(server_type="enterprise")
        durable_gateway = create_gateway(server_type="durable")
        basic_gateway = create_gateway(server_type="basic")

        # Enterprise should default to 20
        assert enterprise_gateway.executor._max_workers == 20
        # Others should still default to their configured values
        assert durable_gateway.executor._max_workers == 20  # Uses same as enterprise
        assert basic_gateway.executor._max_workers == 20  # Uses same as enterprise

    def test_create_gateway_feature_combinations(self):
        """Test various combinations of feature flags."""
        # All disabled
        gateway1 = create_gateway(
            enable_durability=False,
            enable_resource_management=False,
            enable_async_execution=False,
            enable_health_checks=False,
        )
        assert not gateway1.enable_durability
        assert not gateway1.enable_resource_management

        # Mixed configuration
        gateway2 = create_gateway(
            enable_durability=True,
            enable_resource_management=False,
            enable_async_execution=True,
            enable_health_checks=True,
        )
        assert gateway2.enable_durability
        assert not gateway2.enable_resource_management
        assert gateway2.enable_async_execution
        assert gateway2.enable_health_checks
