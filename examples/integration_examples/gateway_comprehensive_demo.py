"""Comprehensive Multi-Workflow Gateway Demo.

This example demonstrates a production-ready multi-workflow gateway setup with:
1. Multiple workflows for different domains
2. MCP integration for AI-powered tools
3. Proper error handling and validation
4. Real-world use cases
"""

import logging
from typing import Any, Dict

from kailash.api.gateway import WorkflowAPIGateway
from kailash.api.mcp_integration import MCPIntegration
from kailash.nodes.code import PythonCodeNode
from kailash.workflow import Workflow

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_data_processing_workflow() -> Workflow:
    """Create a data processing workflow with validation and transformation."""
    workflow = Workflow(
        workflow_id="data_proc_001",
        name="Data Processing",
        description="Validate, transform, and enrich data",
    )

    # Validation node
    validator = PythonCodeNode(
        name="data_validator",
        code="""
import json
from datetime import datetime

# Validate input data
data = input_data.get('data', [])
errors = []

if not isinstance(data, list):
    errors.append("Data must be a list")
elif len(data) == 0:
    errors.append("Data cannot be empty")
else:
    # Validate each record
    for i, record in enumerate(data):
        if not isinstance(record, dict):
            errors.append(f"Record {i} must be a dictionary")
        elif 'id' not in record:
            errors.append(f"Record {i} missing required 'id' field")

output = {
    'valid': len(errors) == 0,
    'errors': errors,
    'data': data if len(errors) == 0 else None,
    'validated_at': datetime.now().isoformat()
}
""",
    )
    workflow.add_node("validate", validator)

    # Transformation node
    transformer = PythonCodeNode(
        name="data_transformer",
        code="""
# Transform validated data
input_dict = input_data if isinstance(input_data, dict) else {'data': input_data}
data = input_dict.get('data', [])

transformed = []
for record in data:
    # Add computed fields
    transformed_record = record.copy()
    transformed_record['processed'] = True
    transformed_record['timestamp'] = datetime.now().isoformat()
    
    # Calculate risk score (example)
    value = float(record.get('value', 0))
    if value > 1000:
        transformed_record['risk_level'] = 'high'
    elif value > 500:
        transformed_record['risk_level'] = 'medium'
    else:
        transformed_record['risk_level'] = 'low'
    
    transformed.append(transformed_record)

output = {
    'transformed_data': transformed,
    'record_count': len(transformed),
    'transformation_complete': True
}
""",
    )
    workflow.add_node("transform", transformer)

    # Connect nodes
    workflow.connect("validate", "transform")

    return workflow


def create_analytics_workflow() -> Workflow:
    """Create an analytics workflow for data aggregation and insights."""
    workflow = Workflow(
        workflow_id="analytics_001",
        name="Analytics Engine",
        description="Generate insights and aggregations from data",
    )

    # Aggregation node
    aggregator = PythonCodeNode(
        name="data_aggregator",
        code="""
# Aggregate data by various dimensions
data = input_data.get('data', [])

# Initialize aggregations
aggregations = {
    'total_records': len(data),
    'by_category': {},
    'by_risk_level': {},
    'value_stats': {
        'total': 0,
        'min': float('inf'),
        'max': float('-inf'),
        'avg': 0
    }
}

# Process each record
total_value = 0
for record in data:
    # Category aggregation
    category = record.get('category', 'unknown')
    if category not in aggregations['by_category']:
        aggregations['by_category'][category] = 0
    aggregations['by_category'][category] += 1
    
    # Risk level aggregation
    risk = record.get('risk_level', 'unknown')
    if risk not in aggregations['by_risk_level']:
        aggregations['by_risk_level'][risk] = 0
    aggregations['by_risk_level'][risk] += 1
    
    # Value statistics
    value = float(record.get('value', 0))
    total_value += value
    aggregations['value_stats']['min'] = min(aggregations['value_stats']['min'], value)
    aggregations['value_stats']['max'] = max(aggregations['value_stats']['max'], value)

# Calculate average
if len(data) > 0:
    aggregations['value_stats']['avg'] = total_value / len(data)
    aggregations['value_stats']['total'] = total_value

output = aggregations
""",
    )
    workflow.add_node("aggregate", aggregator)

    # Insights generator
    insights = PythonCodeNode(
        name="insights_generator",
        code="""
# Generate insights from aggregations
agg = input_data

insights = []

# High-level insights
total = agg.get('total_records', 0)
if total > 0:
    insights.append(f"Processed {total} records")
    
    # Value insights
    stats = agg.get('value_stats', {})
    avg_value = stats.get('avg', 0)
    if avg_value > 1000:
        insights.append(f"High average value detected: ${avg_value:.2f}")
    
    # Risk insights
    risk_dist = agg.get('by_risk_level', {})
    high_risk = risk_dist.get('high', 0)
    if high_risk > total * 0.3:
        insights.append(f"Warning: {high_risk} high-risk records ({high_risk/total*100:.1f}%)")
    
    # Category insights
    categories = agg.get('by_category', {})
    if len(categories) > 5:
        insights.append(f"Data spans {len(categories)} different categories")

output = {
    'insights': insights,
    'summary': agg,
    'generated_at': datetime.now().isoformat()
}
""",
    )
    workflow.add_node("generate_insights", insights)

    # Connect nodes
    workflow.connect("aggregate", "generate_insights")

    return workflow


def create_notification_workflow() -> Workflow:
    """Create a notification workflow for alerts and reports."""
    workflow = Workflow(
        workflow_id="notif_001",
        name="Notification System",
        description="Send alerts and generate reports",
    )

    # Alert checker
    alert_checker = PythonCodeNode(
        name="check_alerts",
        code="""
# Check for alert conditions
data = input_data.get('insights', {})
summary = data.get('summary', {})
insights_list = data.get('insights', [])

alerts = []
notifications = []

# Check for critical conditions
risk_levels = summary.get('by_risk_level', {})
high_risk_count = risk_levels.get('high', 0)
total = summary.get('total_records', 0)

if high_risk_count > 10:
    alerts.append({
        'level': 'critical',
        'message': f'{high_risk_count} high-risk records detected',
        'timestamp': datetime.now().isoformat()
    })

# Check value thresholds
value_stats = summary.get('value_stats', {})
max_value = value_stats.get('max', 0)
if max_value > 10000:
    alerts.append({
        'level': 'warning',
        'message': f'Maximum value exceeds threshold: ${max_value:.2f}',
        'timestamp': datetime.now().isoformat()
    })

# Create notifications
for insight in insights_list:
    notifications.append({
        'type': 'insight',
        'message': insight,
        'timestamp': datetime.now().isoformat()
    })

output = {
    'alerts': alerts,
    'notifications': notifications,
    'alert_count': len(alerts),
    'should_notify': len(alerts) > 0
}
""",
    )
    workflow.add_node("check_alerts", alert_checker)

    # Report generator
    report_gen = PythonCodeNode(
        name="generate_report",
        code="""
# Generate formatted report
alert_data = input_data
summary = alert_data.get('summary', {}) if 'summary' not in alert_data else input_data.get('summary', {})

report = {
    'title': 'Data Processing Report',
    'generated_at': datetime.now().isoformat(),
    'sections': []
}

# Executive summary
exec_summary = {
    'title': 'Executive Summary',
    'content': []
}

if alert_data.get('alert_count', 0) > 0:
    exec_summary['content'].append(f"⚠️ {alert_data['alert_count']} alerts require attention")

total_records = summary.get('total_records', 0) if summary else 0
exec_summary['content'].append(f"📊 Processed {total_records} records")

report['sections'].append(exec_summary)

# Alerts section
if alert_data.get('alerts'):
    alerts_section = {
        'title': 'Alerts',
        'content': []
    }
    for alert in alert_data['alerts']:
        alerts_section['content'].append(f"[{alert['level'].upper()}] {alert['message']}")
    report['sections'].append(alerts_section)

# Statistics section
if summary and 'value_stats' in summary:
    stats = summary['value_stats']
    stats_section = {
        'title': 'Value Statistics',
        'content': [
            f"Total: ${stats.get('total', 0):,.2f}",
            f"Average: ${stats.get('avg', 0):,.2f}",
            f"Range: ${stats.get('min', 0):,.2f} - ${stats.get('max', 0):,.2f}"
        ]
    }
    report['sections'].append(stats_section)

output = report
""",
    )
    workflow.add_node("generate_report", report_gen)

    # Connect nodes
    workflow.connect("check_alerts", "generate_report")

    return workflow


def create_mcp_tools() -> MCPIntegration:
    """Create MCP server with AI-powered analysis tools."""
    mcp = MCPIntegration("ai_analyst", "AI-powered data analysis tools")

    # Anomaly detection tool
    def detect_anomalies(data: list, sensitivity: float = 0.8) -> Dict[str, Any]:
        """Detect anomalies in data (simplified simulation)."""
        anomalies = []

        # Calculate statistics
        values = [float(record.get("value", 0)) for record in data if "value" in record]
        if not values:
            return {"anomalies": [], "anomaly_count": 0}

        avg = sum(values) / len(values)
        std_dev = (sum((x - avg) ** 2 for x in values) / len(values)) ** 0.5

        # Detect outliers
        threshold = avg + (2 * std_dev * sensitivity)

        for i, record in enumerate(data):
            value = float(record.get("value", 0))
            if value > threshold:
                anomalies.append(
                    {
                        "index": i,
                        "record_id": record.get("id", f"record_{i}"),
                        "value": value,
                        "deviation": (value - avg) / std_dev,
                        "reason": "Value exceeds threshold",
                    }
                )

        return {
            "anomalies": anomalies,
            "anomaly_count": len(anomalies),
            "threshold_used": threshold,
            "statistics": {"mean": avg, "std_dev": std_dev, "sensitivity": sensitivity},
        }

    mcp.add_tool(
        "anomaly_detection",
        detect_anomalies,
        "Detect anomalies in numerical data",
        {
            "data": {"type": "array", "required": True},
            "sensitivity": {"type": "number", "default": 0.8},
        },
    )

    # Pattern recognition tool
    def recognize_patterns(data: list, pattern_type: str = "trend") -> Dict[str, Any]:
        """Recognize patterns in data (simplified)."""
        patterns = []

        if pattern_type == "trend":
            # Simple trend detection
            values = [
                float(record.get("value", 0)) for record in data if "value" in record
            ]
            if len(values) > 2:
                # Calculate simple moving average
                window = min(5, len(values))
                for i in range(len(values) - window + 1):
                    window_values = values[i : i + window]
                    avg = sum(window_values) / window

                    # Detect upward/downward trends
                    if i > 0:
                        prev_avg = sum(values[i - 1 : i - 1 + window]) / window
                        if avg > prev_avg * 1.1:
                            patterns.append(
                                {
                                    "type": "upward_trend",
                                    "position": i,
                                    "strength": (avg - prev_avg) / prev_avg,
                                }
                            )
                        elif avg < prev_avg * 0.9:
                            patterns.append(
                                {
                                    "type": "downward_trend",
                                    "position": i,
                                    "strength": (prev_avg - avg) / prev_avg,
                                }
                            )

        return {
            "patterns": patterns,
            "pattern_count": len(patterns),
            "pattern_type": pattern_type,
        }

    mcp.add_tool(
        "pattern_recognition",
        recognize_patterns,
        "Recognize patterns in data sequences",
        {
            "data": {"type": "array", "required": True},
            "pattern_type": {"type": "string", "default": "trend"},
        },
    )

    return mcp


def main():
    """Run the comprehensive gateway demo."""
    print("=== Comprehensive Multi-Workflow Gateway Demo ===\n")

    # Create MCP server
    print("Setting up AI-powered MCP tools...")
    mcp_server = create_mcp_tools()
    print(f"✓ Created MCP server with {len(mcp_server.tools)} AI tools\n")

    # Create gateway
    gateway = WorkflowAPIGateway(
        title="Enterprise Data Platform",
        description="Unified platform for data processing, analytics, and insights",
        version="3.0.0",
        max_workers=15,
    )

    # Register MCP server
    gateway.register_mcp_server("ai_analyst", mcp_server)

    # Register workflows
    print("Registering workflows...")

    gateway.register_workflow(
        "process",
        create_data_processing_workflow(),
        description="Data validation and transformation pipeline",
        tags=["data", "validation", "transformation"],
    )

    gateway.register_workflow(
        "analyze",
        create_analytics_workflow(),
        description="Analytics and insights generation",
        tags=["analytics", "aggregation", "insights"],
    )

    gateway.register_workflow(
        "notify",
        create_notification_workflow(),
        description="Alert detection and report generation",
        tags=["alerts", "notifications", "reports"],
    )

    print("✓ Registered 3 core workflows\n")

    # Display platform information
    print("Platform Overview:")
    print("=" * 60)
    print(f"Title: {gateway.app.title}")
    print(f"Version: {gateway.app.version}")
    print(f"Workflows: {len(gateway.workflows)}")
    print(f"MCP Tools: {len(mcp_server.tools)}")
    print()

    print("Available Endpoints:")
    print("-" * 60)
    print("Platform:")
    print("  GET  /              - Platform information")
    print("  GET  /workflows     - List all workflows")
    print("  GET  /health        - Health status")
    print("  WS   /ws            - WebSocket for real-time updates")
    print()

    for name, reg in gateway.workflows.items():
        print(f"{name.upper()} Workflow ({reg.description}):")
        print(f"  POST /{name}/execute       - Execute workflow")
        print(f"  GET  /{name}/workflow/info - Workflow information")
        print(f"  GET  /{name}/health        - Workflow health")
        print(f"  GET  /{name}/docs          - Interactive API docs")
        print()

    print("Example Workflow Chain:")
    print("-" * 60)
    print("1. Process data:")
    print("curl -X POST http://localhost:8000/process/execute \\")
    print('  -H "Content-Type: application/json" \\')
    print("  -d '{")
    print('    "validate": {')
    print('      "data": [')
    print('        {"id": 1, "value": 1500, "category": "electronics"},')
    print('        {"id": 2, "value": 750, "category": "clothing"},')
    print('        {"id": 3, "value": 2500, "category": "electronics"}')
    print("      ]")
    print("    }")
    print("  }'")
    print()
    print("2. Analyze results:")
    print("curl -X POST http://localhost:8000/analyze/execute \\")
    print('  -H "Content-Type: application/json" \\')
    print('  -d \'{"aggregate": {"data": <processed_data>}}\'')
    print()
    print("3. Generate notifications:")
    print("curl -X POST http://localhost:8000/notify/execute \\")
    print('  -H "Content-Type: application/json" \\')
    print('  -d \'{"check_alerts": {"insights": <analysis_results>}}\'')

    return gateway


if __name__ == "__main__":
    gateway = main()

    print("\n\n" + "=" * 60)
    print("Gateway Configuration Complete!")
    print("=" * 60)
    print()
    print("The Enterprise Data Platform is ready with:")
    print(f"  ✓ {len(gateway.workflows)} production-ready workflows")
    print(f"  ✓ {len(gateway.mcp_servers)} MCP servers with AI tools")
    print("  ✓ Real-time WebSocket support")
    print("  ✓ Comprehensive error handling")
    print("  ✓ Interactive API documentation")
    print()
    print("To start the server:")
    print("  gateway.run(host='0.0.0.0', port=8000)")
    print()
    print("Then access:")
    print("  - Platform API: http://localhost:8000")
    print("  - Interactive docs: http://localhost:8000/docs")
    print("  - Workflow-specific docs: http://localhost:8000/<workflow>/docs")
