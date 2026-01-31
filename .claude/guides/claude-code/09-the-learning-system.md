# Guide 09: The Learning System

## Introduction

The learning system enables **continuous improvement** of this setup. It captures patterns from your sessions, extracts insights (instincts), and can evolve high-confidence patterns into new skills, commands, or agents.

By the end of this guide, you will understand:
- How observations are captured
- How instincts are formed
- How evolution creates new components
- The commands for interacting with learning
- How to checkpoint and restore learning state

---

## Part 1: The Learning Loop

### Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     LEARNING LOOP                            │
│                                                              │
│   ┌──────────────┐                                          │
│   │  OBSERVATIONS │ ◄───── During sessions                  │
│   │  Tool usage   │        Patterns logged                   │
│   │  Errors/fixes │                                          │
│   │  Frameworks   │                                          │
│   └───────┬──────┘                                          │
│           │                                                  │
│           ▼                                                  │
│   ┌──────────────┐                                          │
│   │   INSTINCTS   │ ◄───── Extracted patterns               │
│   │  High conf.   │        Statistical analysis             │
│   │  patterns     │        Frequency-based                   │
│   └───────┬──────┘                                          │
│           │                                                  │
│           ▼                                                  │
│   ┌──────────────┐                                          │
│   │   EVOLUTION   │ ◄───── New components                   │
│   │  Skills       │        From high-confidence              │
│   │  Commands     │        instincts                         │
│   │  Agents       │                                          │
│   └──────────────┘                                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### What Gets Learned

| Category | Examples |
|----------|----------|
| **Tool Usage** | Which tools are used most, in what sequences |
| **Workflow Patterns** | Common workflow structures, node combinations |
| **Error Fixes** | Errors encountered and their solutions |
| **Framework Selection** | Which framework for which problem type |
| **Node Usage** | Frequently used nodes and their configurations |
| **Test Patterns** | Testing approaches that work |

---

## Part 2: Observations

### What Are Observations?

Observations are **raw data points** captured during sessions:

```json
{
  "id": "obs_1706720400000_abc123def",
  "timestamp": "2024-01-31T12:00:00.000Z",
  "type": "workflow_pattern",
  "data": {
    "pattern": "api_to_database",
    "nodes": ["HTTPRequest", "Transform", "DataFlowCreate"],
    "success": true
  },
  "context": {
    "session_id": "session_xyz",
    "cwd": "/project/path",
    "framework": "dataflow"
  }
}
```

### Observation Types

| Type | What It Captures |
|------|------------------|
| `tool_use` | Tool invocations and outcomes |
| `workflow_pattern` | Workflow structures used |
| `error_occurrence` | Errors encountered |
| `error_fix` | How errors were resolved |
| `framework_selection` | Framework choices made |
| `node_usage` | Node types and configurations |
| `connection_pattern` | How nodes are connected |
| `test_pattern` | Testing approaches used |
| `dataflow_model` | DataFlow model definitions |
| `session_summary` | End-of-session summaries |

### Observation Storage

Observations are stored in `~/.claude/kailash-learning/`:

```
~/.claude/kailash-learning/
├── observations.jsonl       # Current observations (JSONL format)
├── observations.archive/    # Archived when > 1000 observations
│   ├── observations_1706720400000.jsonl
│   └── observations_1706806800000.jsonl
├── identity.json           # System identity and config
├── instincts/
│   ├── personal/           # Your learned instincts
│   └── inherited/          # Instincts from templates
└── evolved/
    ├── skills/             # Evolved skill files
    ├── commands/           # Evolved command files
    └── agents/             # Evolved agent files
```

### Manual Observation Logging

Use the `/learn` command to log observations manually:

```
> /learn
> DataFlow bulk operations work better with batch sizes of 100
```

This creates an observation that may become an instinct.

---

## Part 3: Instincts

### What Are Instincts?

Instincts are **extracted patterns** with confidence scores:

```json
{
  "id": "instinct_dataflow_batch_100",
  "created": "2024-01-31T12:00:00.000Z",
  "pattern": "dataflow_bulk_batch_size",
  "description": "Use batch size of 100 for DataFlow bulk operations",
  "confidence": 0.85,
  "evidence": {
    "observation_count": 25,
    "success_rate": 0.92,
    "last_observed": "2024-01-31T11:55:00.000Z"
  },
  "category": "dataflow",
  "applies_to": ["bulk_create", "bulk_update"]
}
```

### Confidence Calculation

Confidence is calculated from:

| Factor | Weight | Description |
|--------|--------|-------------|
| Frequency | 40% | How often the pattern appears |
| Success Rate | 30% | How often it leads to success |
| Recency | 20% | Recent observations count more |
| Consistency | 10% | Same pattern across contexts |

### Instinct Categories

| Category | Example Instincts |
|----------|-------------------|
| **workflow** | "Linear workflows with 3-5 nodes are most maintainable" |
| **dataflow** | "Batch size 100 for bulk operations" |
| **testing** | "Always test error paths for DataFlow models" |
| **security** | "Validate email format before database insert" |
| **patterns** | "Use Transform node after API calls" |

### Processing Instincts

Use the `/evolve` command to process observations into instincts:

```
> /evolve
```

This:
1. Reads all observations
2. Identifies patterns with statistical significance
3. Creates or updates instincts
4. Reports new high-confidence patterns

---

## Part 4: Evolution

### What Is Evolution?

Evolution transforms **high-confidence instincts** into new setup components:

```
┌──────────────────────────────────────────────────────────────┐
│                     EVOLUTION                                 │
│                                                               │
│   Instinct (confidence > 0.90):                              │
│   "Always use batch size 100 for DataFlow bulk"              │
│                                                               │
│                        ▼                                      │
│                                                               │
│   Evolution creates:                                          │
│   └── skills/evolved/dataflow-bulk-patterns.md               │
│       └── Contains: Best practices for bulk operations        │
│       └── References: Original instinct                       │
│       └── Examples: Working code patterns                     │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### Evolution Thresholds

| Component Type | Confidence Threshold | Required Observations |
|----------------|---------------------|----------------------|
| **Skills** | 0.85 | 20+ |
| **Commands** | 0.90 | 30+ |
| **Agents** | 0.95 | 50+ |

### Evolved Component Structure

**Evolved Skill**:
```markdown
---
name: evolved-dataflow-bulk
description: "Learned patterns for DataFlow bulk operations"
source: instinct
instinct_id: instinct_dataflow_batch_100
confidence: 0.92
---

# DataFlow Bulk Operation Patterns

## Learned Pattern
Use batch size of 100 for optimal performance.

## Evidence
- Observed 25 times
- 92% success rate
- Last observed: 2024-01-31

## Application
```python
# Instead of processing all at once
db.bulk_create(all_items)  # May timeout

# Use batches
for batch in chunks(items, 100):
    db.bulk_create(batch)  # Reliable
```
```

### Manual Evolution

Use `/evolve` with options:

```
> /evolve                    # Process all instincts
> /evolve --threshold 0.80   # Lower threshold
> /evolve --category dataflow # Only dataflow instincts
> /evolve --dry-run          # Preview without creating
```

---

## Part 5: Learning Commands

### `/learn` - Log Observations

Record a pattern or insight manually:

```
> /learn
> The MCP transport for local development should use stdio
```

Creates an observation that contributes to instinct formation.

### `/evolve` - Process Instincts

Process observations into instincts and evolve high-confidence patterns:

```
> /evolve
```

Output:
```
Processing 150 observations...

New Instincts:
- dataflow_batch_size (confidence: 0.87)
- transform_after_api (confidence: 0.91)

Evolved Components:
- skills/evolved/transform-patterns.md (from transform_after_api)

Summary:
- 150 observations processed
- 12 instincts updated
- 1 new component evolved
```

### `/checkpoint` - Save State

Save current learning state for recovery:

```
> /checkpoint
```

Creates a timestamped backup of:
- All observations
- All instincts
- Evolved components
- Identity configuration

### Viewing Learning Stats

```
> node scripts/learning/observation-logger.js --stats
```

Output:
```json
{
  "total_observations": 1250,
  "current_file": 250,
  "archives": 1,
  "type_breakdown": {
    "tool_use": 500,
    "workflow_pattern": 300,
    "error_fix": 150,
    "framework_selection": 100,
    "test_pattern": 200
  }
}
```

---

## Part 6: Learning Scripts

### observation-logger.js

**Purpose**: Capture and store observations

**Usage**:
```bash
# Log an observation
echo '{"type": "workflow_pattern", "data": {...}}' | node scripts/learning/observation-logger.js

# Get statistics
node scripts/learning/observation-logger.js --stats
```

### instinct-processor.js

**Purpose**: Extract patterns from observations

**Usage**:
```bash
# Process observations into instincts
node scripts/learning/instinct-processor.js

# With options
node scripts/learning/instinct-processor.js --min-confidence 0.80
```

### instinct-evolver.js

**Purpose**: Evolve instincts into components

**Usage**:
```bash
# Evolve high-confidence instincts
node scripts/learning/instinct-evolver.js

# Dry run
node scripts/learning/instinct-evolver.js --dry-run
```

### checkpoint-manager.js

**Purpose**: Manage learning state checkpoints

**Usage**:
```bash
# Create checkpoint
node scripts/learning/checkpoint-manager.js --create

# List checkpoints
node scripts/learning/checkpoint-manager.js --list

# Restore checkpoint
node scripts/learning/checkpoint-manager.js --restore checkpoint_1706720400000
```

---

## Part 7: The Learning Directory

### Structure

```
~/.claude/kailash-learning/
│
├── observations.jsonl          # Active observations (JSONL)
│
├── observations.archive/       # Archived observation files
│   └── observations_*.jsonl
│
├── identity.json              # System identity
│   {
│     "system": "kailash-vibe-cc-setup",
│     "version": "1.0.0",
│     "learning_enabled": true,
│     "focus_areas": [...]
│   }
│
├── instincts/
│   ├── personal/              # Your learned instincts
│   │   └── *.json
│   └── inherited/             # Template instincts
│       └── *.json
│
└── evolved/
    ├── skills/                # Evolved skill files
    │   └── *.md
    ├── commands/              # Evolved command files
    │   └── *.md
    └── agents/                # Evolved agent files
        └── *.md
```

### Identity Configuration

The `identity.json` controls learning behavior:

```json
{
  "system": "kailash-vibe-cc-setup",
  "version": "1.0.0",
  "created_at": "2024-01-31T12:00:00.000Z",
  "learning_enabled": true,
  "focus_areas": [
    "workflow-patterns",
    "error-fixes",
    "dataflow-patterns",
    "testing-patterns",
    "framework-selection"
  ]
}
```

---

## Part 8: Practical Learning Workflow

### Daily Learning

During your sessions, the system automatically:
1. Logs tool usage
2. Captures workflow patterns
3. Records error/fix pairs
4. Notes framework selections

### Weekly Processing

Periodically (weekly recommended):

```
> /evolve
```

This:
1. Processes accumulated observations
2. Updates instinct confidence scores
3. Evolves high-confidence patterns
4. Reports learning summary

### Monthly Checkpointing

Monthly (or before major changes):

```
> /checkpoint
```

This creates a recovery point.

### Reviewing Learned Patterns

Check what's been learned:

```
> What instincts have been learned about DataFlow?
```

Claude checks the instincts directory and reports patterns.

---

## Part 9: Learning Best Practices

### Do Log Valuable Insights

```
> /learn
> When using Nexus with DataFlow, set auto_discovery=False to prevent blocking
```

### Do Process Regularly

```
> /evolve
```

Run periodically to keep instincts fresh.

### Do Checkpoint Before Changes

```
> /checkpoint
```

Before major refactors or updates.

### Don't Over-Log

Don't log every trivial observation. Focus on:
- Patterns that took time to discover
- Solutions to tricky problems
- Non-obvious best practices

### Don't Ignore Evolved Components

Review evolved skills/commands to ensure quality.

---

## Part 10: Key Takeaways

### Summary

1. **Observations capture raw data** - Tool usage, patterns, errors, fixes

2. **Instincts extract patterns** - Statistical analysis of observations

3. **Evolution creates components** - High-confidence instincts become skills

4. **Three commands** - `/learn`, `/evolve`, `/checkpoint`

5. **Four scripts** - logger, processor, evolver, checkpoint manager

6. **Learning directory** - `~/.claude/kailash-learning/`

### Quick Reference

| Command | Purpose |
|---------|---------|
| `/learn` | Log a manual observation |
| `/evolve` | Process instincts, evolve components |
| `/checkpoint` | Save learning state |

| Script | Purpose |
|--------|---------|
| `observation-logger.js` | Capture observations |
| `instinct-processor.js` | Extract patterns |
| `instinct-evolver.js` | Create components |
| `checkpoint-manager.js` | Manage state |

### The Learning Benefit

Over time, the setup becomes:
- **More personalized** - Learns your patterns
- **More efficient** - Common patterns become skills
- **More accurate** - Instincts refine recommendations

---

## What's Next?

Now you understand all the components. The next guide shows how to use them together in daily workflows.

**Next: [10 - Daily Workflows](10-daily-workflows.md)**

---

## Navigation

- **Previous**: [08 - The Rule System](08-the-rule-system.md)
- **Next**: [10 - Daily Workflows](10-daily-workflows.md)
- **Home**: [README.md](README.md)
