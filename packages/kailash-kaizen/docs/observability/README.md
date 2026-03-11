# Kaizen Observability & Performance Monitoring

Comprehensive guide to the Kaizen observability system with metrics, logging, tracing, and audit trails.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Architecture](#architecture)
4. [System Components](#system-components)
5. [Usage Guide](#usage-guide)
6. [API Reference](#api-reference)
7. [Grafana Dashboards](#grafana-dashboards)
8. [Performance & Overhead](#performance--overhead)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)
11. [Examples](#examples)

## Overview

The Kaizen observability system provides comprehensive production monitoring for AI agents:

### Four Integrated Systems

| System | Purpose | Key Features |
|--------|---------|--------------|
| **System 3: Distributed Tracing** | Request flow visualization | OpenTelemetry, Jaeger UI, <1ms overhead |
| **System 4: Metrics Collection** | Performance monitoring | Prometheus export, p50/p95/p99, <2% overhead |
| **System 5: Structured Logging** | Contextual logging | JSON format, ELK-ready, <5% overhead |
| **System 6: Audit Trails** | Compliance & governance | Immutable logs, SOC2/GDPR/HIPAA, <10ms append |

### System 7: Unified Manager

`ObservabilityManager` provides a single interface for all observability operations with selective component enabling/disabling.

## Quick Start

### 1. Install Dependencies

```bash
pip install kailash-kaizen opentelemetry-api opentelemetry-sdk
```

### 2. Enable Observability

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField

class QASignature(Signature):
    question: str = InputField(description="Question")
    answer: str = OutputField(description="Answer")

# Create agent
agent = BaseAgent(config=config, signature=QASignature())

# Enable full observability (all 4 systems)
obs = agent.enable_observability(
    service_name="qa-agent",
    jaeger_host="localhost",
    jaeger_port=4317,
)

# Run agent - metrics, logs, traces, audits are automatic
result = agent.run(question="What is Kaizen?")
```

### 3. View Observability Data

- **Traces**: http://localhost:16686 (Jaeger UI)
- **Metrics**: http://localhost:3000 (Grafana dashboards)
- **Logs**: Check console or ELK Stack
- **Audits**: `~/.kaizen/audit_trail.jsonl`

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        BaseAgent                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           ObservabilityManager (System 7)               │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────┐│  │
│  │  │  Metrics   │  │  Logging   │  │  Tracing   │  │Audit││  │
│  │  │ (System 4) │  │ (System 5) │  │ (System 3) │  │ (6)││  │
│  │  └────┬───────┘  └────┬───────┘  └────┬───────┘  └──┬─┘│  │
│  └───────┼───────────────┼───────────────┼─────────────┼───┘  │
└──────────┼───────────────┼───────────────┼─────────────┼──────┘
           │               │               │             │
           ▼               ▼               ▼             ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
    │Prometheus│   │ELK Stack │   │  Jaeger  │   │  Files   │
    │  (Pull)  │   │  (Push)  │   │  (Push)  │   │ (Append) │
    └─────┬────┘   └──────────┘   └──────────┘   └──────────┘
          │
          ▼
    ┌──────────┐
    │ Grafana  │
    │Dashboards│
    └──────────┘
```

### Data Flow

1. **Agent Operations** → Trigger observability events
2. **ObservabilityManager** → Routes to appropriate systems
3. **Metrics** → Collected in-memory, exported to Prometheus
4. **Logs** → JSON-formatted, sent to stdout/ELK
5. **Traces** → Sent to Jaeger via OTLP
6. **Audits** → Appended to immutable JSONL file
7. **Grafana** → Queries Prometheus for visualization

## System Components

### System 3: Distributed Tracing

**Purpose**: Visualize request flow and identify performance bottlenecks

**Technology Stack**:
- OpenTelemetry for instrumentation
- OTLP gRPC for export
- Jaeger for visualization

**Key Features**:
- Automatic span creation from hook events
- Parent-child span hierarchy
- Trace ID propagation across agents
- Exception recording in spans
- <1ms overhead per span

**Example**:
```python
# Tracing is automatic with enable_observability()
obs = agent.enable_observability(
    service_name="my-agent",
    jaeger_host="localhost",
    jaeger_port=4317,
)

# View traces at http://localhost:16686
result = agent.run(question="Test")
```

### System 4: Metrics Collection

**Purpose**: Monitor agent performance and resource usage

**Metric Types**:
- **Counter**: Monotonically increasing values (e.g., total requests)
- **Gauge**: Point-in-time values (e.g., memory usage)
- **Histogram**: Distribution of values (e.g., latency percentiles)

**Key Features**:
- Prometheus export format
- Percentile calculation (p50, p95, p99)
- Label-based dimensions
- Async/sync timer context managers
- <2% overhead target

**Example**:
```python
# Record custom metrics
await obs.record_metric(
    "api_calls_total",
    1.0,
    type="counter",
    labels={"provider": "openai", "model": "gpt-4"}
)

await obs.record_metric(
    "memory_bytes",
    1024000,
    type="gauge",
    labels={"agent_id": "qa-agent"}
)

await obs.record_metric(
    "request_duration_ms",
    150.5,
    type="histogram",
    labels={"operation": "llm_call"}
)

# Export for Prometheus
metrics_text = await obs.export_metrics()
```

### System 5: Structured Logging

**Purpose**: Contextual logging with correlation IDs

**Key Features**:
- JSON-formatted logs
- Context propagation (trace_id, span_id, agent_id)
- ELK Stack integration
- Log level support (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- <5% overhead target

**Example**:
```python
# Get logger
logger = obs.get_logger("qa-agent")

# Add persistent context
logger.add_context(
    agent_id="qa-agent",
    session_id="session-123",
    user_id="user@example.com"
)

# Log with additional fields
logger.info("Processing question",
    question="What is AI?",
    estimated_tokens=100
)

# Context is automatically included:
# {
#   "timestamp": "2025-10-24T12:00:00.000Z",
#   "level": "INFO",
#   "message": "Processing question",
#   "context": {
#     "agent_id": "qa-agent",
#     "session_id": "session-123",
#     "user_id": "user@example.com",
#     "question": "What is AI?",
#     "estimated_tokens": 100
#   },
#   "trace_id": "abc123",
#   "span_id": "def456"
# }
```

### System 6: Audit Trails

**Purpose**: Immutable compliance logging for governance

**Key Features**:
- Append-only JSONL storage
- Immutability for compliance
- Query by agent, action, time range
- SOC2, GDPR, HIPAA ready
- <10ms append latency (0.57ms actual)

**Example**:
```python
# Record audit event
await obs.record_audit(
    agent_id="qa-agent",
    action="tool_execute",
    details={
        "tool_name": "bash",
        "command": "ls -la",
        "danger_level": "MODERATE"
    },
    result="success",
    user_id="user@example.com",
    metadata={"session_id": "session-123"}
)

# Query audit trail
entries = await obs.query_audit_by_agent("qa-agent")
for entry in entries:
    print(f"{entry.timestamp}: {entry.action} - {entry.result}")
```

### System 7: Unified Manager

**Purpose**: Single interface for all observability operations

**Key Features**:
- Selective component enabling
- Convenience methods for all systems
- Centralized configuration
- Resource management (shutdown)

**Example**:
```python
from kaizen.core.autonomy.observability import ObservabilityManager

# Full observability
obs = ObservabilityManager(
    service_name="qa-agent",
    enable_metrics=True,
    enable_logging=True,
    enable_tracing=True,
    enable_audit=True
)

# Lightweight observability (metrics + logging only)
obs_lite = ObservabilityManager(
    service_name="qa-agent",
    enable_metrics=True,
    enable_logging=True,
    enable_tracing=False,  # Disabled
    enable_audit=False     # Disabled
)

# Use observability
logger = obs.get_logger("component")
await obs.record_metric("counter", 1.0, type="counter")
await obs.record_audit("agent-1", "action", {}, "success")

# Cleanup
obs.shutdown()
```

## Usage Guide

### Enabling Observability

#### Option 1: BaseAgent (Recommended)

```python
from kaizen.core.base_agent import BaseAgent

agent = BaseAgent(config=config, signature=signature)

# Enable with all defaults
obs = agent.enable_observability()

# Enable with custom configuration
obs = agent.enable_observability(
    service_name="custom-agent",  # Default: agent_id
    jaeger_host="jaeger.example.com",
    jaeger_port=4317,
    enable_metrics=True,
    enable_logging=True,
    enable_tracing=True,
    enable_audit=True
)
```

#### Option 2: Direct ObservabilityManager

```python
from kaizen.core.autonomy.observability import ObservabilityManager

obs = ObservabilityManager(
    service_name="my-service",
    enable_metrics=True,
    enable_logging=True,
    enable_tracing=True,
    enable_audit=True
)
```

### Recording Metrics

```python
# Counter: Incrementing values
await obs.record_metric(
    "requests_total",
    1.0,
    type="counter",
    labels={"status": "success", "endpoint": "/api/chat"}
)

# Gauge: Current values
await obs.record_metric(
    "active_sessions",
    42,
    type="gauge",
    labels={"agent_id": "qa-agent"}
)

# Histogram: Distributions
await obs.record_metric(
    "latency_ms",
    250.5,
    type="histogram",
    labels={"operation": "llm_call"}
)

# Export metrics
metrics_text = await obs.export_metrics()
print(metrics_text)
# requests_total{status="success",endpoint="/api/chat"} 1.0
# active_sessions{agent_id="qa-agent"} 42.0
# latency_ms_p50{operation="llm_call"} 250.5
```

### Structured Logging

```python
# Get logger for component
logger = obs.get_logger("my-component")

# Add persistent context
logger.add_context(
    agent_id="qa-agent",
    session_id="session-123"
)

# Log at different levels
logger.debug("Debug message", details="verbose info")
logger.info("Processing started", item_count=100)
logger.warning("Slow operation detected", duration_ms=5000)
logger.error("Operation failed", error_code="E001")

# Clear context
logger.clear_context()
```

### Recording Audit Events

```python
# Record successful action
await obs.record_audit(
    agent_id="qa-agent",
    action="tool_execute",
    details={
        "tool_name": "file_read",
        "file_path": "/data/report.pdf"
    },
    result="success",
    user_id="user@example.com"
)

# Record failed action
await obs.record_audit(
    agent_id="qa-agent",
    action="permission_request",
    details={
        "resource": "database",
        "operation": "write"
    },
    result="denied",
    user_id="user@example.com",
    metadata={"reason": "insufficient_privileges"}
)

# Query audit trail
by_agent = await obs.query_audit_by_agent("qa-agent")
by_action = await obs.query_audit_by_action("tool_execute")
```

### Selective Observability

Enable only the components you need:

```python
# Metrics and logging only (lightweight)
obs = agent.enable_observability(
    enable_metrics=True,
    enable_logging=True,
    enable_tracing=False,
    enable_audit=False
)

# Tracing only (debugging)
obs = agent.enable_observability(
    enable_metrics=False,
    enable_logging=False,
    enable_tracing=True,
    enable_audit=False
)

# Audit only (compliance)
obs = agent.enable_observability(
    enable_metrics=False,
    enable_logging=False,
    enable_tracing=False,
    enable_audit=True
)

# Check what's enabled
if obs.is_component_enabled("metrics"):
    await obs.record_metric("counter", 1.0, type="counter")

enabled = obs.get_enabled_components()
print(f"Enabled: {enabled}")  # ['metrics', 'logging']
```

## API Reference

### ObservabilityManager

```python
class ObservabilityManager:
    """Unified observability management."""

    def __init__(
        self,
        service_name: str = "kaizen-agent",
        enable_metrics: bool = True,
        enable_logging: bool = True,
        enable_tracing: bool = True,
        enable_audit: bool = True
    )

    # Logging
    def get_logger(self, name: str) -> StructuredLogger | None

    # Metrics
    async def record_metric(
        self,
        name: str,
        value: float,
        type: MetricType = "counter",
        labels: dict[str, str] | None = None
    ) -> None

    async def export_metrics(self) -> str

    # Tracing
    def get_tracing_manager(self) -> TracingManager | None

    # Audit
    async def record_audit(
        self,
        agent_id: str,
        action: str,
        details: dict[str, Any],
        result: AuditResult,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> None

    async def query_audit_by_agent(self, agent_id: str)
    async def query_audit_by_action(self, action: str)

    # Status
    def is_component_enabled(self, component: str) -> bool
    def get_enabled_components(self) -> list[str]
    def get_service_name(self) -> str

    # Cleanup
    def shutdown(self) -> None
```

### MetricsCollector

```python
class MetricsCollector:
    """Metrics collection with Prometheus export."""

    def counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None
    ) -> None

    def gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None
    ) -> None

    def histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None
    ) -> None

    @asynccontextmanager
    async def timer(
        self,
        name: str,
        labels: dict[str, str] | None = None
    )

    @contextmanager
    def timer_sync(
        self,
        name: str,
        labels: dict[str, str] | None = None
    )

    async def export(self) -> str
```

### StructuredLogger

```python
class StructuredLogger:
    """Structured JSON logging with context."""

    def add_context(self, **kwargs) -> None
    def get_context(self) -> dict[str, Any]
    def clear_context(self) -> None

    def debug(self, message: str, **extra) -> None
    def info(self, message: str, **extra) -> None
    def warning(self, message: str, **extra) -> None
    def error(self, message: str, **extra) -> None
    def critical(self, message: str, **extra) -> None
```

### AuditTrailManager

```python
class AuditTrailManager:
    """Audit trail management."""

    async def record(
        self,
        agent_id: str,
        action: str,
        details: dict[str, Any],
        result: AuditResult,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> None

    async def query_by_agent(self, agent_id: str) -> list[AuditEntry]
    async def query_by_action(self, action: str) -> list[AuditEntry]
    async def query_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> list[AuditEntry]
```

## Grafana Dashboards

Three pre-built dashboards for comprehensive monitoring:

### 1. Agent Monitoring Dashboard

**Location**: `grafana/dashboards/agent-monitoring-dashboard.json`

**Panels**:
- Agent Loop Duration (p95) with alert
- Agent Loop Success Rate
- Tool Execution Count and Latency
- API Calls by Provider
- API Cost per Hour
- Active Agents
- Memory Usage
- Error Rate
- Audit Events per Minute
- Permission Approval Rate
- Tool Execution Success Rate

**Use For**: Real-time agent health monitoring

### 2. Performance Metrics Dashboard

**Location**: `grafana/dashboards/performance-metrics-dashboard.json`

**Panels**:
- Observability Overhead (metrics, logging, tracing, audit)
- CPU and Memory Usage
- Latency Percentile Distributions
- Throughput (ops/sec)
- Disk and Network I/O
- GC Pause Time
- Cache Hit Rate
- Performance Target Compliance

**Use For**: Performance optimization and overhead tracking

### 3. Audit & Compliance Dashboard

**Location**: `grafana/dashboards/audit-compliance-dashboard.json`

**Panels**:
- Audit Events Volume and Trends
- Audit Events by Action Type and Result
- Active Users
- Audit Trail Completeness
- Critical Actions Count
- Top Users and Agents
- Permission Requests
- Compliance Scores (SOC2, GDPR, HIPAA)
- Audit Event Timeline
- Retention Policy Compliance
- Immutability Verification

**Use For**: Compliance reporting and governance

### Setup

See `grafana/README.md` for complete setup instructions.

## Performance & Overhead

### NFR Targets (ADR-017)

| Component | Target | Actual (Production) | Status |
|-----------|--------|---------------------|--------|
| Metrics Collection | <2% overhead | ~0.001% (500ms op) | ✅ Exceeds |
| Structured Logging | <5% overhead | ~0.06% (500ms op) | ✅ Exceeds |
| Distributed Tracing | <1% overhead | <0.001% (500ms op) | ✅ Exceeds |
| Audit Append Latency | <10ms p95 | 0.57ms p95 | ✅ Exceeds |

### Absolute Costs

| Operation | Time | Impact on 500ms Agent Loop |
|-----------|------|----------------------------|
| Counter increment | 0.005ms | 0.001% |
| Gauge update | 0.005ms | 0.001% |
| Histogram observation | 0.005ms | 0.001% |
| Log entry (JSON) | 0.012ms | 0.002% |
| Span creation | <0.001ms | <0.0002% |
| Audit append (avg) | 0.457ms | 0.09% |

**Total Observability Overhead** (typical agent loop):
- 10 metrics: 0.05ms
- 50 log entries: 0.60ms
- 5 spans: 0.01ms
- 3 audit entries: 1.40ms
- **Total**: 2.06ms (~0.4% of 500ms operation)

See `benchmarks/PERFORMANCE_RESULTS.md` for detailed analysis.

## Best Practices

### 1. Selective Observability

Don't enable everything everywhere:

```python
# Production: Full observability for critical agents
critical_agent.enable_observability(
    enable_metrics=True,
    enable_logging=True,
    enable_tracing=True,
    enable_audit=True
)

# Development: Lightweight for debugging
dev_agent.enable_observability(
    enable_metrics=True,
    enable_logging=True,
    enable_tracing=False,
    enable_audit=False
)

# Cost-sensitive: Metrics only
batch_agent.enable_observability(
    enable_metrics=True,
    enable_logging=False,
    enable_tracing=False,
    enable_audit=False
)
```

### 2. Meaningful Metric Names

Follow Prometheus naming conventions:

```python
# Good
await obs.record_metric("http_requests_total", 1.0, type="counter")
await obs.record_metric("memory_bytes", 1024000, type="gauge")
await obs.record_metric("request_duration_seconds", 0.25, type="histogram")

# Bad
await obs.record_metric("requests", 1.0, type="counter")  # Missing unit
await obs.record_metric("mem", 1024000, type="gauge")  # Ambiguous
```

### 3. Use Labels for Dimensions

```python
# Good: Labels for dimensions
await obs.record_metric(
    "api_calls_total",
    1.0,
    type="counter",
    labels={"provider": "openai", "model": "gpt-4", "status": "success"}
)

# Bad: Metric name includes dimensions
await obs.record_metric("api_calls_openai_gpt4_success", 1.0, type="counter")
```

### 4. Context Propagation

Add context once, use everywhere:

```python
logger = obs.get_logger("my-component")

# Add context at session start
logger.add_context(
    session_id="session-123",
    user_id="user@example.com",
    agent_id="qa-agent"
)

# All subsequent logs include context automatically
logger.info("Processing question", question="What is AI?")
logger.info("Calling LLM", model="gpt-4")
logger.info("Response generated", tokens=150)
```

### 5. Audit Sensitive Operations

Always audit actions involving:
- Data access (especially PII/PHI)
- Privilege escalation
- Configuration changes
- File system operations
- External API calls

```python
await obs.record_audit(
    agent_id="qa-agent",
    action="phi_access",
    details={
        "record_id": "patient-123",
        "fields": ["name", "diagnosis", "medications"]
    },
    result="success",
    user_id="doctor@hospital.com",
    metadata={"justification": "patient_care"}
)
```

### 6. Resource Cleanup

Always cleanup observability resources:

```python
agent = BaseAgent(config=config, signature=signature)
obs = agent.enable_observability()

try:
    # Use agent
    result = agent.run(question="Test")
finally:
    # Cleanup (flushes traces, closes audit file)
    agent.cleanup()
```

### 7. Production Deployment

#### Enable Gradual Rollout

```python
# Week 1: Metrics only
obs = agent.enable_observability(
    enable_metrics=True,
    enable_logging=False,
    enable_tracing=False,
    enable_audit=False
)

# Week 2: Add logging
obs = agent.enable_observability(
    enable_metrics=True,
    enable_logging=True,
    enable_tracing=False,
    enable_audit=False
)

# Week 3: Add tracing for 1% of requests
if random.random() < 0.01:
    obs = agent.enable_observability(enable_tracing=True)

# Week 4: Full observability
obs = agent.enable_observability()  # All enabled
```

## Troubleshooting

### Metrics Not Appearing in Prometheus

**Symptom**: Metrics endpoint returns empty or Prometheus shows no data

**Solutions**:

1. **Check metrics endpoint**:
   ```bash
   curl http://localhost:8000/metrics
   ```

2. **Verify metrics are being recorded**:
   ```python
   await obs.record_metric("test_metric", 1.0, type="counter")
   metrics = await obs.export_metrics()
   print(metrics)  # Should contain test_metric
   ```

3. **Check Prometheus configuration**:
   ```yaml
   # prometheus.yml
   scrape_configs:
     - job_name: 'kaizen-agents'
       static_configs:
         - targets: ['localhost:8000']  # Your agent endpoint
   ```

4. **Reload Prometheus**:
   ```bash
   curl -X POST http://localhost:9090/-/reload
   ```

### Traces Not Appearing in Jaeger

**Symptom**: Jaeger UI shows no traces for service

**Solutions**:

1. **Verify Jaeger is running**:
   ```bash
   docker ps | grep jaeger
   curl http://localhost:16686
   ```

2. **Check tracing is enabled**:
   ```python
   obs = agent.enable_observability(enable_tracing=True)
   assert obs.is_component_enabled("tracing")
   ```

3. **Verify Jaeger endpoint**:
   ```python
   obs = agent.enable_observability(
       jaeger_host="localhost",
       jaeger_port=4317  # OTLP gRPC port
   )
   ```

4. **Check Jaeger logs**:
   ```bash
   docker logs kaizen-jaeger
   ```

### High Observability Overhead

**Symptom**: Agent performance degraded after enabling observability

**Solutions**:

1. **Profile which component**:
   ```python
   # Test one at a time
   obs = agent.enable_observability(enable_metrics=True, ...)  # Test metrics
   obs = agent.enable_observability(enable_logging=True, ...)  # Test logging
   obs = agent.enable_observability(enable_tracing=True, ...)  # Test tracing
   obs = agent.enable_observability(enable_audit=True, ...)    # Test audit
   ```

2. **Reduce log verbosity**:
   ```python
   import logging
   logging.getLogger("kaizen").setLevel(logging.WARNING)  # Reduce noise
   ```

3. **Use lightweight mode**:
   ```python
   obs = agent.enable_observability(
       enable_metrics=True,   # Keep
       enable_logging=False,  # Disable
       enable_tracing=False,  # Disable
       enable_audit=False     # Disable
   )
   ```

4. **Disable sampling**:
   ```python
   # For tracing, sample 10% of requests
   if random.random() < 0.1:
       obs = agent.enable_observability(enable_tracing=True)
   else:
       obs = agent.enable_observability(enable_tracing=False)
   ```

### Audit File Growing Too Large

**Symptom**: `~/.kaizen/audit_trail.jsonl` is >1GB

**Solutions**:

1. **Rotate audit logs**:
   ```bash
   # Compress and archive
   gzip ~/.kaizen/audit_trail.jsonl
   mv ~/.kaizen/audit_trail.jsonl.gz ~/.kaizen/archive/audit_$(date +%Y%m%d).jsonl.gz

   # Start fresh
   touch ~/.kaizen/audit_trail.jsonl
   ```

2. **Use custom audit storage**:
   ```python
   from kaizen.core.autonomy.observability.audit import FileAuditStorage

   # Daily rotation
   audit_file = f"~/.kaizen/audit_{datetime.now().strftime('%Y%m%d')}.jsonl"
   storage = FileAuditStorage(audit_file)

   obs = ObservabilityManager(service_name="agent")
   obs.audit.storage = storage
   ```

3. **Query and archive old entries**:
   ```python
   # Archive entries older than 90 days
   cutoff = datetime.now() - timedelta(days=90)
   old_entries = await obs.audit.query_by_time_range(
       start_time=datetime(2020, 1, 1),
       end_time=cutoff
   )

   # Save to archive
   with open("archive.jsonl", "w") as f:
       for entry in old_entries:
           f.write(json.dumps(asdict(entry)) + "\n")
   ```

## Examples

### Example 1: Full Observability

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField

class QASignature(Signature):
    question: str = InputField(description="Question")
    answer: str = OutputField(description="Answer")

# Create agent with full observability
agent = BaseAgent(config=config, signature=QASignature())
obs = agent.enable_observability(service_name="qa-agent")

# Run agent - all observability is automatic
result = agent.run(question="What is Kaizen?")

# Access observability data
logger = obs.get_logger("qa-agent")
logger.info("Question answered",
    answer_length=len(result['answer']),
    confidence="high"
)

await obs.record_metric(
    "questions_answered_total",
    1.0,
    type="counter",
    labels={"topic": "kaizen"}
)
```

### Example 2: Custom Metrics

```python
# Track API costs
await obs.record_metric(
    "llm_api_cost_usd",
    0.05,
    type="gauge",
    labels={"provider": "openai", "model": "gpt-4"}
)

# Track cache hit rate
await obs.record_metric(
    "cache_hits_total",
    1.0,
    type="counter",
    labels={"cache_type": "memory"}
)

await obs.record_metric(
    "cache_misses_total",
    1.0,
    type="counter",
    labels={"cache_type": "memory"}
)

# Track latency distribution
async with obs.metrics.timer("llm_call_duration_ms", labels={"model": "gpt-4"}):
    result = await call_llm()
```

### Example 3: Audit Trail for Compliance

```python
# Audit sensitive data access
await obs.record_audit(
    agent_id="data-agent",
    action="pii_access",
    details={
        "user_id": "user-123",
        "fields": ["email", "phone", "address"],
        "purpose": "customer_support"
    },
    result="success",
    user_id="support@company.com",
    metadata={"ticket_id": "TICKET-456"}
)

# Query audit trail
from datetime import datetime, timedelta

# Last 24 hours
recent = await obs.audit.query_by_time_range(
    start_time=datetime.now() - timedelta(hours=24),
    end_time=datetime.now()
)

# By user
user_actions = await obs.query_audit_by_agent("data-agent")

# By action type
pii_accesses = await obs.query_audit_by_action("pii_access")
```

### Example 4: Lightweight Mode

```python
# Metrics and logging only (no tracing or audit)
obs = agent.enable_observability(
    service_name="batch-agent",
    enable_metrics=True,
    enable_logging=True,
    enable_tracing=False,
    enable_audit=False
)

# Verify configuration
assert obs.is_component_enabled("metrics")
assert obs.is_component_enabled("logging")
assert not obs.is_component_enabled("tracing")
assert not obs.is_component_enabled("audit")

# Use available components
logger = obs.get_logger("batch-agent")
logger.info("Processing batch", batch_size=1000)

await obs.record_metric(
    "batch_processed_total",
    1000,
    type="counter"
)
```

---

**Last Updated**: 2025-10-24
**Related Documentation**:
- `grafana/README.md` - Observability stack setup
- `benchmarks/PERFORMANCE_RESULTS.md` - Performance validation
- ADR-017 - Observability & Performance Monitoring
- Integration tests: `tests/integration/observability/test_baseagent_observability.py`
