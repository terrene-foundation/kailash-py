# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP MCP Server -- JSON-RPC over stdio.

Exposes EATP trust operations as MCP tools and trust data as MCP resources
using the JSON-RPC protocol directly, without depending on the external
``mcp`` Python SDK.

Protocol flow (MCP specification):
    1. Client sends ``initialize`` -> server responds with capabilities
    2. Client sends ``tools/list`` -> server responds with tool definitions
    3. Client sends ``tools/call`` with tool name and arguments
    4. Server executes the tool and returns result content
    5. Client sends ``resources/list`` -> server responds with resource templates
    6. Client sends ``resources/read`` with URI -> server returns resource content

Transport: stdio (read JSON-RPC from stdin, write responses to stdout).

Tools:
    - eatp_verify: Check action authorization (verdict + details)
    - eatp_status: Get trust state (score, posture, delegations, constraints)
    - eatp_audit_query: Query audit trail with filters
    - eatp_delegate: Delegate capabilities (confirmation required)
    - eatp_revoke: Revoke delegation (confirmation required)

Resources:
    - eatp://authorities: List all organizational authorities
    - eatp://agents/{id}: Agent details with trust posture
    - eatp://chains/{authority_id}: Delegation chain visualization
    - eatp://constraints/{agent_id}: Active constraint envelope
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from eatp.audit_store import AppendOnlyAuditStore
from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import VerificationLevel, VerificationResult
from eatp.enforce.strict import HeldBehavior, StrictEnforcer
from eatp.exceptions import (
    DelegationError,
    TrustChainNotFoundError,
    TrustError,
)
from eatp.operations import TrustOperations
from eatp.postures import PostureStateMachine
from eatp.reasoning import ConfidentialityLevel, ReasoningTrace
from eatp.scoring import compute_trust_score
from eatp.store import TrustStore
from eatp.store.memory import InMemoryTrustStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

_JSONRPC_VERSION = "2.0"
_MCP_PROTOCOL_VERSION = "2024-11-05"


def _ok_response(id: Any, result: Any) -> Dict[str, Any]:
    """Build a JSON-RPC success response."""
    return {"jsonrpc": _JSONRPC_VERSION, "id": id, "result": result}


def _error_response(
    id: Any,
    code: int,
    message: str,
    data: Any = None,
) -> Dict[str, Any]:
    """Build a JSON-RPC error response."""
    error: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": _JSONRPC_VERSION, "id": id, "error": error}


# Standard JSON-RPC error codes
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603

# ---------------------------------------------------------------------------
# Tool definitions (MCP schema)
# ---------------------------------------------------------------------------

_TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "eatp_verify",
        "description": (
            "Check whether an agent is authorized to perform an action. "
            "Returns a verdict (AUTO_APPROVED, FLAGGED, HELD, or BLOCKED) "
            "with details about the verification result."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The agent requesting authorization",
                },
                "action": {
                    "type": "string",
                    "description": "The action to authorize",
                },
                "resource": {
                    "type": "string",
                    "description": "The resource being accessed (optional)",
                },
            },
            "required": ["agent_id", "action"],
        },
    },
    {
        "name": "eatp_status",
        "description": (
            "Get the current trust state for an agent, including trust "
            "score, posture, active delegations, and constraints summary."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The agent to query",
                },
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "eatp_audit_query",
        "description": (
            "Query the audit trail for agent actions. "
            "Supports filtering by agent_id and action type."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Filter by agent ID (optional)",
                },
                "action": {
                    "type": "string",
                    "description": "Filter by action type (optional)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of records to return (default: 10)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "eatp_delegate",
        "description": (
            "Delegate capabilities from one agent to another. "
            "This is a privileged operation that modifies trust chains. "
            "Optionally attach a reasoning trace explaining WHY the delegation "
            "was made (decision transparency)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_agent": {
                    "type": "string",
                    "description": "Agent delegating capabilities",
                },
                "to_agent": {
                    "type": "string",
                    "description": "Agent receiving capabilities",
                },
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of capability names to delegate",
                },
                "constraints": {
                    "type": "object",
                    "description": "Additional constraints for the delegation (optional)",
                },
                "reasoning_decision": {
                    "type": "string",
                    "description": (
                        "What was decided — human-readable summary for "
                        "the reasoning trace (optional)"
                    ),
                },
                "reasoning_rationale": {
                    "type": "string",
                    "description": (
                        "Why it was decided — human-readable explanation "
                        "for the reasoning trace (optional)"
                    ),
                },
                "reasoning_confidentiality": {
                    "type": "string",
                    "description": (
                        "Confidentiality level for the reasoning trace. "
                        "One of: public, restricted, confidential, secret, "
                        "top_secret. Default: restricted (optional)"
                    ),
                },
            },
            "required": ["from_agent", "to_agent", "capabilities"],
        },
    },
    {
        "name": "eatp_revoke",
        "description": (
            "Revoke a delegation. Optionally cascade revocation to "
            "downstream agents that received trust through this delegation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "delegation_id": {
                    "type": "string",
                    "description": "ID of the delegation to revoke",
                },
                "cascade": {
                    "type": "boolean",
                    "description": "Whether to cascade revocation to downstream agents (default: false)",
                },
            },
            "required": ["delegation_id"],
        },
    },
]


# ---------------------------------------------------------------------------
# Resource definitions (MCP schema)
# ---------------------------------------------------------------------------

_RESOURCE_TEMPLATES: List[Dict[str, Any]] = [
    {
        "uriTemplate": "eatp://authorities",
        "name": "EATP Authorities",
        "description": (
            "List all organizational authorities registered in the trust store. "
            "Returns authority ID, name, type, and capabilities for each."
        ),
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "eatp://agents/{id}",
        "name": "EATP Agent Details",
        "description": (
            "Get detailed information for a specific agent including trust posture, "
            "trust score, active capabilities, and active delegations."
        ),
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "eatp://chains/{authority_id}",
        "name": "EATP Delegation Chain",
        "description": (
            "Visualize the delegation chain hierarchy for all agents under a "
            "specific authority. Returns a tree structure showing delegation "
            "relationships."
        ),
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "eatp://constraints/{agent_id}",
        "name": "EATP Constraint Envelope",
        "description": (
            "Get the active constraint envelope for a specific agent. Returns "
            "detailed constraint information including type, value, source, "
            "and priority for each active constraint."
        ),
        "mimeType": "application/json",
    },
]

# URI patterns for resource routing
_RESOURCE_PATTERNS: List[tuple] = [
    (re.compile(r"^eatp://authorities$"), "authorities"),
    (re.compile(r"^eatp://agents/(?P<id>[^/]+)$"), "agents"),
    (re.compile(r"^eatp://chains/(?P<authority_id>[^/]+)$"), "chains"),
    (re.compile(r"^eatp://constraints/(?P<agent_id>[^/]+)$"), "constraints"),
]


# ---------------------------------------------------------------------------
# EATPMCPServer
# ---------------------------------------------------------------------------


class EATPMCPServer:
    """
    MCP server exposing EATP trust operations over JSON-RPC/stdio.

    Implements the MCP protocol (initialize, tools/list, tools/call) using
    raw JSON-RPC messages without any external MCP SDK dependency.

    The server wraps a TrustStore and TrustOperations instance to provide
    five tools: eatp_verify, eatp_status, eatp_audit_query, eatp_delegate,
    and eatp_revoke.

    Args:
        trust_store: Storage backend for trust chains. Defaults to
            InMemoryTrustStore if not provided.
        trust_ops: TrustOperations instance. When provided, the server
            uses it directly. When omitted, the server constructs a
            lightweight TrustOperations internally (requires the store
            to already contain established chains for verification
            and delegation).
        audit_store: Append-only audit store for eatp_audit_query.
            Defaults to an empty AppendOnlyAuditStore.
        posture_machine: PostureStateMachine for trust scoring.
            Defaults to a new PostureStateMachine.
        enforcer: StrictEnforcer for verdict classification.
            Defaults to a new StrictEnforcer.

    Example:
        >>> from eatp.mcp.server import EATPMCPServer
        >>> from eatp.store.memory import InMemoryTrustStore
        >>>
        >>> store = InMemoryTrustStore()
        >>> server = EATPMCPServer(trust_store=store)
        >>> await server.serve_stdio()
    """

    def __init__(
        self,
        trust_store: Optional[TrustStore] = None,
        trust_ops: Optional[TrustOperations] = None,
        audit_store: Optional[AppendOnlyAuditStore] = None,
        posture_machine: Optional[PostureStateMachine] = None,
        enforcer: Optional[StrictEnforcer] = None,
        authorities_dir: Optional[str] = None,
    ) -> None:
        self._store = trust_store or InMemoryTrustStore()
        self._ops = trust_ops
        self._audit_store = audit_store or AppendOnlyAuditStore()
        self._posture_machine = posture_machine or PostureStateMachine(
            require_upgrade_approval=False,
        )
        self._enforcer = enforcer or StrictEnforcer(
            on_held=HeldBehavior.RAISE,
            flag_threshold=1,
        )
        self._initialized = False
        self._authorities_dir = authorities_dir

        # Method dispatch table
        self._methods: Dict[str, Any] = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "resources/templates/list": self._handle_resource_templates_list,
            "notifications/initialized": self._handle_notification,
            "ping": self._handle_ping,
        }

        # Tool dispatch table
        self._tools: Dict[str, Any] = {
            "eatp_verify": self._tool_verify,
            "eatp_status": self._tool_status,
            "eatp_audit_query": self._tool_audit_query,
            "eatp_delegate": self._tool_delegate,
            "eatp_revoke": self._tool_revoke,
        }

        # Resource dispatch table
        self._resource_handlers: Dict[str, Any] = {
            "authorities": self._resource_authorities,
            "agents": self._resource_agent,
            "chains": self._resource_chain,
            "constraints": self._resource_constraints,
        }

    async def _ensure_initialized(self) -> None:
        """Initialize the trust store if not yet initialized."""
        if not self._initialized:
            await self._store.initialize()
            if self._ops and not self._ops._initialized:
                await self._ops.initialize()
            self._initialized = True

    # ------------------------------------------------------------------
    # JSON-RPC message handling
    # ------------------------------------------------------------------

    async def handle_message(self, raw: str) -> Optional[str]:
        """
        Parse and dispatch a single JSON-RPC message.

        Args:
            raw: Raw JSON string from stdin.

        Returns:
            JSON response string, or None for notifications (no id).
        """
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as exc:
            resp = _error_response(None, _PARSE_ERROR, f"Parse error: {exc}")
            return json.dumps(resp)

        if not isinstance(msg, dict):
            resp = _error_response(None, _INVALID_REQUEST, "Request must be an object")
            return json.dumps(resp)

        msg_id = msg.get("id")
        method = msg.get("method")

        if not method or not isinstance(method, str):
            resp = _error_response(
                msg_id, _INVALID_REQUEST, "Missing or invalid method"
            )
            return json.dumps(resp)

        handler = self._methods.get(method)
        if handler is None:
            # Ignore unknown notifications (no id)
            if msg_id is None:
                return None
            resp = _error_response(
                msg_id, _METHOD_NOT_FOUND, f"Unknown method: {method}"
            )
            return json.dumps(resp)

        try:
            result = await handler(msg.get("params", {}))
        except Exception as exc:
            logger.exception("Error handling method %s", method)
            # Notifications have no id and expect no response
            if msg_id is None:
                return None
            resp = _error_response(msg_id, _INTERNAL_ERROR, str(exc))
            return json.dumps(resp)

        # Notifications (no id) get no response
        if msg_id is None:
            return None

        resp = _ok_response(msg_id, result)
        return json.dumps(resp)

    # ------------------------------------------------------------------
    # MCP protocol handlers
    # ------------------------------------------------------------------

    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle the ``initialize`` handshake."""
        await self._ensure_initialized()
        return {
            "protocolVersion": _MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {
                "name": "eatp-mcp-server",
                "version": "0.2.0",
            },
        }

    async def _handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ``tools/list`` -- return tool definitions."""
        return {"tools": _TOOL_DEFINITIONS}

    async def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ``tools/call`` -- dispatch to the appropriate tool."""
        await self._ensure_initialized()

        tool_name = params.get("name")
        if not tool_name or not isinstance(tool_name, str):
            raise ValueError("Missing or invalid tool name in tools/call params")

        tool_fn = self._tools.get(tool_name)
        if tool_fn is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"error": f"Unknown tool: {tool_name}"},
                        ),
                    }
                ],
                "isError": True,
            }

        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"error": "arguments must be an object"},
                        ),
                    }
                ],
                "isError": True,
            }

        try:
            result = await tool_fn(arguments)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, default=str),
                    }
                ],
            }
        except Exception as exc:
            logger.exception("Tool %s failed", tool_name)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"error": str(exc), "error_type": type(exc).__name__},
                            default=str,
                        ),
                    }
                ],
                "isError": True,
            }

    async def _handle_notification(self, params: Dict[str, Any]) -> None:
        """Handle ``notifications/initialized`` -- no-op acknowledgement."""
        return None

    async def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ``ping`` -- respond with empty result."""
        return {}

    # ------------------------------------------------------------------
    # MCP resource protocol handlers
    # ------------------------------------------------------------------

    async def _handle_resources_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ``resources/list`` -- return concrete resource URIs.

        Enumerates all available concrete resources by walking the store
        and authorities directory. Clients use this to discover what data
        is available.
        """
        await self._ensure_initialized()

        resources: List[Dict[str, Any]] = []

        # Always include the authorities list resource
        resources.append(
            {
                "uri": "eatp://authorities",
                "name": "EATP Authorities",
                "description": "List all organizational authorities",
                "mimeType": "application/json",
            }
        )

        # Add per-agent and per-agent-constraints resources
        all_chains = await self._store.list_chains()
        seen_authorities: set = set()
        for chain in all_chains:
            agent_id = chain.genesis.agent_id
            resources.append(
                {
                    "uri": f"eatp://agents/{agent_id}",
                    "name": f"Agent: {agent_id}",
                    "description": f"Trust details for agent {agent_id}",
                    "mimeType": "application/json",
                }
            )
            resources.append(
                {
                    "uri": f"eatp://constraints/{agent_id}",
                    "name": f"Constraints: {agent_id}",
                    "description": f"Active constraint envelope for agent {agent_id}",
                    "mimeType": "application/json",
                }
            )
            seen_authorities.add(chain.genesis.authority_id)

        # Add per-authority chain resources
        for authority_id in sorted(seen_authorities):
            resources.append(
                {
                    "uri": f"eatp://chains/{authority_id}",
                    "name": f"Delegation Chain: {authority_id}",
                    "description": (
                        f"Delegation hierarchy under authority {authority_id}"
                    ),
                    "mimeType": "application/json",
                }
            )

        return {"resources": resources}

    async def _handle_resource_templates_list(
        self, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle ``resources/templates/list`` -- return URI templates."""
        return {"resourceTemplates": _RESOURCE_TEMPLATES}

    async def _handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ``resources/read`` -- return resource content by URI.

        Matches the requested URI against known patterns and dispatches
        to the appropriate resource handler.

        Args:
            params: Must contain ``uri`` string.

        Returns:
            MCP resources/read response with contents array.
        """
        await self._ensure_initialized()

        uri = params.get("uri")
        if not uri or not isinstance(uri, str):
            raise ValueError("Missing or invalid 'uri' in resources/read params")

        # Match URI against patterns
        for pattern, handler_key in _RESOURCE_PATTERNS:
            match = pattern.match(uri)
            if match:
                handler = self._resource_handlers[handler_key]
                try:
                    data = await handler(match.groupdict())
                    return {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(data, default=str),
                            }
                        ],
                    }
                except Exception as exc:
                    logger.exception("Resource handler %s failed", handler_key)
                    return {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(
                                    {
                                        "error": str(exc),
                                        "error_type": type(exc).__name__,
                                    },
                                    default=str,
                                ),
                            }
                        ],
                    }

        raise ValueError(f"Unknown resource URI: {uri}")

    # ------------------------------------------------------------------
    # Resource implementations
    # ------------------------------------------------------------------

    def _load_authorities_from_dir(self) -> List[OrganizationalAuthority]:
        """Load all authorities from the authorities directory.

        Scans ``self._authorities_dir`` for JSON files and deserializes
        each into an OrganizationalAuthority.

        Returns:
            List of OrganizationalAuthority objects. Empty if no directory
            is configured or the directory does not exist.
        """
        if not self._authorities_dir:
            return []

        from pathlib import Path

        auth_dir = Path(self._authorities_dir)
        if not auth_dir.exists():
            return []

        authorities: List[OrganizationalAuthority] = []
        for auth_file in sorted(auth_dir.glob("*.json")):
            try:
                data = json.loads(auth_file.read_text())
                authorities.append(OrganizationalAuthority.from_dict(data))
            except Exception as exc:
                logger.warning("Failed to load authority from %s: %s", auth_file, exc)
        return authorities

    async def _resource_authorities(self, uri_params: Dict[str, str]) -> Dict[str, Any]:
        """Resource: ``eatp://authorities`` -- list all authorities.

        Returns authority information from two sources:
        1. The authorities directory on disk (if configured).
        2. Authorities referenced by chains in the trust store (always).

        Returns:
            Dictionary with ``authorities`` list and ``total`` count.
        """
        # Collect from disk
        disk_authorities = self._load_authorities_from_dir()
        authorities_by_id: Dict[str, Dict[str, Any]] = {}

        for auth in disk_authorities:
            capabilities = [p.value for p in auth.permissions]
            authorities_by_id[auth.id] = {
                "authority_id": auth.id,
                "name": auth.name,
                "type": auth.authority_type.value,
                "capabilities": capabilities,
                "is_active": auth.is_active,
                "created_at": auth.created_at.isoformat(),
            }

        # Augment with authorities referenced in stored chains
        all_chains = await self._store.list_chains()
        for chain in all_chains:
            auth_id = chain.genesis.authority_id
            if auth_id not in authorities_by_id:
                authorities_by_id[auth_id] = {
                    "authority_id": auth_id,
                    "name": auth_id,
                    "type": chain.genesis.authority_type.value,
                    "capabilities": [],
                    "is_active": True,
                    "created_at": chain.genesis.created_at.isoformat(),
                }

        authority_list = sorted(
            authorities_by_id.values(), key=lambda a: a["authority_id"]
        )

        return {
            "authorities": authority_list,
            "total": len(authority_list),
        }

    async def _resource_agent(self, uri_params: Dict[str, str]) -> Dict[str, Any]:
        """Resource: ``eatp://agents/{id}`` -- agent details with trust posture.

        Returns comprehensive information about a single agent including
        trust score, trust posture, active capabilities, and active
        delegations.

        Args:
            uri_params: Must contain ``id`` (the agent ID).

        Returns:
            Dictionary with agent details.

        Raises:
            TrustChainNotFoundError: If the agent has no trust chain.
        """
        agent_id = uri_params["id"]

        chain = await self._store.get_chain(agent_id)

        # Compute trust score
        try:
            score = await compute_trust_score(
                agent_id=agent_id,
                store=self._store,
                posture_machine=self._posture_machine,
            )
            score_dict = {
                "score": score.score,
                "grade": score.grade,
                "breakdown": score.breakdown,
                "computed_at": score.computed_at.isoformat(),
            }
        except Exception as exc:
            logger.warning("Failed to compute trust score for %s: %s", agent_id, exc)
            score_dict = {"error": str(exc)}

        # Get posture
        posture = self._posture_machine.get_posture(agent_id)

        # Active capabilities
        active_capabilities = []
        for cap in chain.capabilities:
            if not cap.is_expired():
                active_capabilities.append(
                    {
                        "id": cap.id,
                        "capability": cap.capability,
                        "capability_type": cap.capability_type.value,
                        "constraints": cap.constraints,
                        "attester_id": cap.attester_id,
                        "attested_at": cap.attested_at.isoformat(),
                        "expires_at": (
                            cap.expires_at.isoformat() if cap.expires_at else None
                        ),
                        "scope": cap.scope,
                    }
                )

        # Active delegations
        active_delegations = []
        for delegation in chain.get_active_delegations():
            active_delegations.append(
                {
                    "id": delegation.id,
                    "delegator_id": delegation.delegator_id,
                    "delegatee_id": delegation.delegatee_id,
                    "capabilities_delegated": delegation.capabilities_delegated,
                    "delegated_at": delegation.delegated_at.isoformat(),
                    "expires_at": (
                        delegation.expires_at.isoformat()
                        if delegation.expires_at
                        else None
                    ),
                    "delegation_depth": delegation.delegation_depth,
                }
            )

        return {
            "agent_id": agent_id,
            "authority_id": chain.genesis.authority_id,
            "authority_type": chain.genesis.authority_type.value,
            "capabilities": active_capabilities,
            "trust_posture": posture.value,
            "trust_score": score_dict,
            "active_delegations": active_delegations,
            "chain_expired": chain.is_expired(),
            "created_at": chain.genesis.created_at.isoformat(),
            "expires_at": (
                chain.genesis.expires_at.isoformat()
                if chain.genesis.expires_at
                else None
            ),
        }

    async def _resource_chain(self, uri_params: Dict[str, str]) -> Dict[str, Any]:
        """Resource: ``eatp://chains/{authority_id}`` -- delegation chain tree.

        Builds a tree structure showing the delegation hierarchy for all
        agents under the specified authority.

        Args:
            uri_params: Must contain ``authority_id``.

        Returns:
            Dictionary with ``authority_id``, ``tree`` (nested nodes), and
            ``total_agents`` count.
        """
        authority_id = uri_params["authority_id"]

        all_chains = await self._store.list_chains(authority_id=authority_id)
        if not all_chains:
            return {
                "authority_id": authority_id,
                "tree": [],
                "total_agents": 0,
            }

        # Build agent info map
        agent_info: Dict[str, Dict[str, Any]] = {}
        for chain in all_chains:
            agent_id = chain.genesis.agent_id
            agent_info[agent_id] = {
                "agent_id": agent_id,
                "capabilities": [
                    cap.capability for cap in chain.capabilities if not cap.is_expired()
                ],
                "delegation_count": len(chain.get_active_delegations()),
                "expired": chain.is_expired(),
            }

        # Build parent-to-children mapping from delegation records
        # A delegation means "from_agent delegated to to_agent", so
        # from_agent is the parent and to_agent is the child in the tree.
        children_map: Dict[str, List[str]] = {}
        child_agents: set = set()
        for chain in all_chains:
            for delegation in chain.get_active_delegations():
                parent = delegation.delegator_id
                child = delegation.delegatee_id
                if parent not in children_map:
                    children_map[parent] = []
                if child not in children_map[parent]:
                    children_map[parent].append(child)
                child_agents.add(child)

        # Also check genesis metadata for derived agents
        for chain in all_chains:
            if chain.genesis.metadata.get("derived_from"):
                parent = chain.genesis.metadata["derived_from"]
                child = chain.genesis.agent_id
                if parent not in children_map:
                    children_map[parent] = []
                if child not in children_map[parent]:
                    children_map[parent].append(child)
                child_agents.add(child)

        def _build_subtree(
            agent_id: str, visited: set, depth: int = 0
        ) -> Dict[str, Any]:
            """Recursively build the delegation subtree for an agent."""
            if agent_id in visited or depth > 20:
                return {
                    "agent_id": agent_id,
                    "cycle_detected": True,
                    "children": [],
                }
            visited.add(agent_id)

            info = agent_info.get(
                agent_id,
                {
                    "agent_id": agent_id,
                    "capabilities": [],
                    "delegation_count": 0,
                    "expired": False,
                },
            )

            node: Dict[str, Any] = {
                "agent_id": agent_id,
                "capabilities": info["capabilities"],
                "delegation_count": info["delegation_count"],
                "expired": info["expired"],
                "depth": depth,
                "children": [],
            }

            for child_id in children_map.get(agent_id, []):
                child_node = _build_subtree(child_id, visited, depth + 1)
                node["children"].append(child_node)

            return node

        # Root agents are those that are not children of any delegation
        known_agents = set(agent_info.keys())
        root_agents = known_agents - child_agents
        if not root_agents:
            # All agents are children -- pick those with no delegation-from
            # within this authority, or fall back to all
            root_agents = known_agents

        tree: List[Dict[str, Any]] = []
        for root_id in sorted(root_agents):
            subtree = _build_subtree(root_id, set())
            tree.append(subtree)

        return {
            "authority_id": authority_id,
            "tree": tree,
            "total_agents": len(all_chains),
        }

    async def _resource_constraints(self, uri_params: Dict[str, str]) -> Dict[str, Any]:
        """Resource: ``eatp://constraints/{agent_id}`` -- constraint envelope.

        Returns the full constraint envelope for an agent, including
        individual constraint details (type, value, source, priority).

        Args:
            uri_params: Must contain ``agent_id``.

        Returns:
            Dictionary with constraint envelope details.

        Raises:
            TrustChainNotFoundError: If the agent has no trust chain.
        """
        agent_id = uri_params["agent_id"]

        chain = await self._store.get_chain(agent_id)
        envelope = chain.constraint_envelope

        constraints_list: List[Dict[str, Any]] = []
        by_type: Dict[str, int] = {}

        if envelope and envelope.active_constraints:
            for c in envelope.active_constraints:
                type_name = c.constraint_type.value
                constraints_list.append(
                    {
                        "id": c.id,
                        "constraint_type": type_name,
                        "value": c.value,
                        "source": c.source,
                        "priority": c.priority,
                    }
                )
                by_type[type_name] = by_type.get(type_name, 0) + 1

        # Also collect per-capability constraints
        capability_constraints: Dict[str, List[str]] = {}
        for cap in chain.capabilities:
            if not cap.is_expired() and cap.constraints:
                capability_constraints[cap.capability] = cap.constraints

        return {
            "agent_id": agent_id,
            "envelope_id": envelope.id if envelope else None,
            "constraint_hash": envelope.constraint_hash if envelope else "",
            "computed_at": (
                envelope.computed_at.isoformat()
                if envelope and envelope.computed_at
                else None
            ),
            "valid_until": (
                envelope.valid_until.isoformat()
                if envelope and envelope.valid_until
                else None
            ),
            "envelope_valid": envelope.is_valid() if envelope else False,
            "constraints": constraints_list,
            "total": len(constraints_list),
            "by_type": by_type,
            "capability_constraints": capability_constraints,
        }

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    async def _tool_verify(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        eatp_verify: Check action authorization.

        Performs EATP VERIFY on the agent's trust chain and classifies
        the result into a Verdict via StrictEnforcer.

        Args:
            params: {"agent_id": str, "action": str, "resource": str?}

        Returns:
            {"verdict": str, "valid": bool, "details": {...}}
        """
        agent_id = params.get("agent_id")
        action = params.get("action")
        resource = params.get("resource")

        if not agent_id or not isinstance(agent_id, str):
            return {"error": "agent_id is required and must be a string"}
        if not action or not isinstance(action, str):
            return {"error": "action is required and must be a string"}

        # Use TrustOperations.verify if available, otherwise do chain-level check
        if self._ops:
            verification = await self._ops.verify(
                agent_id=agent_id,
                action=action,
                resource=resource,
                level=VerificationLevel.STANDARD,
            )
        else:
            verification = await self._verify_from_store(agent_id, action, resource)

        # Classify into verdict
        verdict = self._enforcer.classify(verification)

        result: Dict[str, Any] = {
            "verdict": verdict.value,
            "valid": verification.valid,
            "details": {
                "level": verification.level.value,
                "reason": verification.reason,
                "capability_used": verification.capability_used,
                "effective_constraints": verification.effective_constraints,
                "violations": verification.violations,
            },
        }

        # Include reasoning verification status when available
        if verification.reasoning_present is not None:
            result["reasoning_present"] = verification.reasoning_present
        if verification.reasoning_verified is not None:
            result["reasoning_verified"] = verification.reasoning_verified

        return result

    async def _verify_from_store(
        self,
        agent_id: str,
        action: str,
        resource: Optional[str],
    ) -> VerificationResult:
        """
        Lightweight verification using the store directly.

        Used when no TrustOperations instance is available. Performs
        chain retrieval, expiration check, and capability matching
        without full cryptographic signature verification.
        """
        try:
            chain = await self._store.get_chain(agent_id)
        except TrustChainNotFoundError:
            return VerificationResult(
                valid=False,
                reason="No trust chain found",
                level=VerificationLevel.STANDARD,
            )

        if chain.is_expired():
            return VerificationResult(
                valid=False,
                reason="Trust chain expired",
                level=VerificationLevel.STANDARD,
            )

        # Capability matching
        matched_cap = None
        for cap in chain.capabilities:
            if cap.is_expired():
                continue
            if cap.capability == action:
                matched_cap = cap
                break
            # Wildcard matching
            if cap.capability.endswith("*") and action.startswith(cap.capability[:-1]):
                matched_cap = cap
                break
            if cap.capability.startswith("*") and action.endswith(cap.capability[1:]):
                matched_cap = cap
                break
            if cap.capability == "*":
                matched_cap = cap
                break

        if matched_cap is None:
            return VerificationResult(
                valid=False,
                reason=f"No capability found for action '{action}'",
                level=VerificationLevel.STANDARD,
            )

        effective_constraints = chain.get_effective_constraints(matched_cap.capability)

        return VerificationResult(
            valid=True,
            level=VerificationLevel.STANDARD,
            capability_used=matched_cap.id,
            effective_constraints=effective_constraints,
        )

    async def _tool_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        eatp_status: Get trust state for an agent.

        Returns trust score, current posture, active delegations,
        and a constraints summary.

        Args:
            params: {"agent_id": str}

        Returns:
            {"agent_id": str, "trust_score": {...}, "posture": str,
             "active_delegations": [...], "constraints_summary": {...}}
        """
        agent_id = params.get("agent_id")
        if not agent_id or not isinstance(agent_id, str):
            return {"error": "agent_id is required and must be a string"}

        try:
            chain = await self._store.get_chain(agent_id)
        except TrustChainNotFoundError:
            return {
                "error": f"No trust chain found for agent: {agent_id}",
                "agent_id": agent_id,
            }

        # Compute trust score
        try:
            score = await compute_trust_score(
                agent_id=agent_id,
                store=self._store,
                posture_machine=self._posture_machine,
            )
            score_dict = {
                "score": score.score,
                "grade": score.grade,
                "breakdown": score.breakdown,
                "computed_at": score.computed_at.isoformat(),
            }
        except Exception as exc:
            logger.warning("Failed to compute trust score for %s: %s", agent_id, exc)
            score_dict = {"error": str(exc)}

        # Get posture
        posture = self._posture_machine.get_posture(agent_id)

        # Active delegations
        active_delegations = []
        for delegation in chain.get_active_delegations():
            active_delegations.append(
                {
                    "id": delegation.id,
                    "delegator_id": delegation.delegator_id,
                    "delegatee_id": delegation.delegatee_id,
                    "capabilities_delegated": delegation.capabilities_delegated,
                    "delegated_at": delegation.delegated_at.isoformat(),
                    "expires_at": (
                        delegation.expires_at.isoformat()
                        if delegation.expires_at
                        else None
                    ),
                    "delegation_depth": delegation.delegation_depth,
                }
            )

        # Constraints summary
        constraints_summary: Dict[str, Any] = {"total": 0, "by_type": {}}
        if chain.constraint_envelope and chain.constraint_envelope.active_constraints:
            constraints = chain.constraint_envelope.active_constraints
            constraints_summary["total"] = len(constraints)
            by_type: Dict[str, int] = {}
            for c in constraints:
                type_name = c.constraint_type.value
                by_type[type_name] = by_type.get(type_name, 0) + 1
            constraints_summary["by_type"] = by_type
            constraints_summary["values"] = [str(c.value) for c in constraints]

        return {
            "agent_id": agent_id,
            "trust_score": score_dict,
            "posture": posture.value,
            "active_delegations": active_delegations,
            "constraints_summary": constraints_summary,
            "chain_expired": chain.is_expired(),
            "capabilities": [
                cap.capability for cap in chain.capabilities if not cap.is_expired()
            ],
        }

    async def _tool_audit_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        eatp_audit_query: Query the audit trail.

        Searches the audit store with optional agent_id and action filters.

        Args:
            params: {"agent_id": str?, "action": str?, "limit": int?}

        Returns:
            {"records": [...], "total_returned": int}
        """
        agent_id = params.get("agent_id")
        action = params.get("action")
        limit = params.get("limit", 10)

        if not isinstance(limit, int) or limit < 1:
            limit = 10
        if limit > 100:
            limit = 100

        # Validate optional string params
        if agent_id is not None and not isinstance(agent_id, str):
            return {"error": "agent_id must be a string if provided"}
        if action is not None and not isinstance(action, str):
            return {"error": "action must be a string if provided"}

        records = await self._audit_store.list_records(
            agent_id=agent_id,
            action=action,
            limit=limit,
        )

        serialized = []
        for record in records:
            anchor = record.anchor
            entry: Dict[str, Any] = {
                "record_id": record.record_id,
                "sequence_number": record.sequence_number,
                "stored_at": record.stored_at.isoformat(),
                "anchor": {
                    "id": anchor.id,
                    "agent_id": anchor.agent_id,
                    "action": anchor.action,
                    "resource": anchor.resource,
                    "timestamp": anchor.timestamp.isoformat(),
                    "result": anchor.result.value,
                    "trust_chain_hash": anchor.trust_chain_hash,
                    "parent_anchor_id": anchor.parent_anchor_id,
                },
            }
            if anchor.context:
                entry["anchor"]["context"] = anchor.context
            # Include reasoning trace info when present on the audit anchor,
            # applying confidentiality-based filtering
            if anchor.reasoning_trace is not None:
                from eatp.reasoning import ConfidentialityLevel

                if (
                    anchor.reasoning_trace.confidentiality
                    <= ConfidentialityLevel.RESTRICTED
                ):
                    entry["anchor"][
                        "reasoning_trace"
                    ] = anchor.reasoning_trace.to_dict()
                # else CONFIDENTIAL/SECRET/TOP_SECRET: omit full trace
            if anchor.reasoning_trace_hash is not None:
                entry["anchor"]["reasoning_trace_hash"] = anchor.reasoning_trace_hash
            serialized.append(entry)

        return {
            "records": serialized,
            "total_returned": len(serialized),
            "filters_applied": {
                "agent_id": agent_id,
                "action": action,
                "limit": limit,
            },
        }

    async def _tool_delegate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        eatp_delegate: Delegate capabilities from one agent to another.

        Requires TrustOperations to be configured. Creates a signed
        delegation record in the trust store. Optionally attaches a
        reasoning trace explaining WHY the delegation was made.

        Args:
            params: {"from_agent": str, "to_agent": str,
                     "capabilities": [str], "constraints": dict?,
                     "reasoning_decision": str?, "reasoning_rationale": str?,
                     "reasoning_confidentiality": str?}

        Returns:
            {"delegation_id": str, "from_agent": str, "to_agent": str, ...}
        """
        from_agent = params.get("from_agent")
        to_agent = params.get("to_agent")
        capabilities = params.get("capabilities")
        constraints = params.get("constraints")

        if not from_agent or not isinstance(from_agent, str):
            return {"error": "from_agent is required and must be a string"}
        if not to_agent or not isinstance(to_agent, str):
            return {"error": "to_agent is required and must be a string"}
        if not capabilities or not isinstance(capabilities, list):
            return {"error": "capabilities is required and must be a list of strings"}
        for cap in capabilities:
            if not isinstance(cap, str):
                return {
                    "error": f"Each capability must be a string, got: {type(cap).__name__}"
                }

        if self._ops is None:
            return {
                "error": (
                    "Delegation requires a TrustOperations instance. "
                    "Initialize EATPMCPServer with trust_ops parameter."
                )
            }

        # Build metadata with constraint_overrides if provided
        metadata: Dict[str, Any] = {}
        additional_constraints: List[str] = []
        if constraints and isinstance(constraints, dict):
            metadata["constraint_overrides"] = constraints
            additional_constraints = [f"{k}={v}" for k, v in constraints.items()]

        # Build reasoning trace from optional parameters
        reasoning_trace: Optional[ReasoningTrace] = None
        reasoning_decision = params.get("reasoning_decision")
        reasoning_rationale = params.get("reasoning_rationale")
        if reasoning_decision and reasoning_rationale:
            conf_str = params.get("reasoning_confidentiality", "restricted")
            try:
                confidentiality = ConfidentialityLevel(conf_str)
            except ValueError:
                return {
                    "error": (
                        f"Invalid reasoning_confidentiality: '{conf_str}'. "
                        f"Must be one of: public, restricted, confidential, "
                        f"secret, top_secret"
                    )
                }
            reasoning_trace = ReasoningTrace(
                decision=reasoning_decision,
                rationale=reasoning_rationale,
                confidentiality=confidentiality,
                timestamp=datetime.now(timezone.utc),
            )

        try:
            delegation = await self._ops.delegate(
                delegator_id=from_agent,
                delegatee_id=to_agent,
                task_id=f"mcp-delegation-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
                capabilities=capabilities,
                additional_constraints=additional_constraints,
                metadata=metadata,
                reasoning_trace=reasoning_trace,
            )
        except TrustChainNotFoundError as exc:
            return {"error": f"Trust chain not found: {exc.agent_id}"}
        except DelegationError as exc:
            return {"error": f"Delegation failed: {exc.message}"}
        except TrustError as exc:
            return {"error": f"Trust error: {exc.message}"}

        result: Dict[str, Any] = {
            "delegation_id": delegation.id,
            "from_agent": delegation.delegator_id,
            "to_agent": delegation.delegatee_id,
            "capabilities_delegated": delegation.capabilities_delegated,
            "constraint_subset": delegation.constraint_subset,
            "delegated_at": delegation.delegated_at.isoformat(),
            "expires_at": (
                delegation.expires_at.isoformat() if delegation.expires_at else None
            ),
            "delegation_depth": delegation.delegation_depth,
        }

        # Include reasoning trace confirmation if it was provided
        if reasoning_trace is not None:
            result["reasoning_trace"] = {
                "decision": reasoning_trace.decision,
                "rationale": reasoning_trace.rationale,
                "confidentiality": reasoning_trace.confidentiality.value,
                "timestamp": reasoning_trace.timestamp.isoformat(),
            }

        return result

    async def _tool_revoke(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        eatp_revoke: Revoke a delegation.

        Locates the delegation across all chains in the store and revokes
        it. When cascade=True, also revokes downstream agents.

        Args:
            params: {"delegation_id": str, "cascade": bool?}

        Returns:
            {"revoked": bool, "delegation_id": str, "cascade_revoked": [...]}
        """
        delegation_id = params.get("delegation_id")
        cascade = params.get("cascade", False)

        if not delegation_id or not isinstance(delegation_id, str):
            return {"error": "delegation_id is required and must be a string"}
        if not isinstance(cascade, bool):
            cascade = False

        if self._ops is None:
            return {
                "error": (
                    "Revocation requires a TrustOperations instance. "
                    "Initialize EATPMCPServer with trust_ops parameter."
                )
            }

        # Find the delegation across all chains
        delegatee_id: Optional[str] = None
        delegator_id: Optional[str] = None
        all_chains = await self._store.list_chains()
        for chain in all_chains:
            for delegation in chain.delegations:
                if delegation.id == delegation_id:
                    delegatee_id = chain.genesis.agent_id
                    delegator_id = delegation.delegator_id
                    break
            if delegatee_id:
                break

        if delegatee_id is None:
            return {
                "error": f"Delegation not found: {delegation_id}",
                "delegation_id": delegation_id,
            }

        cascade_revoked: List[str] = []

        try:
            if cascade:
                # Cascade revocation from the delegatee
                cascade_revoked = await self._ops.revoke_cascade(
                    agent_id=delegatee_id,
                    reason=f"Cascade revocation from delegation {delegation_id}",
                )
            else:
                # Revoke single delegation
                await self._ops.revoke_delegation(
                    delegation_id=delegation_id,
                    delegatee_id=delegatee_id,
                )
        except DelegationError as exc:
            return {"error": f"Revocation failed: {exc.message}"}
        except TrustError as exc:
            return {"error": f"Trust error: {exc.message}"}

        return {
            "revoked": True,
            "delegation_id": delegation_id,
            "delegatee_id": delegatee_id,
            "delegator_id": delegator_id,
            "cascade": cascade,
            "cascade_revoked": cascade_revoked,
        }

    # ------------------------------------------------------------------
    # Transport: stdio
    # ------------------------------------------------------------------

    async def serve_stdio(self) -> None:
        """
        Serve the MCP protocol over stdio (stdin/stdout).

        Reads newline-delimited JSON-RPC messages from stdin, dispatches
        them, and writes responses to stdout. Runs until stdin is closed
        or an unrecoverable error occurs.

        Stderr is used for logging; stdout is reserved for JSON-RPC only.
        """
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(
            lambda: protocol, sys.stdin.buffer
        )

        (
            writer_transport,
            writer_protocol,
        ) = await asyncio.get_event_loop().connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout.buffer
        )
        writer = asyncio.StreamWriter(
            writer_transport, writer_protocol, None, asyncio.get_event_loop()
        )

        logger.info("EATP MCP Server started on stdio")

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break  # EOF

                raw = line.decode("utf-8").strip()
                if not raw:
                    continue

                response = await self.handle_message(raw)
                if response is not None:
                    writer.write((response + "\n").encode("utf-8"))
                    await writer.drain()
        except asyncio.CancelledError:
            logger.info("EATP MCP Server shutting down")
        except Exception:
            logger.exception("EATP MCP Server error")
        finally:
            writer.close()
            logger.info("EATP MCP Server stopped")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_server(
    trust_store: Optional[TrustStore] = None,
    trust_ops: Optional[TrustOperations] = None,
    audit_store: Optional[AppendOnlyAuditStore] = None,
    posture_machine: Optional[PostureStateMachine] = None,
    enforcer: Optional[StrictEnforcer] = None,
    authorities_dir: Optional[str] = None,
) -> None:
    """
    Run the EATP MCP server on stdio.

    Convenience entry point that creates an EATPMCPServer and starts
    serving over stdin/stdout. Defaults to InMemoryTrustStore when
    no store is provided.

    Args:
        trust_store: Trust chain storage backend. Defaults to InMemoryTrustStore.
        trust_ops: Optional TrustOperations for delegate/revoke/full verify.
        audit_store: Optional audit store for eatp_audit_query.
        posture_machine: Optional PostureStateMachine for scoring.
        enforcer: Optional StrictEnforcer for verdict classification.
        authorities_dir: Optional path to the directory containing authority
            JSON files. Used by the ``eatp://authorities`` resource.

    Example:
        >>> import asyncio
        >>> from eatp.mcp.server import run_server
        >>> asyncio.run(run_server())
    """
    server = EATPMCPServer(
        trust_store=trust_store,
        trust_ops=trust_ops,
        audit_store=audit_store,
        posture_machine=posture_machine,
        enforcer=enforcer,
        authorities_dir=authorities_dir,
    )
    await server.serve_stdio()


__all__ = [
    "EATPMCPServer",
    "run_server",
]
