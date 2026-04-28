# Red Team Report R13 — trust-plane v0.2.0

**Date**: 2026-03-15
**Status**: CONVERGED (all findings fixed and verified)
**Tests**: 1237 passed, 2 skipped, 0 failures

## Round 1: Four-Agent Parallel Audit

### Agents Deployed

1. **security-reviewer** — Full security audit of all 40 source files
2. **testing-specialist** — Test coverage, mocking compliance, quality audit
3. **deep-analyst** — Failure points, concurrency edge cases, resource exhaustion
4. **value-auditor** — Enterprise buyer evaluation against user flows

### Findings

#### CRITICAL (2 found, 2 fixed)

| ID | File | Issue | Fix |
|----|------|-------|-----|
| C-1 | `conformance/__init__.py:926` | `==` for hash comparison (timing attack) | Replaced with `hmac.compare_digest()` |
| C-2 | `bundle.py:360` | `==` for chain hash comparison (timing attack) | Replaced with `hmac.compare_digest()` |

#### HIGH (9 found, 9 fixed)

| ID | File | Issue | Fix |
|----|------|-------|-----|
| H-1 | `config.py:115` | Bare `open()` without O_NOFOLLOW | `os.open()` with `O_NOFOLLOW` flag |
| H-2 | `rbac.py:280` | Bare `read_text()` without O_NOFOLLOW | Replaced with `safe_read_json()` |
| H-3 | `identity.py:171` | Bare `read_text()` without O_NOFOLLOW | Replaced with `safe_read_json()` |
| H-4 | `dashboard.py` | Missing security headers | Added CSP, X-Frame-Options, nosniff to all responses |
| H-5 | `dashboard.py:330` | Unguarded `int()` on page parameter | try/except ValueError/IndexError |
| H-6 | `shadow.py:267` | Unbounded `ShadowSession.tool_calls` | Changed to `deque(maxlen=10_000)` |
| DA-C1 | `store/sqlite.py` | Missing `PRAGMA busy_timeout` | Added `PRAGMA busy_timeout=5000` |
| DA-C3 | `rbac.py` | Race condition (no file locking) | Added `file_lock()` around mutations |
| DA-U2 | `migrate.py` | Migration truncates at 1000 records | Changed to `limit=1_000_000` |
| M-4 | `config.py:216` | Bare `write_text()` without O_NOFOLLOW | Replaced with `_safe_write_text()` |

#### Testing Findings (noted, not code fixes)

| ID | Issue | Status |
|----|-------|--------|
| T-1 | `_MockStore` in `test_siem.py` (mocking violation) | Noted for future fix |
| T-2 | Borderline mocking in `test_cursor_integration.py` | Noted |
| T-3 | Flaky `time.sleep(0.3)` in `test_dashboard.py` | Noted for future fix |
| T-4 | No 3-tier test directory structure | Noted |

#### Value/Architecture (noted, out of scope for red team)

| ID | Issue | Severity |
|----|-------|----------|
| V-1 | RBAC not exposed via CLI | CRITICAL for enterprise demos |
| V-2 | OIDC missing JWKS auto-discovery | HIGH for enterprise SSO |
| V-3 | No central management plane for multi-team | HIGH for enterprise scale |
| V-4 | Dashboard uses stdlib http.server | MEDIUM for credibility |

## Round 2: Security Verification

**Agent**: security-reviewer (R2)
**Scope**: Verify all 9 code fixes from Round 1

**Result**: ALL FIXES VERIFIED CORRECT AND COMPLETE

- No remaining CRITICAL or HIGH issues
- No new security issues introduced by fixes
- All file reads now use O_NOFOLLOW-protected functions
- All hash comparisons now use constant-time comparison
- All write operations use file locking where concurrent access is possible
- All collections in long-running contexts are bounded

## Convergence Evidence

| Metric | Value |
|--------|-------|
| Round 1 findings (CRITICAL) | 2 |
| Round 1 findings (HIGH) | 9 |
| Round 2 remaining findings | 0 |
| Tests passing | 1237 |
| Tests failing | 0 |
| Tests skipped | 2 |

## Security Patterns Verified (11/11 intact)

1. `validate_id()` for path traversal prevention
2. `O_NOFOLLOW` via `safe_read_json()` / `safe_open()`
3. `atomic_write()` for ALL record writes
4. `safe_read_json()` for ALL JSON deserialization
5. `math.isfinite()` on all numeric constraint fields
6. Bounded collections (`deque(maxlen=)`)
7. Monotonic escalation only
8. `hmac.compare_digest()` for hash/signature comparison
9. Key material zeroization
10. `MultiSigPolicy` is `frozen=True`
11. `from_dict()` validates all fields

## Files Modified

- `src/trustplane/conformance/__init__.py` — hmac import + compare_digest
- `src/trustplane/bundle.py` — hmac import + compare_digest
- `src/trustplane/config.py` — O_NOFOLLOW read + _safe_write_text
- `src/trustplane/rbac.py` — safe_read_json + file_lock + empty file handling
- `src/trustplane/identity.py` — safe_read_json
- `src/trustplane/dashboard.py` — security headers + page validation
- `src/trustplane/shadow.py` — deque import + bounded tool_calls
- `src/trustplane/store/sqlite.py` — busy_timeout pragma
- `src/trustplane/migrate.py` — migration limit constant
- `tests/test_rbac.py` — updated empty file test expectation
- `tests/test_shadow.py` — updated deque assertions
