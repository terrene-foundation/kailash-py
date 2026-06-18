# #1339 — DistributedLock / Lease — Architecture & Plan

**Phase:** /analyze → /todos gate
**Date:** 2026-06-16
**Issue:** #1339 (HIGH, cross-SDK parity with rs #1355; true new feature on both SDKs)

## Brief corrections (evidence-first, before planning)

The brief's probe ("No lock/lease/mutex/fencing/semaphore symbol in kailash.infrastructure, kailash.resources, or kailash.middleware") is **directionally right but incomplete**:

- **What exists (none satisfy the ask):**
  - `src/kailash/trust/_locking.py` — `file_lock()` via `filelock.FileLock`. **Single-host only** (directory-level, process-local). Does NOT serialize across hosts. Not a distributed lock.
  - `src/kailash/nodes/data/optimistic_locking.py` — DB row-version optimistic concurrency, not a lease.
  - `src/kailash/edge/coordination/global_ordering.py` — ordering, not mutual exclusion.
- **The real gap is confirmed:** no first-class `DistributedLock`/`Lease` with acquire/release/extend + fencing token over a shared backend.
- **The design template already exists:** `src/kailash/infrastructure/idempotency_store.py::DBIdempotencyStore` is a near-exact analog — atomic `try_claim(key, fingerprint)`, `expires_at` TTL column, `release_claim(key)`, `cleanup(before)`, all dialect-portable via `ConnectionManager`. A distributed lock = `try_claim` + a fencing token + `extend`.

## Backend decision (the issue's first real choice) — RECOMMENDATION: dialect-portable SQL

The brief offers "Redis and/or Postgres backed." kailash-py's entire `infrastructure/` store layer is **dialect-portable SQL via `ConnectionManager`** (SQLite at Level 0, Postgres at Level 1+), auto-detected by `StoreFactory` from `KAILASH_DATABASE_URL`. There is **no Redis** in the infrastructure store layer (Redis appears only in `middleware/event_bus` + circuit breaker).

**Recommend: SQL backend (Postgres/SQLite via `ConnectionManager`), mirroring `DBIdempotencyStore`.** Rationale:

- **Framework-consistency** — reuses the established store pattern (dialect portability, Level 0/1+ tiering, schema-stamping, `cleanup` machinery, `StoreFactory` wiring). A Redis backend would introduce a dependency the infra layer otherwise avoids and a second code path to maintain.
- **Zero new infra for users** — works on the SQLite already present at Level 0; scales to Postgres at Level 1+ with no code change.
- **Fencing is natural in SQL** — a monotonic per-key sequence column gives a strictly-increasing fencing token for free.
- Satisfies the AC ("at least one backend with a documented contextmanager API").

A Redis backend can be added later as a second `StoreFactory` tier if a user needs sub-millisecond lock churn; it is **out of scope** for this shard (the SQL backend is the framework-native first backend).

## Design (mirrors DBIdempotencyStore)

New file `src/kailash/infrastructure/lock_store.py`:

- `Lease` (frozen dataclass): `key`, `owner` (uuid4 per acquire), `fencing_token` (int, monotonic per key), `expires_at` (ISO-8601 UTC).
- `DBDistributedLock`:
  - `async acquire(key, ttl_seconds, *, blocking=False, timeout=None) -> Lease | None` — atomic insert-or-fail (`INSERT … WHERE NOT EXISTS` / dialect `ON CONFLICT DO NOTHING`); on success bumps + returns the fencing token. Steals an **expired** row atomically (`WHERE expires_at < now`).
  - `async release(lease) -> bool` — `DELETE WHERE key=? AND owner=? AND fencing_token=?` (fencing prevents releasing a lock you no longer hold).
  - `async extend(lease, ttl_seconds) -> Lease | None` — `UPDATE expires_at WHERE key+owner+fencing` (None if the lease was lost).
  - `async with lock.lease(key, ttl_seconds) as lease:` — async contextmanager; auto-release on exit.
  - `async cleanup(before)` — reap expired rows (mirrors idempotency cleanup).
- Schema: `key TEXT PK, owner TEXT, fencing_token BIGINT, expires_at TEXT NOT NULL` + index on `expires_at` (dialect-portable via `self._conn.dialect.text_column(indexed=True)`).
- Wire into `StoreFactory.create_lock_store()` + export `DBDistributedLock` / `Lease` from `infrastructure/__init__.py::__all__`.

## Invariant count (shard-fit check)

5 invariants: (1) mutual exclusion under contention, (2) fencing-token monotonicity, (3) expiry-steal atomicity, (4) release-only-own-lease, (5) dialect portability SQLite↔Postgres. ≤500 LOC load-bearing, ~3 call-graph hops, live test feedback loop → **single shard** per `autonomous-execution.md` capacity budget.

## Tests (Tier 2, real infra — no mocking per `rules/testing.md`)

- acquire-succeeds / second-acquire-fails-under-contention
- expiry-steal (expired lock re-acquirable; fencing token strictly increases)
- release-only-own-lease (stale fencing token cannot release/extend)
- extend-extends-ttl / extend-fails-after-loss
- contextmanager auto-release on normal + exception exit
- run on BOTH SQLite (Level 0) and Postgres (Level 1+) — dialect parity

## Specialist

Delegate implementation to **infrastructure-specialist** (domain: connections, dialect-portable SQL, stores, idempotency) with this plan + `idempotency_store.py` as the pattern reference, per `rules/agents.md` § Specialist Delegation.

## REVISION (user gate 2026-06-16: BOTH backends, optimal long-term design)

User approved with two directives: (1) **Redis backend too**, (2) **recommend optimal, root-cause, long-term implementation**. Revised design supersedes the SQL-only scope above:

### Optimal abstraction — one protocol, two backends (no parallel ad-hoc classes)

- `LockBackend` (Protocol/ABC) — the root-cause-correct seam so backends are interchangeable and `StoreFactory` selects at runtime. Methods: `try_acquire(key, owner, ttl) -> int|None` (returns fencing token on success), `release(key, owner, token) -> bool`, `extend(key, owner, token, ttl) -> bool`, `reap_expired(before)`, `close()`.
- `Lease` (frozen value object) — `key, owner (uuid4), fencing_token (int, strictly monotonic per key), expires_at`.
- `DistributedLock` (facade) — wraps any `LockBackend`; owns the `async with lock.lease(key, ttl) as lease:` contextmanager + optional blocking-acquire-with-timeout (poll/backoff). Backend-agnostic.

### Fencing tokens are THE safety mechanism (root-cause correctness, not a feature)

A lease can be lost mid-critical-section (GC pause, clock skew, network partition, expiry-then-steal) on ANY backend. Mutual-exclusion-by-TTL alone is NOT safe — the classic Kleppmann critique of Redlock. The **strictly-monotonic per-key fencing token** is what makes the primitive correct: a protected resource rejects any write carrying a token ≤ the highest it has seen. So `acquire` MUST return a monotonic token, `release`/`extend` MUST verify owner+token, and the docs MUST show the fence-check pattern at the protected resource. This is the design's load-bearing invariant — it holds regardless of the Redlock timing debate.

### SQL backend (`DBLockBackend`) — dialect-portable via ConnectionManager

Mirrors `DBIdempotencyStore`. Table `kailash_locks(key TEXT PK, owner TEXT, fencing_token BIGINT, expires_at TEXT NOT NULL)` + index on expires_at. Atomic acquire = dialect `INSERT … ON CONFLICT(key) DO UPDATE … WHERE expires_at < now` (steal-if-expired in one statement) `RETURNING fencing_token`. Fencing = `max(existing, 0)+1` bumped atomically in the same statement (or a `kailash_lock_fence(key, token)` companion row if a dialect lacks atomic RETURNING-on-conflict — SQLite needs the companion-row path). Release/extend gated on `key+owner+fencing_token`. `reap_expired` mirrors idempotency `cleanup`.

### Redis backend (`RedisLockBackend`) — behind the existing `[redis]` extra, lazy import

`redis.asyncio` (already available; `redis` is the declared `[redis]` extra at pyproject.toml:85). Lazy-import guarded like `trust/_locking.py` guards `filelock` (issue #1154 slim-core pattern). Mechanism:

- acquire: `SET lock:{key} {owner} NX PX {ttl_ms}`; on success `fencing_token = INCR fence:{key}` (monotonic, survives lock churn; never reset).
- release: Lua `if redis.call('GET', KEYS[1])==ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end` (compare-owner-then-delete — atomic, never releases another holder's lock).
- extend: Lua compare-owner-then-`PEXPIRE`.
- TTL expiry is native (PX); no reaper needed. **Honesty note in docs:** this is a single-instance/replica Redis lock (NOT multi-master Redlock across N independent nodes — that timing model is contested); fencing tokens are what provide safety, per the rationale above.

### StoreFactory selection

`StoreFactory.create_lock_store()` → Redis if `REDIS_URL`/redis config present, else SQL (Level-0 SQLite / Level-1+ Postgres). Explicit `backend=` override supported. Export `DistributedLock`, `Lease`, `LockBackend`, `DBLockBackend`, `RedisLockBackend` from `infrastructure/__init__.py`.

### Test infra (confirmed present — real infra, no mocking per `rules/testing.md`)

`docker-compose.test.yml` provides Postgres (`POSTGRES_TEST_URL`, :5434) + Redis (`REDIS_TEST_URL=redis://localhost:6380`); `tests/utils/docker_test_base.py` gives `postgres_conn` + `redis_client` fixtures; mirror `tests/tier2_integration/infrastructure/test_idempotency_store.py`. The full invariant matrix runs against **SQLite + Postgres + Redis** (parametrized backend fixture) — mutual exclusion, fencing monotonicity (incl. across expiry-steal), release-only-own-lease, extend/extend-after-loss, contextmanager auto-release on normal+exception exit.

### Sharding (two milestones, one session, commit per milestone)

- **Milestone A:** `LockBackend` protocol + `Lease` + `DistributedLock` facade + `DBLockBackend` + `StoreFactory` wiring + exports + Tier-2 tests on SQLite+Postgres. → commit.
- **Milestone B:** `RedisLockBackend` (behind `[redis]` extra) + Redis Tier-2 tests + docs (contextmanager + fence-check usage) + CHANGELOG. → commit.

Each milestone has a live test loop (≤500 LOC load-bearing each). Delegated to **infrastructure-specialist**, single main-checkout agent, commit-per-milestone.

## Todos (for /todos gate)

1. **[shard 1]** `lock_store.py` — `Lease` + `DBDistributedLock` (acquire/release/extend/contextmanager/cleanup), dialect-portable, mirroring `DBIdempotencyStore`. (~300-400 LOC)
2. **[shard 1]** `StoreFactory.create_lock_store()` + `infrastructure/__init__.py` exports.
3. **[shard 1]** Tier-2 tests on SQLite + Postgres (the invariant matrix above).
4. Docs: contextmanager usage example in the infrastructure docs + CHANGELOG entry.

(All shard-1: one cohesive store primitive with a live test loop.)
