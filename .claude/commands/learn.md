# /learn - Continuous Learning Command

## Purpose

Interact with the Kailash Continuous Learning System to view, analyze, and evolve learned patterns.

## Quick Reference

| Command | Action |
|---------|--------|
| `/learn` | Show learning status and statistics |
| `/learn stats` | Show detailed observation statistics |
| `/learn analyze` | Analyze observations for patterns |
| `/learn generate` | Generate instincts from patterns |
| `/learn list` | List all learned instincts |

## Usage Examples

### Check Learning Status

```bash
# Show current learning statistics
node scripts/learning/observation-logger.js --stats
```

### Analyze Patterns

```bash
# Analyze observations for patterns
node scripts/learning/instinct-processor.js --analyze
```

### Generate Instincts

```bash
# Generate instincts from detected patterns
node scripts/learning/instinct-processor.js --generate
```

## How It Works

1. **Observation Capture**: Hooks automatically capture tool usage, errors, and patterns
2. **Pattern Detection**: Analyzer identifies recurring patterns in observations
3. **Instinct Generation**: Patterns with sufficient occurrences become instincts
4. **Evolution**: Instincts can be evolved into new skills, commands, or agents

## Learning Focus Areas

The system learns Kailash-specific patterns:

| Area | What It Learns |
|------|---------------|
| **Workflow Patterns** | Common node sequences, connection patterns |
| **Error-Fix Pairs** | Which errors occur and how they're fixed |
| **DataFlow Patterns** | Model definition patterns, query patterns |
| **Framework Selection** | Project type → framework mapping |
| **Testing Patterns** | Test structure preferences |

## File Locations

```
~/.claude/kailash-learning/
├── identity.json           # System identity
├── observations.jsonl      # Raw observations
├── observations.archive/   # Processed observations
├── instincts/
│   ├── personal/          # Auto-learned instincts
│   └── inherited/         # Shared from team
└── evolved/               # Generated content
```

## Related Commands

- `/evolve` - Evolve instincts into skills
- `/checkpoint` - Save current learning state

## Skill Reference

- See `06-continuous-learning` in skill directories for full documentation
