# Tool Agent Support — kailash-py Implementation Brief

## Product

The CARE Platform (Terrene Foundation, open-source) needs tool agent capabilities to support the Shared Capability pattern described in the CARE specification. kailash-py is the pure Python SDK that CARE Platform uses. These deliverables are the Python-native equivalents of what kailash-rs provides for Aegis — same concepts, independent implementation, open-source (Apache 2.0).

## Objectives

- Provide Kaizen agent manifest support (`kaizen.toml` / `app.toml`) for CARE Platform deployments
- Implement MCP catalog server for tool agent discovery (CO methodology requires MCP-first)
- Add composite agent validation utilities (cycle detection, schema compatibility)
- Extend DataFlow with aggregation query patterns for analytics
- Provide pure-Python posture state machine (reference implementation for EATP)

## Tech Stack

- Backend: kailash-py pure Python SDK (Terrene Foundation, Apache 2.0)
- Packages: kailash-dataflow, kailash-kaizen, kailash-nexus, kailash-mcp, eatp
- Testing: pytest, 3-tier (NO MOCKING in Tier 2-3)

## Context

Aegis (Integrum, proprietary) has implemented the tool agent architecture using kailash-rs. CARE Platform (Terrene Foundation, open-source) needs equivalent capabilities in kailash-py. The specifications are the same (CARE, EATP, CO standards), but the implementations are independent:

| Layer | Aegis (Integrum) | CARE Platform (Terrene) |
|-------|-------------------|------------------------|
| SDK | kailash-rs (Rust + PyO3) | kailash-py (pure Python) |
| License | Proprietary | Apache 2.0 |
| Models | Defined in Aegis codebase | Defined in CARE Platform |
| Runtime | Rust Runtime | LocalRuntime / AsyncLocalRuntime |

## Deliverables

### P1: Kaizen — Agent Deployment Manifest (1 week)

**Package**: `kailash-kaizen`

Agent manifest parsing and introspection for `kaizen.toml`:

```toml
[agent]
name = "market-analyzer"
module = "agents.market_analyzer"
class = "MarketAnalyzer"

[agent.metadata]
description = "Analyzes market data"
capabilities = ["market_research", "risk_analysis"]

[agent.capabilities]
tools = ["search_market_data", "calculate_risk"]
supported_models = ["claude-sonnet-4-20250514", "gpt-4o"]

[governance]
purpose = "Market data analysis for portfolio rebalancing"
risk_level = "medium"
data_access_needed = ["market_data"]
suggested_posture = "supervised"
```

Implement:
1. `kaizen.manifest.AgentManifest` — Pydantic model for `kaizen.toml` parsing
2. `kaizen.manifest.AppManifest` — Pydantic model for `app.toml` (application registration)
3. `kaizen.manifest.GovernanceManifest` — Governance metadata section
4. `kaizen.deploy.introspect_agent(module, class_name)` — Reads Agent class, extracts Signature/tools/A2A card/capabilities into manifest-compatible dict
5. `kaizen.deploy.deploy(manifest, target_url, api_key)` — HTTP client that POSTs registration to CARE Platform API

### P2: MCP Catalog Server — Tool Agent Discovery (2 weeks)

**Package**: `kailash-mcp`

MCP server implementing the CO-required catalog surface. This is the primary interface for developers using COC (Cognitive Orchestration for Codegen).

Implement an MCP server with these tools (P1 subset of 40+ total):

**Discovery:**
```python
catalog_search(query, capabilities?, type?, status?)
catalog_describe(agent_name)
catalog_schema(agent_name)     # Input/output JSON Schema
catalog_deps(agent_name)       # Dependency graph for composites
```

**Deployment:**
```python
deploy_agent(manifest_path_or_content)
deploy_status(agent_name)
```

**Application:**
```python
app_register(name, description, agents_requested[], budget, justification)
app_status(app_name)
```

The MCP server wraps CARE Platform API calls. Built with `kailash-mcp` server patterns.

### P3: Composite Agent Validation Utilities (1 week)

**Package**: `kailash-kaizen`

SDK-level validation for composite agent manifests:

1. `kaizen.composition.validate_dag(agents: list[dict]) -> ValidationResult` — Cycle detection via BFS/DFS
2. `kaizen.composition.check_schema_compatibility(output_schema, input_schema) -> CompatibilityResult` — Verify agent A output pipes to agent B input
3. `kaizen.composition.estimate_cost(composition, historical_data) -> CostEstimate` — Cost projection from sub-agent history

### P4: DataFlow Aggregation Query Patterns (1 week)

**Package**: `kailash-dataflow`

Analytics queries that auto-generated CRUD nodes don't provide:

1. `dataflow.query.count_by(model, group_by_field, filter?)` — COUNT(*) GROUP BY
2. `dataflow.query.sum_by(model, sum_field, group_by_field, filter?)` — SUM GROUP BY
3. `dataflow.query.aggregate(model, aggregations: list, filter?)` — Generic aggregation

Must work across PostgreSQL, SQLite, and MongoDB backends.

### P5: EATP Posture State Machine — Reference Implementation (1 week)

**Package**: `eatp`

Pure-Python reference implementations (not stubs) for types not yet in the EATP SDK:

1. `eatp.posture.PostureStateMachine` — 5-posture state machine with valid transitions, fail-closed on unknown state
2. `eatp.posture.TransitionGuard` — Validates posture transitions against evidence requirements
3. `eatp.posture.PostureEvidence` — Evidence record for posture change justification (observation count, success rate, time at current posture)
4. `eatp.posture.EvaluationResult` — Structured result from posture evaluation (approved/denied/deferred with rationale)

These are the canonical open-source implementations that Aegis's `aegis.compat.trust_plane` shims should eventually align with.

### P6: Budget Tracking Utilities (1 week)

**Package**: `kailash-kaizen` or `kailash-dataflow`

Python-native budget tracking for CARE Platform:

1. `BudgetTracker(allocated, consumed=0)` — Track budget with Decimal precision
2. `reserve(amount) -> bool` — Check-and-reserve (thread-safe via threading.Lock)
3. `record(actual_amount)` — Adjust consumed after provider response
4. `remaining() -> Decimal` — Current remaining budget
5. `check(estimated_cost) -> dict` — Returns `{allowed, remaining, monthly, consumed}`

Uses `threading.Lock` for thread safety (adequate for Python's single-process model). For multi-process, callers use database-level atomic updates.

## Priority

| Priority | Item | Blocks CARE Platform | Timeline |
|----------|------|---------------------|----------|
| P1 | Agent manifest | Developer deployment workflow | 1 week |
| P2 | MCP catalog server | COC-first developer experience | 2 weeks |
| P3 | Composite validation | Composite governance | 1 week |
| P4 | DataFlow aggregation | Scalable analytics | 1 week |
| P5 | EATP posture state machine | Reference posture management | 1 week |
| P6 | Budget tracking | Application-level budgets | 1 week |

## Constraints

- All code Apache 2.0 (Terrene Foundation)
- No dependency on kailash-rs or Aegis — fully independent implementation
- Must work with pure Python runtime (LocalRuntime / AsyncLocalRuntime)
- Must maintain parity with CARE specification (not Aegis-specific extensions)
- Follow existing kailash-py patterns (see `CLAUDE.md`)

## Reference

- CARE specification: `~/repos/terrene/care/`
- Aegis tool agent architecture (reference, not dependency): `~/repos/dev/aegis/workspaces/tool-agents/`
- Aegis architecture journal: `~/repos/dev/aegis/workspaces/tool-agents/01-analysis/00-architecture-journal.md`
- kailash-rs equivalent brief: `~/repos/kailash/kailash-rs/workspaces/tool-agent-support/briefs/01-product-brief.md`
