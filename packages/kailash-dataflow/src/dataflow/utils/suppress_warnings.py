"""
Suppress verbose Core SDK warnings and configure DataFlow logging.

This module provides utilities to:
1. Suppress console warnings from Core SDK that flood the output
2. Configure DataFlow logging levels centrally
3. Support environment variable configuration for 12-factor apps
4. Provide context managers for temporary logging configuration
5. Helper functions for getting properly prefixed loggers

See ADR-002 for architectural details.
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Union

# Logger name to category mapping
_LOGGER_CATEGORIES: Dict[str, str] = {
    "dataflow": "core",
    "dataflow.core.nodes": "node_execution",
    "dataflow.core.engine": "core",
    "dataflow.migrations": "migration",
    "dataflow.migrations.auto_migration_system": "migration",
    "dataflow.migrations.schema_state_manager": "migration",
    "dataflow.features.bulk": "node_execution",
    "dataflow.utils": "core",
}

# Storage for original log levels (for restore functionality)
_original_levels: Dict[str, int] = {}

# Track if logging has been configured
_logging_configured: bool = False

# Storage for complete original logger state (level, handlers, propagate, filters)
_original_logger_state: Dict[str, Any] = {}


def suppress_core_sdk_warnings():
    """
    Suppress verbose Core SDK warnings that flood console output.

    Warnings suppressed:
    - kailash.nodes.base: "Overwriting existing node registration"
    - kailash.resources.registry: "Overwriting existing factory for resource"

    These warnings are benign in DataFlow context where node registration
    overwriting is expected during model decoration.

    Usage:
        from dataflow.utils.suppress_warnings import suppress_core_sdk_warnings
        suppress_core_sdk_warnings()
    """
    # Suppress node registration warnings
    logging.getLogger("kailash.nodes.base").setLevel(logging.ERROR)

    # Suppress resource factory warnings
    logging.getLogger("kailash.resources.registry").setLevel(logging.ERROR)


def restore_core_sdk_warnings():
    """
    Restore Core SDK warning levels to default (WARNING).

    Use this to re-enable warnings for debugging if needed.

    Usage:
        from dataflow.utils.suppress_warnings import restore_core_sdk_warnings
        restore_core_sdk_warnings()
    """
    # Restore node registration warnings
    logging.getLogger("kailash.nodes.base").setLevel(logging.WARNING)

    # Restore resource factory warnings
    logging.getLogger("kailash.resources.registry").setLevel(logging.WARNING)


def configure_dataflow_logging(
    config: Optional["LoggingConfig"] = None,
    level: Optional[int] = None,
    format: Optional[str] = None,
) -> None:
    """Configure DataFlow logging with centralized settings.

    This function configures all DataFlow loggers according to the provided
    LoggingConfig or explicit parameters. It supports:
    - Global log level setting
    - Category-specific log level overrides
    - Environment variable configuration (via LoggingConfig.from_env())
    - Propagation control
    - Sensitive data masking via SensitiveMaskingFilter

    Args:
        config: LoggingConfig instance. If None, uses LoggingConfig.from_env()
                unless level or format are explicitly provided.
        level: Explicit log level (e.g., logging.DEBUG). Overrides config.level.
        format: Explicit log format string. Overrides config.format.

    Usage:
        from dataflow.core.config import LoggingConfig
        from dataflow.utils.suppress_warnings import configure_dataflow_logging

        # Use environment variables
        configure_dataflow_logging()

        # Use explicit config
        configure_dataflow_logging(LoggingConfig(level=logging.DEBUG))

        # Use explicit level parameter
        configure_dataflow_logging(level=logging.DEBUG)

        # Category-specific debugging
        configure_dataflow_logging(LoggingConfig(
            level=logging.WARNING,
            node_execution=logging.DEBUG,
        ))
    """
    global _original_levels, _logging_configured, _original_logger_state

    # Import here to avoid circular imports
    from dataflow.core.config import LoggingConfig as ConfigLoggingConfig
    from dataflow.core.logging_config import LoggingConfig as NewLoggingConfig
    from dataflow.core.logging_config import SensitiveMaskingFilter

    # Determine the effective config
    if config is None and level is None and format is None:
        config = ConfigLoggingConfig.from_env()
    elif config is None:
        # Create a config from explicit parameters
        effective_level = level if level is not None else logging.WARNING
        config = ConfigLoggingConfig(level=effective_level)

    # Apply explicit overrides
    effective_level = level if level is not None else config.level

    # Set the root dataflow logger
    dataflow_logger = logging.getLogger("dataflow")

    # Store original state if not already stored
    if "dataflow" not in _original_levels:
        _original_levels["dataflow"] = dataflow_logger.level
    if "dataflow" not in _original_logger_state:
        _original_logger_state["dataflow"] = {
            "level": dataflow_logger.level,
            "propagate": dataflow_logger.propagate,
            "handlers": list(dataflow_logger.handlers),
            "filters": list(dataflow_logger.filters),
        }

    dataflow_logger.setLevel(effective_level)

    # Disable propagation to avoid duplicate logs (common in complex applications)
    # The propagate attribute from config controls this (defaults to True for backward compat)
    propagate = getattr(config, "propagate", True)
    dataflow_logger.propagate = propagate

    # Add SensitiveMaskingFilter if masking is enabled
    # Check for both old (mask_sensitive_values) and new (mask_sensitive) attribute names
    mask_enabled = getattr(config, "mask_sensitive", None)
    if mask_enabled is None:
        mask_enabled = getattr(config, "mask_sensitive_values", True)

    if mask_enabled:
        # Create a new LoggingConfig for the filter if we have an old-style config
        new_config = NewLoggingConfig(
            level=effective_level,
            mask_sensitive=True,
        )
        masking_filter = SensitiveMaskingFilter(new_config)

        # Add filter to all handlers of the dataflow logger
        for handler in dataflow_logger.handlers:
            # Check if filter is already added (avoid duplicates)
            if not any(isinstance(f, SensitiveMaskingFilter) for f in handler.filters):
                handler.addFilter(masking_filter)

    # Configure category-specific loggers
    for logger_name, category in _LOGGER_CATEGORIES.items():
        logger = logging.getLogger(logger_name)

        # Store original level if not already stored
        if logger_name not in _original_levels:
            _original_levels[logger_name] = logger.level
        if logger_name not in _original_logger_state:
            _original_logger_state[logger_name] = {
                "level": logger.level,
                "propagate": logger.propagate,
                "handlers": list(logger.handlers),
                "filters": list(logger.filters),
            }

        # Set the appropriate level
        category_level = config.get_level_for_category(category)
        # Apply explicit level override if provided
        final_level = level if level is not None else category_level
        logger.setLevel(final_level)

    # Also apply existing SDK warning suppression
    suppress_core_sdk_warnings()

    _logging_configured = True

    # Log configuration applied (at DEBUG to avoid noise)
    logging.getLogger("dataflow").debug(
        f"DataFlow logging configured: level={logging.getLevelName(effective_level)}"
    )


def restore_dataflow_logging() -> None:
    """Restore original logging levels and state.

    This function restores all DataFlow loggers to their original levels
    before configure_dataflow_logging() was called. It also restores:
    - Original log levels
    - Propagation settings
    - Removes any SensitiveMaskingFilter added during configuration

    This is useful for testing or when you need to temporarily change
    and restore logging levels. Safe to call multiple times.

    Usage:
        from dataflow.utils.suppress_warnings import (
            configure_dataflow_logging,
            restore_dataflow_logging,
        )

        # Change logging
        configure_dataflow_logging(LoggingConfig(level=logging.DEBUG))

        # ... do something ...

        # Restore original levels
        restore_dataflow_logging()
    """
    global _original_levels, _logging_configured, _original_logger_state

    # Import here to avoid circular imports
    from dataflow.core.logging_config import SensitiveMaskingFilter

    # Restore from detailed state if available
    for logger_name, state in _original_logger_state.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(state["level"])
        logger.propagate = state["propagate"]

        # Remove any SensitiveMaskingFilter from handlers
        for handler in logger.handlers:
            filters_to_remove = [
                f for f in handler.filters if isinstance(f, SensitiveMaskingFilter)
            ]
            for f in filters_to_remove:
                handler.removeFilter(f)

    # Also restore from simple levels dict (backward compatibility)
    for logger_name, original_level in _original_levels.items():
        if logger_name not in _original_logger_state:
            logging.getLogger(logger_name).setLevel(original_level)

    _original_levels.clear()
    _original_logger_state.clear()
    _logging_configured = False

    # Restore SDK warnings too
    restore_core_sdk_warnings()


def is_logging_configured() -> bool:
    """Check if DataFlow logging has been configured.

    Returns:
        True if configure_dataflow_logging() has been called.
    """
    return _logging_configured


def get_dataflow_logger(name: str) -> logging.Logger:
    """Get a logger with the dataflow prefix.

    This helper function ensures consistent logger naming across the
    DataFlow framework. If the name already starts with "dataflow.",
    it's returned as-is. Otherwise, "dataflow." is prepended.

    Args:
        name: Logger name. Can be with or without "dataflow." prefix.
              Use empty string or "dataflow" for the root dataflow logger.

    Returns:
        A logger instance with the appropriate dataflow prefix.

    Usage:
        from dataflow.utils.suppress_warnings import get_dataflow_logger

        # Get component-specific logger
        logger = get_dataflow_logger("my_module")
        # Returns: logging.getLogger("dataflow.my_module")

        # Get root dataflow logger
        logger = get_dataflow_logger("")
        # Returns: logging.getLogger("dataflow")

        # Already prefixed names work too
        logger = get_dataflow_logger("dataflow.core.nodes")
        # Returns: logging.getLogger("dataflow.core.nodes")
    """
    # Handle empty string or "dataflow" as the root logger
    if not name or name == "dataflow":
        return logging.getLogger("dataflow")

    # If already prefixed, return as-is
    if name.startswith("dataflow."):
        return logging.getLogger(name)

    # Add the dataflow prefix
    return logging.getLogger(f"dataflow.{name}")


@contextmanager
def dataflow_logging_context(
    config: Optional["LoggingConfig"] = None,
    level: Optional[int] = None,
) -> Iterator[None]:
    """Context manager for temporary DataFlow logging configuration.

    This context manager applies logging configuration on entry and
    automatically restores the original configuration on exit, even
    if an exception occurs.

    Args:
        config: LoggingConfig instance to apply. If None and level is None,
                uses LoggingConfig.from_env().
        level: Explicit log level to apply. Overrides config.level if both
               are provided.

    Yields:
        None. Use the context manager for its side effects only.

    Usage:
        from dataflow.utils.suppress_warnings import dataflow_logging_context
        import logging

        # Enable debug logging temporarily
        with dataflow_logging_context(level=logging.DEBUG):
            # Debug logging is active here
            logger.debug("This will be logged")

        # Original logging level is restored here

        # With config object
        from dataflow.core.config import LoggingConfig
        with dataflow_logging_context(config=LoggingConfig.development()):
            # Development logging is active
            pass

        # Safe even with exceptions
        try:
            with dataflow_logging_context(level=logging.ERROR):
                raise ValueError("Something went wrong")
        except ValueError:
            pass  # Logging is still restored
    """
    # Declare globals at the start of the function (Python requirement)
    global _original_levels, _original_logger_state, _logging_configured

    # Store current state before making changes
    # We'll rely on configure_dataflow_logging to save state and
    # restore_dataflow_logging to restore it

    # If we're already configured, we need to save the current state
    # so we can restore it after the nested context
    was_configured = is_logging_configured()
    saved_levels: Dict[str, int] = {}
    saved_state: Dict[str, Any] = {}
    saved_configured = False

    if was_configured:
        # Save current state before we modify anything
        saved_levels = dict(_original_levels)
        saved_state = dict(_original_logger_state)
        saved_configured = _logging_configured

        # Clear state so configure_dataflow_logging saves new "original" state
        _original_levels = {}
        _original_logger_state = {}
        _logging_configured = False

    try:
        # Apply the new configuration
        configure_dataflow_logging(config=config, level=level)
        yield
    finally:
        # Restore the original configuration
        restore_dataflow_logging()

        # If we were already configured, restore the previous state
        if was_configured:
            _original_levels.update(saved_levels)
            _original_logger_state.update(saved_state)
            _logging_configured = saved_configured
