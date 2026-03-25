# Ctrl+C Interrupt Handling Example

## Overview

Production-ready example demonstrating graceful Ctrl+C interrupt handling for autonomous agents with checkpoint preservation, resume capability, and comprehensive interrupt metrics tracking. This pattern is essential for long-running autonomous workflows that need reliable recovery from user interruptions.

## Prerequisites

- **Python 3.8+**
- **Ollama** with llama3.1:8b-instruct-q8_0 model (FREE - local inference)
- **Kailash Kaizen** installed (`pip install kailash-kaizen`)

## Installation

```bash
# 1. Install Ollama
# macOS:
brew install ollama

# Linux:
curl -fsSL https://ollama.ai/install.sh | sh

# Windows: Download from https://ollama.ai

# 2. Start Ollama service
ollama serve

# 3. Pull model (first time only)
ollama pull llama3.1:8b-instruct-q8_0

# 4. Install dependencies
pip install kailash-kaizen
```

## Usage

```bash
cd examples/autonomy/interrupts
python 01_ctrl_c_interrupt.py
```

**During execution**, press **Ctrl+C** to trigger graceful shutdown. The agent will:
1. Finish the current cycle
2. Save a checkpoint with all state
3. Log interrupt metrics
4. Exit cleanly

**Run again** to resume from the saved checkpoint.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│           CTRL+C INTERRUPT HANDLING                      │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────┐        ┌────────────────────┐     │
│  │ Signal Handler │◄──────►│ Interrupt Manager  │     │
│  │ (SIGINT)       │        │ - Graceful mode    │     │
│  └────────────────┘        │ - Immediate mode   │     │
│          │                 └────────────────────┘     │
│          │                          │                  │
│          ▼                          ▼                  │
│  ┌─────────────────────────────────────────────────┐  │
│  │       BaseAutonomousAgent                       │  │
│  │  - Detects interrupt signal                     │  │
│  │  - Finishes current cycle                       │  │
│  │  - Saves checkpoint before exit                 │  │
│  │  - Resumes from checkpoint on restart           │  │
│  └─────────────────────────────────────────────────┘  │
│          │                          │                  │
│          ▼                          ▼                  │
│  ┌──────────────────┐      ┌───────────────────┐     │
│  │ Interrupt Metrics│      │ Checkpoint System │     │
│  │ Hook (JSONL)     │      │ - Auto-save       │     │
│  └──────────────────┘      │ - Compression     │     │
│                             │ - Retention       │     │
│                             └───────────────────┘     │
│                                                        │
└────────────────────────────────────────────────────────┘
```

## Features

### 1. Graceful vs Immediate Shutdown

- **First Ctrl+C**: Graceful shutdown
  - Finishes current cycle
  - Saves complete checkpoint
  - Logs interrupt metrics
  - Clean exit (exit code 0)

- **Second Ctrl+C**: Immediate shutdown
  - Stops as soon as possible
  - May lose current cycle work
  - Emergency exit (exit code 1)

### 2. Interrupt Metrics Hook

Tracks all interrupt events with:
- **Interrupt source**: USER, SYSTEM, or PROGRAMMATIC
- **Interrupt mode**: GRACEFUL or IMMEDIATE
- **Timestamp**: ISO 8601 format
- **Counts**: Total, graceful, and immediate interrupts

**JSONL Log Format**:
```json
{"timestamp": "2025-11-03T12:34:56", "event": "interrupt_initiated", "source": "USER", "mode": "GRACEFUL", "message": "User requested graceful shutdown (Ctrl+C)", "agent_id": "autonomous_agent"}
{"timestamp": "2025-11-03T12:35:01", "event": "interrupt_completed", "checkpoint_id": "checkpoint_20251103_123501.jsonl.gz", "agent_id": "autonomous_agent", "total_interrupts": 1, "graceful_interrupts": 1, "immediate_interrupts": 0}
```

### 3. Checkpoint Integration

- **Automatic saving**: Checkpoint created before exit
- **Compression**: 50%+ size reduction with gzip
- **Retention**: Keeps last 20 checkpoints automatically
- **Resume support**: Seamlessly continues from latest checkpoint
- **State preservation**: Conversation history, budget, progress

### 4. Signal Handler

Registers SIGINT handler for Ctrl+C detection:
- Thread-safe signal handling
- Double Ctrl+C detection for immediate shutdown
- Cooperative interruption (agent checks at cycle boundaries)
- Clean signal propagation

## Expected Output

### First Run (New Session)

```
============================================================
🤖 CTRL+C INTERRUPT HANDLING EXAMPLE
============================================================
📂 Checkpoint Dir: .kaizen/checkpoints/ctrl_c_example
🔧 LLM: ollama/llama3.1:8b-instruct-q8_0 (FREE)
⚡ Features:
  ✅ Graceful shutdown on Ctrl+C
  ✅ Checkpoint preservation
  ✅ Resume from latest checkpoint
  ✅ Interrupt metrics tracking
  ✅ Budget visualization ($0.00 with Ollama)

🚀 NEW SESSION - Starting fresh execution
============================================================

ℹ️  Press Ctrl+C at any time to trigger graceful shutdown.
ℹ️  Press Ctrl+C twice for immediate shutdown.

2025-11-03 12:34:50 - INFO - Starting autonomous execution...

CYCLE 1: Counting from 1 to 5...
CYCLE 2: Counting from 6 to 10...

^C

⚠️  Ctrl+C detected! Initiating graceful shutdown...
   Finishing current cycle and saving checkpoint...
   Press Ctrl+C again for immediate shutdown.

CYCLE 2: Completing current cycle...

✅ Gracefully interrupted and checkpoint saved!
   Run again to resume from where you left off.

   Source: USER
   Mode: GRACEFUL
   Message: User requested graceful shutdown (Ctrl+C)
   Timestamp: 2025-11-03T12:35:00.123456

   Checkpoint: checkpoint_20251103_123501.jsonl.gz
   Cycles completed: 2

============================================================
📊 EXECUTION STATISTICS
============================================================
Status: interrupted
Cycles: 2
Budget Spent: $0.0000

Interrupt Metrics:
  Total Interrupts: 1
  Graceful: 1
  Immediate: 0
============================================================

📊 Interrupt metrics log: .kaizen/checkpoints/ctrl_c_example/interrupt_metrics.jsonl
   View detailed metrics: cat .kaizen/checkpoints/ctrl_c_example/interrupt_metrics.jsonl
```

### Second Run (Resume from Checkpoint)

```
============================================================
🤖 CTRL+C INTERRUPT HANDLING EXAMPLE
============================================================
📂 Checkpoint Dir: .kaizen/checkpoints/ctrl_c_example
🔧 LLM: ollama/llama3.1:8b-instruct-q8_0 (FREE)
⚡ Features:
  ✅ Graceful shutdown on Ctrl+C
  ✅ Checkpoint preservation
  ✅ Resume from latest checkpoint
  ✅ Interrupt metrics tracking
  ✅ Budget visualization ($0.00 with Ollama)

📂 EXISTING CHECKPOINT FOUND - Resuming previous session
============================================================

ℹ️  Press Ctrl+C at any time to trigger graceful shutdown.
ℹ️  Press Ctrl+C twice for immediate shutdown.

2025-11-03 12:36:00 - INFO - Starting autonomous execution...
2025-11-03 12:36:00 - INFO - Resuming from checkpoint (cycles completed: 2)

CYCLE 3: Counting from 11 to 15...
CYCLE 4: Counting from 16 to 20...
...
CYCLE 10: Counting from 46 to 50... ✅

✅ Task completed successfully!
   Cycles: 10
   Result: Counted from 1 to 50

============================================================
📊 EXECUTION STATISTICS
============================================================
Status: completed
Cycles: 10
Budget Spent: $0.0000

Interrupt Metrics:
  Total Interrupts: 0
  Graceful: 0
  Immediate: 0
============================================================
```

## Key Patterns

### 1. Signal Handler Registration

```python
def setup_signal_handlers(interrupt_manager: InterruptManager) -> None:
    """Setup signal handlers for graceful shutdown."""

    def sigint_handler(signum: int, frame: Any) -> None:
        """Handle SIGINT (Ctrl+C)."""
        if interrupt_manager.is_interrupted():
            # Second Ctrl+C - immediate shutdown
            interrupt_manager.request_interrupt(
                InterruptReason(
                    source=InterruptSource.USER,
                    mode=InterruptMode.IMMEDIATE,
                    message="User requested immediate shutdown (double Ctrl+C)"
                )
            )
        else:
            # First Ctrl+C - graceful shutdown
            interrupt_manager.request_interrupt(
                InterruptReason(
                    source=InterruptSource.USER,
                    mode=InterruptMode.GRACEFUL,
                    message="User requested graceful shutdown (Ctrl+C)"
                )
            )

    signal.signal(signal.SIGINT, sigint_handler)
```

### 2. Interrupt Metrics Hook

```python
class InterruptMetricsHook:
    """Custom hook for tracking interrupt events."""

    async def pre_interrupt(self, context: HookContext) -> HookResult:
        """Track interrupt initiation."""
        reason = context.data.get("reason")
        if reason:
            self.interrupt_count += 1
            if reason.mode == InterruptMode.GRACEFUL:
                self.graceful_count += 1

            # Log to JSONL
            with open(self.log_path, "a") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "event": "interrupt_initiated",
                    "source": reason.source.value,
                    "mode": reason.mode.value,
                    "message": reason.message,
                    "agent_id": context.agent_id
                }, f)
                f.write("\n")

        return HookResult(success=True)
```

### 3. Checkpoint Configuration

```python
# Enable checkpoint on interrupt
config = AutonomousConfig(
    llm_provider="ollama",
    model="llama3.1:8b-instruct-q8_0",
    checkpoint_frequency=1,           # Save every cycle
    resume_from_checkpoint=True,      # Auto-resume
    checkpoint_on_interrupt=True      # Save before exit
)

# Compressed storage with retention
storage = FilesystemStorage(
    base_dir=str(checkpoint_dir),
    compress=True                     # 50%+ size reduction
)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=1,
    retention_count=20                # Keep last 20
)
```

## Troubleshooting

### Issue: Signal handler not working

**Symptom**: Ctrl+C immediately kills the process without graceful shutdown

**Solutions**:
1. Ensure signal handler is registered before agent execution
2. Check for conflicting signal handlers in other libraries
3. Verify interrupt_manager is properly injected into agent
4. Try running without debugger (debuggers may intercept signals)

### Issue: Checkpoint not saved on interrupt

**Symptom**: No checkpoint file created after Ctrl+C

**Solutions**:
1. Verify `checkpoint_on_interrupt=True` in config
2. Check checkpoint directory permissions (should be writable)
3. Ensure agent completes current cycle (graceful mode)
4. Check logs for StateManager errors

### Issue: Resume fails with corrupted checkpoint

**Symptom**: Error loading checkpoint on second run

**Solutions**:
1. Check for immediate shutdown (second Ctrl+C) - may corrupt checkpoint
2. Verify gzip compression/decompression works
3. Delete corrupted checkpoint and run fresh
4. Increase `graceful_shutdown_timeout` in config

### Issue: Interrupt metrics not logged

**Symptom**: JSONL file empty or missing

**Solutions**:
1. Verify hooks are registered with correct priority
2. Check log directory exists and is writable
3. Ensure hook methods return `HookResult(success=True)`
4. Check for exceptions in hook execution (see logs)

## Production Notes

### Multi-Agent Interrupt Propagation

For multi-agent systems, parent agents should propagate interrupts to children:

```python
# Parent agent
parent = SupervisorAgent(config)
child1 = WorkerAgent(config)
child2 = WorkerAgent(config)

# Register children
parent.interrupt_manager.add_child(child1.interrupt_manager)
parent.interrupt_manager.add_child(child2.interrupt_manager)

# When parent interrupted, children also stop
parent.interrupt_manager.request_interrupt(...)
# child1 and child2 receive interrupt signal automatically
```

### Docker Deployment

For Docker containers, map SIGTERM to graceful shutdown:

```python
def sigterm_handler(signum: int, frame: Any) -> None:
    """Handle SIGTERM (Docker stop)."""
    interrupt_manager.request_interrupt(
        InterruptReason(
            source=InterruptSource.SYSTEM,
            mode=InterruptMode.GRACEFUL,
            message="Docker container stop signal received"
        )
    )

signal.signal(signal.SIGTERM, sigterm_handler)
```

### Cost Control

Budget limit can trigger automatic interrupts:

```python
from kaizen.core.autonomy.interrupts.handlers import BudgetInterruptHandler

# Auto-stop at budget limit
budget_handler = BudgetInterruptHandler(
    interrupt_manager=interrupt_manager,
    budget_usd=10.0  # $10 limit
)
```

## Related Examples

- **03_budget_interrupt.py** - Budget-limited execution with auto-stop
- **02_timeout_interrupt.py** - Timeout-based interrupts (timeout handler)
- **checkpoints/resume-interrupted-research/** - Research workflow with checkpoint resume
- **full-integration/autonomous-research-agent/** - All systems integrated

## References

- [Interrupt Mechanism Guide](../../../../docs/guides/interrupt-mechanism-guide.md)
- [Checkpoint System](../../../../docs/features/checkpoint-resume-system.md)
- [Hooks System Guide](../../../../docs/guides/hooks-system-guide.md)
- [ADR-016: Interrupt Mechanism](../../../../docs/architecture/adr/ADR-016-interrupt-mechanism.md)

---

**Example Type**: Interrupt Handling
**Systems**: Interrupts, Checkpoints, Hooks, State Management
**Cost**: $0.00 (FREE with Ollama)
**Complexity**: Intermediate
**Production-Ready**: ✅ Yes
