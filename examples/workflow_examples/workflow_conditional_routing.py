#!/usr/bin/env python3
"""
Conditional Routing Workflow Examples
=====================================

This example demonstrates conditional routing patterns using SwitchNode,
including the critical A → B → C → D → Switch → (B if retry | E if finish) pattern.

Examples included:
1. Simple Boolean Routing - Basic true/false branching
2. Multi-Case Status Routing - Route based on multiple status values
3. Conditional Retry Loops - Quality improvement cycles with conditional exits
4. Error Handling with Fallback Routes - Graceful error recovery
5. Data Filtering and Transformation - Route based on data characteristics

Run: python workflow_conditional_routing.py
"""

from typing import Any

from kailash import Workflow
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.logic import SwitchNode
from kailash.runtime.local import LocalRuntime

# ============================================================================
# Example Nodes for Conditional Routing
# ============================================================================


class InputNode(Node):
    """Generates initial data for processing."""

    def get_parameters(self):
        return {
            "size": NodeParameter(name="size", type=int, required=False, default=10),
            "base_quality": NodeParameter(
                name="base_quality", type=float, required=False, default=0.3
            ),
        }

    def run(self, context, **kwargs):
        size = kwargs.get("size", 10)
        base_quality = kwargs.get("base_quality", 0.3)

        # Generate test data
        data = list(range(size))

        return {"data": data, "quality": base_quality, "size": size}


class ProcessorNode(Node):
    """Processes data and improves quality iteratively."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "quality": NodeParameter(
                name="quality", type=float, required=False, default=0.0
            ),
            "increment": NodeParameter(
                name="increment", type=float, required=False, default=0.2
            ),
        }

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])
        quality = kwargs.get("quality", 0.0)
        increment = kwargs.get("increment", 0.2)

        # Get iteration info from cycle context
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Improve quality on each iteration
        new_quality = min(1.0, quality + increment)

        # Process data (simple transformation)
        processed_data = [x * (1 + iteration * 0.1) for x in data]

        print(
            f"Processor iteration {iteration}: quality {quality:.2f} → {new_quality:.2f}"
        )

        return {"data": processed_data, "quality": new_quality, "iteration": iteration}


class TransformNode(Node):
    """Transforms data format."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "quality": NodeParameter(
                name="quality", type=float, required=False, default=0.0
            ),
        }

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])
        quality = kwargs.get("quality", 0.0)

        # Simple transformation
        transformed = {"values": data, "stats": {"count": len(data), "sum": sum(data)}}

        return {"data": transformed, "quality": quality}


class QualityCheckerNode(Node):
    """Checks quality and makes routing decisions."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=Any, required=False, default={}),
            "quality": NodeParameter(
                name="quality", type=float, required=False, default=0.0
            ),
            "threshold": NodeParameter(
                name="threshold", type=float, required=False, default=0.8
            ),
        }

    def run(self, context, **kwargs):
        data = kwargs.get("data", {})
        quality = kwargs.get("quality", 0.0)
        threshold = kwargs.get("threshold", 0.8)

        # Get iteration info
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Decision logic
        quality_sufficient = quality >= threshold
        max_iterations_reached = iteration >= 5

        if quality_sufficient or max_iterations_reached:
            route_decision = "finish"
            should_continue = False
            reason = "quality_achieved" if quality_sufficient else "max_iterations"
        else:
            route_decision = "retry"
            should_continue = True
            reason = "needs_improvement"

        print(
            f"Quality check: {quality:.2f} >= {threshold} = {quality_sufficient} (iteration {iteration})"
        )
        print(f"Decision: {route_decision} ({reason})")

        return {
            "data": data,
            "quality": quality,
            "route_decision": route_decision,
            "should_continue": should_continue,
            "reason": reason,
        }


class OutputNode(Node):
    """Final output node."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=Any, required=False, default={}),
            "quality": NodeParameter(
                name="quality", type=float, required=False, default=0.0
            ),
        }

    def run(self, context, **kwargs):
        data = kwargs.get("data", {})
        quality = kwargs.get("quality", 0.0)

        return {"final_data": data, "final_quality": quality, "status": "completed"}


class ValidationNode(Node):
    """Validates data and returns boolean result."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=True),
            "threshold": NodeParameter(name="threshold", type=float, default=0.8),
        }

    def run(self, context, **kwargs):
        data = kwargs["data"]
        threshold = kwargs["threshold"]

        # Simple validation: average of data
        quality = sum(data) / len(data) if data else 0
        is_valid = quality >= threshold

        return {"data": data, "quality": quality, "is_valid": is_valid}


class SuccessHandlerNode(Node):
    """Handles successful validation."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[])
        }

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])

        return {
            "result": "success",
            "processed_data": data,
            "message": "Data validation passed",
        }


class RetryHandlerNode(Node):
    """Handles retry scenarios."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[])
        }

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])

        # Improve data for retry
        improved_data = [x * 1.1 for x in data]

        return {
            "result": "retry",
            "improved_data": improved_data,
            "message": "Data improved for retry",
        }


class StatusCheckerNode(Node):
    """Checks data size and returns status."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[])
        }

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])

        if not data:
            status = "empty"
        elif len(data) < 5:
            status = "small"
        elif len(data) < 15:
            status = "medium"
        else:
            status = "large"

        return {"data": data, "status": status}


class SimpleProcessorNode(Node):
    """Simple processor for small data."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[])
        }

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])
        return {"result": [x * 2 for x in data], "processor": "simple"}


class StandardProcessorNode(Node):
    """Standard processor for medium data."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[])
        }

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])
        return {"result": [x * 3 for x in data], "processor": "standard"}


class BatchProcessorNode(Node):
    """Batch processor for large data."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[])
        }

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])
        # Process in batches
        result = []
        for i in range(0, len(data), 5):
            batch = data[i : i + 5]
            result.extend([x * 4 for x in batch])
        return {"result": result, "processor": "batch"}


class ErrorHandlerNode(Node):
    """Handles error cases."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[])
        }

    def run(self, context, **kwargs):
        kwargs.get("data", [])
        return {"result": [], "error": "Empty data provided", "processor": "error"}


# ============================================================================
# Example 1: Simple Boolean Routing
# ============================================================================


def example1_simple_boolean_routing():
    """Demonstrates simple true/false conditional routing."""
    print("\n" + "=" * 60)
    print("EXAMPLE 1: Simple Boolean Routing")
    print("=" * 60)

    workflow = Workflow("boolean-routing", "Simple Boolean Routing Example")

    # Add nodes
    workflow.add_node("validator", ValidationNode())
    workflow.add_node(
        "switch",
        SwitchNode(
            condition_field="is_valid",
            true_route="success_handler",
            false_route="retry_handler",
        ),
    )
    workflow.add_node("success_handler", SuccessHandlerNode())
    workflow.add_node("retry_handler", RetryHandlerNode())

    # Connect nodes
    workflow.connect("validator", "switch")
    workflow.connect("switch", "success_handler", route="success_handler")
    workflow.connect("switch", "retry_handler", route="retry_handler")

    # Execute with different data to show both paths
    runtime = LocalRuntime()

    # Test 1: High quality data (should route to success)
    print("\nTest 1: High quality data")
    results, _ = runtime.execute(
        workflow, parameters={"validator": {"data": [8, 9, 10], "threshold": 0.8}}
    )
    print(
        f"Result: {results.get('success_handler', results.get('retry_handler', {})).get('result')}"
    )

    # Test 2: Low quality data (should route to retry)
    print("\nTest 2: Low quality data")
    results, _ = runtime.execute(
        workflow, parameters={"validator": {"data": [1, 2, 3], "threshold": 0.8}}
    )
    print(
        f"Result: {results.get('success_handler', results.get('retry_handler', {})).get('result')}"
    )


# ============================================================================
# Example 2: Multi-Case Status Routing
# ============================================================================


def example2_multi_case_routing():
    """Demonstrates routing based on multiple status values."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Multi-Case Status Routing")
    print("=" * 60)

    workflow = Workflow("multi-case-routing", "Multi-Case Status Routing Example")

    # Add nodes
    workflow.add_node("checker", StatusCheckerNode())
    workflow.add_node(
        "router",
        SwitchNode(
            condition_field="status",
            routes={
                "empty": "error_handler",
                "small": "simple_processor",
                "medium": "standard_processor",
                "large": "batch_processor",
            },
        ),
    )
    workflow.add_node("error_handler", ErrorHandlerNode())
    workflow.add_node("simple_processor", SimpleProcessorNode())
    workflow.add_node("standard_processor", StandardProcessorNode())
    workflow.add_node("batch_processor", BatchProcessorNode())

    # Connect nodes
    workflow.connect("checker", "router")
    workflow.connect("router", "error_handler", route="error_handler")
    workflow.connect("router", "simple_processor", route="simple_processor")
    workflow.connect("router", "standard_processor", route="standard_processor")
    workflow.connect("router", "batch_processor", route="batch_processor")

    # Test different data sizes
    runtime = LocalRuntime()
    test_cases = [
        ("Empty data", []),
        ("Small data", [1, 2, 3]),
        ("Medium data", list(range(10))),
        ("Large data", list(range(20))),
    ]

    for test_name, test_data in test_cases:
        print(f"\n{test_name}: {len(test_data)} items")
        results, _ = runtime.execute(
            workflow, parameters={"checker": {"data": test_data}}
        )

        # Find which processor was used
        for processor in [
            "error_handler",
            "simple_processor",
            "standard_processor",
            "batch_processor",
        ]:
            if processor in results:
                print(f"Routed to: {results[processor]['processor']}")
                break


# ============================================================================
# Example 3: Conditional Retry Loops (CRITICAL PATTERN)
# ============================================================================


def example3_conditional_retry_loops():
    """Demonstrates the critical A → B → C → D → Switch → (B if retry | E if finish) pattern."""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Conditional Retry Loops (CRITICAL PATTERN)")
    print("=" * 60)
    print("Pattern: A → B → C → D → Switch → (B if retry | E if finish)")

    workflow = Workflow("conditional-cycle", "Quality Improvement Loop")

    # A → B → C → D → Switch → (B if retry | E if finish)
    workflow.add_node("input", InputNode())  # A
    workflow.add_node("processor", ProcessorNode())  # B
    workflow.add_node("transformer", TransformNode())  # C
    workflow.add_node("checker", QualityCheckerNode())  # D
    workflow.add_node(
        "switch",
        SwitchNode(
            condition_field="route_decision",
            routes={
                "retry": "processor",  # Back to B
                "finish": "output",  # Continue to E
            },
        ),
    )
    workflow.add_node("output", OutputNode())  # E

    # Linear flow: A → B → C → D → Switch
    workflow.connect("input", "processor")
    workflow.connect(
        "processor", "transformer", mapping={"data": "data", "quality": "quality"}
    )
    workflow.connect(
        "transformer", "checker", mapping={"data": "data", "quality": "quality"}
    )
    workflow.connect(
        "checker",
        "switch",
        mapping={
            "data": "data",
            "quality": "quality",
            "route_decision": "route_decision",
            "should_continue": "should_continue",
        },
    )

    # Conditional routing from switch
    workflow.connect(
        "switch",
        "processor",  # Cycle back to B
        route="retry",
        mapping={"data": "data", "quality": "quality"},
        cycle=True,
        max_iterations=10,
        convergence_check="should_continue == False",
    )

    workflow.connect(
        "switch",
        "output",  # Continue to E
        route="finish",
        mapping={"data": "data", "quality": "quality"},
    )

    # Execute the conditional cycle
    runtime = LocalRuntime()

    print("\nExecuting quality improvement cycle...")
    print("Will iterate until quality >= 0.8 or max 10 iterations")

    results, _ = runtime.execute(
        workflow,
        parameters={
            "input": {"size": 5, "base_quality": 0.3},
            "checker": {"threshold": 0.8},
        },
    )

    # Check results
    if "output" in results:
        output = results["output"]
        print("\n✅ CYCLE COMPLETED")
        print(f"Final quality: {output['final_quality']:.2f}")
        print(f"Status: {output['status']}")
        print(f"Data processed: {len(output['final_data'].get('values', []))} items")
    else:
        print("\n❌ CYCLE FAILED")
        print(f"Available results: {list(results.keys())}")


# ============================================================================
# Example 4: Error Handling with Fallback Routes
# ============================================================================


def example4_error_handling():
    """Demonstrates error handling with fallback routing."""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Error Handling with Fallback Routes")
    print("=" * 60)

    class SafeProcessorNode(Node):
        def get_parameters(self):
            return {
                "data": NodeParameter(
                    name="data", type=list, required=False, default=[]
                )
            }

        def run(self, context, **kwargs):
            data = kwargs.get("data", [])

            try:
                # Attempt complex processing (will fail for certain data)
                if not data or sum(data) < 10:
                    raise ValueError("Insufficient data for complex processing")

                result = [x * 2.5 for x in data]
                return {"data": result, "status": "success"}
            except Exception as e:
                # Fallback to simple processing
                simple_result = [x for x in data] if data else [0]
                return {"data": simple_result, "status": "fallback", "error": str(e)}

    class SuccessPathNode(Node):
        def get_parameters(self):
            return {
                "data": NodeParameter(
                    name="data", type=list, required=False, default=[]
                )
            }

        def run(self, context, **kwargs):
            data = kwargs.get("data", [])
            return {"result": "Complex processing succeeded", "final_data": data}

    class ErrorRecoveryNode(Node):
        def get_parameters(self):
            return {
                "data": NodeParameter(
                    name="data", type=list, required=False, default=[]
                ),
                "error": NodeParameter(
                    name="error", type=str, required=False, default=""
                ),
            }

        def run(self, context, **kwargs):
            data = kwargs.get("data", [])
            error = kwargs.get("error", "")
            return {
                "result": "Fallback processing used",
                "final_data": data,
                "original_error": error,
            }

    workflow = Workflow("error-handling", "Error Handling with Fallback")

    # Add nodes
    workflow.add_node("processor", SafeProcessorNode())
    workflow.add_node(
        "status_check",
        SwitchNode(
            condition_field="status",
            routes={"success": "success_path", "fallback": "error_recovery"},
        ),
    )
    workflow.add_node("success_path", SuccessPathNode())
    workflow.add_node("error_recovery", ErrorRecoveryNode())

    # Connect nodes
    workflow.connect("processor", "status_check")
    workflow.connect("status_check", "success_path", route="success_path")
    workflow.connect("status_check", "error_recovery", route="error_recovery")

    # Test both success and fallback scenarios
    runtime = LocalRuntime()

    # Test 1: Sufficient data (should succeed)
    print("\nTest 1: Sufficient data for complex processing")
    results, _ = runtime.execute(
        workflow, parameters={"processor": {"data": [5, 6, 7, 8]}}
    )

    if "success_path" in results:
        print(f"✅ Success: {results['success_path']['result']}")
    elif "error_recovery" in results:
        print(f"⚠️  Fallback: {results['error_recovery']['result']}")

    # Test 2: Insufficient data (should use fallback)
    print("\nTest 2: Insufficient data (triggers fallback)")
    results, _ = runtime.execute(workflow, parameters={"processor": {"data": [1, 2]}})

    if "success_path" in results:
        print(f"✅ Success: {results['success_path']['result']}")
    elif "error_recovery" in results:
        print(f"⚠️  Fallback: {results['error_recovery']['result']}")
        print(f"Error: {results['error_recovery']['original_error']}")


# ============================================================================
# Example 5: Data Filtering and Merging
# ============================================================================


def example5_data_filtering_and_merging():
    """Demonstrates data filtering with conditional routing and merging results."""
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Data Filtering and Merging")
    print("=" * 60)

    class DataFilterNode(Node):
        def get_parameters(self):
            return {
                "items": NodeParameter(
                    name="items", type=list, required=False, default=[]
                )
            }

        def run(self, context, **kwargs):
            items = kwargs.get("items", [])

            # Create items with priority if they don't have it
            if items and isinstance(items[0], (int, float)):
                items = [{"value": item, "priority": item % 10} for item in items]

            # Categorize items by priority
            high_priority = [item for item in items if item.get("priority", 0) > 7]
            medium_priority = [
                item for item in items if 3 <= item.get("priority", 0) <= 7
            ]
            low_priority = [item for item in items if item.get("priority", 0) < 3]

            # Determine routing based on content
            if high_priority:
                route = "urgent_processing"
                data = high_priority
            elif medium_priority:
                route = "standard_processing"
                data = medium_priority
            else:
                route = "batch_processing"
                data = low_priority

            return {"data": data, "route": route, "item_count": len(data)}

    class UrgentHandlerNode(Node):
        def get_parameters(self):
            return {
                "data": NodeParameter(
                    name="data", type=list, required=False, default=[]
                )
            }

        def run(self, context, **kwargs):
            data = kwargs.get("data", [])
            processed = [
                {"value": item["value"] * 3, "priority": "HIGH"} for item in data
            ]
            return {"processed_data": processed, "handler": "urgent"}

    class StandardHandlerNode(Node):
        def get_parameters(self):
            return {
                "data": NodeParameter(
                    name="data", type=list, required=False, default=[]
                )
            }

        def run(self, context, **kwargs):
            data = kwargs.get("data", [])
            processed = [
                {"value": item["value"] * 2, "priority": "MEDIUM"} for item in data
            ]
            return {"processed_data": processed, "handler": "standard"}

    class BatchHandlerNode(Node):
        def get_parameters(self):
            return {
                "data": NodeParameter(
                    name="data", type=list, required=False, default=[]
                )
            }

        def run(self, context, **kwargs):
            data = kwargs.get("data", [])
            processed = [{"value": item["value"], "priority": "LOW"} for item in data]
            return {"processed_data": processed, "handler": "batch"}

    workflow = Workflow("data-filtering", "Data Filtering and Processing")

    # Add nodes
    workflow.add_node("filter", DataFilterNode())
    workflow.add_node(
        "router",
        SwitchNode(
            condition_field="route",
            routes={
                "urgent_processing": "urgent_handler",
                "standard_processing": "standard_handler",
                "batch_processing": "batch_handler",
            },
        ),
    )
    workflow.add_node("urgent_handler", UrgentHandlerNode())
    workflow.add_node("standard_handler", StandardHandlerNode())
    workflow.add_node("batch_handler", BatchHandlerNode())

    # Connect for filtering and routing
    workflow.connect("filter", "router")
    workflow.connect("router", "urgent_handler", route="urgent_handler")
    workflow.connect("router", "standard_handler", route="standard_handler")
    workflow.connect("router", "batch_handler", route="batch_handler")

    # Test different priority distributions
    runtime = LocalRuntime()
    test_cases = [
        ("High priority data", list(range(8, 12))),  # Values 8-11, priorities 8-1
        ("Medium priority data", list(range(3, 8))),  # Values 3-7, priorities 3-7
        ("Low priority data", list(range(0, 3))),  # Values 0-2, priorities 0-2
    ]

    for test_name, test_data in test_cases:
        print(f"\n{test_name}: {test_data}")
        results, _ = runtime.execute(
            workflow, parameters={"filter": {"items": test_data}}
        )

        # Find which handler was used
        for handler in ["urgent_handler", "standard_handler", "batch_handler"]:
            if handler in results:
                result = results[handler]
                print(f"Handler used: {result['handler']}")
                print(f"Processed items: {len(result['processed_data'])}")
                if result["processed_data"]:
                    print(f"Sample result: {result['processed_data'][0]}")
                break


# ============================================================================
# Main Execution
# ============================================================================


def main():
    """Run all conditional routing examples."""
    print("🚀 Conditional Routing Workflow Examples")
    print("=" * 60)
    print()
    print("This example demonstrates various conditional routing patterns:")
    print("• Simple boolean routing (true/false branching)")
    print("• Multi-case status routing (multiple conditions)")
    print("• Conditional retry loops (quality improvement cycles)")
    print("• Error handling with fallback routes")
    print("• Data filtering and transformation routing")
    print()

    try:
        # Run all examples
        example1_simple_boolean_routing()
        example2_multi_case_routing()
        example3_conditional_retry_loops()  # CRITICAL PATTERN
        example4_error_handling()
        example5_data_filtering_and_merging()

        print("\n" + "=" * 60)
        print("✅ All conditional routing examples completed successfully!")
        print()
        print("💡 Key Patterns Demonstrated:")
        print("• SwitchNode for dynamic routing based on conditions")
        print("• Boolean routing: condition_field + true_route + false_route")
        print("• Multi-case routing: condition_field + routes dictionary")
        print("• **CRITICAL**: A → B → C → D → Switch → (B if retry | E if finish)")
        print("• Error handling with graceful fallback paths")
        print("• Data-driven routing for processing optimization")
        print()
        print("🔧 Production Usage:")
        print("• Use SwitchNode for all conditional workflow routing")
        print("• Combine with cycles for iterative improvement workflows")
        print("• Implement fallback routes for robust error handling")
        print("• Route based on data characteristics for performance")
        print()
        print("📚 Next Steps:")
        print("• Try conditional routing with your own business logic")
        print("• Combine with MergeNode for complex branching/merging patterns")
        print("• Implement domain-specific routing conditions")
        print("• Add monitoring and metrics to routing decisions")

    except Exception as e:
        print(f"❌ Examples failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
