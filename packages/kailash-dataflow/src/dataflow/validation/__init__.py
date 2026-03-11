"""
DataFlow Strict Mode Validation Package

This package provides opt-in validation for DataFlow models, parameters,
connections, and workflows. Enable strict mode to catch errors early during
development.

Usage:
    from dataflow.validation import is_strict_mode_enabled, StrictModeConfig

    # Check if strict mode is enabled
    if is_strict_mode_enabled(model_config):
        # Run validation
        pass
"""

from dataflow.validation.strict_mode import (
    StrictModeConfig,
    get_strict_mode_config,
    is_strict_mode_enabled,
)

__all__ = [
    "StrictModeConfig",
    "get_strict_mode_config",
    "is_strict_mode_enabled",
]

__version__ = "0.5.0"
