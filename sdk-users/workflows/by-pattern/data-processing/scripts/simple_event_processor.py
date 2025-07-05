#!/usr/bin/env python3
"""
Simple Event Processing Pipeline
================================

A simplified event processing workflow that demonstrates:
1. Reading events from CSV
2. Filtering by priority
3. Aggregating metrics
4. Writing results

This version focuses on working patterns without complex routing.
"""

import csv
import os
import random
from datetime import datetime

from kailash import Workflow
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.transform import DataTransformer, FilterNode
from kailash.runtime.local import LocalRuntime


def create_simple_workflow() -> Workflow:
    """Create a simple event processing workflow."""
    workflow = Workflow(
        workflow_id="simple_event_001",
        name="simple_event_processor",
        description="Simple event processing pipeline",
    )

    # Read events
    reader = CSVReaderNode(id="event_reader", file_path="data/events.csv")
    workflow.add_node("event_reader", reader)

    # Filter priority events
    filter_node = FilterNode(id="priority_filter")
    workflow.add_node("priority_filter", filter_node)
    workflow.connect("event_reader", "priority_filter", mapping={"data": "data"})

    # Transform and aggregate
    aggregator = DataTransformer(
        id="event_aggregator", transformations=[]  # Provided at runtime
    )
    workflow.add_node("event_aggregator", aggregator)
    workflow.connect(
        "priority_filter", "event_aggregator", mapping={"filtered_data": "data"}
    )

    # Write results
    writer = CSVWriterNode(
        id="result_writer", file_path="data/outputs/event_summary.csv"
    )
    workflow.add_node("result_writer", writer)
    workflow.connect("event_aggregator", "result_writer", mapping={"result": "data"})

    return workflow


def run_simple_processor():
    """Run the simple event processor."""
    workflow = create_simple_workflow()
    runtime = LocalRuntime()

    parameters = {
        "priority_filter": {"field": "priority", "operator": ">=", "value": 7},
        "event_aggregator": {
            "transformations": [
                """
# Simple aggregation
from collections import defaultdict
import time

# Group by type
type_counts = defaultdict(int)
priority_sum = 0
event_list = []

for event in data:
    type_counts[event.get('type', 'unknown')] += 1
    priority_sum += int(event.get('priority', 0))
    event_list.append({
        'id': event.get('id'),
        'type': event.get('type'),
        'priority': event.get('priority')
    })

# Create summary
result = [{
    'timestamp': str(int(time.time())),
    'total_events': len(data),
    'avg_priority': priority_sum / len(data) if data else 0,
    'type_distribution': str(dict(type_counts)),
    'high_priority_count': sum(1 for e in data if int(e.get('priority', 0)) >= 8)
}]
"""
            ]
        },
    }

    try:
        print("Running simple event processor...")
        result, run_id = runtime.execute(workflow, parameters=parameters)
        print("Processing complete!")
        print("Summary written to: data/outputs/event_summary.csv")
        return result
    except Exception as e:
        print(f"Processing failed: {str(e)}")
        raise


def generate_events():
    """Generate sample events."""
    os.makedirs("data/outputs", exist_ok=True)

    events = []
    event_types = ["login", "purchase", "error", "api_call", "system"]

    for i in range(30):
        events.append(
            {
                "id": f"evt_{i:04d}",
                "timestamp": datetime.now().isoformat(),
                "type": random.choice(event_types),
                "priority": random.randint(1, 10),
                "source": random.choice(["web", "mobile", "api"]),
            }
        )

    with open("data/events.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=events[0].keys())
        writer.writeheader()
        writer.writerows(events)

    print(f"Generated {len(events)} events")


def main():
    generate_events()
    run_simple_processor()


if __name__ == "__main__":
    main()
