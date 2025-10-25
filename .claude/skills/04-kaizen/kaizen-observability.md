# Kaizen Observability & Distributed Tracing

**Quick reference for complete observability with Jaeger, Prometheus, and ELK Stack**

## Overview

Kaizen v0.5.0 includes production-ready observability with zero performance impact (-0.06% overhead). Complete monitoring stack with distributed tracing (OpenTelemetry/Jaeger), metrics collection (Prometheus), structured logging (JSON/ELK), and audit trails (JSONL).

**⚠️ IMPORTANT: Observability is OPT-IN**
- ✅ **100% backward compatible** - existing agents work without any changes
- ✅ **No migration required** - agents work perfectly fine without observability
- ✅ **Zero breaking changes** - observability is disabled by default
- ✅ **Enable when needed** - call `agent.enable_observability()` to activate monitoring

Agents created without calling `enable_observability()` function normally with no overhead.

## Quick Start - Complete Observability

```python
from kaizen.core.base_agent import BaseAgent

# Create agent
agent = BaseAgent(config=config, signature=signature)

# Enable full observability stack (one line!)
agent.enable_observability(
    service_name="my-agent",     # Service name for all systems
    enable_metrics=True,         # Prometheus metrics
    enable_logging=True,         # Structured JSON logs
    enable_tracing=True,         # Distributed tracing
    enable_audit=True,           # Compliance audit trails
)

# All operations now tracked with zero overhead
result = agent.run(question="test")
```

**Access Points**:
- Traces: `http://localhost:16686` (Jaeger UI)
- Metrics: `http://localhost:9090` (Prometheus)
- Dashboards: `http://localhost:3000` (Grafana)
- Logs: `http://localhost:5601` (Kibana)

## Core Components

### System 3: TracingManager (Distributed Tracing)
- OpenTelemetry TracerProvider with Jaeger OTLP exporter
- Batch span processor for efficient export
- Thread-safe concurrent span creation
- Performance: <1ms per span creation

### System 4: MetricsManager (Prometheus Metrics)
- Counter, Gauge, Histogram with p50/p95/p99 percentiles
- Prometheus-compatible exposition format
- Production overhead: -0.06% (validated with 100 OpenAI calls)

### System 5: LoggingManager (Structured Logging)
- JSON-formatted logs for ELK Stack integration
- Context propagation for trace correlation
- Centralized logger management

### System 6: AuditTrailManager (Compliance)
- Append-only JSONL for immutable audit trails
- SOC2, GDPR, HIPAA, PCI-DSS compliance ready
- 0.57ms p95 latency (<10ms target, 17.5x margin)

### System 7: ObservabilityManager (Unified Interface)
- Single interface for all observability subsystems
- Selective component enabling/disabling
- BaseAgent integration via hook manager

```python
from kaizen.core.autonomy.observability import TracingManager

manager = TracingManager(
    service_name="my-service",
    jaeger_host="localhost",
    jaeger_port=4317,
    batch_size=512,              # Batch span processor max queue
    batch_timeout_ms=5000,       # Batch export timeout
    max_export_batch_size=512,   # Max spans per export batch
)
```

### TracingHook
- Integrates TracingManager with hook system
- Automatic span creation for hook events
- PRE/POST event pairing with actual operation duration
- Event filtering support

```python
from kaizen.core.autonomy.hooks.builtin import TracingHook
from kaizen.core.autonomy.hooks import HookEvent

hook = TracingHook(
    tracing_manager=manager,
    events_to_trace=[HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE],  # Optional filter
)

# Register with hook manager
agent._hook_manager.register_hook(hook)
```

### BaseAgent Integration
- `_hook_manager`: HookManager instance for all agents
- `enable_observability()`: Convenience method for one-line setup
- Automatic cleanup in `agent.cleanup()`

## Traced Events

All hook events are traceable:
- `PRE_AGENT_LOOP` / `POST_AGENT_LOOP`: Agent lifecycle
- `PRE_TOOL_USE` / `POST_TOOL_USE`: Tool executions
- `PRE_LLM_CALL` / `POST_LLM_CALL`: LLM API calls
- `PRE_MEMORY_READ` / `POST_MEMORY_READ`: Memory operations
- Custom events from your hooks

## Span Hierarchy

TracingHook automatically creates parent-child relationships:

```
pre_agent_loop (root span)
├── pre_tool_use:load_data
│   └── post_tool_use:load_data (child of PRE, actual duration)
├── pre_tool_use:analyze_data
│   └── post_tool_use:analyze_data
└── post_agent_loop (ends root span)
```

**Key Features**:
- PRE events create long-running spans
- POST events end PRE spans and calculate actual operation duration
- Composite keys: `(trace_id, event_pair:tool_name)` for multiple tool calls
- Span attributes from HookContext (agent_id, event_type, tool_name, etc.)

## Advanced Usage

### Manual Hook Registration

```python
from kaizen.core.autonomy.hooks.manager import HookManager

# Access agent's hook manager
hook_manager = agent._hook_manager

# Register hook for all events it declares
hook_manager.register_hook(tracing_hook)

# Or register for specific events
hook_manager.register(HookEvent.PRE_TOOL_USE, tracing_hook)
```

### Custom TracingManager

```python
# Advanced configuration
manager = TracingManager(
    service_name="production-agent",
    jaeger_host="jaeger.prod.example.com",
    jaeger_port=4317,
    insecure=False,              # Use secure gRPC
    batch_size=1024,             # Larger batch size
    batch_timeout_ms=10000,      # Longer timeout
    max_export_batch_size=512,
)

# Force export (e.g., before shutdown)
manager.force_flush(timeout=30)

# Shutdown (exports all pending spans)
manager.shutdown(timeout=30)
```

### Event Filtering

```python
# Trace only tool_use and llm_call events
hook = TracingHook(
    tracing_manager=manager,
    events_to_trace=[
        HookEvent.PRE_TOOL_USE,
        HookEvent.POST_TOOL_USE,
        HookEvent.PRE_LLM_CALL,
        HookEvent.POST_LLM_CALL,
    ],
)
```

## Production Deployment

### Complete Grafana Observability Stack

Kaizen includes a production-ready Docker Compose stack with complete observability infrastructure:

```bash
# Start complete stack (Jaeger, Prometheus, Grafana, Elasticsearch, Kibana)
cd docs/observability
docker-compose up -d

# Or use convenience script
./scripts/start_observability.sh
```

**Included Components**:
- **Jaeger**: Distributed tracing (UI: http://localhost:16686)
- **Prometheus**: Metrics collection (UI: http://localhost:9090)
- **Grafana**: Unified dashboards (UI: http://localhost:3000)
- **Elasticsearch**: Log storage backend
- **Kibana**: Log analysis (UI: http://localhost:5601)
- **10+ Pre-built Grafana Dashboards**: Agent performance, LLM metrics, system health

### Agent Configuration

```python
# In production, use environment variables
import os

agent.enable_observability(
    service_name=os.getenv("SERVICE_NAME", "my-agent"),
    enable_metrics=True,   # Prometheus metrics
    enable_logging=True,   # JSON logs to ELK
    enable_tracing=True,   # Jaeger tracing
    enable_audit=True,     # Compliance audit trails
)
```

### Security (Enterprise-Grade)

- **0 Critical Vulnerabilities**: Resolved 5 CVEs
- **SSL/TLS**: Automated certificate generation
- **Authentication**: OAuth + LDAP + Basic Auth support
- **Secrets Management**: Template-based production secrets
- **32 Security Tests**: Automated validation

## Testing

### Integration Testing (NO MOCKING - Tier 2)

```python
import pytest
from tests.utils.docker_config import JAEGER_CONFIG, is_jaeger_available

@pytest.mark.skipif(not is_jaeger_available(), reason="Jaeger not running")
async def test_agent_tracing():
    """Test real Jaeger export"""
    # Setup
    manager = TracingManager(service_name="test-service")
    hook = TracingHook(tracing_manager=manager)
    agent._hook_manager.register_hook(hook)

    # Execute agent workflow
    result = agent.run(question="test")

    # Force flush
    manager.force_flush()
    time.sleep(2)  # Wait for Jaeger indexing

    # Query Jaeger API
    traces = query_jaeger_traces("test-service")
    assert len(traces) > 0
```

### E2E Testing with Jaeger UI

```python
def query_jaeger_traces(service_name: str) -> List[Dict]:
    """Query Jaeger HTTP API for traces"""
    response = requests.get(
        f"{JAEGER_CONFIG['base_url']}/api/traces",
        params={"service": service_name, "limit": 100},
    )
    return response.json().get("data", [])
```

## Performance (Production Validated)

- **Production Overhead**: -0.06% (essentially zero, validated with 100 real OpenAI API calls)
- **Audit Trail Latency**: 0.57ms p95 (<10ms target, 17.5x margin)
- **Span Creation**: <1ms per span
- **Testing Approach**: NO MOCKING in Tiers 2-3 tests (validated with real infrastructure)

## Common Patterns

### Multi-Agent Tracing

```python
# Use shared TracingManager for all agents
manager = TracingManager(service_name="multi-agent-system")

# Each agent gets its own trace_id via HookContext
agent1 = SupervisorAgent(config=config)
agent1.enable_observability()  # Uses agent class name

agent2 = WorkerAgent(config=config)
agent2.enable_observability()  # Uses agent class name

# Traces appear separately in Jaeger
# Search by agent_id or service_name
```

### Long-Running Operations

```python
# PRE spans stay active until POST event
# Ideal for tracking long operations (10s, 1m, 10m+)

# PRE event starts span
context_pre = HookContext(
    event_type=HookEvent.PRE_TOOL_USE,
    agent_id=agent.agent_id,
    trace_id=trace_id,
    timestamp=time.time(),
    data={"operation": "batch_processing"},
)

await hook.handle(context_pre)

# ... long-running operation ...
time.sleep(600)  # 10 minutes

# POST event ends span with actual duration
context_post = HookContext(
    event_type=HookEvent.POST_TOOL_USE,
    agent_id=agent.agent_id,
    trace_id=trace_id,
    timestamp=time.time(),
    data={"operation": "batch_processing", "status": "completed"},
)

await hook.handle(context_post)
```

## Troubleshooting

### Spans Not Appearing in Jaeger

1. **Check Jaeger is running**:
   ```bash
   curl http://localhost:16686/api/services
   ```

2. **Verify OTLP endpoint**:
   ```python
   # Correct: OTLP gRPC port (4317)
   agent.enable_observability(jaeger_port=4317)

   # Wrong: UI port (16686) or collector HTTP (14268)
   ```

3. **Force flush and wait**:
   ```python
   manager.force_flush()
   time.sleep(2)  # Wait for indexing
   ```

### Missing Child Spans

- **Issue**: Only seeing 2 spans when expecting 8
- **Cause**: PRE events without matching POST events
- **Fix**: Always send POST event after PRE event:
  ```python
  # PRE event
  await hook.handle(pre_context)

  # ... operation ...

  # POST event (required!)
  await hook.handle(post_context)
  ```

### "Invalid Parent Span IDs" Warning

- **Cause**: Broken parent-child relationships due to missing spans
- **Fix**: Ensure all PRE spans are properly ended with POST events

## API Reference

### TracingManager

**Constructor**:
- `service_name` (str): Service name for Jaeger
- `jaeger_host` (str): Jaeger OTLP host (default: "localhost")
- `jaeger_port` (int): Jaeger OTLP gRPC port (default: 4317)
- `insecure` (bool): Use insecure gRPC (default: True)
- `batch_size` (int): Max queue size (default: 512)
- `batch_timeout_ms` (int): Export timeout in ms (default: 5000)
- `max_export_batch_size` (int): Max spans per batch (default: 512)

**Methods**:
- `create_span_from_context(context, parent_span=None)`: Create span from HookContext
- `update_span_from_result(span, result)`: Update span status from HookResult
- `record_exception(span, exception)`: Record exception in span
- `force_flush(timeout=30)`: Force export pending spans
- `shutdown(timeout=30)`: Shutdown and export all spans

### TracingHook

**Constructor**:
- `tracing_manager` (TracingManager): TracingManager instance
- `events_to_trace` (List[HookEvent]): Optional event filter (None = all events)

**Methods**:
- `handle(context)`: Handle hook event and create span

### BaseAgent

**Methods**:
- `enable_observability(service_name=None, jaeger_host="localhost", jaeger_port=4317, events_to_trace=None)`: Enable tracing (one-line setup)

**Attributes**:
- `_hook_manager` (HookManager): Hook manager instance

## Resources

- **Implementation**: `src/kaizen/core/autonomy/observability/tracing_manager.py`
- **Hook Integration**: `src/kaizen/core/autonomy/hooks/builtin/tracing_hook.py`
- **Tests**: `tests/unit/core/autonomy/observability/test_tracing_manager.py`
- **Jaeger Documentation**: https://www.jaegertracing.io/docs/
- **OpenTelemetry Python**: https://opentelemetry.io/docs/languages/python/

## Examples

See `examples/autonomy/observability/` for complete working examples:
- `01_basic_tracing.py`: Simple tracing setup
- `02_multi_agent_tracing.py`: Multiple agents with shared TracingManager
- `03_custom_events.py`: Custom hook events and filtering
