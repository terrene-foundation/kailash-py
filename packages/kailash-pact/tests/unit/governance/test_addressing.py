# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for D/T/R positional addressing -- the grammar engine for PACT.

Covers:
- AddressSegment parsing and string representation
- Address parsing, grammar validation, and properties
- Grammar violation detection (D followed by D, D followed by T, trailing D/T, etc.)
- Prefix/ancestor queries
- Round-trip invariants (str(Address.parse(s)) == s)
"""

from __future__ import annotations

import pytest

from pact.governance.addressing import (
    Address,
    AddressError,
    AddressSegment,
    GrammarError,
    NodeType,
)


# ---------------------------------------------------------------------------
# NodeType enum
# ---------------------------------------------------------------------------


class TestNodeType:
    """NodeType enum basic behavior."""

    def test_department_value(self) -> None:
        assert NodeType.DEPARTMENT.value == "D"

    def test_team_value(self) -> None:
        assert NodeType.TEAM.value == "T"

    def test_role_value(self) -> None:
        assert NodeType.ROLE.value == "R"

    def test_is_string_enum(self) -> None:
        assert isinstance(NodeType.DEPARTMENT, str)
        assert isinstance(NodeType.TEAM, str)
        assert isinstance(NodeType.ROLE, str)


# ---------------------------------------------------------------------------
# AddressSegment
# ---------------------------------------------------------------------------


class TestAddressSegment:
    """AddressSegment parsing and display."""

    @pytest.mark.parametrize(
        "input_str, expected_type, expected_seq",
        [
            ("D1", NodeType.DEPARTMENT, 1),
            ("D99", NodeType.DEPARTMENT, 99),
            ("R1", NodeType.ROLE, 1),
            ("R5", NodeType.ROLE, 5),
            ("T1", NodeType.TEAM, 1),
            ("T12", NodeType.TEAM, 12),
            ("d1", NodeType.DEPARTMENT, 1),  # case-insensitive type char
            ("r2", NodeType.ROLE, 2),
            ("t3", NodeType.TEAM, 3),
        ],
    )
    def test_parse_valid_segments(
        self, input_str: str, expected_type: NodeType, expected_seq: int
    ) -> None:
        seg = AddressSegment.parse(input_str)
        assert seg.node_type == expected_type
        assert seg.sequence == expected_seq

    def test_str_representation(self) -> None:
        seg = AddressSegment(node_type=NodeType.DEPARTMENT, sequence=3)
        assert str(seg) == "D3"

    def test_str_representation_role(self) -> None:
        seg = AddressSegment(node_type=NodeType.ROLE, sequence=1)
        assert str(seg) == "R1"

    @pytest.mark.parametrize(
        "bad_input, error_msg_fragment",
        [
            ("", "Invalid segment"),
            ("D", "Invalid segment"),  # too short (len < 2)
            ("X1", "Invalid node type"),
            ("Z99", "Invalid node type"),
            ("Da", "Invalid sequence number"),
            ("D-1", "Sequence must be >= 1"),  # parses as int(-1), fails >= 1 check
            ("D0", "Sequence must be >= 1"),
            ("R0", "Sequence must be >= 1"),
            ("T-5", "Sequence must be >= 1"),  # parses as int(-5), fails >= 1 check
        ],
    )
    def test_parse_invalid_segments(self, bad_input: str, error_msg_fragment: str) -> None:
        with pytest.raises(AddressError, match=error_msg_fragment):
            AddressSegment.parse(bad_input)

    def test_frozen_dataclass(self) -> None:
        seg = AddressSegment(node_type=NodeType.DEPARTMENT, sequence=1)
        with pytest.raises(AttributeError):
            seg.sequence = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Address parsing -- valid addresses
# ---------------------------------------------------------------------------


class TestAddressParsingValid:
    """Address.parse() with valid D/T/R strings."""

    @pytest.mark.parametrize(
        "address_str, expected_depth",
        [
            ("D1-R1", 2),
            ("D1-R1-D1-R1", 4),
            ("D1-R1-T1-R1", 4),
            ("D1-R1-R2", 3),  # D1's head is R1, R2 is another role under D1
            ("D1-R1-D3-R1-T1-R1-R2", 7),
            ("R1", 1),  # standalone role (BOD member)
            ("D1-R1-D1-R1-T1-R1", 6),  # nested dept + team
            ("D1-R1-D2-R1-D1-R1", 6),  # deep nesting
        ],
    )
    def test_parse_valid_address(self, address_str: str, expected_depth: int) -> None:
        addr = Address.parse(address_str)
        assert addr.depth == expected_depth
        assert len(addr) == expected_depth

    def test_round_trip_simple(self) -> None:
        """str(Address.parse(s)) must equal s for canonical addresses."""
        s = "D1-R1"
        assert str(Address.parse(s)) == s

    @pytest.mark.parametrize(
        "address_str",
        [
            "D1-R1",
            "D1-R1-D1-R1",
            "D1-R1-T1-R1",
            "D1-R1-R2",
            "D1-R1-D3-R1-T1-R1-R2",
            "R1",
            "D1-R1-D2-R1-D1-R1-T1-R1",
        ],
    )
    def test_round_trip_all(self, address_str: str) -> None:
        """Round-trip: parse then stringify produces the original string."""
        assert str(Address.parse(address_str)) == address_str


# ---------------------------------------------------------------------------
# Address parsing -- invalid addresses (grammar violations)
# ---------------------------------------------------------------------------


class TestAddressParsingInvalid:
    """Address.parse() must reject grammar violations."""

    @pytest.mark.parametrize(
        "bad_address, expected_error_class, error_msg_fragment",
        [
            # D followed by D -- violates "D must be followed by R"
            ("D1-D2", GrammarError, "must be immediately followed by R"),
            # D followed by T -- violates "D must be followed by R"
            ("D1-T1", GrammarError, "must be immediately followed by R"),
            # T followed by T
            ("D1-R1-T1-T2", GrammarError, "must be immediately followed by R"),
            # T followed by D
            ("D1-R1-T1-D2", GrammarError, "must be immediately followed by R"),
            # Trailing D with no R
            ("D1-R1-D2", GrammarError, "address ends with"),
            # Trailing T with no R
            ("D1-R1-T1", GrammarError, "address ends with"),
            # Just a D (no R)
            ("D1", GrammarError, "address ends with"),
            # Just a T (no R)
            ("T1", GrammarError, "address ends with"),
            # Empty string
            ("", AddressError, "Address string is empty"),
            ("  ", AddressError, "Address string is empty"),
        ],
    )
    def test_grammar_violations(
        self,
        bad_address: str,
        expected_error_class: type,
        error_msg_fragment: str,
    ) -> None:
        with pytest.raises(expected_error_class, match=error_msg_fragment):
            Address.parse(bad_address)

    def test_grammar_error_is_address_error(self) -> None:
        """GrammarError inherits from AddressError."""
        with pytest.raises(AddressError):
            Address.parse("D1-D2")


# ---------------------------------------------------------------------------
# Address properties
# ---------------------------------------------------------------------------


class TestAddressProperties:
    """Address.depth, .parent, .containment_unit, .accountability_chain."""

    def test_depth_single_role(self) -> None:
        addr = Address.parse("R1")
        assert addr.depth == 1

    def test_depth_d_r(self) -> None:
        addr = Address.parse("D1-R1")
        assert addr.depth == 2

    def test_depth_nested(self) -> None:
        addr = Address.parse("D1-R1-D1-R1-T1-R1")
        assert addr.depth == 6

    def test_parent_of_root_role_is_none(self) -> None:
        addr = Address.parse("R1")
        assert addr.parent is None

    def test_parent_of_d_r(self) -> None:
        addr = Address.parse("D1-R1")
        parent = addr.parent
        assert parent is not None
        assert str(parent) == "D1"
        # Note: D1 alone is not grammar-valid as a standalone address,
        # but Address.parent returns a structural parent (segments[:-1]),
        # it does not revalidate grammar.

    def test_parent_of_nested(self) -> None:
        addr = Address.parse("D1-R1-T1-R1")
        parent = addr.parent
        assert parent is not None
        assert str(parent) == "D1-R1-T1"

    def test_containment_unit_for_role_under_team(self) -> None:
        """The containment unit for D1-R1-T1-R1 should be D1-R1-T1 (the team)."""
        addr = Address.parse("D1-R1-T1-R1")
        cu = addr.containment_unit
        assert cu is not None
        assert str(cu) == "D1-R1-T1"

    def test_containment_unit_for_head_role(self) -> None:
        """The containment unit for D1-R1 (head of D1) should be D1."""
        addr = Address.parse("D1-R1")
        cu = addr.containment_unit
        assert cu is not None
        assert str(cu) == "D1"

    def test_containment_unit_for_standalone_role(self) -> None:
        """A standalone role R1 has no containment unit."""
        addr = Address.parse("R1")
        assert addr.containment_unit is None

    def test_containment_unit_for_additional_role(self) -> None:
        """D1-R1-R2: containment unit is D1 (nearest D/T walking backward)."""
        addr = Address.parse("D1-R1-R2")
        cu = addr.containment_unit
        assert cu is not None
        assert str(cu) == "D1"

    def test_accountability_chain_simple(self) -> None:
        """D1-R1 has one accountable role: D1-R1."""
        addr = Address.parse("D1-R1")
        chain = addr.accountability_chain
        assert len(chain) == 1
        assert str(chain[0]) == "D1-R1"

    def test_accountability_chain_nested(self) -> None:
        """D1-R1-D1-R1-T1-R1 has three accountable roles in the chain."""
        addr = Address.parse("D1-R1-D1-R1-T1-R1")
        chain = addr.accountability_chain
        assert len(chain) == 3
        assert str(chain[0]) == "D1-R1"
        assert str(chain[1]) == "D1-R1-D1-R1"
        assert str(chain[2]) == "D1-R1-D1-R1-T1-R1"

    def test_accountability_chain_with_extra_role(self) -> None:
        """D1-R1-R2 has two R segments in the chain."""
        addr = Address.parse("D1-R1-R2")
        chain = addr.accountability_chain
        assert len(chain) == 2
        assert str(chain[0]) == "D1-R1"
        assert str(chain[1]) == "D1-R1-R2"

    def test_last_segment(self) -> None:
        addr = Address.parse("D1-R1-T1-R1")
        assert addr.last_segment == AddressSegment(NodeType.ROLE, 1)


# ---------------------------------------------------------------------------
# Prefix and ancestor queries
# ---------------------------------------------------------------------------


class TestAddressPrefixAndAncestorQueries:
    """is_prefix_of, is_ancestor_of, ancestors()."""

    def test_is_prefix_of_true(self) -> None:
        a = Address.parse("D1-R1")
        b = Address.parse("D1-R1-T1-R1")
        assert a.is_prefix_of(b) is True

    def test_is_prefix_of_false_same(self) -> None:
        """An address is NOT a proper prefix of itself."""
        a = Address.parse("D1-R1")
        assert a.is_prefix_of(a) is False

    def test_is_prefix_of_false_longer(self) -> None:
        a = Address.parse("D1-R1-T1-R1")
        b = Address.parse("D1-R1")
        assert a.is_prefix_of(b) is False

    def test_is_prefix_of_false_divergent(self) -> None:
        a = Address.parse("D1-R1")
        b = Address.parse("D2-R1")
        assert a.is_prefix_of(b) is False

    def test_is_ancestor_of_true_same(self) -> None:
        """An address IS an ancestor of itself (reflexive)."""
        a = Address.parse("D1-R1")
        assert a.is_ancestor_of(a) is True

    def test_is_ancestor_of_true_prefix(self) -> None:
        a = Address.parse("D1-R1")
        b = Address.parse("D1-R1-T1-R1")
        assert a.is_ancestor_of(b) is True

    def test_is_ancestor_of_false(self) -> None:
        a = Address.parse("D1-R1-T1-R1")
        b = Address.parse("D1-R1")
        assert a.is_ancestor_of(b) is False

    def test_ancestors_of_root_role(self) -> None:
        """R1 has no ancestors."""
        a = Address.parse("R1")
        assert a.ancestors() == []

    def test_ancestors_of_d_r(self) -> None:
        """D1-R1 has one ancestor: D1 (structural, not grammar-validated)."""
        a = Address.parse("D1-R1")
        ancs = a.ancestors()
        assert len(ancs) == 1
        assert str(ancs[0]) == "D1"

    def test_ancestors_of_nested(self) -> None:
        """D1-R1-T1-R1 has ancestors: D1, D1-R1, D1-R1-T1."""
        a = Address.parse("D1-R1-T1-R1")
        ancs = a.ancestors()
        assert len(ancs) == 3
        assert str(ancs[0]) == "D1"
        assert str(ancs[1]) == "D1-R1"
        assert str(ancs[2]) == "D1-R1-T1"

    def test_ancestors_of_deep_address(self) -> None:
        """D1-R1-D3-R1-T1-R1-R2 has 6 ancestors."""
        a = Address.parse("D1-R1-D3-R1-T1-R1-R2")
        ancs = a.ancestors()
        assert len(ancs) == 6
        expected = ["D1", "D1-R1", "D1-R1-D3", "D1-R1-D3-R1", "D1-R1-D3-R1-T1", "D1-R1-D3-R1-T1-R1"]
        for anc, exp in zip(ancs, expected):
            assert str(anc) == exp


# ---------------------------------------------------------------------------
# Address.from_segments
# ---------------------------------------------------------------------------


class TestAddressFromSegments:
    """Address.from_segments() constructor with validation."""

    def test_from_segments_valid(self) -> None:
        addr = Address.from_segments(
            AddressSegment(NodeType.DEPARTMENT, 1),
            AddressSegment(NodeType.ROLE, 1),
        )
        assert str(addr) == "D1-R1"

    def test_from_segments_rejects_grammar_violation(self) -> None:
        with pytest.raises(GrammarError):
            Address.from_segments(
                AddressSegment(NodeType.DEPARTMENT, 1),
                AddressSegment(NodeType.DEPARTMENT, 2),
            )

    def test_from_segments_rejects_empty(self) -> None:
        with pytest.raises(AddressError, match="at least one segment"):
            Address.from_segments()


# ---------------------------------------------------------------------------
# Address frozen (immutable)
# ---------------------------------------------------------------------------


class TestAddressImmutability:
    """Address is a frozen dataclass."""

    def test_cannot_mutate_segments(self) -> None:
        addr = Address.parse("D1-R1")
        with pytest.raises(AttributeError):
            addr.segments = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestAddressEdgeCases:
    """Boundary and edge case handling."""

    def test_large_sequence_numbers(self) -> None:
        addr = Address.parse("D999-R1")
        assert addr.segments[0].sequence == 999

    def test_multi_digit_sequences(self) -> None:
        addr = Address.parse("D12-R34")
        assert addr.segments[0].sequence == 12
        assert addr.segments[1].sequence == 34

    def test_multiple_roles_under_department(self) -> None:
        """D1-R1-R2-R3: a department head plus two additional roles."""
        addr = Address.parse("D1-R1-R2-R3")
        assert addr.depth == 4
        chain = addr.accountability_chain
        assert len(chain) == 3

    def test_whitespace_is_stripped(self) -> None:
        addr = Address.parse("  D1-R1  ")
        assert str(addr) == "D1-R1"
