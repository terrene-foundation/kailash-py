from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Posture-Budget Integration: links BudgetTracker threshold events to
PostureStateMachine transitions.

When a BudgetTracker crosses configurable utilization thresholds, this
integration translates them into posture actions:

- **warning** (default 80%): Log a warning. No posture change.
- **downgrade** (default 95%): Transition the agent to TOOL.
- **emergency** (default 100%): Emergency downgrade to PSEUDO.

The integration hooks into the BudgetTracker via ``on_threshold()``
for the fixed 80/95/100% events, and registers an ``on_record()``
callback for custom thresholds at arbitrary utilization percentages.

Direction: kaizen -> eatp (never reverse).
"""

import logging
import math
from typing import Any, Dict, Optional, Set

from kailash.trust.constraints.budget_tracker import BudgetEvent, BudgetTracker
from kailash.trust.posture.postures import (
    PostureStateMachine,
    PostureTransitionRequest,
    TrustPosture,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PostureBudgetIntegration",
]

# Default threshold mapping: fraction of budget consumed -> action
_DEFAULT_THRESHOLDS: Dict[str, float] = {
    "warning": 0.80,  # Log warning only
    "downgrade": 0.95,  # Downgrade to TOOL
    "emergency": 1.0,  # Emergency downgrade to PSEUDO
}

# Valid threshold keys
_VALID_THRESHOLD_KEYS = frozenset({"warning", "downgrade", "emergency"})


class PostureBudgetIntegration:
    """Links a BudgetTracker to a PostureStateMachine for automatic
    posture transitions when budget thresholds are crossed.

    The integration monitors budget utilization via two mechanisms:

    1. The BudgetTracker's ``on_threshold()`` callback fires at fixed
       80/95/100% utilization. Good for default thresholds.
    2. A post-record utilization check handles custom thresholds at
       arbitrary percentages (e.g. ``downgrade=0.70``).

    Each action fires at most once per integration lifetime.

    When utilization crosses configured thresholds:

    - **warning**: Log a warning, no posture change.
    - **downgrade**: Transition agent to TOOL via normal transition.
    - **emergency**: Emergency downgrade agent to PSEUDO (bypasses guards).

    Args:
        budget_tracker: The BudgetTracker to monitor.
        state_machine: The PostureStateMachine to act upon.
        agent_id: The agent whose posture should be managed. Must be
            a non-empty string.
        thresholds: Optional mapping of threshold names to fractions
            (0.0 to 1.0 inclusive, where 1.0 means 100%). Valid keys
            are ``"warning"``, ``"downgrade"``, and ``"emergency"``.

    Raises:
        ValueError: If ``agent_id`` is empty, thresholds contain
            invalid keys, or threshold values are out of range.
    """

    def __init__(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
        agent_id: str,
        thresholds: Optional[Dict[str, float]] = None,
    ) -> None:
        # Validate agent_id
        if not agent_id:
            raise ValueError("agent_id must be a non-empty string, got empty string")

        # Validate and apply thresholds
        if thresholds is not None:
            unknown_keys = set(thresholds.keys()) - _VALID_THRESHOLD_KEYS
            if unknown_keys:
                raise ValueError(
                    f"Invalid threshold keys: {sorted(unknown_keys)}. "
                    f"Valid keys are: {sorted(_VALID_THRESHOLD_KEYS)}"
                )
            for key, value in thresholds.items():
                if not isinstance(value, (int, float)):
                    raise ValueError(
                        f"Threshold '{key}' must be a number, "
                        f"got {type(value).__name__}"
                    )
                if not math.isfinite(value):
                    raise ValueError(f"Threshold '{key}' must be finite, got {value!r}")
                if value <= 0 or value > 1.0:
                    raise ValueError(
                        f"Threshold '{key}' must be in (0.0, 1.0], got {value}"
                    )
            # Merge with defaults: provided keys override defaults
            resolved = dict(_DEFAULT_THRESHOLDS)
            resolved.update(thresholds)
        else:
            resolved = dict(_DEFAULT_THRESHOLDS)

        # Ensure all three keys are present
        missing = _VALID_THRESHOLD_KEYS - set(resolved.keys())
        if missing:
            raise ValueError(
                f"Missing required threshold keys: {sorted(missing)}. "
                f"All of {sorted(_VALID_THRESHOLD_KEYS)} must be defined."
            )

        self._budget_tracker = budget_tracker
        self._state_machine = state_machine
        self._agent_id = agent_id
        self._thresholds = resolved

        # Track which of our integration-level thresholds have fired.
        # Independent of the BudgetTracker's own fired_thresholds tracking.
        self._fired_actions: Set[str] = set()

        # H1: Use the on_record() callback API instead of monkey-patching.
        # This is clean, composable (multiple integrations work), and
        # reversible.  The BudgetTracker fires on_record callbacks after
        # every record() call, outside its lock.
        budget_tracker.on_record(self._check_thresholds)

        logger.info(
            "PostureBudgetIntegration initialized for agent '%s' with "
            "thresholds: warning=%.0f%%, downgrade=%.0f%%, emergency=%.0f%%",
            agent_id,
            resolved["warning"] * 100,
            resolved["downgrade"] * 100,
            resolved["emergency"] * 100,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def agent_id(self) -> str:
        """Return the agent ID this integration manages."""
        return self._agent_id

    @property
    def thresholds(self) -> Dict[str, float]:
        """Return a copy of the configured thresholds."""
        return dict(self._thresholds)

    # ------------------------------------------------------------------
    # Internal: threshold checking
    # ------------------------------------------------------------------

    def _compute_utilization(self) -> float:
        """Compute the current budget utilization as a fraction.

        Uses the BudgetTracker's snapshot to get committed and allocated
        values.  Returns 0.0 if allocated is 0 (avoid division by zero).

        Returns:
            Utilization as a fraction (0.0 to 1.0+).
        """
        snap = self._budget_tracker.snapshot()
        if snap.allocated == 0:
            return 0.0
        return snap.committed / snap.allocated

    def _check_thresholds(self) -> None:
        """Check current utilization against configured thresholds.

        Called after every ``record()`` call on the BudgetTracker.
        Each action fires at most once (tracked via ``_fired_actions``).

        Checks from highest severity to lowest to ensure the most
        severe action is taken first.
        """
        utilization = self._compute_utilization()

        # Check from highest severity to lowest
        if (
            utilization >= self._thresholds["emergency"]
            and "emergency" not in self._fired_actions
        ):
            self._fired_actions.add("emergency")
            self._handle_emergency(utilization)

        if (
            utilization >= self._thresholds["downgrade"]
            and "downgrade" not in self._fired_actions
        ):
            self._fired_actions.add("downgrade")
            self._handle_downgrade(utilization)

        if (
            utilization >= self._thresholds["warning"]
            and "warning" not in self._fired_actions
        ):
            self._fired_actions.add("warning")
            self._handle_warning(utilization)

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _handle_warning(self, utilization: float) -> None:
        """Handle the warning threshold crossing.

        Logs a warning but does NOT change posture.

        Args:
            utilization: Current budget utilization fraction.
        """
        snap = self._budget_tracker.snapshot()
        remaining = max(0, snap.allocated - snap.committed)
        logger.warning(
            "Budget threshold %.0f%% crossed for agent '%s': "
            "utilization=%.1f%%, remaining=%d microdollars, "
            "allocated=%d microdollars",
            self._thresholds["warning"] * 100,
            self._agent_id,
            utilization * 100,
            remaining,
            snap.allocated,
        )

    def _handle_downgrade(self, utilization: float) -> None:
        """Handle the downgrade threshold crossing.

        Attempts to downgrade the agent to TOOL.  If the agent is
        already at SUPERVISED or lower, this is a no-op.

        Args:
            utilization: Current budget utilization fraction.
        """
        current = self._state_machine.get_posture(self._agent_id)
        snap = self._budget_tracker.snapshot()
        remaining = max(0, snap.allocated - snap.committed)

        # Only downgrade if current posture is above SUPERVISED
        if current <= TrustPosture.TOOL:
            logger.info(
                "Budget %.0f%% threshold for agent '%s': already at %s, "
                "no further downgrade from this threshold",
                self._thresholds["downgrade"] * 100,
                self._agent_id,
                current.value,
            )
            return

        request = PostureTransitionRequest(
            agent_id=self._agent_id,
            from_posture=current,
            to_posture=TrustPosture.TOOL,
            reason=f"Budget threshold crossed: utilization="
            f"{utilization * 100:.1f}% "
            f"(remaining={remaining} microdollars)",
            requester_id="posture_budget_integration",
            metadata={
                "trigger": "budget_threshold",
                "threshold_name": "downgrade",
                "threshold_value": self._thresholds["downgrade"],
                "utilization": utilization,
                "remaining_microdollars": remaining,
                "allocated_microdollars": snap.allocated,
            },
        )

        result = self._state_machine.transition(request)
        if result.success:
            logger.warning(
                "Budget %.0f%% threshold: agent '%s' downgraded " "from %s to TOOL",
                self._thresholds["downgrade"] * 100,
                self._agent_id,
                current.value,
            )
        else:
            # M5: If the failure is due to a stale from_posture (posture
            # changed between our get_posture() and transition() calls),
            # re-read the current posture and retry once.
            if "does not match" in (result.reason or ""):
                refreshed = self._state_machine.get_posture(self._agent_id)
                if refreshed <= TrustPosture.TOOL:
                    logger.info(
                        "Budget %.0f%% threshold for agent '%s': posture "
                        "already at %s after refresh, no downgrade needed",
                        self._thresholds["downgrade"] * 100,
                        self._agent_id,
                        refreshed.value,
                    )
                    return

                retry_request = PostureTransitionRequest(
                    agent_id=self._agent_id,
                    from_posture=refreshed,
                    to_posture=TrustPosture.TOOL,
                    reason=request.reason,
                    requester_id="posture_budget_integration",
                    metadata=dict(request.metadata),
                )
                retry_result = self._state_machine.transition(retry_request)
                if retry_result.success:
                    logger.warning(
                        "Budget %.0f%% threshold: agent '%s' downgraded "
                        "from %s to TOOL (retry after stale posture)",
                        self._thresholds["downgrade"] * 100,
                        self._agent_id,
                        refreshed.value,
                    )
                    return
                else:
                    logger.error(
                        "Budget %.0f%% threshold: retry also failed for "
                        "agent '%s': %s",
                        self._thresholds["downgrade"] * 100,
                        self._agent_id,
                        retry_result.reason,
                    )
                    return

            logger.error(
                "Budget %.0f%% threshold: failed to downgrade agent '%s' "
                "from %s to TOOL: %s",
                self._thresholds["downgrade"] * 100,
                self._agent_id,
                current.value,
                result.reason,
            )

    def _handle_emergency(self, utilization: float) -> None:
        """Handle the emergency/exhausted threshold crossing.

        Triggers emergency_downgrade to PSEUDO, bypassing all guards.

        Args:
            utilization: Current budget utilization fraction.
        """
        snap = self._budget_tracker.snapshot()
        remaining = max(0, snap.allocated - snap.committed)

        result = self._state_machine.emergency_downgrade(
            agent_id=self._agent_id,
            reason=f"Budget exhausted: utilization="
            f"{utilization * 100:.1f}% "
            f"(remaining={remaining} microdollars)",
            requester_id="posture_budget_integration",
        )

        logger.critical(
            "Budget exhausted: agent '%s' emergency downgraded to "
            "PSEUDO (from %s). Utilization: %.1f%%, "
            "remaining: %d microdollars",
            self._agent_id,
            result.from_posture.value,
            utilization * 100,
            remaining,
        )
