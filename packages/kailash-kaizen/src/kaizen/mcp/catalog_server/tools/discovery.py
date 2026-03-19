from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Discovery tool handlers: catalog_search, catalog_describe, catalog_schema, catalog_deps.

Each handler is a pure function that takes the registry and arguments dict,
returning a result dict.  Errors are raised as exceptions and caught by
the server dispatcher.
"""

import logging
from typing import Any, Dict, List

from kaizen.composition.dag_validator import validate_dag
from kaizen.mcp.catalog_server.registry import LocalRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "handle_catalog_search",
    "handle_catalog_describe",
    "handle_catalog_schema",
    "handle_catalog_deps",
]


def handle_catalog_search(
    registry: LocalRegistry, args: Dict[str, Any]
) -> Dict[str, Any]:
    """Search agents by query, capabilities, type, or status.

    Args:
        registry: The agent registry to search.
        args: Tool arguments with optional keys: query, capabilities, type, status.

    Returns:
        Dict with ``agents`` list and ``count``.
    """
    query = args.get("query")
    capabilities = args.get("capabilities")
    agent_type = args.get("type")
    status = args.get("status")

    results = registry.search(
        query=query,
        capabilities=capabilities,
        agent_type=agent_type,
        status=status,
    )

    return {
        "agents": results,
        "count": len(results),
    }


def handle_catalog_describe(
    registry: LocalRegistry, args: Dict[str, Any]
) -> Dict[str, Any]:
    """Get full detail for a specific agent.

    Args:
        registry: The agent registry.
        args: Must contain ``name`` (str).

    Returns:
        Dict with the full agent record, or an error if not found.
    """
    name = args.get("name", "")
    if not name:
        raise ValueError("'name' is required")

    agent = registry.get_agent(name)
    if agent is None:
        raise ValueError(f"Agent {name!r} not found in catalog")

    return {"agent": agent}


def handle_catalog_schema(
    registry: LocalRegistry, args: Dict[str, Any]
) -> Dict[str, Any]:
    """Retrieve input/output JSON Schema for an agent.

    Args:
        registry: The agent registry.
        args: Must contain ``name`` (str).

    Returns:
        Dict with ``input_schema`` and ``output_schema`` (may be empty dicts
        if the agent has not declared schemas).
    """
    name = args.get("name", "")
    if not name:
        raise ValueError("'name' is required")

    agent = registry.get_agent(name)
    if agent is None:
        raise ValueError(f"Agent {name!r} not found in catalog")

    return {
        "name": name,
        "input_schema": agent.get("input_schema", {}),
        "output_schema": agent.get("output_schema", {}),
    }


def handle_catalog_deps(
    registry: LocalRegistry, args: Dict[str, Any]
) -> Dict[str, Any]:
    """Get the dependency graph for a composite agent pipeline.

    Args:
        registry: The agent registry (used for context but DAG comes from args).
        args: Must contain ``agents`` list of descriptors with ``name``
              and optional ``inputs_from``.

    Returns:
        Dict with DAG validation result including ``is_valid``,
        ``topological_order``, ``cycles``, and ``warnings``.
    """
    agents: List[Dict[str, Any]] = args.get("agents", [])
    if not agents:
        return {
            "is_valid": True,
            "topological_order": [],
            "cycles": [],
            "warnings": [],
        }

    result = validate_dag(agents)
    return result.to_dict()
