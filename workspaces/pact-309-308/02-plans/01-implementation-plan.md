# Implementation Plan: #309 SUSPENDED VettingStatus + FSM

## Scope

- **#309**: 6 production files, 6 test files, ~100 lines total
- **#308**: No Python work (tracking issue for kailash-rs)

## Design Decisions (requiring approval)

1. **FSM includes SUSPENDED->ACTIVE and EXPIRED->ACTIVE** — reinstatement and renewal are core use cases
2. **grant_clearance() allows unconditional overwrite for terminal/missing states** — FSM validation only for PENDING, ACTIVE, SUSPENDED
3. **New PactAuditAction.CLEARANCE_TRANSITIONED** — distinct from CLEARANCE_GRANTED
4. **EATP capability attestation on transitions** — adapted from grant pattern, with status in constraints

## Implementation Order

### Phase 1: Domain model (clearance.py + tests)

1. Add `SUSPENDED = "suspended"` to VettingStatus enum
2. Add `_VALID_TRANSITIONS` table
3. Add `validate_transition(from_status, to_status)` raising PactError
4. Tests: SUSPENDED enum value, full transition matrix (valid + invalid pairs)

### Phase 2: Store behavior change (store.py, sqlite.py + tests)

5. `MemoryClearanceStore.revoke_clearance()`: use `dataclasses.replace()` to set REVOKED, store back
6. `SqliteClearanceStore.revoke_clearance()`: `UPDATE SET vetting_status='revoked'` instead of DELETE
7. Tests: verify `get_clearance()` returns REVOKED record after revoke (not None)

### Phase 3: Engine methods (engine.py, audit.py + tests)

8. Add `CLEARANCE_TRANSITIONED` to PactAuditAction
9. Add FSM validation to `grant_clearance()` (only for living states)
10. Add `transition_clearance(role_address, new_status)` method with lock, FSM validation, audit, EATP
11. Add `"transition_clearance"` to `_ReadOnlyGovernanceView._BLOCKED` set
12. Tests: transition_clearance valid/invalid, grant over terminal, revoke audit trail preserved

### Phase 4: Cross-SDK

13. File kailash-rs issue for SUSPENDED + FSM alignment (cross-sdk label)

## Estimated Size

~100 lines production code, ~150 lines tests. Single session, single PR.
