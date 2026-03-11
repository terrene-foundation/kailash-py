"""
DataFlow State Models for OrchestrationRuntime.

Provides persistent state tracking for multi-agent workflow orchestration.
Auto-generates 33 CRUD nodes (11 per model × 3 models) via @db.model decorator.

Models:
- WorkflowState: Workflow execution state and metadata
- AgentExecutionRecord: Individual agent task execution records
- WorkflowCheckpoint: Incremental checkpoint snapshots for resume capability

Architecture:
    WorkflowState (parent)
    ├── AgentExecutionRecord (child) - via workflow_state_id foreign key
    └── WorkflowCheckpoint (child) - via workflow_state_id foreign key

Usage:
    from dataflow import DataFlow
    from kaizen.orchestration.models import WorkflowState, AgentExecutionRecord

    # Initialize DataFlow (generates nodes automatically)
    db = DataFlow(
        connection_string="postgresql://user:pass@localhost:5432/orchestration",
        auto_migrate=True,  # Safe - creates tables if missing
        enable_caching=True
    )

    # Models are now registered with 11 nodes each:
    # - WorkflowStateCreateNode, WorkflowStateReadNode, WorkflowStateUpdateNode, etc.
    # - AgentExecutionRecordCreateNode, AgentExecutionRecordReadNode, etc.
    # - WorkflowCheckpointCreateNode, WorkflowCheckpointReadNode, etc.

Author: Kaizen Framework Team
Created: 2025-11-17 (TODO-178, Phase 2: DataFlow Integration)
Reference: DataFlow specialist guidance on state persistence patterns
"""

from datetime import datetime
from typing import Any, Dict, Optional

# DataFlow models will be registered when DataFlow instance is created
# Models use @db.model decorator from DataFlow instance

# Import will be handled by StateManager - models are defined as classes here
# for type hints and documentation, but actual registration happens in StateManager


class WorkflowState:
    """
    Workflow execution state for OrchestrationRuntime.

    Tracks overall workflow status, execution metadata, and high-level results.
    Creates one-to-many relationship with AgentExecutionRecord and WorkflowCheckpoint.

    DataFlow Auto-Generated Nodes (11 total):
    - WorkflowStateCreateNode: Create new workflow state
    - WorkflowStateReadNode: Read workflow state by ID
    - WorkflowStateUpdateNode: Update workflow state fields
    - WorkflowStateDeleteNode: Delete workflow state
    - WorkflowStateListNode: Query workflows with filters
    - WorkflowStateCountNode: Count workflows matching filter
    - WorkflowStateBulkCreateNode: Create multiple workflow states
    - WorkflowStateBulkUpdateNode: Update multiple workflow states
    - WorkflowStateBulkDeleteNode: Delete multiple workflow states
    - WorkflowStateExistsNode: Check if workflow exists
    - WorkflowStateUpsertNode: Create or update workflow state

    Fields:
        id (str): Primary key - CRITICAL: Must be exactly 'id' for DataFlow
        workflow_id (str): Business identifier (can match id or be different)
        status (str): Workflow status (PENDING, RUNNING, COMPLETED, FAILED, CANCELLED)
        start_time (datetime): Workflow start timestamp
        end_time (Optional[datetime]): Workflow completion timestamp
        runtime_id (str): OrchestrationRuntime instance identifier
        routing_strategy (str): Task routing strategy (semantic, round-robin, etc.)
        max_concurrent (int): Maximum concurrent agent executions
        total_tasks (int): Total number of tasks in workflow
        completed_tasks (int): Number of completed tasks
        failed_tasks (int): Number of failed tasks
        success_rate (float): Completion success rate (0.0-1.0)
        error_message (Optional[str]): Error message if workflow failed
        error_type (Optional[str]): Error type classification
        metadata (Dict[str, Any]): Flexible JSON metadata (stored as string, must parse!)
        created_at (datetime): Auto-managed by DataFlow - NEVER set manually
        updated_at (datetime): Auto-managed by DataFlow - NEVER set manually

    Example:
        # Create workflow state via DataFlow node
        workflow.add_node("WorkflowStateCreateNode", "create_state", {
            "db_instance": "orchestration_db",
            "model_name": "WorkflowState",
            "id": "wf_abc123",
            "workflow_id": "wf_abc123",
            "status": "PENDING",
            "start_time": datetime.now().isoformat(),
            "runtime_id": "runtime_001",
            "routing_strategy": "semantic",
            "max_concurrent": 10,
            "total_tasks": 5,
            "metadata": {}
        })
    """

    # CRITICAL: Field name must be exactly 'id' for DataFlow primary key
    id: str

    # Business identifier
    workflow_id: str

    # Status tracking
    status: str  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED

    # Timestamps
    start_time: datetime
    end_time: Optional[datetime] = None

    # Execution context
    runtime_id: str  # Which OrchestrationRuntime instance
    routing_strategy: str  # semantic, round-robin, random, least-loaded
    max_concurrent: int = 10

    # Task metrics
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    success_rate: float = 0.0

    # Error tracking
    error_message: Optional[str] = None
    error_type: Optional[str] = None

    # Flexible metadata (JSON field - returns as STRING, must parse!)
    metadata: Dict[str, Any] = {}

    # Auto-managed fields (NEVER set manually!)
    # created_at: datetime  # Auto-set by DataFlow on insert
    # updated_at: datetime  # Auto-set by DataFlow on update


class AgentExecutionRecord:
    """
    Individual agent task execution record.

    Tracks which agents ran, their status, retries, results, and errors.
    One-to-many relationship with WorkflowState via workflow_state_id foreign key.

    DataFlow Auto-Generated Nodes (11 total):
    - AgentExecutionRecordCreateNode: Create new agent execution record
    - AgentExecutionRecordReadNode: Read record by ID
    - AgentExecutionRecordUpdateNode: Update record fields
    - AgentExecutionRecordDeleteNode: Delete record
    - AgentExecutionRecordListNode: Query records with filters
    - AgentExecutionRecordCountNode: Count records matching filter
    - AgentExecutionRecordBulkCreateNode: Create multiple records
    - AgentExecutionRecordBulkUpdateNode: Update multiple records
    - AgentExecutionRecordBulkDeleteNode: Delete multiple records
    - AgentExecutionRecordExistsNode: Check if record exists
    - AgentExecutionRecordUpsertNode: Create or update record

    Fields:
        id (str): Primary key - CRITICAL: Must be exactly 'id' for DataFlow
        workflow_state_id (str): Foreign key to WorkflowState.id (string-based)
        agent_id (str): Agent identifier
        agent_type (str): Agent class name (SimpleQAAgent, CodeGenerationAgent, etc.)
        task_description (str): Human-readable task description
        task_index (int): Position in workflow task list (0-based)
        status (str): Execution status (PENDING, RUNNING, COMPLETED, FAILED, RETRY)
        retry_count (int): Number of retry attempts
        max_retries (int): Maximum allowed retries
        start_time (datetime): Execution start timestamp
        end_time (Optional[datetime]): Execution completion timestamp
        execution_time_seconds (float): Total execution duration
        result (Dict[str, Any]): Agent output (JSON field - stored as string!)
        error (Optional[str]): Error message if execution failed
        error_stack_trace (Optional[str]): Full stack trace for debugging
        cost_usd (float): Execution cost in USD
        budget_remaining_usd (float): Remaining budget after execution
        created_at (datetime): Auto-managed by DataFlow
        updated_at (datetime): Auto-managed by DataFlow

    Example:
        # Create agent execution record
        workflow.add_node("AgentExecutionRecordCreateNode", "create_record", {
            "db_instance": "orchestration_db",
            "model_name": "AgentExecutionRecord",
            "id": "rec_abc123",
            "workflow_state_id": "wf_abc123",
            "agent_id": "agent_001",
            "agent_type": "SimpleQAAgent",
            "task_description": "Analyze customer data",
            "task_index": 0,
            "status": "COMPLETED",
            "retry_count": 0,
            "max_retries": 3,
            "start_time": datetime.now().isoformat(),
            "execution_time_seconds": 2.5,
            "result": {"answer": "Analysis complete"},
            "cost_usd": 0.001
        })

        # Query all records for a workflow
        workflow.add_node("AgentExecutionRecordListNode", "get_records", {
            "db_instance": "orchestration_db",
            "model_name": "AgentExecutionRecord",
            "filter": {"workflow_state_id": "wf_abc123"},
            "sort": [{"field": "task_index", "order": "asc"}]
        })
    """

    # CRITICAL: Field name must be exactly 'id' for DataFlow primary key
    id: str

    # Foreign key relationship (string-based)
    workflow_state_id: str  # Links to WorkflowState.id

    # Agent identification
    agent_id: str
    agent_type: str  # SimpleQAAgent, CodeGenerationAgent, DataAnalysisAgent, etc.

    # Task details
    task_description: str
    task_index: int  # Position in workflow task list (0-based)

    # Execution status
    status: str  # PENDING, RUNNING, COMPLETED, FAILED, RETRY
    retry_count: int = 0
    max_retries: int = 3

    # Timestamps
    start_time: datetime
    end_time: Optional[datetime] = None
    execution_time_seconds: float = 0.0

    # Results (structured data as JSON - returns as STRING, must parse!)
    result: Dict[str, Any] = {}

    # Error tracking
    error: Optional[str] = None
    error_stack_trace: Optional[str] = None

    # Cost tracking
    cost_usd: float = 0.0
    budget_remaining_usd: float = 0.0

    # Auto-managed fields (NEVER set manually!)
    # created_at: datetime
    # updated_at: datetime


class WorkflowCheckpoint:
    """
    Checkpoint snapshots for long-running workflows.

    Stores incremental state snapshots for resume capability.
    One-to-many relationship with WorkflowState via workflow_state_id foreign key.

    DataFlow Auto-Generated Nodes (11 total):
    - WorkflowCheckpointCreateNode: Create new checkpoint
    - WorkflowCheckpointReadNode: Read checkpoint by ID
    - WorkflowCheckpointUpdateNode: Update checkpoint fields
    - WorkflowCheckpointDeleteNode: Delete checkpoint
    - WorkflowCheckpointListNode: Query checkpoints with filters
    - WorkflowCheckpointCountNode: Count checkpoints matching filter
    - WorkflowCheckpointBulkCreateNode: Create multiple checkpoints
    - WorkflowCheckpointBulkUpdateNode: Update multiple checkpoints
    - WorkflowCheckpointBulkDeleteNode: Delete multiple checkpoints
    - WorkflowCheckpointExistsNode: Check if checkpoint exists
    - WorkflowCheckpointUpsertNode: Create or update checkpoint

    Fields:
        id (str): Primary key (checkpoint_id)
        workflow_state_id (str): Foreign key to WorkflowState.id
        checkpoint_number (int): Incremental counter (1, 2, 3...)
        checkpoint_type (str): AUTO, MANUAL, ERROR_RECOVERY
        snapshot_data (Dict[str, Any]): Compressed incremental state (JSON)
        created_at_timestamp (datetime): Custom timestamp (not auto-managed)
        size_bytes (int): Checkpoint size in bytes
        compression_ratio (float): Compression efficiency ratio
        parent_checkpoint_id (Optional[str]): Link to previous checkpoint for incremental chain
        created_at (datetime): Auto-managed by DataFlow
        updated_at (datetime): Auto-managed by DataFlow

    Example:
        # Create checkpoint with compression
        import gzip
        import json

        checkpoint_data = {"state": "...", "agents": [...]}
        json_str = json.dumps(checkpoint_data)
        compressed = gzip.compress(json_str.encode('utf-8'))

        workflow.add_node("WorkflowCheckpointCreateNode", "create_checkpoint", {
            "db_instance": "orchestration_db",
            "model_name": "WorkflowCheckpoint",
            "id": "cp_abc123_1",
            "workflow_state_id": "wf_abc123",
            "checkpoint_number": 1,
            "checkpoint_type": "AUTO",
            "snapshot_data": {"compressed": compressed.hex()},
            "created_at_timestamp": datetime.now().isoformat(),
            "size_bytes": len(compressed),
            "compression_ratio": len(compressed) / len(json_str)
        })

        # Load latest checkpoint for workflow
        workflow.add_node("WorkflowCheckpointListNode", "get_checkpoints", {
            "db_instance": "orchestration_db",
            "model_name": "WorkflowCheckpoint",
            "filter": {"workflow_state_id": "wf_abc123"},
            "sort": [{"field": "checkpoint_number", "order": "desc"}],
            "limit": 1
        })
    """

    # CRITICAL: Field name must be exactly 'id' for DataFlow primary key
    id: str  # checkpoint_id

    # Foreign key relationship
    workflow_state_id: str  # Links to WorkflowState.id

    # Checkpoint metadata
    checkpoint_number: int  # Incremental counter (1, 2, 3...)
    checkpoint_type: str  # AUTO, MANUAL, ERROR_RECOVERY

    # Snapshot data (incremental - only changed state)
    # Stored as JSON, can contain compressed binary data as hex string
    snapshot_data: Dict[str, Any] = {}

    # Custom timestamp (not auto-managed - we control this)
    created_at_timestamp: datetime

    # Size tracking
    size_bytes: int = 0
    compression_ratio: float = 1.0

    # Parent checkpoint (for incremental chain)
    parent_checkpoint_id: Optional[str] = None

    # Auto-managed fields (NEVER set manually!)
    # created_at: datetime
    # updated_at: datetime


# Validation constants for model fields
WORKFLOW_STATUS_VALUES = ["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
AGENT_STATUS_VALUES = ["PENDING", "RUNNING", "COMPLETED", "FAILED", "RETRY"]
CHECKPOINT_TYPE_VALUES = ["AUTO", "MANUAL", "ERROR_RECOVERY"]
ROUTING_STRATEGY_VALUES = ["semantic", "round-robin", "random", "least-loaded"]


def validate_workflow_state(data: Dict[str, Any]) -> None:
    """
    Validate WorkflowState data before creating/updating.

    Args:
        data: Workflow state data dictionary

    Raises:
        ValueError: If validation fails
    """
    if "status" in data and data["status"] not in WORKFLOW_STATUS_VALUES:
        raise ValueError(
            f"Invalid status: {data['status']}. Must be one of {WORKFLOW_STATUS_VALUES}"
        )

    if (
        "routing_strategy" in data
        and data["routing_strategy"] not in ROUTING_STRATEGY_VALUES
    ):
        raise ValueError(
            f"Invalid routing_strategy: {data['routing_strategy']}. "
            f"Must be one of {ROUTING_STRATEGY_VALUES}"
        )

    if "success_rate" in data and not 0.0 <= data["success_rate"] <= 1.0:
        raise ValueError(
            f"Invalid success_rate: {data['success_rate']}. Must be between 0.0 and 1.0"
        )


def validate_agent_execution_record(data: Dict[str, Any]) -> None:
    """
    Validate AgentExecutionRecord data before creating/updating.

    Args:
        data: Agent execution record data dictionary

    Raises:
        ValueError: If validation fails
    """
    if "status" in data and data["status"] not in AGENT_STATUS_VALUES:
        raise ValueError(
            f"Invalid status: {data['status']}. Must be one of {AGENT_STATUS_VALUES}"
        )

    if "retry_count" in data and data["retry_count"] < 0:
        raise ValueError(f"Invalid retry_count: {data['retry_count']}. Must be >= 0")

    if "execution_time_seconds" in data and data["execution_time_seconds"] < 0:
        raise ValueError(
            f"Invalid execution_time_seconds: {data['execution_time_seconds']}. Must be >= 0"
        )


def validate_workflow_checkpoint(data: Dict[str, Any]) -> None:
    """
    Validate WorkflowCheckpoint data before creating/updating.

    Args:
        data: Checkpoint data dictionary

    Raises:
        ValueError: If validation fails
    """
    if (
        "checkpoint_type" in data
        and data["checkpoint_type"] not in CHECKPOINT_TYPE_VALUES
    ):
        raise ValueError(
            f"Invalid checkpoint_type: {data['checkpoint_type']}. "
            f"Must be one of {CHECKPOINT_TYPE_VALUES}"
        )

    if "checkpoint_number" in data and data["checkpoint_number"] < 1:
        raise ValueError(
            f"Invalid checkpoint_number: {data['checkpoint_number']}. Must be >= 1"
        )

    if "compression_ratio" in data and data["compression_ratio"] <= 0:
        raise ValueError(
            f"Invalid compression_ratio: {data['compression_ratio']}. Must be > 0"
        )
