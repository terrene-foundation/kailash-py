# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for AgentPosture.intersect() and envelope posture-ceiling typing.

Wave 1G of the platform-architecture-convergence remediation sprint
(SPEC-04 CRITICAL #3/#4). Verifies:

- ``AgentPosture.intersect()`` picks the stricter (lower-autonomy) posture
  for every ordered pair, with ``None`` treated as unbounded.
- ``AgentPosture.coerce()`` accepts enum members, lowercase string values,
  and ``None`` but rejects unknown strings with a typed error.
- ``ConstraintEnvelope.posture_ceiling`` is typed ``AgentPosture`` and
  coerces legacy string inputs at construction time.
- ``ConstraintEnvelope.intersect()`` uses the posture intersection method
  to tighten the ceiling monotonically (stricter of the two wins).
- Canonical JSON serialization still emits the posture ceiling as its
  lowercase string value so the Rust SDK wire format is unchanged.
"""

from __future__ import annotations

import itertools
import json

import pytest
from kailash.trust.envelope import (
    AgentPosture,
    ConstraintEnvelope,
    EnvelopeValidationError,
)
from kailash.trust.posture import AgentPosture as ReExportedAgentPosture


class TestAgentPostureReExport:
    """``AgentPosture`` must live on ``kailash.trust.posture`` per SPEC-04."""

    def test_reexport_is_identical(self) -> None:
        assert ReExportedAgentPosture is AgentPosture

    def test_five_canonical_values(self) -> None:
        assert [p.value for p in AgentPosture] == [
            "pseudo_agent",
            "supervised",
            "shared_planning",
            "continuous_insight",
            "delegated",
        ]


class TestAgentPostureIntersect:
    """``AgentPosture.intersect()`` returns the stricter of the two postures."""

    def test_intersect_picks_stricter_of_ordered_pair(self) -> None:
        assert (
            AgentPosture.SUPERVISED.intersect(AgentPosture.DELEGATED)
            is AgentPosture.SUPERVISED
        )
        assert (
            AgentPosture.DELEGATED.intersect(AgentPosture.SUPERVISED)
            is AgentPosture.SUPERVISED
        )

    def test_intersect_is_idempotent(self) -> None:
        for posture in AgentPosture:
            assert posture.intersect(posture) is posture

    def test_intersect_is_commutative(self) -> None:
        for a, b in itertools.product(AgentPosture, repeat=2):
            assert a.intersect(b) is b.intersect(a)

    def test_intersect_is_associative(self) -> None:
        for a, b, c in itertools.product(AgentPosture, repeat=3):
            left = a.intersect(b).intersect(c)
            right = a.intersect(b.intersect(c))
            assert left is right

    def test_intersect_none_is_unbounded(self) -> None:
        # ``None`` on either side is treated as unbounded -- the concrete
        # posture wins.
        for posture in AgentPosture:
            assert posture.intersect(None) is posture

    def test_intersect_monotonic_tightening(self) -> None:
        # The result must fit BOTH input ceilings.
        for a, b in itertools.product(AgentPosture, repeat=2):
            result = a.intersect(b)
            assert result.fits_ceiling(a)
            assert result.fits_ceiling(b)


class TestAgentPostureCoerce:
    """``AgentPosture.coerce()`` accepts wire-format strings."""

    def test_coerce_none_returns_none(self) -> None:
        assert AgentPosture.coerce(None) is None

    def test_coerce_enum_returns_same_instance(self) -> None:
        for posture in AgentPosture:
            assert AgentPosture.coerce(posture) is posture

    @pytest.mark.parametrize(
        "value",
        [
            "pseudo_agent",
            "supervised",
            "shared_planning",
            "continuous_insight",
            "delegated",
        ],
    )
    def test_coerce_valid_string(self, value: str) -> None:
        result = AgentPosture.coerce(value)
        assert isinstance(result, AgentPosture)
        assert result.value == value

    def test_coerce_invalid_string_raises(self) -> None:
        with pytest.raises(EnvelopeValidationError, match="posture must be one of"):
            AgentPosture.coerce("nonexistent")

    def test_coerce_unexpected_type_raises(self) -> None:
        with pytest.raises(EnvelopeValidationError, match="AgentPosture"):
            AgentPosture.coerce(42)  # type: ignore[arg-type]


class TestConstraintEnvelopePostureTyping:
    """``ConstraintEnvelope.posture_ceiling`` is an ``AgentPosture`` enum."""

    def test_string_input_coerced_to_enum(self) -> None:
        env = ConstraintEnvelope(posture_ceiling="supervised")
        assert isinstance(env.posture_ceiling, AgentPosture)
        assert env.posture_ceiling is AgentPosture.SUPERVISED

    def test_enum_input_preserved(self) -> None:
        env = ConstraintEnvelope(posture_ceiling=AgentPosture.DELEGATED)
        assert env.posture_ceiling is AgentPosture.DELEGATED

    def test_invalid_string_rejected_with_field_context(self) -> None:
        with pytest.raises(
            EnvelopeValidationError, match="posture_ceiling must be one of"
        ):
            ConstraintEnvelope(posture_ceiling="nonexistent")

    def test_canonical_json_emits_lowercase_string(self) -> None:
        env = ConstraintEnvelope(posture_ceiling=AgentPosture.SUPERVISED)
        encoded = json.loads(env.to_canonical_json())
        assert encoded["posture_ceiling"] == "supervised"

    def test_from_dict_round_trip_preserves_enum(self) -> None:
        env = ConstraintEnvelope(posture_ceiling=AgentPosture.SHARED_PLANNING)
        encoded = json.loads(env.to_canonical_json())
        # ``envelope_hash`` is computed, not a known input field; strip
        # before round-tripping.
        encoded.pop("envelope_hash", None)
        restored = ConstraintEnvelope.from_dict(encoded)
        assert restored.posture_ceiling is AgentPosture.SHARED_PLANNING

    def test_string_equality_preserved(self) -> None:
        # ``AgentPosture`` is ``str``-backed, so existing code paths that
        # compare against literal strings continue to work.
        env = ConstraintEnvelope(posture_ceiling="supervised")
        assert env.posture_ceiling == "supervised"


class TestConstraintEnvelopeIntersectPostureCeiling:
    """``ConstraintEnvelope.intersect()`` tightens the posture ceiling."""

    def test_intersect_picks_stricter_ceiling(self) -> None:
        a = ConstraintEnvelope(posture_ceiling=AgentPosture.DELEGATED)
        b = ConstraintEnvelope(posture_ceiling=AgentPosture.SUPERVISED)
        result = a.intersect(b)
        assert result.posture_ceiling is AgentPosture.SUPERVISED

    def test_intersect_with_none_uses_the_other_side(self) -> None:
        a = ConstraintEnvelope()
        b = ConstraintEnvelope(posture_ceiling=AgentPosture.SUPERVISED)
        assert a.intersect(b).posture_ceiling is AgentPosture.SUPERVISED
        assert b.intersect(a).posture_ceiling is AgentPosture.SUPERVISED

    def test_intersect_both_none(self) -> None:
        a = ConstraintEnvelope()
        b = ConstraintEnvelope()
        assert a.intersect(b).posture_ceiling is None

    def test_intersect_is_monotonic_never_loosens(self) -> None:
        # Intersecting any envelope with one carrying a stricter ceiling
        # can only tighten (never loosen) the posture ceiling.
        baseline = ConstraintEnvelope(posture_ceiling=AgentPosture.DELEGATED)
        stricter = ConstraintEnvelope(posture_ceiling=AgentPosture.PSEUDO_AGENT)
        result = baseline.intersect(stricter)
        assert result.posture_ceiling is AgentPosture.PSEUDO_AGENT

    def test_intersect_commutative(self) -> None:
        a = ConstraintEnvelope(posture_ceiling=AgentPosture.DELEGATED)
        b = ConstraintEnvelope(posture_ceiling=AgentPosture.SUPERVISED)
        assert a.intersect(b).posture_ceiling is b.intersect(a).posture_ceiling
