# /evolve - Instinct Evolution Command

## Purpose

Evolve learned instincts into actionable artifacts (skills, commands, agents).

## Quick Reference

| Command | Action |
|---------|--------|
| `/evolve` | Show evolution candidates |
| `/evolve skill <instinct_id>` | Evolve instinct into skill |
| `/evolve command <instinct_id>` | Evolve instinct into command |
| `/evolve agent <instinct_id>` | Evolve instinct into agent |
| `/evolve auto` | Auto-evolve high-confidence instincts |

## Usage Examples

### View Evolution Candidates

```bash
# List instincts ready for evolution (confidence >= 0.7)
node scripts/learning/instinct-evolver.js --candidates
```

### Evolve to Skill

```bash
# Evolve a workflow pattern instinct to a skill
node scripts/learning/instinct-evolver.js --evolve-skill instinct_123_abc
```

### Evolve to Command

```bash
# Evolve an error-fix instinct to a command
node scripts/learning/instinct-evolver.js --evolve-command instinct_456_def
```

### Auto-Evolution

```bash
# Auto-evolve all instincts with confidence >= 0.8
node scripts/learning/instinct-evolver.js --auto
```

## Evolution Rules

### Confidence Thresholds

| Target | Min Confidence | Min Occurrences |
|--------|---------------|-----------------|
| Skill | 0.7 | 5 |
| Command | 0.6 | 3 |
| Agent | 0.8 | 10 |

### Pattern Type Mapping

| Pattern Type | Best Evolution |
|--------------|---------------|
| workflow_pattern | Skill (quick patterns) |
| error_fix | Command (slash command) |
| framework_selection | Agent policy update |
| node_usage | Skill examples |

## Output Locations

```
~/.claude/kailash-learning/evolved/
├── skills/           # Generated skill snippets
├── commands/         # Generated commands
└── agents/          # Agent policy updates
```

## Integration

Evolved artifacts are suggestions only. Review before adding to:
- `.claude/skills/` for skills
- `.claude/commands/` for commands
- `.claude/agents/` for agent updates

## Related Commands

- `/learn` - View learning status and instincts
- `/checkpoint` - Save learning state

## Skill Reference

- See `06-continuous-learning` in skill directories for full documentation
