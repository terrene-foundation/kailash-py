# Rust Team Decisions — Impact on Python EATP Plan

**Date**: 2026-03-14
**Source**: kailash-rs team review of cross-SDK analysis (doc 07)
**Status**: RATIFIED — these decisions are final

---

## Decision Record

### D1: Threshold Defaults — Align to 0.80/0.95

**Decision**: CONFIRMED (already in plan)

Rationale from Rust team: "0.80/0.95 is more conservative, which is the right default for a trust protocol. A flag at 0.70 means 30% of the constraint envelope is consumed before anyone notices — that's too permissive for enterprise."

**Impact on Python plan**: None — already adopted in v2 plan. Conservative preset (0.70/0.90) remains available for gradual rollout.

---

### D2: Circuit Breaker NOT in EATP Spec

**Decision**: CONFIRMED (Python keeps for pragmatic reasons, documents divergence)

Rationale from Rust team: "EATP defines trust verification — the 5 canonical elements are all about 'can this agent be trusted to do this thing?' A circuit breaker answers a different question: 'should we stop calling this thing that keeps failing?' That's a resilience/orchestration concern."

**The litmus test**: "If you removed all circuit breaker code from both SDKs, would EATP still be a complete trust protocol? Yes. Would the agent framework be less reliable? Yes. That tells you where it belongs — in the framework (kaizen), not the protocol (eatp)."

**Impact on Python plan**:

- G4 (CircuitBreakerRegistry) stays in Python's `eatp` package — but this is acknowledged as **pragmatic, not principled**
- Must add explicit documentation: "Circuit breaker is an orchestration concern retained in the Python EATP package for `pip install` ergonomics. The canonical placement per the EATP specification is in the agent framework (kailash-kaizen)."
- `orchestration/` sub-package migration to `kailash-kaizen` in v0.2.0 remains planned
- **No spec deliverable needed** — circuit breaker is explicitly out of EATP spec scope

---

### D3: Hook Scope — Narrow (Trust Events Only)

**Decision**: CONFIRMED (already in plan)

Rationale from Rust team: "EATP's 4 operations are ESTABLISH, DELEGATE, VERIFY, AUDIT. None of them reference 'tools' or 'sub-agents' — those are orchestration concepts from kaizen."

**Impact on Python plan**: None — already narrowed to 4 trust-native events:

- `PRE_DELEGATION`, `POST_DELEGATION` (DELEGATE operation)
- `PRE_VERIFICATION`, `POST_VERIFICATION` (VERIFY operation)

**Note**: Existing `PostureTransitionHook` in `eatp::posture` already covers posture state changes. The new hooks cover the remaining EATP operations. ESTABLISH and AUDIT hooks are deliberately omitted in v0.1.x — ESTABLISH is a one-time operation (genesis), and AUDIT is read-only.

---

### D4: Behavioral Scoring — Spec Factors First

**Decision**: CONFIRMED (already captured in Phase 0)

Rationale from Rust team: "If both SDKs implement behavioral scoring independently, the factors will diverge and the scores become incomparable across SDKs. Define the canonical factor list in the EATP spec (even if minimal — e.g., constraint adherence, delegation depth, evidence completeness), then both SDKs implement the same formula."

**Impact on Python plan**:

- Phase 0 already includes "Behavioral Scoring: Factor names, weights, zero-data behavior, computation algorithm" as a deliverable
- Strengthens the case: this is a **spec concern**, not an implementation concern
- Both teams must agree on factor names before either team implements
- Minimum spec-level factors suggested: constraint adherence, delegation depth, evidence completeness

---

### D5: Reasoning Trace Format — JSON Schema (NEW)

**Decision**: NEW REQUIREMENT — not in previous analysis

Rationale from Rust team: "ReasoningTrace already exists in Rust with a defined structure. If Python implements it differently, traces become non-portable. A JSON schema in the spec ensures any EATP-compliant SDK can produce and consume reasoning traces. This is especially important for the MCP channel where traces cross SDK boundaries."

**Impact on Python plan**:

- **New Phase 0 deliverable**: ReasoningTrace JSON Schema
- Must audit Python SDK for existing reasoning/trace structures and compare with Rust's `ReasoningTrace`
- Cross-MCP portability is the key driver — traces that cross SDK boundaries must be parseable by either SDK
- This may surface a new gap if Python has no equivalent to Rust's `ReasoningTrace`

**Action items**:

1. Add "ReasoningTrace JSON Schema" to Phase 0 deliverables
2. Audit Python EATP SDK for existing trace/reasoning structures
3. Compare with Rust's ReasoningTrace definition
4. If Python lacks equivalent: add new gap (RT1) to Phase 4 or 5b

---

### D6: Convergence-First Ordering — DECOUPLE

**Decision**: REJECT convergence-first ordering. Both SDKs implement from the spec, not from each other.

Rationale from Rust team: "The cross-analysis recommended 'Rust implements multi-sig referencing Python's implementation' — but that's coupling development timelines and creating a dependency on another team's code quality."

**First-principles reasoning**: "Both SDKs implement the spec, not each other. The spec defines multi-sig validation. Rust implements it from the spec. Python implements proximity thresholds from the spec. The reference implementations are useful as prior art to study, not as dependencies to track."

**What actually needs alignment**:

- **Spec-level**: threshold defaults, behavioral scoring factors, reasoning trace schema, constraint dimensions
- **Feature parity**: both SDKs should eventually cover the same spec surface
- **Implementation**: independent, each team owns their code

**Impact on Python plan**:

This is the biggest change. It fundamentally redefines Phase 0:

1. **Phase 0 narrows**: It's about producing spec deliverables, not coordinating implementation timelines
2. **Cross-pollination table changes**: "Backport" language → "Prior art" language. Neither team depends on the other's code.
3. **Phase ordering becomes fully independent**: Python team can sequence phases in any order after Phase 0 spec deliverables are agreed. No need to wait for Rust to implement X before Python implements Y.
4. **Effort estimate may decrease**: Without cross-team implementation coordination overhead, Phase 0 could be 2-3 days (spec documents only) instead of 3-5 days (spec + implementation coordination)

---

## Summary of Changes Required

### Phase 0 Revision

**Before** (v2 plan):

- 6 deliverables, 3-5 days, cross-team coordination on implementation
- Cross-pollination tables with "backport" language implying implementation dependency

**After** (v3 plan):

- 7 deliverables (added ReasoningTrace JSON Schema), 2-3 days (spec-only, no implementation coordination)
- Each team studies the other's code as prior art, implements independently from spec

| #   | Deliverable                    | Type     | Change                                                    |
| --- | ------------------------------ | -------- | --------------------------------------------------------- |
| 1   | Hook Specification             | Spec     | Unchanged                                                 |
| 2   | Proximity Defaults             | Spec     | Unchanged                                                 |
| 3   | Behavioral Scoring Factors     | Spec     | Strengthened — "spec concern, not implementation concern" |
| 4   | SIEM Event Schema              | Spec     | Unchanged                                                 |
| 5   | Observability Metrics          | Spec     | Unchanged                                                 |
| 6   | EATP Scope ADR                 | Spec     | Simplified — circuit breaker clearly out                  |
| 7   | **ReasoningTrace JSON Schema** | **Spec** | **NEW** — cross-MCP portability                           |

### Cross-Pollination → Prior Art

The cross-pollination table in doc 07 used "backport" language:

- "Rust → Python (backport): `VerificationConfig`..."
- "Python → Rust (backport): `ShadowEnforcer`..."

This creates an implicit dependency. Replace with:

**Prior art references** (study, don't depend):

- Python team should study Rust's `VerificationConfig` and `track_record_score()` when implementing G2 and G1
- Rust team should study Python's `ShadowEnforcer`, `multi_sig.py`, and challenge-response when implementing RG2 and RG5
- Neither team blocks on the other's implementation

### Decisions Now Closed

| #   | Decision             | Status     | Resolution                                                  |
| --- | -------------------- | ---------- | ----------------------------------------------------------- |
| 2   | Proximity defaults   | **CLOSED** | 80/95 canonical, 70/90 conservative preset                  |
| 8   | Phase 0 investment   | **CLOSED** | YES, but 2-3 days (spec-only), not 3-5 days                 |
| 12  | Cross-SDK governance | **CLOSED** | Terrene Foundation owns spec; teams implement independently |

### Decisions Still Open

| #   | Decision                                   | Status                                          |
| --- | ------------------------------------------ | ----------------------------------------------- |
| 1   | Structural/behavioral weight ratio (60/40) | Open — may be decided by spec factor definition |
| 3   | Hook error policy (fail-closed)            | Open — but both teams lean fail-closed          |
| 4   | KMS algorithm (P-256)                      | Open — Python-specific                          |
| 5   | Threading model (async-only)               | Open — Python-specific                          |
| 6   | Adapter ownership                          | Open                                            |
| 7   | MG1/MG2 scope                              | Open — MG1 recommended for Phase 3              |
| 9   | SIEM priority (CRITICAL)                   | Open                                            |
| 10  | Value audit gaps scope (VA1-VA4)           | Open                                            |
| 11  | Cascade revocation in Phase 3              | Open                                            |

### D5 Follow-Up: ReasoningTrace Audit (RESOLVED)

**Finding**: Python EATP already has `ReasoningTrace` in `reasoning.py` with equivalent core structures (dataclass, `ConfidentialityLevel` enum, integration with `DelegationRecord`/`AuditAnchor`). **No new gap required.**

Minor feature parity gaps vs Rust (enhancements, not new gaps):

- Missing `.redact()` / `.is_redacted()` methods
- Missing `.content_hash()` / `.content_hash_hex()` on trace
- Missing `reasoning_completeness_score()` function (Python has chain-level `_compute_reasoning_coverage()` but lacks 0-100 scoring)
- Python uses untyped dicts for evidence; Rust has structured `EvidenceReference`

**D5 Phase 0 deliverable remains**: Define JSON schema for ReasoningTrace portability across SDKs/MCP channels. Both implementations exist — the spec work is about making them interoperable.

---

## Impact on Effort Estimate

| Phase     | v2 Estimate  | v3 Estimate  | Change      | Reason                                      |
| --------- | ------------ | ------------ | ----------- | ------------------------------------------- |
| 0         | 3-5 days     | **2-3 days** | -2 days     | Spec-only, no implementation coordination   |
| 1         | 2 days       | 2 days       | —           |                                             |
| 2         | 3 days       | 3 days       | —           |                                             |
| 3         | 3-4 days     | 3-4 days     | —           |                                             |
| 4         | 3 days       | 3 days       | —           | May include ReasoningTrace if gap confirmed |
| 5         | 4-5 days     | 4-5 days     | —           |                                             |
| 5b        | 3-4 days     | 3-4 days     | —           |                                             |
| 6         | 1-2 days     | 1-2 days     | —           |                                             |
| **Total** | **~25 days** | **~23 days** | **-2 days** | Phase 0 reduced                             |
