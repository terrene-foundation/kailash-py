"""Unit tests for AuditConfig (TODO-310F).

Tier 1 tests - mocking allowed.
"""

import pytest
from nexus.auth.audit.config import AuditConfig

# =============================================================================
# Tests: Default Values
# =============================================================================


class TestAuditConfigDefaults:
    """Test default configuration values."""

    def test_enabled_by_default(self):
        """Audit logging enabled by default."""
        config = AuditConfig()
        assert config.enabled is True

    def test_default_backend(self):
        """Default backend is 'logging'."""
        config = AuditConfig()
        assert config.backend == "logging"

    def test_default_log_level(self):
        """Default log level is INFO."""
        config = AuditConfig()
        assert config.log_level == "INFO"

    def test_default_body_logging_disabled(self):
        """Request/response body logging disabled by default."""
        config = AuditConfig()
        assert config.log_request_body is False
        assert config.log_response_body is False

    def test_default_max_body_size(self):
        """Default max body log size is 10KB."""
        config = AuditConfig()
        assert config.max_body_log_size == 10 * 1024

    def test_default_include_query_params(self):
        """Query params included by default."""
        config = AuditConfig()
        assert config.include_query_params is True

    def test_default_include_request_headers(self):
        """Request headers not included by default."""
        config = AuditConfig()
        assert config.include_request_headers is False

    def test_default_exclude_paths(self):
        """Health, metrics, docs excluded by default."""
        config = AuditConfig()
        assert "/health" in config.exclude_paths
        assert "/metrics" in config.exclude_paths
        assert "/docs" in config.exclude_paths
        assert "/openapi.json" in config.exclude_paths

    def test_default_exclude_methods(self):
        """OPTIONS excluded by default."""
        config = AuditConfig()
        assert "OPTIONS" in config.exclude_methods

    def test_default_redact_headers(self):
        """Authorization and Cookie headers redacted by default."""
        config = AuditConfig()
        assert "Authorization" in config.redact_headers
        assert "Cookie" in config.redact_headers
        assert "X-API-Key" in config.redact_headers

    def test_default_redact_fields(self):
        """Password, secret, token fields redacted by default."""
        config = AuditConfig()
        assert "password" in config.redact_fields
        assert "secret" in config.redact_fields
        assert "token" in config.redact_fields
        assert "credit_card" in config.redact_fields
        assert "ssn" in config.redact_fields

    def test_default_replacement(self):
        """Default redaction replacement is [REDACTED]."""
        config = AuditConfig()
        assert config.redact_replacement == "[REDACTED]"

    def test_default_dataflow_model_name(self):
        """Default DataFlow model name is AuditRecord."""
        config = AuditConfig()
        assert config.dataflow_model_name == "AuditRecord"


# =============================================================================
# Tests: Custom Values
# =============================================================================


class TestAuditConfigCustom:
    """Test custom configuration values."""

    def test_custom_backend(self):
        """Set custom backend."""
        config = AuditConfig(backend="dataflow")
        assert config.backend == "dataflow"

    def test_callable_backend(self):
        """Set callable as backend."""

        async def custom_store(record):
            pass

        config = AuditConfig(backend=custom_store)
        assert config.backend is custom_store

    def test_custom_exclude_paths(self):
        """Set custom exclude paths."""
        config = AuditConfig(exclude_paths=["/health", "/custom"])
        assert "/custom" in config.exclude_paths

    def test_custom_redact_fields(self):
        """Set custom redact fields."""
        config = AuditConfig(redact_fields=["my_secret_field"])
        assert "my_secret_field" in config.redact_fields

    def test_enable_body_logging(self):
        """Enable request body logging."""
        config = AuditConfig(log_request_body=True, log_response_body=True)
        assert config.log_request_body is True
        assert config.log_response_body is True


# =============================================================================
# Tests: Validation
# =============================================================================


class TestAuditConfigValidation:
    """Test configuration validation."""

    def test_negative_max_body_size_raises(self):
        """Negative max_body_log_size raises ValueError."""
        with pytest.raises(ValueError, match="max_body_log_size"):
            AuditConfig(max_body_log_size=-1)

    def test_invalid_log_level_raises(self):
        """Invalid log_level raises ValueError."""
        with pytest.raises(ValueError, match="Invalid log_level"):
            AuditConfig(log_level="INVALID")

    def test_valid_log_levels(self):
        """All valid log levels accepted."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            config = AuditConfig(log_level=level)
            assert config.log_level == level


# =============================================================================
# Tests: Package Exports
# =============================================================================


class TestAuditPackageExports:
    """Test package exports."""

    def test_config_from_audit_package(self):
        """AuditConfig accessible from audit package."""
        from nexus.auth.audit import AuditConfig as AC

        assert AC is AuditConfig

    def test_middleware_from_audit_package(self):
        """AuditMiddleware accessible from audit package."""
        from nexus.auth.audit import AuditMiddleware

        assert AuditMiddleware is not None

    def test_record_from_audit_package(self):
        """AuditRecord accessible from audit package."""
        from nexus.auth.audit import AuditRecord

        assert AuditRecord is not None

    def test_pii_filter_from_audit_package(self):
        """PIIFilter accessible from audit package."""
        from nexus.auth.audit import PIIFilter

        assert PIIFilter is not None

    def test_backends_from_audit_package(self):
        """All backends accessible from audit package."""
        from nexus.auth.audit import (
            AuditBackend,
            CustomBackend,
            DataFlowBackend,
            LoggingBackend,
        )

        assert AuditBackend is not None
        assert LoggingBackend is not None
        assert DataFlowBackend is not None
        assert CustomBackend is not None

    def test_config_from_auth_package(self):
        """AuditConfig accessible from nexus.auth."""
        from nexus.auth import AuditConfig as AC

        assert AC is AuditConfig

    def test_middleware_from_auth_package(self):
        """AuditMiddleware accessible from nexus.auth."""
        from nexus.auth import AuditMiddleware

        assert AuditMiddleware is not None
