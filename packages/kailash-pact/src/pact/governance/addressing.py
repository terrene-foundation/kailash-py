# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""D/T/R positional addressing -- the grammar engine for PACT organizational structure.

Implements the PACT addressing scheme where every entity has a globally unique
positional address encoding both containment and accountability
(e.g., ``D1-R1-D1-R1-T1-R1``). The core invariant is that every D or T segment
must be immediately followed by exactly one R segment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

__all__ = [
    "Address",
    "AddressSegment",
    "NodeType",
    "AddressError",
    "GrammarError",
]


class NodeType(str, Enum):
    """The three PACT node types."""

    DEPARTMENT = "D"
    TEAM = "T"
    ROLE = "R"


class AddressError(ValueError):
    """Base error for address parsing/validation."""

    pass


class GrammarError(AddressError):
    """The D/T/R grammar constraint was violated."""

    pass


@dataclass(frozen=True)
class AddressSegment:
    """A single segment of a positional address (e.g., D1, R2, T3)."""

    node_type: NodeType
    sequence: int  # 1-based within parent scope

    def __str__(self) -> str:
        return f"{self.node_type.value}{self.sequence}"

    @classmethod
    def parse(cls, s: str) -> AddressSegment:
        """Parse 'D1', 'R2', 'T3' etc.

        Args:
            s: A segment string like 'D1' or 'R2'. Case-insensitive for the type char.

        Returns:
            An AddressSegment with validated node_type and sequence.

        Raises:
            AddressError: If the segment is malformed, has an invalid type, or
                has an invalid/non-positive sequence number.
        """
        if not s or len(s) < 2:
            raise AddressError(f"Invalid segment: {s!r}")
        type_char = s[0].upper()
        try:
            node_type = NodeType(type_char)
        except ValueError:
            raise AddressError(f"Invalid node type '{type_char}' in segment {s!r}")
        try:
            seq = int(s[1:])
        except ValueError:
            raise AddressError(f"Invalid sequence number in segment {s!r}")
        if seq < 1:
            raise AddressError(f"Sequence must be >= 1, got {seq}")
        return cls(node_type=node_type, sequence=seq)


@dataclass(frozen=True)
class Address:
    """A PACT positional address encoding containment and accountability.

    Format: D1-R1-D3-R1-T1-R1

    Grammar constraint: every D or T must be immediately followed by exactly one R.
    """

    segments: tuple[AddressSegment, ...]

    def __str__(self) -> str:
        return "-".join(str(s) for s in self.segments)

    def __len__(self) -> int:
        return len(self.segments)

    @property
    def depth(self) -> int:
        """Number of segments."""
        return len(self.segments)

    @property
    def parent(self) -> Address | None:
        """Address with the last segment removed, or None if root-level.

        Note: The returned parent is a structural parent (segments[:-1]).
        It is NOT grammar-validated because intermediate structural
        addresses (like ``D1``) are valid as containment references even
        though they cannot stand alone as complete addresses.
        """
        if len(self.segments) <= 1:
            return None
        return Address(segments=self.segments[:-1])

    @property
    def containment_unit(self) -> Address | None:
        """The nearest ancestor D or T address (the containing unit).

        Walks backward through segments to find the nearest Department or Team.
        Returns None if no D or T exists in the address (e.g., standalone Role).
        """
        for i in range(len(self.segments) - 1, -1, -1):
            if self.segments[i].node_type in (NodeType.DEPARTMENT, NodeType.TEAM):
                return Address(segments=self.segments[: i + 1])
        return None

    @property
    def accountability_chain(self) -> list[Address]:
        """All R segments in order -- the chain of accountable people.

        Returns a list of Address objects, each truncated to the position
        of a Role segment, representing the accountability chain from
        root to leaf.
        """
        result = []
        for i, seg in enumerate(self.segments):
            if seg.node_type == NodeType.ROLE:
                result.append(Address(segments=self.segments[: i + 1]))
        return result

    @property
    def last_segment(self) -> AddressSegment:
        """The final segment of this address."""
        return self.segments[-1]

    def is_prefix_of(self, other: Address) -> bool:
        """True if self is a proper prefix of other (strictly shorter)."""
        if len(self.segments) >= len(other.segments):
            return False
        return other.segments[: len(self.segments)] == self.segments

    def is_ancestor_of(self, other: Address) -> bool:
        """True if self is a prefix of or equal to other (reflexive)."""
        if len(self.segments) > len(other.segments):
            return False
        return other.segments[: len(self.segments)] == self.segments

    def ancestors(self) -> list[Address]:
        """All ancestor addresses from root to parent (not including self)."""
        result = []
        for i in range(1, len(self.segments)):
            result.append(Address(segments=self.segments[:i]))
        return result

    @classmethod
    def parse(cls, s: str) -> Address:
        """Parse an address string like 'D1-R1-D3-R1-T1-R1'.

        Validates the D/T/R grammar constraint: every D or T must be
        immediately followed by exactly one R.

        Args:
            s: Hyphen-separated address string (e.g., 'D1-R1-T1-R1').

        Returns:
            A validated Address.

        Raises:
            AddressError: If the string is empty or a segment is malformed.
            GrammarError: If the D/T/R grammar is violated.
        """
        if not s or not s.strip():
            raise AddressError("Address string is empty")

        parts = s.strip().split("-")
        segments = tuple(AddressSegment.parse(p) for p in parts)

        _validate_grammar(segments)

        return cls(segments=segments)

    @classmethod
    def from_segments(cls, *segments: AddressSegment) -> Address:
        """Create from segments, validating grammar.

        Args:
            *segments: One or more AddressSegment instances.

        Returns:
            A validated Address.

        Raises:
            AddressError: If no segments are provided.
            GrammarError: If the D/T/R grammar is violated.
        """
        _validate_grammar(segments)
        return cls(segments=tuple(segments))


def _validate_grammar(
    segments: tuple[AddressSegment, ...] | list[AddressSegment],
) -> None:
    """Validate D/T/R grammar: every D or T must be immediately followed by R.

    State machine:
      State 0 (initial/after-R): Accept D, T, R
      State 1 (after D or T): Must see R next

    Args:
        segments: The ordered sequence of address segments to validate.

    Raises:
        AddressError: If segments is empty.
        GrammarError: If any D or T is not immediately followed by R,
            or if the address ends with an unmatched D or T.
    """
    if not segments:
        raise AddressError("Address must have at least one segment")

    state = 0  # 0 = expecting any, 1 = must see R

    for i, seg in enumerate(segments):
        if state == 1:
            # After D/T, must see R
            if seg.node_type != NodeType.ROLE:
                prev = segments[i - 1]
                raise GrammarError(
                    f"Grammar violation at position {i}: {prev.node_type.name} "
                    f"at position {i - 1} must be immediately followed by R (Role), "
                    f"but found {seg.node_type.name}. Every Department or Team "
                    f"must have an accountable person (head Role)."
                )
            state = 0
        else:
            # State 0: accept anything
            if seg.node_type in (NodeType.DEPARTMENT, NodeType.TEAM):
                state = 1  # next must be R
            # R keeps us in state 0

    # If we end in state 1, the last D/T has no R
    if state == 1:
        last = segments[-1]
        raise GrammarError(
            f"Grammar violation: address ends with {last.node_type.name} "
            f"without a head Role. Every Department or Team must be "
            f"immediately followed by a Role."
        )
