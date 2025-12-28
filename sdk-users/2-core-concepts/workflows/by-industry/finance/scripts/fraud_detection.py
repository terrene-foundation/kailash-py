#!/usr/bin/env python3
"""
Fraud Detection Workflow

This workflow implements a real-time fraud detection system that:
1. Monitors transaction streams for anomalous patterns
2. Analyzes velocity, geography, and amount patterns
3. Applies machine learning models for fraud scoring
4. Generates alerts for suspicious transactions

The workflow demonstrates production-ready fraud detection with
multiple detection strategies and real-time alerting.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, JSONReaderNode, JSONWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow

from examples.utils.data_paths import (
    ensure_output_dir_exists,
    get_input_data_path,
    get_output_data_path,
)


def enrich_fraud_indicators(transaction_data: Any, customer_data: list) -> dict:
    """Enrich transactions with comprehensive fraud indicators.

    Args:
        transaction_data: Transaction records (list or dict with 'transactions')
        customer_data: Customer baseline data

    Returns:
        Dict with 'result' key containing enriched transactions with fraud scores
    """
    # Handle both formats - direct array or nested in 'transactions'
    if isinstance(transaction_data, list):
        transactions = transaction_data
    else:
        transactions = transaction_data.get("transactions", [])
    customers = customer_data

    # Convert to DataFrame for analysis
    trans_df = pd.DataFrame(transactions)
    cust_df = pd.DataFrame(customers)

    # Add timestamps if not present (for demo data)
    if "timestamp" not in trans_df.columns and not trans_df.empty:
        # Generate timestamps for demo
        base_time = datetime.now() - timedelta(days=7)
        trans_df["timestamp"] = [
            base_time + timedelta(hours=i * 2) for i in range(len(trans_df))
        ]
    elif "timestamp" in trans_df.columns:
        trans_df["timestamp"] = pd.to_datetime(trans_df["timestamp"])

    trans_df = (
        trans_df.sort_values("timestamp")
        if "timestamp" in trans_df.columns
        else trans_df
    )

    # Calculate velocity indicators
    result = []
    customer_history = {}

    for idx, trans in trans_df.iterrows():
        cust_id = trans["customer_id"]

        # Initialize customer history
        if cust_id not in customer_history:
            customer_history[cust_id] = {
                "transactions": [],
                "locations": set(),
                "avg_amount": 0,
                "max_amount": 0,
            }

        history = customer_history[cust_id]

        # Calculate fraud indicators
        indicators = {
            "transaction_id": trans.get("id", f"TXN-{idx}"),
            "customer_id": cust_id,
            "amount": trans["amount"],
            "timestamp": trans.get("timestamp", datetime.now().isoformat()),
        }

        # 1. Velocity check - transactions in last hour
        recent_trans = [
            t
            for t in history["transactions"]
            if "timestamp" in trans
            and (trans["timestamp"] - t["timestamp"]).total_seconds() < 3600
        ]
        indicators["velocity_count"] = len(recent_trans)
        indicators["velocity_amount"] = sum(t["amount"] for t in recent_trans)

        # 2. Amount anomaly - compare to historical average
        if history["transactions"]:
            avg_amount = np.mean([t["amount"] for t in history["transactions"]])
            std_amount = np.std([t["amount"] for t in history["transactions"]])
            if std_amount > 0:
                indicators["amount_zscore"] = abs(
                    (trans["amount"] - avg_amount) / std_amount
                )
            else:
                indicators["amount_zscore"] = 0
            indicators["amount_ratio"] = trans["amount"] / (avg_amount + 1)
        else:
            indicators["amount_zscore"] = 0
            indicators["amount_ratio"] = 1

        # 3. Pattern detection
        indicators["is_round_amount"] = trans["amount"] % 10 == 0
        indicators["is_high_value"] = trans["amount"] > 1000
        indicators["is_low_value"] = trans["amount"] < 10

        # 4. Time-based patterns
        if "timestamp" in trans:
            hour = trans["timestamp"].hour
            indicators["is_unusual_time"] = hour < 6 or hour > 23
            indicators["is_weekend"] = trans["timestamp"].weekday() >= 5
        else:
            indicators["is_unusual_time"] = False
            indicators["is_weekend"] = False

        # 5. Calculate fraud risk score (0-100)
        risk_score = 0

        # High velocity
        if indicators["velocity_count"] > 3:
            risk_score += 20
        if indicators["velocity_amount"] > 2000:
            risk_score += 15

        # Amount anomalies
        if indicators["amount_zscore"] > 3:
            risk_score += 25
        if indicators["amount_ratio"] > 5:
            risk_score += 20

        # Pattern risks
        if indicators["is_high_value"]:
            risk_score += 15
        if indicators["is_unusual_time"]:
            risk_score += 10
        if indicators["is_weekend"] and indicators["is_high_value"]:
            risk_score += 10

        indicators["fraud_risk_score"] = min(risk_score, 100)

        # Categorize risk
        if indicators["fraud_risk_score"] >= 70:
            indicators["risk_category"] = "high"
        elif indicators["fraud_risk_score"] >= 40:
            indicators["risk_category"] = "medium"
        else:
            indicators["risk_category"] = "low"

        # Update history (keep datetime objects for calculations)
        history["transactions"].append(
            {
                "amount": trans["amount"],
                "timestamp": trans.get("timestamp", datetime.now()),
            }
        )

        # Convert timestamp to string for JSON serialization
        if "timestamp" in indicators and hasattr(indicators["timestamp"], "isoformat"):
            indicators["timestamp"] = indicators["timestamp"].isoformat()

        result.append(indicators)

    # Return enriched transactions sorted by risk
    sorted_result = sorted(result, key=lambda x: x["fraud_risk_score"], reverse=True)
    return {"result": sorted_result}


def filter_by_risk_level(enriched_transactions: list) -> dict:
    """Filter transactions by risk level and prepare summary for AI analysis.

    Args:
        enriched_transactions: List of transactions with fraud indicators

    Returns:
        Dict with 'result' key containing filtered transactions and summary
    """
    # Filter transactions by risk level
    high_risk = [t for t in enriched_transactions if t["risk_category"] == "high"]
    medium_risk = [t for t in enriched_transactions if t["risk_category"] == "medium"]
    low_risk = [t for t in enriched_transactions if t["risk_category"] == "low"]

    # Prepare summary for AI analysis
    result = {
        "high_risk_transactions": high_risk[:10],  # Limit to top 10 for AI
        "all_transactions": enriched_transactions,
        "summary": {
            "total_transactions": len(enriched_transactions),
            "high_risk_count": len(high_risk),
            "medium_risk_count": len(medium_risk),
            "low_risk_count": len(low_risk),
            "total_amount": sum(t["amount"] for t in enriched_transactions),
            "high_risk_amount": sum(t["amount"] for t in high_risk),
        },
    }

    return {"result": result}


def generate_fraud_alerts(transaction_summary: dict, ai_response: Any) -> dict:
    """Generate alerts and comprehensive fraud report.

    Args:
        transaction_summary: Filtered transactions with summary
        ai_response: AI analysis response

    Returns:
        Dict with 'result' key containing alerts and full report
    """
    # Parse AI analysis
    ai_analysis = {}
    if isinstance(ai_response, str):
        try:
            ai_analysis = json.loads(ai_response)
        except Exception:
            ai_analysis = {"analysis": ai_response}

    # Generate alerts for high-risk transactions
    alerts = []
    for trans in transaction_summary["high_risk_transactions"]:
        alert = {
            "alert_id": f"ALERT-{trans['transaction_id']}",
            "transaction_id": trans["transaction_id"],
            "customer_id": trans["customer_id"],
            "amount": trans["amount"],
            "risk_score": trans["fraud_risk_score"],
            "risk_category": trans["risk_category"],
            "indicators": {
                "velocity_count": trans["velocity_count"],
                "amount_zscore": trans["amount_zscore"],
                "unusual_time": trans["is_unusual_time"],
                "high_value": trans["is_high_value"],
            },
            "ai_recommendation": ai_analysis.get("recommended_action", "review"),
            "timestamp": datetime.now().isoformat(),
            "status": "pending_review",
        }
        alerts.append(alert)

    # Create comprehensive report
    report = {
        "alerts": alerts,
        "summary": transaction_summary["summary"],
        "ai_analysis": ai_analysis,
        "all_transactions": transaction_summary["all_transactions"],
        "generated_at": datetime.now().isoformat(),
    }

    return {"result": report}


def create_fraud_detection_workflow() -> Workflow:
    """Create a comprehensive fraud detection workflow."""
    workflow = Workflow("fraud-detection", "Real-time Fraud Detection System")

    # Step 1: Load transaction data
    transaction_reader = JSONReaderNode(
        name="transaction_reader",
        file_path=str(get_input_data_path("transactions.json", "json")),
    )
    workflow.add_node("transaction_reader", transaction_reader)

    # Step 2: Load historical customer data for baseline
    customer_reader = CSVReaderNode(
        name="customer_reader", file_path=str(get_input_data_path("customers.csv"))
    )
    workflow.add_node("customer_reader", customer_reader)

    # Step 3: Enrich transactions with fraud indicators
    fraud_enricher = PythonCodeNode.from_function(
        name="fraud_enricher", func=enrich_fraud_indicators
    )
    workflow.add_node("fraud_enricher", fraud_enricher)

    # Connect data sources
    workflow.connect(
        "transaction_reader", "fraud_enricher", mapping={"data": "transaction_data"}
    )
    workflow.connect(
        "customer_reader", "fraud_enricher", mapping={"data": "customer_data"}
    )

    # Step 4: Filter high-risk transactions for AI analysis
    risk_filter = PythonCodeNode.from_function(
        name="risk_filter", func=filter_by_risk_level
    )
    workflow.add_node("risk_filter", risk_filter)
    workflow.connect(
        "fraud_enricher", "risk_filter", mapping={"result": "enriched_transactions"}
    )

    # Step 5: AI-powered fraud analysis for high-risk transactions
    fraud_analyzer = LLMAgentNode(
        name="fraud_analyzer",
        model="gpt-4",
        system_prompt="""You are a fraud detection expert. Analyze transaction patterns and provide:
        1. Detailed fraud risk assessment
        2. Specific fraud pattern identification (account takeover, card testing, etc.)
        3. Recommended actions (block, review, allow with monitoring)
        4. Additional investigation points

        Consider factors like:
        - Transaction velocity and amounts
        - Time patterns and geographic indicators
        - Historical customer behavior
        - Known fraud patterns

        Provide your analysis in structured JSON format.""",
        prompt="Analyze these high-risk transactions for fraud patterns: {{high_risk_transactions}}",
    )
    workflow.add_node("fraud_analyzer", fraud_analyzer)

    # Connect filtered data to AI analyzer
    workflow.connect(
        "risk_filter", "fraud_analyzer", mapping={"result": "high_risk_transactions"}
    )

    # Step 6: Generate alerts and reports
    alert_generator = PythonCodeNode.from_function(
        name="alert_generator", func=generate_fraud_alerts
    )
    workflow.add_node("alert_generator", alert_generator)
    workflow.connect(
        "risk_filter", "alert_generator", mapping={"result": "transaction_summary"}
    )
    workflow.connect(
        "fraud_analyzer", "alert_generator", mapping={"response": "ai_response"}
    )

    # Step 7: Save fraud detection results
    ensure_output_dir_exists("json")
    report_writer = JSONWriterNode(
        name="report_writer",
        file_path=str(get_output_data_path("fraud_detection_report.json", "json")),
        pretty_print=True,
    )
    workflow.add_node("report_writer", report_writer)
    workflow.connect("alert_generator", "report_writer", mapping={"result": "data"})

    return workflow


def main():
    """Execute the fraud detection workflow."""
    print("🚨 Starting Fraud Detection Workflow...")

    try:
        workflow = create_fraud_detection_workflow()
        runtime = LocalRuntime()

        print("🔍 Analyzing transactions for fraud patterns...")
        results, run_id = runtime.execute(workflow)

        print("\n✅ Workflow completed successfully!")
        print(
            f"📁 Fraud report saved to: {get_output_data_path('fraud_detection_report.json', 'json')}"
        )

        # Display summary
        if "alert_generator" in results:
            report = results["alert_generator"].get("result", {})
            summary = report.get("summary", {})
            alerts = report.get("alerts", [])

            print("\n📊 Fraud Detection Summary:")
            print(
                f"   Total transactions analyzed: {summary.get('total_transactions', 0)}"
            )
            print(f"   High risk: {summary.get('high_risk_count', 0)}")
            print(f"   Medium risk: {summary.get('medium_risk_count', 0)}")
            print(f"   Low risk: {summary.get('low_risk_count', 0)}")

            if alerts:
                print(f"\n🚨 Generated {len(alerts)} fraud alerts")
                print("   Top alerts:")
                for alert in alerts[:3]:
                    print(
                        f"   - {alert['alert_id']}: ${alert['amount']:.2f} "
                        f"(Risk Score: {alert['risk_score']})"
                    )

        return results

    except Exception as e:
        print(f"❌ Error in fraud detection: {str(e)}")
        raise


if __name__ == "__main__":
    main()
