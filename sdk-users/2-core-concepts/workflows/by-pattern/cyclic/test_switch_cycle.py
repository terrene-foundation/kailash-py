#!/usr/bin/env python3
"""
Test cycle with switch node to understand the pattern
"""

import sys
from pathlib import Path
from typing import Any, Dict

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow


class OptimizerNode(Node):
    """Optimizer that improves score each iteration."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "score": NodeParameter(
                name="score", type=float, required=False, default=0.5
            ),
            "improvement_rate": NodeParameter(
                name="improvement_rate", type=float, required=False, default=0.1
            ),
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        score = kwargs.get("score", 0.5)
        rate = kwargs.get("improvement_rate", 0.1)

        # Get cycle info
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Improve score
        new_score = min(1.0, score + rate)
        converged = new_score >= 0.9

        print(
            f"[Iteration {iteration}] Score: {score:.3f} → {new_score:.3f}, Converged: {converged}"
        )

        return {
            "score": new_score,
            "converged": converged,
            "iteration": iteration,
            "data": {"score": new_score, "iteration": iteration},
        }


def test_switch_cycle():
    """Test cycle with switch node."""
    workflow = Workflow("switch_test", "Switch Cycle Test")

    # Add nodes
    optimizer = OptimizerNode(name="optimizer")

    # Package the data for switch
    def package_for_switch(
        score: float = 0.5,
        converged: bool = False,
        iteration: int = 0,
        data: Dict = None,
    ) -> Dict[str, Any]:
        """Package data for switch node."""
        return {
            "switch_input": {
                "converged": converged,
                "score": score,
                "iteration": iteration,
                "data": data or {},
            }
        }

    packager = PythonCodeNode.from_function(name="packager", func=package_for_switch)

    switch = SwitchNode(
        name="switch", condition_field="converged", operator="==", value=True
    )

    # Final processor
    def process_final(data: Dict[str, Any]) -> Dict[str, Any]:
        """Process final converged data."""
        return {
            "final_score": data.get("score", 0),
            "total_iterations": data.get("iteration", 0),
            "status": "complete",
        }

    final_processor = PythonCodeNode.from_function(name="final", func=process_final)

    # Add all nodes
    workflow.add_node("optimizer", optimizer)
    workflow.add_node("packager", packager)
    workflow.add_node("switch", switch)
    workflow.add_node("final", final_processor)

    # Connect nodes
    workflow.connect(
        "optimizer",
        "packager",
        {
            "score": "score",
            "converged": "converged",
            "iteration": "iteration",
            "data": "data",
        },
    )

    workflow.connect("packager", "switch", {"result.switch_input": "input_data"})

    # Set up forward connections for conditional routing
    workflow.connect(
        "switch",
        "optimizer",
        condition="false_output",
        mapping={"false_output.score": "score"},
    )
    workflow.connect(
        "switch", "final", condition="true_output", mapping={"true_output": "data"}
    )

    # Create cycle for the retry path back to start
    workflow.create_cycle("switch_cycle").connect(
        "optimizer",
        "packager",
        mapping={
            "score": "score",
            "converged": "converged",
            "iteration": "iteration",
            "data": "data",
        },
    ).max_iterations(10).converge_when("converged == True").build()

    # Execute
    runtime = LocalRuntime(enable_cycles=True)
    results, _ = runtime.execute(
        workflow, parameters={"optimizer": {"score": 0.5, "improvement_rate": 0.15}}
    )

    print(f"\nFinal results: {results}")
    return results


if __name__ == "__main__":
    test_switch_cycle()
