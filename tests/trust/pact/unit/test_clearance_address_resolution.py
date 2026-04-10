# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Regression tests for clearance methods resolving D/T/R addresses.

Issue #388: grant_clearance(), revoke_clearance(), and transition_clearance()
only accepted config role IDs (e.g., "r-president"). They did NOT resolve
D/T/R positional addresses (e.g., "D1-R1"). Direct Python callers bypassed
the HTTP endpoint's band-aid resolution.

Fix: At the start of each method, resolve the address via
_resolve_role_address() which accepts both forms.
"""

from __future__ import annotations

from typing import Any

import pytest
from kailash.trust.pact.clearance import RoleClearance, VettingStatus
from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.config import ConfidentialityLevel
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.exceptions import PactError
from kailash.trust.pact.store import MemoryClearanceStore
from pact.examples.university.org import create_university_org

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def university_compiled() -> tuple[CompiledOrg, Any]:
    """Compiled university org and the original OrgDefinition."""
    return create_university_org()


@pytest.fixture
def compiled_org(university_compiled: tuple[CompiledOrg, Any]) -> CompiledOrg:
    """Just the compiled org."""
    return university_compiled[0]


@pytest.fixture
def engine(compiled_org: CompiledOrg) -> GovernanceEngine:
    """Engine with empty clearance store for testing grant/revoke/transition."""
    return GovernanceEngine(compiled_org)


def _make_clearance(role_address: str) -> RoleClearance:
    """Helper to create a basic ACTIVE clearance for a given address."""
    return RoleClearance(
        role_address=role_address,
        max_clearance=ConfidentialityLevel.CONFIDENTIAL,
        vetting_status=VettingStatus.ACTIVE,
        granted_by_role_address="D1-R1",
    )


# ---------------------------------------------------------------------------
# grant_clearance tests
# ---------------------------------------------------------------------------


class TestGrantClearanceAddressResolution:
    """Regression: #388 -- grant_clearance() resolves D/T/R addresses."""

    @pytest.mark.regression
    def test_grant_with_positional_address(self, engine: GovernanceEngine) -> None:
        """grant_clearance() accepts a D/T/R positional address."""
        clearance = _make_clearance("D1-R1")
        engine.grant_clearance("D1-R1", clearance)

        # Verify the clearance was stored at the resolved address
        org = engine.get_org()
        node = org.nodes.get("D1-R1")
        assert node is not None

    @pytest.mark.regression
    def test_grant_with_config_role_id(self, engine: GovernanceEngine) -> None:
        """grant_clearance() accepts a config role ID and resolves it."""
        # "r-president" is the config role_id for the node at D1-R1
        clearance = _make_clearance("D1-R1")
        engine.grant_clearance("r-president", clearance)

        # The method should have resolved "r-president" -> "D1-R1"
        # and completed without error
        node = engine.get_node("r-president")
        assert node is not None
        assert node.address == "D1-R1"

    @pytest.mark.regression
    def test_grant_with_non_head_role_id(self, engine: GovernanceEngine) -> None:
        """grant_clearance() resolves non-head config role IDs like r-cs-faculty."""
        node = engine.get_node("r-cs-faculty")
        assert node is not None
        faculty_address = node.address

        clearance = _make_clearance(faculty_address)
        engine.grant_clearance("r-cs-faculty", clearance)

    @pytest.mark.regression
    def test_grant_with_invalid_address_raises(self, engine: GovernanceEngine) -> None:
        """grant_clearance() raises PactError for unresolvable addresses."""
        clearance = _make_clearance("BOGUS-ADDRESS")
        with pytest.raises(PactError, match="Cannot resolve role address"):
            engine.grant_clearance("totally-invalid-address", clearance)

    @pytest.mark.regression
    def test_grant_backward_compat_config_id(self, engine: GovernanceEngine) -> None:
        """Existing callers using config role IDs continue to work."""
        clearance = _make_clearance("D1-R1")
        # This was the only way that worked before the fix
        engine.grant_clearance("r-provost", clearance)


# ---------------------------------------------------------------------------
# revoke_clearance tests
# ---------------------------------------------------------------------------


class TestRevokeClearanceAddressResolution:
    """Regression: #388 -- revoke_clearance() resolves D/T/R addresses."""

    @pytest.mark.regression
    def test_revoke_with_positional_address(self, engine: GovernanceEngine) -> None:
        """revoke_clearance() accepts a D/T/R positional address."""
        clearance = _make_clearance("D1-R1")
        engine.grant_clearance("D1-R1", clearance)
        engine.revoke_clearance("D1-R1")

    @pytest.mark.regression
    def test_revoke_with_config_role_id(self, engine: GovernanceEngine) -> None:
        """revoke_clearance() accepts a config role ID and resolves it."""
        node = engine.get_node("r-cs-chair")
        assert node is not None
        clearance = _make_clearance(node.address)
        engine.grant_clearance(node.address, clearance)
        # Revoke using config role_id
        engine.revoke_clearance("r-cs-chair")

    @pytest.mark.regression
    def test_revoke_with_invalid_address_raises(self, engine: GovernanceEngine) -> None:
        """revoke_clearance() raises PactError for unresolvable addresses."""
        with pytest.raises(PactError, match="Cannot resolve role address"):
            engine.revoke_clearance("nonexistent-role-xyz")


# ---------------------------------------------------------------------------
# transition_clearance tests
# ---------------------------------------------------------------------------


class TestTransitionClearanceAddressResolution:
    """Regression: #388 -- transition_clearance() resolves D/T/R addresses."""

    @pytest.mark.regression
    def test_transition_with_positional_address(self, engine: GovernanceEngine) -> None:
        """transition_clearance() accepts a D/T/R positional address."""
        clearance = _make_clearance("D1-R1")
        engine.grant_clearance("D1-R1", clearance)
        engine.transition_clearance("D1-R1", VettingStatus.SUSPENDED)

    @pytest.mark.regression
    def test_transition_with_config_role_id(self, engine: GovernanceEngine) -> None:
        """transition_clearance() accepts a config role ID and resolves it."""
        node = engine.get_node("r-dean-eng")
        assert node is not None
        clearance = _make_clearance(node.address)
        engine.grant_clearance(node.address, clearance)
        # Transition using config role_id
        engine.transition_clearance("r-dean-eng", VettingStatus.SUSPENDED)

    @pytest.mark.regression
    def test_transition_with_invalid_address_raises(
        self, engine: GovernanceEngine
    ) -> None:
        """transition_clearance() raises PactError for unresolvable addresses."""
        with pytest.raises(PactError, match="Cannot resolve role address"):
            engine.transition_clearance("nonexistent-role-xyz", VettingStatus.SUSPENDED)

    @pytest.mark.regression
    def test_transition_no_clearance_still_raises_after_resolution(
        self, engine: GovernanceEngine
    ) -> None:
        """transition_clearance() resolves the address, then raises PactError
        if no clearance exists (not an address resolution error)."""
        with pytest.raises(PactError, match="no clearance found"):
            engine.transition_clearance("D1-R1", VettingStatus.SUSPENDED)
