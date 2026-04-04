---
paths:
  - "**/db/**"
  - "**/pool*"
  - "**/database*"
  - "**/infrastructure/**"
---

# Connection Pool Safety Rules

### 1. Never Use Default Pool Size in Production

Set `DATAFLOW_MAX_CONNECTIONS` env var. Default (25/worker) exhausts PostgreSQL on small instances.

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

### 4. Verify Pool Math at Deployment

```
DATAFLOW_MAX_CONNECTIONS × num_workers ≤ postgres_max_connections × 0.7
```

The 0.7 reserves 30% for admin, migrations, monitoring.

**Example**: 150 max_connections, 4 workers → `DATAFLOW_MAX_CONNECTIONS = 25` → `25 × 4 = 100 ≤ 105` PASS

### 5. Connection Timeout Must Be Set

Without timeout, requests queue indefinitely when pool exhausted → cascading failures.

### 6. Async Workers Must Share Pool

Application-level singleton. MUST NOT create new pool per request or per route handler.

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
- No pool size from user input (API params, form fields)
