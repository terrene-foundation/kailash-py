#!/usr/bin/env python3
"""Basic usage example of Kailash Nexus v1.4.0.

Shows the FastAPI-style API with explicit instances, handler registration,
and enterprise auth via NexusAuthPlugin.
"""

import os

from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus


def main():
    """Example of FastAPI-style Nexus usage."""

    # --- Pattern 1: Zero-config (simplest) ---
    app = Nexus()

    # --- Pattern 2: Constructor options ---
    # app = Nexus(
    #     api_port=8000,
    #     mcp_port=3001,
    #     enable_auth=True,
    #     enable_monitoring=True,
    #     rate_limit=100,
    #     auto_discovery=False,        # Prevents blocking with DataFlow
    #     cors_origins=["http://localhost:3000"],
    # )

    # --- Pattern 3: Preset (one-line middleware stack) ---
    # app = Nexus(preset="saas", cors_origins=["https://app.example.com"])

    # --- Register a workflow (WorkflowBuilder) ---
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "greet",
        {
            "code": """
try:
    name = name
except NameError:
    name = 'World'
result = {'greeting': f'Hello, {name}!'}
"""
        },
    )

    # register() accepts both Workflow and WorkflowBuilder (auto-calls .build())
    app.register("greeter", workflow)

    # --- Handler pattern (recommended for v1.2.0+) ---
    # Direct async function as multi-channel workflow -- bypasses PythonCodeNode sandbox.
    @app.handler("echo", description="Echo a message back", tags=["utility"])
    async def echo(message: str, uppercase: bool = False) -> dict:
        """Echo handler available on API, CLI, and MCP."""
        text = message.upper() if uppercase else message
        return {"echo": text}

    # --- Enterprise auth via NexusAuthPlugin (v1.3.0) ---
    # There is NO app.auth.strategy attribute. Use the plugin system instead:
    #
    # from nexus.auth.plugin import NexusAuthPlugin
    # from nexus.auth import JWTConfig, TenantConfig, AuditConfig
    #
    # auth = NexusAuthPlugin.basic_auth(
    #     jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    # )
    # app.add_plugin(auth)

    # --- CORS configuration ---
    # Option A: Constructor (preferred)
    # app = Nexus(cors_origins=["http://localhost:3000"], cors_allow_credentials=True)
    #
    # Option B: After construction
    # app.configure_cors(allow_origins=["http://localhost:3000"])

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
    #     POST /workflows/greeter/execute  {"name": "Alice"}
    #     POST /workflows/echo/execute     {"message": "hi", "uppercase": true}
    # - CLI: nexus execute greeter
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
