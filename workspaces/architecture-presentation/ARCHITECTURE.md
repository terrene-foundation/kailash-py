# Kailash Python SDK — Ecosystem Architecture

**Audience:** Architects & Product Owners
**Versions referenced:** kailash 2.20.3 · dataflow 2.x · nexus 2.x · kaizen 2.x · ml 1.x · align 0.x · mcp 0.x · pact 0.x (see §13 stability table)
**License:** Apache-2.0 across every package · **Steward:** Terrene Foundation (Singapore CLG) · **Spec basis:** CARE / EATP / PACT (CC BY 4.0)

---

## 1. One-Paragraph Summary

Kailash is an open-source platform for building **enterprise-grade AI systems**. It is one **Core SDK** plus a **suite of seven modular companion packages** — install only what you need. Every package composes on a single workflow engine, so a request entering via REST, CLI, or an LLM tool-call executes the same code. Two things are wired-in rather than bolted on: **trust** (every governed action is cryptographically signed and audited) and **multi-channel deployment** (write once, expose as REST + CLI + MCP + WebSocket). It is designed to be adopted **incrementally** alongside your existing stack — not as a rip-and-replace.

> **Maturity in one line:** Core SDK and four companion packages (DataFlow, Nexus, Kaizen, ML) are at 2.x and stable. Three (MCP, Align, PACT) are pre-1.0 and evolving. Every load-bearing claim in this deck cites a file/test/commit you can verify in the public repo (see §13.1). External attestations (third-party security audit, named customer references, SBOM in CI) are on the published roadmap (§13.3).

---

## 2. Hello World (skip if non-technical)

```python
# pip install kailash
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

wf = WorkflowBuilder()
wf.add_node("PythonCodeNode", "greet",
            {"code": "result = {'msg': f'hello, {name}'}", "inputs": {"name": "world"}})

results, run_id = LocalRuntime().execute(wf.build())
print(results["greet"])   # → {'msg': 'hello, world'}
```

That is the entire platform on Day 1 — no DB, no server, no LLM key. Companion packages get added only when you hit a specific pain.

---

## 3. The Big Picture (Layered View)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ACCESS CHANNELS — how the outside world reaches a Kailash workflow      │
│   REST API · CLI · MCP server · WebSocket · Webhooks · Scheduler         │
│           one registration → all channels (via Nexus)                    │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  7 COMPANION PACKAGES — modular, opt-in. Adopt what you need.            │
│                                                                          │
│  Domain                       Package      Stability                     │
│  ──────────────────────────   ─────────    ─────────                     │
│  Multi-channel deployment     Nexus        2.x · Stable                  │
│  Databases (zero-config)      DataFlow     2.x · Stable                  │
│  AI agents (signature DSL)    Kaizen       2.x · Stable                  │
│  ML lifecycle                 ML           1.x · Stable                  │
│  Tools for LLM clients        MCP          0.x · Evolving                │
│  LLM fine-tuning + serving    Align        0.x · Evolving                │
│  Org. governance (RBAC++)     PACT         0.x · Evolving                │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  CORE SDK — workflow engine (the only mandatory dependency)              │
│                                                                          │
│   WorkflowBuilder ── builds ──▶ Workflow (DAG of Nodes)                  │
│                                       │ executed by                      │
│                                       ▼                                  │
│   8 runtime variants:                                                    │
│   LocalRT · AsyncLocalRT · ParallelRT · DistributedRT ·                  │
│   DurableRT · AccessControlledRT · DockerRT · DispatcherRT               │
│                                                                          │
│   110+ built-in nodes across 21 categories (see §3.1).                   │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  CROSS-CUTTING PLANES — wrap every framework, every node, every request  │
│   TRUST PLANE        ·  OBSERVABILITY PLANE  ·  SECURITY PLANE           │
│   Ed25519 chains        OTEL traces             param. queries primary   │
│   posture L1–L5         Prometheus metrics      classification +         │
│   EATP audit log        structured logs         redaction + LLM defense  │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  INFRASTRUCTURE LAYER — the "boring but essential" production guts       │
│  Dialect-portable SQL · Task queue · Event store · Checkpoint manager    │
│  Idempotency store · Dead-letter queue · Saga coordinator                │
│  Leader election · Circuit breaker · Rate limiter · Connection pools     │
└──────────────────────────────────────────────────────────────────────────┘
```

The shape is **1 Core + 7 companion packages + 3 cross-cutting planes + 1 infra layer**. Most teams start with Core + one package and grow.

### 3.1 — What the 110+ nodes actually do

A node is a typed, registered unit of work the runtime can schedule. The 21 categories cover (paraphrased): **HTTP / API** (request, REST, GraphQL), **Data** (SQL read/write, JSON/CSV/Parquet, streaming, ETL), **Transform** (filter, map, aggregate, join, validate), **Logic** (switch, merge, conditional, cycle), **Code** (Python expression, sandboxed exec), **AI / LLM** (LLM call, embedding, RAG), **MCP** (tool, resource, prompt), **Cache** (Redis, in-memory, TTL), **Auth** (JWT, OAuth, RBAC), **Admin** (user/tenant management), **Compliance** (audit emit, classification check), **Monitoring** (metric, alert, watchdog), **Security** (validator, sanitiser, secret read), **Enterprise** (saga step, idempotency guard), **Edge** (device-local execution), **System / testing / mixins** (test fixtures, common helpers). Full catalogue: `src/kailash/nodes/`.

---

## 4. Where Kailash Sits In Your Existing Stack

Kailash is **not** a replacement for your IdP, your SIEM, your API gateway, or your CMDB. It plugs in:

```
                    ┌──────────────┐
   internet ──────▶ │ API gateway  │ ──▶ (your existing Apigee / Kong / etc.)
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │   Kailash    │ ◀── OIDC / SAML federation from your IdP
                    │     app      │      (Okta · Entra · Auth0 · KeyCloak)
                    │ (Nexus host) │
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   ┌─────────┐       ┌──────────┐      ┌────────────┐
   │ your    │       │  your    │      │ your CMDB  │
   │ SIEM    │ ◀──── │  audit   │      │ (workflow  │
   │(Splunk/ │  EATP │  store   │      │  ID as CI) │
   │Sentinel)│       │ (signed) │      └────────────┘
   └─────────┘       └──────────┘
```

- **IdP federation** — Nexus accepts JWT/OIDC; CI-tested today against Auth0 and KeyCloak; Okta/Entra are interface-compatible (JWT-claim shape) but not currently exercised in CI.
- **SIEM export** — EATP audit records export to any JSON-lines sink (Splunk HEC, Sentinel, file → forwarder).
- **API gateway** — Kailash apps deploy behind your existing gateway; no requirement to replace it.
- **CMDB** — workflow names + run_ids are stable identifiers you can register as CIs.

---

## 5. The Idea That Holds It Together

Every companion package ultimately **builds a `Workflow` and hands it to a `Runtime`**.

```
   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ DataFlow │  │   Nexus  │  │  Kaizen  │  │   PACT   │
   │ models   │  │ channels │  │  agents  │  │ envelopes│
   └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
        │ generate    │ register    │ wrap as     │ guard
        │ nodes for   │ for multi-  │ workflow    │ every
        │ a workflow  │ channel exec│ steps       │ execution
        └─────────────┴──────┬──────┴─────────────┘
                             ▼
                     Workflow (DAG)
                             │
                             ▼
                     Runtime.execute()
                             │
                             ▼
                  (results, run_id, audit)
```

**For a PO:** we build one workflow and decorate it; we don't build four parallel systems.
**For an architect:** the `WorkflowBuilder → Runtime` contract is the integration point. Companion packages produce or consume that contract; you can write your own.

---

## 6. Request Lifecycle (One Call End-to-End)

A workflow can be entered from any of six surfaces — REST, CLI, MCP, WebSocket, webhook, scheduler.

```
 1. Surface (REST/CLI/MCP/WS/webhook/scheduler) → request envelope
 2. Nexus              → AuthN: validate JWT/session/API key from your IdP
 3. PACT (if enabled)  → AuthZ: does this principal's envelope permit
                          this action under its clearance? Fail-closed.
 4. Trust Plane        → Open signed audit span. Stamp request with posture
                          (assigned by PACT, never claimed by caller).
 5. Runtime            → Dispatch workflow; load checkpoint if resuming.
 6. Nodes execute      → Each node validates inputs, applies classification/
                          redaction, emits metrics + OTEL spans.
 7. Cross-cutting      → Trust signs each step. Security redacts PII before
                          any return path. Observability emits structured
                          spans correlated by run_id.
 8. Response           → Marshalled per channel (JSON / table / ToolResult /
                          event frame). Audit span closes; signed record
                          persists to event store.
```

### Trust Posture (L1–L5) — quick definition

| Level | Meaning                              | Typical use                 |
| ----- | ------------------------------------ | --------------------------- |
| L1    | Unverified caller                    | Anonymous read              |
| L2    | Authenticated, no delegation         | Self-service user actions   |
| L3    | Authenticated + role-attested        | Most enterprise CRUD        |
| L4    | Delegated with signed envelope       | Agent acting for user       |
| L5    | Fully delegated, capability-attested | Autonomous agent under PACT |

Posture is assigned by PACT from the caller's signed context. Callers cannot self-promote.

---

## 7. Deployment Topology (Progressive Scaling)

```
LEVEL 0 — Developer                                         (laptop / CI)
┌────────────────────────────────────────────────────────────────────┐
│ python script.py                                                   │
│   └─ LocalRuntime · SQLite · in-process queue · file event store   │
│ Zero external dependencies. Same workflow code as production.      │
└────────────────────────────────────────────────────────────────────┘

LEVEL 1 — Single-worker production                          (one VM/pod)
┌────────────────────────────────────────────────────────────────────┐
│ uvicorn nexus_app:app                                              │
│   ├─ AsyncLocalRuntime · PostgreSQL · SQL task queue               │
│   ├─ Prometheus /metrics (BYO collector) · OTLP traces (BYO)       │
│   └─ JWT/RBAC enforced on every request                            │
└────────────────────────────────────────────────────────────────────┘

LEVEL 2 — Multi-worker production                          (HA cluster)
┌────────────────────────────────────────────────────────────────────┐
│  workers (autoscaled via queue-depth HPA signal)                   │
│         │                                                          │
│  ───── separated data planes (see §7.1) ──────────────────────     │
│  PostgreSQL #1  → task queue (SKIP LOCKED, autovacuum-tuned)       │
│  PostgreSQL #2  → event store + checkpoint + idempotency           │
│  Redis HA       → circuit breaker + saga state + rate limiter      │
│                                                                    │
│  Leader election (RAFT) — embedded pysyncobj today (see §7.5       │
│        risk note); operator chart for K8s; etcd backend in 2.21    │
│  Dead-letter queue + audit log (signed, chained, externally        │
│        anchorable to transparency log / RFC-3161 TSA)              │
└────────────────────────────────────────────────────────────────────┘
```

### 7.1 — Why the data planes are split

Production splits the role: **(a)** a high-write task-queue DB sized for `SKIP LOCKED` throughput and aggressive autovacuum; **(b)** an event-store DB for append-mostly audit + checkpoint state with WAL archival. This avoids head-of-line blocking and lets WAL-archival cadence match audit retention.

### 7.2 — Capacity reference (internal load test, not a customer benchmark)

| Topology                                                           | Sustained workflow throughput |
| ------------------------------------------------------------------ | ----------------------------- |
| Level 1 — 1 worker, 8 vCPU / 16 GB, PG 15 colocated                | ~200–400 workflows/sec        |
| Level 2 — 4 workers + PG 15 (16 vCPU) + pgBouncer transaction-pool | ~1k–2k workflows/sec          |

Hardware spec, workload mix, and the runner scripts live in the public test harness under `tests/benchmarks/` and `tests/performance/`; the numbers above are reproducible from a clean checkout against the named hardware. Above ~2k workflows/sec the Postgres `SKIP LOCKED` dequeue path becomes the dominant ceiling (typical for a single queue table under realistic row sizes); the 2026-Q3 Redis Streams queue backend lifts the ceiling. A customer-validated benchmark is on the Q4 roadmap. **Do not treat these as procurement-grade benchmarks** — they are internal-test order-of-magnitude reference points.

### 7.2.1 — Cost reference (illustrative cloud list-price, US region)

| Topology                                                          | Approx. monthly cost (managed cloud, on-demand) |
| ----------------------------------------------------------------- | ----------------------------------------------- |
| Level 1 — 1 worker + small managed Postgres (~db.t3.medium-class) | ~$150–$300                                      |
| Level 2 — 4 workers + 2 managed Postgres (HA) + small Redis (HA)  | ~$1.5k–$4k                                      |

Costs scale linearly with worker count and Postgres tier; reserved-instance pricing typically halves the figures. Order-of-magnitude reference for procurement scoping; use your own cloud calculator for the actual deployment.

### 7.2.2 — Connection-pool sizing (Level 2 reference)

Per-worker async pool size ≈ `concurrent_workflows_per_worker × 2`. With 4 workers × pool 25 → 100 client connections to the queue DB. With PgBouncer in transaction-pool mode at the queue DB front, Postgres `max_connections` ≥ ~120 (100 client + ~20 admin overhead). The event-store DB sees roughly one-third of that traffic. Reserve ≥30% of each Postgres `max_connections` for admin/monitoring/migration tools.

### 7.2.3 — Autoscaling signal (Level 2 reference)

Horizontal scaling on Kubernetes uses an HPA whose primary signal is **queue depth per worker** (custom metric exported from the Prometheus `/metrics` endpoint), with CPU as a secondary tiebreaker. Reference HPA values: min=2, max=20, target queue-depth-per-worker=50, scale-up cooldown=60s, scale-down cooldown=300s. Cold-start latency on a warm container image is ~3–5s (Python import + DB pool acquire); pre-warm one extra worker if your SLO is sub-second.

### 7.3 — DR / RTO / RPO

Kailash inherits the durability of the underlying Postgres/Redis topology. Reference targets for a Level-2 deployment with streaming replicas + WAL archival: **RPO ≤ 60s · RTO ≤ 15 min**. Suggested WAL retention is **≥7 days** (covers a weekend incident window) and PITR snapshot cadence **≥daily** (covers an accidental-truncation window). Restore-test cadence (quarterly game-day, validated against a non-prod replica) is the deploying team's responsibility; Kailash ships the durable primitives (idempotency keys, signed checkpoints, dead-letter queue) that make those targets achievable.

### 7.4 — Failover protocol (in one paragraph)

**Worker dies:** in-flight workflow steps idempotent by run_id+step_id; a sibling worker dequeues the un-completed step on lease expiry (default 30s) and re-applies the idempotency guard. **Leader dies:** RAFT term advance; the next leader resumes saga coordination from the durable saga state in Redis; in-flight compensation steps are idempotent. **Postgres fails over:** workers reconnect via PgBouncer; queued steps survive (WAL-archived); audit chain replays from event store on restart with no signature regeneration.

### 7.5 — Honest operational risks

- **Leader-election library (`pysyncobj`) has a small maintainer base.** This is load-bearing; an etcd-backed alternative ships in 2.21 to remove the single-library dependency.
- **Capacity numbers above are internal load tests**, not customer-validated; treat as order-of-magnitude only.
- **K8s packaging** today is Helm + an operator chart for leader election; multi-cloud Terraform modules are not yet published.

### 7.6 — Schema migration during live deploy

Expand-contract via Alembic; the runtime tolerates mixed-schema workers during rolling deploy (every node validates its inputs before reading rows, so a worker running the prior schema does not crash on a newly-added nullable column).

### 7.7 — Time-to-first-business-outcome (typical pilot)

| Milestone                                                 | Typical week |
| --------------------------------------------------------- | ------------ |
| First workflow running locally (Level 0)                  | Week 1       |
| First multi-channel deployment (Level 1, behind your IdP) | Week 2       |
| First signed audit pack exported to your SIEM             | Week 3       |
| First SOC2/HIPAA control mapping for a regulator demo     | Week 4       |
| First Kaizen agent (with PACT envelope) live              | Week 6       |
| Level-2 cluster bring-up + game-day DR drill              | Week 8       |

---

## 8. Cross-Cutting Planes (the "always on" wrappers)

### 8.1 — Trust Plane

Every governed action is signed with **Ed25519** and chained (Genesis → Delegation → Voucher records). Audit log is hash-chained and externally anchorable to RFC-3161 or a transparency-log endpoint of your choice. Byte-stable across the Python and Rust SDK implementations — verified by a cross-SDK conformance harness in CI.

**What is independently verifiable today:** code paths exist in the public repo; cross-SDK byte-stable test harness produces identical hashes for identical inputs; internal hardening cycles (4 rounds) have closed 72 findings on the trust + auth + audit boundary with the disposition records in the repo journal.
**What we do not yet claim:** external third-party cryptographic audit. A Trail-of-Bits-class audit is on the roadmap before PACT 1.0.

### 8.2 — Observability Plane

- **Metrics:** counter / gauge / histogram with bounded cardinality. Optional Prometheus bridge. **No telemetry phones home** — Kailash never calls out unless you configure a collector endpoint.
- **Tracing:** OpenTelemetry spans per node, correlated by run_id. BYO collector. Example Grafana dashboards + Prometheus alert rules ship under `deploy/observability/`.
- **Logging:** structured JSON, redaction-aware (classified fields scrubbed before write).

### 8.3 — Security Plane

- **Parameterized queries are the primary SQL-injection defense everywhere.** Inputs route through driver placeholders (`?` / `$N` / `%s`) — never string concatenation.
- **Sentinel-token sanitizer is defense-in-depth, not primary defense.** It tokenizes attack signatures (`STATEMENT_BLOCKED`, `DROP_TABLE`) on stringly-typed display paths so post-incident grep of audit logs surfaces attempted attacks.
- **Classification at the model:** `@classify(field, PII, REDACT)` enforced on every return path. A CI lint flags any scalar column lacking an explicit classification (no silent unclassified PII).
- **Multi-tenancy isolation:** **row-level** (`WHERE tenant_id = ?` enforced by the DataFlow query rewriter) is the default; schema-per-tenant and database-per-tenant deployments are supported when stricter isolation is required (cell-based architectures).
- **Secrets** pluggable (env, encrypted vault, cloud KMS); **never logged**.
- **Checkpoint/event store encryption:** for any workflow whose models contain classified fields, checkpoint payloads are encrypted at rest with a per-tenant DEK by default. Per-tenant DEK rotation defaults to **90 days** with envelope-key (KEK) rotation **annually**; rotation is online (existing rows decrypt with the old DEK until re-written). When the KMS is unreachable at decrypt time the runtime **fails closed** (the workflow step retries with backoff; it does not proceed with unprotected payloads). A `KAILASH_CHECKPOINT_PLAINTEXT=1` opt-out exists for explicitly non-regulated workloads only — turning it on is logged and surfaced in the audit chain. Existing encrypted checkpoints are migrated lazily (re-encrypted on next write) when the encryption mode changes.
- **Key management:** Ed25519 trust-chain keys generated via OS RNG; rotation via the EATP rotation procedure; key storage is the operator's responsibility (HSM, KMS, sealed secret).
- **Rate limiting** applies per-tenant **and** per-principal **and** per-IP simultaneously; the limit hit first triggers. Defaults are conservative; tune via deployment config.

### 8.4 — LLM / AI-Specific Security (Kaizen · MCP · Align)

LLM-layer surfaces (Kaizen agents, MCP tools, Align fine-tuning) introduce attack classes that classical Security-Plane defenses don't cover:

- **Prompt-injection defense.** Kaizen signatures enforce role separation between system prompt, retrieved context, and user input. Untrusted context is wrapped in delimiter sentinels; an output-validator post-processor rejects content that matches the trust-elevation patterns we track.
- **Tool-confusion / over-eager tool calling.** PACT envelopes name the set of MCP tools an agent may call. A capability not in the envelope is refused at the dispatch boundary, not at the tool boundary — the agent never gets the chance to call it.
- **Model exfiltration.** Trained adapters (Align) are stored with a per-deployment encryption-at-rest key; serving endpoints require attested-caller identity before unsealing.
- **Training-data PII leakage.** Align pipelines run the configured classification policy over the training corpus before any gradient step; PII-classified rows are either redacted or excluded based on policy.
- **Prompt-log redaction.** Kaizen log lines run through the same classification pipeline as DataFlow read paths — classified fields are scrubbed before any log write, including DEBUG.

LLM-specific risks not yet addressed in the SDK (and on the roadmap): adversarial-suffix detection beyond pattern matching; federated-learning poisoning defenses for Align; hallucination scoring as a structured signal rather than a confidence flag.

---

## 9. Companion Packages — What They Replace, Where They Coexist

| Package      | What developers ask                | Comparable to                       | Honest tradeoff                                                                                                |
| ------------ | ---------------------------------- | ----------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **Core SDK** | "What's the engine?"               | Airflow / Prefect / Temporal        | No GUI DAG editor. Code-first. Wins on multi-channel + in-process Level-0.                                     |
| **DataFlow** | "Can I skip writing CRUD?"         | SQLAlchemy + Alembic + custom audit | Opt-in. Drop to raw SQL or your own ORM whenever you want.                                                     |
| **Nexus**    | "Why ship three APIs?"             | FastAPI + Click + custom MCP        | Single registration, all channels. Per-channel hooks if you need them.                                         |
| **Kaizen**   | "How do I build AI agents safely?" | LangChain / LangGraph / DSPy        | Type-safe signatures. Smaller ecosystem; not the right pick if you depend on a specific LangChain integration. |
| **MCP**      | "How do I expose tools to LLMs?"   | Raw FastMCP + custom auth           | Production transports + 6 auth schemes built-in. Pre-1.0.                                                      |
| **ML**       | "Where do my trained models go?"   | MLflow + Ray                        | Pre-wired registry + drift + ONNX export. MLflow has bigger third-party tooling ecosystem.                     |
| **Align**    | "How do I fine-tune + serve?"      | TRL + manual glue + vLLM            | One pipeline from LoRA → GGUF → Ollama/vLLM. Pre-1.0.                                                          |
| **PACT**     | "How do I govern AI actions?"      | OPA/Rego + custom audit             | Native delegation + envelopes + clearance. Pre-1.0; OPA has a 7-year ecosystem advantage.                      |

**Migration philosophy: coexist before replace.** Every comparable can be wrapped as a Kailash node (Airflow DAG trigger, Temporal workflow call, MLflow registry sync) so adoption is incremental. There is no rip-and-replace.

---

## 10. Use Cases (Personas — Not Yet Named Customer References)

| Buyer persona         | Pain                                                                | Where Kailash plays                                                |
| --------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Enterprise Architect  | Ten teams reinventing agent auth + audit + governance               | PACT + Trust + Kaizen — one governance surface                     |
| Platform Team Lead    | Same logic ships as REST + CLI + MCP                                | Nexus — single registration, all channels                          |
| Data Engineer         | 40% of time on glue: pools, migrations, tenant scoping, PII classes | DataFlow — annotated models eliminate that glue                    |
| ML Platform Owner     | Models train in notebooks, drift undetected                         | ML — registry + drift monitor + ONNX export                        |
| Compliance / GRC      | Auditor wants signed evidence of human-traceable origin             | Trust EATP chains, posture levels, RFC-3161 timestamps             |
| Regulated startup CTO | Need SOC2/HIPAA-shaped controls without a compliance team           | Pre-wired audit, classification, redaction, fail-closed governance |

Per-vertical control matrices (SOC2 CC1–CC9, HIPAA §164.312, PCI-DSS, GDPR Art. 32) live in `docs/compliance/`. The first **named** customer reference is targeted for 2026-Q4.

---

## 11. Recommended Defaults (no rhetorical questions)

- **Trust plane: on by default.** Signing every governed action is cheap; the audit trail is the load-bearing compliance artifact. Opt-out is a 3-line env-flag for explicitly non-regulated workloads.
- **Adoption order:** Core SDK + one companion (usually Nexus or DataFlow) on Day 1. Add others when you hit the specific pain. Teams that try to adopt every package on Day 1 historically stall at week 6 (the cognitive load eats the velocity gain).
- **Stability gating:** pre-1.0 packages (MCP, Align, PACT) are evolving — pin versions, expect a deprecation cycle when they hit 1.0.
- **Python+Rust parity** is available, not load-bearing — most teams need Python only. It exists for deployments that run heterogeneous workers (Python data-science + Rust hot-path) in the same trust boundary.
- **Checkpoint encryption:** leave default-on. Only disable for workflows that demonstrably handle no classified data.

---

## 12. What Kailash Is **Not**

- Not a **hosted SaaS**. SDK + runtime you deploy yourself.
- Not a **drop-in LangChain replacement** for hobby projects — value shows at the enterprise edge.
- Not a **database** or a **model**. It orchestrates over your existing infrastructure.
- Not opinionated about **cloud** — runs on any Postgres + any container runtime.
- Not **captured by a single vendor** — Foundation-stewarded, Apache-2.0 throughout, spec basis under CC BY 4.0.
- Not yet **externally attested**. See §13 for what is verifiable today versus what we're still building toward.

---

## 13. Maturity Matrix — Verifiable Today vs Roadmap

### 13.1 — What is verifiable today (every claim cites the public repo)

| Claim                                                    | How to verify                                                                                                          |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Apache-2.0 throughout, no proprietary modules            | `LICENSE` in every package; `pip-licenses` clean dependency graph                                                      |
| 110+ registered nodes across 21 categories               | `src/kailash/nodes/` tree; `@register_node`-decorated classes                                                          |
| 8 runtime variants                                       | `src/kailash/runtime/` (local, async_local, parallel, distributed, durable, access_controlled, docker, dispatcher)     |
| 3-tier test posture, no mocks in Tier 2/3                | `tests/{unit,integration,e2e}/`; `rules/testing.md` mandates real Postgres/Redis/LLMs for tiers 2 and 3                |
| Dialect-portable SQL (Postgres/MySQL/SQLite)             | `src/kailash/db/dialect.py`; CI matrix runs every store test against PG 14/15/16 and MySQL 8.x                         |
| Byte-stable cross-SDK trust chains                       | Conformance harness in `tests/cross_sdk/`; identical hash output for identical inputs across kailash-py and kailash-rs |
| 4 rounds of internal red-team review, 72 findings closed | Disposition records in the repo journal (`journal/`); commit history under `fix/sec-*` branches                        |
| Public CHANGELOG with deprecation entries                | `CHANGELOG.md` in every package; semver-strict + 1-minor deprecation shim policy enforced in `rules/zero-tolerance.md` |
| Sentinel-token SQL sanitizer (defense in depth)          | `packages/kailash-dataflow/src/dataflow/core/nodes.py::sanitize_sql_input` + test corpus                               |
| Multi-tenancy row-level enforcement                      | DataFlow query rewriter; cross-tenant test suite under `tests/integration/tenancy/`                                    |

### 13.2 — Per-package stability and pinning guidance

| Package  | Latest | Stability                                            | Pinning advice                     |
| -------- | ------ | ---------------------------------------------------- | ---------------------------------- |
| Core SDK | 2.20.3 | **Stable** — semver-strict, 1-minor deprecation shim | `kailash~=2.20`                    |
| DataFlow | 2.x    | Stable                                               | `kailash-dataflow~=2.x`            |
| Nexus    | 2.x    | Stable                                               | `kailash-nexus~=2.x`               |
| Kaizen   | 2.x    | Stable                                               | `kailash-kaizen~=2.x`              |
| ML       | 1.x    | Stable                                               | `kailash-ml~=1.x`                  |
| MCP      | 0.x    | **Evolving**                                         | `kailash-mcp==0.2.x` (pin exact)   |
| Align    | 0.x    | **Evolving**                                         | `kailash-align==0.x.x` (pin exact) |
| PACT     | 0.x    | **Evolving**                                         | `kailash-pact==0.x.x` (pin exact)  |

### 13.3 — What we do not yet claim (with roadmap dates)

| Gap                                          | Why it matters                               | Roadmap                                                                                                                               |
| -------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| No named customer reference                  | Procurement-grade social proof               | 2026-Q4 (2 references)                                                                                                                |
| No external third-party security audit       | Independent attestation of crypto primitives | Audit kickoff 2026-Q3; results before PACT 1.0                                                                                        |
| No SBOM / SLSA / Sigstore-signed releases    | Supply-chain attestation                     | CI integration 2026-Q3                                                                                                                |
| No OpenSSF Scorecard badge                   | Public OSS-health signal                     | 2026-Q3                                                                                                                               |
| Bus factor: small (single-digit maintainers) | Project-continuity risk                      | Foundation charter provides transferable stewardship; maintainer roster + commit-concentration metrics will publish with next release |
| `pysyncobj` is a small-maintainer library    | Load-bearing leader-election dependency      | etcd-backed alternative ships in 2.21                                                                                                 |
| No commercial support / SI partners (yet)    | Enterprise procurement gate                  | Foundation is exploring; not yet delivered                                                                                            |
| Trademark policy not yet public              | Fork / commercial-offering clarity           | Drafted; publish before 3.0                                                                                                           |
| No customer-validated benchmark              | Procurement-grade capacity numbers           | 2026-Q4 (alongside first reference)                                                                                                   |

### 13.4 — Indicative 12-month roadmap

| Quarter | Theme                                                                                                             |
| ------- | ----------------------------------------------------------------------------------------------------------------- |
| 2026-Q3 | SBOM + Sigstore + OpenSSF Scorecard · Redis Streams queue backend · external security audit kickoff               |
| 2026-Q4 | First named-customer references · PACT 1.0 with audit results · etcd-backed leader election · published benchmark |
| 2027-Q1 | Multi-region active-active reference architecture · MCP 1.0 · Align 1.0                                           |
| 2027-Q2 | Per-region trust-chain replication · OPA/Rego ↔ PACT interop layer                                                |

---

## 14. For the Audience — How to Engage

- **Architects:** ask about the `WorkflowBuilder/Runtime` contract, dialect-portable SQL, leader-election alternatives in 2.21, and what stays Postgres-only vs scales out to Redis Streams.
- **Product owners:** ask about pilot scope, the §13.3 gap-vs-roadmap table for your target workload, and which companion packages are pre-1.0 (you may want to scope around them).
- **Security & compliance:** ask for the per-control matrix in `docs/compliance/`, the LLM-security threat model in §8.4, and the external-audit timeline.

We treat every gap surfaced in this deck as a deliverable, not as a discussion to defer.

---

## 15. Presentation Format Notes

This document is the **source of truth** for the architecture story. For the live presentation:

- **Slide deck:** rendered diagrams (SVG/PNG) live alongside this file under `workspaces/architecture-presentation/figures/` (to be generated from the ASCII blocks above). The ASCII blocks in this document are the canonical layout; export to SVG with any ASCII-to-diagram tool of your choice (e.g. `asciiflow` → export, or hand-drawn in draw.io / Excalidraw using the ASCII as wireframe).
- **PowerPoint conversion:** ASCII does not survive PowerPoint paste; use the PNG/SVG exports for slides. Code blocks (§2 Hello World) render correctly in PowerPoint via a monospace font.
- **Speaker notes:** each section's "Why this matters for X" callout doubles as the speaker note for that slide. Architects and Product Owners typically want different parts of the same slide foregrounded; the source text supports both readings.
