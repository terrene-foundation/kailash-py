# Interrupt Mechanism Examples

This directory contains examples demonstrating the interrupt mechanism for graceful shutdown of autonomous agents.

## Overview

The interrupt mechanism provides:
- **Graceful Shutdown**: Finish current cycle and save checkpoint
- **Immediate Shutdown**: Stop as soon as possible (best effort)
- **Multiple Sources**: User (Ctrl+C), System (timeout/budget), API (programmatic)
- **Propagation**: Parent interrupts cascade to children
- **Resume**: Continue from checkpoint after interrupt

## Examples

### 01. Ctrl+C Interrupt (`01_ctrl_c_interrupt.py`)

Handle Ctrl+C gracefully during autonomous execution.

**Features**:
- Signal handler registration for SIGINT
- Graceful shutdown on first Ctrl+C
- Immediate shutdown on second Ctrl+C
- Checkpoint saved before exit
- Resume capability

**Usage**:
```bash
python 01_ctrl_c_interrupt.py

# Press Ctrl+C during execution
# Run again to resume from checkpoint
```

**How it works**:
1. Registers SIGINT handler that triggers graceful interrupt
2. Agent finishes current cycle when interrupted
3. Saves checkpoint with interrupt metadata
4. Next run resumes from checkpoint

---

### 02. Timeout Interrupt (`02_timeout_interrupt.py`)

Auto-stop agent after timeout duration.

**Features**:
- TimeoutHandler for automatic interruption
- Configurable timeout (10 seconds in example)
- Graceful shutdown on timeout
- Checkpoint saved

**Usage**:
```bash
python 02_timeout_interrupt.py

# Agent stops automatically after 10 seconds
```

**How it works**:
1. TimeoutHandler monitors execution time
2. Triggers graceful interrupt when timeout reached
3. Agent finishes current cycle and saves checkpoint
4. Shows elapsed time and cycles completed

---

### 03. Budget Interrupt (`03_budget_interrupt.py`)

Auto-stop agent when cost limit exceeded.

**Features**:
- BudgetHandler for cost-based interruption
- Real-time cost tracking
- Configurable budget limit ($0.10 in example)
- Graceful shutdown when budget exceeded
- Cost breakdown report

**Usage**:
```bash
python 03_budget_interrupt.py

# Agent stops when cost exceeds $0.10
```

**How it works**:
1. BudgetHandler tracks accumulated cost per cycle
2. Triggers graceful interrupt when budget exceeded
3. Agent finishes current cycle and saves checkpoint
4. Shows cost breakdown and remaining budget

---

## Requirements

All examples require:
- Ollama installed with llama3.2 model
- Python 3.10+
- kailash-kaizen installed

Install requirements:
```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# Pull llama3.2 model
ollama pull llama3.1:8b-instruct-q8_0

# Install kailash-kaizen
pip install kailash-kaizen
```

## Key Concepts

### Interrupt Sources

- **USER**: Ctrl+C, user-initiated interrupts
- **SYSTEM**: Timeout, budget limits, system events
- **API**: Programmatic interrupts via Control Protocol
- **PARENT**: Propagated from parent agent

### Interrupt Modes

- **GRACEFUL**: Finish current cycle, save checkpoint, then exit
- **IMMEDIATE**: Stop as soon as possible (best effort, may not complete cycle)

### Interrupt Flow

```
1. Interrupt triggered (Ctrl+C / timeout / budget)
   ↓
2. InterruptManager sets interrupted flag
   ↓
3. Agent checks is_interrupted() at cycle boundary
   ↓
4. If GRACEFUL: Finish cycle, save checkpoint
   If IMMEDIATE: Stop now (best effort)
   ↓
5. Return result with status="interrupted"
```

### Checkpoint Integration

All examples save checkpoints before shutdown:
- Checkpoint includes interrupt metadata (source, mode, message, timestamp)
- Resume skips interrupted cycle
- Checkpoint cleaned up on successful completion

### Multi-Agent Propagation

Parent interrupt propagates to all children:
```python
parent_manager.add_child(child_manager)
parent_manager.request_interrupt(...)  # Children also interrupted
```

## Troubleshooting

**Checkpoint not saved?**
- Verify checkpoint_frequency > 0
- Check disk space in checkpoint directory
- Ensure graceful shutdown (not immediate)

**Resume not working?**
- Verify resume_from_checkpoint=True
- Check checkpoint file exists
- Ensure agent_id matches original run

**Timeout too short?**
- Increase timeout_seconds parameter
- Consider cycle duration when setting timeout
- Add logging to see cycle timings

**Budget exceeded too quickly?**
- Increase max_cost parameter
- Use smaller model (llama3.1:8b-instruct-q8_0)
- Reduce max_tokens in config

## Further Reading

- [Interrupt Mechanism Guide](../../../docs/guides/interrupt-mechanism-guide.md)
- [Interrupt API Reference](../../../docs/reference/interrupt-api.md)
- [ADR-016: Interrupt Mechanism](../../../docs/architecture/adr/016-interrupt-mechanism-design.md)
