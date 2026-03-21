# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cursor IDE integration for TrustPlane.

Provides automated setup for integrating TrustPlane with Cursor IDE.
Generates a ``.cursorrules`` file that instructs Cursor's AI to report
tool use to the TrustPlane MCP server, and a hook script that intercepts
tool calls for constraint checking.

Usage:
    attest integration setup cursor

Or programmatically:
    >>> from kailash.trust.plane.integration.cursor import setup_cursor
    >>> setup_cursor(project_dir=Path("."), trust_dir="./trust-plane", mode="shadow")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from string import Template
from typing import Any

from kailash.trust._locking import _safe_write_text, safe_read_text

logger = logging.getLogger(__name__)

__all__ = [
    "generate_cursorrules",
    "generate_hook_script",
    "setup_cursor",
    "configure_mcp_server",
    "CURSORRULES_FILENAME",
]

CURSORRULES_FILENAME = ".cursorrules"
_CURSOR_DIR = ".cursor"
_MCP_CONFIG_FILENAME = "mcp.json"

# Path to the template bundled with this package
_TEMPLATE_PATH = Path(__file__).parent / "cursorrules_template.txt"


def generate_cursorrules(
    mode: str = "shadow",
    trust_dir: str = "./trust-plane",
) -> str:
    """Generate ``.cursorrules`` content from the bundled template.

    Args:
        mode: Enforcement mode — ``"shadow"`` (log only) or ``"strict"``
              (block on HELD/BLOCKED verdicts).
        trust_dir: Path to the trust-plane directory, used in instructions.

    Returns:
        The rendered ``.cursorrules`` content as a string.

    Raises:
        ValueError: If *mode* is not ``"shadow"`` or ``"strict"``.
    """
    if mode not in ("shadow", "strict"):
        raise ValueError(f"Invalid mode: {mode!r}. Must be 'shadow' or 'strict'.")

    template_text = safe_read_text(_TEMPLATE_PATH)
    tmpl = Template(template_text)

    if mode == "shadow":
        enforcement_description = (
            "Shadow mode is active. All actions are LOGGED but never blocked. "
            "The trust-plane records what WOULD have happened under strict "
            "enforcement. You should still call trust_check before actions "
            "to build the observation log."
        )
        on_held = (
            "HELD: Log this verdict. The action WOULD be held under strict mode. "
            "Proceed but note the hold to the user."
        )
        on_blocked = (
            "BLOCKED: Log this verdict. The action WOULD be blocked under strict mode. "
            "Proceed but warn the user that this action violates constraints."
        )
    else:
        enforcement_description = (
            "Strict mode is active. Actions that violate constraints are "
            "HELD or BLOCKED. You MUST call trust_check before any gated "
            "action and respect the verdict."
        )
        on_held = (
            "HELD: Do NOT proceed. Inform the user that this action requires "
            "human approval. Wait for the hold to be resolved via "
            "'attest hold approve <hold_id>'."
        )
        on_blocked = (
            "BLOCKED: Do NOT proceed. Inform the user that this action is "
            "blocked by the constraint envelope. Explain which constraint "
            "was violated."
        )

    return tmpl.safe_substitute(
        MODE=mode,
        TRUST_DIR=trust_dir,
        ENFORCEMENT_DESCRIPTION=enforcement_description,
        ON_HELD=on_held,
        ON_BLOCKED=on_blocked,
    )


def generate_hook_script() -> str:
    """Return the content of the Cursor pre-tool hook script.

    The hook script is a standalone Python script that:
    - Intercepts tool calls via Cursor's hook mechanism (stdin JSON)
    - Forwards them to the TrustPlane MCP server for constraint checking
    - In shadow mode: logs but never blocks
    - In strict mode: blocks on HELD/BLOCKED verdicts

    Returns:
        The hook script content as a string.
    """
    hook_path = Path(__file__).parent / "hook.py"
    return safe_read_text(hook_path)


def configure_mcp_server(
    project_dir: Path,
    trust_dir: str = "./trust-plane",
) -> Path:
    """Write the MCP server configuration for Cursor.

    Creates or updates ``.cursor/mcp.json`` with the TrustPlane MCP
    server entry. Preserves any existing MCP server entries.

    Args:
        project_dir: Root directory of the project.
        trust_dir: Path to the trust-plane directory.

    Returns:
        Path to the written MCP config file.
    """
    cursor_dir = project_dir / _CURSOR_DIR
    cursor_dir.mkdir(parents=True, exist_ok=True)
    config_path = cursor_dir / _MCP_CONFIG_FILENAME

    config: dict[str, Any] = {}
    if config_path.exists():
        try:
            config = json.loads(safe_read_text(config_path))
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not parse existing %s; overwriting.", config_path)
            config = {}

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    config["mcpServers"]["trustplane"] = {
        "command": "trustplane-mcp",
        "args": ["--trust-dir", trust_dir],
    }

    _safe_write_text(config_path, json.dumps(config, indent=2) + "\n")
    logger.info("Wrote MCP config to %s", config_path)
    return config_path


def setup_cursor(
    project_dir: Path,
    trust_dir: str = "./trust-plane",
    mode: str = "shadow",
    merge: bool = False,
) -> dict[str, Any]:
    """Full Cursor IDE setup for TrustPlane integration.

    Performs all setup steps:
    1. Generates ``.cursorrules`` from template
    2. Writes ``.cursorrules`` to project root (merge or overwrite)
    3. Configures MCP server in ``.cursor/mcp.json``
    4. Copies hook script to ``.cursor/hooks/``

    Args:
        project_dir: Root directory of the project.
        trust_dir: Path to the trust-plane directory.
        mode: Enforcement mode — ``"shadow"`` or ``"strict"``.
        merge: If True and ``.cursorrules`` exists, append TrustPlane
               rules. If False, overwrite.

    Returns:
        A dict summarizing what was created/updated.
    """
    result: dict[str, Any] = {
        "cursorrules_action": "created",
        "mcp_configured": False,
        "hook_installed": False,
        "files_written": [],
    }

    # 1. Generate and write .cursorrules
    cursorrules_path = project_dir / CURSORRULES_FILENAME
    new_content = generate_cursorrules(mode=mode, trust_dir=trust_dir)

    if cursorrules_path.exists() and merge:
        existing = safe_read_text(cursorrules_path)
        # Check if TrustPlane section already exists
        if "# TrustPlane Trust Environment" in existing:
            # Replace existing TrustPlane section
            marker_start = "# --- TrustPlane Begin ---"
            marker_end = "# --- TrustPlane End ---"
            if marker_start in existing and marker_end in existing:
                before = existing[: existing.index(marker_start)]
                after = existing[existing.index(marker_end) + len(marker_end) :]
                merged = (
                    before.rstrip()
                    + "\n\n"
                    + marker_start
                    + "\n"
                    + new_content
                    + "\n"
                    + marker_end
                    + after.lstrip("\n")
                )
                _safe_write_text(cursorrules_path, merged)
                result["cursorrules_action"] = "merged (replaced existing section)"
            else:
                # Has TrustPlane content but no markers — overwrite
                _safe_write_text(cursorrules_path, new_content)
                result["cursorrules_action"] = (
                    "overwritten (existing had TrustPlane content)"
                )
        else:
            # Append TrustPlane section with markers
            marker_start = "# --- TrustPlane Begin ---"
            marker_end = "# --- TrustPlane End ---"
            merged = (
                existing.rstrip()
                + "\n\n"
                + marker_start
                + "\n"
                + new_content
                + "\n"
                + marker_end
                + "\n"
            )
            _safe_write_text(cursorrules_path, merged)
            result["cursorrules_action"] = "merged (appended)"
    else:
        _safe_write_text(cursorrules_path, new_content)
        if cursorrules_path.exists():
            result["cursorrules_action"] = "overwritten"
        else:
            result["cursorrules_action"] = "created"

    result["files_written"].append(str(cursorrules_path))

    # 2. Configure MCP server
    mcp_path = configure_mcp_server(project_dir, trust_dir=trust_dir)
    result["mcp_configured"] = True
    result["files_written"].append(str(mcp_path))

    # 3. Install hook script
    hooks_dir = project_dir / _CURSOR_DIR / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_dest = hooks_dir / "trustplane_hook.py"
    hook_content = generate_hook_script()
    _safe_write_text(hook_dest, hook_content)
    result["hook_installed"] = True
    result["files_written"].append(str(hook_dest))

    return result
