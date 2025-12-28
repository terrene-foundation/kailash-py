#!/usr/bin/env python3
"""
Credit Risk Assessment Workflow

This workflow demonstrates a comprehensive credit risk assessment system that:
1. Loads customer demographic and transaction history data
2. Calculates risk metrics (payment patterns, transaction volumes, etc.)
3. Uses AI to analyze patterns and generate risk scores
4. Produces detailed risk assessment reports

The workflow uses real customer data and implements production-ready
error handling and validation.
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow

from examples.utils.data_paths import (
    ensure_output_dir_exists,
    get_input_data_path,
    get_output_data_path,
)


def package_customer_data(customers: list, transactions: list) -> dict:
    """Package both datasets into a single dict for processing."""
    return {"result": {"customers": customers, "transactions": transactions}}


def calculate_risk_metrics(packaged_data: dict) -> dict:
    """Calculate comprehensive risk metrics for credit assessment."""
    import pandas as pd

    try:
        # Handle None inputs
        if packaged_data is None:
            packaged_data = {}

        # Convert to DataFrames for easier processing
        customers_df = pd.DataFrame(packaged_data.get("customers", []))
        transactions_df = pd.DataFrame(packaged_data.get("transactions", []))

        # Normalize customer IDs for proper join
        if not customers_df.empty and "customer_id" in customers_df.columns:
            customers_df["customer_id_norm"] = (
                customers_df["customer_id"]
                .str.extract(r"(\d+)")[0]
                .str.zfill(3)
                .apply(lambda x: f"C{x}")
            )

        if not transactions_df.empty and "customer_id" in transactions_df.columns:
            transactions_df["customer_id_norm"] = transactions_df["customer_id"]

        # Calculate transaction metrics per customer
        if not transactions_df.empty:
            transaction_metrics = (
                transactions_df.groupby("customer_id_norm")
                .agg(
                    {
                        "amount": ["sum", "mean", "count", "std"],
                        "transaction_date": ["min", "max"],
                    }
                )
                .reset_index()
            )

            # Flatten column names
            transaction_metrics.columns = [
                "customer_id_norm",
                "total_amount",
                "avg_amount",
                "transaction_count",
                "amount_volatility",
                "first_transaction",
                "last_transaction",
            ]
        else:
            transaction_metrics = pd.DataFrame()

        # Merge customer data with transaction metrics
        if not customers_df.empty and not transaction_metrics.empty:
            risk_df = pd.merge(
                customers_df, transaction_metrics, on="customer_id_norm", how="left"
            )
        elif not customers_df.empty:
            risk_df = customers_df.copy()
            # Add default transaction metrics
            risk_df["total_amount"] = 0
            risk_df["avg_amount"] = 0
            risk_df["transaction_count"] = 0
            risk_df["amount_volatility"] = 0
        else:
            return {"result": [], "status": "no_data"}

        # Calculate risk scores
        risk_df = risk_df.fillna(0)  # Handle missing values

        # Tier-based scoring
        tier_scores = {"premium": 90, "gold": 70, "silver": 50, "bronze": 30}
        risk_df["tier_score"] = risk_df.get("tier", "bronze").map(tier_scores)

        # Transaction-based scoring
        risk_df["transaction_score"] = (risk_df["transaction_count"] * 10).clip(0, 50)

        # Amount-based scoring
        max_amount = (
            risk_df["total_amount"].max() if risk_df["total_amount"].max() > 0 else 1
        )
        risk_df["amount_score"] = (risk_df["total_amount"] / max_amount * 30).clip(
            0, 30
        )

        # Composite risk score
        risk_df["risk_score"] = (
            risk_df["tier_score"] * 0.4
            + risk_df["transaction_score"] * 0.3
            + risk_df["amount_score"] * 0.3
        ).clip(0, 100)

        # Risk categorization
        def categorize_risk(score):
            if score >= 80:
                return "low_risk"
            elif score >= 60:
                return "medium_risk"
            elif score >= 40:
                return "high_risk"
            else:
                return "critical_risk"

        risk_df["risk_category"] = risk_df["risk_score"].apply(categorize_risk)

        # Convert to records
        result = risk_df.to_dict("records")

        return {"result": result, "status": "success", "total_customers": len(result)}

    except Exception as e:
        return {"result": [], "status": "error", "error": str(e)}


def process_ai_response(ai_response: str, risk_metrics: list) -> dict:
    """Process AI response and categorize risks."""
    import json

    try:
        # Parse AI response
        if isinstance(ai_response, str):
            analysis = json.loads(ai_response)
        else:
            analysis = ai_response
    except Exception:
        analysis = {"risk_score": 50, "category": "medium_risk"}

    # Ensure we have the risk metrics data
    risk_data = risk_metrics if isinstance(risk_metrics, list) else []

    # Combine AI analysis with calculated metrics
    result = []
    for customer in risk_data:
        customer_analysis = {
            **customer,
            "ai_risk_score": analysis.get("risk_score", customer.get("risk_score", 50)),
            "ai_category": analysis.get("category", "medium_risk"),
            "ai_recommendations": analysis.get("recommendations", []),
        }
        result.append(customer_analysis)

    return {"result": result}


def create_credit_risk_workflow() -> Workflow:
    """Create a comprehensive credit risk assessment workflow."""
    workflow = Workflow("credit-risk-assessment", "Credit Risk Assessment System")

    # Step 1: Load customer data
    customer_reader = CSVReaderNode(
        name="customer_reader", file_path=str(get_input_data_path("customers.csv"))
    )
    workflow.add_node("customer_reader", customer_reader)

    # Step 2: Load transaction history
    transaction_reader = CSVReaderNode(
        name="transaction_reader",
        file_path=str(get_input_data_path("transactions.csv")),
    )
    workflow.add_node("transaction_reader", transaction_reader)

    # Step 3: Package both datasets for processing using from_function pattern
    data_packager = PythonCodeNode.from_function(
        name="data_packager", func=package_customer_data
    )
    workflow.add_node("data_packager", data_packager)

    # Step 4: Calculate risk metrics using from_function pattern
    risk_calculator = PythonCodeNode.from_function(
        name="risk_calculator", func=calculate_risk_metrics
    )
    workflow.add_node("risk_calculator", risk_calculator)

    # Connect readers to packager
    workflow.connect("customer_reader", "data_packager", mapping={"data": "customers"})
    workflow.connect(
        "transaction_reader", "data_packager", mapping={"data": "transactions"}
    )

    # Connect packager to risk calculator
    workflow.connect(
        "data_packager", "risk_calculator", mapping={"result": "packaged_data"}
    )

    # Step 4: AI-powered risk analysis
    risk_analyzer = LLMAgentNode(
        name="risk_analyzer",
        model="gpt-4",
        system_prompt="You are a financial risk assessment expert. Analyze customer risk data and provide insights.",
        prompt="""
        Analyze the following customer risk metrics and provide a comprehensive assessment:

        Risk Data: {{risk_metrics}}

        Please provide your analysis in JSON format with:
        {
            "risk_score": <overall_score_0_to_100>,
            "category": "<low_risk|medium_risk|high_risk|critical_risk>",
            "recommendations": ["<recommendation1>", "<recommendation2>"]
        }
        """,
    )
    workflow.add_node("risk_analyzer", risk_analyzer)
    workflow.connect(
        "risk_calculator", "risk_analyzer", mapping={"result": "risk_metrics"}
    )

    # Step 5: Process AI response and categorize using from_function pattern
    response_processor = PythonCodeNode.from_function(
        name="response_processor", func=process_ai_response
    )
    workflow.add_node("response_processor", response_processor)

    workflow.connect(
        "risk_analyzer", "response_processor", mapping={"response": "ai_response"}
    )
    workflow.connect(
        "risk_calculator", "response_processor", mapping={"result": "risk_metrics"}
    )

    # Step 6: Save final report
    ensure_output_dir_exists("json")
    report_writer = JSONWriterNode(
        name="report_writer",
        file_path=str(get_output_data_path("credit_risk_reports.json", "json")),
        pretty_print=True,
    )
    workflow.add_node("report_writer", report_writer)
    workflow.connect("response_processor", "report_writer", mapping={"result": "data"})

    return workflow


def main():
    """Execute the credit risk assessment workflow."""
    print("🏦 Starting Credit Risk Assessment...")

    try:
        workflow = create_credit_risk_workflow()
        runtime = LocalRuntime()

        results, run_id = runtime.execute(workflow)

        print("✅ Workflow completed successfully!")
        print(
            f"📁 Report saved to: {get_output_data_path('credit_risk_reports.json', 'json')}"
        )

        # Display summary
        if "response_processor" in results:
            final_results = results["response_processor"].get("result", [])
            if final_results:
                print("\n📊 Credit Risk Summary:")
                print(f"   Total customers processed: {len(final_results)}")

                # Count by risk category
                categories = {}
                for customer in final_results:
                    cat = customer.get("risk_category", "Unknown")
                    categories[cat] = categories.get(cat, 0) + 1

                print("\n   Risk Distribution:")
                for cat, count in sorted(categories.items()):
                    print(f"   - {cat}: {count} customers")

        return results

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise


if __name__ == "__main__":
    main()
