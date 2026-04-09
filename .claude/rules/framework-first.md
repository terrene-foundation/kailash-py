---
paths:
  - "**/*.py"
  - "**/*.rs"
---

# Framework-First: Use the Highest Abstraction Layer

## ABSOLUTE: Work-Domain → Framework Binding

| Work domain                                                           | MANDATORY framework       |
| --------------------------------------------------------------------- | ------------------------- |
| Workflow orchestration, node building, runtime, parameters            | **Core SDK** (foundation) |
| LLM, prompts, completions, embeddings, agents, RAG, multi-agent       | **Kaizen**                |
| DB schema, queries, CRUD, migrations, repositories, pools, cache      | **DataFlow**              |
| Data pipelines, ETL, fabric, feature stores                           | **DataFlow** (+ ML)       |
| HTTP API, REST, gateway, middleware, login, sessions, websockets      | **Nexus**                 |
| MCP servers, tools, resources, transports, exposing APIs as LLM tools | **MCP**                   |
| LLM fine-tuning, LoRA, DPO/SFT, model serving                         | **Align**                 |
| ML training, inference, drift, AutoML, feature stores                 | **ML**                    |
| Governance, RBAC, policy, access control, envelopes, audit            | **PACT**                  |

**Auth split**: Nexus owns authentication (login, sessions, JWT middleware). PACT owns authorization (RBAC, policy, role, permission, access control).

The framework specialists for each domain auto-invoke proactively (see their agent descriptions). This rule is the brief-form mandate; the live enforcement lives in the specialist agents and the framework skills, which load semantically on the work context.

**Why:** Rolling your own LLM service, custom HTTP gateway, or hand-rolled repository class is the #1 source of "we'll migrate later" debt that never migrates. The framework choice MUST be made before the first line of code.

---

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

## MUST: Specialist Consultation Before Dropping Below Engine Layer

This table extends the specialist delegation in `rules/agents.md` with pattern-level triggers. `agents.md` mandates specialist consultation for all framework work at any layer; this table adds a stricter gate for the specific patterns that signal a drop below the Engine layer.

Writing any of the following WITHOUT first consulting the named framework specialist is a `zero-tolerance.md` Rule 4 violation:

| Raw/Primitive pattern                                      | Specialist required |
| ---------------------------------------------------------- | ------------------- |
| Raw SQL strings (`SELECT`, `INSERT`, `ALTER`, `CREATE`)    | dataflow-specialist |
| Raw HTTP clients (`requests`, `httpx`, `fetch`, `reqwest`) | nexus-specialist    |
| Direct DB connections (`psycopg`, `aiosqlite.connect`)     | dataflow-specialist |
| Raw LLM API calls (`openai.chat.completions.create`)       | kaizen-specialist   |
| Direct MCP transport wiring                                | mcp-specialist      |
| Manual policy/envelope construction                        | pact-specialist     |

The specialist either confirms the framework cannot express the need (and the drop to primitives is documented), or redirects to the correct Engine/Primitive API.

```python
# DO — ask the specialist, get confirmation, document the exception
# (specialist confirmed: DataFlow auto-migrate cannot express partial index)
# Using raw migration as approved exception
conn.execute("CREATE INDEX CONCURRENTLY idx_active ON users (id) WHERE active = true")

# DO NOT — bypass without asking
conn.execute("INSERT INTO users (name, email) VALUES (%s, %s)", (name, email))
# ↑ DataFlow.express.create("User", {...}) handles this — no specialist needed, no raw SQL needed
```

**Why:** Without a mandatory specialist gate, agents default to the pattern they know (raw SQL, raw HTTP) rather than the framework pattern they should learn. The gate forces the question "does the framework already do this?" before any raw code is written. This is the single highest-leverage fix for the "bypass DataFlow and directly connect" failure mode.
