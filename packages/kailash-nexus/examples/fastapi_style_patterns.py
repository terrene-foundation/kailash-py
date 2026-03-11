#!/usr/bin/env python3
"""FastAPI-style Nexus usage patterns (v1.3.0).

Shows different ways to use the Nexus API:
- Zero-config instances
- Handler registration (recommended)
- Enterprise auth via NexusAuthPlugin
- Middleware, routers, plugins
- Preset system
- Multiple independent instances
"""

import os

from nexus import Nexus

from kailash.workflow.builder import WorkflowBuilder

# ---------------------------------------------------------------------------
# Pattern 1: Simple -- like FastAPI
# ---------------------------------------------------------------------------
app = Nexus()


# ---------------------------------------------------------------------------
# Pattern 2: Enterprise features via constructor + NexusAuthPlugin
# ---------------------------------------------------------------------------
enterprise_app = Nexus(
    api_port=8000,
    mcp_port=3001,
    enable_auth=True,
    enable_monitoring=True,
    rate_limit=100,
    auto_discovery=False,  # Prevents blocking with DataFlow
    cors_origins=["https://app.example.com"],
    cors_allow_credentials=False,
    cors_max_age=600,
)

# Auth is configured via NexusAuthPlugin -- NOT via enterprise_app.auth.*
# See configure_enterprise_auth() below.


# ---------------------------------------------------------------------------
# Pattern 3: Multiple independent instances (like FastAPI apps)
# ---------------------------------------------------------------------------
api_server = Nexus(api_port=8000)
mcp_server = Nexus(api_port=8001, mcp_port=3002)


def configure_workflows():
    """Register workflows and handlers on different instances."""

    # --- WorkflowBuilder registration (classic pattern) ---
    simple_workflow = WorkflowBuilder()
    simple_workflow.add_node(
        "PythonCodeNode",
        "process",
        {"code": "result = {'message': 'Hello from API server'}"},
    )
    # register() accepts WorkflowBuilder (auto-calls .build())
    api_server.register("api-workflow", simple_workflow)

    # --- Handler registration (recommended for v1.2.0+) ---
    # Direct async functions bypass PythonCodeNode sandbox restrictions.
    @mcp_server.handler("ai-process", description="AI-powered processor", tags=["ai"])
    async def ai_process(prompt: str, model: str = "gpt-4") -> dict:
        """Handler available on all channels (API, CLI, MCP)."""
        return {"processed": True, "model": model, "prompt": prompt}

    # Non-decorator alternative
    async def postprocess(data: str) -> dict:
        return {"postprocessed": True, "input": data}

    mcp_server.register_handler(
        "postprocess", postprocess, description="Post-processing step"
    )


def configure_enterprise_auth():
    """Configure enterprise auth via NexusAuthPlugin (v1.3.0).

    IMPORTANT: There is NO app.auth.strategy or app.auth.provider attribute.
    Authentication is configured entirely through the plugin system.
    """
    from nexus.auth import AuditConfig, JWTConfig, RateLimitConfig, TenantConfig
    from nexus.auth.plugin import NexusAuthPlugin

    # --- Basic auth (JWT + audit) ---
    # auth = NexusAuthPlugin.basic_auth(
    #     jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    # )
    # --- SaaS auth (JWT + RBAC + tenant isolation + audit) ---
    auth = NexusAuthPlugin.saas_app(
        jwt=JWTConfig(
            secret=os.environ.get("JWT_SECRET", "dev-secret-at-least-32-chars-long!"),
            algorithm="HS256",
            exempt_paths=["/health", "/docs"],  # Use exempt_paths, NOT exclude_paths
        ),
        rbac={
            "admin": ["*"],  # Full access
            "editor": ["read:*", "write:articles"],  # Wildcard + specific
            "viewer": ["read:*"],  # Read-only
        },
        tenant_isolation=TenantConfig(
            admin_role="super_admin",  # Use admin_role (singular), NOT admin_roles
        ),
        rbac_default_role="viewer",
    )

    # --- Enterprise auth (all features) ---
    # auth = NexusAuthPlugin.enterprise(
    #     jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    #     rbac={"admin": ["*"], "editor": ["read:*", "write:*"], "viewer": ["read:*"]},
    #     rate_limit=RateLimitConfig(requests_per_minute=100, burst_size=20),
    #     tenant_isolation=TenantConfig(),
    #     audit=AuditConfig(backend="logging"),
    # )

    enterprise_app.add_plugin(auth)


def configure_middleware_and_routers():
    """Show native middleware and router patterns (v1.3.0).

    These mirror FastAPI's add_middleware() and include_router() exactly.
    """

    # --- Custom middleware ---
    # enterprise_app.add_middleware(SomeMiddlewareClass, param="value")

    # --- Custom router ---
    # from fastapi import APIRouter
    # health_router = APIRouter(prefix="/custom", tags=["custom"])
    #
    # @health_router.get("/ping")
    # async def ping():
    #     return {"pong": True}
    #
    # enterprise_app.include_router(health_router)

    # --- Plugin protocol ---
    # Any class implementing NexusPluginProtocol can be added:
    # enterprise_app.add_plugin(my_plugin)
    pass


def startup_pattern():
    """Show typical startup pattern."""

    # Configure everything
    configure_workflows()
    configure_enterprise_auth()
    configure_middleware_and_routers()

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
    """Show how multiple instances can coexist with different auth levels."""
    from nexus.auth import JWTConfig
    from nexus.auth.plugin import NexusAuthPlugin

    # Development instance -- no auth, monitoring on
    dev_app = Nexus(api_port=9000, enable_monitoring=True)

    @dev_app.handler("dev-status", description="Development status check")
    async def dev_status() -> dict:
        return {"environment": "dev", "status": "running"}

    # Production instance -- full auth via plugin
    prod_app = Nexus(
        api_port=9080,
        enable_auth=True,
        enable_monitoring=True,
        rate_limit=1000,
        cors_origins=["https://prod.example.com"],
    )

    prod_auth = NexusAuthPlugin.basic_auth(
        jwt=JWTConfig(
            secret=os.environ.get("JWT_SECRET", "prod-secret-at-least-32-chars-long!"),
        ),
    )
    prod_app.add_plugin(prod_auth)

    @prod_app.handler("prod-status", description="Production status check")
    async def prod_status() -> dict:
        return {"environment": "prod", "status": "running"}

    # Testing instance -- auto_discovery=False for DataFlow integration
    test_app = Nexus(api_port=9090, auto_discovery=False)

    @test_app.handler("test-status", description="Test status check")
    async def test_status() -> dict:
        return {"environment": "test", "status": "running"}

    return dev_app, prod_app, test_app


def preset_pattern():
    """Show preset system for one-line middleware stacks (v1.3.0).

    Presets provide pre-configured middleware combinations.
    """

    # Lightweight preset
    # lightweight_app = Nexus(preset="lightweight")

    # SaaS preset (includes common SaaS middleware)
    # saas_app = Nexus(preset="saas", cors_origins=["https://app.example.com"])

    pass


if __name__ == "__main__":
    print("FastAPI-style Nexus Patterns Demo (v1.3.0)")
    print("=" * 50)

    # Show the main startup pattern
    api, mcp, enterprise = startup_pattern()

    print("\nMultiple instances pattern:")
    dev, prod, test = multiple_instances_pattern()

    print("\nRunning instances:")
    print(f"- API server:   port {api._api_port}")
    print(f"- MCP server:   port {mcp._api_port}")
    print(f"- Enterprise:   port {enterprise._api_port}")
    print(f"- Dev:          port {dev._api_port}")
    print(f"- Prod:         port {prod._api_port}")
    print(f"- Test:         port {test._api_port}")

    print("\nAll patterns work correctly!")

    # Clean shutdown
    for server in [api, mcp, enterprise, dev, prod, test]:
        server.stop()
