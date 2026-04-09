# /api - Nexus Quick Reference

## Purpose

Load the Nexus skill for zero-config multi-channel platform deployment (API + CLI + MCP simultaneously).

## Step 0: Verify Project Uses Kailash Nexus

Before loading Nexus patterns, check that this project uses Kailash Nexus:

- Look for `kailash-nexus` or `nexus` in `requirements.txt`, `pyproject.toml`
- Look for `from nexus` / `import nexus` in source files

If not found, inform the user: "This project doesn't appear to use Kailash Nexus. These patterns may not apply. Continue anyway?"

## Quick Reference

| Command         | Action                                    |
| --------------- | ----------------------------------------- |
| `/api`          | Load Nexus patterns and deployment basics |
| `/api deploy`   | Show deployment patterns                  |
| `/api session`  | Show unified session management           |
| `/api channels` | Show multi-channel configuration          |

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

| Concept              | Description                              |
| -------------------- | ---------------------------------------- |
| **Unified Sessions** | State maintained across API/CLI/MCP      |
| **Zero-Config**      | Automatic endpoint generation            |
| **Multi-Channel**    | Single workflow, multiple access methods |
| **Plugin System**    | Extend with custom plugins               |

## Agent Teams

When working with Nexus, deploy:

- **nexus-specialist** — Multi-channel deployment, unified sessions, workflow registration
- **release-specialist** — Docker/Kubernetes production deployment

## Related Commands

- `/sdk` - Core SDK patterns
- `/db` - DataFlow database operations
- `/ai` - Kaizen AI agents
- `/test` - Testing strategies
- `/validate` - Project compliance checks

## Skill Reference

This command loads: `.claude/skills/03-nexus/SKILL.md`
