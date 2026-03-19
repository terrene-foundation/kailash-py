from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Self-contained local registry for catalog MCP server.

Provides in-memory agent and application registration with bounded
storage (maxlen-based eviction).  Deliberately avoids importing from
``kaizen.core`` or ``kaizen.agents`` to sidestep the pre-existing
``kailash.nodes.base.Node`` import error.
"""

import logging
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["MemoryRegistry", "LocalRegistry"]

# Agent/application name validation: alphanumeric, hyphens, underscores
_VALID_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,127}$")

# Maximum entries to prevent OOM in long-running processes
_MAX_AGENTS = 10_000
_MAX_APPS = 10_000


def _validate_name(name: str) -> None:
    """Validate a registry name.

    Raises:
        ValueError: If the name does not match the allowed pattern.
    """
    if not _VALID_NAME_RE.match(name):
        raise ValueError(
            f"Invalid name {name!r}: must match ^[a-zA-Z][a-zA-Z0-9_-]{{0,127}}$"
        )


class MemoryRegistry:
    """In-memory registry for agents and applications.

    Bounded to ``_MAX_AGENTS`` / ``_MAX_APPS`` entries with LRU eviction
    (oldest entry removed when capacity is reached).
    """

    def __init__(self, registry_dir: Optional[str] = None) -> None:
        # registry_dir accepted for API compatibility but this is in-memory only
        self._agents: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._apps: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    # ------------------------------------------------------------------
    # Agent operations
    # ------------------------------------------------------------------

    def register(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Register an agent.

        Args:
            agent_data: Dict with at least ``name`` (str).

        Returns:
            The stored agent record.

        Raises:
            ValueError: If the name is invalid or already registered.
        """
        name = agent_data.get("name", "")
        _validate_name(name)

        if name in self._agents:
            raise ValueError(f"Agent {name!r} is already registered")

        # Evict oldest if at capacity
        while len(self._agents) >= _MAX_AGENTS:
            evicted_name, _ = self._agents.popitem(last=False)
            logger.warning("Registry at capacity, evicted agent %r", evicted_name)

        record: Dict[str, Any] = {
            "name": name,
            "description": agent_data.get("description", ""),
            "capabilities": list(agent_data.get("capabilities", [])),
            "tools": list(agent_data.get("tools", [])),
            "manifest_version": agent_data.get("manifest_version", "1.0"),
            "module": agent_data.get("module", ""),
            "class_name": agent_data.get("class_name", ""),
            "status": agent_data.get("status", "registered"),
            "supported_models": list(agent_data.get("supported_models", [])),
        }

        # Preserve governance if present
        gov = agent_data.get("governance")
        if gov is not None:
            record["governance"] = dict(gov)

        # Preserve input_schema / output_schema if present
        for key in ("input_schema", "output_schema"):
            if key in agent_data:
                record[key] = agent_data[key]

        self._agents[name] = record
        logger.debug("Registered agent %r", name)
        return record

    def get_agent(self, name: str) -> Optional[Dict[str, Any]]:
        """Look up an agent by name.  Returns None if not found."""
        return self._agents.get(name)

    def deregister(self, name: str) -> bool:
        """Remove an agent from the registry.

        Returns:
            True if the agent was found and removed, False otherwise.
        """
        if name in self._agents:
            del self._agents[name]
            logger.debug("Deregistered agent %r", name)
            return True
        return False

    def search(
        self,
        *,
        query: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        agent_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search agents with optional filters.

        Args:
            query: Substring match on name or description (case-insensitive).
            capabilities: All listed capabilities must be present.
            agent_type: Substring match on class_name (case-insensitive).
            status: Exact match on status.

        Returns:
            List of matching agent records.
        """
        results: List[Dict[str, Any]] = []

        for agent in self._agents.values():
            # Query filter: fuzzy match on name or description
            if query:
                q_lower = query.lower()
                name_match = q_lower in agent.get("name", "").lower()
                desc_match = q_lower in agent.get("description", "").lower()
                if not name_match and not desc_match:
                    continue

            # Capabilities filter: all must be present
            if capabilities:
                agent_caps = set(agent.get("capabilities", []))
                if not all(cap in agent_caps for cap in capabilities):
                    continue

            # Type filter: substring match on class_name
            if agent_type:
                class_name = agent.get("class_name", "").lower()
                if agent_type.lower() not in class_name:
                    continue

            # Status filter: exact match
            if status:
                if agent.get("status", "") != status:
                    continue

            results.append(agent)

        return results

    def list_agents(self) -> List[Dict[str, Any]]:
        """Return all registered agents."""
        return list(self._agents.values())

    # ------------------------------------------------------------------
    # Application operations
    # ------------------------------------------------------------------

    def register_app(self, app_data: Dict[str, Any]) -> Dict[str, Any]:
        """Register an application.

        Args:
            app_data: Dict with at least ``name`` (str).

        Returns:
            The stored application record.

        Raises:
            ValueError: If the name is invalid or already registered.
        """
        name = app_data.get("name", "")
        _validate_name(name)

        if name in self._apps:
            raise ValueError(f"Application {name!r} is already registered")

        # Evict oldest if at capacity
        while len(self._apps) >= _MAX_APPS:
            evicted_name, _ = self._apps.popitem(last=False)
            logger.warning("App registry at capacity, evicted %r", evicted_name)

        record: Dict[str, Any] = {
            "name": name,
            "description": app_data.get("description", ""),
            "owner": app_data.get("owner", ""),
            "org_unit": app_data.get("org_unit"),
            "agents_requested": list(app_data.get("agents_requested", [])),
            "budget_monthly_microdollars": app_data.get("budget_monthly_microdollars"),
            "justification": app_data.get("justification", ""),
            "status": "registered",
        }
        self._apps[name] = record
        logger.debug("Registered application %r", name)
        return record

    def get_app(self, name: str) -> Optional[Dict[str, Any]]:
        """Look up an application by name.  Returns None if not found."""
        return self._apps.get(name)

    def list_apps(self) -> List[Dict[str, Any]]:
        """Return all registered applications."""
        return list(self._apps.values())


# Backward-compatible alias -- existing code imports ``LocalRegistry``
LocalRegistry = MemoryRegistry
