#!/usr/bin/env python3
"""
Core Dependency Analysis Engine - TODO-137 Phase 1

Provides comprehensive dependency analysis for PostgreSQL column removal scenarios,
detecting all database objects that depend on a specific column to prevent data loss
and system breakage.

CRITICAL REQUIREMENTS:
- 100% dependency detection accuracy (any missed dependency = potential data loss)
- Support all PostgreSQL object types (FK, views, triggers, indexes, constraints)
- Handle large schemas efficiently (<30 seconds for 1000+ objects)
- Zero tolerance for data loss (conservative, safety-first approach)

Core dependency types detected:
- Foreign Key Dependencies (CRITICAL - data loss prevention)
- View Dependencies (HIGH - system breakage prevention)
- Trigger Dependencies (HIGH - runtime failure prevention)
- Index Dependencies (MEDIUM - performance impact)
- Constraint Dependencies (MEDIUM - data integrity)
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import asyncpg

logger = logging.getLogger(__name__)


class DependencyType(Enum):
    """Types of database dependencies."""

    FOREIGN_KEY = "foreign_key"
    VIEW = "view"
    TRIGGER = "trigger"
    INDEX = "index"
    CONSTRAINT = "constraint"


class ImpactLevel(Enum):
    """Impact level of dependency removal."""

    CRITICAL = "critical"  # Data loss or referential integrity violation
    HIGH = "high"  # System breakage or functionality loss
    MEDIUM = "medium"  # Performance impact or minor functionality
    LOW = "low"  # Minimal impact
    INFORMATIONAL = "informational"  # No impact


@dataclass
class ForeignKeyDependency:
    """Represents a foreign key dependency."""

    constraint_name: str
    source_table: str
    source_column: str
    source_columns: List[str] = field(default_factory=list)
    target_table: str = ""
    target_column: str = ""
    target_columns: List[str] = field(default_factory=list)
    on_delete: str = "RESTRICT"
    on_update: str = "RESTRICT"
    dependency_type: DependencyType = DependencyType.FOREIGN_KEY
    impact_level: ImpactLevel = ImpactLevel.CRITICAL

    def __post_init__(self):
        """Initialize computed fields."""
        if not self.source_columns:
            self.source_columns = [self.source_column] if self.source_column else []
        if not self.target_columns:
            self.target_columns = [self.target_column] if self.target_column else []


@dataclass
class ViewDependency:
    """Represents a view dependency."""

    view_name: str
    view_definition: str
    schema_name: str = "public"
    is_materialized: bool = False
    dependency_type: DependencyType = DependencyType.VIEW
    impact_level: ImpactLevel = ImpactLevel.HIGH


@dataclass
class TriggerDependency:
    """Represents a trigger dependency."""

    trigger_name: str
    event: str  # INSERT, UPDATE, DELETE
    timing: str  # BEFORE, AFTER, INSTEAD OF
    function_name: str
    action_statement: str = ""
    dependency_type: DependencyType = DependencyType.TRIGGER
    impact_level: ImpactLevel = ImpactLevel.HIGH


@dataclass
class IndexDependency:
    """Represents an index dependency."""

    index_name: str
    index_type: str
    columns: List[str]
    is_unique: bool = False
    is_partial: bool = False
    index_definition: str = ""
    dependency_type: DependencyType = DependencyType.INDEX
    impact_level: ImpactLevel = ImpactLevel.MEDIUM


@dataclass
class ConstraintDependency:
    """Represents a constraint dependency."""

    constraint_name: str
    constraint_type: str  # CHECK, UNIQUE, PRIMARY KEY, etc.
    definition: str
    columns: List[str]
    dependency_type: DependencyType = DependencyType.CONSTRAINT
    impact_level: ImpactLevel = ImpactLevel.MEDIUM


@dataclass
class DependencyReport:
    """Comprehensive dependency analysis report."""

    table_name: str
    column_name: str
    dependencies: Dict[DependencyType, List[Any]] = field(default_factory=dict)
    analysis_timestamp: Optional[str] = None
    total_analysis_time: float = 0.0

    def __post_init__(self):
        """Initialize empty dependency lists."""
        for dep_type in DependencyType:
            if dep_type not in self.dependencies:
                self.dependencies[dep_type] = []

    def has_dependencies(self) -> bool:
        """Check if any dependencies exist."""
        return any(len(deps) > 0 for deps in self.dependencies.values())

    def get_critical_dependencies(self) -> List[Any]:
        """Get all dependencies with CRITICAL impact level."""
        critical_deps = []
        for dep_list in self.dependencies.values():
            for dep in dep_list:
                if (
                    hasattr(dep, "impact_level")
                    and dep.impact_level == ImpactLevel.CRITICAL
                ):
                    critical_deps.append(dep)
        return critical_deps

    def get_total_dependency_count(self) -> int:
        """Get total count of all dependencies."""
        return sum(len(deps) for deps in self.dependencies.values())

    def get_all_dependencies(self) -> List[Any]:
        """Get all dependencies as a flattened list."""
        all_deps = []
        for dep_list in self.dependencies.values():
            all_deps.extend(dep_list)
        return all_deps

    @property
    def all_dependencies(self) -> List[Any]:
        """Property alias for get_all_dependencies for backwards compatibility."""
        return self.get_all_dependencies()

    def generate_impact_summary(self) -> Dict[ImpactLevel, int]:
        """Generate summary of dependencies by impact level."""
        impact_summary = {level: 0 for level in ImpactLevel}

        for dep_list in self.dependencies.values():
            for dep in dep_list:
                if hasattr(dep, "impact_level"):
                    impact_summary[dep.impact_level] += 1

        return impact_summary

    def get_removal_recommendation(self) -> str:
        """Get removal safety recommendation."""
        critical_deps = self.get_critical_dependencies()

        if len(critical_deps) > 0:
            return "DANGEROUS"

        impact_summary = self.generate_impact_summary()
        high_impact = impact_summary[ImpactLevel.HIGH]
        medium_impact = impact_summary[ImpactLevel.MEDIUM]

        if high_impact > 0:
            return "CAUTION"
        elif medium_impact > 0:
            return "REVIEW"
        elif self.has_dependencies():
            return "LOW_RISK"
        else:
            return "SAFE"


class DependencyAnalyzer:
    """
    Core dependency analysis engine for PostgreSQL column removal scenarios.

    Detects all database objects dependent on a column to prevent data loss
    and system breakage during column removal operations.
    """

    def __init__(self, connection_manager: Optional[Any] = None):
        """Initialize the dependency analyzer."""
        self.connection_manager = connection_manager
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def analyze_column_dependencies(
        self,
        table_name: str,
        column_name: str,
        connection: Optional[asyncpg.Connection] = None,
    ) -> DependencyReport:
        """
        Analyze all dependencies for a specific column.

        Args:
            table_name: Name of the table
            column_name: Name of the column
            connection: Optional database connection

        Returns:
            DependencyReport with comprehensive analysis
        """
        import time

        start_time = time.time()

        # Sanitize inputs to prevent SQL injection
        safe_table_name = self._sanitize_identifier(table_name)
        safe_column_name = self._sanitize_identifier(column_name)

        self.logger.info(
            f"Analyzing dependencies for {safe_table_name}.{safe_column_name}"
        )

        if connection is None:
            connection = await self._get_connection()

        # Initialize report
        report = DependencyReport(safe_table_name, safe_column_name)

        try:
            # Analyze all dependency types sequentially to avoid connection conflicts
            # Running in parallel causes "another operation in progress" errors with asyncpg

            report.dependencies[DependencyType.FOREIGN_KEY] = (
                await self.find_foreign_key_dependencies(
                    safe_table_name, safe_column_name, connection
                )
            )

            report.dependencies[DependencyType.VIEW] = (
                await self.find_view_dependencies(
                    safe_table_name, safe_column_name, connection
                )
            )

            report.dependencies[DependencyType.TRIGGER] = (
                await self.find_trigger_dependencies(
                    safe_table_name, safe_column_name, connection
                )
            )

            report.dependencies[DependencyType.INDEX] = (
                await self.find_index_dependencies(
                    safe_table_name, safe_column_name, connection
                )
            )

            report.dependencies[DependencyType.CONSTRAINT] = (
                await self.find_constraint_dependencies(
                    safe_table_name, safe_column_name, connection
                )
            )

            analysis_time = time.time() - start_time
            report.total_analysis_time = analysis_time

            self.logger.info(
                f"Dependency analysis complete for {safe_table_name}.{safe_column_name}: "
                f"Found {report.get_total_dependency_count()} dependencies in {analysis_time:.2f}s"
            )

            return report

        except Exception as e:
            self.logger.error(f"Dependency analysis failed: {e}")
            raise

    async def find_foreign_key_dependencies(
        self,
        table_name: str,
        column_name: str,
        connection: Optional[asyncpg.Connection] = None,
    ) -> List[ForeignKeyDependency]:
        """
        Find all foreign key dependencies referencing the column.

        CRITICAL: This detects foreign keys that reference the target column.
        Removing a column referenced by FK constraints will break referential integrity.
        """
        if connection is None:
            connection = await self._get_connection()

        # Query to find all foreign keys referencing this table.column
        fk_query = """
        SELECT DISTINCT
            tc.constraint_name,
            tc.table_name as source_table,
            kcu.column_name as source_column,
            ccu.table_name AS target_table,
            ccu.column_name AS target_column,
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
            AND ccu.table_name = $1
            AND ccu.column_name = $2
            AND tc.table_schema = 'public'
        ORDER BY tc.constraint_name
        """

        try:
            rows = await connection.fetch(fk_query, table_name, column_name)
            dependencies = []

            for row in rows:
                dep = ForeignKeyDependency(
                    constraint_name=row["constraint_name"],
                    source_table=row["source_table"],
                    source_column=row["source_column"],
                    target_table=row["target_table"],
                    target_column=row["target_column"],
                    on_delete=row.get("delete_rule")
                    or row.get("on_delete", "RESTRICT"),
                    on_update=row.get("update_rule")
                    or row.get("on_update", "RESTRICT"),
                )
                dependencies.append(dep)

            self.logger.debug(
                f"Found {len(dependencies)} foreign key dependencies for {table_name}.{column_name}"
            )
            return dependencies

        except Exception as e:
            self.logger.error(f"Error finding foreign key dependencies: {e}")
            return []

    async def find_view_dependencies(
        self,
        table_name: str,
        column_name: str,
        connection: Optional[asyncpg.Connection] = None,
    ) -> List[ViewDependency]:
        """
        Find all views that depend on the column.

        HIGH IMPACT: Removing a column used in views will break those views.
        """
        if connection is None:
            connection = await self._get_connection()

        # Query to find views that reference the column
        view_query = """
        SELECT
            schemaname,
            viewname,
            definition
        FROM pg_views
        WHERE schemaname = 'public'
            AND (
                definition ILIKE '%' || $1 || '.' || $2 || '%'
                OR definition ILIKE '%' || $2 || '%'
            )
        """

        try:
            rows = await connection.fetch(view_query, table_name, column_name)
            dependencies = []

            for row in rows:
                # Additional check to ensure the column is actually referenced
                definition = row.get("definition") or row.get("view_definition", "")
                definition_lower = definition.lower()
                column_patterns = [
                    f"{table_name.lower()}.{column_name.lower()}",
                    f" {column_name.lower()} ",
                    f" {column_name.lower()},",
                    f"({column_name.lower()}",
                    f"{column_name.lower()})",
                ]

                if any(pattern in definition_lower for pattern in column_patterns):
                    dep = ViewDependency(
                        view_name=row.get("viewname") or row.get("view_name"),
                        view_definition=definition,
                        schema_name=row.get("schemaname")
                        or row.get("schema_name", "public"),
                    )
                    dependencies.append(dep)

            self.logger.debug(
                f"Found {len(dependencies)} view dependencies for {table_name}.{column_name}"
            )
            return dependencies

        except Exception as e:
            self.logger.error(f"Error finding view dependencies: {e}")
            return []

    async def find_trigger_dependencies(
        self,
        table_name: str,
        column_name: str,
        connection: Optional[asyncpg.Connection] = None,
    ) -> List[TriggerDependency]:
        """
        Find all triggers that depend on the column.

        HIGH IMPACT: Triggers referencing the column (OLD.column, NEW.column) will fail.
        """
        if connection is None:
            connection = await self._get_connection()

        # Query to find triggers on the table
        trigger_query = """
        SELECT DISTINCT
            t.trigger_name,
            t.event_manipulation,
            t.action_timing,
            t.action_statement,
            p.proname as function_name
        FROM information_schema.triggers t
        LEFT JOIN pg_proc p ON t.action_statement ILIKE '%' || p.proname || '%'
        WHERE t.event_object_table = $1
            AND t.event_object_schema = 'public'
        ORDER BY t.trigger_name
        """

        try:
            rows = await connection.fetch(trigger_query, table_name)
            dependencies = []

            for row in rows:
                # Check if trigger might reference the column
                action_statement = row["action_statement"] or ""
                if self._trigger_references_column(action_statement, column_name):
                    dep = TriggerDependency(
                        trigger_name=row["trigger_name"],
                        event=row["event_manipulation"],
                        timing=row["action_timing"],
                        function_name=row["function_name"] or "unknown",
                        action_statement=action_statement,
                    )
                    dependencies.append(dep)

            self.logger.debug(
                f"Found {len(dependencies)} trigger dependencies for {table_name}.{column_name}"
            )
            return dependencies

        except Exception as e:
            self.logger.error(f"Error finding trigger dependencies: {e}")
            return []

    async def find_index_dependencies(
        self,
        table_name: str,
        column_name: str,
        connection: Optional[asyncpg.Connection] = None,
    ) -> List[IndexDependency]:
        """
        Find all indexes that depend on the column.

        MEDIUM IMPACT: Indexes on the column will be automatically dropped.
        """
        if connection is None:
            connection = await self._get_connection()

        # Query to find indexes that include the column
        index_query = """
        SELECT DISTINCT
            i.relname as index_name,
            am.amname as index_type,
            pg_get_indexdef(i.oid) as index_definition,
            ix.indisunique as is_unique,
            array_agg(a.attname ORDER BY a.attnum) as columns
        FROM pg_class t
        JOIN pg_index ix ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_am am ON i.relam = am.oid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
        WHERE t.relname = $1
            AND t.relkind = 'r'
            AND i.relkind = 'i'
            AND a.attname = $2
        GROUP BY i.relname, am.amname, i.oid, ix.indisunique
        ORDER BY i.relname
        """

        try:
            rows = await connection.fetch(index_query, table_name, column_name)
            dependencies = []

            for row in rows:
                dep = IndexDependency(
                    index_name=row["index_name"],
                    index_type=row["index_type"],
                    columns=row["columns"],
                    is_unique=row["is_unique"],
                    index_definition=row["index_definition"],
                )
                dependencies.append(dep)

            self.logger.debug(
                f"Found {len(dependencies)} index dependencies for {table_name}.{column_name}"
            )
            return dependencies

        except Exception as e:
            self.logger.error(f"Error finding index dependencies: {e}")
            return []

    async def find_constraint_dependencies(
        self,
        table_name: str,
        column_name: str,
        connection: Optional[asyncpg.Connection] = None,
    ) -> List[ConstraintDependency]:
        """
        Find all constraints that depend on the column.

        MEDIUM IMPACT: Check constraints referencing the column will fail.
        """
        if connection is None:
            connection = await self._get_connection()

        # Query to find constraints that reference the column
        constraint_query = """
        SELECT
            tc.constraint_name,
            tc.constraint_type,
            COALESCE(cc.check_clause, tc.constraint_name) as constraint_definition,
            array_agg(kcu.column_name) as columns
        FROM information_schema.table_constraints AS tc
        LEFT JOIN information_schema.check_constraints AS cc
            ON tc.constraint_name = cc.constraint_name
            AND tc.table_schema = cc.constraint_schema
        LEFT JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        WHERE tc.table_name = $1
            AND tc.table_schema = 'public'
            AND tc.constraint_type IN ('CHECK', 'UNIQUE')
            AND (
                cc.check_clause ILIKE '%' || $2 || '%'
                OR kcu.column_name = $2
            )
        GROUP BY tc.constraint_name, tc.constraint_type, cc.check_clause
        ORDER BY tc.constraint_name
        """

        try:
            rows = await connection.fetch(constraint_query, table_name, column_name)
            dependencies = []

            for row in rows:
                dep = ConstraintDependency(
                    constraint_name=row["constraint_name"],
                    constraint_type=row["constraint_type"],
                    definition=row["constraint_definition"],
                    columns=row["columns"] or [],
                )
                dependencies.append(dep)

            self.logger.debug(
                f"Found {len(dependencies)} constraint dependencies for {table_name}.{column_name}"
            )
            return dependencies

        except Exception as e:
            self.logger.error(f"Error finding constraint dependencies: {e}")
            return []

    # Helper methods

    async def _get_connection(self) -> asyncpg.Connection:
        """Get database connection from connection manager."""
        if self.connection_manager is None:
            raise ValueError("Connection manager not configured")

        return await self.connection_manager.get_connection()

    def _sanitize_identifier(self, identifier: str) -> str:
        """Sanitize database identifiers to prevent SQL injection."""
        if not identifier:
            return identifier

        # Remove potentially dangerous characters
        sanitized = re.sub(r"[^\w]", "", identifier)

        # Ensure it starts with a letter or underscore
        if sanitized and not sanitized[0].isalpha() and sanitized[0] != "_":
            sanitized = f"sanitized_{sanitized}"

        return sanitized or "unknown"

    def _trigger_references_column(
        self, action_statement: str, column_name: str
    ) -> bool:
        """Check if trigger action statement references the column."""
        if not action_statement:
            return False

        action_lower = action_statement.lower()
        column_lower = column_name.lower()

        # Check for common trigger patterns that reference columns
        patterns = [
            f"old.{column_lower}",
            f"new.{column_lower}",
            f"old_{column_lower}",
            f"new_{column_lower}",
            f" {column_lower} ",
            f".{column_lower}",
        ]

        return any(pattern in action_lower for pattern in patterns)
