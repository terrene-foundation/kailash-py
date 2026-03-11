# ADR-017: Observability & Performance Monitoring

## Status
**Proposed** - Phase 4 Implementation (Weeks 33-44)

**Priority**: P1 - HIGH (enables production operations and debugging)

## Context

Kaizen agents with autonomous capabilities (from ADR-011 through ADR-016) will execute for **30+ hours** with minimal human supervision. This creates critical operational challenges:

**Operational Blindness**:
- Cannot monitor agent progress during long-running execution
- No visibility into resource consumption (CPU, memory, API costs)
- Cannot detect performance degradation or bottlenecks
- No alerts when agents are stuck or failing
- Cannot debug issues without comprehensive logging

**Production Risks**:
- Agents may consume excessive resources (runaway API calls)
- Performance degradation goes unnoticed until failure
- No metrics for capacity planning or cost optimization
- Debugging production issues requires code changes + redeployment
- No compliance audit trails for enterprise deployments

**Performance Unknowns**:
- No baseline metrics for autonomous agent performance
- Cannot validate performance parity with Claude Agent SDK
- No regression detection when adding new features
- Cannot identify optimization opportunities

**Problem**: Kaizen needs a **comprehensive observability system** that:
1. Provides real-time monitoring of agent execution
2. Collects performance metrics for all autonomy components
3. Enables debugging via structured logging and tracing
4. Supports compliance auditing and cost tracking
5. Detects performance regressions automatically
6. Integrates with standard monitoring tools (Prometheus, Grafana, ELK)

**Inspiration**: Claude Code provides extensive observability:
- Real-time progress updates via Control Protocol
- Detailed execution logs with filtering
- Performance metrics for all operations
- Cost tracking and budget alerts
- Integration with enterprise monitoring systems

## Requirements

### Functional Requirements

1. **FR-1**: Real-time metrics collection (agent loop, tool execution, API calls)
2. **FR-2**: Structured logging with context propagation
3. **FR-3**: Distributed tracing across agent invocations
4. **FR-4**: Performance profiling (CPU, memory, I/O)
5. **FR-5**: Cost tracking (API calls, compute resources)
6. **FR-6**: Health checks and liveness probes
7. **FR-7**: Audit trails for compliance (who/what/when)
8. **FR-8**: Alerting on anomalies (high latency, errors, budget overruns)

### Non-Functional Requirements

1. **NFR-1**: Metrics collection overhead <2% of execution time
2. **NFR-2**: Logging overhead <5% of execution time
3. **NFR-3**: Metrics export latency <1000ms
4. **NFR-4**: Log retention: 30 days default (configurable)
5. **NFR-5**: Metrics retention: 90 days default (configurable)
6. **NFR-6**: Zero data loss for audit trails (persistent storage)

### Metrics to Collect

**Agent Execution Metrics**:
- Agent loop iterations (count, duration, success/failure rate)
- Tool execution (count per tool, latency p50/p95/p99, success rate)
- API call metrics (count, cost, latency, errors)
- Memory usage (current, peak, average)
- CPU usage (user time, system time, percentage)

**Autonomy Component Metrics**:
- Control Protocol (request/response latency, timeout rate)
- Permission System (check latency, approval rate, denial reasons)
- State Persistence (checkpoint save/load latency, checkpoint size)
- Hooks System (hook execution count, latency, failure rate)
- Interrupt Mechanism (interrupt frequency, graceful vs immediate)

**Business Metrics**:
- Total cost per agent execution (USD)
- Cost per tool invocation (USD)
- Execution time per task type
- Success rate by task complexity
- User satisfaction (approval rate, interrupt rate)

## Decision

We will implement an **Observability & Performance System** in `kaizen/core/autonomy/observability/` with the following design:

### Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│ BaseAgent / Autonomy Components (Instrumentation)       │
│ - metrics.record("agent_loop", duration_ms)             │
│ - logger.info("Tool executed", extra=context)           │
│ - tracer.span("execute_tool", attributes)               │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ Emit events
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Observability Manager (Collection & Routing)             │
│ - MetricsCollector → Prometheus/StatsD                   │
│ - LoggingManager → JSON logs / ELK                       │
│ - TracingManager → OpenTelemetry / Jaeger                │
│ - AuditTrailManager → Persistent storage                 │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ Query & Export
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Monitoring Backends (Visualization & Alerting)           │
│ - Prometheus + Grafana (metrics dashboards)              │
│ - ELK Stack (log aggregation and search)                 │
│ - Jaeger (distributed tracing)                           │
│ - Custom audit DB (compliance reporting)                 │
└──────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. Metrics Types (`kaizen/core/autonomy/observability/types.py`)

```python
from dataclasses import dataclass
from typing import Literal, Any
from datetime import datetime

MetricType = Literal["counter", "gauge", "histogram", "summary"]

@dataclass
class Metric:
    """Single metric observation"""
    name: str
    value: float
    type: MetricType
    timestamp: datetime
    labels: dict[str, str] = field(default_factory=dict)
    unit: str | None = None

@dataclass
class LogEntry:
    """Structured log entry"""
    timestamp: datetime
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None

@dataclass
class Span:
    """Distributed tracing span"""
    trace_id: str
    span_id: str
    parent_span_id: str | None
    operation_name: str
    start_time: datetime
    end_time: datetime | None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

@dataclass
class AuditEntry:
    """Immutable audit trail entry"""
    timestamp: datetime
    agent_id: str
    user_id: str | None
    action: str  # "tool_execute", "permission_grant", "checkpoint_save"
    details: dict[str, Any]
    result: Literal["success", "failure", "denied"]
    metadata: dict[str, Any] = field(default_factory=dict)
```

#### 2. Metrics Collector (`kaizen/core/autonomy/observability/metrics.py`)

```python
from collections import defaultdict
import time
from typing import Callable
from contextlib import asynccontextmanager

class MetricsCollector:
    """Collects and exports metrics"""

    def __init__(self, backend: str = "prometheus"):
        self.backend = backend
        self._metrics: list[Metric] = []
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)

    def counter(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Increment a counter"""
        key = self._metric_key(name, labels or {})
        self._counters[key] += value

        self._metrics.append(Metric(
            name=name,
            value=value,
            type="counter",
            timestamp=datetime.utcnow(),
            labels=labels or {}
        ))

    def gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge value"""
        key = self._metric_key(name, labels or {})
        self._gauges[key] = value

        self._metrics.append(Metric(
            name=name,
            value=value,
            type="gauge",
            timestamp=datetime.utcnow(),
            labels=labels or {}
        ))

    def histogram(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record a histogram observation"""
        key = self._metric_key(name, labels or {})
        self._histograms[key].append(value)

        self._metrics.append(Metric(
            name=name,
            value=value,
            type="histogram",
            timestamp=datetime.utcnow(),
            labels=labels or {}
        ))

    @asynccontextmanager
    async def timer(self, name: str, labels: dict[str, str] | None = None):
        """Context manager for timing operations"""
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.histogram(name, duration_ms, labels)

    def _metric_key(self, name: str, labels: dict[str, str]) -> str:
        """Generate unique key for metric + labels"""
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}" if label_str else name

    async def export(self) -> str:
        """Export metrics in Prometheus format"""
        lines = []

        # Counters
        for key, value in self._counters.items():
            lines.append(f"{key} {value}")

        # Gauges
        for key, value in self._gauges.items():
            lines.append(f"{key} {value}")

        # Histograms (export p50, p95, p99)
        for key, values in self._histograms.items():
            if values:
                sorted_values = sorted(values)
                p50 = sorted_values[len(values) // 2]
                p95 = sorted_values[int(len(values) * 0.95)]
                p99 = sorted_values[int(len(values) * 0.99)]

                lines.append(f"{key}_p50 {p50}")
                lines.append(f"{key}_p95 {p95}")
                lines.append(f"{key}_p99 {p99}")

        return "\n".join(lines)
```

#### 3. Logging Manager (`kaizen/core/autonomy/observability/logging.py`)

```python
import logging
import json
from typing import Any

class StructuredLogger:
    """Structured JSON logging with context propagation"""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.context: dict[str, Any] = {}

    def add_context(self, **kwargs) -> None:
        """Add persistent context to all log entries"""
        self.context.update(kwargs)

    def info(self, message: str, **extra) -> None:
        """Log info message with context"""
        self._log("INFO", message, extra)

    def warning(self, message: str, **extra) -> None:
        """Log warning message with context"""
        self._log("WARNING", message, extra)

    def error(self, message: str, **extra) -> None:
        """Log error message with context"""
        self._log("ERROR", message, extra)

    def _log(self, level: str, message: str, extra: dict[str, Any]) -> None:
        """Internal log method with JSON formatting"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
            "context": {**self.context, **extra}
        }

        # Use standard logging with JSON string
        log_method = getattr(self.logger, level.lower())
        log_method(json.dumps(log_entry))

class LoggingManager:
    """Manages structured logging for all agents"""

    def __init__(self):
        self._loggers: dict[str, StructuredLogger] = {}

    def get_logger(self, name: str) -> StructuredLogger:
        """Get or create logger for name"""
        if name not in self._loggers:
            self._loggers[name] = StructuredLogger(name)
        return self._loggers[name]
```

#### 4. Tracing Manager (`kaizen/core/autonomy/observability/tracing.py`)

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from contextlib import asynccontextmanager
import uuid

class TracingManager:
    """Distributed tracing using OpenTelemetry"""

    def __init__(self, service_name: str = "kaizen-agent"):
        self.service_name = service_name

        # Initialize OpenTelemetry
        trace.set_tracer_provider(TracerProvider())
        self.tracer = trace.get_tracer(__name__)

        # Add span processor (console for now, Jaeger in production)
        span_processor = BatchSpanProcessor(ConsoleSpanExporter())
        trace.get_tracer_provider().add_span_processor(span_processor)

    @asynccontextmanager
    async def span(
        self,
        operation_name: str,
        attributes: dict[str, Any] | None = None
    ):
        """Create a tracing span"""
        with self.tracer.start_as_current_span(operation_name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)

            try:
                yield span
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                raise
```

#### 5. Audit Trail Manager (`kaizen/core/autonomy/observability/audit.py`)

```python
from typing import Protocol
import json

class AuditStorage(Protocol):
    """Protocol for audit trail storage backends"""

    async def append(self, entry: AuditEntry) -> None:
        """Append immutable audit entry"""
        pass

    async def query(
        self,
        agent_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        action: str | None = None
    ) -> list[AuditEntry]:
        """Query audit entries"""
        pass

class FileAuditStorage:
    """File-based audit storage (JSONL format)"""

    def __init__(self, file_path: str = ".kaizen/audit.jsonl"):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    async def append(self, entry: AuditEntry) -> None:
        """Append audit entry to JSONL file"""
        async with anyio.open_file(self.file_path, "a") as f:
            await f.write(json.dumps(asdict(entry)) + "\n")

    async def query(
        self,
        agent_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        action: str | None = None
    ) -> list[AuditEntry]:
        """Query audit entries (simple filtering)"""
        entries = []

        async with anyio.open_file(self.file_path, "r") as f:
            async for line in f:
                entry_dict = json.loads(line)
                entry = AuditEntry(**entry_dict)

                # Apply filters
                if agent_id and entry.agent_id != agent_id:
                    continue
                if start_time and entry.timestamp < start_time:
                    continue
                if end_time and entry.timestamp > end_time:
                    continue
                if action and entry.action != action:
                    continue

                entries.append(entry)

        return entries

class AuditTrailManager:
    """Manages audit trail recording and querying"""

    def __init__(self, storage: AuditStorage | None = None):
        self.storage = storage or FileAuditStorage()

    async def record(
        self,
        agent_id: str,
        action: str,
        details: dict[str, Any],
        result: Literal["success", "failure", "denied"],
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Record audit entry"""
        entry = AuditEntry(
            timestamp=datetime.utcnow(),
            agent_id=agent_id,
            user_id=user_id,
            action=action,
            details=details,
            result=result,
            metadata=metadata or {}
        )

        await self.storage.append(entry)

    async def query_by_agent(self, agent_id: str) -> list[AuditEntry]:
        """Get all audit entries for an agent"""
        return await self.storage.query(agent_id=agent_id)

    async def query_by_action(self, action: str) -> list[AuditEntry]:
        """Get all audit entries for a specific action"""
        return await self.storage.query(action=action)
```

#### 6. Observability Manager (`kaizen/core/autonomy/observability/manager.py`)

```python
class ObservabilityManager:
    """Unified observability management"""

    def __init__(
        self,
        service_name: str = "kaizen-agent",
        enable_metrics: bool = True,
        enable_logging: bool = True,
        enable_tracing: bool = True,
        enable_audit: bool = True
    ):
        self.service_name = service_name

        # Initialize components
        self.metrics = MetricsCollector() if enable_metrics else None
        self.logging = LoggingManager() if enable_logging else None
        self.tracing = TracingManager(service_name) if enable_tracing else None
        self.audit = AuditTrailManager() if enable_audit else None

    def get_logger(self, name: str) -> StructuredLogger:
        """Get logger for component"""
        if not self.logging:
            raise RuntimeError("Logging not enabled")
        return self.logging.get_logger(name)

    async def record_metric(
        self,
        name: str,
        value: float,
        type: MetricType = "counter",
        labels: dict[str, str] | None = None
    ) -> None:
        """Record a metric"""
        if not self.metrics:
            return

        if type == "counter":
            self.metrics.counter(name, value, labels)
        elif type == "gauge":
            self.metrics.gauge(name, value, labels)
        elif type == "histogram":
            self.metrics.histogram(name, value, labels)

    async def export_metrics(self) -> str:
        """Export metrics in Prometheus format"""
        if not self.metrics:
            return ""
        return await self.metrics.export()
```

### Integration with BaseAgent

```python
# kaizen/core/base_agent.py

class BaseAgent(Node):
    def __init__(self, config: BaseAgentConfig):
        super().__init__(config)
        self.observability = ObservabilityManager(
            service_name=f"kaizen-agent-{config.name}"
        )
        self.logger = self.observability.get_logger(config.name)

    async def run(self, **kwargs) -> dict[str, Any]:
        """Agent execution loop with observability"""

        # Start tracing span
        async with self.observability.tracing.span(
            "agent_run",
            attributes={"agent_id": self.config.name, "inputs": str(kwargs)}
        ):
            # Record metric
            await self.observability.record_metric(
                "agent_loop_start",
                1.0,
                type="counter",
                labels={"agent_id": self.config.name}
            )

            # Log start
            self.logger.info("Agent execution started", inputs=kwargs)

            # Execute with timing
            async with self.observability.metrics.timer(
                "agent_loop_duration",
                labels={"agent_id": self.config.name}
            ):
                result = await super().run(**kwargs)

            # Record audit trail
            await self.observability.audit.record(
                agent_id=self.config.name,
                action="agent_execution",
                details={"inputs": kwargs, "result": result},
                result="success" if not result.get("error") else "failure"
            )

            # Log completion
            self.logger.info("Agent execution completed", result=result)

            return result
```

### Grafana Dashboard Configuration

```yaml
# grafana/dashboards/kaizen-agent-dashboard.json
{
  "dashboard": {
    "title": "Kaizen Agent Monitoring",
    "panels": [
      {
        "title": "Agent Loop Duration (p95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(agent_loop_duration_bucket[5m]))"
          }
        ]
      },
      {
        "title": "Tool Execution Success Rate",
        "targets": [
          {
            "expr": "rate(tool_execution_success[5m]) / rate(tool_execution_total[5m])"
          }
        ]
      },
      {
        "title": "API Cost per Hour",
        "targets": [
          {
            "expr": "sum(rate(api_cost_usd[1h]))"
          }
        ]
      },
      {
        "title": "Memory Usage",
        "targets": [
          {
            "expr": "process_resident_memory_bytes"
          }
        ]
      }
    ]
  }
}
```

## Consequences

### Positive

1. **✅ Production Visibility**: Real-time monitoring of all agent operations
2. **✅ Debugging**: Structured logs and traces enable fast issue resolution
3. **✅ Cost Control**: API cost tracking prevents budget overruns
4. **✅ Performance**: Metrics enable optimization and regression detection
5. **✅ Compliance**: Audit trails meet enterprise compliance requirements
6. **✅ Standard Tools**: Integrates with Prometheus, Grafana, ELK, Jaeger

### Negative

1. **⚠️ Performance Overhead**: 2-5% execution time overhead for instrumentation
2. **⚠️ Storage Costs**: Metrics, logs, traces require storage infrastructure
3. **⚠️ Complexity**: More systems to configure and maintain
4. **⚠️ Privacy**: Logs may contain sensitive data (requires scrubbing)

### Mitigations

1. **Performance**: Async metrics export, sampling for high-volume operations
2. **Storage**: Retention policies, compression, aggregation
3. **Complexity**: Default configuration works out-of-the-box
4. **Privacy**: Built-in PII scrubbing, configurable redaction rules

## Performance Targets

| Metric | Target | Validation |
|--------|--------|------------|
| Metrics collection overhead | <2% execution time | Benchmark with/without metrics |
| Logging overhead | <5% execution time | Benchmark with/without logging |
| Metrics export latency | <1000ms | Measure Prometheus scrape time |
| Trace overhead | <1% execution time | Benchmark with/without tracing |
| Audit write latency | <10ms per entry | Measure append time |

See `PERFORMANCE_PARITY_PLAN.md` for full benchmarking strategy.

## Alternatives Considered

### Alternative 1: Custom Metrics Format
**Rejected**: Prometheus is industry standard, better tooling ecosystem

### Alternative 2: Print-Based Logging
**Rejected**: Structured JSON logs enable better filtering and analysis

### Alternative 3: No Audit Trails
**Rejected**: Required for enterprise compliance (SOC2, GDPR, HIPAA)

## Implementation Plan

**Phase 4 Timeline**: Weeks 33-44 (12 weeks)

| Week | Tasks |
|------|-------|
| 33-34 | Implement metrics collector, Prometheus exporter |
| 35-36 | Implement structured logging, ELK integration |
| 37-38 | Implement distributed tracing, Jaeger integration |
| 39-40 | Implement audit trail storage and querying |
| 41 | BaseAgent integration, instrumentation |
| 42 | Grafana dashboards, alerting rules |
| 43 | Performance benchmarks, overhead validation |
| 44 | Documentation, examples, troubleshooting guide |

**Deliverables**:
- [ ] `kaizen/core/autonomy/observability/` module (~1500 lines)
- [ ] Prometheus metrics exporter
- [ ] Structured JSON logging
- [ ] OpenTelemetry tracing integration
- [ ] Audit trail storage (file + database)
- [ ] 3 Grafana dashboards
- [ ] 60+ unit/integration tests
- [ ] Comprehensive documentation

## Testing Strategy

### Tier 1: Unit Tests
```python
def test_metrics_collector_counter():
    collector = MetricsCollector()
    collector.counter("test_counter", 5.0, labels={"env": "test"})

    assert collector._counters["test_counter{env=test}"] == 5.0

async def test_audit_trail_append():
    storage = FileAuditStorage("/tmp/test-audit.jsonl")

    await storage.append(AuditEntry(
        timestamp=datetime.utcnow(),
        agent_id="test-agent",
        action="test_action",
        details={},
        result="success"
    ))

    entries = await storage.query(agent_id="test-agent")
    assert len(entries) == 1
```

### Tier 2: Integration Tests
```python
@pytest.mark.tier2
async def test_observability_with_real_agent():
    agent = BaseAgent(config=config)

    # Execute agent
    result = await agent.run(input="Test")

    # Verify metrics recorded
    metrics = await agent.observability.export_metrics()
    assert "agent_loop_start" in metrics
    assert "agent_loop_duration" in metrics

    # Verify audit trail
    entries = await agent.observability.audit.query_by_agent(agent.config.name)
    assert len(entries) > 0
```

### Tier 3: E2E Tests
```python
@pytest.mark.tier3
async def test_prometheus_integration():
    # Start agent with metrics enabled
    agent = BaseAgent(config=config)

    # Execute workload
    for i in range(100):
        await agent.run(input=f"Task {i}")

    # Scrape Prometheus endpoint
    response = requests.get("http://localhost:8000/metrics")
    assert response.status_code == 200

    # Verify metrics present
    metrics = response.text
    assert "agent_loop_duration_p95" in metrics
```

## Documentation Requirements

- [ ] **ADR** (this document)
- [ ] **API Reference**: `docs/reference/observability-api.md`
- [ ] **Monitoring Guide**: `docs/guides/monitoring-setup.md`
- [ ] **Grafana Dashboards**: `docs/dashboards/grafana-dashboards.md`
- [ ] **Troubleshooting**: `docs/reference/observability-troubleshooting.md`

## References

1. **Gap Analysis**: `.claude/improvements/CLAUDE_AGENT_SDK_KAIZEN_GAP_ANALYSIS.md`
2. **Implementation Proposal**: `.claude/improvements/KAIZEN_AUTONOMOUS_AGENT_ENHANCEMENT_PROPOSAL.md` (Section 3.7)
3. **Performance Plan**: `.claude/improvements/PERFORMANCE_PARITY_PLAN.md` (Phase 4)
4. **Prometheus Best Practices**: https://prometheus.io/docs/practices/naming/
5. **OpenTelemetry Python**: https://opentelemetry.io/docs/instrumentation/python/

## Dependencies

**This ADR depends on**:
- 011: Control Protocol (for progress reporting)
- 012: Permission System (for permission metrics)
- 013: Specialist System (for specialist metrics)
- 014: Hooks System (for hook metrics)
- 015: State Persistence (for checkpoint metrics)
- 016: Interrupt Mechanism (for interrupt metrics)

**Other ADRs depend on this**:
- None (final ADR in autonomous agent enhancement series)

## Approval

**Proposed By**: Kaizen Architecture Team
**Date**: 2025-10-19
**Reviewers**: TBD
**Status**: Proposed (awaiting team review)

---

**Previous ADR**: ADR-016: Interrupt Mechanism Design
**This completes the autonomous agent enhancement architecture design** (ADR-011 through ADR-017)
