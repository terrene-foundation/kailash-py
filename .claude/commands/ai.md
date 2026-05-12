# /ai - Kaizen Quick Reference

## Purpose

Load the Kaizen skill for production-ready AI agent implementation with signature-based programming and multi-agent coordination.

## Step 0: Verify Project Uses Kailash Kaizen

Before loading Kaizen patterns, check that this project uses Kailash Kaizen:

- Look for `kailash-kaizen` or `kaizen` in `requirements.txt`, `pyproject.toml`
- Look for `from kaizen` / `import kaizen` in source files

If not found, inform the user: "This project doesn't appear to use Kailash Kaizen. These patterns may not apply. Continue anyway?"

## Quick Reference

| Command         | Action                                |
| --------------- | ------------------------------------- |
| `/ai`           | Load Kaizen patterns and agent basics |
| `/ai agent`     | Show Agent API patterns               |
| `/ai signature` | Show signature-based programming      |
| `/ai multi`     | Show multi-agent coordination         |

## What You Get

- Unified Agent API (v1.0.0)
- Signature-based programming
- Multi-agent coordination
- BaseAgent architecture
- Autonomous execution modes

## Quick Pattern

```python
import os
from kaizen.api import Agent

# 2-line quickstart — model from .env, NEVER hardcoded
agent = Agent(model=os.environ["KAIZEN_MODEL"])
result = await agent.run("What is IRP?")

# Autonomous mode with memory
agent = Agent(
    model=os.environ["KAIZEN_MODEL"],
    execution_mode="autonomous",  # TAOD loop
    memory="session",
    tool_access="constrained",
)
```

## Key Concepts

| Concept             | Description                    |
| ------------------- | ------------------------------ |
| **Signatures**      | Define input/output contracts  |
| **Execution Modes** | supervised, autonomous, hybrid |
| **BaseAgent**       | Inherit for custom agents      |
| **AgentRegistry**   | Scale to 100+ agents           |
| **TAOD Loop**       | Think, Act, Observe, Decide    |

## Agent Teams

When working with Kaizen, deploy:

- **kaizen-specialist** — Signatures, multi-agent coordination, BaseAgent architecture
- **testing-specialist** — Agent testing patterns (NO MOCKING)

## Related Commands

- `/sdk` - Core SDK patterns
- `/db` - DataFlow database operations
- `/api` - Nexus multi-channel deployment
- `/test` - Testing strategies
- `/validate` - Project compliance checks

## Skill Reference

This command loads: `.claude/skills/04-kaizen/SKILL.md`
