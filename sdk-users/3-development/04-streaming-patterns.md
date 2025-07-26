# Streaming Patterns - Real-time Data Processing & WebSockets

*Build real-time workflows with streaming data, WebSocket connections, and event processing*

## Prerequisites

- Completed [Fundamentals](01-fundamentals-core-concepts.md) - Core SDK concepts
- Completed [Workflows](02-workflows-creation.md) - Basic workflow patterns
- Completed [Production](04-production.md) - Core production patterns
- Understanding of asynchronous programming

## Real-time Streaming & WebSockets

### WebSocket Streaming Node

```python
from kailash.nodes.api import WebSocketNode
from kailash.workflow.builder import WorkflowBuilder

# Configure WebSocket streaming
workflow = WorkflowBuilder()

workflow.add_node("WebSocketNode", "websocket_stream", {
    "url": "wss://streaming.example.com/feed",
    "connection_timeout": 30.0,
    "message_timeout": 5.0,

    # Authentication
    "auth_headers": {
        "Authorization": "Bearer {api_token}",
        "X-Client-ID": "production-client"
    },

    # Message handling
    "message_format": "json",           # json, text, binary
    "batch_size": 100,                  # Messages per batch
    "batch_timeout": 1.0,               # Max time to wait for batch

    # Reconnection
    "auto_reconnect": True,
    "max_reconnect_attempts": 5,
    "reconnect_delay": 2.0,
    "exponential_backoff": True,

    # Flow control
    "max_queue_size": 10000,
    "backpressure_strategy": "drop_oldest",  # drop_oldest, drop_newest, block

    # Monitoring
    "enable_metrics": True,
    "heartbeat_interval": 30.0
})

# Process streaming data
workflow.add_node("PythonCodeNode", "stream_processor", {
    "code": """
import json
from datetime import datetime

processed_messages = []
error_count = 0

for message in stream_data:
    try:
        # Parse and validate message
        if isinstance(message, str):
            msg_data = json.loads(message)
        else:
            msg_data = message

        # Process message
        processed_msg = {
            "id": msg_data.get("id"),
            "timestamp": datetime.now(datetime.UTC).isoformat(),
            "data": msg_data.get("data"),
            "processed": True
        }
        processed_messages.append(processed_msg)

    except Exception as e:
        error_count += 1
        print(f"Error processing message: {e}")

result = {
    "processed_messages": processed_messages,
    "total_processed": len(processed_messages),
    "error_count": error_count,
    "batch_id": datetime.now(datetime.UTC).isoformat()
}
"""
})

# Connect stream to processor
workflow.add_connection("websocket_stream", "stream_processor", "messages", "stream_data")
```

### Real-time Data Pipeline

```python
import asyncio
import json
from typing import AsyncGenerator, Dict, Any

async def real_time_data_pipeline(
    source_config: Dict[str, Any]
) -> AsyncGenerator[Dict[str, Any], None]:
    """Real-time data processing pipeline with WebSocket streaming."""

    import websockets
    import aiohttp

    async def stream_processor():
        uri = source_config.get("websocket_url")
        headers = source_config.get("headers", {})

        async with websockets.connect(uri, extra_headers=headers) as websocket:
            batch = []
            batch_size = source_config.get("batch_size", 100)
            batch_timeout = source_config.get("batch_timeout", 1.0)

            last_batch_time = asyncio.get_event_loop().time()

            async for message in websocket:
                try:
                    # Parse message
                    if isinstance(message, str):
                        data = json.loads(message)
                    else:
                        data = message

                    batch.append(data)

                    # Check if batch is ready
                    current_time = asyncio.get_event_loop().time()
                    batch_ready = (
                        len(batch) >= batch_size or
                        (current_time - last_batch_time) >= batch_timeout
                    )

                    if batch_ready and batch:
                        # Process batch
                        processed_batch = {
                            "messages": batch,
                            "count": len(batch),
                            "timestamp": current_time,
                            "processing_latency": current_time - last_batch_time
                        }

                        yield processed_batch

                        # Reset batch
                        batch = []
                        last_batch_time = current_time

                except Exception as e:
                    yield {
                        "error": str(e),
                        "message": str(message)[:100],
                        "timestamp": asyncio.get_event_loop().time()
                    }

    # Run the streaming processor
    async for batch in stream_processor():
        yield batch

# Use in workflow function
def streaming_workflow_processor(config: Dict[str, Any]) -> Dict[str, Any]:
    """Process real-time streaming data in workflow."""
    import asyncio

    async def process_stream():
        results = []
        error_count = 0
        total_messages = 0

        async for batch in real_time_data_pipeline(config):
            if "error" in batch:
                error_count += 1
                continue

            # Process batch
            batch_results = {
                "batch_size": batch["count"],
                "processing_time": batch["processing_latency"],
                "processed_at": batch["timestamp"]
            }

            results.append(batch_results)
            total_messages += batch["count"]

            # Limit processing for workflow context
            if len(results) >= config.get("max_batches", 10):
                break

        return {
            "batches_processed": len(results),
            "total_messages": total_messages,
            "error_count": error_count,
            "average_latency": sum(r["processing_time"] for r in results) / len(results) if results else 0
        }

    # Execute streaming
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        stream_results = loop.run_until_complete(process_stream())
        return {"result": stream_results}
    finally:
        loop.close()

# Create streaming node
streaming_node = PythonCodeNode.from_function(
    name="streaming_processor",
    func=streaming_workflow_processor
)
```

## Stream Analytics with Windowing

### Time-Based Window Analytics

```python
from collections import defaultdict, deque
import time
from typing import Dict, List, Any

class StreamingAnalytics:
    """Real-time analytics with time-based windowing."""

    def __init__(self, window_size_seconds: int = 60):
        self.window_size = window_size_seconds
        self.data_windows = defaultdict(deque)
        self.metrics = defaultdict(dict)

    def add_data_point(self, stream_id: str, data: Dict[str, Any]):
        """Add data point to streaming window."""
        current_time = time.time()

        # Add to window
        self.data_windows[stream_id].append({
            "timestamp": current_time,
            "data": data
        })

        # Clean old data
        cutoff_time = current_time - self.window_size
        while (self.data_windows[stream_id] and
               self.data_windows[stream_id][0]["timestamp"] < cutoff_time):
            self.data_windows[stream_id].popleft()

    def get_window_metrics(self, stream_id: str) -> Dict[str, Any]:
        """Calculate metrics for current window."""
        window_data = list(self.data_windows[stream_id])

        if not window_data:
            return {"count": 0, "rate": 0.0}

        # Calculate metrics
        count = len(window_data)
        time_span = window_data[-1]["timestamp"] - window_data[0]["timestamp"]
        rate = count / max(time_span, 1.0)  # Events per second

        # Extract numeric values for aggregation
        numeric_values = []
        for point in window_data:
            data = point["data"]
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, (int, float)):
                        numeric_values.append(value)

        metrics = {
            "count": count,
            "rate_per_second": rate,
            "window_duration": time_span,
            "first_timestamp": window_data[0]["timestamp"],
            "last_timestamp": window_data[-1]["timestamp"]
        }

        if numeric_values:
            metrics.update({
                "min_value": min(numeric_values),
                "max_value": max(numeric_values),
                "avg_value": sum(numeric_values) / len(numeric_values),
                "sum_value": sum(numeric_values)
            })

        return metrics

def streaming_analytics_processor(stream_data: List[Dict], config: Dict = None) -> Dict:
    """Process streaming data with real-time analytics."""
    if config is None:
        config = {}

    window_size = config.get("window_size_seconds", 60)
    analytics = StreamingAnalytics(window_size)

    # Process each data point
    for item in stream_data:
        stream_id = item.get("stream_id", "default")
        data = item.get("data", {})

        analytics.add_data_point(stream_id, data)

    # Calculate metrics for all streams
    all_metrics = {}
    for stream_id in analytics.data_windows.keys():
        all_metrics[stream_id] = analytics.get_window_metrics(stream_id)

    return {
        "result": {
            "stream_metrics": all_metrics,
            "total_streams": len(all_metrics),
            "window_size_seconds": window_size,
            "processed_count": len(stream_data)
        }
    }

# Create analytics node
analytics_node = PythonCodeNode.from_function(
    name="stream_analytics",
    func=streaming_analytics_processor
)
```

### Sliding Window Aggregation

```python
from typing import Callable, Any
import heapq

class SlidingWindow:
    """Efficient sliding window with automatic expiration."""

    def __init__(self, window_size_seconds: float, aggregation_func: Callable = None):
        self.window_size = window_size_seconds
        self.data_points = []  # heap of (timestamp, value)
        self.aggregation_func = aggregation_func or (lambda x: len(x))

    def add(self, value: Any, timestamp: float = None):
        """Add value to sliding window."""
        if timestamp is None:
            timestamp = time.time()

        heapq.heappush(self.data_points, (timestamp, value))
        self._cleanup()

    def _cleanup(self):
        """Remove expired data points."""
        current_time = time.time()
        cutoff_time = current_time - self.window_size

        while self.data_points and self.data_points[0][0] < cutoff_time:
            heapq.heappop(self.data_points)

    def aggregate(self) -> Any:
        """Get aggregated value for current window."""
        self._cleanup()
        values = [value for _, value in self.data_points]
        return self.aggregation_func(values)

    def size(self) -> int:
        """Get current window size."""
        self._cleanup()
        return len(self.data_points)

# Example usage in streaming processor
def windowed_stream_processor(stream_data: List[Dict], config: Dict = None) -> Dict:
    """Process streaming data with sliding windows."""
    if config is None:
        config = {}

    window_size = config.get("window_size_seconds", 60)

    # Create different aggregation windows
    windows = {
        "count": SlidingWindow(window_size, lambda x: len(x)),
        "sum": SlidingWindow(window_size, lambda x: sum(v for v in x if isinstance(v, (int, float)))),
        "avg": SlidingWindow(window_size, lambda x: sum(v for v in x if isinstance(v, (int, float))) / len([v for v in x if isinstance(v, (int, float))]) if x else 0),
        "max": SlidingWindow(window_size, lambda x: max(v for v in x if isinstance(v, (int, float))) if x else 0),
        "min": SlidingWindow(window_size, lambda x: min(v for v in x if isinstance(v, (int, float))) if x else 0)
    }

    # Process data points
    for item in stream_data:
        timestamp = item.get("timestamp", time.time())
        value = item.get("value")

        # Add to all windows
        for window in windows.values():
            window.add(value, timestamp)

    # Calculate aggregated metrics
    metrics = {}
    for name, window in windows.items():
        metrics[name] = window.aggregate()
        metrics[f"{name}_window_size"] = window.size()

    return {
        "result": {
            "metrics": metrics,
            "window_size_seconds": window_size,
            "processed_count": len(stream_data)
        }
    }

# Create windowed processor
windowed_processor = PythonCodeNode.from_function(
    name="windowed_processor",
    func=windowed_stream_processor
)
```

## Event Stream Processing

### Event-Driven Workflow Patterns

```python
from kailash.nodes.events import EventStreamNode, EventFilterNode, EventTransformNode
from kailash.workflow.builder import WorkflowBuilder

# Create event-driven workflow
event_workflow = WorkflowBuilder()

# Event source
event_workflow.add_node("EventStreamNode", "event_source", {
    "source_type": "kafka",
    "topic": "user_events",
    "consumer_group": "analytics_group",
    "batch_size": 100,
    "auto_commit": True,
    "event_format": "json"
})

# Filter relevant events
event_workflow.add_node("EventFilterNode", "event_filter", {
    "filter_conditions": [
        {"field": "event_type", "operator": "in", "values": ["click", "purchase", "view"]},
        {"field": "user_id", "operator": "exists"},
        {"field": "timestamp", "operator": "greater_than", "value": "now-1h"}
    ],
    "filter_logic": "and"  # all conditions must match
})

# Transform events
event_workflow.add_node("EventTransformNode", "event_transform", {
    "transformations": [
        {"field": "timestamp", "operation": "parse_iso", "output_field": "parsed_timestamp"},
        {"field": "user_id", "operation": "hash", "output_field": "user_hash"},
        {"field": "event_data", "operation": "flatten", "output_field": "flat_data"}
    ]
})

# Aggregate events
event_workflow.add_node("PythonCodeNode", "event_aggregator", {
    "code": """
from collections import defaultdict

# Aggregate by user and event type
aggregations = defaultdict(lambda: defaultdict(int))
event_details = []

for event in events:
    user_hash = event.get("user_hash", "unknown")
    event_type = event.get("event_type", "unknown")

    aggregations[user_hash][event_type] += 1
    event_details.append({
        "user": user_hash,
        "type": event_type,
        "timestamp": event.get("parsed_timestamp")
    })

result = {
    "aggregations": dict(aggregations),
    "event_details": event_details,
    "total_events": len(events),
    "unique_users": len(aggregations)
}
"""
})

# Connect event processing pipeline
event_workflow.add_connection("event_source", "event_filter", "events", "raw_events")
event_workflow.add_connection("event_filter", "event_transform", "filtered_events", "events")
event_workflow.add_connection("event_transform", "event_aggregator", "transformed_events", "events")
```

### Custom Event Processor

```python
from typing import Generator, Dict, Any, List
import json
import time

class EventProcessor:
    """Custom event processor with routing and enrichment."""

    def __init__(self):
        self.event_handlers = {}
        self.enrichment_rules = []
        self.routing_rules = []

    def register_handler(self, event_type: str, handler_func: Callable):
        """Register handler for specific event type."""
        self.event_handlers[event_type] = handler_func

    def add_enrichment_rule(self, condition: Dict, enrichment: Dict):
        """Add enrichment rule for events matching condition."""
        self.enrichment_rules.append({"condition": condition, "enrichment": enrichment})

    def add_routing_rule(self, condition: Dict, destination: str):
        """Add routing rule for events matching condition."""
        self.routing_rules.append({"condition": condition, "destination": destination})

    def process_event_stream(self, events: List[Dict]) -> Generator[Dict, None, None]:
        """Process stream of events with enrichment and routing."""

        for event in events:
            try:
                # Enrich event
                enriched_event = self._enrich_event(event)

                # Route event
                destinations = self._route_event(enriched_event)

                # Process with registered handlers
                processed_event = self._handle_event(enriched_event)

                yield {
                    "original_event": event,
                    "enriched_event": enriched_event,
                    "processed_event": processed_event,
                    "destinations": destinations,
                    "processing_timestamp": time.time()
                }

            except Exception as e:
                yield {
                    "error": str(e),
                    "failed_event": event,
                    "processing_timestamp": time.time()
                }

    def _enrich_event(self, event: Dict) -> Dict:
        """Apply enrichment rules to event."""
        enriched = event.copy()

        for rule in self.enrichment_rules:
            if self._matches_condition(event, rule["condition"]):
                enriched.update(rule["enrichment"])

        return enriched

    def _route_event(self, event: Dict) -> List[str]:
        """Determine routing destinations for event."""
        destinations = []

        for rule in self.routing_rules:
            if self._matches_condition(event, rule["condition"]):
                destinations.append(rule["destination"])

        return destinations

    def _handle_event(self, event: Dict) -> Dict:
        """Process event with registered handler."""
        event_type = event.get("event_type", "unknown")
        handler = self.event_handlers.get(event_type)

        if handler:
            return handler(event)
        else:
            return {"status": "no_handler", "event_type": event_type}

    def _matches_condition(self, event: Dict, condition: Dict) -> bool:
        """Check if event matches condition."""
        field = condition.get("field")
        operator = condition.get("operator")
        value = condition.get("value")

        if not field or field not in event:
            return False

        event_value = event[field]

        if operator == "equals":
            return event_value == value
        elif operator == "in":
            return event_value in value
        elif operator == "contains":
            return value in str(event_value)
        elif operator == "exists":
            return True  # field exists

        return False

# Use event processor in workflow
def event_processing_workflow(events: List[Dict], config: Dict = None) -> Dict:
    """Process events with custom event processor."""
    if config is None:
        config = {}

    # Setup event processor
    processor = EventProcessor()

    # Register handlers
    processor.register_handler("click", lambda e: {"clicks": 1, "url": e.get("url")})
    processor.register_handler("purchase", lambda e: {"revenue": e.get("amount", 0)})
    processor.register_handler("view", lambda e: {"page_views": 1, "page": e.get("page")})

    # Add enrichment rules
    processor.add_enrichment_rule(
        {"field": "user_id", "operator": "exists"},
        {"user_type": "registered", "enriched_at": time.time()}
    )

    # Add routing rules
    processor.add_routing_rule(
        {"field": "event_type", "operator": "equals", "value": "purchase"},
        "revenue_analytics"
    )
    processor.add_routing_rule(
        {"field": "event_type", "operator": "in", "value": ["click", "view"]},
        "engagement_analytics"
    )

    # Process events
    processed_events = list(processor.process_event_stream(events))

    # Aggregate results
    total_events = len(processed_events)
    error_count = len([e for e in processed_events if "error" in e])
    success_count = total_events - error_count

    # Collect routing stats
    routing_stats = defaultdict(int)
    for event in processed_events:
        if "destinations" in event:
            for dest in event["destinations"]:
                routing_stats[dest] += 1

    return {
        "result": {
            "processed_events": processed_events,
            "total_events": total_events,
            "success_count": success_count,
            "error_count": error_count,
            "routing_stats": dict(routing_stats)
        }
    }

# Create event processor node
event_processor_node = PythonCodeNode.from_function(
    name="event_processor",
    func=event_processing_workflow
)
```

## Stream Processing Patterns

### Backpressure Handling

```python
import asyncio
from asyncio import Queue
from typing import AsyncGenerator, Dict, Any

class BackpressureHandler:
    """Handle backpressure in streaming systems."""

    def __init__(self, max_queue_size: int = 1000, strategy: str = "drop_oldest"):
        self.max_queue_size = max_queue_size
        self.strategy = strategy  # drop_oldest, drop_newest, block, sample
        self.queue = Queue(maxsize=max_queue_size)
        self.dropped_count = 0
        self.sampling_rate = 0.1  # For sampling strategy

    async def handle_message(self, message: Dict[str, Any]) -> bool:
        """Handle incoming message with backpressure strategy."""

        if self.queue.qsize() < self.max_queue_size:
            await self.queue.put(message)
            return True

        # Queue is full, apply backpressure strategy
        if self.strategy == "drop_oldest":
            try:
                self.queue.get_nowait()  # Remove oldest
                await self.queue.put(message)
                self.dropped_count += 1
                return True
            except:
                return False

        elif self.strategy == "drop_newest":
            self.dropped_count += 1
            return False  # Drop the new message

        elif self.strategy == "block":
            await self.queue.put(message)  # This will block
            return True

        elif self.strategy == "sample":
            import random
            if random.random() < self.sampling_rate:
                try:
                    self.queue.get_nowait()  # Remove one message
                    await self.queue.put(message)
                    return True
                except:
                    return False
            else:
                self.dropped_count += 1
                return False

        return False

    async def get_messages(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Get messages from queue."""
        while True:
            try:
                message = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                yield message
            except asyncio.TimeoutError:
                break

    def get_stats(self) -> Dict[str, Any]:
        """Get backpressure statistics."""
        return {
            "queue_size": self.queue.qsize(),
            "max_queue_size": self.max_queue_size,
            "dropped_count": self.dropped_count,
            "strategy": self.strategy
        }

# Use backpressure handler in streaming workflow
def backpressure_stream_processor(stream_data: List[Dict], config: Dict = None) -> Dict:
    """Process streaming data with backpressure handling."""
    import asyncio

    async def process_with_backpressure():
        if config is None:
            config = {}

        # Setup backpressure handler
        handler = BackpressureHandler(
            max_queue_size=config.get("max_queue_size", 100),
            strategy=config.get("backpressure_strategy", "drop_oldest")
        )

        # Simulate high-rate message processing
        processed_messages = []

        # Add messages to queue (simulating fast producer)
        for message in stream_data:
            success = await handler.handle_message(message)
            if not success:
                print(f"Failed to queue message: {message.get('id', 'unknown')}")

        # Process messages from queue (simulating slower consumer)
        async for message in handler.get_messages():
            # Simulate processing delay
            await asyncio.sleep(0.01)

            processed_messages.append({
                "id": message.get("id"),
                "processed_at": time.time(),
                "data": message.get("data")
            })

        stats = handler.get_stats()

        return {
            "processed_messages": processed_messages,
            "backpressure_stats": stats,
            "total_input": len(stream_data),
            "total_processed": len(processed_messages)
        }

    # Execute with backpressure handling
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(process_with_backpressure())
        return {"result": results}
    finally:
        loop.close()

# Create backpressure processor
backpressure_processor = PythonCodeNode.from_function(
    name="backpressure_processor",
    func=backpressure_stream_processor
)
```

## Best Practices

### 1. Streaming Architecture

```python
# Comprehensive streaming configuration
streaming_config = {
    "websocket": {
        "connection_timeout": 30.0,
        "message_timeout": 5.0,
        "auto_reconnect": True,
        "max_reconnect_attempts": 5,
        "exponential_backoff": True
    },

    "batching": {
        "batch_size": 100,
        "batch_timeout": 1.0,
        "adaptive_batching": True
    },

    "windowing": {
        "window_size_seconds": 60,
        "slide_interval_seconds": 10,
        "late_arrival_grace_period": 5
    },

    "backpressure": {
        "max_queue_size": 10000,
        "strategy": "drop_oldest",
        "monitoring_enabled": True
    }
}
```

### 2. Stream Monitoring

```python
def monitor_stream_health(stream_stats: Dict) -> Dict:
    """Monitor streaming system health."""

    alerts = []

    # Check throughput
    if stream_stats.get("rate_per_second", 0) < 1:
        alerts.append("LOW_THROUGHPUT")

    # Check backpressure
    queue_utilization = stream_stats.get("queue_size", 0) / stream_stats.get("max_queue_size", 1)
    if queue_utilization > 0.8:
        alerts.append("HIGH_QUEUE_UTILIZATION")

    # Check error rate
    error_rate = stream_stats.get("error_count", 0) / max(stream_stats.get("total_processed", 1), 1)
    if error_rate > 0.05:  # 5% error rate
        alerts.append("HIGH_ERROR_RATE")

    # Check latency
    if stream_stats.get("average_latency", 0) > 5.0:  # 5 second latency
        alerts.append("HIGH_LATENCY")

    return {
        "health_status": "healthy" if not alerts else "degraded",
        "alerts": alerts,
        "metrics": stream_stats
    }
```

### 3. Stream Testing

```python
def create_test_stream(message_count: int = 1000, rate_per_second: int = 100) -> List[Dict]:
    """Create test stream data for validation."""

    import uuid
    import time

    messages = []
    start_time = time.time()

    for i in range(message_count):
        # Calculate timestamp for desired rate
        timestamp = start_time + (i / rate_per_second)

        message = {
            "id": str(uuid.uuid4()),
            "timestamp": timestamp,
            "sequence": i,
            "event_type": ["click", "view", "purchase"][i % 3],
            "user_id": f"user_{i % 100}",  # 100 unique users
            "data": {
                "value": i * 10,
                "metadata": {"test": True}
            }
        }
        messages.append(message)

    return messages
```

## Related Guides

**Prerequisites:**
- [Production](04-production.md) - Core production patterns
- [Reliability Patterns](04-reliability-patterns.md) - Circuit breakers, retries
- [Fundamentals](01-fundamentals-core-concepts.md) - Core SDK concepts

**Next Steps:**
- [Troubleshooting](05-troubleshooting.md) - Debug streaming issues
- [Custom Development](06-custom-development.md) - Build custom streaming nodes

---

**Build real-time systems that process streaming data with high throughput, low latency, and reliable delivery!**
