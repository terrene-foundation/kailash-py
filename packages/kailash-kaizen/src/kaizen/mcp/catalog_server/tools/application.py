from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Application tool handlers: app_register, app_status.

Manages application-level registrations that declare which agents
an application needs, its budget, and ownership metadata.
"""

import logging
from typing import Any, Dict, List

from kaizen.mcp.catalog_server.registry import LocalRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "handle_app_register",
    "handle_app_status",
]


def handle_app_register(
    registry: LocalRegistry, args: Dict[str, Any]
) -> Dict[str, Any]:
    """Register an application that uses one or more agents.

    Args:
        registry: The registry instance.
        args: Application metadata.  Must contain ``name`` (str).
              Optional: description, owner, org_unit, agents_requested,
              budget_monthly_microdollars, justification.

    Returns:
        Dict with the registered application record and any warnings
        about requested agents not found in the catalog.
    """
    name = args.get("name", "")
    if not name:
        raise ValueError("'name' is required")

    # Validate that requested agents exist (warnings, not errors)
    agents_requested: List[str] = list(args.get("agents_requested", []))
    warnings: List[str] = []
    for agent_name in agents_requested:
        if registry.get_agent(agent_name) is None:
            warnings.append(
                f"Requested agent {agent_name!r} is not currently registered"
            )

    app_data: Dict[str, Any] = {
        "name": name,
        "description": args.get("description", ""),
        "owner": args.get("owner", ""),
        "org_unit": args.get("org_unit"),
        "agents_requested": agents_requested,
        "budget_monthly_microdollars": args.get("budget_monthly_microdollars"),
        "justification": args.get("justification", ""),
    }

    record = registry.register_app(app_data)
    result: Dict[str, Any] = {"application": record, "action": "registered"}
    if warnings:
        result["warnings"] = warnings
    return result


def handle_app_status(registry: LocalRegistry, args: Dict[str, Any]) -> Dict[str, Any]:
    """Query the status of a registered application.

    Args:
        registry: The registry instance.
        args: Must contain ``name`` (str).

    Returns:
        Dict with the application record or not-found status.
    """
    name = args.get("name", "")
    if not name:
        raise ValueError("'name' is required")

    app = registry.get_app(name)
    if app is None:
        return {"name": name, "found": False, "status": "not_found"}

    return {
        "name": name,
        "found": True,
        "application": app,
    }
