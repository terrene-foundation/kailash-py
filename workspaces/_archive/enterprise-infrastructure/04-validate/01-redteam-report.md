# Red Team Validation Report — Enterprise Infrastructure

**Date**: 2026-03-17
**Branch**: `release/v1.0.0`
**Workspace**: enterprise-infrastructure
**Red Team**: security-reviewer, deep-analyst, gold-standards-validator, testing-specialist + manual code review

---

## Test Baseline

| Suite                              | Passed | Failed | Notes                                                    |
| ---------------------------------- | ------ | ------ | -------------------------------------------------------- |
| Unit (infrastructure)              | 193    | 0      | All 8 test files green                                   |
| Integration (Redis queue)          | 1      | 2      | `test_full_roundtrip` + `test_worker_executes_task` fail |
| Full regression (unit+integration) | 5897   | 55     | 55 failures are pre-existing (unrelated to infra)        |

---

## Consolidated Findings

### CRITICAL — Must Fix Before Release

| ID  | Finding                                                                                                                                     | Source                          | Files                          |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- | ------------------------------ |
| C1  | **ConnectionManager has no transaction support** — All multi-statement operations are non-atomic. Root cause of C2-C4.                      | deep-analyst                    | `connection.py`                |
| C2  | **Event store `append()` race condition** — Two concurrent appenders read same MAX(sequence), one gets UNIQUE violation and events are lost | security, deep-analyst, testing | `event_store.py:112-132`       |
| C3  | **Idempotency `try_claim()` TOCTOU race** — check-then-act across 3 non-atomic queries                                                      | security, deep-analyst, testing | `idempotency_store.py:176-238` |
| C4  | **SQL task queue `dequeue()` non-atomic** — FOR UPDATE SKIP LOCKED lock released between SELECT and UPDATE in auto-commit mode              | deep-analyst                    | `task_queue.py:210-269`        |
| C5  | **`AUTOINCREMENT` in event store DDL** — SQLite-specific keyword, fails on PostgreSQL/MySQL                                                 | security                        | `event_store.py:62`            |
| C6  | **SQL identifier injection in dialect methods** — `table`, `columns`, `path` params in upsert/insert_ignore/json_extract not validated      | security                        | `dialect.py:85-128, 177-308`   |
| C7  | **Zero concurrency tests** — No tests for any race condition scenario                                                                       | testing                         | all stores                     |
| C8  | **`queue_factory.py` has zero test coverage** — Critical entry point untested                                                               | testing                         | `queue_factory.py`             |

### HIGH — Should Fix Before Merge

| ID  | Finding                                                                                        | Source         | Files                             |
| --- | ---------------------------------------------------------------------------------------------- | -------------- | --------------------------------- |
| H1  | **Unbounded `InMemoryExecutionStore._store`** — Grows without limit in long-running processes  | security       | `execution_store.py:276`          |
| H2  | **`BLOB` type in checkpoint DDL** — PostgreSQL uses `BYTEA`, not `BLOB`                        | manual review  | `checkpoint_store.py:58`          |
| H3  | **Integration test bugs** — Wrong `connect()` API usage, nonexistent `StartNode`               | manual review  | `test_redis_queue_integration.py` |
| H4  | **Missing `__init__.py` exports** — `create_task_queue`, `SQLTaskMessage`, `EventStoreBackend` | gold-standards | `infrastructure/__init__.py`      |
| H5  | **No PG connection pool limits** — `asyncpg.create_pool()` with no `max_size`                  | security       | `connection.py:250`               |
| H6  | **`purge_completed()` untested**                                                               | testing        | `task_queue.py:379-418`           |
| H7  | **Worker.\_tasks uses O(n) list** — Should be set for O(1) removal                             | security       | `distributed.py:621`              |

### MEDIUM

| ID  | Finding                                                              | Source         |
| --- | -------------------------------------------------------------------- | -------------- |
| M1  | Checkpoint `save()` TOCTOU — SELECT+INSERT/UPDATE not atomic         | manual review  |
| M2  | Missing `@pytest.mark.asyncio` in 3 test files (auto mode mitigates) | gold-standards |
| M3  | No test for duplicate `run_id` on `record_start()`                   | testing        |
| M4  | `SQLTaskMessage.to_dict()`/`from_dict()` untested directly           | testing        |

### LOW

| ID  | Finding                                 | Source         |
| --- | --------------------------------------- | -------------- |
| L1  | `test_task_queue.py` missing logger     | gold-standards |
| L2  | DLQ backoff formula not directly tested | testing        |

---

## Fix Plan (Convergence Round 1)

### Phase A: DDL Portability (C5, H2)

- Remove `AUTOINCREMENT` from event store (SQLite auto-increments INTEGER PRIMARY KEY anyway)
- Add dialect-aware DDL for BLOB/BYTEA in checkpoint store

### Phase B: SQL Safety (C6)

- Add `_validate_identifier()` helper in dialect.py
- Apply to all table/column/path parameters in upsert, insert_ignore, json_extract

### Phase C: Transaction Support (C1, partial)

- Add `transaction()` async context manager to ConnectionManager
- Refactor event store append, idempotency claim, task queue dequeue to use transactions

### Phase D: Race Condition Fixes (C2, C3, C4, M1)

- Event store: use subquery for atomic sequence assignment
- Idempotency: remove pre-check GET, rely on INSERT IGNORE + rowcount
- Task queue dequeue: wrap in transaction
- Checkpoint save: use dialect upsert instead of check-then-act

### Phase E: Test Fixes and Coverage (C7, C8, H3, H4, H6)

- Fix integration test bugs (connect API, StartNode)
- Add queue_factory tests
- Add **init**.py missing exports
- Add purge_completed test
- Add concurrency tests for critical paths

### Phase F: Bounded Collections (H1, H7)

- InMemoryExecutionStore: add maxlen with LRU eviction
- Worker.\_tasks: convert to set

---

## Decision Required

The CRITICAL findings are real and affect correctness under concurrent access. However:

- **Level 0 (SQLite single-writer)** is safe from most race conditions
- **Level 1 (PG/MySQL with single process)** is affected by C2, C3, C4 since ConnectionManager can use concurrent async tasks on the same connection pool
- **Level 2 (multi-worker)** is fully affected

**Recommendation**: Fix C5, C6, H2 (DDL/safety — required for multi-DB), H3, H4 (test/export fixes — required for release). Document C1-C4 race conditions as known limitations for v1.0.0 with the caveat that Level 0 single-process usage is unaffected. Fix C1-C4 in v1.0.1.
