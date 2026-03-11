# Checkpoint System API Reference

Complete API reference for Kaizen's checkpoint and state persistence system for autonomous agents.

**Location**: `kaizen.core.autonomy.state.*`

---

## Overview

The checkpoint system provides automatic state persistence for autonomous agents, enabling save/resume/fork operations with encryption, compression, and hook integration.

### Key Features

- **Automatic Checkpointing**: Save state every N steps or M seconds
- **Resume/Fork Operations**: Continue from checkpoint or create independent branches
- **Atomic Writes**: Temp file + rename for crash safety
- **Encryption Support**: AES-256-GCM encryption for sensitive data
- **Compression**: Gzip compression to reduce storage
- **Hook Integration**: PRE/POST_CHECKPOINT_SAVE events
- **Retention Policies**: Automatic cleanup of old checkpoints
- **Multiple Backends**: Filesystem (default), database (extensible)

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   StateManager                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Checkpoint Orchestration                          │  │
│  │  - save_checkpoint()    - load_checkpoint()        │  │
│  │  - resume_from_latest() - fork_from_checkpoint()   │  │
│  │  - list_checkpoints()   - cleanup_old_checkpoints()│  │
│  └────────────────────────────────────────────────────┘  │
│                         ↕                                 │
│  ┌────────────────────────────────────────────────────┐  │
│  │  StorageBackend (Protocol)                         │  │
│  │  - save()   - load()   - delete()                  │  │
│  │  - list()   - exists()                             │  │
│  └────────────────────────────────────────────────────┘  │
│                         ↕                                 │
│  ┌────────────────────────────────────────────────────┐  │
│  │  FilesystemStorage (Default)                       │  │
│  │  - JSONL format with atomic writes                 │  │
│  │  - Optional gzip compression                       │  │
│  │  - Optional AES-256-GCM encryption                 │  │
│  │  - Automatic retention policy enforcement          │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│                   AgentState                             │
│  - Conversation history, memory contents                 │
│  - Pending/completed actions                             │
│  - Budget, approval history                              │
│  - Tool usage, results cache                             │
│  - Specialist invocations                                │
│  - Workflow state, control protocol state                │
│  - Hook contexts, event history                          │
└──────────────────────────────────────────────────────────┘
```

---

## AgentState

Complete agent state at a checkpoint, capturing all information needed to resume execution.

**Location**: `kaizen.core.autonomy.state.types.AgentState`

### Class Definition

```python
@dataclass
class AgentState:
    """
    Complete agent state at a checkpoint.

    Captures all information needed to resume agent execution from this point.
    """

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

    # Specialist state
    active_specialists: list[str] = field(default_factory=list)
    specialist_invocations: list[dict[str, Any]] = field(default_factory=list)

    # Workflow state (Kailash SDK)
    workflow_run_id: str | None = None
    workflow_state: dict[str, Any] = field(default_factory=dict)

    # Control protocol state
    control_protocol_state: dict[str, Any] = field(default_factory=dict)

    # Hook contexts
    registered_hooks: list[dict[str, Any]] = field(default_factory=list)
    hook_event_history: list[dict[str, Any]] = field(default_factory=list)

    # Metadata
    parent_checkpoint_id: str | None = None  # For forking
    status: Literal["running", "completed", "failed", "interrupted"] = "running"
    metadata: dict[str, Any] = field(default_factory=dict)
```

### Methods

#### to_dict()

```python
def to_dict() -> dict[str, Any]:
    """
    Convert state to dictionary for serialization.

    Returns:
        Dictionary representation of agent state with datetime converted to ISO format
    """
```

#### from_dict()

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> "AgentState":
    """
    Create AgentState from dictionary.

    Args:
        data: Dictionary representation of state

    Returns:
        AgentState instance with datetime parsed from ISO format
    """
```

### Example Usage

```python
from kaizen.core.autonomy.state import AgentState
from datetime import datetime

# Create agent state
state = AgentState(
    agent_id="research_agent",
    step_number=42,
    conversation_history=[
        {"user": "Analyze sales data", "agent": "Starting analysis..."}
    ],
    memory_contents={"current_task": "sales_analysis"},
    pending_actions=[{"action": "fetch_data", "params": {"source": "db"}}],
    budget_spent_usd=0.15,
    tool_usage_counts={"fetch_data": 3, "analyze": 1},
    status="running"
)

# Serialize to dict
state_dict = state.to_dict()

# Deserialize from dict
restored_state = AgentState.from_dict(state_dict)
```

---

## CheckpointMetadata

Lightweight metadata for checkpoint listing without loading full state.

**Location**: `kaizen.core.autonomy.state.types.CheckpointMetadata`

### Class Definition

```python
@dataclass
class CheckpointMetadata:
    """
    Lightweight metadata for checkpoint listing.

    Used for efficient checkpoint discovery without loading full state.
    """

    checkpoint_id: str
    agent_id: str
    timestamp: datetime
    step_number: int
    status: str
    size_bytes: int
    parent_checkpoint_id: str | None = None
```

### Methods

#### to_dict()

```python
def to_dict() -> dict[str, Any]:
    """Convert metadata to dictionary with ISO timestamp"""
```

#### from_dict()

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> "CheckpointMetadata":
    """Create metadata from dictionary with ISO timestamp parsing"""
```

### Example Usage

```python
from kaizen.core.autonomy.state import CheckpointMetadata

# List checkpoints
checkpoints = await state_manager.list_checkpoints(agent_id="research_agent")

for checkpoint in checkpoints:
    print(f"Checkpoint: {checkpoint.checkpoint_id}")
    print(f"  Agent: {checkpoint.agent_id}")
    print(f"  Step: {checkpoint.step_number}")
    print(f"  Size: {checkpoint.size_bytes} bytes")
    print(f"  Status: {checkpoint.status}")
    print(f"  Timestamp: {checkpoint.timestamp}")
```

---

## StateSnapshot

Immutable snapshot of agent state for debugging without modifying checkpoints.

**Location**: `kaizen.core.autonomy.state.types.StateSnapshot`

### Class Definition

```python
@dataclass
class StateSnapshot:
    """
    Immutable snapshot of agent state at a point in time.

    Used for debugging and state inspection without modifying checkpoints.
    """

    state: AgentState
    created_at: datetime = field(default_factory=datetime.utcnow)
    snapshot_reason: str = "manual"
```

### Methods

#### get_summary()

```python
def get_summary() -> dict[str, Any]:
    """
    Get human-readable summary of snapshot.

    Returns:
        Dictionary with key metrics:
            - checkpoint_id, agent_id, step_number, status
            - conversation_turns, pending_actions, completed_actions
            - budget_spent_usd, snapshot_reason, created_at
    """
```

### Example Usage

```python
from kaizen.core.autonomy.state import StateSnapshot

# Create snapshot for debugging
snapshot = StateSnapshot(
    state=current_state,
    snapshot_reason="pre_deployment_validation"
)

# Get summary
summary = snapshot.get_summary()
print(f"Agent: {summary['agent_id']}")
print(f"Step: {summary['step_number']}")
print(f"Conversation turns: {summary['conversation_turns']}")
print(f"Budget spent: ${summary['budget_spent_usd']:.4f}")
print(f"Reason: {summary['snapshot_reason']}")
```

---

## StateManager

Orchestrates checkpoint operations: save, load, resume, fork, list, cleanup.

**Location**: `kaizen.core.autonomy.state.manager.StateManager`

### Class Definition

```python
class StateManager:
    """
    Orchestrates checkpoint operations for agent state persistence.

    Provides high-level API for checkpoint/resume/fork operations.
    """

    def __init__(
        self,
        storage: StorageBackend | None = None,
        checkpoint_frequency: int = 10,  # Every N steps
        checkpoint_interval: float = 60.0,  # OR every M seconds
        retention_count: int = 100,  # Keep last N checkpoints
        hook_manager: "HookManager | None" = None,  # Optional hooks integration
    ):
        """
        Initialize state manager.

        Args:
            storage: Storage backend (defaults to FilesystemStorage)
            checkpoint_frequency: Checkpoint every N steps
            checkpoint_interval: Checkpoint every M seconds
            retention_count: Maximum checkpoints to keep per agent
            hook_manager: Optional HookManager for checkpoint hooks
        """
```

### Methods

#### should_checkpoint()

```python
def should_checkpoint(
    self,
    agent_id: str,
    current_step: int,
    current_time: float
) -> bool:
    """
    Determine if checkpoint is needed based on frequency and interval.

    Args:
        agent_id: ID of agent
        current_step: Current step number
        current_time: Current time (seconds since epoch)

    Returns:
        True if checkpoint should be created

    Logic:
        - Check frequency: current_step - last_step >= checkpoint_frequency
        - Check interval: current_time - last_time >= checkpoint_interval
        - Return True if either condition is met
    """
```

#### save_checkpoint()

```python
async def save_checkpoint(
    self,
    state: AgentState,
    force: bool = False,
) -> str:
    """
    Save agent state as checkpoint.

    Triggers PRE_CHECKPOINT_SAVE and POST_CHECKPOINT_SAVE hooks if enabled.

    Args:
        state: Agent state to checkpoint
        force: Force checkpoint even if not needed

    Returns:
        checkpoint_id of saved checkpoint

    Raises:
        IOError: If save fails

    Notes:
        - Updates tracking for should_checkpoint logic
        - Triggers hooks before and after save
        - Automatically calls cleanup_old_checkpoints
    """
```

#### load_checkpoint()

```python
async def load_checkpoint(self, checkpoint_id: str) -> AgentState:
    """
    Load checkpoint by ID.

    Args:
        checkpoint_id: ID of checkpoint to load

    Returns:
        AgentState restored from checkpoint

    Raises:
        FileNotFoundError: If checkpoint doesn't exist
    """
```

#### resume_from_latest()

```python
async def resume_from_latest(self, agent_id: str) -> AgentState | None:
    """
    Resume from latest checkpoint for agent.

    Args:
        agent_id: ID of agent to resume

    Returns:
        Latest AgentState, or None if no checkpoints exist

    Notes:
        - Automatically loads most recent checkpoint
        - Returns None if agent has no checkpoints
    """
```

#### fork_from_checkpoint()

```python
async def fork_from_checkpoint(self, checkpoint_id: str) -> AgentState:
    """
    Create new state branched from checkpoint.

    Creates a deep copy of the checkpoint with a new checkpoint_id and
    parent_checkpoint_id set to the original.

    Args:
        checkpoint_id: ID of checkpoint to fork from

    Returns:
        New AgentState with updated IDs

    Raises:
        FileNotFoundError: If checkpoint doesn't exist

    Notes:
        - Creates independent execution branch
        - Preserves lineage via parent_checkpoint_id
        - Automatically saves forked checkpoint
    """
```

#### list_checkpoints()

```python
async def list_checkpoints(
    self,
    agent_id: str | None = None
) -> list[CheckpointMetadata]:
    """
    List all checkpoints (optionally filtered by agent_id).

    Args:
        agent_id: Filter checkpoints for specific agent (None = all)

    Returns:
        List of checkpoint metadata sorted by timestamp (newest first)
    """
```

#### cleanup_old_checkpoints()

```python
async def cleanup_old_checkpoints(self, agent_id: str) -> int:
    """
    Delete checkpoints beyond retention_count.

    Keeps the latest N checkpoints for the agent.

    Args:
        agent_id: ID of agent

    Returns:
        Number of checkpoints deleted

    Raises:
        IOError: If deletion fails

    Notes:
        - Automatically called by save_checkpoint
        - Preserves most recent checkpoints
        - Logs errors but continues on failure
    """
```

#### get_checkpoint_tree()

```python
async def get_checkpoint_tree(self, agent_id: str) -> dict[str, list[str]]:
    """
    Return parent-child checkpoint relationships.

    Useful for visualizing checkpoint forks and lineage.

    Args:
        agent_id: ID of agent

    Returns:
        Dictionary mapping checkpoint_id to list of child checkpoint_ids
    """
```

### Example Usage

```python
from kaizen.core.autonomy.state import StateManager, AgentState
from kaizen.core.autonomy.hooks import HookManager

# Create state manager
state_manager = StateManager(
    checkpoint_frequency=10,    # Every 10 steps
    checkpoint_interval=60.0,   # OR every 60 seconds
    retention_count=100,        # Keep last 100 checkpoints
    hook_manager=hook_manager   # Optional hooks
)

# Check if checkpoint needed
current_step = 42
current_time = time.time()
if state_manager.should_checkpoint("my_agent", current_step, current_time):
    # Save checkpoint
    checkpoint_id = await state_manager.save_checkpoint(agent_state)
    print(f"Checkpoint saved: {checkpoint_id}")

# Resume from latest
restored_state = await state_manager.resume_from_latest("my_agent")
if restored_state:
    print(f"Resumed from step {restored_state.step_number}")

# Fork checkpoint for experimentation
forked_state = await state_manager.fork_from_checkpoint(checkpoint_id)
print(f"Forked: {checkpoint_id} → {forked_state.checkpoint_id}")

# List checkpoints
checkpoints = await state_manager.list_checkpoints(agent_id="my_agent")
print(f"Found {len(checkpoints)} checkpoints")

# Cleanup old checkpoints
deleted = await state_manager.cleanup_old_checkpoints("my_agent")
print(f"Deleted {deleted} old checkpoints")
```

---

## StorageBackend

Protocol defining checkpoint storage backend interface.

**Location**: `kaizen.core.autonomy.state.storage.StorageBackend`

### Protocol Definition

```python
@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for checkpoint storage backends"""

    @abstractmethod
    async def save(self, state: AgentState) -> str:
        """
        Save checkpoint and return checkpoint_id.

        Args:
            state: Agent state to checkpoint

        Returns:
            checkpoint_id of saved checkpoint

        Raises:
            IOError: If save fails
        """

    @abstractmethod
    async def load(self, checkpoint_id: str) -> AgentState:
        """
        Load checkpoint by ID.

        Args:
            checkpoint_id: ID of checkpoint to load

        Returns:
            AgentState restored from checkpoint

        Raises:
            FileNotFoundError: If checkpoint doesn't exist
        """

    @abstractmethod
    async def list_checkpoints(
        self,
        agent_id: str | None = None
    ) -> list[CheckpointMetadata]:
        """
        List all checkpoints (optionally filtered by agent_id).

        Args:
            agent_id: Filter checkpoints for specific agent (None = all)

        Returns:
            List of checkpoint metadata sorted by timestamp (newest first)
        """

    @abstractmethod
    async def delete(self, checkpoint_id: str) -> None:
        """
        Delete checkpoint.

        Args:
            checkpoint_id: ID of checkpoint to delete

        Raises:
            FileNotFoundError: If checkpoint doesn't exist
        """

    @abstractmethod
    async def exists(self, checkpoint_id: str) -> bool:
        """
        Check if checkpoint exists.

        Args:
            checkpoint_id: ID of checkpoint

        Returns:
            True if checkpoint exists
        """
```

### Example Implementation

```python
from kaizen.core.autonomy.state.storage import StorageBackend
from kaizen.core.autonomy.state import AgentState, CheckpointMetadata

class CustomDatabaseBackend:
    """Custom database backend for checkpoints"""

    async def save(self, state: AgentState) -> str:
        # Save to database
        await db.execute(
            "INSERT INTO checkpoints (id, agent_id, state_json) VALUES (?, ?, ?)",
            state.checkpoint_id, state.agent_id, json.dumps(state.to_dict())
        )
        return state.checkpoint_id

    async def load(self, checkpoint_id: str) -> AgentState:
        # Load from database
        row = await db.fetch_one(
            "SELECT state_json FROM checkpoints WHERE id = ?",
            checkpoint_id
        )
        if not row:
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")
        return AgentState.from_dict(json.loads(row['state_json']))

    async def list_checkpoints(
        self,
        agent_id: str | None = None
    ) -> list[CheckpointMetadata]:
        # List from database
        query = "SELECT * FROM checkpoints"
        if agent_id:
            query += " WHERE agent_id = ?"
            rows = await db.fetch_all(query, agent_id)
        else:
            rows = await db.fetch_all(query)

        return [CheckpointMetadata(...) for row in rows]

    async def delete(self, checkpoint_id: str) -> None:
        await db.execute("DELETE FROM checkpoints WHERE id = ?", checkpoint_id)

    async def exists(self, checkpoint_id: str) -> bool:
        row = await db.fetch_one(
            "SELECT 1 FROM checkpoints WHERE id = ? LIMIT 1",
            checkpoint_id
        )
        return row is not None
```

---

## FilesystemStorage

Filesystem-based checkpoint storage with JSONL format, compression, and encryption.

**Location**: `kaizen.core.autonomy.state.storage.FilesystemStorage`

### Class Definition

```python
class FilesystemStorage:
    """
    Filesystem-based checkpoint storage (JSONL format).

    Stores checkpoints as JSONL files with atomic writes and optional
    compression/encryption.
    """

    def __init__(
        self,
        base_dir: str | Path = ".kaizen/checkpoints",
        compress: bool = False,
        encrypt: bool = False,
        encryption_key: str | bytes | None = None,
    ):
        """
        Initialize filesystem storage.

        Args:
            base_dir: Directory for checkpoint storage
            compress: Whether to compress checkpoints (gzip)
            encrypt: Whether to encrypt checkpoints (AES-256-GCM)
            encryption_key: Encryption key or passphrase (required if encrypt=True)

        Raises:
            ValueError: If encryption is enabled without encryption_key

        Notes:
            - Creates base_dir if it doesn't exist
            - Processing order: JSON → Encrypt → Compress → Write
        """
```

### Methods

#### save()

```python
async def save(self, state: AgentState) -> str:
    """
    Save checkpoint as JSONL file with atomic write.

    Uses temp file + rename for atomicity.
    Supports gzip compression and AES-256-GCM encryption.

    Processing order: JSON → Encrypt → Compress → Write

    Args:
        state: Agent state to checkpoint

    Returns:
        checkpoint_id

    Raises:
        IOError: If save fails

    File Extensions:
        - .jsonl (plain)
        - .enc.jsonl (encrypted only)
        - .gz.jsonl (compressed only)
        - .enc.gz.jsonl (encrypted + compressed)
    """
```

#### load()

```python
async def load(self, checkpoint_id: str) -> AgentState:
    """
    Load checkpoint from JSONL file.

    Processing order: Read → Decompress → Decrypt → Parse JSON

    Args:
        checkpoint_id: ID of checkpoint to load

    Returns:
        AgentState restored from checkpoint

    Raises:
        FileNotFoundError: If checkpoint doesn't exist
        IOError: If load fails
    """
```

#### list_checkpoints()

```python
async def list_checkpoints(
    self,
    agent_id: str | None = None
) -> list[CheckpointMetadata]:
    """
    List all checkpoints (optionally filtered by agent_id).

    Args:
        agent_id: Filter checkpoints for specific agent (None = all)

    Returns:
        List of checkpoint metadata sorted by timestamp (newest first)

    Notes:
        - Scans base_dir for checkpoint files
        - Parses metadata without loading full state
        - Filters by agent_id if provided
    """
```

#### delete()

```python
async def delete(self, checkpoint_id: str) -> None:
    """
    Delete checkpoint file.

    Args:
        checkpoint_id: ID of checkpoint to delete

    Raises:
        FileNotFoundError: If checkpoint doesn't exist
    """
```

#### exists()

```python
async def exists(self, checkpoint_id: str) -> bool:
    """
    Check if checkpoint file exists.

    Args:
        checkpoint_id: ID of checkpoint

    Returns:
        True if checkpoint file exists
    """
```

### Example Usage (Plain)

```python
from kaizen.core.autonomy.state.storage import FilesystemStorage

# Create storage (plain JSONL)
storage = FilesystemStorage(
    base_dir="./checkpoints"
)

# Save checkpoint
checkpoint_id = await storage.save(agent_state)

# Load checkpoint
restored_state = await storage.load(checkpoint_id)

# List checkpoints
checkpoints = await storage.list_checkpoints(agent_id="my_agent")
```

### Example Usage (Compressed)

```python
from kaizen.core.autonomy.state.storage import FilesystemStorage

# Create storage with gzip compression
storage = FilesystemStorage(
    base_dir="./checkpoints",
    compress=True  # Saves as .gz.jsonl
)

# Save checkpoint (automatically compressed)
checkpoint_id = await storage.save(agent_state)

# Load checkpoint (automatically decompressed)
restored_state = await storage.load(checkpoint_id)
```

### Example Usage (Encrypted)

```python
from kaizen.core.autonomy.state.storage import FilesystemStorage

# Create storage with AES-256-GCM encryption
storage = FilesystemStorage(
    base_dir="./checkpoints",
    encrypt=True,
    encryption_key="your-secret-passphrase"  # Or 32-byte key
)

# Save checkpoint (automatically encrypted)
checkpoint_id = await storage.save(agent_state)

# Load checkpoint (automatically decrypted)
restored_state = await storage.load(checkpoint_id)
```

### Example Usage (Encrypted + Compressed)

```python
from kaizen.core.autonomy.state.storage import FilesystemStorage

# Create storage with encryption + compression
storage = FilesystemStorage(
    base_dir="./checkpoints",
    compress=True,
    encrypt=True,
    encryption_key="your-secret-passphrase"
)

# Saves as .enc.gz.jsonl
checkpoint_id = await storage.save(agent_state)

# Automatically decrypts and decompresses
restored_state = await storage.load(checkpoint_id)
```

---

## Checkpoint Workflow

### Automatic Checkpointing

```python
from kaizen.core.autonomy.state import StateManager, AgentState
import time

# Initialize state manager
state_manager = StateManager(
    checkpoint_frequency=10,    # Every 10 steps
    checkpoint_interval=60.0,   # OR every 60 seconds
    retention_count=50          # Keep last 50 checkpoints
)

# Agent execution loop
for step in range(100):
    # Execute agent step
    agent_state.step_number = step
    # ... agent logic ...

    # Check if checkpoint needed
    current_time = time.time()
    if state_manager.should_checkpoint(
        agent_state.agent_id,
        step,
        current_time
    ):
        checkpoint_id = await state_manager.save_checkpoint(agent_state)
        print(f"Step {step}: Checkpoint {checkpoint_id} saved")
```

### Resume from Crash

```python
from kaizen.core.autonomy.state import StateManager

# Initialize state manager
state_manager = StateManager()

# Try to resume from latest checkpoint
agent_state = await state_manager.resume_from_latest("my_agent")

if agent_state:
    print(f"Resumed from step {agent_state.step_number}")
    # Continue execution from restored state
    start_step = agent_state.step_number + 1
else:
    print("No checkpoint found, starting fresh")
    agent_state = AgentState(agent_id="my_agent")
    start_step = 0

# Continue execution
for step in range(start_step, 100):
    # ... agent logic ...
    pass
```

### Forking for Experimentation

```python
from kaizen.core.autonomy.state import StateManager

# Load production checkpoint
checkpoints = await state_manager.list_checkpoints(agent_id="prod_agent")
production_checkpoint = checkpoints[0].checkpoint_id

# Fork for experimentation
experimental_state = await state_manager.fork_from_checkpoint(
    production_checkpoint
)

# Update experimental state
experimental_state.agent_id = "experimental_agent"
experimental_state.metadata["purpose"] = "testing_new_strategy"

# Save experimental fork
experimental_checkpoint = await state_manager.save_checkpoint(
    experimental_state
)

print(f"Created experimental branch: {experimental_checkpoint}")
print(f"Parent: {experimental_state.parent_checkpoint_id}")
```

---

## Hook Integration

Checkpoints integrate with the hooks system for observability.

### Available Hooks

- `PRE_CHECKPOINT_SAVE`: Triggered before checkpoint save
- `POST_CHECKPOINT_SAVE`: Triggered after checkpoint save

### Example Hook

```python
from kaizen.core.autonomy.hooks import HookManager, HookEvent, HookContext, HookResult

async def checkpoint_audit_hook(context: HookContext) -> HookResult:
    """Audit checkpoint operations"""
    print(f"[AUDIT] Checkpoint saved:")
    print(f"  Agent: {context.data['agent_id']}")
    print(f"  Step: {context.data['step_number']}")
    print(f"  Checkpoint ID: {context.data.get('checkpoint_id', 'pending')}")

    return HookResult(success=True)

# Register hook
hook_manager = HookManager()
hook_manager.register(HookEvent.PRE_CHECKPOINT_SAVE, checkpoint_audit_hook)
hook_manager.register(HookEvent.POST_CHECKPOINT_SAVE, checkpoint_audit_hook)

# Use with state manager
state_manager = StateManager(hook_manager=hook_manager)

# Hooks triggered automatically on save
checkpoint_id = await state_manager.save_checkpoint(agent_state)
```

---

## Testing

### Unit Tests

```python
import pytest
from kaizen.core.autonomy.state import StateManager, AgentState

@pytest.mark.asyncio
async def test_save_load_checkpoint():
    """Test basic save/load operations."""
    state_manager = StateManager()

    # Create state
    original_state = AgentState(
        agent_id="test_agent",
        step_number=42,
        conversation_history=[{"user": "test", "agent": "response"}]
    )

    # Save checkpoint
    checkpoint_id = await state_manager.save_checkpoint(original_state)
    assert checkpoint_id is not None

    # Load checkpoint
    restored_state = await state_manager.load_checkpoint(checkpoint_id)

    # Verify
    assert restored_state.agent_id == original_state.agent_id
    assert restored_state.step_number == original_state.step_number
    assert len(restored_state.conversation_history) == 1
```

### Integration Tests (Tier 2)

```python
import pytest
from kaizen.core.autonomy.state import StateManager, AgentState
from kaizen.core.autonomy.state.storage import FilesystemStorage

@pytest.mark.integration
@pytest.mark.asyncio
async def test_checkpoint_with_encryption():
    """Test checkpoint encryption with real storage."""
    storage = FilesystemStorage(
        base_dir="/tmp/test_checkpoints",
        encrypt=True,
        encryption_key="test-encryption-key-32-bytes!!"
    )

    state_manager = StateManager(storage=storage)

    # Create state with sensitive data
    state = AgentState(
        agent_id="secure_agent",
        metadata={"api_key": "secret-key-12345"}
    )

    # Save checkpoint (encrypted)
    checkpoint_id = await state_manager.save_checkpoint(state)

    # Verify file is encrypted (not plain JSON)
    checkpoint_path = storage.base_dir / f"{checkpoint_id}.enc.jsonl"
    with open(checkpoint_path, 'rb') as f:
        encrypted_data = f.read()
        assert b"secret-key" not in encrypted_data  # Should be encrypted

    # Load checkpoint (decrypted)
    restored_state = await state_manager.load_checkpoint(checkpoint_id)
    assert restored_state.metadata["api_key"] == "secret-key-12345"
```

### E2E Tests (Tier 3)

```python
import pytest
from kaizen.core.autonomy.state import StateManager, AgentState

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_checkpoint_resume_after_crash():
    """Test checkpoint resume workflow."""
    state_manager = StateManager(
        checkpoint_frequency=5,
        retention_count=10
    )

    # Simulate agent execution
    agent_id = "crash_test_agent"
    for step in range(20):
        state = AgentState(
            agent_id=agent_id,
            step_number=step,
            conversation_history=[{"step": step}]
        )

        # Save checkpoints
        if step % 5 == 0:
            await state_manager.save_checkpoint(state)

    # Simulate crash and resume
    restored_state = await state_manager.resume_from_latest(agent_id)

    # Verify resumed from latest checkpoint (step 15)
    assert restored_state is not None
    assert restored_state.step_number == 15

    # Verify retention policy (keep last 10)
    checkpoints = await state_manager.list_checkpoints(agent_id=agent_id)
    assert len(checkpoints) <= 10
```

---

## Related Documentation

- **[Memory API](memory-api.md)** - 3-tier memory system
- **[Interrupts API](interrupts-api.md)** - Graceful shutdown with checkpoints
- **[Hooks System API](hooks-api.md)** - Event-driven observability
- **[Planning Agents API](planning-agents-api.md)** - Planning patterns

---

## Version History

- **v0.7.0** (2025-01) - Initial checkpoint system implementation
  - AgentState with 15+ state fields
  - StateManager with save/load/resume/fork
  - FilesystemStorage with atomic writes
  - Optional compression and encryption
  - Hook integration for observability
  - Retention policies with automatic cleanup

---

**API Stability**: Production-ready (v0.7.0+)
**Test Coverage**: 100% (unit + integration + E2E)
**Security**: AES-256-GCM encryption, atomic writes, crash-safe
