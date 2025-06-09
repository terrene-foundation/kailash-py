# Real-time Processing Training - Common Mistakes and Corrections

This document shows common mistakes when building real-time processing workflows with Kailash SDK, followed by correct implementations.

## ACTUAL ERRORS ENCOUNTERED AND FIXES

### Error 1: DataTransformer Safe Globals
```python
# WRONG: Using datetime in DataTransformer without importing
transformations = [
    '''
enriched['processed_at'] = datetime.now().isoformat()
'''
]
# NameError: name 'datetime' is not defined

# CORRECT: Import inside the transformation or use string formatting
transformations = [
    '''
from datetime import datetime
enriched['processed_at'] = datetime.now().isoformat()
'''
]

# ALSO CORRECT: Use simple string operations
transformations = [
    '''
import time
enriched['processed_at'] = str(time.time())
'''
]
```

### Error 2: DataTransformer Input Data
```python
# WRONG: Assuming custom input parameter names
workflow.connect(switch.id, transformer.id, mapping={"false_output": "input"})
# DataTransformer expects "data", gets "input" -> NameError: name 'data' is not defined

# CORRECT: Always map to "data" for DataTransformer
workflow.connect(switch.id, transformer.id, mapping={"false_output": "data"})
```

### Error 3: Import Availability in DataTransformer
```python
# WRONG: Assuming all modules are available
transformations = [
    '''
type_counts = defaultdict(int)  # NameError: defaultdict not defined
'''
]

# CORRECT: Import what you need inside the transformation
transformations = [
    '''
from collections import defaultdict
import time
type_counts = defaultdict(int)
timestamp = time.time()
'''
]
```

### Error 4: SwitchNode Boolean Output Behavior
```python
# ISSUE: SwitchNode sets one output to None based on condition
# When condition is True: true_output = data, false_output = None
# When condition is False: true_output = None, false_output = data

# This can cause issues if downstream nodes don't handle None properly
# Solution: Design workflows to handle both paths or use different patterns
```

### Error 5: Complex Routing Patterns
```python
# LEARNED: For complex event routing, consider simpler patterns
# Instead of: Event -> Switch -> (Alert | Normal) -> Merge -> Output
# Consider: Event -> Process -> Filter Alerts -> Write Alerts
#           Event -> Process -> Write All Results
```

## CORRECT: Streaming Data Ingestion

```python
# CORRECT: Use StreamingDataNode for real-time data sources
from kailash.nodes.data import StreamingDataNode

stream_node = StreamingDataNode(
    name="kafka_stream",
    source_type="kafka",
    topic="events",
    consumer_group="processor_group"
)

# For Kinesis
kinesis_node = StreamingDataNode(
    name="kinesis_stream",
    source_type="kinesis",
    stream_name="event-stream",
    shard_iterator_type="LATEST"
)
```

## WRONG: Using PythonCodeNode for Streaming

```python
# WRONG: Don't implement streaming logic manually
stream_node = PythonCodeNode(
    name="stream_reader",
    code="""
from kafka import KafkaConsumer
consumer = KafkaConsumer('events', group_id='my-group')
events = []
for message in consumer:
    events.append(json.loads(message.value))
    if len(events) >= 100:
        break
result = {"events": events}
"""
)

# Problems:
# 1. Blocking operation in PythonCodeNode
# 2. No proper error handling
# 3. No connection management
# 4. Doesn't support async execution
```

## CORRECT: Async Processing for Real-time

```python
# CORRECT: Use async nodes and runtime for real-time processing
from kailash.runtime import AsyncLocalRuntime
from kailash.nodes.base_async import AsyncNode

workflow = Workflow(name="realtime_pipeline")
runtime = AsyncLocalRuntime()

# Async execution
result = await runtime.execute(workflow, parameters=params)
```

## WRONG: Synchronous Processing for Streams

```python
# WRONG: Don't use synchronous runtime for streaming
from kailash.runtime import LocalRuntime

runtime = LocalRuntime()  # This will block!
result = runtime.execute(workflow)  # No async support
```

## CORRECT: Window Aggregations with DataTransformer

```python
# CORRECT: Use DataTransformer for sliding window operations
window_agg = DataTransformer(name="sliding_window")
parameters = {
    "sliding_window": {
        "transformations": [
            """
from datetime import datetime, timedelta
from collections import defaultdict

# 5-minute sliding window
window_size = timedelta(minutes=5)
now = datetime.utcnow()
window_start = now - window_size

# Filter and aggregate
window_data = [e for e in data if datetime.fromisoformat(e['timestamp']) >= window_start]
metrics = {
    'count': len(window_data),
    'avg_value': sum(e['value'] for e in window_data) / len(window_data) if window_data else 0,
    'max_value': max((e['value'] for e in window_data), default=0)
}
result = metrics
"""
        ]
    }
}
```

## WRONG: Complex Window Logic in PythonCodeNode

```python
# WRONG: Avoid complex windowing in PythonCodeNode
window_node = PythonCodeNode(
    name="window",
    code="""
import pandas as pd
df = pd.DataFrame(data)
df['timestamp'] = pd.to_datetime(df['timestamp'])
df.set_index('timestamp', inplace=True)
rolling = df.rolling('5min').agg({'value': ['mean', 'max', 'count']})
result = {"windowed": rolling.to_dict()}
"""
)

# Problems:
# 1. Heavy dependency (pandas) in PythonCodeNode
# 2. Complex state management
# 3. Harder to test and debug
```

## CORRECT: Event Routing with SwitchNode

```python
# CORRECT: Use SwitchNode for conditional routing
anomaly_router = SwitchNode(name="anomaly_router")
workflow.add_node(anomaly_router)

parameters = {
    "anomaly_router": {
        "condition_field": "severity",
        "routes": {
            "critical": "alert_path",
            "warning": "monitor_path", 
            "normal": "store_path"
        }
    }
}

# Connect different paths
workflow.connect(anomaly_router.id, alert_handler.id, output_key="alert_path")
workflow.connect(anomaly_router.id, monitor.id, output_key="monitor_path")
workflow.connect(anomaly_router.id, storage.id, output_key="store_path")
```

## WRONG: Manual Routing Logic

```python
# WRONG: Don't implement routing manually
router_node = PythonCodeNode(
    name="router",
    code="""
alerts = []
monitors = []
normal = []

for event in data:
    if event['severity'] == 'critical':
        alerts.append(event)
    elif event['severity'] == 'warning':
        monitors.append(event)
    else:
        normal.append(event)

result = {
    "alerts": alerts,
    "monitors": monitors,
    "normal": normal
}
"""
)
```

## CORRECT: Real-time Alerts with WebhookNode

```python
# CORRECT: Use WebhookNode for real-time notifications
alert_webhook = WebhookNode(
    name="slack_alert",
    url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    method="POST"
)

parameters = {
    "slack_alert": {
        "headers": {"Content-Type": "application/json"},
        "transform_payload": True,
        "payload_template": {
            "text": "🚨 Anomaly Detected!",
            "attachments": [{
                "color": "danger",
                "fields": [
                    {"title": "Event ID", "value": "{{ id }}"},
                    {"title": "Severity", "value": "{{ severity }}"},
                    {"title": "Message", "value": "{{ message }}"}
                ]
            }]
        }
    }
}
```

## WRONG: Manual Webhook Implementation

```python
# WRONG: Don't implement HTTP calls manually
alert_node = PythonCodeNode(
    name="alert",
    code="""
import requests
webhook_url = "https://hooks.slack.com/services/YOUR/WEBHOOK"
for event in critical_events:
    payload = {
        "text": f"Alert: {event['message']}",
        "color": "danger"
    }
    response = requests.post(webhook_url, json=payload)
result = {"alerts_sent": len(critical_events)}
"""
)
```

## CORRECT: State Management for Streaming

```python
# CORRECT: Use proper state management for streaming workflows
from kailash.nodes.data import StateStoreNode

state_store = StateStoreNode(
    name="event_state",
    backend="redis",
    ttl_seconds=3600  # 1 hour TTL
)

# Store processed event IDs to avoid duplicates
parameters = {
    "event_state": {
        "operation": "check_and_set",
        "key_field": "event_id",
        "value_field": "processed_at"
    }
}
```

## Complete Real-time Pipeline Example

```python
# CORRECT: Complete real-time processing pipeline
from kailash import Workflow
from kailash.nodes.data import StreamingDataNode, StateStoreNode
from kailash.nodes.transform import FilterNode, DataTransformer
from kailash.nodes.logic import SwitchNode
from kailash.nodes.api import WebhookNode
from kailash.runtime import AsyncLocalRuntime

async def create_realtime_pipeline():
    workflow = Workflow(name="event_processor")
    
    # Streaming source
    stream = StreamingDataNode(
        name="event_stream",
        source_type="kafka",
        topic="events"
    )
    workflow.add_node(stream)
    
    # Deduplication with state
    dedup = StateStoreNode(name="dedup_store", backend="redis")
    workflow.add_node(dedup)
    workflow.connect(stream.id, dedup.id, mapping={"events": "data"})
    
    # Filter and enrich
    filter_node = FilterNode(name="priority_filter")
    workflow.add_node(filter_node)
    workflow.connect(dedup.id, filter_node.id, mapping={"unique_events": "data"})
    
    # Window aggregation
    window_agg = DataTransformer(name="window_metrics")
    workflow.add_node(window_agg)
    workflow.connect(filter_node.id, window_agg.id, mapping={"filtered_data": "data"})
    
    # Anomaly detection routing
    router = SwitchNode(name="severity_router")
    workflow.add_node(router)
    workflow.connect(window_agg.id, router.id, mapping={"result": "input"})
    
    # Alert path
    alerter = WebhookNode(name="alert_webhook", url="https://alerts.example.com")
    workflow.add_node(alerter)
    workflow.connect(router.id, alerter.id, output_key="critical")
    
    # Execute asynchronously
    runtime = AsyncLocalRuntime()
    await runtime.execute(workflow, parameters={
        "priority_filter": {"field": "priority", "operator": ">=", "value": 7},
        "window_metrics": {
            "transformations": ["... window aggregation logic ..."]
        },
        "severity_router": {
            "condition_field": "anomaly_score",
            "routes": {"high": "critical", "medium": "warning", "low": "normal"}
        }
    })
```

## Key Principles for Real-time Processing

1. **Use Async Nodes**: Always use AsyncLocalRuntime for streaming
2. **Specialized Nodes**: Use StreamingDataNode, WebhookNode, StateStoreNode
3. **Avoid Blocking**: Never use blocking operations in nodes
4. **State Management**: Use StateStoreNode for deduplication and state
5. **Window Operations**: Use DataTransformer with time-based logic
6. **Event Routing**: Use SwitchNode for conditional paths
7. **Error Recovery**: Streaming nodes have built-in retry and recovery