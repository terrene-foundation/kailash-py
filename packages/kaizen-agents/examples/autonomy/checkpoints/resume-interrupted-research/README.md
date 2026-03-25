# Resume Interrupted Research - Checkpoint & Resume Pattern

## Overview

This example demonstrates **automatic checkpointing and graceful resume** for long-running autonomous agents. The agent analyzes 100 research papers with automatic checkpoint creation every 10 steps, graceful interrupt handling (Ctrl+C), and seamless resume from the latest checkpoint.

**Key Features:**
- ✅ Automatic checkpoint every N steps (configurable)
- ✅ Graceful interrupt handling (Ctrl+C detection)
- ✅ Resume from latest checkpoint
- ✅ State preservation (conversation history, budget, progress)
- ✅ Checkpoint compression (50%+ size reduction)
- ✅ Retention policy (keep last N checkpoints)
- ✅ Budget tracking ($0.00 with Ollama - FREE)
- ✅ Hooks integration for checkpoint metrics

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Checkpoint & Resume System                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  RUN 1 (Interrupted at Step 47):                       │
│  ┌─────────────────────────────────────────┐          │
│  │ Step 1-10  → Checkpoint 1 saved ✅       │          │
│  │ Step 11-20 → Checkpoint 2 saved ✅       │          │
│  │ Step 21-30 → Checkpoint 3 saved ✅       │          │
│  │ Step 31-40 → Checkpoint 4 saved ✅       │          │
│  │ Step 47    → Ctrl+C detected! ⚠️         │          │
│  │            → Checkpoint 5 saved ✅       │          │
│  │            → Graceful shutdown complete │          │
│  └─────────────────────────────────────────┘          │
│                     │                                   │
│                     ↓                                   │
│  RUN 2 (Resume from Checkpoint 5):                     │
│  ┌─────────────────────────────────────────┐          │
│  │ Load checkpoint 5 → Resume at step 48   │          │
│  │ Step 48-50 → Continue analysis           │          │
│  │ Step 51-60 → Checkpoint 6 saved ✅       │          │
│  │ ...                                      │          │
│  │ Step 91-100 → Checkpoint 10 saved ✅     │          │
│  │ Complete! Total: 100 papers analyzed    │          │
│  └─────────────────────────────────────────┘          │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  FilesystemStorage (Compressed JSONL):                 │
│  - checkpoint_001.jsonl.gz (compressed 58%)            │
│  - checkpoint_002.jsonl.gz (compressed 55%)            │
│  - checkpoint_005.jsonl.gz (interrupted state)         │
│  - Retention: Keep last 20 checkpoints                 │
└─────────────────────────────────────────────────────────┘
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
cd examples/autonomy/checkpoints/resume-interrupted-research

# 2. Ensure Ollama is running
ollama serve

# 3. Pull model (first time only)
ollama pull llama3.1:8b-instruct-q8_0
```

## Usage

### Quick Start

```bash
# Run 1: Start research (will be interrupted at step 47)
python resume_interrupted_research.py

# The script will simulate Ctrl+C at step 47
# Checkpoint automatically saved

# Run 2: Resume from checkpoint (continues from step 47)
python resume_interrupted_research.py

# Resumes from step 48, completes steps 48-100
```

### Manual Interrupt Testing

To test real Ctrl+C handling:

1. **Comment out** the `simulate_interrupt_at` parameter in `main()`:
   ```python
   # Before:
   result = await agent.analyze_papers(simulate_interrupt_at=47)

   # After:
   result = await agent.analyze_papers()  # No simulation
   ```

2. **Run** the script and press **Ctrl+C** at any time:
   ```bash
   python resume_interrupted_research.py
   # Press Ctrl+C when you see "STEP 47: Analyzing..."
   ```

3. **Run again** to resume from checkpoint:
   ```bash
   python resume_interrupted_research.py
   # Automatically resumes from step 47
   ```

## Expected Output

### Run 1 (Interrupted at Step 47)

```
==================================================================
CHECKPOINT & RESUME DEMONSTRATION
==================================================================

This example demonstrates:
  1. Automatic checkpoint every 10 steps
  2. Graceful interrupt handling (Ctrl+C)
  3. Resume from latest checkpoint
  4. Checkpoint compression (50%+ reduction)
  5. Retention policy (keep last 20 checkpoints)

Instructions:
  - Run 1: Start research (press Ctrl+C at ~step 47)
  - Run 2: Resume from checkpoint (continues from step 47)

Press Ctrl+C anytime to interrupt...

============================================================
RESEARCH SESSION - AI Ethics Paper Analysis
============================================================

✨ NEW SESSION - Starting from paper 1

STEP 1: Analyzing 'Ethics in AI Systems: A Survey (Part 1)...' (0.25s)
STEP 2: Analyzing 'Fairness in Machine Learning Algorithms (Part 1)...' (0.26s)
...
STEP 10: Analyzing 'Ethical Considerations in Facial Recognition (Part 1)...' (0.25s)
→ Checkpoint saved: ckpt_001_20250103_120000
Checkpoint ckpt_001_20250103_120000 saved at step 10 (compression: 58.2%)

STEP 11: Analyzing 'Ethics in AI Systems: A Survey (Part 2)...' (0.24s)
...
STEP 20: Analyzing 'Ethical Considerations in Facial Recognition (Part 2)...' (0.26s)
→ Checkpoint saved: ckpt_002_20250103_120030
Checkpoint ckpt_002_20250103_120030 saved at step 20 (compression: 55.7%)

...

STEP 40: Analyzing 'Ethical Considerations in Facial Recognition (Part 4)...' (0.25s)
→ Checkpoint saved: ckpt_004_20250103_120120
Checkpoint ckpt_004_20250103_120120 saved at step 40 (compression: 57.1%)

STEP 41: Analyzing 'Ethics in AI Systems: A Survey (Part 5)...' (0.24s)
...
STEP 47: Analyzing 'Privacy-Preserving Machine Learning Techniques (Part 5)...' (0.25s)

⚠️  Interrupted at step 47
→ Saving final checkpoint...
→ Checkpoint saved: ckpt_005_20250103_120147
→ Graceful shutdown complete

==================================================================
INTERRUPTED - Now run again to resume!
==================================================================

Checkpoint saved at step 47
Run the script again to resume from this checkpoint.
```

### Run 2 (Resume from Checkpoint)

```
============================================================
RESEARCH SESSION - AI Ethics Paper Analysis
============================================================

🔄 RESUMING from checkpoint ckpt_005_20250103_120147
→ Previous progress: 47 papers analyzed
→ Budget spent: $0.00
→ Continuing from step 48...

STEP 48: Analyzing 'Accountability in Autonomous AI Systems (Part 5)...' (0.25s)
STEP 49: Analyzing 'Human Rights and Artificial Intelligence (Part 5)...' (0.26s)
STEP 50: Analyzing 'Algorithmic Decision-Making and Social Justice (Part 5)...' (0.24s)
→ Checkpoint saved: ckpt_006_20250103_120215
Checkpoint ckpt_006_20250103_120215 saved at step 50 (compression: 56.4%)

...

STEP 100: Analyzing 'Ethical Considerations in Facial Recognition (Part 10)...' (0.25s)
→ Checkpoint saved: ckpt_010_20250103_120345
Checkpoint ckpt_010_20250103_120345 saved at step 100 (compression: 57.8%)

============================================================
RESEARCH SESSION COMPLETE
============================================================
Total papers analyzed: 100
Budget spent: $0.00 (Ollama - FREE)

CHECKPOINT STATISTICS:
- Total checkpoints: 10
- Compressed size: 45.2 KB
- Uncompressed size: 102.7 KB
- Average compression: 56.0%
```

## Configuration

### Checkpoint Frequency

Adjust how often checkpoints are created:

```python
# Checkpoint every 5 steps (more frequent)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=5,  # Every 5 steps
    retention_count=20
)

# Checkpoint every 20 steps (less frequent)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=20,  # Every 20 steps
    retention_count=20
)
```

### Retention Policy

Control how many checkpoints to keep:

```python
# Keep last 10 checkpoints (less disk space)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=10,
    retention_count=10  # Keep only 10 latest
)

# Keep last 50 checkpoints (more history)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=10,
    retention_count=50  # Keep 50 latest
)
```

### Compression

Enable/disable checkpoint compression:

```python
# With compression (recommended - 50%+ size reduction)
storage = FilesystemStorage(
    base_dir="./checkpoints",
    compress=True  # Enable gzip compression
)

# Without compression (faster, but larger files)
storage = FilesystemStorage(
    base_dir="./checkpoints",
    compress=False  # Disable compression
)
```

## Troubleshooting

### Issue: No Checkpoint Files Created

**Symptom:** No files in `./checkpoints/` directory

**Solution:**
1. Check that StateManager is passed to agent
2. Verify checkpoint frequency isn't too high (e.g., 100+)
3. Ensure agent runs for multiple steps
4. Enable debug logging:
   ```python
   logging.basicConfig(level=logging.DEBUG)
   ```

### Issue: Resume Not Working

**Symptom:** Agent starts from beginning despite checkpoints existing

**Solution:**
1. Check that checkpoint files exist in `./checkpoints/`
2. Verify same storage directory is used for both runs
3. Ensure `resume_from_checkpoint=True` in config
4. Check logs for resume errors:
   ```bash
   python resume_interrupted_research.py 2>&1 | grep "RESUMING"
   ```

### Issue: Compression Errors

**Symptom:** Cannot load compressed checkpoints

**Solution:**
1. Ensure gzip module is available (standard library)
2. Verify file has `.jsonl.gz` extension
3. Check file isn't corrupted:
   ```bash
   gzip -t checkpoints/ckpt_*.jsonl.gz
   ```
4. Try loading without compression:
   ```python
   storage = FilesystemStorage(compress=False)
   ```

### Issue: Too Many Checkpoint Files

**Symptom:** Checkpoint directory growing too large

**Solution:**
1. Lower retention count:
   ```python
   state_manager = StateManager(retention_count=10)
   ```
2. Manually clean up old checkpoints:
   ```python
   deleted = await state_manager.cleanup_old_checkpoints("research_agent")
   print(f"Deleted {deleted} old checkpoints")
   ```
3. Enable compression to reduce size:
   ```python
   storage = FilesystemStorage(compress=True)
   ```

## Production Notes

### Long-Running Workflows (30+ Hours)

For production workflows running for many hours:

1. **Increase checkpoint frequency** for safety:
   ```python
   # Checkpoint every 5 steps (more frequent)
   state_manager = StateManager(checkpoint_frequency=5)
   ```

2. **Increase retention** for debugging:
   ```python
   # Keep last 100 checkpoints (better audit trail)
   state_manager = StateManager(retention_count=100)
   ```

3. **Enable hooks** for monitoring:
   ```python
   hook_manager = HookManager()
   hook_manager.register_hook(CheckpointMetricsHook())
   ```

### Storage Strategies

**Development:**
- Use filesystem storage for simplicity
- Enable compression to save disk space
- Keep lower retention (10-20 checkpoints)

**Production:**
- Consider database storage for multi-instance deployments
- Enable compression for network efficiency
- Increase retention for audit trails (50-100 checkpoints)

### Error Recovery

Checkpoints enable recovery from:
- **System crashes** - Resume from last checkpoint
- **Out of memory** - Restart with saved state
- **Network failures** - Continue after connectivity restored
- **Budget limits** - Stop gracefully, resume when budget increased

### Performance Impact

Checkpoint overhead:
- **Save time**: 5-15ms per checkpoint (with compression)
- **Load time**: 3-7ms per checkpoint (with compression)
- **Storage**: ~500 bytes per checkpoint (compressed)
- **Memory**: Negligible (<1MB for state manager)

**Recommendation:** Checkpoint every 5-10 steps for optimal balance.

## Key Concepts

### 1. Automatic Checkpointing

State is automatically saved every N steps without manual intervention:

```python
# Agent automatically creates checkpoints
for i in range(100):
    analyze_paper(i)
    # Checkpoint saved every 10 steps automatically
```

### 2. Graceful Interrupt Handling

Ctrl+C is handled gracefully with state preservation:

```python
# Ctrl+C detected
# → Save checkpoint
# → Clean up resources
# → Exit safely
```

### 3. Resume from Latest

Agent automatically resumes from last checkpoint:

```python
# Run 1: Stop at step 47
# Run 2: Resume from step 47 automatically
```

### 4. Checkpoint Compression

Checkpoints are compressed with gzip for 50%+ size reduction:

```
Uncompressed: 102.7 KB
Compressed:    45.2 KB  (56.0% reduction)
```

### 5. Retention Policy

Old checkpoints are automatically deleted:

```python
# Keep only last 20 checkpoints
# Oldest checkpoints deleted automatically
state_manager = StateManager(retention_count=20)
```

## Related Examples

- **Multi-Day Project** - Checkpoint with forking for experimentation
- **Long-Running Research** - 3-tier memory with persistent storage
- **Interrupt Handling** - Timeout and budget interrupts

## Next Steps

1. **Try manual interrupt** - Comment out `simulate_interrupt_at` and press Ctrl+C
2. **Adjust checkpoint frequency** - Experiment with different frequencies
3. **Test retention policy** - Run multiple times and observe cleanup
4. **Add custom hooks** - Track additional metrics (e.g., paper topics, confidence scores)
5. **Production deployment** - Use database storage for multi-instance workflows

---

**Framework**: Kaizen AI Framework built on Kailash Core SDK
**Cost**: $0.00 (Ollama - unlimited usage)
**Production-Ready**: ✅ Comprehensive error handling, logging, and hooks
