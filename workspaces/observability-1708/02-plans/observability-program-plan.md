# Observability Program Plan — Issue #1708

**Shape:** multi-wave, 5-distribution program. Value-ranked per `value-prioritization.md` (anchor: issue #1708, user-filed 2026-07-13). Wave-structured per `wave-loop.md`. Each wave = its own PR(s) + version bump + **irreversible PyPI release**.

## Architecture decision (cross-cutting — gates all waves)

**Recommendation: consolidate on the OpenTelemetry Meter API as the single metrics backend, behind one façade, with a Prometheus exposition reader feeding `/metrics` AND an OTLP metrics exporter.**

Why this pick makes the whole contract fall out of one design:

- One backend → one unified registry (gap 2) → one `/metrics` scrape (dim 1) via OTel's Prometheus reader.
- The OTLP metrics signal (dim 5) is a second reader on the _same_ meters — no parallel instrumentation.
- Resource attributes (`service.name`/`version`) attach once at provider construction (covers all signals).
- Exemplars (metric→trace) are native to the OTel metrics SDK once traces share the provider.

**Cons (honest):** larger blast radius than a Prometheus-only unification — migrating the custom `MetricsRegistry` + the `prometheus_client` direct emitters onto OTel touches 6 core modules; and OTel's Python metrics SDK exemplar support must be version-checked (`opentelemetry-sdk>=1.20` declared). Alternative (Prometheus-only unified registry) is smaller but leaves the OTLP-metrics-signal requirement (dim 5) unmet — a hard #1708 checklist item — so it does not satisfy the contract.

## Waves (value-ranked)

**Wave 1 — Core foundation (`kailash`)** · HIGHEST value, unblocks every other wave, self-contained in core. Sharded (invariant surface > single-shard budget):

- **1a — OTLP bootstrap** (`observability/otlp.py`) — ✅ DONE (branch `feat/obs-1708-w1a-otlp-bootstrap`, commit `1cb5b0708`): `configure_observability()` installs TracerProvider+MeterProvider+LoggerProvider, OTLP exporters env-gated on `OTEL_EXPORTER_OTLP_ENDPOINT`, `Resource(service.name, service.version=kailash.__version__)`, idempotent, degrades cleanly when `[telemetry]` absent, does NOT clobber a host-configured provider. Added `opentelemetry-exporter-prometheus` to `[telemetry]`. 6 regression tests; verified an OTel histogram exports as a real `le`-bucketed Prometheus histogram. _Keystone; architecture-agnostic; additive._
  - **Finding from the 1a export walk (feeds 1b + every subsystem wave):** OTel's DEFAULT histogram buckets are generic-scale (`le=0,5,10,…,10000`) — **useless percentiles for a `_seconds` latency metric**. Every latency Histogram instrument (core + sub-packages) MUST declare an explicit second-scale bucket boundary set, else "aggregatable p95/p99" is nominally met but practically broken.
- **1b — Unified registry façade + `/metrics`**: bridge the `prometheus_client` global REGISTRY + OTel Prometheus reader + pool lines into ONE server `/metrics` output; converge name/units. _Depends on 1a (available)._ File ownership — `servers/workflow_server.py` + `servers/enterprise_workflow_server.py` (the endpoint); **shares `servers/connection_metrics_router.py` with 1c → 1b+1c serialize or one shard owns that file** (avoids the parallel-edit conflict).
- **1c — Pool USE histogram + completeness**: real `kailash_pool_acquire_wait_seconds` histogram; add idle + exhaustion to the router; fix the mislabeled quantiles-as-histogram.
- **1d — Orphaned enterprise-adapter disposition**: wire `record_*` into the runtime hot path with BOUNDED labels (drop `workflow_id` UUID → `workflow_name`/`success`) — closing the latent cardinality bomb — OR delete the adapter path. Recommend wire+bound (delivers workflow RED).
- **1e — Bounded ML labels** (`observability/ml`): top-N bucket `model_name`/`version`/`feature_name`.

**Wave 2 — MCP (`kailash-mcp`)** · self-contained, clean win. Replace client-side p95/p99 summary with `prometheus_client.Histogram("mcp_tool_duration_seconds", ["tool"])`.

**Wave 3 — DataFlow (`kailash-dataflow`)** · add per-query RED histogram (`dataflow_query_duration_seconds`, bounded `operation`/`model` labels); mirror the correct `fabric/metrics.py` pattern.

**Wave 4 — Kaizen (`kailash-kaizen`)** · high enterprise value (cost visibility). Replace the fake count/sum prod histogram with the real one already in `metrics_hook.py`; add `kaizen_llm_{prompt,completion}_tokens_total` + `kaizen_llm_cost_microdollars_total` counters at the `cost_update` emission site.

**Wave 5 — Nexus core-gateway (`kailash-nexus`)** · smallest gap (HTTP already correct via middleware). Ensure the histogram middleware covers core-gateway HTTP entry points, not only Nexus-wrapped ones.

Inter-wave gate (G1–G5, `wave-loop.md`): each non-final wave → `/redteam` to convergence + spec update + re-rank before the next.

## Specs impact

No dedicated metrics-export spec exists (`nexus-services.md` covers metrics narrowly; `kaizen-observability.md` covers traces). New `specs/observability-metrics.md` to author as the domain authority for the unified contract (`specs-authority.md` Rule 1).

## Release cadence (the human-gated, irreversible decision)

Options: **(A)** one release per distribution as each wave converges (5 releases, incremental value delivery); **(B)** hold all until every wave converges, then a coordinated 5-release bundle (atomic contract, longer to first value); **(C)** core-first (Wave 1 → kailash release), then the 4 sub-package waves. **Recommend (C)** — Wave 1 is the keystone that makes the OTel meters actually export, so shipping it first delivers the biggest single jump in enterprise-readiness and de-risks the sub-package waves that build on the unified provider.
