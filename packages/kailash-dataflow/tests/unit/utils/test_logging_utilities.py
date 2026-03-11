"""
Unit tests for Logging Utilities - Phase 7B.

Tests the logging utility functions for:
- configure_dataflow_logging with various parameters
- restore_dataflow_logging with state management
- get_dataflow_logger helper function
- dataflow_logging_context context manager
"""

import logging
from unittest import mock

import pytest

# =============================================================================
# Tests for configure_dataflow_logging
# =============================================================================


@pytest.mark.unit
class TestConfigureDataflowLogging:
    """Test the configure_dataflow_logging function."""

    def setup_method(self):
        """Reset logging state before each test."""
        from dataflow.utils.suppress_warnings import restore_dataflow_logging

        restore_dataflow_logging()

    def teardown_method(self):
        """Clean up logging state after each test."""
        from dataflow.utils.suppress_warnings import restore_dataflow_logging

        restore_dataflow_logging()

    def test_configure_with_config_object(self):
        """Should configure logging using LoggingConfig object."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import (
            configure_dataflow_logging,
            is_logging_configured,
        )

        config = LoggingConfig(level=logging.DEBUG)
        configure_dataflow_logging(config)

        assert is_logging_configured() is True
        dataflow_logger = logging.getLogger("dataflow")
        assert dataflow_logger.level == logging.DEBUG

    def test_configure_with_level_param(self):
        """Should configure logging using explicit level parameter."""
        from dataflow.utils.suppress_warnings import configure_dataflow_logging

        configure_dataflow_logging(level=logging.ERROR)

        dataflow_logger = logging.getLogger("dataflow")
        assert dataflow_logger.level == logging.ERROR

    def test_level_param_overrides_config(self):
        """Level parameter should override config.level."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import configure_dataflow_logging

        config = LoggingConfig(level=logging.DEBUG)
        configure_dataflow_logging(config=config, level=logging.CRITICAL)

        dataflow_logger = logging.getLogger("dataflow")
        assert dataflow_logger.level == logging.CRITICAL

    def test_propagation_disabled_when_false(self):
        """Should disable propagation when config.propagate is False."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import configure_dataflow_logging

        # The old LoggingConfig doesn't have propagate, so we test by
        # directly setting the attribute
        config = LoggingConfig(level=logging.DEBUG)
        config.propagate = False
        configure_dataflow_logging(config)

        dataflow_logger = logging.getLogger("dataflow")
        assert dataflow_logger.propagate is False

    def test_masking_filter_added_when_enabled(self):
        """Should add SensitiveMaskingFilter when masking is enabled."""
        from dataflow.core.config import LoggingConfig
        from dataflow.core.logging_config import SensitiveMaskingFilter
        from dataflow.utils.suppress_warnings import configure_dataflow_logging

        # Add a handler to test filter addition
        dataflow_logger = logging.getLogger("dataflow")
        handler = logging.StreamHandler()
        dataflow_logger.addHandler(handler)

        try:
            config = LoggingConfig(mask_sensitive_values=True)
            configure_dataflow_logging(config)

            # Check if filter was added to handler
            has_masking_filter = any(
                isinstance(f, SensitiveMaskingFilter) for f in handler.filters
            )
            assert has_masking_filter is True
        finally:
            dataflow_logger.removeHandler(handler)

    def test_all_loggers_configured(self):
        """Should configure all DataFlow loggers."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import configure_dataflow_logging

        config = LoggingConfig(level=logging.INFO)
        configure_dataflow_logging(config)

        # Check various DataFlow loggers
        loggers_to_check = [
            "dataflow",
            "dataflow.core.nodes",
            "dataflow.core.engine",
            "dataflow.migrations",
            "dataflow.features.bulk",
            "dataflow.utils",
        ]

        for logger_name in loggers_to_check:
            logger = logging.getLogger(logger_name)
            assert logger.level == logging.INFO, f"Logger {logger_name} not configured"

    def test_configure_from_env_when_no_params(self):
        """Should use from_env() when no parameters provided."""
        import os

        from dataflow.utils.suppress_warnings import configure_dataflow_logging

        with mock.patch.dict(os.environ, {"DATAFLOW_LOG_LEVEL": "CRITICAL"}):
            configure_dataflow_logging()

        dataflow_logger = logging.getLogger("dataflow")
        assert dataflow_logger.level == logging.CRITICAL


# =============================================================================
# Tests for restore_dataflow_logging
# =============================================================================


@pytest.mark.unit
class TestRestoreDataflowLogging:
    """Test the restore_dataflow_logging function."""

    def setup_method(self):
        """Reset logging state before each test."""
        from dataflow.utils.suppress_warnings import restore_dataflow_logging

        restore_dataflow_logging()

    def teardown_method(self):
        """Clean up logging state after each test."""
        from dataflow.utils.suppress_warnings import restore_dataflow_logging

        restore_dataflow_logging()

    def test_restore_original_level(self):
        """Should restore original log level after configure."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import (
            configure_dataflow_logging,
            restore_dataflow_logging,
        )

        dataflow_logger = logging.getLogger("dataflow")
        original_level = dataflow_logger.level

        # Change to DEBUG
        config = LoggingConfig(level=logging.DEBUG)
        configure_dataflow_logging(config)
        assert dataflow_logger.level == logging.DEBUG

        # Restore
        restore_dataflow_logging()
        assert dataflow_logger.level == original_level

    def test_multiple_restore_calls_safe(self):
        """Multiple restore calls should be safe (no errors)."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import (
            configure_dataflow_logging,
            is_logging_configured,
            restore_dataflow_logging,
        )

        config = LoggingConfig(level=logging.DEBUG)
        configure_dataflow_logging(config)

        # Multiple restore calls should not raise
        restore_dataflow_logging()
        assert is_logging_configured() is False

        restore_dataflow_logging()  # Second call
        assert is_logging_configured() is False

        restore_dataflow_logging()  # Third call
        assert is_logging_configured() is False

    def test_restore_removes_masking_filter(self):
        """Should remove SensitiveMaskingFilter on restore."""
        from dataflow.core.config import LoggingConfig
        from dataflow.core.logging_config import SensitiveMaskingFilter
        from dataflow.utils.suppress_warnings import (
            configure_dataflow_logging,
            restore_dataflow_logging,
        )

        # Add a handler to test filter removal
        dataflow_logger = logging.getLogger("dataflow")
        handler = logging.StreamHandler()
        dataflow_logger.addHandler(handler)

        try:
            config = LoggingConfig(mask_sensitive_values=True)
            configure_dataflow_logging(config)

            # Verify filter was added
            has_masking_filter = any(
                isinstance(f, SensitiveMaskingFilter) for f in handler.filters
            )
            assert has_masking_filter is True

            # Restore and check filter removed
            restore_dataflow_logging()
            has_masking_filter = any(
                isinstance(f, SensitiveMaskingFilter) for f in handler.filters
            )
            assert has_masking_filter is False
        finally:
            dataflow_logger.removeHandler(handler)

    def test_restore_propagate_setting(self):
        """Should restore original propagate setting."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import (
            configure_dataflow_logging,
            restore_dataflow_logging,
        )

        dataflow_logger = logging.getLogger("dataflow")
        original_propagate = dataflow_logger.propagate

        # Change propagate by setting the attribute on config
        config = LoggingConfig(level=logging.DEBUG)
        config.propagate = not original_propagate
        configure_dataflow_logging(config)
        assert dataflow_logger.propagate == (not original_propagate)

        # Restore
        restore_dataflow_logging()
        assert dataflow_logger.propagate == original_propagate


# =============================================================================
# Tests for get_dataflow_logger
# =============================================================================


@pytest.mark.unit
class TestGetDataflowLogger:
    """Test the get_dataflow_logger helper function."""

    def test_adds_dataflow_prefix(self):
        """Should add 'dataflow.' prefix to unprefixed names."""
        from dataflow.utils.suppress_warnings import get_dataflow_logger

        logger = get_dataflow_logger("my_module")
        assert logger.name == "dataflow.my_module"

    def test_already_prefixed_unchanged(self):
        """Should not double-prefix already prefixed names."""
        from dataflow.utils.suppress_warnings import get_dataflow_logger

        logger = get_dataflow_logger("dataflow.core.nodes")
        assert logger.name == "dataflow.core.nodes"

    def test_empty_string_returns_root(self):
        """Empty string should return root dataflow logger."""
        from dataflow.utils.suppress_warnings import get_dataflow_logger

        logger = get_dataflow_logger("")
        assert logger.name == "dataflow"

    def test_dataflow_string_returns_root(self):
        """'dataflow' string should return root dataflow logger."""
        from dataflow.utils.suppress_warnings import get_dataflow_logger

        logger = get_dataflow_logger("dataflow")
        assert logger.name == "dataflow"

    def test_returns_same_logger_instance(self):
        """Should return the same logger instance for same name."""
        from dataflow.utils.suppress_warnings import get_dataflow_logger

        logger1 = get_dataflow_logger("my_module")
        logger2 = get_dataflow_logger("my_module")
        assert logger1 is logger2

    def test_nested_names(self):
        """Should handle nested module names correctly."""
        from dataflow.utils.suppress_warnings import get_dataflow_logger

        logger = get_dataflow_logger("features.bulk.operations")
        assert logger.name == "dataflow.features.bulk.operations"


# =============================================================================
# Tests for dataflow_logging_context
# =============================================================================


@pytest.mark.unit
class TestDataflowLoggingContext:
    """Test the dataflow_logging_context context manager."""

    def setup_method(self):
        """Reset logging state before each test."""
        from dataflow.utils.suppress_warnings import restore_dataflow_logging

        restore_dataflow_logging()

    def teardown_method(self):
        """Clean up logging state after each test."""
        from dataflow.utils.suppress_warnings import restore_dataflow_logging

        restore_dataflow_logging()

    def test_changes_level_inside_context(self):
        """Should change log level inside context."""
        from dataflow.utils.suppress_warnings import dataflow_logging_context

        dataflow_logger = logging.getLogger("dataflow")
        original_level = dataflow_logger.level

        with dataflow_logging_context(level=logging.DEBUG):
            assert dataflow_logger.level == logging.DEBUG

        # After context, should be restored
        assert dataflow_logger.level == original_level

    def test_restores_level_after_context(self):
        """Should restore original level after context exits."""
        from dataflow.utils.suppress_warnings import dataflow_logging_context

        dataflow_logger = logging.getLogger("dataflow")
        dataflow_logger.setLevel(logging.WARNING)
        original_level = dataflow_logger.level

        with dataflow_logging_context(level=logging.ERROR):
            assert dataflow_logger.level == logging.ERROR

        assert dataflow_logger.level == original_level

    def test_with_config_object(self):
        """Should work with LoggingConfig object."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import dataflow_logging_context

        dataflow_logger = logging.getLogger("dataflow")
        original_level = dataflow_logger.level

        config = LoggingConfig(level=logging.CRITICAL)
        with dataflow_logging_context(config=config):
            assert dataflow_logger.level == logging.CRITICAL

        assert dataflow_logger.level == original_level

    def test_restores_on_exception(self):
        """Should restore logging even when exception occurs."""
        from dataflow.utils.suppress_warnings import dataflow_logging_context

        dataflow_logger = logging.getLogger("dataflow")
        dataflow_logger.setLevel(logging.WARNING)
        original_level = dataflow_logger.level

        try:
            with dataflow_logging_context(level=logging.DEBUG):
                assert dataflow_logger.level == logging.DEBUG
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Level should still be restored
        assert dataflow_logger.level == original_level

    def test_nested_contexts(self):
        """Should handle nested contexts correctly."""
        from dataflow.utils.suppress_warnings import dataflow_logging_context

        dataflow_logger = logging.getLogger("dataflow")
        dataflow_logger.setLevel(logging.WARNING)
        original_level = dataflow_logger.level

        with dataflow_logging_context(level=logging.INFO):
            assert dataflow_logger.level == logging.INFO

            with dataflow_logging_context(level=logging.DEBUG):
                assert dataflow_logger.level == logging.DEBUG

            # Should restore to INFO (outer context level)
            assert dataflow_logger.level == logging.INFO

        # Should restore to original
        assert dataflow_logger.level == original_level

    def test_is_logging_configured_inside_context(self):
        """is_logging_configured should return True inside context."""
        from dataflow.utils.suppress_warnings import (
            dataflow_logging_context,
            is_logging_configured,
        )

        assert is_logging_configured() is False

        with dataflow_logging_context(level=logging.DEBUG):
            assert is_logging_configured() is True

        assert is_logging_configured() is False


# =============================================================================
# Tests for exports
# =============================================================================


@pytest.mark.unit
class TestLoggingUtilitiesExports:
    """Test that logging utilities are properly exported."""

    def test_get_dataflow_logger_importable_from_dataflow(self):
        """get_dataflow_logger should be importable from dataflow package."""
        from dataflow import get_dataflow_logger

        assert get_dataflow_logger is not None
        assert callable(get_dataflow_logger)

    def test_dataflow_logging_context_importable_from_dataflow(self):
        """dataflow_logging_context should be importable from dataflow package."""
        from dataflow import dataflow_logging_context

        assert dataflow_logging_context is not None

    def test_get_dataflow_logger_importable_from_utils(self):
        """get_dataflow_logger should be importable from utils module."""
        from dataflow.utils import get_dataflow_logger

        assert get_dataflow_logger is not None
        assert callable(get_dataflow_logger)

    def test_dataflow_logging_context_importable_from_utils(self):
        """dataflow_logging_context should be importable from utils module."""
        from dataflow.utils import dataflow_logging_context

        assert dataflow_logging_context is not None

    def test_all_logging_functions_importable_from_utils(self):
        """All logging functions should be importable from utils."""
        from dataflow.utils import (
            configure_dataflow_logging,
            dataflow_logging_context,
            get_dataflow_logger,
            is_logging_configured,
            restore_core_sdk_warnings,
            restore_dataflow_logging,
            suppress_core_sdk_warnings,
        )

        assert configure_dataflow_logging is not None
        assert restore_dataflow_logging is not None
        assert is_logging_configured is not None
        assert get_dataflow_logger is not None
        assert dataflow_logging_context is not None
        assert suppress_core_sdk_warnings is not None
        assert restore_core_sdk_warnings is not None


# =============================================================================
# Tests for original_logger_state management
# =============================================================================


@pytest.mark.unit
class TestOriginalLoggerState:
    """Test the _original_logger_state tracking."""

    def setup_method(self):
        """Reset logging state before each test."""
        from dataflow.utils.suppress_warnings import restore_dataflow_logging

        restore_dataflow_logging()

    def teardown_method(self):
        """Clean up logging state after each test."""
        from dataflow.utils.suppress_warnings import restore_dataflow_logging

        restore_dataflow_logging()

    def test_original_state_cleared_on_restore(self):
        """_original_logger_state should be cleared after restore."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import (
            _original_logger_state,
            configure_dataflow_logging,
            restore_dataflow_logging,
        )

        config = LoggingConfig(level=logging.DEBUG)
        configure_dataflow_logging(config)

        # State should be populated
        assert len(_original_logger_state) > 0

        restore_dataflow_logging()

        # State should be cleared
        # Note: We need to re-import after restore to get the updated value
        from dataflow.utils.suppress_warnings import _original_logger_state

        assert len(_original_logger_state) == 0

    def test_original_levels_cleared_on_restore(self):
        """_original_levels should be cleared after restore."""
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import (
            _original_levels,
            configure_dataflow_logging,
            restore_dataflow_logging,
        )

        config = LoggingConfig(level=logging.DEBUG)
        configure_dataflow_logging(config)

        # Levels should be populated
        assert len(_original_levels) > 0

        restore_dataflow_logging()

        # Levels should be cleared
        from dataflow.utils.suppress_warnings import _original_levels

        assert len(_original_levels) == 0
