"""
Unified Schema Comparison Module

This module merges the previously separate schema comparison implementations
from AutoMigrationSystem and SchemaChangeDetector into a single, comprehensive
comparison engine with multiple modes and consistent behavior.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)


@dataclass
class UnifiedSchemaComparisonResult:
    """
    Unified result object that combines features from both SchemaDiff and SchemaComparisonResult.

    This provides a comprehensive view of schema differences with support for:
    - Table-level operations (create, drop, modify)
    - Column-level changes (add, remove, modify)
    - Compatibility analysis
    - Performance metrics
    """

    # Table operations
    added_tables: List[str] = field(default_factory=list)
    removed_tables: List[str] = field(default_factory=list)
    modified_tables: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Advanced features from AutoMigrationSystem
    tables_to_create: List[Any] = field(default_factory=list)  # TableDefinition objects
    tables_to_drop: List[str] = field(default_factory=list)
    tables_to_modify: List[Tuple[str, Any, Any]] = field(
        default_factory=list
    )  # (name, current, target)

    # Performance and metadata
    execution_time_ms: float = 0.0
    compatibility_checked: bool = False
    incremental_mode: bool = True

    def has_changes(self) -> bool:
        """Check if there are any schema changes."""
        return bool(
            self.added_tables
            or self.removed_tables
            or self.modified_tables
            or self.tables_to_create
            or self.tables_to_drop
            or self.tables_to_modify
        )

    def has_destructive_changes(self) -> bool:
        """Check if there are destructive changes (drops)."""
        return bool(self.removed_tables or self.tables_to_drop)


class UnifiedSchemaComparator:
    """
    Unified schema comparison engine that merges AutoMigrationSystem and SchemaChangeDetector logic.

    Features:
    - Multiple input formats (TableDefinition objects, raw dictionaries)
    - Incremental mode (don't detect table removals during single model registration)
    - Compatibility checking (detect when migration isn't needed)
    - Performance monitoring (<100ms operations)
    - Smart type mapping for PostgreSQL
    """

    def __init__(self):
        """Initialize the unified schema comparator."""
        self.type_mappings = {
            "str": ["varchar", "text", "character varying", "char"],
            "int": ["integer", "bigint", "serial", "bigserial", "int4", "int8"],
            "float": [
                "decimal",
                "numeric",
                "real",
                "double precision",
                "float4",
                "float8",
            ],
            "bool": ["boolean", "bool"],
            "datetime": [
                "timestamp",
                "timestamptz",
                "timestamp with time zone",
                "timestamp without time zone",
            ],
            "date": ["date"],
            "time": ["time", "timetz"],
            "json": ["json", "jsonb"],
            "uuid": ["uuid"],
            "bytes": ["bytea"],
        }

    def compare_schemas(
        self,
        current_schema: Union[
            Dict[str, Any], Any
        ],  # DatabaseSchema or Dict[str, TableDefinition]
        target_schema: Union[
            Dict[str, Any], Any
        ],  # ModelSchema or Dict[str, TableDefinition]
        incremental_mode: bool = True,
        compatibility_check: bool = True,
        performance_target_ms: float = 100.0,
    ) -> UnifiedSchemaComparisonResult:
        """
        Unified schema comparison with multiple modes.

        Args:
            current_schema: Current database schema (DatabaseSchema or Dict[str, TableDefinition])
            target_schema: Target model schema (ModelSchema or Dict[str, TableDefinition])
            incremental_mode: If True, only compare specified tables, don't detect removals
            compatibility_check: If True, check schema compatibility before generating changes
            performance_target_ms: Performance target in milliseconds (default 100ms)

        Returns:
            Comprehensive comparison results
        """
        start_time = time.perf_counter()

        result = UnifiedSchemaComparisonResult()
        result.incremental_mode = incremental_mode
        result.compatibility_checked = compatibility_check

        # Store original schemas for TableDefinition object retrieval
        self._original_current_schema = current_schema
        self._original_target_schema = target_schema

        # Normalize inputs to common format
        current_tables = self._normalize_schema_input(current_schema)
        target_tables = self._normalize_schema_input(target_schema)

        current_table_names = set(current_tables.keys())
        target_table_names = set(target_tables.keys())

        # Detect table-level changes
        self._detect_table_changes(
            current_table_names,
            target_table_names,
            current_tables,
            target_tables,
            result,
            incremental_mode,
        )

        # Detect column-level changes for common tables
        common_tables = current_table_names & target_table_names
        for table_name in common_tables:
            current_table = current_tables[table_name]
            target_table = target_tables[table_name]

            # Compatibility check if requested
            if compatibility_check and self._schemas_are_compatible(
                current_table, target_table
            ):
                logger.debug(
                    f"Table '{table_name}' schemas are compatible - no migration needed"
                )
                continue

            # Detect column changes
            table_changes = self._compare_table_structures(current_table, target_table)
            if table_changes:
                result.modified_tables[table_name] = table_changes

                # Also populate tables_to_modify for AutoMigrationSystem compatibility
                # We need to pass the original TableDefinition objects, not the normalized dictionaries
                original_current = self._find_original_table_definition(
                    self._original_current_schema, table_name
                )
                original_target = self._find_original_table_definition(
                    self._original_target_schema, table_name
                )
                result.tables_to_modify.append(
                    (table_name, original_current, original_target)
                )

        # Performance monitoring
        end_time = time.perf_counter()
        result.execution_time_ms = (end_time - start_time) * 1000

        if result.execution_time_ms > performance_target_ms:
            logger.warning(
                f"Schema comparison took {result.execution_time_ms:.2f}ms, "
                f"exceeding {performance_target_ms}ms performance target"
            )

        return result

    def _normalize_schema_input(
        self, schema_input: Union[Dict[str, Any], Any]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Normalize different schema input formats to a common dictionary format.

        Handles:
        - DatabaseSchema objects (from schema_state_manager)
        - ModelSchema objects (from schema_state_manager)
        - Dict[str, TableDefinition] (from auto_migration_system)
        - Raw dictionary formats
        """
        if hasattr(schema_input, "tables"):
            # DatabaseSchema or ModelSchema object
            return schema_input.tables
        elif isinstance(schema_input, dict):
            # Check if it's Dict[str, TableDefinition] or raw dict
            normalized = {}
            for table_name, table_data in schema_input.items():
                if hasattr(table_data, "columns"):
                    # TableDefinition object - convert to dict format
                    columns = {}
                    for col in table_data.columns:
                        columns[col.name] = {
                            "type": col.type,
                            "nullable": getattr(col, "nullable", True),
                            "default": getattr(col, "default", None),
                            "primary_key": getattr(col, "primary_key", False),
                        }
                    normalized[table_name] = {"columns": columns}
                else:
                    # Raw dict format
                    normalized[table_name] = table_data
            return normalized

    def _find_original_table_definition(
        self, schema_input: Union[Dict[str, Any], Any], table_name: str
    ) -> Any:
        """
        Find the original TableDefinition object from the schema input.

        Args:
            schema_input: Original schema input (Dict[str, TableDefinition] or other format)
            table_name: Name of table to find

        Returns:
            Original TableDefinition object or None if not found
        """
        if hasattr(schema_input, "tables"):
            # DatabaseSchema or ModelSchema object
            return schema_input.tables.get(table_name)
        elif isinstance(schema_input, dict):
            table_data = schema_input.get(table_name)
            if hasattr(table_data, "columns"):
                # Already a TableDefinition object
                return table_data
            else:
                # Raw dictionary - convert back to TableDefinition for compatibility
                # This is a fallback that shouldn't normally be needed
                return table_data
        else:
            logger.warning(f"Unknown schema input format: {type(schema_input)}")
            return None

    def _detect_table_changes(
        self,
        current_table_names: Set[str],
        target_table_names: Set[str],
        current_tables: Dict[str, Dict[str, Any]],
        target_tables: Dict[str, Dict[str, Any]],
        result: UnifiedSchemaComparisonResult,
        incremental_mode: bool,
    ):
        """Detect table-level changes (create, drop)."""
        # Tables to create
        added_tables = list(target_table_names - current_table_names)
        result.added_tables = added_tables

        # Populate tables_to_create for AutoMigrationSystem compatibility
        for table_name in added_tables:
            # Get the original TableDefinition object, not the normalized dictionary
            original_target = self._find_original_table_definition(
                self._original_target_schema, table_name
            )
            if original_target:
                result.tables_to_create.append(original_target)

        # Tables to drop - only in non-incremental mode
        if not incremental_mode:
            removed_tables = list(current_table_names - target_table_names)
            result.removed_tables = removed_tables
            result.tables_to_drop = removed_tables.copy()
        else:
            # In incremental mode, don't detect table removals
            result.removed_tables = []
            result.tables_to_drop = []

    def _compare_table_structures(
        self, current_table: Dict[str, Any], target_table: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Compare individual table structures for changes.

        Combines logic from both schema_state_manager and auto_migration_system.
        """
        changes = {}

        current_columns = current_table.get("columns", {})
        target_columns = target_table.get("columns", {})

        current_col_names = set(current_columns.keys())
        target_col_names = set(target_columns.keys())

        # Added columns
        added_columns = list(target_col_names - current_col_names)
        if added_columns:
            changes["added_columns"] = added_columns

        # Removed columns
        removed_columns = list(current_col_names - target_col_names)
        if removed_columns:
            changes["removed_columns"] = removed_columns

        # Modified columns
        modified_columns = {}
        common_columns = current_col_names & target_col_names

        for col_name in common_columns:
            current_col = current_columns[col_name]
            target_col = target_columns[col_name]

            col_changes = {}

            # Check type changes (with compatibility awareness)
            current_type = current_col.get("type", "")
            target_type = target_col.get("type", "")

            if not self._types_are_compatible(target_type, current_type):
                col_changes["old_type"] = current_type
                col_changes["new_type"] = target_type

            # Check nullable changes
            current_nullable = current_col.get("nullable", True)
            target_nullable = target_col.get("nullable", True)

            if current_nullable != target_nullable:
                col_changes["old_nullable"] = current_nullable
                col_changes["new_nullable"] = target_nullable

            # Check default value changes
            current_default = current_col.get("default")
            target_default = target_col.get("default")

            if current_default != target_default:
                col_changes["old_default"] = current_default
                col_changes["new_default"] = target_default

            if col_changes:
                modified_columns[col_name] = col_changes

        if modified_columns:
            changes["modified_columns"] = modified_columns

        return changes if changes else None

    def _schemas_are_compatible(
        self, current_table: Dict[str, Any], target_table: Dict[str, Any]
    ) -> bool:
        """
        Check if database table is compatible with target table.

        Compatible means the database has all required target fields,
        even if it has additional fields (legacy support).
        """
        current_columns = current_table.get("columns", {})
        target_columns = target_table.get("columns", {})

        for col_name, target_col in target_columns.items():
            # Skip auto-generated fields
            if col_name in ["id", "created_at", "updated_at"]:
                continue

            # Check if required field exists in database
            if col_name not in current_columns:
                # Missing column - not compatible
                return False

            # Check type compatibility
            current_col = current_columns[col_name]
            target_type = target_col.get("type", "")
            current_type = current_col.get("type", "")

            if not self._types_are_compatible(target_type, current_type):
                return False

            # Check nullable compatibility (can't make non-nullable field nullable without migration)
            target_nullable = target_col.get("nullable", True)
            current_nullable = current_col.get("nullable", True)

            if not target_nullable and current_nullable:
                # Target requires non-null but current allows null - not compatible
                return False

        return True

    def _types_are_compatible(self, model_type: str, db_type: str) -> bool:
        """
        Check if model type is compatible with database type.

        This allows for common type variations and PostgreSQL specifics.
        """
        if not model_type or not db_type:
            return True  # Skip comparison for missing types

        # Normalize types for comparison
        model_type = model_type.lower().strip()
        db_type = db_type.lower().strip()

        # Direct match
        if model_type == db_type:
            return True

        # Check mapped compatibility
        for base_type, compatible_types in self.type_mappings.items():
            if model_type == base_type and db_type in compatible_types:
                return True
            if db_type == base_type and model_type in compatible_types:
                return True

        # Handle common variations not in mapping
        if (
            model_type in ["text", "varchar"]
            and db_type in ["text", "varchar", "character varying"]
        ) or (
            db_type in ["text", "varchar"]
            and model_type in ["text", "varchar", "character varying"]
        ):
            return True

        logger.debug(
            f"Type incompatibility detected: model='{model_type}' vs db='{db_type}'"
        )
        return False


# Global instance for easy access
unified_comparator = UnifiedSchemaComparator()


def compare_schemas_unified(
    current_schema: Union[Dict[str, Any], Any],
    target_schema: Union[Dict[str, Any], Any],
    incremental_mode: bool = True,
    compatibility_check: bool = True,
) -> UnifiedSchemaComparisonResult:
    """
    Convenience function for unified schema comparison.

    This is the main entry point that should replace both:
    - AutoMigrationSystem.compare_schemas()
    - SchemaChangeDetector.compare_schemas()
    """
    return unified_comparator.compare_schemas(
        current_schema, target_schema, incremental_mode, compatibility_check
    )
