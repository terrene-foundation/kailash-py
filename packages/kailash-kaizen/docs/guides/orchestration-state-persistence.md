# OrchestrationStateManager - DataFlow Integration Guide

**Author:** Kaizen Framework Team
**Created:** 2025-11-17 (TODO-178, Phase 2)
**Status:** Production-Ready

## Overview

OrchestrationStateManager provides persistent state tracking for multi-agent workflow orchestration using DataFlow's automatic node generation. This guide covers implementation patterns, best practices, and troubleshooting.

## Table of Contents

1. [Architecture](#architecture)
2. [Quick Start](#quick-start)
3. [DataFlow Integration](#dataflow-integration)
4. [Core Operations](#core-operations)
5. [Error Handling](#error-handling)
6. [Testing Patterns](#testing-patterns)
7. [Performance Optimization](#performance-optimization)
8. [Troubleshooting](#troubleshooting)

---

## Architecture

### Component Overview

```
OrchestrationStateManager
├── DataFlow Instance (one per database)
│   ├── 3 Models Registered
│   └── 33 Auto-Generated Nodes (11 per model)
├── AsyncLocalRuntime (async execution)
└── 5 Public Methods
    ├── save_workflow_state() - Create/update workflow state
    ├── load_workflow_state() - Load with related records
    ├── save_checkpoint() - Create compressed checkpoint
    ├── load_checkpoint() - Decompress and return data
    └── list_active_workflows() - Query active workflows
```

### DataFlow Models and Nodes

**WorkflowState** (11 nodes):
- `WorkflowStateCreateNode`, `WorkflowStateReadNode`, `WorkflowStateUpdateNode`
- `WorkflowStateDeleteNode`, `WorkflowStateListNode`, `WorkflowStateCountNode`
- `WorkflowStateBulkCreateNode`, `WorkflowStateBulkUpdateNode`, `WorkflowStateBulkDeleteNode`
- `WorkflowStateExistsNode`, `WorkflowStateUpsertNode`

**AgentExecutionRecord** (11 nodes):
- `AgentExecutionRecordCreateNode`, `AgentExecutionRecordReadNode`, etc.

**WorkflowCheckpoint** (11 nodes):
- `WorkflowCheckpointCreateNode`, `WorkflowCheckpointReadNode`, etc.

---

## Quick Start

### Installation

```bash
# Install dependencies
pip install kailash-kaizen>=0.8.0
pip install kailash-dataflow>=0.7.9
pip install kailash>=0.9.25

# PostgreSQL driver (recommended)
pip install asyncpg

# Or SQLite (development)
# No additional driver needed
```

### Basic Usage

```python
from kaizen.orchestration.state_manager import OrchestrationStateManager

# Initialize with PostgreSQL
state_mgr = OrchestrationStateManager(
    connection_string="postgresql://user:pass@localhost:5432/orchestration"
)

# Save workflow state
workflow_state_id = await state_mgr.save_workflow_state(
    workflow_id="wf_abc123",
    status="RUNNING",
    metadata={"total_tasks": 5, "priority": "high"},
    routing_strategy="semantic",
    total_tasks=5,
)

# Load workflow state with related records
result = await state_mgr.load_workflow_state("wf_abc123")
print(result["workflow_state"])
print(result["agent_records"])

# Create checkpoint
checkpoint_id = await state_mgr.save_checkpoint(
    workflow_id="wf_abc123",
    checkpoint_data={"agents": [...], "state": {...}},
    checkpoint_type="AUTO",
)

# Load checkpoint
checkpoint_data = await state_mgr.load_checkpoint(checkpoint_id)
```

---

## DataFlow Integration

### Model Registration Pattern

**CRITICAL:** Models are registered using the `@db.model` decorator pattern **inside** the StateManager initialization. This generates 33 nodes automatically.

```python
# Inside OrchestrationStateManager.__init__()

@self.db.model
class WorkflowStateModel:
    id: str  # CRITICAL: Must be exactly 'id' for DataFlow
    workflow_id: str
    status: str
    start_time: datetime
    metadata: Dict[str, Any] = {}
    # ... other fields
```

**Key Rules:**
1. Primary key **MUST** be named `id` (DataFlow requirement)
2. Foreign keys use string IDs (`workflow_state_id: str`)
3. JSON fields return as **strings** - must parse manually
4. `created_at`/`updated_at` auto-managed - NEVER set manually

### Node Usage Patterns

**Pattern 1: Upsert (Create or Update)**
```python
workflow = WorkflowBuilder()
workflow.add_node(
    "WorkflowStateUpsertNode",
    "upsert_state",
    {
        "db_instance": self.db_instance_name,
        "model_name": "WorkflowState",
        "id": workflow_id,
        "status": "RUNNING",
        "metadata": {"key": "value"},
    },
)

results, run_id = await self.runtime.execute_workflow_async(
    workflow.build(), inputs={}
)
```

**Pattern 2: Read by ID**
```python
workflow = WorkflowBuilder()
workflow.add_node(
    "WorkflowStateReadNode",
    "read_state",
    {
        "db_instance": self.db_instance_name,
        "model_name": "WorkflowState",
        "id": workflow_id,
    },
)

results, run_id = await self.runtime.execute_workflow_async(
    workflow.build(), inputs={}
)

# Parse result
state_result = results.get("read_state", {})
if isinstance(state_result, dict) and "result" in state_result:
    workflow_state = state_result["result"]
else:
    workflow_state = state_result
```

**Pattern 3: List with Filter (MongoDB-style)**
```python
workflow = WorkflowBuilder()
workflow.add_node(
    "WorkflowStateListNode",
    "list_active",
    {
        "db_instance": self.db_instance_name,
        "model_name": "WorkflowState",
        "filter": {
            "status": {"$in": ["PENDING", "RUNNING"]}
        },
        "sort": [{"field": "start_time", "order": "desc"}],
        "limit": 100,
    },
)
```

**Pattern 4: Create Record**
```python
workflow = WorkflowBuilder()
workflow.add_node(
    "AgentExecutionRecordCreateNode",
    "create_record",
    {
        "db_instance": self.db_instance_name,
        "model_name": "AgentExecutionRecord",
        "id": record_id,
        "workflow_state_id": workflow_id,  # Foreign key
        "agent_id": "agent_001",
        "status": "COMPLETED",
        "result": {"answer": "Result data"},  # JSON field
    },
)
```

### JSON Field Parsing

**CRITICAL:** DataFlow stores JSON fields as strings. You **MUST** parse them manually.

```python
# Load workflow state
result = await state_mgr.load_workflow_state(workflow_id)
workflow_state = result["workflow_state"]

# Parse metadata JSON field
if isinstance(workflow_state.get("metadata"), str):
    try:
        workflow_state["metadata"] = json.loads(workflow_state["metadata"])
    except json.JSONDecodeError:
        workflow_state["metadata"] = {}

# Now you can access metadata as dict
print(workflow_state["metadata"]["total_tasks"])
```

---

## Core Operations

### 1. Save Workflow State

**Method:** `save_workflow_state(workflow_id, status, metadata, ...)`

**Purpose:** Create or update WorkflowState record using atomic upsert.

**Parameters:**
- `workflow_id` (str): Business workflow identifier
- `status` (str): PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
- `metadata` (dict): Flexible JSON metadata
- `runtime_id` (str, optional): OrchestrationRuntime instance ID
- `routing_strategy` (str): semantic, round-robin, random, least-loaded
- `max_concurrent` (int): Max concurrent agents
- `total_tasks` (int): Total task count

**Returns:** `workflow_state_id` (str)

**Example:**
```python
state_id = await state_mgr.save_workflow_state(
    workflow_id="wf_customer_analysis_001",
    status="RUNNING",
    metadata={
        "customer_id": "cust_123",
        "analysis_type": "sentiment",
        "priority": "high",
    },
    routing_strategy="semantic",
    max_concurrent=10,
    total_tasks=15,
)
```

**Error Handling:**
```python
from kaizen.orchestration.state_manager import DatabaseConnectionError

try:
    state_id = await state_mgr.save_workflow_state(...)
except ValueError as e:
    # Invalid status or routing_strategy
    logger.error(f"Validation error: {e}")
except DatabaseConnectionError as e:
    # Database operation failed
    logger.error(f"Database error: {e}")
```

### 2. Load Workflow State

**Method:** `load_workflow_state(workflow_id, include_records=True)`

**Purpose:** Load WorkflowState with optional related AgentExecutionRecords.

**Parameters:**
- `workflow_id` (str): Workflow identifier
- `include_records` (bool): Include related agent records (default: True)

**Returns:** Dict with:
- `workflow_state` (dict): WorkflowState data
- `agent_records` (list): AgentExecutionRecord data (if include_records=True)

**Example:**
```python
# Load with agent records
result = await state_mgr.load_workflow_state("wf_customer_analysis_001")

workflow_state = result["workflow_state"]
print(f"Status: {workflow_state['status']}")
print(f"Total tasks: {workflow_state['total_tasks']}")
print(f"Metadata: {workflow_state['metadata']}")

agent_records = result["agent_records"]
for record in agent_records:
    print(f"Agent {record['agent_id']}: {record['status']}")
    print(f"Result: {record['result']}")

# Load without agent records (faster)
result = await state_mgr.load_workflow_state(
    "wf_customer_analysis_001",
    include_records=False
)
```

**Error Handling:**
```python
from kaizen.orchestration.state_manager import WorkflowNotFoundError

try:
    result = await state_mgr.load_workflow_state("wf_nonexistent")
except WorkflowNotFoundError as e:
    logger.error(f"Workflow not found: {e}")
except DatabaseConnectionError as e:
    logger.error(f"Database error: {e}")
```

### 3. Save Checkpoint

**Method:** `save_checkpoint(workflow_id, checkpoint_data, checkpoint_type, ...)`

**Purpose:** Create compressed checkpoint snapshot for workflow state.

**Parameters:**
- `workflow_id` (str): Workflow identifier
- `checkpoint_data` (dict): Checkpoint payload (will be compressed)
- `checkpoint_type` (str): AUTO, MANUAL, ERROR_RECOVERY
- `parent_checkpoint_id` (str, optional): Previous checkpoint for incremental chain

**Returns:** `checkpoint_id` (str)

**Compression:** Automatic gzip compression with metrics tracking.

**Example:**
```python
checkpoint_data = {
    "agents": [
        {"id": "agent_001", "status": "active", "progress": 0.5},
        {"id": "agent_002", "status": "active", "progress": 0.3},
    ],
    "state": {
        "current_step": 5,
        "completed_tasks": 3,
        "pending_tasks": 2,
    },
    "metadata": {
        "timestamp": datetime.now().isoformat(),
        "trigger": "auto_checkpoint",
    },
}

checkpoint_id = await state_mgr.save_checkpoint(
    workflow_id="wf_customer_analysis_001",
    checkpoint_data=checkpoint_data,
    checkpoint_type="AUTO",
)

print(f"Checkpoint created: {checkpoint_id}")
```

**Incremental Checkpoints:**
```python
# First checkpoint
cp1_id = await state_mgr.save_checkpoint(
    workflow_id="wf_001",
    checkpoint_data={"step": 1, "data": "initial"},
    checkpoint_type="AUTO",
)

# Second checkpoint (incremental)
cp2_id = await state_mgr.save_checkpoint(
    workflow_id="wf_001",
    checkpoint_data={"step": 2, "data": "updated"},
    checkpoint_type="AUTO",
    parent_checkpoint_id=cp1_id,  # Link to previous checkpoint
)
```

### 4. Load Checkpoint

**Method:** `load_checkpoint(checkpoint_id)`

**Purpose:** Load and decompress checkpoint snapshot.

**Parameters:**
- `checkpoint_id` (str): Checkpoint identifier

**Returns:** Decompressed checkpoint data (dict)

**Example:**
```python
checkpoint_data = await state_mgr.load_checkpoint(checkpoint_id)

# Access checkpoint data
agents = checkpoint_data["agents"]
state = checkpoint_data["state"]
metadata = checkpoint_data["metadata"]

print(f"Checkpoint step: {state['current_step']}")
print(f"Active agents: {len(agents)}")
```

**Error Handling:**
```python
from kaizen.orchestration.state_manager import CheckpointNotFoundError

try:
    data = await state_mgr.load_checkpoint("cp_nonexistent")
except CheckpointNotFoundError as e:
    logger.error(f"Checkpoint not found: {e}")
except DatabaseConnectionError as e:
    logger.error(f"Database error: {e}")
```

### 5. List Active Workflows

**Method:** `list_active_workflows()`

**Purpose:** Query all workflows with status PENDING or RUNNING.

**Returns:** List of workflow state dicts

**Example:**
```python
active_workflows = await state_mgr.list_active_workflows()

for workflow in active_workflows:
    print(f"Workflow {workflow['workflow_id']}: {workflow['status']}")
    print(f"  Started: {workflow['start_time']}")
    print(f"  Progress: {workflow['completed_tasks']}/{workflow['total_tasks']}")
    print(f"  Success rate: {workflow['success_rate'] * 100:.1f}%")
```

---

## Error Handling

### Exception Hierarchy

```
StateManagerError (base)
├── WorkflowNotFoundError - Workflow not found in database
├── CheckpointNotFoundError - Checkpoint not found in database
└── DatabaseConnectionError - Database operation failed
```

### Comprehensive Error Handling Pattern

```python
from kaizen.orchestration.state_manager import (
    OrchestrationStateManager,
    StateManagerError,
    WorkflowNotFoundError,
    CheckpointNotFoundError,
    DatabaseConnectionError,
)

async def safe_workflow_operation(workflow_id: str):
    """Demonstrates comprehensive error handling."""
    try:
        # Load workflow state
        result = await state_mgr.load_workflow_state(workflow_id)

        # Update status
        await state_mgr.save_workflow_state(
            workflow_id=workflow_id,
            status="COMPLETED",
            metadata={"finished_at": datetime.now().isoformat()},
        )

        return result

    except WorkflowNotFoundError:
        logger.error(f"Workflow {workflow_id} does not exist")
        # Handle missing workflow (create new one, return error, etc.)
        return None

    except ValueError as e:
        logger.error(f"Invalid parameter: {e}")
        # Handle validation errors
        raise

    except DatabaseConnectionError as e:
        logger.error(f"Database error: {e}")
        # Handle connection failures (retry, failover, etc.)
        raise

    except StateManagerError as e:
        logger.error(f"State manager error: {e}")
        # Handle other state manager errors
        raise
```

---

## Testing Patterns

### Integration Test Setup

```python
import pytest
import os
from kaizen.orchestration.state_manager import OrchestrationStateManager

TEST_DB_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://postgres:postgres@localhost:5432/kaizen_test"
)

@pytest.fixture
async def state_manager():
    """Fixture providing StateManager with test database."""
    manager = OrchestrationStateManager(
        connection_string=TEST_DB_URL,
        db_instance_name="test_orchestration_db",
        auto_migrate=True,
    )
    yield manager
    # Cleanup happens automatically (auto_migrate=True is safe)
```

### Test Examples

**Test 1: Basic CRUD**
```python
@pytest.mark.asyncio
async def test_workflow_crud(state_manager):
    """Test create, read, update workflow state."""
    workflow_id = "wf_test_001"

    # Create
    state_id = await state_manager.save_workflow_state(
        workflow_id=workflow_id,
        status="PENDING",
    )
    assert state_id == workflow_id

    # Read
    result = await state_manager.load_workflow_state(workflow_id)
    assert result["workflow_state"]["status"] == "PENDING"

    # Update
    await state_manager.save_workflow_state(
        workflow_id=workflow_id,
        status="COMPLETED",
    )

    # Verify update
    result = await state_manager.load_workflow_state(workflow_id)
    assert result["workflow_state"]["status"] == "COMPLETED"
```

**Test 2: Checkpoint Compression**
```python
@pytest.mark.asyncio
async def test_checkpoint_compression(state_manager):
    """Test checkpoint compression/decompression."""
    workflow_id = "wf_test_002"

    # Create workflow
    await state_manager.save_workflow_state(workflow_id, "RUNNING")

    # Create checkpoint with large data
    original_data = {
        "agents": [{"id": f"agent_{i}"} for i in range(1000)],
        "state": {"data": "x" * 10000},
    }

    checkpoint_id = await state_manager.save_checkpoint(
        workflow_id=workflow_id,
        checkpoint_data=original_data,
    )

    # Load and verify
    loaded_data = await state_manager.load_checkpoint(checkpoint_id)
    assert loaded_data == original_data
```

---

## Performance Optimization

### Connection Pooling

```python
# DataFlow automatically manages connection pooling
state_mgr = OrchestrationStateManager(
    connection_string="postgresql://user:pass@localhost:5432/orchestration",
    enable_caching=True,  # Enable query caching
    enable_metrics=True,  # Track performance
)
```

### Batch Operations

```python
# For bulk agent record creation, use BulkCreateNode directly
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node(
    "AgentExecutionRecordBulkCreateNode",
    "bulk_create",
    {
        "db_instance": "orchestration_db",
        "model_name": "AgentExecutionRecord",
        "data": [
            {"id": f"rec_{i}", "workflow_state_id": "wf_001", ...}
            for i in range(100)
        ],
    },
)
```

### Checkpoint Optimization

```python
# Incremental checkpoints save space
cp1 = await state_mgr.save_checkpoint(
    workflow_id="wf_001",
    checkpoint_data={"full_state": {...}},  # Large initial state
)

cp2 = await state_mgr.save_checkpoint(
    workflow_id="wf_001",
    checkpoint_data={"changed_fields": {...}},  # Only changes
    parent_checkpoint_id=cp1,  # Link to previous
)
```

---

## Troubleshooting

### Issue 1: JSON Fields Return Strings

**Problem:** `workflow_state["metadata"]` is a string, not a dict.

**Solution:** DataFlow stores JSON fields as strings. Parse manually:

```python
if isinstance(workflow_state.get("metadata"), str):
    workflow_state["metadata"] = json.loads(workflow_state["metadata"])
```

### Issue 2: Primary Key Must Be 'id'

**Problem:** `TypeError: got multiple values for keyword argument 'model_name'`

**Solution:** DataFlow requires primary key named exactly `id`:

```python
# ✅ CORRECT
@db.model
class User:
    id: str  # MUST be 'id'

# ❌ WRONG
@db.model
class User:
    user_id: str  # DataFlow requires 'id'
```

### Issue 3: created_at/updated_at Errors

**Problem:** Validation errors when setting `created_at` or `updated_at`.

**Solution:** These fields are auto-managed by DataFlow. NEVER set manually:

```python
# ✅ CORRECT
workflow.add_node("WorkflowStateCreateNode", "create", {
    "id": "wf_001",
    "status": "PENDING",
    # created_at auto-set by DataFlow
})

# ❌ WRONG
workflow.add_node("WorkflowStateCreateNode", "create", {
    "id": "wf_001",
    "created_at": datetime.now(),  # Error!
})
```

### Issue 4: Workflow Not Found

**Problem:** `WorkflowNotFoundError` when loading workflow.

**Solution:** Check if workflow exists before loading:

```python
try:
    result = await state_mgr.load_workflow_state(workflow_id)
except WorkflowNotFoundError:
    # Create new workflow
    await state_mgr.save_workflow_state(
        workflow_id=workflow_id,
        status="PENDING",
    )
```

### Issue 5: Database Connection Errors

**Problem:** `DatabaseConnectionError` on initialization.

**Solution:** Verify connection string and database availability:

```python
# Test connection manually
import asyncpg

async def test_connection():
    try:
        conn = await asyncpg.connect(
            "postgresql://user:pass@localhost:5432/orchestration"
        )
        await conn.close()
        print("Connection successful")
    except Exception as e:
        print(f"Connection failed: {e}")
```

---

## Production Checklist

- [ ] Use PostgreSQL for production (not SQLite)
- [ ] Enable connection pooling (automatic in DataFlow)
- [ ] Enable query caching (`enable_caching=True`)
- [ ] Enable metrics tracking (`enable_metrics=True`)
- [ ] Set `auto_migrate=True` (safe - preserves data)
- [ ] Implement error handling for all state operations
- [ ] Parse JSON fields after loading (`metadata`, `result`)
- [ ] Use incremental checkpoints for large workflows
- [ ] Monitor checkpoint compression ratios
- [ ] Set up database backups
- [ ] Configure connection timeouts
- [ ] Test failover scenarios

---

## References

- **DataFlow Documentation:** `/packages/kailash-dataflow/README.md`
- **Model Definitions:** `/src/kaizen/orchestration/models.py`
- **Integration Tests:** `/tests/integration/orchestration/test_state_manager_integration.py`
- **TODO-178 Phase 2:** DataFlow Integration Implementation Plan
