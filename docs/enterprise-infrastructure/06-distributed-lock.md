# Distributed Lock Reference

A **distributed lock** lets workers across multiple processes and hosts agree that exactly one of them holds a named resource for a bounded time (a **lease**). Kailash ships one lock API with two interchangeable backends behind a single seam:

| Backend       | Class              | Storage                        | Best for                           |
| ------------- | ------------------ | ------------------------------ | ---------------------------------- |
| SQL (default) | `DBLockBackend`    | SQLite (L0) / PostgreSQL (L1+) | No new infra; reuses your database |
| Redis         | `RedisLockBackend` | Redis (`[redis]` extra)        | Sub-millisecond lock churn         |

Both backends are selected for you by `StoreFactory.create_lock_store()`; your code talks only to the backend-agnostic `DistributedLock` facade.

## Fencing tokens are the safety mechanism (not the TTL)

A lease can be lost **mid-critical-section** on any backend — a garbage-collection pause, a clock skew, a network partition, or an expiry-then-steal by another worker. Mutual exclusion by TTL alone is therefore **not** safe (the classic Kleppmann critique of TTL-only locks).

The load-bearing safety value is the **fencing token**: a strictly-monotonic-per-key integer that `acquire` returns and that `release` / `extend` verify. It is **never reset** — not across release, expiry, or steal. A correctly-built protected resource records the highest fencing token it has observed and **rejects any write carrying a token less than or equal to** that high-water mark. So even if two workers briefly believe they hold the same lock, only the one with the higher token can mutate the resource — correctness comes from the fence, not from Redis or database timing.

### The fence-check pattern at the protected resource

```python
lease = await lock.acquire("invoice-42", ttl_seconds=30)
if lease is None:
    return  # contended — someone else holds it

# ... do work ...

# When writing to the protected resource, carry the fencing token. The
# resource MUST reject any write whose token is <= the highest it has seen:
await resource.write(data, fencing_token=lease.fencing_token)

await lock.release(lease)
```

A resource that honours fencing tokens stays correct even when the lock is briefly held by two workers — the stale holder's lower token is rejected.

## Quick start

```python
from kailash.infrastructure import StoreFactory

factory = StoreFactory()                      # auto-detects from KAILASH_DATABASE_URL
lock = await factory.create_lock_store()       # Redis if REDIS_URL set, else SQL

# Contextmanager — auto-releases on normal AND exception exit:
async with lock.lease("invoice-42", ttl_seconds=30) as held:
    await charge_invoice(data, fencing_token=held.fencing_token)
# Lock released here, even if charge_invoice() raised.

await lock.close()
```

The `lease()` contextmanager raises `LockAcquireError` if the lock is contended (it does not block). For blocking semantics, use `acquire(..., blocking=True, timeout=...)`.

## API

### `DistributedLock`

```python
lease = await lock.acquire(key, ttl_seconds=30, *, blocking=False, timeout=None)
#  -> Lease on success, None on contention (non-blocking) or timeout (blocking)

ok = await lock.release(lease)          #  -> True if released, False if lost
refreshed = await lock.extend(lease, ttl_seconds=30)  # -> Lease (same token) or None if lost
reaped = await lock.reap_expired()      #  -> int (SQL: rows reaped; Redis: 0, native expiry)

async with lock.lease(key, ttl_seconds=30) as held:   # auto-release on exit
    ...
```

- **`acquire`** mints a fresh `owner` (uuid4 hex) per call and returns a `Lease`. An **expired** lock is stolen automatically, and the fencing token strictly increases across the steal.
- **`blocking=True`** polls with exponential backoff until the lock frees or `timeout` (seconds) elapses; `timeout=None` blocks indefinitely.
- **`release` / `extend`** verify `owner` + `fencing_token`, so a stale lease (one lost to expiry-then-steal) can never release or extend the new holder's lock — they return `False` / `None`.
- **`extend`** keeps the **same** fencing token (extending a held lease is the same critical section), only pushing out `expires_at`.

### `Lease` (frozen value object)

```python
@dataclass(frozen=True)
class Lease:
    key: str             # the resource name
    owner: str           # uuid4 hex, unique per acquire
    fencing_token: int   # strictly monotonic per key, never reset
    expires_at: str      # ISO-8601 UTC
```

### Backend selection

```python
lock = await factory.create_lock_store()                # auto: Redis if REDIS_URL set, else SQL
lock = await factory.create_lock_store(backend="redis") # force Redis ([redis] extra required)
lock = await factory.create_lock_store(backend="sql")   # force SQL (SQLite L0 / PostgreSQL L1+)
```

## SQL backend (`DBLockBackend`)

Dialect-portable via `ConnectionManager`, mirroring `DBIdempotencyStore`. It uses a **single** table:

| Table           | Columns                                                                  | Purpose                      |
| --------------- | ------------------------------------------------------------------------ | ---------------------------- |
| `kailash_locks` | `key` (PK), `owner` (nullable), `fencing_token`, `expires_at` (nullable) | The lock rows + expiry index |

The lock row is **never deleted**: release and reap _tombstone_ the row (`owner` / `expires_at` set to `NULL`) while preserving `fencing_token`. Keeping one persistent row per key is what makes both the fence monotonicity AND the acquire atomicity hold:

- **Monotonic fence, never reset.** The fence lives in the lock row and is bumped on every steal; because the row survives release / native expiry / steal as a tombstone, the token is strictly increasing across all of them.
- **Atomic acquire (one winner, the rest get `None`).** Acquire runs in **one transaction**: it first ensures the row exists (`INSERT ... ON CONFLICT DO NOTHING`), then `SELECT ... FOR UPDATE` row-locks the key. Because the row always exists, the `FOR UPDATE` lock serializes every concurrent acquirer of that key — including two workers racing to steal the _same expired_ row — so exactly one bumps the fence and writes the new owner; the rest block, re-read the now-live row, and get `None`. This holds on **every** dialect regardless of transaction isolation level (PostgreSQL's asyncpg pool runs at READ COMMITTED; `FOR UPDATE`'s block-then-reread is correct under it). On SQLite `dialect.for_update()` is `""` because `BEGIN IMMEDIATE` already serializes writers.

## Redis backend (`RedisLockBackend`)

Behind the `[redis]` extra (`pip install kailash[redis]`); `redis.asyncio` is imported lazily so a slim-core install never pays for it. If the extra is missing, the backend raises a typed, actionable `ImportError` — never a silent fallback.

- **acquire** — `INCR fence:{key}` first mints the monotonic token, then `SET lock:{key} {owner}:{token} NX PX {ttl_ms}` claims the key only when free, storing the **composite** `{owner}:{token}` value. The `fence:{key}` counter has **no** expiry, so the token survives lock churn. (A contended `SET NX` after a successful `INCR` leaves a harmless gap in the fence sequence — tokens need only be strictly monotonic, not gap-free.)
- **release** — a Lua compare-`{owner}:{token}`-then-`DEL` script (atomic; never deletes another holder's lock, even one that re-acquired at a higher token).
- **extend** — a Lua compare-`{owner}:{token}`-then-`PEXPIRE` script.
- **expiry** — native (`PX`); no reaper is needed, so `reap_expired()` returns `0`.

Storing the full `{owner}:{token}` composite (rather than `owner` alone) keeps the SQL and Redis backends semantically identical under the one `LockBackend` Protocol: **both** gate release / extend on `owner` **and** `fencing_token` (EATP-D6 cross-backend parity).

**Honesty note.** This is a **single-instance** (or single-primary + replicas) Redis lock — **not** the multi-master Redlock algorithm across N independent Redis nodes, whose timing model is contested (Kleppmann). Safety does **not** rest on Redis timing: it rests on the **fencing token**. Under a primary failover that loses an un-replicated `SET`, two workers can briefly hold the same key — but only the one with the higher fencing token can mutate a fence-checking resource, so correctness is preserved.

## Next Steps

- [Idempotency Reference](04-idempotency.md) -- exactly-once execution
- [Task Queue Reference](03-task-queue.md) -- Redis vs SQL queue
- [Migration Guide](05-migration-guide.md) -- moving between levels
