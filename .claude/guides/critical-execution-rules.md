# Critical execution rules — the canonical call shapes

Extracted from `CLAUDE.md` per `cc-artifacts.md` Rule 4, which bars embedded
reference material there. The normative rules are `rules/patterns.md`;
this is the copy-paste surface.

```python
# DataFlow: Use Express API for simple CRUD (23x faster than workflows)
result = await db.express.create("User", {"id": "u1", "name": "Alice"})
user = await db.express.read("User", "u1")
users = await db.express.list("User", {"active": True}, limit=10)
await db.express.update("User", "u1", {"name": "Bob"})
count = await db.express.count("User", {"active": True})
# Sync variant: db.express_sync.create("User", {...})

# Workflow API: Only for multi-node operations
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Async workflows (Docker/FastAPI):
runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})

# String-based nodes only
workflow.add_node("NodeType", "node_id", {"param": "value"})

# Return structure is always (results, run_id)
```
