# Red Team Round 10 — Deep Hardening

**Date**: 2026-03-15
**Scope**: All findings from R10 agents (deep-analyst, security-reviewer, gold-standards-validator, intermediate-reviewer)
**Result**: All items fixed, 431 tests passing

## Agent Results

| Agent | Findings | Result |
|-------|----------|--------|
| gold-standards-validator | 0 violations | Fully compliant |
| deep-analyst | 1 MEDIUM, 3 LOW, 3 INFO | All fixed |
| security-reviewer | 3 HIGH, 5 MEDIUM, 3 LOW | All fixed |
| intermediate-reviewer | 2 important, 3 minor | All fixed |

## Items Fixed

### HIGH

| # | Finding | Fix |
|---|---------|-----|
| 1 | `session.py`: `rglob()` follows symlinked directories in snapshot traversal | Added `is_symlink()` check on both base paths and enumerated files to skip symlinks during traversal. |
| 2 | `session.py`: `_snapshot_files` has no file count limit — unbounded I/O DoS | Added `_MAX_SNAPSHOT_FILES = 10_000` cap with warning log when limit reached. |
| 3 | `proxy.py`: `**arguments` forwarded to handler without filtering — argument injection | Added `_filter_arguments()` that introspects handler signature via `inspect.signature()` and filters to accepted parameters only. Handlers with `**kwargs` receive all arguments (opt-in). |

### MEDIUM

| # | Finding | Fix |
|---|---------|-----|
| 4 | `models.py`: `allowed_hours` wrap-around comparison incorrect for overnight windows | Added `__post_init__` validation: `start >= end` raises ValueError ("wrap-around windows not supported"). Hours validated 0-23. |
| 5 | `models.py`: `allowed_hours` list length not validated in `from_dict` | Changed to `if ah and len(ah) >= 2` — short lists produce `None` instead of IndexError. |
| 6 | `models.py`: `FinancialConstraints` accepts negative cost limits | Added `__post_init__` validation rejecting negative `max_cost_per_session` and `max_cost_per_action`. |
| 7 | `models.py`: `TemporalConstraints` accepts negative time limits | Added `__post_init__` validation rejecting negative `max_session_hours` and `cooldown_minutes`. |
| 8 | `proxy.py`: error messages expose internal server names and tool names | Genericized to "Requested server is not registered" / "Requested tool is not registered" / "Action blocked by constraint envelope". Details logged at WARNING level. |
| 9 | `proxy.py`: `_call_log` grows unbounded in long-running sessions | Changed from `list` to `collections.deque(maxlen=10_000)`. |
| 10 | `mcp_server.py`: cached project never invalidated — stale constraints | Added manifest mtime check in `_get_project()`. Reloads project when `manifest.json` changes on disk. |
| 11 | `mcp_server.py`: `confidence` parameter not validated before DecisionRecord | Added `0.0 <= confidence <= 1.0` check with clean error return before constructing record. |
| 12 | `project.py`: `_load_keys` uses `exists()` before O_NOFOLLOW read — minor TOCTOU | Removed `exists()` pre-check. Let `_safe_read_text` raise `FileNotFoundError` directly, caught and re-raised with descriptive message. |

### LOW

| # | Finding | Fix |
|---|---------|-----|
| 13 | `_locking.py`: redundant `try/except Exception: raise` in `safe_read_json` | Removed. `with f:` context manager handles cleanup. |
| 14 | Product brief: test count 433 → 431, test file count 19 → 21, version v0.12.0 → v0.2.0 | Updated all three values. |
| 15 | `test_proxy.py`: assertions reference old verbose error messages | Updated 2 assertions to match new generic messages. |

## Files Modified

| File | Changes |
|------|---------|
| `src/trustplane/models.py` | `FinancialConstraints.__post_init__` (negative validation). `TemporalConstraints.__post_init__` (negative + hours range + wrap-around). `from_dict` length check. |
| `src/trustplane/session.py` | `_snapshot_files`: symlink skip + `_MAX_SNAPSHOT_FILES` cap. |
| `src/trustplane/proxy.py` | `_filter_arguments()` method. `deque(maxlen=10_000)` for call_log. Generic error messages. `inspect` + `deque` imports. |
| `src/trustplane/mcp_server.py` | `_get_project()` mtime-based cache invalidation. `trust_record` confidence validation. |
| `src/trustplane/project.py` | `_load_keys` TOCTOU fix — removed `exists()` pre-check. |
| `src/trustplane/_locking.py` | Removed redundant try/except in `safe_read_json`. |
| `tests/test_proxy.py` | Updated 2 error message assertions. |
| `workspaces/trust-plane/briefs/01-product-brief.md` | Test count, file count, version corrected. |

## Verification

```
$ python -m pytest tests/ -x -q
431 passed, 1 warning in 7.46s
```

## Accepted Risks

None. All R10 items have been addressed.
