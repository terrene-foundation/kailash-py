#!/usr/bin/env python3
"""
Conditional Routing & Control Flow Patterns - Production Business Solution

Advanced conditional routing patterns for production business workflows:
1. Multi-tier data processing routing based on business rules
2. A → B → C → D → Switch → (B if retry | E if finish) quality improvement cycles
3. Error handling with intelligent fallback strategies
4. Priority-based processing with SLA compliance
5. Dynamic resource allocation based on workload
6. Business intelligence on routing decisions

Business Value:
- Intelligent workload distribution optimizes resource utilization
- Quality improvement cycles ensure data accuracy and completeness
- Priority-based routing maintains SLA compliance for critical tasks
- Fallback strategies ensure business continuity during failures
- Real-time routing decisions based on business rules
- Operational visibility into processing patterns and bottlenecks

Key Features:
- SwitchNode with multi-case routing for complex business logic
- Auto-mapping parameters for streamlined conditional workflows
- LocalRuntime with enterprise monitoring and quality tracking
- Business intelligence on processing patterns and resource usage
- Production-ready error handling and recovery strategies
"""

import json
import logging
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Add examples directory to path for utils import
examples_dir = project_root / "examples"
sys.path.insert(0, str(examples_dir))

from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import NodeExecutionError
from kailash.workflow.graph import Workflow

from examples.utils.paths import get_data_dir

# Configure business-focused logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_business_data_classifier():
    """Create a node that classifies business data by priority and complexity."""

    def classify_business_data(
        transactions: List[Dict] = None, sla_threshold_hours: int = 4
    ) -> Dict[str, Any]:
        """Classify business transactions for optimal routing."""

        if transactions is None:
            # Generate realistic business transaction data
            customer_types = ["enterprise", "business", "individual"]
            transaction_types = [
                "purchase",
                "refund",
                "subscription",
                "service",
                "upgrade",
            ]
            regions = ["north_america", "europe", "asia_pacific", "latin_america"]

            transactions = []
            for i in range(random.randint(10, 25)):
                amount = round(random.uniform(50, 50000), 2)
                customer_type = random.choice(customer_types)

                # Business rules for priority
                priority_score = 0
                if customer_type == "enterprise":
                    priority_score += 3
                elif customer_type == "business":
                    priority_score += 2

                if amount > 10000:
                    priority_score += 2
                elif amount > 1000:
                    priority_score += 1

                # Create realistic transaction
                transaction = {
                    "transaction_id": f"TXN_{2000 + i}",
                    "customer_id": f"CUST_{random.randint(1, 1000)}",
                    "customer_type": customer_type,
                    "transaction_type": random.choice(transaction_types),
                    "amount": amount,
                    "currency": "USD",
                    "region": random.choice(regions),
                    "priority_score": priority_score,
                    "submitted_at": (
                        datetime.now() - timedelta(minutes=random.randint(0, 480))
                    ).isoformat(),
                    "requires_approval": amount > 25000,
                    "complexity": (
                        "high"
                        if amount > 20000 or customer_type == "enterprise"
                        else "medium" if amount > 5000 else "low"
                    ),
                }
                transactions.append(transaction)

        # Business classification logic
        urgent_transactions = []
        standard_transactions = []
        batch_transactions = []

        processing_stats = {
            "total_value": 0,
            "urgent_count": 0,
            "standard_count": 0,
            "batch_count": 0,
            "enterprise_count": 0,
            "approval_required_count": 0,
        }

        current_time = datetime.now()

        for transaction in transactions:
            processing_stats["total_value"] += transaction.get("amount", 0)

            # Business priority rules
            submitted_time = datetime.fromisoformat(
                transaction.get("submitted_at", current_time.isoformat())
            )
            hours_pending = (current_time - submitted_time).total_seconds() / 3600

            # Classification logic
            priority_score = transaction.get("priority_score", 0)
            requires_approval = transaction.get("requires_approval", False)
            customer_type = transaction.get("customer_type", "individual")
            amount = transaction.get("amount", 0)

            # Count special cases
            if customer_type == "enterprise":
                processing_stats["enterprise_count"] += 1
            if requires_approval:
                processing_stats["approval_required_count"] += 1

            # Business routing logic
            if (
                hours_pending > sla_threshold_hours
                or priority_score >= 4
                or requires_approval
                or customer_type == "enterprise"
            ):

                urgent_transactions.append(transaction)
                processing_stats["urgent_count"] += 1

            elif (
                priority_score >= 2
                or amount > 1000
                or hours_pending > sla_threshold_hours / 2
            ):

                standard_transactions.append(transaction)
                processing_stats["standard_count"] += 1

            else:
                batch_transactions.append(transaction)
                processing_stats["batch_count"] += 1

        # Determine optimal routing strategy
        if urgent_transactions:
            route_decision = "urgent_processing"
            primary_data = urgent_transactions
            route_reason = f"Found {len(urgent_transactions)} urgent transactions requiring immediate attention"
        elif standard_transactions:
            route_decision = "standard_processing"
            primary_data = standard_transactions
            route_reason = f"Processing {len(standard_transactions)} standard priority transactions"
        else:
            route_decision = "batch_processing"
            primary_data = batch_transactions
            route_reason = (
                f"Batch processing {len(batch_transactions)} low priority transactions"
            )

        # Business intelligence summary
        return {
            "routing_decision": route_decision,
            "primary_data": primary_data,
            "all_transactions": {
                "urgent": urgent_transactions,
                "standard": standard_transactions,
                "batch": batch_transactions,
            },
            "processing_stats": processing_stats,
            "route_reason": route_reason,
            "sla_compliance": {
                "within_sla": processing_stats["urgent_count"]
                + processing_stats["standard_count"],
                "approaching_sla": len(
                    [
                        t
                        for t in transactions
                        if (
                            current_time
                            - datetime.fromisoformat(
                                t.get("submitted_at", current_time.isoformat())
                            )
                        ).total_seconds()
                        / 3600
                        > sla_threshold_hours * 0.75
                    ]
                ),
                "sla_threshold_hours": sla_threshold_hours,
            },
            "classification_timestamp": current_time.isoformat(),
        }

    return PythonCodeNode.from_function(
        func=classify_business_data,
        name="business_data_classifier",
        description="Classifies business transactions for optimal processing routing",
    )


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

    def run(self, **kwargs):
        data = kwargs.get("data", [])
        quality = kwargs.get("quality", 0.0)
        increment = kwargs.get("increment", 0.2)

        # Get iteration info from kwargs if available
        iteration = kwargs.get("iteration", 0)

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

    def run(self, **kwargs):
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

    def run(self, **kwargs):
        data = kwargs.get("data", {})
        quality = kwargs.get("quality", 0.0)
        threshold = kwargs.get("threshold", 0.8)

        # Get iteration info from kwargs if available
        iteration = kwargs.get("iteration", 0)

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

    def run(self, **kwargs):
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

    def run(self, **kwargs):
        data = kwargs.get("data", [])
        threshold = kwargs.get("threshold", 0.8)

        # Simple validation: average of data
        quality = sum(data) / len(data) if data else 0
        is_valid = quality >= threshold

        # Return the full validation result
        return {"data": data, "quality": quality, "is_valid": is_valid}


class SuccessHandlerNode(Node):
    """Handles successful validation."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=dict, required=False, default={})
        }

    def run(self, **kwargs):
        # The switch passes the full input_data dict
        input_data = kwargs.get("data", {})
        actual_data = input_data.get("data", []) if isinstance(input_data, dict) else []

        return {
            "result": "success",
            "processed_data": actual_data,
            "message": "Data validation passed",
        }


class RetryHandlerNode(Node):
    """Handles retry scenarios."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=dict, required=False, default={})
        }

    def run(self, **kwargs):
        # The switch passes the full input_data dict
        input_data = kwargs.get("data", {})
        actual_data = input_data.get("data", []) if isinstance(input_data, dict) else []

        # Improve data for retry (ensure numeric data)
        improved_data = []
        for x in actual_data:
            if isinstance(x, (int, float)):
                improved_data.append(x * 1.1)
            else:
                improved_data.append(x)

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

    def run(self, **kwargs):
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

    def run(self, **kwargs):
        data = kwargs.get("data", [])
        return {"result": [x * 2 for x in data], "processor": "simple"}


class StandardProcessorNode(Node):
    """Standard processor for medium data."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[])
        }

    def run(self, **kwargs):
        data = kwargs.get("data", [])
        return {"result": [x * 3 for x in data], "processor": "standard"}


class BatchProcessorNode(Node):
    """Batch processor for large data."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[])
        }

    def run(self, **kwargs):
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

    def run(self, **kwargs):
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

    # Create a wrapper node that formats data for SwitchNode
    class DataPrepNode(Node):
        def get_parameters(self):
            return {
                "data": NodeParameter(
                    name="data", type=list, required=False, default=[]
                ),
                "quality": NodeParameter(
                    name="quality", type=float, required=False, default=0.0
                ),
                "is_valid": NodeParameter(
                    name="is_valid", type=bool, required=False, default=False
                ),
            }

        def run(self, **kwargs):
            # Package all inputs as a single dict for SwitchNode's input_data
            return {
                "input_data": {
                    "data": kwargs.get("data", []),
                    "quality": kwargs.get("quality", 0.0),
                    "is_valid": kwargs.get("is_valid", False),
                }
            }

    workflow = Workflow("boolean-routing", "Simple Boolean Routing Example")

    # Add nodes
    workflow.add_node("validator", ValidationNode())
    workflow.add_node("prep", DataPrepNode())  # Prep data for switch
    workflow.add_node(
        "switch",
        SwitchNode(condition_field="is_valid", operator="==", value=True),
    )
    workflow.add_node("success_handler", SuccessHandlerNode())
    workflow.add_node("retry_handler", RetryHandlerNode())

    # Connect nodes - prep formats the data for SwitchNode
    workflow.connect("validator", "prep")
    workflow.connect("prep", "switch", mapping={"input_data": "input_data"})
    # SwitchNode produces true_output and false_output in boolean mode
    # Note: The switch passes the entire input_data to the output, not just the 'data' field
    workflow.connect("switch", "success_handler", mapping={"true_output": "data"})
    workflow.connect("switch", "retry_handler", mapping={"false_output": "data"})

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
            cases={
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

    # Connect nodes - checker outputs {data, status} which SwitchNode needs as input_data
    # Create prep node inline
    class DataPrepNode(Node):
        def get_parameters(self):
            return {
                "data": NodeParameter(
                    name="data", type=list, required=False, default=[]
                ),
                "status": NodeParameter(
                    name="status", type=str, required=False, default=""
                ),
            }

        def run(self, **kwargs):
            return {"input_data": kwargs}

    workflow.add_node("prep", DataPrepNode())
    workflow.connect("checker", "prep")
    workflow.connect("prep", "router", mapping={"input_data": "input_data"})
    workflow.connect("router", "error_handler", mapping={"case_empty": "data"})
    workflow.connect("router", "simple_processor", mapping={"case_small": "data"})
    workflow.connect("router", "standard_processor", mapping={"case_medium": "data"})
    workflow.connect("router", "batch_processor", mapping={"case_large": "data"})

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
            cases={
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

    # Create prep node for switch input
    class DataPrepNode2(Node):
        def get_parameters(self):
            return {
                "data": NodeParameter(
                    name="data", type=Any, required=False, default={}
                ),
                "quality": NodeParameter(
                    name="quality", type=float, required=False, default=0.0
                ),
                "route_decision": NodeParameter(
                    name="route_decision", type=str, required=False, default=""
                ),
                "should_continue": NodeParameter(
                    name="should_continue", type=bool, required=False, default=True
                ),
                "reason": NodeParameter(
                    name="reason", type=str, required=False, default=""
                ),
            }

        def run(self, **kwargs):
            return {"input_data": kwargs}

    workflow.add_node("prep2", DataPrepNode2())
    workflow.connect("checker", "prep2")
    workflow.connect("prep2", "switch", mapping={"input_data": "input_data"})

    # Route to completion when converged
    workflow.connect(
        "switch",
        "output",  # Continue to E
        mapping={"case_finish": "data"},
    )

    # Build workflow first, then create cycle for conditional retry
    built_workflow = workflow.build()
    cycle_builder = built_workflow.create_cycle("conditional_retry_cycle")
    cycle_builder.connect(
        "switch", "processor", condition="case_retry", mapping={"case_retry": "data"}
    )
    cycle_builder.max_iterations(10)
    cycle_builder.converge_when("should_continue == False")
    cycle_builder.build()

    # Execute the conditional cycle
    runtime = LocalRuntime()

    print("\nExecuting quality improvement cycle...")
    print("Will iterate until quality >= 0.8 or max 10 iterations")

    results, _ = runtime.execute(
        built_workflow,
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

        def run(self, **kwargs):
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

        def run(self, **kwargs):
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

        def run(self, **kwargs):
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
            cases={"success": "success_path", "fallback": "error_recovery"},
        ),
    )
    workflow.add_node("success_path", SuccessPathNode())
    workflow.add_node("error_recovery", ErrorRecoveryNode())

    # Connect nodes - processor outputs {data, status} which SwitchNode needs as input_data
    class DataPrepNode3(Node):
        def get_parameters(self):
            return {
                "data": NodeParameter(
                    name="data", type=list, required=False, default=[]
                ),
                "status": NodeParameter(
                    name="status", type=str, required=False, default=""
                ),
                "error": NodeParameter(
                    name="error", type=str, required=False, default=""
                ),
            }

        def run(self, **kwargs):
            return {"input_data": kwargs}

    workflow.add_node("prep3", DataPrepNode3())
    workflow.connect("processor", "prep3")
    workflow.connect("prep3", "status_check", mapping={"input_data": "input_data"})
    workflow.connect("status_check", "success_path", mapping={"case_success": "data"})
    workflow.connect(
        "status_check",
        "error_recovery",
        mapping={"case_fallback": "data", "error": "error"},
    )

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

        def run(self, **kwargs):
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

        def run(self, **kwargs):
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

        def run(self, **kwargs):
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

        def run(self, **kwargs):
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
            cases={
                "urgent_processing": "urgent_handler",
                "standard_processing": "standard_handler",
                "batch_processing": "batch_handler",
            },
        ),
    )
    workflow.add_node("urgent_handler", UrgentHandlerNode())
    workflow.add_node("standard_handler", StandardHandlerNode())
    workflow.add_node("batch_handler", BatchHandlerNode())

    # Connect for filtering and routing - filter outputs {data, route, item_count} which SwitchNode needs as input_data
    class DataPrepNode4(Node):
        def get_parameters(self):
            return {
                "data": NodeParameter(
                    name="data", type=list, required=False, default=[]
                ),
                "route": NodeParameter(
                    name="route", type=str, required=False, default=""
                ),
                "item_count": NodeParameter(
                    name="item_count", type=int, required=False, default=0
                ),
            }

        def run(self, **kwargs):
            return {"input_data": kwargs}

    workflow.add_node("prep4", DataPrepNode4())
    workflow.connect("filter", "prep4")
    workflow.connect("prep4", "router", mapping={"input_data": "input_data"})
    workflow.connect(
        "router", "urgent_handler", mapping={"case_urgent_processing": "data"}
    )
    workflow.connect(
        "router", "standard_handler", mapping={"case_standard_processing": "data"}
    )
    workflow.connect(
        "router", "batch_handler", mapping={"case_batch_processing": "data"}
    )

    # Test different priority distributions
    runtime = LocalRuntime()
    test_cases = [
        ("High priority data", list(range(8, 12))),  # Values 8-11, priorities 8-1
        ("Medium priority data", list(range(3, 8))),  # Values 3-7, priorities 3-7
        ("Low priority data", list(range(3))),  # Values 0-2, priorities 0-2
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
        print(
            "• Boolean routing: condition_field + operator + value → true_output/false_output"
        )
        print(
            "• Multi-case routing: condition_field + cases dictionary → case_X outputs"
        )
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
