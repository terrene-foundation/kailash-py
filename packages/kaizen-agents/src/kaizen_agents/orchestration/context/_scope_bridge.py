# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ScopeBridge — bridges kaizen-agents context management with SDK ContextScope.

When a parent agent delegates a subtask to a child, the context injector
selects which keys are relevant. This module bridges that selection logic
with the SDK's ContextScope, which enforces classification-based access
control and projection-based visibility.

The ScopeBridge provides a simplified interface over ContextScope for the
kaizen-agents orchestration layer:
- Classification strings ("public", "confidential") instead of enum imports
- Simple key lists instead of ScopeProjection construction
- Writable prefix instead of explicit write projection patterns
"""

from __future__ import annotations

import logging
from typing import Any

from kaizen.l3.context.projection import ScopeProjection
from kaizen.l3.context.scope import ContextScope
from kaizen.l3.context.types import DataClassification, MergeResult

logger = logging.getLogger(__name__)

__all__ = [
    "ScopeBridge",
]

# ---------------------------------------------------------------------------
# Classification string mapping
# ---------------------------------------------------------------------------

_CLASSIFICATION_MAP: dict[str, DataClassification] = {
    "public": DataClassification.PUBLIC,
    "restricted": DataClassification.RESTRICTED,
    "confidential": DataClassification.CONFIDENTIAL,
    "secret": DataClassification.SECRET,
    "top_secret": DataClassification.TOP_SECRET,
}


def _parse_classification(clearance: str) -> DataClassification:
    """Convert a classification string to DataClassification.

    Case-insensitive. Supports: public, restricted, confidential,
    secret, top_secret.

    Args:
        clearance: Classification string to convert.

    Returns:
        The corresponding DataClassification enum value.

    Raises:
        ValueError: If the clearance string is not recognized.
    """
    normalized = clearance.strip().lower()
    classification = _CLASSIFICATION_MAP.get(normalized)
    if classification is None:
        valid_keys = ", ".join(sorted(_CLASSIFICATION_MAP.keys()))
        raise ValueError(f"Unknown classification '{clearance}'. " f"Valid values: {valid_keys}")
    return classification


# ---------------------------------------------------------------------------
# ScopeBridge
# ---------------------------------------------------------------------------


class ScopeBridge:
    """Bridges kaizen-agents context management with SDK ContextScope.

    Provides a simplified interface for the context injector to work with
    classification-based access control without directly importing SDK
    enums and constructing projections.

    Usage:
        # Create root scope for a supervisor agent
        bridge = ScopeBridge.create_root(
            owner_id="supervisor-1",
            clearance="confidential",
        )

        # Set context values with classification
        bridge.root_scope.set(
            "project.name", "Alpha",
            classification=DataClassification.PUBLIC,
        )

        # Create a child scope with restricted visibility
        child = bridge.create_child_scope(
            child_owner_id="worker-1",
            visible_keys=["project.*"],
            writable_prefix="results",
            clearance="public",
        )

        # Extract context for injection into child agent
        context = bridge.inject_context(keys=["project.name"])

        # After child completes, merge results back
        merged = bridge.merge_child_results(child)
    """

    def __init__(self, root_scope: ContextScope) -> None:
        """Wrap an existing ContextScope as the root.

        Args:
            root_scope: The SDK ContextScope to bridge. Must be a valid
                ContextScope instance.
        """
        if not isinstance(root_scope, ContextScope):
            raise TypeError(
                f"root_scope must be a ContextScope instance, " f"got {type(root_scope).__name__}"
            )
        self._root = root_scope

    @property
    def root_scope(self) -> ContextScope:
        """Return the underlying SDK ContextScope."""
        return self._root

    @classmethod
    def create_root(
        cls,
        owner_id: str,
        clearance: str = "confidential",
    ) -> ScopeBridge:
        """Create a root scope bridge with classification.

        Args:
            owner_id: Agent instance ID that owns this root scope.
            clearance: Maximum classification level this scope can access.
                Valid values: public, restricted, confidential, secret,
                top_secret. Case-insensitive. Defaults to "confidential".

        Returns:
            A new ScopeBridge wrapping a freshly created root ContextScope.

        Raises:
            ValueError: If the clearance string is not recognized.
        """
        classification = _parse_classification(clearance)
        root = ContextScope.root(
            owner_id=owner_id,
            clearance=classification,
        )
        logger.debug(
            "Created ScopeBridge root scope for owner=%s with clearance=%s",
            owner_id,
            classification.name,
        )
        return cls(root_scope=root)

    def create_child_scope(
        self,
        child_owner_id: str,
        visible_keys: list[str],
        writable_prefix: str,
        clearance: str | None = None,
    ) -> ContextScope:
        """Create a child scope with controlled visibility.

        Converts the simplified visible_keys list and writable_prefix into
        SDK ScopeProjection objects and delegates to ContextScope.create_child().

        Args:
            child_owner_id: Agent instance ID for the child scope.
            visible_keys: List of dot-segment glob patterns defining which
                keys the child can read. Uses the same pattern syntax as
                ScopeProjection (e.g., "project.*", "data.**").
            writable_prefix: A dot-separated prefix under which the child
                can write. Converted to a write projection pattern of
                "{prefix}.**".
            clearance: Optional classification level for the child. Must be
                equal to or lower than the parent's clearance. If None,
                inherits the parent's clearance. Case-insensitive string.

        Returns:
            A new ContextScope that is a child of this bridge's root scope.

        Raises:
            ValueError: If the clearance string is not recognized.
            ClearanceExceedsParent: If child clearance exceeds parent's.
            ProjectionNotSubset: If read projection is not a subset of
                parent's projection.
        """
        # Build write projection pattern from writable_prefix
        write_pattern = f"{writable_prefix}.**"

        # Build read projection from visible_keys, including the write
        # prefix so the child can read back its own writes.
        read_allow = list(visible_keys)
        if write_pattern not in read_allow:
            read_allow.append(write_pattern)
        read_projection = ScopeProjection(
            allow_patterns=read_allow,
            deny_patterns=[],
        )
        write_projection = ScopeProjection(
            allow_patterns=[write_pattern],
            deny_patterns=[],
        )

        # Parse clearance if provided
        effective_clearance = _parse_classification(clearance) if clearance is not None else None

        child = self._root.create_child(
            owner_id=child_owner_id,
            read_projection=read_projection,
            write_projection=write_projection,
            effective_clearance=effective_clearance,
        )

        logger.debug(
            "Created child scope for owner=%s with visible_keys=%s, "
            "writable_prefix=%s, clearance=%s",
            child_owner_id,
            visible_keys,
            writable_prefix,
            effective_clearance.name if effective_clearance else "inherited",
        )

        return child

    def inject_context(self, keys: list[str] | None = None) -> dict[str, Any]:
        """Extract context values for injection into a child agent.

        Reads values from the root scope and returns them as a flat dict
        suitable for passing to the ContextInjector or directly to a child.

        Args:
            keys: Specific keys to extract. If None, returns all visible
                values from the root scope (via snapshot()).

        Returns:
            A dict mapping key names to their values. Keys that do not
            exist in the root scope are silently omitted.
        """
        if keys is None:
            return self._root.snapshot()

        if not keys:
            return {}

        result: dict[str, Any] = {}
        for key in keys:
            cv = self._root.get(key)
            if cv is not None:
                result[key] = cv.value
        return result

    def merge_child_results(self, child_scope: ContextScope) -> dict[str, Any]:
        """Merge child scope results back into the root scope.

        Delegates to ContextScope.merge_child_results() and returns a dict
        of the merged key-value pairs for easy consumption.

        Args:
            child_scope: The child ContextScope whose writes should be
                merged back. Must be a direct child of this bridge's
                root scope.

        Returns:
            A dict mapping merged key names to their values. Empty dict
            if no keys were merged.

        Raises:
            NotAChild: If child_scope is not a direct child of root.
        """
        merge_result: MergeResult = self._root.merge_child_results(child_scope)

        # Build a dict of merged values for easy consumption
        merged: dict[str, Any] = {}
        for key in merge_result.merged_keys:
            cv = self._root.get(key)
            if cv is not None:
                merged[key] = cv.value

        if merge_result.conflicts:
            logger.warning(
                "Merge had %d conflict(s) (resolved as child-wins): %s",
                len(merge_result.conflicts),
                [c.key for c in merge_result.conflicts],
            )

        if merge_result.skipped_keys:
            logger.info(
                "Merge skipped %d key(s) outside write projection: %s",
                len(merge_result.skipped_keys),
                merge_result.skipped_keys,
            )

        return merged
