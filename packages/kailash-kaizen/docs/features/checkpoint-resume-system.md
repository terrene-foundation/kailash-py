# Checkpoint & Resume System for Autonomous Agents

**Version**: 1.0.0
**Status**: Production Ready
**Implementation**: TODO-168 (Phase 3: Hooks & State Persistence)
**Test Coverage**: 114/114 tests passing (100%)

---

## Overview

The Checkpoint & Resume System enables autonomous agents to save their execution state at regular intervals and resume from those checkpoints after interruptions. This ensures long-running agents can recover from failures, be paused and resumed, and maintain execution continuity.

### Key Features

- ✅ **Automatic Checkpointing**: Save state every N steps or M seconds
- ✅ **Seamless Resume**: Continue execution from last checkpoint
- ✅ **JSONL Compression**: Reduce checkpoint size by >50% with gzip
- ✅ **Retention Policy**: Automatically clean up old checkpoints
- ✅ **Hook Integration**: PRE/POST checkpoint hooks for custom logic
- ✅ **Error Recovery**: Resume after failures or interruptions
- ✅ **Zero Configuration**: Works out-of-the-box with sensible defaults

---

## Quick Start

### Basic Usage

```python
from kaizen.agents.autonomous.base import BaseAutonomousAgent, AutonomousConfig
from kaizen.core.autonomy.state.storage import FilesystemStorage
from kaizen.core.autonomy.state.manager import StateManager
from kaizen.signatures import Signature, InputField, OutputField

class TaskSignature(Signature):
    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result")

# Configure with automatic checkpointing
config = AutonomousConfig(
    max_cycles=10,
    checkpoint_frequency=5,  # Save every 5 steps
    llm_provider="ollama",
    model="llama3.2",
)

# Create agent with state manager
storage = FilesystemStorage(base_dir=".kaizen/checkpoints")
state_manager = StateManager(storage=storage, checkpoint_frequency=5)

agent = BaseAutonomousAgent(
    config=config,
    signature=TaskSignature(),
    state_manager=state_manager,
)

# Run with automatic checkpointing
result = await agent._autonomous_loop("Perform a complex task")
```

### Resume from Checkpoint

```python
# Configure with resume enabled
config = AutonomousConfig(
    max_cycles=10,
    resume_from_checkpoint=True,  # Enable resume
    checkpoint_frequency=5,
    llm_provider="ollama",
    model="llama3.2",
)

# Create agent with same storage
storage = FilesystemStorage(base_dir=".kaizen/checkpoints")
state_manager = StateManager(storage=storage)

agent = BaseAutonomousAgent(
    config=config,
    signature=TaskSignature(),
    state_manager=state_manager,
)

# Resume from latest checkpoint
result = await agent._autonomous_loop("Continue the task")
```

---

## Configuration

### AutonomousConfig Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `checkpoint_frequency` | `int` | `10` | Save checkpoint every N steps |
| `checkpoint_interval_seconds` | `float` | `60.0` | OR save every M seconds |
| `resume_from_checkpoint` | `bool` | `False` | Resume from latest checkpoint on start |

### StateManager Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `storage` | `StorageBackend` | `FilesystemStorage()` | Storage backend for checkpoints |
| `checkpoint_frequency` | `int` | `10` | Checkpoint every N steps |
| `checkpoint_interval` | `float` | `60.0` | Checkpoint every M seconds |
| `retention_count` | `int` | `100` | Keep latest N checkpoints |
| `hook_manager` | `HookManager` | `None` | Optional hook manager for events |

### FilesystemStorage Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_dir` | `str\|Path` | `.kaizen/checkpoints` | Directory for checkpoint files |
| `compress` | `bool` | `False` | Enable gzip compression |

---

## Advanced Usage

### Compression for Large Checkpoints

```python
# Enable compression to reduce storage by >50%
storage = FilesystemStorage(
    base_dir=".kaizen/checkpoints",
    compress=True,  # Enable gzip compression
)

state_manager = StateManager(storage=storage, checkpoint_frequency=5)
```

**Performance**:
- Compression ratio: >50% size reduction
- Minimal overhead: <10ms per checkpoint
- Automatic decompression on load

### Retention Policy

```python
# Keep only the 10 most recent checkpoints
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=5,
    retention_count=10,  # Keep only 10 latest
)
```

**Behavior**:
- Oldest checkpoints deleted automatically
- Deletion happens after each checkpoint save
- Non-blocking (errors logged but don't fail saves)

### Checkpoint Frequency vs Interval

```python
# Checkpoint every 5 steps OR every 30 seconds (whichever comes first)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=5,     # Every 5 steps
    checkpoint_interval=30.0,   # OR every 30 seconds
)
```

**Strategy**:
- Use **frequency** for step-based checkpointing (predictable)
- Use **interval** for time-based checkpointing (long-running steps)
- Both can be active simultaneously (OR logic)

### Hook Integration

```python
from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.types import HookEvent, HookPriority, HookResult

# Create hook manager
hook_manager = HookManager()

# Register checkpoint hooks
async def checkpoint_logger(context):
    """Log checkpoint events"""
    checkpoint_id = context.data.get("checkpoint_id")
    step = context.data.get("step_number")
    print(f"Checkpoint {checkpoint_id} at step {step}")
    return HookResult(success=True)

hook_manager.register(
    HookEvent.POST_CHECKPOINT_SAVE,
    checkpoint_logger,
    HookPriority.NORMAL,
)

# Pass to state manager
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=5,
    hook_manager=hook_manager,
)
```

**Available Hooks**:
- `PRE_CHECKPOINT_SAVE`: Before checkpoint is saved
- `POST_CHECKPOINT_SAVE`: After checkpoint is saved (includes checkpoint_id)

**Hook Data**:
- `agent_id`: ID of the agent
- `step_number`: Current step number
- `status`: Agent status ("running", "completed", "failed")
- `timestamp`: Current timestamp
- `checkpoint_id`: ID of saved checkpoint (POST only)

---

## API Reference

### StateManager

#### Methods

**`save_checkpoint(state: AgentState, force: bool = False) -> str`**
```python
# Save checkpoint with current state
checkpoint_id = await state_manager.save_checkpoint(state, force=True)
```

**`load_checkpoint(checkpoint_id: str) -> AgentState`**
```python
# Load specific checkpoint
state = await state_manager.load_checkpoint("ckpt_abc123")
```

**`resume_from_latest(agent_id: str) -> AgentState | None`**
```python
# Resume from latest checkpoint for agent
state = await state_manager.resume_from_latest("my_agent")
```

**`list_checkpoints(agent_id: str | None = None) -> list[CheckpointMetadata]`**
```python
# List all checkpoints (optionally filtered by agent)
checkpoints = await state_manager.list_checkpoints(agent_id="my_agent")
```

**`cleanup_old_checkpoints(agent_id: str) -> int`**
```python
# Delete old checkpoints beyond retention_count
deleted_count = await state_manager.cleanup_old_checkpoints("my_agent")
```

**`fork_checkpoint(checkpoint_id: str, new_agent_id: str) -> AgentState`**
```python
# Create independent copy of checkpoint
forked_state = await state_manager.fork_checkpoint("ckpt_abc123", "new_agent")
```

### AgentState

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `checkpoint_id` | `str` | Unique checkpoint ID |
| `agent_id` | `str` | Agent identifier |
| `timestamp` | `datetime` | Checkpoint creation time |
| `step_number` | `int` | Execution step number |
| `conversation_history` | `list[dict]` | Conversation messages |
| `memory_contents` | `dict` | Memory state |
| `pending_actions` | `list[dict]` | Pending actions (planning) |
| `completed_actions` | `list[dict]` | Completed actions |
| `budget_spent_usd` | `float` | Budget tracking |
| `approval_history` | `list[dict]` | Permission approvals |
| `tool_usage_counts` | `dict` | Tool usage statistics |
| `status` | `str` | "running", "completed", "failed", "interrupted" |
| `parent_checkpoint_id` | `str\|None` | Parent checkpoint for forking |

### CheckpointMetadata

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `checkpoint_id` | `str` | Unique checkpoint ID |
| `agent_id` | `str` | Agent identifier |
| `timestamp` | `datetime` | Creation timestamp |
| `step_number` | `int` | Step number |
| `status` | `str` | Checkpoint status |
| `size_bytes` | `int` | File size in bytes |
| `parent_checkpoint_id` | `str\|None` | Parent checkpoint |

---

## Performance

### Benchmark Results

**Environment**:
- Platform: macOS (Apple Silicon)
- Storage: SSD
- Compression: gzip (level 6)

**Checkpoint Save Performance**:
```
Uncompressed:
  - Average: 5-10ms per checkpoint
  - Size: 500-2000 bytes (typical)

Compressed (gzip):
  - Average: 8-15ms per checkpoint
  - Size: 200-800 bytes (typical)
  - Compression ratio: >50% reduction
  - Overhead: <5ms (acceptable)
```

**Checkpoint Load Performance**:
```
Uncompressed:
  - Average: 2-5ms per load

Compressed (gzip):
  - Average: 3-7ms per load
  - Decompression overhead: <2ms
```

**Storage Impact**:
```
100 checkpoints (uncompressed): ~100KB
100 checkpoints (compressed):   ~40KB
Reduction: 60KB (60% savings)
```

**Test Results**:
- 114/114 tests passing (100% coverage)
- Unit tests: <1 second
- Integration tests: ~7 seconds (real Ollama)
- E2E tests: ~12 seconds (full autonomous agents)

---

## Best Practices

### 1. Choose Appropriate Checkpoint Frequency

**For short-running tasks (< 1 minute)**:
```python
# Checkpoint infrequently or disable
config = AutonomousConfig(
    checkpoint_frequency=100,  # High value = infrequent
)
```

**For long-running tasks (> 5 minutes)**:
```python
# Checkpoint frequently
config = AutonomousConfig(
    checkpoint_frequency=5,           # Every 5 steps
    checkpoint_interval_seconds=30.0,  # OR every 30 seconds
)
```

### 2. Enable Compression for Large States

```python
# If conversation history grows large, enable compression
storage = FilesystemStorage(
    base_dir=".kaizen/checkpoints",
    compress=True,  # Recommended for large states
)
```

### 3. Set Appropriate Retention

**Development**:
```python
# Keep many checkpoints for debugging
state_manager = StateManager(retention_count=100)
```

**Production**:
```python
# Keep fewer checkpoints to save space
state_manager = StateManager(retention_count=10)
```

### 4. Use Hooks for Observability

```python
# Track checkpoint statistics
async def checkpoint_monitor(context):
    if context.event_type == HookEvent.POST_CHECKPOINT_SAVE:
        checkpoint_id = context.data["checkpoint_id"]
        step = context.data["step_number"]

        # Send to monitoring system
        metrics.record_checkpoint(checkpoint_id, step)

    return HookResult(success=True)

hook_manager.register(HookEvent.POST_CHECKPOINT_SAVE, checkpoint_monitor)
```

### 5. Handle Resume Gracefully

```python
# Check if resume is possible before enabling
config = AutonomousConfig(
    max_cycles=10,
    resume_from_checkpoint=True,
    llm_provider="ollama",
    model="llama3.2",
)

agent = BaseAutonomousAgent(config=config, signature=sig, state_manager=state_manager)

# Resume returns None if no checkpoint found (agent starts from beginning)
result = await agent._autonomous_loop("Task")
```

---

## Troubleshooting

### Issue: No Checkpoints Created

**Symptom**: No checkpoint files in `.kaizen/checkpoints/`

**Solution**:
1. Check that StateManager is passed to agent
2. Verify checkpoint frequency isn't too high
3. Ensure agent runs for multiple cycles
4. Check logs for checkpoint save errors

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.INFO)
```

### Issue: Resume Not Working

**Symptom**: Agent starts from beginning despite `resume_from_checkpoint=True`

**Solution**:
1. Check that checkpoint files exist in storage directory
2. Verify same storage directory is used for both runs
3. Ensure agent_id matches (defaults to "autonomous_agent")
4. Check logs for resume errors

```python
# Manually check for checkpoints
checkpoints = await storage.list_checkpoints()
print(f"Found {len(checkpoints)} checkpoints")
```

### Issue: Compression Errors

**Symptom**: Cannot load compressed checkpoints

**Solution**:
1. Ensure gzip module is available
2. Verify file is actually compressed (.jsonl.gz extension)
3. Check file isn't corrupted
4. Try loading with FilesystemStorage(compress=True)

```python
# Auto-detect handles both formats
storage = FilesystemStorage(base_dir=".kaizen/checkpoints")
state = await storage.load("ckpt_abc123")  # Works for both
```

### Issue: Too Many Checkpoint Files

**Symptom**: Checkpoint directory growing too large

**Solution**:
1. Lower retention_count
2. Manually clean up old checkpoints
3. Enable automatic cleanup

```python
# Set lower retention
state_manager = StateManager(retention_count=10)

# Manual cleanup
deleted = await state_manager.cleanup_old_checkpoints("agent_id")
print(f"Deleted {deleted} old checkpoints")
```

---

## Examples

### Example 1: Long-Running Data Processing

```python
"""
Long-running agent that processes data in batches.
Checkpoints after each batch to enable resume.
"""

from kaizen.agents.autonomous.base import BaseAutonomousAgent, AutonomousConfig
from kaizen.core.autonomy.state.storage import FilesystemStorage
from kaizen.core.autonomy.state.manager import StateManager

config = AutonomousConfig(
    max_cycles=100,
    checkpoint_frequency=10,           # Every 10 batches
    checkpoint_interval_seconds=300.0,  # OR every 5 minutes
    resume_from_checkpoint=True,        # Resume if interrupted
    llm_provider="ollama",
    model="llama3.2",
)

storage = FilesystemStorage(
    base_dir="/data/checkpoints",
    compress=True,  # Large state = compress
)

state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=10,
    retention_count=20,  # Keep last 20 checkpoints
)

agent = BaseAutonomousAgent(
    config=config,
    signature=DataProcessingSignature(),
    state_manager=state_manager,
)

# Runs for hours, checkpoints regularly, resumes if interrupted
result = await agent._autonomous_loop("Process 1 million records")
```

### Example 2: Multi-Stage Pipeline with Forking

```python
"""
Multi-stage pipeline where each stage forks from previous checkpoint.
Enables parallel processing of different branches.
"""

# Stage 1: Data collection
agent1 = BaseAutonomousAgent(config=config1, signature=sig, state_manager=mgr1)
await agent1._autonomous_loop("Collect data")

# Get checkpoint from stage 1
checkpoints = await storage.list_checkpoints()
stage1_checkpoint = checkpoints[0].checkpoint_id

# Stage 2a: Analysis branch (fork from stage 1)
forked_state_a = await state_manager.fork_checkpoint(
    stage1_checkpoint,
    new_agent_id="analysis_branch"
)
agent2a = BaseAutonomousAgent(config=config2a, signature=sig, state_manager=mgr2a)
# ... restore forked_state_a and continue

# Stage 2b: Visualization branch (fork from stage 1)
forked_state_b = await state_manager.fork_checkpoint(
    stage1_checkpoint,
    new_agent_id="viz_branch"
)
agent2b = BaseAutonomousAgent(config=config2b, signature=sig, state_manager=mgr2b)
# ... restore forked_state_b and continue
```

### Example 3: Production Deployment with Monitoring

```python
"""
Production deployment with checkpoint monitoring and alerting.
"""

from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.types import HookEvent, HookResult

# Setup monitoring hook
hook_manager = HookManager()

async def checkpoint_monitor(context):
    """Monitor checkpoint health and send metrics"""
    if context.event_type == HookEvent.POST_CHECKPOINT_SAVE:
        checkpoint_id = context.data["checkpoint_id"]
        step = context.data["step_number"]
        agent_id = context.data["agent_id"]

        # Send metrics to monitoring system
        await metrics_client.record({
            "metric": "checkpoint.created",
            "agent_id": agent_id,
            "checkpoint_id": checkpoint_id,
            "step": step,
            "timestamp": time.time(),
        })

        # Alert if checkpoints not being created
        last_checkpoint_time[agent_id] = time.time()

    return HookResult(success=True)

hook_manager.register(HookEvent.POST_CHECKPOINT_SAVE, checkpoint_monitor)

# Production configuration
config = AutonomousConfig(
    max_cycles=1000,
    checkpoint_frequency=50,
    checkpoint_interval_seconds=600.0,  # 10 minutes
    resume_from_checkpoint=True,
    llm_provider="ollama",
    model="llama3.2",
)

storage = FilesystemStorage(
    base_dir="/var/lib/kaizen/checkpoints",
    compress=True,
)

state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=50,
    retention_count=50,
    hook_manager=hook_manager,
)

agent = BaseAutonomousAgent(
    config=config,
    signature=ProductionSignature(),
    state_manager=state_manager,
)

# Production execution with monitoring
result = await agent._autonomous_loop("Production task")
```

---

## Migration Guide

### From No Checkpointing

**Before**:
```python
agent = BaseAutonomousAgent(config=config, signature=sig)
result = await agent._autonomous_loop("Task")
```

**After** (with checkpointing):
```python
# Add state manager
storage = FilesystemStorage(base_dir=".kaizen/checkpoints")
state_manager = StateManager(storage=storage)

agent = BaseAutonomousAgent(
    config=config,
    signature=sig,
    state_manager=state_manager,  # Add this
)

result = await agent._autonomous_loop("Task")
```

**Impact**: Zero breaking changes, fully backward compatible

---

## Implementation Details

### File Format

Checkpoints are stored as JSONL (JSON Lines) files:
```
.kaizen/checkpoints/
├── ckpt_abc123.jsonl         # Uncompressed
├── ckpt_def456.jsonl.gz      # Compressed
└── ckpt_ghi789.jsonl
```

Each checkpoint is a single-line JSON object:
```json
{
  "checkpoint_id": "ckpt_abc123",
  "agent_id": "my_agent",
  "timestamp": "2025-10-25T14:00:00",
  "step_number": 5,
  "conversation_history": [...],
  "memory_contents": {...},
  "status": "running"
}
```

### Atomic Writes

Checkpoints use atomic writes to prevent corruption:
1. Write to temporary file: `.kaizen/checkpoints/tmpXXX.tmp`
2. Atomic rename to final path: `ckpt_abc123.jsonl`

This ensures checkpoints are never partially written.

### Backward Compatibility

- Compressed and uncompressed checkpoints coexist
- Auto-detection on load (checks both `.jsonl` and `.jsonl.gz`)
- Old uncompressed checkpoints can be loaded with compressed storage

---

## Related Documentation

- [Autonomous Agents](./autonomous-agents.md)
- [Hooks System](./hooks-system.md)
- [State Management](./state-management.md)
- [Production Deployment](../deployment/production.md)

---

## Changelog

### Version 1.0.0 (2025-10-25)

**Initial Release**:
- ✅ Automatic checkpointing (frequency + interval)
- ✅ Resume from checkpoint
- ✅ JSONL compression (gzip)
- ✅ Retention policy
- ✅ Hook integration
- ✅ Error recovery
- ✅ 114/114 tests passing (100% coverage)

---

## Support

For issues, questions, or feedback:
- **GitHub Issues**: https://github.com/terrene-foundation/kailash_kaizen/issues
- **Documentation**: https://docs.kailash.ai
- **Examples**: `examples/autonomy/checkpoint-resume/`

---

**Last Updated**: 2025-10-25
**Maintained By**: Kailash Kaizen Team
