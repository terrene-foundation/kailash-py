# Red Team Round 3 — TrustPlane Validation Report

**Date**: 2026-03-14
**Scope**: All TrustPlane code + modified spec documents
**Agents deployed**: deep-analyst, gold-standards-validator, intermediate-reviewer, security-reviewer, eatp-expert
**Follow-up agents**: EATP first-principles (conformance spec analysis), deep-analyst (concurrency design), SDK explorers (kailash-py + kailash-rs)

---

## Summary

| Category | Found | Fixed in R3 | Deferred to Implementation |
|----------|-------|-------------|---------------------------|
| CRITICAL | 2 | 2 | 0 |
| HIGH | 5 | 5 | 0 |
| MEDIUM | 4 | 4 | 0 |
| Accepted Risks (escalated) | 3 | 0 | 3 |

After R3 fixes: **396 tests passing**, zero regressions.

The 3 "accepted risks" were escalated to deep-dive analysis and are now **approved for implementation** — they are NOT acceptable as deferred risks.

---

## Fixes Applied in Round 3

### CRITICAL

1. **Path traversal bypass in `check()`** — Added `posixpath.normpath()` canonicalization + case-insensitive comparison. Test: `test_path_traversal_blocked`.

2. **XSS in `to_html()`** — Added `html.escape()` on all interpolated values (project name, author, action, resource, chain hash, bundle JSON). Import: `html as html_mod`.

### HIGH

3. **Case-sensitive blocked actions** — `"Fabricate"` no longer bypasses `"fabricate"`. Lowercased comparison. Test: `test_case_insensitive_blocked_action`.

4. **Fail-open on enforcer exception** — Changed from `AUTO_APPROVED` to `HELD` (fail-to-human). Comment updated to explain rationale.

5. **Allowlist-to-empty bypasses `is_tighter_than()`** — When parent has allowlist and child drops it, returns `False` (loosening). Applied to `allowed_actions`, `read_paths`, `write_paths`, `allowed_channels`. Test: `test_dropping_allowlist_is_loosening`.

6. **None-to-limit removal not caught** — When parent has numeric limit and child has `None`, returns `False`. Applied to `max_cost_per_session`, `max_cost_per_action`, `max_session_hours`, `allowed_hours`. Tests: `test_none_to_limit_removal_is_loosening`, `test_adding_limit_where_none_existed_is_tighter`.

7. **Audit callback missing traceback** — Added `exc_info=True` to `logger.warning` in `_cascade_revoke`.

### MEDIUM

8. **Temporal `allowed_hours` not checked** — Added window subset validation (child start >= parent start, child end <= parent end). Tests: `test_narrower_allowed_hours_is_tighter`, `test_wider_allowed_hours_is_loosening`, `test_dropping_allowed_hours_is_loosening`.

9. **`cooldown_minutes` reduction not checked** — Added `self >= other` check. Test: `test_longer_cooldown_is_tighter`.

10. **`blocked_patterns` never enforced** — Added `fnmatch.fnmatch()` matching in `check()`. Test: `test_blocked_patterns_enforced`.

11. **Missing `is_tighter_than()` checks** — Added: `required_outputs` (superset), `blocked_patterns` (superset), `max_cost_per_action` (<=), `budget_tracking` (if parent requires), `requires_review` (superset). Tests: `test_budget_tracking_required_is_tighter`, `test_adding_requires_review_is_tighter`, `test_adding_blocked_patterns_is_tighter`.

### DOC FIXES

12. **Companion paper lettering** — All 5 theses now self-identify (e.g., "This paper is Hong (2026b)") and use consistent letter suffixes (a-e) in "See also" footers.

13. **Conformance test `mirror` element** — Added `assert "mirror" in elements` to `test_suite_covers_all_elements`.

---

## Escalated Risks — Analysis and Decisions

### Risk 1: Conformance Suite Gameable

**Analysis**: 8 tests can be passed by stub implementations. The EATP spec (`07-conformance.md`) requires behavioral semantics — cryptographic verification, semantic scope matching, constraint checking — not just structural existence checks.

**Specific weak tests**:
- `_test_constraint_hash_stable`: `hash == hash` (same object, always true)
- `_test_constraint_monotonic_tightening`: Creates its own envelopes, never tests the project
- `_test_constraint_enforcement`: Wrong `check()` call signature
- `_test_attestation_supported`: Checks files exist, not validity
- `_test_persistent_storage`: Checks directory exists, not round-trip
- `_test_posture_five_levels`: Only checks 1 posture, not all 5 reachable
- `_test_mirror_*` (3 tests): `hasattr` — no-op method passes

**Decision**: Rewrite all 8 to behavioral verification. The reference implementation's conformance suite must be ungameable.

### Risk 2: `required_outputs` Not Enforced

**Analysis**: EATP expert confirmed `required_outputs` is NOT in the EATP spec. The constraint model bounds what agents MAY do, not what they MUST produce. Neither kailash-py nor kailash-rs has this field.

**Decision**: Remove `required_outputs` from `OperationalConstraints`. Completion criteria belong in CO Layer 4 (workflow quality gates), not EATP constraint envelopes. Update `is_tighter_than()` to remove the superset check added in R3.

### Risk 3: Concurrent Multi-Stakeholder Operations

**Analysis**: Deep-analyst identified 7 risks, 2 CRITICAL (active delegate under revoked parent, orphaned sub-delegate). TrustPlane is designed for teams — multiple delegates, concurrent revocation, simultaneous hold resolution.

**SDK landscape**:
- kailash-rs: Already has `fs4` cross-process locking, `Mutex`/`RwLock`, path validation
- kailash-py: Has `threading.RLock` (thread-safe only, NOT process-safe) + atomic writes. **kailash-py dev assigned to upgrade to cross-process locking.**
- TrustPlane: Has `fcntl.flock` in project.py but DelegationManager and HoldManager have zero locking

**Decision**: Implement all 3 layers:
1. Atomic writes (write-to-temp-then-rename) in delegation.py and holds.py
2. Directory-level file locks (`fcntl.flock`) for all mutating operations
3. Audit write-ahead log (WAL) for revocation audit recovery

Extract `_file_lock()` from project.py to shared `trustplane/_locking.py`.

---

## Files Modified in Round 3

| File | Changes |
|------|---------|
| `src/trustplane/project.py` | Path normalization, case-insensitive checks, blocked_patterns, fail-to-HELD, imports |
| `src/trustplane/bundle.py` | XSS prevention via html.escape on all interpolated values |
| `src/trustplane/models.py` | Complete `is_tighter_than()` rewrite — all dimensions, all fields |
| `src/trustplane/delegation.py` | Audit callback `exc_info=True` |
| `tests/test_constraints.py` | 13 new tests (tightening, path traversal, case sensitivity, patterns) |
| `tests/test_conformance.py` | Added mirror element coverage check |
| `docs/02-standards/publications/CARE-Core-Thesis.md` | Self-identification as Hong (2026a) |
| `docs/02-standards/publications/EATP-Core-Thesis.md` | Self-identification as Hong (2026b) (R2) |
| `docs/02-standards/publications/CO-Core-Thesis.md` | Self-identification as Hong (2026c), letter suffixes |
| `docs/02-standards/publications/COC-Core-Thesis.md` | Self-identification as Hong (2026d), letter suffixes |
| `docs/02-standards/publications/Constrained-Organization-Thesis.md` | Self-identification as Hong (2026e), added COC reference |
