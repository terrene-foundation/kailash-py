# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for monotonic tightening across all 7 dimensions (PACT spec Section 5.3).

Covers the 3 dimensions added in TODO-01: Temporal, Data Access, Communication.
These supplement the existing Financial, Confidentiality, Operational, and
Delegation depth checks already validated in test_envelopes.py.
"""

from __future__ import annotations

import pytest

from kailash.trust.pact.config import (
    CommunicationConstraintConfig,
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
)
from kailash.trust.pact.envelopes import (
    MonotonicTighteningError,
    RoleEnvelope,
)


# ---------------------------------------------------------------------------
# Helpers -- build constraint configs for tests
# ---------------------------------------------------------------------------


def _make_envelope(
    *,
    envelope_id: str = "test",
    max_spend: float = 1000.0,
    allowed_actions: list[str] | None = None,
    active_hours_start: str | None = None,
    active_hours_end: str | None = None,
    blackout_periods: list[str] | None = None,
    read_paths: list[str] | None = None,
    write_paths: list[str] | None = None,
    confidentiality: ConfidentialityLevel = ConfidentialityLevel.CONFIDENTIAL,
    internal_only: bool = False,
    allowed_channels: list[str] | None = None,
    max_delegation_depth: int | None = None,
) -> ConstraintEnvelopeConfig:
    """Helper to build a ConstraintEnvelopeConfig with sensible defaults."""
    return ConstraintEnvelopeConfig(
        id=envelope_id,
        confidentiality_clearance=confidentiality,
        financial=FinancialConstraintConfig(max_spend_usd=max_spend),
        operational=OperationalConstraintConfig(
            allowed_actions=allowed_actions or [],
        ),
        temporal=TemporalConstraintConfig(
            active_hours_start=active_hours_start,
            active_hours_end=active_hours_end,
            blackout_periods=blackout_periods or [],
        ),
        data_access=DataAccessConstraintConfig(
            read_paths=read_paths or [],
            write_paths=write_paths or [],
        ),
        communication=CommunicationConstraintConfig(
            internal_only=internal_only,
            allowed_channels=allowed_channels or [],
        ),
        max_delegation_depth=max_delegation_depth,
    )


# ===========================================================================
# Temporal dimension tightening
# ===========================================================================


class TestTighteningTemporal:
    """Temporal dimension: child active hours must be within parent's window."""

    def test_tightening_temporal_within_parent(self) -> None:
        """Child hours inside parent hours -- passes (valid tightening)."""
        parent = _make_envelope(active_hours_start="06:00", active_hours_end="20:00")
        child = _make_envelope(active_hours_start="09:00", active_hours_end="17:00")
        # Should not raise
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    def test_tightening_temporal_exceeds_parent_start(self) -> None:
        """Child starts earlier than parent -- violation."""
        parent = _make_envelope(active_hours_start="09:00", active_hours_end="17:00")
        child = _make_envelope(active_hours_start="06:00", active_hours_end="17:00")
        with pytest.raises(MonotonicTighteningError, match="Temporal"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent, child_envelope=child
            )

    def test_tightening_temporal_exceeds_parent_end(self) -> None:
        """Child ends later than parent -- violation."""
        parent = _make_envelope(active_hours_start="09:00", active_hours_end="17:00")
        child = _make_envelope(active_hours_start="09:00", active_hours_end="20:00")
        with pytest.raises(MonotonicTighteningError, match="Temporal"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent, child_envelope=child
            )

    def test_tightening_temporal_equal_hours_passes(self) -> None:
        """Child has identical hours to parent -- passes (equal is valid)."""
        parent = _make_envelope(active_hours_start="09:00", active_hours_end="17:00")
        child = _make_envelope(active_hours_start="09:00", active_hours_end="17:00")
        # Should not raise
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    def test_tightening_temporal_blackout_superset(self) -> None:
        """Child has all parent blackouts plus extra -- passes (more restrictive)."""
        parent = _make_envelope(blackout_periods=["2026-01-01", "2026-12-25"])
        child = _make_envelope(
            blackout_periods=["2026-01-01", "2026-12-25", "2026-07-04"]
        )
        # Should not raise -- child has MORE blackouts (tighter)
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    def test_tightening_temporal_blackout_missing(self) -> None:
        """Child missing a parent blackout period -- violation."""
        parent = _make_envelope(blackout_periods=["2026-01-01", "2026-12-25"])
        child = _make_envelope(blackout_periods=["2026-01-01"])
        with pytest.raises(MonotonicTighteningError, match="Temporal"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent, child_envelope=child
            )

    def test_tightening_temporal_parent_has_hours_child_unrestricted(self) -> None:
        """Parent has active hours but child has no time restrictions -- violation.

        An unrestricted child is wider than a restricted parent.
        """
        parent = _make_envelope(active_hours_start="09:00", active_hours_end="17:00")
        child = _make_envelope(active_hours_start=None, active_hours_end=None)
        with pytest.raises(MonotonicTighteningError, match="Temporal"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent, child_envelope=child
            )

    def test_tightening_temporal_neither_has_hours(self) -> None:
        """Neither parent nor child has active hours -- passes (both unrestricted)."""
        parent = _make_envelope(active_hours_start=None, active_hours_end=None)
        child = _make_envelope(active_hours_start=None, active_hours_end=None)
        # Should not raise
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)


# ===========================================================================
# Data Access dimension tightening
# ===========================================================================


class TestTighteningDataAccess:
    """Data Access dimension: child paths must be subsets of parent paths."""

    def test_tightening_data_access_read_subset(self) -> None:
        """Child read_paths subset of parent -- passes."""
        parent = _make_envelope(
            read_paths=["/data/reports", "/data/logs", "/data/config"]
        )
        child = _make_envelope(read_paths=["/data/reports", "/data/config"])
        # Should not raise
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    def test_tightening_data_access_read_exceeds(self) -> None:
        """Child has extra read path not in parent -- violation."""
        parent = _make_envelope(read_paths=["/data/reports", "/data/config"])
        child = _make_envelope(
            read_paths=["/data/reports", "/data/config", "/data/secrets"]
        )
        with pytest.raises(MonotonicTighteningError, match="Data access"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent, child_envelope=child
            )

    def test_tightening_data_access_write_exceeds(self) -> None:
        """Child has extra write path not in parent -- violation."""
        parent = _make_envelope(write_paths=["/data/output"])
        child = _make_envelope(write_paths=["/data/output", "/data/classified"])
        with pytest.raises(MonotonicTighteningError, match="Data access"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent, child_envelope=child
            )

    def test_tightening_data_access_write_subset_passes(self) -> None:
        """Child write_paths subset of parent -- passes."""
        parent = _make_envelope(write_paths=["/data/output", "/data/logs"])
        child = _make_envelope(write_paths=["/data/output"])
        # Should not raise
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    def test_tightening_data_access_empty_child_passes(self) -> None:
        """Child has no paths (empty lists) -- passes (maximally restrictive)."""
        parent = _make_envelope(
            read_paths=["/data/reports"],
            write_paths=["/data/output"],
        )
        child = _make_envelope(
            read_paths=[],
            write_paths=[],
        )
        # Should not raise -- empty is a subset of anything
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    def test_tightening_data_access_both_empty_passes(self) -> None:
        """Both parent and child have empty paths -- passes."""
        parent = _make_envelope(read_paths=[], write_paths=[])
        child = _make_envelope(read_paths=[], write_paths=[])
        # Should not raise
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    def test_tightening_data_access_parent_empty_child_has_paths(self) -> None:
        """Parent has empty read paths, child has read paths -- violation.

        If parent allows nothing, child cannot add new paths.
        """
        parent = _make_envelope(read_paths=[])
        child = _make_envelope(read_paths=["/data/secrets"])
        with pytest.raises(MonotonicTighteningError, match="Data access"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent, child_envelope=child
            )


# ===========================================================================
# Communication dimension tightening
# ===========================================================================


class TestTighteningCommunication:
    """Communication dimension: channel subsets and internal_only tightening."""

    def test_tightening_communication_channels_subset(self) -> None:
        """Child allowed_channels subset of parent -- passes."""
        parent = _make_envelope(allowed_channels=["email", "slack", "teams"])
        child = _make_envelope(allowed_channels=["email", "slack"])
        # Should not raise
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    def test_tightening_communication_channels_exceeds(self) -> None:
        """Child has extra channel not in parent -- violation."""
        parent = _make_envelope(allowed_channels=["email", "slack"])
        child = _make_envelope(allowed_channels=["email", "slack", "sms"])
        with pytest.raises(MonotonicTighteningError, match="Communication"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent, child_envelope=child
            )

    def test_tightening_communication_internal_only_tighter(self) -> None:
        """Child=True, parent=False -- passes (child is more restrictive)."""
        parent = _make_envelope(internal_only=False)
        child = _make_envelope(internal_only=True)
        # Should not raise -- True is more restrictive
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    def test_tightening_communication_internal_only_looser(self) -> None:
        """Child=False, parent=True -- violation (child is less restrictive)."""
        parent = _make_envelope(internal_only=True)
        child = _make_envelope(internal_only=False)
        with pytest.raises(MonotonicTighteningError, match="Communication"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent, child_envelope=child
            )

    def test_tightening_communication_equal_passes(self) -> None:
        """Equal communication settings -- passes."""
        parent = _make_envelope(
            internal_only=True,
            allowed_channels=["internal"],
        )
        child = _make_envelope(
            internal_only=True,
            allowed_channels=["internal"],
        )
        # Should not raise
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    def test_tightening_communication_both_empty_channels_passes(self) -> None:
        """Both parent and child have empty channel lists -- passes."""
        parent = _make_envelope(allowed_channels=[])
        child = _make_envelope(allowed_channels=[])
        # Should not raise
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    def test_tightening_communication_parent_empty_child_has_channels(self) -> None:
        """Parent has empty channels, child adds channels -- violation."""
        parent = _make_envelope(allowed_channels=[])
        child = _make_envelope(allowed_channels=["email"])
        with pytest.raises(MonotonicTighteningError, match="Communication"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent, child_envelope=child
            )
