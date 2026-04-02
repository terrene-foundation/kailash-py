# End-to-End Scenarios: Every Actor, Every Moment

## Scenario 1: SME With CRM + Database + Excel

**Company**: 50-person consulting firm
**Systems**: PostgreSQL (projects, timesheets), HubSpot CRM (clients, deals), Excel on SharePoint (financial projections)
**Need**: Partner dashboard showing utilization, pipeline, and revenue in one view

### Backend Developer Sets Up (30 minutes)

```python
db = DataFlow(os.environ["DATABASE_URL"])

@db.model
class Project:
    id: str
    client_id: str
    name: str
    status: str        # active, completed, on_hold
    hours_budget: float
    hours_used: float

@db.model
class Timesheet:
    id: str
    project_id: str
    consultant_id: str
    hours: float
    date: str

db.source("crm", RestSource(
    url=os.environ["HUBSPOT_API_URL"],
    auth=BearerAuth(token_env="HUBSPOT_TOKEN"),
    endpoints={
        "deals": "/crm/v3/objects/deals",
        "contacts": "/crm/v3/objects/contacts",
    },
    poll_interval=300,
    webhook=WebhookConfig(path="/webhooks/hubspot", secret_env="HUBSPOT_WEBHOOK_SECRET"),
))

db.source("finance", CloudSource(
    bucket=os.environ["SHAREPOINT_SITE"],
    provider="sharepoint",
    path="Shared Documents/Finance/projections.xlsx",
    poll_interval=600,
))

@db.product("partner_dashboard",
    depends_on=["Project", "Timesheet", "crm", "finance"],
    staleness=StalenessPolicy(max_age=timedelta(hours=2)),
)
async def partner_dashboard(ctx: FabricContext) -> dict:
    projects = await ctx.express.list("Project", filter={"status": "active"})
    timesheets = await ctx.express.list("Timesheet")
    deals = await ctx.source("crm").fetch("deals", params={"properties": "amount,dealstage,closedate"})
    projections = await ctx.source("finance").read()

    # Business logic: compute utilization
    total_budget = sum(p["hours_budget"] for p in projects)
    total_used = sum(t["hours"] for t in timesheets)
    utilization = (total_used / total_budget * 100) if total_budget > 0 else 0

    # Business logic: pipeline from CRM
    pipeline_value = sum(
        float(d.get("properties", {}).get("amount", 0))
        for d in deals.get("results", [])
        if d.get("properties", {}).get("dealstage") != "closedlost"
    )

    return {
        "utilization_pct": round(utilization, 1),
        "active_projects": len(projects),
        "pipeline_value": pipeline_value,
        "deals_in_pipeline": len(deals.get("results", [])),
        "projected_revenue": projections[0].get("q2_total", 0) if projections else 0,
    }

@db.product("project_list",
    mode="parameterized",
    depends_on=["Project", "Timesheet"],
)
async def project_list(ctx, status: str = None, page: int = 1, limit: int = 20):
    filters = {}
    if status:
        filters["status"] = status
    projects = await ctx.express.list("Project", filter=filters, limit=limit, offset=(page-1)*limit)
    count = await ctx.express.count("Project", filter=filters)
    return {"data": projects, "total": count, "page": page}

await db.start()
```

### Frontend Developer Consumes (15 minutes)

```typescript
// One hook for everything
const { data, isStale } = useFabricProduct("partner_dashboard");
const { data: projects } = useFabricProduct("project_list", {
  status: "active",
  page: 1,
});

// One hook for writes
const logTime = useFabricWrite("Timesheet");
logTime.mutate({
  operation: "create",
  data: { project_id: "p1", hours: 8, date: "2026-04-02" },
});
// → Dashboard auto-refreshes with updated utilization
```

### Operator Monitors (ongoing)

```
GET /fabric/_health
→ sources: crm=healthy, finance=healthy
→ products: partner_dashboard=fresh (age: 2min), project_list=fresh
→ cache: hit_rate=0.96

Alert: fabric_source_consecutive_failures{source="crm"} > 3
→ Slack notification: "HubSpot CRM connection lost, dashboard showing data from 15 min ago"
```

---

## Scenario 2: Source Goes Down and Recovers

```
T+0:   All sources healthy, dashboard fresh
T+5m:  CRM poll fails (HubSpot returns 503)
       Log: source=crm action=fetch_failed error=503 consecutive_failures=1
T+10m: CRM poll fails again
       Log: source=crm action=fetch_failed error=503 consecutive_failures=2
T+15m: CRM poll fails third time
       Circuit breaker OPENS
       Log: source=crm circuit=open consecutive_failures=3
       Health endpoint: sources.crm.health = "unhealthy"

T+15m: Pipeline runs for partner_dashboard
       ctx.source("crm").fetch() throws SourceUnavailableError
       Product catches it, uses stale data, sets degraded=true
       Cache updated: dashboard shows old CRM numbers + degraded flag

T+15m: FE fetches dashboard
       Response: _fabric.freshness = "fresh" (product ran successfully)
       But: data.degraded = true, data.degraded_sources = ["crm"]
       FE shows banner: "CRM data may be outdated"

T+16m: Circuit breaker probes CRM (lightweight health check)
       Still failing → stays open, probe again in 30s

T+20m: HubSpot recovers
       Circuit breaker probe succeeds
       Circuit breaker CLOSES
       Log: source=crm circuit=closed recovery=true

T+20m: Immediate pipeline trigger for all crm-dependent products
       Fresh CRM data fetched
       Cache updated: degraded=false

T+20m: FE fetches dashboard
       Response: _fabric.freshness = "fresh", degraded = false
       Banner disappears
```

---

## Scenario 3: Webhook-Driven Instant Update

```
T+0:   Sales rep closes deal in HubSpot
T+0s:  HubSpot fires webhook → POST /webhooks/hubspot
       Fabric validates HMAC signature
       Payload: { "event": "deal.closed", "deal_id": "d-123", "amount": 50000 }

T+0s:  Fabric identifies: products with "crm" in depends_on → ["partner_dashboard"]
       Pipeline triggered immediately (no waiting for poll)

T+1s:  Pipeline fetches fresh deals from HubSpot
       Product function runs
       pipeline_value increased by $50,000
       Cache atomic swap

T+1s:  FE next request (or TanStack Query refetch):
       Partner sees updated pipeline value — less than 2 seconds after deal closed
```

---

## Scenario 4: Finance Team Saves Spreadsheet

```
T+0:   CFO saves projections.xlsx on SharePoint

T+10m: CloudSource polls SharePoint metadata API
       Detects: LastModified changed from 2026-04-01T09:00 to 2026-04-02T16:45
       Pipeline triggered

       Fabric fetches updated file → parses Excel → runs product function
       projected_revenue changes from $1.2M to $1.4M
       Cache updated

T+10m: Partners see updated projection on dashboard

NOTE: poll_interval=600 means up to 10 minutes delay for SharePoint.
      If near-instant is needed: set poll_interval=60 (every minute).
      SharePoint does not support webhooks for file changes (Microsoft limitation).
```

---

## Scenario 5: Developer Debugging Stale Data

```
User reports: "Dashboard still shows old pipeline value"

Developer checks:
  GET /fabric/_health
  → sources.crm.health = "healthy", last_success = "2 min ago"
  → products.partner_dashboard.freshness = "fresh", age = "2 min"

Data looks fresh. Developer digs deeper:
  GET /fabric/_trace/partner_dashboard
  → Last run: triggered by poll, source=crm fetched 142 deals, duration 450ms
  → Inspects the deals data: deal d-123 is NOT in the response

Problem found: HubSpot API paginated response, fabric only fetched page 1.
Fix: update the product function to handle pagination:

  deals = await ctx.source("crm").fetch("deals", params={"limit": 500})
  # Or use fetch_all() for auto-pagination:
  deals = await ctx.source("crm").fetch_all("deals")
```
