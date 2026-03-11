"""
Unit tests for KaizenConfig enterprise parameter support.

This module tests the foundational configuration system that enables all
advanced Kaizen features including signature programming, MCP integration,
transparency, and enterprise compliance.

CRITICAL: These tests define the exact requirements for unblocking
BLOCKER-001 and must pass before any implementation changes.
"""

import os
import tempfile
from unittest.mock import patch

import pytest
from kaizen.core.config import KaizenConfig
from kaizen.core.framework import Kaizen


class TestKaizenConfigParameterSupport:
    """Test core parameter validation and handling."""

    def test_enterprise_parameter_support(self):
        """Test all required enterprise parameters are supported."""
        enterprise_config = {
            "signature_programming_enabled": True,
            "mcp_integration": {"enabled": True, "port": 8080},
            "multi_agent_enabled": True,
            "transparency_enabled": True,
            "audit_trail_enabled": True,
            "compliance_mode": "enterprise",
            "security_level": "high",
            "memory_enabled": True,
            "optimization_enabled": False,
            "monitoring_level": "detailed",
        }

        # This should not raise an exception
        config = KaizenConfig(**enterprise_config)

        # Verify all parameters are set correctly
        assert config.signature_programming_enabled == True
        assert config.mcp_integration == {"enabled": True, "port": 8080}
        assert config.multi_agent_enabled == True
        assert config.transparency_enabled == True
        assert config.audit_trail_enabled == True
        assert config.compliance_mode == "enterprise"
        assert config.security_level == "high"
        assert config.memory_enabled == True
        assert config.optimization_enabled == False
        assert config.monitoring_level == "detailed"

    def test_minimal_configuration(self):
        """Test basic configuration with defaults."""
        config = KaizenConfig()

        # Test essential defaults
        assert config.signature_programming_enabled == False  # Conservative default
        assert config.mcp_integration == {}  # Empty dict default
        assert config.multi_agent_enabled == False
        assert config.transparency_enabled == False
        assert config.audit_trail_enabled == False
        assert config.compliance_mode == "standard"
        assert config.security_level == "standard"
        assert config.memory_enabled == False
        assert config.optimization_enabled == False
        assert config.monitoring_level == "basic"

    def test_progressive_configuration(self):
        """Test incremental feature enablement."""
        # Start with basic config
        config = KaizenConfig(signature_programming_enabled=True)
        assert config.signature_programming_enabled == True
        assert config.mcp_integration == {}  # Still default

        # Add MCP integration
        config = KaizenConfig(
            signature_programming_enabled=True, mcp_integration={"enabled": True}
        )
        assert config.signature_programming_enabled == True
        assert config.mcp_integration == {"enabled": True}

    def test_development_vs_production_profiles(self):
        """Test different configuration profiles."""
        # Development profile
        dev_config = KaizenConfig(
            debug=True, monitoring_level="detailed", security_level="standard"
        )
        assert dev_config.debug == True
        assert dev_config.monitoring_level == "detailed"
        assert dev_config.security_level == "standard"

        # Production profile
        prod_config = KaizenConfig(
            debug=False,
            monitoring_level="basic",
            security_level="high",
            audit_trail_enabled=True,
            transparency_enabled=True,
            compliance_mode="enterprise",
        )
        assert prod_config.debug == False
        assert prod_config.monitoring_level == "basic"
        assert prod_config.security_level == "high"
        assert prod_config.audit_trail_enabled == True
        assert prod_config.compliance_mode == "enterprise"

    def test_mcp_integration_configuration(self):
        """Test MCP integration parameter handling."""
        # Basic MCP config
        config = KaizenConfig(mcp_integration={"enabled": True})
        assert config.mcp_integration["enabled"] == True

        # Advanced MCP config
        advanced_mcp = {
            "enabled": True,
            "port": 8080,
            "server_config": {"name": "kaizen-server", "version": "1.0.0"},
            "client_configs": [
                {"name": "client1", "endpoint": "http://localhost:8081"}
            ],
        }
        config = KaizenConfig(mcp_integration=advanced_mcp)
        assert config.mcp_integration == advanced_mcp

    def test_signature_programming_configuration(self):
        """Test signature programming parameter."""
        # Disabled by default
        config = KaizenConfig()
        assert config.signature_programming_enabled == False

        # Explicitly enabled
        config = KaizenConfig(signature_programming_enabled=True)
        assert config.signature_programming_enabled == True

        # Test with additional signature config
        config = KaizenConfig(
            signature_programming_enabled=True,
            signature_validation_strict=True,  # Future parameter
            signature_auto_generation=False,  # Future parameter
        )
        assert config.signature_programming_enabled == True


class TestKaizenConfigValidation:
    """Test parameter validation and error handling."""

    def test_invalid_compliance_mode(self):
        """Test validation of compliance mode values."""
        with pytest.raises(ValueError, match="Invalid compliance_mode"):
            KaizenConfig(compliance_mode="invalid_mode")

    def test_invalid_security_level(self):
        """Test validation of security level values."""
        with pytest.raises(ValueError, match="Invalid security_level"):
            KaizenConfig(security_level="invalid_level")

    def test_invalid_monitoring_level(self):
        """Test validation of monitoring level values."""
        with pytest.raises(ValueError, match="Invalid monitoring_level"):
            KaizenConfig(monitoring_level="invalid_level")

    def test_mcp_integration_validation(self):
        """Test MCP integration parameter validation."""
        # Must be dict if provided
        with pytest.raises(TypeError, match="mcp_integration must be a dict"):
            KaizenConfig(mcp_integration="not_a_dict")

        # Empty dict is valid
        config = KaizenConfig(mcp_integration={})
        assert config.mcp_integration == {}

    def test_boolean_parameter_validation(self):
        """Test boolean parameter type validation."""
        bool_params = [
            "signature_programming_enabled",
            "multi_agent_enabled",
            "transparency_enabled",
            "audit_trail_enabled",
            "memory_enabled",
            "optimization_enabled",
        ]

        for param in bool_params:
            # Test valid boolean
            config = KaizenConfig(**{param: True})
            assert getattr(config, param) == True

            # Test invalid type
            with pytest.raises(TypeError, match=f"{param} must be a boolean"):
                KaizenConfig(**{param: "not_boolean"})

    def test_conflicting_configurations(self):
        """Test detection of conflicting configuration options."""
        # High security should require audit trails
        with pytest.raises(
            ValueError, match="High security level requires audit trails"
        ):
            KaizenConfig(security_level="high", audit_trail_enabled=False)

        # Enterprise compliance should require transparency
        with pytest.raises(
            ValueError, match="Enterprise compliance requires transparency"
        ):
            KaizenConfig(compliance_mode="enterprise", transparency_enabled=False)


class TestKaizenConfigEnvironmentVariables:
    """Test environment variable configuration support."""

    def test_environment_variable_override(self):
        """Test configuration from environment variables."""
        env_vars = {
            "KAIZEN_SIGNATURE_PROGRAMMING_ENABLED": "true",
            "KAIZEN_MCP_INTEGRATION_ENABLED": "true",
            "KAIZEN_TRANSPARENCY_ENABLED": "true",
            "KAIZEN_AUDIT_TRAIL_ENABLED": "true",  # Required for high security and enterprise compliance
            "KAIZEN_COMPLIANCE_MODE": "enterprise",
            "KAIZEN_SECURITY_LEVEL": "high",
        }

        with patch.dict(os.environ, env_vars):
            config = KaizenConfig.from_environment()

            assert config.signature_programming_enabled == True
            assert config.transparency_enabled == True
            assert config.audit_trail_enabled == True
            assert config.compliance_mode == "enterprise"
            assert config.security_level == "high"

    def test_environment_variable_types(self):
        """Test proper type conversion from environment variables."""
        with patch.dict(
            os.environ,
            {
                "KAIZEN_SIGNATURE_PROGRAMMING_ENABLED": "false",
                "KAIZEN_MEMORY_ENABLED": "true",
                "KAIZEN_MONITORING_LEVEL": "detailed",
            },
        ):
            config = KaizenConfig.from_environment()

            assert config.signature_programming_enabled == False  # Boolean
            assert config.memory_enabled == True  # Boolean
            assert config.monitoring_level == "detailed"  # String

    def test_environment_variable_precedence(self):
        """Test environment variables override defaults but not explicit params."""
        with patch.dict(os.environ, {"KAIZEN_SIGNATURE_PROGRAMMING_ENABLED": "true"}):
            # Environment variable should override default
            config = KaizenConfig.from_environment()
            assert config.signature_programming_enabled == True

            # Explicit parameter should override environment variable
            config = KaizenConfig.from_environment(signature_programming_enabled=False)
            assert config.signature_programming_enabled == False


class TestKaizenConfigFileLoading:
    """Test configuration file loading support."""

    def test_yaml_configuration_loading(self):
        """Test loading configuration from YAML file."""
        yaml_content = """
signature_programming_enabled: true
mcp_integration:
  enabled: true
  port: 8080
transparency_enabled: true
audit_trail_enabled: true
compliance_mode: enterprise
security_level: high
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            config = KaizenConfig.from_file(f.name)

            assert config.signature_programming_enabled == True
            assert config.mcp_integration == {"enabled": True, "port": 8080}
            assert config.transparency_enabled == True
            assert config.compliance_mode == "enterprise"
            assert config.security_level == "high"

        os.unlink(f.name)

    def test_json_configuration_loading(self):
        """Test loading configuration from JSON file."""
        json_content = """{
    "signature_programming_enabled": true,
    "mcp_integration": {
        "enabled": true,
        "port": 8080
    },
    "transparency_enabled": true,
    "compliance_mode": "enterprise"
}"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(json_content)
            f.flush()

            config = KaizenConfig.from_file(f.name)

            assert config.signature_programming_enabled == True
            assert config.mcp_integration == {"enabled": True, "port": 8080}
            assert config.transparency_enabled == True
            assert config.compliance_mode == "enterprise"

        os.unlink(f.name)

    def test_configuration_file_validation(self):
        """Test validation when loading from files."""
        invalid_json = """{
    "compliance_mode": "invalid_mode"
}"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(invalid_json)
            f.flush()

            with pytest.raises(ValueError, match="Invalid compliance_mode"):
                KaizenConfig.from_file(f.name)

        os.unlink(f.name)


class TestKaizenConfigPersistence:
    """Test configuration saving and loading."""

    def test_configuration_serialization(self):
        """Test config can be serialized and deserialized."""
        original_config = KaizenConfig(
            signature_programming_enabled=True,
            mcp_integration={"enabled": True, "port": 8080},
            transparency_enabled=True,
            compliance_mode="enterprise",
        )

        # Serialize to dict
        config_dict = original_config.to_dict()

        # Recreate from dict
        restored_config = KaizenConfig.from_dict(config_dict)

        # Verify all parameters match
        assert (
            restored_config.signature_programming_enabled
            == original_config.signature_programming_enabled
        )
        assert restored_config.mcp_integration == original_config.mcp_integration
        assert (
            restored_config.transparency_enabled == original_config.transparency_enabled
        )
        assert restored_config.compliance_mode == original_config.compliance_mode

    def test_configuration_save_load(self):
        """Test saving and loading configuration to/from file."""
        config = KaizenConfig(
            signature_programming_enabled=True,
            transparency_enabled=True,
            compliance_mode="enterprise",
        )

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            # Save configuration
            config.save(f.name)

            # Load configuration
            loaded_config = KaizenConfig.load(f.name)

            # Verify parameters match
            assert (
                loaded_config.signature_programming_enabled
                == config.signature_programming_enabled
            )
            assert loaded_config.transparency_enabled == config.transparency_enabled
            assert loaded_config.compliance_mode == config.compliance_mode

        os.unlink(f.name)


class TestKaizenFrameworkConfigIntegration:
    """Test Kaizen framework integration with enterprise configuration."""

    def test_dict_config_backward_compatibility(self):
        """Test Kaizen() with dict config (backward compatibility)."""
        config_dict = {
            "signature_programming_enabled": True,
            "mcp_integration": {"enabled": True},
            "transparency_enabled": True,
            "memory_enabled": True,
        }

        # This is the pattern that currently fails - must work after implementation
        kaizen = Kaizen(config=config_dict)

        # Verify config is properly handled
        assert hasattr(kaizen, "_config")
        assert kaizen._config.signature_programming_enabled == True
        assert kaizen._config.mcp_integration == {"enabled": True}
        assert kaizen._config.transparency_enabled == True
        assert kaizen._config.memory_enabled == True

    def test_kaizen_config_object_integration(self):
        """Test Kaizen() with KaizenConfig object."""
        config = KaizenConfig(
            signature_programming_enabled=True,
            mcp_integration={"enabled": True, "port": 8080},
            transparency_enabled=True,
            audit_trail_enabled=True,
        )

        kaizen = Kaizen(config=config)

        # Verify config object is stored properly
        assert kaizen._config == config
        assert kaizen._config.signature_programming_enabled == True
        assert kaizen._config.mcp_integration == {"enabled": True, "port": 8080}

    def test_mixed_parameter_integration(self):
        """Test Kaizen() with both config dict and individual parameters."""
        config_dict = {
            "signature_programming_enabled": True,
            "mcp_integration": {"enabled": True},
        }

        # Config dict should take precedence over individual parameters
        kaizen = Kaizen(
            config=config_dict,
            memory_enabled=False,  # This should be overridden by config
            debug=True,  # This should be used since not in config
        )

        # Verify proper precedence
        assert kaizen._config.signature_programming_enabled == True  # From config dict
        assert kaizen._config.mcp_integration == {"enabled": True}  # From config dict
        assert kaizen.debug == True  # From individual parameter

    def test_performance_requirements(self):
        """Test configuration loading performance requirements."""
        import time

        # Large enterprise configuration
        enterprise_config = {
            "signature_programming_enabled": True,
            "mcp_integration": {
                "enabled": True,
                "port": 8080,
                "server_config": {"name": "kaizen-server", "version": "1.0.0"},
                "client_configs": [
                    {"name": f"client{i}", "endpoint": f"http://localhost:808{i}"}
                    for i in range(10)
                ],
            },
            "transparency_enabled": True,
            "audit_trail_enabled": True,
            "compliance_mode": "enterprise",
            "security_level": "high",
            "monitoring_level": "detailed",
        }

        # Test configuration creation performance (<10ms)
        start_time = time.time()
        config = KaizenConfig(**enterprise_config)
        config_time = (time.time() - start_time) * 1000

        assert (
            config_time < 10
        ), f"Configuration creation took {config_time:.2f}ms, should be <10ms"

        # Test framework initialization performance
        start_time = time.time()
        Kaizen(config=config)
        init_time = (time.time() - start_time) * 1000

        # Framework init can be slower but should be reasonable
        assert (
            init_time < 100
        ), f"Framework initialization took {init_time:.2f}ms, should be <100ms"
