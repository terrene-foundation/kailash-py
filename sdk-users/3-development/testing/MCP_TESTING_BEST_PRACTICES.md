# MCP Testing Best Practices

A comprehensive guide to testing Model Context Protocol (MCP) implementations in the Kailash SDK.

## 🎯 MCP Testing Overview

**Test Suite Statistics**:
- **Total Tests**: 407 MCP-specific tests
- **Unit Tests**: 391 (fast, isolated)
- **Integration Tests**: 14 (real servers)
- **E2E Tests**: 2 (complete workflows)
- **Pass Rate**: 100%

## Three-Tier Testing Strategy

### 1. Unit Testing (391 tests)

**Purpose**: Test MCP components in isolation with mocked dependencies.

**Best Practices**:
```python
import pytest
from unittest.mock import MagicMock, patch
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

class TestMCPUnit:
    """Unit tests for MCP functionality."""

    def test_tool_discovery_mock(self):
        """Test tool discovery with mocked MCP server."""
        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", "agent", {
            "provider": "mock",
            "model": "gpt-4",
            "mcp_servers": [{
                "name": "test",
                "transport": "stdio",
                "command": "echo"
            }],
            "auto_discover_tools": True
        })

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert results["agent"]["success"] is True
        assert "tools_available" in results["agent"]["context"]

    def test_tool_execution_mock(self):
        """Test tool execution flow."""
        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", "agent", {
            "provider": "mock",
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Execute tool"}],
            "auto_execute_tools": True
        })

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert results["agent"]["success"] is True
```

**Key Patterns**:
- Always use `provider="mock"` for unit tests
- Mock external dependencies
- Test edge cases and error conditions
- Keep tests fast (< 1 second each)

### 2. Integration Testing (14 tests)

**Purpose**: Test MCP with real servers and protocols.

**Best Practices**:
```python
@pytest.mark.integration
class TestMCPIntegration:
    """Integration tests with real MCP servers."""

    @pytest.fixture
    def real_mcp_server(self):
        """Start a real MCP test server."""
        # Server started via Docker or subprocess
        yield {"name": "test", "transport": "stdio", "command": "mcp-test-server"}

    def test_stdio_transport(self, real_mcp_server):
        """Test STDIO transport with real server."""
        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", "agent", {
            "provider": "ollama",  # Use real provider
            "model": "llama3.2",
            "mcp_servers": [real_mcp_server],
            "auto_discover_tools": True,
            "messages": [{"role": "user", "content": "List tools"}]
        })

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify real tool discovery
        assert results["agent"]["success"] is True
        assert len(results["agent"]["context"]["tools_available"]) > 0

    def test_error_recovery(self, real_mcp_server):
        """Test connection failure recovery."""
        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", "agent", {
            "provider": "ollama",
            "model": "llama3.2",
            "mcp_servers": [{
                "name": "invalid",
                "transport": "stdio",
                "command": "nonexistent-command"
            }],
            "auto_discover_tools": True
        })

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Should gracefully handle failure
        assert results["agent"]["success"] is True
        assert results["agent"]["context"]["tools_available"] == []
```

**Key Patterns**:
- Use real providers (Ollama, OpenAI)
- Test actual protocol communication
- Verify error recovery mechanisms
- Use Docker for consistent test environment

### 3. End-to-End Testing (2 scenarios)

**Purpose**: Validate complete MCP workflows.

**Best Practices**:
```python
@pytest.mark.e2e
class TestMCPEndToEnd:
    """Complete workflow tests."""

    def test_multi_round_tool_execution(self):
        """Test complex multi-round tool execution."""
        from kailash.workflow.builder import WorkflowBuilder
        from kailash.runtime.local import LocalRuntime

        # Build workflow
        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", "agent", {})

        # Execute with real MCP server
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build(), parameters={
            "agent": {
                "provider": "ollama",
                "model": "llama3.2:1b",
                "mcp_servers": [{
                    "name": "data-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "mcp_data_server"]
                }],
                "auto_discover_tools": True,
                "auto_execute_tools": True,
                "tool_execution_config": {
                    "max_rounds": 3
                },
                "messages": [
                    {"role": "user", "content": "Search data, analyze it, and create a report"}
                ]
            }
        })

        # Verify complete execution
        assert results["agent"]["success"] is True
        assert len(results["agent"]["context"]["tools_executed"]) >= 2
        assert "report" in results["agent"]["response"].lower()
```

**Key Patterns**:
- Test realistic user scenarios
- Verify multi-step workflows
- Check end-to-end data flow
- Validate business outcomes

## Testing Async Contexts

MCP must handle various async execution contexts:

```python
def test_jupyter_environment():
    """Test MCP in Jupyter-like environment."""
    import asyncio

    # Create event loop (simulates Jupyter)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Run background task
    async def background():
        while True:
            await asyncio.sleep(0.1)

    task = loop.create_task(background())

    try:
        # MCP should work despite active loop
        node = "LLMAgentNode"
        result = node.run(
            provider="mock",
            model="gpt-4",
            mcp_servers=[test_server],
            auto_discover_tools=True
        )

        assert result["success"] is True
    finally:
        task.cancel()
        loop.close()
```

## Error Handling Patterns

### Timeout Testing
```python
def test_mcp_timeout_handling():
    """Test timeout protection."""
    node = "LLMAgentNode"

    result = node.run(
        provider="mock",
        model="gpt-4",
        mcp_servers=[{
            "name": "slow-server",
            "transport": "stdio",
            "command": "sleep",
            "args": ["30"]  # Will timeout
        }],
        mcp_config={
            "connection_timeout": 5  # 5 second timeout
        }
    )

    # Should handle timeout gracefully
    assert result["success"] is True
    assert result["context"]["tools_available"] == []
```

### Connection Failure Testing
```python
def test_connection_failure_recovery():
    """Test connection failure handling."""
    node = "LLMAgentNode"

    # Multiple servers, one failing
    result = node.run(
        provider="mock",
        model="gpt-4",
        mcp_servers=[
            {"name": "good", "transport": "stdio", "command": "echo"},
            {"name": "bad", "transport": "stdio", "command": "nonexistent"},
            {"name": "good2", "transport": "stdio", "command": "cat"}
        ],
        auto_discover_tools=True
    )

    # Should discover tools from working servers
    assert result["success"] is True
    assert len(result["context"]["tools_available"]) >= 2
```

## Performance Testing

```python
def test_mcp_performance():
    """Test MCP performance characteristics."""
    import time

    node = "LLMAgentNode"

    # Measure tool discovery time
    start = time.time()
    result = node.run(
        provider="mock",
        model="gpt-4",
        mcp_servers=[test_server] * 5,  # Multiple servers
        auto_discover_tools=True
    )
    discovery_time = time.time() - start

    # Should be fast
    assert discovery_time < 2.0  # Under 2 seconds
    assert result["success"] is True
```

## Test Organization

### Directory Structure
```
tests/
├── unit/
│   └── mcp/
│       ├── test_client.py
│       ├── test_server.py
│       ├── test_tool_execution.py
│       └── test_error_handling.py
├── integration/
│   └── nodes/
│       └── ai/
│           └── test_llm_agent_mcp_real.py
└── e2e/
    └── test_mcp_workflows.py
```

### Test Markers
```python
# Mark tests appropriately
@pytest.mark.unit          # Fast, no dependencies
@pytest.mark.integration   # Requires Docker/services
@pytest.mark.e2e          # Full workflow tests
@pytest.mark.slow         # Long-running tests
@pytest.mark.mcp          # All MCP-related tests
```

## CI/CD Integration

### GitHub Actions Example
```yaml
name: MCP Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run MCP Unit Tests
        run: pytest tests/unit/ -k "mcp" -v

  integration-tests:
    runs-on: ubuntu-latest
    services:
      ollama:
        image: ollama/ollama
        ports:
          - 11435:11434
    steps:
      - uses: actions/checkout@v2
      - name: Run MCP Integration Tests
        run: pytest tests/integration/ -k "mcp" -v
```

## Common Testing Pitfalls

### 1. Not Mocking in Unit Tests
❌ **Bad**:
```python
def test_mcp_unit():
    # This will be slow and flaky
    result = node.run(provider="openai", ...)
```

✅ **Good**:
```python
def test_mcp_unit():
    # Fast and reliable
    result = node.run(provider="mock", ...)
```

### 2. Missing Async Context Tests
❌ **Bad**: Only testing synchronous execution

✅ **Good**: Test both sync and async contexts

### 3. Inadequate Error Testing
❌ **Bad**: Only testing happy path

✅ **Good**: Test timeouts, failures, and recovery

### 4. Not Using Test Markers
❌ **Bad**: Running all tests together

✅ **Good**: Properly mark and organize tests

## Debugging MCP Tests

### Enable Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Now run your test
def test_mcp_debug():
    # Debug logs will show MCP communication
    result = node.run(...)
```

### Capture MCP Communication
```python
def test_mcp_communication():
    """Capture and verify MCP messages."""
    from unittest.mock import patch

    captured_messages = []

    with patch('kailash.mcp.client.send_message') as mock_send:
        mock_send.side_effect = lambda msg: captured_messages.append(msg)

        result = node.run(...)

    # Verify message structure
    assert len(captured_messages) > 0
    assert captured_messages[0]["method"] == "tools/list"
```

## Test Data Management

### Mock MCP Responses
```python
# tests/fixtures/mcp_responses.py
MOCK_TOOL_LIST = {
    "tools": [
        {
            "name": "search",
            "description": "Search for information",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                }
            }
        }
    ]
}

# Use in tests
def test_with_mock_data():
    with patch('mcp_client.list_tools', return_value=MOCK_TOOL_LIST):
        result = node.run(...)
```

## Continuous Improvement

1. **Monitor Test Times**: Keep unit tests under 1 second
2. **Track Flaky Tests**: Fix or mark as flaky
3. **Coverage Goals**: Maintain > 90% coverage for MCP code
4. **Regular Updates**: Update tests when MCP protocol changes
5. **Documentation**: Keep test documentation current

## Summary

The MCP testing strategy ensures:
- **Fast Feedback**: Unit tests run in seconds
- **Real Validation**: Integration tests catch protocol issues
- **Business Confidence**: E2E tests verify user scenarios
- **Robust Error Handling**: Comprehensive failure testing
- **Maintainability**: Clear organization and patterns

With 407 tests achieving 100% pass rate, the MCP implementation is production-ready and thoroughly validated.
