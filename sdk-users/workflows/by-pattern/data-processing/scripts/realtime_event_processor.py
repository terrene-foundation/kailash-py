#!/usr/bin/env python3
"""
Real-time Event Processing with Kailash SDK
==========================================

This script demonstrates real-time event processing patterns including:
1. Event filtering and prioritization
2. Window-based aggregations
3. Anomaly detection and alerting
4. Conditional routing

Key Features:
- Uses proper Kailash nodes throughout
- Implements sliding window aggregations
- Handles conditional routing with SwitchNode
- Production-ready patterns
"""

from datetime import datetime

from kailash import Workflow
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.logic import SwitchNode
from kailash.nodes.transform import DataTransformer, FilterNode
from kailash.runtime.local import LocalRuntime


def create_event_processor_workflow() -> Workflow:
    """Create an event processing workflow."""
    workflow = Workflow(
        workflow_id="event_processor_001",
        name="event_processor",
        description="Real-time event processing with anomaly detection",
    )

    # Event source (CSV for demo, replace with streaming source in production)
    event_reader = CSVReaderNode(id="event_reader", file_path="data/events.csv")
    workflow.add_node("event_reader", event_reader)

    # Filter high-priority events
    priority_filter = FilterNode(id="priority_filter")
    workflow.add_node("priority_filter", priority_filter)
    workflow.connect("event_reader", "priority_filter", mapping={"data": "data"})

    # Enrich events with metadata
    event_enricher = DataTransformer(
        id="event_enricher", transformations=[]  # Will be provided at runtime
    )
    workflow.add_node("event_enricher", event_enricher)
    workflow.connect(
        "priority_filter", "event_enricher", mapping={"filtered_data": "data"}
    )

    # Window aggregation for anomaly detection
    window_aggregator = DataTransformer(
        id="window_aggregator", transformations=[]  # Will be provided at runtime
    )
    workflow.add_node("window_aggregator", window_aggregator)
    workflow.connect("event_enricher", "window_aggregator", mapping={"result": "data"})

    # Anomaly detection routing
    anomaly_router = SwitchNode(id="anomaly_router")
    workflow.add_node("anomaly_router", anomaly_router)
    workflow.connect(
        "window_aggregator", "anomaly_router", mapping={"result": "input_data"}
    )

    # Alert processing (write to file for demo)
    alert_writer = CSVWriterNode(id="alert_writer", file_path="data/outputs/alerts.csv")
    workflow.add_node("alert_writer", alert_writer)

    # Normal event processing
    normal_processor = DataTransformer(
        id="normal_processor", transformations=[]  # Will be provided at runtime
    )
    workflow.add_node("normal_processor", normal_processor)

    # Connect router outputs
    workflow.connect(
        "anomaly_router",
        "alert_writer",
        mapping={"true_output": "data"},  # For boolean switch
    )
    workflow.connect(
        "anomaly_router",
        "normal_processor",
        mapping={"false_output": "data"},  # For boolean switch
    )

    # Results storage
    results_writer = CSVWriterNode(
        id="results_writer", file_path="data/outputs/processed_events.csv"
    )
    workflow.add_node("results_writer", results_writer)
    workflow.connect("normal_processor", "results_writer", mapping={"result": "data"})

    return workflow


def run_event_processor():
    """Execute the event processing workflow."""
    workflow = create_event_processor_workflow()
    runtime = LocalRuntime()

    # Define runtime parameters
    parameters = {
        "priority_filter": {
            "field": "priority",
            "operator": ">=",
            "value": 5,  # Medium priority and above
        },
        "event_enricher": {
            "transformations": [
                # Add processing timestamp
                """
from datetime import datetime
result = []
for event in data:
    enriched = dict(event)
    enriched['processed_at'] = datetime.now().isoformat()
    enriched['processing_day'] = datetime.now().strftime('%Y-%m-%d')
    result.append(enriched)
"""
            ]
        },
        "window_aggregator": {
            "transformations": [
                # Aggregate events by type in 5-minute windows
                """
from collections import defaultdict
from datetime import datetime, timedelta

# Group events by type
event_groups = defaultdict(list)
for event in data:
    event_groups[event.get('type', 'unknown')].append(event)

# Calculate metrics
total_events = len(data)
unique_types = len(event_groups)
high_priority_count = sum(1 for e in data if int(e.get('priority', 0)) >= 8)

# Detect anomalies
is_anomaly = (
    total_events > 100 or  # Too many events
    high_priority_count > 10 or  # Too many high priority
    unique_types > 20  # Too many different types
)

result = {
    'window_start': datetime.now().isoformat(),
    'total_events': total_events,
    'unique_types': unique_types,
    'high_priority_count': high_priority_count,
    'is_anomaly': is_anomaly,
    'events': data
}
"""
            ]
        },
        "anomaly_router": {
            "condition_field": "is_anomaly",
            "operator": "==",
            "value": True,
        },
        "normal_processor": {
            "transformations": [
                # Standard processing - simplified
                """
# Handle case where data might be the window aggregation result
if isinstance(data, dict) and 'events' in data:
    # Extract events from windowed data
    result = []
    for event in data['events']:
        processed = {
            'event_id': event.get('id'),
            'type': event.get('type'),
            'priority': event.get('priority'),
            'status': 'processed',
            'anomaly': False
        }
        result.append(processed)
else:
    # Shouldn't happen but handle gracefully
    result = []
"""
            ]
        },
    }

    try:
        print("Starting event processor...")
        result, run_id = runtime.execute(workflow, parameters=parameters)
        print("Event processing completed!")
        print("Alerts written to: data/outputs/alerts.csv")
        print("Processed events written to: data/outputs/processed_events.csv")
        return result
    except Exception as e:
        print(f"Event processing failed: {str(e)}")
        raise


def generate_sample_events():
    """Generate sample event data for testing."""
    import csv
    import os
    import random

    os.makedirs("data/outputs", exist_ok=True)

    events = []
    event_types = ["login", "purchase", "error", "api_call", "update", "delete"]

    for i in range(50):
        event = {
            "id": f"evt_{i:04d}",
            "timestamp": datetime.now().isoformat(),
            "type": random.choice(event_types),
            "priority": random.randint(1, 10),
            "user_id": f"user_{random.randint(1, 20)}",
            "source": random.choice(["web", "mobile", "api"]),
            "status": "pending",
        }
        events.append(event)

    # Add some anomalous events
    for i in range(5):
        event = {
            "id": f"evt_anom_{i:04d}",
            "timestamp": datetime.now().isoformat(),
            "type": "security_alert",
            "priority": 9,
            "user_id": f"suspicious_{i}",
            "source": "system",
            "status": "critical",
        }
        events.append(event)

    # Write to CSV
    with open("data/events.csv", "w", newline="") as f:
        if events:
            writer = csv.DictWriter(f, fieldnames=events[0].keys())
            writer.writeheader()
            writer.writerows(events)

    print(f"Generated {len(events)} sample events")
    return events


def main():
    """Main entry point."""
    # Generate sample data
    generate_sample_events()

    # Run the processor
    run_event_processor()


if __name__ == "__main__":
    main()
