# MCP Monitoring and Observability

## Overview

Comprehensive monitoring and observability are crucial for maintaining healthy MCP deployments. This guide covers metrics collection, logging strategies, distributed tracing, alerting, and dashboard creation for MCP servers and clients.

## Table of Contents

1. [Monitoring Architecture](#monitoring-architecture)
2. [Metrics Collection](#metrics-collection)
3. [Logging Strategy](#logging-strategy)
4. [Distributed Tracing](#distributed-tracing)
5. [Health Checks](#health-checks)
6. [Alerting](#alerting)
7. [Dashboards](#dashboards)
8. [Performance Monitoring](#performance-monitoring)
9. [Security Monitoring](#security-monitoring)
10. [Cost Monitoring](#cost-monitoring)

## Monitoring Architecture

### Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   MCP Server    │────►│   Prometheus    │────►│     Grafana     │
│   (Metrics)     │     │   (Storage)     │     │  (Visualization)│
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │                         │
         │              ┌────────┴────────┐               │
         │              │   AlertManager   │               │
         │              │    (Alerting)    │               │
         │              └─────────────────┘               │
         │                                                 │
┌────────▼────────┐     ┌─────────────────┐     ┌────────▼────────┐
│   FluentBit     │────►│  Elasticsearch  │────►│     Kibana      │
│    (Logs)       │     │  (Log Storage)  │     │ (Log Analysis)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │
┌────────▼────────┐     ┌─────────────────┐
│     Jaeger      │────►│    Cassandra    │
│   (Tracing)     │     │ (Trace Storage) │
└─────────────────┘     └─────────────────┘
```

### Components

1. **Metrics**: Prometheus + Grafana
2. **Logs**: FluentBit + Elasticsearch + Kibana
3. **Traces**: Jaeger + OpenTelemetry
4. **Alerts**: AlertManager + PagerDuty/Slack

## Metrics Collection

### Core Metrics Implementation

```python
# monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, Summary
from functools import wraps
import time
from typing import Dict, Any

class MCPMetrics:
    """MCP server metrics collection"""

    def __init__(self):
        # Request metrics
        self.request_count = Counter(
            'mcp_requests_total',
            'Total number of MCP requests',
            ['method', 'tool', 'status']
        )

        self.request_duration = Histogram(
            'mcp_request_duration_seconds',
            'MCP request duration in seconds',
            ['method', 'tool'],
            buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
        )

        # Tool metrics
        self.tool_execution_time = Summary(
            'mcp_tool_execution_seconds',
            'Tool execution time in seconds',
            ['tool_name']
        )

        self.tool_errors = Counter(
            'mcp_tool_errors_total',
            'Total number of tool execution errors',
            ['tool_name', 'error_type']
        )

        # Connection metrics
        self.active_connections = Gauge(
            'mcp_active_connections',
            'Number of active MCP connections',
            ['transport_type']
        )

        self.connection_duration = Histogram(
            'mcp_connection_duration_seconds',
            'Connection duration in seconds',
            ['transport_type']
        )

        # Resource metrics
        self.resource_usage = Gauge(
            'mcp_resource_usage',
            'Resource usage metrics',
            ['resource_type', 'metric_name']
        )

        # Cache metrics
        self.cache_hits = Counter(
            'mcp_cache_hits_total',
            'Total cache hits',
            ['cache_type']
        )

        self.cache_misses = Counter(
            'mcp_cache_misses_total',
            'Total cache misses',
            ['cache_type']
        )

    def track_request(self, method: str, tool: str = None):
        """Decorator to track request metrics"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                status = "success"

                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    status = "error"
                    raise
                finally:
                    duration = time.time() - start_time
                    self.request_count.labels(
                        method=method,
                        tool=tool or "none",
                        status=status
                    ).inc()
                    self.request_duration.labels(
                        method=method,
                        tool=tool or "none"
                    ).observe(duration)

            return wrapper
        return decorator

    def track_tool_execution(self, tool_name: str):
        """Track tool execution metrics"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                with self.tool_execution_time.labels(tool_name=tool_name).time():
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        self.tool_errors.labels(
                            tool_name=tool_name,
                            error_type=type(e).__name__
                        ).inc()
                        raise
            return wrapper
        return decorator

# Usage example
metrics = MCPMetrics()

class MCPServer:
    @metrics.track_request("list_tools")
    async def list_tools(self) -> Dict[str, Any]:
        """List available tools"""
        return {"tools": self.tools}

    @metrics.track_request("execute_tool", tool="dynamic")
    @metrics.track_tool_execution("dynamic")
    async def execute_tool(self, tool_name: str, args: Dict) -> Any:
        """Execute a specific tool"""
        return await self.tools[tool_name].execute(args)
```

### Custom Metrics

```python
# monitoring/custom_metrics.py
from prometheus_client import Histogram, Counter, Gauge, Info

class BusinessMetrics:
    """Business-specific metrics"""

    def __init__(self):
        # Usage metrics
        self.api_calls_per_user = Counter(
            'mcp_api_calls_per_user_total',
            'API calls per user',
            ['user_id', 'plan_type']
        )

        self.tokens_consumed = Counter(
            'mcp_tokens_consumed_total',
            'Total tokens consumed',
            ['user_id', 'model']
        )

        # Performance metrics
        self.llm_response_time = Histogram(
            'mcp_llm_response_time_seconds',
            'LLM response time',
            ['model', 'prompt_type'],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
        )

        # Quality metrics
        self.tool_success_rate = Gauge(
            'mcp_tool_success_rate',
            'Tool execution success rate',
            ['tool_name', 'time_window']
        )

        # System info
        self.server_info = Info(
            'mcp_server_info',
            'MCP server information'
        )
        self.server_info.info({
            'version': '1.0.0',
            'transport': 'sse',
            'auth_enabled': 'true'
        })
```

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'production'
    region: 'us-east-1'

# Alerting
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

# Load rules
rule_files:
  - "alerts/*.yml"

# Scrape configs
scrape_configs:
  # MCP Server metrics
  - job_name: 'mcp-server'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - mcp-system
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        target_label: __address__
        regex: ([^:]+)(?::\d+)?
        replacement: $1:${1}
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: replace
        target_label: app
      - source_labels: [__meta_kubernetes_pod_name]
        action: replace
        target_label: pod

  # Node exporter
  - job_name: 'node-exporter'
    kubernetes_sd_configs:
      - role: node
    relabel_configs:
      - action: labelmap
        regex: __meta_kubernetes_node_label_(.+)
      - target_label: __address__
        replacement: kubernetes.default.svc:443
      - source_labels: [__meta_kubernetes_node_name]
        regex: (.+)
        target_label: __metrics_path__
        replacement: /api/v1/nodes/${1}/proxy/metrics

  # Kubernetes metrics
  - job_name: 'kubernetes-apiservers'
    kubernetes_sd_configs:
      - role: endpoints
    scheme: https
    tls_config:
      ca_file: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
    bearer_token_file: /var/run/secrets/kubernetes.io/serviceaccount/token
    relabel_configs:
      - source_labels: [__meta_kubernetes_namespace, __meta_kubernetes_service_name, __meta_kubernetes_endpoint_port_name]
        action: keep
        regex: default;kubernetes;https
```

## Logging Strategy

### Structured Logging

```python
# monitoring/logging.py
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict
import traceback

class StructuredLogger:
    """Structured JSON logger for MCP"""

    def __init__(self, name: str, level: str = "INFO"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level))

        # JSON formatter
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(self.JSONFormatter())
        self.logger.addHandler(handler)

    class JSONFormatter(logging.Formatter):
        """JSON log formatter"""

        def format(self, record: logging.LogRecord) -> str:
            log_obj = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }

            # Add extra fields
            if hasattr(record, 'request_id'):
                log_obj['request_id'] = record.request_id
            if hasattr(record, 'user_id'):
                log_obj['user_id'] = record.user_id
            if hasattr(record, 'tool_name'):
                log_obj['tool_name'] = record.tool_name

            # Add exception info
            if record.exc_info:
                log_obj['exception'] = {
                    'type': record.exc_info[0].__name__,
                    'message': str(record.exc_info[1]),
                    'traceback': traceback.format_exception(*record.exc_info)
                }

            return json.dumps(log_obj)

    def with_context(self, **context):
        """Add context to logger"""
        adapter = logging.LoggerAdapter(self.logger, context)
        return adapter

# Usage
logger = StructuredLogger("mcp.server")

# Log with context
request_logger = logger.with_context(
    request_id="req-123",
    user_id="user-456"
)
request_logger.info("Processing request", extra={
    "tool_name": "search",
    "args": {"query": "example"}
})
```

### Log Aggregation with FluentBit

```yaml
# fluent-bit-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fluent-bit-config
  namespace: mcp-system
data:
  fluent-bit.conf: |
    [SERVICE]
        Flush         5
        Log_Level     info
        Daemon        off
        Parsers_File  parsers.conf

    [INPUT]
        Name              tail
        Path              /var/log/containers/*mcp*.log
        Parser            docker
        Tag               mcp.*
        Refresh_Interval  5
        Mem_Buf_Limit     50MB
        Skip_Long_Lines   On

    [FILTER]
        Name         parser
        Match        mcp.*
        Key_Name     log
        Parser       json
        Reserve_Data On

    [FILTER]
        Name         record_modifier
        Match        mcp.*
        Record       cluster ${CLUSTER_NAME}
        Record       environment ${ENVIRONMENT}

    [OUTPUT]
        Name         es
        Match        mcp.*
        Host         ${ELASTICSEARCH_HOST}
        Port         ${ELASTICSEARCH_PORT}
        Index        mcp-logs
        Type         _doc
        Retry_Limit  5

  parsers.conf: |
    [PARSER]
        Name         json
        Format       json
        Time_Key     timestamp
        Time_Format  %Y-%m-%dT%H:%M:%S.%L
        Time_Keep    On

    [PARSER]
        Name         docker
        Format       json
        Time_Key     time
        Time_Format  %Y-%m-%dT%H:%M:%S.%LZ
```

### Log Analysis Queries

```python
# monitoring/log_analysis.py
from elasticsearch import Elasticsearch
from datetime import datetime, timedelta

class LogAnalyzer:
    """Analyze MCP logs in Elasticsearch"""

    def __init__(self, es_host: str):
        self.es = Elasticsearch([es_host])

    def get_error_rate(self, time_range: timedelta) -> float:
        """Calculate error rate over time range"""
        end_time = datetime.utcnow()
        start_time = end_time - time_range

        # Total requests
        total_query = {
            "query": {
                "range": {
                    "timestamp": {
                        "gte": start_time.isoformat(),
                        "lte": end_time.isoformat()
                    }
                }
            }
        }
        total = self.es.count(index="mcp-logs", body=total_query)['count']

        # Error requests
        error_query = {
            "query": {
                "bool": {
                    "must": [
                        {"range": {"timestamp": {
                            "gte": start_time.isoformat(),
                            "lte": end_time.isoformat()
                        }}},
                        {"term": {"level": "ERROR"}}
                    ]
                }
            }
        }
        errors = self.es.count(index="mcp-logs", body=error_query)['count']

        return (errors / total * 100) if total > 0 else 0

    def get_slow_requests(self, threshold_ms: int = 1000) -> list:
        """Find slow requests"""
        query = {
            "query": {
                "range": {
                    "duration_ms": {"gte": threshold_ms}
                }
            },
            "sort": [{"duration_ms": "desc"}],
            "size": 100
        }

        response = self.es.search(index="mcp-logs", body=query)
        return response['hits']['hits']
```

## Distributed Tracing

### OpenTelemetry Integration

```python
# monitoring/tracing.py
from opentelemetry import trace
from opentelemetry.exporter.jaeger import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.trace import Status, StatusCode
import contextvars

# Context variable for request ID
request_id_var = contextvars.ContextVar('request_id', default=None)

class MCPTracing:
    """MCP distributed tracing setup"""

    def __init__(self, service_name: str, jaeger_endpoint: str):
        # Set up tracer provider
        trace.set_tracer_provider(TracerProvider())

        # Configure Jaeger exporter
        jaeger_exporter = JaegerExporter(
            agent_host_name=jaeger_endpoint.split(':')[0],
            agent_port=int(jaeger_endpoint.split(':')[1]),
            service_name=service_name,
        )

        # Add span processor
        span_processor = BatchSpanProcessor(jaeger_exporter)
        trace.get_tracer_provider().add_span_processor(span_processor)

        self.tracer = trace.get_tracer(__name__)

    def trace_method(self, span_name: str = None):
        """Decorator for tracing methods"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                name = span_name or f"{func.__module__}.{func.__name__}"

                with self.tracer.start_as_current_span(name) as span:
                    # Add request ID to span
                    request_id = request_id_var.get()
                    if request_id:
                        span.set_attribute("request.id", request_id)

                    # Add function arguments as attributes
                    span.set_attribute("function.args", str(args))
                    span.set_attribute("function.kwargs", str(kwargs))

                    try:
                        result = await func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as e:
                        span.set_status(
                            Status(StatusCode.ERROR, str(e))
                        )
                        span.record_exception(e)
                        raise

            return wrapper
        return decorator

    def create_span(self, name: str, attributes: Dict[str, Any] = None):
        """Create a new span"""
        span = self.tracer.start_span(name)
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
        return span

# Usage
tracing = MCPTracing("mcp-server", "jaeger:6831")

class MCPToolExecutor:
    @tracing.trace_method("tool.execute")
    async def execute_tool(self, tool_name: str, args: Dict) -> Any:
        """Execute tool with tracing"""
        current_span = trace.get_current_span()
        current_span.set_attribute("tool.name", tool_name)
        current_span.set_attribute("tool.args", json.dumps(args))

        # Create child span for tool execution
        with tracing.create_span(f"tool.{tool_name}") as tool_span:
            tool_span.set_attribute("tool.type", self.tools[tool_name].type)
            result = await self.tools[tool_name].execute(args)
            tool_span.set_attribute("tool.result_size", len(str(result)))

        return result
```

### Trace Analysis

```python
# monitoring/trace_analysis.py
from jaeger_client import Config
import requests

class TraceAnalyzer:
    """Analyze traces from Jaeger"""

    def __init__(self, jaeger_query_url: str):
        self.jaeger_url = jaeger_query_url

    def get_slow_traces(self, service: str, min_duration_ms: int):
        """Find slow traces"""
        params = {
            'service': service,
            'minDuration': f"{min_duration_ms}ms",
            'limit': 100
        }

        response = requests.get(
            f"{self.jaeger_url}/api/traces",
            params=params
        )
        return response.json()['data']

    def get_error_traces(self, service: str, lookback: str = "1h"):
        """Find traces with errors"""
        params = {
            'service': service,
            'lookback': lookback,
            'tags': '{"error":"true"}'
        }

        response = requests.get(
            f"{self.jaeger_url}/api/traces",
            params=params
        )
        return response.json()['data']
```

## Health Checks

### Comprehensive Health Check Implementation

```python
# monitoring/health.py
from enum import Enum
from typing import Dict, Any, List
import asyncio
import aiohttp
import asyncpg
import aioredis

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

class HealthCheck:
    """Comprehensive health check system"""

    def __init__(self):
        self.checks = []

    def register_check(self, name: str, check_func):
        """Register a health check"""
        self.checks.append((name, check_func))

    async def run_all_checks(self) -> Dict[str, Any]:
        """Run all registered health checks"""
        results = {
            "status": HealthStatus.HEALTHY,
            "checks": {},
            "timestamp": datetime.utcnow().isoformat()
        }

        # Run checks concurrently
        check_tasks = [
            self._run_check(name, func)
            for name, func in self.checks
        ]
        check_results = await asyncio.gather(*check_tasks)

        # Aggregate results
        for name, result in check_results:
            results["checks"][name] = result
            if result["status"] == HealthStatus.UNHEALTHY:
                results["status"] = HealthStatus.UNHEALTHY
            elif result["status"] == HealthStatus.DEGRADED and results["status"] != HealthStatus.UNHEALTHY:
                results["status"] = HealthStatus.DEGRADED

        return results

    async def _run_check(self, name: str, check_func) -> tuple:
        """Run individual check with timeout"""
        try:
            result = await asyncio.wait_for(check_func(), timeout=5.0)
            return (name, result)
        except asyncio.TimeoutError:
            return (name, {
                "status": HealthStatus.UNHEALTHY,
                "message": "Health check timed out",
                "duration_ms": 5000
            })
        except Exception as e:
            return (name, {
                "status": HealthStatus.UNHEALTHY,
                "message": str(e),
                "error": type(e).__name__
            })

# Health check implementations
class MCPHealthChecks:
    """MCP-specific health checks"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.health = HealthCheck()
        self._register_checks()

    def _register_checks(self):
        """Register all health checks"""
        self.health.register_check("database", self.check_database)
        self.health.register_check("redis", self.check_redis)
        self.health.register_check("tools", self.check_tools)
        self.health.register_check("disk_space", self.check_disk_space)
        self.health.register_check("memory", self.check_memory)

    async def check_database(self) -> Dict[str, Any]:
        """Check database connectivity"""
        start_time = time.time()
        try:
            conn = await asyncpg.connect(self.config['database_url'])
            await conn.fetchval('SELECT 1')
            await conn.close()

            return {
                "status": HealthStatus.HEALTHY,
                "duration_ms": int((time.time() - start_time) * 1000)
            }
        except Exception as e:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": str(e),
                "duration_ms": int((time.time() - start_time) * 1000)
            }

    async def check_redis(self) -> Dict[str, Any]:
        """Check Redis connectivity"""
        start_time = time.time()
        try:
            redis = await aioredis.create_redis_pool(
                self.config['redis_url']
            )
            await redis.ping()
            redis.close()
            await redis.wait_closed()

            return {
                "status": HealthStatus.HEALTHY,
                "duration_ms": int((time.time() - start_time) * 1000)
            }
        except Exception as e:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": str(e),
                "duration_ms": int((time.time() - start_time) * 1000)
            }

    async def check_tools(self) -> Dict[str, Any]:
        """Check tool availability"""
        unhealthy_tools = []

        for tool_name, tool in self.tools.items():
            try:
                if hasattr(tool, 'health_check'):
                    await tool.health_check()
            except:
                unhealthy_tools.append(tool_name)

        if not unhealthy_tools:
            return {"status": HealthStatus.HEALTHY}
        elif len(unhealthy_tools) < len(self.tools) * 0.1:
            return {
                "status": HealthStatus.DEGRADED,
                "unhealthy_tools": unhealthy_tools
            }
        else:
            return {
                "status": HealthStatus.UNHEALTHY,
                "unhealthy_tools": unhealthy_tools
            }
```

### Health Check Endpoints

```python
# monitoring/health_endpoints.py
from fastapi import FastAPI, Response
from typing import Optional

app = FastAPI()

@app.get("/health")
async def health_check(detailed: bool = False):
    """Basic health check endpoint"""
    health_checker = MCPHealthChecks(config)
    results = await health_checker.health.run_all_checks()

    # Set response status based on health
    status_code = 200
    if results["status"] == HealthStatus.UNHEALTHY:
        status_code = 503
    elif results["status"] == HealthStatus.DEGRADED:
        status_code = 200  # Still return 200 for degraded

    if detailed:
        return Response(
            content=json.dumps(results),
            status_code=status_code,
            media_type="application/json"
        )
    else:
        return Response(
            content=results["status"].value,
            status_code=status_code
        )

@app.get("/ready")
async def readiness_check():
    """Readiness check for Kubernetes"""
    # Check if server is ready to accept traffic
    if not server.is_initialized:
        return Response(status_code=503)

    # Quick checks only
    try:
        await server.tools_loaded()
        return Response(status_code=200)
    except:
        return Response(status_code=503)

@app.get("/live")
async def liveness_check():
    """Liveness check for Kubernetes"""
    # Very basic check - just verify process is responsive
    return Response(status_code=200)
```

## Alerting

### Alert Rules

```yaml
# alerts/mcp_alerts.yml
groups:
  - name: mcp_server
    interval: 30s
    rules:
      # High error rate
      - alert: MCPHighErrorRate
        expr: |
          (
            sum(rate(mcp_requests_total{status="error"}[5m]))
            /
            sum(rate(mcp_requests_total[5m]))
          ) > 0.05
        for: 5m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "High error rate on MCP server"
          description: "Error rate is {{ $value | humanizePercentage }} on {{ $labels.instance }}"

      # High latency
      - alert: MCPHighLatency
        expr: |
          histogram_quantile(0.95,
            sum(rate(mcp_request_duration_seconds_bucket[5m])) by (le)
          ) > 2
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "High latency on MCP server"
          description: "95th percentile latency is {{ $value }}s"

      # Tool failures
      - alert: MCPToolFailures
        expr: |
          sum(rate(mcp_tool_errors_total[5m])) by (tool_name) > 0.1
        for: 10m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Tool {{ $labels.tool_name }} is failing"
          description: "Tool {{ $labels.tool_name }} has {{ $value }} errors/sec"

      # Memory usage
      - alert: MCPHighMemoryUsage
        expr: |
          (
            container_memory_usage_bytes{pod=~"mcp-server-.*"}
            /
            container_spec_memory_limit_bytes{pod=~"mcp-server-.*"}
          ) > 0.9
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "High memory usage on {{ $labels.pod }}"
          description: "Memory usage is {{ $value | humanizePercentage }}"

      # Connection pool exhaustion
      - alert: MCPConnectionPoolExhausted
        expr: |
          mcp_active_connections / mcp_max_connections > 0.9
        for: 5m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Connection pool nearly exhausted"
          description: "{{ $value | humanizePercentage }} of connections in use"
```

### AlertManager Configuration

```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m
  slack_api_url: 'YOUR_SLACK_WEBHOOK'
  pagerduty_url: 'https://events.pagerduty.com/v2/enqueue'

route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: pagerduty
      continue: true
    - match:
        severity: warning
      receiver: slack

receivers:
  - name: 'default'
    # No-op

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_SERVICE_KEY'
        description: '{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}'
        details:
          firing: '{{ template "pagerduty.default.firing" . }}'
          resolved: '{{ template "pagerduty.default.resolved" . }}'

  - name: 'slack'
    slack_configs:
      - channel: '#mcp-alerts'
        title: 'MCP Alert'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}'
        send_resolved: true

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'dev', 'instance']
```

## Dashboards

### Grafana Dashboard Configuration

```json
{
  "dashboard": {
    "title": "MCP Server Monitoring",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [
          {
            "expr": "sum(rate(mcp_requests_total[5m]))",
            "legendFormat": "Total Requests/sec"
          }
        ],
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0}
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "sum(rate(mcp_requests_total{status=\"error\"}[5m])) / sum(rate(mcp_requests_total[5m])) * 100",
            "legendFormat": "Error %"
          }
        ],
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0}
      },
      {
        "title": "Response Time (95th percentile)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, sum(rate(mcp_request_duration_seconds_bucket[5m])) by (le))",
            "legendFormat": "95th percentile"
          }
        ],
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8}
      },
      {
        "title": "Active Connections",
        "targets": [
          {
            "expr": "sum(mcp_active_connections) by (transport_type)",
            "legendFormat": "{{ transport_type }}"
          }
        ],
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8}
      },
      {
        "title": "Tool Execution Time",
        "targets": [
          {
            "expr": "sum(rate(mcp_tool_execution_seconds_sum[5m])) by (tool_name) / sum(rate(mcp_tool_execution_seconds_count[5m])) by (tool_name)",
            "legendFormat": "{{ tool_name }}"
          }
        ],
        "type": "table",
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 16}
      }
    ]
  }
}
```

### Custom Dashboard Generator

```python
# monitoring/dashboard_generator.py
from grafana_api.grafana_face import GrafanaFace
import json

class DashboardGenerator:
    """Generate Grafana dashboards programmatically"""

    def __init__(self, grafana_url: str, api_key: str):
        self.grafana = GrafanaFace(
            auth=api_key,
            host=grafana_url
        )

    def create_mcp_dashboard(self):
        """Create comprehensive MCP dashboard"""
        dashboard = {
            "dashboard": {
                "title": "MCP Comprehensive Monitoring",
                "tags": ["mcp", "generated"],
                "timezone": "UTC",
                "panels": [],
                "schemaVersion": 16,
                "version": 0
            }
        }

        # Add panels
        y_pos = 0

        # Overview row
        dashboard["dashboard"]["panels"].extend(
            self._create_overview_panels(y_pos)
        )
        y_pos += 8

        # Performance row
        dashboard["dashboard"]["panels"].extend(
            self._create_performance_panels(y_pos)
        )
        y_pos += 8

        # Tool metrics row
        dashboard["dashboard"]["panels"].extend(
            self._create_tool_panels(y_pos)
        )

        # Create dashboard
        response = self.grafana.dashboard.update_dashboard(
            dashboard=dashboard
        )
        return response

    def _create_overview_panels(self, y_pos: int) -> list:
        """Create overview panels"""
        return [
            self._create_stat_panel(
                "Total Requests",
                'sum(increase(mcp_requests_total[1h]))',
                0, y_pos
            ),
            self._create_stat_panel(
                "Error Rate",
                'sum(rate(mcp_requests_total{status="error"}[5m])) / sum(rate(mcp_requests_total[5m])) * 100',
                6, y_pos,
                unit="%"
            ),
            self._create_stat_panel(
                "Active Users",
                'count(count by (user_id) (increase(mcp_api_calls_per_user_total[5m]) > 0))',
                12, y_pos
            ),
            self._create_stat_panel(
                "Uptime",
                'up{job="mcp-server"}',
                18, y_pos,
                unit="bool"
            )
        ]
```

## Performance Monitoring

### Performance Profiling

```python
# monitoring/performance.py
import cProfile
import pstats
import io
from memory_profiler import profile
import asyncio
import psutil

class PerformanceMonitor:
    """Monitor MCP server performance"""

    def __init__(self):
        self.profiler = cProfile.Profile()
        self.process = psutil.Process()

    async def profile_endpoint(self, func, *args, **kwargs):
        """Profile endpoint performance"""
        # CPU profiling
        self.profiler.enable()
        result = await func(*args, **kwargs)
        self.profiler.disable()

        # Get stats
        s = io.StringIO()
        ps = pstats.Stats(self.profiler, stream=s).sort_stats('cumulative')
        ps.print_stats(20)  # Top 20 functions

        return {
            "result": result,
            "profile": s.getvalue(),
            "memory_usage": self.process.memory_info().rss / 1024 / 1024,  # MB
            "cpu_percent": self.process.cpu_percent()
        }

    @profile
    async def memory_profile_function(self, func, *args, **kwargs):
        """Profile memory usage of a function"""
        return await func(*args, **kwargs)

    async def continuous_monitoring(self):
        """Continuous performance monitoring"""
        while True:
            metrics = {
                "cpu_percent": self.process.cpu_percent(interval=1),
                "memory_mb": self.process.memory_info().rss / 1024 / 1024,
                "threads": self.process.num_threads(),
                "connections": len(self.process.connections()),
                "open_files": len(self.process.open_files())
            }

            # Send to monitoring system
            for metric, value in metrics.items():
                gauge = Gauge(f"mcp_process_{metric}", f"Process {metric}")
                gauge.set(value)

            await asyncio.sleep(10)
```

### Load Testing Integration

```python
# monitoring/load_testing.py
from locust import HttpUser, task, between
import random

class MCPLoadTest(HttpUser):
    """Load test for MCP server"""
    wait_time = between(1, 3)

    def on_start(self):
        """Authenticate before testing"""
        response = self.client.post("/auth/token", json={
            "username": "test_user",
            "password": "test_pass"
        })
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(3)
    def list_tools(self):
        """Test list tools endpoint"""
        self.client.get("/tools", headers=self.headers)

    @task(5)
    def execute_search_tool(self):
        """Test search tool execution"""
        self.client.post("/tools/search/execute",
            headers=self.headers,
            json={"query": f"test query {random.randint(1, 100)}"}
        )

    @task(2)
    def execute_calculate_tool(self):
        """Test calculate tool execution"""
        self.client.post("/tools/calculate/execute",
            headers=self.headers,
            json={"expression": f"{random.randint(1, 100)} + {random.randint(1, 100)}"}
        )

    @task(1)
    def health_check(self):
        """Test health check endpoint"""
        self.client.get("/health")
```

## Security Monitoring

### Security Event Detection

```python
# monitoring/security.py
from typing import Dict, Any
import re

class SecurityMonitor:
    """Monitor security events in MCP"""

    def __init__(self):
        self.suspicious_patterns = [
            r"(?i)(union.*select|select.*from.*information_schema)",  # SQL injection
            r"(?i)(<script|javascript:|onerror=)",  # XSS attempts
            r"\.\.\/|\.\.\\",  # Path traversal
            r"(?i)(eval|exec|system)\s*\(",  # Code execution
        ]

        # Metrics
        self.auth_failures = Counter(
            'mcp_auth_failures_total',
            'Authentication failures',
            ['reason', 'user']
        )

        self.suspicious_requests = Counter(
            'mcp_suspicious_requests_total',
            'Suspicious requests detected',
            ['pattern_type', 'endpoint']
        )

    async def check_request(self, request: Dict[str, Any]) -> bool:
        """Check request for security issues"""
        # Check for suspicious patterns
        request_str = json.dumps(request)

        for pattern in self.suspicious_patterns:
            if re.search(pattern, request_str):
                self.suspicious_requests.labels(
                    pattern_type="injection_attempt",
                    endpoint=request.get("endpoint", "unknown")
                ).inc()

                # Log security event
                logger.warning("Suspicious request detected", extra={
                    "request_id": request.get("id"),
                    "pattern": pattern,
                    "user_id": request.get("user_id"),
                    "ip_address": request.get("ip_address")
                })

                return False

        return True

    async def monitor_auth_events(self, event: Dict[str, Any]):
        """Monitor authentication events"""
        if event["type"] == "auth_failure":
            self.auth_failures.labels(
                reason=event["reason"],
                user=event.get("username", "unknown")
            ).inc()

            # Check for brute force
            recent_failures = await self.get_recent_auth_failures(
                event.get("ip_address")
            )

            if recent_failures > 5:
                logger.error("Possible brute force attack", extra={
                    "ip_address": event.get("ip_address"),
                    "failures": recent_failures
                })

                # Trigger alert
                await self.send_security_alert({
                    "type": "brute_force",
                    "ip_address": event.get("ip_address"),
                    "failures": recent_failures
                })
```

### Audit Logging

```python
# monitoring/audit.py
class AuditLogger:
    """Comprehensive audit logging"""

    def __init__(self, storage_backend: str = "elasticsearch"):
        self.storage = self._init_storage(storage_backend)

    async def log_event(self, event_type: str, **kwargs):
        """Log audit event"""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "event_id": str(uuid.uuid4()),
            **kwargs
        }

        # Add request context
        if request_id := request_id_var.get():
            event["request_id"] = request_id

        # Store event
        await self.storage.store(event)

    async def log_tool_execution(self, tool_name: str, user_id: str,
                                args: Dict, result: Any):
        """Log tool execution for audit"""
        await self.log_event(
            "tool_execution",
            tool_name=tool_name,
            user_id=user_id,
            args=self._sanitize_args(args),
            result_size=len(str(result)),
            success=True
        )

    def _sanitize_args(self, args: Dict) -> Dict:
        """Remove sensitive data from args"""
        sanitized = {}
        sensitive_keys = {"password", "token", "secret", "key"}

        for key, value in args.items():
            if any(s in key.lower() for s in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value

        return sanitized
```

## Cost Monitoring

### Cloud Cost Tracking

```python
# monitoring/cost_tracking.py
import boto3
from google.cloud import billing_v1
from azure.mgmt.consumption import ConsumptionManagementClient

class CostMonitor:
    """Monitor cloud infrastructure costs"""

    def __init__(self, cloud_provider: str):
        self.provider = cloud_provider
        self._init_client()

    async def get_current_costs(self) -> Dict[str, float]:
        """Get current month costs"""
        if self.provider == "aws":
            return await self._get_aws_costs()
        elif self.provider == "gcp":
            return await self._get_gcp_costs()
        elif self.provider == "azure":
            return await self._get_azure_costs()

    async def _get_aws_costs(self) -> Dict[str, float]:
        """Get AWS costs"""
        ce = boto3.client('ce')

        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': datetime.now().replace(day=1).isoformat(),
                'End': datetime.now().isoformat()
            },
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'SERVICE'}
            ],
            Filter={
                'Tags': {
                    'Key': 'Application',
                    'Values': ['mcp-server']
                }
            }
        )

        costs = {}
        for result in response['ResultsByTime']:
            for group in result['Groups']:
                service = group['Keys'][0]
                cost = float(group['Metrics']['UnblendedCost']['Amount'])
                costs[service] = costs.get(service, 0) + cost

        return costs

    async def set_cost_alerts(self, budget_limit: float):
        """Set up cost alerts"""
        # Create CloudWatch alarm for costs
        cw = boto3.client('cloudwatch')

        cw.put_metric_alarm(
            AlarmName='MCP-Cost-Alert',
            ComparisonOperator='GreaterThanThreshold',
            EvaluationPeriods=1,
            MetricName='EstimatedCharges',
            Namespace='AWS/Billing',
            Period=86400,
            Statistic='Maximum',
            Threshold=budget_limit * 0.8,  # Alert at 80% of budget
            ActionsEnabled=True,
            AlarmActions=['arn:aws:sns:region:account:cost-alerts'],
            AlarmDescription=f'Alert when MCP costs exceed 80% of ${budget_limit} budget'
        )
```

## Best Practices

### 1. Monitoring Strategy
- **Golden Signals**: Focus on latency, traffic, errors, and saturation
- **SLI/SLO Definition**: Define clear service level indicators and objectives
- **Alert Fatigue**: Avoid over-alerting, focus on actionable alerts

### 2. Dashboard Design
- **Information Hierarchy**: Most important metrics at the top
- **Time Windows**: Consistent time windows across panels
- **Color Coding**: Red for errors, yellow for warnings, green for healthy

### 3. Log Management
- **Structured Logging**: Always use structured JSON logs
- **Correlation IDs**: Track requests across services
- **Log Levels**: Use appropriate log levels (ERROR, WARN, INFO, DEBUG)

### 4. Performance Monitoring
- **Baseline Establishment**: Know your normal performance metrics
- **Trend Analysis**: Look for gradual degradation
- **Capacity Planning**: Monitor resource usage trends

### 5. Security Monitoring
- **Anomaly Detection**: Identify unusual patterns
- **Compliance Logging**: Ensure audit requirements are met
- **Incident Response**: Have clear procedures for security events

## Conclusion

Effective monitoring and observability are essential for maintaining reliable MCP deployments. By implementing comprehensive metrics, logging, tracing, and alerting, you can ensure your MCP servers perform optimally and issues are detected and resolved quickly.
