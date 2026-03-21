# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for GovernanceContext -- frozen read-only governance snapshot for agents.

Covers:
- TODO-7016: GovernanceContext dataclass
- Frozen immutability (anti-self-modification defense)
- to_dict / from_dict roundtrip serialization
- allowed_actions derived from operational envelope
- effective_clearance posture-capped via POSTURE_CEILING
- None envelope produces empty allowed_actions
- None clearance produces empty compartments
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    OperationalConstraintConfig,
    TrustPostureLevel,
)
from pact.governance.clearance import POSTURE_CEILING, RoleClearance, effective_clearance
from pact.governance.context import GovernanceContext


# ---------------------------------------------------------------------------
# Frozen immutability
# ---------------------------------------------------------------------------


class TestFrozen:
    """GovernanceContext must be immutable -- agents cannot modify their governance state."""

    def test_frozen_posture(self) -> None:
        """Attempting to set posture on a frozen context raises an error."""
        ctx = GovernanceContext(
            role_address="D1-R1",
            posture=TrustPostureLevel.SUPERVISED,
            effective_envelope=None,
            clearance=None,
            effective_clearance_level=None,
            allowed_actions=frozenset(),
            compartments=frozenset(),
            org_id="test-org",
            created_at=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            ctx.posture = TrustPostureLevel.DELEGATED  # type: ignore[misc]

    def test_frozen_role_address(self) -> None:
        """Attempting to set role_address on a frozen context raises an error."""
        ctx = GovernanceContext(
            role_address="D1-R1",
            posture=TrustPostureLevel.SUPERVISED,
            effective_envelope=None,
            clearance=None,
            effective_clearance_level=None,
            allowed_actions=frozenset(),
            compartments=frozenset(),
            org_id="test-org",
            created_at=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            ctx.role_address = "D2-R1"  # type: ignore[misc]

    def test_frozen_allowed_actions(self) -> None:
        """Attempting to set allowed_actions on a frozen context raises an error."""
        ctx = GovernanceContext(
            role_address="D1-R1",
            posture=TrustPostureLevel.SUPERVISED,
            effective_envelope=None,
            clearance=None,
            effective_clearance_level=None,
            allowed_actions=frozenset({"read"}),
            compartments=frozenset(),
            org_id="test-org",
            created_at=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            ctx.allowed_actions = frozenset({"read", "write", "delete"})  # type: ignore[misc]

    def test_frozen_effective_envelope(self) -> None:
        """Attempting to set effective_envelope on a frozen context raises an error."""
        ctx = GovernanceContext(
            role_address="D1-R1",
            posture=TrustPostureLevel.SUPERVISED,
            effective_envelope=None,
            clearance=None,
            effective_clearance_level=None,
            allowed_actions=frozenset(),
            compartments=frozenset(),
            org_id="test-org",
            created_at=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            ctx.effective_envelope = ConstraintEnvelopeConfig(id="hacked")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Serialization roundtrip
# ---------------------------------------------------------------------------


class TestSerialization:
    """to_dict / from_dict must produce identical GovernanceContext objects."""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Full roundtrip: create -> to_dict -> from_dict -> compare fields."""
        now = datetime.now(UTC)
        envelope = ConstraintEnvelopeConfig(
            id="env-001",
            description="test envelope",
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write"],
            ),
        )
        clearance = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.SECRET,
            compartments=frozenset({"finance", "hr"}),
        )
        ctx = GovernanceContext(
            role_address="D1-R1",
            posture=TrustPostureLevel.SUPERVISED,
            effective_envelope=envelope,
            clearance=clearance,
            effective_clearance_level=ConfidentialityLevel.RESTRICTED,
            allowed_actions=frozenset({"read", "write"}),
            compartments=frozenset({"finance", "hr"}),
            org_id="test-org",
            created_at=now,
        )

        data = ctx.to_dict()
        restored = GovernanceContext.from_dict(data)

        assert restored.role_address == ctx.role_address
        assert restored.posture == ctx.posture
        assert restored.effective_clearance_level == ctx.effective_clearance_level
        assert restored.allowed_actions == ctx.allowed_actions
        assert restored.compartments == ctx.compartments
        assert restored.org_id == ctx.org_id
        assert restored.created_at == ctx.created_at

    def test_to_dict_none_envelope(self) -> None:
        """to_dict handles None envelope correctly."""
        ctx = GovernanceContext(
            role_address="D1-R1",
            posture=TrustPostureLevel.SUPERVISED,
            effective_envelope=None,
            clearance=None,
            effective_clearance_level=None,
            allowed_actions=frozenset(),
            compartments=frozenset(),
            org_id="test-org",
            created_at=datetime.now(UTC),
        )
        data = ctx.to_dict()
        assert data["effective_envelope"] is None
        assert data["clearance"] is None
        assert data["effective_clearance_level"] is None

    def test_from_dict_none_envelope(self) -> None:
        """from_dict restores None envelope correctly."""
        now = datetime.now(UTC)
        data = {
            "role_address": "D1-R1",
            "posture": "supervised",
            "effective_envelope": None,
            "clearance": None,
            "effective_clearance_level": None,
            "allowed_actions": [],
            "compartments": [],
            "org_id": "test-org",
            "created_at": now.isoformat(),
        }
        ctx = GovernanceContext.from_dict(data)
        assert ctx.effective_envelope is None
        assert ctx.clearance is None
        assert ctx.effective_clearance_level is None
        assert ctx.allowed_actions == frozenset()
        assert ctx.compartments == frozenset()


# ---------------------------------------------------------------------------
# Allowed actions from envelope
# ---------------------------------------------------------------------------


class TestAllowedActionsFromEnvelope:
    """allowed_actions should reflect the operational envelope's allowed_actions."""

    def test_allowed_actions_from_envelope(self) -> None:
        """allowed_actions should be populated from envelope operational dimension."""
        envelope = ConstraintEnvelopeConfig(
            id="env-001",
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "propose"],
            ),
        )
        ctx = GovernanceContext(
            role_address="D1-R1",
            posture=TrustPostureLevel.SHARED_PLANNING,
            effective_envelope=envelope,
            clearance=None,
            effective_clearance_level=None,
            allowed_actions=frozenset(envelope.operational.allowed_actions),
            compartments=frozenset(),
            org_id="test-org",
            created_at=datetime.now(UTC),
        )
        assert ctx.allowed_actions == frozenset({"read", "write", "propose"})


# ---------------------------------------------------------------------------
# Effective clearance posture-capped
# ---------------------------------------------------------------------------


class TestEffectiveClearancePostureCapped:
    """effective_clearance_level must be capped by POSTURE_CEILING."""

    def test_effective_clearance_posture_capped(self) -> None:
        """A role with SECRET clearance at SUPERVISED posture gets RESTRICTED."""
        clearance = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.SECRET,
        )
        eff = effective_clearance(clearance, TrustPostureLevel.SUPERVISED)
        assert eff == ConfidentialityLevel.RESTRICTED

        ctx = GovernanceContext(
            role_address="D1-R1",
            posture=TrustPostureLevel.SUPERVISED,
            effective_envelope=None,
            clearance=clearance,
            effective_clearance_level=eff,
            allowed_actions=frozenset(),
            compartments=frozenset(),
            org_id="test-org",
            created_at=datetime.now(UTC),
        )
        assert ctx.effective_clearance_level == ConfidentialityLevel.RESTRICTED

    def test_effective_clearance_delegated_allows_top_secret(self) -> None:
        """A role with TOP_SECRET clearance at DELEGATED posture gets TOP_SECRET."""
        clearance = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.TOP_SECRET,
        )
        eff = effective_clearance(clearance, TrustPostureLevel.DELEGATED)
        assert eff == ConfidentialityLevel.TOP_SECRET

        ctx = GovernanceContext(
            role_address="D1-R1",
            posture=TrustPostureLevel.DELEGATED,
            effective_envelope=None,
            clearance=clearance,
            effective_clearance_level=eff,
            allowed_actions=frozenset(),
            compartments=frozenset(),
            org_id="test-org",
            created_at=datetime.now(UTC),
        )
        assert ctx.effective_clearance_level == ConfidentialityLevel.TOP_SECRET

    def test_effective_clearance_pseudo_agent_caps_to_public(self) -> None:
        """Any clearance level at PSEUDO_AGENT posture is capped to PUBLIC."""
        clearance = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.TOP_SECRET,
        )
        eff = effective_clearance(clearance, TrustPostureLevel.PSEUDO_AGENT)
        assert eff == ConfidentialityLevel.PUBLIC


# ---------------------------------------------------------------------------
# None envelope => empty actions
# ---------------------------------------------------------------------------


class TestNoneEnvelopeEmptyActions:
    """When effective_envelope is None, allowed_actions should be empty."""

    def test_none_envelope_empty_actions(self) -> None:
        ctx = GovernanceContext(
            role_address="D1-R1",
            posture=TrustPostureLevel.SUPERVISED,
            effective_envelope=None,
            clearance=None,
            effective_clearance_level=None,
            allowed_actions=frozenset(),
            compartments=frozenset(),
            org_id="test-org",
            created_at=datetime.now(UTC),
        )
        assert ctx.allowed_actions == frozenset()
        assert len(ctx.allowed_actions) == 0


# ---------------------------------------------------------------------------
# None clearance => empty compartments
# ---------------------------------------------------------------------------


class TestNoneClearanceEmptyCompartments:
    """When clearance is None, compartments should be empty."""

    def test_none_clearance_empty_compartments(self) -> None:
        ctx = GovernanceContext(
            role_address="D1-R1",
            posture=TrustPostureLevel.SUPERVISED,
            effective_envelope=None,
            clearance=None,
            effective_clearance_level=None,
            allowed_actions=frozenset(),
            compartments=frozenset(),
            org_id="test-org",
            created_at=datetime.now(UTC),
        )
        assert ctx.clearance is None
        assert ctx.compartments == frozenset()
        assert len(ctx.compartments) == 0
