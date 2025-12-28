#!/usr/bin/env python3
"""FastAPI-style Nexus usage patterns.

Shows different ways to use the new Nexus API similar to FastAPI patterns.
"""

from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus

# Pattern 1: Simple - like FastAPI
app = Nexus()

# Pattern 2: With enterprise features at construction
enterprise_app = Nexus(
    enable_auth=True,
    enable_monitoring=True,
    api_port=8000,
    mcp_port=3001,
    rate_limit=100,
    auto_discovery=True,
)

# Pattern 3: Multiple independent instances (like FastAPI apps)
api_server = Nexus(api_port=8000)
mcp_server = Nexus(api_port=8001, mcp_port=3002)


def configure_workflows():
    """Configure workflows on different instances."""

    # Simple workflow for API server
    simple_workflow = WorkflowBuilder()
    simple_workflow.add_node(
        "PythonCodeNode",
        "process",
        {"code": "result = {'message': 'Hello from API server'}"},
    )
    api_server.register("api-workflow", simple_workflow)

    # Complex workflow for MCP server
    complex_workflow = WorkflowBuilder()
    complex_workflow.add_node(
        "LLMAgentNode",
        "agent",
        {"model": "gpt-4", "prompt": "Process this data intelligently"},
    )
    complex_workflow.add_node(
        "PythonCodeNode",
        "postprocess",
        {"code": "result = {'processed': True, 'data': input_data}"},
    )
    mcp_server.register("ai-workflow", complex_workflow)


def configure_enterprise_features():
    """Configure enterprise features via attributes."""

    # Fine-tune authentication
    enterprise_app.auth.strategy = "rbac"

    # Configure monitoring
    enterprise_app.monitoring.interval = 30

    # API configuration
    enterprise_app.api.cors_enabled = True
    enterprise_app.api.docs_enabled = True

    # MCP configuration
    enterprise_app.mcp.cors_enabled = True


def startup_pattern():
    """Show typical startup pattern."""

    # Configure everything
    configure_workflows()
    configure_enterprise_features()

    # Start servers
    print("Starting API server on port 8000...")
    api_server.start()

    print("Starting MCP server on port 8001...")
    mcp_server.start()

    print("Starting enterprise app...")
    enterprise_app.start()

    # Health checks
    for name, server in [
        ("API", api_server),
        ("MCP", mcp_server),
        ("Enterprise", enterprise_app),
    ]:
        health = server.health_check()
        print(f"{name} server: {health['status']}")

    return api_server, mcp_server, enterprise_app


def multiple_instances_pattern():
    """Show how multiple instances can coexist."""

    # Development instance
    dev_app = Nexus(api_port=8000, enable_monitoring=True)

    # Production instance
    prod_app = Nexus(
        api_port=8080, enable_auth=True, enable_monitoring=True, rate_limit=1000
    )

    # Testing instance
    test_app = Nexus(api_port=9000, auto_discovery=False)

    # Each has independent configuration
    dev_app.monitoring.interval = 5  # Frequent monitoring for dev
    prod_app.monitoring.interval = 60  # Less frequent for prod
    prod_app.auth.strategy = "oauth2"

    # Independent workflows
    for env, app in [("dev", dev_app), ("prod", prod_app), ("test", test_app)]:
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "env",
            {"code": f"result = {{'environment': '{env}', 'status': 'running'}}"},
        )
        app.register(f"{env}-status", workflow)

    return dev_app, prod_app, test_app


if __name__ == "__main__":
    print("FastAPI-style Nexus Patterns Demo")
    print("=" * 40)

    # Show the main startup pattern
    api, mcp, enterprise = startup_pattern()

    print("\nMultiple instances pattern:")
    dev, prod, test = multiple_instances_pattern()

    print("\nRunning instances:")
    print(f"- API server: {api._api_port}")
    print(f"- MCP server: {mcp._api_port}")
    print(f"- Enterprise: {enterprise._api_port}")
    print(f"- Dev: {dev._api_port}")
    print(f"- Prod: {prod._api_port}")
    print(f"- Test: {test._api_port}")

    print("\n✅ All patterns work correctly!")

    # Clean shutdown
    for server in [api, mcp, enterprise, dev, prod, test]:
        server.stop()
