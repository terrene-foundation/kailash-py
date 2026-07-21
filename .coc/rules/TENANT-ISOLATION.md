---
id: "TENANT-ISOLATION"
paths: ["**/tenant*", "**/multi_tenant*", "**/dataflow/**", "**/cache/**", "**/audit/**"]
---

# Tenant Isolation Rules

In a multi-tenant SaaS, tenant isolation is the difference between an API that scales to a thousand customers and a P0 incident that destroys the company's reputation. Cross-tenant data leaks happen because some piece of state — a cache key, a query filter, a metric label, an audit row — was constructed without a tenant dimension. The leak doesn't surface until two tenants happen to share a primary key, at which point one of them sees the other's data.

This rule mandates a tenant dimension on every piece of state that can hold per-tenant data. The audit is mechanical: grep for cache key construction, query filter construction, metric label construction, and verify that each one accepts a `tenant_id` and uses it.

## MUST Rules

### 1. Cache Keys Include Tenant_id for Multi-Tenant Models

Any cache key built for a model with `multi_tenant=True` MUST include `tenant_id` as a dimension. The canonical key shape is:

```
{prefix}:v1:{tenant_id}:{model}:{operation}:{params_hash}
```

Single-tenant models keep the simpler form:

```
{prefix}:v1:{model}:{operation}:{params_hash}
```

```python
# DO — tenant in the key
key = f"dataflow:v1:{tenant_id}:{model}:{op}:{params_hash}"

# DO — tenant STAYS in the key even when the secondary key is a per-tenant-unique UUID
# (Anti-optimization: future secondary-key change could collide; the tenant dimension
# is defense-in-depth against that future refactor.)
key = f"dataflow:v1:{tenant_id}:Document:{uuid}"  # keep tenant_id even though uuid is unique

# DO NOT — tenant absent
key = f"dataflow:v1:{model}:{op}:{params_hash}"  # leaks across tenants

# DO NOT — drop tenant "because the UUID is already unique"
key = f"dataflow:v1:Document:{uuid}"  # saves 36 bytes, adds a CVE-class hazard
```

**BLOCKED rationalizations:**

- "The UUID is already unique across tenants, so tenant_id is redundant"
- "We can save 36 bytes per key by dropping tenant_id from UUID-keyed entries"
- "UUIDv7 / UUIDv4 collision probability is negligible"
- "The migration from UUID to natural key is unlikely"

**Why:** Two tenants with overlapping primary keys (UUID collisions are rare but document IDs, user IDs, slugs, and natural keys are not) will read each other's cached records when the cache key doesn't distinguish them. The UUID-is-unique optimization destroys the defense against a future schema change that replaces the UUID with a tenant-local identifier (slug, sequence, email). The optimization saves bytes today and costs a data leak the day the secondary key changes — keeping `tenant_id` in the key is a 36-byte hedge against a CVE-class refactor.

### 2. Multi-Tenant Strict Mode — Missing Tenant_id Is a Typed Error

Reading a multi-tenant model without supplying a `tenant_id` MUST raise a typed error (e.g. `TenantRequiredError`). Silent fallback to a default tenant or an unscoped key is BLOCKED.

```python
# DO — strict typed error
def generate_cache_key(model, op, params, tenant_id=None):
    if model.multi_tenant and tenant_id is None:
        raise TenantRequiredError(
            f"Model '{model.name}' is multi_tenant=True; tenant_id is required"
        )

# DO NOT — silent fallback to default tenant
def generate_cache_key(model, op, params, tenant_id=None):
    tenant_id = tenant_id or "default"  # leaks every multi-tenant read into shared "default" tenant
```

**Why:** Defaulting to "default" or "global" or "" silently merges every multi-tenant read into a single shared cache slot. The leak is invisible until a tenant's data shows up in another tenant's query.

### 3. Invalidation Is Tenant-Scoped

`invalidate_model("User")` and equivalent invalidation entry points MUST accept an optional `tenant_id` so a tenant-scoped invalidation only clears its own slots.

```python
# DO — scoped invalidation
async def invalidate_model(self, model: str, tenant_id: Optional[str] = None) -> int:
    pattern = f"dataflow:v1:{tenant_id}:{model}:*" if tenant_id else f"dataflow:v1:*:{model}:*"
    return await self.scan_and_delete(pattern)

# DO NOT — invalidation that nukes every tenant's slots
async def invalidate_model(self, model: str) -> int:
    pattern = f"dataflow:v1:{model}:*"  # only matches the legacy single-tenant key shape
    return await self.scan_and_delete(pattern)
```

**Why:** A user invalidating "their" cache should not clear every other tenant's cache. Tenant-scoped invalidation also enables targeted cache busting on tenant-specific events (a single tenant's password rotation, a single tenant's quota change).

### 3a. Keyspace Version Bumps Require Invalidation-Path Sweep

When the default keyspace version emitted by `CacheKeyGenerator` (or equivalent key-constructor) is bumped — e.g. `v1 → v2` for a classification-hash format change — EVERY invalidation entry point in the codebase MUST be audited and updated in the same PR. The safest disposition is to match the version segment as a wildcard (`dataflow:v*:*`) so legacy keys AND current keys are swept in one call.

```python
# DO — version-wildcard sweep, future-proof
if tenant_id is not None:
    express_pattern = f"dataflow:v*:{tenant_id}:{model_name}:*"
else:
    express_pattern = f"dataflow:v*:{model_name}:*"
query_pattern = f"dataflow:{model_name}:v*:*"

# DO NOT — version-pinned sweep after the generator bumps
express_pattern = f"dataflow:v1:{model_name}:*"   # misses every v2 entry
query_pattern = f"dataflow:{model_name}:v1:*"
```

**BLOCKED rationalizations:**

- "The invalidation path runs rarely, v1 entries will expire on their own TTL"
- "We'll update the invalidation in a follow-up PR"
- "The generator default can be reverted if it causes issues"
- "Only one adapter pins the old version; the others are fine"

**Why:** A cache keyspace bump is a producer-side change that silently breaks every consumer-side invalidator pinned to the old version. Write-then-invalidate leaves stale entries on the shared backend (Redis, Memcached, etc.) indefinitely; TTL-based eventual-expiry is not a substitute because TTLs are often multi-hour and users observe the stale reads in the meantime. Version-wildcard sweeps are the structural defense — the only invalidation code that survives the next keyspace bump unchanged.

Origin: 2026-04-19 — keyspace bump `v1→v2`; Redis invalidator missed in the producer-side update, caught by post-release reviewer, fast-patched.

### 4. Metric Labels Carry Tenant_id (Bounded)

Metrics that count per-tenant operations (`requests_total`, `cache_hits_total`, `errors_total`) MAY include `tenant_id` as a label, BUT label cardinality MUST be bounded. Unbounded `tenant_id` labels in Prometheus produce a metric series per tenant which exhausts memory at scale.

Two acceptable strategies:

**Bounded label** — only emit `tenant_id` for the top-N tenants by traffic, bucket the rest as `"_other"`:

```python
TOP_TENANT_CARDINALITY = 100

def record_request(self, tenant_id: str):
    label = tenant_id if self.is_top_tenant(tenant_id) else "_other"
    self.requests_total.labels(tenant_id=label).inc()
```

**Aggregation tier** — emit at request log level (with full tenant_id) and let the log pipeline aggregate, not the metric:

```python
logger.info("request.handled", extra={"tenant_id": tenant_id, "duration_ms": d})
self.requests_total.inc()  # no per-tenant label
```

**Why:** Unbounded label cardinality is the #1 cause of Prometheus OOMs at scale. A 10K-tenant SaaS with 13 metric families and per-tenant labels produces 130K time series — well past the practical limit.

### 5. Audit Rows Persist Tenant_id

Every audit row written by the trust plane / governance layer MUST persist `tenant_id` as a column, indexed. Without it, "show me everything tenant X did this month" is a full table scan.

**Why:** Audit queries are the primary forensic tool when responding to a tenant-reported incident. Forcing a full table scan converts a 30-second query into a 30-minute query and means the response team is hours behind the customer.

### 6. Every Write Path Reads Tenant From One Canonical Source

When a model is `multi_tenant=True`, EVERY write/scope path — single-record AND bulk (`bulk_create` / `bulk_update` / `bulk_upsert`, `upsert`) — MUST read the tenant from the SAME canonical source (the live tenant contextvar via `get_current_tenant_id()`), never a parallel legacy dict/field. A subsystem that builds its own SQL MUST still resolve tenant from the canonical source and fail closed (typed error per Rule 2) when none is bound.

```python
# DO — every path, including bulk, reads the live canonical source
tenant_id = get_current_tenant_id()          # same source for single-record AND bulk
if tenant_id is None and model.multi_tenant:
    raise TenantRequiredError(model.name)

# DO NOT — bulk subsystem reads a parallel legacy dict
tenant_id = self._tenant_context.get("tenant_id")   # stale after switch();
# bulk writes land tenant_id=NULL — rows invisible to EVERY tenant
```

**BLOCKED rationalizations:**

- "Single-record writes are correct, bulk shares the engine"
- "The legacy dict is kept in sync by switch()"
- "The bulk path builds its own SQL, the contextvar doesn't apply there"
- "NULL tenant rows are harmless — no tenant can see them"

**Why:** A dual-tenant-source split is the failure mode: single-record correctness does NOT imply bulk correctness, and a stale parallel dict silently writes `tenant_id=NULL` rows invisible to every tenant (evidence: issue #1252 — the bulk subsystem read a stale `_tenant_context` dict instead of the `switch()` contextvar). Extends Rules 1–5, which audit cache-key / filter / label / audit sites but not write-path tenant-source parity.

**Trust Posture Wiring (Rule 6):** Severity `halt-and-report` at the /implement gate (reviewer mechanical sweep: every write/scope path of a `multi_tenant=True` model resolves tenant via the canonical accessor — `rg 'get_current_tenant_id|_tenant_context'` and flag any parallel source) · Grace 7 days from landing · Cumulative per `trust-posture.md` MUST-4 (3× same-rule in 30d → drop 1 posture) · Regression-within-grace → emergency downgrade (1 step) per MUST-4 · Receipt soft-gate `[ack: tenant-one-canonical-source]` IFF `posture.json::pending_verification` includes this rule_id · Detection: the Audit Protocol grep below + gate-level sweep · **Violation scope:** Rule 6 (write-path tenant-source parity) · Origin: issue #1252 (2026-06, bulk tenant-source mismatch).

### 7. Upsert `ON CONFLICT DO UPDATE` Is Tenant-Guarded And Excludes `tenant_id` From SET

When a `multi_tenant=True` model uses a global single-column `id` PK, EVERY upsert builder that emits `INSERT ... ON CONFLICT (id) DO UPDATE SET ...` (PostgreSQL/SQLite) or `INSERT ... ON DUPLICATE KEY UPDATE ...` (MySQL) MUST (a) EXCLUDE `tenant_id` from the SET clause AND (b) GATE the update by the row's own tenant — PG/SQLite via `WHERE {table}.tenant_id = EXCLUDED.tenant_id` appended to the `DO UPDATE`; MySQL (ODKU has no WHERE) via a per-column `IF(tenant_id = VALUES(tenant_id), <new>, <col>)` guard on EVERY updated column INCLUDING version/timestamp bumps. A guard-suppressed cross-tenant collision MUST route to the actionable tenant-scoped collision diagnostic (naming ONLY the caller's own tenant) — NEVER a silent success or silent skip. EVERY upsert builder in the codebase MUST be audited, not just the primary one.

```python
# DO — tenant-guarded DO UPDATE, tenant_id excluded from SET
update_cols = [c for c in cols if c != "id" and not (tenant_guarded and c == "tenant_id")]
set_parts = [f"{c} = EXCLUDED.{c}" for c in update_cols]
where = f" WHERE {table}.tenant_id = EXCLUDED.tenant_id" if tenant_guarded else ""
sql = f"INSERT ... ON CONFLICT (id) DO UPDATE SET {', '.join(set_parts)}{where}"
# MySQL ODKU: f"{c} = IF(tenant_id = VALUES(tenant_id), VALUES({c}), {c})" per column

# DO NOT — un-guarded DO UPDATE (cross-tenant id collision overwrites + steals the other tenant's row)
set_parts = [f"{c} = EXCLUDED.{c}" for c in cols if c != "id"]  # tenant_id IN the SET → ownership flip
sql = f"INSERT ... ON CONFLICT (id) DO UPDATE SET {', '.join(set_parts)}"  # no WHERE → tenant B overwrites tenant A
```

**BLOCKED rationalizations:**

- "The write already reads the right tenant (Rule 6), so the upsert is safe"
- "bulk_upsert tenant isolation is correct" (the exact pre-#1650 assumption that was false on both SQLite and PostgreSQL)
- "`conflict_on` defaults to `id`; a cross-tenant id collision won't happen"
- "the ON CONFLICT path returned success, so no collision occurred"
- "I fixed the primary bulk_upsert builder; the sibling nodes are rare / opt-in"
- "MySQL ODKU has no WHERE, so it can't be tenant-guarded" (use the per-column `IF()` guard)

**Why:** A global `id` PK means a cross-tenant `id` collision IS a genuine `ON CONFLICT`; an un-guarded `DO UPDATE` resolves it by OVERWRITING the other tenant's row — and, if `tenant_id` is in the SET, flipping its ownership — while returning success, so the collision diagnostic never fires. This is DISTINCT from Rule 6 (which ensures the write reads the RIGHT tenant): a correctly-tenant-scoped write STILL overwrites another tenant's row via the un-guarded upsert-conflict path. Auditing ALL builders (not just the primary) is load-bearing — the #1650 fix found the same breach in a sibling registered node the primary fix missed.

**Trust Posture Wiring (Rule 7):**

- **Severity:** `halt-and-report` at gate-review (security-reviewer + reviewer mechanical sweep at `/implement` + `/redteam`: enumerate every `ON CONFLICT`/`ON DUPLICATE KEY` `DO UPDATE` builder in the DB package, confirm each `multi_tenant` path carries the tenant `WHERE`/`IF()` guard AND excludes `tenant_id` from SET); `advisory` at the hook layer (the tenant-guard property is judgment-bearing over generated SQL, not a structural tool-call signal, per `hook-output-discipline.md` MUST-2).
- **Grace period:** 7 days from rule landing (2026-07-10 → 2026-07-17).
- **Cumulative posture impact:** same-class violations (a `multi_tenant` upsert builder shipped without the tenant `WHERE`/`IF()` guard, or with `tenant_id` in the SET clause) contribute to `trust-posture.md` MUST Rule 4 cumulative-window math (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** a same-class violation within the 7-day grace window routes through the GENERIC `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture) — NO dedicated per-clause trigger key (an SQL-shape property is review-layer-only and judgment-bearing; minting a key would drag `trust-posture.md`, a self-referential-codify allowlist file, into a self-ref edit, and the universal `regression_within_grace` trigger already covers it).
- **Receipt requirement:** SessionStart soft-gate `[ack: tenant-isolation]` IFF `posture.json::pending_verification` includes this rule_id.
- **Detection mechanism:** Phase 1 (manual, gate-review) — for any `multi_tenant` upsert change, enumerate ALL `ON CONFLICT`/`ON DUPLICATE KEY` `DO UPDATE` builders (`grep -rln 'DO UPDATE SET\|ON DUPLICATE KEY UPDATE' <db-pkg>/src`), then grep each for the tenant guard (`tenant_id = EXCLUDED.tenant_id` / `IF(tenant_id =`) — a builder emitting a multi_tenant DO UPDATE with no guard is a finding; run by security-reviewer + reviewer at `/implement` + `/redteam` (the Audit Protocol grep below). Phase 2 (deferred per `trust-posture.md` § Two-Phase Rollout, after ≥3 real sessions exercise Phase 1) — no hook detector; audit fixtures land with the Phase-2 detector at `.claude/audit-fixtures/tenant-upsert-guard/` per `cc-artifacts.md` Rule 9.
- **Violation scope:** Rule 7 (upsert `ON CONFLICT DO UPDATE` tenant-guard + `tenant_id`-excluded-from-SET) ONLY; Rules 1–6 stay grandfathered until each is itself `/codify`-touched.
- **Origin:** See Rule 7 Origin below.

Origin: #1650 / kailash-dataflow 2.14.5 (2026-07-10) — a holistic `/redteam` CONFIRMED (real SQLite + PostgreSQL) that `bulk_upsert` / single `upsert` / `BulkCreatePoolNode` on a `multi_tenant` model with the default `conflict_on=["id"]` overwrote and reassigned another tenant's row via an un-guarded `ON CONFLICT DO UPDATE`; fixed across all five upsert builders. The completeness lesson (audit ALL builders) came from the closure-parity round finding the sibling `BulkCreatePoolNode` after the primary fix.

## MUST NOT

- Default missing tenant_id to a placeholder ("default", "global", "")

**Why:** Silent defaulting masks the bug at write time and surfaces as data leaks days later when two tenants happen to share a primary key.

- Use `tenant_id` as an unbounded Prometheus label

**Why:** Cardinality explosion crashes the metrics pipeline at the worst possible time — the moment the tenant count grows fastest.

- Build tenant-scoped infrastructure (cache, queue, store) without a tenant-aware invalidation entry point

**Why:** Without tenant-scoped invalidation, the only way to clear a single tenant's cache is to clear everyone's, which converts every tenant-event into a full cache rebuild.

## Audit Protocol

This rule is audited mechanically as part of `/redteam` and `/codify`:

```bash
# Find every cache key construction; verify each accepts tenant_id
rg 'def (generate|build)_cache_key' .

# Find every invalidate_model entry point; verify each accepts tenant_id
rg 'def invalidate_model' .

# Find every metric .labels() call; verify cardinality is bounded
rg '\.labels\(' .

# Find every audit-row write; verify it persists tenant_id
rg 'audit_store\.append|record_query_success|record_query_failure' .

# Find every write/scope path; verify each resolves tenant via the canonical source (Rule 6)
rg 'def (bulk_create|bulk_update|bulk_upsert|upsert|create|update)' .
rg '_tenant_context\[|_tenant_context\.get' .   # any hit on a write path = HIGH (parallel source)

# Find every upsert DO UPDATE builder; verify each multi_tenant path is tenant-guarded (Rule 7)
rg -l 'DO UPDATE SET|ON DUPLICATE KEY UPDATE' .            # enumerate ALL upsert builders
rg 'tenant_id = EXCLUDED\.tenant_id|IF\(tenant_id =' .     # the guard — a builder emitting a
                                                          # multi_tenant DO UPDATE with NO hit here = HIGH
```

Any match that fails the contract above is a HIGH finding.

**Length rationale (per `rules/rule-authoring.md` MUST NOT § "Rules longer than 200 lines").** Rule body is ~269 lines, over the 200-line guidance. Named rationale: **tenant-isolation-contract scope** — the rule codifies the complete cross-tenant-leak surface across seven numbered rules (1 cache-key dimension, 2 strict-mode typed error, 3/3a invalidation scope + keyspace-bump sweep, 4 bounded metric labels, 5 audit-row persistence, 6 canonical write-path tenant source, 7 upsert `ON CONFLICT` tenant-guard) plus the mechanical Audit Protocol grep battery each rule feeds. Each rule guards a DISTINCT piece of per-tenant state (cache / query filter / metric label / audit row / write path / upsert-conflict path) that a multi-tenant audit MUST hold simultaneously; splitting into sibling rules would fragment the one contract every tenant-isolation edit consults and force cross-rule lookups per audit. The rule is `priority: 10` + `scope: path-scoped`, so it pays NO baseline-emission cost (loaded only in sessions matching its `paths:` globs) and `rule-authoring.md` Rule 10's proximity-band gate does NOT fire. Per `rule-authoring.md` MUST NOT § "Rules longer than 200 lines": overage is permitted with named rationale. Sibling precedent: `artifact-flow.md` + `recommendation-quality.md` + `spec-accuracy.md` length rationales.
