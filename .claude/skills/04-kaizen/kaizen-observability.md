# Kaizen Observability

Monitor, trace, and debug AI agent execution with structured logging and metrics.

## SpanContext

Track execution spans for timing and correlation.

```python
from kailash_kaizen.observability import SpanContext
import time

# Create a span for tracking
span = SpanContext(name="research_task", trace_id="trace-001")
span.start()

# ... do work ...
time.sleep(0.1)

span.end()
print(f"Duration: {span.duration_ms}ms")
print(f"Trace ID: {span.trace_id}")
```

## MetricsCollector

Collect and aggregate execution metrics.

```python
from kailash_kaizen.observability import MetricsCollector

metrics = MetricsCollector()

# Record metrics
metrics.record("agent_calls", 1)
metrics.record("tokens_used", 150)
metrics.record("latency_ms", 230)

# Get aggregated metrics
summary = metrics.summary()
print(f"Total agent calls: {summary['agent_calls']}")
print(f"Total tokens: {summary['tokens_used']}")
print(f"Avg latency: {summary['latency_ms_avg']}ms")
```

## LogAggregator

Aggregate logs from multiple agents.

```python
from kailash_kaizen.observability import LogAggregator

logs = LogAggregator()

# Add log entries
logs.add("researcher", "info", "Starting research on AI safety")
logs.add("researcher", "debug", "Found 15 relevant papers")
logs.add("writer", "info", "Generating summary")
logs.add("writer", "warning", "Output exceeded max length, truncating")

# Query logs
researcher_logs = logs.get_by_agent("researcher")
warnings = logs.get_by_level("warning")
all_logs = logs.get_all()
```

## ObservabilityManager

Unified observability combining spans, metrics, and logs.

```python
from kailash_kaizen.observability import ObservabilityManager

obs = ObservabilityManager()

# Start a traced operation
with obs.span("full_pipeline") as span:
    # Research phase
    with obs.span("research") as research_span:
        obs.log("researcher", "info", "Starting research")
        # ... research work ...
        obs.record("research_sources", 15)

    # Writing phase
    with obs.span("writing") as write_span:
        obs.log("writer", "info", "Generating article")
        # ... writing work ...
        obs.record("output_words", 500)

# Get full report
report = obs.report()
print(f"Total duration: {report['total_duration_ms']}ms")
print(f"Spans: {len(report['spans'])}")
print(f"Metrics: {report['metrics']}")
```

## Integration with Agents

```python
from kailash_kaizen import BaseAgent
from kailash_kaizen.observability import ObservabilityManager

class ObservableAgent(BaseAgent):
    def __init__(self, name, obs=None):
        super().__init__(name=name)
        self.obs = obs or ObservabilityManager()

    def run(self, input_text):
        with self.obs.span(f"{self.name}_execution") as span:
            self.obs.log(self.name, "info", f"Processing: {input_text[:50]}")

            result = self._process(input_text)

            self.obs.record(f"{self.name}_tokens", len(input_text.split()))
            self.obs.log(self.name, "info", "Complete")

            return result

    def _process(self, input_text):
        return {"response": f"Processed: {input_text}"}
```

## Best Practices

1. **Use spans for timing** -- wrap operations in spans for duration tracking
2. **Log at appropriate levels** -- info for key events, debug for details, warning for issues
3. **Record meaningful metrics** -- token counts, latency, error rates
4. **Use trace IDs for correlation** -- link spans across agent boundaries
5. **Don't over-instrument** -- focus on key operations, not every function call

<!-- Trigger Keywords: observability, tracing, metrics, logging, spans, monitoring, agent debugging -->
