# OpenTelemetry Progressive Tracing

## TracingLevel Configuration

```python
from kailash.runtime.tracing import get_workflow_tracer, TracingLevel, configure_tracing

# Env var: KAILASH_TRACING_LEVEL=none|basic|detailed|full
# Default: BASIC if opentelemetry installed, NONE otherwise

# Programmatic override
configure_tracing(level=TracingLevel.DETAILED, service_name="my-app")
```

| Level    | What's traced                                         |
| -------- | ----------------------------------------------------- |
| NONE     | Nothing                                               |
| BASIC    | Workflow-level spans (start/end, workflow_id, run_id) |
| DETAILED | + Node-level spans (node_id, node_type, duration)     |
| FULL     | + Database queries, DataFlow operations, custom spans |

## Node Instrumentation (DETAILED+)

```python
from kailash.runtime.instrumentation.nodes import NodeInstrumentor

instrumentor = NodeInstrumentor(tracer)
# Wraps node execution with child spans:
# - node.id, node.type, node.duration_ms, node.input_size, node.output_size
```

## Database Instrumentation (FULL)

```python
from kailash.runtime.instrumentation.database import DatabaseInstrumentor

instrumentor = DatabaseInstrumentor(tracer)
instrumentor.instrument(connection_manager)
# Instruments execute/fetchone/fetchall with OTel DB semantic conventions:
# db.system, db.statement (truncated), db.operation, db.row_count
```

## DataFlow Instrumentation (FULL)

```python
from kailash.runtime.instrumentation.dataflow import DataFlowInstrumentor
# Same DB conventions for DataFlow-specific operations
```

## Prometheus Metrics Bridge

```python
from kailash.runtime.metrics import MetricsBridge

bridge = MetricsBridge()
# Exposes:
# - kailash_workflow_executions_total (counter)
# - kailash_workflow_duration_seconds (histogram)
# - kailash_node_execution_duration_seconds (histogram)
bridge.record_workflow(workflow_id, duration_s, status="ok")
bridge.record_node(node_id, node_type, duration_s)
```

## Source Files

- `src/kailash/runtime/tracing.py` — TracingLevel, WorkflowTracer
- `src/kailash/runtime/instrumentation/` — nodes, dataflow, database
- `src/kailash/runtime/metrics.py` — MetricsBridge
