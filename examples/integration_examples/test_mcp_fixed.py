#!/usr/bin/env python3
"""
Test the fixed MCP ecosystem implementation
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


def test_imports():
    """Test that all imports work correctly"""
    print("Testing imports...")

    try:
        # Import the fixed implementation
        from mcp_ecosystem_fixed import MCPServerRegistry, SimpleMCPGateway

        # Import required Kailash components
        from kailash.api.gateway import WorkflowAPIGateway
        from kailash.nodes.code.python import PythonCodeNode
        from kailash.workflow import Workflow

        print("✓ All imports successful")
        return True

    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False


def test_gateway_creation():
    """Test creating the MCP gateway"""
    print("\nTesting gateway creation...")

    try:
        from mcp_ecosystem_fixed import SimpleMCPGateway

        # Create gateway
        gateway = SimpleMCPGateway()

        # Check attributes
        assert hasattr(gateway, "gateway")
        assert hasattr(gateway, "mcp_registry")
        assert hasattr(gateway, "workflows")

        # Check it's a WorkflowAPIGateway
        from kailash.api.gateway import WorkflowAPIGateway

        assert isinstance(gateway.gateway, WorkflowAPIGateway)

        print("✓ Gateway created successfully")
        return True

    except Exception as e:
        print(f"✗ Gateway creation error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_workflow_creation():
    """Test creating a workflow"""
    print("\nTesting workflow creation...")

    try:
        from kailash.nodes.code.python import PythonCodeNode
        from kailash.workflow import Workflow

        # Create workflow with required parameters
        workflow = Workflow(workflow_id="test_workflow", name="Test Workflow")

        # Add a simple node (PythonCodeNode requires name parameter)
        node = PythonCodeNode(name="test_node", code="result = {'test': True}")
        workflow.add_node("test_node", node)

        # Check workflow
        assert len(workflow.nodes) == 1
        assert "test_node" in workflow.nodes

        print("✓ Workflow created successfully")
        return True

    except Exception as e:
        print(f"✗ Workflow creation error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_mcp_registry():
    """Test MCP server registry"""
    print("\nTesting MCP registry...")

    try:
        import asyncio

        from mcp_ecosystem_fixed import MCPServerRegistry

        async def test_async():
            registry = MCPServerRegistry()

            # Register a mock server
            config = {"command": "echo", "args": ["test"], "transport": "stdio"}

            result = await registry.register_server("test-server", config)

            # Check registration
            assert "test-server" in registry.servers
            assert registry.servers["test-server"]["status"] == "connected"

            return True

        result = asyncio.run(test_async())
        if result:
            print("✓ MCP registry works")
        return result

    except Exception as e:
        print(f"✗ MCP registry error: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("Testing Fixed MCP Ecosystem Implementation")
    print("=" * 50)

    tests = [
        test_imports(),
        test_gateway_creation(),
        test_workflow_creation(),
        test_mcp_registry(),
    ]

    passed = sum(tests)
    total = len(tests)

    print("\n" + "=" * 50)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("✅ All tests passed! The fixed implementation works correctly.")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    exit(main())
