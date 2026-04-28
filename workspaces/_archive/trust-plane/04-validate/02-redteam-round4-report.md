# Red Team Round 4 — M11 Hardening Validation

**Date**: 2026-03-14
**Scope**: M11 code changes (locking, atomic writes, WAL, conformance, delegation)
**Agents**: deep-analyst, eatp-expert, security-reviewer, intermediate-reviewer
**Result**: 8 fixes applied, 6 new tests, 417 total tests passing

## Attack Vectors Tested

### Defended (8 fixes applied)

| # | Attack Vector | Fix |
|---|--------------|-----|
| C1 | **Path traversal** via delegate_id/hold_id → escape trust directory | Added `validate_id()` — rejects IDs with path separators |
| C2 | **`_write_json()` crash** → corrupt manifest.json | Switched to `atomic_write()` (temp+rename) |
| C3 | **`resolve_hold()` TOCTOU** → resolution by revoked delegate | Moved validation + write under single lock scope |
| H1 | **WAL recovery race** → `FileNotFoundError` on concurrent startup | Moved `exists()` check inside lock |
| H2 | **Corrupted WAL** → permanent `JSONDecodeError`, all operations blocked | Added try/except, remove corrupt WAL, log critical |
| H3 | **Cascade cycle** → infinite recursion from circular delegate files | Added `_visited` set to both `_build_revocation_plan` and `_cascade_revoke` |
| H4 | **Attestation conformance fallback** → stub passes CONFORMANT MUST test | Removed fallback, now verifies EATP chain structure |
| H5 | **FD leak in `atomic_write()`** → resource exhaustion under sustained failures | Fixed fd ownership tracking, close on `os.fdopen()` failure |

### Accepted Risks (documented, not fixed)

| # | Risk | Rationale |
|---|------|-----------|
| L1 | `fcntl.flock` is advisory | Design limitation of POSIX. All TrustPlane code paths use it. |
| L2 | WAL poisoning (no HMAC) | Requires architectural change (key derivation). Attacker needs write access to delegates/. |
| L3 | Lock DoS (no timeout) | CLI tool, not long-running server. Acceptable. |
| L4 | Delegate ID collision (same microsecond) | Extremely unlikely. Hash includes name + timestamp. |
| L5 | Symlink attacks (`O_NOFOLLOW`) | Requires more invasive changes. Defer to next round. |
| L6 | project.py chain fork (in-process concurrency) | Requires asyncio lock. Defer to SDK integration. |
| L7 | Depth limit not runtime-configurable | SHOULD-level, not MUST. Module constant is overridable. |

### EATP Spec Compliance (EATP Expert)

- `required_outputs` removal: **CONFIRMED CORRECT** (not in spec)
- Monotonic tightening: **FULLY COMPLIANT** (all 5 dimensions)
- Cascade revocation: **COMPLIANT** (exceeds spec with WAL recovery)
- Conformance levels: **COMPLIANT** (matches Section 7)
- Terminology: **COMPLIANT** (all canonical terms match)
- Missing conformance tests: REASONING_REQUIRED + dual-binding signing (deferred — M12 candidates)

## Deferred Items (M12 candidates)

1. Conformance test for REASONING_REQUIRED constraint type
2. Conformance test for dual-binding signing verification
3. `repair()` locking
4. `enforcement_dual_mode` test should verify behavior, not private attrs
5. Expired delegate + sub-delegation test
6. Tautological tamper detection test fix
7. Symlink protection (`O_NOFOLLOW`)

## Files Modified

| File | Changes |
|------|---------|
| `src/trustplane/_locking.py` | Added `validate_id()`, `_SAFE_ID_RE`; fixed FD leak in `atomic_write()`; added `fsync()` |
| `src/trustplane/delegation.py` | Added ID validation; fixed WAL race + corrupted WAL; cycle detection in cascade; `resolve_hold()` TOCTOU fix |
| `src/trustplane/holds.py` | Added ID validation to `get()` |
| `src/trustplane/project.py` | `_write_json()` now uses `atomic_write()` |
| `src/trustplane/conformance/__init__.py` | Attestation test verifies EATP chain structure, no fallback |
| `tests/test_concurrency.py` | Added 6 tests: 5 path traversal + 1 corrupted WAL recovery |
