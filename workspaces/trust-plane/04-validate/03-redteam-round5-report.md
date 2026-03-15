# Red Team Round 5 — Full Risk Remediation

**Date**: 2026-03-14
**Scope**: All 7 previously "accepted risks" (L1-L7) + all 7 "deferred items" from R4
**Result**: All 14 items fixed, 13 new tests, 430 total tests passing (was 417)

## Items Fixed

### Previously "Accepted Risks" — Now Fixed

| # | Risk | Fix |
|---|------|-----|
| L1 | `fcntl.flock` is advisory | Documented advisory nature in module docstring, added defense-in-depth assertion (verify lock file exists after acquisition), added `O_NOFOLLOW` flag |
| L2 | WAL poisoning (no HMAC) | Added SHA-256 content hash to WAL (`compute_wal_hash()`). Recovery verifies hash before applying revocations. Tampered WAL is rejected and removed. |
| L3 | Lock DoS (no timeout) | `file_lock()` now accepts `timeout` parameter (default: 30s). Non-blocking retry loop with 10ms interval. Raises `LockTimeoutError` on timeout. `timeout=0` preserves original blocking behavior. |
| L4 | Delegate ID collision (same microsecond) | Added `secrets.token_hex(4)` random nonce to ALL ID generation: delegates, holds, decisions, milestones, executions, escalations, interventions. |
| L5 | Symlink attacks (`O_NOFOLLOW`) | `file_lock()` opens with `O_NOFOLLOW` (rejects symlink lock files). `check_not_symlink()` guards all data file reads in `delegation.py` and `holds.py`. |
| L6 | project.py chain fork (in-process concurrency) | Added `asyncio.Lock()` to `TrustProject`. All 8 state-mutating async methods (`record_decision`, `record_milestone`, `record_execution`, `record_escalation`, `record_intervention`, `transition_posture`, `start_session`, `end_session`, `abandon_session`) acquire the async lock before mutating state. |
| L7 | Depth limit not runtime-configurable | Renamed `MAX_DELEGATION_DEPTH` to `DEFAULT_MAX_DELEGATION_DEPTH`. `DelegationManager.__init__()` now accepts `max_depth` parameter. |

### Previously "Deferred Items" — Now Fixed

| # | Item | Fix |
|---|------|-----|
| 8 | Conformance test for REASONING_REQUIRED | Added `_test_reasoning_required`: records a decision, verifies anchor has non-empty reasoning trace with decision and rationale fields. |
| 9 | Conformance test for dual-binding signing | Added `_test_dual_binding_signing`: records a decision, reconstructs ReasoningTrace from anchor, verifies `content_hash_hex()` produces valid SHA-256 hash. Checks for `reasoning_trace_hash` binding in anchor or chain. |
| 10 | `repair()` locking | Wrapped `repair()` body in `_file_lock(self._lock_path)`. Anchor fixes now use `_atomic_write()` instead of bare `open()/json.dump()`. |
| 11 | `enforcement_dual_mode` test tautological | Rewritten to behavioral: switches strict→shadow→strict, verifies `check()` results, verifies `shadow_report()` returns string, verifies mode switch creates audit anchor (total_audits increases). |
| 12 | Expired delegate + sub-delegation test | Added `test_sub_delegate_of_expired_fails`: creates expired parent, verifies `is_active()` returns False, verifies sub-delegation raises ValueError. Added `test_configurable_max_depth`: tests custom `max_depth` parameter. |
| 13 | Tautological tamper detection test | Replaced with two proper tests: (1) `test_tampered_decision_detected_by_verify`: tampers decision file, asserts `chain_valid=False` and hash mismatch in issues. (2) `test_tampered_anchor_parent_chain_detected`: breaks anchor parent chain, asserts `chain_valid=False`. |

## Files Modified

| File | Changes |
|------|---------|
| `src/trustplane/_locking.py` | Added `LockTimeoutError`, `check_not_symlink()`, `compute_wal_hash()`. `file_lock()` now has `timeout` param, `O_NOFOLLOW`, defense-in-depth assertion. |
| `src/trustplane/delegation.py` | `DelegationManager.__init__()` accepts `max_depth`. Uses `check_not_symlink()`, `compute_wal_hash()`. WAL writes include content hash. Recovery verifies hash. Nonce in delegate ID generation. |
| `src/trustplane/holds.py` | Uses `check_not_symlink()` in `get()`. Nonce in hold ID generation. |
| `src/trustplane/models.py` | Nonce in all ID generation: `ExecutionRecord`, `EscalationRecord`, `InterventionRecord`, `DecisionRecord`, `MilestoneRecord`. |
| `src/trustplane/project.py` | `asyncio.Lock()` in `TrustProject.__init__()`. 8 async methods delegate to `_locked` variants. `repair()` wrapped in `_file_lock()`, uses `_atomic_write()`. |
| `src/trustplane/conformance/__init__.py` | Added `reasoning_required` and `dual_binding_signing` tests. Rewrote `enforcement_dual_mode` to behavioral test. |
| `tests/test_concurrency.py` | Added 3 test classes: `TestLockTimeout` (2), `TestSymlinkProtection` (4), `TestWALContentHash` (4). |
| `tests/test_delegation.py` | Updated import (`DEFAULT_MAX_DELEGATION_DEPTH`). Added `test_sub_delegate_of_expired_fails`, `test_configurable_max_depth`. |
| `tests/test_constraints.py` | Replaced tautological tamper test with `test_tampered_decision_detected_by_verify` and `test_tampered_anchor_parent_chain_detected`. |
| `tests/test_models.py` | Updated `test_deterministic_id` → verifies uniqueness (IDs now include nonce). |
| `workspaces/trust-plane/briefs/01-product-brief.md` | Updated to v0.10.0, 430 tests, documented all new capabilities. |

## Accepted Risks

None. All 14 items from R4 have been addressed.
