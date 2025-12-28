#!/usr/bin/env python3
"""
Simple Conditional Routing Patterns - Production Business Solution

Basic conditional routing patterns for business workflows:
1. Priority-based transaction routing
2. SLA compliance monitoring and routing
3. Business intelligence on routing decisions
4. Quality-based routing with fallback strategies

Business Value:
- Automatic prioritization based on business rules
- SLA compliance through intelligent routing
- Resource optimization through workload distribution
- Business intelligence on processing patterns

Key Features:
- SwitchNode for multi-case routing
- PythonCodeNode with business logic
- LocalRuntime with monitoring
- Real-time business decision making
"""

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

from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow

from examples.utils.paths import get_data_dir

# Configure business-focused logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_transaction_classifier():
    """Create a node that classifies transactions by priority."""

    def classify_transactions(transaction_count: int = 15) -> Dict[str, Any]:
        """Generate and classify business transactions."""

        # Generate realistic transaction data
        transactions = []
        for i in range(transaction_count):
            amount = round(random.uniform(100, 10000), 2)
            customer_type = random.choice(["enterprise", "business", "individual"])

            transaction = {
                "id": f"TXN_{1000 + i}",
                "amount": amount,
                "customer_type": customer_type,
                "submitted_at": (
                    datetime.now() - timedelta(minutes=random.randint(0, 120))
                ).isoformat(),
                "requires_approval": amount > 5000,
            }
            transactions.append(transaction)

        # Classify transactions
        urgent_count = 0
        standard_count = 0
        batch_count = 0

        for transaction in transactions:
            if (
                transaction["customer_type"] == "enterprise"
                or transaction["requires_approval"]
                or transaction["amount"] > 5000
            ):
                urgent_count += 1
            elif transaction["amount"] > 1000:
                standard_count += 1
            else:
                batch_count += 1

        # Determine routing based on transaction mix
        if urgent_count > 0:
            routing_decision = "urgent"
            priority_data = [
                t
                for t in transactions
                if t["customer_type"] == "enterprise"
                or t["requires_approval"]
                or t["amount"] > 5000
            ]
        elif standard_count > 0:
            routing_decision = "standard"
            priority_data = [t for t in transactions if 1000 < t["amount"] <= 5000]
        else:
            routing_decision = "batch"
            priority_data = [t for t in transactions if t["amount"] <= 1000]

        return {
            "routing_decision": routing_decision,
            "transactions": priority_data,
            "classification_stats": {
                "urgent_count": urgent_count,
                "standard_count": standard_count,
                "batch_count": batch_count,
                "total_transactions": len(transactions),
            },
        }

    return PythonCodeNode.from_function(
        func=classify_transactions,
        name="transaction_classifier",
        description="Classifies transactions for priority-based routing",
    )


def create_urgent_processor():
    """Create processor for urgent transactions."""

    def process_urgent(transactions: List[Dict]) -> Dict[str, Any]:
        """Process urgent transactions with priority handling."""

        processed = []
        total_value = 0

        for transaction in transactions:
            processed_transaction = transaction.copy()
            processed_transaction["priority"] = "URGENT"
            processed_transaction["processed_at"] = datetime.now().isoformat()
            processed_transaction["sla_status"] = "PRIORITY"

            if transaction.get("requires_approval"):
                processed_transaction["approval_status"] = "ESCALATED"

            processed.append(processed_transaction)
            total_value += transaction.get("amount", 0)

        return {
            "processed_transactions": processed,
            "processor_type": "urgent",
            "total_value": round(total_value, 2),
            "processing_time": "< 1 minute",
            "sla_compliance": "GUARANTEED",
        }

    return PythonCodeNode.from_function(
        func=process_urgent,
        name="urgent_processor",
        description="Processes urgent transactions with priority handling",
    )


def create_standard_processor():
    """Create processor for standard transactions."""

    def process_standard(transactions: List[Dict]) -> Dict[str, Any]:
        """Process standard transactions with normal handling."""

        processed = []
        total_value = 0

        for transaction in transactions:
            processed_transaction = transaction.copy()
            processed_transaction["priority"] = "STANDARD"
            processed_transaction["processed_at"] = datetime.now().isoformat()
            processed_transaction["sla_status"] = "NORMAL"

            processed.append(processed_transaction)
            total_value += transaction.get("amount", 0)

        return {
            "processed_transactions": processed,
            "processor_type": "standard",
            "total_value": round(total_value, 2),
            "processing_time": "< 5 minutes",
            "sla_compliance": "ON_TRACK",
        }

    return PythonCodeNode.from_function(
        func=process_standard,
        name="standard_processor",
        description="Processes standard transactions with normal handling",
    )


def create_batch_processor():
    """Create processor for batch transactions."""

    def process_batch(transactions: List[Dict]) -> Dict[str, Any]:
        """Process batch transactions with efficient handling."""

        processed = []
        total_value = 0

        for transaction in transactions:
            processed_transaction = transaction.copy()
            processed_transaction["priority"] = "BATCH"
            processed_transaction["processed_at"] = datetime.now().isoformat()
            processed_transaction["sla_status"] = "BATCH_QUEUE"

            processed.append(processed_transaction)
            total_value += transaction.get("amount", 0)

        return {
            "processed_transactions": processed,
            "processor_type": "batch",
            "total_value": round(total_value, 2),
            "processing_time": "< 30 minutes",
            "sla_compliance": "BATCH_SCHEDULE",
        }

    return PythonCodeNode.from_function(
        func=process_batch,
        name="batch_processor",
        description="Processes batch transactions with efficient handling",
    )


def main():
    """Execute the simple conditional routing workflow."""

    # Create data directories
    data_dir = get_data_dir()
    data_dir.mkdir(exist_ok=True)

    print("🚦 Starting Simple Conditional Routing Patterns Workflow")
    print("=" * 70)

    # Create workflow
    print("📋 Creating conditional routing workflow...")
    workflow = Workflow(
        workflow_id="simple_conditional_routing",
        name="simple_conditional_routing",
        description="Simple conditional routing patterns for business transactions",
    )

    # Create nodes
    print("🔧 Creating routing nodes...")

    classifier = create_transaction_classifier()
    urgent_processor = create_urgent_processor()
    standard_processor = create_standard_processor()
    batch_processor = create_batch_processor()

    # Add nodes to workflow
    workflow.add_node(node_id="classifier", node_or_type=classifier)

    # Create switch node for routing
    router = SwitchNode(
        condition_field="routing_decision",
        cases={
            "urgent": "urgent_processor",
            "standard": "standard_processor",
            "batch": "batch_processor",
        },
    )
    workflow.add_node(node_id="router", node_or_type=router)

    workflow.add_node(node_id="urgent_processor", node_or_type=urgent_processor)
    workflow.add_node(node_id="standard_processor", node_or_type=standard_processor)
    workflow.add_node(node_id="batch_processor", node_or_type=batch_processor)

    # Connect nodes
    print("🔗 Connecting routing pipeline...")

    # Classifier to router
    workflow.connect("classifier", "router", {"result": "input_data"})

    # Router to processors
    workflow.connect(
        "router", "urgent_processor", {"case_urgent.transactions": "transactions"}
    )
    workflow.connect(
        "router", "standard_processor", {"case_standard.transactions": "transactions"}
    )
    workflow.connect(
        "router", "batch_processor", {"case_batch.transactions": "transactions"}
    )

    # Validate workflow with sample parameters
    print("✅ Validating routing workflow...")
    try:
        validation_params = {"classifier": {"transaction_count": 10}}
        workflow.validate(runtime_parameters=validation_params)
        print("✓ Workflow validation successful!")
    except Exception as e:
        print(f"✗ Workflow validation failed: {e}")
        return 1

    # Execute with multiple scenarios
    print("🚀 Executing conditional routing patterns...")

    test_scenarios = [
        {
            "name": "High Volume Test",
            "parameters": {"classifier": {"transaction_count": 20}},
        },
        {
            "name": "Medium Volume Test",
            "parameters": {"classifier": {"transaction_count": 10}},
        },
        {
            "name": "Low Volume Test",
            "parameters": {"classifier": {"transaction_count": 5}},
        },
    ]

    for i, scenario in enumerate(test_scenarios):
        print(f"\\n📊 Test {i + 1}/3: {scenario['name']}")
        print("-" * 50)

        try:
            # Use enterprise runtime with monitoring
            runner = LocalRuntime(
                debug=True, enable_monitoring=True, enable_audit=False
            )

            results, run_id = runner.execute(
                workflow, parameters=scenario["parameters"]
            )

            print("✓ Conditional routing completed successfully!")
            print(f"  📊 Run ID: {run_id}")

            # Show routing decision
            if "classifier" in results:
                classifier_result = results["classifier"]
                if (
                    isinstance(classifier_result, dict)
                    and "result" in classifier_result
                ):
                    routing_data = classifier_result["result"]
                    routing_decision = routing_data.get("routing_decision", "unknown")
                    stats = routing_data.get("classification_stats", {})

                    print(f"  🚦 Routing Decision: {routing_decision.upper()}")
                    print("  📈 Classification Stats:")
                    print(
                        f"    • Total Transactions: {stats.get('total_transactions', 0)}"
                    )
                    print(f"    • Urgent: {stats.get('urgent_count', 0)}")
                    print(f"    • Standard: {stats.get('standard_count', 0)}")
                    print(f"    • Batch: {stats.get('batch_count', 0)}")

            # Show processing results
            processor_found = False
            for processor_name in [
                "urgent_processor",
                "standard_processor",
                "batch_processor",
            ]:
                if processor_name in results:
                    processor_result = results[processor_name]
                    if (
                        isinstance(processor_result, dict)
                        and "result" in processor_result
                    ):
                        processing_data = processor_result["result"]

                        print(
                            f"  🔧 Processed by: {processing_data.get('processor_type', 'unknown').upper()}"
                        )
                        print(
                            f"  💰 Total Value: ${processing_data.get('total_value', 0):,.2f}"
                        )
                        print(
                            f"  ⏱️  Processing Time: {processing_data.get('processing_time', 'unknown')}"
                        )
                        print(
                            f"  📋 SLA Status: {processing_data.get('sla_compliance', 'unknown')}"
                        )
                        print(
                            f"  📊 Transactions Processed: {len(processing_data.get('processed_transactions', []))}"
                        )
                        processor_found = True
                        break

            if not processor_found:
                print("  ⚠️  No processor output found")

        except Exception as e:
            print(f"✗ Test execution failed: {e}")
            print(f"  Error Type: {type(e).__name__}")

    print("\\n🎉 Simple Conditional Routing Patterns completed!")
    print("📊 This workflow demonstrates:")
    print("  • Multi-case conditional routing with SwitchNode")
    print("  • Business priority classification")
    print("  • SLA-aware processing routing")
    print("  • Real-time business intelligence")

    return 0


if __name__ == "__main__":
    sys.exit(main())
