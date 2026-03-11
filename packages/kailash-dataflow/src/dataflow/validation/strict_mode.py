"""
Strict Mode Configuration and Control

This module provides the configuration infrastructure for DataFlow's strict mode.
Strict mode is opt-in and provides early error detection during development.

Configuration Hierarchy (priority order):
1. Per-model override: @db.model(strict_mode=True)
2. Global flag: DataFlow(url, strict_mode=True)
3. Environment variable: DATAFLOW_STRICT_MODE=true
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class StrictModeConfig:
    """
    Configuration for strict mode validation.

    Attributes:
        enabled: Whether strict mode is enabled globally
        validate_models: Enable model validation (Layer 1)
        validate_parameters: Enable parameter validation (Layer 2)
        validate_connections: Enable connection validation (Layer 3)
        validate_workflows: Enable workflow validation (Layer 4)
        fail_fast: Stop on first validation error
        verbose: Show detailed validation messages
    """

    enabled: bool = False
    validate_models: bool = True
    validate_parameters: bool = True
    validate_connections: bool = True
    validate_workflows: bool = True
    fail_fast: bool = False
    verbose: bool = False

    @classmethod
    def from_env(cls) -> "StrictModeConfig":
        """
        Create configuration from environment variables.

        Environment Variables:
            DATAFLOW_STRICT_MODE: Enable strict mode (true/false)
            DATAFLOW_STRICT_FAIL_FAST: Stop on first error (true/false)
            DATAFLOW_STRICT_VERBOSE: Show detailed messages (true/false)

        Returns:
            StrictModeConfig instance
        """
        enabled = os.getenv("DATAFLOW_STRICT_MODE", "false").lower() == "true"
        fail_fast = os.getenv("DATAFLOW_STRICT_FAIL_FAST", "false").lower() == "true"
        verbose = os.getenv("DATAFLOW_STRICT_VERBOSE", "false").lower() == "true"

        return cls(
            enabled=enabled,
            fail_fast=fail_fast,
            verbose=verbose,
        )


# Global configuration instance
_global_config: Optional[StrictModeConfig] = None


def get_strict_mode_config() -> StrictModeConfig:
    """
    Get the global strict mode configuration.

    Returns:
        StrictModeConfig instance (from environment if not set)
    """
    global _global_config
    if _global_config is None:
        _global_config = StrictModeConfig.from_env()
    return _global_config


def is_strict_mode_enabled(
    model_override: Optional[bool] = None,
    global_config: Optional[StrictModeConfig] = None,
) -> bool:
    """
    Check if strict mode is enabled for a specific context.

    Priority order:
    1. model_override (per-model setting)
    2. global_config.enabled (global setting)
    3. Environment variable (DATAFLOW_STRICT_MODE)

    Args:
        model_override: Per-model strict mode setting
        global_config: Global configuration (uses default if None)

    Returns:
        True if strict mode is enabled
    """
    # Priority 1: Per-model override
    if model_override is not None:
        return model_override

    # Priority 2: Global configuration
    if global_config is None:
        global_config = get_strict_mode_config()

    return global_config.enabled
