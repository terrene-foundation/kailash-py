"""Tracks node-level execution state for checkpoint/restore.

This module provides per-node completion tracking used by the durable
request system to capture workflow state at checkpoint boundaries and
restore it when resuming from a checkpoint.  On restore, the runtime
skips already-completed nodes and replays their cached outputs, avoiding
duplicate side effects.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["ExecutionTracker"]


class ExecutionTracker:
    """Records per-node completion and outputs during workflow execution.

    The tracker is threaded through the runtime execution loop:

    * **During execution** -- after each node completes, the runtime calls
      ``record_completion(node_id, output)`` to cache the result.
    * **During restore** -- the tracker is rebuilt from a serialised
      checkpoint via ``from_dict``.  When the runtime encounters a node
      whose ``is_completed`` returns ``True``, it skips execution and
      uses ``get_output`` instead.

    The class is intentionally kept small and JSON-serialisable so that it
    can be embedded directly inside ``Checkpoint.workflow_state``.
    """

    def __init__(self) -> None:
        self._completed: Dict[str, Dict[str, Any]] = {}  # node_id -> output
        self._execution_order: List[str] = []

    # ------------------------------------------------------------------
    # Recording API
    # ------------------------------------------------------------------

    def record_completion(self, node_id: str, output: Any) -> None:
        """Record that *node_id* completed with *output*."""
        self._completed[node_id] = self._serialize(output)
        if node_id not in self._execution_order:
            self._execution_order.append(node_id)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def is_completed(self, node_id: str) -> bool:
        """Return ``True`` if *node_id* has already been recorded."""
        return node_id in self._completed

    def get_output(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Return the cached output for *node_id*, or ``None``."""
        return self._completed.get(node_id)

    @property
    def completed_node_ids(self) -> List[str]:
        """Node IDs in the order they were recorded."""
        return list(self._execution_order)

    @property
    def serialized_outputs(self) -> Dict[str, Any]:
        """All cached outputs keyed by node ID."""
        return dict(self._completed)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly dict suitable for checkpoint storage."""
        return {
            "completed_nodes": list(self._execution_order),
            "node_outputs": dict(self._completed),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionTracker":
        """Reconstruct a tracker from a dict produced by ``to_dict``."""
        tracker = cls()
        for node_id in data.get("completed_nodes", []):
            output = data.get("node_outputs", {}).get(node_id, {})
            # Store directly -- the output was already serialised when it
            # was first recorded, so no need to re-serialise.
            tracker._completed[node_id] = output
            tracker._execution_order.append(node_id)
        return tracker

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize(output: Any) -> Dict[str, Any]:
        """Ensure *output* is a JSON-serialisable ``dict``."""
        if output is None:
            return {}
        if not isinstance(output, dict):
            try:
                json.dumps(output)
                return {"result": output}
            except (TypeError, ValueError):
                logger.warning(
                    "Non-serializable output for checkpoint — converted to string: %s",
                    type(output),
                )
                return {"result": str(output), "_serialization_degraded": True}
        # Verify the dict itself is serialisable.
        try:
            json.dumps(output)
            return output
        except (TypeError, ValueError):
            logger.warning(
                "Non-serializable output for checkpoint — converted to string: %s",
                type(output),
            )
            return {k: str(v) for k, v in output.items()} | {
                "_serialization_degraded": True
            }
