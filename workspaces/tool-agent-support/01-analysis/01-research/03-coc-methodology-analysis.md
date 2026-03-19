# COC Methodology Analysis -- Tool Agent Support

**Workspace**: tool-agent-support
**Phase**: 01-analysis
**Date**: 2026-03-18
**Agent**: coc-expert
**Grounding**: Aegis Architecture Journal (Decision 9 / First Principle), Product Brief, COC Five-Layer Architecture

---

## Executive Summary

The Aegis architecture journal establishes a first principle that overrides all other decisions: **"CO governs the entire tool agent lifecycle."** Every workflow step must be performable via MCP without leaving the COC conversation. The kailash-py product brief scopes six deliverables (P1-P6). This analysis evaluates those deliverables against the COC five-layer architecture, identifies gaps where a developer would be forced out of the conversation, and assesses the three fault lines (amnesia, convention drift, security blindness) specific to this implementation.

**Key finding**: The product brief's P2 scopes 8 MCP tools. The Aegis journal defines 40+ across 10 phases. For kailash-py (SDK layer, open-source), the correct scope is approximately 18-22 SDK-layer tools. The remaining 20+ are platform-layer tools that belong in CARE Platform, not in kailash-py. The brief's 8 tools leave critical gaps in the Analyze and Validate CO phases.

---

## 1. COC Phase Coverage Assessment

### Mapping Deliverables to CO Phases

For each CO phase, the table below identifies which deliverables provide MCP coverage, which gaps force a developer out of the conversation, and the minimum viable MCP surface.

#### Phase 1: Analyze (`/analyze`)

| Operation                     | MCP Tool Needed               | Provided By | Status                                                      |
| ----------------------------- | ----------------------------- | ----------- | ----------------------------------------------------------- |
| Search agent catalog          | `catalog_search`              | P2          | COVERED                                                     |
| Describe agent details        | `catalog_describe`            | P2          | COVERED                                                     |
| Get agent I/O schema          | `catalog_schema`              | P2          | COVERED                                                     |
| Get agent dependency graph    | `catalog_deps`                | P2          | COVERED                                                     |
| Check schema compatibility    | `catalog_check_compatibility` | P2          | COVERED (brief lists it)                                    |
| Register application          | `app_register`                | P2          | COVERED                                                     |
| Check application status      | `app_status`                  | P2          | COVERED                                                     |
| List agents by capability     | `catalog_list_by_capability`  | --          | GAP                                                         |
| List developer's applications | `app_list_mine`               | --          | GAP                                                         |
| Estimate composition cost     | `cost_estimate`               | --          | GAP (P6 provides BudgetTracker but no MCP tool wrapping it) |

**Assessment**: Analyze phase is 7/10 covered. Three gaps: capability-based discovery, application listing, and cost estimation via MCP. The capability-based search gap is significant -- a developer asking "what document processing agents exist?" would need to craft keyword queries instead of searching by capability tag.

**Minimum viable addition**: `catalog_list_by_capability` (SDK-layer, wraps registry query).

#### Phase 2: Plan (`/todos`)

| Operation                          | MCP Tool Needed               | Provided By | Status                                                                             |
| ---------------------------------- | ----------------------------- | ----------- | ---------------------------------------------------------------------------------- |
| Get schema for compatibility check | `catalog_schema`              | P2          | COVERED                                                                            |
| Check A->B compatibility           | `catalog_check_compatibility` | P2/P3       | COVERED (P3 `check_schema_compatibility` is the SDK function; P2 wraps it as MCP)  |
| Validate composition DAG           | `validate_composition`        | P3          | PARTIALLY COVERED (P3 provides `validate_dag` as Python function, but no MCP tool) |
| Estimate composition cost          | `cost_estimate`               | P3/P6       | PARTIALLY COVERED (P3 `estimate_cost` as Python function, no MCP tool)             |

**Assessment**: Plan phase is functionally covered by P2 + P3 Python APIs, but **P3 functions lack MCP tool wrappers**. A COC session calling `catalog_check_compatibility` via MCP can check schema compatibility, but cannot call `validate_dag` or `estimate_cost` via MCP. The developer would need to exit the conversation and run Python code.

**Minimum viable addition**: MCP tool wrappers for `validate_composition` and `cost_estimate` in the catalog server.

#### Phase 3: Implement (`/implement`)

| Operation               | MCP Tool Needed       | Provided By | Status                                                         |
| ----------------------- | --------------------- | ----------- | -------------------------------------------------------------- |
| Scaffold new agent      | `scaffold_agent`      | --          | GAP                                                            |
| Scaffold composite      | `scaffold_composite`  | --          | GAP                                                            |
| Validate agent code     | `validate_agent_code` | --          | GAP (P1 `introspect_agent` provides the function, no MCP tool) |
| Deploy agent manifest   | `deploy_agent`        | P2          | COVERED                                                        |
| Check deployment status | `deploy_status`       | P2          | COVERED                                                        |
| Local test run          | `local_test_run`      | --          | GAP                                                            |

**Assessment**: Implement phase has the largest gap. P2 covers deployment, but scaffolding, validation, and local testing have no MCP surface. A developer building a new agent via COC would need to exit the conversation to create boilerplate files and run local tests.

**Critical question**: Are scaffold/test tools SDK-layer or platform-layer?

- `scaffold_agent` and `scaffold_composite` are SDK-layer (generate local files using Kaizen patterns). They belong in kailash-py.
- `validate_agent_code` is SDK-layer (introspects local Python modules). Belongs in kailash-py.
- `local_test_run` is SDK-layer (runs agent via LocalRuntime). Belongs in kailash-py.

**Minimum viable addition**: 4 MCP tools (`scaffold_agent`, `scaffold_composite`, `validate_agent_code`, `local_test_run`).

#### Phase 4: Validate (`/redteam`)

| Operation                        | MCP Tool Needed                                  | Provided By | Status                                          |
| -------------------------------- | ------------------------------------------------ | ----------- | ----------------------------------------------- |
| Sandbox invoke single agent      | `sandbox_invoke`                                 | --          | PLATFORM-LAYER (requires CARE Platform sandbox) |
| Sandbox invoke composite         | `sandbox_invoke_composite`                       | --          | PLATFORM-LAYER                                  |
| Validate composition constraints | `validate_composition`                           | P3          | PARTIALLY COVERED (Python function, no MCP)     |
| Simulate failures                | `sandbox_invoke_composite` + `simulate_failures` | --          | PLATFORM-LAYER                                  |

**Assessment**: Validate phase is primarily platform-layer. The SDK can provide `validate_composition` (DAG cycles, schema compat, cost estimate) via MCP. Sandbox invocation requires a running CARE Platform instance -- it cannot be an SDK-only tool.

**What kailash-py CAN provide**: Local validation tools (composition validation, constraint checking, schema compatibility). What it CANNOT provide: sandbox execution, failure simulation, production-like testing.

**Minimum viable addition**: `validate_composition` MCP tool (wraps P3 functions). Sandbox tools are CARE Platform scope.

#### Phase 5: Codify (`/codify`)

| Operation                  | MCP Tool Needed              | Provided By | Status         |
| -------------------------- | ---------------------------- | ----------- | -------------- |
| Create governance template | `governance_template_create` | --          | PLATFORM-LAYER |
| List governance templates  | `governance_template_list`   | --          | PLATFORM-LAYER |

**Assessment**: Codify phase is entirely platform-layer for governance templates. The SDK has no governance template concept -- that is CARE Platform's responsibility. No kailash-py MCP tools needed.

#### Phase 6: Deploy (`/deploy`)

| Operation                | MCP Tool Needed         | Provided By | Status         |
| ------------------------ | ----------------------- | ----------- | -------------- |
| Deploy agent to platform | `deploy_agent`          | P2          | COVERED        |
| Check deployment status  | `deploy_status`         | P2          | COVERED        |
| Get agent health         | `agent_health`          | --          | PLATFORM-LAYER |
| Get agent metrics        | `agent_metrics`         | --          | PLATFORM-LAYER |
| Compare versions         | `agent_metrics_compare` | --          | PLATFORM-LAYER |

**Assessment**: Deploy phase is split. Deployment initiation is SDK-layer (P2 covers it). Monitoring/metrics are platform-layer (require production CARE Platform).

### Phase Coverage Summary

| CO Phase  | SDK-Layer Tools Needed | Currently Covered | Gap Count          |
| --------- | ---------------------- | ----------------- | ------------------ |
| Analyze   | 10                     | 7                 | 3                  |
| Plan      | 4                      | 2 (as MCP)        | 2                  |
| Implement | 6                      | 2                 | 4                  |
| Validate  | 1 (SDK) + 3 (platform) | 0 (as MCP)        | 1 SDK + 3 platform |
| Codify    | 0 (SDK) + 2 (platform) | 0                 | 0 SDK + 2 platform |
| Deploy    | 2 (SDK) + 3 (platform) | 2                 | 0 SDK + 3 platform |

**Total SDK-layer MCP tools needed**: ~20
**Currently covered by P2 brief**: 8
**Gap**: 12 SDK-layer MCP tools missing from the brief

---

## 2. Three Fault Lines Assessment

### 2.1 Amnesia -- Institutional Knowledge at Risk

The amnesia fault line is the most severe for this workspace because tool agent support involves deep cross-cutting conventions that span multiple packages (EATP, Kaizen, DataFlow, MCP). A developer working in a long COC session will encounter context window pressure as they move between packages.

**At-risk institutional knowledge:**

| Knowledge                                                                                      | Where It Lives Today      | Amnesia Risk                                                                    |
| ---------------------------------------------------------------------------------------------- | ------------------------- | ------------------------------------------------------------------------------- |
| Posture is per-invocation, not per-agent (Decision 2, 3)                                       | Aegis journal only        | HIGH -- this is a CARE spec-level insight that exists only in one markdown file |
| Constraints are subtractive (intersection, never union)                                        | EATP spec + Aegis journal | MEDIUM -- exists in EATP code but the invocation-level intersection is new      |
| Five CARE constraint dimensions (Financial, Operational, Temporal, Data Access, Communication) | EATP SDK                  | LOW -- already codified in `eatp.constraints.dimension`                         |
| `kaizen.toml` manifest format                                                                  | Product brief only        | HIGH -- no schema, no validation, no examples in the SDK yet                    |
| Application-first access model (Decision 7)                                                    | Aegis journal only        | HIGH -- the `app.toml` format exists only in one journal entry                  |
| Monotonic trust escalation (never downgrade except emergency)                                  | EATP postures.py          | LOW -- already enforced in code                                                 |
| Operating Envelope as governance unit (Decision 6)                                             | Aegis journal only        | HIGH -- entirely new concept, no SDK representation                             |
| MCP tool naming conventions (`catalog_*`, `deploy_*`, `app_*`)                                 | Aegis journal only        | MEDIUM -- naming convention exists but is not codified as a rule                |

**Critical amnesia vectors:**

1. **Cross-package conventions**: When implementing P1 (kaizen.manifest) and P5 (eatp.postures), the convention that `suggested_posture` in the manifest must map to `TrustPosture` enum values could be forgotten mid-session. The manifest uses string `"supervised"` while the enum is `TrustPosture.SUPERVISED`. Without explicit validation, drift is guaranteed.

2. **Schema compatibility semantics**: P3's `check_schema_compatibility` must implement structural subtyping (output schema is a structural subtype of input schema), not nominal equality. This is an EATP-level convention (delegation cannot expand authority) applied to data schemas. Without anti-amnesia reinforcement, an implementer might default to exact schema match.

3. **Budget precision**: P6 specifies `Decimal` precision. Python's `float` is pervasive in the codebase. Without hooks enforcing Decimal usage in budget code, a developer will inevitably use `float` for "just this one calculation."

### 2.2 Convention Drift -- Python vs CARE Spec vs kailash-rs

Convention drift has three vectors in this workspace:

**Vector 1: Python idioms vs CARE specification semantics**

| CARE Spec Concept            | Correct Python Implementation           | Drift Risk                                                                           |
| ---------------------------- | --------------------------------------- | ------------------------------------------------------------------------------------ |
| Posture state machine        | `PostureStateMachine` class with guards | LOW -- already implemented in `eatp.postures`                                        |
| Constraint envelope          | Intersection of constraint sets         | MEDIUM -- Python developers will use `dict.update()` (union) instead of intersection |
| Trust chain verification     | Cryptographic hash chain                | LOW -- already in `eatp.chain`                                                       |
| Fail-closed on unknown state | `raise TrustError`                      | MEDIUM -- Python's permissive exception handling encourages `try/except: pass`       |
| Bounded collections          | `deque(maxlen=N)`                       | MEDIUM -- already a rule, but new collections in P5/P6 need enforcement              |

**Vector 2: kailash-py vs kailash-rs semantic alignment**

The product brief states: "same concepts, independent implementation." Convention drift between Python and Rust SDKs is a specification-level risk.

| Concept              | kailash-rs Name                         | kailash-py Name (Proposed) | Drift Risk                                               |
| -------------------- | --------------------------------------- | -------------------------- | -------------------------------------------------------- |
| Agent manifest       | `kaizen.toml`                           | `kaizen.toml`              | LOW -- same file name                                    |
| Application manifest | `app.toml`                              | `app.toml`                 | LOW -- same file name                                    |
| Posture enum values  | `delegated`, `continuous_insight`, etc. | Same (from EATP spec)      | LOW -- both derive from spec                             |
| MCP tool names       | `catalog_search`, `deploy_agent`, etc.  | Same (from Aegis journal)  | MEDIUM -- journal is proprietary, kailash-py may diverge |
| Budget tracking      | `BudgetTracker` with Decimal            | Same (from brief)          | LOW -- brief specifies explicitly                        |

The highest drift risk is MCP tool naming. The Aegis journal defines tool names for the proprietary platform. CARE Platform (open-source) should derive tool names from the CARE specification, not from Aegis. If kailash-py copies Aegis tool names, it creates implicit coupling. If it invents new names, interoperability suffers.

**Recommendation**: Define MCP tool naming in the CARE specification (CO methodology section), not in either SDK. Both SDKs derive from the spec.

**Vector 3: Python ecosystem conventions vs kailash-py conventions**

| Area           | Python Ecosystem Default | kailash-py Convention                        | Drift Risk                                                                              |
| -------------- | ------------------------ | -------------------------------------------- | --------------------------------------------------------------------------------------- |
| Data models    | Pydantic                 | `@dataclass` (EATP rule)                     | HIGH -- P1 brief says "Pydantic model for kaizen.toml" which contradicts EATP SDK rules |
| Async patterns | `asyncio.run()`          | `AsyncLocalRuntime.execute_workflow_async()` | MEDIUM                                                                                  |
| Configuration  | YAML/JSON                | TOML (for manifests)                         | LOW -- explicit in brief                                                                |
| Error handling | Generic `Exception`      | `TrustError` hierarchy                       | MEDIUM -- new code may skip hierarchy                                                   |
| Testing        | `unittest.mock`          | Real infrastructure (Tier 2/3)               | LOW -- already enforced by rules                                                        |

**CRITICAL FINDING**: The product brief (P1) specifies "Pydantic model for `kaizen.toml` parsing." The EATP SDK rules (`rules/eatp.md`) mandate "Use `@dataclass` (NOT Pydantic) for all data types." This is an active convention conflict. The manifest parsing can use a TOML library for file I/O, but the data model must be `@dataclass` with `to_dict()`/`from_dict()` per EATP convention. The brief's "Pydantic" language must be corrected to `@dataclass`.

### 2.3 Security Blindness -- Python-Specific Risks

Python lacks Rust's compile-time safety guarantees. The following security patterns require explicit enforcement in kailash-py where Rust provides them automatically:

**2.3.1 Type Safety**

| Risk                        | Rust Safety                            | Python Gap                              | Mitigation                                                                                                                |
| --------------------------- | -------------------------------------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Budget arithmetic overflow  | Checked arithmetic / `Decimal` in Rust | Python `float` silently loses precision | P6 must enforce `Decimal` everywhere. `math.isfinite()` on all numeric inputs (rule: trust-plane-security.md MUST Rule 3) |
| Posture enum exhaustiveness | `match` is exhaustive                  | Python `if/elif` can miss cases         | `PostureStateMachine.transition()` must fail-closed on unknown posture (already implemented)                              |
| Null safety                 | `Option<T>` explicit                   | `None` passes silently                  | All public APIs must validate `None` inputs explicitly                                                                    |
| Schema type confusion       | Serde type checking                    | JSON schema validation at runtime only  | P3 `check_schema_compatibility` must validate schemas before comparison                                                   |

**2.3.2 Concurrency Safety**

| Risk                           | Rust Safety               | Python Gap                                   | Mitigation                                                                                                                                   |
| ------------------------------ | ------------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Budget race condition          | `Arc<Mutex<T>>`           | GIL protects single-process only             | P6 specifies `threading.Lock` -- adequate for single-process. Multi-process requires database-level atomic updates (brief acknowledges this) |
| Posture transition TOCTOU      | Ownership system prevents | `get_posture()` then `transition()` can race | `PostureStateMachine.transition()` must check current state atomically within the method (already implemented)                               |
| MCP server concurrent requests | Tokio task safety         | asyncio single-threaded event loop           | Adequate for MCP stdio transport (sequential requests)                                                                                       |

**2.3.3 Input Validation Gaps**

| Input Surface                   | Attack Vector                                                 | Required Validation                                                           |
| ------------------------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `kaizen.toml` manifest          | Path traversal in `module` field                              | Validate module path does not contain `..` or absolute paths                  |
| `app.toml` manifest             | Injection in `name`, `description`                            | Validate against `^[a-zA-Z0-9_-]+$` for name                                  |
| MCP tool arguments              | Oversized payloads, malformed JSON schema                     | Max payload size, JSON schema validation                                      |
| `catalog_search` query          | Regex injection if query is used in regex match               | Escape or reject regex metacharacters                                         |
| `deploy_agent` manifest content | Arbitrary code execution via `module` + `class` introspection | Restrict introspection to allowed module paths                                |
| Budget amounts                  | NaN/Infinity bypass                                           | `math.isfinite()` on all Decimal inputs (trust-plane-security.md MUST Rule 3) |

**2.3.4 Missing Security Reviews**

The following P5-specific security concerns have no existing rule coverage:

1. **Posture downgrade protection**: `PostureStateMachine` allows `set_posture()` which bypasses all guards. This method is necessary for initialization but could be misused to downgrade without emergency justification. Needs audit logging.
2. **Guard removal**: `remove_guard()` can silently weaken the state machine. No audit trail. Should log when guards are removed and by whom.
3. **Manifest introspection**: P1's `introspect_agent(module, class_name)` dynamically imports and inspects arbitrary Python modules. This is a code execution vector if the module path is not restricted.

---

## 3. MCP Tool Completeness -- SDK-Layer vs Platform-Layer

### The Scoping Problem

The Aegis journal defines 40+ MCP tools across 10 phases. The kailash-py brief defines 8. The correct scope is neither -- it is determined by the four-layer IP architecture:

```
Specs (CARE, EATP, CO)     -- Defines WHAT tools must exist
SDKs (kailash-py)           -- Implements tools that work LOCALLY (no platform required)
Platform (CARE Platform)    -- Implements tools that require PLATFORM state
Verticals                   -- Consume tools
```

### Classification of All Aegis Journal Tools

| Tool                          | SDK-Layer (kailash-py) | Platform-Layer (CARE Platform) | Rationale                                          |
| ----------------------------- | ---------------------- | ------------------------------ | -------------------------------------------------- |
| `catalog_search`              | YES                    | also                           | SDK queries local registry + optional platform API |
| `catalog_describe`            | YES                    | also                           | Same                                               |
| `catalog_schema`              | YES                    | also                           | Same                                               |
| `catalog_deps`                | YES                    | also                           | Same                                               |
| `catalog_check_compatibility` | YES                    | --                             | Pure computation on schemas                        |
| `catalog_list_by_capability`  | YES                    | also                           | Same as catalog_search pattern                     |
| `app_register`                | --                     | YES                            | Requires platform state                            |
| `app_status`                  | --                     | YES                            | Requires platform state                            |
| `app_request_agent`           | --                     | YES                            | Requires platform governance                       |
| `app_renew`                   | --                     | YES                            | Requires platform state                            |
| `app_list_mine`               | --                     | YES                            | Requires platform state                            |
| `scaffold_agent`              | YES                    | --                             | Generates local files                              |
| `scaffold_composite`          | YES                    | --                             | Generates local files                              |
| `validate_agent_code`         | YES                    | --                             | Introspects local Python                           |
| `validate_composition`        | YES                    | --                             | Pure computation                                   |
| `local_test_run`              | YES                    | --                             | Runs via LocalRuntime                              |
| `local_test_suite`            | YES                    | --                             | Runs via LocalRuntime                              |
| `deploy_agent`                | YES (HTTP client)      | YES (HTTP server)              | SDK provides client, platform provides endpoint    |
| `deploy_composite`            | YES (HTTP client)      | YES (HTTP server)              | Same                                               |
| `deploy_status`               | YES (HTTP client)      | YES (HTTP server)              | Same                                               |
| `deploy_version_diff`         | --                     | YES                            | Requires version history in platform               |
| `sandbox_invoke`              | --                     | YES                            | Requires platform sandbox                          |
| `sandbox_invoke_composite`    | --                     | YES                            | Requires platform sandbox                          |
| `sandbox_examples`            | --                     | YES                            | Requires platform data                             |
| `governance_status`           | --                     | YES                            | Requires platform state                            |
| `governance_constraints`      | --                     | YES                            | Requires platform state                            |
| `governance_template_match`   | --                     | YES                            | Requires platform state                            |
| `governance_history`          | --                     | YES                            | Requires platform state                            |
| `agent_metrics`               | --                     | YES                            | Requires production data                           |
| `agent_metrics_compare`       | --                     | YES                            | Requires production data                           |
| `agent_metrics_by_consumer`   | --                     | YES                            | Requires production data                           |
| `agent_logs`                  | --                     | YES                            | Requires production data                           |
| `agent_errors`                | --                     | YES                            | Requires production data                           |
| `agent_health`                | --                     | YES                            | Requires production data                           |
| `agent_versions`              | --                     | YES                            | Requires platform state                            |
| `agent_rollback`              | --                     | YES                            | Requires platform state                            |
| `agent_deprecate`             | --                     | YES                            | Requires platform state                            |
| `agent_suspend`               | --                     | YES                            | Requires platform state                            |
| `agent_resume`                | --                     | YES                            | Requires platform state                            |
| `budget_status`               | --                     | YES                            | Requires platform state                            |
| `budget_breakdown`            | --                     | YES                            | Requires platform state                            |
| `cost_estimate`               | YES                    | also                           | Can estimate locally from historical data          |

### Recommended kailash-py MCP Tool Scope

**20 SDK-layer MCP tools** organized by CO phase:

**Discovery (6 tools):**

1. `catalog_search` -- Search local + optional remote catalog
2. `catalog_describe` -- Full agent detail
3. `catalog_schema` -- I/O JSON Schema
4. `catalog_deps` -- Dependency graph
5. `catalog_check_compatibility` -- Schema compatibility check
6. `catalog_list_by_capability` -- Capability-based search

**Building (4 tools):** 7. `scaffold_agent` -- Generate agent boilerplate + manifest 8. `scaffold_composite` -- Generate composite boilerplate 9. `validate_agent_code` -- Introspect and validate agent class 10. `validate_composition` -- DAG, schema, cost validation

**Testing (3 tools):** 11. `local_test_run` -- Single agent local test 12. `local_test_suite` -- Multi-case local test 13. `cost_estimate` -- Cost projection from historical data

**Deployment (3 tools):** 14. `deploy_agent` -- POST manifest to CARE Platform 15. `deploy_composite` -- POST composite to CARE Platform 16. `deploy_status` -- GET deployment status

**Application (4 tools -- thin HTTP clients):** 17. `app_register` -- POST application registration 18. `app_status` -- GET application status 19. `app_request_agent` -- POST agent grant request 20. `app_list_mine` -- GET developer's applications

The Application tools (17-20) are HTTP client wrappers. They require a CARE Platform instance, but they belong in the SDK because the developer invokes them from the COC conversation. The SDK is the client; the platform is the server.

### Gap Analysis: Brief vs Recommended Scope

| Brief P2 Tool      | In Recommended Scope | Notes |
| ------------------ | -------------------- | ----- |
| `catalog_search`   | YES                  |       |
| `catalog_describe` | YES                  |       |
| `catalog_schema`   | YES                  |       |
| `catalog_deps`     | YES                  |       |
| `deploy_agent`     | YES                  |       |
| `deploy_status`    | YES                  |       |
| `app_register`     | YES                  |       |
| `app_status`       | YES                  |       |

**12 tools missing from the brief:**

- `catalog_check_compatibility` (listed in brief text but not in the 8 tool list)
- `catalog_list_by_capability`
- `scaffold_agent`
- `scaffold_composite`
- `validate_agent_code`
- `validate_composition`
- `local_test_run`
- `local_test_suite`
- `cost_estimate`
- `deploy_composite`
- `app_request_agent`
- `app_list_mine`

**Recommendation**: Expand P2 from 8 tools to 20. The additional 12 tools are essential for covering the Implement and Validate CO phases. Without them, a developer building a new agent must leave the COC conversation for scaffolding, validation, and testing -- violating the first principle.

---

## 4. COC Developer Experience Flow

### Scenario: Building a "Market Analyzer" Agent

A developer is building a market analysis agent using kailash-py + CARE Platform. They are in a COC session (Claude Code with kailash-py COC template).

#### Step 1: Discovery -- "What market analysis agents already exist?"

```
Developer: "I need to build a market analysis pipeline that fetches market data,
           calculates risk metrics, and generates reports."

COC action: catalog_search(query="market analysis", capabilities=["market_research"])
            catalog_search(query="risk calculation", capabilities=["risk_analysis"])
            catalog_search(query="report generation", capabilities=["document_generation"])
```

| What Happens                       | MCP Tool           | Deliverable | Conversation Exit? |
| ---------------------------------- | ------------------ | ----------- | ------------------ |
| Search catalog for existing agents | `catalog_search`   | P2          | NO                 |
| Get details on found agents        | `catalog_describe` | P2          | NO                 |
| Get I/O schemas                    | `catalog_schema`   | P2          | NO                 |

**Result**: COC finds a `risk-scorer` agent (existing) and a `report-generator` agent (existing). No market data fetcher exists.

#### Step 2: Compatibility Check -- "Can these agents wire together?"

```
COC action: catalog_check_compatibility(
              output_schema=risk_scorer_output,
              input_schema=report_generator_input
            )
```

| What Happens               | MCP Tool                      | Deliverable                           | Conversation Exit? |
| -------------------------- | ----------------------------- | ------------------------------------- | ------------------ |
| Check schema compatibility | `catalog_check_compatibility` | P2/P3                                 | NO                 |
| Validate DAG is acyclic    | `validate_composition`        | P3 (as MCP tool -- CURRENTLY MISSING) | **YES -- GAP**     |

**Gap identified**: P3 provides `validate_dag` as a Python function but there is no MCP tool wrapping it. The developer or COC must run Python code directly.

#### Step 3: Plan -- "Here's what I need to build"

```
Developer approves plan:
  - BUILD: market-data-fetcher (new agent)
  - REUSE: risk-scorer (existing)
  - REUSE: report-generator (existing)
  - COMPOSE: market-analyzer (composite of all three)
```

| What Happens              | MCP Tool        | Deliverable                              | Conversation Exit? |
| ------------------------- | --------------- | ---------------------------------------- | ------------------ |
| Estimate composition cost | `cost_estimate` | P3/P6 (as MCP tool -- CURRENTLY MISSING) | **YES -- GAP**     |

#### Step 4: Register Application

```
COC action: app_register(
              name="market-analyzer",
              description="Market analysis pipeline for portfolio team",
              agents_requested=["risk-scorer", "report-generator"],
              budget={"monthly": 200},
              justification="Portfolio rebalancing requires automated market analysis"
            )
```

| What Happens          | MCP Tool       | Deliverable | Conversation Exit? |
| --------------------- | -------------- | ----------- | ------------------ |
| Register application  | `app_register` | P2          | NO                 |
| Check approval status | `app_status`   | P2          | NO                 |

#### Step 5: Scaffold New Agent

```
COC action: scaffold_agent(
              name="market-data-fetcher",
              capabilities=["market_research"],
              input_schema={"query": "string", "market": "string"},
              output_schema={"data": "array", "timestamp": "string"},
              tools=["http_get"]
            )
```

| What Happens               | MCP Tool           | Deliverable            | Conversation Exit? |
| -------------------------- | ------------------ | ---------------------- | ------------------ |
| Generate agent boilerplate | `scaffold_agent`   | -- (CURRENTLY MISSING) | **YES -- GAP**     |
| Generate kaizen.toml       | (part of scaffold) | P1                     | --                 |

**Gap identified**: No `scaffold_agent` MCP tool. COC must generate files manually (error-prone, convention drift risk).

#### Step 6: Implement Agent

COC writes the agent code using Kaizen patterns. This is standard COC code generation -- no special MCP tool needed. COC uses its Layer 2 context (kailash-py skills) to generate correct `BaseAgent` subclass code.

| What Happens            | MCP Tool              | Deliverable                         | Conversation Exit? |
| ----------------------- | --------------------- | ----------------------------------- | ------------------ |
| Write agent Python code | (COC code generation) | --                                  | NO                 |
| Validate agent code     | `validate_agent_code` | P1 introspect (MISSING MCP wrapper) | **YES -- GAP**     |

#### Step 7: Local Testing

```
COC action: local_test_run(
              module_path="agents/market_data_fetcher.py",
              class_name="MarketDataFetcher",
              input_data={"query": "AAPL", "market": "US"}
            )
```

| What Happens      | MCP Tool           | Deliverable            | Conversation Exit? |
| ----------------- | ------------------ | ---------------------- | ------------------ |
| Run agent locally | `local_test_run`   | -- (CURRENTLY MISSING) | **YES -- GAP**     |
| Run test suite    | `local_test_suite` | -- (CURRENTLY MISSING) | **YES -- GAP**     |

#### Step 8: Deploy

```
COC action: deploy_agent(manifest_path="agents/market-data-fetcher/kaizen.toml")
            deploy_status("market-data-fetcher")
```

| What Happens            | MCP Tool        | Deliverable | Conversation Exit? |
| ----------------------- | --------------- | ----------- | ------------------ |
| Deploy to CARE Platform | `deploy_agent`  | P2          | NO                 |
| Check status            | `deploy_status` | P2          | NO                 |

#### Step 9: Deploy Composite

```
COC action: deploy_composite(manifest_path="pipelines/market-analyzer/kaizen.toml")
```

| What Happens     | MCP Tool           | Deliverable                                        | Conversation Exit? |
| ---------------- | ------------------ | -------------------------------------------------- | ------------------ |
| Deploy composite | `deploy_composite` | -- (CURRENTLY MISSING, `deploy_agent` may suffice) | PARTIAL GAP        |

### Flow Summary

| Step | Description      | Forces Exit? | Missing Tool                         |
| ---- | ---------------- | ------------ | ------------------------------------ |
| 1    | Discovery        | NO           | --                                   |
| 2    | Compatibility    | YES          | `validate_composition` MCP wrapper   |
| 3    | Cost estimation  | YES          | `cost_estimate` MCP wrapper          |
| 4    | App registration | NO           | --                                   |
| 5    | Scaffold         | YES          | `scaffold_agent`                     |
| 6    | Implementation   | NO           | --                                   |
| 7    | Local testing    | YES          | `local_test_run`, `local_test_suite` |
| 8    | Deploy agent     | NO           | --                                   |
| 9    | Deploy composite | PARTIAL      | `deploy_composite`                   |

**Conversation exits**: 4 out of 9 steps force the developer out of the COC conversation. This violates the first principle.

---

## 5. Institutional Knowledge Gaps

### 5.1 Design Decisions Requiring SDK-Level Codification

The following decisions from the Aegis architecture journal contain institutional knowledge that must become SDK-level enforcement in kailash-py, not just documentation.

| Decision                                 | Knowledge                                                                      | Codification Method                                                                                                                  |
| ---------------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| Decision 2: Tool agents are singletons   | Agent identity is ONE instance shared across consumers                         | `AgentManifest` must have a unique `name` field. Registry enforces uniqueness. No "copy" or "clone" API.                             |
| Decision 3: Per-invocation authority     | Effective authority = intersection of caller constraints and agent constraints | `eatp.constraints.evaluator.evaluate()` must implement intersection, not union. Test golden files must verify intersection behavior. |
| Decision 4: Application as policy holder | Applications hold invocation policies, not agent ownership                     | `AppManifest` schema must NOT have an `owned_agents` field. `agents_requested` is the correct field name.                            |
| Decision 6: Operating Envelope           | Governance unit is the project, not the agent                                  | `AppManifest.budget` is project-level. Individual agent budget is derived, not declared.                                             |
| Decision 7: Application-first access     | Access is application-scoped, time-bound, justification-required               | `AppManifest` must have `duration` and `justification` as required fields (not optional).                                            |

### 5.2 Conventions Requiring Codification

| Convention                                           | Current State                             | Required Codification                                                                                    |
| ---------------------------------------------------- | ----------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Manifest format is TOML, not YAML or JSON            | Brief states TOML                         | Validation must reject non-TOML. `AgentManifest.from_file()` must enforce `.toml` extension.             |
| `@dataclass` not Pydantic for data models            | EATP rule exists                          | P1 brief says "Pydantic" -- must be corrected. Rule enforcement via hook.                                |
| Posture values are lowercase strings                 | EATP TrustPosture uses lowercase `.value` | Manifest `suggested_posture` must validate against `TrustPosture` enum values.                           |
| MCP tool names use `snake_case` with category prefix | Journal convention                        | Must be codified as a rule if kailash-py adopts it.                                                      |
| Budget uses `Decimal`, never `float`                 | Brief specifies                           | Hook or linter rule needed for files in `budget/` or `governance/` directories.                          |
| Fail-closed on unknown state                         | EATP convention                           | Every `match`/`if-elif` on posture or constraint state must have explicit default that raises or denies. |

### 5.3 Anti-Patterns the SDK Must Prevent

| Anti-Pattern                                   | Why It's Dangerous                   | Enforcement                                                                                     |
| ---------------------------------------------- | ------------------------------------ | ----------------------------------------------------------------------------------------------- |
| `constraint_a.update(constraint_b)` (union)    | Expands authority beyond delegation  | Constraint class must not have `update()` method. Provide `intersect()` only.                   |
| `machine.set_posture(agent, DELEGATED)` bypass | Skips all guards for posture upgrade | `set_posture()` should be `_set_posture()` (private) or require a special `InitializationToken` |
| `float(budget_amount)`                         | Precision loss on financial data     | Linter rule or `__init__` validation rejecting float input                                      |
| `except Exception: pass` in trust code         | Silently ignores trust violations    | Already in `rules/no-stubs.md` but needs explicit enforcement in trust-plane code               |
| Schema compatibility via `==` (exact match)    | Rejects valid structural subtypes    | `check_schema_compatibility` must use structural subtyping, not equality                        |
| Agent manifest without governance section      | Deploys without constraint metadata  | `AgentManifest` must require `governance` section (not optional)                                |

---

## 6. Anti-Amnesia Recommendations

### 6.1 CLAUDE.md / Rules Additions

**New rule file: `.claude/rules/tool-agent-conventions.md`**

Scope: `packages/kailash-kaizen/src/kaizen/manifest/**`, `packages/kailash-kaizen/src/kaizen/composition/**`, `packages/kailash-kaizen/src/kaizen/deploy/**`

Must contain:

- Manifest format is TOML (`kaizen.toml`, `app.toml`)
- Data models use `@dataclass` with `to_dict()`/`from_dict()` (NOT Pydantic)
- `governance` section is REQUIRED in agent manifests (not optional)
- `suggested_posture` must validate against `eatp.postures.TrustPosture` enum values
- `agents_requested` (not `owned_agents`) in application manifests
- `duration` and `justification` are required fields in application manifests
- MCP tool names use `snake_case` with category prefix (`catalog_*`, `deploy_*`, `app_*`)

**New rule file: `.claude/rules/budget-precision.md`**

Scope: `**/budget/**`, `**/cost/**`, `**/governance/cost*`

Must contain:

- All monetary values use `decimal.Decimal`, never `float`
- `math.isfinite()` equivalent check on all Decimal inputs (reject NaN/Infinity via `Decimal.is_finite()`)
- Thread safety via `threading.Lock` for single-process, database atomics for multi-process
- Budget tracking is SUBTRACTIVE only (consume from allocation, never add to allocation outside of top-level grant)

**CLAUDE.md addition** (Critical Execution Rules section):

```python
# Agent manifests use @dataclass, NOT Pydantic
# (EATP SDK convention applies to all data types)
@dataclass
class AgentManifest:
    name: str
    module: str
    ...
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentManifest: ...

# Constraint intersection, NEVER union
effective = caller_constraints.intersect(agent_constraints)
# NEVER: effective = caller_constraints.update(agent_constraints)

# Budget is Decimal
from decimal import Decimal
budget = BudgetTracker(allocated=Decimal("500.00"))
# NEVER: budget = BudgetTracker(allocated=500.0)
```

### 6.2 Validation Tools for Convention Drift Prevention

| Tool                         | Purpose                                                       | Implementation                                      |
| ---------------------------- | ------------------------------------------------------------- | --------------------------------------------------- |
| `validate_manifest` hook     | Reject `kaizen.toml` files that are missing required sections | Pre-commit hook checking TOML structure             |
| `check_dataclass_convention` | Detect Pydantic usage in EATP/Kaizen manifest code            | Grep hook for `from pydantic` in scoped directories |
| `check_budget_precision`     | Detect `float` usage in budget/cost code                      | Grep hook for `float(` in budget-scoped files       |
| `check_posture_fail_closed`  | Detect `if/elif` chains on TrustPosture without `else: raise` | AST analysis or grep for posture switch patterns    |

### 6.3 Test Fixtures and Golden Files

| Golden File                                              | Purpose                                               | Location                                  |
| -------------------------------------------------------- | ----------------------------------------------------- | ----------------------------------------- |
| `tests/fixtures/manifests/valid_agent.toml`              | Reference manifest with all required sections         | `packages/kailash-kaizen/tests/fixtures/` |
| `tests/fixtures/manifests/valid_app.toml`                | Reference application manifest                        | Same                                      |
| `tests/fixtures/manifests/invalid_no_governance.toml`    | Must be rejected by parser                            | Same                                      |
| `tests/fixtures/manifests/invalid_pydantic_posture.toml` | Invalid posture value                                 | Same                                      |
| `tests/fixtures/schemas/compatible_pair.json`            | Two schemas that are structurally compatible          | `packages/kailash-kaizen/tests/fixtures/` |
| `tests/fixtures/schemas/incompatible_pair.json`          | Two schemas that are NOT compatible                   | Same                                      |
| `tests/fixtures/composition/acyclic_dag.json`            | Valid composition DAG                                 | Same                                      |
| `tests/fixtures/composition/cyclic_dag.json`             | Invalid composition (cycle)                           | Same                                      |
| `tests/fixtures/posture/transition_sequence.json`        | Valid posture transition sequence                     | `packages/eatp/tests/fixtures/`           |
| `tests/fixtures/posture/invalid_downgrade.json`          | Rejected posture downgrade                            | Same                                      |
| `tests/fixtures/budget/decimal_precision.json`           | Budget operations with Decimal precision verification | `packages/kailash-kaizen/tests/fixtures/` |

### 6.4 Anti-Amnesia Hook Injection

The existing `user-prompt-rules-reminder.js` hook fires on every user message and re-injects critical rules. For tool agent work, it should inject:

```
[TOOL-AGENT] Manifests use @dataclass (NOT Pydantic). Constraints use intersection (NOT union).
Budget uses Decimal (NOT float). Posture checks must fail-closed.
```

This one-line reminder survives context compression and prevents the four most likely amnesia failures.

---

## 7. Consolidated Recommendations

### 7.1 Brief Corrections

1. **P1**: Change "Pydantic model" to "@dataclass" for `AgentManifest`, `AppManifest`, `GovernanceManifest`. This aligns with EATP SDK convention (`rules/eatp.md`).

2. **P2**: Expand from 8 MCP tools to 20 (see Section 3). The 12 missing tools cover the Implement and Validate CO phases, which are currently entirely unserviced.

3. **P5**: The product brief lists `PostureStateMachine`, `TransitionGuard`, `PostureEvidence`, and `EvaluationResult` as "types not yet in the EATP SDK." Analysis shows that `PostureStateMachine`, `TransitionGuard`, `TransitionResult`, `PostureTransitionRequest`, `PostureConstraints`, and `PostureResult` ALREADY EXIST in `packages/eatp/src/eatp/postures.py`. What is missing is `PostureEvidence` (evidence record for posture change justification) and the specific `EvaluationResult` structure described in the brief. P5 scope should be refined to: extend the existing state machine with evidence-based transitions, not reimplement it.

### 7.2 Architecture Decisions for kailash-py

1. **MCP server location**: The catalog MCP server belongs in `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/`, extending the existing `KaizenMCPServer` pattern. It is NOT a new package.

2. **Manifest location**: `packages/kailash-kaizen/src/kaizen/manifest/` (new module). Contains `AgentManifest`, `AppManifest`, `GovernanceManifest` as `@dataclass` types with TOML parsing.

3. **Composition location**: `packages/kailash-kaizen/src/kaizen/composition/` (new module). Contains `validate_dag`, `check_schema_compatibility`, `estimate_cost`.

4. **Budget location**: `packages/kailash-kaizen/src/kaizen/governance/budget.py` (new file in existing governance module). Contains `BudgetTracker` with `Decimal` precision.

5. **Posture evidence location**: `packages/eatp/src/eatp/postures.py` (extend existing file). Add `PostureEvidence` dataclass and evidence-based guard.

6. **Aggregation location**: `packages/kailash-dataflow/src/dataflow/query/` (new module). Contains `count_by`, `sum_by`, `aggregate` functions that generate SQL across backends.

### 7.3 Implementation Priority Reorder

The brief's priority order (P1 through P6) should be adjusted based on dependency analysis:

| Order | Deliverable                                   | Rationale                                                 |
| ----- | --------------------------------------------- | --------------------------------------------------------- |
| 1     | P1: Agent Manifest                            | Foundation -- all other deliverables reference manifests  |
| 2     | P5: Posture Evidence (extend existing)        | Small scope (existing code), unblocks P2 governance tools |
| 3     | P3: Composite Validation                      | Required before P2 MCP tools can wrap validation          |
| 4     | P6: Budget Tracking                           | Required before P2 MCP tools can expose cost estimation   |
| 5     | P2: MCP Catalog Server (expanded to 20 tools) | Depends on P1, P3, P5, P6 for functions to wrap           |
| 6     | P4: DataFlow Aggregation                      | Independent, lowest coupling to other deliverables        |

### 7.4 COC Layer Mapping

| COC Layer                 | Tool Agent Implementation                                                                                                                                                                        |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Layer 1: Intent**       | New agent: `tool-agent-specialist` -- routes tool agent questions to manifest, composition, posture, budget specialists                                                                          |
| **Layer 2: Context**      | New skill: `kaizen-manifest` (manifest format, validation rules). New skill: `care-composition` (DAG patterns, schema compatibility). Extend skill: `eatp-posture` (evidence-based transitions). |
| **Layer 3: Guardrails**   | New rule: `tool-agent-conventions.md`. New rule: `budget-precision.md`. Anti-amnesia hook extension for tool agent conventions.                                                                  |
| **Layer 4: Instructions** | Workspace phases already apply. P2 MCP tools enable CO phase coverage.                                                                                                                           |
| **Layer 5: Learning**     | After implementation, capture manifest validation patterns as instincts. Capture "Pydantic vs dataclass" correction as a high-confidence instinct.                                               |

---

## 8. Risk Summary

| Risk                                      | Severity                        | Mitigation                               |
| ----------------------------------------- | ------------------------------- | ---------------------------------------- |
| Brief says Pydantic, rules say @dataclass | HIGH (convention conflict)      | Correct brief before implementation      |
| P2 scopes 8 tools, 20 needed              | HIGH (CO phase gaps)            | Expand P2 scope                          |
| P5 reimplements existing code             | MEDIUM (wasted effort)          | Refine P5 to extend, not reimplement     |
| No scaffold/test MCP tools                | HIGH (forces conversation exit) | Add scaffold_agent, local_test_run to P2 |
| Budget float vs Decimal                   | MEDIUM (precision loss)         | New rule file + hook enforcement         |
| Manifest introspection security           | MEDIUM (code execution risk)    | Restrict module paths, sandbox imports   |
| MCP tool naming divergence from spec      | LOW (future interop risk)       | Define names in CARE spec, not in SDK    |

---

## Appendix A: Existing Code Inventory

Components that ALREADY EXIST in kailash-py and must be reused (not reimplemented):

| Component             | Location                                                                | Relevance                                          |
| --------------------- | ----------------------------------------------------------------------- | -------------------------------------------------- |
| `PostureStateMachine` | `packages/eatp/src/eatp/postures.py`                                    | P5 extends this, does not replace it               |
| `TransitionGuard`     | Same                                                                    | P5 adds evidence-based guard to existing system    |
| `TrustPosture` enum   | Same                                                                    | All manifests validate against this                |
| `EvaluationResult`    | `packages/eatp/src/eatp/constraints/evaluator.py`                       | Constraint evaluation already exists               |
| `KaizenMCPServer`     | `packages/kailash-kaizen/src/kaizen/mcp/builtin_server/server.py`       | P2 MCP server extends this                         |
| `EATP MCP Server`     | `packages/eatp/src/eatp/mcp/server.py`                                  | Reference pattern for MCP server implementation    |
| `AgentRegistration`   | `packages/kailash-kaizen/src/kaizen/agents/registry.py`                 | P1 manifest aligns with registration metadata      |
| `AggregateNode`       | `packages/kailash-dataflow/src/dataflow/nodes/aggregate_operations.py`  | P4 may extend existing aggregation, not replace it |
| `BaseAgent`           | `packages/kailash-kaizen/src/kaizen/core/base_agent.py`                 | All agents inherit from this                       |
| Cost estimator        | `packages/kailash-kaizen/src/kaizen/trust/governance/cost_estimator.py` | P6 may extend existing cost infrastructure         |

## Appendix B: Complete MCP Tool Specification (SDK-Layer)

For reference, the complete 20-tool MCP specification for kailash-py:

```
# Discovery (6 tools)
catalog_search(query: str, capabilities?: list[str], type?: str, status?: str) -> list[AgentSummary]
catalog_describe(agent_name: str) -> AgentDetail
catalog_schema(agent_name: str) -> dict  # JSON Schema
catalog_deps(agent_name: str) -> dict  # Dependency graph
catalog_check_compatibility(output_schema: dict, input_schema: dict) -> CompatibilityResult
catalog_list_by_capability(capability_tags: list[str]) -> list[AgentSummary]

# Building (4 tools)
scaffold_agent(name: str, capabilities: list[str], input_schema: dict, output_schema: dict, tools?: list[str]) -> ScaffoldResult
scaffold_composite(name: str, steps: list[dict], new_agents?: list[dict]) -> ScaffoldResult
validate_agent_code(module_path: str, class_name: str) -> ValidationResult
validate_composition(composition: dict) -> ValidationResult  # DAG + schema + cost

# Testing (3 tools)
local_test_run(module_path: str, class_name: str, input_data: dict) -> TestResult
local_test_suite(module_path: str, test_cases: list[dict]) -> TestSuiteResult
cost_estimate(composition: dict, expected_volume?: int) -> CostEstimate

# Deployment (3 tools)
deploy_agent(manifest_path_or_content: str) -> DeployResult
deploy_composite(manifest_path_or_content: str) -> DeployResult
deploy_status(agent_name: str) -> StatusResult

# Application (4 tools -- HTTP clients to CARE Platform)
app_register(name: str, description: str, agents_requested: list[str], budget: dict, justification: str) -> AppResult
app_status(app_name: str) -> AppStatusResult
app_request_agent(app_name: str, agent_name: str, justification: str) -> RequestResult
app_list_mine() -> list[AppSummary]
```
