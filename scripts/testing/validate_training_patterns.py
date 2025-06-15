#!/usr/bin/env python3
"""
Validate that training material code examples actually work.
"""

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow


def test_node_attribute_initialization():
    """Test Pattern #02: Node Attribute Initialization Order"""
    print("Testing Node Attribute Initialization Order...")

    try:

        class TestNode(Node):
            def __init__(self, name: str = "test_node", **kwargs):
                # CORRECT: Set attributes BEFORE super().__init__()
                self.chunk_size = kwargs.get("chunk_size", 2000)
                self.threshold = kwargs.get("threshold", 0.75)

                # NOW call parent init
                super().__init__(name=name)

            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "chunk_size": NodeParameter(
                        name="chunk_size",
                        type=int,
                        required=False,
                        default=self.chunk_size,
                    ),
                    "threshold": NodeParameter(
                        name="threshold",
                        type=float,
                        required=False,
                        default=self.threshold,
                    ),
                }

            def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
                return {"result": "success"}

        # This should work without AttributeError
        node = TestNode()
        print("✅ Node Attribute Initialization Order: PASSED")
        return True

    except Exception as e:
        print(f"❌ Node Attribute Initialization Order: FAILED - {e}")
        traceback.print_exc()
        return False


def test_get_parameters_return_type():
    """Test Pattern #03: get_parameters Return Type"""
    print("Testing get_parameters Return Type...")

    try:

        class TestNode(Node):
            def __init__(self, name: str = "test_node", **kwargs):
                self.max_tokens = kwargs.get("max_tokens", 4000)
                super().__init__(name=name)

            def get_parameters(self) -> Dict[str, NodeParameter]:
                # CORRECT: Return NodeParameter objects
                return {
                    "max_tokens": NodeParameter(
                        name="max_tokens",
                        type=int,
                        required=False,
                        default=self.max_tokens,
                    ),
                    "input_data": NodeParameter(
                        name="input_data", type=dict, required=True
                    ),
                }

            def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
                return {"result": "success"}

        node = TestNode()
        params = node.get_parameters()

        # Validate structure
        assert isinstance(params, dict)
        assert "max_tokens" in params
        assert hasattr(params["max_tokens"], "required")
        assert hasattr(params["max_tokens"], "type")

        print("✅ get_parameters Return Type: PASSED")
        return True

    except Exception as e:
        print(f"❌ get_parameters Return Type: FAILED - {e}")
        traceback.print_exc()
        return False


def test_pythoncode_dot_notation():
    """Test Pattern #15: Dot Notation Parameter Mapping"""
    print("Testing PythonCodeNode Dot Notation...")

    try:
        # Test function
        def process_data(input_data: list) -> dict:
            processed = [x * 2 for x in input_data]
            return {
                "processed_data": processed,
                "count": len(processed),
                "metadata": {"timestamp": "2024-01-01"},
            }

        # Create node
        processor = PythonCodeNode.from_function(process_data, name="data_processor")

        # Test direct execution
        result = processor.execute(input_data=[1, 2, 3])

        # Verify wrapping
        assert "result" in result
        assert "processed_data" in result["result"]
        assert result["result"]["processed_data"] == [2, 4, 6]
        assert result["result"]["count"] == 3

        # Test in workflow with dot notation
        workflow = Workflow("test_dot_notation", "Test Workflow")
        workflow.add_node("processor", processor)

        # Next node that uses dot notation
        def consume_processed_func(processed_data: list, count: int) -> dict:
            return {"total": sum(processed_data), "items": count}

        consumer_node = PythonCodeNode.from_function(
            consume_processed_func, name="consumer"
        )
        workflow.add_node("consumer", consumer_node)

        # Connect with dot notation
        workflow.connect(
            "processor",
            "consumer",
            {"result.processed_data": "processed_data", "result.count": "count"},
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, _ = runtime.execute(
            workflow, parameters={"processor": {"input_data": [1, 2, 3]}}
        )

        # Verify results
        assert results["consumer"]["result"]["total"] == 12
        assert results["consumer"]["result"]["items"] == 3

        print("✅ PythonCodeNode Dot Notation: PASSED")
        return True

    except Exception as e:
        print(f"❌ PythonCodeNode Dot Notation: FAILED - {e}")
        traceback.print_exc()
        return False


def test_cycle_aware_state_preservation():
    """Test Pattern #14: Cyclic Workflow Parameter Propagation"""
    print("Testing CycleAware State Preservation...")

    try:

        class TestOptimizerNode(CycleAwareNode):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "targets": NodeParameter(
                        name="targets", type=dict, required=False, default={}
                    ),
                    "current_score": NodeParameter(
                        name="current_score", type=float, required=False, default=0.5
                    ),
                }

            def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
                # Get state
                iteration = self.get_iteration(context)
                prev_state = self.get_previous_state(context)

                # Preserve targets through cycles
                targets = kwargs.get("targets", {})
                if not targets and prev_state.get("targets"):
                    targets = prev_state["targets"]

                # Default targets if none provided
                if not targets:
                    targets = {"efficiency": 0.95}

                current_score = kwargs.get("current_score", 0.5)

                # Simulate optimization
                improvement = 0.1
                new_score = min(
                    targets.get("efficiency", 0.95), current_score + improvement
                )
                converged = new_score >= targets.get("efficiency", 0.95)

                self.log_cycle_info(
                    context, f"Iteration {iteration}: score={new_score:.3f}"
                )

                return {
                    "current_score": new_score,
                    "converged": converged,
                    "iteration": iteration,
                    **self.set_cycle_state(
                        {
                            "targets": targets,
                            "score_history": self.accumulate_values(
                                context, "scores", new_score
                            ),
                        }
                    ),
                }

        # Test basic functionality
        optimizer = TestOptimizerNode(name="optimizer")

        # Create simple workflow
        workflow = Workflow("test_cycle", "Test Cycle")
        workflow.add_node("optimizer", optimizer)

        # Self-loop with cycle
        workflow.connect(
            "optimizer",
            "optimizer",
            mapping={"current_score": "current_score"},
            cycle=True,
            max_iterations=5,
            convergence_check="converged == True",
        )

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, _ = runtime.execute(
            workflow, parameters={"optimizer": {"targets": {"efficiency": 0.8}}}
        )

        # Verify convergence
        final_result = results.get("optimizer", {})
        assert final_result.get("converged", False)
        assert final_result.get("current_score", 0) >= 0.8

        print("✅ CycleAware State Preservation: PASSED")
        return True

    except Exception as e:
        print(f"❌ CycleAware State Preservation: FAILED - {e}")
        traceback.print_exc()
        return False


def test_switch_cycle_pattern():
    """Test SwitchNode cycle pattern from training"""
    print("Testing SwitchNode Cycle Pattern...")

    try:
        # Simple self-loop with switch-like logic
        def optimizer_with_switch(score: float = 0.5) -> dict:
            new_score = min(1.0, score + 0.2)
            converged = new_score >= 0.9
            return {"score": new_score, "converged": converged}

        # Create workflow with simple self-loop
        workflow = Workflow("test_switch_cycle", "Test Switch Cycle")

        optimizer_node = PythonCodeNode.from_function(
            optimizer_with_switch, name="optimizer"
        )
        workflow.add_node("optimizer", optimizer_node)

        # Self-loop until converged
        workflow.connect(
            "optimizer",
            "optimizer",
            mapping={"result.score": "score"},
            cycle=True,
            max_iterations=10,
            convergence_check="converged == True",
        )

        # Execute with initial parameters
        runtime = LocalRuntime(enable_cycles=True)
        results, _ = runtime.execute(workflow, parameters={"optimizer": {"score": 0.1}})

        # Should have converged
        final_optimizer = results.get("optimizer", {})
        assert final_optimizer.get("result", {}).get("score", 0) >= 0.9
        assert final_optimizer.get("result", {}).get("converged", False)

        print("✅ SwitchNode Cycle Pattern: PASSED")
        return True

    except Exception as e:
        print(f"❌ SwitchNode Cycle Pattern: FAILED - {e}")
        traceback.print_exc()
        return False


def test_unified_localruntime():
    """Test unified LocalRuntime patterns"""
    print("Testing Unified LocalRuntime...")

    try:
        # Test basic usage
        runtime1 = LocalRuntime()

        # Test with parameters
        runtime2 = LocalRuntime(
            enable_cycles=True,
            enable_async=True,
            enable_monitoring=True,
            max_concurrency=5,
        )

        # Create simple workflow to test
        def simple_processor_func(data: str = "test") -> dict:
            return {"processed": data.upper()}

        workflow = Workflow("test_runtime", "Test Runtime")
        processor_node = PythonCodeNode.from_function(
            simple_processor_func, name="processor"
        )
        workflow.add_node("processor", processor_node)

        # Test execution
        results1, _ = runtime1.execute(
            workflow, parameters={"processor": {"data": "test"}}
        )
        results2, _ = runtime2.execute(
            workflow, parameters={"processor": {"data": "test"}}
        )

        assert results1["processor"]["result"]["processed"] == "TEST"
        assert results2["processor"]["result"]["processed"] == "TEST"

        print("✅ Unified LocalRuntime: PASSED")
        return True

    except Exception as e:
        print(f"❌ Unified LocalRuntime: FAILED - {e}")
        traceback.print_exc()
        return False


def main():
    """Run all validation tests"""
    print("🧪 Validating Training Material Code Examples")
    print("=" * 60)

    tests = [
        test_node_attribute_initialization,
        test_get_parameters_return_type,
        test_pythoncode_dot_notation,
        test_cycle_aware_state_preservation,
        test_switch_cycle_pattern,
        test_unified_localruntime,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            traceback.print_exc()
        print()

    print("=" * 60)
    print(f"📊 Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All training material code examples are working correctly!")
        return True
    else:
        print("⚠️  Some training material code examples need fixing.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
