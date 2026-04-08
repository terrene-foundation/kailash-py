# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Trust contributor for the kailash-platform MCP server.

Provides lightweight trust-plane status by reading the trust-plane directory
(JSON files). Does NOT duplicate the full TrustPlane MCP server functionality.

Tools registered:
    - ``trust.trust_status`` (Tier 1): Current trust plane status
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["register_tools"]


# ---------------------------------------------------------------------------
# Trust status reader
# ---------------------------------------------------------------------------


def _read_trust_status(trust_dir: Path) -> dict[str, Any]:
    """Read trust-plane directory and return status summary.

    This is a lightweight file-read operation. The MCP server runs as a
    separate process and cannot access TrustPlane runtime state.
    """
    if not trust_dir.exists():
        return {
            "posture": None,
            "trust_dir": str(trust_dir),
            "trust_dir_exists": False,
            "has_manifest": False,
            "has_envelope": False,
            "constraint_summary": None,
            "scan_metadata": {
                "method": "file_read",
                "trust_dir": str(trust_dir),
                "limitations": ["Trust-plane directory not found"],
            },
        }

    manifest_path = trust_dir / "manifest.json"
    has_manifest = manifest_path.exists()
    posture = None
    constraint_summary = None

    if has_manifest:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            posture = manifest.get("posture")
            constraints = manifest.get("constraints")
            if isinstance(constraints, dict):
                allowed_tools = constraints.get("allowed_tools")
                constraint_summary = {
                    "max_cost": constraints.get("max_cost"),
                    "allowed_tools": (
                        len(allowed_tools)
                        if isinstance(allowed_tools, list)
                        else allowed_tools
                    ),
                    "blocked_actions": constraints.get("blocked_actions", []),
                }
        except (json.JSONDecodeError, OSError):
            pass

    envelope_path = trust_dir / "envelope.json"
    has_envelope = envelope_path.exists()

    return {
        "posture": posture,
        "trust_dir": str(trust_dir),
        "trust_dir_exists": True,
        "has_manifest": has_manifest,
        "has_envelope": has_envelope,
        "constraint_summary": constraint_summary,
        "scan_metadata": {
            "method": "file_read",
            "trust_dir": str(trust_dir),
            "limitations": [
                "Reads static files only; runtime trust state not accessible from MCP process"
            ],
        },
    }


# ---------------------------------------------------------------------------
# register_tools
# ---------------------------------------------------------------------------


def register_tools(server: Any, project_root: Path, namespace: str) -> None:
    """Register Trust tools on the MCP server."""
    trust_dir = project_root / "trust-plane"

    @server.tool(name=f"{namespace}.trust_status")
    async def trust_status() -> dict:
        """Report current Trust Plane status for this project.

        Reads the trust-plane directory to check posture, manifest,
        and constraint envelope. This is a lightweight status check,
        not a full trust gating tool.
        """
        return _read_trust_status(trust_dir)
