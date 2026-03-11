# ADR-015: State Persistence Strategy

## Status
**Proposed** - Phase 3 Implementation (Weeks 23-30)

**Priority**: P0 - CRITICAL (enables resumable autonomous execution)

## Context

Kaizen agents currently have **no state persistence**. When an agent stops (crash, interrupt, timeout), all progress is lost:

**Critical Problems**:
- **30+ hour autonomous execution**: Cannot resume if agent crashes at hour 29
- **No recovery from failures**: Transient errors (network issues, API rate limits) require full restart
- **No debugging**: Cannot inspect agent state at failure point
- **No branching**: Cannot fork execution to explore alternatives
- **No rollback**: Cannot undo harmful actions

**Production Impact**:
- Users cannot deploy long-running agents safely
- Every crash = complete restart = wasted compute and API costs
- No reproducibility for debugging complex failures
- Cannot implement "undo" functionality
- Cannot support multi-day agent execution

**Problem**: Kaizen needs a **state persistence system** that:
1. Checkpoints agent state incrementally (every N steps or M seconds)
2. Enables resuming execution from any checkpoint
3. Supports forking execution to explore alternatives
4. Provides state inspection for debugging
5. Integrates with existing Kailash SDK workflow state

**Inspiration**: Claude Code uses JSONL checkpoints that enable:
- Resume after crash/interrupt
- Fork execution from any checkpoint
- Full state inspection for debugging
- Incremental saves (not full state dumps)

## Requirements

### Functional Requirements

1. **FR-1**: Checkpoint agent state every N steps or M seconds (configurable)
2. **FR-2**: Resume execution from latest checkpoint
3. **FR-3**: Resume execution from specific checkpoint (by ID or timestamp)
4. **FR-4**: Fork execution from checkpoint (create new branch)
5. **FR-5**: List all checkpoints with metadata (timestamp, step count, status)
6. **FR-6**: Inspect checkpoint state (for debugging)
7. **FR-7**: Delete old checkpoints (retention policy)
8. **FR-8**: Export/import checkpoints (portability)

### Non-Functional Requirements

1. **NFR-1**: Checkpoint save latency <1000ms (p95)
2. **NFR-2**: Checkpoint load latency <500ms (p95)
3. **NFR-3**: Storage overhead <100MB per checkpoint (JSONL compression)
4. **NFR-4**: Checkpoint frequency: Every 10 steps OR every 60 seconds
5. **NFR-5**: Retention: Keep last 100 checkpoints by default

### State Components to Persist

1. **Agent State**:
   - Conversation history (messages, tool calls, results)
   - Memory contents (short-term, long-term, episodic)
   - Agent configuration (signature, model, temperature)

2. **Execution State**:
   - Current step number
   - Pending actions (tools to execute)
   - Completed actions (tool execution history)

3. **Permission State**:
   - Budget tracking (total spent, remaining)
   - Approval history (which tools were approved/denied)
   - Permission rules applied

4. **Tool State**:
   - Tool usage counts
   - Tool execution results (cached)
   - Tool errors and retries

5. **Specialist State** (from 013):
   - Active specialists
   - Specialist invocation history
   - Specialist-specific memory

6. **Workflow State** (Kailash SDK Integration):
   - Workflow execution state (from LocalRuntime)
   - Node execution results
   - Workflow metadata (run_id, timestamps)

## Decision

We will implement a **State Persistence System** in `kaizen/core/autonomy/state/` with the following design:

### Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│ BaseAgent (Execution Layer)                              │
│ - await state_manager.checkpoint()  # Every N steps      │
│ - await state_manager.resume(checkpoint_id)              │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ Checkpoint operations
                        ▼
┌──────────────────────────────────────────────────────────┐
│ StateManager (Orchestration)                             │
│ - checkpoint(state) → checkpoint_id                      │
│ - resume(checkpoint_id) → restored_state                 │
│ - fork(checkpoint_id) → new_state                        │
│ - list_checkpoints() → metadata[]                        │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ Storage operations
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Storage Backend (Pluggable)                              │
│ - FilesystemStorage (default) → .kaizen/checkpoints/     │
│ - DatabaseStorage (via DataFlow) → PostgreSQL/SQLite     │
│ - RemoteStorage (S3, GCS) → Cloud storage                │
└──────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. State Types (`kaizen/core/autonomy/state/types.py`)

```python
from dataclasses import dataclass, field
from typing import Any, Literal
from datetime import datetime
import uuid

@dataclass
class AgentState:
    """Complete agent state at a checkpoint"""

    # Identification
    checkpoint_id: str = field(default_factory=lambda: f"ckpt_{uuid.uuid4().hex[:12]}")
    agent_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    step_number: int = 0

    # Conversation state
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    memory_contents: dict[str, Any] = field(default_factory=dict)

    # Execution state
    pending_actions: list[dict[str, Any]] = field(default_factory=list)
    completed_actions: list[dict[str, Any]] = field(default_factory=list)

    # Permission state
    budget_spent_usd: float = 0.0
    approval_history: list[dict[str, Any]] = field(default_factory=list)

    # Tool state
    tool_usage_counts: dict[str, int] = field(default_factory=dict)
    tool_results_cache: dict[str, Any] = field(default_factory=dict)

    # Specialist state (from 013)
    active_specialists: list[str] = field(default_factory=list)
    specialist_invocations: list[dict[str, Any]] = field(default_factory=list)

    # Workflow state (Kailash SDK)
    workflow_run_id: str | None = None
    workflow_state: dict[str, Any] = field(default_factory=dict)

    # Metadata
    parent_checkpoint_id: str | None = None  # For forking
    status: Literal["running", "completed", "failed", "interrupted"] = "running"
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class CheckpointMetadata:
    """Lightweight metadata for checkpoint listing"""
    checkpoint_id: str
    agent_id: str
    timestamp: datetime
    step_number: int
    status: str
    size_bytes: int
    parent_checkpoint_id: str | None = None
```

#### 2. Storage Backend Protocol (`kaizen/core/autonomy/state/storage.py`)

```python
from typing import Protocol, runtime_checkable
from abc import abstractmethod

@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for checkpoint storage backends"""

    @abstractmethod
    async def save(self, state: AgentState) -> str:
        """Save checkpoint, return checkpoint_id"""
        pass

    @abstractmethod
    async def load(self, checkpoint_id: str) -> AgentState:
        """Load checkpoint by ID"""
        pass

    @abstractmethod
    async def list_checkpoints(self, agent_id: str | None = None) -> list[CheckpointMetadata]:
        """List all checkpoints (optionally filtered by agent_id)"""
        pass

    @abstractmethod
    async def delete(self, checkpoint_id: str) -> None:
        """Delete checkpoint"""
        pass

    @abstractmethod
    async def exists(self, checkpoint_id: str) -> bool:
        """Check if checkpoint exists"""
        pass
```

#### 3. Filesystem Storage (`kaizen/core/autonomy/state/backends/filesystem.py`)

```python
import json
import os
from pathlib import Path
from datetime import datetime

class FilesystemStorage:
    """Filesystem-based checkpoint storage (JSONL format)"""

    def __init__(self, base_dir: str | Path = ".kaizen/checkpoints"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, state: AgentState) -> str:
        """Save checkpoint as JSONL file"""
        checkpoint_path = self.base_dir / f"{state.checkpoint_id}.jsonl"

        # Convert state to dict
        state_dict = asdict(state)
        state_dict["timestamp"] = state.timestamp.isoformat()

        # Write as JSONL (one line per checkpoint for append efficiency)
        with open(checkpoint_path, "w") as f:
            json.dump(state_dict, f)
            f.write("\n")

        logger.info(f"Checkpoint saved: {state.checkpoint_id} ({checkpoint_path.stat().st_size} bytes)")
        return state.checkpoint_id

    async def load(self, checkpoint_id: str) -> AgentState:
        """Load checkpoint from JSONL file"""
        checkpoint_path = self.base_dir / f"{checkpoint_id}.jsonl"

        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")

        with open(checkpoint_path, "r") as f:
            state_dict = json.loads(f.read().strip())

        # Convert ISO timestamp back to datetime
        state_dict["timestamp"] = datetime.fromisoformat(state_dict["timestamp"])

        return AgentState(**state_dict)

    async def list_checkpoints(self, agent_id: str | None = None) -> list[CheckpointMetadata]:
        """List all checkpoints in directory"""
        checkpoints = []

        for path in self.base_dir.glob("*.jsonl"):
            # Read first line to get metadata (avoid loading full state)
            with open(path, "r") as f:
                state_dict = json.loads(f.read().strip())

            # Filter by agent_id if specified
            if agent_id and state_dict.get("agent_id") != agent_id:
                continue

            metadata = CheckpointMetadata(
                checkpoint_id=state_dict["checkpoint_id"],
                agent_id=state_dict["agent_id"],
                timestamp=datetime.fromisoformat(state_dict["timestamp"]),
                step_number=state_dict["step_number"],
                status=state_dict["status"],
                size_bytes=path.stat().st_size,
                parent_checkpoint_id=state_dict.get("parent_checkpoint_id")
            )
            checkpoints.append(metadata)

        # Sort by timestamp (newest first)
        return sorted(checkpoints, key=lambda c: c.timestamp, reverse=True)

    async def delete(self, checkpoint_id: str) -> None:
        """Delete checkpoint file"""
        checkpoint_path = self.base_dir / f"{checkpoint_id}.jsonl"
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.info(f"Checkpoint deleted: {checkpoint_id}")

    async def exists(self, checkpoint_id: str) -> bool:
        """Check if checkpoint exists"""
        return (self.base_dir / f"{checkpoint_id}.jsonl").exists()
```

#### 4. State Manager (`kaizen/core/autonomy/state/manager.py`)

```python
import asyncio
import time
from typing import Callable
from datetime import datetime, timedelta

class StateManager:
    """Manages agent state persistence and restoration"""

    def __init__(
        self,
        storage: StorageBackend,
        checkpoint_interval_steps: int = 10,
        checkpoint_interval_seconds: float = 60.0,
        retention_count: int = 100
    ):
        self.storage = storage
        self.checkpoint_interval_steps = checkpoint_interval_steps
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self.retention_count = retention_count

        self._last_checkpoint_time: float = 0
        self._last_checkpoint_step: int = 0

    async def should_checkpoint(self, current_step: int) -> bool:
        """Determine if checkpoint should be created now"""
        step_trigger = (current_step - self._last_checkpoint_step) >= self.checkpoint_interval_steps
        time_trigger = (time.time() - self._last_checkpoint_time) >= self.checkpoint_interval_seconds

        return step_trigger or time_trigger

    async def checkpoint(self, state: AgentState) -> str:
        """Create checkpoint from current state"""
        start_time = time.perf_counter()

        # Save checkpoint
        checkpoint_id = await self.storage.save(state)

        # Update tracking
        self._last_checkpoint_time = time.time()
        self._last_checkpoint_step = state.step_number

        # Apply retention policy
        await self._apply_retention_policy(state.agent_id)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"Checkpoint created: {checkpoint_id} (step {state.step_number}, {duration_ms:.1f}ms)")

        return checkpoint_id

    async def resume(self, checkpoint_id: str) -> AgentState:
        """Resume execution from checkpoint"""
        start_time = time.perf_counter()

        state = await self.storage.load(checkpoint_id)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"Checkpoint loaded: {checkpoint_id} (step {state.step_number}, {duration_ms:.1f}ms)")

        return state

    async def fork(self, checkpoint_id: str) -> AgentState:
        """Create new execution branch from checkpoint"""
        # Load original state
        original_state = await self.storage.load(checkpoint_id)

        # Create new state with new checkpoint_id
        forked_state = AgentState(
            **{k: v for k, v in asdict(original_state).items() if k != "checkpoint_id"}
        )
        forked_state.parent_checkpoint_id = checkpoint_id
        forked_state.timestamp = datetime.utcnow()

        logger.info(f"Execution forked: {checkpoint_id} → {forked_state.checkpoint_id}")

        return forked_state

    async def list_checkpoints(self, agent_id: str | None = None) -> list[CheckpointMetadata]:
        """List checkpoints with optional filtering"""
        return await self.storage.list_checkpoints(agent_id=agent_id)

    async def get_latest_checkpoint(self, agent_id: str) -> CheckpointMetadata | None:
        """Get most recent checkpoint for agent"""
        checkpoints = await self.list_checkpoints(agent_id=agent_id)
        return checkpoints[0] if checkpoints else None

    async def _apply_retention_policy(self, agent_id: str) -> None:
        """Delete old checkpoints beyond retention limit"""
        checkpoints = await self.list_checkpoints(agent_id=agent_id)

        if len(checkpoints) > self.retention_count:
            # Delete oldest checkpoints
            to_delete = checkpoints[self.retention_count:]
            for checkpoint in to_delete:
                await self.storage.delete(checkpoint.checkpoint_id)
                logger.debug(f"Retention cleanup: deleted {checkpoint.checkpoint_id}")
```

### Integration with BaseAgent

```python
# kaizen/core/base_agent.py

class BaseAgent(Node):
    def __init__(self, config: BaseAgentConfig):
        super().__init__(config)
        self.state_manager: StateManager | None = None
        self._current_step = 0

    def enable_state_persistence(
        self,
        storage: StorageBackend | None = None,
        checkpoint_interval_steps: int = 10,
        checkpoint_interval_seconds: float = 60.0
    ) -> None:
        """Enable state persistence (opt-in)"""
        if storage is None:
            storage = FilesystemStorage()

        self.state_manager = StateManager(
            storage=storage,
            checkpoint_interval_steps=checkpoint_interval_steps,
            checkpoint_interval_seconds=checkpoint_interval_seconds
        )

    async def run(self, **kwargs) -> dict[str, Any]:
        """Agent execution loop with checkpointing"""

        # Auto-checkpoint if enabled
        if self.state_manager:
            self._current_step += 1

            if await self.state_manager.should_checkpoint(self._current_step):
                state = await self._capture_state()
                await self.state_manager.checkpoint(state)

        # Execute agent
        result = await super().run(**kwargs)

        return result

    async def _capture_state(self) -> AgentState:
        """Capture current agent state for checkpoint"""
        return AgentState(
            agent_id=self.config.name,
            step_number=self._current_step,
            conversation_history=self._get_conversation_history(),
            memory_contents=self._get_memory_contents(),
            pending_actions=self._get_pending_actions(),
            completed_actions=self._get_completed_actions(),
            budget_spent_usd=self._get_budget_spent(),
            approval_history=self._get_approval_history(),
            tool_usage_counts=self._get_tool_usage_counts(),
            workflow_run_id=self._workflow_run_id,
            workflow_state=self._get_workflow_state()
        )

    async def resume_from_checkpoint(self, checkpoint_id: str) -> None:
        """Resume agent from checkpoint"""
        if not self.state_manager:
            raise RuntimeError("State persistence not enabled")

        state = await self.state_manager.resume(checkpoint_id)

        # Restore state
        self._current_step = state.step_number
        self._restore_conversation_history(state.conversation_history)
        self._restore_memory_contents(state.memory_contents)
        self._restore_pending_actions(state.pending_actions)
        self._restore_workflow_state(state.workflow_state)

        logger.info(f"Agent resumed from checkpoint {checkpoint_id} at step {self._current_step}")
```

### User Code Examples

#### Example 1: Enable Checkpointing
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.state import FilesystemStorage

agent = BaseAgent(config=config)

# Enable state persistence with default settings
agent.enable_state_persistence()

# Run agent (auto-checkpoints every 10 steps or 60 seconds)
result = await agent.run(input="Analyze this dataset")
```

#### Example 2: Resume from Crash
```python
# List checkpoints
checkpoints = await agent.state_manager.list_checkpoints(agent_id="my-agent")
latest = checkpoints[0]

# Resume from latest checkpoint
await agent.resume_from_checkpoint(latest.checkpoint_id)

# Continue execution
result = await agent.run(input="Continue from where you left off")
```

#### Example 3: Fork Execution
```python
# Fork from a specific checkpoint
forked_state = await agent.state_manager.fork(checkpoint_id="ckpt_abc123")

# Create new agent with forked state
new_agent = BaseAgent(config=config)
new_agent.enable_state_persistence()
await new_agent._restore_from_state(forked_state)

# Run alternative path
result = await new_agent.run(input="Try a different approach")
```

## Consequences

### Positive

1. **✅ Resumable Execution**: Agents can resume after crashes, interrupts, or timeouts
2. **✅ Reduced Waste**: No need to restart long-running agents from scratch
3. **✅ Debugging**: Inspect agent state at any checkpoint
4. **✅ Branching**: Explore alternative execution paths
5. **✅ Rollback**: Undo harmful actions by reverting to previous checkpoint
6. **✅ Cost Savings**: Avoid re-running expensive LLM calls after crashes

### Negative

1. **⚠️ Storage Overhead**: ~100MB per checkpoint for large conversation histories
2. **⚠️ Performance**: 500-1000ms checkpoint latency (I/O bound)
3. **⚠️ Complexity**: More moving parts (storage backends, retention policies)
4. **⚠️ State Drift**: Checkpoint might not capture all external state (files, databases)

### Mitigations

1. **Storage**: JSONL compression, retention policies, remote storage support
2. **Performance**: Async I/O, incremental checkpoints, background saves
3. **Complexity**: Clear documentation, default configuration works out-of-the-box
4. **State Drift**: Document limitations, provide hooks for custom state capture

## Performance Targets

| Metric | Target | Validation |
|--------|--------|------------|
| Checkpoint save latency (p95) | <1000ms | Benchmark with large state |
| Checkpoint load latency (p95) | <500ms | Benchmark with large state |
| Storage overhead per checkpoint | <100MB | Measure with 1000-step conversation |
| Checkpoint interval (default) | 10 steps OR 60 seconds | Configurable |
| Retention (default) | 100 checkpoints | Configurable |

See `PERFORMANCE_PARITY_PLAN.md` for full benchmarking strategy.

## Alternatives Considered

### Alternative 1: Full State Dumps (Pickle/Marshal)
**Rejected**: Not portable across Python versions, security risks, hard to inspect

### Alternative 2: Database-Only Storage
**Rejected**: Requires database setup, slower for filesystem-based workflows

### Alternative 3: Git-Based Versioning
**Rejected**: Too heavyweight, unnecessary features (branching already handled)

## Implementation Plan

**Phase 3 Timeline**: Weeks 23-30 (8 weeks)

| Week | Tasks |
|------|-------|
| 23-24 | Implement core types, StorageBackend protocol, FilesystemStorage |
| 25-26 | StateManager implementation, checkpoint/resume/fork logic |
| 27 | BaseAgent integration, auto-checkpointing |
| 28 | DatabaseStorage backend (via DataFlow) |
| 29 | Retention policies, compression, optimization |
| 30 | Performance benchmarks, documentation, examples |

**Deliverables**:
- [ ] `kaizen/core/autonomy/state/` module (~1200 lines)
- [ ] 2 storage backends (filesystem, database)
- [ ] BaseAgent checkpointing integration
- [ ] 50+ unit/integration tests
- [ ] 5 example use cases
- [ ] Performance benchmark suite
- [ ] Comprehensive documentation

## Testing Strategy

### Tier 1: Unit Tests
```python
async def test_filesystem_storage_save_load():
    storage = FilesystemStorage(base_dir="/tmp/test-checkpoints")
    state = AgentState(agent_id="test", step_number=5)

    checkpoint_id = await storage.save(state)
    loaded_state = await storage.load(checkpoint_id)

    assert loaded_state.agent_id == "test"
    assert loaded_state.step_number == 5
```

### Tier 2: Integration Tests
```python
@pytest.mark.tier2
async def test_agent_checkpointing():
    agent = BaseAgent(config=config)
    agent.enable_state_persistence()

    # Run for 20 steps (should create 2 checkpoints at steps 10, 20)
    for i in range(20):
        await agent.run(input=f"Step {i}")

    checkpoints = await agent.state_manager.list_checkpoints(agent_id=agent.config.name)
    assert len(checkpoints) >= 2
```

### Tier 3: E2E Tests
```python
@pytest.mark.tier3
async def test_resume_after_crash():
    # Simulate crash
    agent = BaseAgent(config=config)
    agent.enable_state_persistence()

    await agent.run(input="Step 1")
    checkpoints = await agent.state_manager.list_checkpoints()
    crash_checkpoint = checkpoints[0].checkpoint_id

    # Kill agent
    del agent

    # Resume from checkpoint
    new_agent = BaseAgent(config=config)
    new_agent.enable_state_persistence()
    await new_agent.resume_from_checkpoint(crash_checkpoint)

    # Verify state restored
    assert new_agent._current_step > 0
```

## Documentation Requirements

- [ ] **ADR** (this document)
- [ ] **API Reference**: `docs/reference/state-persistence-api.md`
- [ ] **Tutorial**: `docs/guides/checkpointing-tutorial.md`
- [ ] **Storage Backends**: `docs/reference/storage-backends.md`
- [ ] **Troubleshooting**: `docs/reference/state-persistence-troubleshooting.md`

## References

1. **Gap Analysis**: `.claude/improvements/CLAUDE_AGENT_SDK_KAIZEN_GAP_ANALYSIS.md`
2. **Implementation Proposal**: `.claude/improvements/KAIZEN_AUTONOMOUS_AGENT_ENHANCEMENT_PROPOSAL.md` (Section 3.5)
3. **Performance Plan**: `.claude/improvements/PERFORMANCE_PARITY_PLAN.md` (Phase 3)

## Dependencies

**This ADR depends on**:
- 013: Specialist System (for specialist state capture)
- 014: Hooks System (for checkpoint hooks)

**Other ADRs depend on this**:
- 016: Interrupt Mechanism (for saving state before interrupt)
- 017: Observability (for checkpoint metrics)

## Approval

**Proposed By**: Kaizen Architecture Team
**Date**: 2025-10-19
**Reviewers**: TBD
**Status**: Proposed (awaiting team review)

---

**Next ADR**: 016: Interrupt Mechanism Design (user control mid-execution)
