"""
Unit tests for LoggingConfig - Centralized Logging Configuration.

Tests the LoggingConfig dataclass and related utilities for:
- Basic configuration with defaults
- Environment variable support
- Category-specific log levels
- Sensitive value masking
- Regex-based string masking
- SensitiveMaskingFilter for log records
- Integration with suppress_warnings utilities
"""

import logging
import os
from unittest import mock

import pytest

# =============================================================================
# Tests for NEW logging_config.py module (Phase 7)
# =============================================================================


@pytest.mark.unit
class TestLoggingConfigNew:
    """Test the new LoggingConfig from logging_config.py."""

    def test_default_values(self):
        """Default values should be production-ready."""
        from dataflow.core.logging_config import LoggingConfig

        config = LoggingConfig()
        assert config.level == logging.WARNING
        assert config.mask_sensitive is True
        assert config.mask_replacement == "***MASKED***"
        assert config.propagate is True
        assert len(config.mask_patterns) > 0

    def test_custom_level(self):
        """Custom log levels should be applied."""
        from dataflow.core.logging_config import LoggingConfig

        config = LoggingConfig(level=logging.DEBUG)
        assert config.level == logging.DEBUG

    def test_custom_format(self):
        """Custom format should be applied."""
        from dataflow.core.logging_config import LoggingConfig

        custom_format = "%(message)s"
        config = LoggingConfig(format=custom_format)
        assert config.format == custom_format

    def test_from_env_with_level(self):
        """from_env should read DATAFLOW_LOG_LEVEL."""
        from dataflow.core.logging_config import LoggingConfig

        with mock.patch.dict(os.environ, {"DATAFLOW_LOG_LEVEL": "DEBUG"}):
            config = LoggingConfig.from_env()
            assert config.level == logging.DEBUG

    def test_from_env_with_mask_sensitive_true(self):
        """from_env should read DATAFLOW_LOG_MASK_SENSITIVE=true."""
        from dataflow.core.logging_config import LoggingConfig

        with mock.patch.dict(os.environ, {"DATAFLOW_LOG_MASK_SENSITIVE": "true"}):
            config = LoggingConfig.from_env()
            assert config.mask_sensitive is True

    def test_from_env_with_mask_sensitive_false(self):
        """from_env should read DATAFLOW_LOG_MASK_SENSITIVE=false."""
        from dataflow.core.logging_config import LoggingConfig

        with mock.patch.dict(os.environ, {"DATAFLOW_LOG_MASK_SENSITIVE": "false"}):
            config = LoggingConfig.from_env()
            assert config.mask_sensitive is False

    def test_from_env_with_custom_patterns(self):
        """from_env should read DATAFLOW_LOG_MASK_PATTERNS."""
        from dataflow.core.logging_config import (
            DEFAULT_SENSITIVE_PATTERNS,
            LoggingConfig,
        )

        with mock.patch.dict(
            os.environ,
            {"DATAFLOW_LOG_MASK_PATTERNS": "custom_secret=([^\\s]+),my_key=([^\\s]+)"},
        ):
            config = LoggingConfig.from_env()
            # Should have default patterns plus custom ones
            assert len(config.mask_patterns) > len(DEFAULT_SENSITIVE_PATTERNS)
            assert "custom_secret=([^\\s]+)" in config.mask_patterns

    def test_from_env_with_format(self):
        """from_env should read DATAFLOW_LOG_FORMAT."""
        from dataflow.core.logging_config import LoggingConfig

        custom_format = "%(levelname)s: %(message)s"
        with mock.patch.dict(os.environ, {"DATAFLOW_LOG_FORMAT": custom_format}):
            config = LoggingConfig.from_env()
            assert config.format == custom_format

    def test_from_env_invalid_level_uses_default(self):
        """from_env should use default for invalid level names."""
        from dataflow.core.logging_config import LoggingConfig

        with mock.patch.dict(os.environ, {"DATAFLOW_LOG_LEVEL": "INVALID_LEVEL"}):
            config = LoggingConfig.from_env()
            assert config.level == logging.WARNING

    def test_from_env_with_custom_prefix(self):
        """from_env should support custom prefix."""
        from dataflow.core.logging_config import LoggingConfig

        with mock.patch.dict(os.environ, {"MYAPP_LOG_LEVEL": "ERROR"}):
            config = LoggingConfig.from_env(prefix="MYAPP")
            assert config.level == logging.ERROR

    def test_production_preset(self):
        """production() should return WARNING level config."""
        from dataflow.core.logging_config import LoggingConfig

        config = LoggingConfig.production()
        assert config.level == logging.WARNING
        assert config.mask_sensitive is True

    def test_development_preset(self):
        """development() should return DEBUG level config."""
        from dataflow.core.logging_config import LoggingConfig

        config = LoggingConfig.development()
        assert config.level == logging.DEBUG
        assert config.mask_sensitive is True

    def test_quiet_preset(self):
        """quiet() should return ERROR level config."""
        from dataflow.core.logging_config import LoggingConfig

        config = LoggingConfig.quiet()
        assert config.level == logging.ERROR
        assert config.mask_sensitive is True


@pytest.mark.unit
class TestMaskSensitiveValues:
    """Test the mask_sensitive_values function for string masking."""

    def test_mask_postgresql_url(self):
        """Should mask password in PostgreSQL URL."""
        from dataflow.core.logging_config import mask_sensitive_values

        url = "postgresql://user:secretpassword@localhost:5432/db"
        masked = mask_sensitive_values(url)
        assert "secretpassword" not in masked
        assert "***MASKED***" in masked
        assert "user:" in masked

    def test_mask_mysql_url(self):
        """Should mask password in MySQL URL."""
        from dataflow.core.logging_config import mask_sensitive_values

        url = "mysql://root:rootpass@127.0.0.1:3306/mydb"
        masked = mask_sensitive_values(url)
        assert "rootpass" not in masked
        assert "***MASKED***" in masked

    def test_mask_password_param(self):
        """Should mask password parameter."""
        from dataflow.core.logging_config import mask_sensitive_values

        message = "Connecting with password=supersecret123"
        masked = mask_sensitive_values(message)
        assert "supersecret123" not in masked
        assert "***MASKED***" in masked

    def test_mask_api_key(self):
        """Should mask API key."""
        from dataflow.core.logging_config import mask_sensitive_values

        message = "Using api_key=sk-12345abcde"
        masked = mask_sensitive_values(message)
        assert "sk-12345abcde" not in masked
        assert "***MASKED***" in masked

    def test_mask_bearer_token(self):
        """Should mask bearer token."""
        from dataflow.core.logging_config import mask_sensitive_values

        message = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        masked = mask_sensitive_values(message)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in masked
        assert "***MASKED***" in masked

    def test_mask_aws_access_key(self):
        """Should mask AWS access key ID."""
        from dataflow.core.logging_config import mask_sensitive_values

        message = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        masked = mask_sensitive_values(message)
        assert "AKIAIOSFODNN7EXAMPLE" not in masked
        assert "***MASKED***" in masked

    def test_mask_aws_secret_key(self):
        """Should mask AWS secret access key."""
        from dataflow.core.logging_config import mask_sensitive_values

        message = "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        masked = mask_sensitive_values(message)
        assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in masked
        assert "***MASKED***" in masked

    def test_no_sensitive_data_unchanged(self):
        """Should not modify messages without sensitive data."""
        from dataflow.core.logging_config import mask_sensitive_values

        message = "This is a normal log message with no secrets"
        masked = mask_sensitive_values(message)
        assert masked == message

    def test_custom_patterns(self):
        """Should support custom masking patterns."""
        from dataflow.core.logging_config import LoggingConfig, mask_sensitive_values

        config = LoggingConfig(
            mask_patterns=["my_custom_secret=([^\\s]+)"],
            mask_sensitive=True,
        )
        message = "my_custom_secret=verysecret123"
        masked = mask_sensitive_values(message, config)
        assert "verysecret123" not in masked
        assert "***MASKED***" in masked

    def test_empty_message(self):
        """Should handle empty message."""
        from dataflow.core.logging_config import mask_sensitive_values

        assert mask_sensitive_values("") == ""
        assert mask_sensitive_values(None) is None

    def test_multiple_patterns_in_same_message(self):
        """Should mask multiple sensitive values in same message."""
        from dataflow.core.logging_config import mask_sensitive_values

        message = "Connection: password=secret1 api_key=key123 token=tok456"
        masked = mask_sensitive_values(message)
        assert "secret1" not in masked
        assert "key123" not in masked
        assert "tok456" not in masked
        # All should be masked
        assert masked.count("***MASKED***") >= 3

    def test_mask_disabled(self):
        """Should not mask when mask_sensitive is False."""
        from dataflow.core.logging_config import LoggingConfig, mask_sensitive_values

        config = LoggingConfig(mask_sensitive=False)
        message = "password=secret123"
        masked = mask_sensitive_values(message, config)
        assert masked == message

    def test_custom_replacement(self):
        """Should use custom replacement string."""
        from dataflow.core.logging_config import LoggingConfig, mask_sensitive_values

        config = LoggingConfig(mask_replacement="[REDACTED]")
        message = "password=secret123"
        masked = mask_sensitive_values(message, config)
        assert "[REDACTED]" in masked
        assert "***MASKED***" not in masked


@pytest.mark.unit
class TestSensitiveMaskingFilter:
    """Test the SensitiveMaskingFilter logging filter."""

    def test_filter_masks_message(self):
        """Filter should mask sensitive values in log message."""
        from dataflow.core.logging_config import LoggingConfig, SensitiveMaskingFilter

        config = LoggingConfig()
        log_filter = SensitiveMaskingFilter(config)

        # Create a log record with sensitive data
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Connecting to postgresql://user:password@localhost/db",
            args=(),
            exc_info=None,
        )

        # Apply filter
        result = log_filter.filter(record)

        # Filter should return True (pass the record)
        assert result is True
        # Message should be masked
        assert "password" not in record.msg
        assert "***MASKED***" in record.msg

    def test_filter_preserves_non_sensitive(self):
        """Filter should not modify non-sensitive messages."""
        from dataflow.core.logging_config import SensitiveMaskingFilter

        log_filter = SensitiveMaskingFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="This is a normal log message",
            args=(),
            exc_info=None,
        )

        original_msg = record.msg
        log_filter.filter(record)

        assert record.msg == original_msg

    def test_filter_handles_non_string_messages(self):
        """Filter should handle non-string messages gracefully."""
        from dataflow.core.logging_config import SensitiveMaskingFilter

        log_filter = SensitiveMaskingFilter()

        # Create record with non-string msg (integer)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=12345,  # Non-string
            args=(),
            exc_info=None,
        )

        # Should not raise exception
        result = log_filter.filter(record)
        assert result is True
        assert record.msg == 12345

    def test_filter_custom_replacement(self):
        """Filter should use custom replacement from config."""
        from dataflow.core.logging_config import LoggingConfig, SensitiveMaskingFilter

        config = LoggingConfig(mask_replacement="[HIDDEN]")
        log_filter = SensitiveMaskingFilter(config)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="password=secret",
            args=(),
            exc_info=None,
        )

        log_filter.filter(record)

        assert "[HIDDEN]" in record.msg
        assert "***MASKED***" not in record.msg

    def test_filter_custom_patterns(self):
        """Filter should use custom patterns from config."""
        from dataflow.core.logging_config import LoggingConfig, SensitiveMaskingFilter

        config = LoggingConfig(
            mask_patterns=["custom_field=([^\\s]+)"],
        )
        log_filter = SensitiveMaskingFilter(config)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="custom_field=myvalue123",
            args=(),
            exc_info=None,
        )

        log_filter.filter(record)

        assert "myvalue123" not in record.msg
        assert "***MASKED***" in record.msg

    def test_filter_with_string_args(self):
        """Filter should mask sensitive values in string args."""
        from dataflow.core.logging_config import SensitiveMaskingFilter

        log_filter = SensitiveMaskingFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Connection: %s",
            args=("password=secret123",),
            exc_info=None,
        )

        log_filter.filter(record)

        # Args tuple should have masked string
        assert "secret123" not in record.args[0]

    def test_filter_with_dict_args(self):
        """Filter should mask sensitive values in dict args."""
        from dataflow.core.logging_config import SensitiveMaskingFilter

        log_filter = SensitiveMaskingFilter()

        # Create record first, then set dict args (LogRecord doesn't accept dict directly)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Data: %(data)s",
            args=(),
            exc_info=None,
        )
        # Manually set dict args after creation
        record.args = {"data": "password=secret123"}

        log_filter.filter(record)

        # Dict args should have masked value
        assert "secret123" not in record.args["data"]


@pytest.mark.unit
class TestDefaultSensitivePatterns:
    """Test DEFAULT_SENSITIVE_PATTERNS coverage."""

    def test_patterns_exist(self):
        """DEFAULT_SENSITIVE_PATTERNS should be non-empty list."""
        from dataflow.core.logging_config import DEFAULT_SENSITIVE_PATTERNS

        assert isinstance(DEFAULT_SENSITIVE_PATTERNS, list)
        assert len(DEFAULT_SENSITIVE_PATTERNS) > 10  # Should have many patterns

    def test_patterns_are_valid_regex(self):
        """All default patterns should be valid regex."""
        import re

        from dataflow.core.logging_config import DEFAULT_SENSITIVE_PATTERNS

        for pattern in DEFAULT_SENSITIVE_PATTERNS:
            # Should not raise
            compiled = re.compile(pattern, re.IGNORECASE)
            assert compiled is not None

    def test_database_url_patterns(self):
        """Patterns should cover common database URL formats."""
        from dataflow.core.logging_config import mask_sensitive_values

        urls = [
            "postgresql://user:pass@host/db",
            "postgres://admin:secret@localhost/mydb",
            "mysql://root:password@127.0.0.1/test",
            "mariadb://user:pwd@host:3306/db",
        ]

        for url in urls:
            masked = mask_sensitive_values(url)
            assert "***MASKED***" in masked, f"Pattern not matched for: {url}"

    def test_aws_credential_patterns(self):
        """Patterns should cover AWS credential formats."""
        from dataflow.core.logging_config import mask_sensitive_values

        # AWS Access Key ID format
        assert "***MASKED***" in mask_sensitive_values("AKIAIOSFODNN7EXAMPLE")
        # AWS Secret with env var format
        assert "***MASKED***" in mask_sensitive_values(
            "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI"
        )


# =============================================================================
# Tests for EXISTING config.py LoggingConfig (backward compatibility)
# =============================================================================


@pytest.mark.unit
class TestLoggingConfigBasics:
    """Test LoggingConfig basic functionality."""

    def test_default_level_is_warning(self):
        """Default log level should be WARNING for production-friendly output."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig()
        assert config.level == logging.WARNING

    def test_category_levels_default_to_none(self):
        """Category-specific levels should default to None (use global)."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig()
        assert config.node_execution is None
        assert config.sql_generation is None
        assert config.list_operations is None
        assert config.migration is None
        assert config.core is None

    def test_custom_level_override(self):
        """Custom log level should override default."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig(level=logging.DEBUG)
        assert config.level == logging.DEBUG

    def test_category_specific_levels(self):
        """Category-specific levels can be set independently."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig(
            level=logging.WARNING,
            node_execution=logging.DEBUG,
            sql_generation=logging.ERROR,
        )
        assert config.level == logging.WARNING
        assert config.node_execution == logging.DEBUG
        assert config.sql_generation == logging.ERROR

    def test_get_level_for_category_with_specific(self):
        """get_level_for_category returns category-specific level when set."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig(level=logging.WARNING, node_execution=logging.DEBUG)
        assert config.get_level_for_category("node_execution") == logging.DEBUG

    def test_get_level_for_category_falls_back_to_global(self):
        """get_level_for_category falls back to global level when not set."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig(level=logging.ERROR)
        assert config.get_level_for_category("node_execution") == logging.ERROR
        assert config.get_level_for_category("sql_generation") == logging.ERROR

    def test_get_level_for_unknown_category(self):
        """get_level_for_category returns global level for unknown categories."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig(level=logging.INFO)
        assert config.get_level_for_category("unknown_category") == logging.INFO


@pytest.mark.unit
class TestLoggingConfigEnvironmentVariables:
    """Test LoggingConfig.from_env() environment variable support."""

    def test_from_env_default_values(self):
        """from_env() should use defaults when no env vars set."""
        from dataflow.core.config import LoggingConfig

        # Clear any existing env vars
        env_vars = [
            "DATAFLOW_LOG_LEVEL",
            "DATAFLOW_LOG_NODE_EXECUTION",
            "DATAFLOW_LOG_SQL_GENERATION",
            "DATAFLOW_LOG_LIST_OPERATIONS",
            "DATAFLOW_LOG_MIGRATION",
            "DATAFLOW_LOG_CORE",
            "DATAFLOW_MASK_SENSITIVE",
        ]
        with mock.patch.dict(os.environ, {}, clear=True):
            for var in env_vars:
                os.environ.pop(var, None)
            config = LoggingConfig.from_env()
            assert config.level == logging.WARNING
            assert config.mask_sensitive_values is True

    def test_from_env_global_level(self):
        """from_env() should parse DATAFLOW_LOG_LEVEL."""
        from dataflow.core.config import LoggingConfig

        with mock.patch.dict(os.environ, {"DATAFLOW_LOG_LEVEL": "DEBUG"}):
            config = LoggingConfig.from_env()
            assert config.level == logging.DEBUG

    def test_from_env_global_level_case_insensitive(self):
        """from_env() should handle case-insensitive level names."""
        from dataflow.core.config import LoggingConfig

        with mock.patch.dict(os.environ, {"DATAFLOW_LOG_LEVEL": "debug"}):
            config = LoggingConfig.from_env()
            assert config.level == logging.DEBUG

    def test_from_env_category_levels(self):
        """from_env() should parse category-specific levels."""
        from dataflow.core.config import LoggingConfig

        with mock.patch.dict(
            os.environ,
            {
                "DATAFLOW_LOG_LEVEL": "WARNING",
                "DATAFLOW_LOG_NODE_EXECUTION": "DEBUG",
                "DATAFLOW_LOG_SQL_GENERATION": "ERROR",
            },
        ):
            config = LoggingConfig.from_env()
            assert config.level == logging.WARNING
            assert config.node_execution == logging.DEBUG
            assert config.sql_generation == logging.ERROR
            assert config.list_operations is None  # Not set

    def test_from_env_mask_sensitive_true(self):
        """from_env() should parse DATAFLOW_MASK_SENSITIVE=true."""
        from dataflow.core.config import LoggingConfig

        with mock.patch.dict(os.environ, {"DATAFLOW_MASK_SENSITIVE": "true"}):
            config = LoggingConfig.from_env()
            assert config.mask_sensitive_values is True

    def test_from_env_mask_sensitive_false(self):
        """from_env() should parse DATAFLOW_MASK_SENSITIVE=false."""
        from dataflow.core.config import LoggingConfig

        with mock.patch.dict(os.environ, {"DATAFLOW_MASK_SENSITIVE": "false"}):
            config = LoggingConfig.from_env()
            assert config.mask_sensitive_values is False

    def test_from_env_invalid_level_uses_default(self):
        """from_env() should use default for invalid level names."""
        from dataflow.core.config import LoggingConfig

        with mock.patch.dict(os.environ, {"DATAFLOW_LOG_LEVEL": "INVALID"}):
            config = LoggingConfig.from_env()
            assert config.level == logging.WARNING  # Default


@pytest.mark.unit
class TestSensitiveValueMasking:
    """Test sensitive value masking functionality."""

    def test_mask_sensitive_values_enabled_by_default(self):
        """Sensitive value masking should be enabled by default."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig()
        assert config.mask_sensitive_values is True

    def test_default_sensitive_patterns(self):
        """Default sensitive patterns should include common secrets."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig()
        assert "password" in config.sensitive_patterns
        assert "token" in config.sensitive_patterns
        assert "secret" in config.sensitive_patterns
        assert "key" in config.sensitive_patterns
        assert "credential" in config.sensitive_patterns
        assert "auth" in config.sensitive_patterns

    def test_custom_sensitive_patterns(self):
        """Custom sensitive patterns can be provided."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig(sensitive_patterns=["ssn", "dob", "credit_card"])
        assert "ssn" in config.sensitive_patterns
        assert "password" not in config.sensitive_patterns  # Custom replaces default


@pytest.mark.unit
class TestMaskSensitiveFunction:
    """Test the mask_sensitive utility function."""

    def test_mask_sensitive_password_field(self):
        """Password fields should be masked."""
        from dataflow.core.config import LoggingConfig, mask_sensitive

        config = LoggingConfig()
        data = {"username": "alice", "password": "secret123"}
        masked = mask_sensitive(data, config)
        assert masked["username"] == "alice"
        assert masked["password"] == "***MASKED***"

    def test_mask_sensitive_multiple_fields(self):
        """Multiple sensitive fields should be masked."""
        from dataflow.core.config import LoggingConfig, mask_sensitive

        config = LoggingConfig()
        data = {
            "api_key": "sk-12345",
            "auth_token": "bearer-xyz",
            "user_secret": "private",
            "name": "Alice",
        }
        masked = mask_sensitive(data, config)
        assert masked["api_key"] == "***MASKED***"
        assert masked["auth_token"] == "***MASKED***"
        assert masked["user_secret"] == "***MASKED***"
        assert masked["name"] == "Alice"

    def test_mask_sensitive_nested_dict(self):
        """Nested dictionaries should be recursively masked."""
        from dataflow.core.config import LoggingConfig, mask_sensitive

        config = LoggingConfig()
        data = {
            "user": {"name": "Alice", "password": "secret123"},
            "metadata": {"api_key": "sk-123"},
        }
        masked = mask_sensitive(data, config)
        assert masked["user"]["name"] == "Alice"
        assert masked["user"]["password"] == "***MASKED***"
        assert masked["metadata"]["api_key"] == "***MASKED***"

    def test_mask_sensitive_disabled(self):
        """When masking disabled, values should not be masked."""
        from dataflow.core.config import LoggingConfig, mask_sensitive

        config = LoggingConfig(mask_sensitive_values=False)
        data = {"password": "secret123"}
        masked = mask_sensitive(data, config)
        assert masked["password"] == "secret123"

    def test_mask_sensitive_case_insensitive(self):
        """Field name matching should be case-insensitive."""
        from dataflow.core.config import LoggingConfig, mask_sensitive

        config = LoggingConfig()
        data = {"PASSWORD": "secret", "Api_Key": "key123", "AuthToken": "token"}
        masked = mask_sensitive(data, config)
        assert masked["PASSWORD"] == "***MASKED***"
        assert masked["Api_Key"] == "***MASKED***"
        assert masked["AuthToken"] == "***MASKED***"

    def test_mask_sensitive_preserves_non_dict_values(self):
        """Non-dict values should be preserved as-is."""
        from dataflow.core.config import LoggingConfig, mask_sensitive

        config = LoggingConfig()
        data = {"count": 42, "active": True, "tags": ["a", "b"]}
        masked = mask_sensitive(data, config)
        assert masked["count"] == 42
        assert masked["active"] is True
        assert masked["tags"] == ["a", "b"]

    def test_mask_sensitive_with_none_values(self):
        """None values should be preserved."""
        from dataflow.core.config import LoggingConfig, mask_sensitive

        config = LoggingConfig()
        data = {"name": "Alice", "password": None}
        masked = mask_sensitive(data, config)
        assert masked["name"] == "Alice"
        assert masked["password"] is None


@pytest.mark.unit
class TestConfigureDataflowLogging:
    """Test configure_dataflow_logging() function."""

    def setup_method(self):
        """Reset logging state before each test."""
        from dataflow.utils.suppress_warnings import restore_dataflow_logging

        # Ensure clean state before each test
        restore_dataflow_logging()

    def teardown_method(self):
        """Clean up logging state after each test."""
        from dataflow.utils.suppress_warnings import restore_dataflow_logging

        restore_dataflow_logging()

    def test_configure_dataflow_logging_sets_levels(self):
        """configure_dataflow_logging should set logger levels."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import configure_dataflow_logging

        config = LoggingConfig(level=logging.DEBUG)
        configure_dataflow_logging(config)

        # Check that DataFlow loggers are configured
        nodes_logger = logging.getLogger("dataflow.core.nodes")
        assert nodes_logger.level == logging.DEBUG

    def test_configure_dataflow_logging_with_categories(self):
        """configure_dataflow_logging should respect category-specific levels."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import configure_dataflow_logging

        config = LoggingConfig(
            level=logging.WARNING,
            node_execution=logging.DEBUG,
            migration=logging.ERROR,
        )
        configure_dataflow_logging(config)

        nodes_logger = logging.getLogger("dataflow.core.nodes")
        migration_logger = logging.getLogger("dataflow.migrations")
        assert nodes_logger.level == logging.DEBUG
        assert migration_logger.level == logging.ERROR

    def test_configure_dataflow_logging_from_env(self):
        """configure_dataflow_logging should use from_env() when no config provided."""
        from dataflow.utils.suppress_warnings import configure_dataflow_logging

        with mock.patch.dict(os.environ, {"DATAFLOW_LOG_LEVEL": "ERROR"}):
            configure_dataflow_logging()

        dataflow_logger = logging.getLogger("dataflow")
        assert dataflow_logger.level == logging.ERROR

    def test_restore_dataflow_logging(self):
        """restore_dataflow_logging should restore original levels."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import (
            configure_dataflow_logging,
            restore_dataflow_logging,
        )

        # Set a known state first
        nodes_logger = logging.getLogger("dataflow.core.nodes")
        nodes_logger.setLevel(logging.INFO)  # Set a known level
        original_level = nodes_logger.level

        # Change to DEBUG
        config = LoggingConfig(level=logging.DEBUG)
        configure_dataflow_logging(config)
        assert nodes_logger.level == logging.DEBUG

        # Restore
        restore_dataflow_logging()
        assert nodes_logger.level == original_level


@pytest.mark.unit
class TestLoggingConfigQuickMethods:
    """Test quick configuration methods."""

    def test_production_config(self):
        """production() should return WARNING level config."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig.production()
        assert config.level == logging.WARNING
        assert config.mask_sensitive_values is True

    def test_development_config(self):
        """development() should return DEBUG level config."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig.development()
        assert config.level == logging.DEBUG
        assert config.mask_sensitive_values is True  # Still mask in dev

    def test_quiet_config(self):
        """quiet() should return ERROR level config."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig.quiet()
        assert config.level == logging.ERROR


@pytest.mark.unit
class TestLoggingConfigExport:
    """Test LoggingConfig is properly exported."""

    def test_logging_config_importable_from_dataflow(self):
        """LoggingConfig should be importable from dataflow package."""
        from dataflow import LoggingConfig

        assert LoggingConfig is not None
        config = LoggingConfig()
        assert config.level == logging.WARNING

    def test_mask_sensitive_importable_from_dataflow(self):
        """mask_sensitive should be importable from dataflow package."""
        from dataflow import mask_sensitive

        assert mask_sensitive is not None

    def test_configure_dataflow_logging_importable_from_dataflow(self):
        """configure_dataflow_logging should be importable from dataflow package."""
        from dataflow import configure_dataflow_logging

        assert configure_dataflow_logging is not None
        assert callable(configure_dataflow_logging)

    def test_restore_dataflow_logging_importable_from_dataflow(self):
        """restore_dataflow_logging should be importable from dataflow package."""
        from dataflow import restore_dataflow_logging

        assert restore_dataflow_logging is not None
        assert callable(restore_dataflow_logging)

    def test_is_logging_configured_importable_from_dataflow(self):
        """is_logging_configured should be importable from dataflow package."""
        from dataflow import is_logging_configured

        assert is_logging_configured is not None
        assert callable(is_logging_configured)

    def test_mask_sensitive_values_importable_from_dataflow(self):
        """mask_sensitive_values should be importable from dataflow package."""
        from dataflow import mask_sensitive_values

        assert mask_sensitive_values is not None
        assert callable(mask_sensitive_values)
        # Verify it works
        result = mask_sensitive_values("password=secret")
        assert "secret" not in result

    def test_sensitive_masking_filter_importable_from_dataflow(self):
        """SensitiveMaskingFilter should be importable from dataflow package."""
        from dataflow import SensitiveMaskingFilter

        assert SensitiveMaskingFilter is not None
        # Verify it can be instantiated
        filter_instance = SensitiveMaskingFilter()
        assert filter_instance is not None

    def test_default_sensitive_patterns_importable_from_dataflow(self):
        """DEFAULT_SENSITIVE_PATTERNS should be importable from dataflow package."""
        from dataflow import DEFAULT_SENSITIVE_PATTERNS

        assert DEFAULT_SENSITIVE_PATTERNS is not None
        assert isinstance(DEFAULT_SENSITIVE_PATTERNS, list)
        assert len(DEFAULT_SENSITIVE_PATTERNS) > 0


@pytest.mark.unit
class TestLoggingConfigEdgeCases:
    """Test edge cases and error handling."""

    def test_mask_sensitive_empty_dict(self):
        """mask_sensitive should handle empty dictionary."""
        from dataflow.core.config import LoggingConfig, mask_sensitive

        config = LoggingConfig()
        result = mask_sensitive({}, config)
        assert result == {}

    def test_mask_sensitive_with_default_config(self):
        """mask_sensitive should use default config when None provided."""
        from dataflow.core.config import mask_sensitive

        data = {"password": "secret123"}
        result = mask_sensitive(data, None)
        assert result["password"] == "***MASKED***"

    def test_mask_sensitive_deeply_nested(self):
        """mask_sensitive should handle deeply nested structures."""
        from dataflow.core.config import LoggingConfig, mask_sensitive

        config = LoggingConfig()
        data = {
            "level1": {"level2": {"level3": {"api_key": "secret-key", "name": "test"}}}
        }
        result = mask_sensitive(data, config)
        assert result["level1"]["level2"]["level3"]["api_key"] == "***MASKED***"
        assert result["level1"]["level2"]["level3"]["name"] == "test"

    def test_mask_sensitive_list_values_preserved(self):
        """mask_sensitive should preserve list values (not recurse into lists)."""
        from dataflow.core.config import LoggingConfig, mask_sensitive

        config = LoggingConfig()
        data = {"items": [{"password": "secret"}], "count": 1}
        result = mask_sensitive(data, config)
        # Lists are preserved as-is (not recursively masked)
        assert result["items"] == [{"password": "secret"}]
        assert result["count"] == 1

    def test_get_level_for_category_with_all_categories(self):
        """get_level_for_category should work for all defined categories."""
        from dataflow.core.config import LoggingConfig

        config = LoggingConfig(
            level=logging.WARNING,
            node_execution=logging.DEBUG,
            sql_generation=logging.INFO,
            list_operations=logging.ERROR,
            migration=logging.CRITICAL,
            core=logging.DEBUG,
        )
        assert config.get_level_for_category("node_execution") == logging.DEBUG
        assert config.get_level_for_category("sql_generation") == logging.INFO
        assert config.get_level_for_category("list_operations") == logging.ERROR
        assert config.get_level_for_category("migration") == logging.CRITICAL
        assert config.get_level_for_category("core") == logging.DEBUG

    def test_from_env_with_all_categories(self):
        """from_env() should parse all category environment variables."""
        from dataflow.core.config import LoggingConfig

        with mock.patch.dict(
            os.environ,
            {
                "DATAFLOW_LOG_LEVEL": "INFO",
                "DATAFLOW_LOG_NODE_EXECUTION": "DEBUG",
                "DATAFLOW_LOG_SQL_GENERATION": "WARNING",
                "DATAFLOW_LOG_LIST_OPERATIONS": "ERROR",
                "DATAFLOW_LOG_MIGRATION": "CRITICAL",
                "DATAFLOW_LOG_CORE": "INFO",
            },
        ):
            config = LoggingConfig.from_env()
            assert config.level == logging.INFO
            assert config.node_execution == logging.DEBUG
            assert config.sql_generation == logging.WARNING
            assert config.list_operations == logging.ERROR
            assert config.migration == logging.CRITICAL
            assert config.core == logging.INFO


@pytest.mark.unit
class TestLoggingConfigIsConfigured:
    """Test is_logging_configured() function."""

    def setup_method(self):
        """Reset logging state before each test."""
        from dataflow.utils.suppress_warnings import restore_dataflow_logging

        restore_dataflow_logging()

    def teardown_method(self):
        """Clean up logging state after each test."""
        from dataflow.utils.suppress_warnings import restore_dataflow_logging

        restore_dataflow_logging()

    def test_is_logging_configured_initially_false(self):
        """is_logging_configured should return False initially."""
        from dataflow.utils.suppress_warnings import is_logging_configured

        assert is_logging_configured() is False

    def test_is_logging_configured_after_configure(self):
        """is_logging_configured should return True after configure."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import (
            configure_dataflow_logging,
            is_logging_configured,
        )

        configure_dataflow_logging(LoggingConfig())
        assert is_logging_configured() is True

    def test_is_logging_configured_after_restore(self):
        """is_logging_configured should return False after restore."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import (
            configure_dataflow_logging,
            is_logging_configured,
            restore_dataflow_logging,
        )

        configure_dataflow_logging(LoggingConfig())
        assert is_logging_configured() is True
        restore_dataflow_logging()
        assert is_logging_configured() is False
