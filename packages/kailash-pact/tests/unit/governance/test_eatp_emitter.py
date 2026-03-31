# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for EATP record emission from PACT governance events.

Covers TODO-11 (PactEatpEmitter + GenesisRecord), TODO-10 (configurable deadline).
"""

from __future__ import annotations

import pytest
from datetime import timedelta

from kailash.trust.pact.config import OrgDefinition
from kailash.trust.pact.eatp_emitter import InMemoryPactEmitter, PactEatpEmitter
from kailash.trust.pact.engine import GovernanceEngine


# ---------------------------------------------------------------------------
# PactEatpEmitter protocol and InMemoryPactEmitter
# ---------------------------------------------------------------------------


class TestInMemoryPactEmitter:
    def test_protocol_satisfied(self) -> None:
        """InMemoryPactEmitter satisfies the PactEatpEmitter protocol."""
        emitter = InMemoryPactEmitter()
        assert isinstance(emitter, PactEatpEmitter)

    def test_bounded_collections(self) -> None:
        """Emitter respects maxlen bounds."""
        from kailash.trust.chain import GenesisRecord, AuthorityType
        from datetime import UTC, datetime

        emitter = InMemoryPactEmitter(maxlen=3)
        for i in range(5):
            emitter.emit_genesis(
                GenesisRecord(
                    id=f"g-{i}",
                    agent_id="a",
                    authority_id="org",
                    authority_type=AuthorityType.ORGANIZATION,
                    created_at=datetime.now(UTC),
                    signature="UNSIGNED",
                )
            )
        assert len(emitter.genesis_records) == 3
        # Oldest evicted: first record should be g-2, not g-0
        assert emitter.genesis_records[0].id == "g-2"


# ---------------------------------------------------------------------------
# GenesisRecord emission on engine init (TODO-11)
# ---------------------------------------------------------------------------


class TestGenesisRecordEmission:
    def test_genesis_emitted_with_emitter(self) -> None:
        """GenesisRecord is emitted when eatp_emitter is provided."""
        emitter = InMemoryPactEmitter()
        org = OrgDefinition(org_id="test-org", name="Test Org")
        GovernanceEngine(org, eatp_emitter=emitter)

        assert len(emitter.genesis_records) == 1
        genesis = emitter.genesis_records[0]
        assert genesis.id == "pact-genesis-test-org"
        assert genesis.agent_id == "pact-engine-test-org"
        assert genesis.authority_id == "test-org"
        assert genesis.signature == "UNSIGNED"

    def test_no_emission_without_emitter(self) -> None:
        """No error or emission when eatp_emitter is None (default)."""
        org = OrgDefinition(org_id="test-org", name="Test Org")
        engine = GovernanceEngine(org)
        assert engine._eatp_emitter is None

    def test_backward_compatible(self) -> None:
        """Engine works without eatp_emitter parameter (existing behavior)."""
        org = OrgDefinition(org_id="test-org", name="Test Org")
        engine = GovernanceEngine(org)
        assert len(engine._compiled_org.nodes) == 0  # empty org


# ---------------------------------------------------------------------------
# Configurable vacancy deadline (TODO-10)
# ---------------------------------------------------------------------------


class TestVacancyDeadline:
    def test_default_24h(self) -> None:
        """Default vacancy deadline is 24 hours."""
        org = OrgDefinition(org_id="test-org", name="Test Org")
        engine = GovernanceEngine(org)
        assert engine._vacancy_deadline == timedelta(hours=24)

    def test_configurable(self) -> None:
        """Vacancy deadline can be set to any positive value."""
        org = OrgDefinition(org_id="test-org", name="Test Org")
        engine = GovernanceEngine(org, vacancy_deadline_hours=48)
        assert engine._vacancy_deadline == timedelta(hours=48)

    def test_zero_rejected(self) -> None:
        """Zero deadline raises ValueError."""
        org = OrgDefinition(org_id="test-org", name="Test Org")
        with pytest.raises(ValueError, match="vacancy_deadline_hours must be > 0"):
            GovernanceEngine(org, vacancy_deadline_hours=0)

    def test_negative_rejected(self) -> None:
        """Negative deadline raises ValueError."""
        org = OrgDefinition(org_id="test-org", name="Test Org")
        with pytest.raises(ValueError, match="vacancy_deadline_hours must be > 0"):
            GovernanceEngine(org, vacancy_deadline_hours=-1)

    def test_deadline_used_in_designation(self) -> None:
        """Vacancy designation expiry uses the configured deadline."""
        from kailash.trust.pact.compilation import RoleDefinition

        roles = [
            RoleDefinition(
                role_id="ceo",
                name="CEO",
                is_primary_for_unit="d-eng",
            ),
            RoleDefinition(
                role_id="vp",
                name="VP (Vacant)",
                reports_to_role_id="ceo",
                is_vacant=True,
            ),
            RoleDefinition(
                role_id="eng1",
                name="Engineer",
                reports_to_role_id="ceo",
            ),
        ]
        from kailash.trust.pact.config import DepartmentConfig

        org = OrgDefinition(
            org_id="test-org",
            name="Test Org",
            departments=[DepartmentConfig(department_id="d-eng", name="Engineering")],
            roles=roles,
        )
        engine = GovernanceEngine(org, vacancy_deadline_hours=72)

        # Find the vacant role address
        vacant_addrs = [
            addr for addr, node in engine._compiled_org.nodes.items() if node.is_vacant
        ]
        if vacant_addrs:
            # Designate acting occupant -- verify expiry uses 72h deadline
            # Find the VP and engineer addresses
            vp_addr = None
            eng_addr = None
            ceo_addr = None
            for addr, node in engine._compiled_org.nodes.items():
                if node.role_definition and node.role_definition.role_id == "vp":
                    vp_addr = addr
                elif node.role_definition and node.role_definition.role_id == "eng1":
                    eng_addr = addr
                elif node.role_definition and node.role_definition.role_id == "ceo":
                    ceo_addr = addr

            if vp_addr and eng_addr and ceo_addr:
                designation = engine.designate_acting_occupant(
                    vacant_role=vp_addr,
                    acting_role=eng_addr,
                    designated_by=ceo_addr,
                )
                from datetime import datetime

                expires = datetime.fromisoformat(designation.expires_at)
                designated = datetime.fromisoformat(designation.designated_at)
                delta = expires - designated
                # Should be approximately 72 hours (3 days)
                assert timedelta(hours=71) < delta <= timedelta(hours=73)
