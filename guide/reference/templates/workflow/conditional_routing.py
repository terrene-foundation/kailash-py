"""
Template: Conditional Routing Workflow
Purpose: Route data through different processing paths based on conditions
Use Case: Business rules processing, status-based workflows, A/B testing

Customization Points:
- ROUTING_CONDITIONS: Define your routing logic
- Process functions: Customize processing for each route
- MERGE_STRATEGY: How to combine results from different paths
"""

from kailash.workflow import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data.readers import JSONReaderNode
from kailash.nodes.logic.operations import SwitchNode, MergeNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.writers import JSONWriterNode
from typing import Dict, Any, List

# Configuration (customize these)
INPUT_FILE = "data/customers.json"
OUTPUT_FILE = "outputs/processed_customers.json"

# Define routing conditions
ROUTING_CONDITIONS = {
    "premium": "customer_type == 'premium' or total_spent > 1000",
    "standard": "customer_type == 'standard' and total_spent <= 1000",
    "inactive": "last_purchase_days > 180",
}

# Merge strategy for combining results
MERGE_STRATEGY = "concat"  # Options: concat, dict_merge, custom


def process_premium_customers(data: List[Dict]) -> Dict[str, Any]:
    """Process premium customers with special treatment"""
    processed = []

    for customer in data:
        processed_customer = customer.copy()
        processed_customer.update(
            {
                "discount": 0.20,  # 20% discount
                "priority_support": True,
                "loyalty_points": int(customer.get("total_spent", 0) * 0.1),
                "processing_path": "premium",
            }
        )
        processed.append(processed_customer)

    return {
        "customers": processed,
        "summary": {
            "path": "premium",
            "count": len(processed),
            "total_discounts": sum(c["discount"] for c in processed),
        },
    }


def process_standard_customers(data: List[Dict]) -> Dict[str, Any]:
    """Process standard customers"""
    processed = []

    for customer in data:
        processed_customer = customer.copy()
        processed_customer.update(
            {
                "discount": 0.05,  # 5% discount
                "priority_support": False,
                "loyalty_points": int(customer.get("total_spent", 0) * 0.05),
                "processing_path": "standard",
            }
        )
        processed.append(processed_customer)

    return {
        "customers": processed,
        "summary": {
            "path": "standard",
            "count": len(processed),
            "upgrade_eligible": len(
                [c for c in processed if c.get("total_spent", 0) > 800]
            ),
        },
    }


def process_inactive_customers(data: List[Dict]) -> Dict[str, Any]:
    """Process inactive customers with reactivation offers"""
    processed = []

    for customer in data:
        processed_customer = customer.copy()
        processed_customer.update(
            {
                "discount": 0.25,  # 25% reactivation discount
                "reactivation_offer": True,
                "offer_expiry_days": 30,
                "processing_path": "inactive",
            }
        )
        processed.append(processed_customer)

    return {
        "customers": processed,
        "summary": {
            "path": "inactive",
            "count": len(processed),
            "potential_revenue": sum(c.get("average_order_value", 0) for c in processed)
            * 0.75,
        },
    }


def merge_results(results: List[Dict]) -> Dict[str, Any]:
    """Custom merge function to combine results from all paths"""
    all_customers = []
    summaries = {}

    for result in results:
        if isinstance(result, dict):
            # Extract customers
            customers = result.get("customers", [])
            all_customers.extend(customers)

            # Extract summary
            summary = result.get("summary", {})
            if "path" in summary:
                summaries[summary["path"]] = summary

    # Calculate overall statistics
    total_customers = len(all_customers)
    customers_by_path = {}

    for customer in all_customers:
        path = customer.get("processing_path", "unknown")
        customers_by_path[path] = customers_by_path.get(path, 0) + 1

    return {
        "all_customers": all_customers,
        "overall_summary": {
            "total_processed": total_customers,
            "by_path": customers_by_path,
            "path_summaries": summaries,
        },
    }


def create_conditional_workflow():
    """Create the conditional routing workflow"""
    workflow = Workflow()

    # 1. Read input data
    reader = JSONReaderNode(config={"file_path": INPUT_FILE})
    workflow.add_node("reader", reader)

    # 2. Route based on conditions
    router = SwitchNode(
        config={
            "outputs": list(ROUTING_CONDITIONS.keys()),
            "conditions": ROUTING_CONDITIONS,
            "default_output": "standard",  # Fallback route
        }
    )
    workflow.add_node("router", router)

    # 3. Process each route differently
    premium_processor = PythonCodeNode.from_function(
        func=process_premium_customers,
        name="premium_processor",
        description="Process premium customers",
    )
    workflow.add_node("process_premium", premium_processor)

    standard_processor = PythonCodeNode.from_function(
        func=process_standard_customers,
        name="standard_processor",
        description="Process standard customers",
    )
    workflow.add_node("process_standard", standard_processor)

    inactive_processor = PythonCodeNode.from_function(
        func=process_inactive_customers,
        name="inactive_processor",
        description="Process inactive customers",
    )
    workflow.add_node("process_inactive", inactive_processor)

    # 4. Merge results from all paths
    if MERGE_STRATEGY == "custom":
        merger = PythonCodeNode.from_function(
            func=merge_results,
            name="custom_merger",
            description="Merge results with custom logic",
        )
    else:
        merger = MergeNode(
            config={
                "merge_strategy": MERGE_STRATEGY,
                "wait_for_all": False,  # Process as results arrive
            }
        )
    workflow.add_node("merger", merger)

    # 5. Write final results
    writer = JSONWriterNode(config={"file_path": OUTPUT_FILE, "indent": 2})
    workflow.add_node("writer", writer)

    # Connect the workflow
    workflow.connect("reader", "router", mapping={"data": "data"})

    # Connect router to processors
    workflow.connect("router", "process_premium", output_key="premium")
    workflow.connect("router", "process_standard", output_key="standard")
    workflow.connect("router", "process_inactive", output_key="inactive")

    # Connect processors to merger
    workflow.connect("process_premium", "merger")
    workflow.connect("process_standard", "merger")
    workflow.connect("process_inactive", "merger")

    # Connect merger to writer
    if MERGE_STRATEGY == "custom":
        workflow.connect("merger", "writer", mapping={"all_customers": "data"})
    else:
        workflow.connect("merger", "writer")

    return workflow


def main():
    """Execute the conditional routing workflow"""
    import os

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    # Create sample data if input doesn't exist
    if not os.path.exists(INPUT_FILE):
        sample_data = [
            {
                "id": 1,
                "name": "Alice",
                "customer_type": "premium",
                "total_spent": 1500,
                "last_purchase_days": 10,
            },
            {
                "id": 2,
                "name": "Bob",
                "customer_type": "standard",
                "total_spent": 500,
                "last_purchase_days": 30,
            },
            {
                "id": 3,
                "name": "Charlie",
                "customer_type": "standard",
                "total_spent": 900,
                "last_purchase_days": 200,
            },
            {
                "id": 4,
                "name": "Diana",
                "customer_type": "premium",
                "total_spent": 2000,
                "last_purchase_days": 5,
            },
            {
                "id": 5,
                "name": "Eve",
                "customer_type": "standard",
                "total_spent": 300,
                "last_purchase_days": 365,
            },
        ]

        os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
        import json

        with open(INPUT_FILE, "w") as f:
            json.dump(sample_data, f, indent=2)
        print(f"Created sample data in {INPUT_FILE}")

    # Create and execute workflow
    workflow = create_conditional_workflow()
    workflow.validate()

    runtime = LocalRuntime()
    try:
        results = runtime.execute(workflow)

        print("Conditional routing workflow completed!")
        print(f"Results saved to: {OUTPUT_FILE}")

        # Print routing summary
        if "merger" in results:
            if isinstance(results["merger"], dict):
                summary = results["merger"].get("overall_summary", {})
                print("\nRouting Summary:")
                print(f"Total customers processed: {summary.get('total_processed', 0)}")

                by_path = summary.get("by_path", {})
                for path, count in by_path.items():
                    print(f"- {path}: {count} customers")

        return 0

    except Exception as e:
        print(f"Error executing workflow: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
