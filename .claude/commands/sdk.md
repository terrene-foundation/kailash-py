# /sdk - Core SDK Quick Reference

## Purpose

Load the Kailash Core SDK skill for workflow patterns, node configuration, and runtime execution.

## Step 0: Verify Project Uses Kailash

Before loading SDK patterns, check that this project uses Kailash:

- Look for `kailash` in `requirements.txt`, `pyproject.toml`, `setup.py`, `Cargo.toml`
- Look for `from kailash` / `import kailash` in source files

If not found, inform the user: "This project doesn't appear to use Kailash SDK. These patterns may not apply. Continue anyway?"

## Quick Reference

| Command         | Action                                     |
| --------------- | ------------------------------------------ |
| `/sdk`          | Load Core SDK patterns and workflow basics |
| `/sdk workflow` | Show WorkflowBuilder patterns              |
| `/sdk runtime`  | Show runtime selection guidance            |
| `/sdk nodes`    | Show node configuration patterns           |

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

## Agent Teams

When working with Core SDK, deploy:

- **pattern-expert** — Workflow patterns, node configuration, cyclic patterns
- **sdk-navigator** — Find existing patterns and documentation

## Related Commands

- `/db` - DataFlow database operations
- `/api` - Nexus multi-channel deployment
- `/ai` - Kaizen AI agents
- `/test` - Testing strategies
- `/validate` - Project compliance checks

## Skill Reference

This command loads: `.claude/skills/01-core-sdk/SKILL.md`
