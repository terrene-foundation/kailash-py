# Kailash ML Serving Specification (v1.0 Draft)

Version: 1.0.0 (draft)

**Status:** DRAFT — shard 4B of round-2 spec authoring. Resolves round-1 HIGH findings: "no Prometheus metrics on InferenceServer", "shadow stage has no shadow-traffic consumer" (fake-feature `rules/zero-tolerance.md` Rule 2 violation), "no batch-inference engine", "no streaming", "no tenant_id on InferenceServer", "no request correlation ID / observability".
**Sibling specs:** `ml-engines.md` §2 (MLEngine.serve() entry point), `ml-registry-draft.md` (consumes), `ml-drift.md` (shadow divergence feeds drift), `ml-tracking.md` (inference events feed the tracker).
**Scope:** ONE canonical inference server delivering REST, gRPC, MCP, online + batch + streaming inference with per-tenant quotas, shadow traffic, canary deploys, Prometheus metrics, and full audit via contextvar to the ambient tracker.

---

## 1. Scope and Non-Goals

### 1.1 What InferenceServer IS

`InferenceServer` is the canonical inference runtime for kailash-ml. It:

1. Loads a model via `ModelRegistry.get_model(name, alias="@production")` per `ml-registry-draft.md` §9.1 — paths, file names, raw pickle handles are BLOCKED.
2. Serves predictions via three channels: REST (via `kailash-nexus` mount), gRPC (via `grpcio` optional extra), MCP (via `kailash-mcp` tool registration).
3. Runs ONNX artifacts by default, TorchScript when explicitly loaded, GGUF for align-served LLMs (cross-spec).
4. Supports online (request-per-request), batch (large file/DataFrame), and streaming (SSE / gRPC streaming / WebSocket) inference modes.
5. Routes shadow traffic + canary traffic with production/shadow divergence telemetry.
6. Emits Prometheus metrics + structured logs + audit events into the ambient tracker.
7. Enforces per-tenant rate limits + size quotas; rejects over-quota requests with `TenantQuotaExceededError`.

### 1.2 What InferenceServer IS NOT

- Not a model registry — uses one (`ml-registry-draft.md`).
- Not a drift monitor — feeds one (`ml-drift.md`).
- Not an autoscaler — emits hints (`expected_qps`, `p95_target_ms`, `memory_budget_mb`) for Nexus/K8s to consume. Autoscaling is a Nexus/Kubernetes concern.
- Not an API framework — mounts into Nexus; does not own HTTP routing primitives. Raw FastAPI / custom `aiohttp` paths are BLOCKED per `rules/framework-first.md`.
- Not a gateway — auth, rate limit, and session are delegated to Nexus middleware.

### 1.3 Non-Goals as MUST NOT

- **MUST NOT** expose a model by file path or raw bytes — every serve entry resolves through `ModelRegistry`.
- **MUST NOT** accept requests without resolving a `tenant_id` at the entry boundary — Nexus middleware extracts tenant from auth; bare-metal deployments use `tenant_id="_single"` (canonical cross-spec sentinel per `ml-tracking.md §7.2`).
- **MUST NOT** expose a `shadow` stage to the registry without a shadow-traffic consumer — this round-1 HIGH is the textbook `rules/zero-tolerance.md` Rule 2 "fake tenant isolation / fake encryption" pattern. §6 implements the consumer; failure to ship §6 together with shadow-stage support blocks release.
- **MUST NOT** silently swallow a shadow-model failure — divergence detection + error logging is mandatory (§6.4).
- **MUST NOT** cache predictions across tenants — cache keys are tenant-scoped per `rules/tenant-isolation.md` MUST 1 (§8.3).

---

## 2. Construction

### 2.1 Canonical Surface

```python
@dataclass(frozen=True, slots=True)
class InferenceServerConfig:
    tenant_id: str
    model_uri: str                          # "registry://fraud@production" OR "registry://fraud:7"
    format: Literal["onnx", "torchscript", "gguf"] = "onnx"
    batch: bool = True                       # enable micro-batching at predict()
    micro_batch_window_ms: float = 5.0       # window for collecting concurrent calls
    micro_batch_max_size: int = 64
    shadow: InferenceShadowSpec | None = None
    canary: InferenceCanarySpec | None = None
    cache: InferenceCacheSpec | None = None  # None = no response cache (only model cache)
    rate_limit: InferenceRateLimitSpec | None = None
    expected_qps: int | None = None           # autoscaling hint
    p95_target_ms: float | None = None        # autoscaling hint
    memory_budget_mb: int | None = None       # autoscaling hint
    request_id_source: Literal["nexus", "header", "generate"] = "nexus"
    # A10-3 ONNX custom-op export + fallback enumeration
    ort_extensions: list[str] | None = None   # custom-op package names (e.g. ["onnxruntime_extensions"])
    opset_imports: dict[str, int] | None = None  # derived from signature.opset_imports at load
    allow_pickle: bool = False                # explicit opt-in to pickle fallback (§2.5.3)
    # A10-1 padding override
    length_buckets: tuple[int, ...] | None = None  # None = DEFAULT_LENGTH_BUCKETS (§4.1.2)
    # A3-3 histogram bucket override
    latency_buckets_ms: tuple[float, ...] | None = None  # None = LATENCY_BUCKETS_MS (§3.2.2)


class InferenceServer:
    def __init__(
        self,
        config: InferenceServerConfig,
        *,
        registry: ModelRegistry,
        tracker: Optional[ExperimentRun] = None,     # HIGH-8 — user-visible handle; None → get_current_run() (CRIT-4)
        metrics_registry: MetricsRegistry | None = None,  # None = module default
        audit_store: AuditStore | None = None,
    ):
        ...
```

### 2.2 Registry-Backed Construction (Canonical)

The canonical construction is through `MLEngine.serve(...)`, which resolves the registry + tracker + audit store from the ambient engine:

```python
# DO — engine.serve() owns composition
engine = km.Engine(store=url, tenant_id="acme")
server = await engine.serve(
    model="fraud",
    alias="@production",
    shadow=ShadowSpec(alias="@challenger", percent=10),
    rate_limit=RateLimitSpec(per_tenant_rps=500),
)

# DO — direct construction still permitted for bare-metal deployments
server = InferenceServer(
    InferenceServerConfig(
        tenant_id="acme",
        model_uri="registry://fraud@production",
    ),
    registry=my_registry,
)
```

### 2.3 Top-Level `km.serve` Convenience Wrapper

In addition to `engine.serve(...)`, `kailash-ml` exports a package-level `km.serve(...)` wrapper that dispatches to the tenant-scoped cached default engine (per `ml-engines-v2.md §15.5`). This wrapper exists to deliver the newbie-UX one-line serve path that every competitor (MLflow Serving, BentoML, TorchServe) ships.

```python
import kailash_ml as km

# DO — one-line serve against a registered + promoted model
server = await km.serve("fraud@production")  # alias baked into URI
# server.url -> "http://127.0.0.1:8080/ml/predict/fraud"
# server.status -> "ready"
# await server.stop()

# DO — explicit alias kwarg, multi-channel
server = await km.serve("fraud", alias="@production", channels=("rest", "mcp"))

# DO — pinned version, tenant-scoped
server = await km.serve("fraud", version=7, tenant_id="acme")
```

#### 2.3.1 Signature

```python
async def serve(
    model_uri_or_result: "str | RegisterResult",
    *,
    alias: str | None = None,                          # e.g. "@production", "@staging"
    channels: tuple[str, ...] = ("rest",),             # subset of ("rest", "mcp", "grpc")
    tenant_id: str | None = None,
    version: int | None = None,
    autoscale: bool = False,
    options: dict | None = None,
) -> "ServeHandle": ...
```

#### 2.3.2 Behaviour

1. Resolve the cached default engine via `kailash_ml._get_default_engine(tenant_id)` (the per-tenant cache from `ml-engines-v2.md §15.2 MUST 1`).
2. Normalise `model_uri_or_result` — accept `"fraud@production"` (parsed into `model="fraud"` + `alias="@production"`), `"fraud:7"` (parsed into `model="fraud"` + `version=7`), a raw `RegisterResult` (uses `result.name` + `result.version`), or a bare `"fraud"` (requires `alias` or `version` kwarg).
3. Delegate to `await engine.serve(model=..., alias=..., channels=channels, version=version, autoscale=autoscale, options=options)` per `ml-engines-v2.md §2.1 MUST 10` + the eight-method contract.
4. Return the engine method's return value unchanged — a process-local `ServeHandle`.

#### 2.3.3 `ServeHandle` Surface

```python
@dataclass(frozen=True, slots=True)
class ServeHandle:
    url: str                            # primary channel URL (REST if available, else first requested)
    urls: dict[str, str]                # per-channel URLs {"rest": "http://...", "mcp": "mcp+stdio://..."}
    server_id: str                      # opaque identifier for administration
    tenant_id: str | None
    model_name: str
    model_version: int
    alias: str | None
    channels: tuple[str, ...]

    async def stop(self) -> None: ...   # graceful shutdown; drains in-flight requests
    @property
    def status(self) -> Literal["starting", "ready", "draining", "stopped"]: ...
```

#### 2.3.4 MUST: No New Engine Method

`km.serve` is a package-level function. It MUST NOT be added as a ninth method on `MLEngine`. The eight-method surface locked by `ml-engines-v2.md §2.1 MUST 5` is preserved — `km.serve` dispatches INTO the existing `engine.serve(...)` method.

```python
# DO — package-level wrapper, engine method count unchanged at 8
# kailash_ml/__init__.py
async def serve(model_uri_or_result, *, alias=None, channels=("rest",), tenant_id=None, **kw):
    engine = _get_default_engine(tenant_id)
    model_name, parsed_alias, parsed_version = _parse_model_uri(model_uri_or_result)
    return await engine.serve(
        model=model_name, alias=alias or parsed_alias,
        channels=list(channels), version=parsed_version, **kw,
    )

# DO NOT — add km.serve as a 9th engine method
class Engine:
    async def km_serve(self, model_uri, ...): ...  # BLOCKED — grows surface to nine
```

**Why:** `ml-engines-v2.md §15.2 MUST 2` freezes the engine method count at eight. Package-level wrappers are the structural mechanism for adding discoverable lifecycle verbs without growing the class surface.

### 2.4 Reloaded On `@production` Promotion

The server subscribes to the registry's `on_model_promoted` event (emitted by `ml-registry-draft.md` §8.1 step 5). When a promotion targets the alias the server is watching:

1. The server loads the new version in parallel with the currently-serving version.
2. Once the new version passes its post-load sanity check (one warmup prediction on a sample input from the stored signature), the server atomically swaps the pointer.
3. The old version remains loaded for `drain_seconds` (default 30) to complete in-flight requests, then is unloaded.
4. A `server.reload.ok` INFO log is emitted with `prev_version`, `new_version`, `duration_ms`, `tenant_id`.
5. The event is mirrored to the tracker (`ml-tracking.md`) as `inference.model_reloaded`.

Load failure of the new version MUST leave the old version serving + emit `server.reload.error` WARN + write an audit row (`operation="reload_failed"`).

### 2.5 Model-Load Contract (A10-3 — ONNX Custom-Op Export)

When `format="onnx"` and the model signature declares opset imports or the registry has tagged the model with custom-op dependencies, the server MUST configure the ONNX Runtime session with the requested extension packages AND fail loudly with enumerated unsupported ops when extensions cannot satisfy the requirement.

#### 2.5.1 Load-Time Resolution

At `InferenceServer._load_model()`:

1. Resolve `opset_imports` — the server pulls the `_kml_model_versions.onnx_opset_imports: dict[str, int]` column from the model registry (see `ml-registry-draft.md §5.6` — the ONNX Export Probe persists this at `register_model(format="onnx")` time) and passes them to the `onnxruntime.InferenceSession` via session options. Mismatch between session-supported opset and model-requested opset raises `OnnxOpsetMismatchError(model_name, requested_opset, available_opset)`.
2. Register custom-op packages — for each name in the registry's `_kml_model_versions.ort_extensions` JSON list (populated by the probe in `ml-registry-draft.md §5.6` when any non-default opset domain is present, e.g. `["onnxruntime_extensions"]` for the `com.microsoft` domain), the server imports the package and attaches its `get_library_path()` to the ORT session options. Missing packages raise `OnnxExtensionNotInstalledError(package_name)` with install instructions.
3. If the model was tagged by the registry with `_kml_model_versions.onnx_unsupported_ops: list[str]` (non-empty — set when `register_model(format="onnx")` probed and recorded unsupported ops; see `ml-registry-draft.md §5.6`), the server MUST raise `OnnxExportUnsupportedOpsError(model_name, unsupported_ops=[...], suggested_fallback="torch" | "pickle")` before touching the wire.

#### 2.5.2 Fallback Enumeration

`OnnxExportUnsupportedOpsError` enumerates alternate formats in this order:

```python
@dataclass(frozen=True, slots=True)
class OnnxExportUnsupportedOpsError(ModelRegistryError):
    model_name: str
    unsupported_ops: list[str]               # e.g. ["FlashAttentionForward", "RMSNorm"]
    suggested_fallback: Literal["torch", "torchscript", "safetensors", "pickle"]
    install_hints: dict[str, str]            # {format: pip-install-command}
    # Message template:
    # "Model '{model}' requires ONNX ops {ops} not in runtime. Suggested fallback:
    #  {fallback} (install: {install_hints[fallback]}). See ml-registry-draft.md §5.6."
```

Server-side fallback selection order:

1. `torch` (native `.pt`) — best fidelity, requires `[dl]` extra.
2. `torchscript` — traced graph, requires `[dl]` extra.
3. `safetensors` — tensor-weights only (transformers-compatible), requires `[dl]` extra.
4. `pickle` — last-resort; REQUIRES explicit `allow_pickle=True` (per §2.5.3 pickle-gate; §15 L1191 clarifies: opt-in + loud-WARN discipline) AND emits `server.load.pickle_fallback` WARN on every load.

#### 2.5.3 Pickle Fallback Gate (loud-fail discipline)

Per `approved-decisions.md §Implications summary` — the opt-in + loud-WARN discipline that underpins multiple decisions (the `MLError` hierarchy's loud-fail mandate, Decision 1 status-vocab hard-migration, Decision 11 legacy-namespace sunset, and Decision 14 migration-doc-ships-with-breaking-changes) — and `ml-registry-draft.md` pickle-is-last-resort discipline: pickle fallback is BLOCKED unless BOTH:

- `InferenceServerConfig.allow_pickle = True` (explicit opt-in at construction), AND
- `ModelSignature.metadata["allow_pickle"] = True` (tagged at registration time by a human actor).

When both are set, the server MUST emit at load:

```
WARN  server.load.pickle_fallback  model=fraud version=7 tenant_id=acme
      reason="ONNX export failed, unsupported_ops=['FlashAttentionForward']; "
             "torchscript trace failed; pickle fallback gated by allow_pickle=True"
      security_caveat="pickle is arbitrary-code-execution — validate model provenance"
```

An audit row `operation="load_pickle_fallback"` with `actor_id`, `model`, `version`, `unsupported_ops`, `attempted_formats`, `elapsed_ms` is written on every pickle-fallback load — NOT only the first.

#### 2.5.4 Tier-2 Test Binding

`test_inference_onnx_unsupported_ops_enumeration.py` MUST:

1. Register a torch model using FlashAttention-2 → the registry tags `unsupported_ops=["FlashAttentionForward"]`.
2. Server `_load_model(format="onnx")` raises `OnnxExportUnsupportedOpsError` with `unsupported_ops=["FlashAttentionForward"]`, `suggested_fallback="torch"`, `install_hints={"torch": "pip install kailash-ml[dl]"}`.
3. Retry with `format="torch"` succeeds and loads via native `.pt`.
4. Pickle fallback refused when `allow_pickle=False`; succeeds + WARN + audit row when `allow_pickle=True`.

---

## 3. Request Lifecycle — Entry, Exit, Error

### 3.1 Mandatory Log Points (per `rules/observability.md` §1-3)

Every request path (online, batch row, streaming chunk) emits three structured log lines:

```python
# Entry
logger.info("inference.predict.start", extra={
    "tenant_id": tenant_id,
    "request_id": request_id,
    "model": model_name,
    "version": model_version,
    "alias": alias,
    "path": "online" | "batch" | "stream",
    "input_shape": (n_rows, n_cols),
    "mode": "real",                # NOT "fake" — stub detection per rules/zero-tolerance.md
    "actor_id": actor_id,           # from Nexus session, "anonymous" if public endpoint
})

# Exit (success)
logger.info("inference.predict.ok", extra={
    "tenant_id": tenant_id,
    "request_id": request_id,
    "model": model_name, "version": model_version,
    "latency_ms": dt,
    "cache_hit": bool,
    "inference_path": "micro_batch" | "single" | "batch" | "stream",
    "shadow_recorded": bool,
    "mode": "real",
})

# Error
logger.warning("inference.predict.error", extra={
    "tenant_id": tenant_id,
    "request_id": request_id,
    "model": model_name, "version": model_version,
    "latency_ms": dt,
    "exc_type": exc.__class__.__name__,
    "exc_fingerprint": sha256_first8(str(exc)),   # NOT raw message, per dataflow-identifier-safety §2
    "mode": "real",
})
```

Missing any of the three lines is a `rules/zero-tolerance.md` Rule 1 violation (observability.md §1-3 breach).

### 3.2 Prometheus Metrics

Every server exports the following metric families via `MetricsRegistry`:

| Metric                                     | Type      | Labels                                        | Semantics                           |
| ------------------------------------------ | --------- | --------------------------------------------- | ----------------------------------- |
| `ml_inference_duration_seconds`            | histogram | `{tenant_id, model, version, path, outcome}`  | End-to-end request latency          |
| `ml_inference_total`                       | counter   | `{tenant_id, model, version, path, outcome}`  | Request count                       |
| `ml_inference_cache_hit_total`             | counter   | `{tenant_id, model, version}`                 | Response cache hits                 |
| `ml_inference_error_total`                 | counter   | `{tenant_id, model, version, exc_type}`       | Error count by exception class      |
| `ml_inference_shadow_divergence_total`     | counter   | `{tenant_id, model, version, shadow_version}` | Shadow-vs-prod disagreements        |
| `ml_inference_shadow_latency_delta_ms`     | histogram | `{tenant_id, model, version}`                 | Latency gap main - shadow           |
| `ml_inference_model_load_duration_seconds` | histogram | `{tenant_id, model, version, outcome}`        | Load-from-registry duration         |
| `ml_inference_micro_batch_size`            | histogram | `{tenant_id, model, version}`                 | Actual batch size when window fires |
| `ml_inference_tenant_quota_denied_total`   | counter   | `{tenant_id, reason}`                         | Over-quota rejections               |

### 3.2.1 Label Cardinality Bound

Per `rules/tenant-isolation.md` MUST 4, the `tenant_id` label on every family MUST be bounded. Strategy: top-N (default N=100) tenants by traffic get their own label; the remainder bucket as `"_other"`. Operators override N at server construction.

**Why:** A 10K-tenant SaaS with 9 metric families × unbounded tenant labels produces 90K series — past the practical Prometheus limit. Top-N bucketing preserves per-big-tenant visibility AND bounds the explosion.

### 3.2.2 Histogram Bucket Boundaries (A3-3)

Every latency histogram MUST declare explicit bucket boundaries. Prometheus defaults `(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)` saturate at 10s and silently bucket every LLM first-token latency (routinely 30-300s on 1M-context prefill) into the `+Inf` bucket — destroying p99 computation.

```python
# kailash_ml/serving/server.py
LATENCY_BUCKETS_MS: tuple[float, ...] = (
    1, 5, 10, 25, 50, 100, 250, 500,         # online inference (1ms-500ms)
    1_000, 2_500, 5_000, 10_000,             # near-online / batch rows (1s-10s)
    30_000, 60_000, 300_000,                 # batch / LLM streaming (30s-5min)
    float("inf"),                            # overflow
)
# 16 explicit bounds covering:
#   online classical      (1-500ms)
#   online DL / small LLM (500ms-5s)
#   batch per-row         (5-30s)
#   LLM streaming TTFT    (30s-5min, supports 1M-context prefill)
```

Bound to the following metric families:

- `ml_inference_duration_seconds` → recorded in milliseconds via `LATENCY_BUCKETS_MS`.
- `ml_inference_stream_first_token_latency_ms` → same bucket set.
- `ml_inference_stream_subsequent_token_latency_ms` → same bucket set.
- `ml_inference_stream_duration_ms` → same bucket set.
- `ml_inference_shadow_latency_delta_ms` → same bucket set.
- `ml_inference_model_load_duration_seconds` → same bucket set.

#### 3.2.3 Cardinality Budget

Explicit upper bound: **16 buckets × 3 tenant-id classes (top-100 bucketed + `_other` + unbounded admin) × 2 model-id classes = 96 time-series per metric family**. Operators who override `length_buckets` via `InferenceServerConfig.latency_buckets_ms: tuple[float, ...] | None = None` remain bound by the same 96-series cap (validated at server construction — more than 16 buckets raises `MetricCardinalityBudgetExceededError`).

**Why:** Pinning the bucket boundary set AND the cardinality budget guarantees that a 10K-tenant SaaS with 15 metric families produces a predictable ≤1440 series total, well under the 10K-series/instance Prometheus guidance. Default buckets saturate LLM workloads; pinned buckets cover 1ms-to-5min with 16 explicit bounds.

#### 3.2.4 Tier-2 Test Binding

`test_inference_histogram_bucket_coverage.py` MUST run a 60-second synthetic stream (first-token at 35s), scrape `/metrics`, and assert `histogram_quantile(0.99, ml_inference_stream_first_token_latency_ms_bucket)` returns a finite value (NOT `+Inf`).

### 3.3 OpenTelemetry Span

Every request emits an OTel span named `ml.inference.predict` with attributes `{tenant_id, model_name, model_version, alias, request_id, path}`. Parent span = the Nexus request span when mounted under Nexus. Round-1 LOW finding resolves here.

### 3.4 Correlation ID Resolution

`request_id_source` determines the source:

- `"nexus"` (default when mounted) — extract from Nexus's session middleware.
- `"header"` — read `X-Request-ID` header, UUID4 if missing.
- `"generate"` — always generate a fresh UUID4.

Emitted as a response header AND in every log line AND in the tracker event AND in the audit row.

---

## 4. Batch-Inference Engine

### 4.1 Surface

```python
async def predict_batch(
    self,
    df: pl.DataFrame,
    *,
    tenant_id: str,
    chunk_size: int = 1024,
    padding_strategy: Literal["bucket", "pad_to_max", "dynamic", "none"] = "bucket",
    shadow_split: float = 0.0,              # 0.0-1.0; fraction of rows shadowed
    actor_id: str | None = None,
    metadata: dict | None = None,
) -> BatchInferenceResult:
    ...
```

`BatchInferenceResult`:

```python
@dataclass(frozen=True, slots=True)
class BatchInferenceResult:
    tenant_id: str
    model_name: str
    model_version: int
    input_row_count: int
    output: pl.DataFrame                     # polars-native per ml-engines.md §4
    latency_ms_total: float
    latency_ms_p50: float
    latency_ms_p95: float
    throughput_rows_per_sec: float
    shadow_rows_compared: int                # 0 if shadow_split == 0.0
    shadow_divergence_count: int
    padding_strategy: Literal["bucket", "pad_to_max", "dynamic", "none"]  # echoed from request
    padding_wasted_tokens: int               # count of pad tokens computed but discarded (cost telemetry)
    request_id: str
```

### 4.1.1 Padding Strategy Contract (A10-1)

Variable-length inputs (LLM prompts, tokenized text, variable-shape tensors) MUST be routed through one of four explicit strategies. Default is `"bucket"` — the strictly-dominant choice for mixed-length workloads on GPU backends.

```python
padding_strategy: Literal["bucket", "pad_to_max", "dynamic", "none"] = "bucket"
# bucket:     group requests by length into power-of-2 length classes, pad each
#             bucket to its class max. Best throughput/cost ratio for mixed LLM
#             workloads. See §4.1.2 for bucket boundaries.
# pad_to_max: pad every input in the batch to the single max length across the
#             batch. Simplest. Wastes compute on mixed-length inputs but minimises
#             kernel launches. Use for near-uniform-length workloads.
# dynamic:    dispatch variable-length per-token (LLM streaming / continuous
#             batching). Requires vLLM-compatible backend. When the detected
#             backend does NOT advertise continuous-batching capability via
#             `BackendCapability.continuous_batching`, the server MUST fall back
#             to "bucket" + emit `inference.padding.dynamic_fallback` WARN.
# none:       fixed-length inputs (classical tabular ML). No padding applied.
#             Raises `VariableLengthInputError` if inputs have non-uniform shape.
```

#### 4.1.2 Bucket Boundaries

Default length classes (power-of-2 progression):

```python
DEFAULT_LENGTH_BUCKETS: tuple[int, ...] = (64, 128, 256, 512, 1024, 2048, 4096, 8192)
# Dispatch: each request routes to the smallest bucket >= its length.
# Requests exceeding 8192 fall into the max bucket and MUST emit
# `inference.padding.over_max_bucket` WARN (candidate for "dynamic" mode).
```

Operators MAY override via `InferenceServerConfig.length_buckets: tuple[int, ...] | None = None`. Buckets MUST be strictly increasing and MUST NOT include values above the model signature's `max_position_embeddings`.

#### 4.1.3 Padding Direction

- **Decoder-only LLMs** (GPT-style causal): **LEFT-padding** — padding tokens precede the prompt so the most-recent tokens sit at the rightmost positions where the generation cursor begins.
- **All other families** (encoder-decoder, encoder-only, classical sequence models, vision-language models): **RIGHT-padding** — padding tokens follow real tokens.

Direction is resolved from `ModelSignature.architecture` at load time. Mismatch against explicit `padding_direction` kwarg raises `InvalidPaddingDirectionError`.

#### 4.1.4 Cost Telemetry

Every batch call records `padding_wasted_tokens` on the result:

- `bucket`: `sum(bucket_max - input_length for input in batch)` per bucket.
- `pad_to_max`: `sum(batch_max - input_length for input in batch)`.
- `dynamic`: 0 (no padding).
- `none`: 0.

Emitted via metric `ml_inference_padding_wasted_tokens_total{tenant_id, model, version, strategy}` counter and audit row. Enables operators to see the wall-clock-cost of their chosen strategy.

#### 4.1.5 Tier-2 Test Binding

`test_predict_batch_padding_strategy_contract.py` MUST assert:

1. Mixed-length input (sequence lengths `[10, 20, 10, 500, 10, 20, 10, 20]`) produces strictly lower wall-time under `bucket` vs `pad_to_max`.
2. `dynamic` strategy against a backend without continuous-batching capability falls back to `bucket` AND emits the fallback WARN.
3. `none` strategy against variable-length input raises `VariableLengthInputError`.
4. Bucket override via `length_buckets=(32, 64, 128)` restricts dispatch.

### 4.2 Chunked Streaming Internals

The batch engine streams chunks of `chunk_size` rows to avoid loading the full prediction array into memory. Per-chunk latency is recorded AND exported via `ml_inference_duration_seconds` with `path="batch"`. Aggregate p50/p95 are computed in-request.

### 4.3 Shadow Split In Batch Mode

When `shadow_split=0.1`, 10% of rows are passed through both main and shadow models. Divergence rows are recorded per §6.4 even in batch mode.

### 4.4 Large-Batch Path (Optional Extra)

A `predict_batch_from_storage(path, *, tenant_id, actor_id, output_path, ...)` surface reads from object store (S3/GCS/Azure/local), predicts in chunks, writes to an output path. Reserved for `kailash-ml[batch]` extra — NOT in the core package.

### 4.5 Batch Job Persistence

Batch jobs MUST persist a job row to `_kml_inference_batch_jobs(tenant_id, job_id, model, version, state, started_at, completed_at, input_row_count, output_row_count, error)` with state transitions `pending → running → completed|failed`. This lets operators answer "is the 10M-row batch still running?" without poking at Python process state.

---

## 5. Streaming Inference

### 5.1 Channels

Three streaming channels:

1. **SSE (Server-Sent Events)** — via Nexus mount; for LLM token-by-token or classical iterator-over-predictions.
2. **gRPC streaming** — `stream Predict(stream InferenceRequest) returns (stream InferenceResponse)`. Optional extra `kailash-ml[grpc]`.
3. **WebSocket** — via Nexus mount; bidirectional. Primary use case: interactive LLM agent with mid-response tool calls.

### 5.2 Token-By-Token For LLMs

When the loaded model is GGUF / an align-served LLM, the server exposes:

```python
async def predict_stream(
    self,
    prompt: str,
    *,
    tenant_id: str,
    max_tokens: int = 512,
    stop: list[str] | None = None,
    actor_id: str | None = None,
    stream_spec: StreamingInferenceSpec | None = None,  # None → per-server default
) -> AsyncIterator[StreamChunk]:
    ...
```

`StreamChunk`: `{token: str, token_id: int, logprob: float | None, cumulative_text: str, finish_reason: str | None}`.

### 5.2.1 StreamingInferenceSpec (A10-2 — Backpressure Contract)

Every streaming surface MUST accept a `StreamingInferenceSpec` governing server-side buffering, client-disconnect detection, and abort semantics. Default kwargs are per-server; a request MAY narrow them via `stream_spec=`.

```python
@dataclass(frozen=True, slots=True)
class StreamingInferenceSpec:
    max_buffered_chunks: int = 256              # server-side buffer bound per stream
    abort_on_disconnect: bool = True            # kill generation when client disconnects
    chunk_backpressure_ms: float = 500.0        # grace period before "paused" event fires
    sse_last_event_id_gap_seconds: float = 30.0 # SSE disconnect threshold
    ws_ping_timeout_seconds: float = 15.0       # WebSocket ping-pong disconnect threshold
```

#### 5.2.2 Buffer-Full Policy

When the producer (token generator / prediction iterator) outpaces the consumer (SSE/WS client) and the in-memory buffer reaches `max_buffered_chunks`, the server MUST:

1. Emit `stream.backpressure.paused` event to the tracker with `{request_id, tenant_id, buffered_chunks, elapsed_ms}`.
2. Increment `ml_inference_stream_backpressure_paused_total{tenant_id, model, version}` counter.
3. Pause the producer task (`asyncio.Event.clear()`) — the generation kernel STOPS consuming GPU cycles while the buffer drains.
4. Resume the producer when the buffer drains below `max_buffered_chunks // 2` (50% watermark) AND emit `stream.backpressure.resumed` event.

The paused state MUST NOT count as a fault — the stream is healthy but flow-controlled.

#### 5.2.3 Client-Disconnect Detection

Disconnect detection is transport-specific:

- **SSE**: the `Last-Event-ID` header reconnect contract applies. If the client's reconnect-gap exceeds `sse_last_event_id_gap_seconds` (30s default), the server declares disconnect. SSE has no explicit close event, so the server MUST poll the underlying transport with `await asyncio.sleep(0.1)` between chunks and check `response.is_disconnected()` (Starlette primitive) every cycle.
- **WebSocket**: the server MUST send a ping frame every `ws_ping_timeout_seconds / 2` (7.5s default). Two missed pongs = disconnect.
- **gRPC streaming**: rely on `context.is_active()` — falsy = disconnect.

#### 5.2.4 Abort Path (MUST)

When `abort_on_disconnect=True` (the default) AND the server detects client disconnect, the server MUST:

1. Call the backend's abort primitive — `torch.Generator.cancel()` / vLLM `engine.abort(request_id)` / llama-cpp-python `interrupt()`. Generation kernel stops; GPU is freed.
2. Emit `stream.aborted_on_disconnect` WARN with `{request_id, tenant_id, model, version, tokens_generated, elapsed_ms, wasted_gpu_seconds}`.
3. Increment `ml_inference_stream_disconnected_total{reason="client_disconnect", tenant_id, model, version}`.
4. Write an audit row with `outcome="aborted_disconnect"`.
5. NOT flush remaining buffered chunks (the client is gone).

**Why:** A 1M-context LLM prefill on a single A100 costs ~\$0.30 per minute of GPU-time. Running to completion after client hang-up silently wastes operator budget. `abort_on_disconnect=False` is available for callers whose response MUST be computed regardless (e.g. background summarisation jobs), but MUST be explicitly opted-into.

#### 5.2.5 Tier-2 Test Binding

`test_streaming_backpressure_contract.py` MUST assert (against a real test-server + test-client with controllable consumption rate):

1. Producer is paused when buffer reaches `max_buffered_chunks`; `stream.backpressure.paused` event observable; GPU-side generation STOPS (assert via mock kernel counter frozen).
2. Producer resumes when buffer drains below 50% watermark; `stream.backpressure.resumed` event observable.
3. Client disconnect (TCP RST) within 1s of first token → server emits `stream.aborted_on_disconnect` WARN within `chunk_backpressure_ms + sse_last_event_id_gap_seconds` budget; backend `abort()` primitive invoked.
4. `abort_on_disconnect=False` over-ride: client disconnect does NOT call abort; generation runs to `max_tokens`; audit row outcome is `completed_disconnected` (distinct from `aborted_disconnect`).
5. WebSocket: two missed pongs trigger disconnect path identically.

### 5.3 Streaming Audit

Every stream emits:

- One `inference.predict_stream.start` on open (with request_id, tenant_id, model).
- One `inference.predict_stream.chunk` DEBUG per chunk (sampled — default 1 per 16 chunks to avoid log floods).
- One `inference.predict_stream.ok` on clean close with `total_tokens`, `latency_ms_total`, `latency_ms_first_token`.
- One `inference.predict_stream.error` on unclean close.

### 5.4 Streaming Metrics (A7-3 — Token-Metric Split)

A single `tokens_per_sec` histogram conflates first-token latency (time-to-first-token, TTFT) with subsequent-token latency (inter-token latency, ITL). For LLMs where TTFT is 100-1000× slower than ITL, the composite metric is NOT comparable step-to-step. The spec MUST emit four distinct metric families with explicit downstream-SLO bindings:

| Metric                                            | Type      | Labels                                                                        | Semantics / Downstream SLO                                                                                |
| ------------------------------------------------- | --------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `ml_inference_stream_first_token_latency_ms`      | histogram | `{tenant_id, model, version}`                                                 | TTFT — user-facing SLO. p50 / p95 / p99 panel in MLDashboard. Drives the "is my LLM UI snappy" dashboard. |
| `ml_inference_stream_subsequent_token_latency_ms` | histogram | `{tenant_id, model, version}`                                                 | ITL — per-token latency after first token. Drives throughput. Independent from TTFT. p50 / p95 panel.     |
| `ml_inference_stream_total_tokens_total`          | counter   | `{tenant_id, model, version, direction}` where `direction in {input, output}` | Cumulative token counts. Input tokens drive prompt-cost accounting; output tokens drive generation cost.  |
| `ml_inference_stream_duration_ms`                 | histogram | `{tenant_id, model, version}`                                                 | Per-stream session duration (open to close). Drives GPU-occupancy / capacity planning.                    |

Additional operational counters (retained):

- `ml_inference_stream_connections_active` gauge — currently-open streams per tenant.
- `ml_inference_stream_disconnected_total{reason, tenant_id, model, version}` counter — `reason ∈ {client_disconnect, timeout, backpressure_abort, server_error, completed}`.
- `ml_inference_stream_backpressure_paused_total{tenant_id, model, version}` counter — backpressure pause events.
- `ml_inference_padding_wasted_tokens_total{tenant_id, model, version, strategy}` counter — padding cost telemetry (see §4.1.4).

#### 5.4.1 Why The Split Matters

- **TTFT** (first_token_latency) is the user-facing SLO — the latency a user perceives when they hit "send". Chatbot UX dashboards MUST surface TTFT p95, not throughput.
- **ITL** (subsequent_token_latency) drives **throughput** — tokens-per-second in sustained generation. Capacity planning dashboards MUST read ITL p50, not TTFT.
- **total_tokens** (counter) drives **cost accounting** — token-based billing (input + output tokens) is the cost model for every LLM API. Operators MUST be able to compute `sum(rate(ml_inference_stream_total_tokens_total{direction="output"}[5m]))` per tenant.
- **duration_ms** drives **resource occupancy** — a single 60s stream occupies one GPU slot for 60s. Capacity planning MUST see duration histograms to estimate concurrency ceilings.

Grafana can compute lifetime tokens/sec via `sum(rate(ml_inference_stream_total_tokens_total[5m])) / sum(rate(ml_inference_stream_duration_ms_sum[5m]))` — no first-token contamination, no dashboard arithmetic gymnastics.

#### 5.4.2 Emission Contract

- `first_token_latency_ms` is recorded exactly once per stream (time from `predict_stream()` entry to first yielded chunk).
- `subsequent_token_latency_ms` is recorded per-chunk AFTER the first chunk.
- `total_tokens_total` is incremented per chunk, labeled by direction (input tokens counted once at stream open, output tokens counted per yielded chunk).
- `duration_ms` is recorded once at stream close (clean or aborted).

---

## 6. Shadow Traffic

This section resolves the round-1 HIGH finding: "`shadow` stage exists in `ALL_STAGES` but no shadow-traffic consumer; this is fake-feature per `rules/zero-tolerance.md` Rule 2." Below IS the consumer.

### 6.1 ShadowSpec

```python
@dataclass(frozen=True, slots=True)
class InferenceShadowSpec:
    alias: str = "@shadow"                # which alias defines the shadow model
    percent: float = 10.0                 # 0-100, fraction of traffic mirrored
    compare_outputs: bool = True
    divergence_threshold: float = 0.01    # |main - shadow| > threshold triggers divergence event
    max_latency_ms: float = 500            # shadow call aborted past this
    record_to: str = "_kml_shadow_predictions"   # table persistence
```

### 6.2 Lifecycle

For each online prediction request:

1. Forward to main model synchronously — this is the request's blocking path.
2. Sample `uniform(0, 100) < shadow_spec.percent`. If false, return main result, skip shadow.
3. If true, spawn a shadow task (`asyncio.create_task`) that:
   a. Calls shadow model with a latency budget of `max_latency_ms`.
   b. Computes divergence: L1 norm for regression, argmax disagreement for classification, embedding cosine for embeddings.
   c. Emits `inference.shadow.ok` with `{divergence, main_latency_ms, shadow_latency_ms}`.
   d. Persists shadow row: `(tenant_id, request_id, main_version, shadow_version, main_output_fingerprint, shadow_output_fingerprint, divergence, occurred_at)`.
   e. If divergence exceeds threshold, increments `ml_inference_shadow_divergence_total` + emits `ShadowDivergenceError` to the audit trail.
4. Return main result. The shadow task is fire-and-forget for the client; observable via metrics + the shadow table.

### 6.3 Cross-Mode

Shadow split is available on online, batch (§4.3), and streaming inference.

### 6.4 Divergence Event Feeds DriftMonitor

The `_kml_shadow_predictions` table is a first-class `DriftMonitor` source (see `ml-drift.md` §6.5). A persistent divergence trend trips drift alerts.

### 6.5 Shadow Never Affects Correctness

A shadow failure MUST NOT affect the main response. If the shadow model fails to load, times out, or diverges:

- Main request completes unaffected.
- `inference.shadow.error` WARN logged with the shadow's error fingerprint.
- `ml_inference_shadow_error_total{reason}` incremented.
- Audit row written.
- Shadow is NOT retried in-request; the next sampled request picks up the retry.

### 6.6 `predict_with_shadow()` Explicit Entry

For callers who need the shadow result immediately (rare; typically only canary dashboards), an explicit entry:

```python
async def predict_with_shadow(
    self, record, *, tenant_id, actor_id=None,
) -> tuple[PredictionResult, ShadowPredictionResult]:
    ...
```

This form pays the shadow latency synchronously (unlike §6.2 which fire-and-forgets).

---

## 7. Canary Deploys

### 7.1 CanarySpec

```python
@dataclass(frozen=True, slots=True)
class InferenceCanarySpec:
    alias: str = "@canary"
    percent: float = 5.0                   # initial split
    step_percent: float = 10.0             # per-step auto-promotion
    step_interval_seconds: int = 300       # interval between auto-promotions
    error_rate_cap: float = 0.01            # stop-on-error threshold
    p95_cap_ms: float | None = None         # stop-on-latency-regression
    rollback_on_drift: bool = True
```

### 7.2 Lifecycle

Canary is an ALIAS-LEVEL split, NOT a shadow split:

1. Server receives request; RNG decides main vs canary per `percent`.
2. Canary response IS the user-facing response (unlike shadow).
3. `ml_inference_duration_seconds` + `ml_inference_error_total` are tagged with `version=<canary_version>` on canary hits.
4. An auto-promoter (optional) monitors `ml_inference_error_total` + `ml_inference_duration_seconds` for canary; if within caps, steps percent forward by `step_percent` every `step_interval_seconds`. At 100%, auto-promotes `@canary` → `@production` via `registry.promote_model` (requires `actor_id=system`, reason="auto-canary-promotion").
5. Exceeding `error_rate_cap` or `p95_cap_ms` (or rollback_on_drift + a fresh drift alert) pauses the auto-promoter AND emits `server.canary.paused` WARN.

### 7.3 Canary Metrics Panel

The registered metrics provide the panel data. A dashboard widget in `MLDashboard` reads:

- `ml_inference_duration_seconds` split by `version` → latency compare.
- `ml_inference_error_total` split by `version` → error rate compare.
- `ml_inference_shadow_divergence_total` for the canary alias → signal leak.

---

## 8. Caching

### 8.1 Two-Level Cache

1. **Model cache** — loaded models stay in memory (LRU, bounded by `memory_budget_mb`). Eviction on capacity pressure. Cache KEY is `(tenant_id, model_name, version)` — tenant-scoped per `rules/tenant-isolation.md` MUST 1.
2. **Response cache** — optional, per `InferenceCacheSpec`. Caches `predict(features) -> output` keyed by content hash. Disabled by default (models are often non-deterministic or context-dependent).

### 8.2 Response Cache Spec

```python
@dataclass(frozen=True, slots=True)
class InferenceCacheSpec:
    backend: Literal["memory", "redis"] = "memory"
    ttl_seconds: int = 60
    max_size: int = 10_000                 # memory backend only
    deterministic_models_only: bool = True  # only cache when model signature marks deterministic
```

Cache key shape per `ml-engines.md` §5.1 MUST 2: `kailash_ml:v1:{tenant_id}:cache:{model}:{version}:{sha256_features_8}`.

### 8.3 Tenant-Scoped Invalidation

```python
async def invalidate_cache(self, *, tenant_id: str, model_name: str | None = None) -> int:
    ...
```

Returns the number of keys evicted. Tenant-scoped per `rules/tenant-isolation.md` MUST 3.

Pattern: `kailash_ml:v1:{tenant_id}:cache:{model}:*` for model-specific; `kailash_ml:v1:{tenant_id}:cache:*` for tenant-wide.

### 8.4 Response-Cache Safety Guard

When `deterministic_models_only=True` (default), a cache entry is written only when `model.signature.metadata.get("deterministic", False) is True`. Models without that metadata are not response-cached. Users who explicitly mark their LightGBM/LightGBM/sklearn classifier as deterministic opt in; torch forwards with dropout default to NOT cached.

**Why:** `rules/zero-tolerance.md` Rule 2 — a "fake cache" that caches non-deterministic output produces silent wrong answers. Guard MUST exist.

---

## 9. Registry Integration

### 9.1 Canonical Serve Entry

```python
# DO — registry-alias serve; reload on promotion happens transparently
server = await engine.serve(model="fraud", alias="@production")

# DO — explicit version pin for canary/staging
server = await engine.serve(model="fraud", version=7)

# DO NOT — serve a file path
server = await engine.serve(model_path="/tmp/fraud.onnx")  # BLOCKED
```

### 9.2 Promotion Event Subscription

On construction, the server calls `registry.subscribe_on_promoted(alias, callback=self._on_promoted)`. The callback is invoked on every promotion targeting the watched alias AND `(tenant_id, name)`.

### 9.3 Signature Mismatch At Load

On model load, the server compares the loaded signature with the previously-cached signature (if any). Mismatch between sessions (i.e. signature changed across promotion) MUST emit an INFO log `server.signature.changed` but does NOT block — the signature change is a feature of the promotion, expected.

Mismatch between the signature and an incoming request's features → `InvalidInputSchemaError` (per §12.1).

---

## 9A. Schema DDL (Serving Tables)

Resolves Round-3 HIGH B6: DDL blocks for the three serving tables the spec references (`_kml_shadow_predictions`, `_kml_inference_batch_jobs`, `_kml_inference_audit`) but did not define. All three carry `tenant_id` per `rules/tenant-isolation.md` MUST Rule 5 and participate in the audit trail per `rules/event-payload-classification.md`.

### 9A.1 Identifier Discipline

All dynamic table names written by DDL-emitting code MUST route through `kailash.db.dialect.quote_identifier()` per `rules/dataflow-identifier-safety.md` MUST Rule 1. The `_kml_` table prefix (leading underscore marks these as internal tables users should not query directly) MUST be validated in the caller's `__init__` against the regex `^[a-zA-Z_][a-zA-Z0-9_]*$` per `rules/dataflow-identifier-safety.md` MUST Rule 2; table-name + prefix total length MUST stay within the Postgres 63-char limit (Decision 2 approved).

### 9A.2 Postgres DDL

```sql
-- _kml_shadow_predictions
CREATE TABLE _kml_shadow_predictions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id VARCHAR(255) NOT NULL,
  main_model_version_id UUID NOT NULL REFERENCES _kml_model_versions(id),
  shadow_model_version_id UUID NOT NULL REFERENCES _kml_model_versions(id),
  request_id VARCHAR(64) NOT NULL,
  input_hash VARCHAR(72) NOT NULL,  -- sha256:<64hex>
  main_output JSONB NOT NULL,
  shadow_output JSONB NOT NULL,
  divergence_score DOUBLE PRECISION,
  divergence_kind VARCHAR(64),  -- 'value' | 'distribution' | 'class_flip'
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_shadow_tenant_created ON _kml_shadow_predictions(tenant_id, created_at DESC);

-- _kml_inference_batch_jobs
CREATE TABLE _kml_inference_batch_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id VARCHAR(255) NOT NULL,
  model_version_id UUID NOT NULL REFERENCES _kml_model_versions(id),
  actor_id VARCHAR(255),
  input_path TEXT NOT NULL,
  output_path TEXT NOT NULL,
  batch_size INTEGER NOT NULL DEFAULT 1024,
  status VARCHAR(16) NOT NULL DEFAULT 'PENDING',  -- {PENDING, RUNNING, FINISHED, FAILED, KILLED} per Decision 1
  total_rows BIGINT,
  processed_rows BIGINT DEFAULT 0,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  error_class VARCHAR(255),
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_batch_tenant_status ON _kml_inference_batch_jobs(tenant_id, status, created_at DESC);

-- _kml_inference_audit
CREATE TABLE _kml_inference_audit (
  id BIGSERIAL PRIMARY KEY,
  tenant_id VARCHAR(255) NOT NULL,
  model_version_id UUID NOT NULL,
  request_id VARCHAR(64) NOT NULL,
  actor_id VARCHAR(255),
  input_hash VARCHAR(72) NOT NULL,
  output_hash VARCHAR(72) NOT NULL,
  latency_ms DOUBLE PRECISION NOT NULL,
  status_code INTEGER NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_inference_audit_tenant_time ON _kml_inference_audit(tenant_id, occurred_at DESC);
CREATE INDEX idx_inference_audit_request ON _kml_inference_audit(request_id);
```

### 9A.3 SQLite-Compatible Variant

SQLite does not support `UUID`, `JSONB`, `TIMESTAMPTZ`, `BIGSERIAL`, or `DOUBLE PRECISION` as distinct types. The SQLite subset MUST substitute:

- `UUID` → `TEXT` (canonical 36-char hyphenated string; caller generates via `uuid.uuid4()`)
- `JSONB` → `TEXT` (JSON-serialized string; caller `json.dumps()` / `json.loads()`)
- `TIMESTAMPTZ` → `TEXT` (ISO-8601 UTC string, e.g. `2026-04-21T12:34:56.789Z`; caller normalizes to UTC before write)
- `BIGSERIAL` → `INTEGER PRIMARY KEY AUTOINCREMENT`
- `DOUBLE PRECISION` → `REAL`
- `BIGINT` → `INTEGER`
- `DEFAULT gen_random_uuid()` → omitted; caller supplies UUID at insert
- `DEFAULT NOW()` → omitted; caller supplies ISO-8601 UTC string at insert
- `REFERENCES ... (id)` → kept verbatim (SQLite supports FK syntax; enforcement requires `PRAGMA foreign_keys = ON`)

### 9A.4 Tier-2 Schema-Migration Tests

- `test_kml_shadow_predictions_schema_migration.py` — applies §9A.2 + §9A.3 DDL to a fresh Postgres (via `ConnectionManager`) AND a fresh SQLite (`:memory:`); asserts `pragma_table_info` / `information_schema.columns` match the declared shape; asserts composite index `idx_shadow_tenant_created` exists.
- `test_kml_inference_batch_jobs_schema_migration.py` — same contract; additionally asserts the allowed `status` values from Decision 1 `{PENDING, RUNNING, FINISHED, FAILED, KILLED}` all round-trip, and that `status='INVALID'` is rejected when a CHECK constraint is registered.
- `test_kml_inference_audit_schema_migration.py` — same contract; additionally asserts both indexes (`idx_inference_audit_tenant_time`, `idx_inference_audit_request`) exist on both backends.

Each test MUST use `quote_identifier()` when referencing the table name by string for validation queries, closing the `rules/dataflow-identifier-safety.md` Rule 5 loop even for hardcoded test fixtures.

---

## 10. Autoscaling Hints

### 10.1 Hints Are Metadata Only

`expected_qps`, `p95_target_ms`, `memory_budget_mb` are served as server metadata via:

```
GET /ml/server/{server_id}/hints
{
  "expected_qps": 500,
  "p95_target_ms": 50.0,
  "memory_budget_mb": 4096,
  "current_qps_60s": 432,
  "current_p95_ms_60s": 47.3,
  "current_memory_mb": 3810,
}
```

Nexus / K8s HPA / Kubeflow KServe autoscaler consume these via the standard metrics+spec endpoints. kailash-ml does NOT own scaling decisions.

### 10.2 Why Not Own Autoscaling

`rules/framework-first.md` — Nexus owns platform deployment concerns; kailash-ml owns ML lifecycle. Duplicate would violate specialist boundaries. Round-1 MED finding resolves here.

---

## 11. Multi-Tenant Isolation

### 11.1 Tenant Required On Every Entry

Every public method (`predict`, `predict_batch`, `predict_stream`, `predict_with_shadow`, `invalidate_cache`, `reload`) MUST accept `tenant_id`. Missing raises `TenantRequiredError` per `ml-engines.md` §5.1 MUST 3.

### 11.2 Per-Tenant Rate Limit

```python
@dataclass(frozen=True, slots=True)
class InferenceRateLimitSpec:
    per_tenant_rps: int
    per_tenant_burst: int = 0               # 0 = use rps as burst
    per_actor_rps: int | None = None         # None = no actor-level limit
    backend: Literal["memory", "redis"] = "memory"
```

Rate-limit enforcement via token bucket; backend is per-tenant Redis key with atomic INCR+EXPIRE. Over-limit: raise `RateLimitExceededError` + increment `ml_inference_tenant_quota_denied_total{reason="rate_limit"}`.

### 11.3 Per-Tenant Size Quota

On `predict_batch`, verify the tenant's `_kml_tenant_quotas` does not exceed `max_inference_rows_per_day`. Over-quota: raise `TenantQuotaExceededError`.

### 11.4 Per-Request Audit Row (Redacted)

Every request writes an audit row to `_kml_inference_audit`:

- `tenant_id, actor_id, request_id, model, version, alias, occurred_at, latency_ms, outcome, input_row_count, path`.
- `input_fingerprint` — SHA-256 of canonical feature serialization, first 8 hex chars.
- `output_fingerprint` — same for output.
- NO raw feature or prediction values (per `rules/event-payload-classification.md` MUST 2 — classified fields are fingerprinted, not echoed).

### 11.5 Cross-Tenant Cache Leak Test Required

Tier 2 test `test_inference_server_wiring_tenant_isolation.py` MUST verify a tenant-A predict does NOT populate tenant-B cache, and a tenant-A invalidate does NOT clear tenant-B keys. See §14.4.

---

## 12. Error Taxonomy

All inherit from `kailash_ml.errors.InferenceServerError` → `kailash_ml.errors.MLError`, EXCEPT the three ONNX-load errors which inherit from `kailash_ml.errors.ModelRegistryError` → `MLError` (registry-tagging provenance). Cross-cutting errors sitting at the `MLError` root (`MultiTenantOpError` per Decision 12) are re-exported from `kailash_ml.errors` so serving callers may write `except MultiTenantOpError` without importing the `kailash.ml.errors` module directly.

| Error                                  | Raised When                                                                                                                                                                                                                                                                                                                                                                                       | HTTP | Retry safe? |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--: | :---------: |
| `ModelLoadError`                       | Failed to load version from registry (bytes corrupted, format mismatch, missing CAS blob)                                                                                                                                                                                                                                                                                                         | 503  |     No      |
| `ModelNotInRegistryError`              | `model_uri` resolves to a non-existent `(tenant_id, name, alias\|version)`                                                                                                                                                                                                                                                                                                                        | 404  |     No      |
| `InvalidInputSchemaError`              | Request columns don't match model signature                                                                                                                                                                                                                                                                                                                                                       | 400  |     No      |
| `VariableLengthInputError`             | `padding_strategy="none"` but input has non-uniform shape (§4.1.1)                                                                                                                                                                                                                                                                                                                                | 400  |     No      |
| `InvalidPaddingDirectionError`         | Explicit `padding_direction` kwarg contradicts `ModelSignature.architecture` inference (§4.1.3)                                                                                                                                                                                                                                                                                                   | 400  |     No      |
| `TenantRequiredError`                  | `tenant_id` missing                                                                                                                                                                                                                                                                                                                                                                               | 401  |     No      |
| `RateLimitExceededError`               | Per-tenant or per-actor RPS exceeded                                                                                                                                                                                                                                                                                                                                                              | 429  |     Yes     |
| `TenantQuotaExceededError`             | Per-tenant size/count quota exceeded                                                                                                                                                                                                                                                                                                                                                              | 429  |     No      |
| `ShadowDivergenceError`                | Shadow output diverged past threshold (AUDIT-only, never raised to client)                                                                                                                                                                                                                                                                                                                        | n/a  |     n/a     |
| `CanaryGateError`                      | Canary error rate exceeded cap; server paused auto-promote                                                                                                                                                                                                                                                                                                                                        | n/a  |     n/a     |
| `StreamConnectionError`                | Stream client disconnected mid-inference                                                                                                                                                                                                                                                                                                                                                          | n/a  |     Yes     |
| `UnsupportedFormatError`               | `format=` not installed (e.g. torchscript without `[dl]` extra)                                                                                                                                                                                                                                                                                                                                   | 501  |     No      |
| `InferenceTimeoutError`                | Per-request budget exceeded                                                                                                                                                                                                                                                                                                                                                                       | 504  |     Yes     |
| `MetricCardinalityBudgetExceededError` | Operator-supplied `latency_buckets_ms` exceeds 16-bucket cap (§3.2.3)                                                                                                                                                                                                                                                                                                                             | n/a  |     No      |
| `OnnxExportUnsupportedOpsError`        | Registry tagged model with `unsupported_ops` OR ONNX session reports unsupported op at runtime (§2.5). ModelRegistryError.                                                                                                                                                                                                                                                                        | 501  |     No      |
| `OnnxOpsetMismatchError`               | Requested ONNX opset > runtime-supported opset (§2.5.1). ModelRegistryError.                                                                                                                                                                                                                                                                                                                      | 501  |     No      |
| `OnnxExtensionNotInstalledError`       | Requested package in `ort_extensions` is not importable (§2.5.1). ModelRegistryError.                                                                                                                                                                                                                                                                                                             | 501  |     No      |
| `MultiTenantOpError`                   | (Decision 12, cross-cutting, post-1.0) `predict_with_shadow()` across tenants OR cross-tenant model mirror without PACT D/T/R clearance. Root inherits `MLError`, NOT `InferenceServerError`, so `except MLError` catches uniformly across registry + feature-store + serving + tracking. See `ml-tracking-draft.md §9.1.1` + `supporting-specs-draft/kailash-core-ml-integration-draft.md §3.3`. | 403  |     No      |

All errors carry `tenant_id` fingerprint + `request_id` for post-incident correlation.

---

## 13. Industry Parity

### 13.1 Feature Matrix vs Competitors

| Capability                          | kailash-ml (v2.0) | MLflow Serving |    SageMaker EP     | TorchServe |  BentoML  |  KServe   |     Triton      |
| ----------------------------------- | :---------------: | :------------: | :-----------------: | :--------: | :-------: | :-------: | :-------------: |
| REST + gRPC + MCP                   |       **Y**       |      REST      |        REST         | REST+gRPC  | REST+gRPC | REST+gRPC |    REST+gRPC    |
| ONNX-first                          |       **Y**       |    partial     |          Y          |  partial   |  partial  |     Y     |        Y        |
| Polars-native DataFrame input       |       **Y**       |       N        |          N          |     N      |     N     |     N     |        N        |
| Registry-backed (no file paths)     |       **Y**       |       Y        |          Y          |  partial   |  partial  |     Y     |     partial     |
| Prometheus `/metrics`               | **Y** (required)  |    partial     |     CloudWatch      |     Y      |     Y     |     Y     |        Y        |
| OTel tracing                        |       **Y**       |    partial     |          Y          |  partial   |  partial  |     Y     |        Y        |
| Shadow traffic (with consumer)      |       **Y**       |       N        |          Y          |     N      |  partial  |     Y     |        N        |
| Canary with auto-promote            |       **Y**       |       N        |          Y          |     N      |  partial  |     Y     |        N        |
| Batch inference engine              |       **Y**       |    partial     | Y (Batch Transform) |     Y      |     Y     |     Y     |        Y        |
| Streaming (SSE/gRPC/WebSocket)      |       **Y**       |       N        |          N          |  partial   |  partial  |     Y     |        Y        |
| Micro-batching                      |       **Y**       |       N        |       partial       |     Y      |     Y     |     Y     | Y (dyn_batcher) |
| Per-tenant rate limit               |       **Y**       |       N        |       Y (IAM)       |     N      |     N     |     Y     |        N        |
| Per-tenant size quota               |       **Y**       |       N        |          Y          |     N      |     N     |     Y     |        N        |
| Per-request audit row               |       **Y**       |       N        |     CloudTrail      |     N      |     N     |     Y     |        N        |
| Cross-tenant cache isolation tested |       **Y**       |      N/A       |       Y (VPC)       |    N/A     |    N/A    |     Y     |       N/A       |

### 13.2 Position

kailash-ml positions serving as **ONNX-first + polars-native + registry-enforced + multi-tenant from day one**, occupying the niche between MLflow Serving (single-tenant) and SageMaker / KServe (multi-tenant but platform-coupled).

### 13.3 Known Gaps (Post-1.0)

- No GPU-autobatching heuristics (Triton's dynamic batcher is more sophisticated).
- No A/B test splitter beyond 2-way (shadow + canary); multi-arm bandit is post-1.0.
- No payload transform layer (TFServing + KServe both have this; we delegate to Nexus middleware).

---

## 14. Test Contract

### 14.1 Tier 1 (Unit) — Load / Unload / Config

- `test_server_load_onnx_roundtrip` — load an ONNX model, predict one row, unload.
- `test_server_reject_format_without_extra` — TorchScript without `[dl]` extra raises `UnsupportedFormatError`.
- `test_server_missing_tenant_raises_tenant_required` — constructor without `tenant_id` raises.
- `test_server_invalid_input_schema_raises` — mismatched columns raise `InvalidInputSchemaError`.
- `test_server_config_validation` — impossible configs (negative percent, shadow without alias) raise at construction.

### 14.2 Tier 2 — Wiring Through MLEngine Facade (file: `test_inference_server_wiring.py`)

```python
@pytest.mark.integration
async def test_serve_predicts_and_audits(test_suite):
    engine = km.Engine(store=test_suite.url, tenant_id="acme")
    async with km.track(run_name="svc-v1"):
        train = await engine.fit(family="sklearn", model_class=RandomForestClassifier)
    await engine.register(train, name="fraud", actor_id="agent-42")
    await engine.promote(name="fraud", version=1, alias="@production",
                          actor_id="agent-42", reason="ci")

    server = await engine.serve(model="fraud", alias="@production")

    # Real HTTP round-trip via Nexus mount
    async with httpx.AsyncClient(app=engine.nexus_app) as client:
        resp = await client.post("/ml/predict/fraud", json={"features": {...}},
                                  headers={"X-Tenant-Id": "acme"})
        assert resp.status_code == 200
        assert "prediction" in resp.json()
        request_id = resp.headers["X-Request-ID"]

    # Audit row persisted
    audit = await engine._conn.fetchrow(
        "SELECT * FROM _kml_inference_audit WHERE request_id=$1", request_id,
    )
    assert audit["tenant_id"] == "acme"
    assert audit["outcome"] == "success"
    assert audit["latency_ms"] is not None

    # Prometheus metric incremented
    m = engine.metrics_registry.get("ml_inference_total")
    assert m.labels(tenant_id="acme", model="fraud", version="1",
                     path="online", outcome="success")._value.get() >= 1.0
```

### 14.3 Tier 2 — Shadow Divergence Detection

```python
@pytest.mark.integration
async def test_serve_shadow_divergence_recorded(test_suite):
    engine = km.Engine(store=test_suite.url, tenant_id="acme")
    # Two models with deliberately divergent predictions
    prod = await _train_model(engine, "fraud_a", seed=42)
    shadow = await _train_model(engine, "fraud_b", seed=123)
    await engine.promote("fraud_a", prod.version, "@production", actor_id="ci", reason="ci")
    await engine.promote("fraud_b", shadow.version, "@shadow", actor_id="ci", reason="ci")

    server = await engine.serve(
        model="fraud_a",
        alias="@production",
        shadow=InferenceShadowSpec(alias="@shadow", percent=100.0, compare_outputs=True),
    )

    # 50 requests → shadow runs for all (percent=100)
    async with httpx.AsyncClient(app=engine.nexus_app) as client:
        for _ in range(50):
            await client.post("/ml/predict/fraud_a", json={"features": {...}},
                              headers={"X-Tenant-Id": "acme"})

    # Shadow rows recorded, divergences counted
    rows = await engine._conn.fetch(
        "SELECT * FROM _kml_shadow_predictions WHERE tenant_id=$1", "acme",
    )
    assert len(rows) == 50
    divergences = sum(1 for r in rows if r["divergence"] > 0.01)
    assert divergences > 0  # two models with different seeds DO diverge

    # Divergence metric incremented
    div_metric = engine.metrics_registry.get("ml_inference_shadow_divergence_total")
    assert div_metric.labels(tenant_id="acme", model="fraud_a", version="1",
                              shadow_version="1")._value.get() == divergences
```

### 14.4 Tier 2 — Tenant Isolation (Two Tenants, Shared Model Name)

```python
@pytest.mark.integration
async def test_serve_tenant_isolation_same_model_name(test_suite):
    engine_acme = km.Engine(store=test_suite.url, tenant_id="acme")
    engine_bob = km.Engine(store=test_suite.url, tenant_id="bob")

    # Both tenants register a model named "fraud" (different predictions)
    await _train_register_promote(engine_acme, "fraud", seed=42)
    await _train_register_promote(engine_bob, "fraud", seed=999)

    server_acme = await engine_acme.serve(model="fraud", alias="@production",
                                            cache=InferenceCacheSpec(backend="memory"))
    server_bob = await engine_bob.serve(model="fraud", alias="@production",
                                          cache=InferenceCacheSpec(backend="memory"))

    # Same features, but the two tenants' servers return different predictions
    features = {"amount": 100.0, "merchant": "m1"}
    p_acme = await server_acme.predict(features, tenant_id="acme")
    p_bob = await server_bob.predict(features, tenant_id="bob")
    assert p_acme != p_bob

    # Invalidating acme's cache does not evict bob's key
    evicted_acme = await server_acme.invalidate_cache(tenant_id="acme")
    assert evicted_acme >= 1
    p_bob_after = await server_bob.predict(features, tenant_id="bob")
    assert p_bob_after == p_bob  # bob's cache still warm

    # Cross-tenant request refused
    with pytest.raises(TenantRequiredError):
        await server_acme.predict(features, tenant_id=None)

    # Audit row for acme does NOT include bob's request_ids
    acme_audit = await engine_acme._conn.fetch(
        "SELECT DISTINCT tenant_id FROM _kml_inference_audit WHERE tenant_id=$1", "acme",
    )
    assert [r["tenant_id"] for r in acme_audit] == ["acme"]
```

### 14.5 Tier 2 — Batch Inference Round-Trip

```python
@pytest.mark.integration
async def test_serve_predict_batch_round_trip(test_suite):
    engine = km.Engine(store=test_suite.url, tenant_id="acme")
    await _train_register_promote(engine, "fraud", seed=42)
    server = await engine.serve(model="fraud", alias="@production")

    df = pl.DataFrame({"amount": [10.0, 20.0, 30.0] * 500, "merchant": ["m1"] * 1500})
    result = await server.predict_batch(df, tenant_id="acme", chunk_size=100, shadow_split=0.1)
    assert result.input_row_count == 1500
    assert result.output.shape[0] == 1500
    assert 0.05 <= (result.shadow_rows_compared / 1500) <= 0.15
    # Persisted job row
    job = await engine._conn.fetchrow(
        "SELECT * FROM _kml_inference_batch_jobs WHERE tenant_id=$1 ORDER BY started_at DESC LIMIT 1",
        "acme",
    )
    assert job["state"] == "completed"
    assert job["output_row_count"] == 1500
```

### 14.6 Regression Tests (Permanent)

- `tests/regression/test_issue_mlops_HIGH_shadow_consumer_exists.py` — asserts shadow stage always has a consumer; asserts `_kml_shadow_predictions` table populated after a sampled shadow request. Prevents Rule 2 regression.
- `tests/regression/test_issue_mlops_HIGH_prometheus_exists.py` — asserts the server exposes `/metrics` + that the 9 metric families enumerate.
- `tests/regression/test_issue_mlops_HIGH_tenant_required.py` — asserts `TenantRequiredError` raises on every entry method.
- `tests/regression/test_issue_mlops_HIGH_rules_observability_mandatory_log_points.py` — parses log stream during a predict call; asserts start+ok+error are emitted in the correct order with the required extra keys.

---

## 15. Spec Cross-References

- `ml-engines.md` §2.1 MUST 5 — `engine.serve()` is one of the 8 canonical methods.
- `ml-engines.md` §5 — multi-tenancy contract; this spec enforces.
- `ml-engines.md` §6 — ONNX-default; this spec is the primary consumer.
- `ml-registry-draft.md` §9.1 — `get_model(alias="@production")` is the canonical model source.
- `ml-registry-draft.md` §8.1 step 5 — `on_model_promoted` event drives `reload()` here.
- `ml-registry-draft.md` §5.6 — `register_model(format="onnx")` is where `onnx_unsupported_ops` / `onnx_opset_imports` / `ort_extensions` are recorded on `_kml_model_versions` by the ONNX Export Probe; §2.5 of this spec is the load-time consumer.
- `ml-drift.md` §6.5 — `_kml_shadow_predictions` table is a drift source.
- `ml-tracking.md` — ambient tracker receives every lifecycle event (`inference.model_reloaded`, `inference.predict`, `inference.shadow`, `inference.canary.paused`, `stream.backpressure.paused`, `stream.backpressure.resumed`, `stream.aborted_on_disconnect`, `server.load.pickle_fallback`).
- `ml-dashboard-draft.md` §5.2 — MLDashboard SSE topic set. Serving metrics flow via these topics (`metric`, `metric_batch`, `system_metric`, `run_status`). Every serving metric family emitted here (`first_token_latency_ms`, `subsequent_token_latency_ms`, `total_tokens_total`, `duration_ms`, bucket boundaries per §3.2.2) flows through the MLDashboard SSE broker without transformation.
- `kailash-core-ml-integration-draft.md §6` — `kailash.observability.ml` is the metric factory module; every `ml_inference_*` metric family in §3.2 + §5.4 MUST be constructed via this factory so the Prometheus registry + OTel bridge see identical names and bounded-cardinality labels across the SDK.
- `approved-decisions.md` Decision 4 (DDP / FSDP / DeepSpeed rank-0 emission) — all serving metrics + audit rows + tracker events MUST emit from `torch.distributed.get_rank() == 0` only. When InferenceServer is deployed behind a distributed inference backend (e.g. sharded vLLM), the server process acting as rank-0 is the sole metric emitter; worker-rank processes MUST NOT emit to the Prometheus registry or the audit store. Applies identically to §3.2 histograms, §5.4 streaming metrics, §4.1.4 padding cost telemetry.
- `approved-decisions.md` Decision 8 — Lightning hard lock-in has no direct bearing on serving load, BUT the pickle-fallback gate (§2.5.3) derives from the same discipline ("explicit opt-in + loud WARN for escape-hatch paths").
- `rules/tenant-isolation.md` MUST 1-5 — cache key shape, strict typed error, scoped invalidation, bounded metric labels, tenant_id in audit.
- `rules/observability.md` §1-3 — mandatory log points, correlation IDs, mode=real/fake.
- `rules/zero-tolerance.md` Rule 2 — shadow consumer implementation is the direct anti-regression for the fake-feature pattern.
- `rules/event-payload-classification.md` MUST 2 — input/output fingerprinted, never raw in audit.
- `rules/framework-first.md` — delegation to Nexus for HTTP routing and autoscaling.
- `rules/facade-manager-detection.md` — `InferenceServer` is a manager class; §14.2 is the mandatory wiring test.

---

## 16. RESOLVED — Prior Open Questions

All round-2 open questions are RESOLVED. Phase-B SAFE-DEFAULTs S-01..S-05 live in `workspaces/kailash-ml-audit/04-validate/round-2b-open-tbd-triage.md` § S (serving). The Phase-D D1 shard closed the A10 extension items (padding, backpressure, ONNX custom-op probe) in the corresponding sub-sections of this spec. This section is retained for traceability.

| Original TBD                                                                  | Disposition                                                                                                                    | Reference                  |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | -------------------------- |
| gRPC + MCP mount ordering                                                     | **PINNED** — REST + MCP land in 1.0.0 core; gRPC behind `[grpc]` extra.                                                        | Phase-B SAFE-DEFAULT S-01  |
| Multi-arm bandit canary                                                       | **DEFERRED to post-1.0** — 1.0.0 ships 2-way canary (main + canary + shadow); MAB is a future `[serving-mab]` extension.       | Phase-B SAFE-DEFAULT S-02  |
| Response cache for LLM streaming                                              | **DEFERRED to post-1.0** — streaming responses are NOT cacheable at 1.0.0; per-token cache semantics ship in a later revision. | Phase-B SAFE-DEFAULT S-03  |
| Cross-server replication of `(tenant_id, model, alias)`                       | **DEFERRED to post-1.0** — single-server reload at 1.0.0; Nexus-consensus reload ships in a later revision.                    | Phase-B SAFE-DEFAULT S-04  |
| Quantized runtime (INT8 / INT4)                                               | **DEFERRED to post-1.0** — GGUF handles at serve time; ONNX INT8 runtime EP selection deferred to `ml-backends.md` §5.         | Phase-B SAFE-DEFAULT S-05  |
| A10-1: Batch variable-length padding strategy                                 | **CLOSED in Phase-D D1 shard** — explicit padding contract landed in the batch-inference section of this spec.                 | Phase-D D1 (Theme-1 A10-1) |
| A10-2: Streaming backpressure (`abort_on_disconnect` / `max_buffered_chunks`) | **CLOSED in Phase-D D1 shard** — backpressure contract landed in the streaming section of this spec.                           | Phase-D D1 (Theme-1 A10-2) |
| A10-3: ONNX custom-op export probe + fallback                                 | **CLOSED in Phase-D D1 shard** — probe + fallback enumeration landed in the ONNX section of this spec.                         | Phase-D D1 (Theme-1 A10-3) |
