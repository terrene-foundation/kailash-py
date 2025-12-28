#!/usr/bin/env python3
"""
Basic ETL Workflow - Production Business Solution

A foundational Extract, Transform, Load pattern demonstrating:
1. CSV data ingestion with validation
2. Data transformation using business logic
3. Results persistence in structured format
4. Workflow export for reuse and sharing

Business Value:
- Foundation for all data processing workflows
- Customer tier calculation for marketing segmentation
- Reusable pattern for business data transformation
- Production-ready error handling and monitoring

Key Features:
- Dot notation mapping for nested data access
- Auto-mapping parameters for seamless connections
- LocalRuntime with enterprise capabilities
- Workflow visualization and export
"""

import sys
from pathlib import Path
from typing import Any

import pandas as pd

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Add examples directory to path for utils import
examples_dir = project_root / "examples"
sys.path.insert(0, str(examples_dir))

from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow
from kailash.workflow.visualization import WorkflowVisualizer

from examples.utils.paths import get_data_dir


def create_customer_tier_calculator():
    """Create a Python node for customer tier calculation using business rules."""

    def calculate_customer_tier(data: list) -> dict[str, Any]:
        """Transform customer data by calculating tier based on purchase behavior."""
        df = pd.DataFrame(data)

        # Business logic: Customer tier calculation
        if "purchase_total" in df.columns:
            df["purchase_total"] = pd.to_numeric(df["purchase_total"], errors="coerce")

            # Business tier rules
            df["customer_tier"] = pd.cut(
                df["purchase_total"],
                bins=[0, 100, 500, 1000, float("inf")],
                labels=["Bronze", "Silver", "Gold", "Platinum"],
            )

            # Add tier benefits (business logic)
            tier_benefits = {
                "Bronze": {"discount": 0.05, "support": "standard"},
                "Silver": {"discount": 0.10, "support": "priority"},
                "Gold": {"discount": 0.15, "support": "premium"},
                "Platinum": {"discount": 0.20, "support": "concierge"},
            }

            df["discount_rate"] = df["customer_tier"].map(
                lambda x: tier_benefits.get(str(x), {}).get("discount", 0)
            )
            df["support_level"] = df["customer_tier"].map(
                lambda x: tier_benefits.get(str(x), {}).get("support", "standard")
            )

        elif "tier" in df.columns:
            # If tier already exists, standardize format
            df["customer_tier"] = df["tier"].str.title()

        # Return structured data for business reporting
        return {
            "customers": df.to_dict(orient="records"),
            "summary": {
                "total_customers": len(df),
                "tier_distribution": (
                    df["customer_tier"].value_counts().to_dict()
                    if "customer_tier" in df.columns
                    else {}
                ),
                "average_purchase": (
                    float(df["purchase_total"].mean())
                    if "purchase_total" in df.columns
                    else 0
                ),
            },
        }

    return PythonCodeNode.from_function(
        func=calculate_customer_tier,
        name="customer_tier_calculator",
        description="Calculate customer tiers and benefits using business rules",
    )


def main():
    """Execute the basic ETL workflow with enterprise features."""

    # Create data directories
    data_dir = get_data_dir()
    data_dir.mkdir(exist_ok=True)
    output_dir = data_dir / "outputs"
    output_dir.mkdir(exist_ok=True)

    print("🏭 Starting Basic ETL Workflow")
    print("=" * 50)

    # Step 1: Create workflow with business context
    print("📋 Creating ETL workflow...")
    workflow = Workflow(
        workflow_id="basic_customer_etl",
        name="basic_customer_etl",
        description="Basic ETL for customer tier analysis and business intelligence",
    )

    # Step 2: Create nodes with business focus
    print("🔧 Creating workflow nodes...")

    # Data ingestion
    csv_reader = CSVReaderNode(file_path=str(data_dir / "customers.csv"), headers=True)

    # Business transformation
    tier_calculator = create_customer_tier_calculator()

    # Data persistence
    csv_writer = CSVWriterNode(file_path=str(output_dir / "customer_tiers.csv"))

    # Add nodes to workflow
    workflow.add_node(node_id="data_ingestion", node_or_type=csv_reader)
    workflow.add_node(node_id="tier_calculation", node_or_type=tier_calculator)
    workflow.add_node(node_id="data_output", node_or_type=csv_writer)

    # Step 3: Connect nodes using dot notation for nested data
    print("🔗 Connecting workflow nodes...")

    # Simple connection: CSV reader to tier calculator
    workflow.connect("data_ingestion", "tier_calculation", {"data": "data"})

    # Dot notation: Extract customers array from nested result
    workflow.connect("tier_calculation", "data_output", {"result.customers": "data"})

    # Step 4: Validate workflow
    print("✅ Validating workflow...")
    try:
        workflow.validate()
        print("✓ Workflow validation successful!")
    except Exception as e:
        print(f"✗ Workflow validation failed: {e}")
        return 1

    # Step 5: Execute with LocalRuntime enterprise features
    print("🚀 Executing workflow...")
    try:
        # Use enterprise runtime with monitoring
        runner = LocalRuntime(debug=True, enable_monitoring=True, enable_async=True)

        results, run_id = runner.execute(workflow)

        print("✓ ETL workflow completed successfully!")
        print(f"  📊 Run ID: {run_id}")
        print(f"  📈 Nodes executed: {len(results)}")

        # Business reporting
        if "tier_calculation" in results:
            tier_result = results["tier_calculation"]
            if isinstance(tier_result, dict) and "result" in tier_result:
                summary = tier_result["result"].get("summary", {})
                print("\n📊 Business Intelligence Summary:")
                print(f"  • Total Customers: {summary.get('total_customers', 0)}")
                print(
                    f"  • Average Purchase: ${summary.get('average_purchase', 0):.2f}"
                )

                tier_dist = summary.get("tier_distribution", {})
                if tier_dist:
                    print("  • Tier Distribution:")
                    for tier, count in tier_dist.items():
                        print(f"    - {tier}: {count} customers")

    except Exception as e:
        print(f"✗ ETL workflow execution failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    # Step 6: Create business artifacts
    print("\n📁 Creating business artifacts...")

    # Workflow visualization
    try:
        visualizer = WorkflowVisualizer(workflow)
        visualizer.visualize(output_path=str(output_dir / "etl_workflow.png"))
        print(f"✓ Workflow diagram: {output_dir / 'etl_workflow.png'}")
    except Exception as e:
        print(f"⚠️ Visualization not available: {e}")

    # Workflow export for reuse
    try:
        workflow.export_to_kailash(
            output_path=str(output_dir / "etl_workflow.yaml"), format="yaml"
        )
        print(f"✓ Workflow definition: {output_dir / 'etl_workflow.yaml'}")
    except Exception as e:
        print(f"⚠️ Export not available: {e}")

    print("\n🎉 Basic ETL workflow completed!")
    print("📁 Check output directory for results and artifacts")

    return 0


if __name__ == "__main__":
    # Create sample business data if needed
    sample_data_file = get_data_dir() / "customers.csv"
    if not sample_data_file.exists():
        print("📝 Creating sample customer data...")

        # Realistic business sample data
        sample_data = pd.DataFrame(
            {
                "customer_id": range(1, 21),
                "name": [f"Customer {i}" for i in range(1, 21)],
                "email": [f"customer{i}@business.com" for i in range(1, 21)],
                "purchase_total": [
                    150.50,
                    750.25,
                    50.75,
                    1200.00,
                    450.80,
                    2500.00,
                    75.30,
                    950.60,
                    1800.40,
                    320.15,
                    125.90,
                    680.70,
                    45.25,
                    1450.80,
                    890.35,
                    3200.00,
                    180.60,
                    720.40,
                    2100.25,
                    95.85,
                ],
                "registration_date": pd.date_range("2023-01-01", periods=20, freq="D"),
                "region": ["North", "South", "East", "West"] * 5,
            }
        )

        sample_data.to_csv(sample_data_file, index=False)
        print(f"✓ Created sample data: {sample_data_file}")

    sys.exit(main())
