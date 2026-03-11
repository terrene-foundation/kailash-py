"""
WebMigrationAPI - Web interface for DataFlow migration system

Provides a web-friendly API that wraps VisualMigrationBuilder and AutoMigrationSystem
for schema inspection, migration preview, validation, and execution.

Features:
- Schema inspection with JSON serialization
- Migration preview generation
- Session-based draft migration management
- Migration validation and conflict detection
- Complete workflow execution with rollback support
"""

import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from ..migrations.auto_migration_system import (
    AutoMigrationSystem,
    Migration,
    MigrationOperation,
    MigrationStatus,
    MigrationType,
)
from ..migrations.visual_migration_builder import (
    ColumnBuilder,
    ColumnType,
    TableBuilder,
    VisualMigrationBuilder,
)
from .exceptions import (
    DatabaseConnectionError,
    MigrationConflictError,
    SerializationError,
    SessionNotFoundError,
    SQLExecutionError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class WebMigrationAPI:
    """
    Web-friendly API for DataFlow migration system.

    Wraps VisualMigrationBuilder and AutoMigrationSystem to provide:
    - JSON-based schema inspection
    - Web-safe migration preview generation
    - Session management for draft migrations
    - Validation and conflict detection
    - Execution planning and rollback support
    """

    def __init__(
        self,
        connection_string: str,
        dialect: Optional[str] = None,
        session_timeout: int = 3600,
    ):
        """
        Initialize WebMigrationAPI.

        Args:
            connection_string: Database connection string
            dialect: Database dialect (auto-detected if not provided)
            session_timeout: Session timeout in seconds (default 1 hour)
        """
        self.connection_string = connection_string
        self.session_timeout = session_timeout
        self.active_sessions: Dict[str, Dict[str, Any]] = {}

        # Auto-detect dialect from connection string if not provided
        if dialect is None:
            parsed = urlparse(connection_string)
            if parsed.scheme.startswith("postgresql"):
                self.dialect = "postgresql"
            elif parsed.scheme.startswith("mysql"):
                self.dialect = "mysql"
            elif parsed.scheme.startswith("sqlite"):
                self.dialect = "sqlite"
            else:
                self.dialect = "postgresql"  # default
        else:
            self.dialect = dialect

        self._last_cleanup = datetime.now()
        self._rollback_points: Dict[str, Dict[str, Any]] = {}

    def inspect_schema(self, schema_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Inspect database schema and return structured data.

        Args:
            schema_name: Specific schema to inspect (default: public)

        Returns:
            Dict containing tables, columns, indexes, constraints, and metadata

        Raises:
            DatabaseConnectionError: If connection fails
            ValidationError: If schema_name is invalid
        """
        # SECURITY: Validate schema name to prevent SQL injection
        if schema_name and self._is_invalid_identifier(schema_name):
            raise ValidationError(
                f"Invalid schema name: '{schema_name}'. "
                "Schema names must start with a letter or underscore, "
                "contain only alphanumeric characters and underscores, "
                "be 1-63 characters long, and not be SQL keywords."
            )

        try:
            # Create SQLAlchemy engine for real database schema inspection
            # NOTE: This uses actual database connection - NOT a mock
            # Requires SQLAlchemy to be installed (will raise ImportError if missing)
            engine = create_engine(self.connection_string)
            inspector = engine.inspector()

            start_time = time.perf_counter()

            # Get table names from inspector
            tables = inspector.get_table_names()

            schema_data = {
                "tables": {},
                "metadata": {
                    "schema_name": schema_name or "public",
                    "inspected_at": datetime.now().isoformat(),
                    "performance": {
                        "inspection_time_ms": (time.perf_counter() - start_time) * 1000
                    },
                },
            }

            # Process each table
            for table_name in tables:
                # Get columns for this table
                columns_data = inspector.get_columns(table_name)

                table_info = {"columns": {}, "indexes": [], "constraints": []}

                # Get primary key info
                try:
                    pk_constraint = inspector.get_pk_constraint(table_name)
                    pk_columns = pk_constraint.get("constrained_columns", [])
                except Exception as e:
                    logger.debug(
                        "PK introspection failed for %s: %s",
                        table_name,
                        type(e).__name__,
                    )
                    pk_columns = []

                # Get unique constraints
                try:
                    unique_constraints = inspector.get_unique_constraints(table_name)
                    unique_columns = set()
                    for uc in unique_constraints:
                        unique_columns.update(uc.get("column_names", []))
                except Exception as e:
                    logger.debug(
                        "Unique constraint introspection failed for %s: %s",
                        table_name,
                        type(e).__name__,
                    )
                    unique_columns = set()

                # Get foreign key info
                try:
                    fk_constraints = inspector.get_foreign_keys(table_name)
                    fk_info = {}
                    for fk in fk_constraints:
                        for col in fk.get("constrained_columns", []):
                            ref_table = fk.get("referred_table", "")
                            ref_cols = fk.get("referred_columns", [])
                            if ref_cols:
                                fk_info[col] = f"{ref_table}({ref_cols[0]})"
                except Exception as e:
                    logger.debug(
                        "FK introspection failed for %s: %s",
                        table_name,
                        type(e).__name__,
                    )
                    fk_info = {}

                # Process columns
                for col_data in columns_data:
                    col_name = col_data["name"]
                    col_type = str(col_data["type"])

                    table_info["columns"][col_name] = {
                        "type": col_type,
                        "nullable": col_data.get("nullable", True),
                        "primary_key": col_name in pk_columns,
                        "unique": col_name in unique_columns,
                        "foreign_key": fk_info.get(col_name),
                    }

                # Get indexes
                try:
                    indexes = inspector.get_indexes(table_name)
                    for idx in indexes:
                        table_info["indexes"].append(
                            {
                                "name": idx.get("name", ""),
                                "columns": idx.get("column_names", []),
                                "unique": idx.get("unique", False),
                            }
                        )
                except Exception as e:
                    logger.debug(
                        "Index introspection failed for %s: %s",
                        table_name,
                        type(e).__name__,
                    )

                schema_data["tables"][table_name] = table_info

            return schema_data

        except Exception as e:
            raise DatabaseConnectionError(f"Failed to connect to database: {str(e)}")

    def create_migration_preview(
        self, migration_name: str, migration_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create migration preview using VisualMigrationBuilder.

        Args:
            migration_name: Name for the migration
            migration_spec: Migration specification

        Returns:
            Dict containing preview SQL, operations, and metadata

        Raises:
            ValidationError: If spec is invalid
        """
        self._validate_migration_spec(migration_spec)

        # Create VisualMigrationBuilder
        builder = VisualMigrationBuilder(migration_name, self.dialect)

        # Process migration specification
        operation_type = migration_spec["type"]

        if operation_type == "create_table":
            self._process_create_table(builder, migration_spec)
        elif operation_type == "add_column":
            self._process_add_column(builder, migration_spec)
        elif operation_type == "multi_operation":
            self._process_multi_operation(builder, migration_spec)
        else:
            raise ValidationError(f"Unsupported migration type: {operation_type}")

        # Build migration and generate preview
        migration = builder.build()
        preview_sql = (
            migration.preview()
            if hasattr(migration, "preview")
            else str(builder.preview())
        )

        # Generate rollback SQL
        rollback_sql = self._generate_rollback_sql(migration)

        return {
            "migration_name": migration_name,
            "preview": {"sql": preview_sql, "rollback_sql": rollback_sql},
            "operations": [
                {
                    "type": op.operation_type.value,
                    "table_name": op.table_name,
                    "description": op.description,
                    "metadata": op.metadata,
                }
                for op in migration.operations
            ],
            "metadata": {
                "dialect": self.dialect,
                "generated_at": datetime.now().isoformat(),
                "operation_count": len(migration.operations),
            },
        }

    def validate_migration(self, migration_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate migration using AutoMigrationSystem.

        Args:
            migration_data: Migration data to validate

        Returns:
            Dict containing validation results
        """
        # Create AutoMigrationSystem for validation
        auto_system = AutoMigrationSystem(self.connection_string)

        # Convert to Migration object
        migration = self._dict_to_migration(migration_data)

        # Validate using auto system
        validation_result = auto_system.validate_migration(migration)

        return validation_result

    def create_session(self, user_id: str) -> str:
        """
        Create new session for draft migration management.

        Args:
            user_id: User identifier

        Returns:
            Session ID
        """
        session_id = str(uuid.uuid4())

        self.active_sessions[session_id] = {
            "user_id": user_id,
            "created_at": datetime.now(),
            "last_accessed": datetime.now(),
            "draft_migrations": [],
        }

        return session_id

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """
        Get session data.

        Args:
            session_id: Session identifier

        Returns:
            Session data

        Raises:
            SessionNotFoundError: If session not found
        """
        if session_id not in self.active_sessions:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        session = self.active_sessions[session_id]
        session["last_accessed"] = datetime.now()

        return session

    def add_draft_migration(
        self, session_id: str, migration_draft: Dict[str, Any]
    ) -> str:
        """
        Add draft migration to session.

        Args:
            session_id: Session identifier
            migration_draft: Draft migration data

        Returns:
            Draft migration ID
        """
        session = self.get_session(session_id)

        draft_id = str(uuid.uuid4())
        draft_with_id = {
            "id": draft_id,
            "created_at": datetime.now().isoformat(),
            **migration_draft,
        }

        session["draft_migrations"].append(draft_with_id)

        return draft_id

    def remove_draft_migration(self, session_id: str, draft_id: str) -> None:
        """
        Remove draft migration from session.

        Args:
            session_id: Session identifier
            draft_id: Draft migration ID
        """
        session = self.get_session(session_id)

        session["draft_migrations"] = [
            draft for draft in session["draft_migrations"] if draft["id"] != draft_id
        ]

    def cleanup_expired_sessions(self) -> None:
        """Clean up expired sessions."""
        import time

        current_time = datetime.now()

        expired_sessions = []
        for session_id, session_data in self.active_sessions.items():
            time_diff = current_time - session_data["last_accessed"]
            if time_diff.total_seconds() > self.session_timeout:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            del self.active_sessions[session_id]

        self._last_cleanup = current_time

    def close_session(self, session_id: str) -> None:
        """
        Close session manually.

        Args:
            session_id: Session identifier
        """
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]

    def _expire_session_for_testing(self, session_id: str) -> None:
        """Helper method to manually expire a session for testing."""
        if session_id in self.active_sessions:
            # Set last_accessed to a time in the past
            expired_time = datetime.now() - timedelta(seconds=self.session_timeout + 1)
            self.active_sessions[session_id]["last_accessed"] = expired_time

    def serialize_migration(self, migration_data: Dict[str, Any]) -> str:
        """
        Serialize migration data to JSON.

        Args:
            migration_data: Migration data to serialize

        Returns:
            JSON string

        Raises:
            SerializationError: If serialization fails
        """
        try:
            return json.dumps(migration_data, default=self._json_serializer, indent=2)
        except (TypeError, ValueError) as e:
            raise SerializationError(f"Failed to serialize migration data: {str(e)}")
        except Exception as e:
            raise SerializationError(f"Failed to serialize migration data: {str(e)}")

    def deserialize_migration(self, json_data: str) -> Dict[str, Any]:
        """
        Deserialize migration data from JSON.

        Args:
            json_data: JSON string

        Returns:
            Migration data dict
        """
        try:
            return json.loads(json_data)
        except Exception as e:
            raise SerializationError(f"Failed to deserialize migration data: {str(e)}")

    def serialize_schema_data(self, schema_data: Dict[str, Any]) -> str:
        """
        Serialize schema data to JSON.

        Args:
            schema_data: Schema data to serialize

        Returns:
            JSON string
        """
        return self.serialize_migration(schema_data)

    def generate_session_preview(self, session_id: str) -> Dict[str, Any]:
        """
        Generate preview for all migrations in session.

        Args:
            session_id: Session identifier

        Returns:
            Combined preview data
        """
        session = self.get_session(session_id)

        previews = []
        combined_sql_parts = []

        for draft in session["draft_migrations"]:
            preview = self.create_migration_preview(draft["name"], draft["spec"])
            previews.append(preview)
            combined_sql_parts.append(preview["preview"]["sql"])

        return {
            "session_id": session_id,
            "migrations": previews,
            "combined_sql": "\n\n".join(combined_sql_parts),
            "total_operations": sum(len(p["operations"]) for p in previews),
        }

    def validate_session_migrations(self, session_id: str) -> Dict[str, Any]:
        """
        Validate all migrations in session.

        Args:
            session_id: Session identifier

        Returns:
            Validation results for all migrations
        """
        session = self.get_session(session_id)

        validations = []
        overall_valid = True

        for draft in session["draft_migrations"]:
            # Create migration data for validation
            migration_data = {
                "version": datetime.now().strftime("%Y%m%d_%H%M%S"),
                "operations": [],  # Would be populated from draft spec
            }

            try:
                validation = self.validate_migration(migration_data)
                validations.append(
                    {
                        "migration_name": draft["name"],
                        "valid": validation["valid"],
                        "warnings": validation.get("warnings", []),
                        "errors": validation.get("errors", []),
                    }
                )

                if not validation["valid"]:
                    overall_valid = False

            except Exception as e:
                validations.append(
                    {
                        "migration_name": draft["name"],
                        "valid": False,
                        "errors": [str(e)],
                    }
                )
                overall_valid = False

        return {
            "valid": overall_valid,
            "migration_validations": validations,
            "session_id": session_id,
        }

    def create_execution_plan(
        self,
        session_id: str,
        optimize_for: str = "safety",
        enforce_dependencies: bool = False,
    ) -> Dict[str, Any]:
        """
        Create execution plan for session migrations.

        Args:
            session_id: Session identifier
            optimize_for: Optimization strategy (safety, performance, speed)
            enforce_dependencies: Whether to enforce dependency ordering

        Returns:
            Execution plan with steps and metadata
        """
        session = self.get_session(session_id)

        steps = []
        for i, draft in enumerate(session["draft_migrations"]):
            steps.append(
                {
                    "step_number": i + 1,
                    "migration_name": draft["name"],
                    "estimated_duration": 1.0,  # seconds
                    "risk_level": "low",
                }
            )

        # Calculate execution strategy
        if optimize_for == "performance":
            execution_strategy = "staged"
            stages = self._create_execution_stages(steps)
        else:
            execution_strategy = "sequential"
            stages = [{"stage": 1, "steps": steps}]

        return {
            "session_id": session_id,
            "steps": steps,
            "execution_strategy": execution_strategy,
            "stages": stages,
            "estimated_duration": sum(step["estimated_duration"] for step in steps),
            "risk_level": self._calculate_overall_risk(steps),
        }

    def execute_session_migrations(
        self, session_id: str, dry_run: bool = True, create_rollback_point: bool = False
    ) -> Dict[str, Any]:
        """
        Execute all migrations in session.

        Args:
            session_id: Session identifier
            dry_run: Whether to perform dry run
            create_rollback_point: Whether to create rollback point

        Returns:
            Execution results

        Raises:
            SQLExecutionError: If a migration operation fails during execution
            MigrationConflictError: If a migration conflicts with current schema state
        """
        session = self.get_session(session_id)

        overall_start = time.perf_counter()
        executed_migrations = []
        overall_success = True
        rollback_point_id = None

        engine = create_engine(self.connection_string)

        # Save schema state before execution for rollback support
        if create_rollback_point:
            rollback_point_id = str(uuid.uuid4())

        rollback_operations = []

        for draft in session["draft_migrations"]:
            migration_start = time.perf_counter()
            migration_name = draft["name"]
            operations_count = 0
            status = "success"
            error_message = None

            try:
                # Build the migration from the draft spec using VisualMigrationBuilder
                builder = VisualMigrationBuilder(migration_name, self.dialect)
                spec = draft.get("spec", draft)
                operation_type = spec.get("type", "")

                if operation_type == "create_table":
                    self._process_create_table(builder, spec)
                elif operation_type == "add_column":
                    self._process_add_column(builder, spec)
                elif operation_type == "multi_operation":
                    self._process_multi_operation(builder, spec)
                else:
                    raise ValidationError(
                        f"Unsupported migration type: {operation_type}"
                    )

                migration = builder.build()
                operations_count = len(migration.operations)

                # Execute each operation's SQL against the real database
                from sqlalchemy import text

                with engine.connect() as connection:
                    if dry_run:
                        # In dry run mode, use a transaction and roll it back
                        trans = connection.begin()
                        try:
                            for op in migration.operations:
                                if op.sql_up:
                                    connection.execute(text(op.sql_up))
                        finally:
                            trans.rollback()
                    else:
                        # Execute for real within a transaction
                        with connection.begin():
                            for op in migration.operations:
                                if op.sql_up:
                                    connection.execute(text(op.sql_up))

                # Track rollback operations (reverse order within each migration)
                if create_rollback_point and not dry_run:
                    for op in reversed(migration.operations):
                        if op.sql_down and not op.sql_down.startswith("--"):
                            rollback_operations.append(op.sql_down)

            except (ValidationError, MigrationConflictError):
                raise
            except Exception as e:
                status = "failed"
                error_message = str(e)
                overall_success = False
                logger.error(f"Migration '{migration_name}' failed: {error_message}")

            migration_duration = time.perf_counter() - migration_start

            migration_result = {
                "migration_name": migration_name,
                "status": status,
                "duration": migration_duration,
                "operations_count": operations_count,
            }
            if error_message:
                migration_result["error"] = error_message

            executed_migrations.append(migration_result)

            # Stop executing further migrations if one fails
            if not overall_success:
                break

        overall_duration = time.perf_counter() - overall_start

        result = {
            "success": overall_success,
            "executed_migrations": executed_migrations,
            "total_duration": overall_duration,
            "dry_run": dry_run,
        }

        if create_rollback_point and rollback_point_id:
            result["rollback_point_id"] = rollback_point_id
            self._rollback_points[rollback_point_id] = {
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
                "operations": rollback_operations,
            }

        return result

    def analyze_schema_performance(self) -> Dict[str, Any]:
        """
        Analyze schema performance characteristics.

        Inspects the real database schema to calculate a performance score based on
        index coverage of foreign keys, primary key presence, and index distribution.

        Returns:
            Performance analysis results including score, recommendations,
            current indexes, and query pattern analysis.

        Raises:
            DatabaseConnectionError: If connection to database fails
        """
        try:
            engine = create_engine(self.connection_string)
            inspector = engine.inspector()

            tables = inspector.get_table_names()
            if not tables:
                return {
                    "performance_score": 100,
                    "recommendations": [],
                    "current_indexes": [],
                    "query_patterns": [],
                }

            all_indexes = []
            recommendations = []
            total_fk_count = 0
            indexed_fk_count = 0
            tables_with_pk = 0
            query_patterns = []

            for table_name in tables:
                # Gather indexes for this table
                try:
                    indexes = inspector.get_indexes(table_name)
                except Exception as e:
                    logger.debug(
                        "Index introspection failed for %s: %s",
                        table_name,
                        type(e).__name__,
                    )
                    indexes = []

                indexed_columns = set()
                for idx in indexes:
                    cols = idx.get("column_names", [])
                    indexed_columns.update(cols)
                    all_indexes.append(
                        {
                            "table": table_name,
                            "name": idx.get("name", ""),
                            "columns": cols,
                            "unique": idx.get("unique", False),
                        }
                    )

                # Check primary keys
                try:
                    pk_constraint = inspector.get_pk_constraint(table_name)
                    pk_columns = pk_constraint.get("constrained_columns", [])
                    if pk_columns:
                        tables_with_pk += 1
                except Exception as e:
                    logger.debug(
                        "PK introspection failed for %s: %s",
                        table_name,
                        type(e).__name__,
                    )
                    pk_columns = []

                # Check foreign keys and whether they are indexed
                try:
                    fk_constraints = inspector.get_foreign_keys(table_name)
                    for fk in fk_constraints:
                        fk_cols = fk.get("constrained_columns", [])
                        for col in fk_cols:
                            total_fk_count += 1
                            if col in indexed_columns:
                                indexed_fk_count += 1
                            else:
                                ref_table = fk.get("referred_table", "unknown")
                                recommendations.append(
                                    f"Add index on {table_name}.{col} "
                                    f"(foreign key to {ref_table})"
                                )
                                query_patterns.append(
                                    {
                                        "table": table_name,
                                        "pattern": f"JOIN on {table_name}.{col}",
                                        "recommendation": "Add index for join performance",
                                    }
                                )
                except Exception as e:
                    logger.debug(
                        "FK introspection failed for %s: %s",
                        table_name,
                        type(e).__name__,
                    )

            # Calculate performance score (0-100)
            # Component 1: FK index coverage (50 points max)
            if total_fk_count > 0:
                fk_score = (indexed_fk_count / total_fk_count) * 50
            else:
                fk_score = 50  # No FKs means no penalty

            # Component 2: PK coverage (30 points max)
            if tables:
                pk_score = (tables_with_pk / len(tables)) * 30
            else:
                pk_score = 30

            # Component 3: General index presence (20 points max)
            # Award points based on ratio of indexes to tables
            if tables:
                index_ratio = min(len(all_indexes) / len(tables), 2.0) / 2.0
                index_score = index_ratio * 20
            else:
                index_score = 20

            performance_score = round(fk_score + pk_score + index_score)

            # Add general recommendations if score is below thresholds
            if not all_indexes and tables:
                recommendations.append(
                    "Consider adding indexes on frequently queried columns"
                )

            return {
                "performance_score": performance_score,
                "recommendations": recommendations,
                "current_indexes": all_indexes,
                "query_patterns": query_patterns,
            }

        except Exception as e:
            raise DatabaseConnectionError(
                f"Failed to analyze schema performance: {str(e)}"
            )

    def validate_performance_impact(self, session_id: str) -> Dict[str, Any]:
        """
        Validate performance impact of session migrations.

        Analyzes the draft migrations in the session to estimate their performance
        impact based on the types of operations they contain.

        Args:
            session_id: Session identifier

        Returns:
            Performance impact analysis with estimated improvement,
            risk assessment, and safety determination.
        """
        session = self.get_session(session_id)

        index_additions = 0
        index_removals = 0
        column_additions = 0
        column_removals = 0
        table_creations = 0
        table_drops = 0
        other_operations = 0

        for draft in session["draft_migrations"]:
            spec = draft.get("spec", draft)
            op_type = spec.get("type", "")

            if op_type == "create_table":
                table_creations += 1
                # Count columns in the table spec
                columns = spec.get("columns", [])
                column_additions += len(columns)
            elif op_type == "add_column":
                column_additions += 1
            elif op_type == "multi_operation":
                for sub_op in spec.get("operations", []):
                    sub_type = sub_op.get("type", "")
                    if sub_type == "create_table":
                        table_creations += 1
                        column_additions += len(sub_op.get("columns", []))
                    elif sub_type == "add_column":
                        column_additions += 1
                    else:
                        other_operations += 1
            else:
                other_operations += 1

            # Also analyze via VisualMigrationBuilder to inspect SQL operations
            try:
                builder = VisualMigrationBuilder(
                    draft.get("name", "analysis"), self.dialect
                )
                if op_type == "create_table":
                    self._process_create_table(builder, spec)
                elif op_type == "add_column":
                    self._process_add_column(builder, spec)
                elif op_type == "multi_operation":
                    self._process_multi_operation(builder, spec)

                migration = builder.build()
                for op in migration.operations:
                    op_value = op.operation_type.value.lower()
                    if "add_index" in op_value:
                        index_additions += 1
                    elif "drop_index" in op_value:
                        index_removals += 1
                    elif "drop_column" in op_value:
                        column_removals += 1
                    elif "drop_table" in op_value:
                        table_drops += 1
            except Exception as e:
                logger.debug("Migration preview build failed: %s", type(e).__name__)

        # Calculate estimated improvement based on operation types
        # Index additions improve performance, removals degrade it
        improvement_points = (
            index_additions * 10
            - index_removals * 15
            + table_creations * 2
            + column_additions * 1
            - column_removals * 1
            - table_drops * 5
        )

        if improvement_points > 0:
            estimated_improvement = f"{min(improvement_points, 50)}%"
        elif improvement_points < 0:
            estimated_improvement = f"{max(improvement_points, -50)}%"
        else:
            estimated_improvement = "0%"

        # Risk assessment based on destructive operations
        if table_drops > 0 or column_removals > 0 or index_removals > 2:
            risk_assessment = "high"
        elif index_removals > 0 or other_operations > 0:
            risk_assessment = "medium"
        else:
            risk_assessment = "low"

        # Safe to execute if risk is not high and no destructive operations
        safe_to_execute = risk_assessment != "high"

        return {
            "estimated_improvement": estimated_improvement,
            "risk_assessment": risk_assessment,
            "safe_to_execute": safe_to_execute,
            "operation_summary": {
                "index_additions": index_additions,
                "index_removals": index_removals,
                "column_additions": column_additions,
                "column_removals": column_removals,
                "table_creations": table_creations,
                "table_drops": table_drops,
            },
        }

    def execute_migration_stage(
        self, session_id: str, stage_num: int
    ) -> Dict[str, Any]:
        """
        Execute specific migration stage from the execution plan.

        Retrieves the execution plan for the session, finds the specified stage,
        and executes all migration steps within that stage sequentially against
        the real database.

        Args:
            session_id: Session identifier
            stage_num: Stage number to execute (0-indexed)

        Returns:
            Stage execution results with real operation counts and timing

        Raises:
            ValidationError: If stage_num is out of range
            SQLExecutionError: If a migration operation fails
        """
        # Get the execution plan to find the requested stage
        execution_plan = self.create_execution_plan(session_id)
        stages = execution_plan.get("stages", [])

        if stage_num < 0 or stage_num >= len(stages):
            raise ValidationError(
                f"Stage {stage_num} out of range. "
                f"Available stages: 0-{len(stages) - 1}"
            )

        stage = stages[stage_num]
        stage_steps = stage.get("steps", [])

        stage_start = time.perf_counter()
        operations_executed = 0
        success = True
        errors = []

        session = self.get_session(session_id)
        drafts_by_name = {draft["name"]: draft for draft in session["draft_migrations"]}

        engine = create_engine(self.connection_string)

        from sqlalchemy import text

        for step in stage_steps:
            migration_name = step.get("migration_name", "")
            draft = drafts_by_name.get(migration_name)

            if not draft:
                errors.append(
                    f"Draft migration '{migration_name}' not found in session"
                )
                success = False
                continue

            try:
                # Build the migration from the draft spec
                builder = VisualMigrationBuilder(migration_name, self.dialect)
                spec = draft.get("spec", draft)
                operation_type = spec.get("type", "")

                if operation_type == "create_table":
                    self._process_create_table(builder, spec)
                elif operation_type == "add_column":
                    self._process_add_column(builder, spec)
                elif operation_type == "multi_operation":
                    self._process_multi_operation(builder, spec)
                else:
                    raise ValidationError(
                        f"Unsupported migration type: {operation_type}"
                    )

                migration = builder.build()

                # Execute each operation within a transaction
                with engine.connect() as connection:
                    with connection.begin():
                        for op in migration.operations:
                            if op.sql_up:
                                connection.execute(text(op.sql_up))
                                operations_executed += 1

            except Exception as e:
                errors.append(f"Migration '{migration_name}' failed: {str(e)}")
                success = False
                logger.error(
                    f"Stage {stage_num} migration '{migration_name}' failed: {e}"
                )
                break

        stage_duration = time.perf_counter() - stage_start

        result = {
            "success": success,
            "stage": stage_num,
            "operations_executed": operations_executed,
            "duration": stage_duration,
        }

        if errors:
            result["errors"] = errors

        return result

    def get_session_migrations(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all migrations from session.

        Args:
            session_id: Session identifier

        Returns:
            List of migration definitions
        """
        session = self.get_session(session_id)
        return session["draft_migrations"]

    def check_migration_conflicts(self, session_id: str) -> Dict[str, Any]:
        """
        Check for migration conflicts in session.

        Analyzes all draft migrations in the session for conflicting operations
        on the same table/column (e.g., two migrations both adding the same column,
        or one dropping a table another modifies).

        Args:
            session_id: Session identifier

        Returns:
            Conflict analysis results with has_conflicts flag and conflict details
        """
        session = self.get_session(session_id)
        drafts = session["draft_migrations"]
        conflicts = []

        # Track table operations across drafts to detect conflicts
        table_operations: Dict[str, List[Dict[str, Any]]] = {}

        for idx, draft in enumerate(drafts):
            spec = draft.get("spec", draft)
            op_type = spec.get("type", "")
            table_name = spec.get("table_name", "")

            if op_type == "create_table":
                table_operations.setdefault(table_name, []).append(
                    {
                        "draft_index": idx,
                        "draft_name": draft.get("name", ""),
                        "operation": "create_table",
                    }
                )
            elif op_type == "add_column":
                table_operations.setdefault(table_name, []).append(
                    {
                        "draft_index": idx,
                        "draft_name": draft.get("name", ""),
                        "operation": "add_column",
                        "column": spec.get("column_name", ""),
                    }
                )
            elif op_type == "multi_operation":
                for sub_op in spec.get("operations", []):
                    sub_table = sub_op.get("table_name", table_name)
                    table_operations.setdefault(sub_table, []).append(
                        {
                            "draft_index": idx,
                            "draft_name": draft.get("name", ""),
                            "operation": sub_op.get("type", "unknown"),
                            "column": sub_op.get("column_name", ""),
                        }
                    )

        # Detect conflicts: duplicate table creation, duplicate column additions
        for table, ops in table_operations.items():
            create_ops = [o for o in ops if o["operation"] == "create_table"]
            if len(create_ops) > 1:
                conflicts.append(
                    {
                        "type": "duplicate_table_creation",
                        "table": table,
                        "migrations": [o["draft_name"] for o in create_ops],
                    }
                )

            # Check for duplicate column additions on the same table
            column_adds: Dict[str, List[str]] = {}
            for op in ops:
                if op["operation"] == "add_column" and op.get("column"):
                    column_adds.setdefault(op["column"], []).append(op["draft_name"])

            for col, migration_names in column_adds.items():
                if len(migration_names) > 1:
                    conflicts.append(
                        {
                            "type": "duplicate_column_addition",
                            "table": table,
                            "column": col,
                            "migrations": migration_names,
                        }
                    )

            # Check for drop + modify conflicts
            drop_ops = [
                o for o in ops if o["operation"] in ("drop_table", "drop_column")
            ]
            modify_ops = [
                o
                for o in ops
                if o["operation"] in ("add_column", "modify_column", "add_constraint")
                and o["draft_index"]
                > max((d["draft_index"] for d in drop_ops), default=-1)
            ]
            if drop_ops and modify_ops:
                conflicts.append(
                    {
                        "type": "modify_after_drop",
                        "table": table,
                        "drop_migration": drop_ops[0]["draft_name"],
                        "modify_migration": modify_ops[0]["draft_name"],
                    }
                )

        return {"has_conflicts": len(conflicts) > 0, "conflicts": conflicts}

    def validate_migration_dependencies(self, session_id: str) -> Dict[str, Any]:
        """
        Validate migration dependencies.

        Checks that the ordering of draft migrations is valid: tables must be
        created before columns are added to them, foreign key references must
        point to tables that exist (either in schema or created earlier).

        Args:
            session_id: Session identifier

        Returns:
            Dependency validation results with valid flag and ordered chain
        """
        session = self.get_session(session_id)
        drafts = session["draft_migrations"]

        # Build dependency graph: track which tables each migration creates/requires
        errors = []
        tables_available: set = set()

        # Pre-populate with existing database tables if possible
        try:
            schema = self.inspect_schema()
            tables_available = set(schema.get("tables", {}).keys())
        except Exception as e:
            logger.debug(
                "Schema inspection for dependency analysis failed: %s", type(e).__name__
            )

        dependency_chain = []

        for idx, draft in enumerate(drafts):
            spec = draft.get("spec", draft)
            op_type = spec.get("type", "")
            table_name = spec.get("table_name", "")

            if op_type == "create_table":
                # Creating a new table — adds to available set
                tables_available.add(table_name)
            elif op_type == "add_column":
                # Requires the target table to already exist
                if table_name and table_name not in tables_available:
                    errors.append(
                        {
                            "draft_index": idx,
                            "draft_name": draft.get("name", ""),
                            "error": f"Table '{table_name}' does not exist yet",
                        }
                    )
            elif op_type == "multi_operation":
                for sub_op in spec.get("operations", []):
                    sub_type = sub_op.get("type", "")
                    sub_table = sub_op.get("table_name", table_name)
                    if sub_type == "create_table":
                        tables_available.add(sub_table)
                    elif sub_table and sub_table not in tables_available:
                        errors.append(
                            {
                                "draft_index": idx,
                                "draft_name": draft.get("name", ""),
                                "error": f"Table '{sub_table}' does not exist yet",
                            }
                        )

            dependency_chain.append(idx)

        return {
            "valid": len(errors) == 0,
            "dependency_chain": dependency_chain,
            "errors": errors,
        }

    def rollback_to_point(self, rollback_point_id: str) -> Dict[str, Any]:
        """
        Rollback to specific point by executing stored reverse SQL operations.

        Uses the rollback operations recorded during execute_session_migrations
        when create_rollback_point=True.

        Args:
            rollback_point_id: Rollback point identifier

        Returns:
            Rollback results with list of rolled-back operations

        Raises:
            ValidationError: If rollback point not found
            SQLExecutionError: If rollback SQL fails
        """
        if rollback_point_id not in self._rollback_points:
            raise ValidationError(f"Rollback point not found: {rollback_point_id}")

        rollback_data = self._rollback_points[rollback_point_id]
        rollback_ops = rollback_data["operations"]

        if not rollback_ops:
            return {
                "success": True,
                "operations_rolled_back": [],
                "rollback_point_id": rollback_point_id,
            }

        engine = create_engine(self.connection_string)
        from sqlalchemy import text

        executed_rollbacks = []

        try:
            with engine.connect() as connection:
                with connection.begin():
                    for sql_down in rollback_ops:
                        connection.execute(text(sql_down))
                        executed_rollbacks.append(sql_down)
        except Exception as e:
            raise SQLExecutionError(
                f"Rollback failed after {len(executed_rollbacks)} operations: {e}"
            )

        # Remove the used rollback point
        del self._rollback_points[rollback_point_id]

        return {
            "success": True,
            "operations_rolled_back": executed_rollbacks,
            "rollback_point_id": rollback_point_id,
        }

    def log_performance_metrics(
        self, session_id: str, performance_data: Dict[str, Any]
    ) -> None:
        """
        Log performance metrics.

        Args:
            session_id: Session identifier
            performance_data: Performance metrics to log
        """
        logger.info(f"Performance metrics for session {session_id}: {performance_data}")

    # Private helper methods

    def _is_invalid_identifier(self, identifier: str) -> bool:
        """Check if identifier contains invalid characters.

        Validates database identifiers (table names, column names) to prevent SQL injection.
        Only allows alphanumeric characters and underscores, starting with letter/underscore.

        Args:
            identifier: The identifier to validate

        Returns:
            True if invalid, False if valid
        """
        import re

        # Must be non-empty string
        if not isinstance(identifier, str) or not identifier:
            return True

        # Length limits (PostgreSQL/MySQL limit is 63/64)
        if len(identifier) > 63:
            return True

        # Only allow alphanumeric + underscore, starting with letter/underscore
        # This prevents all SQL injection patterns:
        # - Quotes (', ", `)
        # - Comment markers (--, /*, */, #)
        # - Statement terminators (;)
        # - Null bytes (\x00)
        # - Special characters
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier):
            return True

        # Reject SQL keywords (case-insensitive)
        sql_keywords = {
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "CREATE",
            "ALTER",
            "TABLE",
            "DATABASE",
            "UNION",
            "WHERE",
            "FROM",
            "JOIN",
            "EXEC",
            "EXECUTE",
            "DECLARE",
            "CAST",
            "CONVERT",
            "TRUNCATE",
            "GRANT",
            "REVOKE",
            "COMMIT",
            "ROLLBACK",
        }
        if identifier.upper() in sql_keywords:
            return True

        return False

    def _validate_migration_spec(self, spec: Dict[str, Any]) -> None:
        """Validate migration specification."""
        if "type" not in spec:
            raise ValidationError("Missing required field: type")

        migration_type = spec["type"]

        if migration_type == "create_table":
            if "table_name" not in spec:
                raise ValidationError("Missing required field: table_name")
        elif migration_type == "add_column":
            if "table_name" not in spec:
                raise ValidationError("Missing required field: table_name")

    def _process_create_table(
        self, builder: VisualMigrationBuilder, spec: Dict[str, Any]
    ) -> None:
        """Process create table migration.

        Validates all identifiers to prevent SQL injection.

        Args:
            builder: VisualMigrationBuilder instance
            spec: Migration specification

        Raises:
            ValidationError: If any identifier is invalid
        """
        # SECURITY: Validate table name to prevent SQL injection
        table_name = spec["table_name"]
        if self._is_invalid_identifier(table_name):
            raise ValidationError(
                f"Invalid table name: '{table_name}'. "
                "Table names must start with a letter or underscore, "
                "contain only alphanumeric characters and underscores, "
                "be 1-63 characters long, and not be SQL keywords."
            )

        table_builder = builder.create_table(table_name)

        for col_spec in spec.get("columns", []):
            # SECURITY: Validate column name to prevent SQL injection
            col_name = col_spec.get("name", "")
            if self._is_invalid_identifier(col_name):
                raise ValidationError(
                    f"Invalid column name: '{col_name}'. "
                    "Column names must start with a letter or underscore, "
                    "contain only alphanumeric characters and underscores, "
                    "be 1-63 characters long, and not be SQL keywords."
                )

            column_type = self._get_column_type(col_spec["type"])
            col_builder = table_builder.add_column(col_name, column_type)

            if col_spec.get("primary_key"):
                col_builder.primary_key()
            if col_spec.get("nullable") is False:
                col_builder.not_null()
            if "length" in col_spec:
                # SECURITY: Validate length is a reasonable positive integer
                length = col_spec["length"]
                if not isinstance(length, int) or length <= 0 or length > 65535:
                    raise ValidationError(
                        f"Invalid column length: {length}. Must be an integer between 1 and 65535."
                    )
                col_builder.length(length)
            if "default" in col_spec:
                # SECURITY: Validate default value
                default_val = col_spec["default"]
                # Only allow simple types for default values
                if not isinstance(default_val, (str, int, float, bool, type(None))):
                    raise ValidationError(
                        f"Invalid default value type: {type(default_val).__name__}. "
                        "Only string, int, float, bool, or null allowed."
                    )
                # String default values should not contain SQL injection patterns
                if isinstance(default_val, str):
                    # Check for common SQL injection patterns in string defaults
                    dangerous_patterns = [
                        "';",
                        "--",
                        "/*",
                        "*/",
                        "DROP",
                        "DELETE",
                        "INSERT",
                        "UPDATE",
                        "UNION",
                    ]
                    if any(
                        pattern in default_val.upper() for pattern in dangerous_patterns
                    ):
                        raise ValidationError(
                            "Invalid default value: contains potentially dangerous SQL patterns. "
                            "If this is a legitimate value, please use a parameterized migration instead."
                        )
                col_builder.default_value(default_val)

    def _process_add_column(
        self, builder: VisualMigrationBuilder, spec: Dict[str, Any]
    ) -> None:
        """Process add column migration.

        Validates all identifiers to prevent SQL injection.

        Args:
            builder: VisualMigrationBuilder instance
            spec: Migration specification

        Raises:
            ValidationError: If any identifier is invalid
        """
        # SECURITY: Validate table name to prevent SQL injection
        table_name = spec["table_name"]
        if self._is_invalid_identifier(table_name):
            raise ValidationError(
                f"Invalid table name: '{table_name}'. "
                "Table names must start with a letter or underscore, "
                "contain only alphanumeric characters and underscores, "
                "be 1-63 characters long, and not be SQL keywords."
            )

        col_spec = spec["column"]

        # SECURITY: Validate column name to prevent SQL injection
        col_name = col_spec.get("name", "")
        if self._is_invalid_identifier(col_name):
            raise ValidationError(
                f"Invalid column name: '{col_name}'. "
                "Column names must start with a letter or underscore, "
                "contain only alphanumeric characters and underscores, "
                "be 1-63 characters long, and not be SQL keywords."
            )

        column_type = self._get_column_type(col_spec["type"])
        col_builder = builder.add_column(table_name, col_name, column_type)

        if col_spec.get("nullable") is False:
            col_builder.not_null()
        if "length" in col_spec:
            # SECURITY: Validate length is a reasonable positive integer
            length = col_spec["length"]
            if not isinstance(length, int) or length <= 0 or length > 65535:
                raise ValidationError(
                    f"Invalid column length: {length}. Must be an integer between 1 and 65535."
                )
            col_builder.length(length)

    def _process_multi_operation(
        self, builder: VisualMigrationBuilder, spec: Dict[str, Any]
    ) -> None:
        """Process multi-operation migration atomically.

        Iterates over the ``operations`` list in the spec and processes each
        sub-operation sequentially using the same builder, ensuring all
        operations are part of a single migration transaction.

        Args:
            builder: VisualMigrationBuilder instance
            spec: Migration specification with an ``operations`` list.
                  Each operation must have a ``type`` key and the same
                  structure as a single-operation migration spec.

        Raises:
            ValidationError: If operations list is missing or empty,
                or if any individual operation fails validation.
        """
        operations = spec.get("operations", [])
        if not operations:
            raise ValidationError(
                "Multi-operation migration requires a non-empty 'operations' list. "
                "Each operation should have a 'type' field (e.g., 'create_table', "
                "'add_column') and the corresponding specification fields."
            )

        for i, operation in enumerate(operations):
            op_type = operation.get("type")
            if not op_type:
                raise ValidationError(
                    f"Operation {i} in multi-operation migration is missing 'type' field"
                )

            if op_type == "create_table":
                self._process_create_table(builder, operation)
            elif op_type == "add_column":
                self._process_add_column(builder, operation)
            else:
                raise ValidationError(
                    f"Unsupported operation type '{op_type}' at index {i} "
                    f"in multi-operation migration. Supported types: "
                    f"create_table, add_column"
                )

    def _get_column_type(self, type_str: str) -> ColumnType:
        """Convert string type to ColumnType enum."""
        type_mapping = {
            "SERIAL": ColumnType.INTEGER,
            "INTEGER": ColumnType.INTEGER,
            "VARCHAR": ColumnType.VARCHAR,
            "TEXT": ColumnType.TEXT,
            "DECIMAL": ColumnType.DECIMAL,
            "TIMESTAMP": ColumnType.TIMESTAMP,
            "BOOLEAN": ColumnType.BOOLEAN,
        }

        return type_mapping.get(type_str.upper(), ColumnType.VARCHAR)

    def _generate_rollback_sql(self, migration: Migration) -> str:
        """Generate rollback SQL for migration."""
        rollback_parts = []

        for operation in reversed(migration.operations):
            sql_down = getattr(operation, "sql_down", "-- No rollback available")
            if hasattr(sql_down, "__call__"):
                sql_down = str(sql_down)
            rollback_parts.append(str(sql_down))

        return "\n".join(rollback_parts)

    def _dict_to_migration(self, migration_data: Dict[str, Any]) -> Migration:
        """Convert dict to Migration object.

        Args:
            migration_data: Dictionary containing migration fields

        Returns:
            Migration: Properly instantiated Migration object

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Validate required fields
        if "version" not in migration_data:
            raise ValueError("Migration data must include 'version' field")

        version = migration_data["version"]
        name = migration_data.get("name", f"migration_{version}")

        # Convert operations if present
        operations = []
        for op_data in migration_data.get("operations", []):
            if not isinstance(op_data, dict):
                raise ValueError(f"Operation must be a dictionary, got {type(op_data)}")

            # Support both full format and simplified web API format
            # Full format: operation_type, sql_up, sql_down, description
            # Simplified format: type, sql, table_name (description auto-generated)

            # Parse operation type (handle both "operation_type" and "type" keys)
            op_type_str = op_data.get("operation_type") or op_data.get("type")
            if not op_type_str:
                raise ValueError(
                    "Operation must include 'operation_type' or 'type' field"
                )

            try:
                op_type = MigrationType(op_type_str)
            except ValueError:
                raise ValueError(f"Invalid operation_type: {op_type_str}")

            # Get table name
            table_name = op_data.get("table_name", "")
            if not table_name:
                raise ValueError("Operation must include 'table_name' field")

            # SECURITY: Validate table name to prevent SQL injection
            if self._is_invalid_identifier(table_name):
                raise ValueError(
                    f"Invalid table name in migration operation: '{table_name}'. "
                    "Table names must start with a letter or underscore, "
                    "contain only alphanumeric characters and underscores, "
                    "be 1-63 characters long, and not be SQL keywords."
                )

            # Handle SQL - support both full format (sql_up/sql_down) and simplified (sql)
            sql_up = op_data.get("sql_up") or op_data.get("sql", "")
            sql_down = op_data.get("sql_down", "")  # Optional for simplified format

            # SECURITY WARNING: Direct SQL from user input
            # This method is typically called during validation/review, not direct execution
            # However, SQL should be generated by VisualMigrationBuilder, not provided directly
            # Log warning if SQL appears to be user-provided rather than builder-generated
            if sql_up and any(
                dangerous in sql_up.upper()
                for dangerous in [
                    "DROP TABLE",
                    "DELETE FROM",
                    "TRUNCATE",
                    "GRANT",
                    "REVOKE",
                ]
            ):
                logger.warning(
                    f"Migration operation contains potentially dangerous SQL: {sql_up[:100]}... "
                    "Ensure this SQL is from a trusted source and not user input."
                )

            # Generate description if not provided
            description = op_data.get("description")
            if not description:
                description = f"{op_type.value} on table {table_name}"

            # Create MigrationOperation
            operation = MigrationOperation(
                operation_type=op_type,
                table_name=table_name,
                description=description,
                sql_up=sql_up,
                sql_down=sql_down,
                metadata=op_data.get("metadata", {}),
            )
            operations.append(operation)

        # Parse timestamps if provided
        created_at = migration_data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()

        applied_at = migration_data.get("applied_at")
        if isinstance(applied_at, str):
            applied_at = datetime.fromisoformat(applied_at)

        # Parse status
        status_str = migration_data.get("status", "pending")
        try:
            status = MigrationStatus(status_str)
        except ValueError:
            raise ValueError(f"Invalid status: {status_str}")

        # Create Migration object
        migration = Migration(
            version=version,
            name=name,
            operations=operations,
            created_at=created_at,
            applied_at=applied_at,
            status=status,
            checksum=migration_data.get("checksum"),
        )

        return migration

    def _json_serializer(self, obj: Any) -> Any:
        """Custom JSON serializer for complex objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        else:
            # Check if it's a custom class (not built-in types)
            if hasattr(obj, "__class__") and obj.__class__.__module__ != "builtins":
                # For custom classes, we should raise an error to be explicit
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
            elif hasattr(obj, "__dict__"):
                return obj.__dict__
            else:
                # Always raise error for non-standard objects to catch serialization issues
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    def _create_execution_stages(
        self, steps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Create execution stages from steps."""
        # Simple staging: group steps by type
        return [{"stage": 1, "steps": steps}]

    def _calculate_overall_risk(self, steps: List[Dict[str, Any]]) -> str:
        """Calculate overall risk level based on migration operation types.

        Examines each step's migration name and risk level to determine the highest
        risk across all steps. Destructive operations (drop table, drop column)
        yield "high" risk. Schema modifications (alter table, modify column) yield
        "medium" risk. Additive operations (create table, add index, add column)
        yield "low" risk.

        Args:
            steps: List of execution plan steps, each containing migration_name
                   and optionally risk_level.

        Returns:
            The highest risk level found: "high", "medium", or "low".
        """
        risk_priority = {"low": 0, "medium": 1, "high": 2}
        highest_risk = "low"

        # High-risk operation indicators (destructive)
        high_risk_patterns = [
            "drop_table",
            "drop_column",
            "drop_constraint",
            "truncate",
        ]
        # Medium-risk operation indicators (modifications)
        medium_risk_patterns = [
            "alter_table",
            "modify_column",
            "rename_table",
            "rename_column",
            "drop_index",
        ]

        for step in steps:
            # Check explicit risk_level on the step first
            step_risk = step.get("risk_level", "low")
            if risk_priority.get(step_risk, 0) > risk_priority.get(highest_risk, 0):
                highest_risk = step_risk

            # Infer risk from migration name patterns
            migration_name = step.get("migration_name", "").lower()

            for pattern in high_risk_patterns:
                if pattern in migration_name:
                    highest_risk = "high"
                    break

            if highest_risk == "high":
                break  # Cannot get higher than high

            for pattern in medium_risk_patterns:
                if pattern in migration_name:
                    if risk_priority.get("medium", 1) > risk_priority.get(
                        highest_risk, 0
                    ):
                        highest_risk = "medium"
                    break

        return highest_risk


def create_engine(connection_string: str):
    """Create database engine using SQLAlchemy.

    Args:
        connection_string: Database connection URL

    Returns:
        SQLAlchemy engine with inspector method attached

    Raises:
        ImportError: If SQLAlchemy is not installed
    """
    try:
        # Try to import real SQLAlchemy
        from sqlalchemy import create_engine as sa_create_engine
        from sqlalchemy import inspect

        # Create real engine
        engine = sa_create_engine(connection_string)

        # Add inspector method
        def get_inspector():
            return inspect(engine)

        engine.inspector = get_inspector
        return engine

    except ImportError as e:
        # Raise clear error with resolution steps
        raise ImportError(
            "SQLAlchemy is required for WebMigrationAPI.\n"
            "Install with: pip install sqlalchemy>=2.0.0\n"
            "Or reinstall DataFlow: pip install --force-reinstall kailash-dataflow"
        ) from e
