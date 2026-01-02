#!/usr/bin/env python3
"""
Simple Credit Risk Assessment Workflow

A streamlined credit risk assessment that works with the available
customer value data to demonstrate financial risk analysis patterns.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow

from examples.utils.data_paths import (
    ensure_output_dir_exists,
    get_input_data_path,
    get_output_data_path,
)


def calculate_simple_risk_metrics(data: list) -> dict:
    """Calculate risk metrics for simple credit assessment."""

    import pandas as pd

    try:
        # Convert to DataFrame
        df = pd.DataFrame(data)

        # Convert claim amount to numeric (handle string values)
        df["Total Claim Amount"] = pd.to_numeric(
            df["Total Claim Amount"], errors="coerce"
        )

        # Group by customer to get aggregated metrics
        customer_metrics = (
            df.groupby("Customer")
            .agg(
                {
                    "Total Claim Amount": ["sum", "mean", "count", "max"],
                    "Status": lambda x: x.iloc[-1],  # Latest status
                    "Region": "first",
                }
            )
            .reset_index()
        )

        # Flatten column names
        customer_metrics.columns = [
            "Customer",
            "total_claims",
            "avg_claim",
            "claim_count",
            "max_claim",
            "status",
            "region",
        ]

        # Calculate risk scores
        customer_metrics["activity_score"] = customer_metrics["status"].map(
            {"Active": 70, "Inactive": 30}
        )

        # Normalize claim amounts for risk scoring
        max_total = customer_metrics["total_claims"].max()
        customer_metrics["claim_risk"] = (
            customer_metrics["total_claims"] / max_total * 100
        )

        # Calculate composite risk score (0-100, higher is better/lower risk)
        customer_metrics["risk_score"] = (
            customer_metrics["activity_score"] * 0.5
            + (100 - customer_metrics["claim_risk"]) * 0.3
            + (customer_metrics["claim_count"] * 10).clip(0, 20)
        ).clip(0, 100)

        # Assign risk categories
        def categorize_risk(score):
            if score >= 80:
                return "Low Risk"
            elif score >= 60:
                return "Medium Risk"
            elif score >= 40:
                return "High Risk"
            else:
                return "Critical Risk"

        customer_metrics["risk_category"] = customer_metrics["risk_score"].apply(
            categorize_risk
        )

        # Add recommendations
        def get_recommendations(row):
            recs = []
            if row["status"] == "Inactive":
                recs.append("Re-engage customer with targeted offers")
            if row["total_claims"] > 3000:
                recs.append("High-value customer - provide premium service")
            if row["risk_category"] in ["High Risk", "Critical Risk"]:
                recs.append("Review credit limits and terms")
            return "; ".join(recs) if recs else "Standard monitoring"

        customer_metrics["recommendations"] = customer_metrics.apply(
            get_recommendations, axis=1
        )

        # Convert to records for output
        result = customer_metrics.to_dict("records")

        return {"result": result, "status": "success", "total_customers": len(result)}

    except Exception as e:
        return {"result": [], "status": "error", "error": str(e)}


def create_simple_credit_risk_workflow() -> Workflow:
    """Create a simple credit risk assessment workflow."""
    workflow = Workflow("simple-credit-risk", "Simple Credit Risk Assessment")

    # Load customer financial data
    data_reader = CSVReaderNode(
        name="data_reader", file_path=str(get_input_data_path("customer_value.csv"))
    )
    workflow.add_node("data_reader", data_reader)

    # Calculate risk metrics using from_function pattern
    risk_calculator = PythonCodeNode.from_function(
        name="risk_calculator", func=calculate_simple_risk_metrics
    )
    workflow.add_node("risk_calculator", risk_calculator)
    workflow.connect("data_reader", "risk_calculator", mapping={"data": "data"})

    # Save results
    ensure_output_dir_exists("json")
    report_writer = JSONWriterNode(
        name="report_writer",
        file_path=str(get_output_data_path("simple_credit_risk_report.json", "json")),
        pretty_print=True,
    )
    workflow.add_node("report_writer", report_writer)
    workflow.connect("risk_calculator", "report_writer", mapping={"result": "data"})

    return workflow


def main():
    """Execute the simple credit risk workflow."""
    print("🏦 Starting Simple Credit Risk Assessment...")

    try:
        workflow = create_simple_credit_risk_workflow()
        runtime = LocalRuntime()

        results, run_id = runtime.execute(workflow)

        print("✅ Workflow completed successfully!")
        print(
            f"📁 Report saved to: {get_output_data_path('simple_credit_risk_report.json', 'json')}"
        )

        # Display summary
        if "risk_calculator" in results:
            result_data = results["risk_calculator"]
            data = result_data.get("result", [])
            status = result_data.get("status", "unknown")

            if status == "success" and data:
                print("\n📊 Risk Assessment Summary:")
                print(f"   Total customers analyzed: {len(data)}")

                # Count by risk category
                categories = {}
                for customer in data:
                    cat = customer.get("risk_category", "Unknown")
                    categories[cat] = categories.get(cat, 0) + 1

                print("\n   Risk Distribution:")
                for cat, count in sorted(categories.items()):
                    print(f"   - {cat}: {count} customers")
            elif status == "error":
                print(
                    f"\n❌ Risk calculation failed: {result_data.get('error', 'Unknown error')}"
                )
            else:
                print(f"\n⚠️ No risk data generated (status: {status})")

        return results

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise


if __name__ == "__main__":
    main()
