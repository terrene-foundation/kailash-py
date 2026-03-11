# State Persistence Guide

**Status**: ✅ Implemented (Phase 3)
**Location**: `src/kaizen/core/autonomy/state/`
**Tests**: 54 unit tests + integration tests (100% passing)

## Overview

The State Persistence System enables checkpoint/resume/fork capabilities for autonomous agents:

- **Complete state capture** - 22 fields covering all agent context
- **Atomic checkpoint saves** - Temp file + rename pattern prevents corruption
- **JSONL storage format** - One checkpoint per line, efficient append
- **Dual trigger logic** - Frequency (every N steps) OR interval (every M seconds)
- **Fork support** - Create independent execution branches with parent tracking
- **Automatic cleanup** - Retention policy keeps last N checkpoints
- **Tree visualization** - View checkpoint lineage and branches

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    StateManager                             │
│  - Checkpoint frequency/interval tracking                  │
│  - Fork with parent tracking                                │
│  - Automatic cleanup (retention policy)                     │
│  - Tree visualization                                       │
└────────────┬────────────────────────────────────────────────┘
             │
    ┌────────▼───────────┐
    │  StorageBackend    │
    │  - FilesystemStorage (JSONL)                            │
    │  - Atomic writes (temp + rename)                        │
    │  - Efficient listing                                    │
    └────────────────────┘
```

## Core Types

### AgentState (22 Fields)

```python
@dataclass
class AgentState:
    # Identification
    checkpoint_id: str                  # Unique checkpoint ID
    agent_id: str                       # Agent identifier
    timestamp: datetime                  # When checkpoint was created
    step_number: int                    # Current step in execution

    # Conversation state
    conversation_history: list[dict]    # Full conversation history
    memory_contents: dict               # Agent memory state

    # Execution state
    pending_actions: list[dict]         # Actions not yet executed
    completed_actions: list[dict]       # Actions already executed

    # Permission state
    budget_spent_usd: float             # Total cost spent
    approval_history: list[dict]        # Permission decisions

    # Tool state
    tool_usage_counts: dict[str, int]   # Tool usage statistics
    tool_results_cache: dict            # Cached tool results

    # Specialist state
    active_specialists: list[str]       # Currently active specialists
    specialist_invocations: list[dict]  # Specialist call history

    # Workflow state (Kailash SDK)
    workflow_run_id: str | None         # Current workflow run ID
    workflow_state: dict                # Workflow execution state

    # Control protocol state
    control_protocol_state: dict        # Control protocol state

    # Hook contexts
    registered_hooks: list[dict]        # Registered hooks
    hook_event_history: list[dict]      # Hook execution history

    # Metadata
    parent_checkpoint_id: str | None    # For forking
    status: Literal["running", "completed", "failed", "interrupted"]
    metadata: dict                      # Additional metadata
```

### CheckpointMetadata

```python
@dataclass
class CheckpointMetadata:
    """Lightweight metadata for efficient listing"""
    checkpoint_id: str
    agent_id: str
    timestamp: datetime
    step_number: int
    status: str
    size_bytes: int
    parent_checkpoint_id: str | None
```

## Quick Start

### 1. Basic Checkpoint/Resume

```python
from kaizen.core.autonomy.state import StateManager, AgentState, FilesystemStorage

# Setup storage
storage = FilesystemStorage(base_dir="checkpoints/")
state_manager = StateManager(storage=storage)

# Create agent state
agent_state = AgentState(
    agent_id="agent1",
    step_number=0,
    status="running"
)

# Agent execution loop
for step in range(100):
    agent_state.step_number = step

    # Do work...
    result = await agent.step()

    # Update state
    agent_state.conversation_history.append(result)

    # Save checkpoint every 10 steps
    if state_manager.should_checkpoint(agent_state.agent_id, step, time.time()):
        checkpoint_id = await state_manager.save_checkpoint(agent_state)
        print(f"Checkpoint saved: {checkpoint_id}")

# Resume from checkpoint
checkpoints = await state_manager.list_checkpoints(agent_id="agent1")
latest = checkpoints[0]  # Most recent

resumed_state = await state_manager.load_checkpoint(latest.checkpoint_id)
print(f"Resumed from step {resumed_state.step_number}")
```

### 2. Automatic Frequency-Based Checkpoints

```python
# Save every 10 steps
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=10,  # Every 10 steps
)

for step in range(100):
    agent_state.step_number = step

    # Check if should checkpoint
    if state_manager.should_checkpoint(
        agent_id="agent1",
        current_step=step,
        current_time=time.time()
    ):
        checkpoint_id = await state_manager.save_checkpoint(agent_state)
```

### 3. Time-Based Checkpoints

```python
# Save every 5 minutes
state_manager = StateManager(
    storage=storage,
    checkpoint_interval=300.0,  # 300 seconds = 5 minutes
)

while not interrupted:
    # Work...
    agent_state.step_number += 1

    # Check if should checkpoint (time-based)
    if state_manager.should_checkpoint(
        agent_id="agent1",
        current_step=agent_state.step_number,
        current_time=time.time()
    ):
        await state_manager.save_checkpoint(agent_state)
```

### 4. Forking Execution

```python
# Save initial checkpoint
checkpoint_id = await state_manager.save_checkpoint(agent_state)

# Fork to try different approaches
fork1 = await state_manager.fork_from_checkpoint(checkpoint_id)
fork2 = await state_manager.fork_from_checkpoint(checkpoint_id)

# fork1 and fork2 have:
# - New checkpoint IDs
# - Same state as parent
# - parent_checkpoint_id set to original

print(f"Fork 1: {fork1.checkpoint_id}")
print(f"Fork 2: {fork2.checkpoint_id}")
print(f"Parent: {fork1.parent_checkpoint_id}")  # Same as checkpoint_id
```

## Patterns

### Pattern 1: Dual Trigger Checkpointing

```python
# Checkpoint every 10 steps OR every 5 minutes (whichever comes first)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=10,      # Steps
    checkpoint_interval=300.0,    # Seconds
)

# Both triggers evaluated
for step in range(1000):
    if state_manager.should_checkpoint(
        agent_id="agent1",
        current_step=step,
        current_time=time.time()
    ):
        await state_manager.save_checkpoint(agent_state)
```

### Pattern 2: Forced Checkpoint on Critical Events

```python
# Normal checkpointing every 10 steps
state_manager = StateManager(storage, checkpoint_frequency=10)

# But force checkpoint on critical events
try:
    for step in range(100):
        agent_state.step_number = step

        # Do work
        result = await agent.step()

        # Force checkpoint on errors
        if result.get("error"):
            await state_manager.save_checkpoint(agent_state, force=True)
            break

        # Normal checkpoint logic
        if state_manager.should_checkpoint("agent1", step, time.time()):
            await state_manager.save_checkpoint(agent_state)
except Exception as e:
    # Force checkpoint on exception
    agent_state.status = "failed"
    await state_manager.save_checkpoint(agent_state, force=True)
```

### Pattern 3: Checkpoint Tree Exploration

```python
# Save multiple checkpoints
checkpoint1 = await state_manager.save_checkpoint(agent_state)

agent_state.step_number = 10
checkpoint2 = await state_manager.save_checkpoint(agent_state)

# Fork from checkpoint1
fork1 = await state_manager.fork_from_checkpoint(checkpoint1)
fork1.step_number = 5
fork1_id = await state_manager.save_checkpoint(fork1)

# Visualize tree
tree = await state_manager.get_checkpoint_tree(agent_id="agent1")

# Tree structure:
# checkpoint1 (step 0)
#  ├─ checkpoint2 (step 10)
#  └─ fork1_id (step 5) [fork]
```

### Pattern 4: Automatic Cleanup

```python
# Keep only last 5 checkpoints
state_manager = StateManager(
    storage=storage,
    retention_count=5  # Retention policy
)

# As new checkpoints are saved, old ones are deleted
for step in range(100):
    if step % 10 == 0:
        await state_manager.save_checkpoint(agent_state)
        # Automatically deletes checkpoints beyond the 5 most recent
```

### Pattern 5: Metadata-Based Checkpoint Selection

```python
# List all checkpoints
checkpoints = await state_manager.list_checkpoints(agent_id="agent1")

# Filter by status
completed = [c for c in checkpoints if c.status == "completed"]
interrupted = [c for c in checkpoints if c.status == "interrupted"]

# Find checkpoint at specific step
step_50 = [c for c in checkpoints if c.step_number == 50]

# Find checkpoints in time range
from datetime import datetime, timedelta
recent = [
    c for c in checkpoints
    if c.timestamp > datetime.utcnow() - timedelta(hours=1)
]
```

## Advanced Usage

### Custom Storage Backend

```python
from kaizen.core.autonomy.state.storage import StorageBackend

class S3Storage(StorageBackend):
    """Store checkpoints in S3"""

    async def save(self, state: AgentState) -> str:
        # Convert to dict
        state_dict = state.to_dict()

        # Upload to S3
        await s3_client.put_object(
            Bucket=self.bucket,
            Key=f"checkpoints/{state.checkpoint_id}.json",
            Body=json.dumps(state_dict)
        )

        return state.checkpoint_id

    async def load(self, checkpoint_id: str) -> AgentState:
        # Download from S3
        response = await s3_client.get_object(
            Bucket=self.bucket,
            Key=f"checkpoints/{checkpoint_id}.json"
        )

        # Parse and return
        data = json.loads(await response['Body'].read())
        return AgentState.from_dict(data)

    # Implement other required methods...

# Use custom storage
storage = S3Storage(bucket="my-checkpoints")
state_manager = StateManager(storage=storage)
```

### Conditional Checkpointing

```python
def should_checkpoint_custom(state: AgentState) -> bool:
    """Custom checkpoint logic"""

    # Always checkpoint on errors
    if state.status == "failed":
        return True

    # Checkpoint after expensive operations
    if state.budget_spent_usd > last_checkpoint_cost + 1.0:
        return True

    # Checkpoint before specialist invocations
    if state.pending_actions and "specialist" in str(state.pending_actions):
        return True

    return False

# Use custom logic
if should_checkpoint_custom(agent_state):
    await state_manager.save_checkpoint(agent_state, force=True)
```

### Checkpoint Compression

```python
import gzip
import json

class CompressedFilesystemStorage(FilesystemStorage):
    """Filesystem storage with gzip compression"""

    async def save(self, state: AgentState) -> str:
        state_dict = state.to_dict()

        # Compress before saving
        compressed = gzip.compress(json.dumps(state_dict).encode())

        checkpoint_path = self.base_dir / f"{state.checkpoint_id}.json.gz"

        async with aiofiles.open(checkpoint_path, "wb") as f:
            await f.write(compressed)

        return state.checkpoint_id

    async def load(self, checkpoint_id: str) -> AgentState:
        checkpoint_path = self.base_dir / f"{checkpoint_id}.json.gz"

        async with aiofiles.open(checkpoint_path, "rb") as f:
            compressed = await f.read()

        # Decompress
        data = json.loads(gzip.decompress(compressed).decode())
        return AgentState.from_dict(data)
```

## Best Practices

### 1. Use Dual Trigger Logic

```python
# Good: Checkpoint by frequency OR time
state_manager = StateManager(
    storage,
    checkpoint_frequency=10,     # Every 10 steps
    checkpoint_interval=300.0,   # OR every 5 minutes
)

# Bad: Only frequency (may never checkpoint if stuck)
state_manager = StateManager(storage, checkpoint_frequency=10)
```

### 2. Force Checkpoints on Critical Events

```python
# Always force checkpoint before/after critical operations
await state_manager.save_checkpoint(agent_state, force=True)

# Examples of critical events:
# - Before expensive operations
# - After errors
# - Before specialist invocations
# - On user interrupts
```

### 3. Set Appropriate Retention

```python
# Production: Keep 10-20 checkpoints
state_manager = StateManager(storage, retention_count=10)

# Development: Keep fewer for faster iteration
state_manager = StateManager(storage, retention_count=3)

# Long-running: Keep more for recovery options
state_manager = StateManager(storage, retention_count=50)
```

### 4. Use Metadata for Selection

```python
# Save important info in metadata
agent_state.metadata = {
    "strategy": "conservative",
    "model": "gpt-4",
    "dataset": "production_v2",
    "experiment_id": "exp_123"
}

await state_manager.save_checkpoint(agent_state)

# Later, filter by metadata
checkpoints = await state_manager.list_checkpoints("agent1")
gpt4_checkpoints = [
    c for c in checkpoints
    if c.metadata.get("model") == "gpt-4"
]
```

### 5. Clean Up Old Checkpoints

```python
# Manual cleanup
old_checkpoints = await state_manager.list_checkpoints("agent1")
if len(old_checkpoints) > 100:
    # Delete checkpoints older than 7 days
    cutoff = datetime.utcnow() - timedelta(days=7)
    for ckpt in old_checkpoints:
        if ckpt.timestamp < cutoff:
            await state_manager.delete_checkpoint(ckpt.checkpoint_id)

# Or use automatic cleanup
await state_manager.cleanup_old_checkpoints(
    agent_id="agent1",
    keep_count=10  # Keep only 10 most recent
)
```

## Testing

### Unit Testing State Persistence

```python
import pytest
from kaizen.core.autonomy.state import StateManager, AgentState, FilesystemStorage

@pytest.mark.asyncio
async def test_checkpoint_save_and_load(tmp_path):
    storage = FilesystemStorage(base_dir=tmp_path)
    manager = StateManager(storage=storage)

    # Create and save state
    state = AgentState(agent_id="test", step_number=5)
    checkpoint_id = await manager.save_checkpoint(state)

    # Load and verify
    loaded = await manager.load_checkpoint(checkpoint_id)
    assert loaded.agent_id == "test"
    assert loaded.step_number == 5

@pytest.mark.asyncio
async def test_checkpoint_frequency(tmp_path):
    storage = FilesystemStorage(base_dir=tmp_path)
    manager = StateManager(storage, checkpoint_frequency=10)

    # Should checkpoint at step 10
    assert manager.should_checkpoint("agent1", current_step=10, current_time=0)

    # Should not checkpoint at step 5
    assert not manager.should_checkpoint("agent1", current_step=5, current_time=0)
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_full_checkpoint_workflow(tmp_path):
    storage = FilesystemStorage(base_dir=tmp_path)
    manager = StateManager(storage, checkpoint_frequency=5)

    state = AgentState(agent_id="test", status="running")

    # Simulate execution with checkpoints
    checkpoint_ids = []
    for step in range(20):
        state.step_number = step

        if manager.should_checkpoint("test", step, time.time()):
            ckpt_id = await manager.save_checkpoint(state)
            checkpoint_ids.append(ckpt_id)

    # Should have 4 checkpoints (steps 0, 5, 10, 15)
    assert len(checkpoint_ids) == 4

    # Resume from latest
    latest = checkpoint_ids[-1]
    resumed = await manager.load_checkpoint(latest)
    assert resumed.step_number == 15
```

## Troubleshooting

### Issue: Checkpoints not saving

**Problem**: `should_checkpoint()` always returns False

**Solution**: Check both frequency and interval are set:

```python
# Wrong: No triggers set
manager = StateManager(storage)  # Won't checkpoint automatically

# Correct: Set at least one trigger
manager = StateManager(storage, checkpoint_frequency=10)
```

### Issue: Checkpoint file corruption

**Problem**: Checkpoint file is corrupted or empty

**Solution**: FilesystemStorage uses atomic writes (temp + rename):

```python
# Atomic write is automatic, but verify:
# 1. Check disk space
# 2. Check write permissions
# 3. Check temp directory exists

# Debug mode shows temp file path
storage = FilesystemStorage(base_dir="checkpoints", debug=True)
```

### Issue: Too many checkpoints

**Problem**: Disk filling up with old checkpoints

**Solution**: Set retention policy:

```python
# Option 1: Automatic cleanup
manager = StateManager(storage, retention_count=10)

# Option 2: Manual cleanup
await manager.cleanup_old_checkpoints("agent1", keep_count=5)
```

### Issue: Fork not preserving state

**Problem**: Forked state missing data

**Solution**: Verify deep copy is working:

```python
# Fork creates deep copy
fork = await manager.fork_from_checkpoint(checkpoint_id)

# Verify they're independent
fork.conversation_history.append({"new": "message"})

original = await manager.load_checkpoint(checkpoint_id)
assert len(original.conversation_history) < len(fork.conversation_history)
```

## API Reference

### StateManager

```python
class StateManager:
    def __init__(
        storage: StorageBackend,
        checkpoint_frequency: int = 10,
        checkpoint_interval: float = 60.0,
        retention_count: int = 100
    )

    def should_checkpoint(agent_id, current_step, current_time) -> bool
    async def save_checkpoint(state, force=False) -> str
    async def load_checkpoint(checkpoint_id) -> AgentState
    async def list_checkpoints(agent_id) -> list[CheckpointMetadata]
    async def delete_checkpoint(checkpoint_id) -> None
    async def fork_from_checkpoint(checkpoint_id) -> AgentState
    async def cleanup_old_checkpoints(agent_id, keep_count) -> int
    async def get_checkpoint_tree(agent_id) -> dict
```

### FilesystemStorage

```python
class FilesystemStorage:
    def __init__(base_dir: str | Path)

    async def save(state: AgentState) -> str
    async def load(checkpoint_id: str) -> AgentState
    async def list(agent_id: str) -> list[CheckpointMetadata]
    async def delete(checkpoint_id: str) -> None
    async def exists(checkpoint_id: str) -> bool
```

### AgentState

```python
class AgentState:
    def to_dict() -> dict[str, Any]
    @classmethod
    def from_dict(data: dict) -> AgentState
```

## See Also

- [Interrupt Mechanism Guide](interrupt-mechanism-guide.md) - Graceful shutdown with checkpoints
- [Hooks System Guide](hooks-system-guide.md) - Event-driven checkpoint monitoring
- [ADR-015: Phase 3 Lifecycle Management](../architecture/adr/ADR-015-autonomous-agent-capability-phase-3.md)
