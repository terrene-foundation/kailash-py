# Aether as Reference Implementation — Decision

## The Answer: Aether Is the First Consumer, Not the Reference

### Measured Data from Aether

| Metric                  | Count                       |
| ----------------------- | --------------------------- |
| REST routes             | 264 (5,554 LOC in proxy.py) |
| Backend stores          | 52 in-memory singletons     |
| Frontend hooks          | 31 files                    |
| Source adapters         | 26 (all real, no stubs)     |
| Auto-generatable routes | ~220 (83%)                  |
| Custom handler routes   | ~44 (17%)                   |

### Why Aether Is the First Consumer

Aether has the pain the fabric solves:

- 26 adapters = 26 custom source integrations that `db.source()` replaces
- 52 in-memory stores = 52 data containers that `@db.product()` replaces
- 264 routes = 220 that fabric auto-generates + 44 custom
- Zero backend caching = exactly the problem pipeline-driven cache fixes
- 31 FE hooks with 30s stale time = exactly the pattern `staleTime: Infinity` replaces

### Why Aether Is NOT the Reference

A reference implementation should be:

1. **Minimal** — demonstrate patterns, not a full application
2. **Self-contained** — run without 26 external service credentials
3. **Focused** — show fabric value, not Aether domain logic (governance, ontology, knowledge graph)
4. **Clean-room** — no legacy patterns (Nexus envelope unwrapping, in-memory store fallbacks)

Aether has 52 stores, 264 routes, 26 adapters. It demonstrates complexity, not clarity.

### The Two-Track Plan

**Track 1: Fabric Reference App** (clean-room, ships with DataFlow)

A minimal app that demonstrates every fabric concept with 3 sources:

```python
db = DataFlow("sqlite:///app.db")

@db.model
class Task:
    id: str
    title: str
    status: str
    assigned_to: str

# Source 1: REST API (JSONPlaceholder — free, no auth needed)
db.source("todos", RestSource(
    url="https://jsonplaceholder.typicode.com",
    endpoints={"items": "/todos"},
    poll_interval=60,
))

# Source 2: Local file
db.source("config", FileSource(path="./config.yaml", watch=True))

# Product: combines DB + API + file
@db.product("dashboard",
    depends_on=["Task", "todos", "config"],
    staleness=StalenessPolicy(max_age=timedelta(hours=1)),
)
async def dashboard(ctx):
    tasks = await ctx.express.list("Task")
    todos = await ctx.source("todos").fetch("items")
    config = await ctx.source("config").read()
    return {
        "my_tasks": len(tasks),
        "api_todos": len(todos),
        "theme": config.get("theme", "light"),
    }

await db.start(dev_mode=True)
# GET /fabric/dashboard → instant cached data
```

Runs with: `pip install kailash-dataflow[fabric]` + SQLite + no external credentials.

**Track 2: Aether Migration** (validates fabric at scale)

Migrate Aether's connection layer to fabric after the fabric ships:

| Phase                  | What Changes                                                  | LOC Impact                                              |
| ---------------------- | ------------------------------------------------------------- | ------------------------------------------------------- |
| 1. Source registration | Replace 26 custom adapters with `db.source()` calls           | -5,753 LOC adapter code → ~260 LOC source registrations |
| 2. Product definitions | Replace 52 in-memory stores with `@db.product()`              | -3,000+ LOC store code → ~1,500 LOC product functions   |
| 3. Route replacement   | Replace 220 CRUD routes with fabric auto-generated endpoints  | -4,000 LOC proxy.py → ~200 LOC product registrations    |
| 4. Keep custom routes  | 44 aggregation/dashboard routes stay as custom Nexus handlers | No change                                               |
| 5. Frontend migration  | Change path prefix from `/` to `/fabric/` in 31 hooks         | ~31 one-line changes                                    |

**Net impact**: ~12,750 LOC removed, ~2,000 LOC added. 6:1 reduction.

### Frontend Migration Is Minimal

Aether's hooks are already abstracted — they're thin wrappers around `api.get()`:

```typescript
// BEFORE (current)
export function useConnectors(params) {
  return useQuery({
    queryKey: ["connectors", params],
    queryFn: () => api.get("/connectors", searchParams),
  });
}

// AFTER (fabric)
export function useConnectors(params) {
  return useQuery({
    queryKey: ["connectors", params],
    queryFn: () => api.get("/fabric/connectors", searchParams),
    staleTime: 60_000, // Fabric manages freshness — FE trusts it
  });
}
```

Only the path prefix and staleTime change. Return types stay identical if fabric generates compatible response schemas.

### What Aether Proves That the Reference Can't

| Capability                       | Reference App | Aether Migration                    |
| -------------------------------- | ------------- | ----------------------------------- |
| Fabric works at all              | YES           | YES                                 |
| Fabric works with 3 sources      | YES           | —                                   |
| Fabric works with 26 sources     | —             | YES                                 |
| Fabric handles real OAuth2 flows | —             | YES (Salesforce, Azure AD)          |
| Fabric handles cloud storage     | —             | YES (S3, GCS, SharePoint)           |
| Fabric handles streaming         | —             | YES (Kafka)                         |
| Fabric replaces custom API layer | —             | YES (264 routes → fabric endpoints) |
| FE migration effort              | —             | YES (31 hooks, minimal changes)     |
| LOC reduction measurable         | —             | YES (12,750 → 2,000)                |
| Pipeline-driven cache vs TTL     | —             | YES (30s stale → Infinity)          |

### Risk Assessment

| Risk                                       | Severity | Mitigation                                                       |
| ------------------------------------------ | -------- | ---------------------------------------------------------------- |
| Fabric designed around Aether's needs only | MEDIUM   | Reference app ensures patterns are generic                       |
| Aether migration blocks fabric release     | LOW      | Fabric releases independently. Aether migrates after.            |
| Aether regression during migration         | MEDIUM   | Incremental migration, one route at a time, both stacks coexist  |
| Aether's 52 stores assume in-memory        | LOW      | Fabric supports in-memory cache. Migration path: store → product |
