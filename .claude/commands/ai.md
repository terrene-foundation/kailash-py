# /ai - Kaizen Quick Reference

## Purpose

Load the Kaizen skill for production-ready AI agent implementation with signature-based programming and multi-agent coordination.

## Quick Reference

| Command | Action |
|---------|--------|
| `/ai` | Load Kaizen patterns and agent basics |
| `/ai agent` | Show Agent API patterns |
| `/ai signature` | Show signature-based programming |
| `/ai multi` | Show multi-agent coordination |

## What You Get

- Unified Agent API (v1.0.0)
- Signature-based programming
- Multi-agent coordination
- BaseAgent architecture
- Autonomous execution modes

## Quick Pattern

```python
from kaizen.api import Agent

# 2-line quickstart
agent = Agent(model="gpt-4")
result = await agent.run("What is IRP?")

# Autonomous mode with memory
agent = Agent(
    model="gpt-4",
    execution_mode="autonomous",  # TAOD loop
    memory="session",
    tool_access="constrained",
)
```

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Signatures** | Define input/output contracts |
| **Execution Modes** | supervised, autonomous, hybrid |
| **BaseAgent** | Inherit for custom agents |
| **AgentRegistry** | Scale to 100+ agents |
| **TAOD Loop** | Think, Act, Observe, Decide |

## Usage Examples

```bash
# Load Kaizen basics
/ai

# Get Agent API patterns
/ai agent

# Learn signature-based programming
/ai signature

# See multi-agent coordination
/ai multi
```

## Related Commands

- `/sdk` - Core SDK patterns
- `/db` - DataFlow database operations
- `/api` - Nexus multi-channel deployment
- `/test` - Testing strategies
- `/validate` - Gold standards compliance

## Skill Reference

This command loads: `.claude/skills/04-kaizen/SKILL.md`
