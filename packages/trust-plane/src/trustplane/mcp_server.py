# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""TrustPlane MCP Server — trust gating for AI assistants.

Exposes TrustPlane as MCP tools that AI assistants call to check
constraints, record decisions, and query trust status.

The key tool is `trust_check` — the gating function that evaluates
proposed actions against the constraint envelope BEFORE execution.

Usage:
    trustplane-mcp --trust-dir ./trust-plane

Or in Claude Code settings:
    {
        "mcpServers": {
            "trustplane": {
                "command": "trustplane-mcp",
                "args": ["--trust-dir", "./trust-plane"]
            }
        }
    }
"""

import logging
import os
import threading
from pathlib import Path

from mcp.server import FastMCP

from trustplane.models import DecisionRecord, _parse_decision_type
from trustplane.project import ConstraintViolationError, TrustProject

logger = logging.getLogger(__name__)

# Resolve trust directory from environment or default
TRUST_DIR = Path(os.environ.get("TRUSTPLANE_DIR", "./trust-plane"))

mcp = FastMCP(
    "TrustPlane",
    instructions=(
        "TrustPlane provides trust gating for AI operations. "
        "Before performing actions that modify files, create content, "
        "or make decisions, call trust_check to verify the action is "
        "allowed by the constraint envelope. Record significant "
        "decisions with trust_record for audit trail."
    ),
)

# Cache the loaded project to avoid re-loading on every call.
# Protected by _project_lock to prevent concurrent initialization races.
_project: TrustProject | None = None
_manifest_mtime: float = 0.0
_project_lock = threading.Lock()


def _set_project(project: TrustProject) -> None:
    """Set the cached project under the lock (for testing).

    Also updates _manifest_mtime to match the current manifest on disk
    so _get_project() will not immediately reload.
    """
    global _project, _manifest_mtime
    manifest_path = TRUST_DIR / "manifest.json"
    try:
        mtime = manifest_path.stat().st_mtime
    except FileNotFoundError:
        mtime = 0.0
    with _project_lock:
        _project = project
        _manifest_mtime = mtime


def _reset_project() -> None:
    """Clear cached project and mtime under the lock (for testing)."""
    global _project, _manifest_mtime
    with _project_lock:
        _project = None
        _manifest_mtime = 0.0


def _get_manifest_mtime() -> float:
    """Return the current cached manifest mtime (for testing)."""
    with _project_lock:
        return _manifest_mtime


async def _get_project() -> TrustProject:
    """Load or return cached TrustProject.

    Reloads if the manifest file has been modified on disk,
    ensuring constraint envelope changes take effect without restart.

    Thread-safe: uses double-checked locking so the lock is only
    contended during initialization or manifest reload, not on every
    request.
    """
    global _project, _manifest_mtime

    manifest_path = TRUST_DIR / "manifest.json"
    try:
        current_mtime = manifest_path.stat().st_mtime
    except FileNotFoundError:
        current_mtime = 0.0

    # Fast path: project loaded and manifest unchanged — no lock needed.
    cached = _project
    if cached is not None and current_mtime == _manifest_mtime:
        return cached

    # Slow path: need to load or reload — acquire lock.
    with _project_lock:
        # Double-check after acquiring lock: another thread may have
        # already completed the load while we were waiting.
        if _project is not None and current_mtime == _manifest_mtime:
            return _project

        logger.info(
            "Loading TrustProject from %s (mtime changed: %s -> %s)",
            TRUST_DIR,
            _manifest_mtime,
            current_mtime,
        )
        loaded = await TrustProject.load(TRUST_DIR)
        # Update both atomically while holding the lock.
        _project = loaded
        _manifest_mtime = current_mtime
        return _project


@mcp.tool(
    name="trust_check",
    description=(
        "Check whether a proposed action is allowed by the constraint "
        "envelope. Returns a verdict: AUTO_APPROVED, FLAGGED, HELD, "
        "or BLOCKED. Call this BEFORE performing actions that modify "
        "files, create content, or make decisions."
    ),
)
async def trust_check(
    action: str,
    resource: str = "",
    decision_type: str = "",
) -> dict:
    """Gate: can I do this?

    Args:
        action: The action to check (e.g., "record_decision", "edit_file")
        resource: The resource being acted on (e.g., file path)
        decision_type: Optional decision type for decision-specific checks
    """
    project = await _get_project()
    context = {}
    if resource:
        context["resource"] = resource
    if decision_type:
        context["decision_type"] = decision_type

    verdict = project.check(action, context)
    return {
        "verdict": verdict.value if hasattr(verdict, "value") else str(verdict),
        "action": action,
        "resource": resource,
        "posture": project.posture.value,
    }


@mcp.tool(
    name="trust_record",
    description=(
        "Record a decision with full reasoning trace and EATP audit "
        "anchor. Use this after making a significant decision to "
        "create an auditable record."
    ),
)
async def trust_record(
    decision: str,
    rationale: str,
    decision_type: str = "scope",
    alternatives: list[str] | None = None,
    risks: list[str] | None = None,
    confidence: float = 0.8,
    confidentiality: str = "public",
) -> dict:
    """Log: I did this (with reasoning trace).

    Args:
        decision: What was decided
        rationale: Why it was decided
        decision_type: Type of decision (scope, design, argument, evidence, methodology, meta)
        alternatives: Alternatives considered
        risks: Known risks
        confidence: Confidence level 0.0-1.0
        confidentiality: Confidentiality level (public, restricted, confidential)
    """
    project = await _get_project()
    if not 0.0 <= confidence <= 1.0:
        return {"error": "confidence must be between 0.0 and 1.0", "blocked": True}
    record = DecisionRecord(
        decision_type=_parse_decision_type(decision_type),
        decision=decision,
        rationale=rationale,
        alternatives=alternatives or [],
        risks=risks or [],
        confidence=confidence,
        confidentiality=confidentiality,
    )
    try:
        decision_id = await project.record_decision(record)
        return {
            "decision_id": decision_id,
            "anchor_created": True,
            "posture": project.posture.value,
        }
    except ConstraintViolationError as e:
        return {
            "error": str(e),
            "blocked": True,
        }


@mcp.tool(
    name="trust_envelope",
    description=(
        "Read the current constraint envelope — what actions are "
        "blocked, what paths are restricted, financial limits, etc."
    ),
)
async def trust_envelope() -> dict:
    """Read: what are my constraints?"""
    project = await _get_project()
    envelope = project.constraint_envelope
    if envelope is None:
        return {"envelope": None, "message": "No constraint envelope configured"}
    return {"envelope": envelope.to_dict()}


@mcp.tool(
    name="trust_status",
    description=(
        "Query current trust status: posture, active session, "
        "decision count, constraint summary."
    ),
)
async def trust_status() -> dict:
    """Query: current session, posture, stats."""
    project = await _get_project()
    status = {
        "project_name": project.manifest.project_name,
        "trust_posture": project.posture.value,
        "total_decisions": project.manifest.total_decisions,
        "total_milestones": project.manifest.total_milestones,
        "total_audits": project.manifest.total_audits,
        "has_session": project.session is not None,
    }
    if project.session is not None:
        status["session_id"] = project.session.session_id
        status["session_actions"] = project.session.action_count
    if project.constraint_envelope is not None:
        env = project.constraint_envelope
        status["blocked_actions"] = env.operational.blocked_actions
        status["blocked_paths"] = env.data_access.blocked_paths
    return status


@mcp.tool(
    name="trust_verify",
    description=(
        "Verify the integrity of the trust chain. Returns a report "
        "showing whether the chain is valid and any integrity issues."
    ),
)
async def trust_verify() -> dict:
    """Verify: is the trust chain intact?"""
    project = await _get_project()
    return await project.verify()


def main():
    """Entry point for trustplane-mcp command."""
    import argparse

    parser = argparse.ArgumentParser(description="TrustPlane MCP Server")
    parser.add_argument(
        "--trust-dir",
        default=os.environ.get("TRUSTPLANE_DIR", "./trust-plane"),
        help="Path to trust plane directory",
    )
    args = parser.parse_args()

    global TRUST_DIR
    TRUST_DIR = Path(args.trust_dir)

    mcp.run()


if __name__ == "__main__":
    main()
