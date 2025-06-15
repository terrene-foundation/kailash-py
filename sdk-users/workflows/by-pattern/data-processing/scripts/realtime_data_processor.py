#!/usr/bin/env python3
"""
Real-time Data Processing with Kailash SDK
==========================================

This script demonstrates real-time data processing patterns including:
1. Event stream processing
2. Real-time transformations
3. Conditional routing
4. Alert notifications

Key Features:
- Uses proper Kailash nodes for all operations
- Implements window aggregations with DataTransformer
- Handles conditional routing with SwitchNode
- Production-ready patterns
"""

import asyncio
from datetime import datetime, timedelta, timezone

from kailash import Workflow
from kailash.nodes.api import WebhookNode
from kailash.nodes.data import ConstantNode
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.nodes.transform import DataTransformer, FilterNode
from kailash.runtime import AsyncLocalRuntime


def create_realtime_workflow() -> Workflow:
    """Create a real-time data processing workflow."""
    workflow = Workflow(
        workflow_id="realtime_processor_001",
        name="realtime_processor",
        description="Real-time event processing pipeline",
    )

    # For demo: Use ConstantNode to simulate streaming data
    # In production: Replace with KafkaConsumerNode or actual streaming source
    event_source = ConstantNode(
        id="event_stream", value=[]  # Will be provided at runtime
    )
    workflow.add_node("event_stream", event_source)

    # Filter high-priority events
    priority_filter = FilterNode(name="priority_filter")
    workflow.add_node(priority_filter)
    workflow.connect(event_source.id, priority_filter.id, mapping={"value": "data"})

    # Transform events with enrichment
    event_enricher = DataTransformer(name="event_enricher")
    workflow.add_node(event_enricher)
    workflow.connect(
        priority_filter.id, event_enricher.id, mapping={"filtered_data": "data"}
    )

    # Sliding window aggregation
    window_aggregator = DataTransformer(name="window_aggregator")
    workflow.add_node(window_aggregator)
    workflow.connect(
        event_enricher.id, window_aggregator.id, mapping={"result": "data"}
    )

    # Anomaly detection switch
    anomaly_detector = SwitchNode(name="anomaly_detector")
    workflow.add_node(anomaly_detector)
    workflow.connect(
        window_aggregator.id, anomaly_detector.id, mapping={"result": "input"}
    )

    # Alert webhook for anomalies
    alert_webhook = WebhookNode(
        name="alert_webhook", url="https://alerts.example.com/webhook"
    )
    workflow.add_node(alert_webhook)

    # Normal processing path
    normal_processor = DataTransformer(name="normal_processor")
    workflow.add_node(normal_processor)

    # Connect switch outputs
    workflow.connect(
        anomaly_detector.id,
        alert_webhook.id,
        mapping={"anomaly": "data"},
        output_key="anomaly",
    )
    workflow.connect(
        anomaly_detector.id,
        normal_processor.id,
        mapping={"normal": "data"},
        output_key="normal",
    )

    # Merge results
    result_merger = MergeNode(name="result_merger")
    workflow.add_node(result_merger)
    workflow.connect(
        alert_webhook.id, result_merger.id, mapping={"response": "alert_data"}
    )
    workflow.connect(
        normal_processor.id, result_merger.id, mapping={"result": "processed_data"}
    )

    return workflow


async def run_realtime_processor():
    """Execute the real-time processing workflow."""
    workflow = create_realtime_workflow()
    runtime = AsyncLocalRuntime()

    # Define runtime parameters
    parameters = {
        "priority_filter": {
            "field": "priority",
            "operator": ">=",
            "value": 7,  # High priority events only
        },
        "event_enricher": {
            "transformations": [
                # Add processing timestamp
                "lambda event: {**event, 'processed_at': datetime.now(timezone.utc).isoformat()}",
                # Calculate event age
                "lambda event: {**event, 'age_seconds': (datetime.now(timezone.utc) - datetime.fromisoformat(event['timestamp'])).total_seconds()}",
            ]
        },
        "window_aggregator": {
            "transformations": [
                """
# Sliding window aggregation (5-minute window)
from collections import defaultdict
from datetime import datetime, timedelta

window_size = timedelta(minutes=5)
now = datetime.now(timezone.utc)
window_start = now - window_size

# Filter events in window
window_events = [e for e in data if datetime.fromisoformat(e['processed_at']) >= window_start]

# Aggregate metrics
metrics = {
    'window_start': window_start.isoformat(),
    'window_end': now.isoformat(),
    'event_count': len(window_events),
    'avg_priority': sum(e['priority'] for e in window_events) / len(window_events) if window_events else 0,
    'unique_sources': len(set(e.get('source') for e in window_events)),
    'events': window_events
}

# Detect anomalies
metrics['is_anomaly'] = (
    metrics['event_count'] > 100 or  # Too many events
    metrics['avg_priority'] > 8.5 or  # Very high priority
    metrics['unique_sources'] > 50    # Too many sources
)

result = metrics
"""
            ]
        },
        "anomaly_detector": {
            "condition_field": "is_anomaly",
            "routes": {"True": "anomaly", "False": "normal"},
        },
        "normal_processor": {
            "transformations": [
                # Standard processing for normal events
                "lambda metrics: {**metrics, 'status': 'processed', 'action': 'store'}"
            ]
        },
        "result_merger": {"merge_strategy": "combine", "include_metadata": True},
    }

    try:
        print("Starting real-time processor...")
        # In production, this would run continuously
        result = await runtime.execute(workflow, parameters=parameters)
        print("Real-time processing active")
        return result
    except Exception as e:
        print(f"Real-time processor error: {str(e)}")
        raise


def simulate_event_stream():
    """Simulate events for testing."""
    import random

    events = []
    base_time = datetime.now(timezone.utc) - timedelta(minutes=10)

    for i in range(50):
        event = {
            "id": f"evt_{i:04d}",
            "timestamp": (base_time + timedelta(seconds=i * 12)).isoformat(),
            "priority": random.randint(1, 10),
            "source": f"sensor_{random.randint(1, 10)}",
            "type": random.choice(["temperature", "pressure", "humidity"]),
            "value": random.uniform(20, 100),
            "metadata": {
                "location": random.choice(["zone_a", "zone_b", "zone_c"]),
                "device_id": f"dev_{random.randint(100, 200)}",
            },
        }
        events.append(event)

    # Add some anomalous events
    for i in range(5):
        event = {
            "id": f"evt_anom_{i:04d}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "priority": 9,  # High priority
            "source": f"sensor_anomaly_{i}",
            "type": "alert",
            "value": random.uniform(150, 200),  # Out of range
            "metadata": {"location": "danger_zone", "alert_type": "threshold_exceeded"},
        }
        events.append(event)

    return events


def main():
    """Main entry point."""
    # For testing, we'll simulate a streaming data source
    # In production, this would connect to actual Kafka/Kinesis/etc

    print("Simulating real-time event stream...")
    events = simulate_event_stream()

    # Create a mock streaming workflow for demonstration
    from kailash import Workflow
    from kailash.nodes.data import ConstantNode

    demo_workflow = Workflow(name="realtime_demo")

    # Use ConstantNode to simulate streaming data
    event_source = ConstantNode(name="event_stream", value=events)
    demo_workflow.add_node(event_source)

    # Add the rest of the real-time processing pipeline
    # (In production, replace ConstantNode with actual StreamingDataNode)

    print(f"Generated {len(events)} events for processing")
    print(
        f"Including {len([e for e in events if e.get('type') == 'alert'])} anomalous events"
    )

    # Run async processing
    asyncio.execute(run_realtime_processor())


if __name__ == "__main__":
    main()
