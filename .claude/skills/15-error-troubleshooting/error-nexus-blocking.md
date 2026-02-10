---
name: error-nexus-blocking
description: "Fix Nexus blocking and slow startup issues with DataFlow integration. Use when encountering 'Nexus blocking', 'Nexus slow startup', 'Nexus hangs', 'DataFlow Nexus integration slow', or startup delays."
---

# Error: Nexus Blocking / Slow Startup

Fix Nexus blocking and 5-30 second startup delays when integrating with DataFlow.

> **Skill Metadata**
> Category: `cross-cutting` (error-resolution)
> Priority: `HIGH` (Critical integration issue)
> SDK Version: `0.9.0+` (Nexus + DataFlow)
> Related Skills: [`dataflow-quickstart`](../../02-dataflow/dataflow-quickstart.md), [`nexus-quickstart`](../../03-nexus/nexus-quickstart.md)
> Related Subagents: `nexus-specialist` (integration debugging), `dataflow-specialist`

## The Problem

**Symptoms**:

- Nexus startup hangs or blocks indefinitely
- 5-10 second delay per DataFlow model
- Server never starts
- Blocking during initialization

**Root Cause**: Configuration conflict between Nexus auto-discovery and DataFlow model registration

## Quick Fix

### ❌ WRONG: Default Configuration (Blocks)

```python
from nexus import Nexus
from dataflow import DataFlow

# This will BLOCK or take 10-30 seconds!
app = Nexus()  # auto_discovery=True by default
db = DataFlow()  # Registers models with workflows

@db.model
class User:
    name: str

app.start()  # ✗ HANGS or very slow
```

### ✅ FIX: Critical Settings (<2s Startup)

```python
from nexus import Nexus
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder

# Step 1: Create Nexus FIRST with auto_discovery=False
app = Nexus(
    auto_discovery=False  # CRITICAL: Prevents blocking
)

# Step 2: Create DataFlow (v0.11.0 defaults work correctly)
db = DataFlow(
    "postgresql://user:pass@localhost/db",
    auto_migrate=True,  # Default - works in Docker/FastAPI via SyncDDLExecutor
)

# Step 3: Define models (now instant!)
@db.model
class User:
    name: str
    email: str

# Step 4: Register workflows manually
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
})

app.register("create_user", workflow.build())

# Fast startup: <2 seconds!
app.start()
```

## Why This Happens

1. `auto_discovery=True` → Nexus scans Python files
2. Importing DataFlow models → Triggers workflow execution
3. Each model registration → Runs `LocalRuntime.execute()` synchronously
4. Creates blocking loop → Prevents server startup

## What You Keep

With `auto_discovery=False` + DataFlow v0.11.0 defaults:

- All CRUD operations (11 nodes per model)
- Connection pooling, caching, metrics
- All Nexus channels (API, CLI, MCP)
- Automatic schema migration via SyncDDLExecutor
- Fast startup

## What You Lose

With `auto_discovery=False`:

- Auto-discovery of workflows (must register manually with `app.register()`)

## Related Patterns

- **Nexus basics**: [`nexus-quickstart`](../../03-nexus/nexus-quickstart.md)
- **DataFlow basics**: [`dataflow-quickstart`](../../02-dataflow/dataflow-quickstart.md)
- **Integration guide**: [`dataflow-nexus-integration`](../integrations/dataflow-nexus-integration.md)

## When to Escalate to Subagent

Use `nexus-specialist` subagent when:

- Still experiencing blocking after fix
- Need full-feature configuration guidance
- Complex multi-framework integration
- Production deployment planning

## Documentation References

### Primary Sources

- **Nexus Specialist**: [`.claude/agents/frameworks/nexus-specialist.md` (lines 320-386)](../../../../.claude/agents/frameworks/nexus-specialist.md#L320-L386)
- **DataFlow Specialist**: [`.claude/agents/frameworks/dataflow-specialist.md` (lines 13-25)](../../../../.claude/agents/frameworks/dataflow-specialist.md#L13-L25)
- **Integration Guide**: [`sdk-users/guides/dataflow-nexus-integration.md`](../../../../sdk-users/guides/dataflow-nexus-integration.md)

### Related Documentation

- **Blocking Analysis**: [`sdk-users/apps/dataflow/docs/integration/nexus-blocking-issue-analysis.md`](../../../../sdk-users/apps/dataflow/docs/integration/nexus-blocking-issue-analysis.md)
- **Working Examples**: [`sdk-users/apps/nexus/examples/dataflow-integration/`](../../../../sdk-users/apps/nexus/examples/dataflow-integration/)

## Quick Tips

- 💡 **Critical setting**: `auto_discovery=False` when using DataFlow with Nexus
- 💡 **Order matters**: Create Nexus FIRST, then DataFlow
- 💡 **Manual registration**: Register workflows explicitly with `app.register()`
- 💡 **DataFlow v0.11.0**: `auto_migrate=True` (default) works correctly in Docker/FastAPI

<!-- Trigger Keywords: Nexus blocking, Nexus slow startup, Nexus hangs, DataFlow Nexus integration slow, startup delay, Nexus initialization slow, blocking on startup, slow Nexus, integration blocking -->
