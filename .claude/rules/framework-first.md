# Framework-First: Engine Over Primitives

## Scope

These rules apply when writing application code using Kailash frameworks.

**Applies to**: `**/*.py`, `**/*.rs`

## The Three-Layer Model

Every Kailash framework provides three abstraction layers. Default to the highest layer (Engine) and drop to lower layers only when needed.

| Framework | Layer 1: Raw (Outside Kailash) | Layer 2: Primitives | Layer 3: Engine (Default) |
|-----------|-------------------------------|--------------------|--------------------------|
| **DataFlow** | Raw SQL, SQLAlchemy, Django ORM | `@db.model` + `WorkflowBuilder` + generated nodes | `DataFlowEngine.builder()` + `db.express` |
| **Nexus** | Raw FastAPI, Actix, axum | `ChannelManager`, manual channel setup | `Nexus()` zero-config, `NexusEngine.builder()` |
| **Kaizen** | Raw LLM API calls (OpenAI/Anthropic SDK) | `BaseAgent` + `Signature` (single agents) | `Delegate`, `GovernedSupervisor`, `Pipeline` patterns |
| **PACT** | Manual policy construction | Individual envelope builders | `GovernanceEngine` |

## MUST Rules

### 1. Engine-First for All Framework Operations

When using a Kailash framework, MUST start with the Engine layer. Drop to Primitives only when the Engine cannot express the required behavior.

```python
# DO: Engine layer (DataFlow Express for simple CRUD)
result = await db.express.create("User", {"name": "Alice", "email": "alice@example.com"})
users = await db.express.list("User", filter={"active": True})

# DO NOT: Primitives for simple CRUD (10x more code, same result)
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"name": "Alice", "email": "alice@example.com"})
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

```python
# DO: Engine layer (Delegate for autonomous agents)
from kaizen_agents import Delegate
delegate = Delegate(model=os.environ["LLM_MODEL"])
async for event in delegate.run("Analyze this data"):
    print(event)

# DO NOT: Primitives for autonomous agents (60+ lines of boilerplate)
class MyAgent(BaseAgent):
    class Sig(Signature):
        task: str = InputField(...)
        response: str = OutputField(...)
    # ... 50+ more lines of wiring
```

### 2. Consult Framework Specialist Before Dropping to Primitives

If the Engine layer does not fit your use case, consult the relevant framework specialist before writing Primitive-level code. The specialist may know an Engine-level pattern you missed.

### 3. Never Bypass Frameworks (Layer 1)

When a Kailash framework exists for your use case, MUST NOT write raw code that duplicates framework functionality. This is the existing "Framework-First" directive from CLAUDE.md — Layer 1 is always wrong when a framework exists.

## When to Use Primitives (Layer 2)

Primitives are the correct choice when:

- **Complex multi-step workflows** requiring explicit node wiring, conditional branching, or saga patterns
- **Custom transaction control** with savepoints or isolation levels that the engine doesn't expose
- **Custom agent extension** where the Delegate's TAOD loop doesn't fit your execution model
- **Novel patterns** the engine doesn't support yet — but file a feature request when this happens
- **Performance-critical paths** where workflow overhead matters and express doesn't cover the operation

## Detection Patterns

Code review SHOULD flag these patterns:

```python
# FLAG: WorkflowBuilder with single DataFlow CRUD node → suggest db.express
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"name": "Alice"})
# Suggest: await db.express.create("User", {"name": "Alice"})

# FLAG: BaseAgent subclass for simple autonomous task → suggest Delegate
class SimpleAgent(BaseAgent):
    # ... if this is just a TAOD loop with tools, use Delegate instead

# FLAG: Manual FastAPI route when Nexus handler covers it → suggest Nexus
@app.post("/api/workflow")
async def run_workflow():
    # Suggest: nexus.register("workflow", workflow.build())
```

## Cross-References

- `rules/agents.md` Rule 3 — Framework specialist required for framework work
- `rules/patterns.md` — Framework-specific execution patterns
- `skills/13-architecture-decisions/decide-framework.md` — Framework selection guide
