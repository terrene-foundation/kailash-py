# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for PostureStateMachine default posture fix (RT-17 / TODO-22).

CARE spec requires that tool agents start at SUPERVISED (autonomy_level=2),
not SHARED_PLANNING (autonomy_level=3).  This module validates:

- Default posture is SUPERVISED when no initial_posture is given
- Explicit initial_posture=SHARED_PLANNING works (backward compat)
- Explicit initial_posture=PSEUDO_AGENT works
- All existing posture functionality remains intact
"""

from __future__ import annotations

import pytest

from kailash.trust.posture.postures import (
    PostureStateMachine,
    PostureTransitionRequest,
    TrustPosture,
)


class TestPostureStateMachineDefaultPosture:
    """PostureStateMachine defaults to SUPERVISED per CARE spec."""

    def test_default_posture_is_supervised(self) -> None:
        """When no default_posture is passed, new agents get SUPERVISED."""
        machine = PostureStateMachine()
        posture = machine.get_posture("new-agent")
        assert (
            posture == TrustPosture.SUPERVISED
        ), f"Expected default posture SUPERVISED (CARE spec), got {posture.value}"

    def test_explicit_shared_planning_default(self) -> None:
        """Callers can still pass default_posture=SHARED_PLANNING explicitly."""
        machine = PostureStateMachine(
            default_posture=TrustPosture.SHARED_PLANNING,
        )
        posture = machine.get_posture("new-agent")
        assert posture == TrustPosture.SHARED_PLANNING

    def test_explicit_pseudo_agent_default(self) -> None:
        """Callers can pass default_posture=PSEUDO_AGENT for maximum restriction."""
        machine = PostureStateMachine(
            default_posture=TrustPosture.PSEUDO_AGENT,
        )
        posture = machine.get_posture("new-agent")
        assert posture == TrustPosture.PSEUDO_AGENT

    def test_explicit_delegated_default(self) -> None:
        """Callers can pass default_posture=DELEGATED (full autonomy)."""
        machine = PostureStateMachine(
            default_posture=TrustPosture.DELEGATED,
        )
        posture = machine.get_posture("new-agent")
        assert posture == TrustPosture.DELEGATED

    def test_explicit_continuous_insight_default(self) -> None:
        """Callers can pass default_posture=CONTINUOUS_INSIGHT."""
        machine = PostureStateMachine(
            default_posture=TrustPosture.CONTINUOUS_INSIGHT,
        )
        posture = machine.get_posture("new-agent")
        assert posture == TrustPosture.CONTINUOUS_INSIGHT

    def test_default_posture_used_for_unknown_agents(self) -> None:
        """Unknown agent IDs return the default posture, not an error."""
        machine = PostureStateMachine()
        # Multiple unknown agent IDs all get the default
        assert machine.get_posture("unknown-1") == TrustPosture.SUPERVISED
        assert machine.get_posture("unknown-2") == TrustPosture.SUPERVISED

    def test_set_posture_overrides_default(self) -> None:
        """After set_posture, the agent gets the set posture, not the default."""
        machine = PostureStateMachine()
        machine.set_posture("agent-x", TrustPosture.DELEGATED)
        assert machine.get_posture("agent-x") == TrustPosture.DELEGATED

    def test_transition_from_default_posture(self) -> None:
        """An agent at the default SUPERVISED posture can transition."""
        machine = PostureStateMachine(require_upgrade_approval=False)
        # Agent starts at SUPERVISED (default)
        assert machine.get_posture("agent-new") == TrustPosture.SUPERVISED

        # Upgrade from SUPERVISED to SHARED_PLANNING
        result = machine.transition(
            PostureTransitionRequest(
                agent_id="agent-new",
                from_posture=TrustPosture.SUPERVISED,
                to_posture=TrustPosture.SHARED_PLANNING,
                reason="Graduated from supervised mode",
            )
        )
        assert result.success is True
        assert machine.get_posture("agent-new") == TrustPosture.SHARED_PLANNING

    def test_supervised_is_safer_than_shared_planning(self) -> None:
        """SUPERVISED has lower autonomy level than SHARED_PLANNING."""
        assert (
            TrustPosture.SUPERVISED.autonomy_level
            < TrustPosture.SHARED_PLANNING.autonomy_level
        )
        assert TrustPosture.SUPERVISED < TrustPosture.SHARED_PLANNING
