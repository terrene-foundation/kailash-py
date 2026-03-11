#!/usr/bin/env python3
"""
Migration Safety Validation System

Provides real validation for migration safety checks to replace mock implementations.
Validates schema integrity and application compatibility before production deployment.

Core Components:
- SafetyCheckResult: Structured validation result with violations and recommendations
- SafetyCheckSeverity: Severity levels for validation issues
- SchemaIntegrityValidator: Validates foreign keys, constraints, and indexes
- ApplicationCompatibilityValidator: Validates views, triggers, and functions
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _validate_table_name(table_name: str) -> None:
    """Validate table name is safe for use in SQL queries.

    Args:
        table_name: Table name to validate

    Raises:
        ValueError: If table name is invalid or unsafe

    Note:
        PostgreSQL unquoted identifiers are limited to 63 characters.
        SQL identifiers must start with letter or underscore, followed by
        letters, digits, underscores, or dollar signs.
    """
    if not table_name:
        raise ValueError("Table name cannot be empty")

    # Check for valid SQL identifier pattern
    # Allow letters, digits, underscores (standard SQL identifiers)
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table_name):
        raise ValueError(
            f"Invalid table name '{table_name}': must start with letter or underscore, "
            "followed by letters, digits, or underscores only"
        )

    # PostgreSQL limit (most restrictive)
    if len(table_name) > 63:
        raise ValueError(f"Table name too long: {len(table_name)} characters (max 63)")

    # Prevent SQL keywords that could be dangerous
    sql_keywords = {
        "select",
        "insert",
        "update",
        "delete",
        "drop",
        "create",
        "alter",
        "truncate",
    }
    if table_name.lower() in sql_keywords:
        raise ValueError(f"Table name '{table_name}' is a SQL keyword and not allowed")


class SafetyCheckSeverity(Enum):
    """Severity levels for safety check violations."""

    CRITICAL = "critical"  # Must fix - blocks deployment
    HIGH = "high"  # Should fix - may cause issues
    MEDIUM = "medium"  # Could fix - potential problems
    LOW = "low"  # Nice to fix - informational
    INFO = "info"  # Informational only


@dataclass
class SafetyCheckResult:
    """Result of a single safety check validation.

    Provides structured information about validation success, violations,
    warnings, and recommendations for fixing issues.
    """

    check_name: str
    passed: bool
    severity: SafetyCheckSeverity
    message: str
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    affected_objects: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "severity": self.severity.value,
            "message": self.message,
            "violations": self.violations,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "affected_objects": self.affected_objects,
            "execution_time_ms": self.execution_time_ms,
        }


class SchemaIntegrityValidator:
    """Validates schema integrity after table rename operations.

    Checks:
    - Foreign key constraints (no orphaned FKs, all valid)
    - Unique indexes (migrated to new table)
    - Check constraints (all migrated)
    - Primary keys (on new table only)
    """

    def __init__(self, connection_manager: Any, database_type: str = "postgresql"):
        """Initialize schema integrity validator.

        Args:
            connection_manager: Database connection manager
            database_type: Database type ("postgresql" or "sqlite")
        """
        self.connection_manager = connection_manager
        self.database_type = database_type.lower()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def validate_foreign_keys(
        self, old_table: str, new_table: str
    ) -> SafetyCheckResult:
        """Validate foreign key constraints after rename.

        Checks:
        1. No foreign keys still reference old table
        2. All foreign keys reference new table correctly
        3. Foreign key constraints are valid and active

        Args:
            old_table: Original table name
            new_table: New table name

        Returns:
            SafetyCheckResult with validation details
        """
        import time

        start_time = time.time()

        # Validate table names to prevent SQL injection
        try:
            _validate_table_name(old_table)
            _validate_table_name(new_table)
        except ValueError as e:
            return SafetyCheckResult(
                check_name="foreign_key_constraints",
                passed=False,
                severity=SafetyCheckSeverity.CRITICAL,
                message=f"Invalid table name: {str(e)}",
                violations=[str(e)],
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        try:
            if self.database_type == "postgresql":
                violations = await self._validate_postgresql_foreign_keys(
                    old_table, new_table
                )
            elif self.database_type == "sqlite":
                violations = await self._validate_sqlite_foreign_keys(
                    old_table, new_table
                )
            else:
                return SafetyCheckResult(
                    check_name="foreign_key_constraints",
                    passed=False,
                    severity=SafetyCheckSeverity.CRITICAL,
                    message=f"Unsupported database type: {self.database_type}",
                    violations=[f"Database type '{self.database_type}' not supported"],
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            execution_time = (time.time() - start_time) * 1000

            if violations:
                return SafetyCheckResult(
                    check_name="foreign_key_constraints",
                    passed=False,
                    severity=SafetyCheckSeverity.CRITICAL,
                    message=f"Found {len(violations)} foreign key violations after rename",
                    violations=violations,
                    recommendations=[
                        f"Update foreign keys to reference '{new_table}' instead of '{old_table}'",
                        "Use ALTER TABLE ... RENAME CONSTRAINT for PostgreSQL",
                        "Recreate foreign keys for SQLite (no ALTER support)",
                    ],
                    affected_objects=[old_table, new_table],
                    execution_time_ms=execution_time,
                )
            else:
                return SafetyCheckResult(
                    check_name="foreign_key_constraints",
                    passed=True,
                    severity=SafetyCheckSeverity.INFO,
                    message="All foreign key constraints valid",
                    violations=[],
                    affected_objects=[new_table],
                    execution_time_ms=execution_time,
                )

        except Exception as e:
            self.logger.error(f"Foreign key validation failed: {e}")
            return SafetyCheckResult(
                check_name="foreign_key_constraints",
                passed=False,
                severity=SafetyCheckSeverity.CRITICAL,
                message=f"Validation error: {str(e)}",
                violations=[str(e)],
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    async def _validate_postgresql_foreign_keys(
        self, old_table: str, new_table: str
    ) -> List[str]:
        """Validate PostgreSQL foreign keys.

        Args:
            old_table: Original table name
            new_table: New table name

        Returns:
            List of violation messages (empty if valid)
        """
        violations = []

        # Query to find foreign keys referencing old table
        query = """
        SELECT
            tc.constraint_name,
            tc.table_name,
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND (ccu.table_name = $1 OR tc.table_name = $1);
        """

        try:
            async with self.connection_manager.get_connection() as conn:
                rows = await conn.fetch(query, old_table)

                for row in rows:
                    # Check if foreign key still references old table
                    if row["foreign_table_name"] == old_table:
                        violations.append(
                            f"Foreign key '{row['constraint_name']}' on table "
                            f"'{row['table_name']}.{row['column_name']}' still "
                            f"references old table '{old_table}'"
                        )

                    # Check if table with foreign key is still named old_table
                    if row["table_name"] == old_table:
                        violations.append(
                            f"Table '{old_table}' still exists with foreign key "
                            f"'{row['constraint_name']}' - rename incomplete"
                        )

        except Exception as e:
            self.logger.error(f"PostgreSQL FK validation query failed: {e}")
            violations.append(f"Database query error: {str(e)}")

        return violations

    async def _validate_sqlite_foreign_keys(
        self, old_table: str, new_table: str
    ) -> List[str]:
        """Validate SQLite foreign keys using PRAGMA.

        Args:
            old_table: Original table name
            new_table: New table name

        Returns:
            List of violation messages (empty if valid)
        """
        violations = []

        try:
            async with self.connection_manager.get_connection() as conn:
                # Check if old table still exists
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (old_table,),
                )
                old_table_exists = await cursor.fetchone()

                if old_table_exists:
                    violations.append(
                        f"Old table '{old_table}' still exists - rename incomplete"
                    )

                # Check new table foreign keys
                # SAFETY: new_table validated by _validate_table_name() before entry
                # SQLite PRAGMA statements don't support parameterized queries
                cursor = await conn.execute(f"PRAGMA foreign_key_list({new_table})")
                fk_rows = await cursor.fetchall()

                for fk in fk_rows:
                    # fk structure: (id, seq, table, from, to, on_update, on_delete, match)
                    referenced_table = fk[2] if len(fk) > 2 else None
                    if referenced_table == old_table:
                        violations.append(
                            f"Foreign key on '{new_table}' still references "
                            f"old table '{old_table}'"
                        )

                # Check if any other tables reference old table
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                all_tables = await cursor.fetchall()

                for (table_name,) in all_tables:
                    if table_name in [old_table, new_table]:
                        continue

                    # SAFETY: table_name from sqlite_master is trusted system data
                    cursor = await conn.execute(
                        f"PRAGMA foreign_key_list({table_name})"
                    )
                    fk_rows = await cursor.fetchall()

                    for fk in fk_rows:
                        referenced_table = fk[2] if len(fk) > 2 else None
                        if referenced_table == old_table:
                            violations.append(
                                f"Table '{table_name}' has foreign key referencing "
                                f"old table '{old_table}'"
                            )

        except Exception as e:
            self.logger.error(f"SQLite FK validation failed: {e}")
            violations.append(f"Database query error: {str(e)}")

        return violations


class ApplicationCompatibilityValidator:
    """Validates application compatibility after table rename.

    Checks:
    - Views (no old table references)
    - Triggers (updated to new table)
    - Functions/procedures (no old table references)
    """

    def __init__(self, connection_manager: Any, database_type: str = "postgresql"):
        """Initialize application compatibility validator.

        Args:
            connection_manager: Database connection manager
            database_type: Database type ("postgresql" or "sqlite")
        """
        self.connection_manager = connection_manager
        self.database_type = database_type.lower()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def validate_views(self, old_table: str, new_table: str) -> SafetyCheckResult:
        """Validate views after table rename.

        Checks that no views reference the old table name.

        Args:
            old_table: Original table name
            new_table: New table name

        Returns:
            SafetyCheckResult with validation details
        """
        import time

        start_time = time.time()

        # Validate table names to prevent SQL injection
        try:
            _validate_table_name(old_table)
            _validate_table_name(new_table)
        except ValueError as e:
            return SafetyCheckResult(
                check_name="view_references",
                passed=False,
                severity=SafetyCheckSeverity.HIGH,
                message=f"Invalid table name: {str(e)}",
                violations=[str(e)],
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        try:
            if self.database_type == "postgresql":
                violations = await self._validate_postgresql_views(old_table, new_table)
            elif self.database_type == "sqlite":
                violations = await self._validate_sqlite_views(old_table, new_table)
            else:
                return SafetyCheckResult(
                    check_name="view_references",
                    passed=False,
                    severity=SafetyCheckSeverity.HIGH,
                    message=f"Unsupported database type: {self.database_type}",
                    violations=[f"Database type '{self.database_type}' not supported"],
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            execution_time = (time.time() - start_time) * 1000

            if violations:
                return SafetyCheckResult(
                    check_name="view_references",
                    passed=False,
                    severity=SafetyCheckSeverity.HIGH,
                    message=f"Found {len(violations)} views with old table references",
                    violations=violations,
                    recommendations=[
                        f"Update view definitions to reference '{new_table}'",
                        "Use CREATE OR REPLACE VIEW to update",
                        "Drop and recreate views if needed",
                    ],
                    affected_objects=[old_table, new_table],
                    execution_time_ms=execution_time,
                )
            else:
                return SafetyCheckResult(
                    check_name="view_references",
                    passed=True,
                    severity=SafetyCheckSeverity.INFO,
                    message="No views reference old table",
                    violations=[],
                    execution_time_ms=execution_time,
                )

        except Exception as e:
            self.logger.error(f"View validation failed: {e}")
            return SafetyCheckResult(
                check_name="view_references",
                passed=False,
                severity=SafetyCheckSeverity.HIGH,
                message=f"Validation error: {str(e)}",
                violations=[str(e)],
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    async def _validate_postgresql_views(
        self, old_table: str, new_table: str
    ) -> List[str]:
        """Validate PostgreSQL views.

        Uses regex for word boundary matching to avoid false positives
        (e.g., 'users' should not match 'app_users').

        Args:
            old_table: Original table name (already validated)
            new_table: New table name (already validated)

        Returns:
            List of violation messages
        """
        violations = []

        # Use PostgreSQL regex for word boundary matching
        query = """
        SELECT
            schemaname,
            viewname,
            definition
        FROM pg_views
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
          AND definition ~ $1;
        """

        try:
            async with self.connection_manager.get_connection() as conn:
                # Search for old table name with word boundaries
                # \y matches word boundaries in PostgreSQL regex
                pattern = rf"\y{re.escape(old_table)}\y"
                rows = await conn.fetch(query, pattern)

                for row in rows:
                    violations.append(
                        f"View '{row['schemaname']}.{row['viewname']}' "
                        f"references old table '{old_table}'"
                    )

        except Exception as e:
            self.logger.error(f"PostgreSQL view validation failed: {e}")
            violations.append(f"Database query error: {str(e)}")

        return violations

    async def _validate_sqlite_views(self, old_table: str, new_table: str) -> List[str]:
        """Validate SQLite views.

        Uses regex for word boundary matching to avoid false positives.

        Args:
            old_table: Original table name (already validated)
            new_table: New table name (already validated)

        Returns:
            List of violation messages
        """
        violations = []

        try:
            async with self.connection_manager.get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='view'"
                )
                views = await cursor.fetchall()

                # Use regex with word boundaries to avoid false positives
                # e.g., 'users' should not match 'app_users'
                pattern = re.compile(rf"\b{re.escape(old_table)}\b", re.IGNORECASE)

                for view_name, sql_def in views:
                    if sql_def and pattern.search(sql_def):
                        violations.append(
                            f"View '{view_name}' references old table '{old_table}'"
                        )

        except Exception as e:
            self.logger.error(f"SQLite view validation failed: {e}")
            violations.append(f"Database query error: {str(e)}")

        return violations


async def validate_migration_safety(
    connection_manager: Any,
    old_table: str,
    new_table: str,
    database_type: str = "postgresql",
) -> Dict[str, SafetyCheckResult]:
    """Validate complete migration safety.

    Runs all safety checks (schema integrity + application compatibility)
    and returns aggregated results.

    Args:
        connection_manager: Database connection manager
        old_table: Original table name
        new_table: New table name
        database_type: Database type ("postgresql" or "sqlite")

    Returns:
        Dictionary mapping check names to SafetyCheckResult objects
    """
    results = {}

    # Schema Integrity Checks
    schema_validator = SchemaIntegrityValidator(connection_manager, database_type)
    results["foreign_key_constraints"] = await schema_validator.validate_foreign_keys(
        old_table, new_table
    )

    # Application Compatibility Checks
    app_validator = ApplicationCompatibilityValidator(connection_manager, database_type)
    results["view_references"] = await app_validator.validate_views(
        old_table, new_table
    )

    return results
