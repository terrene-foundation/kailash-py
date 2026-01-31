# /api - Nexus Quick Reference

## Purpose

Load the Nexus skill for zero-config multi-channel platform deployment (API + CLI + MCP simultaneously).

## Quick Reference

| Command | Action |
|---------|--------|
| `/api` | Load Nexus patterns and deployment basics |
| `/api deploy` | Show deployment patterns |
| `/api session` | Show unified session management |
| `/api channels` | Show multi-channel configuration |

## What You Get

- Zero-config deployment (API + CLI + MCP)
- Unified session management
- Workflow registration patterns
- Health monitoring
- Plugin system

## Quick Pattern

```python
from nexus import Nexus

app = Nexus()

# Register workflows
app.register(my_workflow)

# Deploy to all channels simultaneously
app.start()  # API on :8000, CLI ready, MCP server running
```

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Unified Sessions** | State maintained across API/CLI/MCP |
| **Zero-Config** | Automatic endpoint generation |
| **Multi-Channel** | Single workflow, multiple access methods |
| **Plugin System** | Extend with custom plugins |

## Usage Examples

```bash
# Load Nexus basics
/api

# Get deployment patterns
/api deploy

# Learn session management
/api session

# See multi-channel configuration
/api channels
```

## Related Commands

- `/sdk` - Core SDK patterns
- `/db` - DataFlow database operations
- `/ai` - Kaizen AI agents
- `/test` - Testing strategies
- `/validate` - Gold standards compliance

## Skill Reference

This command loads: `.claude/skills/03-nexus/SKILL.md`
