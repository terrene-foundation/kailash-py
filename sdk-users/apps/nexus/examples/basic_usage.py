#!/usr/bin/env python3
"""Basic usage example of Kailash Nexus.

Shows the new FastAPI-style API with explicit instances and enterprise options.
"""

from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus


def main():
    """Example of FastAPI-style Nexus usage."""

    # Simple case - like FastAPI
    app = Nexus()

    # Or with enterprise features at construction
    # app = Nexus(
    #     enable_auth=True,
    #     enable_monitoring=True,
    #     api_port=8000,
    #     mcp_port=3001,
    #     rate_limit=100
    # )

    # Create a simple workflow
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "greet",
        {
            "code": """
name = parameters.get('name', 'World')
result = {'greeting': f'Hello, {name}!'}
"""
        },
    )

    # Register the workflow
    app.register("greeter", workflow)

    # Fine-tune configuration via attributes
    app.auth.strategy = "rbac"
    app.monitoring.interval = 30
    app.api.cors_enabled = True

    # Start the platform (API, CLI, MCP all available)
    print("Starting Nexus...")
    app.start()

    # Check health
    health = app.health_check()
    print(f"Nexus status: {health['status']}")
    print(
        f"Available workflows: {list(health['workflows'].keys()) if 'workflows' in health else 'None'}"
    )

    # The platform is now running and accessible via:
    # - API: http://localhost:8000
    # - CLI: nexus-cli
    # - MCP: localhost:3001

    print("Press Ctrl+C to stop...")
    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Nexus...")
        app.stop()
        print("Nexus stopped.")


if __name__ == "__main__":
    main()
