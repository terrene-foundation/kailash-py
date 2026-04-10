# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for PostureStateMachine default posture fix (RT-17 / TODO-22).

CARE spec requires that tool agents start at TOOL (autonomy_level=2),
not SUPERVISED (autonomy_level=3).  This module validates:

- Default posture is TOOL when no initial_posture is given
- Explicit initial_posture=SUPERVISED works (backward compat)
- Explicit initial_posture=PSEUDO works
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
    """PostureStateMachine defaults to TOOL per CARE spec."""

    def test_default_posture_is_tool(self) -> None:
        """When no default_posture is passed, new agents get TOOL."""
        machine = PostureStateMachine()
        posture = machine.get_posture("new-agent")
        assert (
            posture == TrustPosture.TOOL
        ), f"Expected default posture TOOL (CARE spec), got {posture.value}"

    def test_explicit_supervised_default(self) -> None:
        """Callers can still pass default_posture=SUPERVISED explicitly."""
        machine = PostureStateMachine(
            default_posture=TrustPosture.SUPERVISED,
        )
        posture = machine.get_posture("new-agent")
        assert posture == TrustPosture.SUPERVISED

    def test_explicit_pseudo_default(self) -> None:
        """Callers can pass default_posture=PSEUDO for maximum restriction."""
        machine = PostureStateMachine(
            default_posture=TrustPosture.PSEUDO,
        )
        posture = machine.get_posture("new-agent")
        assert posture == TrustPosture.PSEUDO

    def test_explicit_autonomous_default(self) -> None:
        """Callers can pass default_posture=AUTONOMOUS (full autonomy)."""
        machine = PostureStateMachine(
            default_posture=TrustPosture.AUTONOMOUS,
        )
        posture = machine.get_posture("new-agent")
        assert posture == TrustPosture.AUTONOMOUS

    def test_explicit_delegating_default(self) -> None:
        """Callers can pass default_posture=DELEGATING."""
        machine = PostureStateMachine(
            default_posture=TrustPosture.DELEGATING,
        )
        posture = machine.get_posture("new-agent")
        assert posture == TrustPosture.DELEGATING

    def test_default_posture_used_for_unknown_agents(self) -> None:
        """Unknown agent IDs return the default posture, not an error."""
        machine = PostureStateMachine()
        # Multiple unknown agent IDs all get the default
        assert machine.get_posture("unknown-1") == TrustPosture.TOOL
        assert machine.get_posture("unknown-2") == TrustPosture.TOOL

    def test_set_posture_overrides_default(self) -> None:
        """After set_posture, the agent gets the set posture, not the default."""
        machine = PostureStateMachine()
        machine.set_posture("agent-x", TrustPosture.AUTONOMOUS)
        assert machine.get_posture("agent-x") == TrustPosture.AUTONOMOUS

    def test_transition_from_default_posture(self) -> None:
        """An agent at the default SUPERVISED posture can transition."""
        machine = PostureStateMachine(require_upgrade_approval=False)
        # Agent starts at SUPERVISED (default)
        assert machine.get_posture("agent-new") == TrustPosture.TOOL

        # Upgrade from SUPERVISED to SHARED_PLANNING
        result = machine.transition(
            PostureTransitionRequest(
                agent_id="agent-new",
                from_posture=TrustPosture.TOOL,
                to_posture=TrustPosture.SUPERVISED,
                reason="Graduated from supervised mode",
            )
        )
        assert result.success is True
        assert machine.get_posture("agent-new") == TrustPosture.SUPERVISED

    def test_supervised_is_safer_than_shared_planning(self) -> None:
        """SUPERVISED has lower autonomy level than SHARED_PLANNING."""
        assert TrustPosture.TOOL.autonomy_level < TrustPosture.SUPERVISED.autonomy_level
        assert TrustPosture.TOOL < TrustPosture.SUPERVISED
