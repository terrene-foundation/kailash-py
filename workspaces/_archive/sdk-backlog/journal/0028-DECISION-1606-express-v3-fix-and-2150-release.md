# 0028 — DECISION: #1606 Express v3 keyspace fix + kailash-dataflow 2.15.0 release

**Date:** 2026-07-12 · **Type:** DECISION · **Phase:** 05-codify · **Posture:** L5_DELEGATED

## What shipped (F2 CLOSED)

Closed the **Express hot-path** half of the #1606 cross-DB cache bleed — the query half
landed in 2.14.6; the express half was held open pending this coordinated cross-SDK re-pin.

- **Express keyspace v2→v3**: inserted a credential-free `db<16hex>` database-instance segment
  after the version (`dataflow:v3:{db_instance}:{tenant}:{model}:{op}:{hash}`), byte-identical to
  the Rust SDK's #1713 contract (`dataflow-cache-keys-v3`).
- **Vendored** the canonical vector fixture byte-for-byte (git-blob sha match, NOT re-authored —
  `cross-sdk-inspection.md` Rule 4a) at `packages/kailash-dataflow/tests/fixtures/dataflow-cache-keys.json`.
  All 6 V1–V6 vectors reproduce exactly (incl. empty-params/cross-DB/credential-strip sentinels).
- New `express_db_instance_fingerprint()` (distinct algo+length from the query-side
  `hash_database_identity`); query keyspace stays v2 (decoupled).
- **Cross-DB bleed proven closed on real Redis** (RED→GREEN, two DBs, Tier 2).

## Redteam findings resolved (3 parallel agents: reviewer + security-reviewer + conformance-verifier)

- **M1** (my regression, caught same-session): `clear_cache(model)` pinned its glob to the
  generator's v2 `self.version` → silently cleared 0 express entries after the bump (and never
  matched tenant-scoped keys). Fixed → delegate to `invalidate_model` (version+db-instance-agnostic).
- **L1** security hardening: a `//`-less credential DSN (`postgres:user:pass@host/db`) left userinfo
  in urlparse `path` → credential bytes in the hash pre-image. Now fails closed (returns None).
  Affects ZERO canonical vectors. → mirrored to rs as **rs#1771** (grant `journal/0027`).
- **L3** stale invalidation docstrings updated (memory_cache + async_redis_adapter).

## Release

PR **#1700** (admin-merged, 20 CI checks green on head SHA) → tag **dataflow-v2.15.0** →
publish-pypi success + GitHub Release → clean-venv install verified (2.15.0 imports, V1 fingerprint
reproduces from the published wheel). Version bumped 2.14.7→2.15.0 (pyproject + **init**).
No sibling-package drift (all main==PyPI). #1606 auto-closed on merge.
