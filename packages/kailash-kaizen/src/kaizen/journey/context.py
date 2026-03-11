"""
Context Accumulator for Journey Orchestration.

Manages cross-pathway context accumulation with field-level merge strategies,
versioning, and snapshot/restore capabilities.

Components:
    - MergeStrategy: Enum for merge strategies
    - AccumulatedField: Tracked field with metadata
    - ContextSnapshot: Point-in-time context snapshot
    - ContextAccumulator: Main accumulator class

Merge Strategies:
    - REPLACE: New value replaces old (default)
    - APPEND: Append to list
    - MERGE_DICT: Merge dictionaries
    - MAX: Keep maximum value
    - MIN: Keep minimum value
    - SUM: Sum numeric values
    - UNION: Set union for lists

Usage:
    from kaizen.journey.context import ContextAccumulator, MergeStrategy

    accumulator = ContextAccumulator(config)
    accumulator.configure_field("rejected_doctors", MergeStrategy.APPEND)

    context = {"customer_name": "Alice"}
    accumulator.accumulate(context, {"preferred_time": "morning"}, "intake")
    accumulator.accumulate(context, {"rejected_doctors": ["Dr. Smith"]}, "booking")
    accumulator.accumulate(context, {"rejected_doctors": ["Dr. Jones"]}, "booking")
    # Result: {"customer_name": "Alice", "preferred_time": "morning",
    #          "rejected_doctors": ["Dr. Smith", "Dr. Jones"]}

References:
    - docs/plans/03-journey/05-runtime.md
    - TODO-JO-004: Runtime Components
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from kaizen.journey.errors import ContextSizeExceededError

if TYPE_CHECKING:
    from kaizen.journey.core import JourneyConfig


class MergeStrategy(str, Enum):
    """
    Strategy for merging accumulated values.

    Each strategy defines how new values are combined with existing values
    for a specific context field.

    Values:
        REPLACE: New value replaces old (default behavior)
        APPEND: Append to list (creates list if needed)
        MERGE_DICT: Merge dictionaries (new values override old keys)
        MAX: Keep maximum value (numeric comparison)
        MIN: Keep minimum value (numeric comparison)
        SUM: Sum numeric values
        UNION: Set union for lists (removes duplicates)

    Example:
        >>> accumulator.configure_field("preferences", MergeStrategy.UNION)
        >>> context = {"preferences": ["morning", "telehealth"]}
        >>> accumulator.accumulate(context, {"preferences": ["morning", "female_doctor"]})
        >>> set(context["preferences"])
        {'morning', 'telehealth', 'female_doctor'}
    """

    REPLACE = "replace"
    APPEND = "append"
    MERGE_DICT = "merge"
    MAX = "max"
    MIN = "min"
    SUM = "sum"
    UNION = "union"


@dataclass
class AccumulatedField:
    """
    Tracked accumulated field with metadata.

    Records the history of a context field for debugging, auditing,
    and potential rollback scenarios.

    Attributes:
        name: Field name
        value: Current value
        source_pathway: Pathway that last modified this field
        timestamp: When the field was last modified
        version: Accumulation version number
    """

    name: str
    value: Any
    source_pathway: str
    timestamp: datetime
    version: int = 1


@dataclass
class ContextSnapshot:
    """
    Snapshot of context at a point in time.

    Used for rollback, debugging, and recovery scenarios.
    Snapshots are immutable after creation.

    Attributes:
        context: Copy of the context at snapshot time
        pathway_id: Pathway that was active at snapshot time
        timestamp: When the snapshot was created
        version: Accumulation version at snapshot time
    """

    context: Dict[str, Any]
    pathway_id: str
    timestamp: datetime
    version: int


class ContextAccumulator:
    """
    Manages cross-pathway context accumulation.

    The ContextAccumulator is responsible for:
    - Merging outputs from pathways into accumulated context
    - Applying field-level merge strategies
    - Tracking field history for auditing
    - Creating and restoring snapshots
    - Validating context size limits

    The accumulator supports different merge strategies per field,
    allowing for flexible context management:

    - Simple fields use REPLACE (last value wins)
    - Lists like rejected_doctors use APPEND (accumulate rejections)
    - Sets like preferences use UNION (collect unique values)
    - Counters use SUM (accumulate totals)

    Attributes:
        config: Journey configuration with size limits
        _merge_strategies: Field name -> MergeStrategy mapping
        _field_history: Field name -> List[AccumulatedField] mapping
        _snapshots: List of context snapshots
        _version: Current accumulation version

    Example:
        >>> accumulator = ContextAccumulator(config)
        >>> accumulator.configure_field("rejected", MergeStrategy.APPEND)
        >>> context = {}
        >>> accumulator.accumulate(context, {"name": "Alice"}, "intake")
        >>> accumulator.accumulate(context, {"rejected": ["Dr. A"]}, "booking")
        >>> accumulator.accumulate(context, {"rejected": ["Dr. B"]}, "booking")
        >>> context
        {'name': 'Alice', 'rejected': ['Dr. A', 'Dr. B']}
    """

    def __init__(self, config: "JourneyConfig"):
        """
        Initialize ContextAccumulator.

        Args:
            config: Journey configuration with size limits
        """
        self.config = config
        self._merge_strategies: Dict[str, MergeStrategy] = {}
        self._field_history: Dict[str, List[AccumulatedField]] = {}
        self._snapshots: List[ContextSnapshot] = []
        self._version = 0

    def configure_field(
        self,
        field_name: str,
        strategy: MergeStrategy = MergeStrategy.REPLACE,
    ) -> None:
        """
        Configure merge strategy for a specific field.

        Fields without explicit configuration use REPLACE strategy.

        Args:
            field_name: Name of the field to configure
            strategy: Merge strategy to use for this field

        Example:
            >>> accumulator.configure_field("preferences", MergeStrategy.UNION)
            >>> accumulator.configure_field("retry_count", MergeStrategy.SUM)
        """
        self._merge_strategies[field_name] = strategy

    def configure_fields(self, strategies: Dict[str, MergeStrategy]) -> None:
        """
        Configure merge strategies for multiple fields at once.

        Args:
            strategies: Dict of field_name -> MergeStrategy

        Example:
            >>> accumulator.configure_fields({
            ...     "rejected_doctors": MergeStrategy.APPEND,
            ...     "preferences": MergeStrategy.UNION,
            ...     "total_cost": MergeStrategy.SUM,
            ... })
        """
        self._merge_strategies.update(strategies)

    def accumulate(
        self,
        context: Dict[str, Any],
        new_values: Dict[str, Any],
        source_pathway: str = "",
    ) -> Dict[str, Any]:
        """
        Accumulate new values into context.

        Applies field-level merge strategies to combine new values with
        existing context. The context is modified in place and returned.

        Args:
            context: Current accumulated context (modified in place)
            new_values: New values to accumulate
            source_pathway: Pathway that produced these values (for tracking)

        Returns:
            Updated context

        Raises:
            ContextSizeExceededError: If context exceeds size limit

        Example:
            >>> context = {"name": "Alice"}
            >>> accumulator.accumulate(context, {"age": 30}, "intake")
            {'name': 'Alice', 'age': 30}
        """
        for field_name, new_value in new_values.items():
            if new_value is None:
                continue

            strategy = self._merge_strategies.get(field_name, MergeStrategy.REPLACE)

            old_value = context.get(field_name)
            merged_value = self._merge_value(old_value, new_value, strategy)

            context[field_name] = merged_value

            # Track field history
            self._track_field(field_name, merged_value, source_pathway)

        self._version += 1

        # Validate size
        if not self.validate_size(context):
            current_size = self.get_context_size(context)
            max_size = self.config.max_context_size_bytes
            raise ContextSizeExceededError(current_size, max_size)

        return context

    def _merge_value(
        self,
        old: Any,
        new: Any,
        strategy: MergeStrategy,
    ) -> Any:
        """
        Merge old and new values based on strategy.

        Args:
            old: Existing value (may be None)
            new: New value to merge
            strategy: Merge strategy to apply

        Returns:
            Merged value
        """
        if old is None:
            return new

        if strategy == MergeStrategy.REPLACE:
            return new

        elif strategy == MergeStrategy.APPEND:
            if isinstance(old, list):
                if isinstance(new, list):
                    return old + new
                return old + [new]
            return [old, new]

        elif strategy == MergeStrategy.MERGE_DICT:
            if isinstance(old, dict) and isinstance(new, dict):
                merged = old.copy()
                merged.update(new)
                return merged
            return new

        elif strategy == MergeStrategy.MAX:
            try:
                return max(old, new)
            except TypeError:
                return new

        elif strategy == MergeStrategy.MIN:
            try:
                return min(old, new)
            except TypeError:
                return new

        elif strategy == MergeStrategy.SUM:
            try:
                return old + new
            except TypeError:
                return new

        elif strategy == MergeStrategy.UNION:
            if isinstance(old, list) and isinstance(new, list):
                # Convert to set for union, then back to list
                # Preserves order from old + new unique items
                seen = set()
                result = []
                for item in old + new:
                    # Handle unhashable items by converting to string
                    try:
                        key = item
                        if key not in seen:
                            seen.add(key)
                            result.append(item)
                    except TypeError:
                        # Unhashable item - use string representation
                        key = str(item)
                        if key not in seen:
                            seen.add(key)
                            result.append(item)
                return result
            return new

        return new

    def _track_field(
        self,
        field_name: str,
        value: Any,
        source_pathway: str,
    ) -> None:
        """
        Track field history for debugging/auditing.

        Args:
            field_name: Name of the field
            value: Current value
            source_pathway: Pathway that modified this field
        """
        if field_name not in self._field_history:
            self._field_history[field_name] = []

        entry = AccumulatedField(
            name=field_name,
            value=value,
            source_pathway=source_pathway,
            timestamp=datetime.now(timezone.utc),
            version=self._version,
        )

        self._field_history[field_name].append(entry)

        # Limit history size per field
        max_history = 100
        if len(self._field_history[field_name]) > max_history:
            self._field_history[field_name] = self._field_history[field_name][
                -max_history:
            ]

    def snapshot(
        self,
        context: Dict[str, Any],
        pathway_id: str,
    ) -> ContextSnapshot:
        """
        Create a snapshot of current context.

        Snapshots can be used to restore context to a previous state,
        useful for error recovery or rollback scenarios.

        Args:
            context: Current context to snapshot
            pathway_id: Current pathway ID

        Returns:
            ContextSnapshot with copy of context

        Example:
            >>> snapshot = accumulator.snapshot(context, "booking")
            >>> # ... more operations ...
            >>> restored = accumulator.restore_snapshot(snapshot.version)
        """
        snapshot = ContextSnapshot(
            context=context.copy(),
            pathway_id=pathway_id,
            timestamp=datetime.now(timezone.utc),
            version=self._version,
        )
        self._snapshots.append(snapshot)

        # Limit snapshots
        max_snapshots = 10
        if len(self._snapshots) > max_snapshots:
            self._snapshots = self._snapshots[-max_snapshots:]

        return snapshot

    def restore_snapshot(self, version: int) -> Optional[Dict[str, Any]]:
        """
        Restore context from a specific version.

        Searches snapshots in reverse order to find matching version.

        Args:
            version: Version number to restore

        Returns:
            Copy of context at that version, or None if not found
        """
        for snapshot in reversed(self._snapshots):
            if snapshot.version == version:
                return snapshot.context.copy()
        return None

    def get_latest_snapshot(self) -> Optional[ContextSnapshot]:
        """
        Get the most recent snapshot.

        Returns:
            Most recent ContextSnapshot, or None if no snapshots exist
        """
        if self._snapshots:
            return self._snapshots[-1]
        return None

    def get_field_history(
        self,
        field_name: str,
    ) -> List[AccumulatedField]:
        """
        Get history of a specific field.

        Args:
            field_name: Name of the field

        Returns:
            List of AccumulatedField entries (copy to prevent mutation)
        """
        return self._field_history.get(field_name, []).copy()

    def get_context_size(self, context: Dict[str, Any]) -> int:
        """
        Calculate approximate size of context in bytes.

        Uses JSON serialization to estimate size. Returns 0 if
        serialization fails (e.g., for non-JSON-serializable objects).

        Args:
            context: Context to measure

        Returns:
            Size in bytes, or 0 if measurement fails
        """
        try:
            return len(json.dumps(context).encode("utf-8"))
        except (TypeError, ValueError):
            return 0

    def validate_size(self, context: Dict[str, Any]) -> bool:
        """
        Check if context is within size limits.

        Args:
            context: Context to validate

        Returns:
            True if within limits, False otherwise
        """
        size = self.get_context_size(context)
        return size <= self.config.max_context_size_bytes

    def get_version(self) -> int:
        """
        Get current accumulation version.

        Returns:
            Current version number
        """
        return self._version

    def get_configured_strategies(self) -> Dict[str, MergeStrategy]:
        """
        Get all configured merge strategies.

        Returns:
            Copy of field -> strategy mapping
        """
        return self._merge_strategies.copy()

    def clear_history(self) -> None:
        """Clear all field history and snapshots."""
        self._field_history.clear()
        self._snapshots.clear()

    def get_stats(self) -> Dict[str, Any]:
        """
        Get accumulator statistics.

        Returns:
            Dict with version, history count, snapshot count, etc.
        """
        return {
            "version": self._version,
            "configured_fields": len(self._merge_strategies),
            "tracked_fields": len(self._field_history),
            "snapshot_count": len(self._snapshots),
            "total_history_entries": sum(
                len(entries) for entries in self._field_history.values()
            ),
        }


__all__ = [
    "MergeStrategy",
    "AccumulatedField",
    "ContextSnapshot",
    "ContextAccumulator",
]
