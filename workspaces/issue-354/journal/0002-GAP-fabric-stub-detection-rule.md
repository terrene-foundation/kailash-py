# GAP — Existing rule did not catch fabric `redis_url` stub

**Date**: 2026-04-08
**Phase**: 01-analyze
**Context**: /analyze 354

## The rule

`.claude/rules/dataflow-pool.md` Rule 3 — "No Deceptive Configuration":

> Config flags MUST have backing implementation. A flag set to True with no consumer is a stub (`zero-tolerance.md` Rule 2).

## Why it didn't catch this

Rule 3 is framed around **boolean flags** ("a flag set to True"). The fabric bug is a **string URL** — `redis_url: Optional[str] = None` with no consumer. The rule's wording let the reviewer read past it because "url" isn't a "flag".

The intent of the rule clearly covers this case. The wording is narrower than the intent.

## Proposed fix

Extend `dataflow-pool.md` Rule 3 with an explicit broader list:

> Every config field named `*_url`, `*_backend`, `*_client`, `*_enabled`, `*_mode`, or accepting an `Optional[str]` / `bool` / `Literal["...", "..."]` type that signals a runtime selection, MUST have at least one import or instantiation of the backing client or code path in the class body that contains it. Verify with `grep` at `/redteam` time:
>
> ```bash
> # For every Optional[str] kwarg that looks like a connection URL,
> # grep the class body for its consumer.
> grep -nE "redis_url|cache_url|backend|from_url|aioredis|redis\.asyncio" <file>
> ```

## Why this matters beyond #354

The same pattern can hide in:

- `nexus_url`, `gateway_url`, `admin_url` kwargs accepted by frameworks but not plumbed
- `auth_backend`, `session_backend` fields stored but never instantiated
- `mode="sync"|"async"` discriminators that switch nothing
- Any `Optional[X]` field in an `__init__` that doesn't appear elsewhere in the class body

A grep guard in `/redteam` would catch all of them in one pass.

## Proposed test rule (extend `.claude/rules/testing.md`)

> For any `__init__` parameter whose docstring contains the words "production", "Redis", "cross-worker", "cross-replica", "distributed", or "shared", there MUST be at least one Tier 2 integration test that passes a non-None value for the parameter and asserts the backing side effect (e.g., verifies Redis traffic, verifies cross-process visibility, verifies the backend's `close()` method was called).

Rationale: the fabric stub survived because every fabric test passes `dev_mode=True, redis_url=None`. Not a single test exercises the Redis path. A test rule that requires exercise of any `*_url` parameter whose docstring claims production use would catch this class of bug at the test phase.

## Action

Both rule extensions go into the #354 fix PR — they are institutional-knowledge capture, not code changes. The test rule is enforced at `/redteam` time; the dataflow-pool rule is enforced by the rule reviewer at `/implement` time.
