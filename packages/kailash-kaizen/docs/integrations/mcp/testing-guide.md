# MCP Integration Testing Guide for Kaizen

**Last Updated**: 2025-10-04

---

## Overview

This guide provides comprehensive testing strategies for Kaizen applications that integrate with MCP (Model Context Protocol). We follow a **3-tier testing strategy** with **NO MOCKING in Tiers 2-3** to ensure real protocol validation.

---

## Table of Contents

1. [3-Tier Testing Strategy](#3-tier-testing-strategy)
2. [Tier 1: Unit Tests (Mock MCP)](#tier-1-unit-tests-mock-mcp)
3. [Tier 2: Integration Tests (Real MCP)](#tier-2-integration-tests-real-mcp)
4. [Tier 3: E2E Tests (Complete Workflows)](#tier-3-e2e-tests-complete-workflows)
5. [Test Fixtures and Helpers](#test-fixtures-and-helpers)
6. [Common Assertions](#common-assertions)
7. [Performance Testing](#performance-testing)
8. [Error Testing](#error-testing)

---

## 3-Tier Testing Strategy

### Philosophy

**Tier 1**: Fast, isolated unit tests with mocks (milliseconds)
**Tier 2**: Real MCP infrastructure tests (seconds)
**Tier 3**: Complete workflow tests (seconds to minutes)

### Critical Rule

⚠️ **NO MOCKING IN TIERS 2-3**

Tiers 2 and 3 must use real MCP servers, real MCP clients, and real JSON-RPC protocol. This ensures:
- Protocol compliance
- Real error conditions
- Actual latency characteristics
- Production-like behavior

---

## Tier 1: Unit Tests (Mock MCP)

### Purpose

Test agent logic in isolation without network overhead or external dependencies.

### When to Use

- Configuration validation
- Signature structure tests
- Agent initialization
- Method behavior without MCP calls

### Pattern: Mock MCP Server

```python
import pytest
from kailash.mcp_server import SimpleMCPServer

@pytest.fixture
def mock_mcp_server():
    """Create mock MCP server for fast testing."""
    server = SimpleMCPServer("test-server")

    @server.tool()
    def add(a: int, b: int) -> dict:
        return {"result": a + b}

    @server.tool()
    def search(query: str) -> dict:
        return {"results": [f"Result for {query}"]}

    return server

def test_agent_config_validation(mock_mcp_server):
    """Test agent configuration without MCP calls."""
    config = MyAgentConfig(
        llm_provider="mock",
        model="test-model",
        mcp_servers=[{"name": "test-server", "transport": "stdio"}]
    )

    assert config.llm_provider == "mock"
    assert len(config.mcp_servers) == 1
```

### Pattern: Mock Tool Responses

```python
@pytest.fixture
def mock_tool_responses():
    """Mock responses for different tools."""
    return {
        "search": {
            "success": True,
            "results": ["result1", "result2", "result3"]
        },
        "analyze": {
            "success": True,
            "sentiment": "positive",
            "topics": ["AI", "testing"]
        }
    }

def test_agent_processes_tool_response(mock_tool_responses):
    """Test agent logic with mock tool response."""
    agent = MyAgent(config)

    # Process mock response
    result = agent.process_search_results(mock_tool_responses["search"])

    assert result["success"]
    assert len(result["processed_results"]) == 3
```

### Pattern: Configuration Tests

```python
def test_mcp_server_config_validation():
    """Test MCP server configuration validation."""
    # Valid config
    config = {
        "name": "test-server",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "test_server"]
    }

    from kaizen.core.base_agent import BaseAgent
    agent = BaseAgent(config={})

    # Should not raise
    # (actual validation happens in setup_mcp_client)

def test_signature_structure():
    """Test signature structure without MCP."""
    from kaizen.signatures import Signature, InputField, OutputField

    class MySignature(Signature):
        query: str = InputField()
        result: str = OutputField()

    sig = MySignature()
    assert hasattr(sig, 'query')
    assert hasattr(sig, 'result')
```

---

## Tier 2: Integration Tests (Real MCP)

### Purpose

Test real MCP client-server communication with real JSON-RPC protocol.

### When to Use

- MCP tool discovery
- MCP tool invocation
- JSON-RPC protocol validation
- Error handling
- Authentication

### Pattern: Real MCP Client-Server

```python
import pytest
from kailash.mcp_server import MCPClient, SimpleMCPServer

@pytest.fixture
async def real_mcp_server():
    """Create real MCP server for testing."""
    server = SimpleMCPServer("test-tools")

    @server.tool()
    def add(a: int, b: int) -> dict:
        return {"result": a + b}

    @server.tool()
    def search(query: str) -> dict:
        return {"results": [f"Found: {query}"]}

    # Start server in background (implementation depends on your setup)
    # For STDIO transport, you'd start a subprocess
    # For HTTP transport, you'd start the server on a port

    yield server

    # Cleanup
    # Stop server

@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_mcp_tool_discovery(real_mcp_server):
    """Test real MCP tool discovery via JSON-RPC."""
    # Create real MCP client
    client = MCPClient(enable_metrics=True)

    # Server configuration
    server_config = {
        "name": "test-tools",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "test_mcp_server"]
    }

    # Discover tools via real JSON-RPC
    tools = await client.discover_tools(server_config)

    # Verify tools discovered
    assert len(tools) > 0
    tool_names = [t["name"] for t in tools]
    assert "add" in tool_names
    assert "search" in tool_names
```

### Pattern: Real Tool Invocation

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_mcp_tool_invocation():
    """Test real MCP tool invocation via JSON-RPC."""
    client = MCPClient(enable_metrics=True)

    server_config = {
        "name": "test-tools",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "test_mcp_server"]
    }

    # Call tool via real JSON-RPC
    result = await client.call_tool(
        server_config,
        "add",
        {"a": 5, "b": 3},
        timeout=30.0
    )

    # Verify JSON-RPC response
    assert result["success"]
    assert result["result"] == 8
```

### Pattern: BaseAgent MCP Helpers

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_baseagent_setup_mcp_client():
    """Test BaseAgent.setup_mcp_client() with real MCP."""
    from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

    config = BaseAgentConfig(
        llm_provider="mock",
        model="test-model"
    )

    agent = BaseAgent(config=config)

    # Setup real MCP client
    servers = [
        {
            "name": "test-server",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "test_server"]
        }
    ]

    client = await agent.setup_mcp_client(
        servers=servers,
        retry_strategy="circuit_breaker",
        enable_metrics=True
    )

    # Verify client created
    assert agent._mcp_client is not None
    assert len(agent._available_mcp_tools) > 0

@pytest.mark.integration
@pytest.mark.asyncio
async def test_baseagent_call_mcp_tool():
    """Test BaseAgent.call_mcp_tool() with real MCP."""
    agent = BaseAgent(config=BaseAgentConfig(llm_provider="mock"))

    # Setup client first
    await agent.setup_mcp_client(servers=[...])

    # Call tool
    result = await agent.call_mcp_tool(
        tool_id="test-server:add",
        arguments={"a": 10, "b": 20},
        timeout=30.0,
        store_in_memory=True
    )

    # Verify result
    assert result["success"]
    assert result["result"] == 30
```

### Pattern: Authentication Testing

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_server_authentication():
    """Test MCP server with authentication."""
    from kailash.mcp_server import MCPServer
    from kailash.mcp_server.auth import APIKeyAuth

    # Create server with auth
    auth = APIKeyAuth({
        "demo-key": {"permissions": ["tools.*"]},
        "read-key": {"permissions": ["tools.read"]}
    })

    server = MCPServer(
        name="secure-server",
        auth_provider=auth,
        enable_metrics=True
    )

    @server.tool()
    async def protected_action(data: str) -> dict:
        return {"processed": data}

    # Test with valid key
    # (implementation depends on your test setup)

    # Test with invalid key
    # Should return authentication error
```

---

## Tier 3: E2E Tests (Complete Workflows)

### Purpose

Test complete agent workflows with real MCP infrastructure and real LLM providers.

### When to Use

- Full agent execution
- Multi-step workflows
- Multiple MCP servers
- Performance validation
- Production scenarios

### Pattern: Complete Agent Workflow

```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_agent_mcp_workflow():
    """Test complete agent workflow with MCP."""
    from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

    # 1. Create agent with real config
    config = BaseAgentConfig(
        llm_provider="openai",  # Real LLM provider
        model="gpt-4o-mini",
        temperature=0.7
    )

    agent = MyResearchAgent(config=config)

    # 2. Setup real MCP servers
    servers = [
        {
            "name": "search-tools",
            "transport": "http",
            "url": "http://localhost:8080",
            "headers": {"Authorization": "Bearer demo-key"}
        },
        {
            "name": "analysis-tools",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "analysis_server"]
        }
    ]

    await agent.setup_mcp_client(servers=servers)

    # 3. Execute workflow
    result = await agent.research("What is quantum computing?")

    # 4. Verify complete workflow
    assert result["success"]
    assert "answer" in result
    assert len(result["answer"]) > 0
    assert "sources" in result
```

### Pattern: Multi-Server Orchestration

```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_multi_server_orchestration():
    """Test agent using multiple MCP servers."""
    agent = MultiServerAgent(config)

    # Setup multiple servers
    servers = [
        {"name": "db-server", "transport": "stdio", ...},
        {"name": "api-server", "transport": "http", ...},
        {"name": "compute-server", "transport": "websocket", ...}
    ]

    await agent.setup_mcp_client(servers=servers)

    # Execute workflow requiring multiple servers
    result = await agent.complex_analysis(data)

    # Verify used multiple servers
    assert result["db_queries"] > 0
    assert result["api_calls"] > 0
    assert result["computations"] > 0
```

### Pattern: Performance E2E

```python
@pytest.mark.e2e
@pytest.mark.performance
@pytest.mark.asyncio
async def test_mcp_workflow_performance():
    """Test performance of complete MCP workflow."""
    import time

    agent = MyAgent(config)
    await agent.setup_mcp_client(servers=[...])

    # Measure end-to-end latency
    start_time = time.time()
    result = await agent.execute_workflow(task)
    latency = time.time() - start_time

    # Verify performance
    assert result["success"]
    assert latency < 5.0  # Should complete in < 5 seconds

    # Verify MCP overhead is acceptable
    mcp_time = result.get("mcp_time", 0)
    assert mcp_time < 2.0  # MCP calls should be < 2 seconds
```

---

## Test Fixtures and Helpers

### Standard Fixtures

```python
# tests/conftest.py

import pytest
from kailash.mcp_server import SimpleMCPServer, MCPClient

@pytest.fixture
def mock_mcp_server():
    """Standard mock MCP server for Tier 1 tests."""
    server = SimpleMCPServer("test-server")

    @server.tool()
    def add(a: int, b: int) -> dict:
        return {"result": a + b}

    @server.tool()
    def multiply(a: int, b: int) -> dict:
        return {"result": a * b}

    return server

@pytest.fixture
async def real_mcp_client():
    """Standard real MCP client for Tier 2 tests."""
    client = MCPClient(
        retry_strategy="circuit_breaker",
        enable_metrics=True
    )

    yield client

    # Cleanup
    # Close connections

@pytest.fixture
def mcp_server_configs():
    """Standard MCP server configurations."""
    return {
        "stdio": {
            "name": "test-stdio",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "test_server"]
        },
        "http": {
            "name": "test-http",
            "transport": "http",
            "url": "http://localhost:8080",
            "headers": {"Authorization": "Bearer test-key"}
        },
        "websocket": {
            "name": "test-ws",
            "transport": "websocket",
            "url": "ws://localhost:3001/mcp"
        }
    }
```

### Helper Functions

```python
# tests/utils/mcp_test_helpers.py

async def wait_for_server_ready(server_config, timeout=10):
    """Wait for MCP server to be ready."""
    import asyncio
    from kailash.mcp_server import MCPClient

    client = MCPClient()
    start_time = asyncio.get_event_loop().time()

    while asyncio.get_event_loop().time() - start_time < timeout:
        try:
            tools = await client.discover_tools(server_config)
            if len(tools) > 0:
                return True
        except:
            await asyncio.sleep(0.5)

    return False

def assert_json_rpc_response(response):
    """Assert response is valid JSON-RPC 2.0."""
    assert "jsonrpc" in response
    assert response["jsonrpc"] == "2.0"

    # Should have either result or error
    assert "result" in response or "error" in response

    if "error" in response:
        assert "code" in response["error"]
        assert "message" in response["error"]

async def call_mcp_tool_with_retry(client, server_config, tool_name, arguments, max_retries=3):
    """Call MCP tool with automatic retry."""
    import asyncio

    for attempt in range(max_retries):
        try:
            result = await client.call_tool(
                server_config,
                tool_name,
                arguments
            )
            return result
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(1.0 * (attempt + 1))
```

---

## Common Assertions

### MCP Protocol Assertions

```python
def assert_mcp_tool_discovered(tools, tool_name):
    """Assert tool was discovered via MCP."""
    tool_names = [t["name"] for t in tools]
    assert tool_name in tool_names, f"Tool {tool_name} not found in {tool_names}"

def assert_mcp_tool_has_schema(tool):
    """Assert tool has valid MCP schema."""
    assert "name" in tool
    assert "description" in tool
    assert "inputSchema" in tool or "parameters" in tool

def assert_mcp_response_success(response):
    """Assert MCP response indicates success."""
    assert response.get("success", False), f"MCP call failed: {response}"

def assert_mcp_response_error(response, expected_code=None):
    """Assert MCP response is an error."""
    assert "error" in response or not response.get("success", True)

    if expected_code and "error" in response:
        assert response["error"]["code"] == expected_code
```

### Agent Assertions

```python
def assert_agent_has_mcp_client(agent):
    """Assert agent has MCP client setup."""
    assert hasattr(agent, '_mcp_client')
    assert agent._mcp_client is not None

def assert_agent_has_mcp_tools(agent, min_tools=1):
    """Assert agent has MCP tools available."""
    assert hasattr(agent, '_available_mcp_tools')
    assert len(agent._available_mcp_tools) >= min_tools

def assert_agent_memory_has_mcp_calls(agent, min_calls=1):
    """Assert agent memory contains MCP tool calls."""
    if hasattr(agent, 'shared_memory') and agent.shared_memory:
        insights = agent.shared_memory.read_all()
        mcp_insights = [i for i in insights if "mcp_tool_call" in i.get("tags", [])]
        assert len(mcp_insights) >= min_calls
```

---

## Performance Testing

### Pattern: Latency Measurement

```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_mcp_tool_call_latency():
    """Test MCP tool call latency."""
    import time

    client = MCPClient(enable_metrics=True)
    server_config = {...}

    # Measure latency
    start_time = time.time()
    result = await client.call_tool(
        server_config,
        "fast_tool",
        {"input": "test"}
    )
    latency = time.time() - start_time

    # Verify acceptable latency
    assert latency < 1.0  # Should complete in < 1 second

    # Check client metrics
    metrics = client.get_metrics()
    assert metrics["total_calls"] == 1
```

### Pattern: Throughput Testing

```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_mcp_throughput():
    """Test MCP tool call throughput."""
    import asyncio
    import time

    client = MCPClient()
    server_config = {...}

    # Prepare requests
    requests = [
        {"tool": "add", "args": {"a": i, "b": i+1}}
        for i in range(100)
    ]

    # Execute concurrently
    start_time = time.time()
    tasks = [
        client.call_tool(server_config, req["tool"], req["args"])
        for req in requests
    ]
    results = await asyncio.gather(*tasks)
    total_time = time.time() - start_time

    # Calculate throughput
    throughput = len(requests) / total_time

    assert len(results) == len(requests)
    assert throughput > 10  # Should handle > 10 requests/sec
```

---

## Error Testing

### Pattern: Connection Errors

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_connection_error():
    """Test handling of MCP connection errors."""
    client = MCPClient()

    # Invalid server config
    server_config = {
        "name": "invalid-server",
        "transport": "http",
        "url": "http://localhost:99999"  # Invalid port
    }

    # Should raise or return error
    with pytest.raises(Exception):
        await client.discover_tools(server_config)
```

### Pattern: Tool Execution Errors

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_tool_execution_error():
    """Test handling of tool execution errors."""
    client = MCPClient()
    server_config = {...}

    # Call tool with invalid arguments
    result = await client.call_tool(
        server_config,
        "divide",
        {"a": 10, "b": 0}  # Division by zero
    )

    # Should return error response
    assert not result.get("success", False)
    assert "error" in result or "error_message" in result
```

### Pattern: Timeout Handling

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_timeout():
    """Test MCP timeout handling."""
    client = MCPClient()
    server_config = {...}

    # Call slow tool with short timeout
    with pytest.raises(asyncio.TimeoutError):
        await client.call_tool(
            server_config,
            "slow_tool",
            {"sleep": 10},
            timeout=1.0  # 1 second timeout
        )
```

---

## Running Tests

### Run All MCP Tests

```bash
pytest tests/ -m mcp -v
```

### Run by Tier

```bash
# Tier 1 (fast, no external dependencies)
pytest tests/unit/ -v

# Tier 2 (real MCP, no LLM)
pytest tests/integration/ -m "integration and mcp" -v

# Tier 3 (complete workflows with real LLM)
pytest tests/e2e/ -m "e2e and mcp" -v
```

### Run with Coverage

```bash
pytest tests/ -m mcp --cov=kaizen --cov-report=html
```

---

## Best Practices

1. **Use the right tier** - Don't use Tier 3 tests for logic that can be tested in Tier 1
2. **NO MOCKING in Tiers 2-3** - Use real MCP infrastructure
3. **Async everywhere** - MCP protocol is async, tests should be too
4. **Clean up resources** - Use fixtures with proper teardown
5. **Test error cases** - Don't just test happy paths
6. **Measure performance** - Track latency and throughput
7. **Use standard fixtures** - Reuse fixtures from conftest.py
8. **Document assumptions** - Note required services, ports, etc.

---

## Troubleshooting

### Tests Timing Out

- Increase timeout values for slow operations
- Check if MCP servers are actually running
- Verify network connectivity

### Import Errors

- Use `importlib.util` for loading example modules
- Don't pollute `sys.path`
- Use standardized test fixtures

### Flaky Tests

- Add retries for network operations
- Use `wait_for_server_ready()` helper
- Increase timeouts in CI environments

---

## See Also

- [MCP Integration README](./README.md) - Main integration guide
- [Quick Reference](./quick-reference.md) - Common patterns
- [Migration Guide](./migration-guide.md) - Migrating from kaizen.mcp

---

**Maintained by**: Kaizen Team
**Last Updated**: 2025-10-04
