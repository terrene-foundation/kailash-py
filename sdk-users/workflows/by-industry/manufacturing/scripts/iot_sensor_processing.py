"""
IoT Sensor Processing Workflow

This workflow demonstrates real-time IoT sensor data processing for manufacturing:
1. Reads sensor data from multiple sources
2. Normalizes and aggregates sensor readings
3. Detects anomalies and generates alerts
4. Triggers predictive maintenance recommendations
5. Stores processed data for historical analysis

Real-world use case: Manufacturing plant monitoring system that processes
sensor data from production equipment to prevent failures and optimize performance.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add the src directory to the path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../src"))
)

from kailash.nodes import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.nodes.logic import SwitchNode
from kailash.nodes.transform import DataTransformer
from kailash.workflow import Workflow, WorkflowBuilder

# Import data path utilities
project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../../../")
)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


# Define data path utilities inline for simplicity
def get_input_data_path(relative_path):
    """Get the full path for input data files."""
    return os.path.join(project_root, "data", "inputs", relative_path)


def get_output_data_path(relative_path):
    """Get the full path for output data files."""
    return os.path.join(project_root, "data", "outputs", relative_path)


def ensure_output_dir_exists():
    """Ensure output directory exists."""
    output_dir = os.path.join(project_root, "data", "outputs", "manufacturing", "iot")
    os.makedirs(output_dir, exist_ok=True)


def analyze_sensor_anomalies(sensor_data):
    """
    Analyze sensor data for anomalies using statistical methods.
    Returns enriched data with anomaly scores and maintenance recommendations.
    """
    import numpy as np
    import pandas as pd

    print(f"\n🔍 DEBUG: AnomalyAnalyzer received data type: {type(sensor_data)}")
    print(
        f"🔍 DEBUG: AnomalyAnalyzer data length: {len(sensor_data) if sensor_data else 'None'}"
    )

    # Convert to DataFrame for easier analysis
    df = pd.DataFrame(sensor_data)

    # Define normal operating ranges
    thresholds = {
        "temperature_celsius": {"min": 65, "max": 80, "critical": 85},
        "pressure_bar": {"min": 2.0, "max": 2.8, "critical": 3.0},
        "vibration_hz": {"min": 40, "max": 55, "critical": 60},
        "rpm": {"min": 1400, "max": 1550, "critical": 1600},
        "power_kw": {"min": 38, "max": 50, "critical": 55},
    }

    # Calculate anomaly scores
    anomalies = []

    for _, row in df.iterrows():
        anomaly_score = 0
        issues = []
        recommendations = []

        # Check each parameter
        for param, limits in thresholds.items():
            if param in row:
                value = float(row[param])

                # Critical threshold check
                if value >= limits.get("critical", float("inf")):
                    anomaly_score += 3
                    issues.append(f"{param} CRITICAL: {value}")
                    recommendations.append(f"Immediate inspection required for {param}")

                # Normal range check
                elif value < limits["min"] or value > limits["max"]:
                    anomaly_score += 1
                    issues.append(f"{param} out of range: {value}")
                    recommendations.append(f"Monitor {param} closely")

        # Trend analysis (simplified for this example)
        if row["status"] == "warning":
            anomaly_score += 1
            recommendations.append("Schedule preventive maintenance")
        elif row["status"] == "critical":
            anomaly_score += 2
            recommendations.append("Immediate maintenance required")

        # Add analysis results
        anomaly_data = {
            "sensor_id": row["sensor_id"],
            "timestamp": row["timestamp"],
            "anomaly_score": anomaly_score,
            "status": (
                "critical"
                if anomaly_score >= 3
                else "warning" if anomaly_score >= 1 else "normal"
            ),
            "issues": issues,
            "recommendations": recommendations,
            "original_data": dict(row),
        }

        anomalies.append(anomaly_data)

    print(f"🔍 DEBUG: AnomalyAnalyzer returning {len(anomalies)} anomaly records")
    return anomalies


def aggregate_sensor_metrics(anomaly_data):
    """
    Aggregate sensor metrics by sensor ID and calculate statistics.
    """
    import statistics
    from collections import defaultdict

    print(f"\n🔍 DEBUG: MetricAggregator received data type: {type(anomaly_data)}")
    print(
        f"🔍 DEBUG: MetricAggregator data length: {len(anomaly_data) if anomaly_data else 'None'}"
    )

    # Group by sensor
    sensor_groups = defaultdict(list)
    for record in anomaly_data:
        sensor_groups[record["sensor_id"]].append(record)

    # Calculate aggregated metrics
    aggregated = []

    for sensor_id, records in sensor_groups.items():
        # Extract numeric values for statistics
        temps = [float(r["original_data"]["temperature_celsius"]) for r in records]
        pressures = [float(r["original_data"]["pressure_bar"]) for r in records]
        anomaly_scores = [r["anomaly_score"] for r in records]

        # Count status types
        status_counts = defaultdict(int)
        for r in records:
            status_counts[r["status"]] += 1

        # Build aggregated record
        agg_record = {
            "sensor_id": sensor_id,
            "reading_count": len(records),
            "avg_temperature": round(statistics.mean(temps), 2),
            "max_temperature": max(temps),
            "avg_pressure": round(statistics.mean(pressures), 2),
            "max_pressure": max(pressures),
            "avg_anomaly_score": round(statistics.mean(anomaly_scores), 2),
            "critical_count": status_counts.get("critical", 0),
            "warning_count": status_counts.get("warning", 0),
            "normal_count": status_counts.get("normal", 0),
            "health_score": round(
                100 - (statistics.mean(anomaly_scores) * 20), 1
            ),  # Simple health metric
            "maintenance_priority": (
                "high"
                if status_counts.get("critical", 0) > 0
                else "medium" if status_counts.get("warning", 0) > 0 else "low"
            ),
            "last_reading": records[-1]["timestamp"],
        }

        aggregated.append(agg_record)

    print(f"🔍 DEBUG: MetricAggregator returning {len(aggregated)} aggregated records")
    return aggregated


def generate_maintenance_report(aggregated_data):
    """
    Generate a comprehensive maintenance report based on aggregated sensor data.
    """
    print(
        f"\n🔍 DEBUG: MaintenanceReportGenerator received data type: {type(aggregated_data)}"
    )
    print(
        f"🔍 DEBUG: MaintenanceReportGenerator data length: {len(aggregated_data) if aggregated_data else 'None'}"
    )

    if not aggregated_data:
        print("⚠️  DEBUG: No aggregated data received!")
        # Return empty report instead of error to satisfy node output requirements
        return {
            "report_timestamp": datetime.now().isoformat(),
            "summary": {
                "total_sensors": 0,
                "sensors_needing_attention": 0,
                "critical_sensors": 0,
                "overall_health": 0,
            },
            "sensor_details": [],
            "recommendations": [],
        }

    report = {
        "report_timestamp": datetime.now().isoformat(),
        "summary": {
            "total_sensors": len(aggregated_data),
            "sensors_needing_attention": sum(
                1 for s in aggregated_data if s["maintenance_priority"] != "low"
            ),
            "critical_sensors": sum(
                1 for s in aggregated_data if s["maintenance_priority"] == "high"
            ),
            "overall_health": (
                round(
                    sum(s["health_score"] for s in aggregated_data)
                    / len(aggregated_data),
                    1,
                )
                if aggregated_data
                else 0
            ),
        },
        "sensor_details": aggregated_data,
        "recommendations": [],
    }

    # Generate recommendations
    for sensor in aggregated_data:
        if sensor["maintenance_priority"] == "high":
            report["recommendations"].append(
                {
                    "sensor_id": sensor["sensor_id"],
                    "priority": "IMMEDIATE",
                    "action": f"Inspect and service {sensor['sensor_id']} - Critical readings detected",
                    "health_score": sensor["health_score"],
                }
            )
        elif sensor["maintenance_priority"] == "medium":
            report["recommendations"].append(
                {
                    "sensor_id": sensor["sensor_id"],
                    "priority": "SCHEDULED",
                    "action": f"Schedule maintenance for {sensor['sensor_id']} - Warning signs detected",
                    "health_score": sensor["health_score"],
                }
            )

    # Sort recommendations by priority
    report["recommendations"].sort(
        key=lambda x: (x["priority"] != "IMMEDIATE", x["health_score"])
    )

    print(
        f"🔍 DEBUG: MaintenanceReportGenerator returning report with {len(report['recommendations'])} recommendations"
    )
    print(f"🔍 DEBUG: Report type: {type(report)}, has content: {bool(report)}")

    # Return the report data as individual outputs to match PythonCodeNode expectations
    return {
        "result": report,  # This ensures the 'result' output exists
        "summary": report["summary"],
        "recommendations": report["recommendations"],
    }


def send_critical_alert(data):
    """
    Simulate sending critical alerts to maintenance team.
    """
    print(f"\n🔍 DEBUG: CriticalAlertSender received data type: {type(data)}")
    print(f"🔍 DEBUG: CriticalAlertSender data length: {len(data) if data else 'None'}")

    # Extract critical sensors - data is directly the list of aggregated metrics
    critical_sensors = [s for s in data if s.get("maintenance_priority") == "high"]

    if critical_sensors:
        alert = {
            "alert_type": "CRITICAL_MAINTENANCE",
            "timestamp": datetime.now().isoformat(),
            "recipient": "maintenance-team@manufacturing.com",
            "subject": f"CRITICAL: {len(critical_sensors)} sensors require immediate attention",
            "sensors": [
                {"id": s["sensor_id"], "health_score": s["health_score"]}
                for s in critical_sensors
            ],
            "message": "Immediate maintenance required to prevent equipment failure!",
        }

        # In production, this would send an actual notification
        # For now, we'll save it as part of the output
        print(
            f"\n⚠️  CRITICAL ALERT: {len(critical_sensors)} sensors need immediate attention!"
        )
        return {"result": alert}

    return {"result": {"status": "no_alerts", "timestamp": datetime.now().isoformat()}}


def create_iot_sensor_workflow():
    """Create the IoT sensor processing workflow."""

    # Create workflow
    workflow = Workflow(
        workflow_id="iot-sensor-processing", name="IoT Sensor Processing"
    )

    # Add nodes

    # 1. Read sensor data
    workflow.add_node(
        "SensorDataReader",
        CSVReaderNode(
            file_path=get_input_data_path("manufacturing/sensor_readings.csv")
        ),
    )

    # 2. Analyze for anomalies
    workflow.add_node(
        "AnomalyAnalyzer",
        PythonCodeNode.from_function(
            func=analyze_sensor_anomalies, input_mapping={"sensor_data": "data"}
        ),
    )

    # 3. Aggregate metrics
    workflow.add_node(
        "MetricAggregator",
        PythonCodeNode.from_function(
            func=aggregate_sensor_metrics, input_mapping={"anomaly_data": "result"}
        ),
    )

    # 4. Generate maintenance report
    from kailash.nodes.base import NodeParameter

    workflow.add_node(
        "MaintenanceReportGenerator",
        PythonCodeNode.from_function(
            func=generate_maintenance_report,
            input_mapping={"aggregated_data": "result"},
            output_schema={
                "result": NodeParameter(
                    name="result",
                    type=dict,
                    required=True,
                    description="Maintenance report",
                )
            },
        ),
    )

    # 5. Send critical alerts
    workflow.add_node(
        "CriticalAlertSender", PythonCodeNode.from_function(func=send_critical_alert)
    )

    # 6. Write anomaly data
    ensure_output_dir_exists()
    workflow.add_node(
        "AnomalyDataWriter",
        JSONWriterNode(
            file_path=get_output_data_path("manufacturing/iot/anomaly_analysis.json")
        ),
    )

    # 7. Write maintenance report
    workflow.add_node(
        "MaintenanceReportWriter",
        JSONWriterNode(
            file_path=get_output_data_path("manufacturing/iot/maintenance_report.json")
        ),
    )

    # 8. Write alert status
    workflow.add_node(
        "AlertStatusWriter",
        JSONWriterNode(
            file_path=get_output_data_path("manufacturing/iot/alert_status.json")
        ),
    )

    # Connect the workflow
    workflow.connect("SensorDataReader", "AnomalyAnalyzer", {"data": "sensor_data"})
    workflow.connect("AnomalyAnalyzer", "AnomalyDataWriter", {"result": "data"})
    workflow.connect("AnomalyAnalyzer", "MetricAggregator", {"result": "anomaly_data"})
    workflow.connect(
        "MetricAggregator", "MaintenanceReportGenerator", {"result": "aggregated_data"}
    )
    workflow.connect("MetricAggregator", "CriticalAlertSender", {"result": "data"})
    workflow.connect(
        "MaintenanceReportGenerator", "MaintenanceReportWriter", {"result": "data"}
    )
    workflow.connect("CriticalAlertSender", "AlertStatusWriter", {"result": "data"})

    # Validate workflow
    workflow.validate()

    return workflow


def main():
    """Execute the IoT sensor processing workflow."""
    print("=" * 80)
    print("IoT Sensor Processing Workflow - Manufacturing")
    print("=" * 80)

    # Create and run workflow
    workflow = create_iot_sensor_workflow()

    # Execute workflow
    from kailash.runtime.local import LocalRuntime

    runtime = LocalRuntime()
    result = runtime.execute(workflow)

    print(f"\n🔍 DEBUG: Result type: {type(result)}")
    print(f"🔍 DEBUG: Result content: {result}")

    # Handle tuple return format (outputs, status)
    if isinstance(result, tuple):
        outputs, status = result
        print(
            "Workflow Status: completed"
        )  # The presence of outputs means it completed
        print(f"🔍 DEBUG: Output keys: {list(outputs.keys()) if outputs else 'None'}")
    else:
        print(f"Workflow Status: {result['status']}")
        print(f"🔍 DEBUG: Result keys: {list(result.keys())}")
        if "outputs" in result:
            print(f"🔍 DEBUG: Output nodes: {list(result['outputs'].keys())}")
            outputs = result["outputs"]
        else:
            outputs = result
        status = result["status"]

    # Display results
    # For tuple results, we assume completion if we have outputs
    if (isinstance(result, tuple) and outputs) or (
        not isinstance(result, tuple) and result.get("status") == "completed"
    ):
        print("\n📊 Sensor Analysis Summary:")

        # Get the maintenance report
        report_data = outputs.get("MaintenanceReportWriter", {}).get("written_data", {})

        print(
            f"🔍 DEBUG: MaintenanceReportWriter output: {report_data is not None and bool(report_data)}"
        )
        print(
            f"🔍 DEBUG: Report data keys: {list(report_data.keys()) if report_data else 'None'}"
        )

        if report_data:
            summary = report_data.get("summary", {})
            print(f"  Total Sensors: {summary.get('total_sensors', 0)}")
            print(
                f"  Sensors Needing Attention: {summary.get('sensors_needing_attention', 0)}"
            )
            print(f"  Critical Sensors: {summary.get('critical_sensors', 0)}")
            print(f"  Overall Health Score: {summary.get('overall_health', 0)}%")

            # Show recommendations
            recommendations = report_data.get("recommendations", [])
            if recommendations:
                print("\n🔧 Maintenance Recommendations:")
                for i, rec in enumerate(recommendations[:5], 1):  # Show top 5
                    print(
                        f"  {i}. [{rec['priority']}] {rec['sensor_id']}: {rec['action']}"
                    )
                    print(f"     Health Score: {rec['health_score']}%")

        # Check if alerts were triggered
        alert_status = outputs.get("AlertStatusWriter", {}).get("written_data", {})
        if alert_status and alert_status.get("alert_type") == "CRITICAL_MAINTENANCE":
            print("\n⚠️  CRITICAL ALERTS TRIGGERED!")

        print(f"\n✅ Reports saved to: {get_output_data_path('manufacturing/iot/')}")

    else:
        if isinstance(result, tuple):
            print(f"\n❌ Workflow failed: {outputs.get('error', 'Unknown error')}")
            if "node_errors" in outputs:
                for node, error in outputs["node_errors"].items():
                    print(f"  - {node}: {error}")
        else:
            print(f"\n❌ Workflow failed: {result.get('error', 'Unknown error')}")
            if "node_errors" in result:
                for node, error in result["node_errors"].items():
                    print(f"  - {node}: {error}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
