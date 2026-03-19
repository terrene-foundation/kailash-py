# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Proximity scanning for constraint utilization alerts.

Detects when agents approach constraint limits (e.g., 80% of cost budget)
and escalates enforcement verdicts before actual violations occur. This
provides early warning to prevent sudden transitions from AUTO_APPROVED
to BLOCKED.

Cross-SDK alignment:
    Default thresholds (flag=0.80, hold=0.95) match kailash-rs D1 decision.
    The CONSERVATIVE preset (flag=0.70, hold=0.90) provides tighter margins
    for high-risk environments.

Integration:
    ProximityScanner runs after initial verdict classification. It inspects
    ConstraintCheckResult objects for usage ratios (used/limit) and may
    escalate the verdict upward (never downgrade). This enforces the
    monotonic escalation invariant: AUTO_APPROVED -> FLAGGED -> HELD -> BLOCKED.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from eatp.constraints.dimension import ConstraintCheckResult
from eatp.enforce.strict import Verdict

logger = logging.getLogger(__name__)


@dataclass
class ProximityConfig:
    """Configuration for proximity threshold scanning.

    Attributes:
        flag_threshold: Usage ratio at which verdict escalates to FLAGGED.
            Default: 0.80 (80% of limit). Cross-SDK aligned with D1.
        hold_threshold: Usage ratio at which verdict escalates to HELD.
            Default: 0.95 (95% of limit). Cross-SDK aligned with D1.
        dimension_overrides: Per-dimension threshold overrides.
            Keys are dimension names, values are (flag, hold) tuples.
    """

    flag_threshold: float = 0.80
    hold_threshold: float = 0.95
    dimension_overrides: Dict[str, tuple] = field(default_factory=dict)

    def __post_init__(self):
        """Validate thresholds and dimension overrides."""
        if not 0.0 < self.flag_threshold < 1.0:
            raise ValueError(f"flag_threshold must be between 0 and 1, got {self.flag_threshold}")
        if not 0.0 < self.hold_threshold <= 1.0:
            raise ValueError(f"hold_threshold must be between 0 and 1, got {self.hold_threshold}")
        if self.flag_threshold >= self.hold_threshold:
            raise ValueError(
                f"flag_threshold ({self.flag_threshold}) must be less than hold_threshold ({self.hold_threshold})"
            )
        # Validate per-dimension overrides
        for dim_name, thresholds in self.dimension_overrides.items():
            if not isinstance(thresholds, tuple) or len(thresholds) != 2:
                raise ValueError(f"dimension_overrides['{dim_name}'] must be a (flag, hold) tuple")
            flag, hold = thresholds
            if not 0.0 < flag < 1.0:
                raise ValueError(f"dimension_overrides['{dim_name}'] flag must be between 0 and 1, got {flag}")
            if not 0.0 < hold <= 1.0:
                raise ValueError(f"dimension_overrides['{dim_name}'] hold must be between 0 and 1, got {hold}")
            if flag >= hold:
                raise ValueError(f"dimension_overrides['{dim_name}'] flag ({flag}) must be less than hold ({hold})")


CONSERVATIVE_PROXIMITY = ProximityConfig(flag_threshold=0.70, hold_threshold=0.90)
"""Conservative proximity preset for high-risk environments."""


@dataclass
class ProximityAlert:
    """Alert raised when constraint utilization approaches a threshold.

    Attributes:
        dimension: Name of the constraint dimension (e.g., "cost_limit").
        usage_ratio: Computed usage ratio (used / limit), between 0.0 and 1.0+.
        used: Amount of the constraint budget consumed.
        limit: Total constraint budget available.
        escalated_verdict: The verdict this alert escalates to.
        original_verdict: The pre-scan baseline verdict. Always AUTO_APPROVED
            because proximity alerts represent constraint utilization *before*
            enforcement classification. The actual base verdict is supplied
            separately to ``ProximityScanner.escalate_verdict()``.
    """

    dimension: str
    usage_ratio: float
    used: float
    limit: float
    escalated_verdict: Verdict
    original_verdict: Verdict

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dictionary for metadata/logging."""
        return {
            "dimension": self.dimension,
            "usage_ratio": round(self.usage_ratio, 4),
            "used": self.used,
            "limit": self.limit,
            "escalated_verdict": self.escalated_verdict.value,
            "original_verdict": self.original_verdict.value,
        }


# Verdict ordering for monotonic escalation
_VERDICT_ORDER = {
    Verdict.AUTO_APPROVED: 0,
    Verdict.FLAGGED: 1,
    Verdict.HELD: 2,
    Verdict.BLOCKED: 3,
}


class ProximityScanner:
    """Scans constraint check results for utilization proximity alerts.

    Computes usage ratios from ConstraintCheckResult objects and generates
    alerts when utilization exceeds configured thresholds. Supports
    per-dimension threshold overrides and monotonic verdict escalation.

    Example:
        >>> from eatp.enforce.proximity import ProximityScanner, ProximityConfig
        >>> scanner = ProximityScanner()
        >>> alerts = scanner.scan(constraint_results, "cost_limit")
        >>> final_verdict = scanner.escalate_verdict(Verdict.AUTO_APPROVED, alerts)
    """

    def __init__(self, config: Optional[ProximityConfig] = None):
        """Initialize the proximity scanner.

        Args:
            config: Proximity threshold configuration.
                Defaults to ProximityConfig() (flag=0.80, hold=0.95).
        """
        self._config = config or ProximityConfig()

    @property
    def config(self) -> ProximityConfig:
        """Get the current proximity configuration."""
        return self._config

    def scan(
        self,
        results: List[ConstraintCheckResult],
        dimension_name: Optional[str] = None,
    ) -> List[ProximityAlert]:
        """Scan constraint check results for proximity alerts.

        Computes usage ratios (used/limit) for each result and generates
        alerts when the ratio exceeds configured thresholds.

        Args:
            results: List of constraint check results to scan.
            dimension_name: Optional dimension name to use for all results.
                If None, uses "unknown" as the dimension name.

        Returns:
            List of ProximityAlert objects for results exceeding thresholds.
        """
        alerts: List[ProximityAlert] = []

        for result in results:
            if result.limit is None or result.limit <= 0:
                # Cannot compute usage ratio without a valid limit
                continue

            if result.used is None:
                continue

            usage_ratio = result.used / result.limit
            dim_name = dimension_name or "unknown"

            # Get thresholds (per-dimension override or global)
            flag_thresh, hold_thresh = self._get_thresholds(dim_name)

            if usage_ratio >= hold_thresh:
                alerts.append(
                    ProximityAlert(
                        dimension=dim_name,
                        usage_ratio=usage_ratio,
                        used=result.used,
                        limit=result.limit,
                        escalated_verdict=Verdict.HELD,
                        original_verdict=Verdict.AUTO_APPROVED,
                    )
                )
                logger.warning(
                    f"[PROXIMITY] HOLD alert: {dim_name} at {usage_ratio:.1%} (threshold: {hold_thresh:.0%})"
                )
            elif usage_ratio >= flag_thresh:
                alerts.append(
                    ProximityAlert(
                        dimension=dim_name,
                        usage_ratio=usage_ratio,
                        used=result.used,
                        limit=result.limit,
                        escalated_verdict=Verdict.FLAGGED,
                        original_verdict=Verdict.AUTO_APPROVED,
                    )
                )
                logger.info(f"[PROXIMITY] FLAG alert: {dim_name} at {usage_ratio:.1%} (threshold: {flag_thresh:.0%})")

        return alerts

    def scan_multi(
        self,
        results_by_dimension: Dict[str, List[ConstraintCheckResult]],
    ) -> List[ProximityAlert]:
        """Scan multiple dimensions at once.

        Convenience method for scanning constraint results grouped by
        dimension name.

        Args:
            results_by_dimension: Dict mapping dimension names to their
                constraint check results.

        Returns:
            Combined list of ProximityAlert objects across all dimensions.
        """
        all_alerts: List[ProximityAlert] = []
        for dim_name, results in results_by_dimension.items():
            all_alerts.extend(self.scan(results, dimension_name=dim_name))
        return all_alerts

    def escalate_verdict(
        self,
        base_verdict: Verdict,
        alerts: List[ProximityAlert],
    ) -> Verdict:
        """Escalate a verdict based on proximity alerts.

        Applies monotonic escalation: the returned verdict is always >=
        the base verdict. Never downgrades.

        Args:
            base_verdict: The original enforcement verdict.
            alerts: Proximity alerts to consider for escalation.

        Returns:
            The escalated verdict (may be the same as base if no escalation).
        """
        if not alerts:
            return base_verdict

        # Find the highest escalation level from alerts
        max_alert_level = max(_VERDICT_ORDER.get(a.escalated_verdict, 0) for a in alerts)
        base_level = _VERDICT_ORDER.get(base_verdict, 0)

        # Monotonic: only escalate, never downgrade
        if max_alert_level > base_level:
            escalated = [v for v, level in _VERDICT_ORDER.items() if level == max_alert_level][0]
            logger.info(
                f"[PROXIMITY] Escalating verdict from {base_verdict.value} "
                f"to {escalated.value} based on {len(alerts)} alert(s)"
            )
            return escalated

        return base_verdict

    def _get_thresholds(self, dimension_name: str) -> tuple:
        """Get flag/hold thresholds for a dimension.

        Args:
            dimension_name: The dimension to look up.

        Returns:
            Tuple of (flag_threshold, hold_threshold).
        """
        if dimension_name in self._config.dimension_overrides:
            return self._config.dimension_overrides[dimension_name]
        return (self._config.flag_threshold, self._config.hold_threshold)


__all__ = [
    "ProximityConfig",
    "ProximityAlert",
    "ProximityScanner",
    "CONSERVATIVE_PROXIMITY",
]
