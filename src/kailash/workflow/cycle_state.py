"""Cycle state management for workflow iterations."""

import logging
import time
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class CycleState:
    """Manages state across cycle iterations."""

    def __init__(self, cycle_id: str = "default"):
        """Initialize cycle state.

        Args:
            cycle_id: Identifier for this cycle group
        """
        self.cycle_id = cycle_id
        self.iteration = 0
        self.history: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {}
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.node_states: dict[str, Any] = {}  # Per-node state storage

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time since cycle started."""
        return time.time() - self.start_time

    @property
    def iteration_time(self) -> float:
        """Get time since last iteration."""
        return time.time() - self.last_update_time

    def update(self, results: dict[str, Any], iteration: int | None = None) -> None:
        """Update state with iteration results.

        Args:
            results: Results from current iteration
            iteration: Optional iteration number (auto-incremented if not provided)
        """
        if iteration is not None:
            self.iteration = iteration
        else:
            self.iteration += 1

        # Record iteration history
        history_entry = {
            "iteration": self.iteration,
            "results": results,
            "timestamp": datetime.now(UTC).isoformat(),
            "elapsed_time": self.elapsed_time,
            "iteration_time": self.iteration_time,
        }
        self.history.append(history_entry)

        # Update timing
        self.last_update_time = time.time()

        # Update node states if provided
        for node_id, node_result in results.items():
            if isinstance(node_result, dict) and "_cycle_state" in node_result:
                self.node_states[node_id] = node_result["_cycle_state"]

        logger.debug(
            f"Cycle {self.cycle_id} updated: iteration={self.iteration}, "
            f"elapsed_time={self.elapsed_time:.2f}s"
        )

    def get_node_state(self, node_id: str) -> Any:
        """Get state for specific node.

        Args:
            node_id: Node identifier

        Returns:
            Node state or None if not found
        """
        return self.node_states.get(node_id)

    def set_node_state(self, node_id: str, state: Any) -> None:
        """Set state for specific node.

        Args:
            node_id: Node identifier
            state: State to store
        """
        self.node_states[node_id] = state

    def get_convergence_context(self) -> dict[str, Any]:
        """Get context for convergence evaluation.

        Returns:
            Dict with iteration info, history, and trends
        """
        context = {
            "iteration": self.iteration,
            "history": self.history,
            "elapsed_time": self.elapsed_time,
            "metadata": self.metadata,
            "node_states": self.node_states,
        }

        # Add trend analysis if we have history
        if len(self.history) >= 2:
            context["trend"] = self.calculate_trend()

        return context

    def calculate_trend(self) -> dict[str, Any]:
        """Calculate trends from iteration history.

        Returns:
            Dict with trend information
        """
        if len(self.history) < 2:
            return {}

        trends = {
            "iteration_times": [],
            "numeric_trends": {},
        }

        # Calculate iteration times
        for i in range(1, len(self.history)):
            trends["iteration_times"].append(self.history[i]["iteration_time"])

        # Find numeric values and calculate trends
        all_keys = set()
        for entry in self.history:
            all_keys.update(self._extract_numeric_keys(entry["results"]))

        for key in all_keys:
            values = []
            for entry in self.history:
                value = self._extract_value(entry["results"], key)
                if value is not None and isinstance(value, (int, float)):
                    values.append(value)

            if len(values) >= 2:
                # Calculate simple trend metrics
                trends["numeric_trends"][key] = {
                    "values": values,
                    "latest": values[-1],
                    "previous": values[-2],
                    "change": values[-1] - values[-2],
                    "change_percent": (
                        (values[-1] - values[-2]) / abs(values[-2]) * 100
                        if values[-2] != 0
                        else 0
                    ),
                    "average": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                }

        return trends

    def _extract_numeric_keys(self, obj: Any, prefix: str = "") -> list[str]:
        """Extract all numeric value keys from nested dict."""
        keys = []

        if isinstance(obj, dict):
            for key, value in obj.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, (int, float)):
                    keys.append(full_key)
                elif isinstance(value, dict):
                    keys.extend(self._extract_numeric_keys(value, full_key))

        return keys

    def _extract_value(self, obj: Any, key_path: str) -> Any:
        """Extract value from nested dict using dot notation."""
        keys = key_path.split(".")
        value = obj

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None

        return value

    def get_summary(self) -> dict[str, Any]:
        """Get summary of cycle execution.

        Returns:
            Dict with summary statistics
        """
        summary = {
            "cycle_id": self.cycle_id,
            "iterations": self.iteration,
            "elapsed_time": self.elapsed_time,
            "start_time": datetime.fromtimestamp(self.start_time, UTC).isoformat(),
            "history_length": len(self.history),
        }

        if self.history:
            summary["first_iteration"] = self.history[0]["timestamp"]
            summary["last_iteration"] = self.history[-1]["timestamp"]
            summary["average_iteration_time"] = sum(
                h.get("iteration_time", 0) for h in self.history[1:]
            ) / max(1, len(self.history) - 1)

        # Add trend summary if available
        trends = self.calculate_trend()
        if trends.get("numeric_trends"):
            summary["trends"] = {
                key: {
                    "latest": data["latest"],
                    "change": data["change"],
                    "change_percent": data["change_percent"],
                }
                for key, data in trends["numeric_trends"].items()
            }

        return summary

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dictionary.

        Returns:
            Dict representation of state
        """
        return {
            "cycle_id": self.cycle_id,
            "iteration": self.iteration,
            "history": self.history,
            "metadata": self.metadata,
            "start_time": self.start_time,
            "last_update_time": self.last_update_time,
            "node_states": self.node_states,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CycleState":
        """Create CycleState from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            CycleState instance
        """
        state = cls(data.get("cycle_id", "default"))
        state.iteration = data.get("iteration", 0)
        state.history = data.get("history", [])
        state.metadata = data.get("metadata", {})
        state.start_time = data.get("start_time", time.time())
        state.last_update_time = data.get("last_update_time", state.start_time)
        state.node_states = data.get("node_states", {})
        return state


class CycleStateManager:
    """Manages multiple cycle states for nested cycles."""

    def __init__(self):
        """Initialize cycle state manager."""
        self.states: dict[str, CycleState] = {}
        self.active_cycles: list[str] = []

    def get_or_create_state(self, cycle_id: str) -> CycleState:
        """Get existing state or create new one.

        Args:
            cycle_id: Cycle identifier

        Returns:
            CycleState instance
        """
        if cycle_id not in self.states:
            self.states[cycle_id] = CycleState(cycle_id)
            logger.info(f"Created new cycle state for: {cycle_id}")

        return self.states[cycle_id]

    def push_cycle(self, cycle_id: str) -> None:
        """Push cycle onto active stack (for nested cycles).

        Args:
            cycle_id: Cycle identifier
        """
        self.active_cycles.append(cycle_id)
        logger.debug(f"Pushed cycle: {cycle_id}, stack: {self.active_cycles}")

    def pop_cycle(self) -> str | None:
        """Pop cycle from active stack.

        Returns:
            Popped cycle ID or None
        """
        if self.active_cycles:
            cycle_id = self.active_cycles.pop()
            logger.debug(f"Popped cycle: {cycle_id}, stack: {self.active_cycles}")
            return cycle_id
        return None

    def get_active_cycle(self) -> str | None:
        """Get currently active cycle ID.

        Returns:
            Active cycle ID or None
        """
        return self.active_cycles[-1] if self.active_cycles else None

    def get_all_summaries(self) -> dict[str, dict[str, Any]]:
        """Get summaries for all cycles.

        Returns:
            Dict mapping cycle_id to summary
        """
        return {
            cycle_id: state.get_summary() for cycle_id, state in self.states.items()
        }

    def clear(self, cycle_id: str | None = None) -> None:
        """Clear cycle state(s).

        Args:
            cycle_id: Specific cycle to clear, or None to clear all
        """
        if cycle_id:
            if cycle_id in self.states:
                del self.states[cycle_id]
                self.active_cycles = [c for c in self.active_cycles if c != cycle_id]
                logger.info(f"Cleared cycle state: {cycle_id}")
        else:
            self.states.clear()
            self.active_cycles.clear()
            logger.info("Cleared all cycle states")
