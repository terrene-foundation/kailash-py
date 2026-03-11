#!/usr/bin/env python3
"""
Constraint Validator for DataFlow NOT NULL Column Addition

Provides comprehensive constraint validation for NOT NULL column addition,
ensuring data integrity and preventing migration failures due to constraint
violations.

This validator handles all PostgreSQL constraint types including foreign keys,
check constraints, unique constraints, and trigger compatibility.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import asyncpg

from .not_null_handler import ColumnDefinition, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class ForeignKeyConstraint:
    """Represents a foreign key constraint."""

    name: str
    source_columns: List[str]
    target_table: str
    target_columns: List[str]
    on_delete: str = "RESTRICT"
    on_update: str = "RESTRICT"
    deferrable: bool = False
    initially_deferred: bool = False


@dataclass
class CheckConstraint:
    """Represents a check constraint."""

    name: str
    definition: str
    columns_referenced: List[str]
    is_not_null: bool = False


@dataclass
class UniqueConstraint:
    """Represents a unique constraint."""

    name: str
    columns: List[str]
    is_primary_key: bool = False
    include_columns: List[str] = None

    def __post_init__(self):
        if self.include_columns is None:
            self.include_columns = []


@dataclass
class TriggerInfo:
    """Represents trigger information."""

    name: str
    event: str  # INSERT, UPDATE, DELETE
    timing: str  # BEFORE, AFTER, INSTEAD OF
    function_name: str
    columns: List[str] = None

    def __post_init__(self):
        if self.columns is None:
            self.columns = []


@dataclass
class ConstraintValidationResult:
    """Result of constraint validation."""

    constraint_type: str
    constraint_name: str
    is_compatible: bool
    issues: List[str]
    warnings: List[str]
    suggested_actions: List[str] = None

    def __post_init__(self):
        if self.issues is None:
            self.issues = []
        if self.warnings is None:
            self.warnings = []
        if self.suggested_actions is None:
            self.suggested_actions = []


class ConstraintValidator:
    """
    Validates NOT NULL column addition against all types of database constraints.

    Provides comprehensive validation for foreign keys, check constraints,
    unique constraints, and trigger compatibility to prevent migration failures.
    """

    def __init__(self, connection_manager: Optional[Any] = None):
        """Initialize the constraint validator."""
        self.connection_manager = connection_manager
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def validate_all_constraints(
        self,
        table_name: str,
        column: ColumnDefinition,
        default_value: Any,
        connection: Optional[asyncpg.Connection] = None,
    ) -> ValidationResult:
        """
        Validate column addition against all table constraints.

        Args:
            table_name: Target table name
            column: Column definition
            default_value: Default value to validate
            connection: Database connection (optional)

        Returns:
            ValidationResult with comprehensive constraint analysis
        """
        self.logger.info(f"Validating all constraints for {table_name}.{column.name}")

        if connection is None:
            connection = await self._get_connection()

        all_issues = []
        all_warnings = []
        validation_results = []

        try:
            # Get all constraints for the table
            constraints_info = await self._get_all_constraints_info(
                table_name, connection
            )

            # Validate foreign key constraints
            if constraints_info["foreign_keys"]:
                fk_result = await self._validate_foreign_key_constraints(
                    table_name,
                    column,
                    default_value,
                    constraints_info["foreign_keys"],
                    connection,
                )
                validation_results.append(fk_result)
                all_issues.extend(fk_result.issues)
                all_warnings.extend(fk_result.warnings)

            # Validate check constraints
            if constraints_info["check_constraints"]:
                check_result = await self._validate_check_constraints(
                    table_name,
                    column,
                    default_value,
                    constraints_info["check_constraints"],
                    connection,
                )
                validation_results.append(check_result)
                all_issues.extend(check_result.issues)
                all_warnings.extend(check_result.warnings)

            # Validate unique constraints
            if constraints_info["unique_constraints"]:
                unique_result = await self._validate_unique_constraints(
                    table_name,
                    column,
                    default_value,
                    constraints_info["unique_constraints"],
                    connection,
                )
                validation_results.append(unique_result)
                all_issues.extend(unique_result.issues)
                all_warnings.extend(unique_result.warnings)

            # Validate trigger compatibility
            if constraints_info["triggers"]:
                trigger_result = await self._validate_trigger_compatibility(
                    table_name, column, constraints_info["triggers"], connection
                )
                validation_results.append(trigger_result)
                all_issues.extend(trigger_result.issues)
                all_warnings.extend(trigger_result.warnings)

            # Overall validation result
            is_safe = len(all_issues) == 0

            self.logger.info(
                f"Constraint validation complete for {table_name}.{column.name}: "
                f"Safe={is_safe}, Issues={len(all_issues)}, Warnings={len(all_warnings)}"
            )

            return ValidationResult(
                is_safe=is_safe, issues=all_issues, warnings=all_warnings
            )

        except Exception as e:
            self.logger.error(f"Constraint validation failed: {e}")
            return ValidationResult(
                is_safe=False,
                issues=[f"Constraint validation error: {str(e)}"],
                warnings=[],
            )

    async def validate_foreign_key_references(
        self,
        default_value: Any,
        fk_constraint: ForeignKeyConstraint,
        connection: Optional[asyncpg.Connection] = None,
    ) -> bool:
        """
        Validate that default value satisfies foreign key constraint.

        Args:
            default_value: Default value to validate
            fk_constraint: Foreign key constraint information
            connection: Database connection (optional)

        Returns:
            True if default value is valid for foreign key
        """
        if connection is None:
            connection = await self._get_connection()

        try:
            # Handle NULL default value
            if default_value is None:
                return True  # NULL is always valid for foreign keys

            # Check if referenced value exists
            target_table = fk_constraint.target_table
            target_column = fk_constraint.target_columns[
                0
            ]  # Simplified for single column FK

            exists = await connection.fetchval(
                f"SELECT EXISTS(SELECT 1 FROM {target_table} WHERE {target_column} = $1)",
                default_value,
            )

            return bool(exists)

        except Exception as e:
            self.logger.error(f"Foreign key validation failed: {e}")
            return False

    async def validate_check_constraints(
        self,
        default_value: Any,
        check_constraints: List[CheckConstraint],
        connection: Optional[asyncpg.Connection] = None,
    ) -> bool:
        """
        Validate that default value satisfies all check constraints.

        Args:
            default_value: Default value to validate
            check_constraints: List of check constraints
            connection: Database connection (optional)

        Returns:
            True if default value satisfies all check constraints
        """
        if connection is None:
            connection = await self._get_connection()

        try:
            for constraint in check_constraints:
                # Create a test query to validate the constraint
                # This is simplified - in production would need full SQL parsing
                test_query = self._create_constraint_test_query(
                    constraint.definition, default_value
                )

                if test_query:
                    result = await connection.fetchval(test_query)
                    if not result:
                        self.logger.warning(
                            f"Check constraint {constraint.name} may be violated by default value"
                        )
                        return False

            return True

        except Exception as e:
            self.logger.error(f"Check constraint validation failed: {e}")
            return False

    async def validate_unique_constraints(
        self,
        column_name: str,
        default_value: Any,
        unique_constraints: List[UniqueConstraint],
        connection: Optional[asyncpg.Connection] = None,
    ) -> bool:
        """
        Validate that default value doesn't violate unique constraints.

        Args:
            column_name: Name of the column being added
            default_value: Default value to validate
            unique_constraints: List of unique constraints
            connection: Database connection (optional)

        Returns:
            True if default value doesn't violate unique constraints
        """
        if connection is None:
            connection = await self._get_connection()

        try:
            for constraint in unique_constraints:
                if column_name in constraint.columns:
                    # This column is part of a unique constraint
                    # Default value will be applied to ALL rows, which would violate uniqueness
                    if len(constraint.columns) == 1:
                        # Single column unique constraint - default value would create duplicates
                        self.logger.warning(
                            f"Column {column_name} is part of unique constraint {constraint.name}. "
                            f"Default value will create duplicates."
                        )
                        return False
                    else:
                        # Multi-column unique constraint - may still be valid if other columns differ
                        self.logger.warning(
                            f"Column {column_name} is part of multi-column unique constraint {constraint.name}. "
                            f"Verify that other columns provide uniqueness."
                        )

            return True

        except Exception as e:
            self.logger.error(f"Unique constraint validation failed: {e}")
            return False

    async def validate_trigger_compatibility(
        self,
        table_name: str,
        column_name: str,
        default_value: Any,
        connection: Optional[asyncpg.Connection] = None,
    ) -> bool:
        """
        Validate trigger compatibility with column addition.

        Args:
            table_name: Target table name
            column_name: Name of the column being added
            default_value: Default value
            connection: Database connection (optional)

        Returns:
            True if triggers are compatible with column addition
        """
        if connection is None:
            connection = await self._get_connection()

        try:
            # Get trigger information
            triggers = await self._get_table_triggers(table_name, connection)

            for trigger in triggers:
                # Check if trigger might be affected by the new column
                if self._trigger_might_be_affected(trigger, column_name):
                    self.logger.warning(
                        f"Trigger {trigger.name} might be affected by adding column {column_name}. "
                        f"Manual review recommended."
                    )
                    # For now, we allow it but warn - in production might want stricter validation

            return True

        except Exception as e:
            self.logger.error(f"Trigger compatibility validation failed: {e}")
            return False

    # Private helper methods

    async def _get_connection(self) -> asyncpg.Connection:
        """Get database connection."""
        if self.connection_manager:
            return await self.connection_manager.get_connection()
        else:
            raise NotImplementedError("Connection manager not configured")

    async def _get_all_constraints_info(
        self, table_name: str, connection: asyncpg.Connection
    ) -> Dict[str, List[Any]]:
        """Get comprehensive constraint information for table."""

        # Get foreign key constraints
        fk_query = """
        SELECT
            tc.constraint_name,
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name,
            rc.delete_rule,
            rc.update_rule
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        JOIN information_schema.referential_constraints AS rc
            ON tc.constraint_name = rc.constraint_name
            AND tc.table_schema = rc.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = $1
        """
        fk_rows = await connection.fetch(fk_query, table_name)

        foreign_keys = []
        for row in fk_rows:
            fk = ForeignKeyConstraint(
                name=row["constraint_name"],
                source_columns=[row["column_name"]],
                target_table=row["foreign_table_name"],
                target_columns=[row["foreign_column_name"]],
                on_delete=row["delete_rule"],
                on_update=row["update_rule"],
            )
            foreign_keys.append(fk)

        # Get check constraints
        check_query = """
        SELECT
            tc.constraint_name,
            cc.check_clause
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.check_constraints AS cc
            ON tc.constraint_name = cc.constraint_name
            AND tc.table_schema = cc.constraint_schema
        WHERE tc.constraint_type = 'CHECK'
            AND tc.table_name = $1
        """
        check_rows = await connection.fetch(check_query, table_name)

        check_constraints = []
        for row in check_rows:
            # Extract referenced columns from check clause (simplified)
            referenced_columns = self._extract_columns_from_check_clause(
                row["check_clause"]
            )

            check = CheckConstraint(
                name=row["constraint_name"],
                definition=row["check_clause"],
                columns_referenced=referenced_columns,
            )
            check_constraints.append(check)

        # Get unique constraints
        unique_query = """
        SELECT
            tc.constraint_name,
            kcu.column_name,
            tc.constraint_type
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type IN ('UNIQUE', 'PRIMARY KEY')
            AND tc.table_name = $1
        ORDER BY tc.constraint_name, kcu.ordinal_position
        """
        unique_rows = await connection.fetch(unique_query, table_name)

        # Group by constraint name
        unique_constraints_dict = {}
        for row in unique_rows:
            constraint_name = row["constraint_name"]
            if constraint_name not in unique_constraints_dict:
                unique_constraints_dict[constraint_name] = {
                    "name": constraint_name,
                    "columns": [],
                    "is_primary_key": row["constraint_type"] == "PRIMARY KEY",
                }
            unique_constraints_dict[constraint_name]["columns"].append(
                row["column_name"]
            )

        unique_constraints = []
        for constraint_info in unique_constraints_dict.values():
            unique = UniqueConstraint(
                name=constraint_info["name"],
                columns=constraint_info["columns"],
                is_primary_key=constraint_info["is_primary_key"],
            )
            unique_constraints.append(unique)

        # Get triggers
        triggers = await self._get_table_triggers(table_name, connection)

        return {
            "foreign_keys": foreign_keys,
            "check_constraints": check_constraints,
            "unique_constraints": unique_constraints,
            "triggers": triggers,
        }

    async def _validate_foreign_key_constraints(
        self,
        table_name: str,
        column: ColumnDefinition,
        default_value: Any,
        fk_constraints: List[ForeignKeyConstraint],
        connection: asyncpg.Connection,
    ) -> ConstraintValidationResult:
        """Validate foreign key constraints for column addition."""
        issues = []
        warnings = []
        suggestions = []

        # Check if the new column will be part of any foreign key
        if column.foreign_key_reference:
            # This column is itself a foreign key
            is_valid = await self.validate_foreign_key_references(
                default_value,
                # Create temporary FK constraint object
                ForeignKeyConstraint(
                    name="temp",
                    source_columns=[column.name],
                    target_table=column.foreign_key_reference.split(".")[0],
                    target_columns=[column.foreign_key_reference.split(".")[1]],
                ),
                connection,
            )

            if not is_valid:
                issues.append(
                    f"Default value {default_value} does not exist in referenced table"
                )
                suggestions.append(
                    "Verify that the default value exists in the referenced table"
                )

        # Check for potential impacts on existing foreign keys
        for fk in fk_constraints:
            # Existing FKs shouldn't be directly affected by adding a new column
            # But warn if the new column might affect related logic
            warnings.append(
                f"Existing foreign key {fk.name} references {fk.target_table}. Verify compatibility with new column."
            )

        return ConstraintValidationResult(
            constraint_type="FOREIGN_KEY",
            constraint_name="all_foreign_keys",
            is_compatible=len(issues) == 0,
            issues=issues,
            warnings=warnings,
            suggested_actions=suggestions,
        )

    async def _validate_check_constraints(
        self,
        table_name: str,
        column: ColumnDefinition,
        default_value: Any,
        check_constraints: List[CheckConstraint],
        connection: asyncpg.Connection,
    ) -> ConstraintValidationResult:
        """Validate check constraints for column addition."""
        issues = []
        warnings = []
        suggestions = []

        for constraint in check_constraints:
            # Check if the constraint might reference the new column
            if column.name in constraint.definition.lower():
                issues.append(
                    f"Check constraint {constraint.name} already references column {column.name}"
                )
                continue

            # For existing constraints, adding a new column shouldn't affect them
            # unless the constraint has complex logic
            if (
                "case" in constraint.definition.lower()
                or "exists" in constraint.definition.lower()
            ):
                warnings.append(
                    f"Check constraint {constraint.name} has complex logic. Manual verification recommended."
                )

            # Test if default value would satisfy constraint (simplified test)
            try:
                # This is a simplified validation - production would need full SQL parsing
                if self._constraint_might_affect_new_column(
                    constraint.definition, column.name
                ):
                    warnings.append(
                        f"Check constraint {constraint.name} might be affected by new column"
                    )
                    suggestions.append(
                        f"Test constraint {constraint.name} with the new column default value"
                    )
            except Exception as e:
                warnings.append(
                    f"Could not analyze constraint {constraint.name}: {str(e)}"
                )

        return ConstraintValidationResult(
            constraint_type="CHECK",
            constraint_name="all_check_constraints",
            is_compatible=len(issues) == 0,
            issues=issues,
            warnings=warnings,
            suggested_actions=suggestions,
        )

    async def _validate_unique_constraints(
        self,
        table_name: str,
        column: ColumnDefinition,
        default_value: Any,
        unique_constraints: List[UniqueConstraint],
        connection: asyncpg.Connection,
    ) -> ConstraintValidationResult:
        """Validate unique constraints for column addition."""
        issues = []
        warnings = []
        suggestions = []

        # Check if table has any data
        row_count = await connection.fetchval(f"SELECT COUNT(*) FROM {table_name}")

        for constraint in unique_constraints:
            if column.name in [col.lower() for col in constraint.columns]:
                issues.append(
                    f"Column {column.name} is already part of unique constraint {constraint.name}"
                )
                continue

            # If we're adding to an empty table, no issues
            if row_count == 0:
                continue

            # Warn about potential issues if table has data
            if row_count > 0:
                warnings.append(
                    f"Table has {row_count} rows. Adding NOT NULL column with default value will not violate "
                    f"existing unique constraint {constraint.name}"
                )

        # Special case: if the new column itself should be unique
        if column.unique and row_count > 1:
            issues.append(
                f"Cannot add unique NOT NULL column {column.name} with default value to table with {row_count} rows. "
                f"Default value would create duplicates."
            )
            suggestions.append(
                "Use a sequence or expression that generates unique values for each row"
            )

        return ConstraintValidationResult(
            constraint_type="UNIQUE",
            constraint_name="all_unique_constraints",
            is_compatible=len(issues) == 0,
            issues=issues,
            warnings=warnings,
            suggested_actions=suggestions,
        )

    async def _validate_trigger_compatibility(
        self,
        table_name: str,
        column: ColumnDefinition,
        triggers: List[TriggerInfo],
        connection: asyncpg.Connection,
    ) -> ConstraintValidationResult:
        """Validate trigger compatibility with column addition."""
        issues = []
        warnings = []
        suggestions = []

        for trigger in triggers:
            # Check if trigger might be affected
            if self._trigger_might_be_affected(trigger, column.name):
                warnings.append(
                    f"Trigger {trigger.name} might be affected by new column {column.name}"
                )
                suggestions.append(
                    f"Review trigger function {trigger.function_name} for compatibility"
                )

            # Specific checks for common trigger patterns
            if "update" in trigger.function_name.lower():
                warnings.append(
                    f"Update trigger {trigger.name} may need to handle new column {column.name}"
                )

            if "audit" in trigger.function_name.lower():
                warnings.append(
                    f"Audit trigger {trigger.name} may need to track changes to new column {column.name}"
                )

        return ConstraintValidationResult(
            constraint_type="TRIGGER",
            constraint_name="all_triggers",
            is_compatible=len(issues) == 0,
            issues=issues,
            warnings=warnings,
            suggested_actions=suggestions,
        )

    async def _get_table_triggers(
        self, table_name: str, connection: asyncpg.Connection
    ) -> List[TriggerInfo]:
        """Get all triggers for a table."""
        query = """
        SELECT
            t.trigger_name,
            t.event_manipulation,
            t.action_timing,
            t.action_statement
        FROM information_schema.triggers t
        WHERE t.event_object_table = $1
        ORDER BY t.trigger_name
        """

        rows = await connection.fetch(query, table_name)

        triggers = []
        for row in rows:
            # Extract function name from action statement (simplified)
            action_statement = row["action_statement"]
            function_name = self._extract_function_name(action_statement)

            trigger = TriggerInfo(
                name=row["trigger_name"],
                event=row["event_manipulation"],
                timing=row["action_timing"],
                function_name=function_name,
            )
            triggers.append(trigger)

        return triggers

    def _extract_columns_from_check_clause(self, check_clause: str) -> List[str]:
        """Extract column names from check constraint clause."""
        # Simplified extraction - production would use proper SQL parsing
        columns = []

        # Look for patterns like column_name op value
        pattern = r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b"
        matches = re.findall(pattern, check_clause)

        # Filter out SQL keywords and operators
        sql_keywords = {
            "AND",
            "OR",
            "NOT",
            "IN",
            "EXISTS",
            "BETWEEN",
            "LIKE",
            "IS",
            "NULL",
            "TRUE",
            "FALSE",
            "CASE",
            "WHEN",
            "THEN",
            "ELSE",
            "END",
        }

        for match in matches:
            if match.upper() not in sql_keywords and not match.isdigit():
                columns.append(match)

        return list(set(columns))

    def _create_constraint_test_query(
        self, constraint_definition: str, default_value: Any
    ) -> Optional[str]:
        """Create a test query to validate constraint with default value."""
        # This is highly simplified - production would need full SQL parsing
        try:
            # For basic constraints like column > 0, we can create simple tests
            if ">" in constraint_definition or "<" in constraint_definition:
                # Replace column references with the default value
                # This is very basic and would need much more sophistication
                test_expr = constraint_definition.replace("(", "").replace(")", "")

                # Simple substitution for testing
                if isinstance(default_value, (int, float)):
                    # Replace any column name with the default value
                    words = test_expr.split()
                    for i, word in enumerate(words):
                        if word.replace("_", "").isalpha():  # Likely a column name
                            words[i] = str(default_value)
                    test_expr = " ".join(words)
                    return f"SELECT ({test_expr})"

            return None  # Unable to create test query

        except Exception:
            return None

    def _constraint_might_affect_new_column(
        self, definition: str, column_name: str
    ) -> bool:
        """Check if constraint definition might be affected by new column."""
        # Very simplified check
        keywords_indicating_complexity = ["case", "exists", "in", "any", "all"]

        definition_lower = definition.lower()
        for keyword in keywords_indicating_complexity:
            if keyword in definition_lower:
                return True

        return False

    def _trigger_might_be_affected(
        self, trigger: TriggerInfo, column_name: str
    ) -> bool:
        """Check if trigger might be affected by new column."""
        # Triggers on INSERT or UPDATE events might be affected
        if trigger.event.upper() in ["INSERT", "UPDATE"]:
            return True

        # Triggers with certain function names are likely affected
        function_patterns = ["update", "modify", "change", "audit", "log"]
        function_lower = trigger.function_name.lower()

        for pattern in function_patterns:
            if pattern in function_lower:
                return True

        return False

    def _extract_function_name(self, action_statement: str) -> str:
        """Extract function name from trigger action statement."""
        # Simplified extraction from statements like "EXECUTE FUNCTION function_name()"
        if "execute function" in action_statement.lower():
            match = re.search(
                r"execute\s+function\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                action_statement,
                re.IGNORECASE,
            )
            if match:
                return match.group(1)

        return action_statement  # Return full statement if can't extract function name
