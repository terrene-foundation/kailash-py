---
type: DECISION
date: 2026-04-25
created_at: 2026-04-25T10:10:04.114Z
author: agent
session_id: c8cb11ec-e2ab-40d5-95ce-947a896a84ec
project: kailash-ml-audit
topic: PlanSuspension parity (5-variant SuspensionReason) closes #598
phase: implement
tags: [kaizen, l3, plan-suspension, pact-n3, cross-sdk-parity, eatp-d6]
source_commit: b7bd7d156cd94370c20d05a8ccafca602ccdd4a9
---

# DECISION — feat(kaizen): add PlanSuspension parity (5-variant SuspensionReason) (#598)

## What

New module `kaizen.l3.plan.suspension` with 5 reason variants:

- `HumanApprovalGateReason(held_node, reason)`
- `CircuitBreakerTrippedReason(breaker_id, triggering_node)`
- `BudgetExceededReason(dimension, usage_pct, triggering_node)`
- `EnvelopeViolationReason(dimension, detail, triggering_node)`
- `ExplicitCancellationReason(reason, resume_hint)`
- `SuspensionRecord` with `from_plan()` partition + sort + UTC timestamp
- `to_dict` / `from_dict` matching Rust serde tag-rename_all=snake_case

New Plan field: `Plan.suspension: Optional[SuspensionRecord]`. Round-trips through `Plan.to_dict` / `Plan.from_dict`.

L3 executor wiring (sync + async PlanExecutor): `_determine_terminal_state` for HumanApprovalGate (lex-first HELD node, deterministic for cross-SDK); `suspend_for_circuit_breaker` wrapper for CircuitBreakerTripped; async `_execute_node` enforcer-BLOCKED + enforcer-HELD paths for BudgetExceeded; sync + async `_execute_node` enforcer-BLOCKED + callback-result paths for EnvelopeViolation; `cancel(plan, reason, resume_hint)` for ExplicitCancellation.

`resume()` clears `plan.suspension`. Callers who need the record for audit MUST capture it before calling `resume()`.

## Why

PACT N3 mandates resumable plan suspension: any plan which suspends execution MUST be resumable from the exact suspension point. kailash-rs has shipped `SuspensionReason` + `SuspensionRecord` since the L3 landing; Python had no equivalent, so any cross-SDK plan serialization round-trip lost both the suspension cause and the resume frontier. This release closes that gap and aligns Python with EATP D6.

Per the issue, Python ships FIVE variants. Rust currently exposes four; the Python `EnvelopeViolation` variant is added to disambiguate structural envelope rejection (clearance, classification, dimension policy) from threshold-driven `BudgetExceeded`. Wire-format kind tag `"envelope_violation"` is reserved cross-SDK; a follow-up kailash-rs issue tracks adding the 5th variant for full parity.

## Tests

42 new tests, all passing. Full L3 plan suite (1012 tests) verified no regression against parent `.venv`.

- Tier 1 (30 tests): per-variant construction, frozen-dataclass mutation rejection, label stability for cross-SDK metric cardinality, wire-format round-trip per variant, missing/unknown kind error paths, `SuspensionRecord.from_plan` partition + sort, `with_resume_context` builder, `to_dict` / `from_dict` round-trip, `Plan.suspension` default + dict round-trip, parametrized cross-SDK parity vector table.
- Tier 2 (12 tests): all 5 trigger conditions end-to-end through real PlanExecutor; sync + async parity for every applicable trigger; `resume()` clears the record; Plan dict round-trip preserves suspension.

## Versioning

Minor bump 2.12.3 → 2.13.0 (new public API surface). Backwards compatible: existing `suspend()` / `cancel()` callers receive the same PlanState transitions; new behavior is the SuspensionRecord attachment.

## For Discussion

1. Python has 5 variants; Rust has 4. EATP D6 is satisfied at the wire-format level (`envelope_violation` is a reserved kind tag). Is this a tolerable asymmetry, or should we treat "Rust missing a variant" as a P1 and block any further suspension features until parity?
2. Counterfactual: the lex-first HELD node selection for `HumanApprovalGate` was chosen over "first HELD by execution order" for determinism. If two SDKs implement different ordering, `from_plan()` round-trips diverge. Is determinism worth the loss of "the FIRST node the user actually held" semantics?
3. `resume()` clears `plan.suspension` — meaning audit consumers MUST capture the record before resume. This is documented but not enforced. Should we either (a) move audit emission INTO the suspend path so it's always captured, or (b) add a typed `ResumeWithoutCapture` warning at runtime?
