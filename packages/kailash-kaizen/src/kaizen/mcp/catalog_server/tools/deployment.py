from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Deployment tool handlers: deploy_agent, deploy_status, catalog_deregister.

Security:
    - ``deploy_agent`` accepts inline TOML content ONLY.  Anything that
      looks like a file path (contains ``/``, ``\\``, or ends with
      ``.toml`` without TOML section markers) is rejected (RT-06).
    - Agent names are validated via ``_VALID_NAME_RE`` in the registry.
"""

import logging
import re
from typing import Any, Dict

from kaizen.manifest.agent import AgentManifest
from kaizen.mcp.catalog_server.registry import LocalRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "handle_deploy_agent",
    "handle_deploy_status",
    "handle_catalog_deregister",
]

# Pattern that suggests the input is a file path rather than TOML content
_FILE_PATH_INDICATORS = re.compile(r"[\\/]")


def _looks_like_file_path(content: str) -> bool:
    """Return True if *content* appears to be a file path rather than TOML.

    Heuristic: if the string contains path separators and does NOT contain
    a TOML section header (``[something]``), it is likely a file path.
    """
    stripped = content.strip()
    has_path_sep = bool(_FILE_PATH_INDICATORS.search(stripped))
    has_toml_section = bool(re.search(r"^\[", stripped, re.MULTILINE))

    if has_path_sep and not has_toml_section:
        return True

    # Bare filename ending in .toml without TOML content
    if stripped.endswith(".toml") and not has_toml_section:
        return True

    return False


def handle_deploy_agent(
    registry: LocalRegistry, args: Dict[str, Any]
) -> Dict[str, Any]:
    """Deploy an agent from an inline TOML manifest string.

    Args:
        registry: The agent registry.
        args: Must contain ``manifest_toml`` (str) with TOML content.

    Returns:
        Dict with the deployed agent record.

    Raises:
        ValueError: If the input looks like a file path (RT-06) or
            if the TOML is invalid / missing required fields.
    """
    manifest_toml = args.get("manifest_toml", "")
    if not manifest_toml or not manifest_toml.strip():
        raise ValueError("'manifest_toml' is required and must be non-empty")

    # RT-06: reject file paths
    if _looks_like_file_path(manifest_toml):
        raise ValueError(
            "File paths are not accepted.  Pass the TOML manifest content "
            "as a string, not a file path."
        )

    # Parse the TOML content into an AgentManifest
    manifest = AgentManifest.from_toml_str(manifest_toml)

    # Convert to registry record and register
    agent_data = manifest.to_dict()
    agent_data["status"] = "deployed"

    # If already registered, deregister first (redeploy)
    existing = registry.get_agent(manifest.name)
    if existing is not None:
        registry.deregister(manifest.name)

    record = registry.register(agent_data)
    return {"agent": record, "action": "deployed"}


def handle_deploy_status(
    registry: LocalRegistry, args: Dict[str, Any]
) -> Dict[str, Any]:
    """Query the deployment status of an agent.

    Args:
        registry: The agent registry.
        args: Must contain ``name`` (str).

    Returns:
        Dict with ``name``, ``status``, and ``found`` fields.
    """
    name = args.get("name", "")
    if not name:
        raise ValueError("'name' is required")

    agent = registry.get_agent(name)
    if agent is None:
        return {"name": name, "found": False, "status": "not_found"}

    return {
        "name": name,
        "found": True,
        "status": agent.get("status", "unknown"),
        "module": agent.get("module", ""),
        "class_name": agent.get("class_name", ""),
    }


def handle_catalog_deregister(
    registry: LocalRegistry, args: Dict[str, Any]
) -> Dict[str, Any]:
    """Remove an agent from the catalog registry.

    Args:
        registry: The agent registry.
        args: Must contain ``name`` (str).

    Returns:
        Dict with ``name`` and ``removed`` status.
    """
    name = args.get("name", "")
    if not name:
        raise ValueError("'name' is required")

    removed = registry.deregister(name)
    return {"name": name, "removed": removed}
