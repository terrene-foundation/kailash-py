# Red Team Round 9 — R8 Residual Hardening

**Date**: 2026-03-15
**Scope**: All findings from Red Team Round 9 agents (deep-analyst, security-reviewer, gold-standards-validator, intermediate-reviewer)
**Result**: All items fixed, 431 tests passing, zero bare file operations in production code

## Items Fixed

### High

| # | Finding | Fix |
|---|---------|-----|
| 1 | `project.py`: `_save_keys()` public key write missing O_NOFOLLOW | Added O_NOFOLLOW flag to public key `os.open()` call, matching private key protection. |
| 2 | `project.py`: `milestone()` uses `path.read_bytes()` — bypasses O_NOFOLLOW | Created `_safe_hash_file()` helper with O_NOFOLLOW + fdopen binary + chunked SHA-256. All milestone hashing now uses it. |
| 3 | `cli.py`: export and audit output writes use bare `write_text()` | Converted both to use `_safe_write_text()` from `_locking` module. |
| 4 | `project.py`: `_safe_read_text()` fd leak on `os.fdopen()` failure | Restructured to separate try/except around `os.fdopen()` with `os.close(fd)` in except handler, matching `safe_read_json()` pattern. |

### Medium

| # | Finding | Fix |
|---|---------|-----|
| 5 | `bundle.py`: bare `except Exception: pass` swallows mirror summary errors | Changed to `logger.debug("Mirror summary unavailable for bundle", exc_info=True)` for debuggability. |
| 6 | `_locking.py`: dead `check_not_symlink()` function (superseded by O_NOFOLLOW) | Removed function entirely. Updated module docstring to reference current pattern. |
| 7 | `_locking.py`: stale docstring referencing `is_symlink()` checks | Updated to reference `safe_read_json() with O_NOFOLLOW for atomic symlink protection`. |
| 8 | `test_concurrency.py`: imports and tests dead `check_not_symlink` | Removed import and 2 tests (`test_check_not_symlink_passes_regular_files`, `test_check_not_symlink_rejects_symlinks`). |

## Files Modified

| File | Changes |
|------|---------|
| `src/trustplane/project.py` | O_NOFOLLOW on pub key write. `_safe_hash_file()` helper. `_safe_read_text()` fd leak fix. |
| `src/trustplane/cli.py` | Export and audit output writes use `_safe_write_text()`. |
| `src/trustplane/bundle.py` | `except Exception: pass` → `logger.debug(...)`. |
| `src/trustplane/_locking.py` | Removed `check_not_symlink()`. Updated module docstring. Updated `safe_read_json()` docstring. |
| `tests/test_concurrency.py` | Removed `check_not_symlink` import and 2 dead tests. |

## Verification

```
$ grep -r "with open\|\.read_text()\|\.read_bytes()\|\.write_text(" src/trustplane/
# Zero results — all bare file operations eliminated
```

431 tests passing. 2 tests removed (dead `check_not_symlink` tests). Net: 433 → 431.

## Accepted Risks

None. All R9 items have been addressed.
