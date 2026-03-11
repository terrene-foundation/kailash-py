# MCP Integration Test Migration Status

**Date**: 2025-10-04
**Status**: Partial Migration Complete - Tests Require Refactoring

## Summary

The MCP integration tests in `tests/integration/` were designed to test the deprecated `kaizen.mcp` implementation. Since the examples have been fully migrated to use production `kailash.mcp_server` via BaseAgent helpers, these integration tests need to be refactored to match the new patterns.

## Current State

### ✅ Completed
1. **`tests/integration/conftest.py`** - UPDATED
   - Removed deprecated `kaizen.mcp` imports
   - Replaced with real `kailash.mcp_server.SimpleMCPServer`
   - Removed `populate_agent_tools()` helper (deprecated pattern)
   - Now provides real MCP servers for integration testing

### ⚠️ Needs Refactoring
The following files use deprecated patterns and need significant rework:

1. **`tests/integration/test_mcp_agent_as_client_real_llm.py`**
   - **Issue**: Tests use `populate_agent_tools()` to manually copy tools
   - **Root Cause**: Tests were designed for deprecated `kaizen.mcp.MCPConnection`
   - **Solution Needed**: Refactor to use `BaseAgent.setup_mcp_client()` and automatic tool discovery

2. **`tests/integration/test_mcp_agent_as_server_real_llm.py`**
   - **Issue**: Tests use deprecated `kaizen.mcp` imports
   - **Root Cause**: Tests were designed for deprecated `kaizen.mcp.MCPServerConfig`
   - **Solution Needed**: Refactor to use `kailash.mcp_server.MCPServer` directly

## Why Tests Need Refactoring (Not Just Import Updates)

### The Fundamental Pattern Change

**Old Pattern (Deprecated)**:
```python
from kaizen.mcp import MCPConnection

# Manual connection
connection = MCPConnection(name="server", url="http://localhost:8080")
connection.connect()

# Manual tool population (workaround for string matching)
for tool in server.exposed_tools:
    client.available_tools[tool_id] = tool_info  # Manual copy
```

**New Pattern (Production)**:
```python
# Via BaseAgent helpers (recommended)
agent.setup_mcp_client(server_configs=[{
    "name": "server",
    "transport": "http",
    "url": "http://localhost:8080"
}])

# OR direct kailash.mcp_server usage
from kailash.mcp_server import MCPClient

client = MCPClient(enable_metrics=True)
tools = await client.discover_tools(server_config)  # Real JSON-RPC
result = await client.call_tool(server_config, "tool_name", args)  # Real JSON-RPC
```

### Key Differences

1. **Tool Discovery**:
   - Old: String matching + manual copying
   - New: Real JSON-RPC `tools/list` request

2. **Tool Invocation**:
   - Old: Mock responses via hardcoded lookup
   - New: Real JSON-RPC `tools/call` request

3. **Connection Management**:
   - Old: Manual `connect()`/`disconnect()` calls
   - New: Automatic via transport layer

4. **Error Handling**:
   - Old: Simple success/failure booleans
   - New: Full JSON-RPC error codes and retry strategies

## Recommended Approach for Test Migration

### Option 1: Refactor Tests to Match Examples (RECOMMENDED)

Since the examples (`examples/5-mcp-integration/`) have been fully migrated, the integration tests should test those migrated examples with real LLMs.

**Steps**:
1. Import example classes (already done)
2. Create agent instances using example configs
3. Use example methods (which use BaseAgent helpers internally)
4. Assert on real MCP protocol results (not manual tool copies)

**Example**:
```python
def test_openai_tool_discovery_real_protocol(openai_agent, mcp_server_info):
    """Test real MCP tool discovery via JSON-RPC."""
    # Agent should use BaseAgent.setup_mcp_client() internally
    # Tools discovered via real protocol, not manual copying

    # Execute task (which internally discovers and uses tools)
    result = openai_agent.execute_task(
        task="What is the capital of France?",
        context="Integration test"
    )

    # Assert on real MCP results
    assert result["success"]
    assert "final_answer" in result
```

### Option 2: Add New Real MCP Protocol Tests

Create new integration tests that specifically test:
- Real JSON-RPC tool discovery
- Real JSON-RPC tool invocation
- Real error handling and retry
- Real circuit breaker patterns
- Real metrics collection

**Location**: `tests/integration/test_real_mcp_protocol.py`

### Option 3: Mark Current Tests as Deprecated

Add `@pytest.mark.skip(reason="Deprecated - uses old kaizen.mcp patterns")` to current tests until refactoring is complete.

## Files Requiring Updates

### High Priority (Blocks Tests)
1. `tests/integration/test_mcp_agent_as_client_real_llm.py`
   - Remove `populate_agent_tools()` calls
   - Use agent methods that call BaseAgent helpers internally
   - Test real protocol results, not manual tool copies

2. `tests/integration/test_mcp_agent_as_server_real_llm.py`
   - Remove `kaizen.mcp` imports
   - Use `kailash.mcp_server.MCPServer` or example's migrated server
   - Test real JSON-RPC server responses

### Medium Priority (Import Errors)
1. `tests/unit/examples/test_agent_as_client.py`
   - Same issue - imports `kaizen.mcp`
   - Needs refactor to test migrated example

2. `tests/unit/examples/test_agent_as_server.py`
   - Same issue - imports `kaizen.mcp`
   - Needs refactor to test migrated example

## Impact Assessment

### Tests Currently Broken
- ❌ `test_openai_tool_schema_parsing` - Uses `populate_agent_tools()`
- ❌ `test_openai_argument_generation_from_natural_language` - Uses `populate_agent_tools()`
- ❌ `test_ollama_tool_invocation` - Uses `populate_agent_tools()`
- ❌ All tests in `test_mcp_agent_as_server_real_llm.py` - Import errors

### Tests That May Work (Need Verification)
- ✅ `test_openai_task_analysis_with_real_llm` - Doesn't use deprecated helpers
- ✅ `test_openai_end_to_end_mcp_workflow` - May work if example handles MCP internally
- ✅ `test_openai_memory_integration` - Tests memory, not MCP directly

## Next Steps

### Immediate (Required for Tests to Run)
1. ✅ Update `conftest.py` to use real `kailash.mcp_server` - DONE
2. ⏳ Update or skip tests using `populate_agent_tools()`
3. ⏳ Update or skip tests importing `kaizen.mcp` directly

### Short-term (Restore Test Coverage)
1. Refactor integration tests to test migrated examples
2. Focus on E2E scenarios (agent executes task → uses MCP internally → returns result)
3. Add assertions for real MCP protocol behavior

### Long-term (Expand Test Coverage)
1. Add tests for BaseAgent MCP helpers
2. Add tests for real JSON-RPC protocol
3. Add tests for enterprise features (auth, metrics, circuit breaker)

## Conclusion

The migration from `kaizen.mcp` to `kailash.mcp_server` via BaseAgent helpers represents a fundamental architectural change. The integration tests cannot be "fixed" with simple import updates - they need to be refactored to test the new patterns.

**Recommendation**: Refactor tests to match the migrated examples, focusing on E2E scenarios that test the real MCP protocol behavior rather than deprecated manual tool copying patterns.
