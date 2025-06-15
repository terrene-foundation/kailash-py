"""Unit tests for the Multi-Workflow API Gateway."""

import asyncio

import pytest
from fastapi.testclient import TestClient

# Skip all tests in this file as the API gateway has been refactored
pytestmark = pytest.mark.skip(reason="API gateway refactored to middleware")

from kailash.nodes.code import PythonCodeNode
from kailash.workflow import Workflow


class TestWorkflowAPIGateway:
    """Test cases for WorkflowAPIGateway."""

    def test_gateway_initialization(self):
        """Test gateway initialization with default parameters."""
        gateway = WorkflowAPIGateway()

        assert gateway.app.title == "Kailash Workflow Gateway"
        assert gateway.app.version == "1.0.0"
        assert len(gateway.workflows) == 0
        assert len(gateway.mcp_servers) == 0
        assert gateway.executor._max_workers == 10

    def test_gateway_initialization_with_params(self):
        """Test gateway initialization with custom parameters."""
        gateway = WorkflowAPIGateway(
            title="Test Gateway",
            description="Test Description",
            version="2.0.0",
            max_workers=20,
            cors_origins=["http://localhost:3000"],
        )

        assert gateway.app.title == "Test Gateway"
        assert gateway.app.description == "Test Description"
        assert gateway.app.version == "2.0.0"
        assert gateway.executor._max_workers == 20

    def test_register_workflow(self):
        """Test registering a workflow."""
        gateway = WorkflowAPIGateway()

        # Create a simple workflow
        workflow = Workflow(
            workflow_id="test_001", name="Test Workflow", description="A test workflow"
        )

        # Add a simple node
        node = PythonCodeNode(name="test_node", code="output = input_data")
        workflow.add_node("process", node)

        # Register workflow
        gateway.register_workflow(
            "test",
            workflow,
            description="Test workflow",
            version="1.0.0",
            tags=["test", "example"],
        )

        assert "test" in gateway.workflows
        assert gateway.workflows["test"].name == "test"
        assert gateway.workflows["test"].type == "embedded"
        assert gateway.workflows["test"].description == "Test workflow"
        assert gateway.workflows["test"].version == "1.0.0"
        assert gateway.workflows["test"].tags == ["test", "example"]

    def test_register_duplicate_workflow(self):
        """Test registering a workflow with duplicate name."""
        gateway = WorkflowAPIGateway()

        workflow = Workflow("test_001", "Test Workflow")

        # Register first time
        gateway.register_workflow("test", workflow)

        # Try to register again
        with pytest.raises(ValueError, match="Workflow 'test' already registered"):
            gateway.register_workflow("test", workflow)

    def test_root_endpoints(self):
        """Test gateway root endpoints."""
        gateway = WorkflowAPIGateway(title="Test Gateway", version="1.0.0")

        # Register a workflow
        workflow = Workflow("test_001", "Test Workflow")
        gateway.register_workflow("test", workflow)

        # Test with TestClient
        client = TestClient(gateway.app)

        # Test root endpoint
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Gateway"
        assert data["version"] == "1.0.0"
        assert "test" in data["workflows"]

        # Test workflows endpoint
        response = client.get("/workflows")
        assert response.status_code == 200
        data = response.json()
        assert "test" in data
        assert data["test"]["type"] == "embedded"
        assert "/test/execute" in data["test"]["endpoints"]

        # Test health endpoint
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "test" in data["workflows"]

    def test_register_mcp_server(self):
        """Test registering an MCP server."""
        gateway = WorkflowAPIGateway()

        # Create MCP server
        mcp = MCPIntegration("test_mcp", "Test MCP Server")
        mcp.add_tool("test_tool", lambda x: x, "Test tool")

        # Register MCP server
        gateway.register_mcp_server("test", mcp)

        assert "test" in gateway.mcp_servers
        assert gateway.mcp_servers["test"] == mcp

    def test_register_duplicate_mcp_server(self):
        """Test registering duplicate MCP server."""
        gateway = WorkflowAPIGateway()

        mcp = MCPIntegration("test_mcp")

        # Register first time
        gateway.register_mcp_server("test", mcp)

        # Try to register again
        with pytest.raises(ValueError, match="MCP server 'test' already registered"):
            gateway.register_mcp_server("test", mcp)

    def test_proxy_workflow(self):
        """Test registering a proxied workflow."""
        gateway = WorkflowAPIGateway()

        # Register proxy workflow
        gateway.proxy_workflow(
            "external",
            "http://external-service:8080",
            health_check="/health",
            description="External workflow",
            version="1.0.0",
            tags=["external", "proxy"],
        )

        assert "external" in gateway.workflows
        assert gateway.workflows["external"].type == "proxied"
        assert gateway.workflows["external"].proxy_url == "http://external-service:8080"
        assert gateway.workflows["external"].health_check == "/health"

    def test_get_workflow_endpoints(self):
        """Test getting workflow endpoints."""
        gateway = WorkflowAPIGateway()

        # Register embedded workflow
        workflow = Workflow("test_001", "Test")
        gateway.register_workflow("test", workflow)

        endpoints = gateway._get_workflow_endpoints("test")
        assert "/test/execute" in endpoints
        assert "/test/workflow/info" in endpoints
        assert "/test/health" in endpoints
        assert "/test/docs" in endpoints

        # Register proxied workflow
        gateway.proxy_workflow("external", "http://external:8080")

        endpoints = gateway._get_workflow_endpoints("external")
        assert "/external/execute" in endpoints
        assert "/external/docs" not in endpoints  # No docs for proxied

    @pytest.mark.asyncio
    async def test_websocket_endpoint(self):
        """Test WebSocket endpoint."""
        gateway = WorkflowAPIGateway()
        client = TestClient(gateway.app)

        with client.websocket_connect("/ws") as websocket:
            # Send subscription message
            websocket.send_json({"type": "subscribe", "workflow": "test"})

            # Receive acknowledgment
            data = websocket.receive_json()
            assert data["type"] == "ack"
            assert data["message"] == "Message received"

    def test_workflow_registration_model(self):
        """Test WorkflowRegistration model."""
        workflow = Workflow("test_001", "Test")

        registration = WorkflowRegistration(
            name="test",
            type="embedded",
            workflow=workflow,
            description="Test workflow",
            version="1.0.0",
            tags=["test"],
        )

        assert registration.name == "test"
        assert registration.type == "embedded"
        assert registration.workflow == workflow
        assert registration.description == "Test workflow"
        assert registration.version == "1.0.0"
        assert registration.tags == ["test"]

    def test_cors_middleware(self):
        """Test CORS middleware configuration."""
        gateway = WorkflowAPIGateway(
            cors_origins=["http://localhost:3000", "https://app.example.com"]
        )

        client = TestClient(gateway.app)

        # Test CORS headers
        response = client.options(
            "/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:3000"
        )


class TestMCPIntegration:
    """Test cases for MCPIntegration."""

    def test_mcp_initialization(self):
        """Test MCP server initialization."""
        mcp = MCPIntegration(
            "test_server",
            "Test MCP Server",
            capabilities=["tools", "resources", "context"],
        )

        assert mcp.name == "test_server"
        assert mcp.description == "Test MCP Server"
        assert mcp.capabilities == ["tools", "resources", "context"]
        assert len(mcp.tools) == 0
        assert len(mcp.resources) == 0

    def test_add_sync_tool(self):
        """Test adding a synchronous tool."""
        mcp = MCPIntegration("test")

        def test_function(x: int, y: int) -> int:
            """Test function."""
            return x + y

        mcp.add_tool(
            "add",
            test_function,
            "Add two numbers",
            {"x": {"type": "integer"}, "y": {"type": "integer"}},
        )

        assert "add" in mcp.tools
        assert mcp.tools["add"].name == "add"
        assert mcp.tools["add"].description == "Add two numbers"
        assert mcp.tools["add"].function == test_function

    def test_add_async_tool(self):
        """Test adding an asynchronous tool."""
        mcp = MCPIntegration("test")

        async def async_function(x: int) -> int:
            """Async test function."""
            await asyncio.sleep(0.1)
            return x * 2

        mcp.add_tool("double", async_function, "Double a number")

        assert "double" in mcp.tools
        assert mcp.tools["double"].async_function == async_function

    def test_execute_sync_tool(self):
        """Test executing a synchronous tool."""
        mcp = MCPIntegration("test")

        def multiply(a: int, b: int) -> int:
            return a * b

        mcp.add_tool("multiply", multiply)

        result = mcp.execute_tool_sync("multiply", {"a": 5, "b": 3})
        assert result == 15

    @pytest.mark.asyncio
    async def test_execute_async_tool(self):
        """Test executing an asynchronous tool."""
        mcp = MCPIntegration("test")

        async def async_multiply(a: int, b: int) -> int:
            await asyncio.sleep(0.1)
            return a * b

        mcp.add_tool("async_multiply", async_multiply)

        result = await mcp.execute_tool("async_multiply", {"a": 5, "b": 3})
        assert result == 15

    def test_execute_nonexistent_tool(self):
        """Test executing a non-existent tool."""
        mcp = MCPIntegration("test")

        with pytest.raises(ValueError, match="Tool 'nonexistent' not found"):
            mcp.execute_tool_sync("nonexistent", {})

    def test_add_resource(self):
        """Test adding a resource."""
        mcp = MCPIntegration("test")

        mcp.add_resource(
            "test_doc", "file:///test/doc.txt", "Test document", "text/plain"
        )

        assert "test_doc" in mcp.resources
        assert mcp.resources["test_doc"].name == "test_doc"
        assert mcp.resources["test_doc"].uri == "file:///test/doc.txt"
        assert mcp.resources["test_doc"].mime_type == "text/plain"

    def test_get_resource(self):
        """Test getting a resource."""
        mcp = MCPIntegration("test")

        mcp.add_resource("doc", "file:///doc.txt", "Document")

        resource = mcp.get_resource("doc")
        assert resource is not None
        assert resource.name == "doc"

        # Test non-existent resource
        assert mcp.get_resource("nonexistent") is None

    def test_context_management(self):
        """Test context setting and getting."""
        mcp = MCPIntegration("test")

        # Set context
        mcp.set_context("user_id", "12345")
        mcp.set_context("session", {"id": "abc", "active": True})

        # Get context
        assert mcp.get_context("user_id") == "12345"
        assert mcp.get_context("session")["active"] is True
        assert mcp.get_context("nonexistent") is None

    def test_list_tools(self):
        """Test listing tools."""
        mcp = MCPIntegration("test")

        mcp.add_tool("tool1", lambda: None, "Tool 1", {"param": {"type": "string"}})
        mcp.add_tool("tool2", lambda: None, "Tool 2")

        tools = mcp.list_tools()
        assert len(tools) == 2
        assert tools[0]["name"] == "tool1"
        assert tools[0]["description"] == "Tool 1"
        assert tools[0]["parameters"] == {"param": {"type": "string"}}

    def test_list_resources(self):
        """Test listing resources."""
        mcp = MCPIntegration("test")

        mcp.add_resource("res1", "file:///1.txt", "Resource 1", "text/plain")
        mcp.add_resource("res2", "file:///2.json", "Resource 2", "application/json")

        resources = mcp.list_resources()
        assert len(resources) == 2
        assert resources[0]["name"] == "res1"
        assert resources[0]["mime_type"] == "text/plain"

    def test_to_mcp_protocol(self):
        """Test conversion to MCP protocol format."""
        mcp = MCPIntegration("test", "Test Server", ["tools", "resources"])

        mcp.add_tool("test_tool", lambda: None, "Test")
        mcp.add_resource("test_res", "file:///test.txt", "Test")

        protocol = mcp.to_mcp_protocol()

        assert protocol["name"] == "test"
        assert protocol["description"] == "Test Server"
        assert protocol["capabilities"] == ["tools", "resources"]
        assert len(protocol["tools"]) == 1
        assert len(protocol["resources"]) == 1


class TestMCPToolNode:
    """Test cases for MCPToolNode."""

    def test_node_initialization(self):
        """Test MCPToolNode initialization."""
        node = MCPToolNode(
            mcp_server="test_server",
            tool_name="test_tool",
            parameter_mapping={"input": "data"},
        )

        assert node.mcp_server == "test_server"
        assert node.tool_name == "test_tool"
        assert node.parameter_mapping == {"input": "data"}

    def test_set_mcp_integration(self):
        """Test setting MCP integration."""
        node = MCPToolNode("server", "tool")
        mcp = MCPIntegration("server")

        node.set_mcp_integration(mcp)
        assert node._mcp_integration == mcp

    @pytest.mark.asyncio
    async def test_execute_without_integration(self):
        """Test executing without MCP integration set."""
        from kailash.sdk_exceptions import NodeExecutionError

        node = MCPToolNode("server", "tool")

        with pytest.raises(NodeExecutionError, match="MCP integration not set"):
            await node.execute_async(data="test")

    @pytest.mark.asyncio
    async def test_execute_with_parameter_mapping(self):
        """Test executing with parameter mapping."""
        mcp = MCPIntegration("test")
        mcp.add_tool("process", lambda data, extra=None: f"processed: {data}")

        node = MCPToolNode("test", "process", parameter_mapping={"input": "data"})
        node.set_mcp_integration(mcp)

        result = await node.execute_async(input="test_data", extra="info")
        assert result == {"result": "processed: test_data"}

    @pytest.mark.asyncio
    async def test_execute_with_dict_input(self):
        """Test executing with dictionary input."""
        mcp = MCPIntegration("test")
        mcp.add_tool("echo", lambda **kwargs: kwargs)

        node = MCPToolNode("test", "echo")
        node.set_mcp_integration(mcp)

        result = await node.execute_async(key1="value1", key2="value2")
        assert result["key1"] == "value1"
        assert result["key2"] == "value2"

    @pytest.mark.asyncio
    async def test_execute_with_non_dict_input(self):
        """Test executing with non-dictionary input."""
        mcp = MCPIntegration("test")
        mcp.add_tool("process", lambda input: f"result: {input}")

        node = MCPToolNode("test", "process")
        node.set_mcp_integration(mcp)

        # For non-dict input, we need to pass it as a keyword argument
        result = await node.execute_async(input="simple_string")
        assert result == {"result": "result: simple_string"}


# Integration test
@pytest.mark.asyncio
async def test_gateway_with_mcp_integration():
    """Test complete gateway with MCP integration."""
    # Create MCP server
    mcp = MCPIntegration("analytics", "Analytics Tools")

    def analyze(data: list) -> dict:
        """Analyze data."""
        return {
            "count": len(data),
            "sum": sum(data) if all(isinstance(x, (int, float)) for x in data) else 0,
        }

    mcp.add_tool("analyze", analyze, "Analyze data list")

    # Create workflow using MCP tool
    workflow = Workflow("analysis_001", "Analysis Workflow")

    # Add MCP tool node
    tool_node = MCPToolNode("analytics", "analyze")
    workflow.add_node("analyze_data", tool_node)

    # Create gateway
    gateway = WorkflowAPIGateway()
    gateway.register_mcp_server("analytics", mcp)
    gateway.register_workflow("analysis", workflow)

    # Set MCP integration on the node
    for node_name, node in workflow._node_instances.items():
        if isinstance(node, MCPToolNode):
            node.set_mcp_integration(mcp)

    # Test the integration
    client = TestClient(gateway.app)

    # Check workflow info
    response = client.get("/analysis/workflow/info")
    assert response.status_code == 200

    # List workflows
    response = client.get("/workflows")
    assert response.status_code == 200
    data = response.json()
    assert "analysis" in data
