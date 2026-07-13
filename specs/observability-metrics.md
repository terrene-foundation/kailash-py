# Observability — Metrics Export Contract

Domain authority for the unified metrics contract across all 5 Kailash distributions (issue #1708).
This spec describes the metrics-export behavior shipped on the observability program branch: the
OpenTelemetry-unified export façade, the single `/metrics` scrape surface, the per-distribution metric
inventory, and the cardinality discipline every metric label obeys.

Sibling specs: `nexus-services.md` (Nexus service surface), `kaizen-observability.md` (Kaizen traces).
This spec owns the **metrics** signal specifically.

## Architecture

The metrics backend is consolidated behind ONE façade. There is a single configuration entry point and a
single scrape surface; every distribution's metrics reach that surface through the process-wide default
`prometheus_client` registry.

- **Config façade — `configure_observability()`** (`src/kailash/observability/otlp.py`). Installs the OTel
  `MeterProvider` / `TracerProvider` / `LoggerProvider`, attaches a `Resource` carrying `service.name` +
  `service.version` (= `kailash.__version__`), and — gated on `OTEL_EXPORTER_OTLP_ENDPOINT` — wires the
  OTLP exporters for all three signals. Idempotent (`_STATE.configured` guard); a no-op degrade when the
  `[telemetry]` extra is absent; never clobbers a host-configured provider. When `prometheus=True` it also
  installs an OTel `PrometheusMetricReader`, which registers its collector into the **default
  `prometheus_client.REGISTRY`** — so OTel meters and native `prometheus_client` instruments share one
  registry.
- **Scrape surface — `render_prometheus_exposition()`** (`src/kailash/monitoring/metrics.py`). Calls
  `prometheus_client.generate_latest()` over the default `REGISTRY` (folding every instrument registered
  there), concatenated with the custom `MetricsRegistry` text and any router `extra_lines`. Served at the
  `GET /metrics` route of `WorkflowServer` and `EnterpriseWorkflowServer` (`src/kailash/servers/`). Both
  server surfaces emit the identical metric families.
- **Single-registry rule.** Every metric in the contract registers on the **default global
  `prometheus_client.REGISTRY`** (directly, or via the OTel Prometheus reader). A metric on a private
  `CollectorRegistry` is invisible to `generate_latest()` and therefore to `/metrics` — it does not satisfy
  the contract. Instruments are module-level lazy singletons guarding duplicate registration by adopting the
  already-registered collector on `ValueError` (canonical pattern: `_get_acquire_wait_histogram` in
  `src/kailash/core/monitoring/connection_metrics.py`).

## Metric inventory

Every latency histogram declares EXPLICIT second-scale bucket boundaries (OTel/Prometheus defaults are
generic-scale and make `_seconds` p95/p99 meaningless). Counters end `_total`; durations end `_seconds`;
gauges are unsuffixed.

### Core — `kailash`

| Metric                                    | Type      | Labels                                          | Recorded at                                                                                                                                                             |
| ----------------------------------------- | --------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kailash_workflow_executions_total`       | counter   | `workflow.name`, `success`                      | `MetricsBridge.record_workflow_execution` (`src/kailash/runtime/metrics.py`), from the `finally` in `LocalRuntime.execute` / `AsyncLocalRuntime.execute_workflow_async` |
| `kailash_workflow_duration_seconds`       | histogram | `workflow.name`                                 | same (buckets `WORKFLOW_DURATION_BUCKETS_SECONDS`)                                                                                                                      |
| `kailash_node_execution_duration_seconds` | histogram | `node.id`, `node.type`, `status`                | `MetricsBridge` (same explicit buckets)                                                                                                                                 |
| `kailash_pool_acquire_wait_seconds`       | histogram | `pool`                                          | `ConnectionMetricsCollector.track_acquisition` (`src/kailash/core/monitoring/connection_metrics.py`)                                                                    |
| `kailash_pool_connections_idle`           | gauge     | `pool`                                          | `ConnectionMetricsCollector.update_pool_stats`                                                                                                                          |
| `kailash_pool_exhaustion_events_total`    | counter   | `pool`                                          | `ConnectionMetricsCollector.track_pool_exhaustion`                                                                                                                      |
| `kailash_ml_train_duration_seconds`       | histogram | `engine_name`, `model_name`, `tenant_id_bucket` | `src/kailash/observability/ml/__init__.py`                                                                                                                              |
| `kailash_ml_inference_latency_ms`         | histogram | `model_name`, `version`, `tenant_id_bucket`     | same                                                                                                                                                                    |
| `kailash_ml_drift_alerts_total`           | counter   | `feature_name`, `severity`, `tenant_id_bucket`  | `record_drift_alert`                                                                                                                                                    |

### MCP — `kailash-mcp`

| Metric                      | Type      | Labels | Recorded at                                                                                                                               |
| --------------------------- | --------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `mcp_tool_duration_seconds` | histogram | `tool` | `MetricsCollector.track_tool_call` (`packages/kailash-mcp/src/kailash_mcp/utils/metrics.py`), from the real tool/resource/prompt dispatch |

### DataFlow — `kailash-dataflow`

| Metric                            | Type      | Labels               | Recorded at                                                                                                                                                                                                                          |
| --------------------------------- | --------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `dataflow_query_duration_seconds` | histogram | `operation`, `model` | `DataFlowExpress._execute_with_timing` finally block (`packages/kailash-dataflow/src/dataflow/features/express.py`), the choke point every Express CRUD verb routes through; instrument in `dataflow/observability/query_metrics.py` |

### Kaizen — `kailash-kaizen`

| Metric                               | Type      | Labels              | Recorded at                                                                                                                                                            |
| ------------------------------------ | --------- | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kaizen_request_duration_seconds`    | histogram | `agent_type`        | `production/metrics.py`                                                                                                                                                |
| `kaizen_llm_prompt_tokens_total`     | counter   | `model`, `provider` | `MetricsCollector.track_llm_usage`, from both `cost_update` emission points in `kaizen/execution/streaming_executor.py` (primary + per-subagent, double-count guarded) |
| `kaizen_llm_completion_tokens_total` | counter   | `model`, `provider` | same                                                                                                                                                                   |
| `kaizen_llm_cost_microdollars_total` | counter   | `model`, `provider` | same (cost carried as integer micro-dollars)                                                                                                                           |

### Nexus — `kailash-nexus`

| Metric                                | Type      | Labels                      | Recorded at                                                                                         |
| ------------------------------------- | --------- | --------------------------- | --------------------------------------------------------------------------------------------------- |
| `nexus_http_requests_total`           | counter   | `method`, `route`, `status` | `RequestMetricsMiddleware` → `observe_http_request` (`packages/kailash-nexus/src/nexus/metrics.py`) |
| `nexus_http_request_duration_seconds` | histogram | `method`, `route`, `status` | same middleware, `finally` block                                                                    |

## Cardinality discipline

An unbounded metric label is a cost/DoS bomb: one distinct value = one time series, forever. Every label in
the contract has a bounded value space, enforced structurally:

- **Enum labels** — `operation` (DataFlow: the fixed CRUD-verb set), `success` (`"true"`/`"false"`),
  `status` (finite HTTP code space). Unrecognized → `_other`.
- **Whitelist labels** — `method` (Nexus: the 9 standard HTTP verbs via `_method_label`, else `_other`);
  `severity` (ML: `{low, medium, high, critical}` via `_normalize_severity`, else `unknown`).
- **Top-N bucketed labels** — developer/tenant/model-supplied strings that could be high-cardinality are
  admitted top-N by traffic and collapsed to `_other` past the cap: `workflow.name`
  (`_WorkflowNameBucketer`, env `KAILASH_WORKFLOW_METRICS_TOP_N`), the ML `engine_name`/`model_name`/
  `version`/`feature_name`/`tenant_id_bucket` (`_TenantBucketer`), DataFlow `model`, Kaizen `agent_type`
  (env `KAIZEN_METRICS_AGENT_TYPE_MAX_VALUES`) and `model`/`provider` (bounded to the provider registry).
  Every bucketer bounds its INTERNAL counts working set (not just the exported label), capping memory under
  an adversarial flood of distinct values.
- **Bounded-by-construction labels** — `node.id`/`node.type` (developer-authored string literals per
  `patterns.md`), `tool` (MCP decorator-time names), `pool` (operator-assigned pool names). Not per-request
  input.
- **Route templating** — Nexus `route` is the route TEMPLATE (`/users/{id}`), never the concrete path;
  mounted per-workflow sub-apps re-template to `/workflows/{name}/…` so a scanned path cannot mint series.
- **`workflow.name` sentinel** — the `WorkflowBuilder` UUID-fragment auto-name (`Workflow-{8hex}`) collapses
  to `unnamed_workflow` before bucketing (`sanitize_workflow_name`).

## Secret discipline

No credential, API key, prompt/completion text, or PII reaches any metric label or OTel resource attribute:

- **Pool label** — `pool` is redacted through `redact_pool_key` (masks any embedded `user:pass@`).
- **OTLP endpoint log** — `configure_observability` logs the endpoint through `_mask_otlp_endpoint`, which
  redacts embedded userinfo (auth normally travels via `OTEL_EXPORTER_OTLP_HEADERS`, which is never read or
  logged here); resource attributes carry only `service.name` + `service.version`.
- **Kaizen LLM metrics** — only token counts + cost + bounded `model`/`provider` strings are recorded; the
  prompt/response bodies stay on the SSE event stream, never a label.

## Scrape reachability

A metric satisfies the contract only when a co-hosted `WorkflowServer` / `EnterpriseWorkflowServer`
`/metrics` route actually exposes it. Because every contract instrument registers on the default
`prometheus_client.REGISTRY`, `render_prometheus_exposition()` folds them automatically — core, pool, ML,
MCP, DataFlow, Kaizen, and Nexus metrics all appear in the one unified scrape when their package runs inside
a Kailash server process. A standalone process with no HTTP server (e.g. an MCP stdio transport) records the
instruments but exposes no scrape route, by construction.

## OTLP export

When `OTEL_EXPORTER_OTLP_ENDPOINT` is set and `configure_observability()` runs, the OTel meters (workflow
RED, and any OTel-recorded signal) additionally export via the OTLP metrics exporter to the configured
collector, alongside the `/metrics` Prometheus surface. Traces and logs export through the same façade's
providers.
