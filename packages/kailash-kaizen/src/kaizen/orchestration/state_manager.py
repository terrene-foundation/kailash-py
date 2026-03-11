"""
OrchestrationStateManager - DataFlow-based workflow state persistence.

Provides persistent state tracking for multi-agent workflow orchestration using DataFlow.
Auto-generates 33 CRUD nodes (11 per model × 3 models) via DataFlow integration.

Architecture:
    OrchestrationStateManager
    ├── DataFlow instance (one per database)
    ├── AsyncLocalRuntime (async execution)
    └── 3 Models → 33 Auto-Generated Nodes
        ├── WorkflowState (11 nodes)
        ├── AgentExecutionRecord (11 nodes)
        └── WorkflowCheckpoint (11 nodes)

Key Features:
- Automatic node generation from models (no manual CRUD code)
- String-based IDs preserved (no UUID conversion)
- JSON field parsing (metadata, result fields stored as strings)
- Gzip compression for checkpoint snapshots
- Error handling with descriptive messages
- Async-first for OrchestrationRuntime integration

Usage:
    from kaizen.orchestration.state_manager import OrchestrationStateManager

    # Initialize with database connection
    state_mgr = OrchestrationStateManager(
        connection_string="postgresql://user:pass@localhost:5432/orchestration"
    )

    # Save workflow state
    workflow_state_id = await state_mgr.save_workflow_state(
        workflow_id="wf_abc123",
        status="RUNNING",
        metadata={"total_tasks": 5}
    )

    # Load workflow state with related records
    state = await state_mgr.load_workflow_state("wf_abc123")

    # Create checkpoint
    checkpoint_id = await state_mgr.save_checkpoint(
        workflow_id="wf_abc123",
        checkpoint_data={"agents": [...], "state": {...}}
    )

Author: Kaizen Framework Team
Created: 2025-11-17 (TODO-178, Phase 2: DataFlow Integration)
Reference: DataFlow specialist guidance on state persistence patterns
"""

import gzip
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

# SQLAlchemy imports for DataFlow model definitions
try:
    from sqlalchemy import Column, DateTime, Float, Integer, String, Text

    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False

# DataFlow imports
try:
    from dataflow import DataFlow

    DATAFLOW_AVAILABLE = True
except ImportError:
    DATAFLOW_AVAILABLE = False

# Kailash runtime imports
try:
    from kailash.runtime import AsyncLocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    RUNTIME_AVAILABLE = True
except ImportError:
    RUNTIME_AVAILABLE = False

# Model imports
from kaizen.orchestration.models import (
    WORKFLOW_STATUS_VALUES,
    AgentExecutionRecord,
    WorkflowCheckpoint,
    WorkflowState,
    validate_agent_execution_record,
    validate_workflow_checkpoint,
    validate_workflow_state,
)

logger = logging.getLogger(__name__)


class StateManagerError(Exception):
    """Base exception for OrchestrationStateManager errors."""

    pass


class WorkflowNotFoundError(StateManagerError):
    """Workflow state not found in database."""

    pass


class CheckpointNotFoundError(StateManagerError):
    """Checkpoint not found in database."""

    pass


class DatabaseConnectionError(StateManagerError):
    """Database connection or execution error."""

    pass


class OrchestrationStateManager:
    """
    DataFlow-based state manager for OrchestrationRuntime workflows.

    Provides persistent storage for:
    - Workflow execution state (WorkflowState model)
    - Agent task execution records (AgentExecutionRecord model)
    - Incremental checkpoints (WorkflowCheckpoint model)

    DataFlow Integration:
    - Automatically generates 33 CRUD nodes (11 per model)
    - Uses AsyncLocalRuntime for async execution
    - No manual SQL required - all operations via workflow nodes
    - String IDs preserved throughout the stack

    Attributes:
        db: DataFlow instance (shared across all operations)
        runtime: AsyncLocalRuntime for workflow execution
        db_instance_name: Instance name for multi-instance isolation
        connection_string: Database connection URL
    """

    def __init__(
        self,
        connection_string: str,
        db_instance_name: str = "orchestration_db",
        auto_migrate: bool = True,
        enable_caching: bool = True,
        enable_metrics: bool = True,
        migration_enabled: bool = True,  # FIXED: Enable migrations for table creation
    ):
        """
        Initialize OrchestrationStateManager with DataFlow backend.

        Args:
            connection_string: PostgreSQL/MySQL/SQLite connection URL
                Examples:
                - "postgresql://user:pass@localhost:5432/orchestration"
                - "sqlite:///orchestration.db"
            db_instance_name: DataFlow instance name (for multi-instance isolation)
            auto_migrate: Auto-create tables if missing (safe - preserves data)
            enable_caching: Enable query result caching
            enable_metrics: Enable performance metrics
            migration_enabled: Enable DataFlow migration system (default: True)

        Raises:
            ImportError: If dataflow or kailash not installed
            DatabaseConnectionError: If database connection fails
        """
        if not DATAFLOW_AVAILABLE:
            raise ImportError(
                "DataFlow not installed. Run: pip install kailash-dataflow"
            )

        if not RUNTIME_AVAILABLE:
            raise ImportError("Kailash runtime not installed. Run: pip install kailash")

        self.connection_string = connection_string
        self.db_instance_name = db_instance_name

        # Initialize DataFlow instance with auto-migration enabled
        # Models use Python type hints pattern (id: str, name: str, etc.)
        # DataFlow will create tables automatically on first access
        try:
            self.db = DataFlow(
                database_url=connection_string,
                auto_migrate=True,  # Create tables automatically
                migration_enabled=migration_enabled,  # Enable migration system
                enable_model_persistence=False,  # Disable cross-session persistence
                enable_caching=enable_caching,
                enable_metrics=enable_metrics,
            )
        except Exception as e:
            raise DatabaseConnectionError(f"Failed to initialize DataFlow: {e}") from e

        # Eager connection validation - verify database is reachable
        # This ensures errors are caught at initialization time, not first use
        self._validate_connection()

        # Initialize AsyncLocalRuntime for async workflow execution
        self.runtime = AsyncLocalRuntime(
            debug=False,
            connection_validation="warn",  # Less strict for production
        )

        # Register models with DataFlow (generates 33 nodes automatically)
        # Tables will be created automatically on first access via auto_migrate=True
        self._register_models()

        logger.info(
            f"OrchestrationStateManager initialized: "
            f"db_instance={db_instance_name}, "
            f"connection={connection_string}"
        )

    def _register_models(self):
        """
        Register DataFlow models using Python type hints.

        Generates 33 nodes total (11 per model):
        - WorkflowStateModel: 11 nodes (Create, Read, Update, Delete, List, Upsert, Count, BulkCreate, BulkUpdate, BulkDelete, BulkUpsert)
        - AgentExecutionRecordModel: 11 nodes
        - WorkflowCheckpointModel: 11 nodes

        DataFlow Pattern (v0.9.0+):
        - Use Python type hints: `id: str`, `name: str`, `created_at: datetime`
        - NOT SQLAlchemy Column objects: `id = Column(String, primary_key=True)`
        - Tables created automatically via auto_migrate=True on first access
        """

        # Register WorkflowState model
        @self.db.model
        class WorkflowStateModel:
            # Python type hints - DataFlow infers SQL types
            id: str
            workflow_id: str
            status: str
            start_time: datetime
            end_time: Optional[datetime] = None
            runtime_id: str
            routing_strategy: str
            max_concurrent: int = 10
            total_tasks: int = 0
            completed_tasks: int = 0
            failed_tasks: int = 0
            success_rate: float = 0.0
            error_message: Optional[str] = None
            error_type: Optional[str] = None
            metadata: Optional[dict] = (
                None  # JSON field - DataFlow handles serialization
            )

        # Register AgentExecutionRecord model
        @self.db.model
        class AgentExecutionRecordModel:
            # Python type hints - DataFlow infers SQL types
            id: str
            workflow_state_id: str  # Foreign key to WorkflowState
            agent_id: str
            agent_type: str
            task_description: str
            task_index: int
            status: str
            retry_count: int = 0
            max_retries: int = 3
            start_time: datetime
            end_time: Optional[datetime] = None
            execution_time_seconds: float = 0.0
            result: Optional[dict] = None  # JSON field - DataFlow handles serialization
            error: Optional[str] = None
            error_stack_trace: Optional[str] = None
            cost_usd: float = 0.0
            budget_remaining_usd: float = 0.0

        # Register WorkflowCheckpoint model
        @self.db.model
        class WorkflowCheckpointModel:
            # Python type hints - DataFlow infers SQL types
            id: str
            workflow_state_id: str  # Foreign key to WorkflowState
            checkpoint_number: int
            checkpoint_type: str
            snapshot_data: Optional[dict] = (
                None  # JSON field - DataFlow handles serialization
            )
            created_at_timestamp: datetime
            size_bytes: int = 0
            compression_ratio: float = 1.0
            parent_checkpoint_id: Optional[str] = None

        logger.info(
            "DataFlow models registered: 33 nodes generated "
            "(WorkflowStateModel, AgentExecutionRecordModel, WorkflowCheckpointModel)"
        )

    def _validate_connection(self):
        """
        Validate database connection immediately after initialization.

        This method performs eager validation to catch connection errors early,
        rather than waiting for first database operation to fail.

        Raises:
            DatabaseConnectionError: If database connection fails
        """
        # Test connection by attempting a simple query
        # Use DataFlow's connection pool directly to avoid creating workflows
        try:
            if "postgresql" in self.connection_string.lower():
                # PostgreSQL validation
                from urllib.parse import urlparse

                import psycopg2

                parsed = urlparse(self.connection_string)
                conn = psycopg2.connect(
                    host=parsed.hostname,
                    port=parsed.port or 5432,
                    database=parsed.path.lstrip("/"),
                    user=parsed.username,
                    password=parsed.password,
                    connect_timeout=5,  # Fail fast
                )
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                conn.close()
                logger.debug("PostgreSQL connection validated successfully")

            elif "mysql" in self.connection_string.lower():
                # MySQL validation
                from urllib.parse import urlparse

                import pymysql

                parsed = urlparse(self.connection_string)
                conn = pymysql.connect(
                    host=parsed.hostname,
                    port=parsed.port or 3306,
                    database=parsed.path.lstrip("/"),
                    user=parsed.username,
                    password=parsed.password,
                    connect_timeout=5,
                )
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                conn.close()
                logger.debug("MySQL connection validated successfully")

            elif "sqlite" in self.connection_string.lower():
                # SQLite validation (always succeeds - file-based)
                import os
                import sqlite3

                db_path = self.connection_string.replace("sqlite:///", "")
                # Ensure directory exists
                db_dir = os.path.dirname(db_path)
                if db_dir and not os.path.exists(db_dir):
                    raise DatabaseConnectionError(
                        f"SQLite database directory does not exist: {db_dir}"
                    )
                # Test connection
                conn = sqlite3.connect(db_path, timeout=5)
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                conn.close()
                logger.debug("SQLite connection validated successfully")

            else:
                logger.warning(
                    f"Unknown database type in connection string, skipping validation: "
                    f"{self.connection_string}"
                )

        except ImportError as e:
            # Missing database driver - let it fail later with better error
            logger.warning(f"Database driver not installed, skipping validation: {e}")
        except Exception as e:
            logger.error(f"Database connection validation failed: {e}")
            raise DatabaseConnectionError(f"Failed to connect to database: {e}") from e

    async def save_workflow_state(
        self,
        workflow_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
        runtime_id: Optional[str] = None,
        routing_strategy: str = "semantic",
        max_concurrent: int = 10,
        total_tasks: int = 0,
    ) -> str:
        """
        Create or update WorkflowState record.

        Uses WorkflowStateUpsertNode for atomic create-or-update operation.

        Args:
            workflow_id: Business workflow identifier
            status: Workflow status (PENDING, RUNNING, COMPLETED, FAILED, CANCELLED)
            metadata: Flexible JSON metadata (will be serialized)
            runtime_id: OrchestrationRuntime instance identifier
            routing_strategy: Task routing strategy (semantic, round-robin, etc.)
            max_concurrent: Maximum concurrent agent executions
            total_tasks: Total number of tasks in workflow

        Returns:
            workflow_state_id (str): Primary key of created/updated record

        Raises:
            ValueError: If status is invalid
            DatabaseConnectionError: If database operation fails
        """
        # Validate status
        if status not in WORKFLOW_STATUS_VALUES:
            raise ValueError(
                f"Invalid status: {status}. Must be one of {WORKFLOW_STATUS_VALUES}"
            )

        # Generate IDs
        workflow_state_id = workflow_id  # Use workflow_id as primary key for upsert
        if runtime_id is None:
            runtime_id = f"runtime_{uuid.uuid4().hex[:8]}"

        # Prepare data
        # NOTE: metadata stored as dict (DataFlow serializes to JSON/TEXT)
        # Use empty dict for None to maintain backward compatibility
        data = {
            "id": workflow_state_id,
            "workflow_id": workflow_id,
            "status": status,
            "start_time": datetime.now().isoformat(),
            "runtime_id": runtime_id,
            "routing_strategy": routing_strategy,
            "max_concurrent": max_concurrent,
            "total_tasks": total_tasks,
            "metadata": metadata if metadata is not None else {},
        }

        # Validate data
        validate_workflow_state(data)

        # Build workflow with UpsertNode
        # DataFlow v0.9.0+ UpsertNode requires ONLY: db_instance, model_name, where, update, create
        # The update and create dicts contain the actual data fields
        workflow = WorkflowBuilder()

        # Prepare update dict (all fields except id)
        update_data = {k: v for k, v in data.items() if k != "id"}
        # Prepare create dict (all fields including id)
        create_data = {"id": data["id"], **update_data}

        # CRITICAL: Only pass db_instance, model_name, where, update, create
        # Do NOT pass individual data fields like id, workflow_id, status, etc.
        workflow.add_node(
            "WorkflowStateModelUpsertNode",
            "upsert_state",
            {
                "db_instance": self.db_instance_name,
                "model_name": "WorkflowStateModel",
                "where": {"id": data["id"]},  # Identifies record to upsert
                "update": update_data,  # Fields to update if record exists
                "create": create_data,  # All fields if record doesn't exist
            },
        )

        # Execute workflow
        try:
            results, run_id = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Access result (DataFlow pattern: results[node_id]["result"])
            result = results.get("upsert_state", {})
            if isinstance(result, dict) and "result" in result:
                actual_id = result["result"]
            else:
                actual_id = workflow_state_id  # Fallback to input ID

            logger.info(
                f"Workflow state saved: workflow_id={workflow_id}, "
                f"status={status}, state_id={actual_id}"
            )

            return actual_id

        except Exception as e:
            logger.error(f"Failed to save workflow state: {e}")
            raise DatabaseConnectionError(
                f"Failed to save workflow state for {workflow_id}: {e}"
            ) from e

    async def load_workflow_state(
        self, workflow_id: str, include_records: bool = True
    ) -> Dict[str, Any]:
        """
        Load WorkflowState by workflow_id with optional related records.

        Uses WorkflowStateReadNode + AgentExecutionRecordListNode for loading.

        Args:
            workflow_id: Workflow identifier to load
            include_records: Include related AgentExecutionRecords (default: True)

        Returns:
            Dict containing:
            - workflow_state: WorkflowState data
            - agent_records: List of AgentExecutionRecord data (if include_records=True)

        Raises:
            WorkflowNotFoundError: If workflow not found
            DatabaseConnectionError: If database operation fails
        """
        workflow = WorkflowBuilder()

        # Read workflow state by ID
        workflow.add_node(
            "WorkflowStateModelReadNode",
            "read_state",
            {
                "db_instance": self.db_instance_name,
                "model_name": "WorkflowStateModel",
                "id": workflow_id,
            },
        )

        # Optionally load related agent records
        if include_records:
            workflow.add_node(
                "AgentExecutionRecordModelListNode",
                "list_records",
                {
                    "db_instance": self.db_instance_name,
                    "model_name": "AgentExecutionRecordModel",
                    "filter": {"workflow_state_id": workflow_id},
                    "sort": [{"field": "task_index", "order": "asc"}],
                },
            )

        # Execute workflow
        try:
            results, run_id = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Parse workflow state
            state_result = results.get("read_state", {})
            if isinstance(state_result, dict) and "result" in state_result:
                workflow_state = state_result["result"]
            else:
                workflow_state = state_result

            # Check if workflow exists
            if not workflow_state:
                raise WorkflowNotFoundError(f"Workflow not found: {workflow_id}")

            # Parse metadata JSON field (DataFlow returns as string!)
            # Handle None from database (Optional[dict] field)
            metadata = workflow_state.get("metadata")
            if metadata is None:
                workflow_state["metadata"] = {}
            elif isinstance(metadata, str):
                try:
                    workflow_state["metadata"] = json.loads(metadata)
                except json.JSONDecodeError:
                    workflow_state["metadata"] = {}

            # Parse agent records if included
            agent_records = []
            if include_records:
                records_result = results.get("list_records", {})
                if isinstance(records_result, dict) and "result" in records_result:
                    agent_records = records_result["result"].get("records", [])
                elif isinstance(records_result, dict) and "records" in records_result:
                    agent_records = records_result["records"]
                elif isinstance(records_result, list):
                    agent_records = records_result
                else:
                    logger.warning(
                        f"Unexpected records_result format: {type(records_result)}"
                    )
                    agent_records = []

                # Ensure agent_records is a list
                if not isinstance(agent_records, list):
                    logger.warning(
                        f"Agent records is not a list: {type(agent_records)}"
                    )
                    agent_records = []

                # Parse JSON fields in each record
                for record in agent_records:
                    # Ensure record is a dict
                    if not isinstance(record, dict):
                        logger.warning(f"Skipping non-dict record: {type(record)}")
                        continue

                    # Handle None from database (Optional[dict] field)
                    result = record.get("result")
                    if result is None:
                        record["result"] = {}
                    elif isinstance(result, str):
                        try:
                            record["result"] = json.loads(result)
                        except json.JSONDecodeError:
                            record["result"] = {}

                # DataFlow ListNode sort fix requires Core SDK update
                # Keep Python-level sorting for backward compatibility
                agent_records.sort(
                    key=lambda r: r.get("task_index", 0) if isinstance(r, dict) else 0
                )

            logger.info(
                f"Workflow state loaded: workflow_id={workflow_id}, "
                f"records={len(agent_records)}"
            )

            return {
                "workflow_state": workflow_state,
                "agent_records": agent_records,
            }

        except WorkflowNotFoundError:
            raise
        except Exception as e:
            # Check if this is a DataFlow record-not-found error
            error_msg = str(e)
            if "not found" in error_msg.lower() and workflow_id in error_msg:
                logger.warning(f"Workflow state not found: {workflow_id}")
                raise WorkflowNotFoundError(f"Workflow not found: {workflow_id}") from e

            logger.error(f"Failed to load workflow state: {e}")
            raise DatabaseConnectionError(
                f"Failed to load workflow state for {workflow_id}: {e}"
            ) from e

    async def save_checkpoint(
        self,
        workflow_id: str,
        checkpoint_data: Dict[str, Any],
        checkpoint_type: str = "AUTO",
        parent_checkpoint_id: Optional[str] = None,
    ) -> str:
        """
        Create WorkflowCheckpoint with gzip compression.

        Uses WorkflowCheckpointCreateNode for checkpoint creation.

        Args:
            workflow_id: Workflow identifier
            checkpoint_data: Checkpoint payload (will be compressed)
            checkpoint_type: AUTO, MANUAL, ERROR_RECOVERY
            parent_checkpoint_id: Previous checkpoint ID for incremental chain

        Returns:
            checkpoint_id (str): Primary key of created checkpoint

        Raises:
            ValueError: If checkpoint_type is invalid
            DatabaseConnectionError: If database operation fails
        """
        # Validate checkpoint type
        from kaizen.orchestration.models import CHECKPOINT_TYPE_VALUES

        if checkpoint_type not in CHECKPOINT_TYPE_VALUES:
            raise ValueError(
                f"Invalid checkpoint_type: {checkpoint_type}. "
                f"Must be one of {CHECKPOINT_TYPE_VALUES}"
            )

        # Generate checkpoint ID
        checkpoint_id = f"cp_{workflow_id}_{uuid.uuid4().hex[:8]}"

        # Get next checkpoint number
        checkpoint_number = await self._get_next_checkpoint_number(workflow_id)

        # Compress checkpoint data
        json_str = json.dumps(checkpoint_data)
        compressed = gzip.compress(json_str.encode("utf-8"))
        compressed_hex = compressed.hex()  # Store as hex string

        # Calculate compression metrics
        size_bytes = len(compressed)
        compression_ratio = (
            len(compressed) / len(json_str) if len(json_str) > 0 else 1.0
        )

        # Prepare data
        data = {
            "id": checkpoint_id,
            "workflow_state_id": workflow_id,
            "checkpoint_number": checkpoint_number,
            "checkpoint_type": checkpoint_type,
            "snapshot_data": {"compressed": compressed_hex},
            "created_at_timestamp": datetime.now().isoformat(),
            "size_bytes": size_bytes,
            "compression_ratio": compression_ratio,
            "parent_checkpoint_id": parent_checkpoint_id,
        }

        # Validate data
        validate_workflow_checkpoint(data)

        # Build workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "WorkflowCheckpointModelCreateNode",
            "create_checkpoint",
            {
                "db_instance": self.db_instance_name,
                "model_name": "WorkflowCheckpointModel",
                **data,
            },
        )

        # Execute workflow
        try:
            results, run_id = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            logger.info(
                f"Checkpoint saved: checkpoint_id={checkpoint_id}, "
                f"workflow_id={workflow_id}, number={checkpoint_number}, "
                f"size={size_bytes}B, ratio={compression_ratio:.2f}"
            )

            return checkpoint_id

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            raise DatabaseConnectionError(
                f"Failed to save checkpoint for {workflow_id}: {e}"
            ) from e

    async def load_checkpoint(self, checkpoint_id: str) -> Dict[str, Any]:
        """
        Load WorkflowCheckpoint and decompress snapshot data.

        Uses WorkflowCheckpointReadNode for loading.

        Args:
            checkpoint_id: Checkpoint identifier

        Returns:
            Decompressed checkpoint data (dict)

        Raises:
            CheckpointNotFoundError: If checkpoint not found
            DatabaseConnectionError: If database operation fails
        """
        workflow = WorkflowBuilder()

        # Read checkpoint by ID
        workflow.add_node(
            "WorkflowCheckpointModelReadNode",
            "read_checkpoint",
            {
                "db_instance": self.db_instance_name,
                "model_name": "WorkflowCheckpointModel",
                "id": checkpoint_id,
            },
        )

        # Execute workflow
        try:
            results, run_id = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Parse checkpoint
            checkpoint_result = results.get("read_checkpoint", {})
            if isinstance(checkpoint_result, dict) and "result" in checkpoint_result:
                checkpoint = checkpoint_result["result"]
            else:
                checkpoint = checkpoint_result

            # Check if checkpoint exists
            if not checkpoint:
                raise CheckpointNotFoundError(f"Checkpoint not found: {checkpoint_id}")

            # Parse snapshot_data JSON field
            # Handle None from database (Optional[dict] field)
            snapshot_data = checkpoint.get("snapshot_data")
            if snapshot_data is None:
                snapshot_data = {}
            elif isinstance(snapshot_data, str):
                try:
                    snapshot_data = json.loads(snapshot_data)
                except json.JSONDecodeError:
                    snapshot_data = {}

            # Decompress data
            compressed_hex = snapshot_data.get("compressed", "")
            if compressed_hex:
                try:
                    compressed = bytes.fromhex(compressed_hex)
                    decompressed = gzip.decompress(compressed)
                    checkpoint_data = json.loads(decompressed.decode("utf-8"))
                except (ValueError, gzip.BadGzipFile, json.JSONDecodeError) as e:
                    logger.error(f"Failed to decompress checkpoint data: {e}")
                    checkpoint_data = {}
            else:
                checkpoint_data = {}

            logger.info(f"Checkpoint loaded: checkpoint_id={checkpoint_id}")

            return checkpoint_data

        except CheckpointNotFoundError:
            raise
        except Exception as e:
            # Check if this is a DataFlow record-not-found error
            error_msg = str(e)
            if "not found" in error_msg.lower() and checkpoint_id in error_msg:
                logger.warning(f"Checkpoint not found: {checkpoint_id}")
                raise CheckpointNotFoundError(
                    f"Checkpoint not found: {checkpoint_id}"
                ) from e

            logger.error(f"Failed to load checkpoint: {e}")
            raise DatabaseConnectionError(
                f"Failed to load checkpoint {checkpoint_id}: {e}"
            ) from e

    async def list_active_workflows(self) -> List[Dict[str, Any]]:
        """
        Query WorkflowState with status IN (PENDING, RUNNING).

        Uses WorkflowStateListNode with filter query.

        Returns:
            List of active workflow states (dicts)

        Raises:
            DatabaseConnectionError: If database operation fails
        """
        workflow = WorkflowBuilder()

        # List workflows with active status
        workflow.add_node(
            "WorkflowStateModelListNode",
            "list_active",
            {
                "db_instance": self.db_instance_name,
                "model_name": "WorkflowStateModel",
                "filter": {"status": {"$in": ["PENDING", "RUNNING"]}},
                "sort": [{"field": "start_time", "order": "desc"}],
            },
        )

        # Execute workflow
        try:
            results, run_id = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Parse results with robust handling
            list_result = results.get("list_active", {})
            if isinstance(list_result, dict) and "result" in list_result:
                workflows = list_result["result"].get("records", [])
            elif isinstance(list_result, dict) and "records" in list_result:
                workflows = list_result["records"]
            elif isinstance(list_result, list):
                workflows = list_result
            else:
                # Unexpected format - log and return empty list
                logger.warning(f"Unexpected list_result format: {type(list_result)}")
                workflows = []

            # Ensure workflows is a list
            if not isinstance(workflows, list):
                logger.warning(f"Workflows is not a list: {type(workflows)}")
                workflows = []

            # Parse metadata JSON fields
            for workflow_state in workflows:
                # Ensure workflow_state is a dict
                if not isinstance(workflow_state, dict):
                    logger.warning(
                        f"Skipping non-dict workflow_state: {type(workflow_state)}"
                    )
                    continue

                # Handle None from database (Optional[dict] field)
                metadata = workflow_state.get("metadata")
                if metadata is None:
                    workflow_state["metadata"] = {}
                elif isinstance(metadata, str):
                    try:
                        workflow_state["metadata"] = json.loads(metadata)
                    except json.JSONDecodeError:
                        workflow_state["metadata"] = {}

            logger.info(f"Active workflows loaded: count={len(workflows)}")

            return workflows

        except Exception as e:
            logger.error(f"Failed to list active workflows: {e}")
            raise DatabaseConnectionError(
                f"Failed to list active workflows: {e}"
            ) from e

    async def _get_next_checkpoint_number(self, workflow_id: str) -> int:
        """
        Get next checkpoint number for workflow.

        Queries existing checkpoints and returns max(checkpoint_number) + 1.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Next checkpoint number (int, starting at 1)
        """
        workflow = WorkflowBuilder()

        # List existing checkpoints
        workflow.add_node(
            "WorkflowCheckpointModelListNode",
            "list_checkpoints",
            {
                "db_instance": self.db_instance_name,
                "model_name": "WorkflowCheckpointModel",
                "filter": {"workflow_state_id": workflow_id},
                "sort": [{"field": "checkpoint_number", "order": "desc"}],
                "limit": 1,
            },
        )

        try:
            results, run_id = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Parse results with robust handling (consistent with list_active_workflows)
            list_result = results.get("list_checkpoints", {})
            if isinstance(list_result, dict) and "result" in list_result:
                checkpoints = list_result["result"].get("records", [])
            elif isinstance(list_result, dict) and "records" in list_result:
                checkpoints = list_result["records"]
            elif isinstance(list_result, list):
                checkpoints = list_result
            else:
                logger.warning(
                    f"Unexpected list_checkpoints format: {type(list_result)}"
                )
                checkpoints = []

            # Ensure checkpoints is a list
            if not isinstance(checkpoints, list):
                logger.warning(f"Checkpoints is not a list: {type(checkpoints)}")
                checkpoints = []

            # Get max checkpoint number
            if checkpoints and len(checkpoints) > 0:
                # Safely get checkpoint_number from first checkpoint
                if isinstance(checkpoints[0], dict):
                    max_number = checkpoints[0].get("checkpoint_number", 0)
                    return max_number + 1
                else:
                    logger.warning(
                        f"First checkpoint is not a dict: {type(checkpoints[0])}"
                    )
                    return 1
            else:
                return 1

        except Exception:
            # Default to 1 if query fails
            return 1
