# Aether Migration Recommendation

## Measured Data from Aether

| Layer                        | LOC    | Files | Notes                                                    |
| ---------------------------- | ------ | ----- | -------------------------------------------------------- |
| Connection (adapters)        | 5,753  | 24    | All 24 adapters active and tested                        |
| Connection (pipeline/sync)   | 875    | 6     | Circuit breaker, sync lock, encryption, validation       |
| Fabric (AI agents)           | 4,000+ | 7     | Quality, ontology, structure, insight, lineage, security |
| Fabric (knowledge/reservoir) | 3,200+ | 18    | Knowledge graph, document processing                     |
| Exposure (in-memory stores)  | 5,738  | 28    | Governance, knowledge, quality stores                    |
| Exposure (API handlers)      | 10,457 | 16    | All business logic handlers                              |
| Frontend (React Query hooks) | 3,835  | 31    | 30s stale time, no backend cache                         |

**Total Aether data layer**: ~34,000 LOC

### Current Caching (the problem this solves)

- **Backend**: Zero application-level caching. Every request hits fresh.
- **Frontend**: TanStack Query with 30s stale time, no refetch on focus, 1 retry.
- **Result**: Users see loading spinners on every cache miss. 30s of potential staleness. No pre-warming.

### Actual Adapters in Production (all 24)

AzureBlob, Bloomberg, Discord, Dropbox, GCS, GoogleDrive, GraphQL, IMAP, Kafka, LocalFile, MongoDB, MSGraphEmail, MySQL, OneDrive, PostgreSQL, REST, S3, Salesforce, SharePoint, Slack, Snowflake, Teams, Zoom

---

## Migration Recommendation: Build DataFlow Fabric, Then Migrate Aether

### Phase 1: Build the Fabric in DataFlow

Build the fabric capabilities directly in DataFlow (as analyzed in `03-dataflow-is-the-fabric.md`). This produces:

- New adapter types: `RestAdapter`, `FileAdapter`, `CloudAdapter`, `ExcelAdapter`
- `@db.source()` for external source registration
- `@db.product()` for materialized views
- Pipeline-driven cache with cheap change detection
- Pre-warming on startup
- Nexus endpoint generation

### Phase 2: Aether Becomes First Consumer

Migrate Aether's connection layer to use DataFlow's fabric capabilities.

**What gets replaced** (12,964 LOC):

| Aether Component       | Replaced By                                                                                            | LOC Removed |
| ---------------------- | ------------------------------------------------------------------------------------------------------ | ----------- |
| 24 connection adapters | DataFlow adapters (REST, File, Cloud cover most; custom adapters for specialized like Bloomberg, Zoom) | 5,753       |
| Pipeline + sync engine | DataFlow fabric pipeline                                                                               | 875         |
| Circuit breaker        | DataFlow circuit breaker                                                                               | included    |
| Sync lock              | DataFlow distributed lock                                                                              | included    |
| In-memory stores       | DataFlow Express + cache (most stores become products)                                                 | ~3,000      |
| Manual API caching     | Pipeline-driven cache (automatic)                                                                      | ~500        |

**What stays Aether-specific** (16,299 LOC):

| Aether Component                    | Why It Stays                                                                                 |
| ----------------------------------- | -------------------------------------------------------------------------------------------- |
| AI agents (quality, ontology, etc.) | Application-specific enrichment — these become transform hooks in product definitions        |
| Knowledge graph                     | Domain model, not data access                                                                |
| Governance (EATP trust chains)      | Application governance, not fabric governance                                                |
| API handlers (business logic)       | Application logic — but simplified because they read from products instead of direct queries |
| Frontend hooks                      | No changes needed — same REST endpoints, now served from cache                               |

### Phase 3: Adapter Coverage Strategy

Aether has 24 adapters. DataFlow fabric will ship with 4 base adapter types that cover most:

| DataFlow Adapter | Covers Aether Adapters                                         |
| ---------------- | -------------------------------------------------------------- |
| `RestAdapter`    | REST, Salesforce, GraphQL, Bloomberg, Zoom (all are HTTP APIs) |
| `FileAdapter`    | LocalFile                                                      |
| `CloudAdapter`   | S3, GCS, AzureBlob, OneDrive, GoogleDrive, Dropbox, SharePoint |
| `ExcelAdapter`   | Excel/CSV files (on any source)                                |

**Specialized adapters** (extend `RestAdapter` or `BaseAdapter`):
| Adapter | Extends | Special Handling |
|---------|---------|-----------------|
| Kafka | `BaseAdapter` (streaming) | Continuous consumption, not polling |
| MongoDB/MySQL/Snowflake | `DatabaseAdapter` | Already in DataFlow |
| Slack/Teams/Discord | `RestAdapter` | WebSocket for real-time, REST for history |
| IMAP/MSGraphEmail | `RestAdapter` | IMAP protocol, OAuth2 |

**Coverage**: 20 of 24 covered by base adapters. 4 need specialized subclasses (Kafka, IMAP, Slack WebSocket, Teams WebSocket).

### Migration Effort (COC Autonomous Execution)

Per `rules/autonomous-execution.md`, using the 10x multiplier:

| Task                     | Autonomous Sessions | Notes                                                |
| ------------------------ | ------------------- | ---------------------------------------------------- |
| Build fabric in DataFlow | 2-3 sessions        | ~5-7K new LOC + tests                                |
| Aether adapter migration | 1-2 sessions        | Replace 24 adapters with fabric source registrations |
| Product definitions      | 1 session           | Convert in-memory stores to `@db.product`            |
| Pipeline integration     | 1 session           | Wire Aether AI agents as transform hooks             |
| End-to-end validation    | 1 session           | Verify all 24 sources work through fabric            |
| **Total**                | **6-8 sessions**    |                                                      |

---

## The Demo Story

**Before (Aether today)**:

```
24 custom adapters × ~240 LOC each = 5,753 LOC of adapter code
Zero backend caching — every request hits source fresh
30s stale time on FE — users see loading spinners
Manual sync scheduling — cron-based polling
No pre-warming — cold starts show empty dashboards
```

**After (Aether on DataFlow fabric)**:

```python
db = DataFlow("postgresql://...")

# 24 adapters become 24 source registrations (~10 lines each)
db.source("salesforce", RestSource(url="https://api.salesforce.com/v1", ...))
db.source("sharepoint", CloudSource(bucket="company-sharepoint", ...))
db.source("hr_file", FileSource(path="/shared/hr/employees.xlsx", watch=True))
# ... 21 more

# 28 in-memory stores become ~15 data products
@db.product("dashboard_summary")
async def dashboard(ctx):
    users = await ctx.express.list("User", filter={"active": True})
    crm = await ctx.source("salesforce").fetch("/contacts")
    return {"users": users, "contacts": crm}

# Start: pre-warms ALL products, starts ALL source watchers
await db.start()
# Dashboard loads instantly — cache is warm before first request
```

**Measured impact**:

- 5,753 LOC of adapters → ~240 LOC of source registrations (24× reduction)
- 5,738 LOC of in-memory stores → ~1,500 LOC of product definitions (4× reduction)
- 30s stale time → pipeline-driven freshness (0 perceived staleness)
- Cold start spinners → pre-warmed cache (instant first load)
