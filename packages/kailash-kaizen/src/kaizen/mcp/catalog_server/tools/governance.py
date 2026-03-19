from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Governance tool handlers: validate_composition, budget_status.

Provides DAG validation with optional schema compatibility checking
and budget tracking queries.
"""

import math
import logging
from typing import Any, Dict, List

from kaizen.composition.dag_validator import validate_dag
from kaizen.composition.schema_compat import check_schema_compatibility

logger = logging.getLogger(__name__)

__all__ = [
    "handle_validate_composition",
    "handle_budget_status",
]


def handle_validate_composition(args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a composite agent pipeline.

    Runs DAG validation (cycle detection) and optionally checks schema
    compatibility between connected agents.

    Args:
        args: Must contain ``agents`` list.  Each agent descriptor has
              ``name`` (str), optional ``inputs_from`` (list of str),
              optional ``output_schema`` and ``input_schema`` (JSON Schema dicts).

    Returns:
        Dict with ``dag_valid``, ``topological_order``, ``cycles``,
        ``schema_issues``, and ``warnings``.
    """
    agents: List[Dict[str, Any]] = args.get("agents", [])
    if not agents:
        return {
            "dag_valid": True,
            "topological_order": [],
            "cycles": [],
            "schema_issues": [],
            "warnings": [],
        }

    # Step 1: DAG validation
    dag_result = validate_dag(agents)
    result: Dict[str, Any] = {
        "dag_valid": dag_result.is_valid,
        "topological_order": dag_result.topological_order,
        "cycles": dag_result.cycles,
        "warnings": list(dag_result.warnings),
    }

    # Step 2: Schema compatibility (only if DAG is valid)
    schema_issues: List[Dict[str, Any]] = []
    if dag_result.is_valid:
        # Build name -> agent map for schema lookups
        agent_map: Dict[str, Dict[str, Any]] = {a["name"]: a for a in agents}

        for agent in agents:
            inputs_from = agent.get("inputs_from", [])
            input_schema = agent.get("input_schema")
            if not inputs_from or not input_schema:
                continue

            for upstream_name in inputs_from:
                upstream = agent_map.get(upstream_name)
                if upstream is None:
                    continue
                output_schema = upstream.get("output_schema")
                if output_schema is None:
                    continue

                compat = check_schema_compatibility(output_schema, input_schema)
                if not compat.compatible:
                    schema_issues.append(
                        {
                            "upstream": upstream_name,
                            "downstream": agent["name"],
                            "mismatches": compat.mismatches,
                        }
                    )
                if compat.warnings:
                    for w in compat.warnings:
                        result["warnings"].append(
                            f"{upstream_name} -> {agent['name']}: {w}"
                        )

    result["schema_issues"] = schema_issues
    return result


def handle_budget_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Query budget tracking status for a scope.

    Returns current budget allocation and usage.  In the absence of
    a runtime budget tracker, this tool accepts optional ``budget_microdollars``
    and ``spent_microdollars`` parameters to compute remaining budget and
    utilization percentage.

    Args:
        args: Must contain ``scope`` (str).  Optional:
              ``budget_microdollars`` (int), ``spent_microdollars`` (int).

    Returns:
        Dict with ``scope``, ``budget_microdollars``, ``spent_microdollars``,
        ``remaining_microdollars``, ``utilization_percent``, and ``status``.
    """
    scope = args.get("scope", "")
    if not scope:
        raise ValueError("'scope' is required")

    budget = args.get("budget_microdollars", 0)
    spent = args.get("spent_microdollars", 0)

    # Validate numeric values are finite (NaN/Inf bypass prevention)
    if not math.isfinite(float(budget)):
        raise ValueError("budget_microdollars must be a finite number")
    if not math.isfinite(float(spent)):
        raise ValueError("spent_microdollars must be a finite number")

    budget = int(budget)
    spent = int(spent)

    remaining = max(0, budget - spent)
    utilization = 0.0
    if budget > 0:
        utilization = round((spent / budget) * 100, 2)

    # Determine status
    if budget == 0:
        status = "no_budget_set"
    elif utilization >= 100.0:
        status = "exceeded"
    elif utilization >= 80.0:
        status = "warning"
    else:
        status = "healthy"

    return {
        "scope": scope,
        "budget_microdollars": budget,
        "spent_microdollars": spent,
        "remaining_microdollars": remaining,
        "utilization_percent": utilization,
        "status": status,
    }
