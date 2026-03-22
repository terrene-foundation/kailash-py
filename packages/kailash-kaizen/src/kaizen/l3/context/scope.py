# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""L3 ContextScope — hierarchical scoped context with projection-based access.

A mutable entity type representing a node in the context hierarchy.
Each scope has local key-value data, projections controlling visibility
and writability, and a direct reference to its parent scope for upward
traversal.

Concurrency note: Per AD-L3-04-AMENDED, L3 primitives use asyncio.Lock
for shared state. This module provides synchronous methods for the core
data operations (get/set/remove/visible_keys/snapshot/merge_child_results)
because the context tree is logically single-threaded within one agent's
execution. The asyncio.Lock integration happens at the orchestration layer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Optional

from kaizen.l3.context.projection import ScopeProjection
from kaizen.l3.context.types import (
    ClassificationExceedsClearance,
    ClearanceExceedsParent,
    ConflictResolution,
    ContextValue,
    DataClassification,
    MergeConflict,
    MergeResult,
    NotAChild,
    ProjectionNotSubset,
    WriteProjectionViolation,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ContextScope",
]


class ContextScope:
    """A hierarchical scope node in the context tree.

    Contains local data, a reference to its parent, and projections
    controlling what this scope can see and write.

    Invariants:
        - Root scope: parent is None, unrestricted projections, highest clearance.
        - Child scope: parent is set, read_projection subset of parent's,
          effective_clearance <= parent's (monotonic tightening).
        - No circular parent references (create_child always creates fresh UUIDs).

    Attributes:
        scope_id: Unique identifier for this scope (UUID v4).
        parent: Direct reference to parent ContextScope, or None for root.
        owner_id: Agent instance ID that owns this scope.
        data: Local key-value store (key -> ContextValue).
        read_projection: Controls which keys this scope can read.
        write_projection: Controls which keys this scope can write.
        effective_clearance: Max classification this scope can access.
        default_classification: Default classification for new values.
        children: Child ContextScope references (for traversal/cleanup).
        created_at: When this scope was created.
    """

    __slots__ = (
        "scope_id",
        "parent",
        "owner_id",
        "data",
        "read_projection",
        "write_projection",
        "effective_clearance",
        "default_classification",
        "children",
        "created_at",
    )

    def __init__(
        self,
        *,
        scope_id: str,
        parent: Optional[ContextScope],
        owner_id: str,
        read_projection: ScopeProjection,
        write_projection: ScopeProjection,
        effective_clearance: DataClassification,
        default_classification: DataClassification,
    ) -> None:
        self.scope_id: str = scope_id
        self.parent: Optional[ContextScope] = parent
        self.owner_id: str = owner_id
        self.data: dict[str, ContextValue] = {}
        self.read_projection: ScopeProjection = read_projection
        self.write_projection: ScopeProjection = write_projection
        self.effective_clearance: DataClassification = effective_clearance
        self.default_classification: DataClassification = default_classification
        self.children: list[ContextScope] = []
        self.created_at: datetime = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def root(
        cls,
        owner_id: str,
        *,
        clearance: DataClassification = DataClassification.TOP_SECRET,
        default_classification: DataClassification = DataClassification.RESTRICTED,
    ) -> ContextScope:
        """Create the root scope for a delegation tree (INV-6).

        The root has no parent, unrestricted projections (allow=["**"]),
        and the specified clearance level.
        """
        return cls(
            scope_id=str(uuid.uuid4()),
            parent=None,
            owner_id=owner_id,
            read_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            write_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            effective_clearance=clearance,
            default_classification=default_classification,
        )

    # ------------------------------------------------------------------
    # create_child
    # ------------------------------------------------------------------

    def create_child(
        self,
        owner_id: str,
        read_projection: ScopeProjection,
        write_projection: ScopeProjection,
        effective_clearance: Optional[DataClassification] = None,
        default_classification: Optional[DataClassification] = None,
    ) -> ContextScope:
        """Create a child scope with monotonic tightening enforcement.

        Args:
            owner_id: Agent instance ID for the child.
            read_projection: Must be a subset of self.read_projection (INV-1).
            write_projection: No subset constraint relative to parent.
            effective_clearance: Must be <= self.effective_clearance.
                Defaults to self.effective_clearance.
            default_classification: Must be <= child's effective_clearance.
                Defaults to self.default_classification.

        Returns:
            A new ContextScope with parent=self and empty data.

        Raises:
            ProjectionNotSubset: read_projection not subset of parent's.
            ClearanceExceedsParent: requested clearance exceeds parent's.
            ClassificationExceedsClearance: default_classification exceeds
                the child's effective_clearance.
        """
        # Resolve defaults
        child_clearance = (
            effective_clearance
            if effective_clearance is not None
            else self.effective_clearance
        )

        # Enforce: child clearance <= parent clearance
        if child_clearance.value > self.effective_clearance.value:
            raise ClearanceExceedsParent(
                f"Requested clearance {child_clearance.name} exceeds parent's "
                f"{self.effective_clearance.name}",
                details={
                    "parent_clearance": self.effective_clearance.name,
                    "requested_clearance": child_clearance.name,
                    "parent_scope_id": self.scope_id,
                },
            )

        # Enforce: child read_projection subset of parent's (INV-1)
        if not read_projection.is_subset_of(self.read_projection):
            raise ProjectionNotSubset(
                "Child read_projection is not a subset of parent's read_projection",
                details={
                    "parent_allow": self.read_projection.allow_patterns,
                    "parent_deny": self.read_projection.deny_patterns,
                    "requested_allow": read_projection.allow_patterns,
                    "requested_deny": read_projection.deny_patterns,
                    "parent_scope_id": self.scope_id,
                },
            )

        # Resolve default_classification
        if default_classification is not None:
            # Explicitly provided: MUST be <= child's clearance
            if default_classification.value > child_clearance.value:
                raise ClassificationExceedsClearance(
                    f"Default classification {default_classification.name} exceeds "
                    f"child's effective clearance {child_clearance.name}",
                    details={
                        "key": "(default_classification)",
                        "value_classification": default_classification.name,
                        "scope_clearance": child_clearance.name,
                    },
                )
            child_default_class = default_classification
        else:
            # Inherited: cap to child's clearance (monotonic tightening)
            child_default_class = DataClassification(
                min(self.default_classification.value, child_clearance.value)
            )

        child = ContextScope(
            scope_id=str(uuid.uuid4()),
            parent=self,
            owner_id=owner_id,
            read_projection=read_projection,
            write_projection=write_projection,
            effective_clearance=child_clearance,
            default_classification=child_default_class,
        )
        self.children.append(child)

        logger.debug(
            "Created child scope %s (owner=%s) under parent %s",
            child.scope_id,
            owner_id,
            self.scope_id,
        )
        return child

    # ------------------------------------------------------------------
    # get — read with projection, classification, and parent traversal
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[ContextValue]:
        """Retrieve a value by key, with projection and classification filtering.

        Behavior (INV-7):
            1. Check read_projection permits key; if not, return None.
            2. Check local data for the key.
            3. If found locally and classification <= effective_clearance, return it.
            4. If found locally but classification too high, return None.
            5. If not found locally, traverse to parent.
            6. If not found in any ancestor, return None.

        Args:
            key: The dot-separated key to look up.

        Returns:
            The ContextValue if accessible, otherwise None.
        """
        if not self.read_projection.permits(key):
            return None
        return self._get_internal(key, self.read_projection, self.effective_clearance)

    def _get_internal(
        self,
        key: str,
        requester_projection: ScopeProjection,
        requester_clearance: DataClassification,
    ) -> Optional[ContextValue]:
        """Internal get with the requesting scope's projection and clearance.

        This allows parent scopes to filter based on the requesting child's
        constraints during upward traversal.
        """
        # Check local data
        if key in self.data:
            cv = self.data[key]
            if cv.classification.value <= requester_clearance.value:
                return cv
            # Classification too high for requester
            return None

        # Not found locally — traverse to parent
        if self.parent is not None:
            return self.parent._get_internal(
                key, requester_projection, requester_clearance
            )

        return None

    # ------------------------------------------------------------------
    # set — write with projection enforcement
    # ------------------------------------------------------------------

    def set(
        self,
        key: str,
        value: Any,
        classification: Optional[DataClassification] = None,
    ) -> None:
        """Store a value in local data with projection and classification enforcement.

        Args:
            key: The dot-separated key.
            value: The value to store (any JSON-compatible type).
            classification: Sensitivity level. Defaults to self.default_classification.

        Raises:
            WriteProjectionViolation: Key not in write_projection (INV-3).
            ClassificationExceedsClearance: Classification above scope's clearance.
        """
        # Enforce write projection (INV-3)
        if not self.write_projection.permits(key):
            raise WriteProjectionViolation(
                f"Key '{key}' is not permitted by write_projection",
                details={
                    "key": key,
                    "write_allow": self.write_projection.allow_patterns,
                    "write_deny": self.write_projection.deny_patterns,
                    "scope_id": self.scope_id,
                },
            )

        # Determine classification
        effective_class = (
            classification
            if classification is not None
            else self.default_classification
        )

        # Enforce classification <= clearance
        if effective_class.value > self.effective_clearance.value:
            raise ClassificationExceedsClearance(
                f"Classification {effective_class.name} exceeds scope clearance "
                f"{self.effective_clearance.name}",
                details={
                    "key": key,
                    "value_classification": effective_class.name,
                    "scope_clearance": self.effective_clearance.name,
                    "scope_id": self.scope_id,
                },
            )

        self.data[key] = ContextValue(
            value=value,
            written_by=self.owner_id,
            updated_at=datetime.now(UTC),
            classification=effective_class,
        )

    # ------------------------------------------------------------------
    # remove — local only (INV-8)
    # ------------------------------------------------------------------

    def remove(self, key: str) -> Optional[ContextValue]:
        """Remove a key from local data only (INV-8).

        Does NOT propagate to parent or children.
        Does NOT check projections (removing a locally-held key is always permitted).

        Args:
            key: The key to remove.

        Returns:
            The removed ContextValue, or None if the key was not present locally.
        """
        return self.data.pop(key, None)

    # ------------------------------------------------------------------
    # visible_keys
    # ------------------------------------------------------------------

    def visible_keys(self) -> list[str]:
        """Return all keys visible to this scope.

        Collects keys from local data and parent chain, filtered by
        this scope's read_projection and effective_clearance.
        Deduplicates (local shadows parent).
        """
        seen: set[str] = set()
        result: list[str] = []
        self._collect_visible_keys(
            self.read_projection, self.effective_clearance, seen, result
        )
        return result

    def _collect_visible_keys(
        self,
        requester_projection: ScopeProjection,
        requester_clearance: DataClassification,
        seen: set[str],
        result: list[str],
    ) -> None:
        """Collect visible keys from this scope and its parent chain."""
        # Local keys first (they shadow parent keys)
        for key, cv in self.data.items():
            if key in seen:
                continue
            if not requester_projection.permits(key):
                continue
            if cv.classification.value > requester_clearance.value:
                continue
            seen.add(key)
            result.append(key)

        # Then parent keys
        if self.parent is not None:
            self.parent._collect_visible_keys(
                requester_projection, requester_clearance, seen, result
            )

    # ------------------------------------------------------------------
    # snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Materialize a flat view of all visible keys and their values.

        This is the primary serialization point for sending context to an LLM.
        Returns key -> value (not the full ContextValue metadata).
        """
        keys = self.visible_keys()
        result: dict[str, Any] = {}
        for key in keys:
            cv = self.get(key)
            if cv is not None:
                result[key] = cv.value
        return result

    # ------------------------------------------------------------------
    # merge_child_results (INV-5)
    # ------------------------------------------------------------------

    def merge_child_results(self, child: ContextScope) -> MergeResult:
        """Merge a child scope's writes back into this parent scope.

        Only keys within the child's write_projection are merged (INV-5).
        Keys outside the write_projection are reported as skipped.
        Default merge strategy: CHILD_WINS for conflicts.

        Args:
            child: The child scope to merge from. Must be a direct child.

        Returns:
            MergeResult with merged_keys, skipped_keys, and conflicts.

        Raises:
            NotAChild: The provided scope is not a child of this scope.
        """
        # Validate parent-child relationship
        if child.parent is not self:
            raise NotAChild(
                "Provided scope is not a child of this scope",
                details={
                    "expected_parent_id": self.scope_id,
                    "actual_parent_id": (
                        child.parent.scope_id if child.parent is not None else None
                    ),
                    "child_scope_id": child.scope_id,
                },
            )

        merged_keys: list[str] = []
        skipped_keys: list[str] = []
        conflicts: list[MergeConflict] = []

        for key, child_cv in child.data.items():
            if not child.write_projection.permits(key):
                skipped_keys.append(key)
                continue

            # Check for conflict: parent has the key and it was updated
            # after the child was created
            if key in self.data:
                parent_cv = self.data[key]
                if parent_cv.updated_at > child.created_at:
                    conflicts.append(
                        MergeConflict(
                            key=key,
                            parent_value_updated_at=parent_cv.updated_at,
                            child_value_updated_at=child_cv.updated_at,
                            resolution=ConflictResolution.CHILD_WINS,
                        )
                    )

            # Apply merge: CHILD_WINS (copy child's value preserving provenance)
            self.data[key] = child_cv
            merged_keys.append(key)

        # Remove child from children list
        self.children = [c for c in self.children if c.scope_id != child.scope_id]

        logger.debug(
            "Merged child %s into parent %s: %d merged, %d skipped, %d conflicts",
            child.scope_id,
            self.scope_id,
            len(merged_keys),
            len(skipped_keys),
            len(conflicts),
        )

        return MergeResult(
            merged_keys=merged_keys,
            skipped_keys=skipped_keys,
            conflicts=conflicts,
        )

    def __repr__(self) -> str:
        return (
            f"ContextScope(scope_id={self.scope_id!r}, "
            f"owner_id={self.owner_id!r}, "
            f"keys={list(self.data.keys())}, "
            f"children={len(self.children)})"
        )
