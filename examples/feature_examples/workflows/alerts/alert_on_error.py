#!/usr/bin/env python3
"""
Alert on Error Workflow Example

This example demonstrates error handling patterns with Discord alerts:
- Try-catch error handling with alerts
- Conditional alerts based on workflow status
- Error context and debugging information
- Batch job monitoring with alerts

Environment Setup:
    export DISCORD_WEBHOOK="https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE"
"""

import os
import random
from datetime import datetime

from kailash import Workflow
from kailash.nodes.alerts import DiscordAlertNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.logic import SwitchNode


def error_handling_workflow():
    """Workflow that alerts when errors occur during processing."""

    workflow = Workflow(name="error_handling_alerts")

    # Simulate data processing that might fail
    processor = workflow.add_node(
        PythonCodeNode.from_function(
            id="risky_processor",
            name="RiskyProcessorNode",
            func=lambda data: process_with_potential_error(data),
            inputs=["data"],
            outputs=["result", "status", "error_message", "processed_count"],
        )
    )

    # Switch based on processing status
    status_switch = workflow.add_node(
        SwitchNode(id="check_status", name="StatusSwitchNode", switch_on="status")
    )

    # Success alert
    success_alert = workflow.add_node(
        DiscordAlertNode(
            id="success_alert",
            name="SuccessAlertNode",
            webhook_url="${DISCORD_WEBHOOK}",
            embed=True,
            color=0x28A745,  # Green
        )
    )

    # Error alert with detailed context
    error_alert = workflow.add_node(
        DiscordAlertNode(
            id="error_alert",
            name="ErrorAlertNode",
            webhook_url="${DISCORD_WEBHOOK}",
            embed=True,
            mentions=["@here"],  # Notify team
            footer_text="Error Handler v1.0",
        )
    )

    # Connect nodes
    workflow.connect(processor, status_switch, mapping={"status": "switch_value"})
    workflow.connect(
        status_switch,
        success_alert,
        output_key="success",
        mapping={
            "processed_count": "context.Records Processed",
            "result": "context.Summary",
        },
    )
    workflow.connect(
        status_switch,
        error_alert,
        output_key="error",
        mapping={
            "error_message": "message",
            "processed_count": "context.Records Processed Before Error",
        },
    )

    # Run with sample data
    print("Running error handling workflow...")
    sample_data = [
        {"id": 1, "value": 100},
        {"id": 2, "value": 200},
        {"id": 3, "value": 300},
        {"id": 4, "value": -50},  # This might cause an error
        {"id": 5, "value": 150},
    ]

    results = workflow.run(
        risky_processor={"data": sample_data},
        success_alert={"title": "✅ Data Processing Complete", "alert_type": "success"},
        error_alert={
            "title": "❌ Data Processing Failed",
            "alert_type": "error",
            "context": {
                "Workflow": "error_handling_alerts",
                "Time": datetime.now().isoformat(),
            },
        },
    )

    print(f"Processing status: {results['risky_processor']['status']}")


def batch_job_monitoring():
    """Monitor a batch job and send appropriate alerts."""

    workflow = Workflow(name="batch_job_monitor")

    # Simulate batch job stages
    # Stage 1: Data Loading
    data_loader = workflow.add_node(
        PythonCodeNode.from_function(
            id="load_data",
            name="DataLoaderNode",
            func=lambda: {
                "records_loaded": 5000,
                "load_time": "45s",
                "status": "success",
            },
            inputs=[],
            outputs=["records_loaded", "load_time", "status"],
        )
    )

    # Stage 2: Data Validation
    validator = workflow.add_node(
        PythonCodeNode.from_function(
            id="validate_data",
            name="DataValidatorNode",
            func=lambda records: validate_batch_data(records),
            inputs=["records_loaded"],
            outputs=["valid_records", "invalid_records", "validation_errors", "status"],
        )
    )

    # Stage 3: Data Processing
    processor = workflow.add_node(
        PythonCodeNode.from_function(
            id="process_data",
            name="DataProcessorNode",
            func=lambda valid_records: {
                "processed": valid_records,
                "transformations": 12,
                "process_time": "2m 15s",
                "status": "success" if valid_records > 4500 else "warning",
            },
            inputs=["valid_records"],
            outputs=["processed", "transformations", "process_time", "status"],
        )
    )

    # Create job summary
    summarizer = workflow.add_node(
        PythonCodeNode.from_function(
            id="create_summary",
            name="JobSummaryNode",
            func=lambda load_data, validate_data, process_data: create_job_summary(
                load_data, validate_data, process_data
            ),
            inputs=["load_data", "validate_data", "process_data"],
            outputs=["summary", "overall_status", "alert_type", "metrics"],
        )
    )

    # Send summary alert
    job_alert = workflow.add_node(
        DiscordAlertNode(
            id="job_summary_alert",
            name="JobSummaryAlertNode",
            webhook_url="${DISCORD_WEBHOOK}",
            username="Batch Job Monitor",
            embed=True,
            timestamp=True,
        )
    )

    # Connect workflow
    workflow.connect(
        data_loader, validator, mapping={"records_loaded": "records_loaded"}
    )
    workflow.connect(validator, processor, mapping={"valid_records": "valid_records"})
    workflow.connect(data_loader, summarizer, mapping={"output": "load_data"})
    workflow.connect(validator, summarizer, mapping={"output": "validate_data"})
    workflow.connect(processor, summarizer, mapping={"output": "process_data"})
    workflow.connect(
        summarizer,
        job_alert,
        mapping={"alert_type": "alert_type", "summary": "message", "metrics": "fields"},
    )

    # Run batch job
    print("\nRunning batch job with monitoring...")
    results = workflow.run(
        job_summary_alert={"title": "📊 Batch Job: Customer Data ETL"}
    )

    print(f"Job status: {results['create_summary']['overall_status']}")


def multi_stage_alert_escalation():
    """Demonstrate alert escalation for critical issues."""

    workflow = Workflow(name="alert_escalation")

    # Monitor critical service
    service_monitor = workflow.add_node(
        PythonCodeNode.from_function(
            id="monitor_service",
            name="ServiceMonitorNode",
            func=lambda: {
                "service": "Payment Gateway",
                "status": "down",
                "downtime_minutes": 15,
                "affected_transactions": 342,
                "estimated_revenue_loss": 15000,
            },
            inputs=[],
            outputs=[
                "service",
                "status",
                "downtime_minutes",
                "affected_transactions",
                "estimated_revenue_loss",
            ],
        )
    )

    # Level 1 Alert - Engineering Team
    eng_alert = workflow.add_node(
        DiscordAlertNode(
            id="engineering_alert",
            name="EngineeringAlertNode",
            webhook_url="${DISCORD_WEBHOOK}",
            embed=True,
            color=0xFFA500,  # Orange warning
            mentions=["@here"],
        )
    )

    # Level 2 Alert - Management (if downtime > 10 min)
    mgmt_alert = workflow.add_node(
        DiscordAlertNode(
            id="management_alert",
            name="ManagementAlertNode",
            webhook_url="${DISCORD_WEBHOOK}",
            embed=True,
            color=0xFF0000,  # Red critical
            username="Critical Alert Bot",
            mentions=["@everyone"],
        )
    )

    # Connect with escalation logic
    workflow.connect(service_monitor, eng_alert)
    workflow.connect(service_monitor, mgmt_alert)

    # Run escalation
    print("\nRunning alert escalation example...")
    results = workflow.run(
        engineering_alert={
            "title": "⚠️ Service Degradation Detected",
            "alert_type": "warning",
            "fields": [
                {"name": "Service", "value": "{service}", "inline": True},
                {"name": "Status", "value": "{status}", "inline": True},
                {
                    "name": "Downtime",
                    "value": "{downtime_minutes} minutes",
                    "inline": True,
                },
                {
                    "name": "Affected Transactions",
                    "value": "{affected_transactions}",
                    "inline": False,
                },
            ],
        },
        management_alert={
            "title": "🚨 CRITICAL: Extended Service Outage",
            "alert_type": "critical",
            "message": "Immediate action required - significant business impact",
            "fields": [
                {"name": "Service", "value": "{service}", "inline": True},
                {
                    "name": "Downtime",
                    "value": "{downtime_minutes} minutes",
                    "inline": True,
                },
                {
                    "name": "Revenue Impact",
                    "value": "${estimated_revenue_loss:,}",
                    "inline": True,
                },
                {
                    "name": "Affected Transactions",
                    "value": "{affected_transactions}",
                    "inline": False,
                },
            ],
            "footer_text": "Escalation Level 2 - Management Notification",
        },
    )


# Helper functions
def process_with_potential_error(data):
    """Simulate processing that might fail."""
    try:
        processed_count = 0
        results = []

        for item in data:
            if item.get("value", 0) < 0:
                # Simulate an error condition
                raise ValueError(f"Negative value not allowed: {item['value']}")

            results.append(item["value"] * 2)
            processed_count += 1

        return {
            "result": results,
            "status": "success",
            "error_message": None,
            "processed_count": processed_count,
        }
    except Exception as e:
        return {
            "result": None,
            "status": "error",
            "error_message": str(e),
            "processed_count": processed_count,
        }


def validate_batch_data(records_loaded):
    """Simulate data validation."""
    # Random validation results for demo
    invalid_pct = random.uniform(0.02, 0.08)  # 2-8% invalid
    invalid_records = int(records_loaded * invalid_pct)
    valid_records = records_loaded - invalid_records

    validation_errors = []
    if invalid_records > 0:
        validation_errors = [
            f"Missing required field: {invalid_records // 3} records",
            f"Invalid date format: {invalid_records // 3} records",
            f"Duplicate entries: {invalid_records - (2 * invalid_records // 3)} records",
        ]

    return {
        "valid_records": valid_records,
        "invalid_records": invalid_records,
        "validation_errors": validation_errors,
        "status": "warning" if invalid_records > 250 else "success",
    }


def create_job_summary(load_data, validate_data, process_data):
    """Create batch job summary."""
    # Determine overall status
    statuses = [load_data["status"], validate_data["status"], process_data["status"]]
    if "error" in statuses:
        overall_status = "error"
        alert_type = "error"
    elif "warning" in statuses:
        overall_status = "completed_with_warnings"
        alert_type = "warning"
    else:
        overall_status = "success"
        alert_type = "success"

    # Create summary
    summary = f"Batch job completed with status: **{overall_status.upper()}**"

    # Create metrics fields
    metrics = [
        {
            "name": "📥 Records Loaded",
            "value": f"{load_data['records_loaded']:,}",
            "inline": True,
        },
        {
            "name": "✅ Valid Records",
            "value": f"{validate_data['valid_records']:,}",
            "inline": True,
        },
        {
            "name": "❌ Invalid Records",
            "value": f"{validate_data['invalid_records']:,}",
            "inline": True,
        },
        {
            "name": "⚙️ Processed",
            "value": f"{process_data['processed']:,}",
            "inline": True,
        },
        {
            "name": "⏱️ Total Time",
            "value": f"{load_data['load_time']} + {process_data['process_time']}",
            "inline": True,
        },
        {
            "name": "📊 Status",
            "value": overall_status.replace("_", " ").title(),
            "inline": True,
        },
    ]

    if validate_data["validation_errors"]:
        metrics.append(
            {
                "name": "⚠️ Validation Issues",
                "value": "\n".join(validate_data["validation_errors"]),
                "inline": False,
            }
        )

    return {
        "summary": summary,
        "overall_status": overall_status,
        "alert_type": alert_type,
        "metrics": metrics,
    }


def main():
    """Run all examples."""

    # Check for webhook URL
    if not os.getenv("DISCORD_WEBHOOK"):
        print("ERROR: Please set DISCORD_WEBHOOK environment variable")
        print("Example: export DISCORD_WEBHOOK='https://discord.com/api/webhooks/...'")
        return

    print("Alert on Error Workflow Examples")
    print("=" * 50)

    # Run examples
    error_handling_workflow()
    print("\n" + "-" * 50)

    batch_job_monitoring()
    print("\n" + "-" * 50)

    multi_stage_alert_escalation()

    print("\nAll examples completed!")


if __name__ == "__main__":
    main()
