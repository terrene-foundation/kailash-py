# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for EATP MCP Server.

Tests the EATPMCPServer JSON-RPC protocol, tools, and resources using
real infrastructure (InMemoryTrustStore, TrustOperations, AppendOnlyAuditStore)
with NO mocking.

Covers:
- JSON-RPC protocol flow (initialize -> notifications/initialized -> tools/list -> tools/call)
- All 5 tools: eatp_verify, eatp_status, eatp_audit_query, eatp_delegate, eatp_revoke
- Tool error handling (missing agents, invalid params)
- All 4 resources: eatp://authorities, eatp://agents/{id}, eatp://chains/{authority_id},
  eatp://constraints/{agent_id}
- Resource error handling (nonexistent resources)
- Full workflow: initialize -> establish -> verify -> delegate -> audit query
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from kailash.trust.audit_store import AppendOnlyAuditStore
from kailash.trust.authority import AuthorityPermission, OrganizationalAuthority
from kailash.trust.chain import (
    ActionResult,
    AuditAnchor,
    AuthorityType,
    CapabilityType,
    VerificationLevel,
)
from kailash.trust.signing.crypto import generate_keypair
from kailash.trust.enforce.strict import HeldBehavior, StrictEnforcer
from kailash.trust.mcp.server import EATPMCPServer
from kailash.trust.operations import CapabilityRequest, TrustKeyManager, TrustOperations
from kailash.trust.posture.postures import PostureStateMachine
from kailash.trust.chain_store.memory import InMemoryTrustStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Real Authority Registry (NOT a mock)
# ---------------------------------------------------------------------------


class SimpleAuthorityRegistry:
    """
    A real in-memory authority registry implementing AuthorityRegistryProtocol.

    This is NOT a mock -- it stores and retrieves real OrganizationalAuthority
    objects in memory, fully implementing the protocol contract.
    """

    def __init__(self) -> None:
        self._authorities: Dict[str, OrganizationalAuthority] = {}

    async def initialize(self) -> None:
        """Initialize the registry (no-op for in-memory)."""
        pass

    def register(self, authority: OrganizationalAuthority) -> None:
        """Register an authority in the registry."""
        self._authorities[authority.id] = authority

    async def get_authority(
        self,
        authority_id: str,
        include_inactive: bool = False,
    ) -> OrganizationalAuthority:
        """Retrieve an authority by ID."""
        authority = self._authorities.get(authority_id)
        if authority is None:
            from kailash.trust.exceptions import AuthorityNotFoundError

            raise AuthorityNotFoundError(authority_id)
        if not authority.is_active and not include_inactive:
            from kailash.trust.exceptions import AuthorityInactiveError

            raise AuthorityInactiveError(authority_id)
        return authority

    async def update_authority(self, authority: OrganizationalAuthority) -> None:
        """Persist changes to an authority record."""
        self._authorities[authority.id] = authority


# ---------------------------------------------------------------------------
# JSON-RPC Helpers
# ---------------------------------------------------------------------------


def _make_request(method: str, params: Dict[str, Any], msg_id: int = 1) -> str:
    """Build a JSON-RPC request string."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params,
        }
    )


def _make_notification(method: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Build a JSON-RPC notification string (no id)."""
    msg: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if params is not None:
        msg["params"] = params
    return json.dumps(msg)


def _parse_response(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse a JSON-RPC response string."""
    if raw is None:
        return None
    return json.loads(raw)


def _get_tool_result_data(response: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and parse the tool result data from a tools/call response."""
    result = response["result"]
    content = result["content"]
    assert len(content) > 0, "tools/call response must have at least one content entry"
    text = content[0]["text"]
    return json.loads(text)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 keypair for tests."""
    private_key, public_key = generate_keypair()
    return private_key, public_key


@pytest.fixture
def authority(keypair):
    """Create a real OrganizationalAuthority with valid keys."""
    _, public_key = keypair
    return OrganizationalAuthority(
        id="org-test",
        name="Test Organization",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="test-key-001",
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.DELEGATE_TRUST,
            AuthorityPermission.GRANT_CAPABILITIES,
        ],
    )


@pytest.fixture
def registry(authority):
    """Create a real authority registry with the test authority registered."""
    reg = SimpleAuthorityRegistry()
    reg.register(authority)
    return reg


@pytest.fixture
def key_manager(keypair):
    """Create a TrustKeyManager with the test private key registered."""
    private_key, _ = keypair
    km = TrustKeyManager()
    km.register_key("test-key-001", private_key)
    return km


@pytest.fixture
def trust_store():
    """Create a real InMemoryTrustStore."""
    return InMemoryTrustStore()


@pytest.fixture
def audit_store():
    """Create a real AppendOnlyAuditStore."""
    return AppendOnlyAuditStore()


@pytest.fixture
def trust_ops(registry, key_manager, trust_store):
    """Create a real TrustOperations instance."""
    return TrustOperations(
        authority_registry=registry,
        key_manager=key_manager,
        trust_store=trust_store,
    )


@pytest.fixture
def posture_machine():
    """Create a real PostureStateMachine."""
    return PostureStateMachine(require_upgrade_approval=False)


@pytest.fixture
def enforcer():
    """Create a real StrictEnforcer."""
    return StrictEnforcer(on_held=HeldBehavior.RAISE, flag_threshold=1)


@pytest.fixture
def server(trust_store, trust_ops, audit_store, posture_machine, enforcer):
    """Create an EATPMCPServer with all real dependencies."""
    return EATPMCPServer(
        trust_store=trust_store,
        trust_ops=trust_ops,
        audit_store=audit_store,
        posture_machine=posture_machine,
        enforcer=enforcer,
    )


@pytest.fixture
def server_no_ops(trust_store, audit_store, posture_machine, enforcer):
    """Create an EATPMCPServer without TrustOperations (lightweight mode)."""
    return EATPMCPServer(
        trust_store=trust_store,
        trust_ops=None,
        audit_store=audit_store,
        posture_machine=posture_machine,
        enforcer=enforcer,
    )


async def _initialize_server(server: EATPMCPServer) -> Dict[str, Any]:
    """Helper: send initialize request and return parsed response."""
    request = _make_request(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    )
    raw_response = await server.handle_message(request)
    assert raw_response is not None, "initialize must return a response"
    return _parse_response(raw_response)


async def _establish_agent(
    trust_ops: TrustOperations,
    agent_id: str,
    capabilities: List[str],
    authority_id: str = "org-test",
    constraints: Optional[List[str]] = None,
) -> None:
    """Helper: establish an agent with given capabilities using real TrustOperations."""
    await trust_ops.initialize()
    cap_requests = [
        CapabilityRequest(
            capability=cap,
            capability_type=CapabilityType.ACTION,
        )
        for cap in capabilities
    ]
    await trust_ops.establish(
        agent_id=agent_id,
        authority_id=authority_id,
        capabilities=cap_requests,
        constraints=constraints,
    )


# ===========================================================================
# 1. Protocol Tests
# ===========================================================================


class TestProtocol:
    """Test the JSON-RPC protocol flow."""

    async def test_initialize_returns_capabilities(self, server):
        """initialize must return protocolVersion, capabilities, and serverInfo."""
        response = await _initialize_server(server)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        result = response["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert "tools" in result["capabilities"]
        assert "resources" in result["capabilities"]
        assert result["serverInfo"]["name"] == "eatp-mcp-server"
        assert "version" in result["serverInfo"]

    async def test_initialized_notification_returns_none(self, server):
        """notifications/initialized is a notification (no id) and returns None."""
        notification = _make_notification("notifications/initialized")
        raw_response = await server.handle_message(notification)
        assert raw_response is None, "Notifications must not produce a response"

    async def test_tools_list_returns_all_tools(self, server):
        """tools/list must return all 5 tool definitions."""
        request = _make_request("tools/list", {})
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        assert response is not None
        tools = response["result"]["tools"]
        tool_names = {t["name"] for t in tools}

        expected_tools = {
            "eatp_verify",
            "eatp_status",
            "eatp_audit_query",
            "eatp_delegate",
            "eatp_revoke",
        }
        assert tool_names == expected_tools, f"Expected tools {expected_tools}, got {tool_names}"

    async def test_tools_list_has_input_schemas(self, server):
        """Each tool definition must include an inputSchema with required fields."""
        request = _make_request("tools/list", {})
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        tools = response["result"]["tools"]
        for tool in tools:
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert "description" in tool, f"Tool {tool['name']} missing 'description'"
            assert "inputSchema" in tool, f"Tool {tool['name']} missing 'inputSchema'"
            schema = tool["inputSchema"]
            assert schema["type"] == "object", f"Tool {tool['name']} inputSchema type must be 'object'"
            assert "properties" in schema, f"Tool {tool['name']} inputSchema missing 'properties'"

    async def test_resources_templates_list(self, server):
        """resources/templates/list must return all 4 resource templates."""
        request = _make_request("resources/templates/list", {})
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        assert response is not None
        templates = response["result"]["resourceTemplates"]
        assert len(templates) == 4

        uri_templates = {t["uriTemplate"] for t in templates}
        expected_templates = {
            "eatp://authorities",
            "eatp://agents/{id}",
            "eatp://chains/{authority_id}",
            "eatp://constraints/{agent_id}",
        }
        assert uri_templates == expected_templates, f"Expected templates {expected_templates}, got {uri_templates}"

    async def test_ping_returns_empty_result(self, server):
        """ping must return an empty result object."""
        request = _make_request("ping", {})
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        assert response is not None
        assert response["result"] == {}

    async def test_unknown_method_returns_error(self, server):
        """Unknown method must return a JSON-RPC method-not-found error."""
        request = _make_request("nonexistent/method", {})
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == -32601  # Method not found

    async def test_invalid_json_returns_parse_error(self, server):
        """Invalid JSON must return a parse error."""
        raw_response = await server.handle_message("not valid json {{{")
        response = _parse_response(raw_response)

        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == -32700  # Parse error

    async def test_missing_method_returns_invalid_request(self, server):
        """Request without method field must return invalid request error."""
        request = json.dumps({"jsonrpc": "2.0", "id": 1})
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == -32600  # Invalid request

    async def test_non_object_request_returns_error(self, server):
        """Request that is not a JSON object must return an error."""
        raw_response = await server.handle_message('"just a string"')
        response = _parse_response(raw_response)

        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == -32600  # Invalid request

    async def test_full_protocol_flow(self, server, trust_ops):
        """Test complete protocol flow: initialize -> notification -> tools/list -> tools/call."""
        # Step 1: Initialize
        response = await _initialize_server(server)
        assert response["result"]["protocolVersion"] == "2024-11-05"

        # Step 2: Send initialized notification
        notification = _make_notification("notifications/initialized")
        result = await server.handle_message(notification)
        assert result is None

        # Step 3: List tools
        request = _make_request("tools/list", {}, msg_id=2)
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        assert len(response["result"]["tools"]) == 5

        # Step 4: Establish an agent and call eatp_verify
        await _establish_agent(trust_ops, "agent-protocol-test", ["read_data"])

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_verify",
                "arguments": {"agent_id": "agent-protocol-test", "action": "read_data"},
            },
            msg_id=3,
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert data["valid"] is True
        assert data["verdict"] == "auto_approved"


# ===========================================================================
# 2. Tool Tests (valid inputs)
# ===========================================================================


class TestToolsValid:
    """Test each of the 5 tools with valid inputs."""

    async def test_eatp_verify_authorized_action(self, server, trust_ops):
        """eatp_verify returns auto_approved for an authorized action."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "agent-v1", ["analyze_data", "read_reports"])

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_verify",
                "arguments": {"agent_id": "agent-v1", "action": "analyze_data"},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert data["verdict"] == "auto_approved"
        assert data["valid"] is True
        assert data["details"]["level"] == "standard"
        assert data["details"]["capability_used"] is not None

    async def test_eatp_verify_unauthorized_action(self, server, trust_ops):
        """eatp_verify returns blocked for an action the agent lacks."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "agent-v2", ["read_data"])

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_verify",
                "arguments": {"agent_id": "agent-v2", "action": "delete_everything"},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert data["verdict"] == "blocked"
        assert data["valid"] is False

    async def test_eatp_verify_with_resource(self, server, trust_ops):
        """eatp_verify accepts optional resource parameter."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "agent-v3", ["read_data"])

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_verify",
                "arguments": {
                    "agent_id": "agent-v3",
                    "action": "read_data",
                    "resource": "database://finance",
                },
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert data["valid"] is True
        assert data["verdict"] == "auto_approved"

    async def test_eatp_status_returns_agent_state(self, server, trust_ops):
        """eatp_status returns trust score, posture, and capabilities."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "agent-s1", ["analyze_data", "generate_report"])

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_status",
                "arguments": {"agent_id": "agent-s1"},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert data["agent_id"] == "agent-s1"
        assert "trust_score" in data
        assert "posture" in data
        assert "capabilities" in data
        assert "analyze_data" in data["capabilities"]
        assert "generate_report" in data["capabilities"]
        assert data["chain_expired"] is False
        assert "active_delegations" in data
        assert "constraints_summary" in data

    async def test_eatp_audit_query_empty_store(self, server):
        """eatp_audit_query returns empty results when no audit records exist."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_audit_query",
                "arguments": {},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert data["records"] == []
        assert data["total_returned"] == 0

    async def test_eatp_audit_query_with_records(self, server, audit_store):
        """eatp_audit_query returns records after appending audit anchors."""
        await _initialize_server(server)

        # Append real audit anchors
        anchor1 = AuditAnchor(
            id="audit-001",
            agent_id="agent-aq1",
            action="read_data",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="hash-abc123",
            result=ActionResult.SUCCESS,
            signature="sig-placeholder",
        )
        anchor2 = AuditAnchor(
            id="audit-002",
            agent_id="agent-aq1",
            action="write_data",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="hash-def456",
            result=ActionResult.SUCCESS,
            signature="sig-placeholder",
        )
        await audit_store.append(anchor1)
        await audit_store.append(anchor2)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_audit_query",
                "arguments": {"agent_id": "agent-aq1"},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert data["total_returned"] == 2
        assert len(data["records"]) == 2
        assert data["records"][0]["anchor"]["agent_id"] == "agent-aq1"
        assert data["records"][0]["anchor"]["action"] == "read_data"

    async def test_eatp_audit_query_with_action_filter(self, server, audit_store):
        """eatp_audit_query filters by action when specified."""
        await _initialize_server(server)

        anchor1 = AuditAnchor(
            id="audit-f1",
            agent_id="agent-filter",
            action="read_data",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="hash-1",
            result=ActionResult.SUCCESS,
            signature="sig",
        )
        anchor2 = AuditAnchor(
            id="audit-f2",
            agent_id="agent-filter",
            action="write_data",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="hash-2",
            result=ActionResult.SUCCESS,
            signature="sig",
        )
        await audit_store.append(anchor1)
        await audit_store.append(anchor2)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_audit_query",
                "arguments": {"agent_id": "agent-filter", "action": "write_data"},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert data["total_returned"] == 1
        assert data["records"][0]["anchor"]["action"] == "write_data"

    async def test_eatp_audit_query_with_limit(self, server, audit_store):
        """eatp_audit_query respects the limit parameter."""
        await _initialize_server(server)

        for i in range(5):
            anchor = AuditAnchor(
                id=f"audit-lim-{i}",
                agent_id="agent-limit",
                action="action",
                timestamp=datetime.now(timezone.utc),
                trust_chain_hash=f"hash-{i}",
                result=ActionResult.SUCCESS,
                signature="sig",
            )
            await audit_store.append(anchor)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_audit_query",
                "arguments": {"agent_id": "agent-limit", "limit": 2},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert data["total_returned"] == 2

    async def test_eatp_delegate_creates_delegation(self, server, trust_ops):
        """eatp_delegate creates a real delegation between two agents."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "agent-d-from", ["analyze_data", "read_data"])
        await _establish_agent(trust_ops, "agent-d-to", ["basic_read"])

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "from_agent": "agent-d-from",
                    "to_agent": "agent-d-to",
                    "capabilities": ["analyze_data"],
                },
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        assert "isError" not in response["result"] or response["result"].get("isError") is not True

        data = _get_tool_result_data(response)

        assert "delegation_id" in data
        assert data["from_agent"] == "agent-d-from"
        assert data["to_agent"] == "agent-d-to"
        assert "analyze_data" in data["capabilities_delegated"]
        assert "delegated_at" in data

    async def test_eatp_delegate_with_constraints(self, server, trust_ops):
        """eatp_delegate passes constraints to the delegation."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "agent-dc-from", ["read_data"])
        await _establish_agent(trust_ops, "agent-dc-to", ["basic"])

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "from_agent": "agent-dc-from",
                    "to_agent": "agent-dc-to",
                    "capabilities": ["read_data"],
                    "constraints": {"max_records": 100},
                },
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert "delegation_id" in data

    async def test_eatp_revoke_delegation(self, server, trust_ops):
        """eatp_revoke revokes an existing delegation."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "agent-r-from", ["read_data"])
        await _establish_agent(trust_ops, "agent-r-to", ["basic"])

        # First delegate
        delegate_request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "from_agent": "agent-r-from",
                    "to_agent": "agent-r-to",
                    "capabilities": ["read_data"],
                },
            },
        )
        raw_response = await server.handle_message(delegate_request)
        delegate_response = _parse_response(raw_response)
        delegate_data = _get_tool_result_data(delegate_response)
        delegation_id = delegate_data["delegation_id"]

        # Then revoke
        revoke_request = _make_request(
            "tools/call",
            {
                "name": "eatp_revoke",
                "arguments": {
                    "delegation_id": delegation_id,
                },
            },
        )
        raw_response = await server.handle_message(revoke_request)
        revoke_response = _parse_response(raw_response)
        revoke_data = _get_tool_result_data(revoke_response)

        assert revoke_data["revoked"] is True
        assert revoke_data["delegation_id"] == delegation_id


# ===========================================================================
# 3. Tool Error Tests
# ===========================================================================


class TestToolErrors:
    """Test tools with invalid or error-producing inputs."""

    async def test_eatp_verify_missing_agent_id(self, server):
        """eatp_verify returns error when agent_id is missing."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_verify",
                "arguments": {"action": "read_data"},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert "error" in data
        assert "agent_id" in data["error"]

    async def test_eatp_verify_missing_action(self, server):
        """eatp_verify returns error when action is missing."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_verify",
                "arguments": {"agent_id": "some-agent"},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert "error" in data
        assert "action" in data["error"]

    async def test_eatp_verify_nonexistent_agent(self, server):
        """eatp_verify returns blocked for a nonexistent agent."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_verify",
                "arguments": {"agent_id": "nonexistent-agent", "action": "read_data"},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert data["valid"] is False
        assert data["verdict"] == "blocked"

    async def test_eatp_status_missing_agent_id(self, server):
        """eatp_status returns error when agent_id is missing."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_status",
                "arguments": {},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert "error" in data
        assert "agent_id" in data["error"]

    async def test_eatp_status_nonexistent_agent(self, server):
        """eatp_status returns error for a nonexistent agent."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_status",
                "arguments": {"agent_id": "ghost-agent"},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert "error" in data
        assert "ghost-agent" in data["error"]

    async def test_eatp_delegate_missing_from_agent(self, server):
        """eatp_delegate returns error when from_agent is missing."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "to_agent": "agent-b",
                    "capabilities": ["read_data"],
                },
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert "error" in data
        assert "from_agent" in data["error"]

    async def test_eatp_delegate_missing_to_agent(self, server):
        """eatp_delegate returns error when to_agent is missing."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "from_agent": "agent-a",
                    "capabilities": ["read_data"],
                },
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert "error" in data
        assert "to_agent" in data["error"]

    async def test_eatp_delegate_missing_capabilities(self, server):
        """eatp_delegate returns error when capabilities is missing."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "from_agent": "agent-a",
                    "to_agent": "agent-b",
                },
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert "error" in data
        assert "capabilities" in data["error"]

    async def test_eatp_delegate_nonexistent_delegator(self, server):
        """eatp_delegate returns error when delegator agent does not exist."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "from_agent": "nonexistent-delegator",
                    "to_agent": "nonexistent-delegatee",
                    "capabilities": ["read_data"],
                },
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert "error" in data

    async def test_eatp_delegate_no_ops_returns_error(self, server_no_ops):
        """eatp_delegate without TrustOperations returns descriptive error."""
        await _initialize_server(server_no_ops)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "from_agent": "a",
                    "to_agent": "b",
                    "capabilities": ["read"],
                },
            },
        )
        raw_response = await server_no_ops.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert "error" in data
        assert "TrustOperations" in data["error"]

    async def test_eatp_revoke_missing_delegation_id(self, server):
        """eatp_revoke returns error when delegation_id is missing."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_revoke",
                "arguments": {},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert "error" in data
        assert "delegation_id" in data["error"]

    async def test_eatp_revoke_nonexistent_delegation(self, server):
        """eatp_revoke returns error for nonexistent delegation ID."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_revoke",
                "arguments": {"delegation_id": "del-nonexistent-999"},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert "error" in data
        assert "del-nonexistent-999" in data["error"]

    async def test_eatp_revoke_no_ops_returns_error(self, server_no_ops):
        """eatp_revoke without TrustOperations returns descriptive error."""
        await _initialize_server(server_no_ops)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_revoke",
                "arguments": {"delegation_id": "del-123"},
            },
        )
        raw_response = await server_no_ops.handle_message(request)
        response = _parse_response(raw_response)
        data = _get_tool_result_data(response)

        assert "error" in data
        assert "TrustOperations" in data["error"]

    async def test_unknown_tool_returns_error(self, server):
        """tools/call with an unknown tool name returns isError response."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "nonexistent_tool",
                "arguments": {},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        result = response["result"]
        assert result["isError"] is True
        error_text = json.loads(result["content"][0]["text"])
        assert "error" in error_text

    async def test_tools_call_missing_tool_name(self, server):
        """tools/call without name raises ValueError -> internal error."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "arguments": {"agent_id": "a"},
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        # Should return an error (internal error because of ValueError)
        assert "error" in response
        assert response["error"]["code"] == -32603  # Internal error

    async def test_tools_call_invalid_arguments_type(self, server):
        """tools/call with arguments not a dict returns isError response."""
        await _initialize_server(server)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_verify",
                "arguments": "not-a-dict",
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        result = response["result"]
        assert result["isError"] is True


# ===========================================================================
# 4. Resource Tests (valid inputs)
# ===========================================================================


class TestResourcesValid:
    """Test reading each of the 4 resources with valid data."""

    async def test_resource_authorities_empty(self, server):
        """eatp://authorities returns empty list when no chains exist."""
        await _initialize_server(server)

        request = _make_request(
            "resources/read",
            {
                "uri": "eatp://authorities",
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        contents = response["result"]["contents"]
        assert len(contents) == 1
        assert contents[0]["uri"] == "eatp://authorities"
        assert contents[0]["mimeType"] == "application/json"

        data = json.loads(contents[0]["text"])
        assert data["total"] == 0
        assert data["authorities"] == []

    async def test_resource_authorities_with_chains(self, server, trust_ops):
        """eatp://authorities returns authorities referenced by stored chains."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "agent-res-auth", ["read_data"])

        request = _make_request(
            "resources/read",
            {
                "uri": "eatp://authorities",
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        data = json.loads(response["result"]["contents"][0]["text"])
        assert data["total"] >= 1

        authority_ids = [a["authority_id"] for a in data["authorities"]]
        assert "org-test" in authority_ids

    async def test_resource_agent_details(self, server, trust_ops):
        """eatp://agents/{id} returns comprehensive agent details."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "agent-res-det", ["analyze_data", "read_reports"])

        request = _make_request(
            "resources/read",
            {
                "uri": "eatp://agents/agent-res-det",
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        contents = response["result"]["contents"]
        assert contents[0]["uri"] == "eatp://agents/agent-res-det"

        data = json.loads(contents[0]["text"])
        assert data["agent_id"] == "agent-res-det"
        assert data["authority_id"] == "org-test"
        assert "trust_posture" in data
        assert "trust_score" in data
        assert "capabilities" in data
        assert data["chain_expired"] is False
        assert "created_at" in data

        # Check capabilities are present
        cap_names = [c["capability"] for c in data["capabilities"]]
        assert "analyze_data" in cap_names
        assert "read_reports" in cap_names

    async def test_resource_chains_for_authority(self, server, trust_ops):
        """eatp://chains/{authority_id} returns delegation chain tree."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "agent-res-ch1", ["read_data"])
        await _establish_agent(trust_ops, "agent-res-ch2", ["write_data"])

        request = _make_request(
            "resources/read",
            {
                "uri": "eatp://chains/org-test",
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        data = json.loads(response["result"]["contents"][0]["text"])
        assert data["authority_id"] == "org-test"
        assert data["total_agents"] >= 2
        assert "tree" in data
        assert len(data["tree"]) >= 2

    async def test_resource_constraints_for_agent(self, server, trust_ops):
        """eatp://constraints/{agent_id} returns constraint envelope."""
        await _initialize_server(server)
        await _establish_agent(
            trust_ops,
            "agent-res-con",
            ["read_data"],
            constraints=["audit_required"],
        )

        request = _make_request(
            "resources/read",
            {
                "uri": "eatp://constraints/agent-res-con",
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        data = json.loads(response["result"]["contents"][0]["text"])
        assert data["agent_id"] == "agent-res-con"
        assert "constraints" in data
        assert "total" in data
        assert "envelope_id" in data
        assert "constraint_hash" in data
        assert "capability_constraints" in data

    async def test_resources_list_enumerates_available(self, server, trust_ops):
        """resources/list returns concrete resource URIs for existing agents."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "agent-rl1", ["read_data"])

        request = _make_request("resources/list", {})
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        resources = response["result"]["resources"]
        uris = {r["uri"] for r in resources}

        # Must include at least these URIs
        assert "eatp://authorities" in uris
        assert "eatp://agents/agent-rl1" in uris
        assert "eatp://constraints/agent-rl1" in uris
        assert "eatp://chains/org-test" in uris


# ===========================================================================
# 5. Resource Error Tests
# ===========================================================================


class TestResourceErrors:
    """Test resource reads with invalid or nonexistent URIs."""

    async def test_resource_agent_nonexistent(self, server):
        """eatp://agents/{id} for a nonexistent agent returns error content."""
        await _initialize_server(server)

        request = _make_request(
            "resources/read",
            {
                "uri": "eatp://agents/nonexistent-agent-999",
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        contents = response["result"]["contents"]
        data = json.loads(contents[0]["text"])
        assert "error" in data

    async def test_resource_constraints_nonexistent_agent(self, server):
        """eatp://constraints/{agent_id} for nonexistent agent returns error content."""
        await _initialize_server(server)

        request = _make_request(
            "resources/read",
            {
                "uri": "eatp://constraints/ghost-agent-xyz",
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        contents = response["result"]["contents"]
        data = json.loads(contents[0]["text"])
        assert "error" in data

    async def test_resource_chains_empty_authority(self, server):
        """eatp://chains/{authority_id} for empty authority returns zero agents."""
        await _initialize_server(server)

        request = _make_request(
            "resources/read",
            {
                "uri": "eatp://chains/nonexistent-authority",
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        data = json.loads(response["result"]["contents"][0]["text"])
        assert data["total_agents"] == 0
        assert data["tree"] == []

    async def test_resource_unknown_uri_returns_error(self, server):
        """Unknown resource URI returns an error response."""
        await _initialize_server(server)

        request = _make_request(
            "resources/read",
            {
                "uri": "eatp://unknown/resource/path",
            },
        )
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        # Unknown URI should produce an internal error
        assert "error" in response
        assert response["error"]["code"] == -32603  # Internal error

    async def test_resource_read_missing_uri(self, server):
        """resources/read without uri field returns error."""
        await _initialize_server(server)

        request = _make_request("resources/read", {})
        raw_response = await server.handle_message(request)
        response = _parse_response(raw_response)

        assert "error" in response


# ===========================================================================
# 6. Full Workflow Test
# ===========================================================================


class TestFullWorkflow:
    """Test complete end-to-end workflows through the MCP server."""

    async def test_establish_verify_delegate_audit_workflow(self, server, trust_ops, audit_store):
        """
        Full workflow: initialize -> establish agent -> verify action ->
        delegate to second agent -> verify delegation -> audit query.
        """
        # Step 1: Initialize the server
        init_response = await _initialize_server(server)
        assert init_response["result"]["protocolVersion"] == "2024-11-05"

        # Step 2: Send initialized notification
        notification = _make_notification("notifications/initialized")
        assert await server.handle_message(notification) is None

        # Step 3: Establish agent-alpha with real TrustOperations
        await _establish_agent(
            trust_ops,
            "agent-alpha",
            ["analyze_data", "read_reports", "generate_summary"],
        )

        # Step 4: Verify agent-alpha can analyze_data
        verify_request = _make_request(
            "tools/call",
            {
                "name": "eatp_verify",
                "arguments": {
                    "agent_id": "agent-alpha",
                    "action": "analyze_data",
                },
            },
            msg_id=10,
        )
        raw = await server.handle_message(verify_request)
        verify_data = _get_tool_result_data(_parse_response(raw))
        assert verify_data["valid"] is True
        assert verify_data["verdict"] == "auto_approved"

        # Step 5: Check agent-alpha status
        status_request = _make_request(
            "tools/call",
            {
                "name": "eatp_status",
                "arguments": {"agent_id": "agent-alpha"},
            },
            msg_id=11,
        )
        raw = await server.handle_message(status_request)
        status_data = _get_tool_result_data(_parse_response(raw))
        assert status_data["agent_id"] == "agent-alpha"
        assert "analyze_data" in status_data["capabilities"]
        assert status_data["chain_expired"] is False

        # Step 6: Delegate analyze_data from alpha to agent-gamma (NOT pre-established).
        # When the delegatee has no existing chain, TrustOperations.delegate()
        # creates a derived chain with new CapabilityAttestations for the
        # delegated capabilities. This is the correct path for verifying
        # delegated capabilities via VERIFY.
        delegate_request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "from_agent": "agent-alpha",
                    "to_agent": "agent-gamma",
                    "capabilities": ["analyze_data"],
                },
            },
            msg_id=12,
        )
        raw = await server.handle_message(delegate_request)
        delegate_data = _get_tool_result_data(_parse_response(raw))
        assert "delegation_id" in delegate_data
        assert delegate_data["from_agent"] == "agent-alpha"
        assert delegate_data["to_agent"] == "agent-gamma"
        delegation_id = delegate_data["delegation_id"]

        # Step 7: Verify agent-gamma can now analyze_data (via derived chain).
        # When delegation creates a derived chain, the delegated capabilities
        # become real CapabilityAttestations, so VERIFY can find them.
        verify_gamma = _make_request(
            "tools/call",
            {
                "name": "eatp_verify",
                "arguments": {
                    "agent_id": "agent-gamma",
                    "action": "analyze_data",
                },
            },
            msg_id=13,
        )
        raw = await server.handle_message(verify_gamma)
        verify_gamma_data = _get_tool_result_data(_parse_response(raw))
        assert verify_gamma_data["valid"] is True
        assert verify_gamma_data["verdict"] == "auto_approved"

        # Step 8: Append audit records for the workflow
        audit_anchor = AuditAnchor(
            id="aud-wf-001",
            agent_id="agent-alpha",
            action="analyze_data",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="hash-wf",
            result=ActionResult.SUCCESS,
            signature="sig-wf",
            resource="database://finance",
        )
        await audit_store.append(audit_anchor)

        # Step 9: Query audit trail
        audit_request = _make_request(
            "tools/call",
            {
                "name": "eatp_audit_query",
                "arguments": {"agent_id": "agent-alpha"},
            },
            msg_id=14,
        )
        raw = await server.handle_message(audit_request)
        audit_data = _get_tool_result_data(_parse_response(raw))
        assert audit_data["total_returned"] >= 1
        found = any(r["anchor"]["action"] == "analyze_data" for r in audit_data["records"])
        assert found, "Audit trail must contain the analyze_data action"

        # Step 10: Read resources to verify state
        # Check authorities
        auth_request = _make_request(
            "resources/read",
            {
                "uri": "eatp://authorities",
            },
            msg_id=15,
        )
        raw = await server.handle_message(auth_request)
        auth_data = json.loads(_parse_response(raw)["result"]["contents"][0]["text"])
        assert auth_data["total"] >= 1

        # Check agent-alpha details
        agent_request = _make_request(
            "resources/read",
            {
                "uri": "eatp://agents/agent-alpha",
            },
            msg_id=16,
        )
        raw = await server.handle_message(agent_request)
        agent_data = json.loads(_parse_response(raw)["result"]["contents"][0]["text"])
        assert agent_data["agent_id"] == "agent-alpha"
        assert len(agent_data["capabilities"]) >= 3

        # Check chain tree
        chain_request = _make_request(
            "resources/read",
            {
                "uri": "eatp://chains/org-test",
            },
            msg_id=17,
        )
        raw = await server.handle_message(chain_request)
        chain_data = json.loads(_parse_response(raw)["result"]["contents"][0]["text"])
        assert chain_data["total_agents"] >= 2

        # Check constraints for agent-alpha
        constraint_request = _make_request(
            "resources/read",
            {
                "uri": "eatp://constraints/agent-alpha",
            },
            msg_id=18,
        )
        raw = await server.handle_message(constraint_request)
        constraint_data = json.loads(_parse_response(raw)["result"]["contents"][0]["text"])
        assert constraint_data["agent_id"] == "agent-alpha"

        # Step 11: Revoke the delegation
        revoke_request = _make_request(
            "tools/call",
            {
                "name": "eatp_revoke",
                "arguments": {"delegation_id": delegation_id},
            },
            msg_id=19,
        )
        raw = await server.handle_message(revoke_request)
        revoke_data = _get_tool_result_data(_parse_response(raw))
        assert revoke_data["revoked"] is True

    async def test_lightweight_verify_without_ops(self, server_no_ops, trust_store):
        """
        Server without TrustOperations uses lightweight verification
        from the store directly.
        """
        await _initialize_server(server_no_ops)

        # Manually create and store a chain in the trust store
        from kailash.trust.chain import (
            CapabilityAttestation,
            ConstraintEnvelope,
            GenesisRecord,
            TrustLineageChain,
        )

        genesis = GenesisRecord(
            id="gen-light-1",
            agent_id="agent-light",
            authority_id="org-test",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="sig-light",
        )
        cap = CapabilityAttestation(
            id="cap-light-1",
            capability="read_data",
            capability_type=CapabilityType.ACTION,
            constraints=[],
            attester_id="org-test",
            attested_at=datetime.now(timezone.utc),
            signature="sig-cap-light",
        )
        chain = TrustLineageChain(
            genesis=genesis,
            capabilities=[cap],
            delegations=[],
            audit_anchors=[],
        )
        await trust_store.initialize()
        await trust_store.store_chain(chain)

        # Verify using lightweight path (no TrustOperations)
        request = _make_request(
            "tools/call",
            {
                "name": "eatp_verify",
                "arguments": {"agent_id": "agent-light", "action": "read_data"},
            },
        )
        raw = await server_no_ops.handle_message(request)
        data = _get_tool_result_data(_parse_response(raw))

        assert data["valid"] is True
        assert data["verdict"] == "auto_approved"

        # Verify unauthorized action
        request2 = _make_request(
            "tools/call",
            {
                "name": "eatp_verify",
                "arguments": {"agent_id": "agent-light", "action": "delete_all"},
            },
        )
        raw2 = await server_no_ops.handle_message(request2)
        data2 = _get_tool_result_data(_parse_response(raw2))

        assert data2["valid"] is False
        assert data2["verdict"] == "blocked"

    async def test_multiple_agents_resource_enumeration(self, server, trust_ops):
        """
        After establishing multiple agents, resources/list enumerates
        all agent, constraint, and chain resources.
        """
        await _initialize_server(server)
        await _establish_agent(trust_ops, "agent-enum-a", ["read"])
        await _establish_agent(trust_ops, "agent-enum-b", ["write"])
        await _establish_agent(trust_ops, "agent-enum-c", ["analyze"])

        request = _make_request("resources/list", {})
        raw = await server.handle_message(request)
        response = _parse_response(raw)

        resources = response["result"]["resources"]
        uris = {r["uri"] for r in resources}

        # Should have authorities + 3 agents + 3 constraints + 1 chain
        assert "eatp://authorities" in uris
        assert "eatp://agents/agent-enum-a" in uris
        assert "eatp://agents/agent-enum-b" in uris
        assert "eatp://agents/agent-enum-c" in uris
        assert "eatp://constraints/agent-enum-a" in uris
        assert "eatp://constraints/agent-enum-b" in uris
        assert "eatp://constraints/agent-enum-c" in uris
        assert "eatp://chains/org-test" in uris
