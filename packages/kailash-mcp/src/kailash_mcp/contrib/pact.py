# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""PACT contributor for the kailash-platform MCP server.

Provides organizational hierarchy introspection by reading PACT org
definition files (JSON or YAML).

Tools registered:
    - ``pact.org_tree`` (Tier 1): Organizational hierarchy
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["register_tools"]


# ---------------------------------------------------------------------------
# Org definition reader
# ---------------------------------------------------------------------------

# Candidate filenames for PACT org definition, in priority order.
_ORG_FILE_CANDIDATES = [
    "pact.json",
    "pact.yaml",
    "pact.yml",
    ".pact/org.json",
    ".pact/org.yaml",
    ".pact/org.yml",
]


def _find_org_definition(
    project_root: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """Find and parse a PACT org definition file.

    Returns:
        Tuple of (parsed data, source filename) or (None, None) if not found.
    """
    for candidate in _ORG_FILE_CANDIDATES:
        filepath = project_root / candidate
        if not filepath.exists():
            continue

        try:
            content = filepath.read_text(encoding="utf-8")
        except OSError:
            continue

        if candidate.endswith(".json"):
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    return data, candidate
            except json.JSONDecodeError:
                continue
        elif candidate.endswith((".yaml", ".yml")):
            try:
                import yaml

                data = yaml.safe_load(content)
                if isinstance(data, dict):
                    return data, candidate
            except (ImportError, Exception):
                continue

    return None, None


def _extract_org_tree(data: dict[str, Any]) -> dict[str, Any]:
    """Extract a normalized org tree from parsed PACT data.

    Handles various data shapes:
    - departments as list of dicts with name/roles/teams
    - departments as list of strings
    - roles as list of strings or a single string
    """
    # Detect org name from multiple possible keys
    org_name = data.get("org_name") or data.get("org") or data.get("name")

    raw_departments = data.get("departments", [])
    departments: list[dict[str, Any]] = []
    total_roles = 0
    total_addresses = 0

    if not isinstance(raw_departments, list):
        raw_departments = []

    for dept in raw_departments:
        if isinstance(dept, str):
            departments.append({"name": dept, "roles": [], "teams": []})
            continue

        if not isinstance(dept, dict):
            continue

        dept_name = dept.get("name", "unnamed")
        raw_roles = dept.get("roles", [])
        if isinstance(raw_roles, str):
            raw_roles = [raw_roles]
        if not isinstance(raw_roles, list):
            raw_roles = []

        total_roles += len(raw_roles)
        total_addresses += len(raw_roles)

        raw_teams = dept.get("teams", [])
        if not isinstance(raw_teams, list):
            raw_teams = []

        teams: list[dict[str, Any]] = []
        for team in raw_teams:
            if isinstance(team, str):
                teams.append({"name": team, "roles": []})
                continue
            if not isinstance(team, dict):
                continue
            team_name = team.get("name", "unnamed")
            team_roles = team.get("roles", [])
            if isinstance(team_roles, str):
                team_roles = [team_roles]
            if not isinstance(team_roles, list):
                team_roles = []
            total_roles += len(team_roles)
            total_addresses += len(team_roles)
            teams.append({"name": team_name, "roles": team_roles})

        departments.append(
            {
                "name": dept_name,
                "roles": raw_roles,
                "teams": teams,
            }
        )

    return {
        "org_name": org_name,
        "departments": departments,
        "total_roles": total_roles,
        "total_addresses": total_addresses,
    }


# ---------------------------------------------------------------------------
# register_tools
# ---------------------------------------------------------------------------


def register_tools(server: Any, project_root: Path, namespace: str) -> None:
    """Register PACT tools on the MCP server."""

    @server.tool(name=f"{namespace}.org_tree")
    async def org_tree() -> dict:
        """Read the PACT organizational hierarchy for this project.

        Returns departments, teams, and roles defined in the PACT
        org definition file (pact.json, pact.yaml, or .pact/org.json).
        """
        data, source = _find_org_definition(project_root)
        if data is None:
            return {
                "org_name": None,
                "departments": [],
                "total_roles": 0,
                "total_addresses": 0,
                "scan_metadata": {
                    "method": "file_read",
                    "source": None,
                    "limitations": ["No PACT org definition file found"],
                },
            }

        result = _extract_org_tree(data)
        result["scan_metadata"] = {
            "method": "file_read",
            "source": source,
            "limitations": [
                "Reads static org definition; runtime governance state not accessible"
            ],
        }
        return result
