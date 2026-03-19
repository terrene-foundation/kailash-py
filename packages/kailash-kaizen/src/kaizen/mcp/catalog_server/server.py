from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Catalog MCP Server -- JSON-RPC over stdio.

Exposes Kaizen agent catalog operations as MCP tools:
    - Discovery (4): catalog_search, catalog_describe, catalog_schema, catalog_deps
    - Deployment (3): deploy_agent, deploy_status, catalog_deregister
    - Application (2): app_register, app_status
    - Governance (2): validate_composition, budget_status

Protocol flow (MCP specification):
    1. Client sends ``initialize`` -> server responds with capabilities
    2. Client sends ``notifications/initialized`` -> no response
    3. Client sends ``tools/list`` -> server responds with 11 tool definitions
    4. Client sends ``tools/call`` with tool name and arguments
    5. Server executes the tool and returns result content

Transport: stdio (read JSON-RPC from stdin, write responses to stdout).
"""

import json
import logging
import sys
from collections import deque
from typing import Any, Dict, List, Optional

from kaizen.mcp.catalog_server.registry import LocalRegistry

logger = logging.getLogger(__name__)

__all__ = ["CatalogMCPServer"]

# ---------------------------------------------------------------------------
# JSON-RPC constants
# ---------------------------------------------------------------------------

_JSONRPC_VERSION = "2.0"
_MCP_PROTOCOL_VERSION = "2024-11-05"

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
    # --- Discovery tools ---
    {
        "name": "catalog_search",
        "description": (
            "Search the agent catalog by query string, capabilities, type, "
            "or status.  Returns a list of matching agents."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Substring to match against agent name or description",
                },
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter agents that have ALL of these capabilities",
                },
                "type": {
                    "type": "string",
                    "description": "Filter by agent type (substring match on class_name)",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by exact status (e.g. 'registered', 'deployed')",
                },
            },
        },
    },
    {
        "name": "catalog_describe",
        "description": (
            "Get the full detail record for a specific agent by name, "
            "including capabilities, tools, module path, and governance."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The agent name to look up",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "catalog_schema",
        "description": (
            "Retrieve the input and output JSON Schema for an agent.  "
            "Returns the schemas if declared in the agent's manifest."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The agent name to look up",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "catalog_deps",
        "description": (
            "Get the dependency graph for a composite agent.  "
            "Accepts a list of agent descriptors and validates the DAG."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agents": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "inputs_from": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["name"],
                    },
                    "description": "Agent descriptors with name and inputs_from dependencies",
                },
            },
            "required": ["agents"],
        },
    },
    # --- Deployment tools ---
    {
        "name": "deploy_agent",
        "description": (
            "Deploy an agent from an inline TOML manifest string.  "
            "Parses the manifest and registers the agent.  "
            "File paths are NOT accepted -- pass the TOML content directly."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "manifest_toml": {
                    "type": "string",
                    "description": (
                        "The TOML manifest content as a string.  "
                        "Must contain an [agent] section."
                    ),
                },
            },
            "required": ["manifest_toml"],
        },
    },
    {
        "name": "deploy_status",
        "description": "Query the deployment status of an agent by name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The agent name to query",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "catalog_deregister",
        "description": "Remove an agent from the catalog registry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The agent name to deregister",
                },
            },
            "required": ["name"],
        },
    },
    # --- Application tools ---
    {
        "name": "app_register",
        "description": (
            "Register an application that uses one or more agents.  "
            "Accepts application metadata including owner, budget, and "
            "list of agents requested."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Application name",
                },
                "description": {
                    "type": "string",
                    "description": "Application description",
                },
                "owner": {
                    "type": "string",
                    "description": "Application owner email or identifier",
                },
                "org_unit": {
                    "type": "string",
                    "description": "Organizational unit (optional)",
                },
                "agents_requested": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of agent names this application needs",
                },
                "budget_monthly_microdollars": {
                    "type": "integer",
                    "description": "Monthly budget cap in microdollars (1 USD = 1,000,000)",
                },
                "justification": {
                    "type": "string",
                    "description": "Justification for requesting these agents",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "app_status",
        "description": "Query the status of a registered application by name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The application name to query",
                },
            },
            "required": ["name"],
        },
    },
    # --- Governance tools ---
    {
        "name": "validate_composition",
        "description": (
            "Validate a composite agent pipeline.  Checks the DAG for "
            "cycles and optionally validates schema compatibility between "
            "connected agents."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agents": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "inputs_from": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "output_schema": {"type": "object"},
                            "input_schema": {"type": "object"},
                        },
                        "required": ["name"],
                    },
                    "description": "Agent descriptors for the composition",
                },
            },
            "required": ["agents"],
        },
    },
    {
        "name": "budget_status",
        "description": (
            "Query budget tracking status.  Returns current budget "
            "allocation and usage for a named scope (agent or application)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": "The budget scope name (agent or application name)",
                },
                "budget_microdollars": {
                    "type": "integer",
                    "description": "Total budget allocation in microdollars (optional)",
                },
                "spent_microdollars": {
                    "type": "integer",
                    "description": "Amount already spent in microdollars (optional)",
                },
            },
            "required": ["scope"],
        },
    },
]


# ---------------------------------------------------------------------------
# Built-in agent catalog
# ---------------------------------------------------------------------------

_BUILTIN_AGENTS: List[Dict[str, Any]] = [
    {
        "name": "simple-qa",
        "description": "Simple question-answering agent",
        "capabilities": ["qa"],
        "tools": [],
        "manifest_version": "1.0",
        "module": "kaizen.agents.specialized.simple_qa",
        "class_name": "SimpleQAAgent",
    },
    {
        "name": "react-agent",
        "description": "ReAct reasoning agent",
        "capabilities": ["reasoning", "tool_use"],
        "tools": [],
        "manifest_version": "1.0",
        "module": "kaizen.agents.specialized.react",
        "class_name": "ReActAgent",
    },
    {
        "name": "chain-of-thought",
        "description": "Chain of thought reasoning agent",
        "capabilities": ["reasoning"],
        "tools": [],
        "manifest_version": "1.0",
        "module": "kaizen.agents.specialized.cot",
        "class_name": "ChainOfThoughtAgent",
    },
    {
        "name": "planning-agent",
        "description": "Planning and task decomposition agent",
        "capabilities": ["planning"],
        "tools": [],
        "manifest_version": "1.0",
        "module": "kaizen.agents.specialized.planning",
        "class_name": "PlanningAgent",
    },
    {
        "name": "rag-research",
        "description": "RAG-based research agent",
        "capabilities": ["research", "rag"],
        "tools": [],
        "manifest_version": "1.0",
        "module": "kaizen.agents.specialized.rag",
        "class_name": "RAGResearchAgent",
    },
    {
        "name": "code-gen",
        "description": "Code generation agent",
        "capabilities": ["code_generation"],
        "tools": [],
        "manifest_version": "1.0",
        "module": "kaizen.agents.specialized.codegen",
        "class_name": "CodeGenAgent",
    },
    {
        "name": "memory-agent",
        "description": "Agent with persistent memory",
        "capabilities": ["memory"],
        "tools": [],
        "manifest_version": "1.0",
        "module": "kaizen.agents.specialized.memory",
        "class_name": "MemoryAgent",
    },
    {
        "name": "vision-agent",
        "description": "Vision and image analysis agent",
        "capabilities": ["vision", "image_analysis"],
        "tools": [],
        "manifest_version": "1.0",
        "module": "kaizen.agents.specialized.vision",
        "class_name": "VisionAgent",
    },
    {
        "name": "debate-agent",
        "description": "Multi-agent debate coordinator",
        "capabilities": ["debate", "coordination"],
        "tools": [],
        "manifest_version": "1.0",
        "module": "kaizen.workflows.debate",
        "class_name": "DebateWorkflow",
    },
    {
        "name": "consensus-agent",
        "description": "Multi-agent consensus builder",
        "capabilities": ["consensus", "coordination"],
        "tools": [],
        "manifest_version": "1.0",
        "module": "kaizen.workflows.consensus",
        "class_name": "ConsensusWorkflow",
    },
]


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


class CatalogMCPServer:
    """MCP server for Kaizen tool agent catalog operations.

    Implements the MCP JSON-RPC protocol over stdio with 11 tools
    for agent discovery, deployment, application management, and
    governance validation.
    """

    def __init__(self, registry_dir: Optional[str] = None) -> None:
        self._registry = LocalRegistry(registry_dir=registry_dir)
        self._request_log: deque = deque(maxlen=10_000)
        self._initialized = False
        self._seed_builtin_agents()

    def _seed_builtin_agents(self) -> None:
        """Pre-seed catalog with Kaizen's built-in agent types."""
        for agent in _BUILTIN_AGENTS:
            try:
                self._registry.register(dict(agent))
            except ValueError:
                pass  # Already registered (duplicate name)

    # ------------------------------------------------------------------
    # JSON-RPC dispatch
    # ------------------------------------------------------------------

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a JSON-RPC request and return the response.

        Returns an empty dict for notifications (no id field expected).
        """
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        self._request_log.append({"method": method, "id": req_id})

        if method == "initialize":
            self._initialized = True
            return self._ok(
                req_id,
                {
                    "protocolVersion": _MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "kaizen-catalog", "version": "1.0.0"},
                },
            )

        if method == "notifications/initialized":
            return {}  # Notification -- no response

        if method == "tools/list":
            return self._ok(req_id, {"tools": _TOOL_DEFINITIONS})

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            return self._dispatch_tool(req_id, tool_name, arguments)

        return self._error(req_id, _METHOD_NOT_FOUND, f"Method not found: {method}")

    def _dispatch_tool(
        self, req_id: Any, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch to the appropriate tool handler."""
        handlers = self._tool_handlers
        handler = handlers.get(tool_name)
        if handler is None:
            return self._error(req_id, _INVALID_PARAMS, f"Unknown tool: {tool_name}")
        try:
            result = handler(arguments)
            return self._ok(
                req_id,
                {
                    "content": [
                        {"type": "text", "text": json.dumps(result, default=str)}
                    ]
                },
            )
        except (ValueError, KeyError, TypeError) as exc:
            # Expected validation errors — safe to return message to client
            return self._ok(
                req_id,
                {
                    "content": [
                        {"type": "text", "text": json.dumps({"error": str(exc)})}
                    ],
                    "isError": True,
                },
            )
        except Exception:
            # Unexpected errors — sanitize to avoid leaking internals
            logger.exception("Tool %s failed", tool_name)
            return self._ok(
                req_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "error": "Internal tool error. Check server logs for details."
                                }
                            ),
                        }
                    ],
                    "isError": True,
                },
            )

    @property
    def _tool_handlers(self) -> Dict[str, Any]:
        """Lazily-constructed mapping of tool name -> handler callable."""
        from kaizen.mcp.catalog_server.tools.application import (
            handle_app_register,
            handle_app_status,
        )
        from kaizen.mcp.catalog_server.tools.deployment import (
            handle_catalog_deregister,
            handle_deploy_agent,
            handle_deploy_status,
        )
        from kaizen.mcp.catalog_server.tools.discovery import (
            handle_catalog_deps,
            handle_catalog_describe,
            handle_catalog_schema,
            handle_catalog_search,
        )
        from kaizen.mcp.catalog_server.tools.governance import (
            handle_budget_status,
            handle_validate_composition,
        )

        return {
            "catalog_search": lambda args: handle_catalog_search(self._registry, args),
            "catalog_describe": lambda args: handle_catalog_describe(
                self._registry, args
            ),
            "catalog_schema": lambda args: handle_catalog_schema(self._registry, args),
            "catalog_deps": lambda args: handle_catalog_deps(self._registry, args),
            "deploy_agent": lambda args: handle_deploy_agent(self._registry, args),
            "deploy_status": lambda args: handle_deploy_status(self._registry, args),
            "catalog_deregister": lambda args: handle_catalog_deregister(
                self._registry, args
            ),
            "app_register": lambda args: handle_app_register(self._registry, args),
            "app_status": lambda args: handle_app_status(self._registry, args),
            "validate_composition": lambda args: handle_validate_composition(args),
            "budget_status": lambda args: handle_budget_status(args),
        }

    # ------------------------------------------------------------------
    # JSON-RPC helpers
    # ------------------------------------------------------------------

    def _ok(self, req_id: Any, result: Any) -> Dict[str, Any]:
        return {"jsonrpc": _JSONRPC_VERSION, "id": req_id, "result": result}

    def _error(self, req_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": _JSONRPC_VERSION,
            "id": req_id,
            "error": {"code": code, "message": message},
        }

    # ------------------------------------------------------------------
    # stdio transport
    # ------------------------------------------------------------------

    def serve_stdio(self) -> None:
        """Run the server on stdin/stdout (line-delimited JSON)."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                if response:  # Notifications return empty dict
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except json.JSONDecodeError:
                error_resp = self._error(None, _PARSE_ERROR, "Parse error")
                sys.stdout.write(json.dumps(error_resp) + "\n")
                sys.stdout.flush()
