# Red Team Round 7 — R6 Gap Remediation

**Date**: 2026-03-14
**Scope**: All 13 findings from Red Team Round 6
**Result**: All 13 items fixed, 3 new tests, 433 total tests passing (was 430)

## Items Fixed

### Critical

| # | Finding | Fix |
|---|---------|-----|
| 1 | `errno 40` hardcoded (ELOOP is 62 on macOS) | Added `import errno`, replaced `e.errno == 40` with `e.errno == errno.ELOOP` in `file_lock()` and new `safe_read_json()` |

### High

| # | Finding | Fix |
|---|---------|-----|
| 2 | TOCTOU in check_not_symlink/open pattern | Added `safe_read_json()` to `_locking.py`: uses `os.open(O_NOFOLLOW)` + `os.fdopen()` for atomic symlink-safe reads. All data file reads in `delegation.py`, `holds.py` now use `safe_read_json()` instead of `check_not_symlink()` + `open()`. |
| 3 | `switch_enforcement()` missing async lock | Wrapped in `async with self._async_lock`, delegates to `_switch_enforcement_locked()` |
| 4 | `verify()` missing async lock | Wrapped in `async with self._async_lock`, delegates to `_verify_locked()` |
| 5 | WAL hash bypass (missing `content_hash` tolerated) | Recovery now REJECTS WALs with missing `content_hash` (logs CRITICAL, removes WAL). No backward-compat path since all TrustPlane WALs include the hash. |
| 6 | `assert` used for runtime check | Replaced `assert lock_path.exists()` with `if not lock_path.exists(): raise RuntimeError(...)` — survives Python `-O` |

### Medium

| # | Finding | Fix |
|---|---------|-----|
| 7 | Missing symlink checks in `list_delegates()`, `list_pending()`, `list_all()`, `get_reviews()` | All switched to `safe_read_json()` which has built-in O_NOFOLLOW protection |
| 8 | `_test_dual_binding_signing` always passes | Rewritten: now REQUIRES `reasoning_trace_hash` as top-level field in anchor file. Fails if missing. Verifies hash matches reconstructed trace. |
| 9 | `_test_reasoning_required` doesn't test REASONING_REQUIRED | Extended: now also verifies `reasoning_trace_hash` is present in anchor (dual-binding). |
| 10 | Session ID and project ID missing nonce | Added `secrets.token_hex(4)` nonce to both `project_id` generation in `TrustProject.create()` and `session_id` generation in `AuditSession._generate_id()` |

### Low

| # | Finding | Fix |
|---|---------|-----|
| 11 | `_save_keys` writes private key before chmod | Replaced `write_text()` + `chmod()` with `os.open(path, O_WRONLY|O_CREAT|O_TRUNC, 0o600)` — file created with correct permissions from the start |
| 12 | `repair()` doesn't re-verify after fixing parent links | Added post-repair verification pass that re-walks the anchor chain after fixes |
| 13 | Recursive revocation stack overflow on deep chains | Converted `_build_revocation_plan()` and `_cascade_revoke()` from recursive to iterative (work queue with visited set) |

## Files Modified

| File | Changes |
|------|---------|
| `src/trustplane/_locking.py` | Added `import errno`, `safe_read_json()`. Fixed `errno.ELOOP`, replaced `assert` with `raise RuntimeError`. |
| `src/trustplane/delegation.py` | Imported `safe_read_json`. All file reads use `safe_read_json()`. WAL recovery requires `content_hash`. `_build_revocation_plan()` and `_cascade_revoke()` converted to iterative. |
| `src/trustplane/holds.py` | All file reads use `safe_read_json()`. Removed unused `json` import. |
| `src/trustplane/project.py` | Added `secrets` import, removed `stat` import. Project ID includes nonce. `_save_keys` uses `os.open(0o600)`. `switch_enforcement()` and `verify()` wrapped in async lock. `record_decision()` persists `reasoning_trace_hash` in anchor files. `repair()` includes post-fix verification. |
| `src/trustplane/session.py` | Session ID includes nonce. |
| `src/trustplane/conformance/__init__.py` | `_test_dual_binding_signing` requires `reasoning_trace_hash` field. `_test_reasoning_required` verifies hash presence. |
| `tests/test_concurrency.py` | All WAL tests include `content_hash`. `test_wal_without_hash_still_works` renamed to `test_wal_without_hash_is_rejected`. Added 3 tests: `test_safe_read_json_rejects_symlink`, `test_safe_read_json_reads_regular_files`, `test_safe_read_json_raises_on_missing_file`. |

## Accepted Risks

None. All 13 items from R6 have been addressed.
