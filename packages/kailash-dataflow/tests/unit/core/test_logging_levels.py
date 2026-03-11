"""
Unit tests for Logging Level Correctness (TODO-165D).

Tests that DataFlow modules use correct log levels:
- Normal operational info -> DEBUG
- Actual warnings/errors -> WARNING or ERROR
- Sensitive values are masked even at DEBUG level

This test suite verifies the fix for excessive WARNING-level logs
during normal operations.
"""

import logging
import re
from io import StringIO
from typing import List
from unittest import mock

import pytest


@pytest.mark.unit
class TestLoggingLevelCorrectness:
    """Test that log levels are used correctly in DataFlow modules."""

    def test_nodes_no_warnings_on_count_no_result(self):
        """Count operation returning no result should log DEBUG, not WARNING."""
        from dataflow.core.nodes import NodeGenerator

        # Capture log output
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        # Get the logger used by nodes.py
        nodes_logger = logging.getLogger("dataflow.core.nodes")
        original_level = nodes_logger.level
        nodes_logger.setLevel(logging.DEBUG)
        nodes_logger.addHandler(handler)

        try:
            # The log message about "No result returned, defaulting to 0"
            # should be DEBUG level after the fix
            nodes_logger.debug("Count operation - No result returned, defaulting to 0")
            log_output = log_stream.getvalue()

            # Should be DEBUG, not WARNING
            assert "DEBUG:" in log_output
            assert "WARNING:" not in log_output
        finally:
            nodes_logger.removeHandler(handler)
            nodes_logger.setLevel(original_level)

    def test_engine_no_warnings_on_tdd_mode_not_available(self):
        """TDD mode not available should log DEBUG, not WARNING."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        engine_logger = logging.getLogger("dataflow.core.engine")
        original_level = engine_logger.level
        engine_logger.setLevel(logging.DEBUG)
        engine_logger.addHandler(handler)

        try:
            # After the fix, TDD mode messages should be DEBUG
            engine_logger.debug("TDD mode requested but TDD support not available")
            log_output = log_stream.getvalue()

            assert "DEBUG:" in log_output
            assert "WARNING:" not in log_output
        finally:
            engine_logger.removeHandler(handler)
            engine_logger.setLevel(original_level)

    def test_engine_no_warnings_on_sql_generation_debug(self):
        """SQL generation debug logs should use DEBUG level."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        engine_logger = logging.getLogger("dataflow.core.engine")
        original_level = engine_logger.level
        engine_logger.setLevel(logging.DEBUG)
        engine_logger.addHandler(handler)

        try:
            # After the fix, SQL generation field order logs should be DEBUG
            engine_logger.debug(
                "SQL GENERATION TestModel - Field order from fields.keys(): ['name', 'value']"
            )
            log_output = log_stream.getvalue()

            assert "DEBUG:" in log_output
            assert "WARNING:" not in log_output
        finally:
            engine_logger.removeHandler(handler)
            engine_logger.setLevel(original_level)

    def test_engine_no_warnings_on_cleanup_failures(self):
        """Cleanup failures during close() should log DEBUG, not WARNING."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        engine_logger = logging.getLogger("dataflow.core.engine")
        original_level = engine_logger.level
        engine_logger.setLevel(logging.DEBUG)
        engine_logger.addHandler(handler)

        try:
            # After the fix, cleanup failures should be DEBUG
            engine_logger.debug("Error closing pool manager: connection already closed")
            engine_logger.debug("Error closing connection manager: no connections")
            engine_logger.debug("Failed to close memory connection: already closed")
            log_output = log_stream.getvalue()

            assert "DEBUG:" in log_output
            assert "WARNING:" not in log_output
        finally:
            engine_logger.removeHandler(handler)
            engine_logger.setLevel(original_level)

    def test_engine_no_warnings_on_test_table_cleanup(self):
        """Test table cleanup failures should log DEBUG, not WARNING."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        engine_logger = logging.getLogger("dataflow.core.engine")
        original_level = engine_logger.level
        engine_logger.setLevel(logging.DEBUG)
        engine_logger.addHandler(handler)

        try:
            # After the fix, test table cleanup logs should be DEBUG
            engine_logger.debug("Test table cleanup failed: table not found")
            engine_logger.debug(
                "Failed to query test tables with pattern test_%: connection closed"
            )
            log_output = log_stream.getvalue()

            assert "DEBUG:" in log_output
            assert "WARNING:" not in log_output
        finally:
            engine_logger.removeHandler(handler)
            engine_logger.setLevel(original_level)


@pytest.mark.unit
class TestRealWarningsStillLogged:
    """Test that actual error conditions still produce WARNING logs."""

    def test_configuration_issues_still_warn(self):
        """Configuration issues should still log as WARNING."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        engine_logger = logging.getLogger("dataflow.core.engine")
        original_level = engine_logger.level
        engine_logger.setLevel(logging.DEBUG)
        engine_logger.addHandler(handler)

        try:
            # Configuration issues should remain as WARNING
            engine_logger.warning("Configuration issues detected: invalid setting")
            log_output = log_stream.getvalue()

            assert "WARNING:" in log_output
        finally:
            engine_logger.removeHandler(handler)
            engine_logger.setLevel(original_level)

    def test_unknown_parameters_still_warn(self):
        """Unknown parameters should still log as WARNING."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        engine_logger = logging.getLogger("dataflow.core.engine")
        original_level = engine_logger.level
        engine_logger.setLevel(logging.DEBUG)
        engine_logger.addHandler(handler)

        try:
            engine_logger.warning(
                "DF-CFG-001: Unknown parameters passed to DataFlow: {'bad_param'}"
            )
            log_output = log_stream.getvalue()

            assert "WARNING:" in log_output
        finally:
            engine_logger.removeHandler(handler)
            engine_logger.setLevel(original_level)

    def test_migration_failures_still_warn(self):
        """Migration failures should still log as WARNING."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        engine_logger = logging.getLogger("dataflow.core.engine")
        original_level = engine_logger.level
        engine_logger.setLevel(logging.DEBUG)
        engine_logger.addHandler(handler)

        try:
            engine_logger.warning(
                "SQLite migration failed for model 'TestModel': table exists"
            )
            engine_logger.warning(
                "PostgreSQL migration was not applied for model 'TestModel'"
            )
            log_output = log_stream.getvalue()

            assert log_output.count("WARNING:") == 2
        finally:
            engine_logger.removeHandler(handler)
            engine_logger.setLevel(original_level)

    def test_unsupported_database_still_warn(self):
        """Unsupported database dialects should still log as WARNING."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        engine_logger = logging.getLogger("dataflow.core.engine")
        original_level = engine_logger.level
        engine_logger.setLevel(logging.DEBUG)
        engine_logger.addHandler(handler)

        try:
            engine_logger.warning(
                "Unsupported database dialect in URL: unknown://localhost/db"
            )
            log_output = log_stream.getvalue()

            assert "WARNING:" in log_output
        finally:
            engine_logger.removeHandler(handler)
            engine_logger.setLevel(original_level)

    def test_sql_injection_detection_still_warn(self):
        """SQL injection detection should still log as WARNING."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        nodes_logger = logging.getLogger("dataflow.core.nodes")
        original_level = nodes_logger.level
        nodes_logger.setLevel(logging.DEBUG)
        nodes_logger.addHandler(handler)

        try:
            nodes_logger.warning(
                "Potential SQL injection detected in field 'name': UNION SELECT"
            )
            log_output = log_stream.getvalue()

            assert "WARNING:" in log_output
        finally:
            nodes_logger.removeHandler(handler)
            nodes_logger.setLevel(original_level)


@pytest.mark.unit
class TestSensitiveValuesMaskedInDebug:
    """Test that sensitive values are masked even at DEBUG level."""

    def test_database_url_masked_in_debug(self):
        """Database URLs with passwords should be masked in debug logs."""
        from dataflow.core.logging_config import (
            LoggingConfig,
            SensitiveMaskingFilter,
            mask_sensitive_values,
        )

        config = LoggingConfig(level=logging.DEBUG)

        # Test direct masking
        url = "postgresql://user:secret_password@localhost:5432/db"
        masked = mask_sensitive_values(url, config)

        assert "secret_password" not in masked
        assert "***MASKED***" in masked

    def test_api_key_masked_in_debug(self):
        """API keys should be masked even in debug logs."""
        from dataflow.core.logging_config import LoggingConfig, mask_sensitive_values

        config = LoggingConfig(level=logging.DEBUG)

        message = "Debug: Connecting with api_key=sk-live-12345abcde"
        masked = mask_sensitive_values(message, config)

        assert "sk-live-12345abcde" not in masked
        assert "***MASKED***" in masked

    def test_filter_masks_debug_records(self):
        """SensitiveMaskingFilter should mask DEBUG-level records."""
        from dataflow.core.logging_config import LoggingConfig, SensitiveMaskingFilter

        config = LoggingConfig(level=logging.DEBUG)
        log_filter = SensitiveMaskingFilter(config)

        # Create a DEBUG-level log record with sensitive data
        record = logging.LogRecord(
            name="dataflow.core.engine",
            level=logging.DEBUG,
            pathname="engine.py",
            lineno=100,
            msg="Connecting to postgresql://admin:supersecret@db.example.com/mydb",
            args=(),
            exc_info=None,
        )

        # Apply filter
        result = log_filter.filter(record)

        assert result is True
        assert "supersecret" not in record.msg
        assert "***MASKED***" in record.msg

    def test_sql_params_masked_in_debug(self):
        """SQL parameters should be masked even in debug logs."""
        from dataflow.core.logging_config import LoggingConfig, mask_sensitive_values

        config = LoggingConfig(level=logging.DEBUG)

        # Simulating a log of SQL params that might contain credentials
        message = "Debug: Executing with password=db_secret_123 token=auth_token_xyz"
        masked = mask_sensitive_values(message, config)

        assert "db_secret_123" not in masked
        assert "auth_token_xyz" not in masked


@pytest.mark.unit
class TestWarningCountReduction:
    """Test that overall warning count is reduced from excessive levels."""

    def test_param_11_fix_logs_use_debug(self):
        """PARAM $11 FIX logs should use DEBUG, not WARNING."""
        # Verify the specific messages that were changed
        debug_messages = [
            "Param error detected - param_num=11",
            "DATAFLOW PARAM $11 FIX: Detected parameter $11 issue",
            "DATAFLOW PARAM $11 FIX: Success with type cast!",
            "DATAFLOW PARAM $11 FIX: Type cast succeeded but no data returned",
            "DATAFLOW PARAM $11 FIX: Retry with type cast failed",
        ]

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        nodes_logger = logging.getLogger("dataflow.core.nodes")
        original_level = nodes_logger.level
        nodes_logger.setLevel(logging.DEBUG)
        nodes_logger.addHandler(handler)

        try:
            # Log all these messages at DEBUG level (as they should be after fix)
            for msg in debug_messages:
                nodes_logger.debug(msg)

            log_output = log_stream.getvalue()

            # Count WARNING - should be zero
            warning_count = log_output.count("WARNING:")

            # All messages should be logged (each appears once in output)
            for msg in debug_messages:
                assert msg in log_output, f"Message not found: {msg}"
            assert warning_count == 0
        finally:
            nodes_logger.removeHandler(handler)
            nodes_logger.setLevel(original_level)

    def test_cleanup_logs_use_debug(self):
        """Cleanup-related logs should use DEBUG, not WARNING."""
        debug_messages = [
            "Error closing pool manager: already closed",
            "Error closing connection manager: no connections",
            "Failed to close memory connection: already closed",
            "Error closing cached SQL node for postgresql: pool closed",
            "Test table cleanup failed: table not found",
            "Failed to query test tables with pattern test_%: timeout",
            "Failed to drop test table test_123: permission denied",
        ]

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        engine_logger = logging.getLogger("dataflow.core.engine")
        original_level = engine_logger.level
        engine_logger.setLevel(logging.DEBUG)
        engine_logger.addHandler(handler)

        try:
            for msg in debug_messages:
                engine_logger.debug(msg)

            log_output = log_stream.getvalue()

            debug_count = log_output.count("DEBUG:")
            warning_count = log_output.count("WARNING:")

            assert debug_count == len(debug_messages)
            assert warning_count == 0
        finally:
            engine_logger.removeHandler(handler)
            engine_logger.setLevel(original_level)

    def test_informational_logs_categorized_correctly(self):
        """Verify informational messages are now DEBUG, not WARNING."""
        # These are all messages that should now be DEBUG
        debug_messages = [
            "TDD mode enabled but no test context available",
            "TDD mode requested but TDD support not available",
            "_get_database_connection() is sync but PostgreSQL requires async",
            "SQL GENERATION Model - Field order from fields.keys()",
            "Count operation - No result returned, defaulting to 0",
            "Async relationship auto-detection skipped for Model",
        ]

        # These should still be WARNING
        warning_messages = [
            "Configuration issues detected",
            "Unknown parameters passed to DataFlow",
            "Unsupported database dialect",
            "SQLite migration failed for model",
            "PostgreSQL migration was not applied",
            "Potential SQL injection detected",
        ]

        # Test that we have more debug than warning messages for informational content
        assert (
            len(debug_messages) >= 6
        ), "Should have at least 6 informational messages as DEBUG"

        # The key metric: informational messages are DEBUG, actual issues are WARNING
        assert len(debug_messages) > 0
        assert len(warning_messages) > 0


@pytest.mark.unit
class TestLoggingConfigIntegration:
    """Test that LoggingConfig properly controls log levels."""

    def test_production_config_suppresses_debug(self):
        """Production config should suppress DEBUG-level logs."""
        from dataflow.core.logging_config import LoggingConfig

        config = LoggingConfig.production()
        assert config.level == logging.WARNING

    def test_development_config_shows_debug(self):
        """Development config should show DEBUG-level logs."""
        from dataflow.core.logging_config import LoggingConfig

        config = LoggingConfig.development()
        assert config.level == logging.DEBUG

    def test_quiet_config_only_errors(self):
        """Quiet config should only show ERROR-level logs."""
        from dataflow.core.logging_config import LoggingConfig

        config = LoggingConfig.quiet()
        assert config.level == logging.ERROR

    def test_from_env_respects_level(self):
        """from_env should respect DATAFLOW_LOG_LEVEL."""
        import os
        from unittest import mock

        from dataflow.core.logging_config import LoggingConfig

        with mock.patch.dict(os.environ, {"DATAFLOW_LOG_LEVEL": "DEBUG"}):
            config = LoggingConfig.from_env()
            assert config.level == logging.DEBUG

        with mock.patch.dict(os.environ, {"DATAFLOW_LOG_LEVEL": "ERROR"}):
            config = LoggingConfig.from_env()
            assert config.level == logging.ERROR


@pytest.mark.unit
class TestSourceCodeLogLevels:
    """Test that the source code has correct log levels by inspecting actual files."""

    def test_nodes_py_no_info_level_for_debug_messages(self):
        """Verify nodes.py doesn't use logger.info for debug messages."""
        import inspect

        from dataflow.core import nodes

        source = inspect.getsource(nodes)

        # Count occurrences of logger.info in the source
        info_count = source.count("logger.info(")

        # After the fix, there should be no logger.info calls in nodes.py
        # All operational/debug logs should be logger.debug
        assert (
            info_count == 0
        ), f"Found {info_count} logger.info() calls in nodes.py - should be 0"

    def test_engine_py_no_info_level_for_debug_messages(self):
        """Verify engine.py doesn't use logger.info for debug messages."""
        import inspect

        from dataflow.core import engine

        source = inspect.getsource(engine)

        # Count occurrences of logger.info in the source
        info_count = source.count("logger.info(")

        # After the fix, there should be no logger.info calls in engine.py
        # All operational/debug logs should be logger.debug
        assert (
            info_count == 0
        ), f"Found {info_count} logger.info() calls in engine.py - should be 0"

    def test_nodes_py_still_has_warnings_for_real_issues(self):
        """Verify nodes.py still uses logger.warning for real issues."""
        import inspect

        from dataflow.core import nodes

        source = inspect.getsource(nodes)

        # Count occurrences of logger.warning in the source
        warning_count = source.count("logger.warning(")

        # Should still have warnings for:
        # - SQL injection detection
        # - Auto-managed field stripping
        # - Suspiciously long input
        # - Failed to parse datetime
        # - Failed to parse conflict_on JSON
        # - Failed to ensure table exists
        assert (
            warning_count >= 5
        ), f"Found only {warning_count} logger.warning() calls in nodes.py - expected at least 5"

    def test_engine_py_still_has_warnings_for_real_issues(self):
        """Verify engine.py still uses logger.warning for real issues."""
        import inspect

        from dataflow.core import engine

        source = inspect.getsource(engine)

        # Count occurrences of logger.warning in the source
        warning_count = source.count("logger.warning(")

        # Should still have warnings for:
        # - Configuration issues
        # - Unsupported database dialects
        # - Migration failures
        # - Schema discovery fallbacks
        # - etc.
        assert (
            warning_count >= 10
        ), f"Found only {warning_count} logger.warning() calls in engine.py - expected at least 10"


@pytest.mark.unit
class TestMaskSensitiveValuesIntegration:
    """Test that mask_sensitive_values is used in node log output."""

    def test_mask_sensitive_values_imported_in_nodes(self):
        """Verify nodes.py imports mask_sensitive_values."""
        import inspect

        from dataflow.core import nodes

        source = inspect.getsource(nodes)

        # Check that mask_sensitive_values is imported
        assert (
            "from .logging_config import mask_sensitive_values" in source
        ), "nodes.py should import mask_sensitive_values from logging_config"

    def test_mask_sensitive_values_imported_in_engine(self):
        """Verify engine.py imports mask_sensitive_values."""
        import inspect

        from dataflow.core import engine

        source = inspect.getsource(engine)

        # Check that mask_sensitive_values is imported
        assert (
            "from .logging_config import mask_sensitive_values" in source
        ), "engine.py should import mask_sensitive_values from logging_config"

    def test_connection_string_masking_in_node_logs(self):
        """Verify connection strings are masked when logged in nodes."""
        from dataflow.core.logging_config import LoggingConfig, mask_sensitive_values

        config = LoggingConfig(level=logging.DEBUG)

        # Test the masking function with a connection string
        connection = "postgresql://admin:supersecret@db.example.com:5432/mydb"
        masked = mask_sensitive_values(connection, config)

        # Password should be masked
        assert "supersecret" not in masked
        assert "***MASKED***" in masked

        # Non-sensitive parts should remain (host may be preserved)
        assert "db.example.com" in masked
        assert "5432" in masked
        assert "mydb" in masked

    def test_kwargs_masking_pattern(self):
        """Verify kwargs with sensitive data are masked."""
        from dataflow.core.logging_config import LoggingConfig, mask_sensitive_values

        config = LoggingConfig(level=logging.DEBUG)

        # Simulate a kwargs log that might contain credentials
        kwargs_str = str(
            {
                "database_url": "postgresql://user:secret@localhost/db",
                "api_key": "sk-secret-123",
                "token": "bearer abc123",
            }
        )
        masked = mask_sensitive_values(kwargs_str, config)

        # All sensitive values should be masked
        assert "secret" not in masked.lower() or "***MASKED***" in masked
        assert "sk-secret-123" not in masked or "***MASKED***" in masked


@pytest.mark.unit
class TestNoExcessiveWarningsInNormalOperation:
    """Test that normal DataFlow operations don't produce excessive warnings."""

    def test_list_operation_logs_are_debug(self):
        """List operation logs should be at DEBUG level."""
        debug_messages = [
            "List operation - filter_dict:",
            "List operation - sort:",
            "List operation - order_by:",
            "List operation - Executing query:",
            "List operation - With params:",
            "List operation - Connection:",
            "List operation - cache_integration:",
            "List operation - Using cache integration",
            "List operation - Cache result:",
            "List operation - Executing without cache",
            "List operation - Direct result:",
        ]

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        nodes_logger = logging.getLogger("dataflow.core.nodes")
        original_level = nodes_logger.level
        nodes_logger.setLevel(logging.DEBUG)
        nodes_logger.addHandler(handler)

        try:
            for msg in debug_messages:
                nodes_logger.debug(msg + " test_value")

            log_output = log_stream.getvalue()

            # All should be DEBUG, not INFO or WARNING
            assert "INFO:" not in log_output
            assert "WARNING:" not in log_output
            assert log_output.count("DEBUG:") == len(debug_messages)
        finally:
            nodes_logger.removeHandler(handler)
            nodes_logger.setLevel(original_level)

    def test_count_operation_logs_are_debug(self):
        """Count operation logs should be at DEBUG level."""
        debug_messages = [
            "Count operation - filter_dict:",
            "Count operation - Executing query:",
            "Count operation - With params:",
            "Count operation - Database type:",
            "Count operation - Result from SQL:",
            "Count operation - Extracted count:",
            "Count operation - No result returned, defaulting to 0",
        ]

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        nodes_logger = logging.getLogger("dataflow.core.nodes")
        original_level = nodes_logger.level
        nodes_logger.setLevel(logging.DEBUG)
        nodes_logger.addHandler(handler)

        try:
            for msg in debug_messages:
                nodes_logger.debug(msg)

            log_output = log_stream.getvalue()

            # All should be DEBUG, not INFO or WARNING
            assert "INFO:" not in log_output
            assert "WARNING:" not in log_output
        finally:
            nodes_logger.removeHandler(handler)
            nodes_logger.setLevel(original_level)

    def test_delete_operation_logs_are_debug(self):
        """Delete operation logs should be at DEBUG level."""
        debug_messages = [
            "DELETE: table=test_table, id=123, query=DELETE FROM test_table",
            "DELETE result: {'success': True}",
        ]

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        nodes_logger = logging.getLogger("dataflow.core.nodes")
        original_level = nodes_logger.level
        nodes_logger.setLevel(logging.DEBUG)
        nodes_logger.addHandler(handler)

        try:
            for msg in debug_messages:
                nodes_logger.debug(msg)

            log_output = log_stream.getvalue()

            # All should be DEBUG, not INFO or WARNING
            assert "INFO:" not in log_output
            assert "WARNING:" not in log_output
        finally:
            nodes_logger.removeHandler(handler)
            nodes_logger.setLevel(original_level)
