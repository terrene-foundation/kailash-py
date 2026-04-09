---
paths:
  - "**/db/**"
  - "**/pool*"
  - "**/database*"
  - "**/infrastructure/**"
---

# Connection Pool Safety Rules

> **Scope**: Application code MUST go through DataFlow (`@db.model`, `db.express`) which manages pools for you — see `framework-first.md` § Work-Domain Binding. These rules are for SDK-level pool tuning and for advanced consumers who own the pool lifecycle.

### 1. Never Use Default Pool Size in Production

Set `DATAFLOW_MAX_CONNECTIONS` env var. Default (25/worker) exhausts PostgreSQL on small instances.

**Why:** The default 25 connections/worker times 4 workers = 100 connections, exceeding `max_connections` on t2.micro (87) and causing immediate connection refusal at scale.

**Formula**: `pool_size = postgres_max_connections / num_workers * 0.7`

| Instance        | `max_connections` | Workers | `DATAFLOW_MAX_CONNECTIONS` |
| --------------- | ----------------- | ------- | -------------------------- |
| t2.micro        | 87                | 2       | 30                         |
| t2.small/medium | 150               | 2       | 50                         |
| t3.medium       | 150               | 4       | 25                         |
| r5.large        | 1000              | 4       | 175                        |

```python
# ❌ relies on default pool size
df = DataFlow("postgresql://...")

# ✅ explicit pool size from environment
df = DataFlow(
    os.environ["DATABASE_URL"],
    max_connections=int(os.environ.get("DATAFLOW_MAX_CONNECTIONS", "10"))
)
```

### 2. Never Query DB Per-Request in Middleware

Creates N+1 connection usage, rapidly exhausting pool.

**Why:** Every HTTP request holds a connection for auth lookup before the handler even runs, so under load the pool is exhausted by middleware alone and no handler can acquire a connection.

```python
# ❌ DB query on EVERY request
class AuthMiddleware:
    async def __call__(self, request):
        user = await runtime.execute_async(read_user_workflow.build(registry), ...)

# ✅ JWT claims, no DB hit
class AuthMiddleware:
    async def __call__(self, request):
        claims = jwt.decode(token, key=os.environ["JWT_SECRET"], algorithms=["HS256"])
        request.state.user_id = claims["sub"]

# ✅ In-memory cache with TTL
_session_cache = TTLCache(maxsize=1000, ttl=300)
```

### 3. Health Checks Must Not Use Application Pool

Use lightweight `SELECT 1` with dedicated connection, never a full DataFlow workflow.

**Why:** Load balancer health checks fire every 5-30 seconds per instance — if they use application pool connections, they compete with real requests and can trigger false "unhealthy" cascades.

### 4. Verify Pool Math at Deployment

```
DATAFLOW_MAX_CONNECTIONS × num_workers ≤ postgres_max_connections × 0.7
```

The 0.7 reserves 30% for admin, migrations, monitoring.

**Why:** If pool math exceeds PostgreSQL's `max_connections`, deploys succeed but the application fails under load when the last worker tries to open a connection — a time-bomb that only detonates in production.

**Example**: 150 max_connections, 4 workers → `DATAFLOW_MAX_CONNECTIONS = 25` → `25 × 4 = 100 ≤ 105` PASS

### 5. Connection Timeout Must Be Set

Without timeout, requests queue indefinitely when pool exhausted → cascading failures.

**Why:** An indefinite wait turns a temporary pool exhaustion into a permanent hang — all worker threads block, the health check fails, and the load balancer takes the instance offline.

### 6. Async Workers Must Share Pool

Application-level singleton. MUST NOT create new pool per request or per route handler.

**Why:** A new pool per request means every request opens fresh connections (bypassing pooling entirely), and those pools are never closed, leaking connections until PostgreSQL refuses all new ones.

```python
# ❌ new pool per request
@app.post("/users")
async def create_user():
    df = DataFlow(os.environ["DATABASE_URL"])  # New pool!

# ✅ application-level singleton via lifespan
@asynccontextmanager
async def lifespan(app):
    app.state.df = DataFlow(os.environ["DATABASE_URL"], ...)
    yield
    await app.state.df.close()
```

## MUST NOT

- No unbounded connection creation in loops — use pool or batch queries
  **Why:** A loop creating one connection per iteration can open thousands of connections in seconds, exhausting PostgreSQL and crashing all other applications sharing the database.
- No pool size from user input (API params, form fields)
  **Why:** A malicious request setting `pool_size=100000` triggers mass connection creation, instantly exhausting database resources and causing a denial-of-service.
