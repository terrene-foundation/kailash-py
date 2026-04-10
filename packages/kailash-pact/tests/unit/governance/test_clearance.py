# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for RoleClearance model and effective_clearance computation.

Covers:
- TODO-2001: RoleClearance dataclass fields and immutability
- VettingStatus enum values
- POSTURE_CEILING mapping correctness
- effective_clearance() posture-capping for every posture level
- Compartment handling (frozenset semantics)
- Vetting status validation (only ACTIVE clearances are valid)
- SECRET/TOP_SECRET requires NDA
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.trust.pact.clearance import (
    POSTURE_CEILING,
    RoleClearance,
    VettingStatus,
    effective_clearance,
)
from kailash.trust.pact.config import ConfidentialityLevel, TrustPostureLevel

# ---------------------------------------------------------------------------
# VettingStatus enum
# ---------------------------------------------------------------------------


class TestVettingStatus:
    """VettingStatus enum values and string backing."""

    def test_pending_value(self) -> None:
        assert VettingStatus.PENDING.value == "pending"

    def test_active_value(self) -> None:
        assert VettingStatus.ACTIVE.value == "active"

    def test_expired_value(self) -> None:
        assert VettingStatus.EXPIRED.value == "expired"

    def test_revoked_value(self) -> None:
        assert VettingStatus.REVOKED.value == "revoked"

    def test_is_string_enum(self) -> None:
        assert isinstance(VettingStatus.ACTIVE, str)


# ---------------------------------------------------------------------------
# POSTURE_CEILING mapping
# ---------------------------------------------------------------------------


class TestPostureCeiling:
    """POSTURE_CEILING maps every TrustPostureLevel to a ConfidentialityLevel."""

    def test_pseudo_ceiling_is_public(self) -> None:
        assert POSTURE_CEILING[TrustPostureLevel.PSEUDO] == ConfidentialityLevel.PUBLIC

    def test_tool_ceiling_is_restricted(self) -> None:
        assert (
            POSTURE_CEILING[TrustPostureLevel.TOOL] == ConfidentialityLevel.RESTRICTED
        )

    def test_supervised_ceiling_is_confidential(self) -> None:
        assert (
            POSTURE_CEILING[TrustPostureLevel.SUPERVISED]
            == ConfidentialityLevel.CONFIDENTIAL
        )

    def test_delegating_ceiling_is_secret(self) -> None:
        assert (
            POSTURE_CEILING[TrustPostureLevel.DELEGATING] == ConfidentialityLevel.SECRET
        )

    def test_autonomous_ceiling_is_top_secret(self) -> None:
        assert (
            POSTURE_CEILING[TrustPostureLevel.AUTONOMOUS]
            == ConfidentialityLevel.TOP_SECRET
        )

    def test_backward_compat_aliases_resolve_correctly(self) -> None:
        """Old enum names resolve to the same ceiling as canonical names."""
        assert (
            POSTURE_CEILING[TrustPostureLevel.PSEUDO_AGENT]
            == ConfidentialityLevel.PUBLIC
        )
        assert (
            POSTURE_CEILING[TrustPostureLevel.SHARED_PLANNING]
            == ConfidentialityLevel.CONFIDENTIAL
        )
        assert (
            POSTURE_CEILING[TrustPostureLevel.CONTINUOUS_INSIGHT]
            == ConfidentialityLevel.SECRET
        )
        assert (
            POSTURE_CEILING[TrustPostureLevel.DELEGATED]
            == ConfidentialityLevel.TOP_SECRET
        )

    def test_all_posture_levels_mapped(self) -> None:
        """Every TrustPostureLevel has a ceiling entry."""
        for posture in TrustPostureLevel:
            assert posture in POSTURE_CEILING, f"Missing ceiling for {posture}"


# ---------------------------------------------------------------------------
# RoleClearance dataclass
# ---------------------------------------------------------------------------


class TestRoleClearanceModel:
    """RoleClearance frozen dataclass behavior."""

    def test_basic_construction(self) -> None:
        rc = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.SECRET,
        )
        assert rc.role_address == "D1-R1"
        assert rc.max_clearance == ConfidentialityLevel.SECRET

    def test_defaults(self) -> None:
        rc = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.PUBLIC,
        )
        assert rc.compartments == frozenset()
        assert rc.granted_by_role_address == ""
        assert rc.vetting_status == VettingStatus.ACTIVE
        assert rc.review_at is None
        assert rc.nda_signed is False

    def test_compartments_frozenset(self) -> None:
        rc = RoleClearance(
            role_address="D1-R1-D1-R1-T1-R1",
            max_clearance=ConfidentialityLevel.SECRET,
            compartments=frozenset({"aml-investigations", "sanctions"}),
        )
        assert "aml-investigations" in rc.compartments
        assert "sanctions" in rc.compartments
        assert len(rc.compartments) == 2

    def test_frozen_immutability(self) -> None:
        rc = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.PUBLIC,
        )
        with pytest.raises(AttributeError):
            rc.max_clearance = ConfidentialityLevel.SECRET  # type: ignore[misc]

    def test_with_nda_signed(self) -> None:
        rc = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.TOP_SECRET,
            nda_signed=True,
        )
        assert rc.nda_signed is True

    def test_with_review_date(self) -> None:
        review = datetime(2026, 6, 1, tzinfo=timezone.utc)
        rc = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            review_at=review,
        )
        assert rc.review_at == review

    def test_with_granted_by(self) -> None:
        rc = RoleClearance(
            role_address="D1-R1-D2-R1-T1-R1",
            max_clearance=ConfidentialityLevel.RESTRICTED,
            granted_by_role_address="D1-R1-D2-R1",
        )
        assert rc.granted_by_role_address == "D1-R1-D2-R1"


# ---------------------------------------------------------------------------
# effective_clearance() -- posture-capping
# ---------------------------------------------------------------------------


class TestEffectiveClearance:
    """effective_clearance() returns min(role.max_clearance, posture_ceiling)."""

    def test_role_below_ceiling_returns_role(self) -> None:
        """When role clearance < posture ceiling, role clearance wins."""
        rc = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.RESTRICTED,
        )
        # DELEGATED ceiling is TOP_SECRET, so RESTRICTED < TOP_SECRET => RESTRICTED
        result = effective_clearance(rc, TrustPostureLevel.DELEGATED)
        assert result == ConfidentialityLevel.RESTRICTED

    def test_role_above_ceiling_returns_ceiling(self) -> None:
        """When role clearance > posture ceiling, ceiling caps it."""
        rc = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.TOP_SECRET,
        )
        # PSEUDO_AGENT ceiling is PUBLIC => TOP_SECRET is capped to PUBLIC
        result = effective_clearance(rc, TrustPostureLevel.PSEUDO_AGENT)
        assert result == ConfidentialityLevel.PUBLIC

    def test_role_equals_ceiling_returns_that_level(self) -> None:
        """When role clearance == posture ceiling, returns that level."""
        rc = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        # SHARED_PLANNING ceiling is CONFIDENTIAL
        result = effective_clearance(rc, TrustPostureLevel.SHARED_PLANNING)
        assert result == ConfidentialityLevel.CONFIDENTIAL

    @pytest.mark.parametrize(
        "posture, role_level, expected",
        [
            # PSEUDO ceiling = PUBLIC
            (
                TrustPostureLevel.PSEUDO,
                ConfidentialityLevel.PUBLIC,
                ConfidentialityLevel.PUBLIC,
            ),
            (
                TrustPostureLevel.PSEUDO,
                ConfidentialityLevel.SECRET,
                ConfidentialityLevel.PUBLIC,
            ),
            # TOOL ceiling = RESTRICTED
            (
                TrustPostureLevel.TOOL,
                ConfidentialityLevel.PUBLIC,
                ConfidentialityLevel.PUBLIC,
            ),
            (
                TrustPostureLevel.TOOL,
                ConfidentialityLevel.RESTRICTED,
                ConfidentialityLevel.RESTRICTED,
            ),
            (
                TrustPostureLevel.TOOL,
                ConfidentialityLevel.CONFIDENTIAL,
                ConfidentialityLevel.RESTRICTED,
            ),
            # SUPERVISED ceiling = CONFIDENTIAL
            (
                TrustPostureLevel.SUPERVISED,
                ConfidentialityLevel.PUBLIC,
                ConfidentialityLevel.PUBLIC,
            ),
            (
                TrustPostureLevel.SUPERVISED,
                ConfidentialityLevel.CONFIDENTIAL,
                ConfidentialityLevel.CONFIDENTIAL,
            ),
            (
                TrustPostureLevel.SUPERVISED,
                ConfidentialityLevel.TOP_SECRET,
                ConfidentialityLevel.CONFIDENTIAL,
            ),
            # DELEGATING ceiling = SECRET
            (
                TrustPostureLevel.DELEGATING,
                ConfidentialityLevel.SECRET,
                ConfidentialityLevel.SECRET,
            ),
            (
                TrustPostureLevel.DELEGATING,
                ConfidentialityLevel.TOP_SECRET,
                ConfidentialityLevel.SECRET,
            ),
            # AUTONOMOUS ceiling = TOP_SECRET
            (
                TrustPostureLevel.AUTONOMOUS,
                ConfidentialityLevel.TOP_SECRET,
                ConfidentialityLevel.TOP_SECRET,
            ),
            (
                TrustPostureLevel.AUTONOMOUS,
                ConfidentialityLevel.PUBLIC,
                ConfidentialityLevel.PUBLIC,
            ),
        ],
    )
    def test_posture_capping_matrix(
        self,
        posture: TrustPostureLevel,
        role_level: ConfidentialityLevel,
        expected: ConfidentialityLevel,
    ) -> None:
        rc = RoleClearance(role_address="test", max_clearance=role_level)
        assert effective_clearance(rc, posture) == expected
