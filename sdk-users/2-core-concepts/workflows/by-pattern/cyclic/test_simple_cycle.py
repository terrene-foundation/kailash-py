#!/usr/bin/env python3
"""
Test simple cycle to understand the pattern
"""

import sys
from pathlib import Path
from typing import Any, Dict

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow


class SimpleCounterNode(Node):
    """Simple counter that increments and tracks convergence."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "count": NodeParameter(name="count", type=int, required=False, default=0),
            "target": NodeParameter(name="target", type=int, required=False, default=5),
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        count = kwargs.get("count", 0)
        target = kwargs.get("target", 5)

        # Get cycle info
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Increment
        new_count = count + 1
        converged = new_count >= target

        print(
            f"[Iteration {iteration}] Count: {count} → {new_count}, Target: {target}, Converged: {converged}"
        )

        return {"count": new_count, "converged": converged, "iteration": iteration}


def test_simple_cycle():
    """Test simple self-loop cycle."""
    workflow = Workflow("simple_test", "Simple Cycle Test")

    # Add node
    counter = SimpleCounterNode(name="counter")
    workflow.add_node("counter", counter)

    # Create cycle using CycleBuilder API
    workflow.create_cycle("simple_cycle").connect(
        "counter", "counter", mapping={"count": "count"}
    ).max_iterations(10).converge_when("count >= 5").build()

    # Execute
    runtime = LocalRuntime(enable_cycles=True)
    results, _ = runtime.execute(
        workflow, parameters={"counter": {"count": 0, "target": 5}}
    )

    print(f"\nFinal result: {results}")
    return results


if __name__ == "__main__":
    test_simple_cycle()
