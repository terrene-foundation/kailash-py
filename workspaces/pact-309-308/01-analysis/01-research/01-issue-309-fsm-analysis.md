# Issue #309: FSM Transition Analysis

## Current State

`VettingStatus` has 4 values: PENDING, ACTIVE, EXPIRED, REVOKED. No FSM enforcement exists — `grant_clearance()` stores whatever the caller provides. `revoke_clearance()` deletes the record entirely, losing the audit trail.

The access algorithm (`access.py:325`) already correctly denies anything != ACTIVE, so adding SUSPENDED requires zero changes to access control.

## Proposed FSM

```
PENDING   -> {ACTIVE, REVOKED}
ACTIVE    -> {SUSPENDED, EXPIRED, REVOKED}
SUSPENDED -> {ACTIVE, REVOKED}      # reinstatement path (core use case)
EXPIRED   -> {ACTIVE, REVOKED}      # renewal path (practical necessity)
REVOKED   -> {}                     # terminal — no outgoing transitions
```

### Design Decision: SUSPENDED -> ACTIVE (reinstatement)

The issue's original FSM has `SUSPENDED -> {REVOKED}` only (reinstate = new PENDING grant). This is wrong. The entire purpose of SUSPENDED vs REVOKED is that SUSPENDED is reversible. If reinstatement requires deleting and re-creating, there's no benefit over REVOKED.

**Recommendation**: Allow `SUSPENDED -> ACTIVE` directly via `transition_clearance()`.

### Design Decision: EXPIRED -> ACTIVE (renewal)

If EXPIRED is terminal, expired clearances can never be renewed without deletion — contradicting #309's goal of preserving records. Including `EXPIRED -> ACTIVE` enables clean renewals.

## Critical Risk: grant_clearance() + revoke_clearance() interaction

**Current flow**: `revoke_clearance("D1-R1")` deletes record. `grant_clearance("D1-R1", new)` creates fresh. No conflict.

**New flow**: `revoke_clearance("D1-R1")` sets status=REVOKED. `grant_clearance("D1-R1", new)` finds existing REVOKED record. If FSM is enforced in grant_clearance(), REVOKED has no outgoing transitions — the grant is rejected.

**Resolution**: `grant_clearance()` validates transitions only for "living" states (PENDING, ACTIVE, SUSPENDED). For terminal states (REVOKED, EXPIRED) and missing records, it allows unconditional overwrite. This preserves backward compatibility and the backup/restore path (`stores/backup.py` calls grant_clearance unconditionally).

## Files to Change (12 total)

### Production Code (6 files)

| #   | File                                       | Change                                                                 |
| --- | ------------------------------------------ | ---------------------------------------------------------------------- |
| 1   | `src/kailash/trust/pact/clearance.py`      | Add SUSPENDED, add `_VALID_TRANSITIONS`, add `validate_transition()`   |
| 2   | `src/kailash/trust/pact/engine.py`         | FSM validation in `grant_clearance()`, new `transition_clearance()`    |
| 3   | `src/kailash/trust/pact/audit.py`          | Add `CLEARANCE_TRANSITIONED` to `PactAuditAction`                      |
| 4   | `src/kailash/trust/pact/store.py`          | `MemoryClearanceStore.revoke_clearance()`: pop -> replace with REVOKED |
| 5   | `src/kailash/trust/pact/stores/sqlite.py`  | `SqliteClearanceStore.revoke_clearance()`: DELETE -> UPDATE            |
| 6   | `packages/kailash-pact/src/pact/engine.py` | Add `transition_clearance` to `_ReadOnlyGovernanceView._BLOCKED`       |

### Test Code (6 files)

| #   | File                                                | Change                                             |
| --- | --------------------------------------------------- | -------------------------------------------------- |
| 7   | `tests/trust/pact/unit/test_clearance.py`           | SUSPENDED enum, FSM transition matrix tests        |
| 8   | `tests/trust/pact/unit/test_engine.py`              | transition_clearance() tests, updated revoke tests |
| 9   | `tests/trust/pact/unit/test_stores.py`              | Revoke returns REVOKED record (not None)           |
| 10  | `tests/trust/pact/unit/test_sqlite_stores.py`       | Same assertion updates                             |
| 11  | `tests/trust/pact/unit/test_store_thread_safety.py` | Verify concurrent revoke with new semantics        |
| 12  | `tests/trust/pact/unit/test_redteam_rt21.py`        | Audit mutation assertions if affected              |

### Files NOT Needing Changes

- `access.py` — `!= ACTIVE` already handles SUSPENDED
- `__init__.py` (both) — no new public symbols
- `yaml_loader.py` — YAML grants always start as ACTIVE
- `stores/backup.py` — uses grant_clearance() which handles terminal overwrite

## Implementation Notes

- **RoleClearance is frozen=True**: Must use `dataclasses.replace()` to create updated instances
- **Thread safety**: All engine methods already acquire `self._lock` — maintain this pattern
- **Audit**: New `PactAuditAction.CLEARANCE_TRANSITIONED` (not reusing CLEARANCE_GRANTED)
- **EATP**: Adapt grant_clearance's CapabilityAttestation pattern for transitions
- **Store protocol**: No changes — existing 3-method protocol is sufficient
- **SQLite**: No schema migration — `vetting_status TEXT` already handles new value
- **Bounded collections**: Revoked records now persist and consume slots. Acceptable; eviction-on-overflow handles it. Purge method is a follow-up.
