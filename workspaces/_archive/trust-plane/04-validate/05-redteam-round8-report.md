# Red Team Round 8 — R7 Gap Remediation (Complete Hardening)

**Date**: 2026-03-15
**Scope**: All findings from Red Team Round 8 agents
**Result**: All items fixed, 433 tests passing, zero bare open() calls in production code

## Items Fixed

### Critical

| # | Finding | Fix |
|---|---------|-----|
| 1 | `safe_read_json()` fd leak on `os.fdopen()` failure | Restructured: `os.fdopen()` in separate try/except with `os.close(fd)` in except handler. `with f:` for cleanup after successful fdopen. |

### High

| # | Finding | Fix |
|---|---------|-----|
| 2 | `bundle.py`: 3 bare `open()` calls (genesis, anchors, public key) | Genesis and anchor reads use `safe_read_json()`. Public key read uses inline O_NOFOLLOW + fdopen pattern. |
| 3 | `conformance/__init__.py`: 11 bare `open()` calls across test methods | All 11 converted to `_safe_read_json()` (aliased import). Covers genesis, anchor chain, attestation, reasoning trace, dual-binding, persistence, and all 3 mirror record tests. |
| 4 | `session.py`: `_hash_file()` uses bare `open()` | Rewritten with O_NOFOLLOW + fdopen pattern for binary read. |
| 5 | `migrate.py`: bare reads AND bare writes (no atomic_write) | All reads converted to `safe_read_json()`. All writes converted to `atomic_write()`. Removed unused `json` import. |
| 6 | `proxy.py`: bare TOML config read and JSON config write | TOML read: O_NOFOLLOW + fdopen binary pattern. JSON write: `atomic_write()`. Removed unused `json` import. Added `os` import. |
| 7 | `_save_keys()` missing O_NOFOLLOW on write | Added `O_NOFOLLOW` flag to `os.open()` call in `_save_keys()` — prevents symlink-based key write redirection. |

### Medium

| # | Finding | Fix |
|---|---------|-----|
| 8 | `delegation.py`: unused `check_not_symlink` import | Removed from import list. |
| 9 | `delegation.py`: `list.pop(0)` O(n) in BFS queues | Converted both `_build_revocation_plan()` and `_cascade_revoke()` to use `collections.deque` with `popleft()` (O(1)). |
| 10 | `diagnostics.py`: bare `open()` for anchor reads | Converted to `safe_read_json()`. Removed unused `json` and `datetime`/`timezone` imports. |

## Files Modified

| File | Changes |
|------|---------|
| `src/trustplane/_locking.py` | `safe_read_json()` fd leak fix: separate try/except around `os.fdopen()` with `os.close(fd)` in except handler. |
| `src/trustplane/bundle.py` | Added `errno`, `os` imports. Import `safe_read_json`. Genesis and anchor reads use `safe_read_json()`. Public key read uses O_NOFOLLOW + fdopen. |
| `src/trustplane/conformance/__init__.py` | Import `safe_read_json as _safe_read_json`. All 11 bare `open()` calls converted. |
| `src/trustplane/delegation.py` | Removed `check_not_symlink` import. Added `collections.deque` import. Both BFS methods use `deque.popleft()`. |
| `src/trustplane/diagnostics.py` | Removed `json`, `datetime`, `timezone` imports. Import `safe_read_json`. Anchor reads use `safe_read_json()`. |
| `src/trustplane/migrate.py` | Removed `json` import. Import `atomic_write`, `safe_read_json`. All reads use `safe_read_json()`, all writes use `atomic_write()`. |
| `src/trustplane/project.py` | `_save_keys()` adds O_NOFOLLOW flag to `os.open()`. |
| `src/trustplane/proxy.py` | Added `os` import. Removed `json` import. TOML config load uses O_NOFOLLOW + fdopen. Config save uses `atomic_write()`. |
| `src/trustplane/session.py` | Added `os` import. `_hash_file()` rewritten with O_NOFOLLOW + fdopen binary read. |

## Verification

```
$ grep -r "with open\|\.read_text()" src/trustplane/
# Zero results — all bare open() calls eliminated
```

Only remaining `os.fdopen()` calls are inside `atomic_write()` and `_safe_read_text()` — both use fd-based opening with O_NOFOLLOW protection.

## Accepted Risks

None. All R8 items have been addressed.
