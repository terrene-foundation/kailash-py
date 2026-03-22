# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""L3 ScopedContext types — classifications, values, merge results, errors.

All value types are frozen dataclasses per AD-L3-15.
All errors inherit from ContextError with structured .details.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum, Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "ClassificationExceedsClearance",
    "ClearanceExceedsParent",
    "ConflictResolution",
    "ContextError",
    "ContextValue",
    "DataClassification",
    "MergeConflict",
    "MergeResult",
    "NotAChild",
    "ProjectionNotSubset",
    "WriteProjectionViolation",
]


# ---------------------------------------------------------------------------
# DataClassification — int-backed enum for numeric ordering
# ---------------------------------------------------------------------------


class DataClassification(IntEnum):
    """Five-level classification per PACT Section 6.2.

    Ordering is numeric: PUBLIC(0) < RESTRICTED(1) < ... < TOP_SECRET(4).
    An agent with clearance N can access values with classification <= N.

    PACT name mapping:
        C0=PUBLIC, C1=RESTRICTED, C2=CONFIDENTIAL, C3=SECRET, C4=TOP_SECRET
    """

    PUBLIC = 0  # C0: Routine operations, published information
    RESTRICTED = 1  # C1: Commercial data, personnel records
    CONFIDENTIAL = 2  # C2: Strategic plans, board materials
    SECRET = 3  # C3: Legal privilege, regulatory investigation
    TOP_SECRET = 4  # C4: Existential risk, crisis plans


# ---------------------------------------------------------------------------
# ConflictResolution
# ---------------------------------------------------------------------------


class ConflictResolution(str, Enum):
    """How a merge conflict was resolved."""

    CHILD_WINS = "child_wins"
    PARENT_WINS = "parent_wins"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# ContextValue — frozen value with provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextValue:
    """A value stored in a context scope with provenance and classification.

    Attributes:
        value: The actual value (any JSON-compatible type).
        written_by: Agent instance ID that wrote this value.
        updated_at: When this value was last written.
        classification: Sensitivity level of this value.
    """

    value: Any
    written_by: str
    updated_at: datetime
    classification: DataClassification

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "written_by": self.written_by,
            "updated_at": self.updated_at.isoformat(),
            "classification": self.classification.name,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ContextValue:
        updated_at_raw = d["updated_at"]
        if isinstance(updated_at_raw, str):
            updated_at = datetime.fromisoformat(updated_at_raw)
        elif isinstance(updated_at_raw, datetime):
            updated_at = updated_at_raw
        else:
            raise ValueError(
                f"updated_at must be str or datetime, got {type(updated_at_raw)}"
            )
        classification_raw = d["classification"]
        if isinstance(classification_raw, str):
            classification = DataClassification[classification_raw]
        elif isinstance(classification_raw, DataClassification):
            classification = classification_raw
        else:
            raise ValueError(
                f"classification must be str or DataClassification, got {type(classification_raw)}"
            )
        return cls(
            value=d["value"],
            written_by=d["written_by"],
            updated_at=updated_at,
            classification=classification,
        )


# ---------------------------------------------------------------------------
# MergeConflict — frozen conflict record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MergeConflict:
    """A conflict detected during merge_child_results().

    Attributes:
        key: The conflicting key.
        parent_value_updated_at: When the parent's value was last updated.
        child_value_updated_at: When the child's value was last updated.
        resolution: How the conflict was resolved.
    """

    key: str
    parent_value_updated_at: datetime
    child_value_updated_at: datetime
    resolution: ConflictResolution

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "parent_value_updated_at": self.parent_value_updated_at.isoformat(),
            "child_value_updated_at": self.child_value_updated_at.isoformat(),
            "resolution": self.resolution.value,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MergeConflict:
        parent_ts = d["parent_value_updated_at"]
        if isinstance(parent_ts, str):
            parent_ts = datetime.fromisoformat(parent_ts)
        child_ts = d["child_value_updated_at"]
        if isinstance(child_ts, str):
            child_ts = datetime.fromisoformat(child_ts)
        resolution = d["resolution"]
        if isinstance(resolution, str):
            resolution = ConflictResolution(resolution)
        return cls(
            key=d["key"],
            parent_value_updated_at=parent_ts,
            child_value_updated_at=child_ts,
            resolution=resolution,
        )


# ---------------------------------------------------------------------------
# MergeResult — frozen merge outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MergeResult:
    """Result of merging a child scope's writes back into its parent.

    Attributes:
        merged_keys: Keys successfully merged into parent.
        skipped_keys: Keys the child wrote but outside its write_projection.
        conflicts: Keys where parent had a newer value.
    """

    merged_keys: list[str]
    skipped_keys: list[str]
    conflicts: list[MergeConflict]

    def to_dict(self) -> dict[str, Any]:
        return {
            "merged_keys": list(self.merged_keys),
            "skipped_keys": list(self.skipped_keys),
            "conflicts": [c.to_dict() for c in self.conflicts],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MergeResult:
        return cls(
            merged_keys=list(d["merged_keys"]),
            skipped_keys=list(d["skipped_keys"]),
            conflicts=[MergeConflict.from_dict(c) for c in d["conflicts"]],
        )


# ---------------------------------------------------------------------------
# Error hierarchy — all inherit from ContextError with structured .details
# ---------------------------------------------------------------------------


class ContextError(Exception):
    """Base error for all ScopedContext operations.

    All subclasses carry a ``details`` dict for structured diagnostics.
    """

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        if details is None:
            raise ValueError(
                "ContextError requires a 'details' dict for structured diagnostics"
            )
        self.details: dict[str, Any] = details


class ProjectionNotSubset(ContextError):
    """Raised when a child's read_projection is not a subset of the parent's."""


class ClearanceExceedsParent(ContextError):
    """Raised when a child's requested clearance exceeds the parent's."""


class WriteProjectionViolation(ContextError):
    """Raised when a set() targets a key outside the scope's write_projection."""


class ClassificationExceedsClearance(ContextError):
    """Raised when a value's classification exceeds the scope's effective_clearance."""


class NotAChild(ContextError):
    """Raised when merge_child_results() is called with a non-child scope."""
