#!/usr/bin/env python3
# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""TrustPlane pre-tool hook for Cursor IDE.

Intercepts tool calls via Cursor's hook mechanism and forwards them to the
TrustPlane MCP server for constraint checking.

Behavior by enforcement mode:
- **shadow**: Logs verdicts but never blocks. All actions proceed.
- **strict**: Blocks on HELD or BLOCKED verdicts. Returns a JSON decision
  to Cursor indicating whether the tool call should proceed.

The hook reads a JSON payload from stdin describing the tool call,
contacts the TrustPlane MCP server, and writes a JSON decision to stdout.

Installation:
    This script is installed automatically by ``attest integration setup cursor``.
    It is placed at ``.cursor/hooks/trustplane_hook.py``.

Environment variables:
    TRUSTPLANE_DIR: Path to the trust-plane directory (default: ./trust-plane)
    TRUSTPLANE_MODE: Enforcement mode — "shadow" or "strict" (default: shadow)
    TRUSTPLANE_HOOK_LOG: Path to the hook log file (default: .cursor/trustplane-hook.log)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Tool names that are gated (require trust_check before execution)
_GATED_TOOLS = frozenset(
    {
        "Edit",
        "Write",
        "Bash",
        "Delete",
        "file_editor",
        "write_file",
        "run_terminal_cmd",
        "codebase_search",
    }
)

# Map Cursor tool names to trust-plane action categories
_TOOL_ACTION_MAP: dict[str, str] = {
    "Edit": "write_file",
    "Write": "write_file",
    "file_editor": "write_file",
    "write_file": "write_file",
    "Delete": "delete_file",
    "Bash": "run_command",
    "run_terminal_cmd": "run_command",
    "codebase_search": "access_data",
}


def _get_trust_dir() -> Path:
    """Resolve the trust-plane directory."""
    return Path(os.environ.get("TRUSTPLANE_DIR", "./trust-plane"))


def _get_enforcement_mode() -> str:
    """Resolve the enforcement mode."""
    mode = os.environ.get("TRUSTPLANE_MODE", "shadow")
    if mode not in ("shadow", "strict"):
        return "shadow"
    return mode


def _extract_resource(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Extract the resource path from a tool call.

    Args:
        tool_name: Name of the tool being called.
        tool_input: The tool's input parameters.

    Returns:
        The resource path, or an empty string if not determinable.
    """
    # File-based tools
    if tool_name in ("Edit", "Write", "file_editor", "write_file", "Delete"):
        return tool_input.get("file_path", tool_input.get("target_file", ""))

    # Command-based tools
    if tool_name in ("Bash", "run_terminal_cmd"):
        return tool_input.get("command", "")

    return ""


def _log_verdict(
    log_path: Path,
    tool_name: str,
    resource: str,
    verdict: str,
    mode: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Append a verdict entry to the hook log file.

    Args:
        log_path: Path to the log file.
        tool_name: Name of the intercepted tool.
        resource: The resource being acted on.
        verdict: The trust_check verdict string.
        mode: Current enforcement mode.
        details: Additional context from the verdict response.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "resource": resource,
        "verdict": verdict,
        "mode": mode,
        "action_taken": (
            "blocked"
            if (mode == "strict" and verdict in ("HELD", "BLOCKED"))
            else "allowed"
        ),
    }
    if details:
        entry["details"] = details

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(log_path), flags, 0o644)
        try:
            f = os.fdopen(fd, "a", encoding="utf-8")
        except Exception:
            os.close(fd)
            raise
        with f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        # Hook logging is best-effort; never crash the hook
        pass


def _check_trust(
    action: str,
    resource: str,
    trust_dir: Path,
) -> dict[str, Any]:
    """Check an action against the TrustPlane constraint envelope.

    Loads the project and runs the synchronous check method.
    Falls back to AUTO_APPROVED if the project cannot be loaded
    (graceful degradation — never crash the hook).

    Args:
        action: The action category (e.g., "write_file").
        resource: The resource being acted on.
        trust_dir: Path to the trust-plane directory.

    Returns:
        A dict with at least a "verdict" key.
    """
    try:
        import asyncio

        from trustplane.project import TrustProject

        project = asyncio.run(TrustProject.load(trust_dir))
        context: dict[str, Any] = {}
        if resource:
            context["resource"] = resource

        verdict = project.check(action, context)
        return {
            "verdict": verdict.value if hasattr(verdict, "value") else str(verdict),
            "action": action,
            "resource": resource,
            "posture": project.posture.value,
        }
    except FileNotFoundError:
        # No project initialized — allow everything
        return {"verdict": "AUTO_APPROVED", "reason": "no trust-plane project found"}
    except Exception as exc:
        # Graceful degradation: never block on hook errors
        return {
            "verdict": "AUTO_APPROVED",
            "reason": f"trust-plane check failed: {exc}",
        }


def process_hook(input_data: dict[str, Any]) -> dict[str, Any]:
    """Process a single hook invocation.

    This is the main entry point for the hook logic, separated from
    stdin/stdout handling for testability.

    Args:
        input_data: The parsed JSON from Cursor's hook mechanism,
            containing ``tool_name`` and ``tool_input``.

    Returns:
        A decision dict with ``"decision"`` (``"allow"`` or ``"block"``)
        and optionally ``"reason"``.
    """
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Only gate specific tools
    if tool_name not in _GATED_TOOLS:
        return {"decision": "allow"}

    trust_dir = _get_trust_dir()
    mode = _get_enforcement_mode()
    action = _TOOL_ACTION_MAP.get(tool_name, "unknown")
    resource = _extract_resource(tool_name, tool_input)

    # Prevent direct modification of trust infrastructure
    if tool_name in ("Edit", "Write", "file_editor", "write_file") and resource:
        trust_dir_str = str(trust_dir)
        if trust_dir_str in resource or "trust-plane/" in resource:
            log_path = Path(
                os.environ.get("TRUSTPLANE_HOOK_LOG", ".cursor/trustplane-hook.log")
            )
            _log_verdict(log_path, tool_name, resource, "BLOCKED", mode)
            return {
                "decision": "block",
                "reason": (
                    "Direct modification of trust-plane/ directory is not allowed. "
                    "Use TrustPlane MCP tools instead."
                ),
            }

    # Check against constraint envelope
    verdict_response = _check_trust(action, resource, trust_dir)
    verdict = verdict_response.get("verdict", "AUTO_APPROVED")

    # Log the verdict
    log_path = Path(
        os.environ.get("TRUSTPLANE_HOOK_LOG", ".cursor/trustplane-hook.log")
    )
    _log_verdict(log_path, tool_name, resource, verdict, mode, verdict_response)

    # Enforce based on mode
    if mode == "strict" and verdict in ("HELD", "BLOCKED"):
        reason = f"Action '{action}' on '{resource}' received verdict: {verdict}."
        if verdict == "HELD":
            reason += " This action requires human approval. Run 'attest hold list' to see pending holds."
        elif verdict == "BLOCKED":
            reason += " This action is blocked by the constraint envelope."
        return {"decision": "block", "reason": reason}

    # Shadow mode or AUTO_APPROVED/FLAGGED: allow
    return {"decision": "allow"}


def main() -> None:
    """Entry point: read hook payload from stdin, write decision to stdout."""
    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        # Cannot parse input — allow to avoid breaking the IDE
        print(json.dumps({"decision": "allow"}))
        return

    decision = process_hook(input_data)
    print(json.dumps(decision))


if __name__ == "__main__":
    main()
