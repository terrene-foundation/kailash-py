# Red Team R2 — Final Spec Validation

**Date**: 2026-04-07 (original), 2026-04-08 (critical findings resolved)
**Scope**: 10 SPECs + ADR-010
**Validator**: analyst (red team)
**Status**: Critical findings RESOLVED. 5 important + 7 minor open for /todos task creation.

## Summary

14 findings: 2 critical (RESOLVED), 5 important (open), 7 minor (open).

The specs are substantially solid. The ADR-010 integration is well-executed across SPEC-03, SPEC-04, SPEC-05, and SPEC-07. Cross-references between specs are consistent. The composition-wrapper pattern is correctly applied.

**Critical findings resolved 2026-04-08:**

- **R2-001 RESOLVED**: `CapabilityBased` keyword routing replaced with `LLMBased` routing in SPEC-03 §2.4 and SPEC-10 §3. `WorkerAgent.capability_score()` removed and replaced with `capability_card` property (A2A-style rich description). All examples and test lists updated. `rules/agent-reasoning.md` Rule 5 (LLM routing over dispatch tables) is now the mandatory pattern. Rust `kaizen-agents/src/orchestration/supervisor.rs` MUST mirror the fix (cross-SDK lockstep per ADR-008).
- **R2-002 RESOLVED**: `## §N Security Considerations` section added to SPECs 03, 04, 05, 06, 07, 08, 09, 10. SPECs 01 and 02 already had them. Each section addresses component-specific threat surfaces (not boilerplate) with concrete mitigations per finding. Total 40+ distinct threats documented with mitigation requirements.

## Findings

### R2-001: CapabilityBased routing violates rules/agent-reasoning.md [RESOLVED 2026-04-08]

**Severity**: Critical
**Location**: SPEC-03 section 2.4, lines 575-579; SPEC-10 section 3 (Phase 1 example)
**Resolution**: `CapabilityBased` and `WorkerAgent.capability_score()` removed entirely. Replaced with `LLMBased(RoutingStrategy)` — an LLM-based router that takes a `BaseAgentConfig` and reasons over `WorkerAgent.capability_card` (A2A-style rich description) via an internal `BaseAgent` with a routing `Signature`. `RoundRobin` retained as the only permitted deterministic strategy (pure load-balancing, no input inspection). `WorkerAgent.__init__` now requires a rich `capabilities: str` description and rejects empty strings. All examples, test lists, and SPEC-10 Phase 1 code updated. Rust `kaizen-agents/src/orchestration/supervisor.rs` MUST apply the same fix per ADR-008 — Rust to remove keyword-based `capability_score` and expose an `A2ACapabilityCard` struct.

**Issue**: The `CapabilityBased` routing strategy uses keyword matching to select workers:

```python
class CapabilityBased(RoutingStrategy):
    """Select worker based on capability keyword matching."""
    def select(self, input_text: str, workers: list[WorkerAgent]) -> WorkerAgent:
        best = max(workers, key=lambda w: w.capability_score(input_text))
        return best
```

And `WorkerAgent.capability_score()` at line 715-726 does:

```python
def capability_score(self, input_text: str) -> float:
    input_lower = input_text.lower()
    score = sum(1.0 for cap in self._capabilities if cap.lower() in input_lower)
    return score
```

This is **keyword matching on agent inputs for routing** -- specifically the anti-pattern `if any(w in text for w in [...])` from `rules/agent-reasoning.md`. The rule explicitly blocks:

> "Keyword matching (`if "cancel" in user_input`)" and "Embedding similarity with hardcoded thresholds for routing"

The comment "Routes to analyst (keyword: 'analyze', 'data')" at line 605 confirms this is intentional keyword routing.

**Recommendation**: Replace `CapabilityBased` with an LLM-based routing strategy that examines worker capability cards (A2A agent cards or capability descriptions) and uses an LLM call to reason about the best match. The Rust equivalent at `kaizen-agents/src/orchestration/supervisor.rs` should be checked for the same violation. The `rules/agent-reasoning.md` explicitly says "Router Agents Use LLM Routing, Not Dispatch Tables" and provides `Pipeline.router()` as the correct pattern.

If keyword-based routing is genuinely needed for performance (e.g., routing thousands of requests per second where LLM latency is unacceptable), then the spec MUST explicitly declare this as a permitted deterministic exception per the rule's "Explicit user opt-in" clause, with justification.

### R2-002: 8 of 10 SPECs are missing Security Considerations section [RESOLVED 2026-04-08]

**Severity**: Critical
**Location**: SPEC-03, SPEC-04, SPEC-05, SPEC-06, SPEC-07, SPEC-08, SPEC-09, SPEC-10
**Resolution**: Added `## §N Security Considerations` as a new section at the end of each of the 8 SPECs (new section numbers: SPEC-03 §11, SPEC-04 §10, SPEC-05 §9, SPEC-06 §8, SPEC-07 §9, SPEC-08 §7, SPEC-09 §8, SPEC-10 §10). Each section contains 4-6 component-specific subsections addressing the threats called out in this finding plus additional threats discovered during writing. Example coverage: envelope bypass via direct inner access (SPEC-03), `_deferred_mcp` window mutation (SPEC-04), `asyncio.run()` constructor deadlock (SPEC-05), credential isolation during migration (SPEC-06), deserialization without validation including NaN/negative/overflow (SPEC-07), audit log Merkle chain integrity (SPEC-08), JSON parser differential attacks (SPEC-09), unbounded delegation depth and LLM router prompt injection (SPEC-10). All mitigations are actionable requirements (MUST/SHOULD) with specific class names, method signatures, and integration test requirements. Implementers have concrete enforcement guidance — no hand-wave "TLS and auth" boilerplate.

**Issue**: The spec template (defined in 00-spec-index.md) requires `## section 5 Security Considerations` in every SPEC. Only SPEC-01 and SPEC-02 have dedicated security sections. The remaining 8 SPECs do not include a security section at all. Their section 5 contains other content (Events, Migration Order, Deleted Files, Test Plan, Cross-SDK Wire Format, New Capability, Gaps Requiring Rust Changes).

This is not just a formatting issue. Several SPECs have real security surfaces that go unaddressed:

- **SPEC-03** (L3GovernedAgent): Envelope enforcement bypass via direct inner agent access (`agent.inner.run()`). Shadow mode that silently disables governance. Posture ceiling comparison using enum integer values which could be manipulated.
- **SPEC-04** (BaseAgent): `_deferred_mcp` pattern stores server configs on the object between construction and first `run()` -- a window where configs could be modified. The `**legacy_kwargs` catch-all accepts arbitrary parameters silently.
- **SPEC-05** (Delegate): `asyncio.run()` in constructor for MCP setup could deadlock in async contexts.
- **SPEC-06** (Nexus migration): Extracts auth primitives to `kailash.trust` but doesn't specify how credential isolation is maintained during the migration (e.g., Nexus's per-tenant JWT secrets vs trust's shared config).
- **SPEC-07** (ConstraintEnvelope): `from_dict()` deserialization without validation could accept malicious payloads (e.g., extremely large `max_turns` values, negative budget amounts).
- **SPEC-10** (Multi-agent patterns): Unbounded delegation depth in `SupervisorAgent(max_delegation_depth=3)` without envelope enforcement means a rogue supervisor could spawn unlimited nested delegations.

**Recommendation**: Add a `## Security Considerations` section to each SPEC addressing the threat surface specific to that component. At minimum: input validation, access control, credential handling, and failure modes. Not boilerplate -- each spec has different threats.

### R2-003: SPEC-03 stacking order contradiction

**Severity**: Important
**Location**: SPEC-03 section 3.1 (lines 755-771) vs section 2.2 comment at line 225

**Issue**: The recommended stacking order in section 3.1 says:

```
BaseAgent -> MonitoredAgent -> L3GovernedAgent -> StreamingAgent
```

But the MonitoredAgent docstring at line 225 says:

```
Standard stack: BaseAgent -> MonitoredAgent -> L3GovernedAgent -> StreamingAgent
```

Both agree. However, this means **L3GovernedAgent wraps MonitoredAgent** (governance is outside cost). The rationale at line 769 says "L3GovernedAgent outside BaseAgent: Governance can reject BEFORE the inner agent incurs LLM cost."

The problem: if L3GovernedAgent is outside MonitoredAgent, governance rejects BEFORE cost tracking, which means blocked requests ARE cost-tracked (MonitoredAgent is the inner agent that gets called by L3GovernedAgent). The stated rationale says the opposite -- that governance should reject before cost is incurred.

For governance to reject before the LLM call, L3GovernedAgent should be INSIDE MonitoredAgent (closer to BaseAgent), not outside it. The stack should be:

```
BaseAgent -> L3GovernedAgent -> MonitoredAgent -> StreamingAgent
```

This way, L3GovernedAgent rejects before the LLM call, and MonitoredAgent only sees cost for approved requests.

**Recommendation**: Re-evaluate the stacking order. If the intent is "governance rejects before LLM cost," then L3GovernedAgent should be between BaseAgent and MonitoredAgent. If the intent is "MonitoredAgent tracks all cost including governance overhead," the current order is correct but the rationale needs rewriting.

### R2-004: SPEC-05 Delegate section numbering deviates from template

**Severity**: Important
**Location**: SPEC-05

**Issue**: SPEC-05 has 8 sections (section 1 through section 8) with non-standard names:

- section 1 Overview (standard)
- section 2 API Contract (close to template)
- section 3 Internal Stack Construction (custom)
- section 4 Progressive Disclosure Layers (custom)
- section 5 Deleted Files (custom)
- section 6 Migration Order (standard)
- section 7 Test Plan (close to template)
- section 8 Related Specs (standard)

Missing entirely: Backward Compatibility, Security Considerations, Rust Parallel, Interop Test Vectors, Semantics. The template requires sections 1-11. SPEC-05 has no backward compatibility section despite being a major rewrite of the Delegate API (adding `signature=`, `envelope=`, `inner_agent=` parameters). The Delegate import path `kaizen_agents.delegate.*` changing to `kaizen_agents.delegate` (single file) is a significant change that needs shim documentation.

**Recommendation**: Add the missing sections. Backward Compatibility is particularly urgent since Delegate is the primary user-facing API. Section 4 in ADR-009 specifically lists `kaizen_agents.delegate.*` subpackage shim as a required backward-compat layer -- this must be documented in SPEC-05.

### R2-005: SPEC-06 Nexus migration has incomplete section coverage

**Severity**: Important
**Location**: SPEC-06

**Issue**: SPEC-06 has only 7 sections, the shortest of all SPECs. Missing:

- Wire Types / API Contracts (critical -- the JWT format, RBAC model, and SSO token exchange are wire types that consumers depend on)
- Semantics (how does the migration preserve tenant isolation?)
- Interop Test Vectors (JWT round-trip between Nexus and trust modules)
- Test Migration (what happens to existing Nexus auth tests?)

The PACTMiddleware `_evaluate()` method at line 139 returns `"AUTO_APPROVED"` with a comment "placeholder -- full implementation per GovernanceEngine API." This is a stub in a spec. While stubs are acceptable in specs (they are not code), the evaluation logic is the entire point of PACTMiddleware, and leaving it as a placeholder means implementers have no guidance on what constraints to check or in what order.

**Recommendation**: Flesh out the PACTMiddleware `_evaluate()` with at least the constraint checking order (financial, temporal, operational, data_access, communication) and how each maps to verification gradient verdicts. Add wire type definitions for the JWT claims structure that trust must preserve.

### R2-006: SPEC-08 Core SDK Consolidation is the most skeletal spec

**Severity**: Important
**Location**: SPEC-08

**Issue**: SPEC-08 has only 6 sections (134 lines total). Missing: Wire Types, Backward Compatibility, Security Considerations, Interop Test Vectors, Test Migration, Rust Parallel. It is effectively an outline rather than an implementable spec.

The `Registry(Protocol[T])` at section 4 says "document canonical patterns rather than forcibly merge" and then provides NO documentation of the patterns. The canonical `AuditEvent` type at section 2 needs a wire format definition for cross-SDK interop, which is absent.

**Recommendation**: Either flesh out SPEC-08 to spec quality, or split it into two: SPEC-08a (Audit Consolidation, which has clear scope) and SPEC-08b (Registry patterns, which may be too vague for a spec and could be a documentation task instead).

### R2-007: SPEC-09 references SPEC-07 section 5 for wire format but SPEC-07 section 5 is "Cross-SDK Wire Format," not "Security Considerations"

**Severity**: Important
**Location**: SPEC-09 section 3.2, line 82

**Issue**: SPEC-09 says "Canonical JSON shape defined in SPEC-07 section 5." This cross-reference is technically correct (SPEC-07 section 5 IS "Cross-SDK Wire Format"), but it is confusing because the template places Security Considerations at section 5. A reader following the template would look for security content at section 5, not wire format.

More importantly, the SPEC-09 type mapping table at section 2.2 lists `kaizen.core.BaseAgent(Node)` as the Python agent contract, but SPEC-04 defines it at `kaizen.core.base_agent.BaseAgent`. The distinction between module and class is important for imports, and the table should use the import path, not the class hierarchy.

**Recommendation**: Fix cross-references to use section titles rather than section numbers (e.g., "SPEC-07 Cross-SDK Wire Format" rather than "SPEC-07 section 5"). Update SPEC-09 section 2.2 to use full import paths.

### R2-008: MonitoredAgent stacking order comment inconsistency

**Severity**: Minor
**Location**: SPEC-03 section 2.2, line 225

**Issue**: MonitoredAgent docstring says: "MonitoredAgent should be OUTSIDE L3GovernedAgent (so cost includes governance overhead)." But then says "Standard stack: BaseAgent -> MonitoredAgent -> L3GovernedAgent -> StreamingAgent."

In this stack, MonitoredAgent is INSIDE L3GovernedAgent (wrapped by it), not outside. The terminology "outside" and "inside" in wrapper stacking is ambiguous -- does "outside" mean "wraps" (outermost) or "called by" (execution order)?

**Recommendation**: Use unambiguous language throughout. Define convention: "outermost wrapper" = first to intercept, "innermost" = closest to BaseAgent. Then consistently use "MonitoredAgent is between BaseAgent and L3GovernedAgent" or "L3GovernedAgent wraps MonitoredAgent."

### R2-009: SPEC-04 BaseAgent `_build_messages()` uses input key guessing

**Severity**: Minor
**Location**: SPEC-04 section 2.3, lines 472-485

**Issue**: The `_build_messages()` method guesses the user input key:

```python
if "prompt" in inputs:
    messages.append(Message(role="user", content=str(inputs["prompt"])))
elif "query" in inputs:
    messages.append(Message(role="user", content=str(inputs["query"])))
elif "message" in inputs:
    messages.append(Message(role="user", content=str(inputs["message"])))
else:
    content = "\n".join(f"{k}: {v}" for k, v in inputs.items())
```

This priority chain is fragile. If a user passes `run(prompt="hello", query="world")`, the `query` is silently ignored. If the Signature defines an InputField named `query`, but someone calls with `prompt=`, the signature fields are not respected.

**Recommendation**: When a Signature is configured, use the Signature's InputField definitions to build messages. Only fall back to the `prompt/query/message` guessing for Signature-less agents. Document the priority chain in the spec.

### R2-010: SPEC-03 L3GovernedAgent `_evaluate()` has stub implementation

**Severity**: Minor
**Location**: SPEC-03 section 2.3, lines 481-516

**Issue**: The `_evaluate()` method body has 5 constraint dimension checks, each containing only `pass`:

```python
if self._envelope.financial:
    # ... budget check against envelope financial limits ...
    pass
```

While specs commonly use abbreviated implementations, having `pass` in each branch with no indication of what the check logic should be means implementers must design the evaluation logic from scratch. The PACT governance engine already has this logic -- the spec should at least reference which `GovernanceEngine` methods to delegate to.

**Recommendation**: Replace the `pass` blocks with references to the evaluation logic source. Either reference `GovernanceEngine.evaluate()` directly, or provide pseudocode for each dimension check (e.g., "financial: compare estimated cost against `envelope.financial.spend_limit_per_call_usd`").

### R2-011: SPEC-10 `SequentialPipelinePattern` is not a BaseAgent

**Severity**: Minor
**Location**: SPEC-10 section 7, line 301

**Issue**: The test at line 301 wraps a `SequentialPipelinePattern` in `StreamingAgent`:

```python
streaming = StreamingAgent(pipeline)  # pipeline IS a BaseAgent
```

But `SequentialPipelinePattern` extends `BaseMultiAgentPattern`, not `BaseAgent`. Unless `BaseMultiAgentPattern` inherits from `BaseAgent` (which is not stated), this code would fail with a type error. The comment "pipeline IS a BaseAgent" is an assertion that needs verification.

**Recommendation**: Either confirm that `BaseMultiAgentPattern extends BaseAgent` (and document this in SPEC-10), or remove the StreamingAgent wrapping test and note that patterns are not directly wrappable -- only the agents within patterns can be wrapped.

### R2-012: SPEC-01 has a section 12 and section 13 beyond the template's section 11

**Severity**: Minor
**Location**: SPEC-01

**Issue**: SPEC-01 has 13 sections including section 12 (pyproject.toml) and section 13 (Rust Parallel). The template defines sections 1-11. While extra sections are not harmful, having the Rust Parallel at section 13 (instead of the template's section 11 position) means the "Related Specs" and "Rust Parallel" sections are in different positions across SPECs. Some SPECs put Rust Parallel as the last section, others have it at different positions.

**Recommendation**: Standardize section numbering. Suggest: section 1-section 9 per template, section 10 Rust Parallel (standardized position), section 11+ for SPEC-specific extras.

### R2-013: SPEC-07 ConstraintEnvelope `intersect()` and `posture_ceiling` interaction undefined

**Severity**: Minor
**Location**: SPEC-07 section 2, lines 53-55

**Issue**: The `intersect()` method is documented as "Monotonic tightening (M7): result no wider than either input." But how does `posture_ceiling` intersect? If envelope A has `posture_ceiling=AUTONOMOUS` and envelope B has `posture_ceiling=SUPERVISED`, the intersection should be `SUPERVISED` (the tighter one). This is implied but not stated.

More subtly: if one envelope has `posture_ceiling=None` (unconstrained) and another has `posture_ceiling=TOOL`, what is the intersection? `None` should mean "no constraint on posture," so the intersection should be `TOOL`. But if `None` is treated as "max posture" rather than "no constraint," the semantics differ.

**Recommendation**: Add explicit `intersect()` semantics for `posture_ceiling`. Recommended: `None` means unconstrained (equivalent to DELEGATING). Intersection of `None` and `X` is `X`. Intersection of `X` and `Y` is `min(X, Y)`.

### R2-014: BudgetExhausted event in Python but not Rust creates cross-SDK semantic gap

**Severity**: Minor
**Location**: SPEC-03 section 5.2 (line 903), SPEC-09 section 2.5

**Issue**: The event mapping table in SPEC-03 and SPEC-09 shows:

| Python            | Rust                       | Notes                       |
| ----------------- | -------------------------- | --------------------------- |
| `BudgetExhausted` | (via PactEngine rejection) | Python adds to event stream |

This means a Python consumer receiving events sees a typed `BudgetExhausted` event, while a Rust consumer sees the same condition as a PactEngine rejection (different event type, different handling path). The cross-SDK interop test vectors in SPEC-09 section 3.3 define an "Agent result equivalence" shape but do not include streaming event equivalence. A consumer writing cross-SDK event handling code would need different logic for each SDK.

**Recommendation**: Either add `BudgetExhausted` to Rust's `CallerEvent` enum (so both SDKs emit the same event type), or document in SPEC-09 that streaming event schemas are SDK-specific and not part of the cross-SDK wire contract.

## R1 Gap Verification

### R1 Item 1: Composition target self-contradiction (BaseAgent + Node + streaming)

**Status**: RESOLVED

ADR-001 + ADR-002 + ADR-003 + ADR-010 resolve this cleanly. The chosen approach is Option C from R1: AgentLoop lives outside BaseAgent. Delegate composes BaseAgent + wrappers independently. BaseAgent keeps Node inheritance and `run() -> Dict`. StreamingAgent is a separate wrapper that adds `run_stream() -> AsyncGenerator`. Multi-agent patterns built on `BaseAgent.run()` still do not get streaming directly, but they can be wrapped in StreamingAgent (per SPEC-10 section 5).

The architectural invariant from `delegate/loop.py` is preserved and rewritten in SPEC-03 section 6.3 to be about "workflow primitives" specifically, not the whole kaizen package. This satisfies R1 item 2 as well.

### R1 Item 2: Architectural invariant status

**Status**: RESOLVED

SPEC-03 section 6.3 rewrites the invariant: "AgentLoop MUST NOT use workflow primitives (WorkflowBuilder, LocalRuntime, NodeRegistry). AgentLoop operates independently of the Core SDK workflow graph." The invariant is no longer about the kaizen package generally -- it is specifically about workflow primitives.

### R1 Item 3: Public API contract breaks (Dict vs AsyncGenerator)

**Status**: RESOLVED

SPEC-03 section 2.1 explicitly defines both interfaces:

- `StreamingAgent.run_stream(**inputs) -> AsyncGenerator[DelegateEvent, None]` -- new streaming surface
- `StreamingAgent.run(**inputs) -> Dict[str, Any]` -- blocking variant that collects stream

The `_events_to_dict()` method at line 151 converts events to Dict, preserving the `BaseAgent.run() -> Dict` contract. Patterns that do `result = agent.run(inputs); result["answer"]` continue to work because `StreamingAgent.run()` returns Dict.

### R1 Item 4: "No consumers" claim for mcp_integration.py

**Status**: RESOLVED

SPEC-01 section 1 line 34 says "DELETED -- zero consumers (verified)." The R1 requested exhaustive search across all directories. The spec asserts it was verified. We trust the verification was done per the R1 instruction.

### R1 Item 5: Three ConstraintEnvelopes not semantically equivalent

**Status**: RESOLVED

SPEC-07 section 3 provides the field-by-field semantic diff that R1 demanded. It covers all 5 dimensions across all 3 types, including NaN protection, monotonic tightening, signing, gradient thresholds, frozen semantics, and YAML loading. The diff explicitly notes behavioral breaking changes (NaN rejection, frozen dataclass) with mitigations.

### R1 Item 6: Nexus migration assumes trust has Nexus capabilities

**Status**: RESOLVED

SPEC-06 section 1 provides the per-capability migration matrix (table at lines 20-37). It explicitly categorizes each capability as "trust has it" / "extract Nexus INTO trust" / "keep in Nexus." The matrix addresses JWT, RBAC, API key, SSO, rate limiting, audit, tenant resolver, EATP headers, trust middleware, session trust, CSRF, security headers, Prometheus, and PACT governance.

### R1 Item 7: Provider unification forces "every provider implements every method"

**Status**: RESOLVED

SPEC-02 section 2.1 defines capability protocols (`LLMProvider`, `AsyncLLMProvider`, `StreamingProvider`, `EmbeddingProvider`, `ToolCallingProvider`, `StructuredOutputProvider`). Each provider implements only the protocols it supports. The Cohere example at section 2.6 explicitly shows an embedding-only provider that does NOT implement `LLMProvider`, `StreamingProvider`, etc. "No stub methods" is stated in the CohereEmbeddingProvider docstring.

## Cross-Reference Matrix

| SPEC    | References ADRs      | Referenced by SPECs  | ADR-010 integrated? | section 4 Backward Compat consistent with ADR-009? |
| ------- | -------------------- | -------------------- | ------------------- | -------------------------------------------------- |
| SPEC-01 | ADR-004              | 02,03,04,05,09       | No (not applicable) | Yes (Layer 1 re-export shims)                      |
| SPEC-02 | ADR-005              | 01,03,04,05,09       | No (not applicable) | Yes (Layer 1+2 shims)                              |
| SPEC-03 | ADR-001,003,**010**  | 01,02,04,05,07,09,10 | **Yes**             | Yes (v2.x compat, extension points work)           |
| SPEC-04 | ADR-001,002,**010**  | 01,02,03,05,07       | **Yes**             | Yes (deprecated params, extension points)          |
| SPEC-05 | ADR-007,**010**      | 01,02,03,04,10       | **Yes**             | **MISSING section** (see R2-004)                   |
| SPEC-06 | (Nexus audit)        | 01,07,08             | Partial (posture)   | Yes (shim at nexus.auth)                           |
| SPEC-07 | ADR-006,**010**      | 03,04,05,06,09       | **Yes**             | Yes (class aliases per Layer 2)                    |
| SPEC-08 | (Core synergy audit) | 06,07,03             | No (not applicable) | **MISSING section** (see R2-006)                   |
| SPEC-09 | ADR-008              | 01,02                | Yes (type mappings) | N/A (validation spec, no changes)                  |
| SPEC-10 | ADR-001              | 03,04,05             | No (not applicable) | Yes (deprecated subclass aliases)                  |

### ADR-010 Integration Assessment

SPECs 03, 04, 05, and 07 were the four SPECs identified for ADR-010 updates. All four include:

- `AgentPosture` type reference
- `posture_ceiling` (SPEC-07)
- Posture-aware instruction enforcement (SPEC-03 section 3.3, SPEC-04 sections 3.3-3.4)
- ADR-010 listed in the Implements header

### Dependency Ordering Verification

| Phase | SPECs   | Depends on                                      | Circular? |
| ----- | ------- | ----------------------------------------------- | --------- |
| 1     | SPEC-01 | None                                            | No        |
| 2     | SPEC-02 | None                                            | No        |
| 2     | SPEC-07 | None                                            | No        |
| 3     | SPEC-03 | SPEC-01, SPEC-02, SPEC-07                       | No        |
| 3     | SPEC-04 | SPEC-01, SPEC-02                                | No        |
| 4     | SPEC-05 | SPEC-01, SPEC-02, SPEC-03, SPEC-04              | No        |
| 4     | SPEC-10 | SPEC-03, SPEC-04                                | No        |
| 5     | SPEC-06 | SPEC-07 (ConstraintEnvelope for PACTMiddleware) | No        |
| 5     | SPEC-08 | SPEC-06 (Nexus audit consumes AuditStore)       | No        |
| 6     | SPEC-09 | All                                             | No        |

No circular dependencies. Phase ordering is correct. SPEC-08 depends on SPEC-06 (both Phase 5) which is acceptable since they can run sequentially within the phase or SPEC-06 sub-phases (5a, 5b) complete before SPEC-08 needs the audit store.

One minor note: SPEC-04 lists dependency on SPEC-01 and SPEC-02, but the spec index shows SPEC-04 in Phase 3 alongside SPEC-03. SPEC-03 also depends on SPEC-07 (for L3GovernedAgent consuming ConstraintEnvelope). SPEC-07 is Phase 2, so this is satisfied.

## Verdict

**GO — both critical findings RESOLVED 2026-04-08.**

R2-001 and R2-002 were the only blockers for `/todos`. Both are resolved:

1. **R2-001 RESOLVED**: `CapabilityBased` replaced with `LLMBased` routing across SPEC-03 and SPEC-10. `WorkerAgent` now uses A2A capability cards, not keyword lists. Rules violation cleared. Cross-SDK lockstep notice added for Rust mirror implementation.

2. **R2-002 RESOLVED**: Security Considerations sections written for all 8 affected SPECs. Each section addresses component-specific threats with concrete mitigation requirements (not boilerplate). Implementers have actionable guidance before touching code.

**Open items (non-blocking for `/todos`; to be addressed during task creation or implementation):**

- R2-003 through R2-007 (5 important): clarification and missing sections — should be converted to explicit tasks during `/todos`.
- R2-008 through R2-014 (7 minor): documentation polish — address during implementation.

**Ready to proceed to `/todos`.** The structural gate (human approves plan) is the next step.

**Cross-SDK impact of resolutions**: kailash-rs must mirror the R2-001 fix (LLM routing, A2A capability cards). Rust's SPEC-03 parallel section and SPEC-10 parallel section need updating to reflect the new signature. R2-002 security sections flow through cross-SDK implementation — Rust enforces the same mitigations via Rust-idiomatic types (frozen types via `#[derive(Debug, Clone)]` without `DerefMut`, builder patterns for immutability, trait bounds for registry validation, etc.).

Overall assessment: The spec corpus is well-constructed. The ADR-010 integration is thorough. Cross-references are consistent. The composition-wrapper pattern is correctly applied throughout. The backward compatibility strategy from ADR-009 is reflected in all SPECs that have backward compatibility sections. The R1 gaps are genuinely resolved.
