# R13 Red Team Report: Store Abstraction Security Review

**Date**: 2026-03-15
**Scope**: Phase 2 store abstraction (TrustPlaneStore protocol, FileSystemTrustPlaneStore, SqliteTrustPlaneStore, migration, config)
**Reviewer**: security-reviewer agent
**Status**: ALL FINDINGS FIXED

## Files Reviewed

- `packages/trust-plane/src/trustplane/store/__init__.py` (protocol)
- `packages/trust-plane/src/trustplane/store/filesystem.py`
- `packages/trust-plane/src/trustplane/store/sqlite.py`
- `packages/trust-plane/src/trustplane/migrate.py`
- `packages/trust-plane/src/trustplane/config.py`
- `packages/trust-plane/src/trustplane/project.py` (store wiring)

## Findings

### H1: Missing `validate_id()` in `store_review()` — FIXED

**Severity**: HIGH
**Location**: `sqlite.py:store_review()`, `filesystem.py:store_review()`
**Risk**: Path traversal (filesystem), contract violation (both)
**Description**: `store_review()` uses `review.hold_id` and `review.delegate_id` directly in filesystem paths and SQL queries without calling `validate_id()` first. Every other store method validates its IDs.
**Fix**: Added `validate_id(review.hold_id)` and `validate_id(review.delegate_id)` to both implementations.

### H2: Non-atomic migration in `migrate_to_sqlite()` — FIXED

**Severity**: HIGH
**Location**: `migrate.py:migrate_to_sqlite()`
**Risk**: Partial migration on failure leaves corrupted state
**Description**: The function opens `BEGIN IMMEDIATE` but then calls `store_*()` methods that each internally call `conn.commit()`, breaking the enclosing transaction. A failure mid-migration would leave a partially-populated database.
**Fix**: Replaced `store_*()` calls with raw parameterized SQL inserts directly on the connection, preserving the single-transaction atomicity guarantee.

### M1: No file permissions on `trust.db` — FIXED

**Severity**: MEDIUM
**Location**: `sqlite.py:initialize()`
**Risk**: Database readable by other users on shared systems
**Description**: Private key files are created with `0o600` but the SQLite database file has no permission restriction after creation. On shared systems, other users could read trust records.
**Fix**: Added `os.chmod(self._db_path, 0o600)` after table creation in `initialize()`, with `OSError` fallback for non-POSIX systems.

### M2: No positive limit validation in `list_*` methods — FIXED

**Severity**: MEDIUM
**Location**: All `list_*()` methods in both `sqlite.py` and `filesystem.py`
**Risk**: `LIMIT -1` in SQLite returns ALL rows, bypassing BOUNDED*RESULTS contract
**Description**: A negative `limit` parameter passes through to SQL `LIMIT -1`, which SQLite interprets as "no limit". This bypasses the BOUNDED_RESULTS store security contract requirement.
**Fix**: Added `limit = max(0, limit)` at the top of every `list*\*()` method in both backends (12 methods total).

## Verification

- All 841 trust-plane tests pass (1 skipped)
- 73 shadow mode tests pass
- Store conformance suite passes for both backends
- No regressions introduced

## Conclusion

R13 converged at zero remaining findings. All HIGH and MEDIUM issues identified during the store abstraction security gate have been fixed and verified.
