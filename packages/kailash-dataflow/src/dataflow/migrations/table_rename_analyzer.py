#!/usr/bin/env python3
"""
Table Rename Analyzer Engine - TODO-139 Phase 1

Provides comprehensive table rename analysis for PostgreSQL schema operations,
detecting all database objects that reference a table to coordinate safe renames.

CRITICAL REQUIREMENTS:
- 100% schema object discovery (any missed object = potential rename failure)
- Support all PostgreSQL object types (FK, views, triggers, indexes, constraints)
- Referential integrity preservation during table renames
- Multi-table coordination for complex dependency chains
- Zero tolerance for SQL injection in table names

Core schema analysis capabilities:
- Foreign Key Reference Analysis (CRITICAL - maintain referential integrity)
- View Dependency Detection (HIGH - SQL rewriting required)
- Index and Constraint Discovery (MEDIUM - automatic rename handling)
- Trigger Dependency Analysis (HIGH - function reference updates)
- Circular Dependency Detection (CRITICAL - prevent deadlocks)
"""

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import asyncpg

from .dependency_analyzer import DependencyAnalyzer
from .foreign_key_analyzer import ForeignKeyAnalyzer

logger = logging.getLogger(__name__)


class SchemaObjectType(Enum):
    """Types of database schema objects."""

    FOREIGN_KEY = "foreign_key"
    VIEW = "view"
    TRIGGER = "trigger"
    INDEX = "index"
    CONSTRAINT = "constraint"
    SEQUENCE = "sequence"


class RenameImpactLevel(Enum):
    """Impact level of table rename operations."""

    CRITICAL = "critical"  # Will break FK constraints or data integrity
    HIGH = "high"  # Requires SQL rewriting (views, triggers)
    MEDIUM = "medium"  # Automatic handling possible (indexes)
    LOW = "low"  # Minimal coordination required
    SAFE = "safe"  # No dependencies found


@dataclass
class SchemaObject:
    """Represents a database schema object that references a table."""

    object_name: str
    object_type: SchemaObjectType
    definition: str = ""
    depends_on_table: str = ""
    references_table: str = ""  # For FK objects
    schema_name: str = "public"
    impact_level: RenameImpactLevel = RenameImpactLevel.MEDIUM
    requires_sql_rewrite: bool = False
    is_materialized: bool = False  # For materialized views

    def __post_init__(self):
        """Determine if SQL rewriting is required."""
        if self.object_type in [SchemaObjectType.VIEW, SchemaObjectType.TRIGGER]:
            self.requires_sql_rewrite = True

        # Upgrade impact level for critical objects
        if self.object_type == SchemaObjectType.FOREIGN_KEY:
            if "CASCADE" in self.definition.upper():
                self.impact_level = RenameImpactLevel.CRITICAL
            else:
                self.impact_level = RenameImpactLevel.HIGH


@dataclass
class DependencyGraph:
    """Represents dependency graph for table rename operations."""

    root_table: str
    nodes: List[SchemaObject] = field(default_factory=list)
    circular_dependency_detected: bool = False

    def get_critical_dependencies(self) -> List[SchemaObject]:
        """Get all dependencies with CRITICAL impact level."""
        return [
            obj for obj in self.nodes if obj.impact_level == RenameImpactLevel.CRITICAL
        ]

    def get_objects_by_type(self, object_type: SchemaObjectType) -> List[SchemaObject]:
        """Get all objects of a specific type."""
        return [obj for obj in self.nodes if obj.object_type == object_type]

    def has_circular_dependencies(self) -> bool:
        """Check for circular dependencies."""
        # Simple check for now - look for bidirectional FK relationships
        fk_objects = self.get_objects_by_type(SchemaObjectType.FOREIGN_KEY)

        table_references = {}
        for fk in fk_objects:
            depends_on = fk.depends_on_table
            references = fk.references_table

            if depends_on not in table_references:
                table_references[depends_on] = set()
            table_references[depends_on].add(references)

        # Check for circular references
        for table, refs in table_references.items():
            for ref_table in refs:
                if (
                    ref_table in table_references
                    and table in table_references[ref_table]
                ):
                    self.circular_dependency_detected = True
                    return True

        return False


@dataclass
class RenameImpactSummary:
    """Summary of rename impact analysis."""

    overall_risk: RenameImpactLevel = RenameImpactLevel.SAFE
    total_objects: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    safe_count: int = 0
    requires_coordination: bool = False

    def __post_init__(self):
        """Calculate derived fields."""
        self.requires_coordination = self.total_objects > 0


@dataclass
class RenameValidation:
    """Result of table rename validation."""

    is_valid: bool = True
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class RenameOperation:
    """Represents a table rename operation."""

    old_name: str
    new_name: str
    operation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_name: str = "public"


@dataclass
class RenameStep:
    """A single step in the table rename execution plan."""

    step_type: str  # validate_target, drop_foreign_key, rename_table, etc.
    description: str
    sql: str
    rollback_sql: Optional[str] = None
    estimated_duration_ms: int = 100
    risk_level: RenameImpactLevel = RenameImpactLevel.MEDIUM


@dataclass
class TableRenamePlan:
    """Execution plan for table rename operation."""

    old_table_name: str
    new_table_name: str
    operation_id: str
    steps: List[RenameStep] = field(default_factory=list)
    total_estimated_duration_ms: int = 0

    def add_step(self, step: RenameStep):
        """Add a step to the plan."""
        self.steps.append(step)
        self.total_estimated_duration_ms += step.estimated_duration_ms


@dataclass
class RenameExecutionResult:
    """Result of table rename execution."""

    operation_id: str
    old_table_name: str
    new_table_name: str
    success: bool = False
    completed_steps: List[RenameStep] = field(default_factory=list)
    failed_step: Optional[RenameStep] = None
    error_message: Optional[str] = None
    rollback_executed: bool = False
    execution_time_ms: int = 0


@dataclass
class TableRenameReport:
    """Comprehensive table rename analysis report."""

    old_table_name: str
    new_table_name: str
    schema_objects: List[SchemaObject] = field(default_factory=list)
    dependency_graph: Optional[DependencyGraph] = None
    impact_summary: Optional[RenameImpactSummary] = None
    validation: Optional[RenameValidation] = None
    analysis_timestamp: Optional[str] = None
    total_analysis_time: float = 0.0

    def __post_init__(self):
        """Initialize computed fields."""
        if not self.impact_summary:
            self.impact_summary = self._calculate_impact_summary()
        if not self.analysis_timestamp:
            self.analysis_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    def _calculate_impact_summary(self) -> RenameImpactSummary:
        """Calculate impact summary from schema objects."""
        summary = RenameImpactSummary(total_objects=len(self.schema_objects))

        for obj in self.schema_objects:
            if obj.impact_level == RenameImpactLevel.CRITICAL:
                summary.critical_count += 1
            elif obj.impact_level == RenameImpactLevel.HIGH:
                summary.high_count += 1
            elif obj.impact_level == RenameImpactLevel.MEDIUM:
                summary.medium_count += 1
            elif obj.impact_level == RenameImpactLevel.LOW:
                summary.low_count += 1
            else:
                summary.safe_count += 1

        # Determine overall risk
        if summary.critical_count > 0:
            summary.overall_risk = RenameImpactLevel.CRITICAL
        elif summary.high_count > 0:
            summary.overall_risk = RenameImpactLevel.HIGH
        elif summary.medium_count > 0:
            summary.overall_risk = RenameImpactLevel.MEDIUM
        elif summary.low_count > 0:
            summary.overall_risk = RenameImpactLevel.LOW
        else:
            summary.overall_risk = RenameImpactLevel.SAFE

        return summary


class TableRenameError(Exception):
    """Raised when table rename analysis or operation fails."""

    pass


class TableRenameAnalyzer:
    """
    Table Rename Analysis Engine for PostgreSQL schema operations.

    Analyzes all database objects that reference a table to coordinate
    safe rename operations and prevent referential integrity violations.
    """

    def __init__(
        self,
        connection_manager: Optional[Any] = None,
        dependency_analyzer: Optional[DependencyAnalyzer] = None,
        fk_analyzer: Optional[ForeignKeyAnalyzer] = None,
    ):
        """Initialize the table rename analyzer."""
        self.connection_manager = connection_manager
        self.dependency_analyzer = dependency_analyzer or DependencyAnalyzer(
            connection_manager
        )
        self.fk_analyzer = fk_analyzer or ForeignKeyAnalyzer(connection_manager)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._analysis_cache = {}  # Cache for performance

    async def analyze_table_rename(
        self,
        old_table_name: str,
        new_table_name: str,
        connection: Optional[asyncpg.Connection] = None,
    ) -> TableRenameReport:
        """
        Analyze all aspects of a table rename operation.

        Args:
            old_table_name: Current table name
            new_table_name: Desired new table name
            connection: Optional database connection

        Returns:
            TableRenameReport with comprehensive analysis
        """
        start_time = time.time()

        # Validate and sanitize inputs
        safe_old_name = self._sanitize_identifier(old_table_name)
        safe_new_name = self._sanitize_identifier(new_table_name)

        if not safe_old_name or not safe_new_name:
            raise TableRenameError("Table names cannot be empty")

        validation = await self.validate_rename_operation(safe_old_name, safe_new_name)
        if not validation.is_valid:
            raise TableRenameError(f"Invalid rename operation: {validation.violations}")

        self.logger.info(f"Analyzing table rename: {safe_old_name} -> {safe_new_name}")

        try:
            if connection is None:
                connection = await self._get_connection()

            # Discover all schema objects that reference the table
            schema_objects = await self.discover_schema_objects(
                safe_old_name, connection
            )

            # Build dependency graph
            dependency_graph = await self.build_dependency_graph(
                safe_old_name, schema_objects
            )

            # Create comprehensive report
            report = TableRenameReport(
                old_table_name=safe_old_name,
                new_table_name=safe_new_name,
                schema_objects=schema_objects,
                dependency_graph=dependency_graph,
                validation=validation,
                total_analysis_time=time.time() - start_time,
            )

            self.logger.info(
                f"Table rename analysis complete: {len(schema_objects)} objects found, "
                f"risk level: {report.impact_summary.overall_risk.value}"
            )

            return report

        except Exception as e:
            self.logger.error(f"Table rename analysis failed: {e}")
            raise TableRenameError(f"Analysis failed: {str(e)}")

    async def discover_schema_objects(
        self, table_name: str, connection: Optional[asyncpg.Connection] = None
    ) -> List[SchemaObject]:
        """
        Discover all schema objects that reference the target table.

        Args:
            table_name: Name of the table to analyze
            connection: Optional database connection

        Returns:
            List of SchemaObject instances
        """
        if connection is None:
            connection = await self._get_connection()

        all_objects = []

        try:
            # Discover all object types sequentially to avoid connection conflicts
            # Using parallel execution can cause "operation is in progress" errors
            # with shared connections

            # Find incoming FK references (other tables referencing this table)
            incoming_fk_objects = await self.find_foreign_key_references(
                table_name, connection
            )
            all_objects.extend(incoming_fk_objects)

            # Find outgoing FK references (this table referencing other tables)
            # This is needed for circular dependency detection
            outgoing_fk_objects = await self.find_outgoing_foreign_key_references(
                table_name, connection
            )
            all_objects.extend(outgoing_fk_objects)

            view_objects = await self.find_view_dependencies(table_name, connection)
            all_objects.extend(view_objects)

            index_objects = await self.find_index_dependencies(table_name, connection)
            all_objects.extend(index_objects)

            trigger_objects = await self.find_trigger_dependencies(
                table_name, connection
            )
            all_objects.extend(trigger_objects)

            self.logger.debug(
                f"Discovered {len(all_objects)} schema objects for {table_name}"
            )

        except Exception as e:
            self.logger.error(f"Schema object discovery failed: {e}")
            raise TableRenameError(f"Object discovery failed: {str(e)}")

        return all_objects

    async def find_foreign_key_references(
        self, table_name: str, connection: Optional[asyncpg.Connection] = None
    ) -> List[SchemaObject]:
        """Find all foreign key constraints that reference the target table."""
        if connection is None:
            connection = await self._get_connection()

        # Query to find all FKs referencing this table
        fk_query = """
        SELECT DISTINCT
            tc.constraint_name,
            tc.table_name as source_table,
            kcu.column_name as source_column,
            ccu.table_name AS target_table,
            ccu.column_name AS target_column,
            rc.delete_rule,
            rc.update_rule,
            pg_get_constraintdef(pgc.oid) as constraint_definition
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
        JOIN pg_constraint pgc ON pgc.conname = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND ccu.table_name = $1
            AND tc.table_schema = 'public'
        ORDER BY tc.constraint_name
        """

        try:
            rows = await connection.fetch(fk_query, table_name)
            fk_objects = []

            for row in rows:
                # Determine impact level based on CASCADE rules
                definition = row.get("constraint_definition", "")
                impact_level = RenameImpactLevel.HIGH

                if "CASCADE" in definition.upper():
                    impact_level = RenameImpactLevel.CRITICAL

                fk_obj = SchemaObject(
                    object_name=row["constraint_name"],
                    object_type=SchemaObjectType.FOREIGN_KEY,
                    definition=definition,
                    depends_on_table=table_name,
                    references_table=row["source_table"],
                    impact_level=impact_level,
                )
                fk_objects.append(fk_obj)

            return fk_objects

        except Exception as e:
            self.logger.error(f"Error finding FK references: {e}")
            raise RuntimeError(
                f"Failed to discover foreign key constraints for table '{table_name}'. "
                f"Cannot safely proceed with rename operation without complete FK information. "
                f"Error: {e}"
            )

    async def find_outgoing_foreign_key_references(
        self, table_name: str, connection: Optional[asyncpg.Connection] = None
    ) -> List[SchemaObject]:
        """Find all foreign key constraints that this table owns (outgoing references)."""
        if connection is None:
            connection = await self._get_connection()

        # Query to find all FKs that this table owns (pointing to other tables)
        outgoing_fk_query = """
        SELECT DISTINCT
            tc.constraint_name,
            tc.table_name as source_table,
            kcu.column_name as source_column,
            ccu.table_name AS target_table,
            ccu.column_name AS target_column,
            rc.delete_rule,
            rc.update_rule,
            pg_get_constraintdef(pgc.oid) as constraint_definition
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
        JOIN pg_constraint pgc ON pgc.conname = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = $1
            AND tc.table_schema = 'public'
        ORDER BY tc.constraint_name
        """

        try:
            rows = await connection.fetch(outgoing_fk_query, table_name)
            fk_objects = []

            for row in rows:
                # Determine impact level based on CASCADE rules
                definition = row.get("constraint_definition", "")
                impact_level = RenameImpactLevel.HIGH

                if "CASCADE" in definition.upper():
                    impact_level = RenameImpactLevel.CRITICAL

                # For outgoing FKs, the table being renamed depends on the target table
                # This is the reverse relationship from incoming FKs
                fk_obj = SchemaObject(
                    object_name=row["constraint_name"],
                    object_type=SchemaObjectType.FOREIGN_KEY,
                    definition=definition,
                    depends_on_table=row[
                        "target_table"
                    ],  # This table depends on the target
                    references_table=table_name,  # The source table (being renamed)
                    impact_level=impact_level,
                )
                fk_objects.append(fk_obj)

            return fk_objects

        except Exception as e:
            self.logger.error(f"Error finding outgoing FK references: {e}")
            raise RuntimeError(
                f"Failed to discover outgoing foreign key constraints for table '{table_name}'. "
                f"Cannot safely proceed with rename operation without complete FK information. "
                f"Error: {e}"
            )

    async def find_view_dependencies(
        self, table_name: str, connection: Optional[asyncpg.Connection] = None
    ) -> List[SchemaObject]:
        """Find all views that reference the target table."""
        if connection is None:
            connection = await self._get_connection()

        # Query for regular views - improved pattern matching
        view_query = """
        SELECT
            viewname,
            definition,
            schemaname,
            false as is_materialized
        FROM pg_views
        WHERE schemaname = 'public'
            AND (
                definition ILIKE '%FROM ' || $1 || ' %'
                OR definition ILIKE '%FROM ' || $1 || '\n%'
                OR definition ILIKE '%JOIN ' || $1 || ' %'
                OR definition ILIKE '%JOIN ' || $1 || '\n%'
                OR definition ILIKE '%' || $1 || '%'
            )

        UNION ALL

        SELECT
            matviewname as viewname,
            definition,
            schemaname,
            true as is_materialized
        FROM pg_matviews
        WHERE schemaname = 'public'
            AND (
                definition ILIKE '%FROM ' || $1 || ' %'
                OR definition ILIKE '%FROM ' || $1 || '\n%'
                OR definition ILIKE '%JOIN ' || $1 || ' %'
                OR definition ILIKE '%JOIN ' || $1 || '\n%'
                OR definition ILIKE '%' || $1 || '%'
            )
        """

        try:
            rows = await connection.fetch(view_query, table_name)
            view_objects = []

            for row in rows:
                # Use the is_materialized field from our query
                definition = row.get("definition", "")
                is_materialized = row.get("is_materialized", False)
                impact_level = (
                    RenameImpactLevel.HIGH
                    if is_materialized
                    else RenameImpactLevel.MEDIUM
                )

                view_obj = SchemaObject(
                    object_name=row["viewname"],
                    object_type=SchemaObjectType.VIEW,
                    definition=definition,
                    depends_on_table=table_name,
                    schema_name=row.get("schemaname", "public"),
                    impact_level=impact_level,
                    requires_sql_rewrite=True,
                    is_materialized=is_materialized,
                )
                view_objects.append(view_obj)

            return view_objects

        except Exception as e:
            self.logger.error(f"Error finding view dependencies: {e}")
            raise RuntimeError(
                f"Failed to discover view dependencies for table '{table_name}'. "
                f"Cannot safely proceed with rename operation without complete dependency information. "
                f"Error: {e}"
            )

    async def find_index_dependencies(
        self, table_name: str, connection: Optional[asyncpg.Connection] = None
    ) -> List[SchemaObject]:
        """Find all indexes on the target table."""
        if connection is None:
            connection = await self._get_connection()

        index_query = """
        SELECT
            indexname,
            tablename,
            indexdef
        FROM pg_indexes
        WHERE tablename = $1
            AND schemaname = 'public'
        ORDER BY indexname
        """

        try:
            rows = await connection.fetch(index_query, table_name)
            index_objects = []

            for row in rows:
                # Unique indexes have higher impact
                is_unique = "UNIQUE" in row["indexdef"].upper()
                impact_level = (
                    RenameImpactLevel.HIGH if is_unique else RenameImpactLevel.MEDIUM
                )

                index_obj = SchemaObject(
                    object_name=row["indexname"],
                    object_type=SchemaObjectType.INDEX,
                    definition=row["indexdef"],
                    depends_on_table=table_name,
                    impact_level=impact_level,
                )
                index_objects.append(index_obj)

            return index_objects

        except Exception as e:
            self.logger.error(f"Error finding index dependencies: {e}")
            raise RuntimeError(
                f"Failed to discover index dependencies for table '{table_name}'. "
                f"Cannot safely proceed with rename operation without complete dependency information. "
                f"Error: {e}"
            )

    async def find_trigger_dependencies(
        self, table_name: str, connection: Optional[asyncpg.Connection] = None
    ) -> List[SchemaObject]:
        """Find all triggers on the target table."""
        if connection is None:
            connection = await self._get_connection()

        trigger_query = """
        SELECT DISTINCT
            trigger_name,
            event_manipulation,
            action_timing,
            action_statement,
            event_object_table as table_name
        FROM information_schema.triggers
        WHERE event_object_table = $1
            AND event_object_schema = 'public'
        ORDER BY trigger_name
        """

        try:
            rows = await connection.fetch(trigger_query, table_name)
            trigger_objects = []

            for row in rows:
                trigger_obj = SchemaObject(
                    object_name=row["trigger_name"],
                    object_type=SchemaObjectType.TRIGGER,
                    definition=row.get("action_statement", ""),
                    depends_on_table=table_name,
                    impact_level=RenameImpactLevel.HIGH,
                    requires_sql_rewrite=True,
                )
                trigger_objects.append(trigger_obj)

            return trigger_objects

        except Exception as e:
            self.logger.error(f"Error finding trigger dependencies: {e}")
            raise RuntimeError(
                f"Failed to discover trigger dependencies for table '{table_name}'. "
                f"Cannot safely proceed with rename operation without complete dependency information. "
                f"Error: {e}"
            )

    async def build_dependency_graph(
        self, root_table: str, schema_objects: List[SchemaObject]
    ) -> DependencyGraph:
        """Build dependency graph for rename coordination."""
        graph = DependencyGraph(root_table=root_table, nodes=schema_objects)

        # Detect circular dependencies
        graph.has_circular_dependencies()

        return graph

    def calculate_rename_impact(
        self, schema_objects: List[SchemaObject]
    ) -> RenameImpactSummary:
        """Calculate the overall impact of the rename operation."""
        summary = RenameImpactSummary(total_objects=len(schema_objects))

        for obj in schema_objects:
            if obj.impact_level == RenameImpactLevel.CRITICAL:
                summary.critical_count += 1
            elif obj.impact_level == RenameImpactLevel.HIGH:
                summary.high_count += 1
            elif obj.impact_level == RenameImpactLevel.MEDIUM:
                summary.medium_count += 1
            elif obj.impact_level == RenameImpactLevel.LOW:
                summary.low_count += 1
            else:
                summary.safe_count += 1

        # Determine overall risk
        if summary.critical_count > 0:
            summary.overall_risk = RenameImpactLevel.CRITICAL
        elif summary.high_count > 0:
            summary.overall_risk = RenameImpactLevel.HIGH
        elif summary.medium_count > 0:
            summary.overall_risk = RenameImpactLevel.MEDIUM
        elif summary.low_count > 0:
            summary.overall_risk = RenameImpactLevel.LOW
        else:
            summary.overall_risk = RenameImpactLevel.SAFE

        return summary

    async def validate_rename_operation(
        self, old_name: str, new_name: str
    ) -> RenameValidation:
        """Validate table rename operation."""
        violations = []
        warnings = []
        recommendations = []

        # Validate table names
        if not old_name or not new_name:
            violations.append("Table names cannot be empty")

        # Check for SQL injection attempts
        if self._has_sql_injection_risk(old_name) or self._has_sql_injection_risk(
            new_name
        ):
            violations.append("Table names contain potentially dangerous characters")

        # Check if names are identical
        if old_name == new_name:
            violations.append("Old and new table names cannot be identical")

        is_valid = len(violations) == 0

        return RenameValidation(
            is_valid=is_valid,
            violations=violations,
            warnings=warnings,
            recommendations=recommendations,
        )

    # Helper methods

    async def _get_connection(self) -> asyncpg.Connection:
        """Get database connection from connection manager."""
        if self.connection_manager is None:
            raise TableRenameError("Connection manager not configured")

        return await self.connection_manager.get_connection()

    def _sanitize_identifier(self, identifier: str) -> str:
        """Sanitize database identifiers to prevent SQL injection."""
        if not identifier:
            return ""

        # Remove potentially dangerous characters but keep valid identifier chars
        sanitized = re.sub(r"[^\w_]", "", str(identifier))

        # Ensure it starts with letter or underscore
        if sanitized and not sanitized[0].isalpha() and sanitized[0] != "_":
            sanitized = f"sanitized_{sanitized}"

        return sanitized

    def _has_sql_injection_risk(self, text: str) -> bool:
        """Check for SQL injection patterns."""
        if not text:
            return False

        dangerous_patterns = [
            ";",
            "--",
            "/*",
            "*/",
            "DROP",
            "DELETE",
            "INSERT",
            "UPDATE",
            "EXEC",
            "EXECUTE",
            "UNION",
            "SELECT",
        ]

        text_upper = text.upper()
        return any(pattern in text_upper for pattern in dangerous_patterns)

    async def generate_rename_plan(
        self, report: TableRenameReport
    ) -> "TableRenamePlan":
        """
        Generate comprehensive rename execution plan from analysis report.

        Args:
            report: Table rename analysis report

        Returns:
            TableRenamePlan with ordered execution steps
        """
        self.logger.info(
            f"Generating rename plan for {report.old_table_name} -> {report.new_table_name}"
        )

        plan = TableRenamePlan(
            old_table_name=report.old_table_name,
            new_table_name=report.new_table_name,
            operation_id=str(uuid.uuid4()),
        )

        # Phase 1: Pre-rename preparation
        plan.add_step(
            RenameStep(
                step_type="validate_target",
                description=f"Validate target table name '{report.new_table_name}' is available",
                sql=f"SELECT NOT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = '{report.new_table_name}')",
                estimated_duration_ms=10,
                risk_level=RenameImpactLevel.LOW,
            )
        )

        # Phase 2: Drop foreign key constraints (will be recreated)
        fk_objects = [
            obj
            for obj in report.schema_objects
            if obj.object_type == SchemaObjectType.FOREIGN_KEY
        ]
        for fk in fk_objects:
            plan.add_step(
                RenameStep(
                    step_type="drop_foreign_key",
                    description=f"Drop foreign key constraint {fk.object_name}",
                    sql=f"ALTER TABLE {fk.references_table} DROP CONSTRAINT IF EXISTS {fk.object_name}",
                    rollback_sql=fk.definition,  # Store original definition for rollback
                    estimated_duration_ms=50,
                    risk_level=RenameImpactLevel.HIGH,
                )
            )

        # Phase 3: Rename the table
        plan.add_step(
            RenameStep(
                step_type="rename_table",
                description=f"Rename table {report.old_table_name} to {report.new_table_name}",
                sql=f"ALTER TABLE {report.old_table_name} RENAME TO {report.new_table_name}",
                rollback_sql=f"ALTER TABLE {report.new_table_name} RENAME TO {report.old_table_name}",
                estimated_duration_ms=100,
                risk_level=RenameImpactLevel.CRITICAL,
            )
        )

        # Phase 4: Update views
        view_objects = [
            obj
            for obj in report.schema_objects
            if obj.object_type == SchemaObjectType.VIEW
        ]
        for view in view_objects:
            updated_definition = self._update_table_reference_in_sql(
                view.definition, report.old_table_name, report.new_table_name
            )

            if view.is_materialized:
                # Materialized views need to be dropped and recreated
                plan.add_step(
                    RenameStep(
                        step_type="drop_materialized_view",
                        description=f"Drop materialized view {view.object_name}",
                        sql=f"DROP MATERIALIZED VIEW IF EXISTS {view.object_name}",
                        rollback_sql=f"CREATE MATERIALIZED VIEW {view.object_name} AS {view.definition}",
                        estimated_duration_ms=50,
                        risk_level=RenameImpactLevel.HIGH,
                    )
                )
                plan.add_step(
                    RenameStep(
                        step_type="recreate_materialized_view",
                        description=f"Recreate materialized view {view.object_name} with updated table reference",
                        sql=f"CREATE MATERIALIZED VIEW {view.object_name} AS {updated_definition}",
                        rollback_sql=f"DROP MATERIALIZED VIEW IF EXISTS {view.object_name}",
                        estimated_duration_ms=200,
                        risk_level=RenameImpactLevel.HIGH,
                    )
                )
            else:
                # Regular views can use CREATE OR REPLACE
                plan.add_step(
                    RenameStep(
                        step_type="recreate_view",
                        description=f"Recreate view {view.object_name} with updated table reference",
                        sql=f"CREATE OR REPLACE VIEW {view.object_name} AS {updated_definition}",
                        rollback_sql=f"CREATE OR REPLACE VIEW {view.object_name} AS {view.definition}",
                        estimated_duration_ms=100,
                        risk_level=RenameImpactLevel.HIGH,
                    )
                )

        # Phase 5: Recreate foreign key constraints with new table name
        for fk in fk_objects:
            updated_fk_def = self._update_table_reference_in_sql(
                fk.definition, report.old_table_name, report.new_table_name
            )
            plan.add_step(
                RenameStep(
                    step_type="recreate_foreign_key",
                    description=f"Recreate foreign key constraint {fk.object_name}",
                    sql=f"ALTER TABLE {fk.references_table} ADD CONSTRAINT {fk.object_name} {updated_fk_def}",
                    rollback_sql=f"ALTER TABLE {fk.references_table} DROP CONSTRAINT IF EXISTS {fk.object_name}",
                    estimated_duration_ms=100,
                    risk_level=RenameImpactLevel.HIGH,
                )
            )

        # Phase 6: Recreate triggers
        trigger_objects = [
            obj
            for obj in report.schema_objects
            if obj.object_type == SchemaObjectType.TRIGGER
        ]
        for trigger in trigger_objects:
            # Triggers are automatically updated with table rename in PostgreSQL
            # But we need to verify they still work
            plan.add_step(
                RenameStep(
                    step_type="validate_trigger",
                    description=f"Validate trigger {trigger.object_name} after rename",
                    sql=f"SELECT tgname FROM pg_trigger WHERE tgname = '{trigger.object_name}'",
                    estimated_duration_ms=10,
                    risk_level=RenameImpactLevel.MEDIUM,
                )
            )

        # Calculate total estimated duration
        plan.total_estimated_duration_ms = sum(
            step.estimated_duration_ms for step in plan.steps
        )

        self.logger.info(
            f"Rename plan generated with {len(plan.steps)} steps, estimated duration: {plan.total_estimated_duration_ms}ms"
        )

        return plan

    def _update_table_reference_in_sql(
        self, sql: str, old_name: str, new_name: str
    ) -> str:
        """
        Update table references in SQL definition.

        Args:
            sql: Original SQL definition
            old_name: Old table name
            new_name: New table name

        Returns:
            Updated SQL with new table name
        """
        # Simple word boundary replacement - production would use SQL parser
        import re

        # Pattern to match table name with word boundaries
        pattern = r"\b" + re.escape(old_name) + r"\b"
        updated_sql = re.sub(pattern, new_name, sql, flags=re.IGNORECASE)

        return updated_sql

    async def execute_rename_plan(
        self, plan: "TableRenamePlan", connection: Optional[asyncpg.Connection] = None
    ) -> "RenameExecutionResult":
        """
        Execute the table rename plan within a transaction.

        Args:
            plan: Table rename execution plan
            connection: Optional database connection

        Returns:
            RenameExecutionResult with execution details
        """
        if connection is None:
            connection = await self._get_connection()

        result = RenameExecutionResult(
            operation_id=plan.operation_id,
            old_table_name=plan.old_table_name,
            new_table_name=plan.new_table_name,
        )

        start_time = time.time()

        try:
            # Start transaction
            await connection.execute("BEGIN")

            # Execute each step
            for step in plan.steps:
                try:
                    step_start = time.time()

                    # Execute the SQL
                    await connection.execute(step.sql)

                    step_duration = int((time.time() - step_start) * 1000)
                    result.completed_steps.append(step)

                    self.logger.debug(
                        f"Completed step: {step.description} in {step_duration}ms"
                    )

                except Exception as step_error:
                    self.logger.error(f"Step failed: {step.description} - {step_error}")
                    result.failed_step = step
                    result.error_message = str(step_error)

                    # Attempt rollback
                    await self._rollback_rename(
                        plan, result.completed_steps, connection
                    )

                    await connection.execute("ROLLBACK")
                    result.success = False
                    result.rollback_executed = True

                    return result

            # Commit transaction
            await connection.execute("COMMIT")

            result.success = True
            result.execution_time_ms = int((time.time() - start_time) * 1000)

            self.logger.info(
                f"Table rename executed successfully in {result.execution_time_ms}ms"
            )

        except Exception as e:
            self.logger.error(f"Rename execution failed: {e}")

            try:
                await connection.execute("ROLLBACK")
            except:
                pass

            result.success = False
            result.error_message = str(e)

        return result

    async def _rollback_rename(
        self,
        plan: "TableRenamePlan",
        completed_steps: List["RenameStep"],
        connection: asyncpg.Connection,
    ) -> None:
        """
        Rollback completed rename steps.

        Args:
            plan: Original rename plan
            completed_steps: Steps that were successfully completed
            connection: Database connection
        """
        self.logger.info("Starting rename rollback")

        # Execute rollback SQL for completed steps in reverse order
        for step in reversed(completed_steps):
            if step.rollback_sql:
                try:
                    await connection.execute(step.rollback_sql)
                    self.logger.debug(f"Rolled back step: {step.description}")
                except Exception as e:
                    self.logger.error(
                        f"Rollback failed for step {step.description}: {e}"
                    )

    async def validate_rename_completion(
        self,
        old_name: str,
        new_name: str,
        connection: Optional[asyncpg.Connection] = None,
    ) -> bool:
        """
        Validate that table rename completed successfully.

        Args:
            old_name: Original table name
            new_name: New table name
            connection: Optional database connection

        Returns:
            True if rename was successful
        """
        if connection is None:
            connection = await self._get_connection()

        try:
            # Check that new table exists
            new_exists = await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = $1)", new_name
            )

            # Check that old table does not exist
            old_exists = await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = $1)", old_name
            )

            return new_exists and not old_exists

        except Exception as e:
            self.logger.error(f"Validation failed: {e}")
            return False
