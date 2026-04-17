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
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple, Union

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

        # Initialize report
        report = DependencyReport(safe_table_name, safe_column_name)

        try:
            async with self._acquire_connection(connection) as connection:
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
            self.logger.error(
                "dependency_analyzer.dependency_analysis_failed",
                extra={"error": str(e)},
            )
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
            async with self._acquire_connection(connection) as connection:
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
            self.logger.error(
                "dependency_analyzer.error_finding_foreign_key_dependencies",
                extra={"error": str(e)},
            )
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
        # Query both pg_views AND pg_matviews so materialized views are
        # detected as view dependencies. pg_views covers regular views only;
        # pg_matviews is a separate catalog and missing it causes materialized
        # views to be silent orphans in the dependency report — operators
        # drop a column, pg_matviews refresh throws, and the failure surfaces
        # in production, not in the audit.
        view_query = """
        SELECT
            schemaname,
            viewname,
            definition,
            FALSE AS is_materialized
        FROM pg_views
        WHERE schemaname = 'public'
            AND (
                definition ILIKE '%' || $1 || '.' || $2 || '%'
                OR definition ILIKE '%' || $2 || '%'
            )
        UNION ALL
        SELECT
            schemaname,
            matviewname AS viewname,
            definition,
            TRUE AS is_materialized
        FROM pg_matviews
        WHERE schemaname = 'public'
            AND (
                definition ILIKE '%' || $1 || '.' || $2 || '%'
                OR definition ILIKE '%' || $2 || '%'
            )
        """

        try:
            async with self._acquire_connection(connection) as connection:
                rows = await connection.fetch(view_query, table_name, column_name)
                dependencies = []

                for row in rows:
                    # Only accept a view if its definition references the
                    # *qualified* column (table.column) OR the view also
                    # references the target table by name. Matching on the
                    # unqualified column alone (" id " etc.) is a
                    # false-positive magnet: every view in the database that
                    # SELECTs an `id` column would be reported as a
                    # dependency of every other table's `id` column.
                    definition = row.get("definition") or row.get("view_definition", "")
                    definition_lower = definition.lower()
                    table_lower = table_name.lower()
                    column_lower = column_name.lower()

                    # Strong signal: qualified column reference.
                    qualified_ref = f"{table_lower}.{column_lower}"
                    if qualified_ref in definition_lower:
                        matched = True
                    else:
                        # Weaker signal: the view must mention the target
                        # TABLE AND the target column tokenized as its own
                        # word. This permits bare-column selects from the
                        # target table while rejecting identically-named
                        # columns in unrelated tables.
                        column_patterns = [
                            f" {column_lower} ",
                            f" {column_lower},",
                            f"({column_lower}",
                            f"{column_lower})",
                            f" {column_lower}\n",
                            f" {column_lower};",
                        ]
                        mentions_table = (
                            f" {table_lower} " in definition_lower
                            or f" {table_lower}\n" in definition_lower
                            or f"({table_lower} " in definition_lower
                            or f"({table_lower})" in definition_lower
                        )
                        matched = mentions_table and any(
                            pattern in definition_lower for pattern in column_patterns
                        )

                    if matched:
                        dep = ViewDependency(
                            view_name=row.get("viewname") or row.get("view_name"),
                            view_definition=definition,
                            schema_name=row.get("schemaname")
                            or row.get("schema_name", "public"),
                            is_materialized=bool(row.get("is_materialized", False)),
                        )
                        dependencies.append(dep)

                self.logger.debug(
                    f"Found {len(dependencies)} view dependencies for {table_name}.{column_name}"
                )
                return dependencies

        except Exception as e:
            self.logger.error(
                "dependency_analyzer.error_finding_view_dependencies",
                extra={"error": str(e)},
            )
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
        # Query to find triggers on the table. Join pg_trigger → pg_proc
        # via tgfoid (the function OID) to get the function body — NOT via
        # ILIKE against information_schema.triggers.action_statement, which
        # only contains "EXECUTE FUNCTION name()" and fuzzy-matches every
        # proc whose name happens to appear as a substring (and misses the
        # OLD.column / NEW.column references that live in the function body).
        trigger_query = """
        SELECT DISTINCT
            tg.tgname AS trigger_name,
            CASE
                WHEN (tg.tgtype & 4) <> 0 THEN 'INSERT'
                WHEN (tg.tgtype & 8) <> 0 THEN 'DELETE'
                WHEN (tg.tgtype & 16) <> 0 THEN 'UPDATE'
                WHEN (tg.tgtype & 32) <> 0 THEN 'TRUNCATE'
                ELSE 'UNKNOWN'
            END AS event_manipulation,
            CASE
                WHEN (tg.tgtype & 2) <> 0 THEN 'BEFORE'
                WHEN (tg.tgtype & 64) <> 0 THEN 'INSTEAD OF'
                ELSE 'AFTER'
            END AS action_timing,
            pg_get_triggerdef(tg.oid) AS action_statement,
            p.proname AS function_name,
            p.prosrc AS function_source
        FROM pg_trigger tg
        JOIN pg_class c ON c.oid = tg.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_proc p ON p.oid = tg.tgfoid
        WHERE n.nspname = 'public'
            AND c.relname = $1
            AND NOT tg.tgisinternal
        ORDER BY tg.tgname
        """

        try:
            async with self._acquire_connection(connection) as connection:
                rows = await connection.fetch(trigger_query, table_name)
                dependencies = []

                for row in rows:
                    # Check function body AND action_statement. The function
                    # body is where OLD.column / NEW.column live; the action
                    # statement (CREATE TRIGGER DDL) may also reference a
                    # column via WHEN (OLD.col IS DISTINCT FROM NEW.col)
                    # clauses.
                    function_source = row["function_source"] or ""
                    action_statement = row["action_statement"] or ""
                    if self._trigger_references_column(
                        function_source, column_name
                    ) or self._trigger_references_column(action_statement, column_name):
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
            self.logger.error(
                "dependency_analyzer.error_finding_trigger_dependencies",
                extra={"error": str(e)},
            )
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
        # Find every index on the table with enough metadata to decide
        # whether it references the target column. Three cases to handle:
        #
        # 1. Direct column index — ix.indkey contains the column's attnum.
        #    Matched by joining pg_attribute on attnum = ANY(indkey).
        # 2. Expression index — ix.indkey contains 0 in the expression
        #    slot, so the pg_attribute join filters it out. pg_attribute
        #    has no attnum=0 row. These indexes (UPPER(col), to_tsvector(
        #    'english', col), GIN on expression) MUST still be reported;
        #    the column name appears inside pg_get_indexdef() even though
        #    it is not a top-level indexed column.
        # 3. Partial index — the WHERE predicate lives in ix.indpred and
        #    is_partial MUST be set so operators know the drop may cascade
        #    into the predicate.
        #
        # The query returns one row per index with the full indexdef plus
        # indexprs/indpred presence flags; Python decides membership by
        # checking either the direct attname list OR whether the column
        # name appears tokenized inside the indexdef expression.
        index_query = """
        SELECT
            i.relname AS index_name,
            am.amname AS index_type,
            pg_get_indexdef(i.oid) AS index_definition,
            ix.indisunique AS is_unique,
            ix.indexprs IS NOT NULL AS has_expression,
            ix.indpred IS NOT NULL AS is_partial,
            COALESCE(
                ARRAY(
                    SELECT a.attname
                    FROM pg_attribute a
                    WHERE a.attrelid = t.oid
                        AND a.attnum = ANY(ix.indkey)
                        AND a.attnum > 0
                    ORDER BY a.attnum
                ),
                ARRAY[]::text[]
            ) AS direct_columns
        FROM pg_class t
        JOIN pg_index ix ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_am am ON i.relam = am.oid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE t.relname = $1
            AND t.relkind = 'r'
            AND i.relkind = 'i'
            AND n.nspname = 'public'
        ORDER BY i.relname
        """

        try:
            async with self._acquire_connection(connection) as connection:
                rows = await connection.fetch(index_query, table_name)
                dependencies = []

                column_lower = column_name.lower()
                for row in rows:
                    direct_columns = list(row["direct_columns"] or [])
                    definition = row["index_definition"] or ""
                    has_expression = bool(row["has_expression"])

                    # Case 1: column is a direct indexed column (e.g. btree,
                    # partial index, composite index containing the column).
                    matched_direct = column_name in direct_columns

                    # Case 2: column appears inside an expression or
                    # predicate. Tokenize on non-identifier chars to avoid
                    # the "target_col substring of target_column_extra"
                    # false positive that killed the naive ILIKE approach
                    # in find_view_dependencies.
                    matched_expression = False
                    if has_expression or row["is_partial"]:
                        tokens = re.findall(
                            r"[A-Za-z_][A-Za-z0-9_]*", definition.lower()
                        )
                        matched_expression = column_lower in tokens

                    if not (matched_direct or matched_expression):
                        continue

                    dep = IndexDependency(
                        index_name=row["index_name"],
                        index_type=row["index_type"],
                        columns=direct_columns if direct_columns else [column_name],
                        is_unique=bool(row["is_unique"]),
                        is_partial=bool(row["is_partial"]),
                        index_definition=definition,
                    )
                    dependencies.append(dep)

                self.logger.debug(
                    f"Found {len(dependencies)} index dependencies for {table_name}.{column_name}"
                )
                return dependencies

        except Exception as e:
            self.logger.error(
                "dependency_analyzer.error_finding_index_dependencies",
                extra={"error": str(e)},
            )
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
        # Query pg_constraint directly so EXCLUDE constraints are covered
        # alongside CHECK / UNIQUE / PRIMARY KEY. information_schema only
        # exposes CHECK and UNIQUE, so the prior query silently dropped
        # EXCLUDE constraints — a dropped column referenced by an EXCLUDE
        # constraint fails at commit time with no audit signal. Collecting
        # the referenced column names via unnest(conkey) + pg_attribute
        # avoids the information_schema fan-out where key_column_usage
        # returns one row per indexed column.
        #
        # NOT NULL constraints live on pg_attribute (attnotnull), not
        # pg_constraint. They are column-level dependencies — dropping a
        # NOT NULL column's constraint is trivially coupled to dropping
        # the column itself, but other tooling (migration safety audits)
        # needs to see the NOT NULL as a constraint row. UNION ALL with a
        # synthetic row for attnotnull columns preserves that contract.
        constraint_query = """
        SELECT
            con.conname AS constraint_name,
            CASE con.contype
                WHEN 'c' THEN 'CHECK'
                WHEN 'u' THEN 'UNIQUE'
                WHEN 'p' THEN 'PRIMARY KEY'
                WHEN 'x' THEN 'EXCLUDE'
                WHEN 'f' THEN 'FOREIGN KEY'
                ELSE con.contype::text
            END AS constraint_type,
            pg_get_constraintdef(con.oid) AS constraint_definition,
            COALESCE(
                ARRAY(
                    SELECT a.attname
                    FROM unnest(con.conkey) AS k(attnum)
                    JOIN pg_attribute a
                        ON a.attrelid = con.conrelid
                        AND a.attnum = k.attnum
                    ORDER BY k.attnum
                ),
                ARRAY[]::text[]
            ) AS columns
        FROM pg_constraint con
        JOIN pg_class cls ON cls.oid = con.conrelid
        JOIN pg_namespace ns ON ns.oid = cls.relnamespace
        WHERE ns.nspname = 'public'
            AND cls.relname = $1
            AND con.contype IN ('c', 'u', 'p', 'x')
        UNION ALL
        SELECT
            cls.relname || '_' || a.attname || '_not_null' AS constraint_name,
            'NOT NULL' AS constraint_type,
            a.attname || ' IS NOT NULL' AS constraint_definition,
            ARRAY[a.attname]::text[] AS columns
        FROM pg_attribute a
        JOIN pg_class cls ON cls.oid = a.attrelid
        JOIN pg_namespace ns ON ns.oid = cls.relnamespace
        WHERE ns.nspname = 'public'
            AND cls.relname = $1
            AND a.attnum > 0
            AND NOT a.attisdropped
            AND a.attnotnull
        ORDER BY constraint_name
        """

        try:
            async with self._acquire_connection(connection) as connection:
                rows = await connection.fetch(constraint_query, table_name)
                dependencies = []

                column_lower = column_name.lower()
                for row in rows:
                    columns = list(row["columns"] or [])
                    definition = row["constraint_definition"] or ""

                    # Membership rule: column is in the constraint's direct
                    # column list (UNIQUE, PK, EXCLUDE's indexed column)
                    # OR appears tokenized inside the constraintdef text
                    # (CHECK clauses, EXCLUDE's USING ... WITH expressions).
                    in_direct = column_name in columns
                    in_def = False
                    if not in_direct:
                        tokens = re.findall(
                            r"[A-Za-z_][A-Za-z0-9_]*", definition.lower()
                        )
                        in_def = column_lower in tokens

                    if not (in_direct or in_def):
                        continue

                    dep = ConstraintDependency(
                        constraint_name=row["constraint_name"],
                        constraint_type=row["constraint_type"],
                        definition=definition,
                        columns=columns,
                    )
                    dependencies.append(dep)

                self.logger.debug(
                    f"Found {len(dependencies)} constraint dependencies for {table_name}.{column_name}"
                )
                return dependencies

        except Exception as e:
            self.logger.error(
                "dependency_analyzer.error_finding_constraint_dependencies",
                extra={"error": str(e)},
            )
            return []

    # Helper methods

    async def _get_connection(self) -> asyncpg.Connection:
        """Get database connection from connection manager.

        NOTE: Prefer _acquire_connection() for all analyzer call sites.
        Raw get_connection() acquires without close() leak asyncpg
        connections (Cluster B: TooManyConnectionsError mid-analysis).
        """
        if self.connection_manager is None:
            raise ValueError("Connection manager not configured")

        return await self.connection_manager.get_connection()

    @asynccontextmanager
    async def _acquire_connection(
        self, connection: Optional[asyncpg.Connection]
    ) -> AsyncIterator[asyncpg.Connection]:
        """Acquire-or-borrow connection with ownership-aware cleanup.

        If ``connection`` is not None, yields it unchanged (caller owns
        lifecycle). If None, acquires a fresh connection and closes it
        on exit including on exception. Single leak-proof acquire point.
        """
        if connection is not None:
            yield connection
            return

        owned = await self._get_connection()
        try:
            yield owned
        finally:
            try:
                await owned.close()
            except Exception as close_exc:  # noqa: BLE001
                self.logger.warning(
                    "dependency_analyzer.connection_close_failed",
                    extra={"error": str(close_exc)},
                )

    def _sanitize_identifier(self, identifier: str) -> str:
        """Sanitize database identifiers to prevent SQL injection.

        Preserves quoted identifiers (``"foo-bar"``) by stripping the outer
        double quotes and returning the inner text verbatim. PostgreSQL
        quoted identifiers may contain ``-``, ``#``, spaces, and unicode,
        all of which the unquoted path strips. Treating a quoted identifier
        the same as an unquoted one destroyed legitimate names like
        ``"acc_edge-test_#hex"`` and caused the analyzer to search for a
        table that never exists.

        Unquoted identifiers still go through the strict allowlist path
        so raw user input like ``"foo'; DROP TABLE bar"`` is still scrubbed.
        """
        if not identifier:
            return identifier

        # Quoted identifier: trust the surrounding quotes and return the
        # inner text verbatim. PostgreSQL interprets every character inside
        # "..." as part of the identifier, so the inner text is passed to
        # parameterized catalog queries where it is bound as a value and
        # cannot be used for injection.
        if (
            len(identifier) >= 2
            and identifier.startswith('"')
            and identifier.endswith('"')
        ):
            inner = identifier[1:-1].replace('""', '"')
            return inner or "unknown"

        # Unquoted: remove potentially dangerous characters.
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
