# /sdk - Core SDK Quick Reference

## Purpose

Load the Core SDK skill for workflow patterns, node configuration, and runtime execution with the Kailash SDK.

## Quick Reference

| Command | Action |
|---------|--------|
| `/sdk` | Load Core SDK patterns and workflow basics |
| `/sdk workflow` | Show WorkflowBuilder patterns |
| `/sdk runtime` | Show runtime selection guidance |
| `/sdk nodes` | Show node configuration patterns |

## What You Get

- WorkflowBuilder patterns
- Node configuration (3-param pattern)
- Runtime execution (`runtime.execute(workflow.build())`)
- Connection patterns (4-param)
- Async vs sync runtime selection

## Quick Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("NodeType", "node_id", {"param": "value"})
workflow.add_connection("node1", "output", "node2", "input")
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Critical Rules

1. **ALWAYS** call `.build()` before execution
2. **ALWAYS** use `runtime.execute(workflow.build())` - never `workflow.execute(runtime)`
3. **ALWAYS** use absolute imports (never relative)
4. **ALWAYS** use string-based node registration

## Usage Examples

```bash
# Load Core SDK basics
/sdk

# Get workflow builder patterns
/sdk workflow

# Learn about runtime selection (async vs sync)
/sdk runtime

# See node configuration patterns
/sdk nodes
```

## Related Commands

- `/db` - DataFlow database operations
- `/api` - Nexus multi-channel deployment
- `/ai` - Kaizen AI agents
- `/test` - Testing strategies
- `/validate` - Gold standards compliance

## Skill Reference

This command loads: `.claude/skills/01-core-sdk/SKILL.md`
