# PACT Spec-Conformance Audit — Issues #199-#202

**Date**: 2026-03-31
**Scope**: 4 open GitHub issues, all tagged `pact`, `spec-conformance`, `enhancement`
**Source**: PACT-Core-Thesis.md sections 4.2, 4.4, 5.3, 5.5, 5.6, 5.7, 12.1, 12.9.1

## Executive Summary

Four spec-conformance gaps in the PACT governance module were identified during a red team audit and filed as GitHub issues #199-#202 on 2026-03-31. These gaps span EATP record emission, write-time tightening validation, bridge consent protocol, and vacancy handling. All four are additive — they extend existing, working functionality rather than replacing it. No regressions expected.

The PACT module currently has **22 source files, 3,900 lines in the 4 key files** (engine.py: 1618, envelopes.py: 937, compilation.py: 974, audit.py: 371), and **1,139 passing unit tests** across 47 test files. The base implementation is mature — these issues fill spec-level gaps, not architectural holes.

---

## Issue Inventory

| #    | Title                                             | Severity | Spec Section | Key Files                 | Estimated LOC |
| ---- | ------------------------------------------------- | -------- | ------------ | ------------------------- | ------------- |
| #199 | EATP record emission                              | CRITICAL | 5.7          | engine.py, audit.py       | ~200          |
| #200 | Write-time tightening (3 missing dims) + gradient | HIGH     | 5.3, 5.6     | envelopes.py, config.py   | ~350          |
| #201 | Vacant heads + bridge consent + scope validation  | HIGH     | 4.2, 4.4     | compilation.py, engine.py | ~300          |
| #202 | Vacancy interim envelope + configurable deadline  | MEDIUM   | 5.5          | engine.py                 | ~100          |

**Total estimated new code**: ~950 LOC production + ~600 LOC tests

---

## Issue #199: EATP Record Emission (CRITICAL)

### Problem

PACT spec Section 5.7 states: _"This mapping is normative; implementations claiming PACT conformance must produce these records."_

The GovernanceEngine maintains its own `AuditAnchor`/`AuditChain` (in `audit.py`) but does NOT emit the EATP record types defined in `src/kailash/trust/chain.py`:

- `GenesisRecord` — never created on org init
- `DelegationRecord` — never created on envelope operations or bridge creation
- `CapabilityAttestation` — never created on clearance grant

**Current state**: Zero imports from `kailash.trust.chain` in the PACT governance module.

### Root Cause

PACT's audit system was built as a self-contained hash chain. The EATP trust chain module was developed separately. Integration was never wired.

### Required Changes

| Emission Point            | EATP Type                   | Method                | Line  |
| ------------------------- | --------------------------- | --------------------- | ----- |
| Org creation              | `GenesisRecord`             | `__init__()`          | ~263  |
| Envelope set (role)       | `DelegationRecord`          | `set_role_envelope()` | ~1221 |
| Envelope set (task)       | `DelegationRecord`          | `set_task_envelope()` | ~1262 |
| Clearance grant           | `CapabilityAttestation`     | `grant_clearance()`   | ~927  |
| Bridge creation           | 2x `DelegationRecord`       | `create_bridge()`     | ~1164 |
| Access denial             | `BARRIER_ENFORCED` subtype  | `check_access()`      | ~322  |
| Envelope create vs modify | Differentiated audit action | `set_role_envelope()` | ~1221 |

### Design

**Dual emission**: Keep existing PACT `AuditAnchor` chain AND add EATP types. The EATP records provide cross-system interop; the PACT anchors provide the tamper-evident governance trail. Both run in parallel.

**Constructor change**: `GovernanceEngine.__init__()` gains optional `trust_chain_store: TrustStore | None = None`. When provided, EATP records are emitted. When `None`, PACT runs standalone (backward-compatible).

### Dependencies

- `kailash.trust.chain.GenesisRecord` (exists, line 122)
- `kailash.trust.chain.DelegationRecord` (exists, line 222)
- `kailash.trust.chain.CapabilityAttestation` (exists, line 172)
- `kailash.trust.chain.AuthorityType` (exists)
- `kailash.trust.chain.CapabilityType` (exists)

All EATP types already exist and have `to_dict()`/`from_dict()` methods. No new EATP types needed.

### Risk

- **LOW**: Additive — existing audit chain untouched
- **Thread safety**: EATP emission must happen outside `_lock` (same pattern as `_emit_audit()`)
- **Backward compat**: `trust_chain_store=None` default preserves current behavior

---

## Issue #200: Write-Time Tightening + Per-Dimension Gradient (HIGH)

### Problem

`RoleEnvelope.validate_tightening()` (envelopes.py:415-544) validates monotonic tightening for 4 of 7 dimensions:

| Dimension         | Validated? | Fields                                                                |
| ----------------- | ---------- | --------------------------------------------------------------------- |
| Financial         | YES        | `max_spend_usd`, `api_cost_budget_usd`, `requires_approval_above_usd` |
| Confidentiality   | YES        | `confidentiality_clearance` (enum order)                              |
| Operational       | YES        | `allowed_actions` (set subset)                                        |
| Delegation        | YES        | `max_delegation_depth`                                                |
| **Temporal**      | **NO**     | `active_hours_start/end`, `blackout_periods`                          |
| **Data Access**   | **NO**     | `read_paths`, `write_paths`                                           |
| **Communication** | **NO**     | `internal_only`, `allowed_channels`                                   |

The intersection functions (`_intersect_temporal`, `_intersect_data_access`, `_intersect_communication`) exist at lines 240-307 for runtime use, but the write-time validation at `validate_tightening()` doesn't check these 3 dimensions.

### Sub-Issues

**Sub-issue 1 (HIGH): Missing dimension validation**

Required tightening checks:

- **Temporal**: child `active_hours` must be within parent's window; child `blackout_periods` must be superset of parent's
- **Data Access**: child `read_paths` must be subset of parent's; child `write_paths` must be subset of parent's
- **Communication**: child `allowed_channels` must be subset of parent's; `internal_only=True` is more restrictive than `False`

Each violation must produce `MonotonicTighteningError` with the specific dimension identified.

**Sub-issue 2 (HIGH): Per-dimension gradient configuration**

`RoleEnvelope` has no gradient field. Spec Section 5.6 envisions per-dimension threshold arrays:

```
Financial: auto-approved <$20K, flagged $20K-$50K, held $50K-$100K, blocked >$100K
```

Required:

1. New `DimensionGradientConfig` dataclass with `auto_approve_threshold`, `flag_threshold`, `hold_threshold`
2. New `GradientConfig` mapping `ConstraintDimension -> DimensionGradientConfig`
3. Add `gradient: GradientConfig | None` field to `RoleEnvelope`
4. Update `_evaluate_against_envelope()` to use configured thresholds
5. Validate ordering: auto_approve < flag < hold < dimension_max

**Sub-issue 3 (MEDIUM): Gradient dereliction detection**

`check_degenerate_envelope()` (line 880) detects overly-tight envelopes but not overly-permissive gradients. When `auto_approve_threshold >= 90%` of the effective limit, it's rubber-stamping — should warn.

**Sub-issue 4 (MEDIUM): Pass-through envelope detection**

No code detects when child envelope is identical to parent. Documented gap in `test_adversarial.py`. Should emit WARNING-level audit anchor (not block).

### Dependencies

- `ConstraintEnvelopeConfig` dataclass (envelopes.py) — needs `gradient` field added
- `_evaluate_against_envelope()` in engine.py — needs gradient-aware evaluation
- `config.py` — new `DimensionGradientConfig` and `GradientConfig` types

### Risk

- **MEDIUM**: Tightening validation is a security boundary. Must be carefully tested.
- All existing tests must continue to pass — the new checks are additional, not replacing.
- Gradient config is optional (defaults to current behavior).

---

## Issue #201: Vacant Heads + Bridge Bilateral Consent (HIGH)

### Problem

Three D/T/R grammar and bridge protocol gaps.

### Sub-Issue 1: Auto-create vacant head roles (HIGH)

Spec Section 4.2: _"When a D or T is created without an R, the system auto-creates a vacant head role."_

`compile_org()` (compilation.py:384-573) builds `unit_head_map` at line 427-430. Units without a head in this map are silently dropped from the compiled org — no address is assigned for headless units, and no vacant role is synthesized.

**Fix**: After building `unit_head_map`, iterate all departments/teams. For any unit not in the map, synthesize a `RoleDefinition` with `is_vacant=True` and `is_primary_for_unit=unit_id`. Also update `yaml_loader.py` to warn (not error) when parsing a unit without a head.

### Sub-Issue 2: Bridge bilateral consent (HIGH)

Spec Section 4.4 property 3: _"requires bilateral establishment (both roles must agree)"_

`create_bridge()` (engine.py:1079-1164) validates LCA approval but does NOT require consent from both endpoint roles. It checks that the LCA approved, but doesn't verify that `role_a` and `role_b` themselves agreed to the bridge.

**Fix**: Add `consent_bridge(role_address, bridge_id)` method. Before `create_bridge()` persists the bridge, verify both roles have registered consent. Store consents in a bounded dict with 24h TTL.

### Sub-Issue 3: Bridge scope validation (MEDIUM)

Spec Section 4.4: _"A bridge cannot grant access broader than either party's own envelope permits."_

`create_bridge()` does NOT validate bridge scope against role envelopes. A bridge could theoretically grant access that exceeds what either connected role is permitted.

**Fix**: Before persisting, compute effective envelopes for both roles. Validate bridge scope against both.

### Sub-Issue 4: Compliance role as alternative bridge approver (LOW)

Spec Section 4.4 property 4: _"or from a designated compliance role"_

`approve_bridge()` only accepts LCA as approver.

**Fix**: Add `register_compliance_role(role_address)` and accept compliance role in `approve_bridge()`.

### Dependencies

- `compile_org()` — needs vacant head synthesis
- `RoleDefinition` — needs `is_vacant` field (check if it exists)
- `yaml_loader.py` — needs validation adjustment
- `engine.py` — needs `consent_bridge()` method, bridge scope validation

### Risk

- **MEDIUM**: Compilation changes affect all downstream address assignment
- Bridge consent is a new protocol step — must be backward-compatible (opt-in or required with migration guide)
- Test impact is high — many existing tests construct orgs without explicit heads

---

## Issue #202: Vacancy Interim Envelope + Configurable Deadline (MEDIUM)

### Problem

`_check_vacancy()` (engine.py:1381-1437) returns a blocking error for ANY vacancy without designation. The spec says there should be a degraded-but-operational middle state during the deadline window.

### Sub-Issue 1: Interim envelope (MEDIUM)

Spec Section 5.5 Rule 2: _"Until an acting role is designated, the vacant role's direct reports operate under the more restrictive of their own Role Envelope or the parent's envelope for the vacant role."_

**Current**: Within deadline window, returns blocking error. Should compute `min(own_envelope, parent_envelope_for_vacant_role)` as interim effective envelope.

**Fix**: In `_check_vacancy()`, instead of returning an error within the deadline window, return a signal that triggers interim envelope computation in `_verify_action_locked()`. The interim envelope = `intersect_envelopes(own_envelope, vacant_parent_envelope)`.

### Sub-Issue 2: Configurable deadline (MEDIUM)

engine.py line 1337 hardcodes `timedelta(hours=24)`.

**Fix**: Add `vacancy_deadline_hours: int = 24` parameter to `GovernanceEngine.__init__()`.

### Dependencies

- `_check_vacancy()` — needs to distinguish "within deadline" vs "past deadline"
- `_verify_action_locked()` — needs interim envelope computation
- `intersect_envelopes()` — already exists (line 314-351)

### Risk

- **LOW**: Well-scoped, existing intersection logic reusable
- Must ensure the interim envelope is never more permissive than either source

---

## Dependency Graph

```
#199 (EATP records) ─── independent, can be done first or in parallel
#200 (tightening)   ─── independent of #199, #201, #202
#201 (bridges/heads) ── sub-issue 3 (scope validation) depends on effective envelope computation
#202 (vacancy)      ─── depends on #201 sub-issue 1 (vacant heads must exist for interim to work)
```

**Recommended execution order**:

1. **#200** (tightening + gradient) — largest, highest security impact, no dependencies
2. **#201** (compilation + bridges) — #202 depends on vacant heads existing
3. **#202** (vacancy interim) — depends on #201 sub-issue 1
4. **#199** (EATP records) — can run in parallel with any of the above

---

## Cross-SDK Status

| Issue | Python Status         | Rust Status                                                   | Action Needed   |
| ----- | --------------------- | ------------------------------------------------------------- | --------------- |
| #199  | Missing               | `explain` module + `GovernanceContext` serialization cover it | Python catch-up |
| #200  | 4/7 dimensions        | Full `validate_tightening()` + `FiniteF64` + gradient zones   | Python catch-up |
| #201  | LCA-only bridges      | `BridgeApprovalStatus` + bilateral/unilateral directionality  | Python catch-up |
| #202  | Hard block on vacancy | `VacancyCheckResult` enum (Active/ActingDesignation/Blocked)  | Python catch-up |

All 4 issues represent Python catching up to Rust's more complete spec implementation. No cross-SDK issues to file — Rust is already aligned.

---

## Test Impact Assessment

| Issue | Existing Tests at Risk                                            | New Tests Needed                                          |
| ----- | ----------------------------------------------------------------- | --------------------------------------------------------- |
| #199  | 0 (additive)                                                      | ~15 (emission verification per method)                    |
| #200  | ~5 (existing tightening tests may need adjustment for new checks) | ~25 (3 new dimensions x scenarios + gradient config)      |
| #201  | ~10 (compilation tests may need vacant head handling)             | ~20 (consent protocol, scope validation, compliance role) |
| #202  | ~3 (vacancy tests expect hard block)                              | ~10 (interim envelope, deadline config)                   |

**Total new tests**: ~70
**Expected post-implementation count**: ~1,209 (1,139 + 70)

---

## Security Considerations

1. **NaN/Inf validation** (from `trust-plane-security.md`): All new gradient threshold fields must be validated with `math.isfinite()`
2. **Monotonic tightening invariant**: New dimension checks must be fail-closed — if comparison fails, treat as violation
3. **Bounded collections**: Bridge consent storage must use bounded dict (10K max, same as bridge approvals)
4. **Thread safety**: All new engine methods must acquire `self._lock`
5. **Frozen dataclasses**: `DimensionGradientConfig` and `GradientConfig` must be `frozen=True`
