# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for KnowledgeItem model.

Covers:
- TODO-2002: KnowledgeItem frozen dataclass
- Field defaults and required fields
- Compartment handling (frozenset)
"""

from __future__ import annotations

import pytest

from pact.build.config.schema import ConfidentialityLevel
from pact.governance.knowledge import KnowledgeItem


class TestKnowledgeItemModel:
    """KnowledgeItem frozen dataclass behavior."""

    def test_basic_construction(self) -> None:
        ki = KnowledgeItem(
            item_id="trading-positions-q1",
            classification=ConfidentialityLevel.CONFIDENTIAL,
            owning_unit_address="D1-R1-D3",
        )
        assert ki.item_id == "trading-positions-q1"
        assert ki.classification == ConfidentialityLevel.CONFIDENTIAL
        assert ki.owning_unit_address == "D1-R1-D3"

    def test_defaults(self) -> None:
        ki = KnowledgeItem(
            item_id="test",
            classification=ConfidentialityLevel.PUBLIC,
            owning_unit_address="D1",
        )
        assert ki.compartments == frozenset()
        assert ki.description == ""

    def test_compartments_frozenset(self) -> None:
        ki = KnowledgeItem(
            item_id="aml-report",
            classification=ConfidentialityLevel.SECRET,
            owning_unit_address="D1-R1-D1-R1-T1",
            compartments=frozenset({"aml-investigations"}),
        )
        assert "aml-investigations" in ki.compartments
        assert len(ki.compartments) == 1

    def test_description_field(self) -> None:
        ki = KnowledgeItem(
            item_id="client-portfolio",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1-R1-D2-R1-T1",
            description="Client investment portfolio data",
        )
        assert ki.description == "Client investment portfolio data"

    def test_frozen_immutability(self) -> None:
        ki = KnowledgeItem(
            item_id="test",
            classification=ConfidentialityLevel.PUBLIC,
            owning_unit_address="D1",
        )
        with pytest.raises(AttributeError):
            ki.classification = ConfidentialityLevel.SECRET  # type: ignore[misc]

    def test_multiple_compartments(self) -> None:
        ki = KnowledgeItem(
            item_id="cross-ref",
            classification=ConfidentialityLevel.TOP_SECRET,
            owning_unit_address="D1-R1-D1",
            compartments=frozenset({"sanctions", "aml-investigations", "insider-trading"}),
        )
        assert len(ki.compartments) == 3
        assert "sanctions" in ki.compartments
        assert "insider-trading" in ki.compartments

    def test_public_item_no_compartments(self) -> None:
        """PUBLIC items typically have no compartments."""
        ki = KnowledgeItem(
            item_id="annual-report",
            classification=ConfidentialityLevel.PUBLIC,
            owning_unit_address="D1",
        )
        assert ki.compartments == frozenset()
        assert ki.classification == ConfidentialityLevel.PUBLIC
