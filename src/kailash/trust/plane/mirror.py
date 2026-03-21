# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Mirror Thesis competency map — what does the pattern of human engagement reveal?

Analyzes ExecutionRecords, EscalationRecords, and InterventionRecords
to produce a competency map showing:
- What AI handles autonomously
- Where AI needs human input (by competency category)
- Where humans intervene unprompted (by competency category)

This is the Mirror Thesis in action: the pattern of human engagement
reveals what AI can and cannot do.

Note per CARE Principle 8 / Goodhart Trap: competency distributions
are decision-support data, not optimization targets. If an organization
starts trying to minimize InterventionRecords tagged with 'ethical_judgment',
they are gaming the mirror.
"""

import json
from collections import Counter
from typing import Any

from kailash.trust.plane.models import (
    EscalationRecord,
    ExecutionRecord,
    HumanCompetency,
    InterventionRecord,
)


def build_competency_map(
    records: dict[str, list[ExecutionRecord | EscalationRecord | InterventionRecord]],
    project_name: str = "",
    period_start: str = "",
    period_end: str = "",
) -> dict[str, Any]:
    """Build a competency map from Mirror Thesis records.

    Args:
        records: Dict from TrustProject.get_mirror_records()
        project_name: Project name for the report header
        period_start: Start of analysis period (ISO format)
        period_end: End of analysis period (ISO format)

    Returns:
        Structured competency map dict
    """
    executions: list[ExecutionRecord] = records.get("executions", [])  # type: ignore[assignment]
    escalations: list[EscalationRecord] = records.get("escalations", [])  # type: ignore[assignment]
    interventions: list[InterventionRecord] = records.get("interventions", [])  # type: ignore[assignment]

    total = len(executions) + len(escalations) + len(interventions)

    if total == 0:
        return {
            "project_name": project_name,
            "total_actions": 0,
            "message": "No mirror data yet",
        }

    # Execution breakdown by action
    exec_actions: Counter[str] = Counter()
    for e in executions:
        exec_actions[e.action] += 1

    # Escalation breakdown by competency
    esc_competencies: Counter[str] = Counter()
    esc_triggers: list[str] = []
    for e in escalations:
        for c in e.competency_categories:
            esc_competencies[c.value] += 1
        if not e.competency_categories:
            esc_competencies["uncategorized"] += 1
        esc_triggers.append(e.trigger)

    # Intervention breakdown by competency
    int_competencies: Counter[str] = Counter()
    int_observations: list[str] = []
    for i in interventions:
        for c in i.competency_categories:
            int_competencies[c.value] += 1
        if not i.competency_categories:
            int_competencies["uncategorized"] += 1
        int_observations.append(i.observation)

    # Compute proportions
    exec_pct = round(len(executions) / total * 100) if total > 0 else 0
    esc_pct = round(len(escalations) / total * 100) if total > 0 else 0
    int_pct = round(len(interventions) / total * 100) if total > 0 else 0

    # Identify patterns
    patterns = _identify_patterns(exec_actions, esc_competencies, int_competencies)

    return {
        "project_name": project_name,
        "period_start": period_start,
        "period_end": period_end,
        "total_actions": total,
        "autonomous": {
            "count": len(executions),
            "percentage": exec_pct,
            "by_action": dict(exec_actions.most_common()),
        },
        "escalated": {
            "count": len(escalations),
            "percentage": esc_pct,
            "by_competency": dict(esc_competencies.most_common()),
            "triggers": esc_triggers,
        },
        "intervened": {
            "count": len(interventions),
            "percentage": int_pct,
            "by_competency": dict(int_competencies.most_common()),
            "observations": int_observations,
        },
        "patterns": patterns,
    }


def _identify_patterns(
    exec_actions: Counter[str],
    esc_competencies: Counter[str],
    int_competencies: Counter[str],
) -> dict[str, list[str]]:
    """Identify emerging patterns from the data."""
    patterns: dict[str, list[str]] = {
        "ai_reliable": [],
        "human_judgment_needed": [],
        "human_detects_missed": [],
    }

    # AI reliable: top execution actions (those appearing 2+ times)
    for action, count in exec_actions.most_common():
        if count >= 2:
            patterns["ai_reliable"].append(action)

    # Human judgment needed: top escalation competencies
    for comp, count in esc_competencies.most_common():
        if comp != "uncategorized":
            patterns["human_judgment_needed"].append(comp)

    # Human detects missed: top intervention competencies
    for comp, count in int_competencies.most_common():
        if comp != "uncategorized":
            patterns["human_detects_missed"].append(comp)

    return patterns


def format_competency_map(cmap: dict[str, Any]) -> str:
    """Format a competency map as human-readable text.

    Args:
        cmap: Output from build_competency_map()

    Returns:
        Formatted text report
    """
    if cmap.get("message") == "No mirror data yet":
        return f"Competency Map for: {cmap.get('project_name', 'Unknown')}\n\nNo mirror data yet.\n"

    lines: list[str] = []
    lines.append(f"Competency Map for: {cmap.get('project_name', 'Unknown')}")

    if cmap.get("period_start") and cmap.get("period_end"):
        lines.append(f"Period: {cmap['period_start']} to {cmap['period_end']}")

    lines.append(f"Total actions: {cmap['total_actions']}")
    lines.append("")

    # Autonomous section
    auto = cmap["autonomous"]
    lines.append(
        f"Autonomous (AI handled without human):  {auto['count']} actions ({auto['percentage']}%)"
    )
    for action, count in auto["by_action"].items():
        lines.append(f"  - {action}: {count}")

    lines.append("")

    # Escalated section
    esc = cmap["escalated"]
    lines.append(
        f"Escalated (AI needed human input):      {esc['count']} actions ({esc['percentage']}%)"
    )
    for comp, count in esc["by_competency"].items():
        label = comp.replace("_", " ")
        lines.append(f"  - {label}: {count}")

    lines.append("")

    # Intervened section
    inv = cmap["intervened"]
    lines.append(
        f"Intervened (Human chose to engage):     {inv['count']} actions ({inv['percentage']}%)"
    )
    for comp, count in inv["by_competency"].items():
        label = comp.replace("_", " ")
        lines.append(f"  - {label}: {count}")

    # Patterns
    patterns = cmap.get("patterns", {})
    if any(patterns.values()):
        lines.append("")
        lines.append("Emerging Patterns:")
        if patterns.get("ai_reliable"):
            items = ", ".join(patterns["ai_reliable"])
            lines.append(f"  AI reliably handles: {items}")
        if patterns.get("human_judgment_needed"):
            items = ", ".join(
                p.replace("_", " ") for p in patterns["human_judgment_needed"]
            )
            lines.append(f"  Human judgment needed for: {items}")
        if patterns.get("human_detects_missed"):
            items = ", ".join(
                p.replace("_", " ") for p in patterns["human_detects_missed"]
            )
            lines.append(f"  Human detects what AI misses: {items}")

    lines.append("")
    return "\n".join(lines)


def competency_map_json(cmap: dict[str, Any]) -> str:
    """Format a competency map as JSON.

    Args:
        cmap: Output from build_competency_map()

    Returns:
        JSON string
    """
    return json.dumps(cmap, indent=2, default=str)
