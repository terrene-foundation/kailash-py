"""
DataFlow Backward Compatibility Module

This module provides backward compatibility components to ensure that existing
DataFlow applications continue to work seamlessly after performance optimizations
and auto-migration system upgrades.
"""

from .legacy_support import (
    CompatibilityReport,
    ConfigEvolutionResult,
    LegacyAPICompatibility,
    UpgradeAssessment,
    WorkflowResult,
)
from .migration_path import MigrationPathTester, MigrationResult, ProductionConfig

__all__ = [
    "LegacyAPICompatibility",
    "CompatibilityReport",
    "WorkflowResult",
    "UpgradeAssessment",
    "ConfigEvolutionResult",
    "MigrationPathTester",
    "MigrationResult",
    "ProductionConfig",
]
