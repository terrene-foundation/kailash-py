"""
Structured logging with JSON formatting and context propagation.

This module provides structured logging capabilities for distributed debugging:
- StructuredLogger: JSON-formatted logging with persistent context
- LoggingManager: Centralized logger management and configuration
- Context propagation: trace_id, span_id, agent_id tracking
- ELK Stack integration: JSON format ready for Elasticsearch/Logstash

Part of Phase 4: Observability & Performance Monitoring (ADR-017)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from kaizen.core.autonomy.observability.types import LogEntry, LogLevel

logger = logging.getLogger(__name__)


class StructuredLogger:
    """
    Structured JSON logging with context propagation.

    Supports distributed debugging by automatically attaching context
    (agent_id, trace_id, span_id) to all log entries. Context is
    persistent across log calls until cleared or updated.

    Performance overhead target: <5% of execution time (ADR-017 NFR-2).

    Example:
        >>> logger = StructuredLogger("my-agent")
        >>> logger.add_context(agent_id="qa-agent", trace_id="abc123")
        >>> logger.info("Tool executed", tool_name="search", duration_ms=45.2)
        # Output: {"timestamp": "2025-10-24T...", "level": "INFO",
        #          "message": "Tool executed", "context": {"agent_id": "qa-agent",
        #          "trace_id": "abc123", "tool_name": "search", "duration_ms": 45.2}}
    """

    def __init__(self, name: str):
        """
        Initialize structured logger.

        Args:
            name: Logger name (typically agent ID or component name)
        """
        self.logger = logging.getLogger(name)
        self.context: dict[str, Any] = {}
        self._name = name

        # Configure JSON formatter if not already set
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def add_context(self, **kwargs) -> None:
        """
        Add persistent context to all subsequent log entries.

        Context is merged with existing context and persists until
        updated or cleared.

        Args:
            **kwargs: Key-value pairs to add to context

        Example:
            >>> logger.add_context(agent_id="qa-agent", user_id="user123")
            >>> logger.add_context(trace_id="abc123")  # Merges with existing
        """
        self.context.update(kwargs)
        logger.debug(f"Context updated: {kwargs}")

    def clear_context(self) -> None:
        """
        Clear all persistent context.

        Example:
            >>> logger.clear_context()
        """
        self.context.clear()
        logger.debug("Context cleared")

    def get_context(self) -> dict[str, Any]:
        """
        Get current context dictionary.

        Returns:
            Copy of current context
        """
        return self.context.copy()

    def debug(self, message: str, **extra) -> None:
        """
        Log debug message with context.

        Args:
            message: Log message
            **extra: Additional key-value pairs for this log entry only

        Example:
            >>> logger.debug("Starting operation", operation_id="op123")
        """
        self._log("DEBUG", message, extra)

    def info(self, message: str, **extra) -> None:
        """
        Log info message with context.

        Args:
            message: Log message
            **extra: Additional key-value pairs for this log entry only

        Example:
            >>> logger.info("Tool executed successfully", tool_name="search")
        """
        self._log("INFO", message, extra)

    def warning(self, message: str, **extra) -> None:
        """
        Log warning message with context.

        Args:
            message: Log message
            **extra: Additional key-value pairs for this log entry only

        Example:
            >>> logger.warning("API rate limit approaching", remaining_requests=10)
        """
        self._log("WARNING", message, extra)

    def error(self, message: str, **extra) -> None:
        """
        Log error message with context.

        Args:
            message: Log message
            **extra: Additional key-value pairs for this log entry only

        Example:
            >>> logger.error("Tool execution failed", tool_name="search", error="timeout")
        """
        self._log("ERROR", message, extra)

    def critical(self, message: str, **extra) -> None:
        """
        Log critical message with context.

        Args:
            message: Log message
            **extra: Additional key-value pairs for this log entry only

        Example:
            >>> logger.critical("Agent unrecoverable error", agent_id="qa-agent")
        """
        self._log("CRITICAL", message, extra)

    def _log(self, level: str, message: str, extra: dict[str, Any]) -> None:
        """
        Internal log method with JSON formatting.

        Creates LogEntry, merges with persistent context, and outputs
        as JSON string for ELK Stack compatibility.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Log message
            extra: Additional context for this log entry
        """
        # Create log entry
        log_entry = LogEntry(
            timestamp=datetime.now(timezone.utc),
            level=level,  # type: ignore
            message=message,
            context={**self.context, **extra},
            agent_id=self.context.get("agent_id"),
            trace_id=self.context.get("trace_id"),
            span_id=self.context.get("span_id"),
        )

        # Convert to JSON-serializable dict
        entry_dict = {
            "timestamp": log_entry.timestamp.isoformat(),
            "level": log_entry.level,
            "message": log_entry.message,
            "context": log_entry.context,
            "agent_id": log_entry.agent_id,
            "trace_id": log_entry.trace_id,
            "span_id": log_entry.span_id,
        }

        # Output as JSON string
        json_str = json.dumps(entry_dict)

        # Use standard logging with appropriate level
        log_method = getattr(self.logger, level.lower())
        log_method(json_str)

    def log_entry(self, entry: LogEntry) -> None:
        """
        Log a pre-constructed LogEntry object.

        Useful for logging entries created elsewhere.

        Args:
            entry: LogEntry to log
        """
        entry_dict = {
            "timestamp": entry.timestamp.isoformat(),
            "level": entry.level,
            "message": entry.message,
            "context": entry.context,
            "agent_id": entry.agent_id,
            "trace_id": entry.trace_id,
            "span_id": entry.span_id,
        }

        json_str = json.dumps(entry_dict)
        log_method = getattr(self.logger, entry.level.lower())
        log_method(json_str)


class LoggingManager:
    """
    Manages structured logging for all agents and components.

    Provides centralized logger creation and configuration.
    Maintains registry of all active loggers for batch operations.

    Example:
        >>> manager = LoggingManager()
        >>> agent_logger = manager.get_logger("qa-agent")
        >>> agent_logger.info("Agent started")
        >>>
        >>> tool_logger = manager.get_logger("tool-executor")
        >>> tool_logger.info("Tool executed")
    """

    def __init__(self):
        """Initialize logging manager."""
        self._loggers: dict[str, StructuredLogger] = {}
        logger.debug("LoggingManager initialized")

    def get_logger(self, name: str) -> StructuredLogger:
        """
        Get or create logger for name.

        Loggers are cached and reused. Multiple calls with the same
        name return the same logger instance.

        Args:
            name: Logger name (typically agent ID or component name)

        Returns:
            StructuredLogger instance

        Example:
            >>> logger = manager.get_logger("qa-agent")
        """
        if name not in self._loggers:
            self._loggers[name] = StructuredLogger(name)
            logger.debug(f"Created new logger: {name}")

        return self._loggers[name]

    def get_all_loggers(self) -> dict[str, StructuredLogger]:
        """
        Get all active loggers.

        Returns:
            Dictionary mapping logger names to StructuredLogger instances

        Example:
            >>> loggers = manager.get_all_loggers()
            >>> print(f"Active loggers: {list(loggers.keys())}")
        """
        return self._loggers.copy()

    def clear_all_context(self) -> None:
        """
        Clear context from all active loggers.

        Useful for resetting state between test runs or agent executions.

        Example:
            >>> manager.clear_all_context()
        """
        for logger_instance in self._loggers.values():
            logger_instance.clear_context()

        logger.info(f"Context cleared for {len(self._loggers)} loggers")

    def set_log_level(self, level: LogLevel) -> None:
        """
        Set log level for all active loggers.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

        Example:
            >>> manager.set_log_level("DEBUG")  # Enable debug logging
            >>> manager.set_log_level("WARNING")  # Only warnings and above
        """
        log_level = getattr(logging, level)

        for logger_instance in self._loggers.values():
            logger_instance.logger.setLevel(log_level)

        logger.info(f"Log level set to {level} for {len(self._loggers)} loggers")

    def get_logger_count(self) -> int:
        """
        Get count of active loggers.

        Returns:
            Number of active loggers

        Example:
            >>> count = manager.get_logger_count()
        """
        return len(self._loggers)


__all__ = [
    "StructuredLogger",
    "LoggingManager",
]
