# Risk & Complexity Analysis -- Tool Agent Support

**Workspace**: tool-agent-support
**Date**: 2026-03-18
**Analyst**: deep-analyst
**Brief**: `workspaces/tool-agent-support/briefs/01-product-brief.md`
**Complexity Score**: 23 (Complex)

---

## Executive Summary

The six deliverables span four packages (kailash-kaizen, eatp, kailash-dataflow, and a new kailash-mcp or nexus-hosted catalog server) with moderate-to-high integration surface area. Three deliverables (P4, P5, P6) have substantial existing code that reduces implementation risk but introduces alignment risk -- the existing code was not designed against the CARE tool-agent architecture and may need structural rework rather than incremental extension. The two highest-risk items are P2 (MCP Catalog Server) which requires a new package or significant new module with no existing foundation, and P1 (Agent Manifest) which introduces a new developer-facing contract (kaizen.toml) that becomes a long-lived API surface. P3 (Composite Validation) is algorithmically straightforward but carries the highest security consequence if defective -- a cycle detection failure enables unbounded resource consumption.

**Recommendation**: Implement in two waves. Wave 1 (P5, P4, P6) hardens existing code against CARE requirements. Wave 2 (P1, P3, P2) builds new surfaces, with P1 and P3 completing before P2 since the catalog server depends on both manifest parsing and composition validation.

---

## 1. Complexity Assessment

### Scoring Matrix

| Dimension    | P1 Manifest | P2 Catalog | P3 Composite | P4 Aggregation | P5 Posture | P6 Budget |
| ------------ | :---------: | :--------: | :----------: | :------------: | :--------: | :-------: |
| Governance   |      3      |     4      |      3       |       1        |     4      |     3     |
| Legal/Spec   |      2      |     3      |      2       |       1        |     3      |     2     |
| Strategic    |      3      |     4      |      2       |       1        |     3      |     2     |
| Technical    |      2      |     4      |      3       |       2        |     2      |     2     |
| Integration  |      3      |     4      |      3       |       2        |     2      |     2     |
| **Subtotal** |   **13**    |   **19**   |    **13**    |     **7**      |   **14**   |  **11**   |

**Aggregate**: 77 points across 6 deliverables. Individual scores: P2 is Complex (19), P5 is Moderate-High (14), P1 and P3 are Moderate (13), P6 is Moderate (11), P4 is Simple (7).

### Lines-of-Code Estimates

| Deliverable     | New Code (LOC) | Modified Code (LOC) | Test Code (LOC) |   Total   |
| --------------- | :------------: | :-----------------: | :-------------: | :-------: |
| P1: Manifest    |      ~600      |        ~100         |      ~500       |   ~1200   |
| P2: MCP Catalog |      ~900      |        ~200         |      ~700       |   ~1800   |
| P3: Composite   |      ~400      |        ~150         |      ~450       |   ~1000   |
| P4: Aggregation |      ~200      |        ~300         |      ~400       |   ~900    |
| P5: Posture     |      ~150      |        ~250         |      ~350       |   ~750    |
| P6: Budget      |      ~350      |        ~200         |      ~400       |   ~950    |
| **Total**       |   **~2600**    |      **~1200**      |    **~2800**    | **~6600** |

---

## 2. Risk Register

### 2.1 P1: Agent Manifest (kaizen.toml)

| Risk                                                                                                                                       | Likelihood |   Impact    |  Severity   | Mitigation                                                                                                                                                                                                                                                          |
| ------------------------------------------------------------------------------------------------------------------------------------------ | :--------: | :---------: | :---------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **R1.1**: Manifest schema becomes a frozen API surface that constrains future tool-agent evolution                                         |    High    |    Major    |  Critical   | Define manifest as v1 with explicit `manifest_version` field. Document forward-compatibility contract. Never inline governance policy in manifest -- keep it as metadata hints.                                                                                     |
| **R1.2**: Brief says "Pydantic model" but EATP rules say "@dataclass (NOT Pydantic)" -- convention conflict                                |    High    | Significant |    Major    | Use `@dataclass` with `to_dict()`/`from_dict()` for internal model. TOML parsing uses `tomllib` (stdlib). Pydantic only if user-facing validation messages are required, and only at the boundary layer.                                                            |
| **R1.3**: `introspect_agent()` reflective introspection may break with lazy imports / metaprogramming in Kaizen agents                     |   Medium   | Significant |    Major    | `TypeIntrospector` already handles complex types. Build on it. Test against all 6 agent archetypes (SimpleQA, ReAct, CoT, Planning, Batch, Memory). Fail-closed: if introspection cannot extract a field, raise an explicit error rather than silently omitting it. |
| **R1.4**: `deploy(manifest, target_url, api_key)` HTTP client introduces an external dependency surface                                    |   Medium   |    Minor    | Significant | Use `httpx` (already in dependency tree via Nexus). No `requests`. Set timeout, validate TLS, never log api_key.                                                                                                                                                    |
| **R1.5**: `kaizen.toml` governance section (`suggested_posture`, `risk_level`) may be misinterpreted as authoritative rather than advisory |   Medium   |    Major    |    Major    | Document clearly: manifest governance section is a REQUEST, not a GRANT. CARE Platform decides actual posture. Name the section `[governance.request]` not `[governance]`.                                                                                          |

**Root Cause (5-Why)**:

- Why R1.1? Because manifest parsers become implicit contracts.
- Why implicit? Because TOML fields get consumed by downstream tooling.
- Why consumed? Because the MCP catalog server (P2) and deploy client both read it.
- Why does that freeze it? Because changing fields breaks deployed manifests.
- Why is that bad? Because the tool-agent architecture is still evolving (Aegis architecture journal shows active design iteration). **Root cause**: premature schema ossification during active design phase. **Mitigation**: version the schema, keep it minimal, use extension fields (`[metadata]` section) for evolving concerns.

### 2.2 P2: MCP Catalog Server

| Risk                                                                                                                                                                         | Likelihood |   Impact    | Severity | Mitigation                                                                                                                                                                                                                                                                                                                           |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------: | :---------: | :------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **R2.1**: No `kailash-mcp` package exists -- the brief references it but it does not exist in the monorepo                                                                   |    High    |  Critical   | Critical | Decision required: (a) create new `packages/kailash-mcp/` or (b) add catalog tools to existing `packages/kailash-nexus/src/nexus/mcp/server.py` or (c) add to `packages/eatp/src/eatp/mcp/server.py`. Recommendation: Nexus, since it already has MCP server infrastructure, WebSocket transport, and workflow-to-tool registration. |
| **R2.2**: Catalog server exposes agent metadata -- information disclosure risk if agents have sensitive capabilities or governance constraints                               |   Medium   |    Major    |  Major   | Implement authorization on all catalog tools. `catalog_search` returns only agents visible to the caller. `catalog_schema` redacts internal implementation details. Never expose budget amounts or constraint thresholds.                                                                                                            |
| **R2.3**: `deploy_agent()` MCP tool creates a code execution surface -- attacker could deploy malicious agent via MCP                                                        |    High    |  Critical   | Critical | `deploy_agent()` MUST NOT execute agent code. It only registers metadata. Actual deployment requires out-of-band approval (CARE Operating Envelope). The MCP tool creates a deployment REQUEST, not a deployment.                                                                                                                    |
| **R2.4**: CO lifecycle principle requires every phase to have full MCP coverage, but brief only lists 8 tools (P1 subset of 40+)                                             |   Medium   | Significant |  Major   | Prioritize the 8 tools listed. Document the remaining tools as Phase 2. CO compliance requires `catalog_*`, `deploy_*`, `app_*` at minimum. The Validate and Codify phase tools can follow.                                                                                                                                          |
| **R2.5**: MCP server pattern divergence -- three MCP server implementations exist (EATP stdio, Nexus WebSocket, Kaizen builtin). Adding a fourth creates maintenance burden. |   Medium   | Significant |  Major   | Use the Nexus MCP server pattern (WebSocket + stdio) as the foundation. Register catalog tools into the existing Nexus server architecture. Do NOT create a standalone server.                                                                                                                                                       |
| **R2.6**: AgentRegistry (kaizen/orchestration/registry.py) is in-memory only. Catalog server needs persistence for deployed agents.                                          |    High    |    Major    |  Major   | Either (a) add SQLite persistence to AgentRegistry or (b) use DataFlow for agent metadata storage. Recommendation: DataFlow, since agent metadata is a CRUD model that DataFlow handles natively.                                                                                                                                    |

**Root Cause (5-Why)**:

- Why R2.1? Because `kailash-mcp` is listed in the brief but never existed.
- Why never existed? Because MCP server capability was split across Nexus (WebSocket), EATP (stdio), and Kaizen (builtin).
- Why split? Because each package needed MCP for different purposes.
- Why is that a problem? Because the catalog server needs both stdio (COC) and WebSocket (programmatic).
- Why both? Because CO mandates MCP-first for all interactions and COC uses stdio. **Root cause**: MCP server infrastructure fragmentation across packages. **Mitigation**: consolidate catalog server in Nexus (which has both transports).

### 2.3 P3: Composite Agent Validation

| Risk                                                                                                                                             | Likelihood |   Impact    |  Severity   | Mitigation                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------------------------------------------------------------------------------------------------------------------------------ | :--------: | :---------: | :---------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **R3.1**: `DelegationGraphValidator` in EATP uses DFS for cycle detection but is purpose-built for delegation chains, not agent composition DAGs |   Medium   | Significant |    Major    | Do NOT reuse `DelegationGraphValidator` directly. It mutates and restores graph state (`validate_new_delegation` saves/restores edges), which is fragile. Build `kaizen.composition.validate_dag()` as a fresh implementation with Kahn's algorithm (topological sort) for DAG validation -- it is iterative, does not mutate input, and naturally detects cycles. |
| **R3.2**: Schema compatibility check is underspecified -- JSON Schema subtyping is undecidable in the general case                               |   Medium   |    Major    |    Major    | Implement structural subtyping for a restricted subset: (a) exact match, (b) output has superset of required input fields, (c) type widening (output int, input number). Do NOT attempt full JSON Schema $ref resolution. Document limitations.                                                                                                                    |
| **R3.3**: Cost estimation for composites has cascading error -- errors compound multiplicatively across N sub-agents                             |   Medium   | Significant | Significant | Use confidence intervals, not point estimates. Report (low, expected, high) ranges. Make clear these are projections, not guarantees. Integrate with the existing `ExternalAgentCostEstimator` pattern.                                                                                                                                                            |
| **R3.4**: Unbounded recursion in deep composite hierarchies                                                                                      |    Low     |  Critical   |    Major    | Enforce maximum composition depth (e.g., 10 levels). Fail-closed if exceeded. CARE constraint tightening already requires monotonic narrowing -- extremely deep hierarchies indicate design problems.                                                                                                                                                              |

**Root Cause (5-Why)**:

- Why R3.1? Because the existing graph validator is for delegation chains.
- Why not reuse? Because it mutates graph state during validation.
- Why does it mutate? Because `validate_new_delegation` temporarily adds edges to check hypothetical cycles.
- Why is that a problem? Because composition validation needs to validate a complete DAG at once, not edge-by-edge.
- Why complete DAG? Because composite agents are declared as a full graph, not built incrementally. **Root cause**: different usage pattern (incremental edge-by-edge vs. batch DAG validation). **Mitigation**: purpose-built DAG validator using topological sort.

### 2.4 P4: DataFlow Aggregation

| Risk                                                                                                                                                                                       | Likelihood |   Impact    |  Severity   | Mitigation                                                                                                                                                                                                                                                                                                                                                                                     |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :--------: | :---------: | :---------: | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **R4.1**: `AggregateNode` exists and works but is in-memory Python only -- the brief requires PostgreSQL/SQLite/MongoDB backend execution                                                  |    High    |    Major    |    Major    | The existing `AggregateNode` processes data in Python memory (iterates over list of dicts). The brief requires database-level `GROUP BY`/`SUM`. These are fundamentally different: one processes fetched data in Python, the other pushes aggregation to the database engine. Need new `count_by()`, `sum_by()`, `aggregate()` query functions that generate SQL/MongoDB aggregation pipeline. |
| **R4.2**: SQL injection risk in dynamically-constructed GROUP BY / aggregate queries                                                                                                       |    High    |  Critical   |  Critical   | All field names and table names MUST be validated with `_validate_identifier()` per infrastructure-sql.md Rule 1. Use parameterized queries for filter values. Never interpolate user-provided field names directly into SQL.                                                                                                                                                                  |
| **R4.3**: MongoDB aggregation pipeline syntax differs fundamentally from SQL GROUP BY                                                                                                      |   Medium   | Significant | Significant | Abstract behind a common interface. The `MongoDBAdapter` already exists in `dataflow/adapters/mongodb.py`. Add `aggregate()` method to the adapter protocol. Each adapter generates dialect-appropriate queries.                                                                                                                                                                               |
| **R4.4**: Brief says "must work across PostgreSQL, SQLite, and MongoDB backends" but existing DataFlow uses `?` canonical placeholders translated by dialect -- MongoDB has no SQL dialect |   Medium   |    Major    |    Major    | MongoDB uses pipeline syntax (`$group`, `$match`, `$sum`), not SQL. The adapter layer must handle this bifurcation. Recommend: `QueryBuilder` generates SQL for relational backends and pipeline dicts for MongoDB. Test against all three backends in Tier 2 integration tests.                                                                                                               |

**Root Cause (5-Why)**:

- Why R4.1? Because the existing AggregateNode processes data client-side.
- Why client-side? Because it was designed for workflow-internal aggregation of intermediate results, not database queries.
- Why is that different? Because database aggregation operates on millions of rows without fetching them to Python.
- Why is fetching bad? Because it defeats the purpose of database engines.
- Why do we need both? Because some use cases aggregate workflow results (existing) and others aggregate stored data (new requirement). **Root cause**: the brief conflates two different aggregation patterns. **Mitigation**: keep `AggregateNode` for in-memory aggregation. Add new `count_by()`/`sum_by()`/`aggregate()` as query-level functions that push computation to the database.

### 2.5 P5: EATP Posture State Machine

| Risk                                                                                                                                                                                                      | Likelihood |   Impact    |  Severity   | Mitigation                                                                                                                                                                                                                                                                                                                                                       |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------: | :---------: | :---------: | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **R5.1**: Existing `PostureStateMachine` uses unbounded `dict` for `_agent_postures` -- no eviction, potential memory exhaustion in long-running processes                                                |   Medium   | Significant | Significant | Add `maxlen` parameter to constructor. When `_agent_postures` exceeds limit, evict least-recently-transitioned agents. Per trust-plane-security.md Rule 4: "Bounded Collections (maxlen=10000)".                                                                                                                                                                 |
| **R5.2**: `_transition_history` uses list trimming (`self._transition_history = self._transition_history[trim_count:]`) which creates a new list on every trim -- GC pressure under high transition rates |    Low     |    Minor    |    Minor    | Replace with `collections.deque(maxlen=10000)` for O(1) trim. Already identified in ROUND6-002 comment but implemented with list slicing.                                                                                                                                                                                                                        |
| **R5.3**: Brief asks for `PostureEvidence` and `EvaluationResult` types that do not exist in the current codebase                                                                                         |    High    | Significant |    Major    | These are new types that must be created. `PostureEvidence` must capture: observation count, success rate, time at current posture, attestation references. `EvaluationResult` must capture: approved/denied/deferred status, rationale string, evidence reference, evaluator identity. Both must have `to_dict()`/`from_dict()` per EATP dataclass conventions. |
| **R5.4**: `TransitionGuard.check_fn` accepts a lambda with no type safety or error handling -- a failing guard function crashes the entire transition                                                     |   Medium   |    Major    |    Major    | Wrap `guard.check(request)` in try/except. On guard exception, fail-closed (deny transition). Log the exception. Per EATP rules: "Fail-closed: unknown/error states -> deny, NEVER silently permit".                                                                                                                                                             |
| **R5.5**: Existing `set_posture()` bypasses all guards -- administrative backdoor that undermines the state machine contract                                                                              |   Medium   |    Major    |    Major    | Document `set_posture()` as an administrative-only method. Add a `force` parameter (default False). When `force=False`, route through guards. Audit log all `set_posture()` calls regardless. Consider deprecating the bypass in favor of an `admin_override_transition()` that still records the override in history.                                           |
| **R5.6**: No thread safety -- `PostureStateMachine` uses plain dicts without locks. Multiple concurrent transitions on the same agent can corrupt state                                                   |   Medium   |    Major    |    Major    | Add `threading.Lock` for `_agent_postures` mutations. Transitions are read-modify-write on the posture dict and must be atomic. The brief for P6 explicitly mentions `threading.Lock` for budget tracking -- same principle applies here.                                                                                                                        |
| **R5.7**: Emergency downgrade bypasses guards but does not check if agent is already PSEUDO_AGENT (no-op transition)                                                                                      |    Low     |    Minor    |    Minor    | Add early return if current posture is already `PSEUDO_AGENT`. Saves a history entry and avoids confusion in audit logs.                                                                                                                                                                                                                                         |

**Root Cause (5-Why)**:

- Why R5.3? Because the brief asks for types not yet implemented.
- Why not implemented? Because the existing posture module was built for the Kaizen trust integration, not as a standalone EATP reference implementation.
- Why is the distinction important? Because a reference implementation must cover ALL spec types, not just those needed by one consumer.
- Why does CARE need all types? Because the posture evidence trail is mandatory for posture progression audit.
- Why mandatory? Because CARE requires every posture change to be traceable to evidence (observation count, success rate, time). **Root cause**: the existing code implements the state machine mechanics but not the evidence model. **Mitigation**: add `PostureEvidence` and `EvaluationResult` as new dataclasses.

### 2.6 P6: Budget Tracking

| Risk                                                                                                                                                                                                                                  | Likelihood |   Impact    |  Severity   | Mitigation                                                                                                                                                                                                                                                                                                                                                                                        |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------: | :---------: | :---------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **R6.1**: Existing `ExternalAgentBudgetEnforcer` uses `float` for USD amounts -- floating-point precision errors accumulate over thousands of transactions                                                                            |    High    |  Critical   |  Critical   | Brief explicitly says "Decimal precision". Replace ALL `float` amounts with `decimal.Decimal`. Use `Decimal("0.00")` not `Decimal(0.00)` (the latter inherits float imprecision). This is a breaking change to the existing budget enforcer.                                                                                                                                                      |
| **R6.2**: `BudgetEnforcer.has_budget()` is not atomic -- between check and execution, another thread could consume the budget (TOCTOU)                                                                                                |    High    |    Major    |  Critical   | Implement `reserve(amount) -> bool` as an atomic check-and-subtract under `threading.Lock`. The brief explicitly requires this pattern. The existing `BudgetEnforcer.has_budget()` is a read-only check followed by a separate `record_usage()` -- this is the classic TOCTOU race.                                                                                                               |
| **R6.3**: Two budget tracking systems exist: `kaizen.core.autonomy.permissions.budget_enforcer.BudgetEnforcer` (tool-level) and `kaizen.trust.governance.budget_enforcer.ExternalAgentBudgetEnforcer` (agent-level). P6 adds a third. |    High    | Significant |    Major    | Consolidate or clearly layer: (a) `BudgetTracker` (P6) is the primitive -- Decimal-safe, thread-safe reserve/record, no external deps. (b) `BudgetEnforcer` wraps `BudgetTracker` with tool-type cost estimation. (c) `ExternalAgentBudgetEnforcer` wraps `BudgetTracker` with DataFlow persistence and multi-dimensional budgets. The primitive must be standalone (no Kaizen/DataFlow imports). |
| **R6.4**: `reserve()` is local-process only (`threading.Lock`). Multi-process deployments (gunicorn workers) will have split budgets                                                                                                  |   Medium   |    Major    |    Major    | Brief acknowledges this: "For multi-process, callers use database-level atomic updates." Document this limitation clearly. Provide a `DatabaseBudgetTracker` protocol that uses `SELECT ... FOR UPDATE` or `UPDATE ... WHERE remaining >= amount` for atomic database-level reservation.                                                                                                          |
| **R6.5**: Budget amounts may receive NaN or Inf values, bypassing all comparisons                                                                                                                                                     |    High    |  Critical   |  Critical   | Per trust-plane-security.md Rule 3: `math.isfinite()` on all numeric constraint fields. `BudgetTracker.__init__` and `reserve()` must validate inputs. `Decimal('NaN')` and `Decimal('Infinity')` exist and must be explicitly rejected.                                                                                                                                                          |
| **R6.6**: No negative budget protection -- what happens when `record(actual)` exceeds `reserve(estimated)`?                                                                                                                           |   Medium   | Significant | Significant | If `actual > estimated`, the budget goes further negative. Define the contract: `record()` adjusts consumed by `actual - estimated_from_reserve`. If actual exceeds estimate, remaining decreases. If actual is less, remaining increases (unused reservation released). Never allow remaining to go below zero -- cap at zero and emit a warning.                                                |

**Root Cause (5-Why)**:

- Why R6.1? Because existing code uses float.
- Why float? Because Python defaults to float for numeric literals.
- Why is that a problem? Because `0.1 + 0.2 != 0.3` in IEEE 754.
- Why does it matter for budgets? Because cumulative rounding errors over thousands of API calls can result in incorrect budget denial or overspend.
- Why thousands of calls? Because tool agents are invoked at high frequency in production. **Root cause**: inadequate numeric type for financial calculations. **Mitigation**: `decimal.Decimal` throughout, with explicit string construction.

---

## 3. Critical Path Analysis

### Dependency Graph

```
P5 (Posture) -----> P1 (Manifest)  -----> P2 (MCP Catalog)
                         ^                      ^
P6 (Budget)  -----------+                      |
                                               |
P4 (Aggregation)  -------> (independent)       |
                                               |
P3 (Composite) --------------------------------+
```

**Detailed Dependencies**:

| Deliverable               |                                       Hard Dependencies                                        |                                Soft Dependencies                                |
| ------------------------- | :--------------------------------------------------------------------------------------------: | :-----------------------------------------------------------------------------: |
| P5: Posture State Machine |                                              None                                              |                                      None                                       |
| P4: DataFlow Aggregation  |                                              None                                              |                                      None                                       |
| P6: Budget Tracking       |                                              None                                              |                         P5 (posture-aware budget caps)                          |
| P1: Agent Manifest        |             P5 (suggested_posture field in manifest references TrustPosture enum)              |                     P6 (budget field in governance section)                     |
| P3: Composite Validation  |                          P1 (validates composite manifest structure)                           |                         P6 (composite cost estimation)                          |
| P2: MCP Catalog Server    | P1 (manifest parsing for deploy_agent tool), P3 (composition validation for catalog_deps tool) | P4 (aggregation for analytics tools), P5 (posture display), P6 (budget display) |

### Parallelization Opportunities

**Wave 1 (can run fully in parallel)**:

- P5: EATP Posture State Machine -- zero dependencies
- P4: DataFlow Aggregation -- zero dependencies
- P6: Budget Tracking -- zero hard dependencies

**Wave 2 (requires Wave 1 complete)**:

- P1: Agent Manifest -- needs P5 for TrustPosture import, P6 for budget types
- P3: Composite Validation -- needs P1 for manifest structure

**Wave 3 (requires Wave 2 complete)**:

- P2: MCP Catalog Server -- needs P1 (manifest), P3 (validation), consumes P4/P5/P6

### Implementation Timeline

| Week | Deliverables            | Rationale                                                  |
| :--: | ----------------------- | ---------------------------------------------------------- |
|  1   | P5 + P4 + P6 (parallel) | Harden existing code, establish primitives                 |
|  2   | P1 + P3 (parallel)      | Build on primitives from Week 1                            |
| 3-4  | P2                      | Highest complexity, needs all other deliverables as inputs |

---

## 4. Failure Mode Analysis

### Blast Radius Matrix

| Deliverable     | Defect Type                                 |                         Blast Radius                          |                   Recoverable?                   |                       Security-Critical?                       |
| --------------- | ------------------------------------------- | :-----------------------------------------------------------: | :----------------------------------------------: | :------------------------------------------------------------: |
| P1: Manifest    | Invalid schema parsing                      |                    Agent deployment fails                     |           Yes -- fix schema, redeploy            |                               No                               |
| P1: Manifest    | Introspection misreads agent capabilities   |           Agent registered with wrong capabilities            |         Yes -- re-introspect and update          | Low -- incorrect capability advertisement, not authority grant |
| P2: Catalog     | Search returns wrong agents                 |            Developer discovers wrong agent via COC            |           Yes -- fix search, re-query            |                Low -- discovery, not execution                 |
| P2: Catalog     | deploy_agent allows unauthorized deployment |             Malicious agent registered in catalog             | **No** -- if agent gets invoked before detection |             **Yes** -- supply chain attack vector              |
| P3: Composite   | Cycle detection false negative              |             Infinite loop in composite execution              |      **No** -- runtime hangs, requires kill      |             **Yes** -- DoS via resource exhaustion             |
| P3: Composite   | Schema compatibility false positive         | Agent A output incompatible with Agent B input, runtime error |      Yes -- composition fails at execution       |                No -- fails fast with type error                |
| P4: Aggregation | SQL injection via field name                |                      Database compromise                      |       **No** -- data exfiltration possible       |                    **Yes** -- SQL injection                    |
| P4: Aggregation | Wrong aggregation result                    |                      Incorrect analytics                      |             Yes -- fix query, re-run             |                               No                               |
| P5: Posture     | State machine allows invalid transition     |            Agent operates at wrong autonomy level             |     **Partially** -- can emergency downgrade     |   **Yes** -- over-permissive posture = unauthorized actions    |
| P5: Posture     | Guard exception not caught                  |      Transition crashes, agent stuck at current posture       |        Yes -- fix guard, retry transition        |       Medium -- denial of service to posture transitions       |
| P6: Budget      | Float precision error                       |                  Over-spend or false denial                   |        Yes -- reconcile with actual costs        |                   Medium -- financial impact                   |
| P6: Budget      | TOCTOU race in reserve                      |   Double-spend (two reserves succeed when only one should)    |          **No** -- money already spent           |          **Yes** -- financial loss, constraint bypass          |

### Security-Critical Failure Modes (Ranked by Severity)

1. **P3: Cycle detection false negative** -- Enables DoS. Mitigation: fuzz test with 10,000+ random graphs, property-based testing (hypothesis library), execution timeout as defense-in-depth.

2. **P4: SQL injection in aggregation** -- Enables database compromise. Mitigation: `_validate_identifier()` on ALL field/table names, parameterized queries for filter values, Tier 2 integration tests with injection payloads.

3. **P6: TOCTOU budget race** -- Enables constraint bypass. Mitigation: atomic `reserve()` under `threading.Lock`, stress test with 100 concurrent threads.

4. **P2: Unauthorized agent deployment** -- Supply chain attack. Mitigation: `deploy_agent()` creates a REQUEST, not a deployment. Require out-of-band approval.

5. **P5: Invalid posture transition** -- Over-permissive autonomy. Mitigation: fail-closed guards, monotonic escalation enforcement, comprehensive transition matrix testing.

---

## 5. Gap Analysis

### 5.1 Brief vs. CARE Platform Requirements

| Brief Asks For                    | CARE Actually Needs                                                                                      | Gap                                                                                                                                                                                                                                         |
| --------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kaizen.toml` manifest            | Operating Envelope that covers entire project, not individual agents                                     | The manifest is per-agent. CARE's CO principle says governance is per-project (Operating Envelope). **Gap**: no `project.toml` or envelope manifest. The brief's `app.toml` partially addresses this but needs explicit envelope semantics. |
| 8 MCP catalog tools               | Every CO phase must have full MCP coverage (40+ tools per architecture journal)                          | P1 subset. Acceptable as Phase 1. Document the full tool inventory for Phase 2.                                                                                                                                                             |
| `validate_dag()` for composites   | Full composition validation: DAG + schema compat + constraint intersection + posture ceiling propagation | Brief covers DAG and schema. Missing: constraint tightening validation (child constraints only narrow), posture ceiling propagation through composite hierarchy. These are CARE-critical.                                                   |
| `count_by`, `sum_by`, `aggregate` | Database-level aggregation with dialect portability                                                      | Brief and implementation align. Gap is small -- ensure MongoDB pipeline generation, not just SQL.                                                                                                                                           |
| Posture state machine             | Posture state machine WITH evidence model AND attestation lifecycle (90-day expiry per CARE spec)        | Brief covers state machine and evidence. Missing: 90-day attestation expiry, posture observation persistence, re-evaluation triggers. These can be Phase 2.                                                                                 |
| BudgetTracker with Decimal        | Per-invocation budget tracking with macaroon-style caveat inheritance                                    | Brief covers the primitive. Missing: integration with InvocationToken caveats (kailash-rs P3). The Python BudgetTracker must be compatible with the caveat model once designed. Not blocking, but design for it.                            |

### 5.2 What kailash-rs Provides That kailash-py Should NOT Replicate

| kailash-rs Feature                                                            | Why NOT in kailash-py                                                                                                                                                                      |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Rust-backed atomic `BudgetTracker` with `AtomicU64`                           | Python GIL makes `threading.Lock` sufficient for single-process. `Decimal` provides precision Rust's u64 microdollars provide in a different way. Different implementation, same contract. |
| PyO3 bindings for Rust posture state machine                                  | kailash-py provides the pure-Python reference implementation. Rust bindings wrap the Rust implementation. They do not need to be compatible at the binary level.                           |
| `InvocationToken` primitive (macaroon-style)                                  | This is a kailash-rs P3 design spike. kailash-py should NOT pre-implement it. Wait for the ADR, then implement the Python equivalent.                                                      |
| 5-level constraint intersection (`org -> team -> agent -> app -> invocation`) | kailash-rs P4. kailash-py has constraint evaluation in `eatp/constraints/`. Extending to 5 levels should follow the same ADR. Do not implement ahead of the spec.                          |
| ABAC evaluator with application-scoped RBAC                                   | kailash-rs P5. Enterprise auth is a Rust binding feature. kailash-py auth is in Nexus (`nexus/auth/`). Different implementation paths.                                                     |

### 5.3 What kailash-py Needs That kailash-rs Does NOT

| kailash-py Need                                               | Why Not in kailash-rs                                                                                                                                                                              |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pure-Python MCP catalog server (stdio + WebSocket)            | kailash-rs exposes Rust MCP tools via PyO3. kailash-py needs a native Python MCP server that works without Rust. The catalog server is Python-native.                                              |
| Natural language aggregation (`AggregateNode`)                | kailash-rs has SQL-level aggregation only. Python's natural language parsing is a unique kailash-py capability for developer experience.                                                           |
| Full reference implementation of EATP posture types           | kailash-rs implements posture in Rust. kailash-py provides the CANONICAL open-source reference that other implementations (including kailash-rs) should align to. This is the spec implementation. |
| TOML config parsing with `tomllib`                            | kailash-rs uses `toml` crate. Different parser, same format.                                                                                                                                       |
| `@dataclass`-based data model (not Pydantic, not Rust struct) | Kaizen convention. Ensures zero-dependency data types.                                                                                                                                             |

---

## 6. Cross-Reference Audit

### Documents Affected by This Work

| Document/Module                                                                   | Impact                                                                                         | Risk                                          |
| --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | --------------------------------------------- |
| `packages/eatp/src/eatp/postures.py`                                              | P5 modifies: add `PostureEvidence`, `EvaluationResult`, thread safety, bounded collections     | Medium -- existing tests may need update      |
| `packages/eatp/src/eatp/posture_agent.py`                                         | P5 indirect: `PostureAwareAgent` depends on `PostureStateMachine` API                          | Low -- API preserved                          |
| `packages/kailash-kaizen/src/kaizen/trust/postures.py`                            | Compatibility shim re-exports from eatp. Must continue to work after P5 changes.               | Low                                           |
| `packages/kailash-kaizen/src/kaizen/trust/governance/budget_enforcer.py`          | P6 refactors: extract `BudgetTracker` primitive, change `float` to `Decimal`                   | High -- breaking change to existing consumers |
| `packages/kailash-kaizen/src/kaizen/trust/governance/cost_estimator.py`           | P6 indirect: shim re-exports from eatp. eatp module uses float.                                | Medium                                        |
| `packages/kailash-kaizen/src/kaizen/core/autonomy/permissions/budget_enforcer.py` | P6 indirect: should use new `BudgetTracker` primitive internally                               | Medium                                        |
| `packages/kailash-kaizen/src/kaizen/core/config.py`                               | P1: TOML parsing exists here. Manifest may need to integrate or extend.                        | Low                                           |
| `packages/kailash-kaizen/src/kaizen/core/type_introspector.py`                    | P1: `introspect_agent()` builds on TypeIntrospector.                                           | Low                                           |
| `packages/kailash-kaizen/src/kaizen/orchestration/registry.py`                    | P2: Catalog server uses agent registry. May need persistence layer.                            | High                                          |
| `packages/kailash-dataflow/src/dataflow/nodes/aggregate_operations.py`            | P4: Keep existing in-memory aggregation. Add new SQL/MongoDB aggregation alongside.            | Low -- additive                               |
| `packages/kailash-nexus/src/nexus/mcp/server.py`                                  | P2: Catalog tools registered into Nexus MCP server.                                            | Medium                                        |
| `packages/eatp/src/eatp/graph_validator.py`                                       | P3: Reference for cycle detection pattern. New implementation in Kaizen.                       | None -- read-only reference                   |
| `packages/eatp/src/eatp/constraints/builtin.py`                                   | P6 indirect: `CostLimitDimension` checks cost constraints. Must align with Decimal.            | Medium                                        |
| `packages/eatp/src/eatp/constraints/dimension.py`                                 | P6 indirect: `ConstraintCheckResult` has `remaining`/`used`/`limit` fields -- currently float. | Medium                                        |

### Inconsistencies Found

1. **Float vs. Decimal inconsistency**: `ExternalAgentBudget.monthly_budget_usd` is `float`. `BudgetCheckResult.remaining_budget_usd` is `float`. `CostLimitDimension` in EATP constraints uses `float`. The brief demands `Decimal`. This is a systemic inconsistency that P6 must resolve across all budget-related code.

2. **Pydantic vs. dataclass**: Brief says "Pydantic model for kaizen.toml parsing" but EATP rules say "@dataclass (NOT Pydantic)". The manifest is in Kaizen, not EATP, so technically Kaizen's convention applies -- but Kaizen's trust modules follow EATP conventions (all files in `kaizen/trust/` are dataclass-based). Decision needed.

3. **MCP package placement**: Brief says "Package: kailash-mcp" but this package does not exist. MCP server code exists in three places: `eatp/mcp/`, `nexus/mcp/`, `kaizen/mcp/`. No consolidated kailash-mcp package.

4. **`PostureStateMachine` default posture**: EATP's `PostureStateMachine.__init__` defaults to `SHARED_PLANNING`. The brief's posture for new tool agents should default to `SUPERVISED` per CARE principle (new agents start at low autonomy). Configuration mismatch.

5. **Budget enforcer duplication**: `kaizen.core.autonomy.permissions.budget_enforcer.BudgetEnforcer` (tool-level, static methods, float) and `kaizen.trust.governance.budget_enforcer.ExternalAgentBudgetEnforcer` (agent-level, instance methods, float). Two implementations with different APIs for overlapping concerns.

---

## 7. Decision Points

These require stakeholder input before implementation proceeds.

### D1: Where does the MCP Catalog Server live?

**Options**:

- (a) New `packages/kailash-mcp/` package (matches brief, but creates a new package with maintenance burden)
- (b) `packages/kailash-nexus/src/nexus/mcp/catalog.py` (leverages existing MCP infrastructure, fewer packages)
- (c) `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/` (keeps agent concerns in Kaizen, but Kaizen already has a builtin MCP server)

**Recommendation**: (b) Nexus. Nexus already has MCP server, WebSocket transport, and workflow-to-tool patterns. The catalog is a deployment/discovery concern, which is Nexus's domain.

### D2: Pydantic or dataclass for `AgentManifest`?

**Options**:

- (a) Pydantic (better validation messages, schema generation, but violates EATP convention)
- (b) `@dataclass` with manual validation (consistent with all trust code, zero extra deps)
- (c) Pydantic at boundary only (parse TOML -> Pydantic model -> convert to dataclass for internal use)

**Recommendation**: (b) `@dataclass`. The manifest is consumed by trust infrastructure. Keep it consistent with EATP conventions. Add explicit validation in `__post_init__` or `from_toml()` classmethod.

### D3: Should `BudgetTracker` live in EATP or Kaizen?

**Options**:

- (a) `eatp.governance.budget_tracker` (EATP is the trust primitive layer)
- (b) `kaizen.trust.governance.budget_tracker` (Kaizen is the agent runtime)
- (c) New standalone module (zero framework dependency)

**Recommendation**: (a) EATP. The budget tracker is a trust primitive (constraint enforcement). It should live where constraint evaluation lives. Kaizen imports it. This also ensures the Kaizen compatibility shim pattern continues working.

### D4: How deep should composite validation go in Phase 1?

**Options**:

- (a) DAG cycle detection + schema compatibility only (brief scope)
- (b) Add constraint tightening validation (CARE requirement)
- (c) Add posture ceiling propagation (CARE requirement)

**Recommendation**: (a) for initial implementation, with the constraint and posture validation interfaces defined but implementations deferred until the InvocationToken ADR (kailash-rs P3) is complete. The interfaces must be designed now to avoid later rework.

### D5: Should `AggregateNode` be modified or new functions created alongside?

**Options**:

- (a) Modify `AggregateNode` to optionally push to database
- (b) Create new `count_by()`, `sum_by()`, `aggregate()` standalone query functions
- (c) Both -- keep `AggregateNode` for in-memory, add query functions for database

**Recommendation**: (c). Different use cases, different execution models. `AggregateNode` processes intermediate workflow results in Python. Query functions push aggregation to the database engine. Both are needed.

### D6: Default posture for newly registered tool agents?

**Options**:

- (a) `SHARED_PLANNING` (current default in PostureStateMachine)
- (b) `SUPERVISED` (CARE principle: start restrictive, earn trust)
- (c) Configurable per-organization

**Recommendation**: (b) `SUPERVISED` as the hardcoded default for tool agents. `SHARED_PLANNING` remains the default for internal agents. Tool agents are external capabilities and should start at lower autonomy. Make the default configurable but with a secure-by-default value.

---

## 8. Testing Strategy

### Tier Allocation

| Deliverable     |                     Tier 1 (Unit)                     |        Tier 2 (Integration)        |                Tier 3 (E2E)                |
| --------------- | :---------------------------------------------------: | :--------------------------------: | :----------------------------------------: |
| P1: Manifest    |        TOML parsing, validation, introspection        |    Deploy client with mock HTTP    |  Full manifest -> deploy -> verify cycle   |
| P2: MCP Catalog |               Individual tool handlers                |  MCP protocol round-trip (stdio)   |        COC-style discovery session         |
| P3: Composite   |    Cycle detection, schema compat, cost estimation    | Multi-agent composition validation |   Composite agent build+validate+execute   |
| P4: Aggregation |      SQL generation, MongoDB pipeline generation      |  Real SQLite + PostgreSQL queries  |       Full workflow with aggregation       |
| P5: Posture     | State machine transitions, guard evaluation, evidence |  Multi-agent posture progression   | Posture lifecycle with emergency downgrade |
| P6: Budget      |   Decimal arithmetic, reserve/record, thread safety   |   Concurrent budget stress test    |     Budget exhaustion -> agent denial      |

### High-Priority Test Scenarios

1. **P3 Fuzz Test**: Generate 10,000 random DAGs, verify cycle detection correctness against networkx reference implementation.
2. **P4 Injection Test**: Attempt SQL injection through field names in `count_by()`, `sum_by()`, `aggregate()`.
3. **P6 Concurrency Test**: 100 threads doing `reserve()` concurrently, verify total reserved never exceeds allocated.
4. **P5 Monotonic Test**: Attempt every possible posture downgrade, verify all are blocked except emergency downgrade.
5. **P2 Auth Test**: Unauthenticated catalog_search, verify no agent metadata is returned.

---

## 9. Implementation Readiness Checklist

| Item                                        |                    Status                     |                                Blocking?                                |
| ------------------------------------------- | :-------------------------------------------: | :---------------------------------------------------------------------: |
| CARE specification accessible               |         Assumed (referenced in brief)         | Yes -- need to verify 5-posture spec and 90-day attestation requirement |
| EATP SDK conventions documented             |         Yes (`.claude/rules/eatp.md`)         |                                   No                                    |
| Trust-plane security rules documented       | Yes (`.claude/rules/trust-plane-security.md`) |                                   No                                    |
| Infrastructure SQL rules documented         |  Yes (`.claude/rules/infrastructure-sql.md`)  |                                   No                                    |
| kailash-mcp package exists                  |                    **No**                     |                       Yes -- D1 must be resolved                        |
| Existing test coverage for modified modules |           Unknown -- need to verify           |                                Moderate                                 |
| Pydantic vs dataclass decision              |                **Unresolved**                 |                       Yes -- D2 must be resolved                        |
| BudgetTracker package location              |                **Unresolved**                 |                       Yes -- D3 must be resolved                        |
| kailash-rs InvocationToken ADR              |              **Not yet written**              |                 Moderate -- affects P3 interface design                 |
| MongoDB adapter availability for P4         |    Exists (`dataflow/adapters/mongodb.py`)    |                                   No                                    |

---

## 10. Success Criteria

| Deliverable | Measurable Outcome                                                                                                                                                                                      |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1          | `kaizen.toml` round-trips: parse -> introspect real agent -> generate manifest -> re-parse == original. Deploy client makes authenticated HTTP POST.                                                    |
| P2          | All 8 MCP tools respond to JSON-RPC calls. `catalog_search` returns results in <50ms for 100-agent registry.                                                                                            |
| P3          | Zero false negatives in cycle detection across 10,000 random graph test. Schema compatibility correctly identifies all JSON Schema primitive type mismatches.                                           |
| P4          | `count_by()` returns correct results on 100K-row table for both PostgreSQL and SQLite. SQL injection via field names blocked with ValueError.                                                           |
| P5          | State machine passes full transition matrix test (5x5 = 25 transitions, each verified). `PostureEvidence` captures observation count, success rate, time. Thread-safe under 100 concurrent transitions. |
| P6          | `BudgetTracker` uses `Decimal` throughout. 100-thread concurrent `reserve()` test: total reserved never exceeds allocated. `NaN` and `Infinity` inputs rejected with ValueError.                        |
