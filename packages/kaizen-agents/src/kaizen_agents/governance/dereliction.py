# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Gradient Dereliction Detection -- detect insufficient envelope tightening.

Per PACT Section 5.4: when a parent delegates to a child with an identical
(or nearly identical) envelope, this constitutes "dereliction" -- the parent
is passing full authority without meaningful governance narrowing.

This module detects such cases and emits monitoring warnings. It does NOT
block the delegation -- dereliction is a warning, not an error.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "DerelictionDetector",
    "DerelictionWarning",
    "DerelictionStats",
]


@dataclass(frozen=True)
class DerelictionWarning:
    """Warning emitted when a delegation has insufficient tightening.

    Attributes:
        parent_id: The delegating parent's instance ID.
        child_id: The receiving child's instance ID.
        tightening_ratio: The ratio of tightening (0.0 = identical, 1.0 = fully restricted).
        threshold: The minimum acceptable tightening ratio.
        dimensions: Per-dimension tightening analysis.
    """

    parent_id: str
    child_id: str
    tightening_ratio: float
    threshold: float
    dimensions: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DerelictionStats:
    """Aggregate statistics for dereliction monitoring.

    Attributes:
        total_delegations: Total number of delegations checked.
        dereliction_count: Number of delegations flagged as dereliction.
        dereliction_rate: Ratio of dereliction_count / total_delegations.
        avg_tightening_ratio: Average tightening ratio across all delegations.
    """

    total_delegations: int
    dereliction_count: int
    dereliction_rate: float
    avg_tightening_ratio: float


class DerelictionDetector:
    """Detects dereliction: delegations with insufficient envelope tightening.

    A delegation is flagged as dereliction when the child envelope is less
    than `threshold` (default 5%) tighter than the parent envelope.

    Thread-safe. Bounded warning history (maxlen=10000).

    Usage:
        detector = DerelictionDetector(threshold=0.05)
        warning = detector.check_delegation(
            parent_id="root",
            child_id="child-1",
            parent_envelope={"financial": {"limit": 100.0}},
            child_envelope={"financial": {"limit": 100.0}},  # identical!
        )
        # warning is not None -- 0% tightening < 5% threshold
    """

    def __init__(self, threshold: float = 0.05, maxlen: int = 10000) -> None:
        if not math.isfinite(threshold):
            raise ValueError(f"threshold must be finite, got {threshold}")
        if threshold < 0.0 or threshold > 1.0:
            raise ValueError(f"threshold must be in [0.0, 1.0], got {threshold}")
        if maxlen <= 0:
            raise ValueError(f"maxlen must be positive, got {maxlen}")

        self._lock = threading.Lock()
        self._threshold = threshold
        self._warnings: deque[DerelictionWarning] = deque(maxlen=maxlen)
        self._total_delegations = 0
        self._dereliction_count = 0  # separate counter, not derived from bounded deque
        self._total_tightening = 0.0

    def check_delegation(
        self,
        parent_id: str,
        child_id: str,
        parent_envelope: dict[str, Any],
        child_envelope: dict[str, Any],
    ) -> DerelictionWarning | None:
        """Check a delegation for dereliction (insufficient tightening).

        Args:
            parent_id: The delegating parent's instance ID.
            child_id: The receiving child's instance ID.
            parent_envelope: The parent's envelope (as dict).
            child_envelope: The child's envelope (as dict).

        Returns:
            A DerelictionWarning if tightening is below threshold, None otherwise.
        """
        dim_ratios = _compute_dimension_ratios(parent_envelope, child_envelope)
        overall_ratio = _compute_overall_ratio(dim_ratios)

        with self._lock:
            self._total_delegations += 1
            self._total_tightening += overall_ratio

            if overall_ratio < self._threshold:
                self._dereliction_count += 1
                warning = DerelictionWarning(
                    parent_id=parent_id,
                    child_id=child_id,
                    tightening_ratio=overall_ratio,
                    threshold=self._threshold,
                    dimensions=dim_ratios,
                )
                self._warnings.append(warning)

                logger.warning(
                    "Dereliction detected: %s -> %s tightening=%.1f%% (threshold=%.1f%%)",
                    parent_id,
                    child_id,
                    overall_ratio * 100,
                    self._threshold * 100,
                )
                return warning

        return None

    def get_stats(self) -> DerelictionStats:
        """Get aggregate dereliction statistics.

        Returns:
            DerelictionStats with counts and rates.
        """
        with self._lock:
            total = self._total_delegations
            count = self._dereliction_count
            rate = count / total if total > 0 else 0.0
            avg = self._total_tightening / total if total > 0 else 0.0

            return DerelictionStats(
                total_delegations=total,
                dereliction_count=count,
                dereliction_rate=rate,
                avg_tightening_ratio=avg,
            )

    def get_warnings(self) -> list[DerelictionWarning]:
        """Return all stored dereliction warnings.

        Returns:
            List of DerelictionWarning instances.
        """
        with self._lock:
            return list(self._warnings)

    @property
    def threshold(self) -> float:
        """The minimum acceptable tightening ratio."""
        return self._threshold


def _compute_dimension_ratios(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, float]:
    """Compute per-dimension tightening ratios.

    For each dimension, ratio = 1 - (child_value / parent_value).
    A ratio of 0.0 means identical; 1.0 means fully restricted.

    For non-numeric dimensions (lists), ratio is based on the fraction
    of items removed from the parent's allowed list.
    """
    ratios: dict[str, float] = {}

    # Financial dimension (NaN-safe)
    parent_fin = parent.get("financial", {})
    child_fin = child.get("financial", {})
    parent_limit = parent_fin.get("limit", 0)
    child_limit = child_fin.get("limit", 0)
    if (
        isinstance(parent_limit, (int, float))
        and isinstance(child_limit, (int, float))
        and math.isfinite(float(parent_limit))
        and math.isfinite(float(child_limit))
        and parent_limit > 0
    ):
        ratios["financial"] = max(0.0, min(1.0, 1.0 - (child_limit / parent_limit)))
    else:
        ratios["financial"] = 0.0

    # Operational dimension (list-based)
    parent_allowed = set(parent.get("operational", {}).get("allowed", []))
    child_allowed = set(child.get("operational", {}).get("allowed", []))
    if parent_allowed:
        removed = parent_allowed - child_allowed
        ratios["operational"] = len(removed) / len(parent_allowed)
    else:
        ratios["operational"] = 0.0

    # Data access dimension
    parent_da = parent.get("data_access", {})
    child_da = child.get("data_access", {})
    parent_scopes = set(parent_da.get("scopes", []))
    child_scopes = set(child_da.get("scopes", []))
    if parent_scopes:
        removed = parent_scopes - child_scopes
        ratios["data_access"] = len(removed) / len(parent_scopes)
    else:
        ratios["data_access"] = 0.0

    # Communication dimension
    parent_channels = set(parent.get("communication", {}).get("channels", []))
    child_channels = set(child.get("communication", {}).get("channels", []))
    if parent_channels:
        removed = parent_channels - child_channels
        ratios["communication"] = len(removed) / len(parent_channels)
    else:
        ratios["communication"] = 0.0

    return ratios


def _compute_overall_ratio(dim_ratios: dict[str, float]) -> float:
    """Average tightening ratio across all dimensions."""
    if not dim_ratios:
        return 0.0
    return sum(dim_ratios.values()) / len(dim_ratios)
