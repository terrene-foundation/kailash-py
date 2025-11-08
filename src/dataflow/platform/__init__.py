"""
DataFlow Platform Layer - Developer Experience Enhancement

This module provides a developer-friendly wrapper around DataFlow core,
offering:
- Smart error messages with actionable guidance
- Build-time validation to catch issues early
- Quick setup API for 1-minute configuration
- Introspection tools for debugging without source code
- Auto-fix capabilities for common issues

Usage:
    from dataflow.platform import DataFlowStudio

    # 1-minute setup
    studio = DataFlowStudio.quick_start(
        name="my_app",
        database="sqlite:///app.db",
        models=[User, Product],
        profile="development"
    )

    # Access DataFlow instance
    db = studio.db

    # Get generated nodes
    create_user = studio.node("User", "create")

    # Validate before deployment
    report = studio.validate()
    if not report.is_valid:
        report.auto_fix()
"""

from .autofix import AutoFix, FixResult
from .errors import DataFlowError, DataFlowWarning, ErrorCode, ErrorEnhancer
from .inspector import Inspector, InstanceInfo, ModelInfo, NodeInfo
from .studio import ConfigProfile, DataFlowStudio
from .validation import BuildValidator, ValidationLevel, ValidationReport

__all__ = [
    # Error handling
    "DataFlowError",
    "DataFlowWarning",
    "ErrorEnhancer",
    "ErrorCode",
    # Validation
    "BuildValidator",
    "ValidationReport",
    "ValidationLevel",
    # Quick setup
    "DataFlowStudio",
    "ConfigProfile",
    # Introspection
    "Inspector",
    "ModelInfo",
    "NodeInfo",
    "InstanceInfo",
    # Auto-fix
    "AutoFix",
    "FixResult",
]

__version__ = "0.1.0"
