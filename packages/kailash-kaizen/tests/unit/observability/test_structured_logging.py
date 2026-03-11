"""
Tier 1 Unit Tests for Structured Logging.

Tests StructuredLogger and LoggingManager with mocked components.
Validates JSON formatting, context propagation, and ELK integration.

Part of Phase 4: Observability & Performance Monitoring (ADR-017)
Target: <5% performance overhead (NFR-2)
"""

import json
import logging
from datetime import datetime, timezone
from unittest.mock import patch

from kaizen.core.autonomy.observability.logging import LoggingManager, StructuredLogger
from kaizen.core.autonomy.observability.types import LogEntry


class TestStructuredLoggerBasics:
    """Test basic StructuredLogger initialization and configuration."""

    def test_logger_initialization(self):
        """Test StructuredLogger initializes with name."""
        logger = StructuredLogger("test-agent")

        assert logger._name == "test-agent"
        assert isinstance(logger.context, dict)
        assert len(logger.context) == 0

    def test_logger_has_handler(self):
        """Test logger has stream handler configured."""
        logger = StructuredLogger("test-agent")

        assert len(logger.logger.handlers) > 0
        assert logger.logger.level == logging.INFO


class TestContextManagement:
    """Test context management (add, clear, get)."""

    def test_add_context_single_entry(self):
        """Test adding single context entry."""
        logger = StructuredLogger("test-agent")

        logger.add_context(agent_id="qa-agent")

        assert logger.context["agent_id"] == "qa-agent"
        assert len(logger.context) == 1

    def test_add_context_multiple_entries(self):
        """Test adding multiple context entries at once."""
        logger = StructuredLogger("test-agent")

        logger.add_context(agent_id="qa-agent", trace_id="abc123", user_id="user456")

        assert logger.context["agent_id"] == "qa-agent"
        assert logger.context["trace_id"] == "abc123"
        assert logger.context["user_id"] == "user456"
        assert len(logger.context) == 3

    def test_add_context_merges_with_existing(self):
        """Test context is merged, not replaced."""
        logger = StructuredLogger("test-agent")

        logger.add_context(agent_id="qa-agent")
        logger.add_context(trace_id="abc123")

        assert logger.context["agent_id"] == "qa-agent"
        assert logger.context["trace_id"] == "abc123"
        assert len(logger.context) == 2

    def test_add_context_overwrites_existing_key(self):
        """Test context key is overwritten if added again."""
        logger = StructuredLogger("test-agent")

        logger.add_context(agent_id="old-agent")
        logger.add_context(agent_id="new-agent")

        assert logger.context["agent_id"] == "new-agent"

    def test_clear_context(self):
        """Test clearing all context."""
        logger = StructuredLogger("test-agent")

        logger.add_context(agent_id="qa-agent", trace_id="abc123")
        logger.clear_context()

        assert len(logger.context) == 0

    def test_get_context_returns_copy(self):
        """Test get_context returns a copy, not reference."""
        logger = StructuredLogger("test-agent")

        logger.add_context(agent_id="qa-agent")
        context_copy = logger.get_context()
        context_copy["modified"] = "value"

        # Original context should be unchanged
        assert "modified" not in logger.context
        assert len(logger.context) == 1


class TestLogLevels:
    """Test all log levels (debug, info, warning, error, critical)."""

    @patch("logging.Logger.debug")
    def test_debug_logging(self, mock_debug):
        """Test debug level logging."""
        logger = StructuredLogger("test-agent")

        logger.debug("Debug message", key="value")

        assert mock_debug.called
        call_args = mock_debug.call_args[0][0]
        log_dict = json.loads(call_args)

        assert log_dict["level"] == "DEBUG"
        assert log_dict["message"] == "Debug message"
        assert log_dict["context"]["key"] == "value"

    @patch("logging.Logger.info")
    def test_info_logging(self, mock_info):
        """Test info level logging."""
        logger = StructuredLogger("test-agent")

        logger.info("Info message", key="value")

        assert mock_info.called
        call_args = mock_info.call_args[0][0]
        log_dict = json.loads(call_args)

        assert log_dict["level"] == "INFO"
        assert log_dict["message"] == "Info message"

    @patch("logging.Logger.warning")
    def test_warning_logging(self, mock_warning):
        """Test warning level logging."""
        logger = StructuredLogger("test-agent")

        logger.warning("Warning message", key="value")

        assert mock_warning.called
        call_args = mock_warning.call_args[0][0]
        log_dict = json.loads(call_args)

        assert log_dict["level"] == "WARNING"
        assert log_dict["message"] == "Warning message"

    @patch("logging.Logger.error")
    def test_error_logging(self, mock_error):
        """Test error level logging."""
        logger = StructuredLogger("test-agent")

        logger.error("Error message", key="value")

        assert mock_error.called
        call_args = mock_error.call_args[0][0]
        log_dict = json.loads(call_args)

        assert log_dict["level"] == "ERROR"
        assert log_dict["message"] == "Error message"

    @patch("logging.Logger.critical")
    def test_critical_logging(self, mock_critical):
        """Test critical level logging."""
        logger = StructuredLogger("test-agent")

        logger.critical("Critical message", key="value")

        assert mock_critical.called
        call_args = mock_critical.call_args[0][0]
        log_dict = json.loads(call_args)

        assert log_dict["level"] == "CRITICAL"
        assert log_dict["message"] == "Critical message"


class TestJSONFormatting:
    """Test JSON output formatting for ELK integration."""

    @patch("logging.Logger.info")
    def test_json_format_structure(self, mock_info):
        """Test log output is valid JSON with required fields."""
        logger = StructuredLogger("test-agent")

        logger.info("Test message")

        call_args = mock_info.call_args[0][0]
        log_dict = json.loads(call_args)  # Should not raise exception

        # Verify required fields
        assert "timestamp" in log_dict
        assert "level" in log_dict
        assert "message" in log_dict
        assert "context" in log_dict
        assert "agent_id" in log_dict
        assert "trace_id" in log_dict
        assert "span_id" in log_dict

    @patch("logging.Logger.info")
    def test_json_timestamp_format(self, mock_info):
        """Test timestamp is ISO 8601 format."""
        logger = StructuredLogger("test-agent")

        logger.info("Test message")

        call_args = mock_info.call_args[0][0]
        log_dict = json.loads(call_args)

        # Verify ISO 8601 format (can be parsed)
        timestamp = datetime.fromisoformat(log_dict["timestamp"])
        assert isinstance(timestamp, datetime)

    @patch("logging.Logger.info")
    def test_json_nested_context(self, mock_info):
        """Test nested context is properly serialized."""
        logger = StructuredLogger("test-agent")

        logger.info("Test message", nested={"key1": "value1", "key2": 42})

        call_args = mock_info.call_args[0][0]
        log_dict = json.loads(call_args)

        assert log_dict["context"]["nested"]["key1"] == "value1"
        assert log_dict["context"]["nested"]["key2"] == 42


class TestContextPropagation:
    """Test context propagation across log calls."""

    @patch("logging.Logger.info")
    def test_context_propagates_to_all_logs(self, mock_info):
        """Test persistent context appears in all log entries."""
        logger = StructuredLogger("test-agent")

        logger.add_context(agent_id="qa-agent", trace_id="abc123")
        logger.info("First message")
        logger.info("Second message")

        # Both calls should have context
        assert mock_info.call_count == 2

        first_call = json.loads(mock_info.call_args_list[0][0][0])
        second_call = json.loads(mock_info.call_args_list[1][0][0])

        assert first_call["context"]["agent_id"] == "qa-agent"
        assert first_call["context"]["trace_id"] == "abc123"
        assert second_call["context"]["agent_id"] == "qa-agent"
        assert second_call["context"]["trace_id"] == "abc123"

    @patch("logging.Logger.info")
    def test_extra_merged_with_context(self, mock_info):
        """Test extra kwargs are merged with persistent context."""
        logger = StructuredLogger("test-agent")

        logger.add_context(agent_id="qa-agent")
        logger.info("Test message", tool_name="search")

        call_args = mock_info.call_args[0][0]
        log_dict = json.loads(call_args)

        # Both persistent and extra context should be present
        assert log_dict["context"]["agent_id"] == "qa-agent"
        assert log_dict["context"]["tool_name"] == "search"

    @patch("logging.Logger.info")
    def test_extra_overwrites_persistent_context(self, mock_info):
        """Test extra kwargs override persistent context with same key."""
        logger = StructuredLogger("test-agent")

        logger.add_context(key="persistent")
        logger.info("Test message", key="temporary")

        call_args = mock_info.call_args[0][0]
        log_dict = json.loads(call_args)

        # Extra should override persistent
        assert log_dict["context"]["key"] == "temporary"

    @patch("logging.Logger.info")
    def test_context_cleared_not_in_logs(self, mock_info):
        """Test cleared context doesn't appear in subsequent logs."""
        logger = StructuredLogger("test-agent")

        logger.add_context(agent_id="qa-agent")
        logger.clear_context()
        logger.info("Test message")

        call_args = mock_info.call_args[0][0]
        log_dict = json.loads(call_args)

        # Context should be empty (only extra from this call)
        assert "agent_id" not in log_dict["context"]

    @patch("logging.Logger.info")
    def test_top_level_ids_extracted_from_context(self, mock_info):
        """Test agent_id, trace_id, span_id extracted to top level."""
        logger = StructuredLogger("test-agent")

        logger.add_context(agent_id="qa-agent", trace_id="trace123", span_id="span456")
        logger.info("Test message")

        call_args = mock_info.call_args[0][0]
        log_dict = json.loads(call_args)

        # Should appear at top level AND in context
        assert log_dict["agent_id"] == "qa-agent"
        assert log_dict["trace_id"] == "trace123"
        assert log_dict["span_id"] == "span456"
        assert log_dict["context"]["agent_id"] == "qa-agent"
        assert log_dict["context"]["trace_id"] == "trace123"
        assert log_dict["context"]["span_id"] == "span456"


class TestLogEntryLogging:
    """Test logging pre-constructed LogEntry objects."""

    @patch("logging.Logger.info")
    def test_log_entry_method(self, mock_info):
        """Test logging a LogEntry object directly."""
        logger = StructuredLogger("test-agent")

        entry = LogEntry(
            timestamp=datetime.now(timezone.utc),
            level="INFO",
            message="Test message",
            context={"key": "value"},
            agent_id="qa-agent",
            trace_id="abc123",
            span_id="span456",
        )

        logger.log_entry(entry)

        assert mock_info.called
        call_args = mock_info.call_args[0][0]
        log_dict = json.loads(call_args)

        assert log_dict["message"] == "Test message"
        assert log_dict["agent_id"] == "qa-agent"
        assert log_dict["context"]["key"] == "value"


class TestLoggingManagerBasics:
    """Test LoggingManager initialization and logger creation."""

    def test_manager_initialization(self):
        """Test LoggingManager initializes empty."""
        manager = LoggingManager()

        assert len(manager._loggers) == 0
        assert manager.get_logger_count() == 0

    def test_get_logger_creates_new(self):
        """Test get_logger creates new logger if not exists."""
        manager = LoggingManager()

        logger = manager.get_logger("test-agent")

        assert isinstance(logger, StructuredLogger)
        assert logger._name == "test-agent"
        assert manager.get_logger_count() == 1

    def test_get_logger_returns_existing(self):
        """Test get_logger returns same instance for same name."""
        manager = LoggingManager()

        logger1 = manager.get_logger("test-agent")
        logger2 = manager.get_logger("test-agent")

        assert logger1 is logger2  # Same instance
        assert manager.get_logger_count() == 1

    def test_get_logger_multiple_names(self):
        """Test get_logger creates separate loggers for different names."""
        manager = LoggingManager()

        logger1 = manager.get_logger("agent-1")
        logger2 = manager.get_logger("agent-2")

        assert logger1 is not logger2
        assert logger1._name == "agent-1"
        assert logger2._name == "agent-2"
        assert manager.get_logger_count() == 2


class TestLoggingManagerBatchOperations:
    """Test LoggingManager batch operations across all loggers."""

    def test_get_all_loggers(self):
        """Test get_all_loggers returns all active loggers."""
        manager = LoggingManager()

        manager.get_logger("agent-1")
        manager.get_logger("agent-2")
        manager.get_logger("agent-3")

        all_loggers = manager.get_all_loggers()

        assert len(all_loggers) == 3
        assert "agent-1" in all_loggers
        assert "agent-2" in all_loggers
        assert "agent-3" in all_loggers

    def test_get_all_loggers_returns_copy(self):
        """Test get_all_loggers returns copy, not reference."""
        manager = LoggingManager()

        manager.get_logger("agent-1")
        loggers = manager.get_all_loggers()
        loggers["modified"] = StructuredLogger("modified")

        # Original should be unchanged
        assert "modified" not in manager._loggers
        assert manager.get_logger_count() == 1

    def test_clear_all_context(self):
        """Test clear_all_context clears context from all loggers."""
        manager = LoggingManager()

        logger1 = manager.get_logger("agent-1")
        logger2 = manager.get_logger("agent-2")

        logger1.add_context(key1="value1")
        logger2.add_context(key2="value2")

        manager.clear_all_context()

        assert len(logger1.context) == 0
        assert len(logger2.context) == 0

    def test_set_log_level_all_loggers(self):
        """Test set_log_level affects all loggers."""
        manager = LoggingManager()

        logger1 = manager.get_logger("agent-1")
        logger2 = manager.get_logger("agent-2")

        manager.set_log_level("DEBUG")

        assert logger1.logger.level == logging.DEBUG
        assert logger2.logger.level == logging.DEBUG

    def test_set_log_level_different_levels(self):
        """Test setting different log levels."""
        manager = LoggingManager()

        logger = manager.get_logger("test-agent")

        manager.set_log_level("WARNING")
        assert logger.logger.level == logging.WARNING

        manager.set_log_level("ERROR")
        assert logger.logger.level == logging.ERROR


# Note: Performance validation (ADR-017 NFR-2: <5% overhead) is tested in
# Tier 2 integration tests with realistic agent workloads. Tier 1 unit tests
# with mocks don't provide meaningful performance metrics.
