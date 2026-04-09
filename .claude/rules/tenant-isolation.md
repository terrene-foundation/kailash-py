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

# DO NOT — tenant absent
key = f"dataflow:v1:{model}:{op}:{params_hash}"  # leaks across tenants
```

**Why:** Two tenants with overlapping primary keys (UUID collisions are rare but document IDs, user IDs, slugs, and natural keys are not) will read each other's cached records when the cache key doesn't distinguish them.

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
rg 'def (generate|build)_cache_key' src/

# Find every invalidate_model entry point; verify each accepts tenant_id
rg 'def invalidate_model' src/

# Find every metric .labels() call; verify cardinality is bounded
rg '\.labels\(' src/

# Find every audit-row write; verify it persists tenant_id
rg 'audit_store\.append|record_query_success|record_query_failure' src/
```

Any match that fails the contract above is a HIGH finding.
