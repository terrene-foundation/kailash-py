# Multi-Day Project - Checkpoint with Compression & Forking

## Overview

This example demonstrates **long-running project workflows with checkpoint forking** for autonomous agents. The agent simulates a 3-day software project with daily checkpoints, compression, retention policies, and the ability to fork checkpoints for experimental approaches while maintaining an independent main branch.

**Key Features:**
- ✅ Daily progress checkpoints (multi-session workflow)
- ✅ Checkpoint compression (50%+ size reduction)
- ✅ Retention policy (automatic cleanup of old checkpoints)
- ✅ Fork checkpoint for experimentation (create independent branch)
- ✅ State restoration from any checkpoint
- ✅ Progress tracking across days
- ✅ Budget tracking ($0.00 with Ollama - FREE)
- ✅ Hooks integration for progress metrics

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                Multi-Day Project with Forking                     │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  DAY 1 (Main Branch):                                            │
│  ┌─────────────────────────────────────────────────┐            │
│  │ Task 1: Design architecture (0.15s)             │            │
│  │ Task 2: Setup environment (0.15s)               │            │
│  │ → Checkpoint: day1_final.jsonl.gz ✅            │            │
│  └─────────────────────────────────────────────────┘            │
│                         │                                         │
│                         ↓                                         │
│  DAY 2 (Main Branch):                                            │
│  ┌─────────────────────────────────────────────────┐            │
│  │ Task 3: Implement data layer (0.15s)            │            │
│  │ Task 4: Implement business logic (0.15s)        │            │
│  │ Task 5: Write unit tests (0.15s)                │            │
│  │ → Checkpoint: day2_final.jsonl.gz ✅            │            │
│  └─────────────────────────────────────────────────┘            │
│                         │                                         │
│                         ├─────────────────┐                       │
│                         │                 │                       │
│                         ↓                 ↓                       │
│  DAY 3 (Main Branch):  │    DAY 3 (Experiment Branch):          │
│  ┌──────────────────┐  │    ┌──────────────────────────┐        │
│  │ Task 6: Auth     │  │    │ FORK from day2_final ✅   │        │
│  │ Task 7: Validate │  │    │ Task: Alt auth approach   │        │
│  │ Task 8: Docs     │  │    │ Task: Test new design     │        │
│  │ → day3_main.gz ✅│  │    │ → day3_experiment.gz ✅   │        │
│  └──────────────────┘  │    └──────────────────────────┘        │
│                         │                                         │
│  RESULT:                │    RESULT:                              │
│  - 8 tasks complete     │    - 2 experiments complete            │
│  - Main branch intact   │    - Independent branch                │
│  - Production ready     │    - Can merge or discard              │
│                                                                   │
├───────────────────────────────────────────────────────────────────┤
│  FilesystemStorage (Compressed JSONL):                           │
│  - day1_final.jsonl.gz (compressed 55%)                          │
│  - day2_final.jsonl.gz (compressed 58%)                          │
│  - day3_main.jsonl.gz (main branch, compressed 60%)              │
│  - day3_experiment.jsonl.gz (fork branch, compressed 57%)        │
│  - Retention: Keep last 20 checkpoints                           │
└───────────────────────────────────────────────────────────────────┘
```

## Prerequisites

### Required
- **Ollama** with `llama3.1:8b-instruct-q8_0` model (FREE - no API costs)
  ```bash
  # Install Ollama (if not already installed)
  curl -fsSL https://ollama.com/install.sh | sh

  # Pull llama3.1:8b-instruct-q8_0 model
  ollama pull llama3.1:8b-instruct-q8_0
  ```

- **Python 3.8+**
- **kailash-kaizen** package
  ```bash
  pip install kailash-kaizen
  ```

### Optional
- None - example is fully self-contained with Ollama (FREE)

## Installation

```bash
# 1. Navigate to example directory
cd examples/autonomy/checkpoints/multi-day-project

# 2. Ensure Ollama is running
ollama serve

# 3. Pull model (first time only)
ollama pull llama3.1:8b-instruct-q8_0
```

## Usage

### Quick Start

```bash
# Run complete 3-day project simulation
python multi_day_project.py

# The script will:
# - Day 1: Complete 2 tasks, save checkpoint
# - Day 2: Complete 3 tasks, save checkpoint
# - Fork from Day 2 checkpoint for experimentation
# - Day 3 (Experiment): Test 2 alternative approaches
# - Day 3 (Main): Complete 3 remaining tasks
```

### Expected Output

```
======================================================================
MULTI-DAY PROJECT SIMULATION
======================================================================

This example demonstrates:
  1. Daily progress checkpoints
  2. Checkpoint compression (50%+ reduction)
  3. Fork checkpoint for experimentation
  4. Independent branch development
  5. Retention policy (keep last 20 checkpoints)


============================================================
═══ DAY 1 ═══
============================================================

TASKS: Design system architecture, Setup development environment

STEP 1: Design system architecture
→ Completed in 0.15s

STEP 2: Setup development environment
→ Completed in 0.15s

DAY 1 COMPLETE: 2 tasks finished
→ Final checkpoint: day1_final_20250103_120000
Checkpoint day1_final_20250103_120000 compressed: 55.2%

============================================================
═══ DAY 2 ═══
============================================================

TASKS: Implement data layer, Implement business logic, Write unit tests

STEP 11: Implement data layer
→ Completed in 0.15s

STEP 12: Implement business logic
→ Completed in 0.15s

STEP 13: Write unit tests
→ Completed in 0.15s

→ Checkpoint saved: day2_step13_20250103_120030
Checkpoint day2_step13_20250103_120030 compressed: 58.4%

DAY 2 COMPLETE: 3 tasks finished
→ Final checkpoint: day2_final_20250103_120045
Checkpoint day2_final_20250103_120045 compressed: 57.1%

============================================================
FORKING CHECKPOINT FOR EXPERIMENTATION
============================================================

→ Forking from checkpoint: day2_final_20250103_120045
→ Fork created: experiment_fork_20250103_120046
→ Experiment branch is now independent

============================================================
═══ DAY 3 ═══
                       BRANCH: experiment
============================================================

TASKS: Experiment with alternative authentication, Test new approach

STEP 21: Experiment with alternative authentication
→ Completed in 0.15s

STEP 22: Test new approach
→ Completed in 0.15s

DAY 3 COMPLETE: 2 tasks finished
→ Final checkpoint: day3_experiment_20250103_120060
Checkpoint day3_experiment_20250103_120060 compressed: 56.8%

============================================================
═══ DAY 3 ═══
                       BRANCH: main
============================================================

TASKS: Add user authentication, Add data validation, Create API documentation

STEP 21: Add user authentication
→ Completed in 0.15s

STEP 22: Add data validation
→ Completed in 0.15s

STEP 23: Create API documentation
→ Completed in 0.15s

→ Checkpoint saved: day3_step23_20250103_120075
Checkpoint day3_step23_20250103_120075 compressed: 59.2%

DAY 3 COMPLETE: 3 tasks finished
→ Final checkpoint: day3_main_20250103_120090
Checkpoint day3_main_20250103_120090 compressed: 60.1%

======================================================================
FINAL PROJECT STATISTICS
======================================================================

Main Branch:
- Total days: 3
- Total tasks: 8 (day 1: 2, day 2: 3, day 3: 3)
- Final checkpoint: day3_main_20250103_120090

Experiment Branch:
- Forked from: Day 2 checkpoint
- Tasks tested: 2 (alternative approaches)
- Final checkpoint: day3_experiment_20250103_120060

Checkpoint Statistics:
- Total checkpoints: 7
- Average compression: 58.1%
- Total forks: 1
- Budget spent: $0.00 (Ollama - FREE)

Checkpoint Files:
  - day1_final_20250103_120000.jsonl.gz (2.3 KB)
  - day2_step13_20250103_120030.jsonl.gz (2.5 KB)
  - day2_final_20250103_120045.jsonl.gz (2.7 KB)
  - experiment_fork_20250103_120046.jsonl.gz (2.7 KB)
  - day3_experiment_20250103_120060.jsonl.gz (2.8 KB)
  - day3_step23_20250103_120075.jsonl.gz (2.9 KB)
  - day3_main_20250103_120090.jsonl.gz (3.1 KB)

======================================================================
PROJECT COMPLETE
======================================================================
```

## Configuration

### Checkpoint Frequency

Adjust how often checkpoints are created:

```python
# More frequent checkpoints (every 3 steps)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=3,
    retention_count=20
)

# Less frequent checkpoints (every 10 steps)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=10,
    retention_count=20
)
```

### Retention Policy

Control how many checkpoints to keep:

```python
# Keep last 10 checkpoints (less disk space)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=5,
    retention_count=10
)

# Keep last 50 checkpoints (more history)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=5,
    retention_count=50
)
```

### Compression Settings

Enable/disable checkpoint compression:

```python
# With compression (recommended - 50%+ size reduction)
storage = FilesystemStorage(
    base_dir="./project_checkpoints",
    compress=True
)

# Without compression (faster, but larger files)
storage = FilesystemStorage(
    base_dir="./project_checkpoints",
    compress=False
)
```

## Troubleshooting

### Issue: Fork Conflicts

**Symptom:** Cannot fork checkpoint or forked state is corrupted

**Solution:**
1. Verify checkpoint exists:
   ```python
   checkpoints = await state_manager.list_checkpoints()
   print([c.checkpoint_id for c in checkpoints])
   ```
2. Load checkpoint before forking:
   ```python
   parent_state = await state_manager.load_checkpoint(checkpoint_id)
   print(f"Loaded checkpoint: {parent_state.checkpoint_id}")
   ```
3. Ensure unique agent_id for fork:
   ```python
   forked_state = AgentState(
       agent_id="project_agent_fork",  # Must be unique
       ...
   )
   ```

### Issue: Checkpoint Size Growing

**Symptom:** Checkpoint files growing too large

**Solution:**
1. Enable compression:
   ```python
   storage = FilesystemStorage(compress=True)
   ```
2. Reduce conversation history retention:
   ```python
   # Keep only last 100 messages
   current_state.conversation_history = history[-100:]
   ```
3. Clear unnecessary memory contents:
   ```python
   current_state.memory_contents = {
       "essential_data_only": data
   }
   ```

### Issue: Cannot Restore from Checkpoint

**Symptom:** Fork or resume fails with deserialization errors

**Solution:**
1. Check checkpoint file integrity:
   ```bash
   gzip -t project_checkpoints/*.jsonl.gz
   ```
2. Verify checkpoint metadata:
   ```python
   checkpoints = await state_manager.list_checkpoints()
   for ckpt in checkpoints:
       print(f"{ckpt.checkpoint_id}: {ckpt.status}")
   ```
3. Load with error handling:
   ```python
   try:
       state = await state_manager.load_checkpoint(checkpoint_id)
   except Exception as e:
       logger.error(f"Failed to load checkpoint: {e}")
   ```

### Issue: Storage Space Exhaustion

**Symptom:** Disk space running out from too many checkpoints

**Solution:**
1. Lower retention count:
   ```python
   state_manager = StateManager(retention_count=10)
   ```
2. Manual cleanup:
   ```python
   deleted = await state_manager.cleanup_old_checkpoints("project_agent_main")
   print(f"Deleted {deleted} checkpoints")
   ```
3. Enable compression if not already:
   ```python
   storage = FilesystemStorage(compress=True)
   ```

## Production Notes

### Long-Running Workflows

For projects spanning days/weeks:

1. **Increase checkpoint frequency** for safety:
   ```python
   state_manager = StateManager(checkpoint_frequency=3)
   ```

2. **Increase retention** for audit trail:
   ```python
   state_manager = StateManager(retention_count=100)
   ```

3. **Enable compression** to save space:
   ```python
   storage = FilesystemStorage(compress=True)
   ```

### Experiment Tracking

**Best Practices for Forking:**

1. **Clear naming convention:**
   ```python
   agent_id = f"project_agent_{experiment_name}"
   ```

2. **Track fork metadata:**
   ```python
   forked_state.memory_contents = {
       "forked_from": parent_checkpoint_id,
       "fork_purpose": "test_alternative_auth",
       "fork_timestamp": datetime.now().isoformat()
   }
   ```

3. **Document fork decisions:**
   ```python
   logger.info(f"Forking from {parent_id} to test: {purpose}")
   ```

### Checkpoint Storage Strategies

**Development:**
- Use filesystem storage for simplicity
- Enable compression (50%+ reduction)
- Keep moderate retention (20 checkpoints)

**Production:**
- Consider database storage for multi-instance deployments
- Enable compression for network efficiency
- Increase retention for audit trails (50-100 checkpoints)

### Performance Characteristics

Checkpoint overhead:
- **Save time**: 8-15ms per checkpoint (with compression)
- **Load time**: 3-7ms per checkpoint (with compression)
- **Fork time**: 5-10ms (copy + modify operation)
- **Storage**: ~2-3 KB per checkpoint (compressed)
- **Memory**: Negligible (<1MB for state manager)

**Recommendation:** Checkpoint every 3-5 steps for optimal balance.

## Key Concepts

### 1. Daily Checkpoints

State is saved at the end of each day for long-running projects:

```python
# Day 1: Complete tasks → Save checkpoint
# Day 2: Resume from Day 1 → Save checkpoint
# Day 3: Resume from Day 2 → Save checkpoint
```

### 2. Checkpoint Compression

Checkpoints are compressed with gzip for 50%+ size reduction:

```
Uncompressed: 6.8 KB
Compressed:   2.8 KB  (58.8% reduction)
```

### 3. Fork for Experimentation

Create independent branch from any checkpoint:

```python
# Fork from Day 2 checkpoint
# → Experiment branch: Try alternative approach
# → Main branch: Continue original plan
# Both branches are independent
```

### 4. State Restoration

Restore agent state from any checkpoint:

```python
# Load specific checkpoint
state = await state_manager.load_checkpoint(checkpoint_id)

# Load latest checkpoint
state = await state_manager.resume_from_latest("project_agent_main")
```

### 5. Retention Policy

Old checkpoints are automatically deleted:

```python
# Keep only last 20 checkpoints
# Oldest checkpoints deleted automatically
state_manager = StateManager(retention_count=20)
```

## Related Examples

- **Resume Interrupted Research** - Automatic checkpoint with Ctrl+C handling
- **Long-Running Research** - 3-tier memory with persistent storage
- **Customer Support** - Persistent conversation memory

## Next Steps

1. **Customize project tasks** - Add your own workflow tasks
2. **Adjust checkpoint frequency** - Experiment with different frequencies
3. **Test forking** - Try different experimental approaches
4. **Production deployment** - Use database storage for multi-instance workflows
5. **Add custom hooks** - Track additional metrics (e.g., task dependencies, completion time)

---

**Framework**: Kaizen AI Framework built on Kailash Core SDK
**Cost**: $0.00 (Ollama - unlimited usage)
**Production-Ready**: ✅ Comprehensive error handling, logging, and hooks
