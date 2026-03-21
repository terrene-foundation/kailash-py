# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Constraint diagnostics and quality scoring.

Analyzes how constraints perform in practice by examining the audit
trail. Provides a quality score and actionable recommendations.

CARE Principle 8 / Goodhart Trap: These diagnostics are
decision-support data, not optimization targets.
"""

from collections import Counter
from pathlib import Path
from typing import Any

from kailash.trust._locking import safe_read_json


def analyze_constraints(
    trust_dir: str | Path,
    envelope: Any | None = None,
) -> dict[str, Any]:
    """Analyze constraint performance from the audit trail.

    Args:
        trust_dir: Path to trust-plane directory
        envelope: The current ConstraintEnvelope (optional)

    Returns:
        Diagnostic report dict
    """
    trust_path = Path(trust_dir)
    anchors_dir = trust_path / "anchors"

    # Collect all actions from anchors
    actions: list[dict[str, Any]] = []
    verdicts: Counter[str] = Counter()
    action_types: Counter[str] = Counter()

    if anchors_dir.exists():
        for af in sorted(anchors_dir.glob("*.json")):
            data = safe_read_json(af)
            action = data.get("action", "")
            action_types[action] += 1

            ctx = data.get("context", {})
            verdict = ctx.get("verification_category", "unknown")
            verdicts[verdict] += 1

            actions.append(
                {
                    "action": action,
                    "timestamp": data.get("timestamp", ""),
                    "verdict": verdict,
                    "resource": data.get("resource", ""),
                }
            )

    total_actions = len(actions)

    # Utilization: what percentage of allowed actions are actually used
    utilization = _compute_utilization(envelope, action_types)

    # Boundary pressure: which constraints cause the most friction
    boundary_pressure = _compute_boundary_pressure(verdicts)

    # Gap detection: actions not covered by constraints
    gaps = _detect_gaps(envelope, action_types)

    # Quality score
    score = _compute_quality_score(
        utilization=utilization,
        boundary_pressure=boundary_pressure,
        gaps=gaps,
        total_actions=total_actions,
    )

    # Suggestions
    suggestions = _generate_suggestions(utilization, boundary_pressure, gaps)

    return {
        "total_actions": total_actions,
        "verdict_distribution": dict(verdicts),
        "action_types": dict(action_types.most_common()),
        "utilization": utilization,
        "boundary_pressure": boundary_pressure,
        "gaps": gaps,
        "quality_score": score,
        "suggestions": suggestions,
    }


def _compute_utilization(
    envelope: Any | None, action_types: Counter[str]
) -> dict[str, Any]:
    """Compute how much of the constraint envelope is utilized."""
    if envelope is None:
        return {"status": "no_envelope", "percentage": 0}

    allowed = set(envelope.operational.allowed_actions)
    blocked = set(envelope.operational.blocked_actions)

    if not allowed and not blocked:
        return {"status": "unconstrained", "percentage": 0}

    used_allowed = allowed & set(action_types.keys())
    tested_blocked = blocked & set(action_types.keys())

    allowed_pct = round(len(used_allowed) / len(allowed) * 100) if allowed else 0

    return {
        "status": "computed",
        "allowed_total": len(allowed),
        "allowed_used": len(used_allowed),
        "allowed_unused": sorted(allowed - used_allowed),
        "allowed_utilization_pct": allowed_pct,
        "blocked_tested": sorted(tested_blocked),
        "blocked_untested": sorted(blocked - tested_blocked),
    }


def _compute_boundary_pressure(verdicts: Counter[str]) -> dict[str, Any]:
    """Identify which constraints cause the most friction."""
    total = sum(verdicts.values())
    if total == 0:
        return {"status": "no_data", "friction_points": []}

    friction = []
    for verdict, count in verdicts.most_common():
        if verdict in ("held", "blocked", "flagged", "HELD", "BLOCKED", "FLAGGED"):
            friction.append(
                {
                    "verdict": verdict,
                    "count": count,
                    "percentage": round(count / total * 100),
                }
            )

    return {
        "status": "computed",
        "total_verdicts": total,
        "friction_points": friction,
    }


def _detect_gaps(envelope: Any | None, action_types: Counter[str]) -> dict[str, Any]:
    """Find actions not covered by any constraint."""
    if envelope is None:
        return {
            "status": "no_envelope",
            "unconstrained_actions": list(action_types.keys()),
        }

    allowed = set(envelope.operational.allowed_actions)
    blocked = set(envelope.operational.blocked_actions)
    all_constrained = allowed | blocked

    unconstrained = set(action_types.keys()) - all_constrained
    # Filter out internal actions
    internal_prefixes = ("session_", "posture_", "enforcement_", "proxy_")
    unconstrained = {
        a for a in unconstrained if not any(a.startswith(p) for p in internal_prefixes)
    }

    return {
        "status": "computed",
        "unconstrained_actions": sorted(unconstrained),
        "unconstrained_count": len(unconstrained),
    }


def _compute_quality_score(
    utilization: dict[str, Any],
    boundary_pressure: dict[str, Any],
    gaps: dict[str, Any],
    total_actions: int,
) -> dict[str, Any]:
    """Compute a 0-100 quality score."""
    if total_actions == 0:
        return {
            "score": 0,
            "level": "insufficient_data",
            "explanation": "No actions recorded yet.",
        }

    score = 100

    # Penalize low utilization (unused constraints = possible drift)
    util_pct = utilization.get("allowed_utilization_pct", 0)
    if utilization.get("status") == "computed" and util_pct < 50:
        score -= 20

    # Penalize high friction (too many blocked/held)
    friction_points = boundary_pressure.get("friction_points", [])
    total_friction = sum(f["count"] for f in friction_points)
    if total_friction > total_actions * 0.3:
        score -= 25
    elif total_friction > total_actions * 0.1:
        score -= 10

    # Penalize unconstrained actions
    gap_count = gaps.get("unconstrained_count", 0)
    if gap_count > 5:
        score -= 25
    elif gap_count > 2:
        score -= 10

    # Penalize no envelope at all
    if utilization.get("status") == "no_envelope":
        score -= 40

    score = max(0, min(100, score))

    if score >= 80:
        level = "well_tuned"
    elif score >= 50:
        level = "needs_attention"
    else:
        level = "major_issues"

    return {"score": score, "level": level}


def _generate_suggestions(
    utilization: dict[str, Any],
    boundary_pressure: dict[str, Any],
    gaps: dict[str, Any],
) -> list[str]:
    """Generate actionable improvement suggestions."""
    suggestions: list[str] = []

    if utilization.get("status") == "no_envelope":
        suggestions.append(
            "No constraint envelope configured. "
            "Use 'attest template apply <template>' to start with a pre-built template."
        )

    unused = utilization.get("allowed_unused", [])
    if unused:
        suggestions.append(
            f"Unused allowed actions: {', '.join(unused[:5])}. "
            "Consider removing these to tighten the envelope."
        )

    untested = utilization.get("blocked_untested", [])
    if untested:
        suggestions.append(
            f"Blocked actions never attempted: {', '.join(untested[:5])}. "
            "Verify these constraints are still needed."
        )

    friction = boundary_pressure.get("friction_points", [])
    for f in friction[:3]:
        suggestions.append(
            f"High friction on '{f['verdict']}' ({f['count']} occurrences, "
            f"{f['percentage']}% of actions). Review whether this constraint "
            f"is too conservative."
        )

    unconstrained = gaps.get("unconstrained_actions", [])
    if unconstrained:
        suggestions.append(
            f"Unconstrained actions detected: {', '.join(unconstrained[:5])}. "
            "Consider adding these to the constraint envelope."
        )

    return suggestions


def format_diagnostics(report: dict[str, Any]) -> str:
    """Format diagnostics as human-readable text."""
    lines: list[str] = []

    score = report["quality_score"]
    lines.append(f"Constraint Quality Score: {score['score']}/100 ({score['level']})")
    lines.append("")

    if report["total_actions"] == 0:
        lines.append("No actions recorded yet. Run some work sessions first.")
        return "\n".join(lines)

    # Utilization
    util = report["utilization"]
    if util.get("status") == "computed":
        lines.append(
            f"Utilization: {util.get('allowed_utilization_pct', 0)}% of allowed actions used"
        )
        if util.get("allowed_unused"):
            lines.append(f"  Unused: {', '.join(util['allowed_unused'][:5])}")
    lines.append("")

    # Boundary pressure
    bp = report["boundary_pressure"]
    if bp.get("friction_points"):
        lines.append("Boundary Pressure:")
        for f in bp["friction_points"]:
            lines.append(f"  - {f['verdict']}: {f['count']} ({f['percentage']}%)")
    lines.append("")

    # Gaps
    gaps = report["gaps"]
    if gaps.get("unconstrained_actions"):
        lines.append(
            f"Unconstrained Actions: {', '.join(gaps['unconstrained_actions'][:5])}"
        )
    lines.append("")

    # Suggestions
    if report["suggestions"]:
        lines.append("Suggestions:")
        for i, s in enumerate(report["suggestions"], 1):
            lines.append(f"  {i}. {s}")
    lines.append("")

    return "\n".join(lines)
