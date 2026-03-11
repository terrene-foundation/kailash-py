"""
Model Registry for DataFlow - Persistent Model Storage

This module integrates with DataFlow's existing migration system to provide
persistent model storage, enabling multi-application access to shared model definitions.
"""

import asyncio
import hashlib
import json
import logging
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from kailash.nodes.data.sql import SQLDatabaseNode
from kailash.runtime import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Persistent model registry integrated with DataFlow's migration system."""

    # Extend existing migration tables rather than creating new ones
    # This prevents conflicts and leverages proven infrastructure

    def __init__(self, dataflow_instance, migration_system=None):
        """
        Initialize model registry with DataFlow instance.

        Automatically detects async context and uses appropriate runtime
        to prevent deadlocks in FastAPI, pytest async, and other async environments.
        """
        self.dataflow = dataflow_instance

        # ✅ FIX: Detect async context and use appropriate runtime
        # This prevents deadlocks when DataFlow is used in FastAPI, pytest async, etc.
        try:
            asyncio.get_running_loop()
            # Running in async context - use AsyncLocalRuntime
            self.runtime = AsyncLocalRuntime()
            self._is_async = True
            logger.debug(
                "ModelRegistry: Detected async context, using AsyncLocalRuntime"
            )
        except RuntimeError:
            # No event loop - use sync LocalRuntime
            self.runtime = LocalRuntime()
            self._is_async = False
            logger.debug("ModelRegistry: Detected sync context, using LocalRuntime")

        self.migration_system = migration_system
        self._initialized = False

        # Track model definitions as part of migration metadata
        self._model_migration_type = "model_definition"

        # ✅ LAZY REGISTRATION FIX: Queue models during import time
        # This prevents race conditions when models are imported before
        # dataflow_model_registry table is created (e.g., pytest collection phase)
        self._pending_models: List[Tuple[str, type, Optional[str]]] = []
        self._pending_models_lock = threading.Lock()
        logger.debug(
            "ModelRegistry: Lazy registration enabled - models will be queued until initialization completes"
        )

        # Transaction safety
        self._registry_lock = threading.Lock()
        self._transaction_manager = None

        # Initialize transaction manager if available
        try:
            from ..features.transactions import TransactionManager

            self._transaction_manager = TransactionManager(dataflow_instance)
        except ImportError:
            logger.warning(
                "TransactionManager not available, operations will not be transactional"
            )

    @contextmanager
    def _transaction_context(self, operation_name: str):
        """Context manager for transaction-safe operations with logging."""
        with self._registry_lock:
            logger.debug(f"Starting registry operation: {operation_name}")

            if self._transaction_manager:
                # Use existing transaction manager
                with self._transaction_manager.transaction(
                    isolation_level="READ_COMMITTED"
                ) as tx:
                    try:
                        yield tx
                        logger.info(
                            f"Registry operation {operation_name} completed successfully"
                        )
                    except Exception as e:
                        logger.error(f"Registry operation {operation_name} failed: {e}")
                        raise
            else:
                # No transaction support, just use lock
                try:
                    yield None
                    logger.info(
                        f"Registry operation {operation_name} completed (non-transactional)"
                    )
                except Exception as e:
                    logger.error(f"Registry operation {operation_name} failed: {e}")
                    raise

    def initialize(self) -> bool:
        """Initialize model registry with dedicated table and process pending models."""
        try:
            # Create dedicated model registry table instead of extending migration tables
            success = self._create_model_registry_table()
            if success:
                self._initialized = True
                logger.info(
                    "Model registry initialized with dedicated dataflow_model_registry table"
                )

                # ✅ LAZY REGISTRATION FIX: Process all pending models after initialization
                self._finalize_initialization()
            else:
                logger.error("Failed to create model registry table")

            return success

        except Exception as e:
            logger.error(f"Error initializing model registry: {e}")
            return False

    def _finalize_initialization(self) -> None:
        """
        Process all pending models after initialization completes.

        This method is called after dataflow_model_registry table is created.
        It registers all models that were queued during import time (before
        the table existed).

        Thread-safe: Uses lock to prevent race conditions during registration.
        """
        with self._pending_models_lock:
            if not self._pending_models:
                logger.debug("No pending models to register")
                return

            pending_count = len(self._pending_models)
            logger.info(
                f"Processing {pending_count} pending model(s) after initialization"
            )

            # Register all pending models
            registered_count = 0
            failed_count = 0

            for model_name, model_class, application_id in self._pending_models:
                try:
                    # Call the actual registration logic (without queueing)
                    success = self._do_register_model(
                        model_name, model_class, application_id
                    )
                    if success:
                        registered_count += 1
                        logger.debug(f"Registered pending model: {model_name}")
                    else:
                        failed_count += 1
                        logger.warning(
                            f"Failed to register pending model: {model_name}"
                        )
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error registering pending model {model_name}: {e}")

            # Clear the pending queue
            self._pending_models.clear()

            logger.info(
                f"Finalized model registration: {registered_count} succeeded, "
                f"{failed_count} failed out of {pending_count} total"
            )

    def _create_model_registry_table(self) -> bool:
        """Create dedicated dataflow_model_registry table using WorkflowBuilder pattern."""
        try:
            # Get database URL
            db_url = self.dataflow.config.database.get_connection_url(
                self.dataflow.config.environment
            )

            # Import connection parser and detect database type
            from ..adapters.connection_parser import ConnectionParser

            database_type = ConnectionParser.detect_database_type(db_url)

            # Get database-specific statements
            if database_type == "sqlite":
                statements = self._get_sqlite_registry_table_statements()
            elif database_type == "mysql":
                statements = self._get_mysql_registry_table_statements()
            else:
                statements = self._get_postgresql_registry_table_statements()

            # Execute statements using WorkflowBuilder
            for i, statement in enumerate(statements):
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "SQLDatabaseNode",
                    f"create_registry_table_{i}",
                    {
                        "connection_string": db_url,
                        "database_type": database_type,
                        "query": statement,
                        "validate_queries": False,
                    },
                )

                # ✅ FIX: Use synchronous SQLDatabaseNode with LocalRuntime for DDL operations
                # SQLDatabaseNode is synchronous and works in all contexts (sync/async/pytest)
                try:
                    init_runtime = LocalRuntime()
                    results, _ = init_runtime.execute(workflow.build())
                    if f"create_registry_table_{i}" not in results or results[
                        f"create_registry_table_{i}"
                    ].get("error"):
                        error_msg = results.get(f"create_registry_table_{i}", {}).get(
                            "error", "Unknown error"
                        )
                        error_lower = str(error_msg).lower()
                        # For MySQL, ignore "duplicate key name" errors when creating indexes
                        # This happens when indexes already exist (MySQL doesn't support IF NOT EXISTS for indexes)
                        if database_type == "mysql" and (
                            "duplicate key name" in error_lower
                            or "already exists" in error_lower
                        ):
                            logger.debug(
                                f"Index already exists (ignoring for MySQL): {error_msg}"
                            )
                            continue  # Continue with next statement
                        logger.error(
                            f"Failed to execute registry table statement {i}: {error_msg}"
                        )
                        return False
                except Exception as exec_error:
                    # For MySQL, ignore "duplicate key name" errors when creating indexes
                    error_lower = str(exec_error).lower()
                    if database_type == "mysql" and (
                        "duplicate key name" in error_lower
                        or "1061" in error_lower  # MySQL error code for duplicate key
                        or "already exists" in error_lower
                    ):
                        logger.debug(
                            f"Index already exists (ignoring for MySQL): {exec_error}"
                        )
                        continue  # Continue with next statement
                    raise  # Re-raise other errors

            return True

        except Exception as e:
            logger.error(f"Failed to create model registry table and indexes: {e}")
            return False

    def _get_sqlite_registry_table_statements(self) -> List[str]:
        """Get SQLite model registry table creation statements."""
        return [
            """
            CREATE TABLE IF NOT EXISTS dataflow_model_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                model_checksum TEXT NOT NULL,
                model_definitions TEXT NOT NULL,
                application_id TEXT,
                registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active',
                version INTEGER DEFAULT 1,
                metadata TEXT,
                UNIQUE(model_name, application_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_model_registry_application ON dataflow_model_registry(application_id)",
            "CREATE INDEX IF NOT EXISTS idx_model_registry_checksum ON dataflow_model_registry(model_checksum)",
            "CREATE INDEX IF NOT EXISTS idx_model_registry_name ON dataflow_model_registry(model_name)",
            "CREATE INDEX IF NOT EXISTS idx_model_registry_status ON dataflow_model_registry(status)",
        ]

    def _get_postgresql_registry_table_statements(self) -> List[str]:
        """Get PostgreSQL model registry table creation statements."""
        return [
            """
            CREATE TABLE IF NOT EXISTS dataflow_model_registry (
                id SERIAL PRIMARY KEY,
                model_name VARCHAR(255) NOT NULL,
                model_checksum VARCHAR(64) NOT NULL,
                model_definitions JSONB NOT NULL,
                application_id VARCHAR(255),
                registered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(50) DEFAULT 'active',
                version INTEGER DEFAULT 1,
                metadata JSONB,
                CONSTRAINT unique_model_per_app UNIQUE (model_name, application_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_model_registry_application ON dataflow_model_registry(application_id)",
            "CREATE INDEX IF NOT EXISTS idx_model_registry_checksum ON dataflow_model_registry(model_checksum)",
            "CREATE INDEX IF NOT EXISTS idx_model_registry_name ON dataflow_model_registry(model_name)",
            "CREATE INDEX IF NOT EXISTS idx_model_registry_status ON dataflow_model_registry(status)",
        ]

    def _get_mysql_registry_table_statements(self) -> List[str]:
        """Get MySQL model registry table creation statements."""
        return [
            """
            CREATE TABLE IF NOT EXISTS dataflow_model_registry (
                id INT AUTO_INCREMENT PRIMARY KEY,
                model_name VARCHAR(255) NOT NULL,
                model_checksum VARCHAR(64) NOT NULL,
                model_definitions JSON NOT NULL,
                application_id VARCHAR(255),
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                status VARCHAR(50) DEFAULT 'active',
                version INT DEFAULT 1,
                metadata JSON,
                UNIQUE KEY unique_model_per_app (model_name, application_id)
            )
            """,
            "CREATE INDEX idx_model_registry_application ON dataflow_model_registry(application_id)",
            "CREATE INDEX idx_model_registry_checksum ON dataflow_model_registry(model_checksum)",
            "CREATE INDEX idx_model_registry_name ON dataflow_model_registry(model_name)",
            "CREATE INDEX idx_model_registry_status ON dataflow_model_registry(status)",
        ]

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

    def _make_json_serializable(self, obj: Any) -> Any:
        """Convert Python objects to JSON-serializable format.

        This handles Python type objects that can't be directly serialized to JSON.
        """
        from datetime import date, datetime, time
        from decimal import Decimal

        if isinstance(obj, dict):
            return {
                key: self._make_json_serializable(value) for key, value in obj.items()
            }
        elif isinstance(obj, list):
            return [self._make_json_serializable(item) for item in obj]
        elif isinstance(obj, datetime):
            # Convert datetime to ISO format string
            return obj.isoformat()
        elif isinstance(obj, date):
            # Convert date to ISO format string
            return obj.isoformat()
        elif isinstance(obj, time):
            # Convert time to ISO format string
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            # Convert Decimal to string to preserve precision
            return str(obj)
        elif isinstance(obj, type):
            # Convert Python type objects to string representation
            return obj.__name__
        elif hasattr(obj, "__name__") and hasattr(obj, "__module__"):
            # Handle other callable objects that might have names
            return (
                f"{obj.__module__}.{obj.__name__}"
                if obj.__module__ != "builtins"
                else obj.__name__
            )
        elif callable(obj):
            return (
                f"<callable:{obj.__name__ if hasattr(obj, '__name__') else str(obj)}>"
            )
        else:
            # Handle SQLAlchemy MetaData and other non-serializable objects
            try:
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return f"<{type(obj).__name__}>"

    def _generate_unified_checksum(self, content: Dict[str, Any]) -> str:
        """Generate checksum for model definition."""
        # Make content JSON serializable before calculating checksum
        serializable_content = self._make_json_serializable(content)
        sorted_content = json.dumps(serializable_content, sort_keys=True)
        return hashlib.sha256(sorted_content.encode()).hexdigest()

    def register_model(
        self, model_name: str, model_class: type, application_id: str = None
    ) -> bool:
        """
        Register a model definition in the registry (with lazy registration support).

        If the registry is not yet initialized (e.g., during pytest collection phase),
        the model is queued for later registration. Otherwise, it's registered immediately.

        Args:
            model_name: Name of the model class
            model_class: The model class to register
            application_id: Optional application identifier

        Returns:
            bool: True if model was queued or registered successfully

        Note:
            This method implements lazy registration to prevent race conditions
            when models are imported before dataflow_model_registry table exists.
        """
        # ✅ LAZY REGISTRATION FIX: Queue models if not initialized
        if not self._initialized:
            with self._pending_models_lock:
                # Check if model is already in pending queue
                for pending_name, _, _ in self._pending_models:
                    if pending_name == model_name:
                        logger.debug(
                            f"Model {model_name} already in pending queue, skipping"
                        )
                        return True

                # Add to pending queue
                self._pending_models.append((model_name, model_class, application_id))
                logger.info(
                    f"Model {model_name} queued for registration "
                    f"(registry not initialized yet, {len(self._pending_models)} pending)"
                )
                return True

        # Registry is initialized, register immediately
        return self._do_register_model(model_name, model_class, application_id)

    def _do_register_model(
        self, model_name: str, model_class: type, application_id: str = None
    ) -> bool:
        """
        Actual model registration logic (internal method).

        This method performs the database operations to register a model.
        It should only be called when the registry is initialized.

        Args:
            model_name: Name of the model class
            model_class: The model class to register
            application_id: Optional application identifier

        Returns:
            bool: True if registration succeeded
        """
        try:
            # Extract model metadata
            model_definitions = self._extract_model_metadata(model_class)
            model_definitions["model_name"] = model_name

            # Generate checksum
            model_checksum = self._generate_unified_checksum(model_definitions)

            # Check if already registered with same checksum
            if self._model_exists_with_checksum(model_checksum):
                logger.debug(
                    f"Model {model_name} already registered with checksum {model_checksum}"
                )
                return True

            # Register the model with database-specific query
            db_url = self.dataflow.config.database.get_connection_url(
                self.dataflow.config.environment
            )

            # Import connection parser and detect database type
            from ..adapters.connection_parser import ConnectionParser

            database_type = ConnectionParser.detect_database_type(db_url)

            workflow = WorkflowBuilder()

            if database_type == "sqlite":
                # SQLite uses INSERT OR REPLACE and ? parameters
                workflow.add_node(
                    "SQLDatabaseNode",
                    "register_model",
                    {
                        "connection_string": db_url,
                        "database_type": database_type,
                        "query": """
                        INSERT OR REPLACE INTO dataflow_model_registry
                        (model_name, model_checksum, model_definitions, application_id,
                         status, version, metadata, updated_at)
                        VALUES (?, ?, ?, ?, ?,
                                COALESCE((SELECT version + 1 FROM dataflow_model_registry
                                         WHERE model_name = ? AND application_id = ?), 1),
                                ?, datetime('now'))
                    """,
                        "parameters": [
                            model_name,
                            model_checksum,
                            json.dumps(model_definitions),
                            application_id or self._get_application_id(),
                            "active",
                            model_name,  # For version calculation
                            application_id
                            or self._get_application_id(),  # For version calculation
                            json.dumps(
                                {
                                    "source": "model_registry",
                                    "timestamp": datetime.utcnow().isoformat(),
                                }
                            ),
                        ],
                    },
                )
            elif database_type == "mysql":
                # MySQL uses ON DUPLICATE KEY UPDATE and %s parameters
                workflow.add_node(
                    "SQLDatabaseNode",
                    "register_model",
                    {
                        "connection_string": db_url,
                        "database_type": database_type,
                        "query": """
                        INSERT INTO dataflow_model_registry
                        (model_name, model_checksum, model_definitions, application_id,
                         status, version, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            model_checksum = VALUES(model_checksum),
                            model_definitions = VALUES(model_definitions),
                            updated_at = CURRENT_TIMESTAMP,
                            version = version + 1
                    """,
                        "parameters": [
                            model_name,
                            model_checksum,
                            json.dumps(model_definitions),
                            application_id or self._get_application_id(),
                            "active",
                            1,
                            json.dumps(
                                {
                                    "source": "model_registry",
                                    "timestamp": datetime.utcnow().isoformat(),
                                }
                            ),
                        ],
                    },
                )
            else:
                # PostgreSQL uses ON CONFLICT and $1 parameters
                workflow.add_node(
                    "SQLDatabaseNode",
                    "register_model",
                    {
                        "connection_string": db_url,
                        "database_type": database_type,
                        "query": """
                        INSERT INTO dataflow_model_registry
                        (model_name, model_checksum, model_definitions, application_id,
                         status, version, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (model_name, application_id)
                        DO UPDATE SET
                            model_checksum = EXCLUDED.model_checksum,
                            model_definitions = EXCLUDED.model_definitions,
                            updated_at = CURRENT_TIMESTAMP,
                            version = dataflow_model_registry.version + 1
                    """,
                        "parameters": [
                            model_name,
                            model_checksum,
                            json.dumps(model_definitions),
                            application_id or self._get_application_id(),
                            "active",
                            1,
                            json.dumps(
                                {
                                    "source": "model_registry",
                                    "timestamp": datetime.utcnow().isoformat(),
                                }
                            ),
                        ],
                    },
                )

            # ✅ FIX: Use LocalRuntime for registry operations to avoid async context issues
            init_runtime = LocalRuntime()
            results, _ = init_runtime.execute(workflow.build())

            if results.get("register_model", {}).get("error"):
                logger.error(
                    f"Failed to register model {model_name}: {results['register_model']['error']}"
                )
                return False

            logger.info(
                f"Successfully registered model {model_name} with checksum {model_checksum}"
            )
            return True

        except Exception as e:
            logger.error(f"Error registering model {model_name}: {e}")
            return False

    def discover_models(self) -> Dict[str, Dict[str, Any]]:
        """Discover models from model registry."""
        if not self._initialized:
            if not self.initialize():
                return {}

        workflow = WorkflowBuilder()

        # Get database-specific query
        db_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )

        # Import connection parser and detect database type
        from ..adapters.connection_parser import ConnectionParser

        database_type = ConnectionParser.detect_database_type(db_url)

        if database_type == "sqlite":
            # SQLite doesn't support DISTINCT ON, use window functions
            query = """
                SELECT model_name, model_definitions, model_checksum, registered_at, application_id
                FROM (
                    SELECT model_name, model_definitions, model_checksum, registered_at, application_id,
                           ROW_NUMBER() OVER (PARTITION BY model_name ORDER BY version DESC) as rn
                    FROM dataflow_model_registry
                    WHERE status = 'active'
                ) ranked
                WHERE rn = 1
                ORDER BY model_name
            """
        else:
            # PostgreSQL supports DISTINCT ON
            query = """
                WITH latest_models AS (
                    SELECT DISTINCT ON (model_name)
                        model_name,
                        model_definitions,
                        model_checksum,
                        registered_at,
                        application_id
                    FROM dataflow_model_registry
                    WHERE status = 'active'
                    ORDER BY model_name, version DESC
                )
                SELECT * FROM latest_models
                ORDER BY model_name
            """

        workflow.add_node(
            "SQLDatabaseNode",
            "discover",
            {
                "connection_string": db_url,
                "database_type": database_type,
                "query": query,
            },
        )

        # ✅ FIX: Use LocalRuntime for registry operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())

        models = {}
        data = self._extract_query_data(results, "discover")

        if data:
            for row in data:
                model_name = row["model_name"]
                # Handle both string and dict formats for model_definitions
                model_def = row["model_definitions"]
                if isinstance(model_def, str):
                    model_def = json.loads(model_def)

                # Normalize field types in discovered models
                if "fields" in model_def:
                    for field_name, field_info in model_def["fields"].items():
                        if "type" in field_info:
                            field_info["type"] = self._normalize_stored_field_type(
                                field_info["type"]
                            )

                models[model_name] = {
                    "definition": model_def,
                    "checksum": row["model_checksum"],
                    "registered_at": row["registered_at"],
                    "application_id": row["application_id"],
                }

        return models

    def sync_models(self, force: bool = False) -> Tuple[int, int]:
        """Sync models from migration history to DataFlow instance.

        Returns:
            Tuple of (models_added, models_updated)
        """
        discovered = self.discover_models()
        added = 0
        updated = 0

        for model_name, model_info in discovered.items():
            if model_name not in self.dataflow._models or force:
                # Reconstruct model class dynamically
                success = self._reconstruct_model(model_name, model_info)
                if success:
                    if model_name in self.dataflow._models:
                        updated += 1
                    else:
                        added += 1

        logger.info(f"Model sync complete: {added} added, {updated} updated")
        return added, updated

    def get_model_version(self, model_name: str) -> int:
        """Get latest version number for a model from registry."""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "SQLDatabaseNode",
            "get_version",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": """
                SELECT MAX(version) as max_version
                FROM dataflow_model_registry
                WHERE model_name = $1
                  AND status = 'active'
            """,
                "parameters": [model_name],
            },
        )

        # ✅ FIX: Use LocalRuntime for registry operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())

        data = self._extract_query_data(results, "get_version")
        if data and len(data) > 0:
            return data[0].get("max_version", 0) or 0

        return 0

    def get_model_history(self, model_name: str) -> List[Dict[str, Any]]:
        """Get version history for a model from registry."""
        workflow = WorkflowBuilder()

        # Get connection URL and detect database type
        from ..adapters.connection_parser import ConnectionParser

        connection_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        database_type = ConnectionParser.detect_database_type(connection_url)

        workflow.add_node(
            "SQLDatabaseNode",
            "get_history",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": """
                SELECT
                    version,
                    model_checksum,
                    model_definitions,
                    application_id,
                    registered_at,
                    updated_at,
                    status,
                    metadata
                FROM dataflow_model_registry
                WHERE model_name = $1
                ORDER BY version DESC
            """,
                "parameters": [model_name],
            },
        )

        # ✅ FIX: Use LocalRuntime for registry operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())

        history = []
        data = self._extract_query_data(results, "get_history")

        if data:
            for row in data:
                history.append(
                    {
                        "version": row["version"],
                        "checksum": row["model_checksum"],
                        "definitions": (
                            json.loads(row["model_definitions"])
                            if isinstance(row["model_definitions"], str)
                            else row["model_definitions"]
                        ),
                        "application_id": row["application_id"],
                        "registered_at": row["registered_at"],
                        "updated_at": row["updated_at"],
                        "status": row["status"],
                        "metadata": (
                            json.loads(row["metadata"])
                            if isinstance(row["metadata"], str)
                            else row["metadata"]
                        ),
                    }
                )

        return history

    def _model_exists_with_checksum(self, checksum: str) -> bool:
        """
        Check if model with this checksum already exists.

        Returns False if registry is not initialized (lazy registration mode).
        """
        # ✅ LAZY REGISTRATION FIX: Return False if not initialized
        # This prevents querying dataflow_model_registry before table exists
        if not self._initialized:
            logger.debug(
                "Registry not initialized, skipping checksum check "
                "(lazy registration mode)"
            )
            return False

        workflow = WorkflowBuilder()

        db_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )

        # Import connection parser and detect database type
        from ..adapters.connection_parser import ConnectionParser

        database_type = ConnectionParser.detect_database_type(db_url)

        if database_type == "sqlite":
            # SQLite doesn't have EXISTS as a direct return, use COUNT instead
            query = """
                SELECT (COUNT(*) > 0) as exists_result FROM dataflow_model_registry
                WHERE model_checksum = ? AND status = 'active'
            """
        else:
            query = """
                SELECT EXISTS (
                    SELECT 1 FROM dataflow_model_registry
                    WHERE model_checksum = $1
                      AND status = 'active'
                )
            """

        workflow.add_node(
            "SQLDatabaseNode",
            "check_checksum",
            {
                "connection_string": db_url,
                "database_type": database_type,
                "query": query,
                "parameters": [checksum],
            },
        )

        # ✅ FIX: Use LocalRuntime for registry operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())

        data = self._extract_query_data(results, "check_checksum")
        if data and len(data) > 0:
            # Handle different column names for different database types
            result = data[0]
            return result.get("exists", result.get("exists_result", False))

        return False

    def _normalize_field_type(self, field_type: Any) -> str:
        """Normalize Python type objects to simple string representations.

        This prevents 'Unknown field type <class str>' warnings by converting
        Python type objects to their simple names.
        """
        if isinstance(field_type, type):
            # Handle built-in types
            if field_type.__module__ == "builtins":
                return field_type.__name__
            else:
                # For non-builtin types, use module.name format
                return f"{field_type.__module__}.{field_type.__name__}"
        elif hasattr(field_type, "__name__"):
            # Handle other objects with __name__ attribute
            return field_type.__name__
        elif hasattr(field_type, "__origin__"):
            # Handle typing generics like List[str], Optional[int], etc.
            origin = field_type.__origin__
            if origin.__module__ == "builtins":
                return origin.__name__
            else:
                return f"{origin.__module__}.{origin.__name__}"
        else:
            # Fallback to string representation
            return str(field_type)

    def _normalize_stored_field_type(self, field_type_str: str) -> str:
        """Normalize stored field types from old format to new format.

        Converts "<class 'str'>" format to "str" format.
        """
        if not isinstance(field_type_str, str):
            return str(field_type_str)

        # Handle old <class 'name'> format
        if field_type_str.startswith("<class '") and field_type_str.endswith("'>"):
            # Extract the class name from <class 'name'>
            class_name = field_type_str[8:-2]  # Remove "<class '" and "'>"
            return class_name
        elif field_type_str.startswith('<class "') and field_type_str.endswith('">'):
            # Handle double quotes variant
            class_name = field_type_str[8:-2]  # Remove '<class "' and '">'
            return class_name
        else:
            # Already normalized or different format
            return field_type_str

    def _extract_model_metadata(self, model_class: type) -> Dict[str, Any]:
        """Extract metadata from a model class."""
        metadata = {
            "class_name": model_class.__name__,
            "module": (
                model_class.__module__ if hasattr(model_class, "__module__") else None
            ),
            "fields": {},
            "options": {},
        }

        # Extract field annotations
        if hasattr(model_class, "__annotations__"):
            for field_name, field_type in model_class.__annotations__.items():
                metadata["fields"][field_name] = {
                    "type": self._normalize_field_type(field_type),
                    "required": not hasattr(
                        model_class, field_name
                    ),  # Has default = not required
                }

                # Get default value if exists
                if hasattr(model_class, field_name):
                    default_value = getattr(model_class, field_name)
                    metadata["fields"][field_name]["default"] = (
                        self._make_json_serializable(default_value)
                    )
                    metadata["fields"][field_name]["required"] = False

        # Extract any additional metadata
        if hasattr(model_class, "__dataflow_meta__"):
            metadata["options"] = model_class.__dataflow_meta__

        return metadata

    def _get_application_id(self) -> str:
        """Get or generate an application ID."""
        if hasattr(self.dataflow.config, "application_id"):
            return self.dataflow.config.application_id

        # Generate a stable ID based on the DataFlow instance
        return f"dataflow_{id(self.dataflow) % 1000000}"

    def _reconstruct_model(self, model_name: str, model_info: Dict[str, Any]) -> bool:
        """Reconstruct model class from stored definition with rollback on failure."""
        # Store original state for rollback
        original_models = self.dataflow._models.copy()
        original_registered = self.dataflow._registered_models.copy()
        original_fields = self.dataflow._model_fields.copy()

        try:
            # Extract definition from model_info structure
            definition = model_info.get(
                "definition", model_info
            )  # Handle both structures

            # Create dynamic class with stored fields
            fields = definition.get("fields", {})
            options = definition.get("options", {})

            # Validate that we have fields
            if not fields:
                logger.warning(
                    f"Model {model_name} has no fields in definition, skipping reconstruction"
                )
                return False

            # Build class attributes
            attrs = {"__dataflow__": options}

            # Add field annotations
            annotations = {}
            type_map = {
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "datetime": datetime,
                "date": datetime,
                "time": datetime,
                "json": dict,
                "jsonb": dict,
                "list": list,
                "dict": dict,
                "uuid": str,
                "decimal": float,
                "text": str,
                "varchar": str,
                "char": str,
                "integer": int,
                "bigint": int,
                "smallint": int,
                "numeric": float,
                "real": float,
                "double": float,
                "boolean": bool,
                "timestamp": datetime,
                "timestamptz": datetime,
                "array": list,
            }

            for field_name, field_info in fields.items():
                field_type = field_info.get("type", "str")

                # Normalize field type if it's in old <class 'name'> format
                field_type = self._normalize_stored_field_type(field_type)

                # Validate and warn for unknown types
                if field_type not in type_map:
                    logger.warning(
                        f"Unknown field type '{field_type}' for {model_name}.{field_name}, "
                        f"defaulting to string. Known types: {list(type_map.keys())}"
                    )

                python_type = type_map.get(field_type, str)
                annotations[field_name] = python_type

                # Set default value if provided
                if "default" in field_info:
                    try:
                        # Handle callable defaults
                        default_value = field_info["default"]
                        if (
                            isinstance(default_value, str)
                            and default_value == "<function>"
                        ):
                            # Skip function defaults in reconstruction
                            continue
                        attrs[field_name] = default_value
                    except Exception as e:
                        logger.warning(
                            f"Could not set default for {model_name}.{field_name}: {e}"
                        )

            attrs["__annotations__"] = annotations

            # Create the class dynamically
            model_class = type(model_name, (), attrs)

            # Test instantiation before registering
            try:
                test_instance = model_class()
                del test_instance  # Clean up
            except Exception as e:
                raise ValueError(
                    f"Reconstructed model {model_name} failed instantiation test: {e}"
                )

            # Register with DataFlow
            self.dataflow.model(model_class)

            logger.info(
                f"Successfully reconstructed model {model_name} with "
                f"{len(fields)} fields from {model_info.get('application_id', 'unknown')} "
                f"application"
            )

            return True

        except Exception as e:
            # Rollback on failure
            logger.error(
                f"Failed to reconstruct model {model_name}: {e}. "
                f"Rolling back DataFlow state."
            )

            self.dataflow._models = original_models
            self.dataflow._registered_models = original_registered
            self.dataflow._model_fields = original_fields

            return False

    def validate_consistency(self) -> Dict[str, List[str]]:
        """Validate model consistency across applications."""
        issues = {}

        # Get all unique model names
        workflow = WorkflowBuilder()

        # Get connection URL and detect database type
        from ..adapters.connection_parser import ConnectionParser

        connection_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        database_type = ConnectionParser.detect_database_type(connection_url)

        workflow.add_node(
            "SQLDatabaseNode",
            "get_models",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": """
                SELECT DISTINCT model_name
                FROM dataflow_model_registry
                WHERE status = 'active'
            """,
            },
        )

        # ✅ FIX: Use LocalRuntime for registry operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())

        data = self._extract_query_data(results, "get_models")
        if data:
            for row in data:
                model_name = row["model_name"]
                checksums = self._get_model_checksums_by_app(model_name)

                # Check for inconsistencies
                unique_checksums = set(checksums.values())
                if len(unique_checksums) > 1:
                    issues[model_name] = [
                        f"Model definition mismatch between applications: {checksums}"
                    ]

        return issues

    def _get_model_checksums_by_app(self, model_name: str) -> Dict[str, str]:
        """Get model checksums grouped by application."""
        workflow = WorkflowBuilder()

        # Get connection URL and detect database type
        from ..adapters.connection_parser import ConnectionParser

        connection_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        database_type = ConnectionParser.detect_database_type(connection_url)

        workflow.add_node(
            "SQLDatabaseNode",
            "get_checksums",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": """
                WITH latest_by_app AS (
                    SELECT DISTINCT ON (application_id)
                        application_id,
                        model_checksum
                    FROM dataflow_model_registry
                    WHERE model_name = $1
                      AND status = 'active'
                    ORDER BY application_id, version DESC
                )
                SELECT application_id, model_checksum as checksum
                FROM latest_by_app
            """,
                "parameters": [model_name],
            },
        )

        # ✅ FIX: Use LocalRuntime for registry operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())

        checksums = {}
        data = self._extract_query_data(results, "get_checksums")
        if data:
            for row in data:
                checksums[row["application_id"]] = row["checksum"]

        return checksums

    def get_latest_model_for_app(
        self, model_name: str, application_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get latest model definition for a specific application."""
        workflow = WorkflowBuilder()

        # Get connection URL and detect database type
        from ..adapters.connection_parser import ConnectionParser

        connection_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        database_type = ConnectionParser.detect_database_type(connection_url)

        workflow.add_node(
            "SQLDatabaseNode",
            "get_model",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": """
                SELECT model_definitions
                FROM dataflow_model_registry
                WHERE model_name = $1
                  AND application_id = $2
                  AND status = 'active'
                ORDER BY version DESC
                LIMIT 1
            """,
                "parameters": [model_name, application_id],
            },
        )

        # ✅ FIX: Use LocalRuntime for registry operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())

        data = self._extract_query_data(results, "get_model")
        if data and len(data) > 0:
            model_def = data[0]["model_definitions"]
            if isinstance(model_def, str):
                return json.loads(model_def)
            return model_def

        return None

    def list_applications(self) -> List[str]:
        """List all applications that have registered models."""
        workflow = WorkflowBuilder()

        # Get connection URL and detect database type
        from ..adapters.connection_parser import ConnectionParser

        connection_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        database_type = ConnectionParser.detect_database_type(connection_url)

        workflow.add_node(
            "SQLDatabaseNode",
            "list_apps",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": """
                SELECT DISTINCT application_id
                FROM dataflow_model_registry
                WHERE application_id IS NOT NULL
                  AND status = 'active'
                ORDER BY application_id
            """,
            },
        )

        # ✅ FIX: Use LocalRuntime for registry operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())
        data = self._extract_query_data(results, "list_apps")

        if data:
            return [row["application_id"] for row in data]

        return []

    def get_models_by_application(self, application_id: str) -> List[Dict[str, Any]]:
        """Get all models registered by a specific application."""
        workflow = WorkflowBuilder()

        # Get connection URL and detect database type
        from ..adapters.connection_parser import ConnectionParser

        connection_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        database_type = ConnectionParser.detect_database_type(connection_url)

        workflow.add_node(
            "SQLDatabaseNode",
            "get_by_app",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": """
                WITH latest_models AS (
                    SELECT DISTINCT ON (model_name)
                        model_name,
                        model_checksum,
                        model_definitions,
                        version,
                        registered_at,
                        updated_at
                    FROM dataflow_model_registry
                    WHERE application_id = $1
                      AND status = 'active'
                    ORDER BY model_name, version DESC
                )
                SELECT * FROM latest_models
                ORDER BY model_name
            """,
                "parameters": [application_id],
            },
        )

        # ✅ FIX: Use LocalRuntime for registry operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())
        data = self._extract_query_data(results, "get_by_app")

        models = []
        if data:
            for row in data:
                models.append(
                    {
                        "model_name": row["model_name"],
                        "checksum": row["model_checksum"],
                        "definitions": (
                            json.loads(row["model_definitions"])
                            if isinstance(row["model_definitions"], str)
                            else row["model_definitions"]
                        ),
                        "version": row["version"],
                        "registered_at": row["registered_at"],
                        "updated_at": row["updated_at"],
                    }
                )

        return models

    def get_model_by_checksum(self, checksum: str) -> Optional[Dict[str, Any]]:
        """Get a specific model by its checksum."""
        workflow = WorkflowBuilder()

        # Get connection URL and detect database type
        from ..adapters.connection_parser import ConnectionParser

        connection_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        database_type = ConnectionParser.detect_database_type(connection_url)

        workflow.add_node(
            "SQLDatabaseNode",
            "get_by_checksum",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": """
                SELECT
                    model_name,
                    model_definitions,
                    application_id,
                    registered_at,
                    version,
                    status
                FROM dataflow_model_registry
                WHERE model_checksum = $1
                  AND status = 'active'
                ORDER BY version DESC
                LIMIT 1
            """,
                "parameters": [checksum],
            },
        )

        # ✅ FIX: Use LocalRuntime for registry operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())
        data = self._extract_query_data(results, "get_by_checksum")

        if data and len(data) > 0:
            row = data[0]
            return {
                "model_name": row["model_name"],
                "definitions": (
                    json.loads(row["model_definitions"])
                    if isinstance(row["model_definitions"], str)
                    else row["model_definitions"]
                ),
                "application_id": row["application_id"],
                "registered_at": row["registered_at"],
                "version": row["version"],
                "status": row["status"],
            }

        return None

    def cleanup_old_versions(self, model_name: str, keep_versions: int = 5):
        """Clean up old versions of a model, keeping only the most recent ones."""
        workflow = WorkflowBuilder()

        # Get connection URL and detect database type
        from ..adapters.connection_parser import ConnectionParser

        connection_url = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        database_type = ConnectionParser.detect_database_type(connection_url)

        workflow.add_node(
            "SQLDatabaseNode",
            "cleanup",
            {
                "connection_string": connection_url,
                "database_type": database_type,
                "query": """
                UPDATE dataflow_model_registry
                SET status = 'archived'
                WHERE model_name = $1
                  AND version < (
                      SELECT MAX(version) - $2 + 1
                      FROM dataflow_model_registry
                      WHERE model_name = $1
                  )
                  AND status = 'active'
            """,
                "parameters": [model_name, keep_versions],
            },
        )

        # ✅ FIX: Use LocalRuntime for registry operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())

        if results.get("cleanup", {}).get("error"):
            logger.error(
                f"Failed to cleanup old versions for {model_name}: {results['cleanup']['error']}"
            )
            return False

        logger.info(
            f"Cleaned up old versions for model {model_name}, keeping {keep_versions} most recent"
        )
        return True

    @contextmanager
    def transaction(self):
        """Context manager for transactional operations."""
        if self._transaction_manager:
            with self._transaction_manager.transaction():
                yield
        else:
            # No transaction support, just yield
            yield
