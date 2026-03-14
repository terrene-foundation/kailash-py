# Cross-SDK EATP Gap Analysis: Python vs. Rust

**Date**: 2026-03-14
**Sources**: Python analysis (01-06), Rust analysis (kailash-rs/workspaces/eatp-gaps/)
**Agents**: eatp-expert (boundary analysis), deep-analyst (gap comparison), coc-expert (institutional knowledge)

---

## Executive Summary

The Rust EATP team completed their analysis AND red-teamed it, producing findings that materially change our Python implementation plan. Three cross-SDK agents analyzed the implications.

### Key Findings

1. **The Rust red team is substantially correct on the principle**: EATP should define trust assessment ("is this agent trusted?"), not enforcement policy ("what do we do about it?"). But Python's `pip install` ergonomics justify keeping enforcement as a convenience layer.

2. **4 new gaps from the Rust value audit** apply equally to Python: SIEM export (CRITICAL), SOC 2 evidence (HIGH), Fleet observability (HIGH), Role-based trust access (MEDIUM). Our Python gap count grows from 14 to 18.

3. **Phase 0 (spec alignment) is BLOCKING**: 7 shared gaps must be designed cross-SDK before implementation. Divergent implementations would fracture the ecosystem.

4. **G3 (hooks) must be narrowed**: Remove `PRE_TOOL_USE`, `POST_TOOL_USE`, `SUBAGENT_SPAWN` from EATP's `HookType` enum. These are orchestration events, not trust events.

5. **Proximity defaults must align**: Python proposed 70/90; Rust already uses 80/95. Recommend 80/95 as canonical with "conservative" 70/90 preset.

6. **Our analysis was missing a value audit**: The Rust team's enterprise buyer perspective found that circuit breakers and hooks don't sell — multi-sig and SIEM integration do.

---

## The Boundary Disagreement — Resolved

### The Principle

**"EATP answers 'is this agent trusted to do this action?' Downstream answers 'what do we do about it?'"**

| In EATP                                                                               | Not in EATP                         |
| ------------------------------------------------------------------------------------- | ----------------------------------- |
| Trust primitives (Genesis, Delegation, Constraint Envelope, Capability, Audit Anchor) | Circuit breaker state machine       |
| Trust operations (ESTABLISH, DELEGATE, VERIFY, AUDIT)                                 | Orchestration runtime               |
| Verification gradient classification (including proximity thresholds)                 | SIEM export adapters                |
| Trust scoring (structural + behavioral)                                               | PRE_TOOL_USE / SUBAGENT_SPAWN hooks |
| Posture state machine + transition guards                                             | CARE vocabulary adapters            |
| Cryptographic infrastructure (keys, signing, dual-sig, multi-sig)                     | Fleet observability dashboards      |
| Enforcement convenience layer (`eatp.enforce`)                                        | SOC 2 evidence generation           |
| Hook protocol (trust-native events only)                                              |                                     |
| Cascade revocation                                                                    |                                     |

### Python-Specific Decision

**Keep enforcement in the `eatp` package** for pragmatic reasons. Python's `pip install eatp` should give developers a working trust enforcement system. Rust's `cargo add eatp` + `cargo add kailash-kaizen` is seamless; Python's `pip install eatp` + `pip install kailash-kaizen` with manual wiring is not.

However, the `orchestration/` sub-package should be deprecated and migrated to `kailash-kaizen` in v0.2.0. It explicitly mixes orchestration with trust.

---

## Gap Overlap Matrix

### Shared Gaps (Must Be Designed Cross-SDK)

| Gap                  | Python                     | Rust                                      | Alignment Risk                                     |
| -------------------- | -------------------------- | ----------------------------------------- | -------------------------------------------------- |
| Lifecycle hooks      | G3: New `hooks.py`         | RG3: New `hooks.rs`                       | **HIGH** — hook types, abort semantics must match  |
| Proximity thresholds | G2: New `ProximityScanner` | Already has `VerificationConfig` (80/95)  | **HIGH** — defaults diverge (Py 70/90 vs Rs 80/95) |
| Behavioral scoring   | G1: New `BehavioralScorer` | Partially done via `track_record_score()` | **MEDIUM** — factor names and weights must align   |
| Multi-sig / Dual-sig | G6: HMAC fast-path         | RG5: M-of-N (Python has this already)     | **MEDIUM** — different features, complementary     |
| Cascade revocation   | MG1: Not implemented       | Not explicitly listed                     | **HIGH** — core EATP spec, 0% in both              |
| SIEM export          | Not in original analysis   | Value audit: CRITICAL                     | **HIGH** — event schema must be identical          |
| Circuit breaker      | G4: Registry wrapper       | RG1: Full implementation                  | **LOW** — placement disputed                       |

### Prior Art References (Study, Don't Depend)

Per Rust team decision D6: both SDKs implement from the spec, not from each other. Reference implementations are prior art to study, not dependencies to track. Neither team blocks on the other's implementation.

**Rust prior art for Python team to study:**
| Feature | Relevance | Informs |
|---------|-----------|---------|
| `VerificationConfig` with `flag_threshold`/`hold_threshold` | Threshold naming, config pattern | G2 design |
| `track_record_score()` behavioral tracking | Factor computation approach | G1 design |
| `ReasoningTrace` struct | Trace format, JSON structure | New spec deliverable |
| Compliance framework (EU AI Act, OWASP) | Compliance mapping pattern | VA2 design |
| Bounded evidence records pattern | VecDeque bounding approach | G5 design |

**Python prior art for Rust team to study:**
| Feature | Relevance | Informs |
|---------|-----------|---------|
| `ShadowEnforcer` + `StrictEnforcer` | Dual enforcement pattern | RG2 design |
| `multi_sig.py` M-of-N validation | Multi-sig API shape | RG5 design |
| Challenge-response protocol | Interactive verification | Future feature |

### Value Audit Gaps (New for Python)

| Gap                                        | Severity     | Description                                                                                                   |
| ------------------------------------------ | ------------ | ------------------------------------------------------------------------------------------------------------- |
| VA1: SIEM Export (CEF/OCSF)                | **CRITICAL** | Structured export for Splunk/QRadar/Sentinel. Python has `SecurityAuditLogger` but no standard format export. |
| VA2: SOC 2 / ISO 27001 Evidence            | **HIGH**     | Compliance artifact generation. Map EATP operations to control objectives.                                    |
| VA3: Fleet Observability (OTel/Prometheus) | **HIGH**     | Trust health metrics for production fleets. `eatp/metrics.py` exists but no standard export.                  |
| VA4: Role-Based Trust Access               | **MEDIUM**   | `TrustRole` enum + guard on `TrustOperations`. Currently all-or-nothing access.                               |

---

## Revised Python Gap Count

| Category        | Original | After Py Analysis | After Cross-SDK    |
| --------------- | -------- | ----------------- | ------------------ |
| CRITICAL        | 3        | 3                 | **4** (+VA1: SIEM) |
| HIGH            | 3        | 4 (+MG1)          | **6** (+VA2, +VA3) |
| MEDIUM          | 4        | 5 (+MG2)          | **6** (+VA4)       |
| LOW             | 1        | 1                 | 1                  |
| Hidden (bundle) | 0        | 4                 | 4                  |
| **Total**       | **11**   | **14**            | **18**             |

---

## Impact on Python Implementation Plan

### New Phase 0: Specification Alignment (BLOCKING)

**Duration**: 2-3 days (spec-only; no implementation coordination per D6)
**Must complete before Phase 2+**

| Deliverable                | Content                                                                                     |
| -------------------------- | ------------------------------------------------------------------------------------------- |
| Hook Specification         | `HookType` values (trust-native only), `HookResult` fields, abort semantics, priority rules |
| Proximity Defaults         | Canonical 80/95, "conservative" 70/90 preset                                                |
| Behavioral Scoring         | Factor names, weights, zero-data behavior, computation algorithm (spec concern per D4)      |
| SIEM Event Schema          | OCSF-aligned event definitions for all EATP operations                                      |
| Observability Metrics      | OpenTelemetry metric naming convention                                                      |
| EATP Scope ADR             | What belongs in eatp vs downstream — circuit breaker clearly out (D2)                       |
| ReasoningTrace JSON Schema | Cross-MCP portable trace format for trust decision reasoning (NEW per D5)                   |

### Revised Phase Order

| Phase  | Gaps                    | Theme                  | Change from Original                |
| ------ | ----------------------- | ---------------------- | ----------------------------------- |
| **0**  | Shared spec             | Cross-SDK alignment    | **NEW (BLOCKING)**                  |
| **1**  | G5/G5+, G8/G8+, G9, G11 | Production safety      | Unchanged                           |
| **2**  | G2, G4                  | Core trust model       | G2 defaults changed to 80/95        |
| **3**  | G3                      | Hooks (narrowed scope) | **G3 narrowed** — trust events only |
| **4**  | G1                      | Behavioral scoring     | Aligned with Rust's factor model    |
| **5**  | G6, G7                  | Production hardening   | Unchanged                           |
| **5b** | VA1, VA2, VA3           | Enterprise readiness   | **NEW**                             |
| **6**  | G10, VA4                | Ecosystem alignment    | VA4 added                           |

### Specific Changes to Gaps

| Gap | Change                                                                                               | Rationale                                                                                   |
| --- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| G2  | Defaults: 70/90 → **80/95**                                                                          | Align with Rust's existing `VerificationConfig`                                             |
| G3  | Remove `PRE_TOOL_USE`, `POST_TOOL_USE`, `SUBAGENT_SPAWN` from `HookType`                             | EATP doesn't know about "tools" or "sub-agents" — orchestration events go to kailash-kaizen |
| G3  | HookType restricted to: `PRE_DELEGATION`, `POST_DELEGATION`, `PRE_VERIFICATION`, `POST_VERIFICATION` | Trust-native events only                                                                    |
| G4  | Stays in eatp (Python pragmatic)                                                                     | `pip install` ergonomics; but document boundary rationale                                   |

---

## Stakeholder Decisions Required

### Closed by Rust Team Decisions (doc 08)

| #   | Decision             | Resolution                                                                   |
| --- | -------------------- | ---------------------------------------------------------------------------- |
| 2   | Proximity defaults   | **CLOSED**: 80/95 canonical, 70/90 conservative preset (D1)                  |
| 8   | Phase 0 investment   | **CLOSED**: YES, 2-3 days spec-only, no impl coordination (D6)               |
| 12  | Cross-SDK governance | **CLOSED**: Terrene Foundation owns spec; teams implement independently (D6) |

### Still Open (9)

| #   | Decision                         | Recommendation                                           |
| --- | -------------------------------- | -------------------------------------------------------- |
| 1   | Scoring weight ratio             | 60/40 — may be decided by spec factor definition (D4)    |
| 3   | Hook error policy                | Fail-closed — both teams lean this way                   |
| 4   | KMS algorithm                    | Accept P-256 (Python-specific)                           |
| 5   | Threading model                  | Async-only for v0.1.x (Python-specific)                  |
| 6   | Adapter ownership                | Vocab docs + downstream bridge                           |
| 7   | MG1/MG2 scope                    | Include MG1 in Phase 3 (core EATP spec, 0% in both SDKs) |
| 9   | SIEM priority                    | Accept as CRITICAL — enterprise SOC integration          |
| 10  | Value audit gaps scope (VA1-VA4) | VA1-VA3 in Phase 5b; VA4 in Phase 6                      |
| 11  | Cascade revocation in Phase 3    | YES — core EATP spec requirement                         |

---

## Documents Index (Updated)

| #      | Document                          | Content                                                                       |
| ------ | --------------------------------- | ----------------------------------------------------------------------------- |
| 01     | `01-gap-details.md`               | Detailed gap descriptions G1-G6                                               |
| 02     | `02-risk-analysis.md`             | Risk register, hidden risks, dependency graph                                 |
| 03     | `03-spec-alignment-evaluation.md` | Spec alignment, boundary analysis, missing gaps                               |
| 04     | `04-requirements-breakdown.md`    | Requirements, ADRs, API surfaces, tests                                       |
| 05     | `05-coc-assessment.md`            | Three fault lines, anti-amnesia, quality gates                                |
| 06     | `06-synthesis.md`                 | Original synthesis (pre-Rust findings)                                        |
| **07** | **`07-cross-sdk-analysis.md`**    | **Cross-SDK comparison, boundary resolution, updated plan (this document)**   |
| **08** | **`08-rust-team-decisions.md`**   | **Rust team decisions D1-D6, impact analysis, closed/open decision tracking** |
