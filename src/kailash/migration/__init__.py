"""Comprehensive migration tools for upgrading to enhanced LocalRuntime.

This module provides a complete suite of migration utilities for upgrading
existing codebases to use the enhanced LocalRuntime with zero downtime and
comprehensive validation.

Components:
- CompatibilityChecker: Analyze existing code for compatibility issues
- MigrationAssistant: Automated configuration conversion and optimization
- PerformanceComparator: Before/after performance analysis
- ConfigurationValidator: Runtime configuration validation
- MigrationDocGenerator: Automated migration guide generation
- RegressionDetector: Post-migration validation and regression detection
"""

from .compatibility_checker import CompatibilityChecker
from .configuration_validator import ConfigurationValidator
from .documentation_generator import MigrationDocGenerator
from .migration_assistant import MigrationAssistant
from .performance_comparator import PerformanceComparator
from .regression_detector import RegressionDetector

__all__ = [
    "CompatibilityChecker",
    "MigrationAssistant",
    "PerformanceComparator",
    "ConfigurationValidator",
    "MigrationDocGenerator",
    "RegressionDetector",
]
