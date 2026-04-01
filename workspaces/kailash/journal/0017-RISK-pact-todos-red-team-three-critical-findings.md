---
type: RISK
date: 2026-03-31
created_at: 2026-03-31T12:15:00+08:00
author: agent
session_id: session-10
session_turn: 3
project: kailash
topic: Red team found 3 critical + 5 high issues in PACT sprint S12 todos
phase: todos
tags: [pact, red-team, todos, risk, spec-conformance]
---

# Red Team Found 3 Critical + 5 High Issues in Sprint S12 Todos

## Risk

The initial todo plan for PACT spec-conformance (14 todos, 5 milestones) had 3 critical issues that would have caused runtime failures and 5 high issues requiring significant revisions. All were caught and fixed before implementation began.

### Critical Findings (Would Have Caused Failures)

**C1: TrustStore API mismatch** — The todos assumed synchronous, per-record emission to `TrustStore`. But `TrustStore` is async and stores complete `TrustLineageChain` objects, not individual records. GovernanceEngine is synchronous. Fix: Created `PactEatpEmitter` synchronous protocol with `InMemoryPactEmitter` default implementation.

**C2: DelegationRecord field name** — Todos used `created_at` but the actual field is `delegated_at`. Would have caused `TypeError` at construction.

**C3: `create_bridge()` breaking change** — 14+ test sites and the university example call `create_bridge()` without consent. Fix: Added `require_bilateral_consent=False` default for backward compatibility.

### High Findings (Significant Revisions Needed)

**H1: Gradient type collision** — `gradient.py` already has `GradientEngine` with 5 dimension evaluators. `config.py` has `VerificationGradientConfig` (Pydantic). TODO-02 originally proposed a parallel system. Fix: Compose with existing types.

**H2: `_check_vacancy()` return type** — Changing from `str|None` to a dataclass would silently break the single caller at engine.py:412-437 (truthiness check on string). Fix: Explicitly updated caller in todo spec.

**H3: `vacant_since` doesn't exist** — Can't add to frozen `OrgNode`. Fix: Track in `_vacancy_start_times` dict on GovernanceEngine.

**H4: None-handling unspecified** — child=None when parent has constraints must be a violation, not a skip. Fix: Explicit semantics added to TODO-01.

**H5: engine.py conflict surface** — 8 of 14 TODOs modify engine.py. Milestones claimed independence but implementation must be serialized. Fix: Revised to 5-phase implementation order.

## Mitigation

All findings were addressed in rev 2 of the milestones. No findings deferred. The revised implementation order ensures engine.py edits don't conflict.

## For Discussion

1. The TrustStore API mismatch (C1) suggests the EATP trust chain module was designed for a different integration pattern (async, chain-level). Should the PACT-EATP bridge eventually use the full `TrustOperations` API (with `establish()`, `delegate()`, `verify()`), or is the lightweight `PactEatpEmitter` the intended long-term interface?
2. If 8 of 14 TODOs touch engine.py, should the engine be decomposed in a future sprint? The 1618-line file is carrying governance logic, bridge logic, vacancy logic, audit emission, AND now EATP emission.
3. The `require_bilateral_consent=False` default is a pragmatic backward-compat choice, but the spec says consent is required (not optional). When should the default be flipped to `True`?
