---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T14:30:00Z
author: agent
session_turn: 2
project: kailash-ml
topic: Protocol surface area and cross-workspace contract risks
phase: analyze
tags:
  [
    ml,
    protocols,
    kailash-align,
    cross-workspace,
    contracts,
    dependency-ordering,
  ]
---

# Risk: Protocol Surface and Cross-Workspace Contracts Are Underspecified

## Context

Red Team Round 2 examined cross-workspace integration points for kailash-ml. Three packages depend on kailash-ml-protocols (kailash-ml, kailash-kaizen, kailash-align), and one package (kailash-align) depends on kailash-ml's ModelRegistry via class inheritance. The protocols package is Phase 0 — it must ship before any engine implementation begins. Yet the exact protocol surface was not fully specified until R2.

## The Risks

### 1. Protocol surface locked too early or too late

If protocols ship before the engines are designed in detail, methods may be missing or wrong. If protocols ship after engine implementation starts, the engines will define ad-hoc interfaces that diverge from what the protocol eventually specifies.

The R2 analysis defines a minimum viable surface: 3 methods on MLToolProtocol, 4 methods on AgentInfusionProtocol, and 3 shared dataclasses (FeatureSchema, ModelSignature, MetricSpec). This is conservative — deliberately excluding `trigger_retrain()` which was in the R1 spec because retraining is too complex for a protocol call. Conservative is correct for protocols; additive changes are non-breaking.

### 2. ModelRegistry inheritance creates a hidden contract

AdapterRegistry extends ModelRegistry via class inheritance. This means AdapterRegistry's correctness depends on ModelRegistry's:

- Constructor signature (what parameters does `__init__` accept?)
- Public method signatures (what does `register_model` look like?)
- Internal state access (does AdapterRegistry use `self._db`?)
- DataFlow model definitions (what columns does `MLModelVersion` have?)

None of these are covered by kailash-ml-protocols. The protocols package breaks the circular dependency between kailash-ml and kailash-kaizen, but it does NOT protect the kailash-ml -> kailash-align contract. That contract is raw class inheritance — any change to ModelRegistry's internals can break AdapterRegistry.

### 3. MCP platform server cannot discover framework agents

The MCP platform server's `kaizen.list_agents()` tool uses AST scanning of the project source tree. kailash-ml agents installed as a pip package are invisible to this scanner. End users will not see kailash-ml's 6 agents in `kaizen.list_agents()` results. This is not a correctness issue (agents still work when invoked directly) but it undermines the platform server's "single-call project understanding" value proposition.

## Impact Assessment

- **Protocol surface**: HIGH impact if wrong. Protocol changes after release require coordinated updates to 3 packages. Getting the MVP surface right in Phase 0 avoids a painful v1.1 protocol update.
- **ModelRegistry inheritance**: MEDIUM impact. Limited to kailash-align, which has a clear sequential dependency on kailash-ml. Breakage would be caught by kailash-align's integration tests. But it adds fragility to what should be a stable interface.
- **MCP agent discovery**: LOW impact. Workaround exists (static listing in `platform_map()`). Full framework agent discovery is a v2 feature.

## Mitigation

1. **Freeze the protocol MVP surface** as defined in R2 (RT-R2-05) before any engine implementation starts. The surface is intentionally minimal — 7 methods, 3 dataclasses. Future methods can be added without breaking existing consumers.

2. **Document ModelRegistry's public API** as a semi-formal contract. Not a Protocol class (too heavy for this use case) but an explicit list of method signatures that kailash-align depends on. Include an integration test in kailash-align that verifies these signatures exist.

3. **Add `options: dict | None = None` parameter** to all protocol methods from the start. This future-proofs against the most common protocol evolution scenario (adding configuration to an existing method).

## For Discussion

1. R2 removes `trigger_retrain()` from MLToolProtocol because retraining requires complex configuration. But if a Kaizen agent wants to trigger retraining via an MCP tool, what API does it use instead? Is the answer "the agent calls kailash-ml's TrainingPipeline API directly," and if so, does this re-introduce a runtime dependency that the protocol was designed to avoid?

2. If ModelRegistry changes its `__init__` signature during kailash-ml implementation (adding a parameter, changing a default), AdapterRegistry breaks. Should kailash-align use composition instead of inheritance to insulate against this? The trade-off: composition requires explicitly delegating ~5 methods, but eliminates the hidden contract risk.

3. The `options: dict | None = None` parameter for future extensibility is a Google-protobuf-style pattern. Is it appropriate for a Python Protocol that uses structural subtyping, or does it add unnecessary complexity? An alternative: version the Protocol classes (`MLToolProtocol`, `MLToolProtocolV2`) and support multiple versions simultaneously.
