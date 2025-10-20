# Architectural Patterns: Claude Agent SDK vs. Kaizen Framework

**Date**: 2025-10-18
**Purpose**: Identify architectural patterns from Claude Agent SDK that Kaizen should adopt
**Focus**: Patterns enabling autonomous agent development

---

## 1. Control Flow Patterns

### Pattern 1.1: Bidirectional Message Protocol

**Claude Agent SDK Pattern (Observed)**:

```python
# Agent can send messages to client AND receive commands
class AgentRuntime:
    def run_agent(self, agent: Agent, task: str):
        # Send initial message
        self.send_to_client({
            "type": "agent_start",
            "agent_id": agent.id,
            "task": task
        })

        # Execute with bidirectional communication
        while not task_complete:
            # Agent thinks
            next_action = agent.think()

            # Ask client for approval/input if needed
            if next_action.requires_approval:
                response = self.request_from_client({
                    "type": "approval_request",
                    "action": next_action.describe(),
                    "risk_level": next_action.risk_level
                })

                if not response.approved:
                    next_action = agent.fallback_action()

            # Execute action
            result = agent.execute_action(next_action)

            # Send progress update
            self.send_to_client({
                "type": "progress",
                "completion": agent.progress_percentage(),
                "status": agent.current_status()
            })

        # Send final result
        self.send_to_client({
            "type": "agent_complete",
            "result": agent.final_result()
        })
```

**Kaizen Current State**:

```python
# ONE-WAY: Agent executes to completion
class BaseAgent:
    def run(self, **inputs):
        # No communication channel
        result = self.strategy.execute(self.workflow, inputs)
        return result  # Return only, no progress updates
```

**Gap**: No bidirectional communication, no runtime intervention.

---

**Proposed Kaizen Pattern**:

```python
# Add ControlChannel to BaseAgent
class BaseAgent:
    def __init__(
        self,
        config: BaseAgentConfig,
        signature: Signature,
        control_channel: Optional[ControlChannel] = None
    ):
        self.control_channel = control_channel
        # ... existing init

    def run(self, **inputs):
        if self.control_channel:
            self.control_channel.send({
                "type": "agent_start",
                "agent_id": self.agent_id,
                "inputs": inputs
            })

        # Pre-execution hook with intervention
        inputs = self._pre_execution_hook(inputs)

        # Check for interrupts during execution
        result = self._execute_with_control(**inputs)

        if self.control_channel:
            self.control_channel.send({
                "type": "agent_complete",
                "result": result
            })

        return result

    def _execute_with_control(self, **inputs):
        """Execute with periodic interrupt checks."""
        # Inject interrupt checks into workflow
        workflow = self._inject_interrupt_checks(self.workflow)
        return self.strategy.execute(workflow, inputs)

    def _inject_interrupt_checks(self, workflow: WorkflowBuilder):
        """Wrap nodes with interrupt check logic."""
        if not self.control_channel:
            return workflow

        # Insert InterruptCheckNode between every node
        # This allows pausing/resuming mid-workflow
        enhanced_workflow = WorkflowBuilder()
        for node in workflow.nodes:
            enhanced_workflow.add_node(
                "InterruptCheckNode",
                f"interrupt_check_{node.id}",
                {"control_channel": self.control_channel}
            )
            enhanced_workflow.add_node(node.type, node.id, node.config)

        return enhanced_workflow
```

**Benefits**:
1. Agents can communicate progress to clients
2. Clients can interrupt/pause/resume agents
3. Approval workflows become native, not separate agents
4. Backward compatible (control_channel defaults to None)

**Implementation Complexity**: High
- Requires ControlChannel abstraction
- Requires InterruptCheckNode implementation
- Requires transport layer (SSE, WebSocket, stdio)
- Requires client SDK updates

**Priority**: P0 (enables autonomous agent control)

---

### Pattern 1.2: Hook-Based Extension Points

**Claude Agent SDK Pattern (Inferred)**:

```python
# Hooks receive full execution context
class AgentHooks:
    def on_tool_call(
        self,
        tool: str,
        args: dict,
        context: ExecutionContext
    ) -> ToolCallDecision:
        """
        Called before tool execution.

        Returns:
            ALLOW: Execute tool
            DENY: Block tool execution
            ASK_USER: Prompt user for approval
            MODIFY: Use modified args
        """
        # Check permissions
        if not context.permissions.allows_tool(tool):
            return ToolCallDecision.DENY

        # Check risk level
        risk = assess_tool_risk(tool, args, context)
        if risk == "high":
            return ToolCallDecision.ASK_USER

        # Allow safe tools
        return ToolCallDecision.ALLOW

    def on_llm_call(
        self,
        prompt: str,
        model: str,
        context: ExecutionContext
    ) -> Optional[str]:
        """
        Called before LLM invocation.

        Returns:
            None: Use original prompt
            str: Use modified prompt
        """
        # Inject system context
        if context.session_id:
            prompt = f"[Session: {context.session_id}]\n{prompt}"

        # Add safety instructions
        prompt += "\n\n[Safety: Do not generate harmful content]"

        return prompt

    def on_error(
        self,
        error: Exception,
        context: ExecutionContext
    ) -> RecoveryAction:
        """
        Called when error occurs.

        Returns:
            RETRY: Retry with same inputs
            FALLBACK: Use fallback strategy
            ABORT: Stop execution
            CONTINUE: Ignore error and continue
        """
        if isinstance(error, RateLimitError):
            return RecoveryAction.RETRY_WITH_BACKOFF

        if isinstance(error, ModelUnavailableError):
            return RecoveryAction.FALLBACK

        return RecoveryAction.ABORT
```

**Kaizen Current State**:

```python
# Hooks exist but don't receive context or allow blocking
class BaseAgent:
    def _pre_execution_hook(self, inputs: dict) -> dict:
        """Override to add pre-execution logic."""
        return inputs

    def _post_execution_hook(self, result: dict) -> dict:
        """Override to add post-execution logic."""
        return result

    def _handle_error(self, error: Exception) -> None:
        """Override to customize error handling."""
        logger.error(f"Error: {error}")
```

**Gap**: Hooks are simple stubs, no execution context, can't block actions.

---

**Proposed Kaizen Pattern**:

```python
# Enhanced hooks with ExecutionContext
class ExecutionContext:
    """Runtime context passed to hooks."""

    def __init__(
        self,
        agent_id: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        permissions: Optional[PermissionSet] = None,
        control_channel: Optional[ControlChannel] = None
    ):
        self.agent_id = agent_id
        self.session_id = session_id
        self.user_id = user_id
        self.permissions = permissions or PermissionSet()
        self.control_channel = control_channel
        self.metadata: Dict[str, Any] = {}

class BaseAgent:
    def _pre_execution_hook(
        self,
        inputs: dict,
        context: ExecutionContext
    ) -> dict:
        """
        Called before execution with full context.

        Args:
            inputs: Execution inputs
            context: Runtime context (permissions, session, etc.)

        Returns:
            Modified inputs

        Raises:
            PermissionDeniedError: If action not allowed
            UserCancelledError: If user cancels
        """
        # Default: Check permissions
        required_perms = self._required_permissions(inputs)
        if not context.permissions.allows_all(required_perms):
            raise PermissionDeniedError(
                f"Missing permissions: {required_perms}"
            )

        # Check for approval requirement
        if self._needs_approval(inputs, context):
            decision = context.control_channel.request_approval(
                action=self._describe_action(inputs),
                risk_level=self._assess_risk(inputs),
                timeout=30.0
            )

            if decision == ApprovalDecision.DENY:
                raise UserCancelledError("User denied execution")

            if decision == ApprovalDecision.MODIFY:
                inputs = decision.modified_inputs

        return inputs

    def _required_permissions(self, inputs: dict) -> Set[str]:
        """Override to specify required permissions."""
        return set()

    def _needs_approval(self, inputs: dict, context: ExecutionContext) -> bool:
        """Override to specify approval requirements."""
        return False

    def _assess_risk(self, inputs: dict) -> str:
        """Override to assess action risk level."""
        return "low"
```

**Benefits**:
1. Hooks can enforce permissions
2. Hooks can request user approval
3. Hooks can modify execution at runtime
4. Backward compatible (context is optional)

**Implementation Complexity**: Medium
- Requires ExecutionContext class
- Requires PermissionSet class
- Requires ApprovalDecision enum
- Requires updating all hook call sites

**Priority**: P0 (enables permission system)

---

### Pattern 1.3: Interrupt-Based Control

**Claude Agent SDK Pattern (Observed)**:

```python
# User can interrupt agents mid-execution
class AgentController:
    def __init__(self):
        self.interrupt_flag = threading.Event()
        self.pause_flag = threading.Event()

    def interrupt_agent(self):
        """Request agent to stop at next checkpoint."""
        self.interrupt_flag.set()

    def pause_agent(self):
        """Request agent to pause execution."""
        self.pause_flag.set()

    def resume_agent(self):
        """Resume paused agent."""
        self.pause_flag.clear()

    def run_with_control(self, agent: Agent, task: str):
        """Run agent with interrupt support."""
        try:
            while not task_complete:
                # Check for interrupts
                if self.interrupt_flag.is_set():
                    raise InterruptedException("User interrupted")

                # Check for pause
                while self.pause_flag.is_set():
                    time.sleep(0.1)  # Wait until resumed

                # Execute next step
                agent.execute_step()

        except InterruptedException:
            # Save checkpoint
            self.save_checkpoint(agent)
            raise
```

**Kaizen Current State**:

```python
# No interrupt mechanism - runs to completion or timeout
class BaseAgent:
    def run(self, **inputs):
        # No interrupt checks
        result = self.strategy.execute(self.workflow, inputs)
        return result
```

**Gap**: Cannot pause/resume/cancel agents mid-execution.

---

**Proposed Kaizen Pattern**:

```python
# Add interrupt mechanism to Kaizen Core
class InterruptController:
    """Manages agent execution interrupts."""

    def __init__(self):
        self._interrupt_flags: Dict[str, threading.Event] = {}
        self._pause_flags: Dict[str, threading.Event] = {}

    def register_agent(self, agent_id: str):
        """Register agent for interrupt control."""
        self._interrupt_flags[agent_id] = threading.Event()
        self._pause_flags[agent_id] = threading.Event()

    def interrupt(self, agent_id: str):
        """Request agent cancellation."""
        if agent_id in self._interrupt_flags:
            self._interrupt_flags[agent_id].set()

    def pause(self, agent_id: str):
        """Request agent pause."""
        if agent_id in self._pause_flags:
            self._pause_flags[agent_id].set()

    def resume(self, agent_id: str):
        """Resume paused agent."""
        if agent_id in self._pause_flags:
            self._pause_flags[agent_id].clear()

    def check_interrupts(self, agent_id: str):
        """Check for pending interrupts. Raises if interrupted/paused."""
        # Check cancellation
        if self._interrupt_flags.get(agent_id, threading.Event()).is_set():
            raise AgentInterruptedError(f"Agent {agent_id} interrupted by user")

        # Check pause
        pause_flag = self._pause_flags.get(agent_id, threading.Event())
        while pause_flag.is_set():
            time.sleep(0.1)  # Wait for resume


# Global interrupt controller
_interrupt_controller = InterruptController()


# Add to BaseAgent
class BaseAgent:
    def __init__(self, ..., interrupt_controller: Optional[InterruptController] = None):
        self.interrupt_controller = interrupt_controller or _interrupt_controller
        self.interrupt_controller.register_agent(self.agent_id)

    def run(self, **inputs):
        try:
            # Check interrupts before execution
            self.interrupt_controller.check_interrupts(self.agent_id)

            # Execute with interrupt checks
            result = self._execute_with_interrupts(**inputs)

            return result

        except AgentInterruptedError:
            # Save checkpoint
            self._save_checkpoint(inputs)
            raise

    def _execute_with_interrupts(self, **inputs):
        """Execute workflow with periodic interrupt checks."""
        # Use InterruptCheckNode pattern from Pattern 1.1
        workflow = self._inject_interrupt_checks(self.workflow)
        return self.strategy.execute(workflow, inputs)

# InterruptCheckNode for workflow injection
class InterruptCheckNode(Node):
    """Node that checks for interrupts during workflow execution."""

    def execute(self, inputs: dict) -> dict:
        agent_id = inputs.get("agent_id")
        interrupt_controller = inputs.get("interrupt_controller")

        if interrupt_controller:
            interrupt_controller.check_interrupts(agent_id)

        return inputs  # Pass through
```

**Benefits**:
1. Users can cancel long-running agents
2. Users can pause/resume agents
3. Agents save state on interruption
4. Works with existing workflow system

**Implementation Complexity**: Medium
- Requires InterruptController class
- Requires InterruptCheckNode implementation
- Requires checkpoint integration
- Requires client API for pause/resume/cancel

**Priority**: P0 (critical for user control)

---

## 2. State Management Patterns

### Pattern 2.1: Execution Checkpointing

**Claude Agent SDK Pattern (Inferred)**:

```python
# Automatic checkpointing at key execution points
class AgentCheckpoint:
    """Represents a saved agent state."""

    def __init__(
        self,
        agent_id: str,
        task: str,
        inputs: dict,
        partial_results: dict,
        conversation_history: List[Message],
        execution_step: int,
        timestamp: datetime
    ):
        self.agent_id = agent_id
        self.task = task
        self.inputs = inputs
        self.partial_results = partial_results
        self.conversation_history = conversation_history
        self.execution_step = execution_step
        self.timestamp = timestamp

    def serialize(self) -> bytes:
        """Serialize checkpoint for storage."""
        return pickle.dumps({
            "agent_id": self.agent_id,
            "task": self.task,
            "inputs": self.inputs,
            "partial_results": self.partial_results,
            "conversation_history": [msg.to_dict() for msg in self.conversation_history],
            "execution_step": self.execution_step,
            "timestamp": self.timestamp.isoformat()
        })

    @classmethod
    def deserialize(cls, data: bytes) -> "AgentCheckpoint":
        """Deserialize checkpoint from storage."""
        state = pickle.loads(data)
        state["conversation_history"] = [
            Message.from_dict(msg) for msg in state["conversation_history"]
        ]
        state["timestamp"] = datetime.fromisoformat(state["timestamp"])
        return cls(**state)


class AgentRuntime:
    def run_with_checkpoints(
        self,
        agent: Agent,
        task: str,
        checkpoint_interval: int = 5  # Save every 5 steps
    ):
        """Run agent with automatic checkpointing."""
        step = 0

        try:
            while not task_complete:
                # Execute step
                agent.execute_step()
                step += 1

                # Checkpoint periodically
                if step % checkpoint_interval == 0:
                    checkpoint = AgentCheckpoint(
                        agent_id=agent.id,
                        task=task,
                        inputs=agent.inputs,
                        partial_results=agent.partial_results,
                        conversation_history=agent.conversation_history,
                        execution_step=step,
                        timestamp=datetime.now()
                    )
                    self.save_checkpoint(checkpoint)

        except Exception as e:
            # Save checkpoint on error
            checkpoint = AgentCheckpoint(...)
            self.save_checkpoint(checkpoint)
            raise

    def resume_from_checkpoint(self, checkpoint: AgentCheckpoint) -> Agent:
        """Resume agent from saved checkpoint."""
        agent = Agent.from_checkpoint(checkpoint)
        agent.execution_step = checkpoint.execution_step
        return agent
```

**Kaizen Current State**:

```python
# No checkpointing - state is lost on failure
class BaseAgent:
    def run(self, **inputs):
        result = self.strategy.execute(self.workflow, inputs)
        return result  # No state persistence
```

**Gap**: No execution checkpointing, cannot resume after failure.

---

**Proposed Kaizen Pattern**:

```python
# Add checkpoint system to Kaizen Core
from dataclasses import dataclass, asdict
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

@dataclass
class AgentCheckpoint:
    """Serializable agent state checkpoint."""
    agent_id: str
    task_description: str
    inputs: Dict[str, Any]
    partial_results: Dict[str, Any]
    execution_step: int
    workflow_state: Dict[str, Any]  # Workflow execution state
    memory_snapshot: Optional[Dict[str, Any]] = None
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "AgentCheckpoint":
        """Deserialize from JSON."""
        data = json.loads(json_str)
        return cls(**data)


class CheckpointManager:
    """Manages agent checkpoints with pluggable storage."""

    def __init__(self, storage_backend: "CheckpointStorage"):
        self.storage = storage_backend

    def save(self, checkpoint: AgentCheckpoint):
        """Save checkpoint to storage."""
        self.storage.write(
            key=f"{checkpoint.agent_id}_{checkpoint.execution_step}",
            data=checkpoint.to_json()
        )

    def load(self, agent_id: str, step: Optional[int] = None) -> AgentCheckpoint:
        """
        Load checkpoint from storage.

        Args:
            agent_id: Agent identifier
            step: Specific step to load (None = latest)
        """
        if step is None:
            key = self.storage.get_latest_key(agent_id)
        else:
            key = f"{agent_id}_{step}"

        data = self.storage.read(key)
        return AgentCheckpoint.from_json(data)

    def list_checkpoints(self, agent_id: str) -> List[AgentCheckpoint]:
        """List all checkpoints for an agent."""
        keys = self.storage.list_keys(prefix=agent_id)
        return [AgentCheckpoint.from_json(self.storage.read(key)) for key in keys]


# Storage backends
class CheckpointStorage(ABC):
    """Abstract checkpoint storage interface."""

    @abstractmethod
    def write(self, key: str, data: str):
        pass

    @abstractmethod
    def read(self, key: str) -> str:
        pass

    @abstractmethod
    def list_keys(self, prefix: str) -> List[str]:
        pass

    @abstractmethod
    def get_latest_key(self, prefix: str) -> str:
        pass


class FileCheckpointStorage(CheckpointStorage):
    """File-based checkpoint storage."""

    def __init__(self, checkpoint_dir: str = ".kaizen_checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(exist_ok=True)

    def write(self, key: str, data: str):
        path = self.checkpoint_dir / f"{key}.json"
        path.write_text(data)

    def read(self, key: str) -> str:
        path = self.checkpoint_dir / f"{key}.json"
        return path.read_text()

    def list_keys(self, prefix: str) -> List[str]:
        return [
            p.stem for p in self.checkpoint_dir.glob(f"{prefix}_*.json")
        ]

    def get_latest_key(self, prefix: str) -> str:
        keys = self.list_keys(prefix)
        if not keys:
            raise CheckpointNotFoundError(f"No checkpoints for {prefix}")
        # Sort by step number (last part of key)
        return max(keys, key=lambda k: int(k.split("_")[-1]))


class DataFlowCheckpointStorage(CheckpointStorage):
    """DataFlow database-backed checkpoint storage."""

    def __init__(self, dataflow: DataFlow, model_class):
        self.dataflow = dataflow
        self.model_class = model_class

    def write(self, key: str, data: str):
        # Use DataFlow's create node
        self.dataflow.create(
            self.model_class,
            {"checkpoint_key": key, "checkpoint_data": data}
        )

    def read(self, key: str) -> str:
        # Use DataFlow's read node
        result = self.dataflow.read(
            self.model_class,
            filters={"checkpoint_key": key}
        )
        if not result:
            raise CheckpointNotFoundError(f"Checkpoint {key} not found")
        return result[0]["checkpoint_data"]

    # ... implement other methods


# Add to BaseAgent
class BaseAgent:
    def __init__(
        self,
        ...,
        checkpoint_manager: Optional[CheckpointManager] = None,
        checkpoint_interval: int = 5
    ):
        self.checkpoint_manager = checkpoint_manager
        self.checkpoint_interval = checkpoint_interval
        self.execution_step = 0

    def run(self, **inputs):
        """Execute with automatic checkpointing."""
        try:
            result = self._execute_with_checkpoints(**inputs)
            return result

        except Exception as e:
            # Save checkpoint on error
            if self.checkpoint_manager:
                self._save_checkpoint(inputs, partial_results={})
            raise

    def _execute_with_checkpoints(self, **inputs):
        """Execute with periodic checkpoint saves."""
        # ... execution logic

        # Checkpoint after each major step
        if self.checkpoint_manager and self.execution_step % self.checkpoint_interval == 0:
            self._save_checkpoint(inputs, partial_results)

        # ... continue execution

    def _save_checkpoint(self, inputs: dict, partial_results: dict):
        """Save current execution state."""
        checkpoint = AgentCheckpoint(
            agent_id=self.agent_id,
            task_description=self._get_task_description(),
            inputs=inputs,
            partial_results=partial_results,
            execution_step=self.execution_step,
            workflow_state=self._get_workflow_state(),
            memory_snapshot=self._get_memory_snapshot() if self.shared_memory else None
        )
        self.checkpoint_manager.save(checkpoint)

    def resume_from_checkpoint(self, checkpoint: AgentCheckpoint):
        """Resume execution from checkpoint."""
        self.execution_step = checkpoint.execution_step
        self._restore_workflow_state(checkpoint.workflow_state)
        if checkpoint.memory_snapshot and self.shared_memory:
            self._restore_memory_snapshot(checkpoint.memory_snapshot)

        # Continue from last step
        return self.run(**checkpoint.inputs)
```

**Benefits**:
1. Automatic state persistence
2. Resume after crashes
3. Pluggable storage (file, database, cloud)
4. DataFlow integration for enterprise storage

**Implementation Complexity**: High
- Requires CheckpointManager and storage abstractions
- Requires workflow state serialization
- Requires memory snapshot support
- Requires resume logic

**Priority**: P0 (critical for long-running agents)

---

### Pattern 2.2: Distributed State Coordination

**Claude Agent SDK Pattern (Inferred)**:

```python
# Multi-agent workflows share state with conflict resolution
class DistributedState:
    """Shared state with distributed locks and conflict resolution."""

    def __init__(self, backend: "StateBackend"):
        self.backend = backend
        self.locks: Dict[str, Lock] = {}

    def acquire_lock(self, key: str, timeout: float = 5.0) -> bool:
        """Acquire exclusive lock on state key."""
        lock = self.locks.setdefault(key, Lock())
        return lock.acquire(timeout=timeout)

    def release_lock(self, key: str):
        """Release lock on state key."""
        if key in self.locks:
            self.locks[key].release()

    def read(self, key: str) -> Any:
        """Read state value (shared lock)."""
        return self.backend.read(key)

    def write(self, key: str, value: Any, version: Optional[int] = None):
        """
        Write state value with optimistic locking.

        Args:
            key: State key
            value: New value
            version: Expected current version (for conflict detection)

        Raises:
            ConflictError: If version mismatch detected
        """
        current_version = self.backend.get_version(key)

        if version is not None and current_version != version:
            raise ConflictError(
                f"Version conflict: expected {version}, got {current_version}"
            )

        self.backend.write(key, value, version=current_version + 1)

    def compare_and_swap(self, key: str, expected: Any, new: Any) -> bool:
        """
        Atomic compare-and-swap operation.

        Returns:
            True if swap succeeded, False if value changed
        """
        with self.acquire_lock(key):
            current = self.backend.read(key)
            if current == expected:
                self.backend.write(key, new)
                return True
            return False
```

**Kaizen Current State**:

```python
# SharedMemoryPool has no distributed locking
class SharedMemoryPool:
    def write_insight(self, data: dict):
        # No lock - race conditions possible
        self.insights.append(data)

    def read_insights(self, tags: List[str]) -> List[dict]:
        # No versioning - no conflict detection
        return [i for i in self.insights if any(t in i["tags"] for t in tags)]
```

**Gap**: No distributed locks, no conflict resolution, race conditions in multi-agent scenarios.

---

**Proposed Kaizen Pattern**:

```python
# Enhance SharedMemoryPool with distributed state
from threading import RLock
from typing import Optional, Callable
import time

class VersionedState:
    """State value with version tracking."""

    def __init__(self, value: Any, version: int = 0):
        self.value = value
        self.version = version
        self.updated_at = time.time()

class SharedMemoryPool:
    """Enhanced with distributed locks and versioning."""

    def __init__(self):
        self.insights: List[dict] = []
        self.state: Dict[str, VersionedState] = {}
        self.locks: Dict[str, RLock] = {}

    def write_state(
        self,
        key: str,
        value: Any,
        expected_version: Optional[int] = None
    ):
        """
        Write state with optimistic locking.

        Args:
            key: State key
            value: New value
            expected_version: Expected current version (None = no check)

        Raises:
            ConflictError: If version mismatch
        """
        lock = self.locks.setdefault(key, RLock())

        with lock:
            current = self.state.get(key)

            # Check version
            if expected_version is not None:
                if current is None:
                    raise ConflictError(f"State {key} does not exist")
                if current.version != expected_version:
                    raise ConflictError(
                        f"Version conflict on {key}: "
                        f"expected {expected_version}, got {current.version}"
                    )

            # Update with new version
            new_version = (current.version + 1) if current else 0
            self.state[key] = VersionedState(value, new_version)

    def read_state(self, key: str) -> Optional[VersionedState]:
        """Read state with version."""
        return self.state.get(key)

    def compare_and_swap(
        self,
        key: str,
        predicate: Callable[[Any], bool],
        new_value: Any
    ) -> bool:
        """
        Atomic compare-and-swap with custom predicate.

        Args:
            key: State key
            predicate: Function that returns True if swap should proceed
            new_value: New value to set

        Returns:
            True if swap succeeded, False otherwise
        """
        lock = self.locks.setdefault(key, RLock())

        with lock:
            current = self.state.get(key)
            current_value = current.value if current else None

            if predicate(current_value):
                new_version = (current.version + 1) if current else 0
                self.state[key] = VersionedState(new_value, new_version)
                return True

            return False

    def acquire_exclusive(self, key: str, timeout: float = 5.0) -> bool:
        """Acquire exclusive lock on state key."""
        lock = self.locks.setdefault(key, RLock())
        return lock.acquire(timeout=timeout)

    def release_exclusive(self, key: str):
        """Release exclusive lock."""
        if key in self.locks:
            self.locks[key].release()


# Use in multi-agent coordination
class SupervisorWorkerPattern:
    def coordinate_workers(self, task: str):
        """Coordinate workers with distributed state."""
        # Acquire lock for task assignment
        lock_key = f"task_assignment_{task}"

        if self.shared_memory.acquire_exclusive(lock_key, timeout=10.0):
            try:
                # Read current assignments
                assignments = self.shared_memory.read_state("task_assignments")
                current_assignments = assignments.value if assignments else {}

                # Assign task to worker
                worker = self._select_best_worker(task)
                current_assignments[task] = worker.agent_id

                # Write back with version check
                self.shared_memory.write_state(
                    "task_assignments",
                    current_assignments,
                    expected_version=assignments.version if assignments else None
                )

            finally:
                self.shared_memory.release_exclusive(lock_key)
```

**Benefits**:
1. Prevents race conditions in multi-agent workflows
2. Detects and resolves conflicts
3. Atomic operations for critical sections
4. Backward compatible (existing write_insight still works)

**Implementation Complexity**: Medium
- Requires VersionedState class
- Requires lock management in SharedMemoryPool
- Requires conflict resolution strategy
- Requires testing with concurrent agents

**Priority**: P1 (important for multi-agent reliability)

---

## 3. Permission & Security Patterns

### Pattern 3.1: Permission Policy System

**Claude Agent SDK Pattern (Observed)**:

```python
# Declarative permission policies
class PermissionPolicy:
    """Defines what actions an agent can perform."""

    def __init__(
        self,
        allow_file_read: bool = True,
        allow_file_write: bool = False,
        allow_file_delete: bool = False,
        allow_network: bool = True,
        allow_code_execution: bool = False,
        allowed_tools: Optional[Set[str]] = None,
        budget_limits: Optional[Dict[str, float]] = None
    ):
        self.allow_file_read = allow_file_read
        self.allow_file_write = allow_file_write
        self.allow_file_delete = allow_file_delete
        self.allow_network = allow_network
        self.allow_code_execution = allow_code_execution
        self.allowed_tools = allowed_tools or set()
        self.budget_limits = budget_limits or {}

    def allows_action(self, action: str, **kwargs) -> bool:
        """Check if action is allowed."""
        if action == "file_read":
            return self.allow_file_read

        if action == "file_write":
            return self.allow_file_write and self._check_path_safe(kwargs["path"])

        if action == "file_delete":
            return self.allow_file_delete

        if action == "tool_call":
            tool = kwargs["tool"]
            return tool in self.allowed_tools

        if action == "llm_call":
            cost = kwargs.get("estimated_cost", 0)
            budget = self.budget_limits.get("llm", float("inf"))
            return cost <= budget

        return False

    def _check_path_safe(self, path: str) -> bool:
        """Check if file path is safe to write."""
        # Block system paths
        dangerous_paths = ["/etc", "/sys", "/proc", "/dev"]
        return not any(path.startswith(p) for p in dangerous_paths)


# Enforce in agent runtime
class AgentRuntime:
    def execute_action(self, agent: Agent, action: Action, policy: PermissionPolicy):
        """Execute action with permission check."""
        # Check permission
        if not policy.allows_action(action.type, **action.params):
            raise PermissionDeniedError(
                f"Action {action.type} denied by policy"
            )

        # Execute
        return agent.perform_action(action)
```

**Kaizen Current State**:

```python
# No permission system
class BaseAgent:
    def run(self, **inputs):
        # Can execute anything - no permission checks
        result = self.strategy.execute(self.workflow, inputs)
        return result
```

**Gap**: No permission policies, agents can perform any action.

---

**Proposed Kaizen Pattern**:

```python
# Add permission system to Kaizen Core
from enum import Enum
from typing import Set, Dict, Any, Optional
from dataclasses import dataclass, field

class PermissionAction(Enum):
    """Standard permission actions."""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    NETWORK_REQUEST = "network_request"
    CODE_EXECUTION = "code_execution"
    TOOL_CALL = "tool_call"
    LLM_CALL = "llm_call"
    DATABASE_READ = "database_read"
    DATABASE_WRITE = "database_write"


@dataclass
class PermissionPolicy:
    """Declarative permission policy for agents."""

    # File permissions
    allow_file_read: bool = True
    allow_file_write: bool = False
    allow_file_delete: bool = False
    safe_paths: Set[str] = field(default_factory=set)  # Allowed write paths
    blocked_paths: Set[str] = field(default_factory=lambda: {
        "/etc", "/sys", "/proc", "/dev", "/bin", "/sbin"
    })

    # Network permissions
    allow_network: bool = True
    allowed_domains: Optional[Set[str]] = None  # None = all allowed

    # Code execution permissions
    allow_code_execution: bool = False

    # Tool permissions
    allowed_tools: Optional[Set[str]] = None  # None = all allowed
    blocked_tools: Set[str] = field(default_factory=set)

    # Budget limits
    max_cost_per_call: float = 1.0  # Max $ per LLM call
    max_total_cost: float = 100.0  # Max $ total
    current_cost: float = 0.0  # Track current spend

    # Database permissions
    allow_database_read: bool = True
    allow_database_write: bool = False

    def allows(self, action: PermissionAction, **kwargs) -> bool:
        """
        Check if action is allowed.

        Args:
            action: Permission action
            **kwargs: Action-specific parameters

        Returns:
            True if allowed, False otherwise
        """
        if action == PermissionAction.FILE_READ:
            return self.allow_file_read

        if action == PermissionAction.FILE_WRITE:
            path = kwargs.get("path", "")
            return (
                self.allow_file_write
                and self._is_path_safe(path)
            )

        if action == PermissionAction.FILE_DELETE:
            path = kwargs.get("path", "")
            return (
                self.allow_file_delete
                and self._is_path_safe(path)
            )

        if action == PermissionAction.NETWORK_REQUEST:
            domain = kwargs.get("domain", "")
            return (
                self.allow_network
                and (self.allowed_domains is None or domain in self.allowed_domains)
            )

        if action == PermissionAction.CODE_EXECUTION:
            return self.allow_code_execution

        if action == PermissionAction.TOOL_CALL:
            tool = kwargs.get("tool", "")
            return (
                (self.allowed_tools is None or tool in self.allowed_tools)
                and tool not in self.blocked_tools
            )

        if action == PermissionAction.LLM_CALL:
            cost = kwargs.get("estimated_cost", 0)
            return (
                cost <= self.max_cost_per_call
                and (self.current_cost + cost) <= self.max_total_cost
            )

        if action == PermissionAction.DATABASE_READ:
            return self.allow_database_read

        if action == PermissionAction.DATABASE_WRITE:
            return self.allow_database_write

        return False

    def _is_path_safe(self, path: str) -> bool:
        """Check if file path is safe."""
        # Check blocked paths
        if any(path.startswith(blocked) for blocked in self.blocked_paths):
            return False

        # If safe_paths specified, must be in safe_paths
        if self.safe_paths:
            return any(path.startswith(safe) for safe in self.safe_paths)

        return True

    def record_cost(self, cost: float):
        """Record cost for budget tracking."""
        self.current_cost += cost


# Integrate with ExecutionContext
class ExecutionContext:
    def __init__(
        self,
        agent_id: str,
        permissions: Optional[PermissionPolicy] = None,
        **kwargs
    ):
        self.agent_id = agent_id
        self.permissions = permissions or PermissionPolicy()  # Default permissive
        # ... other fields


# Enforce in BaseAgent hooks
class BaseAgent:
    def _pre_execution_hook(
        self,
        inputs: dict,
        context: ExecutionContext
    ) -> dict:
        """Check permissions before execution."""
        # Determine required permissions
        required_actions = self._get_required_permissions(inputs)

        # Check all permissions
        for action, params in required_actions:
            if not context.permissions.allows(action, **params):
                raise PermissionDeniedError(
                    f"Permission denied for {action.value}: {params}"
                )

        return inputs

    def _get_required_permissions(self, inputs: dict) -> List[Tuple[PermissionAction, dict]]:
        """
        Override to specify required permissions for execution.

        Returns:
            List of (action, params) tuples
        """
        # Default: Require LLM call permission
        return [(PermissionAction.LLM_CALL, {"estimated_cost": 0.01})]


# Usage example
policy = PermissionPolicy(
    allow_file_write=True,
    safe_paths={"/tmp", "/home/user/workspace"},
    allowed_tools={"search", "calculator"},
    max_cost_per_call=0.10,
    max_total_cost=10.0
)

context = ExecutionContext(
    agent_id="my_agent",
    permissions=policy
)

agent = MyAgent(config=...)
result = agent.run(question="...", context=context)  # Enforces permissions
```

**Benefits**:
1. Declarative permission policies
2. Fine-grained control over agent actions
3. Budget enforcement
4. Safe by default (file writes blocked unless explicitly allowed)

**Implementation Complexity**: Medium
- Requires PermissionPolicy class
- Requires ExecutionContext integration
- Requires updating all action execution points
- Requires permission check enforcement

**Priority**: P0 (critical for production security)

---

## 4. Summary & Recommendations

### Critical Patterns to Adopt (P0)

| Pattern | Kaizen Benefit | Implementation Effort | Timeline |
|---------|---------------|---------------------|----------|
| **Bidirectional Message Protocol** | Enables agent ↔ client communication | High (6-8 weeks) | Phase 1 |
| **Hook-Based Extension with Context** | Enables permission enforcement | Medium (4-6 weeks) | Phase 2 |
| **Interrupt-Based Control** | Enables pause/resume/cancel | Medium (4-6 weeks) | Phase 3 |
| **Execution Checkpointing** | Enables resume after crashes | High (6-8 weeks) | Phase 3 |
| **Permission Policy System** | Enables enterprise security | Medium (4-6 weeks) | Phase 2 |

**Total P0 Effort**: 24-36 weeks (6-9 months)

---

### Important Patterns to Adopt (P1)

| Pattern | Kaizen Benefit | Implementation Effort | Timeline |
|---------|---------------|---------------------|----------|
| **Distributed State Coordination** | Prevents multi-agent race conditions | Medium (4-6 weeks) | Phase 4 |
| **Progress Streaming** | Improves user experience | Low (2-3 weeks) | Phase 4 |
| **Circuit Breaker** | Prevents cost overruns | Low (1-2 weeks) | Phase 5 |
| **Distributed Tracing** | Multi-agent observability | High (6-8 weeks) | Phase 5 |

**Total P1 Effort**: 13-19 weeks (3-5 months)

---

### Architectural Principles to Adopt

1. **Separation of Concerns**: Control logic (Kaizen Core) separate from agent logic (BaseAgent)
2. **Dependency Inversion**: Depend on abstractions (ControlChannel, CheckpointStorage)
3. **Progressive Enhancement**: New features are optional (backward compatible)
4. **Fail-Safe Defaults**: Restrictive permissions by default, explicit opt-in for dangerous operations

---

### Next Steps

1. **Create ADRs**: Document architectural decisions for each pattern
2. **Prototype Phase 1**: Build ControlChannel + CLI transport
3. **Validate Design**: Test with real agents (HumanApprovalAgent, etc.)
4. **Implement Phases 2-5**: Roll out remaining patterns incrementally

---

**Conclusion**: Adopting these patterns will transform Kaizen from a signature-based agent framework into a production-ready autonomous agent platform with Claude Code-level control capabilities.
