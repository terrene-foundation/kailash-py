"""
Schema State Management System

Provides schema caching, change detection, and migration history tracking
with high performance (<100ms operations) and rollback capabilities.

This system integrates with the existing AutoMigrationSystem to provide:
- Schema caching with configurable TTL and size limits
- Change detection comparing models vs database schema
- Migration history tracking with complete rollback capability
- Performance optimization with <100ms schema comparison operations
"""

import asyncio
import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


def _execute_workflow_safe(workflow) -> Tuple[Dict[str, Any], str]:
    """
    Execute a workflow safely in any context (sync or async).

    ARCHITECTURE FIX (v0.10.11):
    This function now uses synchronous database connections (psycopg2/sqlite3)
    instead of async connections via AsyncLocalRuntime.

    The previous async_safe_run approach failed in Docker/FastAPI because:
    - async_safe_run creates a NEW event loop in a thread pool
    - Database connections are bound to the event loop they're created in
    - Connections created in thread pool's loop cannot be used in uvicorn's loop

    The new sync approach works because:
    - DDL operations don't need async - they're one-time setup operations
    - Sync connections (psycopg2) have no event loop binding

    Args:
        workflow: The WorkflowBuilder instance to execute

    Returns:
        Tuple of (results dict, run_id string)
    """
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    # Extract the query and connection info from the workflow
    built_workflow = workflow.build()
    results = {}
    run_id = f"sync_ddl_{id(workflow)}"

    # FIX: built_workflow.nodes is a dict, not a list - iterate over values
    for node in built_workflow.nodes.values():
        node_id = node.node_id
        params = node.config  # FIX: NodeInstance uses .config, not .parameters

        # Extract connection string and query from node parameters
        connection_string = params.get("connection_string", "")
        query = params.get("query", "")

        if not connection_string or not query:
            logger.warning(
                f"Node {node_id} missing connection_string or query, skipping"
            )
            results[node_id] = {"result": [], "error": "Missing parameters"}
            continue

        # Use sync executor
        executor = SyncDDLExecutor(connection_string)

        # Determine if this is a DDL or query operation
        query_upper = query.strip().upper()
        is_ddl = any(
            query_upper.startswith(kw)
            for kw in ["CREATE", "ALTER", "DROP", "INSERT", "UPDATE", "DELETE"]
        )

        if is_ddl:
            result = executor.execute_ddl(query)
            if result.get("success"):
                results[node_id] = {"result": [], "success": True}
            else:
                results[node_id] = {"result": [], "error": result.get("error")}
        else:
            # Schema inspection queries (SELECT)
            result = executor.execute_query(query)
            if "error" in result:
                results[node_id] = {"result": [], "error": result.get("error")}
            else:
                results[node_id] = {"result": result.get("result", [])}

    return results, run_id


class DataLossRisk(Enum):
    """Levels of data loss risk for migrations."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MigrationStatus(Enum):
    """Status of migration operations."""

    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ChangeType(Enum):
    """Types of schema changes."""

    CREATE_TABLE = "create_table"
    DROP_TABLE = "drop_table"
    ADD_COLUMN = "add_column"
    DROP_COLUMN = "drop_column"
    MODIFY_COLUMN = "modify_column"
    ADD_INDEX = "add_index"
    DROP_INDEX = "drop_index"


@dataclass
class CacheEntry:
    """Cache entry with schema and timestamp."""

    schema: "DatabaseSchema"
    timestamp: datetime


@dataclass
class DatabaseSchema:
    """Represents database schema structure."""

    tables: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    indexes: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    constraints: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)


@dataclass
class ModelSchema:
    """Represents model schema structure."""

    tables: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class SchemaComparisonResult:
    """Results of schema comparison."""

    added_tables: List[str] = field(default_factory=list)
    removed_tables: List[str] = field(default_factory=list)
    modified_tables: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def has_changes(self) -> bool:
        """Check if there are any schema changes."""
        return bool(self.added_tables or self.removed_tables or self.modified_tables)


@dataclass
class MigrationOperation:
    """Represents a single migration operation."""

    operation_type: str
    table_name: str
    details: Dict[str, Any] = field(default_factory=dict)
    sql_up: str = ""
    sql_down: str = ""


@dataclass
class SafetyAssessment:
    """Assessment of migration safety."""

    overall_risk: DataLossRisk
    is_safe: bool
    warnings: List[str] = field(default_factory=list)
    affected_tables: List[str] = field(default_factory=list)
    rollback_possible: bool = True


@dataclass
class RollbackStep:
    """Single step in a rollback plan."""

    operation_type: str
    sql: str
    estimated_duration: int  # milliseconds
    risk_level: str


@dataclass
class MigrationRecord:
    """Record of a migration."""

    migration_id: str
    name: str
    operations: List[Dict[str, Any]]
    status: MigrationStatus
    applied_at: Optional[datetime] = None
    checksum: Optional[str] = None
    duration_ms: Optional[int] = None


@dataclass
class RollbackPlan:
    """Plan for rolling back a migration."""

    migration_id: str
    steps: List[RollbackStep]
    estimated_duration: int  # milliseconds
    data_loss_warning: Optional[str] = None
    requires_backup: bool = False
    fully_reversible: bool = True
    irreversible_operations: List[str] = field(default_factory=list)


class SchemaCache:
    """
    High-performance schema caching system with TTL and size limits.

    Provides <100ms cache operations and configurable cache policies.
    """

    def __init__(self, ttl: int = 300, max_size: int = 100):
        """
        Initialize schema cache.

        Args:
            ttl: Time-to-live for cache entries in seconds (default 5 minutes)
            max_size: Maximum number of cached schemas (default 100)
        """
        self.ttl = ttl
        self.max_size = max_size
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._access_times: Dict[str, datetime] = {}
        self._lock = threading.RLock()  # Thread-safe operations

    def get_cached_schema(self, connection_id: str) -> Optional[DatabaseSchema]:
        """
        Retrieve cached schema if valid.

        Args:
            connection_id: Unique identifier for database connection

        Returns:
            Cached schema if valid and not expired, None otherwise
        """
        with self._lock:
            if connection_id not in self._cache:
                return None

            entry = self._cache[connection_id]

            # Check TTL expiration
            if self._is_expired(entry):
                # Clean up expired entry
                del self._cache[connection_id]
                if connection_id in self._access_times:
                    del self._access_times[connection_id]
                return None

            # Update LRU order and access time
            self._cache.move_to_end(connection_id)
            self._access_times[connection_id] = datetime.now()

            return entry.schema

    def cache_schema(self, connection_id: str, schema: DatabaseSchema) -> None:
        """
        Cache schema with timestamp.

        Args:
            connection_id: Unique identifier for database connection
            schema: Database schema to cache
        """
        with self._lock:
            current_time = datetime.now()

            # Enforce size limit with LRU eviction
            if len(self._cache) >= self.max_size and connection_id not in self._cache:
                # Remove least recently used entry
                oldest_id, _ = self._cache.popitem(last=False)
                if oldest_id in self._access_times:
                    del self._access_times[oldest_id]

            # Store new entry
            entry = CacheEntry(schema=schema, timestamp=current_time)
            self._cache[connection_id] = entry
            self._access_times[connection_id] = current_time

            # Move to end (most recently used)
            self._cache.move_to_end(connection_id)

    def invalidate_cache(self, connection_id: Optional[str] = None) -> None:
        """
        Invalidate specific or all cached schemas.

        Args:
            connection_id: Specific connection to invalidate, or None for all
        """
        with self._lock:
            if connection_id is None:
                # Invalidate all
                self._cache.clear()
                self._access_times.clear()
            else:
                # Invalidate specific entry
                if connection_id in self._cache:
                    del self._cache[connection_id]
                if connection_id in self._access_times:
                    del self._access_times[connection_id]

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if cache entry is expired based on TTL."""
        expiry_time = entry.timestamp + timedelta(seconds=self.ttl)
        return datetime.now() > expiry_time


class SchemaChangeDetector:
    """
    High-accuracy schema change detection engine.

    Compares model definitions vs database state with 100% accuracy
    and provides detailed migration operation detection.
    """

    def __init__(self):
        """Initialize schema change detector."""
        pass

    def compare_schemas(
        self,
        model_schema: ModelSchema,
        db_schema: DatabaseSchema,
        incremental_mode: bool = True,
    ) -> SchemaComparisonResult:
        """
        Compare model definitions vs database state.

        Args:
            model_schema: Schema derived from model definitions
            db_schema: Current database schema
            incremental_mode: If True (default), only compare specified tables, don't detect removals.
                             If False, do full schema comparison including removal detection.

        Returns:
            Detailed comparison results with all detected changes
        """
        from ..core.schema_comparator import compare_schemas_unified

        # Use unified schema comparator
        unified_result = compare_schemas_unified(
            db_schema,  # current schema
            model_schema,  # target schema
            incremental_mode=incremental_mode,
            compatibility_check=True,
        )

        # Convert UnifiedSchemaComparisonResult back to SchemaComparisonResult for backward compatibility
        result = SchemaComparisonResult()
        result.added_tables = unified_result.added_tables
        result.removed_tables = unified_result.removed_tables
        result.modified_tables = unified_result.modified_tables

        # Log performance information from unified comparator
        if unified_result.execution_time_ms > 100:
            logger.warning(
                f"Schema comparison took {unified_result.execution_time_ms:.2f}ms, "
                f"exceeding 100ms performance target"
            )

        return result

    def detect_required_migrations(
        self, comparison: SchemaComparisonResult
    ) -> List[MigrationOperation]:
        """
        Identify specific migration operations needed.

        Args:
            comparison: Results from schema comparison

        Returns:
            List of migration operations ordered for safe execution
        """
        operations = []

        # Safe operations first (create, add)
        for table_name in comparison.added_tables:
            operations.append(
                MigrationOperation(
                    operation_type="CREATE_TABLE",
                    table_name=table_name,
                    details={"action": "create_new_table"},
                )
            )

        # Add columns (safe operations)
        for table_name, changes in comparison.modified_tables.items():
            for column_name in changes.get("added_columns", []):
                operations.append(
                    MigrationOperation(
                        operation_type="ADD_COLUMN",
                        table_name=table_name,
                        details={"column_name": column_name, "action": "add_column"},
                    )
                )

        # Modify columns (medium risk)
        for table_name, changes in comparison.modified_tables.items():
            for column_name, column_changes in changes.get(
                "modified_columns", {}
            ).items():
                operations.append(
                    MigrationOperation(
                        operation_type="MODIFY_COLUMN",
                        table_name=table_name,
                        details={
                            "column_name": column_name,
                            "changes": column_changes,
                            "action": "modify_column",
                        },
                    )
                )

        # Dangerous operations last (drop, remove)
        for table_name, changes in comparison.modified_tables.items():
            for column_name in changes.get("removed_columns", []):
                operations.append(
                    MigrationOperation(
                        operation_type="DROP_COLUMN",
                        table_name=table_name,
                        details={"column_name": column_name, "action": "drop_column"},
                    )
                )

        for table_name in comparison.removed_tables:
            operations.append(
                MigrationOperation(
                    operation_type="DROP_TABLE",
                    table_name=table_name,
                    details={"action": "drop_table"},
                )
            )

        return operations

    def validate_migration_safety(
        self, operations: List[MigrationOperation]
    ) -> SafetyAssessment:
        """
        Assess data loss risk of proposed migrations.

        Args:
            operations: List of migration operations to assess

        Returns:
            Safety assessment with risk level and warnings
        """
        warnings = []
        affected_tables = set()
        overall_risk = DataLossRisk.NONE
        rollback_possible = True

        for operation in operations:
            affected_tables.add(operation.table_name)

            if operation.operation_type == "DROP_TABLE":
                warnings.append(
                    f"DROP_TABLE {operation.table_name} will permanently delete all data"
                )
                overall_risk = DataLossRisk.HIGH
                rollback_possible = False

            elif operation.operation_type == "DROP_COLUMN":
                warnings.append(
                    f"DROP_COLUMN will permanently delete data in {operation.table_name}"
                )
                risk_order = {"none": 0, "low": 1, "medium": 2, "high": 3}
                if risk_order[overall_risk.value] < risk_order[DataLossRisk.HIGH.value]:
                    overall_risk = DataLossRisk.HIGH

            elif operation.operation_type == "MODIFY_COLUMN":
                changes = operation.details.get("changes", {})
                # Check for type changes in the changes dict or directly in details
                old_type = changes.get("old_type") or operation.details.get("old_type")
                new_type = changes.get("new_type") or operation.details.get("new_type")

                if old_type and new_type and old_type != new_type:
                    warnings.append(
                        f"Type change may cause data loss in {operation.table_name}"
                    )
                    # Update risk level - need to compare enum order
                    risk_order = {"none": 0, "low": 1, "medium": 2, "high": 3}
                    if (
                        risk_order[overall_risk.value]
                        < risk_order[DataLossRisk.MEDIUM.value]
                    ):
                        overall_risk = DataLossRisk.MEDIUM

        is_safe = overall_risk == DataLossRisk.NONE

        return SafetyAssessment(
            overall_risk=overall_risk,
            is_safe=is_safe,
            warnings=warnings,
            affected_tables=list(affected_tables),
            rollback_possible=rollback_possible,
        )

    def _compare_table_structures(
        self, model_table: Dict[str, Any], db_table: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Compare individual table structures for changes.

        Args:
            model_table: Table structure from model
            db_table: Table structure from database

        Returns:
            Dictionary of changes or None if no changes
        """
        changes = {}

        model_columns = model_table.get("columns", {})
        db_columns = db_table.get("columns", {})

        model_col_names = set(model_columns.keys())
        db_col_names = set(db_columns.keys())

        # Added columns
        added_columns = list(model_col_names - db_col_names)
        if added_columns:
            changes["added_columns"] = added_columns

        # Removed columns
        removed_columns = list(db_col_names - model_col_names)
        if removed_columns:
            changes["removed_columns"] = removed_columns

        # Modified columns
        modified_columns = {}
        common_columns = model_col_names & db_col_names

        for col_name in common_columns:
            model_col = model_columns[col_name]
            db_col = db_columns[col_name]

            col_changes = {}

            # Check type changes (normalize types before comparison)
            model_type = self._normalize_sql_type(model_col.get("type"))
            db_type = self._normalize_sql_type(db_col.get("type"))

            if model_type != db_type:
                col_changes["old_type"] = db_col.get("type")
                col_changes["new_type"] = model_col.get("type")

            # Check nullable changes
            if model_col.get("nullable") != db_col.get("nullable"):
                col_changes["old_nullable"] = db_col.get("nullable")
                col_changes["new_nullable"] = model_col.get("nullable")

            if col_changes:
                modified_columns[col_name] = col_changes

        if modified_columns:
            changes["modified_columns"] = modified_columns

        return changes if changes else None

    def _normalize_sql_type(self, sql_type: str) -> str:
        """
        Normalize SQL types for comparison to avoid false positives.

        Maps equivalent SQL types to a canonical form:
        - SERIAL/serial -> integer (SERIAL is just integer with auto-increment)
        - INTEGER/integer -> integer
        - VARCHAR(255)/character varying -> varchar
        - TIMESTAMP/timestamp without time zone -> timestamp
        - BOOLEAN/boolean -> boolean

        Args:
            sql_type: Raw SQL type string

        Returns:
            Normalized type string for comparison
        """
        if not sql_type:
            return ""

        # Convert to lowercase and remove common variations
        normalized = sql_type.lower().strip()

        # Handle SERIAL types (PostgreSQL auto-increment integers)
        if normalized in ["serial", "bigserial", "smallserial"]:
            return "integer"

        # Handle integer types
        if normalized in [
            "integer",
            "int",
            "int4",
            "bigint",
            "int8",
            "smallint",
            "int2",
        ]:
            return "integer"

        # Handle string/text types
        if normalized.startswith("varchar") or normalized.startswith(
            "character varying"
        ):
            return "varchar"
        if normalized in ["text", "char", "character"]:
            return "varchar"

        # Handle timestamp types
        if normalized.startswith("timestamp"):
            return "timestamp"
        if normalized in [
            "datetime",
            "timestamptz",
            "timestamp with time zone",
            "timestamp without time zone",
        ]:
            return "timestamp"

        # Handle boolean types
        if normalized in ["boolean", "bool"]:
            return "boolean"

        # Handle numeric types
        if normalized in [
            "real",
            "float",
            "double",
            "double precision",
            "numeric",
            "decimal",
        ]:
            return "numeric"

        # Return normalized form for other types
        return normalized


class MigrationHistoryManager:
    """
    Migration history tracking and rollback management.

    Uses Kailash WorkflowBuilder pattern for consistent async execution.
    PostgreSQL-optimized with JSONB support and proper parameter binding.
    """

    def __init__(self, dataflow_instance):
        """
        Initialize migration history manager.

        Automatically detects async context and uses appropriate runtime
        to prevent deadlocks in FastAPI, pytest async, and other async environments.

        Args:
            dataflow_instance: DataFlow instance for database access via WorkflowBuilder
        """
        self.dataflow = dataflow_instance

        # ✅ FIX: Detect async context and use appropriate runtime
        # This prevents deadlocks when DataFlow is used in FastAPI, pytest async, etc.
        try:
            asyncio.get_running_loop()
            # Running in async context - use AsyncLocalRuntime
            from kailash.runtime import AsyncLocalRuntime

            self.runtime = AsyncLocalRuntime()
            self._is_async = True
            logger.debug(
                "MigrationHistoryManager: Detected async context, using AsyncLocalRuntime"
            )
        except RuntimeError:
            # No event loop - use sync LocalRuntime
            from kailash.runtime.local import LocalRuntime

            self.runtime = LocalRuntime()
            self._is_async = False
            logger.debug(
                "MigrationHistoryManager: Detected sync context, using LocalRuntime"
            )

        self._ensure_history_table()

    def _extract_query_data(
        self, results: Dict[str, Any], node_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Extract data from query results, handling different result structures."""
        node_result = results.get(node_id, {})

        # Check for result.data structure (newer format)
        if "result" in node_result and "data" in node_result["result"]:
            return node_result["result"]["data"]

        # Check for direct data structure (older format)
        if "data" in node_result:
            return node_result["data"]

        # Check for result as list
        if "result" in node_result and isinstance(node_result["result"], list):
            return node_result["result"]

        return None

    def record_migration(self, migration: MigrationRecord) -> None:
        """
        Record migration in history using WorkflowBuilder pattern.

        This method tries to record migrations but fails gracefully if event loops are problematic.

        Args:
            migration: Migration record to store
        """
        # Try multiple approaches in order of preference
        attempts = [
            ("thread_pool", self._record_migration_with_thread_pool),
            ("sync", self._record_migration_sync),
            ("fallback", self._record_migration_fallback),
        ]

        for attempt_name, attempt_func in attempts:
            try:
                logger.debug(f"Attempting migration recording via {attempt_name}")
                attempt_func(migration)
                logger.debug(f"Migration recording successful via {attempt_name}")
                return
            except Exception as e:
                # Enhanced error messages with context (Bug #3 fix)
                error_context = self._get_error_context(e)
                logger.warning(
                    f"Migration recording failed via {attempt_name}: {e}\\n{error_context}"
                )
                continue

        # If all attempts fail, log but don't crash the migration
        logger.error(
            "All migration recording attempts failed - migration will proceed without history recording\\n"
            "IMPACT: Migration completed successfully but history not recorded\\n"
            "CAUSE: Unable to write to migration history table\\n"
            "FIX: Check database permissions and ensure migration tables exist"
        )

    def _get_error_context(self, error: Exception) -> str:
        """
        Get helpful context for migration recording errors.

        Args:
            error: The exception that occurred

        Returns:
            Contextual help message
        """
        error_str = str(error).lower()

        # Detect specific error patterns and provide context
        if "cannot be called from a running event loop" in error_str:
            return (
                "CONTEXT: DataFlow called from async context (FastAPI/async app)\\n"
                "NOTE: This error is expected and handled - trying fallback method\\n"
                "INFO: Upgrade to DataFlow v0.7.3+ for improved async support"
            )
        elif "timeout" in error_str:
            return (
                "CONTEXT: Migration recording took too long\\n"
                "POSSIBLE CAUSES: Database connection slow, large migration data\\n"
                "SUGGESTION: Check database connectivity and performance"
            )
        elif "permission" in error_str or "access denied" in error_str:
            return (
                "CONTEXT: Database permission issue\\n"
                "FIX: Ensure database user has INSERT permission on migration tables"
            )
        elif "no such table" in error_str or "relation" in error_str:
            return (
                "CONTEXT: Migration history table does not exist\\n"
                "FIX: Ensure migration tracking table is created (auto_migrate should handle this)"
            )
        else:
            return "SUGGESTION: Check database connectivity and migration table schema"

    def _record_migration_fallback(self, migration: MigrationRecord) -> None:
        """
        Fallback migration recording that always succeeds (possibly as no-op).

        This ensures that migration recording failures don't break actual migrations.
        """
        logger.warning(
            f"Migration {migration.migration_id} completed but could not be recorded in history"
        )
        # In a production system, you might want to write to a file or queue for later processing

    async def _record_migration_async(self, migration: MigrationRecord) -> None:
        """
        Async version of migration recording.

        Args:
            migration: Migration record to store
        """
        from kailash.workflow.builder import WorkflowBuilder

        from ..adapters.connection_parser import ConnectionParser

        # Get connection URL and detect database type
        connection_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        database_type = ConnectionParser.detect_database_type(connection_url)

        # Serialize operations as JSON
        operations_json = json.dumps(migration.operations)

        # Use database-specific SQL for recording migrations
        if database_type.lower() == "sqlite":
            # SQLite doesn't support JSONB or ON CONFLICT with specific columns
            query = """
                INSERT OR REPLACE INTO dataflow_migration_history
                (migration_id, name, operations, status, applied_at, checksum, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
        else:  # PostgreSQL
            query = """
                INSERT INTO dataflow_migration_history
                (migration_id, name, operations, status, applied_at, checksum, duration_ms)
                VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7)
                ON CONFLICT (migration_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    applied_at = EXCLUDED.applied_at,
                    duration_ms = EXCLUDED.duration_ms
            """

        # Use WorkflowBuilder with SQLDatabaseNode for consistent execution
        workflow = WorkflowBuilder()
        workflow.add_node(
            "SQLDatabaseNode",
            "record_migration",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": query,
                "params": [
                    migration.migration_id,
                    migration.name,
                    operations_json,
                    migration.status.value,
                    migration.applied_at,
                    migration.checksum,
                    migration.duration_ms,
                ],
            },
        )

        try:
            # Use async execution for proper event loop management
            results, _ = await self.runtime.execute_async(workflow.build())
            if results.get("record_migration", {}).get("error"):
                error_msg = results["record_migration"]["error"]
                logger.error(f"Failed to record migration: {error_msg}")
                raise Exception(f"Database error: {error_msg}")
        except Exception as e:
            logger.error(f"Failed to record migration: {e}")
            raise

    def _record_migration_with_thread_pool(self, migration: MigrationRecord) -> None:
        """
        Record migration with automatic async/sync context detection.

        Phase 6: Uses async_safe_run for transparent sync/async bridging.
        Works correctly in FastAPI, Docker, Jupyter, and traditional scripts.

        Args:
            migration: Migration record to store

        Raises:
            Exception: If migration recording fails
        """
        try:
            # Phase 6: Use async_safe_run for proper event loop handling
            result = async_safe_run(
                self._record_migration_async(migration), timeout=30  # 30 second timeout
            )
            logger.debug("Migration recording successful")
            return result

        except Exception as e:
            logger.error(f"Migration recording failed: {e}")
            raise

    def _record_migration_sync(self, migration: MigrationRecord) -> None:
        """
        Sync version of migration recording using thread pool.

        Args:
            migration: Migration record to store
        """
        from kailash.workflow.builder import WorkflowBuilder

        from ..adapters.connection_parser import ConnectionParser

        # Get connection URL and detect database type
        connection_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        database_type = ConnectionParser.detect_database_type(connection_url)

        # Serialize operations as JSON
        operations_json = json.dumps(migration.operations)

        # Use database-specific SQL for recording migrations
        if database_type.lower() == "sqlite":
            # SQLite doesn't support JSONB or ON CONFLICT with specific columns
            query = """
                INSERT OR REPLACE INTO dataflow_migration_history
                (migration_id, name, operations, status, applied_at, checksum, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
        else:  # PostgreSQL
            query = """
                INSERT INTO dataflow_migration_history
                (migration_id, name, operations, status, applied_at, checksum, duration_ms)
                VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7)
                ON CONFLICT (migration_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    applied_at = EXCLUDED.applied_at,
                    duration_ms = EXCLUDED.duration_ms
            """

        # Use WorkflowBuilder with SQLDatabaseNode for consistent execution
        workflow = WorkflowBuilder()
        workflow.add_node(
            "SQLDatabaseNode",
            "record_migration",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": query,
                "params": [
                    migration.migration_id,
                    migration.name,
                    operations_json,
                    migration.status.value,
                    migration.applied_at,
                    migration.checksum,
                    migration.duration_ms,
                ],
            },
        )

        try:
            # Phase 6: Use async_safe_run for proper event loop handling
            results, _ = async_safe_run(self.runtime.execute_async(workflow.build()))

            if results.get("record_migration", {}).get("error"):
                error_msg = results["record_migration"]["error"]
                logger.error(f"Failed to record migration: {error_msg}")
                raise Exception(f"Database error: {error_msg}")
        except Exception as e:
            logger.error(f"Failed to record migration: {e}")
            raise

    def get_migration_history(self, limit: int = 50) -> List[MigrationRecord]:
        """
        Retrieve migration history using WorkflowBuilder pattern.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of migration records ordered by applied_at
        """
        from kailash.workflow.builder import WorkflowBuilder

        from ..adapters.connection_parser import ConnectionParser

        # Get connection URL and detect database type
        connection_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        database_type = ConnectionParser.detect_database_type(connection_url)

        workflow = WorkflowBuilder()
        # Database-specific query syntax
        if database_type.lower() == "sqlite":
            history_query = """
                SELECT migration_id, name, operations, status, applied_at, checksum, duration_ms
                FROM dataflow_migration_history
                ORDER BY applied_at DESC
                LIMIT ?
            """
        else:  # PostgreSQL
            history_query = """
                SELECT migration_id, name, operations, status, applied_at, checksum, duration_ms
                FROM dataflow_migration_history
                ORDER BY applied_at DESC NULLS LAST
                LIMIT $1
            """

        workflow.add_node(
            "SQLDatabaseNode",
            "get_history",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": history_query,
                "params": [limit],
            },
        )

        try:
            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)

            if results.get("get_history", {}).get("error"):
                logger.error(
                    f"Failed to retrieve migration history: {results['get_history']['error']}"
                )
                return []

            # Extract data using the same helper method from ModelRegistry
            data = self._extract_query_data(results, "get_history")

            records = []
            if data:
                for row in data:
                    # Parse operations JSON
                    operations_data = row.get("operations", [])
                    if isinstance(operations_data, str):
                        operations = json.loads(operations_data)
                    else:
                        operations = operations_data or []

                    record = MigrationRecord(
                        migration_id=row["migration_id"],
                        name=row["name"],
                        operations=operations,
                        status=MigrationStatus(row["status"]),
                        applied_at=row.get("applied_at"),
                        checksum=row.get("checksum"),
                        duration_ms=row.get("duration_ms"),
                    )
                    records.append(record)

            return records
        except Exception as e:
            logger.error(f"Failed to retrieve migration history: {e}")
            return []

    def prepare_rollback(self, migration_id: str) -> RollbackPlan:
        """
        Generate rollback plan for specific migration using WorkflowBuilder pattern.

        Args:
            migration_id: ID of migration to rollback

        Returns:
            Complete rollback plan with steps and risk assessment
        """
        from kailash.workflow.builder import WorkflowBuilder

        from ..adapters.connection_parser import ConnectionParser

        # Get connection URL and detect database type
        connection_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        database_type = ConnectionParser.detect_database_type(connection_url)

        workflow = WorkflowBuilder()
        # Database-specific query syntax
        if database_type.lower() == "sqlite":
            migration_query = """
                SELECT migration_id, name, operations, status, applied_at, checksum
                FROM dataflow_migration_history
                WHERE migration_id = ?
            """
        else:  # PostgreSQL
            migration_query = """
                SELECT migration_id, name, operations, status, applied_at, checksum
                FROM dataflow_migration_history
                WHERE migration_id = $1
            """

        workflow.add_node(
            "SQLDatabaseNode",
            "get_migration",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": migration_query,
                "params": [migration_id],
            },
        )

        try:
            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)

            if results.get("get_migration", {}).get("error"):
                error_msg = results["get_migration"]["error"]
                logger.error(f"Failed to get migration for rollback: {error_msg}")
                raise Exception(f"Database error: {error_msg}")

            data = self._extract_query_data(results, "get_migration")
            if not data or len(data) == 0:
                raise ValueError(f"Migration {migration_id} not found")

            row = data[0]

            # Parse operations JSON
            operations_data = row.get("operations", [])
            if isinstance(operations_data, str):
                operations = json.loads(operations_data)
            else:
                operations = operations_data or []

            # Create rollback steps in reverse order
            steps = []
            total_duration = 0
            data_loss_warning = None
            requires_backup = False
            fully_reversible = True
            irreversible_operations = []

            for operation in reversed(operations):
                op_type = operation.get("type", "")
                sql_down = operation.get("sql_down", "")

                # Estimate duration based on operation type
                estimated_duration = self._estimate_operation_duration(op_type)
                total_duration += estimated_duration

                # Check if operation is reversible
                if sql_down.startswith("-- Cannot") or not sql_down:
                    fully_reversible = False
                    irreversible_operations.append(
                        f"{op_type} on {operation.get('table', 'unknown')}"
                    )
                    continue

                # Assess risk level
                risk_level = self._assess_rollback_risk(op_type)

                if risk_level in ["MEDIUM", "HIGH"]:
                    requires_backup = True
                    if not data_loss_warning:
                        data_loss_warning = (
                            "Rolling back this migration may result in data loss"
                        )

                step = RollbackStep(
                    operation_type=op_type,
                    sql=sql_down,
                    estimated_duration=estimated_duration,
                    risk_level=risk_level,
                )
                steps.append(step)

            return RollbackPlan(
                migration_id=migration_id,
                steps=steps,
                estimated_duration=total_duration,
                data_loss_warning=data_loss_warning,
                requires_backup=requires_backup,
                fully_reversible=fully_reversible,
                irreversible_operations=irreversible_operations,
            )
        except Exception as e:
            logger.error(f"Failed to prepare rollback plan: {e}")
            raise

    def _ensure_history_table(self):
        """Ensure migration history table exists using WorkflowBuilder pattern."""
        from kailash.workflow.builder import WorkflowBuilder

        from ..adapters.connection_parser import ConnectionParser

        # Get connection URL and detect database type
        connection_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        database_type = ConnectionParser.detect_database_type(connection_url)

        # Create the migration history table with database-specific SQL
        if database_type.lower() == "sqlite":
            create_table_sql = """
                CREATE TABLE IF NOT EXISTS dataflow_migration_history (
                    migration_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    operations TEXT,
                    status TEXT NOT NULL,
                    applied_at TEXT,
                    checksum TEXT,
                    duration_ms INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    CHECK (status IN ('pending', 'applied', 'failed', 'rolled_back'))
                )
            """
        elif database_type.lower() == "mysql":
            # MySQL-specific: use JSON instead of JSONB, DATETIME instead of TIMESTAMP WITH TIME ZONE
            create_table_sql = """
                CREATE TABLE IF NOT EXISTS dataflow_migration_history (
                    migration_id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    operations JSON,
                    status VARCHAR(50) NOT NULL,
                    applied_at DATETIME,
                    checksum VARCHAR(64),
                    duration_ms INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
        else:  # PostgreSQL
            create_table_sql = """
                CREATE TABLE IF NOT EXISTS dataflow_migration_history (
                    migration_id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    operations JSONB,
                    status VARCHAR(50) NOT NULL,
                    applied_at TIMESTAMP WITH TIME ZONE,
                    checksum VARCHAR(64),
                    duration_ms INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT valid_status CHECK (status IN ('pending', 'applied', 'failed', 'rolled_back'))
                )
            """

        workflow = WorkflowBuilder()
        workflow.add_node(
            "SQLDatabaseNode",
            "create_history_table",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": create_table_sql,
                "validate_queries": False,
            },
        )

        try:
            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)
            if results.get("create_history_table", {}).get("error"):
                error = results["create_history_table"]["error"]
                if "already exists" not in str(error).lower():
                    logger.error(f"Failed to create migration history table: {error}")
                    return False

            # Create indexes in separate operations
            # MySQL doesn't support CREATE INDEX IF NOT EXISTS, so use database-specific approach
            if database_type.lower() == "mysql":
                # For MySQL, simply try to create the indexes and ignore "duplicate key" errors
                status_index_sql = "CREATE INDEX idx_migration_history_status ON dataflow_migration_history(status)"
                applied_at_index_sql = "CREATE INDEX idx_migration_history_applied_at ON dataflow_migration_history(applied_at)"
            else:
                # PostgreSQL and SQLite support IF NOT EXISTS
                status_index_sql = "CREATE INDEX IF NOT EXISTS idx_migration_history_status ON dataflow_migration_history(status)"
                applied_at_index_sql = "CREATE INDEX IF NOT EXISTS idx_migration_history_applied_at ON dataflow_migration_history(applied_at)"

            workflow = WorkflowBuilder()
            workflow.add_node(
                "SQLDatabaseNode",
                "add_status_index",
                {
                    "connection_string": connection_url,
                    "database_type": database_type,
                    "query": status_index_sql,
                    "validate_queries": False,
                },
            )

            workflow.add_node(
                "SQLDatabaseNode",
                "add_applied_at_index",
                {
                    "connection_string": connection_url,
                    "database_type": database_type,
                    "query": applied_at_index_sql,
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)

            # For MySQL, ignore "duplicate key" errors when creating indexes
            for node_id in ["add_status_index", "add_applied_at_index"]:
                error = results.get(node_id, {}).get("error")
                if error:
                    error_lower = str(error).lower()
                    # Ignore duplicate index errors for MySQL
                    if (
                        "duplicate key name" in error_lower
                        or "already exists" in error_lower
                    ):
                        logger.debug(f"Index already exists (ignoring): {error}")
                    else:
                        logger.error(f"Failed to create index: {error}")
                        return False
            return True

        except Exception as e:
            logger.error(f"Failed to create migration history table: {e}")
            raise

    def _estimate_operation_duration(self, operation_type: str) -> int:
        """
        Estimate duration for rollback operations.

        Args:
            operation_type: Type of operation to estimate

        Returns:
            Estimated duration in milliseconds
        """
        duration_estimates = {
            "CREATE_TABLE": 100,
            "DROP_TABLE": 500,
            "ADD_COLUMN": 200,
            "DROP_COLUMN": 300,
            "MODIFY_COLUMN": 400,
            "CREATE_INDEX": 1000,
            "DROP_INDEX": 200,
        }

        return duration_estimates.get(operation_type, 250)

    def _assess_rollback_risk(self, operation_type: str) -> str:
        """
        Assess risk level of rollback operation.

        Args:
            operation_type: Type of operation to assess

        Returns:
            Risk level string (LOW, MEDIUM, HIGH)
        """
        risk_levels = {
            "CREATE_INDEX": "LOW",
            "DROP_INDEX": "LOW",
            "CREATE_TABLE": "LOW",
            "ADD_COLUMN": "MEDIUM",  # Rollback drops column, losing data
            "MODIFY_COLUMN": "MEDIUM",
            "DROP_COLUMN": "HIGH",  # Cannot recover dropped data
            "DROP_TABLE": "HIGH",  # Cannot recover dropped table
        }

        return risk_levels.get(operation_type, "MEDIUM")


class SchemaStateManager:
    """
    Main schema state management system integrating all components.

    Provides unified interface for schema caching, change detection,
    and migration history with high performance guarantees.

    Universal implementation supporting PostgreSQL and SQLite.
    """

    def __init__(
        self, dataflow_instance, cache_ttl: int = 300, cache_max_size: int = 100
    ):
        """
        Initialize schema state manager.

        Args:
            dataflow_instance: DataFlow instance for database access via WorkflowBuilder
            cache_ttl: Cache time-to-live in seconds
            cache_max_size: Maximum cache size
        """
        self.dataflow = dataflow_instance
        self.cache = SchemaCache(ttl=cache_ttl, max_size=cache_max_size)
        self.change_detector = SchemaChangeDetector()
        self.history_manager = MigrationHistoryManager(dataflow_instance)

    def _extract_query_data(
        self, results: Dict[str, Any], node_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Extract data from query results, handling different result structures."""
        node_result = results.get(node_id, {})

        # Check for result.data structure (newer format)
        if "result" in node_result and "data" in node_result["result"]:
            return node_result["result"]["data"]

        # Check for direct data structure (older format)
        if "data" in node_result:
            return node_result["data"]

        # Check for result as list
        if "result" in node_result and isinstance(node_result["result"], list):
            return node_result["result"]

        return None

    def get_cached_or_fresh_schema(self, connection_id: str) -> DatabaseSchema:
        """
        Get schema from cache or fetch fresh if needed.

        Args:
            connection_id: Database connection identifier

        Returns:
            Database schema (cached or fresh)
        """
        # Try cache first with error handling
        try:
            cached_schema = self.cache.get_cached_schema(connection_id)
            if cached_schema:
                return cached_schema
        except Exception as e:
            logger.warning(f"Cache error for connection {connection_id}: {e}")
            # Continue to fetch fresh schema

        # Fetch fresh schema (this would integrate with existing schema inspection)
        fresh_schema = self._fetch_fresh_schema()

        # Try to cache for future use (with error handling)
        try:
            self.cache.cache_schema(connection_id, fresh_schema)
        except Exception as e:
            logger.warning(
                f"Failed to cache schema for connection {connection_id}: {e}"
            )
            # Continue without caching

        return fresh_schema

    def detect_and_plan_migrations(
        self, model_schema: ModelSchema, connection_id: str
    ) -> Tuple[List[MigrationOperation], SafetyAssessment]:
        """
        Detect changes and plan migrations with safety assessment.

        Args:
            model_schema: Current model schema
            connection_id: Database connection identifier

        Returns:
            Tuple of (migration operations, safety assessment)
        """
        # Get current database schema
        db_schema = self.get_cached_or_fresh_schema(connection_id)

        # Compare schemas with incremental mode support
        comparison = self.change_detector.compare_schemas(
            model_schema, db_schema, incremental_mode=True
        )

        # Generate migration operations
        operations = self.change_detector.detect_required_migrations(comparison)

        # Assess safety
        safety = self.change_detector.validate_migration_safety(operations)

        return operations, safety

    def _fetch_fresh_schema(self) -> DatabaseSchema:
        """
        Fetch fresh schema using WorkflowBuilder pattern.

        Uses database-specific schema introspection queries.
        """
        from kailash.workflow.builder import WorkflowBuilder

        from ..adapters.connection_parser import ConnectionParser

        try:
            # Get connection URL and detect database type
            connection_url = self.dataflow.config.database.get_connection_url(
                self.dataflow.config.environment
            )
            database_type = ConnectionParser.detect_database_type(connection_url)

            # Get database-specific schema query
            if database_type.lower() == "sqlite":
                schema_query = """
                    SELECT
                        m.name as table_name,
                        p.name as column_name,
                        p.type as data_type,
                        CASE WHEN p."notnull" = 0 THEN 'YES' ELSE 'NO' END as is_nullable,
                        p.dflt_value as column_default,
                        CASE WHEN p.pk = 1 THEN true ELSE false END as is_primary_key
                    FROM sqlite_master m
                    JOIN pragma_table_info(m.name) p
                    WHERE m.type = 'table'
                      AND m.name NOT LIKE 'sqlite_%'
                      AND m.name NOT LIKE 'dataflow_%'
                    ORDER BY m.name, p.cid
                """
            else:  # PostgreSQL
                schema_query = """
                    SELECT
                        t.table_name,
                        c.column_name,
                        c.data_type,
                        c.is_nullable,
                        c.column_default,
                        CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key
                    FROM information_schema.tables t
                    LEFT JOIN information_schema.columns c ON t.table_name = c.table_name
                    LEFT JOIN (
                        SELECT ku.column_name, ku.table_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage ku ON tc.constraint_name = ku.constraint_name
                        WHERE tc.constraint_type = 'PRIMARY KEY'
                    ) pk ON c.table_name = pk.table_name AND c.column_name = pk.column_name
                    WHERE t.table_schema = 'public'
                      AND t.table_type = 'BASE TABLE'
                      AND t.table_name NOT LIKE 'dataflow_%'
                    ORDER BY t.table_name, c.ordinal_position
                """

            workflow = WorkflowBuilder()
            workflow.add_node(
                "SQLDatabaseNode",
                "get_schema",
                {
                    "connection_string": connection_url,
                    "database_type": database_type,
                    "query": schema_query,
                },
            )

            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            logger.debug("_fetch_fresh_schema: Using async-safe workflow execution")
            results, _ = _execute_workflow_safe(workflow)

            if results.get("get_schema", {}).get("error"):
                logger.error(
                    f"Failed to fetch schema: {results['get_schema']['error']}"
                )
                return DatabaseSchema()

            data = self._extract_query_data(results, "get_schema")
            tables = {}

            if data:
                current_table = None
                for row in data:
                    table_name = row.get("table_name")
                    if table_name and table_name != current_table:
                        tables[table_name] = {"columns": {}}
                        current_table = table_name

                    column_name = row.get("column_name")
                    if column_name:  # column_name exists
                        tables[table_name]["columns"][column_name] = {
                            "type": row.get("data_type"),
                            "nullable": row.get("is_nullable") == "YES",
                            "default": row.get("column_default"),
                            "primary_key": row.get("is_primary_key", False),
                        }

            return DatabaseSchema(tables=tables)

        except Exception as e:
            logger.error(f"Failed to fetch schema: {e}")
            # Return empty schema on error
            return DatabaseSchema()

    # Transaction management is handled by WorkflowBuilder pattern
    # No direct transaction context managers needed
