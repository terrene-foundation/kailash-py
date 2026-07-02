---
name: framework-first
description: "Framework-first depth: four-layer hierarchy, Engine/Primitive/Raw, specialist-consultation lookup table, version-stable integration, Rust-bindings framing. Use when choosing a Kailash layer."
---

# Framework-First — Depth Reference

The always-on mandate lives in `rules/framework-first.md` (the work-domain →
framework binding table + "Raw Is Always Wrong"). This skill carries the
on-demand depth: how the layers compose, the concrete DO / DO-NOT patterns, the
specialist-consultation pattern-lookup table, the version-stable
external-integration discipline, and the framing for Rust-runtime (bindings)
consumers.

## Four-Layer Hierarchy

```
Entrypoints  →  Applications (app-a, app-b), CLI (cli-app), others (app-c)
Engines      →  DataFlowEngine, NexusEngine, DelegateEngine/SupervisorAgent, GovernanceEngine
Primitives   →  DataFlow, @db.model, Nexus(), BaseAgent, Signature, envelopes
Specs        →  CARE, EATP, CO, COC, PACT (standards/protocols/methodology)
```

Specs define → Primitives implement building blocks → Engines compose into opinionated frameworks → Entrypoints are products users interact with.

| Framework    | Raw (never ❌)      | Primitives                                          | Engine (default ✅)                                                     | Entrypoints         |
| ------------ | ------------------- | --------------------------------------------------- | ----------------------------------------------------------------------- | ------------------- |
| **DataFlow** | Raw SQL, SQLAlchemy | `DataFlow`, `@db.model`, `db.express`, nodes        | `DataFlowEngine.builder()` (validation, classification, query tracking) | app-a, app-b, app-c |
| **Nexus**    | Raw HTTP frameworks | `Nexus()`, handlers, channels                       | `NexusEngine` (middleware stack, auth, K8s)                             | app-a, app-b        |
| **Kaizen**   | Raw LLM API calls   | `BaseAgent`, `Signature`                            | `DelegateEngine`, `SupervisorAgent`                                     | cli-app             |
| **PACT**     | Manual policy       | Envelopes, D/T/R addressing                         | `GovernanceEngine` (thread-safe, fail-closed)                           | app-a               |
| **ML**       | Raw sklearn/torch   | `FeatureStore`, `ModelRegistry`, `TrainingPipeline` | `AutoMLEngine`, `InferenceServer` (ONNX, drift, caching)                | app-a, app-b        |
| **Align**    | Raw TRL/PEFT        | `AlignmentConfig`, `AlignmentPipeline`              | `align.train()`, `align.deploy()` (GGUF, Ollama, vLLM)                  | —                   |

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

## MUST: Specialist Consultation Before Dropping Below Engine Layer

This table extends the specialist delegation in `rules/agents.md` with pattern-level triggers. `agents.md` mandates specialist consultation for all framework work at any layer (this is the always-on mandate); this table adds a stricter gate for the specific patterns that signal a drop below the Engine layer.

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

## Framework Version-Stable Integration — Drive The Data, Not The Dispatch

When integrating with an external framework's lifecycle hook (FastAPI / Starlette lifespan, aiohttp on_startup, Axum layer, Rails initializer, Rack middleware), if the framework exposes BOTH (a) a dispatch method name AND (b) a list/dict of registered handlers, the data structure is the stable surface across versions. Dispatch method names drift — underscore-prefix transitions, removal, renames — the registration list is what the framework's own internal dispatcher iterates.

Integrations MUST iterate the registered-handlers data structure, NOT call the dispatch method by name.

```python
# DO — iterate the on_startup / on_shutdown list (what FastAPI's _DefaultLifespan does internally)
@asynccontextmanager
async def lifespan(app):
    for handler in app.router.on_startup:
        await handler() if inspect.iscoroutinefunction(handler) else handler()
    yield
    for handler in app.router.on_shutdown:
        await handler() if inspect.iscoroutinefunction(handler) else handler()

# DO NOT — call the dispatch method by name
@asynccontextmanager
async def lifespan(app):
    await app.router.startup()   # AttributeError on builds where only _startup exists
    yield
    await app.router.shutdown()  # same drift hazard
```

```rust
// DO — iterate registered hooks, not dispatch-by-name
for hook in &app.startup_hooks { (hook)().await?; }

// DO NOT — call startup() by name when the framework also exposes startup_hooks
app.startup().await?;   // renamed to _startup in the next major; integration breaks
```

**BLOCKED rationalizations:**

- "The method name has been stable for years"
- "The framework's docs show the method-name form"
- "We'll pin the framework version to avoid the drift"
- "The list form is an internal detail, we should use the public API"
- "If the method is renamed, we'll rename our call"

**Why:** Framework-integration code runs in every production instance; a single `AttributeError` on a renamed dispatch method crashes every service at lifespan boot with zero type-checker signal. The registered-handlers list is the data the framework's OWN internal dispatcher iterates — it cannot be removed without breaking the framework's own hooks, so it is strictly more stable than any dispatch method name. "Pin the framework version" is an anti-pattern: it creates a treadmill where every dependency upgrade re-triggers the same failure mode. Drive the data; don't call the dispatch.

Origin: 2026-04-19 — Nexus called `app.router.startup()` / `.shutdown()` as if stable across FastAPI versions; some production FastAPI builds exposed only `_startup`; every service crashed at uvicorn lifespan. Fix: iterate the `on_startup` / `on_shutdown` lists directly (kailash-py issue #531 / PR #533, fixed in kailash-nexus 2.1.1).

## For Rust-Runtime (Bindings) Consumers

On the Rust runtime (kailash-rs), the bindings give Python a Pythonic API that maps onto the Rust runtime under the hood. **Your code is Python; the kailash-rs runtime executes underneath. You never write Rust.** For canonical API paths in your project, consult the relevant framework specialist (dataflow-specialist, nexus-specialist, kaizen-specialist, mcp-specialist, pact-specialist, ml-specialist) — this skill intentionally avoids listing specific paths to prevent drift.

The Raw anti-patterns to avoid on the bindings runtime:

| Framework    | Raw (never) — Python anti-patterns            | Primitives (binding-exposed)                        | Engine (default)                                                        |
| ------------ | --------------------------------------------- | --------------------------------------------------- | ----------------------------------------------------------------------- |
| **DataFlow** | `psycopg`, `sqlalchemy.text`, raw SQL strings | `DataFlow`, `@db.model`, `db.express`, nodes        | `DataFlowEngine.builder()` (validation, classification, query tracking) |
| **Nexus**    | Raw HTTP frameworks, manual route handlers    | `Nexus()`, handlers, channels                       | `NexusEngine` (middleware stack, auth, K8s)                             |
| **Kaizen**   | `openai`, `anthropic` SDK calls               | `BaseAgent`, `Signature`                            | `DelegateEngine`, `SupervisorAgent`                                     |
| **PACT**     | Manual policy strings                         | Envelopes, D/T/R addressing                         | `GovernanceEngine` (thread-safe, fail-closed)                           |
| **ML**       | `sklearn`, `numpy`, `pandas` directly         | `FeatureStore`, `ModelRegistry`, `TrainingPipeline` | `AutoMLEngine`, `InferenceServer` (ONNX, drift, caching)                |
| **Align**    | `transformers`, `peft`, `trl` directly        | `AlignmentConfig`, `AlignmentPipeline`              | `align.train()`, `align.deploy()` (GGUF, Ollama, vLLM)                  |

```python
# DO: Engine layer (AutoMLEngine for end-to-end ML)
engine = AutoMLEngine(...)
engine.fit(X_train, y_train)
predictions = engine.predict(X_test)

# DO NOT: Manual fit-predict chain when AutoMLEngine handles it
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X_train)
lr = LogisticRegression()
lr.fit(X_scaled, y_train)
predictions = lr.predict(scaler.transform(X_test))
```
