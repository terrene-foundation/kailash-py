"""
Admin Node Schema Manager

Production-ready database schema management for Kailash Admin Nodes.
Handles schema creation, migration, and validation with comprehensive error handling.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kailash.nodes.data import SQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class AdminSchemaManager:
    """Manages admin node database schema creation and migration."""

    def __init__(self, database_config: Dict[str, Any]):
        """Initialize schema manager with database configuration."""
        self.database_config = database_config
        self.db_node = SQLDatabaseNode(name="admin_schema_manager", **database_config)
        self.logger = logging.getLogger(__name__)

        # Schema version for migration tracking
        self.current_schema_version = "1.0.0"

    def create_full_schema(self, drop_existing: bool = False) -> Dict[str, Any]:
        """
        Create the complete admin node schema.

        Args:
            drop_existing: If True, drop existing tables first

        Returns:
            Dict with creation results and metadata
        """
        try:
            results = {
                "schema_version": self.current_schema_version,
                "tables_created": [],
                "indexes_created": [],
                "triggers_created": [],
                "functions_created": [],
                "success": True,
                "errors": [],
            }

            # Drop existing tables if requested
            if drop_existing:
                self._drop_existing_schema()

            # Load and execute schema
            schema_path = Path(__file__).parent / "schema.sql"
            with open(schema_path, "r") as f:
                schema_sql = f.read()

            # Execute schema creation
            self.db_node.execute(query=schema_sql)

            # Verify schema creation
            tables = self._get_existing_tables()
            results["tables_created"] = tables

            # Create schema version tracking
            self._create_schema_version_table()
            self._record_schema_version()

            self.logger.info(f"Admin schema created successfully: {len(tables)} tables")
            return results

        except Exception as e:
            self.logger.error(f"Schema creation failed: {e}")
            raise NodeExecutionError(f"Failed to create admin schema: {str(e)}")

    def validate_schema(self) -> Dict[str, Any]:
        """
        Validate that the admin schema is complete and correct.

        Returns:
            Dict with validation results
        """
        try:
            validation = {
                "is_valid": True,
                "schema_version": None,
                "missing_tables": [],
                "missing_indexes": [],
                "table_issues": [],
                "recommendations": [],
            }

            # Check required tables
            required_tables = [
                "users",
                "roles",
                "user_role_assignments",
                "permissions",
                "permission_cache",
                "user_attributes",
                "resource_attributes",
                "user_sessions",
                "admin_audit_log",
            ]

            existing_tables = self._get_existing_tables()

            for table in required_tables:
                if table not in existing_tables:
                    validation["missing_tables"].append(table)
                    validation["is_valid"] = False

            # Check schema version
            try:
                version_result = self.db_node.execute(
                    query="SELECT version FROM admin_schema_version ORDER BY created_at DESC LIMIT 1",
                    result_format="dict",
                )
                if version_result.get("data"):
                    validation["schema_version"] = version_result["data"][0]["version"]
                else:
                    validation["recommendations"].append(
                        "Schema version tracking not found"
                    )
            except Exception:
                validation["recommendations"].append("Unable to check schema version")

            # Check critical indexes
            critical_indexes = [
                "idx_users_tenant_status",
                "idx_roles_tenant_active",
                "idx_user_roles_user",
                "idx_permission_cache_user",
            ]

            existing_indexes = self._get_existing_indexes()
            for index in critical_indexes:
                if index not in existing_indexes:
                    validation["missing_indexes"].append(index)
                    validation["recommendations"].append(
                        f"Consider creating index: {index}"
                    )

            # Validate table structures
            validation["table_issues"] = self._validate_table_structures()

            return validation

        except Exception as e:
            self.logger.error(f"Schema validation failed: {e}")
            raise NodeExecutionError(f"Failed to validate schema: {str(e)}")

    def migrate_schema(self, target_version: str = None) -> Dict[str, Any]:
        """
        Migrate schema to target version.

        Args:
            target_version: Target schema version (default: latest)

        Returns:
            Dict with migration results
        """
        target_version = target_version or self.current_schema_version

        try:
            current_version = self._get_current_schema_version()

            if current_version == target_version:
                return {
                    "migration_needed": False,
                    "current_version": current_version,
                    "target_version": target_version,
                    "message": "Schema is already at target version",
                }

            # For now, we only support creating from scratch
            # Future versions would implement incremental migrations
            if current_version is None:
                return self.create_full_schema(drop_existing=False)
            else:
                return {
                    "migration_needed": True,
                    "current_version": current_version,
                    "target_version": target_version,
                    "error": "Incremental migrations not yet implemented",
                    "recommendation": "Use create_full_schema() with drop_existing=True",
                }

        except Exception as e:
            self.logger.error(f"Schema migration failed: {e}")
            raise NodeExecutionError(f"Failed to migrate schema: {str(e)}")

    def get_schema_info(self) -> Dict[str, Any]:
        """Get comprehensive schema information."""
        try:
            info = {
                "schema_version": self._get_current_schema_version(),
                "tables": self._get_table_info(),
                "indexes": self._get_existing_indexes(),
                "row_counts": self._get_table_row_counts(),
                "database_info": self._get_database_info(),
            }

            return info

        except Exception as e:
            self.logger.error(f"Failed to get schema info: {e}")
            raise NodeExecutionError(f"Failed to get schema info: {str(e)}")

    def _drop_existing_schema(self):
        """Drop existing admin schema tables."""
        tables_to_drop = [
            "admin_audit_log",
            "user_sessions",
            "resource_attributes",
            "user_attributes",
            "permission_cache",
            "permissions",
            "user_role_assignments",
            "roles",
            "users",
            "admin_schema_version",
        ]

        for table in tables_to_drop:
            try:
                self.db_node.execute(query=f"DROP TABLE IF EXISTS {table} CASCADE")
            except Exception as e:
                self.logger.warning(f"Could not drop table {table}: {e}")

    def _get_existing_tables(self) -> List[str]:
        """Get list of existing tables in the database."""
        try:
            result = self.db_node.execute(
                query="""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """,
                result_format="dict",
            )

            return [row["table_name"] for row in result.get("data", [])]

        except Exception as e:
            self.logger.warning(f"Could not get existing tables: {e}")
            return []

    def _get_existing_indexes(self) -> List[str]:
        """Get list of existing indexes."""
        try:
            result = self.db_node.execute(
                query="""
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                ORDER BY indexname
                """,
                result_format="dict",
            )

            return [row["indexname"] for row in result.get("data", [])]

        except Exception as e:
            self.logger.warning(f"Could not get existing indexes: {e}")
            return []

    def _create_schema_version_table(self):
        """Create table for tracking schema versions."""
        version_table_sql = """
        CREATE TABLE IF NOT EXISTS admin_schema_version (
            id SERIAL PRIMARY KEY,
            version VARCHAR(50) NOT NULL,
            applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            migration_notes TEXT
        )
        """

        self.db_node.execute(query=version_table_sql)

    def _record_schema_version(self):
        """Record the current schema version."""
        self.db_node.execute(
            query="""
            INSERT INTO admin_schema_version (version, migration_notes)
            VALUES ($1, $2)
            """,
            parameters=[
                self.current_schema_version,
                f"Full schema creation for admin nodes v{self.current_schema_version}",
            ],
        )

    def _get_current_schema_version(self) -> Optional[str]:
        """Get the current schema version."""
        try:
            result = self.db_node.execute(
                query="SELECT version FROM admin_schema_version ORDER BY created_at DESC LIMIT 1",
                result_format="dict",
            )

            if result.get("data"):
                return result["data"][0]["version"]
            return None

        except Exception:
            return None

    def _validate_table_structures(self) -> List[Dict[str, Any]]:
        """Validate table structures against expected schema."""
        issues = []

        # Check users table structure
        try:
            users_columns = self._get_table_columns("users")
            required_users_columns = [
                "user_id",
                "email",
                "status",
                "tenant_id",
                "roles",
                "attributes",
            ]

            for col in required_users_columns:
                if col not in users_columns:
                    issues.append(
                        {
                            "table": "users",
                            "issue": f"Missing column: {col}",
                            "severity": "error",
                        }
                    )

        except Exception as e:
            issues.append(
                {
                    "table": "users",
                    "issue": f"Could not validate structure: {e}",
                    "severity": "warning",
                }
            )

        return issues

    def _get_table_columns(self, table_name: str) -> List[str]:
        """Get column names for a table."""
        try:
            result = self.db_node.execute(
                query="""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = $1
                ORDER BY ordinal_position
                """,
                parameters=[table_name],
                result_format="dict",
            )

            return [row["column_name"] for row in result.get("data", [])]

        except Exception as e:
            self.logger.warning(f"Could not get columns for {table_name}: {e}")
            return []

    def _get_table_info(self) -> Dict[str, Any]:
        """Get detailed table information."""
        try:
            result = self.db_node.execute(
                query="""
                SELECT
                    t.table_name,
                    t.table_type,
                    pg_size_pretty(pg_total_relation_size(c.oid)) as size
                FROM information_schema.tables t
                LEFT JOIN pg_class c ON c.relname = t.table_name
                WHERE t.table_schema = 'public'
                AND t.table_type = 'BASE TABLE'
                ORDER BY t.table_name
                """,
                result_format="dict",
            )

            return {row["table_name"]: row for row in result.get("data", [])}

        except Exception as e:
            self.logger.warning(f"Could not get table info: {e}")
            return {}

    def _get_table_row_counts(self) -> Dict[str, int]:
        """Get row counts for all admin tables."""
        tables = ["users", "roles", "user_role_assignments", "permission_cache"]
        counts = {}

        for table in tables:
            try:
                result = self.db_node.execute(
                    query=f"SELECT COUNT(*) as count FROM {table}",
                    result_format="dict",
                )
                counts[table] = result["data"][0]["count"] if result.get("data") else 0
            except Exception:
                counts[table] = -1  # Error indicator

        return counts

    def _get_database_info(self) -> Dict[str, Any]:
        """Get general database information."""
        try:
            version_result = self.db_node.execute(
                query="SELECT version()", result_format="dict"
            )

            size_result = self.db_node.execute(
                query="SELECT pg_size_pretty(pg_database_size(current_database())) as size",
                result_format="dict",
            )

            return {
                "version": (
                    version_result["data"][0]["version"]
                    if version_result.get("data")
                    else "Unknown"
                ),
                "size": (
                    size_result["data"][0]["size"]
                    if size_result.get("data")
                    else "Unknown"
                ),
            }

        except Exception as e:
            self.logger.warning(f"Could not get database info: {e}")
            return {"version": "Unknown", "size": "Unknown"}
