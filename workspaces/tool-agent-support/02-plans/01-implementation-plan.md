# Implementation Plan -- Tool Agent Support

**Date**: 2026-03-18
**Status**: APPROVED (decisions resolved 2026-03-18)
**Input**: Research from 01-analysis/01-research/ (risk, requirements, COC, value, framework)

---

## Synthesis of Analysis Findings

### Convergence Points (all 5 analysts agree)

1. **P5 (Posture) and P3 (Composite Validation) are flagship differentiators** -- ship first
2. **P4 is ~95% done, P5 is ~90% done** -- quick wins that establish momentum
3. **P2 (MCP Catalog) depends on P1 and P3** -- build last
4. **@dataclass over Pydantic** (ADR-1) -- 263:3 precedent, EATP rules, 1.8s import penalty
5. **Budget fragmentation is a real problem** -- P6 must consolidate, not add a 3rd implementation
6. **CARE Platform API contract is undefined** -- P1/P2 deploy functions need local-first mode

### Divergence Points (resolved)

| Topic       | Deep Analyst      | COC Expert                  | Value Auditor                             | Resolution                                                                                                                                                                                      |
| ----------- | ----------------- | --------------------------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P2 scope    | 8 tools (brief)   | 18-22 SDK tools             | 8 is fine, governance-aware search is key | **11 tools**: 8 from brief + validate_composition, budget_status, catalog_deregister. Code-execution tools (importlib) are CLI-only per RT-07.                                                  |
| P6 approach | New BudgetTracker | New module                  | Consolidate existing                      | **New primitive**: BudgetTracker in `eatp.constraints.budget_tracker` using int microdollars (matching kailash-rs). Foundation layer that existing SpendTracker/BudgetEnforcer can delegate to. |
| P4 priority | Wave 1            | Independent, low priority   | Deferrable                                | **Wave 1 with MongoDB dispatch**: SQL aggregation for PG/SQLite + thin dispatch layer routing MongoDB to existing adapter.                                                                      |
| P1 format   | TOML manifest     | Ship governance model first | Governance section is the USP             | **Ship dataclass model + TOML loader together** -- the model IS the value, TOML is the serialization                                                                                            |

---

## Architecture Decision Records (Final)

### ADR-1: @dataclass for All Data Types (ACCEPTED)

Use `@dataclass` with `to_dict()`/`from_dict()` for AgentManifest, AppManifest, GovernanceManifest, and all result types. Override the brief's "Pydantic model" specification.

**Rationale**: 263 @dataclass vs 3 Pydantic imports in kailash-kaizen. EATP rules mandate @dataclass. 1.8s Pydantic import penalty documented in kaizen/core/config.py. Existing KaizenConfig.from_file() already demonstrates TOML + @dataclass.

### ADR-2: MCP Catalog in kailash-kaizen (ACCEPTED)

Place catalog server in `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/`. The `packages/kailash-mcp/` directory does not exist. Kaizen already has `kaizen/mcp/builtin_server/` and the agent registry that backs the catalog.

### ADR-3: BudgetTracker in eatp.constraints as Foundation Primitive (ACCEPTED)

Create `packages/eatp/src/eatp/constraints/budget_tracker.py`. Uses `int` microdollars (1 USD = 1,000,000 microdollars) matching kailash-rs. This is NOT a 3rd budget implementation — it is the low-level atomic primitive that SpendTracker and BudgetEnforcer should delegate their math to. `int` cannot be NaN/Inf, eliminating math.isfinite() security concerns.

### ADR-6: MongoDB Aggregation via Adapter Dispatch (ACCEPTED)

Do NOT build a unified cross-backend aggregation abstraction. SQL backends (PostgreSQL/SQLite) use new `dataflow.query` SQL builder. MongoDB backends dispatch to existing `MongoDBAdapter.aggregate()`. A thin dispatch method on DataFlow routes to the correct path based on adapter type.

### ADR-4: New dataflow.query Module (ACCEPTED)

Create `packages/kailash-dataflow/src/dataflow/query/` separate from existing AggregateNode. AggregateNode does in-memory aggregation. New module generates SQL GROUP BY for database push-down. Both coexist.

### ADR-5: Extend Existing EATP Postures (ACCEPTED)

Only add PostureEvidence, EvaluationResult, PostureStore protocol, and SQLitePostureStore. Do NOT reimplement PostureStateMachine, TransitionGuard, etc. (they already exist, 728 lines).

---

## Implementation Waves

### Wave 1: Foundation (Week 1) -- Parallel

Three deliverables with zero cross-dependencies, substantial existing code.

#### P5: EATP Posture Extensions

- **Scope**: Add PostureEvidence, EvaluationResult to postures.py. Add PostureStore protocol. Add SQLitePostureStore.
- **Effort**: ~200 new lines + ~100 lines tests
- **Existing base**: 728 lines in postures.py, 361 lines in posture_agent.py
- **Files**:
  - EXTEND: `packages/eatp/src/eatp/postures.py`
  - NEW: `packages/eatp/src/eatp/posture_store.py`
  - NEW: `packages/eatp/tests/unit/test_posture_evidence.py`
  - NEW: `packages/eatp/tests/integration/test_posture_store.py`
- **Security**: math.isfinite() on all numerics, parameterized SQL, 0o600 file perms, bounded collections

#### P4: DataFlow Aggregation

- **Scope**: New query module with count_by, sum_by, aggregate as async functions generating SQL
- **Effort**: ~400 new lines + ~200 lines tests
- **Existing base**: AggregateNode (406 lines, in-memory), DataFlow engine and adapters
- **Files**:
  - NEW: `packages/kailash-dataflow/src/dataflow/query/__init__.py`
  - NEW: `packages/kailash-dataflow/src/dataflow/query/aggregation.py`
  - NEW: `packages/kailash-dataflow/src/dataflow/query/sql_builder.py`
  - NEW: `packages/kailash-dataflow/src/dataflow/query/models.py`
  - NEW: `packages/kailash-dataflow/tests/unit/query/test_sql_builder.py`
  - NEW: `packages/kailash-dataflow/tests/integration/query/test_aggregation.py`
- **Security**: Parameterized queries only, validate field/table names, no f-string SQL

#### P6: Budget Tracking

- **Scope**: New BudgetTracker primitive with int microdollars, reserve/record/remaining/snapshot, threading.Lock
- **Effort**: ~300 new lines + ~200 lines tests
- **Existing base**: spend_tracker.py (318 lines), budget_enforcer.py (256 lines)
- **Reference**: kailash-rs `crates/kailash-kaizen/src/cost/budget.rs` (637 lines, 12 concurrent tests)
- **Files**:
  - NEW: `packages/eatp/src/eatp/constraints/budget_tracker.py`
  - NEW: `packages/eatp/tests/unit/test_budget_tracker.py`
- **Security**: int microdollars (cannot be NaN/Inf), threading.Lock for reserve(), bounded transaction log (maxlen=10000), saturating arithmetic (never negative), fail-closed on error state

### Wave 2: Agent Surface (Week 2) -- Parallel

Two deliverables that create the developer-facing surface.

#### P1: Agent Manifest

- **Scope**: AgentManifest, AppManifest, GovernanceManifest as @dataclass. TOML loader. introspect_agent(). deploy() HTTP client.
- **Effort**: ~600 new lines + ~300 lines tests
- **Existing base**: KaizenConfig TOML pattern, TypeIntrospector, agent registry
- **Files**:
  - NEW: `packages/kailash-kaizen/src/kaizen/manifest/__init__.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/manifest/agent.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/manifest/app.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/manifest/governance.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/manifest/loader.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/deploy/__init__.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/deploy/introspect.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/deploy/client.py`
  - NEW: `packages/kailash-kaizen/tests/unit/test_manifest.py`
  - NEW: `packages/kailash-kaizen/tests/unit/test_introspect.py`
  - NEW: `packages/kailash-kaizen/tests/integration/test_deploy.py`
- **Security**: Validate all TOML input fields. importlib.import_module for introspection only from trusted paths. No eval/exec.

#### P3: Composite Validation

- **Scope**: validate_dag(), check_schema_compatibility(), estimate_cost()
- **Effort**: ~400 new lines + ~250 lines tests
- **Existing base**: orchestration patterns (agent format), TypeIntrospector, DelegationGraphValidator
- **Files**:
  - NEW: `packages/kailash-kaizen/src/kaizen/composition/__init__.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/composition/dag_validator.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/composition/schema_compat.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/composition/cost_estimator.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/composition/models.py`
  - NEW: `packages/kailash-kaizen/tests/unit/test_dag_validator.py`
  - NEW: `packages/kailash-kaizen/tests/unit/test_schema_compat.py`
  - NEW: `packages/kailash-kaizen/tests/integration/test_composition.py`
- **Security**: Cycle detection MUST be correct (false negative = unbounded resource consumption). JSON Schema validation must handle malformed input.

### Wave 3: MCP Catalog (Weeks 3-4)

Single deliverable that integrates everything.

#### P2: MCP Catalog Server

- **Scope**: 11 MCP tools: 8 from brief + validate_composition, budget_status, catalog_deregister
- **Effort**: ~900 new lines + ~450 lines tests
- **Depends on**: P1 (manifest parsing, introspection), P3 (DAG validation, schema compat), P6 (budget status)
- **Files**:
  - NEW: `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/__init__.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/server.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/tools/discovery.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/tools/deployment.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/tools/application.py`
  - NEW: `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/resources/agent_resources.py`
  - NEW: `packages/kailash-kaizen/tests/unit/test_catalog_tools.py`
  - NEW: `packages/kailash-kaizen/tests/integration/test_catalog_mcp.py`
  - NEW: `packages/kailash-kaizen/tests/e2e/test_catalog_protocol.py`
- **Security**: Input validation on all tool parameters. No arbitrary code execution from catalog queries. Rate-limit tool calls (bounded request log).
- **Pre-seeding**: Register Kaizen's 14 built-in agents (SimpleQA, ReAct, ChainOfThought, etc.) in the catalog on startup.

---

## Cross-Cutting Concerns

### 1. Posture-Budget Integration (P5 + P6)

Value audit identified this as the #1 governance differentiator. Implementation:

- BudgetTracker emits events on threshold crossings (80%, 95%, 100%)
- PostureStateMachine can accept budget events as transition triggers
- Wire in Wave 2 or early Wave 3 as integration work

### 2. CARE Platform API Contract

P1 deploy() and P2 catalog tools need a remote API. Implementation:

- **Local-first**: All tools work against local registry (file-based or in-memory) without CARE Platform
- **Remote-capable**: deploy() accepts optional target_url. If omitted, registers locally.
- **API contract**: Define as a JSON Schema in `packages/kailash-kaizen/src/kaizen/deploy/api_schema.json`

### 3. Testing Strategy

| Wave | Tier 1 (Unit)                              | Tier 2 (Integration)                   | Tier 3 (E2E)        |
| ---- | ------------------------------------------ | -------------------------------------- | ------------------- |
| 1    | Serialization, algorithms, thread safety   | SQLite persistence, real DataFlow      | —                   |
| 2    | TOML parsing, DAG detection, schema compat | Real agent introspection, compositions | Deploy flow         |
| 3    | Tool handler functions                     | Full MCP server over stdio             | Protocol compliance |

**NO MOCKING in Tier 2/3** per project rules.

---

## Risk Mitigations

| Risk                                    | Severity | Mitigation                                                                                     |
| --------------------------------------- | -------- | ---------------------------------------------------------------------------------------------- |
| Cycle detection false negative (P3)     | CRITICAL | Exhaustive test suite: self-loops, diamonds, back-edges, disconnected. Property-based testing. |
| SQL injection in aggregation (P4)       | CRITICAL | Validate field/table names with `_validate_identifier()`. Parameterized queries only.          |
| TOCTOU budget race (P6)                 | HIGH     | threading.Lock around reserve(). Atomic check-and-subtract.                                    |
| CARE Platform API not ready (P1, P2)    | HIGH     | Local-first mode. Define API contract as JSON Schema.                                          |
| MCP catalog empty on launch (P2)        | MEDIUM   | Pre-seed with Kaizen's 14 built-in agents.                                                     |
| Pydantic import if someone adds it (P1) | LOW      | ADR-1 documented. Code review enforcement.                                                     |

---

## Success Criteria

### Wave 1 Complete When:

- [ ] PostureEvidence and EvaluationResult pass serialization roundtrip tests
- [ ] SQLitePostureStore persists and recovers state across restarts
- [ ] count_by/sum_by/aggregate generate correct SQL for SQLite and PostgreSQL
- [ ] BudgetTracker passes concurrent reserve() test with 10 threads, zero over-allocation

### Wave 2 Complete When:

- [ ] AgentManifest.from_toml() parses valid kaizen.toml files
- [ ] introspect_agent() extracts Signature, tools, capabilities from real Kaizen agents
- [ ] validate_dag() detects cycles in all test graphs
- [ ] check_schema_compatibility() correctly identifies compatible and incompatible JSON Schema pairs

### Wave 3 Complete When:

- [ ] MCP catalog server starts, responds to tools/list, handles all 8 tool calls
- [ ] catalog_search returns results with governance metadata
- [ ] deploy_agent creates agent entry in local registry
- [ ] Full end-to-end: introspect agent -> create manifest -> validate composition -> deploy -> discover via catalog

---

## Estimated Totals

| Metric               | Estimate                                                 |
| -------------------- | -------------------------------------------------------- |
| New production lines | ~2,700                                                   |
| New test lines       | ~1,450                                                   |
| New files            | ~35                                                      |
| Modified files       | ~3 (postures.py, 2x **init**.py re-exports)              |
| New packages/modules | 5 (manifest, deploy, composition, query, catalog_server) |
| Timeline             | 4 weeks (3 waves)                                        |
