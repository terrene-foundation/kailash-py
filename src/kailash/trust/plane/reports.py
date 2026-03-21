# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Audit report generation for TrustPlane projects.

Generates human-readable Markdown reports summarizing a project's
trust chain, constraint envelope, decision timeline, and competency map.
"""

from datetime import datetime, timezone
from typing import Any

from kailash.trust.plane.models import _decision_type_value


def generate_audit_report(
    project: Any,  # TrustProject — avoid circular import
    verification: dict[str, Any] | None = None,
) -> str:
    """Generate a Markdown audit report for a TrustPlane project.

    Args:
        project: The TrustProject to report on
        verification: Optional verification result (from project.verify())

    Returns:
        Markdown string
    """
    m = project.manifest
    lines: list[str] = []

    # Header
    lines.append(f"# Audit Report: {m.project_name}")
    lines.append("")
    lines.append(
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Project ID**: {m.project_id}")
    lines.append(f"- **Author**: {m.author}")
    lines.append(f"- **Created**: {m.created_at.strftime('%Y-%m-%d')}")
    lines.append(f"- **Genesis**: {m.genesis_id}")
    lines.append(f"- **Decisions**: {m.total_decisions}")
    lines.append(f"- **Milestones**: {m.total_milestones}")
    lines.append(f"- **Audit Anchors**: {m.total_audits}")

    if verification:
        status = "Valid" if verification["chain_valid"] else "INVALID"
        issues = len(verification.get("integrity_issues", []))
        lines.append(
            f"- **Chain Status**: {status} "
            f"({verification.get('total_anchors', 0)} anchors, {issues} issues)"
        )
        lines.append(
            f"- **Trust Posture**: {verification.get('trust_posture', 'unknown')}"
        )
        lines.append(
            f"- **Verification Level**: {verification.get('verification_level', 'FULL')}"
        )
    lines.append("")

    # Constraint Envelope
    lines.append("## Constraint Envelope")
    lines.append("")
    envelope = m.constraint_envelope
    if envelope:
        if envelope.operational.allowed_actions:
            lines.append(
                f"- **Allowed Actions**: {', '.join(envelope.operational.allowed_actions)}"
            )
        if envelope.operational.blocked_actions:
            lines.append(
                f"- **Blocked Actions**: {', '.join(envelope.operational.blocked_actions)}"
            )
        if envelope.data_access.read_paths:
            lines.append(
                f"- **Read Paths**: {', '.join(envelope.data_access.read_paths)}"
            )
        if envelope.data_access.write_paths:
            lines.append(
                f"- **Write Paths**: {', '.join(envelope.data_access.write_paths)}"
            )
        if envelope.data_access.blocked_paths:
            lines.append(
                f"- **Blocked Paths**: {', '.join(envelope.data_access.blocked_paths)}"
            )
        if envelope.financial.max_cost_per_session is not None:
            lines.append(
                f"- **Max Cost/Session**: {envelope.financial.max_cost_per_session}"
            )
        if envelope.temporal.max_session_hours is not None:
            lines.append(
                f"- **Max Session Hours**: {envelope.temporal.max_session_hours}"
            )
        lines.append(f"- **Envelope Hash**: `{envelope.envelope_hash()}`")
        lines.append(f"- **Signed By**: {envelope.signed_by}")
    elif m.constraints:
        lines.append(f"- **Constraints**: {', '.join(m.constraints)}")
    else:
        lines.append("No constraints configured.")
    lines.append("")

    # Decision Timeline
    decisions = project.get_decisions()
    lines.append("## Decision Timeline")
    lines.append("")
    if decisions:
        for i, d in enumerate(decisions, 1):
            ts = d.timestamp.strftime("%Y-%m-%d %H:%M")
            dt = _decision_type_value(d.decision_type)
            lines.append(
                f"{i}. **[{ts}]** {dt.upper()}: {d.decision} "
                f"(confidence: {d.confidence})"
            )
    else:
        lines.append("No decisions recorded.")
    lines.append("")

    # Milestones
    milestones = project.get_milestones()
    lines.append("## Milestones")
    lines.append("")
    if milestones:
        for ms in milestones:
            ts = ms.timestamp.strftime("%Y-%m-%d %H:%M")
            lines.append(f"- **{ms.version}** [{ts}]: {ms.description}")
    else:
        lines.append("No milestones recorded.")
    lines.append("")

    # Competency Map
    lines.append("## Competency Map")
    lines.append("")
    try:
        from kailash.trust.plane.mirror import build_competency_map, format_competency_map

        records = project.get_mirror_records()
        total = sum(len(v) for v in records.values())
        if total > 0:
            cmap = build_competency_map(records, project_name=m.project_name)
            lines.append(format_competency_map(cmap))
        else:
            lines.append("No mirror data yet.")
    except Exception:
        lines.append("Mirror data unavailable.")
    lines.append("")

    # Verification
    if verification:
        lines.append("## Verification")
        lines.append("")
        lines.append(f"- **Chain Hash**: `{verification.get('genesis_id', '')}`")
        lines.append(f"- **Verified At**: {verification.get('verified_at', '')}")
        lines.append(
            f"- **Verification Level**: {verification.get('verification_level', '')}"
        )
        if verification.get("integrity_issues"):
            lines.append("")
            lines.append("### Integrity Issues")
            lines.append("")
            for issue in verification["integrity_issues"]:
                lines.append(f"- {issue}")
        lines.append("")

    return "\n".join(lines)
