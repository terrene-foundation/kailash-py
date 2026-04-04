---
description: Data Fabric cache control, consumer adapters, and MCP tool generation
paths: ["packages/kailash-dataflow/src/dataflow/fabric/**"]
---

# Fabric Cache Control + Consumer Adapters

## Cache Control

```python
# Invalidate specific product cache
db.fabric.invalidate("portfolio_snapshot")

# Invalidate with params (parameterized products)
db.fabric.invalidate("users", params={"region": "us"})

# Clear all caches
count = db.fabric.invalidate_all()

# Per-request cache bypass
# GET /fabric/portfolio?refresh=true
```

## Consumer Adapters

Transform canonical product data into consumer-specific views.

```python
# Register consumer transforms (pure functions)
db.fabric.register_consumer("maturity_report", to_maturity_report)
db.fabric.register_consumer("chat_summary", to_chat_summary)

# Declare supported consumers on products
@db.product("portfolio", consumers=["maturity_report", "chat_summary"])
async def portfolio(ctx):
    return {"loans": [...], "market": {...}}

# Access consumer views
# GET /fabric/portfolio                      → canonical data
# GET /fabric/portfolio?consumer=maturity_report → transformed data
# X-Fabric-Consumer header set when consumer used
```

## MCP Tool Generation

```python
# Auto-generate MCP tools from products
tools = db.fabric.get_mcp_tools()
# Returns list of MCP tool definitions: get_portfolio, get_dashboard, etc.

# Optional: register with MCP server
from dataflow.fabric.mcp_integration import register_with_mcp
register_with_mcp(db.fabric, mcp_server)
```

## Fabric-Only Mode

```python
# No database required — just sources + products
db = DataFlow()  # database_url=None
db.source("loans", MyAdapter("loans"))

@db.product("summary", mode="virtual", depends_on=["loans"])
async def summary(ctx):
    return await ctx.source("loans").fetch("active")

await db.start(dev_mode=True, prewarm=True)
```

## Virtual Products

Virtual products execute inline on every request (never cached):

```python
@db.product("active_count", mode="virtual", depends_on=["loans"])
async def active_count(ctx):
    return {"count": len(await ctx.source("loans").fetch("active"))}
```

## Graceful Shutdown

```python
await db.fabric.drain(timeout=30.0)  # Wait for in-flight pipelines
```
