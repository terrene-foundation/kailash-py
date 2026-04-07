# Framework-First: Use the Highest Abstraction Layer

Default to Engines. Drop to Primitives only when Engines can't express the behavior. Never use Raw.

## Four-Layer Hierarchy

```
Entrypoints  →  Applications (aegis, aether), CLI (cli-rs), others (kz-engage)
Engines      →  DataFlowEngine, NexusEngine, DelegateEngine/SupervisorAgent, GovernanceEngine
Primitives   →  DataFlow, @db.model, Nexus(), BaseAgent, Signature, envelopes
Specs        →  CARE, EATP, CO, COC, PACT (standards/protocols/methodology)
```

Specs define → Primitives implement building blocks → Engines compose into opinionated frameworks → Entrypoints are products users interact with.

| Framework    | Raw (never ❌)      | Primitives                                          | Engine (default ✅)                                                     | Entrypoints              |
| ------------ | ------------------- | --------------------------------------------------- | ----------------------------------------------------------------------- | ------------------------ |
| **DataFlow** | Raw SQL, SQLAlchemy | `DataFlow`, `@db.model`, `db.express`, nodes        | `DataFlowEngine.builder()` (validation, classification, query tracking) | aegis, aether, kz-engage |
| **Nexus**    | Raw HTTP frameworks | `Nexus()`, handlers, channels                       | `NexusEngine` (middleware stack, auth, K8s)                             | aegis, aether            |
| **Kaizen**   | Raw LLM API calls   | `BaseAgent`, `Signature`                            | `DelegateEngine`, `SupervisorAgent`                                     | kaizen-cli-rs            |
| **PACT**     | Manual policy       | Envelopes, D/T/R addressing                         | `GovernanceEngine` (thread-safe, fail-closed)                           | aegis                    |
| **ML**       | Raw sklearn/torch   | `FeatureStore`, `ModelRegistry`, `TrainingPipeline` | `AutoMLEngine`, `InferenceServer` (ONNX, drift, caching)                | aegis, aether            |
| **Align**    | Raw TRL/PEFT        | `AlignmentConfig`, `AlignmentPipeline`              | `align.train()`, `align.deploy()` (GGUF, Ollama, vLLM)                  | —                        |

**Note**: `db.express` is a primitive convenience for lightweight CRUD (~23x faster by bypassing workflow). `DataFlowEngine` wraps `DataFlow` with enterprise features (validation, classification, query engine, retention).

## DO / DO NOT

```python
# ✅ Engine layer (DataFlowEngine for production)
engine = DataFlowEngine.builder("postgresql://...")
    .slow_query_threshold(Duration.from_secs(1))
    .build()

# ✅ Primitive convenience (db.express for simple CRUD)
result = await db.express.create("User", {"name": "Alice"})

# ❌ Raw primitives for what Engine handles
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"name": "Alice"})
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

```python
# ✅ Engine layer (DelegateEngine/SupervisorAgent for agents)
delegate = Delegate(model=os.environ["LLM_MODEL"])
async for event in delegate.run("Analyze this data"): ...

# ❌ Primitives for simple autonomous task
class MyAgent(BaseAgent): ...  # 60+ lines boilerplate
```

## When Primitives Are Correct

- Complex multi-step workflows (node wiring, branching, sagas)
- Custom transaction control (savepoints, isolation levels)
- Custom agent execution model (DelegateEngine's TAOD loop doesn't fit)
- Performance-critical paths where workflow overhead matters
- Simple CRUD via `db.express` (designed as primitive convenience)

**Always consult the framework specialist before dropping to Primitives.**

## Raw Is Always Wrong

When a Kailash framework exists for your use case, MUST NOT write raw code that duplicates framework functionality.

**Why:** Raw code bypasses framework guarantees (validation, audit logging, connection pooling, dialect portability), creating maintenance debt that grows with every framework upgrade.
