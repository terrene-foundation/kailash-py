"""EATP MCP Tool Guard -- trust-gated MCP tool execution.

Demonstrates using EATP as a gate before MCP tool calls. Every tool invocation
is verified against the agent's trust chain, and blocked if the agent lacks the
required capability.

Pattern:
    1. Map MCP tool names to EATP capabilities
    2. Before calling any MCP tool, VERIFY the agent's trust
    3. Use StrictEnforcer to block unauthorized tool access
    4. Record AUDIT anchors for every tool execution
    5. Use constraint-based access control for fine-grained rules

This example simulates an MCP tool server with EATP gating. In production,
the EATPMCPServer (eatp.mcp.server) provides this pattern natively via
the eatp_verify tool.

Run:
    python examples/integrations/mcp_tool_guard.py
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

from eatp import CapabilityRequest, TrustKeyManager, TrustOperations
from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import ActionResult, AuthorityType, CapabilityType, VerificationLevel
from eatp.crypto import generate_keypair
from eatp.enforce.shadow import ShadowEnforcer
from eatp.enforce.strict import EATPBlockedError, StrictEnforcer, Verdict
from eatp.store.memory import InMemoryTrustStore


class SimpleAuthorityRegistry:
    """Minimal in-memory authority registry for examples."""

    def __init__(self):
        self._authorities = {}

    async def initialize(self):
        pass

    def register(self, authority: OrganizationalAuthority):
        self._authorities[authority.id] = authority

    async def get_authority(self, authority_id: str, include_inactive: bool = False):
        authority = self._authorities.get(authority_id)
        if authority is None:
            raise KeyError(f"Authority not found: {authority_id}")
        return authority


# ---------------------------------------------------------------------------
# MCP Tool Registry with EATP Guard
# ---------------------------------------------------------------------------


@dataclass
class MCPToolDefinition:
    """Definition of an MCP tool with its required EATP capability."""

    name: str
    description: str
    required_capability: str
    parameters: Dict[str, str] = field(default_factory=dict)


class EATPToolGuard:
    """Guards MCP tool execution with EATP trust verification.

    Sits between the MCP tool call and the actual tool handler. Every call
    is verified, enforced, and audited.

    Usage in an MCP server:
        guard = EATPToolGuard(ops=trust_operations)
        guard.register_tool("read_file", "read_data", handler=read_file_handler)

        # On tools/call:
        result = await guard.call_tool(agent_id, tool_name, arguments)
    """

    def __init__(self, ops: TrustOperations, mode: str = "strict"):
        """Initialize the tool guard.

        Args:
            ops: EATP TrustOperations instance
            mode: Enforcement mode -- "strict" blocks, "shadow" observes
        """
        self._ops = ops
        self._tools: Dict[str, MCPToolDefinition] = {}
        self._handlers: Dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}
        self._enforcer = StrictEnforcer()
        self._shadow = ShadowEnforcer()
        self._mode = mode

    def register_tool(
        self,
        name: str,
        required_capability: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
        description: str = "",
        parameters: Optional[Dict[str, str]] = None,
    ) -> None:
        """Register an MCP tool with its EATP capability mapping."""
        self._tools[name] = MCPToolDefinition(
            name=name,
            description=description,
            required_capability=required_capability,
            parameters=parameters or {},
        )
        self._handlers[name] = handler

    async def call_tool(
        self,
        agent_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a tool call with EATP verification.

        Args:
            agent_id: The calling agent's ID
            tool_name: MCP tool name
            arguments: Tool call arguments

        Returns:
            Tool result with trust metadata

        Raises:
            EATPBlockedError: If the agent lacks the required capability (strict mode)
            KeyError: If the tool is not registered
        """
        if tool_name not in self._tools:
            raise KeyError(f"Unknown tool: {tool_name}")

        tool_def = self._tools[tool_name]
        handler = self._handlers[tool_name]

        # Step 1: VERIFY trust
        verify_result = await self._ops.verify(
            agent_id=agent_id,
            action=tool_def.required_capability,
            level=VerificationLevel.STANDARD,
        )

        # Step 2: Enforce or shadow
        if self._mode == "strict":
            verdict = self._enforcer.enforce(
                agent_id=agent_id,
                action=tool_def.required_capability,
                result=verify_result,
                metadata={"tool": tool_name, "arguments": arguments},
            )
        else:
            verdict = self._shadow.check(
                agent_id=agent_id,
                action=tool_def.required_capability,
                result=verify_result,
                metadata={"tool": tool_name},
            )

        # Step 3: Execute the tool handler
        tool_result = await handler(**arguments)

        # Step 4: AUDIT the execution
        anchor = await self._ops.audit(
            agent_id=agent_id,
            action=tool_def.required_capability,
            resource=f"mcp_tool:{tool_name}",
            result=ActionResult.SUCCESS,
            context_data={
                "tool": tool_name,
                "verdict": verdict.value,
                "arguments_keys": list(arguments.keys()),
            },
        )

        return {
            "tool": tool_name,
            "result": tool_result,
            "trust": {
                "verified": verify_result.valid,
                "verdict": verdict.value,
                "audit_anchor": anchor.id[:12],
            },
        }

    @property
    def shadow_report(self) -> str:
        """Get the shadow enforcement report (only meaningful in shadow mode)."""
        return self._shadow.report()

    @property
    def enforcement_records(self) -> int:
        """Get the count of enforcement records."""
        return len(self._enforcer.records) + len(self._shadow.records)


# ---------------------------------------------------------------------------
# Simulated MCP Tool Handlers
# ---------------------------------------------------------------------------


async def handle_read_file(path: str) -> Dict[str, Any]:
    """Simulated MCP tool: read a file."""
    return {"path": path, "content": f"<contents of {path}>", "size_bytes": 4096}


async def handle_write_file(path: str, content: str) -> Dict[str, Any]:
    """Simulated MCP tool: write a file."""
    return {"path": path, "bytes_written": len(content), "success": True}


async def handle_execute_query(query: str, database: str) -> Dict[str, Any]:
    """Simulated MCP tool: execute a database query."""
    return {"query": query, "database": database, "rows_returned": 42}


async def handle_send_notification(channel: str, message: str) -> Dict[str, Any]:
    """Simulated MCP tool: send a notification."""
    return {"channel": channel, "delivered": True, "message_length": len(message)}


async def handle_admin_reset(target: str) -> Dict[str, Any]:
    """Simulated MCP tool: admin system reset (high privilege)."""
    return {"target": target, "reset": True}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    # -- Setup EATP infrastructure -------------------------------------------
    store = InMemoryTrustStore()
    await store.initialize()

    key_mgr = TrustKeyManager()
    priv_key, pub_key = generate_keypair()
    key_mgr.register_key("key-org", priv_key)

    registry = SimpleAuthorityRegistry()
    registry.register(
        OrganizationalAuthority(
            id="org-platform",
            name="Platform Ops",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=pub_key,
            signing_key_id="key-org",
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.DELEGATE_TRUST,
            ],
        )
    )

    ops = TrustOperations(
        authority_registry=registry,
        key_manager=key_mgr,
        trust_store=store,
    )

    # -- Establish agents with different capability levels -------------------
    print("=== Setup: ESTABLISH agents with role-based capabilities ===")

    # Developer agent -- can read files, execute queries
    await ops.establish(
        agent_id="mcp-developer",
        authority_id="org-platform",
        capabilities=[
            CapabilityRequest(capability="read_file", capability_type=CapabilityType.ACCESS),
            CapabilityRequest(capability="write_file", capability_type=CapabilityType.ACTION),
            CapabilityRequest(capability="execute_query", capability_type=CapabilityType.ACTION),
        ],
        constraints=["audit_required"],
    )
    dev_caps = await ops.get_agent_capabilities("mcp-developer")
    print(f"  mcp-developer: {dev_caps}")

    # Viewer agent -- can only read
    await ops.establish(
        agent_id="mcp-viewer",
        authority_id="org-platform",
        capabilities=[
            CapabilityRequest(capability="read_file", capability_type=CapabilityType.ACCESS),
        ],
        constraints=["audit_required", "read_only"],
    )
    viewer_caps = await ops.get_agent_capabilities("mcp-viewer")
    print(f"  mcp-viewer: {viewer_caps}")

    # Admin agent -- full access
    await ops.establish(
        agent_id="mcp-admin",
        authority_id="org-platform",
        capabilities=[
            CapabilityRequest(capability="read_file", capability_type=CapabilityType.ACCESS),
            CapabilityRequest(capability="write_file", capability_type=CapabilityType.ACTION),
            CapabilityRequest(capability="execute_query", capability_type=CapabilityType.ACTION),
            CapabilityRequest(capability="send_notification", capability_type=CapabilityType.ACTION),
            CapabilityRequest(capability="admin_reset", capability_type=CapabilityType.ACTION),
        ],
        constraints=["audit_required"],
    )
    admin_caps = await ops.get_agent_capabilities("mcp-admin")
    print(f"  mcp-admin: {admin_caps}")

    # -- Create tool guard and register tools --------------------------------
    print("\n=== Register MCP Tools with EATP Guard ===")
    guard = EATPToolGuard(ops=ops, mode="strict")

    guard.register_tool(
        "read_file",
        "read_file",
        handle_read_file,
        description="Read file contents",
        parameters={"path": "string"},
    )
    guard.register_tool(
        "write_file",
        "write_file",
        handle_write_file,
        description="Write file contents",
        parameters={"path": "string", "content": "string"},
    )
    guard.register_tool(
        "execute_query",
        "execute_query",
        handle_execute_query,
        description="Execute database query",
        parameters={"query": "string", "database": "string"},
    )
    guard.register_tool(
        "send_notification",
        "send_notification",
        handle_send_notification,
        description="Send notification",
        parameters={"channel": "string", "message": "string"},
    )
    guard.register_tool(
        "admin_reset",
        "admin_reset",
        handle_admin_reset,
        description="Admin system reset",
        parameters={"target": "string"},
    )
    print(f"  Registered {len(guard._tools)} tools")

    # -- Scenario 1: Developer uses authorized tools -------------------------
    print("\n=== Scenario 1: Developer -- Authorized Tools ===")
    for tool_name, args in [
        ("read_file", {"path": "/src/main.py"}),
        ("write_file", {"path": "/src/config.py", "content": "debug = True"}),
        (
            "execute_query",
            {"query": "SELECT count(*) FROM users", "database": "app_db"},
        ),
    ]:
        result = await guard.call_tool("mcp-developer", tool_name, args)
        trust = result["trust"]
        print(f"  {tool_name}: verdict={trust['verdict']}, audit={trust['audit_anchor']}...")

    # -- Scenario 2: Developer blocked from admin tool -----------------------
    print("\n=== Scenario 2: Developer -- Blocked from Admin Tool ===")
    try:
        await guard.call_tool("mcp-developer", "admin_reset", {"target": "database"})
        print("  ERROR: Should have been blocked")
    except EATPBlockedError as e:
        print(f"  Correctly blocked: {e.reason}")

    # -- Scenario 3: Viewer blocked from write tools -------------------------
    print("\n=== Scenario 3: Viewer -- Read Only ===")
    # Viewer can read
    result = await guard.call_tool("mcp-viewer", "read_file", {"path": "/docs/readme.md"})
    print(f"  read_file: verdict={result['trust']['verdict']}")

    # Viewer cannot write
    try:
        await guard.call_tool("mcp-viewer", "write_file", {"path": "/tmp/out.txt", "content": "data"})
        print("  ERROR: Should have been blocked")
    except EATPBlockedError as e:
        print(f"  write_file blocked: {e.reason}")

    # Viewer cannot query
    try:
        await guard.call_tool(
            "mcp-viewer",
            "execute_query",
            {"query": "DROP TABLE users", "database": "prod"},
        )
        print("  ERROR: Should have been blocked")
    except EATPBlockedError as e:
        print(f"  execute_query blocked: {e.reason}")

    # -- Scenario 4: Admin uses all tools including admin_reset --------------
    print("\n=== Scenario 4: Admin -- Full Access ===")
    for tool_name, args in [
        ("read_file", {"path": "/etc/config"}),
        ("execute_query", {"query": "SELECT * FROM audit_log", "database": "ops_db"}),
        ("send_notification", {"channel": "#ops", "message": "System check passed"}),
        ("admin_reset", {"target": "cache_layer"}),
    ]:
        result = await guard.call_tool("mcp-admin", tool_name, args)
        trust = result["trust"]
        print(f"  {tool_name}: verdict={trust['verdict']}, audit={trust['audit_anchor']}...")

    # -- Scenario 5: Shadow mode for new tool rollout ------------------------
    print("\n=== Scenario 5: Shadow Mode for New Tool ===")
    shadow_guard = EATPToolGuard(ops=ops, mode="shadow")
    shadow_guard.register_tool(
        "read_file",
        "read_file",
        handle_read_file,
        description="Read file contents",
    )
    shadow_guard.register_tool(
        "admin_reset",
        "admin_reset",
        handle_admin_reset,
        description="Admin system reset",
    )

    # In shadow mode, even unauthorized calls proceed (but are logged)
    for agent_id in ["mcp-developer", "mcp-viewer"]:
        for tool_name, args in [
            ("read_file", {"path": "/src/main.py"}),
            ("admin_reset", {"target": "test_env"}),
        ]:
            result = await shadow_guard.call_tool(agent_id, tool_name, args)
            trust = result["trust"]
            print(f"  {agent_id} -> {tool_name}: verdict={trust['verdict']} (shadow)")

    print(f"\n{shadow_guard.shadow_report}")

    # -- Summary -------------------------------------------------------------
    print(f"\n=== Summary ===")
    print(f"  Total enforcement decisions: {guard.enforcement_records}")
    print("  EATP MCP Tool Guard ensures:")
    print("    1. Every tool call is verified against the agent's trust chain")
    print("    2. Unauthorized tools are blocked before execution")
    print("    3. Every execution is recorded in the audit trail")
    print("    4. Shadow mode allows safe rollout of new access policies")
    print("\nMCP tool guard integration completed.")


if __name__ == "__main__":
    asyncio.run(main())
