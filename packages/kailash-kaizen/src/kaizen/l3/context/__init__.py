# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Hierarchical scoped context with projection-based access control.

Provides ScopedContext (L3-002): a tree of context scopes where each child
scope sees a controlled, filtered subset of its parent's data via
projection-based access control and classification-based clearance filtering.

Key types:
    ContextScope       — Hierarchical scope node with local data and projections.
    ScopeProjection    — Allow/deny glob patterns for key visibility/writability.
    DataClassification — Five-level sensitivity classification (C0-C4).
    ContextValue       — Value with provenance and classification metadata.
    MergeResult        — Result of merging child writes back into parent.
"""

from __future__ import annotations

from kaizen.l3.context.projection import ScopeProjection
from kaizen.l3.context.scope import ContextScope
from kaizen.l3.context.types import (
    ClassificationExceedsClearance,
    ClearanceExceedsParent,
    ConflictResolution,
    ContextError,
    ContextValue,
    DataClassification,
    MergeConflict,
    MergeResult,
    NotAChild,
    ProjectionNotSubset,
    WriteProjectionViolation,
)

__all__ = [
    "ClassificationExceedsClearance",
    "ClearanceExceedsParent",
    "ConflictResolution",
    "ContextError",
    "ContextScope",
    "ContextValue",
    "DataClassification",
    "MergeConflict",
    "MergeResult",
    "NotAChild",
    "ProjectionNotSubset",
    "ScopeProjection",
    "WriteProjectionViolation",
]
