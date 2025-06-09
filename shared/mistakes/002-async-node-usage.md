# Mistake #002: Async Node Usage

## Category
Architecture

## Severity
Critical

## Problem
Creating nodes with async operations (API calls, MCP clients, etc.) but inheriting from `Node` instead of `AsyncNode`, causing runtime failures.

## Symptoms
- Error message: `RuntimeError: unhandled errors in a TaskGroup`
- Error message: `RuntimeError: This event loop is already running`
- Async operations fail silently or hang
- Node execution seems to work but no results are produced

## Example
```python
# ❌ WRONG - Using Node for async operations
class MCPClientNode(Node):  # Wrong base class!
    def run(self, **inputs):
        # This will fail at runtime
        async with ClientSession(server, client_params) as session:
            result = await session.request(...)
        return {"result": result}

# ✅ CORRECT - Using AsyncNode for async operations
class MCPClientNode(AsyncNode):  # Correct base class
    async def async_run(self, **inputs):  # Note: async_run, not run
        async with ClientSession(server, client_params) as session:
            result = await session.request(...)
        return {"result": result}
```

## Root Cause
The LocalRuntime intelligently detects async nodes and runs them in an async context, but it needs the node to:
1. Inherit from `AsyncNode`
2. Implement `async_run()` instead of `run()`

This confusion happens because:
- Python allows mixing sync/async code syntactically
- The error doesn't surface until runtime execution
- It's not obvious which operations require async handling

## Solution
1. Identify any I/O operations in your node (network, file, database)
2. If using `async`/`await` anywhere, use `AsyncNode`
3. Implement `async_run()` method instead of `run()`
4. Ensure all async operations use `await`

## Prevention
- Default to `AsyncNode` for any I/O operations
- Common async operations: HTTP requests, MCP calls, database queries
- Use `AsyncNode` when in doubt - it works for sync operations too
- Check imports: if you see `asyncio`, `aiohttp`, etc., use `AsyncNode`

## Related Mistakes
- [#023 - Sync IO in Async Context](023-sync-io-async-context.md)
- [#052 - Blocking IO in Async](052-blocking-io-async.md)

## Fixed In
- Session: 2024-01-06 - MCP client implementation
- PR: Multiple PRs improving async handling

## References
- [AsyncNode API](../reference/api-registry.yaml#asyncnode)
- [MCP Integration Guide](../features/mcp_ecosystem.md)
- [Node Catalog](../reference/node-catalog.md) - See which nodes are async
