# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Verification gradient engine -- evaluates actions against constraint dimensions.

Provides GradientEngine and EvaluationResult for governance-layer constraint
evaluation. This bridges PACT's governance envelopes with EATP's verification
gradient concept.

The GradientEngine evaluates an action context against a ConstraintEnvelopeConfig
and returns an EvaluationResult with per-dimension pass/fail and an overall
verification level (AUTO_APPROVED, FLAGGED, HELD, BLOCKED).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from kailash.trust.pact.config import (
    ConstraintDimension,
    ConstraintEnvelopeConfig,
    GradientRuleConfig,
    VerificationGradientConfig,
    VerificationLevel,
)

logger = logging.getLogger(__name__)

__all__ = [
    "EvaluationResult",
    "DimensionResult",
    "GradientEngine",
]


@dataclass(frozen=True)
class DimensionResult:
    """Result of evaluating a single constraint dimension."""

    dimension: ConstraintDimension
    satisfied: bool
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationResult:
    """Result of evaluating an action against all constraint dimensions.

    Attributes:
        level: The overall verification level determined by the gradient.
        dimensions: Per-dimension evaluation results.
        action: The action that was evaluated.
        matched_rule: The gradient rule that matched (if any).
        all_satisfied: True if all dimensions passed.
    """

    level: VerificationLevel
    dimensions: list[DimensionResult] = field(default_factory=list)
    action: str = ""
    matched_rule: str = ""

    @property
    def all_satisfied(self) -> bool:
        """True if all dimension constraints are satisfied."""
        return all(d.satisfied for d in self.dimensions)


class GradientEngine:
    """Evaluates actions against governance constraint envelopes.

    Takes a ConstraintEnvelopeConfig and optional VerificationGradientConfig,
    evaluates an action context against the constraint dimensions, and returns
    an EvaluationResult with the verification level.

    Fail-closed: Any evaluation error returns BLOCKED.

    Args:
        config: The constraint envelope to evaluate against.
        gradient: Optional gradient rules for action-to-level mapping.
    """

    def __init__(
        self,
        config: ConstraintEnvelopeConfig,
        gradient: VerificationGradientConfig | None = None,
    ) -> None:
        self._config = config
        self._gradient = gradient or VerificationGradientConfig()

    def evaluate(
        self,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """Evaluate an action against all constraint dimensions.

        Args:
            action: The action being evaluated (e.g., "deploy_to_prod").
            context: Optional context dict with keys like "cost_usd",
                "data_paths", "channel", etc.

        Returns:
            EvaluationResult with verification level and per-dimension results.
        """
        ctx = context or {}
        dimensions: list[DimensionResult] = []

        try:
            # Evaluate each dimension
            dimensions.append(self._eval_financial(ctx))
            dimensions.append(self._eval_operational(action, ctx))
            dimensions.append(self._eval_temporal(ctx))
            dimensions.append(self._eval_data_access(ctx))
            dimensions.append(self._eval_communication(ctx))

            # Determine level: gradient rules first, then dimension results
            level = self._determine_level(action, dimensions)

            return EvaluationResult(
                level=level,
                dimensions=dimensions,
                action=action,
                matched_rule=self._find_matching_rule(action),
            )
        except Exception as exc:
            logger.warning(
                "GradientEngine: evaluation failed for '%s': %s", action, exc
            )
            return EvaluationResult(
                level=VerificationLevel.BLOCKED,
                dimensions=dimensions,
                action=action,
            )

    def _determine_level(
        self, action: str, dimensions: list[DimensionResult]
    ) -> VerificationLevel:
        """Determine verification level from gradient rules and dimension results."""
        # Check gradient rules first (first match wins)
        for rule in self._gradient.rules:
            if self._matches_pattern(action, rule.pattern):
                return rule.level

        # If any dimension failed, escalate
        if not all(d.satisfied for d in dimensions):
            return VerificationLevel.BLOCKED

        # All passed, no specific rule → use default
        return self._gradient.default_level

    def _find_matching_rule(self, action: str) -> str:
        """Find the first matching gradient rule pattern."""
        for rule in self._gradient.rules:
            if self._matches_pattern(action, rule.pattern):
                return rule.pattern
        return ""

    @staticmethod
    def _matches_pattern(action: str, pattern: str) -> bool:
        """Match action against a glob-style pattern."""
        import fnmatch

        return fnmatch.fnmatch(action, pattern)

    def _eval_financial(self, ctx: dict[str, Any]) -> DimensionResult:
        """Evaluate financial constraints."""
        if self._config.financial is None:
            return DimensionResult(
                dimension=ConstraintDimension.FINANCIAL,
                satisfied=True,
                reason="No financial constraints configured",
            )

        cost = ctx.get("cost_usd", 0.0)
        if isinstance(cost, (int, float)):
            cost = float(cost)
            if not math.isfinite(cost) or cost < 0:
                return DimensionResult(
                    dimension=ConstraintDimension.FINANCIAL,
                    satisfied=False,
                    reason=f"Invalid cost value: {cost!r}",
                )
            if cost > self._config.financial.max_spend_usd:
                return DimensionResult(
                    dimension=ConstraintDimension.FINANCIAL,
                    satisfied=False,
                    reason=f"Cost {cost} exceeds max_spend_usd {self._config.financial.max_spend_usd}",
                    details={
                        "cost": cost,
                        "limit": self._config.financial.max_spend_usd,
                    },
                )

        return DimensionResult(
            dimension=ConstraintDimension.FINANCIAL,
            satisfied=True,
            reason="Within budget",
        )

    def _eval_operational(self, action: str, ctx: dict[str, Any]) -> DimensionResult:
        """Evaluate operational constraints."""
        op = self._config.operational
        if op is None:
            return DimensionResult(
                dimension=ConstraintDimension.OPERATIONAL,
                satisfied=True,
                reason="No operational constraints configured",
            )

        if op.blocked_actions and action in op.blocked_actions:
            return DimensionResult(
                dimension=ConstraintDimension.OPERATIONAL,
                satisfied=False,
                reason=f"Action '{action}' is explicitly blocked",
            )

        if op.allowed_actions and action not in op.allowed_actions:
            return DimensionResult(
                dimension=ConstraintDimension.OPERATIONAL,
                satisfied=False,
                reason=f"Action '{action}' not in allowed actions list",
            )

        return DimensionResult(
            dimension=ConstraintDimension.OPERATIONAL,
            satisfied=True,
            reason="Action permitted",
        )

    def _eval_temporal(self, ctx: dict[str, Any]) -> DimensionResult:
        """Evaluate temporal constraints."""
        if self._config.temporal is None:
            return DimensionResult(
                dimension=ConstraintDimension.TEMPORAL,
                satisfied=True,
                reason="No temporal constraints configured",
            )
        return DimensionResult(
            dimension=ConstraintDimension.TEMPORAL,
            satisfied=True,
            reason="Temporal constraints not evaluated at governance layer",
        )

    def _eval_data_access(self, ctx: dict[str, Any]) -> DimensionResult:
        """Evaluate data access constraints."""
        if self._config.data_access is None:
            return DimensionResult(
                dimension=ConstraintDimension.DATA_ACCESS,
                satisfied=True,
                reason="No data access constraints configured",
            )

        requested_paths = ctx.get("data_paths", [])
        if isinstance(requested_paths, list):
            blocked = self._config.data_access.blocked_data_types
            for path in requested_paths:
                if path in blocked:
                    return DimensionResult(
                        dimension=ConstraintDimension.DATA_ACCESS,
                        satisfied=False,
                        reason=f"Data path '{path}' is blocked",
                    )

        return DimensionResult(
            dimension=ConstraintDimension.DATA_ACCESS,
            satisfied=True,
            reason="Data access permitted",
        )

    def _eval_communication(self, ctx: dict[str, Any]) -> DimensionResult:
        """Evaluate communication constraints."""
        if self._config.communication is None:
            return DimensionResult(
                dimension=ConstraintDimension.COMMUNICATION,
                satisfied=True,
                reason="No communication constraints configured",
            )

        channel = ctx.get("channel")
        if channel and self._config.communication.internal_only:
            if channel not in (self._config.communication.allowed_channels or []):
                return DimensionResult(
                    dimension=ConstraintDimension.COMMUNICATION,
                    satisfied=False,
                    reason=f"Channel '{channel}' not in allowed channels (internal_only=True)",
                )

        return DimensionResult(
            dimension=ConstraintDimension.COMMUNICATION,
            satisfied=True,
            reason="Communication permitted",
        )
