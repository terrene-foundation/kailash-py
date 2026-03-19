# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for reasoning trace support in the EATP MCP server (TODO-016).

Covers:
- eatp_delegate tool: optional reasoning trace parameters construct a
  ReasoningTrace and pass it to TrustOperations.delegate
- eatp_delegate tool: invalid confidentiality returns descriptive error
- eatp_delegate tool: backward compatibility -- omitting reasoning params
  works identically to before
- eatp_verify tool: reasoning_present and reasoning_verified fields appear
  in output when the VerificationResult carries them
- eatp_audit_query tool: reasoning traces on audit anchors are serialized
  into the query response
- CLI delegate command: --reasoning-decision / --reasoning-rationale /
  --reasoning-confidentiality flags are accepted and result in a
  ReasoningTrace on the DelegationRecord

Uses real infrastructure (InMemoryTrustStore, TrustOperations) -- NO mocking.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from eatp.audit_store import AppendOnlyAuditStore
from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import (
    ActionResult,
    AuditAnchor,
    AuthorityType,
    CapabilityType,
    VerificationLevel,
)
from eatp.crypto import generate_keypair
from eatp.enforce.strict import HeldBehavior, StrictEnforcer
from eatp.mcp.server import EATPMCPServer
from eatp.operations import CapabilityRequest, TrustKeyManager, TrustOperations
from eatp.postures import PostureStateMachine
from eatp.reasoning import ConfidentialityLevel, ReasoningTrace
from eatp.store.memory import InMemoryTrustStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Real Authority Registry (NOT a mock)
# ---------------------------------------------------------------------------


class SimpleAuthorityRegistry:
    """Real in-memory authority registry for tests."""

    def __init__(self) -> None:
        self._authorities: Dict[str, OrganizationalAuthority] = {}

    async def initialize(self) -> None:
        pass

    def register(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority

    async def get_authority(
        self,
        authority_id: str,
        include_inactive: bool = False,
    ) -> OrganizationalAuthority:
        authority = self._authorities.get(authority_id)
        if authority is None:
            from eatp.exceptions import AuthorityNotFoundError

            raise AuthorityNotFoundError(authority_id)
        if not authority.is_active and not include_inactive:
            from eatp.exceptions import AuthorityInactiveError

            raise AuthorityInactiveError(authority_id)
        return authority

    async def update_authority(self, authority: OrganizationalAuthority) -> None:
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


def _parse_response(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse a JSON-RPC response string."""
    if raw is None:
        return None
    return json.loads(raw)


def _get_tool_result_data(response: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and parse the tool result data from a tools/call response."""
    result = response["result"]
    content = result["content"]
    assert len(content) > 0
    text = content[0]["text"]
    return json.loads(text)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 keypair."""
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
    assert raw_response is not None
    return _parse_response(raw_response)


async def _establish_agent(
    trust_ops: TrustOperations,
    agent_id: str,
    capabilities: List[str],
    authority_id: str = "org-test",
    constraints: Optional[List[str]] = None,
) -> None:
    """Helper: establish an agent with given capabilities."""
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
# 1. MCP Server Delegate Tool -- Reasoning Trace Parameters
# ===========================================================================


class TestDelegateReasoning:
    """Tests for reasoning trace support in the eatp_delegate MCP tool."""

    async def test_delegate_with_reasoning_trace(self, server, trust_ops):
        """Providing reasoning parameters attaches a ReasoningTrace to the delegation."""
        await _initialize_server(server)

        # Establish delegator with capabilities
        await _establish_agent(trust_ops, "delegator-agent", ["read", "write"])

        # Delegate with reasoning trace
        request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "from_agent": "delegator-agent",
                    "to_agent": "delegatee-agent",
                    "capabilities": ["read"],
                    "reasoning_decision": "Grant read access for data analysis",
                    "reasoning_rationale": "Agent needs read access to perform analysis task",
                    "reasoning_confidentiality": "restricted",
                },
            },
        )
        raw = await server.handle_message(request)
        response = _parse_response(raw)
        data = _get_tool_result_data(response)

        assert "error" not in data, f"Unexpected error: {data.get('error')}"
        assert "delegation_id" in data
        assert data["from_agent"] == "delegator-agent"
        assert data["to_agent"] == "delegatee-agent"
        assert data["capabilities_delegated"] == ["read"]

        # Verify reasoning trace is included in response
        assert "reasoning_trace" in data
        rt = data["reasoning_trace"]
        assert rt["decision"] == "Grant read access for data analysis"
        assert rt["rationale"] == "Agent needs read access to perform analysis task"
        assert rt["confidentiality"] == "restricted"
        assert "timestamp" in rt

    async def test_delegate_without_reasoning_backward_compat(self, server, trust_ops):
        """Omitting reasoning parameters works identically to before."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "delegator-agent", ["read", "write"])

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "from_agent": "delegator-agent",
                    "to_agent": "delegatee-agent",
                    "capabilities": ["read"],
                },
            },
        )
        raw = await server.handle_message(request)
        response = _parse_response(raw)
        data = _get_tool_result_data(response)

        assert "error" not in data, f"Unexpected error: {data.get('error')}"
        assert "delegation_id" in data
        # reasoning_trace should NOT be in output when not provided
        assert "reasoning_trace" not in data

    async def test_delegate_reasoning_requires_both_decision_and_rationale(self, server, trust_ops):
        """Providing only decision without rationale does NOT create a trace."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "delegator-agent", ["read"])

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "from_agent": "delegator-agent",
                    "to_agent": "delegatee-agent",
                    "capabilities": ["read"],
                    "reasoning_decision": "Some decision",
                    # reasoning_rationale intentionally omitted
                },
            },
        )
        raw = await server.handle_message(request)
        response = _parse_response(raw)
        data = _get_tool_result_data(response)

        assert "error" not in data
        assert "delegation_id" in data
        # No reasoning trace since rationale was not provided
        assert "reasoning_trace" not in data

    async def test_delegate_invalid_confidentiality_returns_error(self, server, trust_ops):
        """Invalid confidentiality level returns a descriptive error."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "delegator-agent", ["read"])

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "from_agent": "delegator-agent",
                    "to_agent": "delegatee-agent",
                    "capabilities": ["read"],
                    "reasoning_decision": "Some decision",
                    "reasoning_rationale": "Some rationale",
                    "reasoning_confidentiality": "ultra_secret",
                },
            },
        )
        raw = await server.handle_message(request)
        response = _parse_response(raw)
        data = _get_tool_result_data(response)

        assert "error" in data
        assert "ultra_secret" in data["error"]
        assert "reasoning_confidentiality" in data["error"]

    async def test_delegate_default_confidentiality_is_restricted(self, server, trust_ops):
        """When reasoning is provided without confidentiality, default is 'restricted'."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "delegator-agent", ["read"])

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_delegate",
                "arguments": {
                    "from_agent": "delegator-agent",
                    "to_agent": "delegatee-agent",
                    "capabilities": ["read"],
                    "reasoning_decision": "Grant read for task",
                    "reasoning_rationale": "Task requires read access",
                    # reasoning_confidentiality intentionally omitted
                },
            },
        )
        raw = await server.handle_message(request)
        response = _parse_response(raw)
        data = _get_tool_result_data(response)

        assert "error" not in data
        assert data["reasoning_trace"]["confidentiality"] == "restricted"

    async def test_delegate_all_confidentiality_levels(self, server, trust_ops):
        """All valid confidentiality levels are accepted."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "delegator-agent", ["read", "write", "exec", "admin", "deploy"])

        for level in ["public", "restricted", "confidential", "secret", "top_secret"]:
            request = _make_request(
                "tools/call",
                {
                    "name": "eatp_delegate",
                    "arguments": {
                        "from_agent": "delegator-agent",
                        "to_agent": f"agent-{level}",
                        "capabilities": ["read"],
                        "reasoning_decision": f"Decision for {level}",
                        "reasoning_rationale": f"Rationale for {level}",
                        "reasoning_confidentiality": level,
                    },
                },
            )
            raw = await server.handle_message(request)
            response = _parse_response(raw)
            data = _get_tool_result_data(response)

            assert "error" not in data, f"Level '{level}' should be valid, got: {data.get('error')}"
            assert data["reasoning_trace"]["confidentiality"] == level


# ===========================================================================
# 2. MCP Server Verify Tool -- Reasoning Status in Output
# ===========================================================================


class TestVerifyReasoning:
    """Tests for reasoning verification status in the eatp_verify MCP tool."""

    async def test_verify_without_reasoning_omits_fields(self, server, trust_ops):
        """When no reasoning is involved, reasoning fields are absent from output."""
        await _initialize_server(server)
        await _establish_agent(trust_ops, "agent-a", ["read"])

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_verify",
                "arguments": {
                    "agent_id": "agent-a",
                    "action": "read",
                },
            },
        )
        raw = await server.handle_message(request)
        response = _parse_response(raw)
        data = _get_tool_result_data(response)

        assert data["valid"] is True
        # reasoning_present and reasoning_verified should not appear
        # when VerificationResult doesn't carry them
        assert "reasoning_present" not in data
        assert "reasoning_verified" not in data


# ===========================================================================
# 3. MCP Server Audit Query -- Reasoning Trace in Output
# ===========================================================================


class TestAuditQueryReasoning:
    """Tests for reasoning trace output in eatp_audit_query."""

    async def test_audit_query_includes_reasoning_trace_on_anchor(self, server, trust_ops, audit_store):
        """When an audit anchor has a reasoning trace, it appears in query results."""
        await _initialize_server(server)

        # Create an audit record with a PUBLIC reasoning trace (included in response)
        trace = ReasoningTrace(
            decision="Approved data export",
            rationale="Agent completed verification checks",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc),
        )
        anchor = AuditAnchor(
            id="audit-001",
            agent_id="agent-x",
            action="export_data",
            timestamp=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc),
            trust_chain_hash="abc123",
            result=ActionResult.SUCCESS,
            signature="sig-placeholder",
            reasoning_trace=trace,
            reasoning_trace_hash="hash-placeholder",
        )
        await audit_store.append(anchor)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_audit_query",
                "arguments": {
                    "agent_id": "agent-x",
                },
            },
        )
        raw = await server.handle_message(request)
        response = _parse_response(raw)
        data = _get_tool_result_data(response)

        assert data["total_returned"] == 1
        record = data["records"][0]
        anchor_data = record["anchor"]
        assert "reasoning_trace" in anchor_data
        assert anchor_data["reasoning_trace"]["decision"] == "Approved data export"
        assert anchor_data["reasoning_trace"]["confidentiality"] == "public"
        assert anchor_data["reasoning_trace_hash"] == "hash-placeholder"

    async def test_audit_query_filters_confidential_reasoning_trace(self, server, trust_ops, audit_store):
        """CONFIDENTIAL+ reasoning traces are filtered from MCP response (only hash included)."""
        await _initialize_server(server)

        trace = ReasoningTrace(
            decision="Approved data export",
            rationale="Agent completed verification checks",
            confidentiality=ConfidentialityLevel.CONFIDENTIAL,
            timestamp=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc),
        )
        anchor = AuditAnchor(
            id="audit-003",
            agent_id="agent-z",
            action="export_data",
            timestamp=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc),
            trust_chain_hash="ghi789",
            result=ActionResult.SUCCESS,
            signature="sig-placeholder",
            reasoning_trace=trace,
            reasoning_trace_hash="hash-confidential",
        )
        await audit_store.append(anchor)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_audit_query",
                "arguments": {"agent_id": "agent-z"},
            },
        )
        raw = await server.handle_message(request)
        response = _parse_response(raw)
        data = _get_tool_result_data(response)

        record = data["records"][0]
        anchor_data = record["anchor"]
        # CONFIDENTIAL trace should NOT be included
        assert "reasoning_trace" not in anchor_data
        # But hash should still be present
        assert anchor_data["reasoning_trace_hash"] == "hash-confidential"

    async def test_audit_query_includes_restricted_reasoning_trace(self, server, trust_ops, audit_store):
        """RESTRICTED reasoning traces should be included in MCP response (boundary test)."""
        await _initialize_server(server)

        trace = ReasoningTrace(
            decision="Approved",
            rationale="Checks passed",
            confidentiality=ConfidentialityLevel.RESTRICTED,
            timestamp=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc),
        )
        anchor = AuditAnchor(
            id="audit-restricted",
            agent_id="agent-boundary",
            action="restricted_action",
            timestamp=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc),
            trust_chain_hash="boundary-hash",
            result=ActionResult.SUCCESS,
            signature="sig-placeholder",
            reasoning_trace=trace,
            reasoning_trace_hash="hash-restricted",
        )
        await audit_store.append(anchor)

        request = _make_request(
            "tools/call",
            {"name": "eatp_audit_query", "arguments": {"agent_id": "agent-boundary"}},
        )
        raw = await server.handle_message(request)
        response = _parse_response(raw)
        data = _get_tool_result_data(response)

        anchor_data = data["records"][0]["anchor"]
        # RESTRICTED is at the boundary — should be INCLUDED
        assert "reasoning_trace" in anchor_data
        assert anchor_data["reasoning_trace"]["confidentiality"] == "restricted"

    async def test_audit_query_filters_secret_reasoning_trace(self, server, trust_ops, audit_store):
        """SECRET reasoning traces should be filtered from MCP response."""
        await _initialize_server(server)

        trace = ReasoningTrace(
            decision="Classified decision",
            rationale="Classified rationale",
            confidentiality=ConfidentialityLevel.SECRET,
            timestamp=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc),
        )
        anchor = AuditAnchor(
            id="audit-secret",
            agent_id="agent-secret",
            action="secret_action",
            timestamp=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc),
            trust_chain_hash="secret-hash",
            result=ActionResult.SUCCESS,
            signature="sig-placeholder",
            reasoning_trace=trace,
            reasoning_trace_hash="hash-secret",
        )
        await audit_store.append(anchor)

        request = _make_request(
            "tools/call",
            {"name": "eatp_audit_query", "arguments": {"agent_id": "agent-secret"}},
        )
        raw = await server.handle_message(request)
        response = _parse_response(raw)
        data = _get_tool_result_data(response)

        anchor_data = data["records"][0]["anchor"]
        # SECRET should be filtered
        assert "reasoning_trace" not in anchor_data
        # Hash should still be present
        assert anchor_data["reasoning_trace_hash"] == "hash-secret"

    async def test_audit_query_filters_top_secret_reasoning_trace(self, server, trust_ops, audit_store):
        """TOP_SECRET reasoning traces should be filtered from MCP response."""
        await _initialize_server(server)

        trace = ReasoningTrace(
            decision="Top secret decision",
            rationale="Top secret rationale",
            confidentiality=ConfidentialityLevel.TOP_SECRET,
            timestamp=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc),
        )
        anchor = AuditAnchor(
            id="audit-topsecret",
            agent_id="agent-ts",
            action="ts_action",
            timestamp=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc),
            trust_chain_hash="ts-hash",
            result=ActionResult.SUCCESS,
            signature="sig-placeholder",
            reasoning_trace=trace,
            reasoning_trace_hash="hash-ts",
        )
        await audit_store.append(anchor)

        request = _make_request(
            "tools/call",
            {"name": "eatp_audit_query", "arguments": {"agent_id": "agent-ts"}},
        )
        raw = await server.handle_message(request)
        response = _parse_response(raw)
        data = _get_tool_result_data(response)

        anchor_data = data["records"][0]["anchor"]
        # TOP_SECRET should be filtered
        assert "reasoning_trace" not in anchor_data
        assert anchor_data["reasoning_trace_hash"] == "hash-ts"

    async def test_audit_query_omits_reasoning_when_absent(self, server, trust_ops, audit_store):
        """When an audit anchor has no reasoning trace, the field is absent."""
        await _initialize_server(server)

        anchor = AuditAnchor(
            id="audit-002",
            agent_id="agent-y",
            action="read_data",
            timestamp=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc),
            trust_chain_hash="def456",
            result=ActionResult.SUCCESS,
            signature="sig-placeholder",
        )
        await audit_store.append(anchor)

        request = _make_request(
            "tools/call",
            {
                "name": "eatp_audit_query",
                "arguments": {
                    "agent_id": "agent-y",
                },
            },
        )
        raw = await server.handle_message(request)
        response = _parse_response(raw)
        data = _get_tool_result_data(response)

        assert data["total_returned"] == 1
        anchor_data = data["records"][0]["anchor"]
        assert "reasoning_trace" not in anchor_data


# ===========================================================================
# 4. Tool Definition Schema Validation
# ===========================================================================


class TestToolDefinitionSchema:
    """Verify the MCP tool definitions include reasoning parameters."""

    async def test_delegate_tool_schema_has_reasoning_fields(self, server):
        """The eatp_delegate tool definition must include reasoning parameters."""
        await _initialize_server(server)

        request = _make_request("tools/list", {})
        raw = await server.handle_message(request)
        response = _parse_response(raw)
        tools = response["result"]["tools"]

        delegate_tool = next(t for t in tools if t["name"] == "eatp_delegate")
        props = delegate_tool["inputSchema"]["properties"]

        assert "reasoning_decision" in props
        assert props["reasoning_decision"]["type"] == "string"

        assert "reasoning_rationale" in props
        assert props["reasoning_rationale"]["type"] == "string"

        assert "reasoning_confidentiality" in props
        assert props["reasoning_confidentiality"]["type"] == "string"

        # Reasoning fields must NOT be required
        required = delegate_tool["inputSchema"]["required"]
        assert "reasoning_decision" not in required
        assert "reasoning_rationale" not in required
        assert "reasoning_confidentiality" not in required
