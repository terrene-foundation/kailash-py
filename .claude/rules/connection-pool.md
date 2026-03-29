---
paths:
  - "**/*.py"
---

# Connection Pool Safety Rules

## Scope

These rules apply to all code that uses DataFlow, creates database connections, or configures application workers.

**Applies to**: `**/*.py`

## MUST Rules

### 1. Never Use Default Pool Size in Production

MUST set `DATAFLOW_MAX_CONNECTIONS` environment variable. The default pool size (typically 25 per worker) will exhaust PostgreSQL's connection limit on small-to-medium instances.

**Formula**: `pool_size = postgres_max_connections / num_workers * 0.7`

| Instance Size | `max_connections` | Workers | `DATAFLOW_MAX_CONNECTIONS` |
| ------------- | ----------------- | ------- | -------------------------- |
| t2.micro      | 87                | 2       | 30                         |
| t2.small      | 150               | 2       | 50                         |
| t2.medium     | 150               | 2       | 50                         |
| t3.medium     | 150               | 4       | 25                         |
| r5.large      | 1000              | 4       | 175                        |

```python
# WRONG — relies on default pool size
df = DataFlow("postgresql://...")

# RIGHT — explicit pool size from environment
import os
df = DataFlow(
    os.environ["DATABASE_URL"],
    max_connections=int(os.environ.get("DATAFLOW_MAX_CONNECTIONS", "10"))
)
```

**Enforced by**: deployment-specialist agent, pool-safety skill
**Violation**: BLOCK deployment

### 2. Never Query DB Per-Request in Middleware

MUST NOT call DataFlow workflows (ReadUser, ReadSession, etc.) in middleware that runs on every HTTP request. This creates N+1 connection usage where N is concurrent requests, rapidly exhausting the pool.

**Detection patterns**:

```python
# WRONG — DB query runs on EVERY request
class AuthMiddleware:
    async def __call__(self, request):
        user = await runtime.execute_async(  # Pool checkout per request!
            read_user_workflow.build(registry),
            inputs={"token": request.headers["Authorization"]}
        )
        request.state.user = user

# WRONG — DataFlow lookup in middleware
@app.middleware("http")
async def load_user(request, call_next):
    workflow = WorkflowBuilder()
    workflow.add_node("ReadUser", "read", {"filter": {"token": token}})
    result = await runtime.execute_async(workflow.build(registry), inputs={})
    # ...
```

**Correct patterns**:

```python
# RIGHT — JWT claims, no DB hit
class AuthMiddleware:
    async def __call__(self, request):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        claims = jwt.decode(token, key=os.environ["JWT_SECRET"], algorithms=["HS256"])
        request.state.user_id = claims["sub"]
        request.state.permissions = claims.get("permissions", [])

# RIGHT — In-memory cache with TTL for session data
from functools import lru_cache
from cachetools import TTLCache

_session_cache = TTLCache(maxsize=1000, ttl=300)  # 5-minute TTL

class AuthMiddleware:
    async def __call__(self, request):
        token = extract_token(request)
        if token in _session_cache:
            request.state.user = _session_cache[token]
        else:
            user = await self._fetch_user(token)  # DB hit only on cache miss
            _session_cache[token] = user
            request.state.user = user
```

**Enforced by**: intermediate-reviewer agent, pool-safety skill
**Violation**: BLOCK commit

### 3. Health Checks Must Not Use Application Pool

MUST use a lightweight query or a dedicated connection for health checks, never a full DataFlow workflow. Health checks run every 10-30 seconds per load balancer target — if they use the application pool, they consume connections continuously.

```python
# WRONG — full DataFlow workflow for health check
@app.get("/health")
async def health():
    workflow = WorkflowBuilder()
    workflow.add_node("ListUser", "check", {"limit": 1})
    result = await runtime.execute_async(workflow.build(registry), inputs={})
    return {"status": "ok"}

# RIGHT — lightweight raw query, dedicated connection
@app.get("/health")
async def health():
    try:
        async with asyncpg.connect(os.environ["DATABASE_URL"]) as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=503)

# RIGHT — if using SQLAlchemy/DataFlow pool, use a simple text query
@app.get("/health")
async def health():
    try:
        await db.execute_raw("SELECT 1")
        return {"status": "ok"}
    except Exception:
        return JSONResponse({"status": "error"}, status_code=503)
```

**Enforced by**: deployment-specialist agent
**Violation**: BLOCK deployment

### 4. Verify Pool Math at Deployment

Before deploying, MUST verify this inequality holds:

```
DATAFLOW_MAX_CONNECTIONS x num_workers <= postgres_max_connections x 0.7
```

The 0.7 factor reserves 30% of connections for admin tasks, migrations, monitoring, and connection spikes.

**Example**:

- PostgreSQL `max_connections = 150` (t2.medium default)
- Gunicorn workers = 4
- `DATAFLOW_MAX_CONNECTIONS = 25`
- Check: `25 x 4 = 100 <= 150 x 0.7 = 105` — PASS

**Counter-example** (the bug that created this rule):

- PostgreSQL `max_connections = 150`
- Gunicorn workers = 4
- `DATAFLOW_MAX_CONNECTIONS = 50` (or default)
- Check: `50 x 4 = 200 > 105` — FAIL. Pool exhaustion under load.

**Enforced by**: pool-safety skill during `/deploy`
**Violation**: BLOCK deployment

### 5. Connection Timeout Must Be Set

MUST set a connection acquisition timeout. Without it, requests queue indefinitely when the pool is exhausted, causing cascading timeouts.

```python
# WRONG — no timeout, requests hang forever
df = DataFlow(os.environ["DATABASE_URL"])

# RIGHT — timeout after 5 seconds
df = DataFlow(
    os.environ["DATABASE_URL"],
    max_connections=int(os.environ.get("DATAFLOW_MAX_CONNECTIONS", "10")),
    connection_timeout=5  # seconds
)
```

### 6. Async Workers Must Share Pool

When using async workers (uvicorn, hypercorn), all coroutines within a single worker share one pool. MUST NOT create a new DataFlow/pool instance per request or per route handler.

```python
# WRONG — new pool per request
@app.post("/users")
async def create_user(data: UserCreate):
    df = DataFlow(os.environ["DATABASE_URL"])  # New pool!
    # ...

# RIGHT — application-level singleton
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    app.state.df = DataFlow(
        os.environ["DATABASE_URL"],
        max_connections=int(os.environ.get("DATAFLOW_MAX_CONNECTIONS", "10"))
    )
    yield
    await app.state.df.close()

app = FastAPI(lifespan=lifespan)

@app.post("/users")
async def create_user(data: UserCreate, request: Request):
    df = request.app.state.df  # Shared pool
    # ...
```

## MUST NOT Rules

### 1. No Unbounded Connection Creation

MUST NOT create database connections in loops or recursive functions without pool limits.

```python
# WRONG — connection per iteration
for user_id in user_ids:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    result = await conn.fetch("SELECT * FROM users WHERE id = $1", user_id)
    await conn.close()

# RIGHT — use pool, or batch query
async with pool.acquire() as conn:
    results = await conn.fetch(
        "SELECT * FROM users WHERE id = ANY($1)", user_ids
    )
```

### 2. No Pool Size From User Input

MUST NOT allow pool size to be set from user-controlled input (API parameters, form fields).

## Cross-References

- `rules/deployment.md` — Production deployment checklist
- `rules/patterns.md` — DataFlow framework patterns
- `rules/infrastructure-sql.md` — SQL safety patterns
- `skills/project/pool-safety.md` — Deployment verification skill
