#!/usr/bin/env python3
"""
Working Complex Cyclic Workflow - Demonstrates full enterprise features
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Add examples directory
examples_dir = project_root / "examples"
sys.path.insert(0, str(examples_dir))

from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.writers import JSONWriterNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow

from examples.utils.paths import get_data_dir

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class EnterpriseOptimizerNode(CycleAwareNode):
    """Enterprise optimizer with full complexity."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "metrics": NodeParameter(
                name="metrics", type=dict, required=False, default={}
            ),
            "targets": NodeParameter(
                name="targets", type=dict, required=False, default={}
            ),
            "learning_rate": NodeParameter(
                name="learning_rate", type=float, required=False, default=0.1
            ),
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Optimize metrics with business logic."""
        # Get iteration from context
        iteration = self.get_iteration(context)
        is_first = self.is_first_iteration(context)

        # Get parameters
        metrics = kwargs.get("metrics", {})
        targets = kwargs.get("targets", {})
        learning_rate = kwargs.get("learning_rate", 0.05)  # Slower learning

        # Adaptive learning rate based on iteration
        adaptive_rate = learning_rate * max(0.1, 1 - iteration / 50)

        # Initialize metrics on first iteration
        if is_first or not metrics:
            metrics = {
                "efficiency": 0.5,
                "quality": 0.6,
                "cost": 150.0,
                "performance": 0.4,
            }
            targets = targets or {
                "efficiency": 0.95,
                "quality": 0.98,
                "cost": 50.0,
                "performance": 0.9,
            }
            self.log_cycle_info(context, "Initialized enterprise metrics")

        # Optimize each metric
        optimized = {}
        for metric, value in metrics.items():
            target = targets.get(metric, value)

            if metric == "cost":  # Minimize cost
                new_value = max(target, value * (1 - adaptive_rate))
            else:  # Maximize others
                new_value = min(target, value + adaptive_rate * (target - value))

            optimized[metric] = new_value

        # Calculate optimization score
        score = 0.0
        for metric, value in optimized.items():
            target = targets.get(metric, value)
            if metric == "cost":
                # For cost, lower is better
                metric_score = min(1.0, target / value) if value > 0 else 0
            else:
                # For others, higher is better
                metric_score = min(1.0, value / target) if target > 0 else 0
            score += metric_score / len(optimized)

        # Log metric details for debugging
        if iteration % 5 == 0:
            self.log_cycle_info(
                context,
                f"Metrics: eff={optimized['efficiency']:.3f}, qual={optimized['quality']:.3f}, "
                f"cost=${optimized['cost']:.2f}, perf={optimized['performance']:.3f}",
            )

        # Calculate business value
        business_value = (
            optimized["efficiency"] * 100000
            + optimized["quality"] * 50000
            + (150 - optimized["cost"]) * 1000
            + optimized["performance"] * 75000
        )

        # Track history
        score_history = self.accumulate_values(context, "score_history", score)

        # Check convergence
        converged = score >= 0.95 or iteration >= 20

        self.log_cycle_info(
            context,
            f"Iteration {iteration}: Score={score:.3f}, Value=${business_value:,.2f}, Converged={converged}",
        )

        # Return complete state
        return {
            "metrics": optimized,
            "score": score,
            "converged": converged,
            "iteration": iteration,
            "business_value": business_value,
            "score_history": score_history[-5:],  # Last 5 for display
            **self.set_cycle_state(
                {
                    "score_history": score_history,
                    "best_score": max(score_history) if score_history else score,
                }
            ),
        }


def create_working_complex_workflow() -> Workflow:
    """Create a working complex cyclic workflow."""

    workflow = Workflow(
        workflow_id=f"working_complex_cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        name="Working Complex Enterprise Cycle",
        description="Demonstrates all enterprise cycle features",
    )

    # Create nodes
    optimizer = EnterpriseOptimizerNode(name="optimizer")

    # Convergence analyzer
    def analyze_convergence(
        metrics: Dict[str, Any] = None,
        score: float = 0.0,
        converged: bool = False,
        iteration: int = 0,
        business_value: float = 0.0,
        score_history: list = None,
    ) -> Dict[str, Any]:
        """Analyze convergence with predictions."""
        if metrics is None:
            metrics = {}
        if score_history is None:
            score_history = []

        # Predict iterations to convergence
        predicted_iterations = 0
        if len(score_history) > 2 and score < 0.95:
            recent_improvement = (
                score_history[-1] - score_history[-3] if len(score_history) > 2 else 0.1
            )
            if recent_improvement > 0:
                predicted_iterations = int((0.95 - score) / (recent_improvement / 3))

        # Confidence calculation
        confidence = (
            min(0.99, score * len(score_history) / 20) if score_history else 0.0
        )

        logger.info(
            f"[Analysis] Score={score:.3f}, Predicted remaining={predicted_iterations}, "
            f"Confidence={confidence:.2%}"
        )

        return {
            "metrics": metrics,
            "score": score,
            "converged": converged,
            "iteration": iteration,
            "business_value": business_value,
            "analysis": {
                "predicted_iterations": predicted_iterations,
                "confidence": confidence,
                "trend": (
                    "improving"
                    if len(score_history) > 1 and score_history[-1] > score_history[-2]
                    else "stable"
                ),
            },
        }

    analyzer = PythonCodeNode.from_function(name="analyzer", func=analyze_convergence)

    # Package for switch
    def package_for_switch(
        metrics: Dict[str, Any] = None,
        score: float = 0.0,
        converged: bool = False,
        iteration: int = 0,
        business_value: float = 0.0,
        analysis: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Package data for switch node."""
        logger.info(
            f"[Packager] Packaging iteration {iteration}: converged={converged}"
        )

        return {
            "switch_input": {
                "converged": converged,
                "metrics": metrics or {},
                "score": score,
                "iteration": iteration,
                "business_value": business_value,
                "analysis": analysis or {},
            }
        }

    packager = PythonCodeNode.from_function(name="packager", func=package_for_switch)

    # Switch node
    switch = SwitchNode(
        name="switch", condition_field="converged", operator="==", value=True
    )

    # Final aggregator
    def aggregate_final_results(data: Dict[str, Any]) -> Dict[str, Any]:
        """Aggregate final results."""
        return {
            "optimization_complete": True,
            "final_metrics": data.get("metrics", {}),
            "final_score": data.get("score", 0),
            "total_iterations": data.get("iteration", 0),
            "total_business_value": data.get("business_value", 0),
            "convergence_analysis": data.get("analysis", {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    aggregator = PythonCodeNode.from_function(
        name="aggregator", func=aggregate_final_results
    )

    # Writer
    writer = JSONWriterNode(
        name="writer",
        file_path=str(get_data_dir() / "working_complex_cycle_results.json"),
    )

    # Add all nodes
    workflow.add_node("optimizer", optimizer)
    workflow.add_node("analyzer", analyzer)
    workflow.add_node("packager", packager)
    workflow.add_node("switch", switch)
    workflow.add_node("aggregator", aggregator)
    workflow.add_node("writer", writer)

    # Connect workflow
    workflow.connect(
        "optimizer",
        "analyzer",
        {
            "metrics": "metrics",
            "score": "score",
            "converged": "converged",
            "iteration": "iteration",
            "business_value": "business_value",
            "score_history": "score_history",
        },
    )

    workflow.connect(
        "analyzer",
        "packager",
        {
            "result.metrics": "metrics",
            "result.score": "score",
            "result.converged": "converged",
            "result.iteration": "iteration",
            "result.business_value": "business_value",
            "result.analysis": "analysis",
        },
    )

    workflow.connect("packager", "switch", {"result.switch_input": "input_data"})

    # Exit when converged
    workflow.connect(
        "switch", "aggregator", condition="true_output", mapping={"true_output": "data"}
    )

    workflow.connect("aggregator", "writer", {"result": "data"})

    # Build workflow first, then create cycle
    built_workflow = workflow.build()
    cycle_builder = built_workflow.create_cycle("optimization_cycle")
    cycle_builder.connect(
        "switch",
        "optimizer",
        condition="false_output",
        mapping={"false_output.metrics": "metrics"},
    )
    cycle_builder.max_iterations(25)
    cycle_builder.converge_when("score >= 0.95")
    cycle_builder.build()

    return built_workflow


def run_working_example():
    """Run the working complex example."""
    logger.info("=" * 80)
    logger.info("WORKING COMPLEX ENTERPRISE CYCLIC WORKFLOW")
    logger.info("=" * 80)

    # Create workflow
    workflow = create_working_complex_workflow()

    # Execute
    runtime = LocalRuntime(debug=False, enable_cycles=True, enable_monitoring=True)

    logger.info("Executing complex cyclic workflow...")
    results, _ = runtime.execute(workflow)

    # Display results
    if "writer" in results:
        result_path = get_data_dir() / "working_complex_cycle_results.json"
        if result_path.exists():
            with open(result_path) as f:
                final_results = json.load(f)

                logger.info("\n📊 FINAL RESULTS:")
                logger.info("-" * 50)
                logger.info(
                    f"Optimization Complete: {final_results.get('optimization_complete')}"
                )
                logger.info(
                    f"Total Iterations: {final_results.get('total_iterations')}"
                )
                logger.info(f"Final Score: {final_results.get('final_score', 0):.3f}")
                logger.info(
                    f"Business Value: ${final_results.get('total_business_value', 0):,.2f}"
                )

                logger.info("\n📈 Final Metrics:")
                for metric, value in final_results.get("final_metrics", {}).items():
                    if isinstance(value, float):
                        logger.info(f"  {metric}: {value:.3f}")

                analysis = final_results.get("convergence_analysis", {})
                logger.info("\n🎯 Convergence Analysis:")
                logger.info(f"  Confidence: {analysis.get('confidence', 0):.2%}")
                logger.info(f"  Trend: {analysis.get('trend', 'unknown')}")

        logger.info("\n✅ Complex cyclic workflow completed successfully!")

        logger.info("\n💡 Key Features Demonstrated:")
        logger.info("  - CycleAwareNode with state preservation")
        logger.info("  - Multi-node cycles with proper parameter flow")
        logger.info("  - Business value tracking per iteration")
        logger.info("  - Convergence prediction and analysis")
        logger.info("  - SwitchNode for conditional cycle exit")
        logger.info("  - Complete enterprise optimization pattern")


if __name__ == "__main__":
    try:
        run_working_example()
    except Exception as e:
        logger.error(f"Example failed: {str(e)}")
        import traceback

        traceback.print_exc()
