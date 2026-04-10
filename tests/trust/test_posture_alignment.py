# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for posture enum alignment (Decision 007, issue #386).

Verifies that all three posture enums (AgentPosture, TrustPosture,
TrustPostureLevel) use canonical EATP names, accept old names via
_missing_(), and remain interoperable.
"""

from __future__ import annotations

import pytest
from kailash.trust.envelope import AgentPosture
from kailash.trust.posture.postures import TrustPosture

# ---------------------------------------------------------------------------
# Canonical names
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestCanonicalNames:
    """Canonical EATP posture names are the primary enum members."""

    def test_agent_posture_canonical_members(self) -> None:
        """AgentPosture has all 5 EATP canonical members."""
        assert AgentPosture.PSEUDO.value == "pseudo"
        assert AgentPosture.SUPERVISED.value == "supervised"
        assert AgentPosture.TOOL.value == "tool"
        assert AgentPosture.DELEGATING.value == "delegating"
        assert AgentPosture.AUTONOMOUS.value == "autonomous"

    def test_trust_posture_canonical_members(self) -> None:
        """TrustPosture has all 5 EATP canonical members."""
        assert TrustPosture.PSEUDO.value == "pseudo"
        assert TrustPosture.TOOL.value == "tool"
        assert TrustPosture.SUPERVISED.value == "supervised"
        assert TrustPosture.DELEGATING.value == "delegating"
        assert TrustPosture.AUTONOMOUS.value == "autonomous"

    def test_exactly_five_members_agent_posture(self) -> None:
        """AgentPosture has exactly 5 members."""
        assert len(AgentPosture) == 5

    def test_exactly_five_members_trust_posture(self) -> None:
        """TrustPosture has exactly 5 members."""
        assert len(TrustPosture) == 5


# ---------------------------------------------------------------------------
# Wire format
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestWireFormat:
    """Wire format uses lowercase canonical names."""

    def test_agent_posture_wire_values(self) -> None:
        """AgentPosture wire values are lowercase canonical strings."""
        expected = {"pseudo", "supervised", "tool", "delegating", "autonomous"}
        actual = {p.value for p in AgentPosture}
        assert actual == expected

    def test_trust_posture_wire_values(self) -> None:
        """TrustPosture wire values are lowercase canonical strings."""
        expected = {"pseudo", "tool", "supervised", "delegating", "autonomous"}
        actual = {p.value for p in TrustPosture}
        assert actual == expected

    def test_agent_posture_str_equality(self) -> None:
        """AgentPosture members compare equal to their wire-format strings."""
        assert AgentPosture.SUPERVISED == "supervised"
        assert AgentPosture.AUTONOMOUS == "autonomous"
        assert AgentPosture.PSEUDO == "pseudo"

    def test_trust_posture_str_equality(self) -> None:
        """TrustPosture members compare equal to their wire-format strings."""
        assert TrustPosture.SUPERVISED == "supervised"
        assert TrustPosture.AUTONOMOUS == "autonomous"
        assert TrustPosture.PSEUDO == "pseudo"


# ---------------------------------------------------------------------------
# Backward compatibility via _missing_()
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestBackwardCompatibility:
    """Old names accepted via _missing_() for wire-format deserialization."""

    @pytest.mark.parametrize(
        ("old_value", "expected"),
        [
            ("pseudo_agent", AgentPosture.PSEUDO),
            ("shared_planning", AgentPosture.TOOL),
            ("continuous_insight", AgentPosture.DELEGATING),
            ("delegated", AgentPosture.AUTONOMOUS),
            # Uppercase old names
            ("PSEUDO_AGENT", AgentPosture.PSEUDO),
            ("SHARED_PLANNING", AgentPosture.TOOL),
            ("CONTINUOUS_INSIGHT", AgentPosture.DELEGATING),
            ("DELEGATED", AgentPosture.AUTONOMOUS),
        ],
    )
    def test_agent_posture_old_names(
        self, old_value: str, expected: AgentPosture
    ) -> None:
        """AgentPosture accepts old wire-format values."""
        assert AgentPosture(old_value) is expected

    @pytest.mark.parametrize(
        ("old_value", "expected"),
        [
            ("delegated", TrustPosture.AUTONOMOUS),
            ("continuous_insight", TrustPosture.DELEGATING),
            ("shared_planning", TrustPosture.SUPERVISED),
            ("pseudo_agent", TrustPosture.PSEUDO),
            # CARE spec alias
            ("pseudo", TrustPosture.PSEUDO),
            ("pseudoagent", TrustPosture.PSEUDO),
        ],
    )
    def test_trust_posture_old_names(
        self, old_value: str, expected: TrustPosture
    ) -> None:
        """TrustPosture accepts old wire-format values."""
        assert TrustPosture(old_value) is expected

    def test_canonical_names_still_work(self) -> None:
        """New canonical values construct correctly."""
        assert AgentPosture("pseudo") is AgentPosture.PSEUDO
        assert AgentPosture("tool") is AgentPosture.TOOL
        assert AgentPosture("supervised") is AgentPosture.SUPERVISED
        assert AgentPosture("delegating") is AgentPosture.DELEGATING
        assert AgentPosture("autonomous") is AgentPosture.AUTONOMOUS

    def test_invalid_value_raises(self) -> None:
        """Invalid values still raise ValueError."""
        with pytest.raises(ValueError):
            AgentPosture("not_a_posture")
        with pytest.raises(ValueError):
            TrustPosture("not_a_posture")


# ---------------------------------------------------------------------------
# Alias resolution (TrustPostureLevel)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestAliasResolution:
    """TrustPostureLevel is a direct alias for TrustPosture."""

    def test_trust_posture_level_is_trust_posture(self) -> None:
        """TrustPostureLevel is the same class as TrustPosture."""
        from kailash.trust.pact.config import TrustPostureLevel

        assert TrustPostureLevel is TrustPosture

    def test_isinstance_cross_check(self) -> None:
        """Values created via TrustPostureLevel pass isinstance for TrustPosture."""
        from kailash.trust.pact.config import TrustPostureLevel

        val = TrustPostureLevel.SUPERVISED
        assert isinstance(val, TrustPosture)
        assert isinstance(val, TrustPostureLevel)

    def test_alias_members_match(self) -> None:
        """TrustPostureLevel members are identical objects to TrustPosture members."""
        from kailash.trust.pact.config import TrustPostureLevel

        assert TrustPostureLevel.AUTONOMOUS is TrustPosture.AUTONOMOUS
        assert TrustPostureLevel.DELEGATING is TrustPosture.DELEGATING
        assert TrustPostureLevel.SUPERVISED is TrustPosture.SUPERVISED
        assert TrustPostureLevel.TOOL is TrustPosture.TOOL
        assert TrustPostureLevel.PSEUDO is TrustPosture.PSEUDO


# ---------------------------------------------------------------------------
# Comparison methods (TrustPosture)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestComparisonMethods:
    """TrustPosture ordering and comparison still work correctly."""

    def test_autonomy_levels(self) -> None:
        """Autonomy levels match canonical ordering."""
        assert TrustPosture.PSEUDO.autonomy_level == 1
        assert TrustPosture.TOOL.autonomy_level == 2
        assert TrustPosture.SUPERVISED.autonomy_level == 3
        assert TrustPosture.DELEGATING.autonomy_level == 4
        assert TrustPosture.AUTONOMOUS.autonomy_level == 5

    def test_ordering_lt(self) -> None:
        """Less-than comparison based on autonomy level."""
        assert TrustPosture.PSEUDO < TrustPosture.TOOL
        assert TrustPosture.TOOL < TrustPosture.SUPERVISED
        assert TrustPosture.SUPERVISED < TrustPosture.DELEGATING
        assert TrustPosture.DELEGATING < TrustPosture.AUTONOMOUS

    def test_ordering_gt(self) -> None:
        """Greater-than comparison based on autonomy level."""
        assert TrustPosture.AUTONOMOUS > TrustPosture.DELEGATING
        assert TrustPosture.DELEGATING > TrustPosture.SUPERVISED

    def test_can_upgrade_to(self) -> None:
        """can_upgrade_to returns True for higher autonomy targets."""
        assert TrustPosture.TOOL.can_upgrade_to(TrustPosture.SUPERVISED)
        assert not TrustPosture.SUPERVISED.can_upgrade_to(TrustPosture.TOOL)

    def test_can_downgrade_to(self) -> None:
        """can_downgrade_to returns True for lower autonomy targets."""
        assert TrustPosture.SUPERVISED.can_downgrade_to(TrustPosture.TOOL)
        assert not TrustPosture.TOOL.can_downgrade_to(TrustPosture.SUPERVISED)


# ---------------------------------------------------------------------------
# AgentPosture ordering and methods
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestAgentPostureOrdering:
    """AgentPosture ordering, ceiling, and intersect methods."""

    def test_ordering_values(self) -> None:
        """Ordering dict maps canonical members to 0-4."""
        order = AgentPosture.ordering()
        assert order[AgentPosture.PSEUDO] == 0
        assert order[AgentPosture.SUPERVISED] == 1
        assert order[AgentPosture.TOOL] == 2
        assert order[AgentPosture.DELEGATING] == 3
        assert order[AgentPosture.AUTONOMOUS] == 4

    def test_fits_ceiling(self) -> None:
        """fits_ceiling checks autonomy is at or below ceiling."""
        assert AgentPosture.TOOL.fits_ceiling(AgentPosture.AUTONOMOUS)
        assert AgentPosture.AUTONOMOUS.fits_ceiling(AgentPosture.AUTONOMOUS)
        assert not AgentPosture.AUTONOMOUS.fits_ceiling(AgentPosture.TOOL)

    def test_clamp_to_ceiling(self) -> None:
        """clamp_to_ceiling returns min of self and ceiling."""
        assert (
            AgentPosture.AUTONOMOUS.clamp_to_ceiling(AgentPosture.TOOL)
            is AgentPosture.TOOL
        )
        assert (
            AgentPosture.TOOL.clamp_to_ceiling(AgentPosture.AUTONOMOUS)
            is AgentPosture.TOOL
        )

    def test_intersect(self) -> None:
        """intersect returns the stricter (lower autonomy) posture."""
        assert (
            AgentPosture.AUTONOMOUS.intersect(AgentPosture.DELEGATING)
            is AgentPosture.DELEGATING
        )
        assert AgentPosture.TOOL.intersect(AgentPosture.AUTONOMOUS) is AgentPosture.TOOL
        # None means unbounded
        assert AgentPosture.AUTONOMOUS.intersect(None) is AgentPosture.AUTONOMOUS

    def test_coerce_canonical(self) -> None:
        """coerce() accepts canonical wire-format strings."""
        assert AgentPosture.coerce("pseudo") is AgentPosture.PSEUDO
        assert AgentPosture.coerce("tool") is AgentPosture.TOOL
        assert AgentPosture.coerce("autonomous") is AgentPosture.AUTONOMOUS
        assert AgentPosture.coerce(None) is None

    def test_coerce_old_values(self) -> None:
        """coerce() accepts old wire-format strings via _missing_()."""
        assert AgentPosture.coerce("pseudo_agent") is AgentPosture.PSEUDO
        assert AgentPosture.coerce("shared_planning") is AgentPosture.TOOL
        assert AgentPosture.coerce("continuous_insight") is AgentPosture.DELEGATING
        assert AgentPosture.coerce("delegated") is AgentPosture.AUTONOMOUS
