#!/usr/bin/env python3
"""
Final Working Enterprise Cyclic Workflow - Complete Demonstration
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

examples_dir = project_root / "examples"
sys.path.insert(0, str(examples_dir))

from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow

from examples.utils.paths import get_data_dir

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class EnterpriseOptimizationNode(Node):
    """Complete enterprise optimization node with business logic."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "efficiency": NodeParameter(
                name="efficiency", type=float, required=False, default=0.5
            ),
            "quality": NodeParameter(
                name="quality", type=float, required=False, default=0.6
            ),
            "cost": NodeParameter(
                name="cost", type=float, required=False, default=150.0
            ),
            "performance": NodeParameter(
                name="performance", type=float, required=False, default=0.4
            ),
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Run optimization iteration."""
        # Get cycle info
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Get current metrics
        efficiency = kwargs.get("efficiency", 0.5)
        quality = kwargs.get("quality", 0.6)
        cost = kwargs.get("cost", 150.0)
        performance = kwargs.get("performance", 0.4)

        # Define targets
        targets = {
            "efficiency": 0.95,
            "quality": 0.98,
            "cost": 50.0,
            "performance": 0.9,
        }

        # Optimization step size (smaller = more iterations)
        step_size = 0.08

        # Optimize each metric
        new_efficiency = min(
            targets["efficiency"],
            efficiency + step_size * (targets["efficiency"] - efficiency),
        )
        new_quality = min(
            targets["quality"], quality + step_size * (targets["quality"] - quality)
        )
        new_cost = max(targets["cost"], cost - step_size * (cost - targets["cost"]))
        new_performance = min(
            targets["performance"],
            performance + step_size * (targets["performance"] - performance),
        )

        # Calculate score
        score = (
            (new_efficiency / targets["efficiency"])
            + (new_quality / targets["quality"])
            + (targets["cost"] / new_cost)
            + (new_performance / targets["performance"])
        ) / 4

        # Business value calculation
        business_value = (
            new_efficiency * 100000
            + new_quality * 50000
            + (150 - new_cost) * 1000
            + new_performance * 75000
        )

        # Check convergence
        converged = score >= 0.95 or iteration >= 20

        logger.info(
            f"Iteration {iteration}: Score={score:.3f}, BizValue=${business_value:,.2f} | "
            f"Eff={new_efficiency:.3f}, Qual={new_quality:.3f}, Cost=${new_cost:.2f}, Perf={new_performance:.3f}"
        )

        return {
            "efficiency": new_efficiency,
            "quality": new_quality,
            "cost": new_cost,
            "performance": new_performance,
            "score": score,
            "business_value": business_value,
            "iteration": iteration,
            "converged": converged,
        }


def create_final_cyclic_workflow() -> Workflow:
    """Create the final working cyclic workflow."""

    workflow = Workflow(
        workflow_id=f"final_cyclic_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        name="Final Enterprise Cyclic Workflow",
        description="Complete working demonstration of enterprise cyclic optimization",
    )

    # Single optimization node with self-loop
    optimizer = EnterpriseOptimizationNode(name="optimizer")
    workflow.add_node("optimizer", optimizer)

    # Create cycle using CycleBuilder API (direct chaining for Workflow class)
    workflow.create_cycle("final_optimization_cycle").connect(
        "optimizer",
        "optimizer",
        mapping={
            "efficiency": "efficiency",
            "quality": "quality",
            "cost": "cost",
            "performance": "performance",
        },
    ).max_iterations(25).converge_when("score >= 0.90").build()

    return workflow


def run_final_demonstration():
    """Run the final cyclic workflow demonstration."""
    logger.info("=" * 80)
    logger.info("FINAL ENTERPRISE CYCLIC WORKFLOW DEMONSTRATION")
    logger.info("=" * 80)
    logger.info("")
    logger.info("This demonstrates:")
    logger.info("- Multi-metric optimization over iterations")
    logger.info("- Business value calculation per cycle")
    logger.info("- Convergence detection with score threshold")
    logger.info("- Parameter propagation through cycles")
    logger.info("")

    # Create and execute workflow
    workflow = create_final_cyclic_workflow()

    runtime = LocalRuntime(debug=False, enable_cycles=True, enable_monitoring=True)

    logger.info("Starting cyclic optimization...")
    logger.info("-" * 80)

    results, _ = runtime.execute(workflow)

    # Display final results
    logger.info("-" * 80)
    logger.info("\n📊 FINAL RESULTS:")

    final = results.get("optimizer", {})
    logger.info(f"  Total Iterations: {final.get('iteration', 0) + 1}")
    logger.info(f"  Final Score: {final.get('score', 0):.3f}")
    logger.info(f"  Business Value: ${final.get('business_value', 0):,.2f}")
    logger.info(f"  Converged: {final.get('converged', False)}")

    logger.info("\n📈 Final Metrics:")
    logger.info(f"  Efficiency: {final.get('efficiency', 0):.3f} (target: 0.95)")
    logger.info(f"  Quality: {final.get('quality', 0):.3f} (target: 0.98)")
    logger.info(f"  Cost: ${final.get('cost', 0):.2f} (target: $50)")
    logger.info(f"  Performance: {final.get('performance', 0):.3f} (target: 0.90)")

    # Save results
    output_path = get_data_dir() / "final_cyclic_results.json"
    with open(output_path, "w") as f:
        json.dump(
            {
                "workflow_id": workflow.workflow_id,
                "execution_time": datetime.now(timezone.utc).isoformat(),
                "final_results": final,
                "features_demonstrated": [
                    "Self-loop cycles with convergence",
                    "Multi-metric optimization",
                    "Business value tracking",
                    "Parameter propagation",
                    "Convergence detection",
                ],
            },
            f,
            indent=2,
        )

    logger.info(f"\n💾 Results saved to: {output_path}")

    logger.info("\n✅ Cyclic workflow demonstration complete!")
    logger.info("\n💡 Key Takeaways:")
    logger.info("  - Cycles enable iterative optimization")
    logger.info("  - Parameters flow seamlessly between iterations")
    logger.info("  - Business metrics tracked throughout")
    logger.info("  - Convergence criteria stop unnecessary iterations")
    logger.info("  - Enterprise-ready for production use")


if __name__ == "__main__":
    try:
        run_final_demonstration()
    except Exception as e:
        logger.error(f"Demonstration failed: {str(e)}")
        import traceback

        traceback.print_exc()
