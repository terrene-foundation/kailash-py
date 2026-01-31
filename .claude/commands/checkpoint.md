# /checkpoint - Learning Checkpoint Command

## Purpose

Save and restore learning state checkpoints for the continuous learning system.

## Quick Reference

| Command | Action |
|---------|--------|
| `/checkpoint` | Show current checkpoint status |
| `/checkpoint save` | Create new checkpoint |
| `/checkpoint list` | List all checkpoints |
| `/checkpoint restore <id>` | Restore specific checkpoint |
| `/checkpoint diff <id>` | Compare current state with checkpoint |

## Usage Examples

### Save Checkpoint

```bash
# Create a named checkpoint
node scripts/learning/checkpoint-manager.js --save --name "before-refactor"
```

### List Checkpoints

```bash
# Show all saved checkpoints
node scripts/learning/checkpoint-manager.js --list
```

### Restore Checkpoint

```bash
# Restore learning state from checkpoint
node scripts/learning/checkpoint-manager.js --restore checkpoint_123
```

### Compare States

```bash
# Show diff between current state and checkpoint
node scripts/learning/checkpoint-manager.js --diff checkpoint_123
```

## What Gets Checkpointed

| Component | Included |
|-----------|----------|
| Observations | Last 100 entries |
| Instincts | All personal instincts |
| Stats | Learning metrics |
| Identity | System configuration |

## Checkpoint Structure

```
~/.claude/kailash-learning/checkpoints/
├── checkpoint_<timestamp>.json
├── checkpoint_<timestamp>.json
└── latest -> checkpoint_<timestamp>.json
```

## Use Cases

### Before Major Changes

```bash
# Save state before refactoring learning rules
/checkpoint save --name "pre-refactor"
# Make changes to instinct-processor.js
# If issues arise:
/checkpoint restore pre-refactor
```

### Team Sharing

```bash
# Export checkpoint for team member
/checkpoint save --export team-baseline.json
# Team member imports:
/checkpoint restore --import team-baseline.json
```

### Periodic Backup

Checkpoints are auto-created:
- On first session of the day
- Before instinct evolution
- After 100 new observations

## Related Commands

- `/learn` - View learning status
- `/evolve` - Evolve instincts

## Skill Reference

- See `06-continuous-learning` in skill directories for full documentation
