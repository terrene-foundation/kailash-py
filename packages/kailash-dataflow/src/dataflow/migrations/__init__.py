"""
DataFlow Migrations Module

Advanced database migration system with automatic schema comparison,
visual confirmation, rollback capabilities, and visual migration builder.
"""

from .auto_migration_system import (
    AutoMigrationSystem,
    ColumnDefinition,
    Migration,
    MigrationOperation,
    MigrationStatus,
    MigrationType,
    PostgreSQLMigrationGenerator,
    PostgreSQLSchemaInspector,
    SchemaDiff,
    TableDefinition,
)
from .fk_migration_operations import (
    CompositeFKOperation,
    FKChainUpdateOperation,
    FKMigrationOperations,
    FKOperationScenario,
    FKTargetRenameOperation,
    PKTypeChangeOperation,
)
from .fk_safe_migration_executor import (
    ConstraintHandlingResult,
    CoordinationResult,
    FKConstraintInfo,
    FKMigrationResult,
    FKMigrationStage,
    FKSafeMigrationExecutor,
    FKTransactionState,
    IntegrityPreservationResult,
)
from .foreign_key_analyzer import (
    FKImpactLevel,
    FKImpactReport,
    FKSafeMigrationPlan,
    ForeignKeyAnalyzer,
    IntegrityValidation,
    MigrationStep,
)
from .visual_migration_builder import (
    ColumnBuilder,
    ColumnType,
    ConstraintType,
    IndexBuilder,
    IndexType,
    MigrationScript,
    TableBuilder,
    VisualMigrationBuilder,
)

__all__ = [
    # Auto Migration System - PostgreSQL Edition
    "AutoMigrationSystem",
    "PostgreSQLSchemaInspector",
    "PostgreSQLMigrationGenerator",
    "Migration",
    "MigrationOperation",
    "SchemaDiff",
    "TableDefinition",
    "ColumnDefinition",
    "MigrationType",
    "MigrationStatus",
    # Visual Migration Builder
    "VisualMigrationBuilder",
    "MigrationScript",
    "ColumnBuilder",
    "TableBuilder",
    "IndexBuilder",
    "ColumnType",
    "IndexType",
    "ConstraintType",
    # FK-Safe Migration System - Phase 2 TODO-138
    "ForeignKeyAnalyzer",
    "FKSafeMigrationPlan",
    "FKImpactReport",
    "FKImpactLevel",
    "MigrationStep",
    "IntegrityValidation",
    "FKSafeMigrationExecutor",
    "FKMigrationResult",
    "FKConstraintInfo",
    "FKMigrationStage",
    "FKTransactionState",
    "ConstraintHandlingResult",
    "CoordinationResult",
    "IntegrityPreservationResult",
    "FKMigrationOperations",
    "PKTypeChangeOperation",
    "FKTargetRenameOperation",
    "FKChainUpdateOperation",
    "CompositeFKOperation",
    "FKOperationScenario",
]
