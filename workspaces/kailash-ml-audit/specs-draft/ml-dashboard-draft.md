# Kailash ML Dashboard — Canonical Tracker-Store Web UI + CLI

Version: 1.0.0 (draft)
Package: `kailash-ml`
Parent domain: ML Lifecycle (`ml-tracking.md` owns the store schema + `ExperimentRun` API; `ml-diagnostics.md` owns the diagnostic-emission contract; `ml-engines.md` owns the engines that feed the store).
Scope authority: `kailash_ml.MLDashboard` class, the `kailash-ml-dashboard` CLI entry point, the REST + SSE + WebSocket endpoints, panel schemas, live-update contract, authentication binding, and templates/static assets.

Status: DRAFT — authored at `workspaces/kailash-ml-audit/specs-draft/ml-dashboard-draft.md`. Becomes `specs/ml-dashboard.md` after human review. New spec — replaces the informal `packages/kailash-ml/src/kailash_ml/dashboard/` README content. Closes Round-1 CRITICAL F-DASHBOARD-DB-MISMATCH, HIGH DL-8 (plot_training_dashboard has no event flow), Industry #4 (dashboard reads same store tracker writes), #14 (run-compare UI), #20 (sharable report), #15 (deep-link URL).

Origin: Round-2 Phase-A authoring cycle, 2026-04-21. Pre-requisites: `ml-tracking.md` v2.0.0-draft (single canonical store path, unified schema) MUST land first.

---

## 1. Scope

### 1.1 In Scope

- **`MLDashboard` class** — one-stop Starlette-based ASGI app backed by the canonical tracker store (`ml-tracking.md`).
- **CLI** — `kailash-ml-dashboard` console script entry point.
- **REST endpoints** — read-only JSON over HTTP.
- **SSE endpoint** — live-metric stream for an in-progress run.
- **WebSocket endpoint** — bidirectional run control (kill, tag, promote).
- **Panels** — Runs, Metrics, Params, Artifacts, Models (registry), Lineage, Drift, System-metrics, Run-Compare, Hyperparameter-sweep heatmaps.
- **Templates + static assets** — single-page HTML at `/`, embedded plotly, no third-party CSS frameworks.
- **Authentication** — Nexus JWT integration when mounted under Nexus; localhost-only + 127.0.0.1 bind when standalone.
- **Tenant-scoped views** — optional `tenant_id` kwarg that scopes every query.
- **Industry parity** — vs MLflow UI, W&B Web, TensorBoard.dev, ClearML UI.

### 1.2 Out of Scope

- **Tracker store schema / `ExperimentRun` API** — `ml-tracking.md` owns both. Dashboard queries via the tracker's public read API (`list_runs`, `search_runs`, `get_run`, `list_metrics`, `list_artifacts`), never via raw SQL.
- **Metric / figure emission** — producers (`ml-diagnostics.md`, `ml-engines.md`, `ml-autolog.md`) emit via `ExperimentRun.log_metric` / `log_figure`; this spec consumes.
- **Model registry CRUD** — `ml-registry.md` owns lifecycle transitions; dashboard displays + delegates promotions via the WebSocket route.
- **Drift-monitor semantics** — `ml-drift.md` owns PSI/KS math; dashboard displays.
- **Authentication provider implementation** — `nexus-gateway.md` owns JWT validation; dashboard consumes.
- **Notebook-inline widget** — deferred to a future `ml-notebook.md` spec.

---

## 2. Scope: One Canonical Dashboard

### 2.1 MUST: No Competing Dashboards

There is **exactly one** kailash-ml dashboard: `kailash_ml.MLDashboard`. The informal `dashboard/` server module used in pre-1.0 is retired; the unified `MLDashboard` replaces it. Both consume the canonical `ExperimentTracker` engine at `~/.kailash_ml/ml.db` per `ml-tracking.md §2.2` (default store path). `rules/orphan-detection.md` §1 applies — a second dashboard class is BLOCKED.

```python
# DO — the canonical import
from kailash_ml import MLDashboard
dashboard = MLDashboard()              # defaults to ~/.kailash_ml/ml.db
app = dashboard.asgi_app               # mount in Nexus or run standalone
```

**BLOCKED rationalizations:**

- "The legacy dashboard still works for users on 0.17.x"
- "A second lightweight dashboard is useful for offline inspection"
- "Users can build their own dashboard on top of the tracker API"

**Why:** Two dashboards mean two schemas to keep in sync, two URL spaces to document, two sources of confusion for "which dashboard does `kailash-ml-dashboard` open?" Round-1 Newbie-UX F-DASHBOARD-DB-MISMATCH was a CRITICAL P0 — the last thing kailash-ml can afford is re-introducing a parallel implementation.

### 2.2 One Entry Per Concern

- `km.track(name=...)` — start a run.
- `ExperimentRun.log_metric(...)` — emit data.
- `MLDashboard()` / `kailash-ml-dashboard` — view data.

Every pair of the three points at the same store. The default store path is `~/.kailash_ml/ml.db` (per `ml-tracking.md §2.2`). If a user points `km.track` at a different store (`store="postgresql://..."`), the dashboard MUST be pointed at the same URL.

---

## 3. Construction

### 3.1 Signature

```python
from kailash_ml import MLDashboard

MLDashboard(
    db_url: Optional[str] = None,       # None = ~/.kailash_ml/ml.db (tracker default)
    *,
    tenant_id: Optional[str] = None,     # scopes every query; None = no tenant scope
    title: str = "Kailash ML",
    bind: str = "127.0.0.1",             # MUST default to loopback in standalone mode
    port: int = 5000,
    enable_control: bool = False,         # False = read-only; True = WS control routes mounted
    auth: Optional["NexusAuthPolicy"] = None,  # None = localhost-only; otherwise JWT-gated
    log_level: str = "INFO",
    cors_origins: Sequence[str] = (),     # empty = same-origin only
)
```

### 3.2 Defaults

When `db_url is None`:

1. Read the `KAILASH_ML_STORE_URL` env var — the canonical cross-spec store-URL variable per `ml-engines-v2.md §2.1 MUST 1b` (store-path env-var authority chain: kwarg → `KAILASH_ML_STORE_URL` → default). Dashboard routes through the same `kailash_ml._env.resolve_store_url()` helper as every other engine. Tier-2 test at `tests/integration/test_engine_store_env.py`. The legacy name `KAILASH_ML_TRACKER_DB` is accepted during 1.x ONLY (see §3.2.1 Migration below).
2. Fall back to `~/.kailash_ml/ml.db` — the canonical tracker default per `ml-tracking.md §2.2`.

**MUST:** The dashboard's default store path MUST equal the tracker's default store path. Divergence is a Round-1 CRITICAL regression.

#### 3.2.1 Migration — `KAILASH_ML_TRACKER_DB` → `KAILASH_ML_STORE_URL` (1.x only)

For 1.x (1.0.0 through the last 1.x release), the dashboard launcher AND the `km.track` resolver MUST accept the legacy `KAILASH_ML_TRACKER_DB` env var with a one-shot DEBUG-level log on first resolution within the process:

```
[DEBUG] kailash_ml.dashboard: legacy env var KAILASH_ML_TRACKER_DB resolved;
        rename to KAILASH_ML_STORE_URL (cross-spec vocabulary; see
        ml-engines-v2.md §2.1 MUST 1b). Legacy var removed at kailash-ml 2.0.
```

The DEBUG log MUST fire at most once per process — a runtime-lifetime `_legacy_env_warned` sentinel prevents dashboards and notebook re-runs from spamming the log pipeline. Precedence: if BOTH `KAILASH_ML_STORE_URL` and `KAILASH_ML_TRACKER_DB` are set, `KAILASH_ML_STORE_URL` wins and the legacy var emits the DEBUG log as above AND a WARN `kml.env.legacy_precedence_ignored`. At 2.0.0, `KAILASH_ML_TRACKER_DB` is ignored entirely (raises `EnvVarDeprecatedError` if the user opts into `KAILASH_ML_STRICT_ENV=1`).

**Why:** "Tracker DB" is incorrect cross-spec vocabulary — the same store also holds registry rows, feature metadata, and audit logs (see `ml-tracking.md §13` for the full table inventory). `STORE_URL` is the engine-level vocabulary; all other engines MUST use the same variable so `km.dashboard` sees the same default as `km.track`, `km.register`, and `FeatureStore` at construction. See `ml-engines-v2.md §2.1 MUST 1b` for the canonical authority chain and the `kailash_ml._env.resolve_store_url()` single-site resolver that every engine — including the dashboard — MUST route through.

### 3.3 Standalone vs Mounted

**Standalone** (no `auth`): `MLDashboard` binds to `127.0.0.1:5000` by default, not `0.0.0.0`. This makes the standalone mode safe-by-default: a developer running the dashboard on a shared workstation does not expose metrics to the LAN. Overriding `bind="0.0.0.0"` is permitted but emits a WARN `mldashboard.bind.exposed_to_network` on startup AND requires `auth=` to be non-None (BLOCKED otherwise — see §8.2).

**Mounted under Nexus**: when Nexus mounts the `asgi_app`, Nexus's JWT middleware is in front; `auth=` should be passed with the Nexus policy. The `bind` / `port` args are ignored (Nexus owns the listener).

### 3.4 Lifecycle

```python
dashboard = MLDashboard()
await dashboard.start()       # opens tracker connection, initializes SSE broker
# ... serve requests ...
await dashboard.stop()        # closes connection, drains SSE subscribers
```

Or, equivalently, via the ASGI app's lifespan handler:

```python
import uvicorn
uvicorn.run(dashboard.asgi_app, host="127.0.0.1", port=5000)
# Starlette lifespan triggers dashboard.start() / dashboard.stop() automatically
```

---

## 4. REST Endpoints (Read-Only JSON)

All REST endpoints are prefixed with `/api/v1/`. All return `application/json`. All accept `Accept: text/html` for the single-page UI wrap (documented in §9).

### 4.1 Route Table

| Method | Path                                     | Purpose                                                       | Response body schema                              |
| ------ | ---------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------- |
| GET    | `/api/v1/runs`                           | List runs, optional filter / limit / order                    | `{runs: list[RunSummary], total: int}`            |
| GET    | `/api/v1/runs/{run_id}`                  | Single run detail                                             | `RunDetail`                                       |
| GET    | `/api/v1/runs/{run_id}/metrics`          | Metric time-series for a run                                  | `{metrics: list[MetricSeries]}`                   |
| GET    | `/api/v1/runs/{run_id}/params`           | Params for a run                                              | `{params: dict[str, Any]}`                        |
| GET    | `/api/v1/runs/{run_id}/artifacts`        | Artifact index for a run                                      | `{artifacts: list[ArtifactHandle]}`               |
| GET    | `/api/v1/runs/{run_id}/artifacts/{name}` | Binary artifact bytes (or signed URL for remote stores)       | `application/octet-stream` or redirect            |
| GET    | `/api/v1/runs/{run_id}/figures`          | Figure index (subset of artifacts with `kind="figure"`)       | `{figures: list[FigureHandle]}`                   |
| GET    | `/api/v1/runs/{run_id}/figures/{name}`   | Plotly JSON for a figure                                      | `plotly.graph_objects.Figure.to_json()`           |
| GET    | `/api/v1/runs/{run_id}/system_metrics`   | System-metrics time-series (CPU, GPU, mem, net)               | `{series: list[SystemMetricSeries]}`              |
| GET    | `/api/v1/runs/compare`                   | Compare N runs (query: `run_ids=a,b,c&metrics=loss,val_loss`) | `{runs: list[RunSummary], overlays: list[...]}`   |
| GET    | `/api/v1/experiments`                    | List experiments (groups of runs)                             | `{experiments: list[ExperimentSummary]}`          |
| GET    | `/api/v1/experiments/{exp_id}/runs`      | Runs in an experiment                                         | `{runs: list[RunSummary]}`                        |
| GET    | `/api/v1/models`                         | List models in the registry                                   | `{models: list[ModelSummary]}`                    |
| GET    | `/api/v1/models/{name}`                  | Model detail + all versions                                   | `ModelDetail`                                     |
| GET    | `/api/v1/models/{name}/versions/{v}`     | Single version detail                                         | `ModelVersionInfo`                                |
| GET    | `/api/v1/lineage/{run_id}`               | Lineage graph: data → run → model → deployment                | `LineageGraph` (see §4.1.1)                       |
| GET    | `/api/v1/drift/{model_name}`             | Drift reports for a served model                              | `{reports: list[DriftReportSummary]}`             |
| GET    | `/api/v1/drift/{model_name}/{report_id}` | Single drift report                                           | `DriftReportDetail`                               |
| GET    | `/api/v1/sweeps/{sweep_id}`              | Hyperparameter sweep trials + parent run                      | `{parent: RunSummary, trials: list[RunSummary]}`  |
| GET    | `/api/v1/health`                         | Health probe (DB reachable, tracker version)                  | `{status: "ok", db: "reachable", version: "..."}` |

### 4.1.1 Canonical `LineageGraph` Reference

The `/api/v1/lineage/{run_id}` endpoint MUST return the JSON serialization of the canonical `LineageGraph` dataclass declared in `ml-engines-v2-addendum-draft.md §E10.2`. This spec does NOT redefine the shape — redefinition is a HIGH finding under `rules/specs-authority.md §5b` (full-sibling-spec re-derivation). The endpoint handler imports the canonical dataclass:

```python
from kailash_ml.engines.lineage import LineageGraph, LineageNode, LineageEdge
```

Response body shape (JSON):

```json
{
  "root_id": "<run_id|model_version|dataset_hash>",
  "nodes": [
    {
      "id": "...",
      "kind": "run|dataset|feature_version|model_version|deployment",
      "label": "...",
      "tenant_id": "...",
      "created_at": "<ISO-8601>",
      "metadata": {}
    }
  ],
  "edges": [
    {
      "source_id": "...",
      "target_id": "...",
      "relation": "produced_by|consumed|used_features|deployed_as|derived_from|evaluated_against",
      "occurred_at": "<ISO-8601>"
    }
  ],
  "computed_at": "<ISO-8601>",
  "max_depth": 10
}
```

The REST handler constructs the `LineageGraph` via `km.lineage(run_id, tenant_id=<request-tenant>)` (§15 top-level wrapper declared in `ml-engines-v2-draft.md §15.8`) and serializes via `dataclasses.asdict()` with the canonical `datetime` → ISO-8601 encoder.

### 4.2 Response Shapes

```python
class RunSummary(TypedDict):
    run_id: str
    experiment: str
    name: str
    status: Literal["RUNNING", "FINISHED", "FAILED", "KILLED"]
    start_time: str                  # ISO-8601
    end_time: Optional[str]
    duration_ms: Optional[int]
    tags: dict[str, str]
    tenant_id: Optional[str]
    # Flattened projection of TrainingResult.device: DeviceReport, populated by
    # ExperimentRun.attach_training_result (ml-tracking §4.6). Source-of-truth
    # for GPU/precision remains the serialized DeviceReport in the run envelope;
    # these fields mirror the 1.x back-compat mirrors on TrainingResult for
    # SQL/JSON response convenience (ml-engines-v2 §4.1).
    device_used: Optional[str]       # == TrainingResult.device.backend_name
    accelerator: Optional[str]       # == TrainingResult.device.family
    precision: Optional[str]         # == TrainingResult.device.precision
    parent_run_id: Optional[str]     # for sweep trials
    metrics_summary: dict[str, float]   # last-value per metric
    url: str                          # deep-link: /runs/{run_id}

class MetricSeries(TypedDict):
    name: str                       # "loss", "grad_norm.encoder.layer.0", etc.
    values: list[tuple[int, float]]  # [(step, value), ...]
    unit: Optional[str]
```

Full TypedDict set is captured in `packages/kailash-ml/src/kailash_ml/dashboard/schemas.py` and cross-referenced by the single-page UI's fetchers.

### 4.3 Filter / Order / Limit

`GET /api/v1/runs?filter=...&order_by=...&limit=...&cursor=...`:

- `filter` — MLflow-compatible expression (`"metrics.accuracy > 0.9"`, `"params.lr = 0.01"`, `"tags.env = 'prod'"`). Delegates to `ExperimentTracker.search_runs` per `ml-tracking.md §5.1` (polars return) + `§5.2` (filter grammar).
- `order_by` — column name with optional `" DESC"` / `" ASC"` suffix.
- `limit` — integer, max 1000 (enforced at the handler).
- `cursor` — opaque pagination token; the handler returns `next_cursor` in the response body.

### 4.4 Refresh Cadence (Per Panel)

| Panel          | Data source endpoint               | Refresh trigger                                 |
| -------------- | ---------------------------------- | ----------------------------------------------- |
| Runs           | `/api/v1/runs`                     | 5-second poll + SSE `run_started` / `run_ended` |
| Metrics        | `/api/v1/runs/{id}/metrics`        | SSE `metric` event (§5) — no polling            |
| Params         | `/api/v1/runs/{id}/params`         | Once on run-detail open                         |
| Artifacts      | `/api/v1/runs/{id}/artifacts`      | SSE `artifact` event                            |
| Models         | `/api/v1/models`                   | 10-second poll + WS `model_promoted` event      |
| Lineage        | `/api/v1/lineage/{run_id}`         | Once on run-detail open                         |
| Drift          | `/api/v1/drift/{model_name}`       | 30-second poll                                  |
| System-metrics | `/api/v1/runs/{id}/system_metrics` | SSE `system_metric` event                       |
| Run-Compare    | `/api/v1/runs/compare`             | Once on compare-panel open                      |
| Sweep-Heatmap  | `/api/v1/sweeps/{sweep_id}`        | SSE `trial_completed` event                     |

---

## 5. SSE — Live Metric Stream

### 5.1 Endpoint

`GET /api/v1/runs/{run_id}/stream` with `Accept: text/event-stream`.

Returns `text/event-stream`. One connection per viewer per run. Stays open until the run transitions out of `RUNNING` (then emits a terminal `run_ended` event and closes) or the client disconnects.

### 5.2 Event Types

```
event: metric
data: {"name":"loss","step":1234,"value":0.042,"timestamp":"2026-04-21T12:34:56Z"}

event: metric_batch
data: {"metrics":[{"name":"grad_norm.layer0","step":1234,"value":0.18}, ...]}

event: figure
data: {"name":"training_dashboard","url":"/api/v1/runs/{id}/figures/training_dashboard"}

event: artifact
data: {"name":"confusion_matrix.png","url":"/api/v1/runs/{id}/artifacts/confusion_matrix.png","kind":"figure"}

event: system_metric
data: {"name":"gpu0.util","timestamp":"2026-04-21T12:34:57Z","value":87.5}

event: run_status
data: {"status":"RUNNING","last_step":1234}

event: run_ended
data: {"status":"FINISHED","end_time":"2026-04-21T12:40:00Z","duration_ms":298000}

event: trial_completed
data: {"trial_id":"...","parent_run_id":"...","metrics":{"accuracy":0.91}}
```

### 5.3 Latency Contract

**MUST:** When a producer calls `await run.log_metric(name, value, step=step)`, the corresponding SSE `metric` event MUST be observable by an already-connected subscriber within **1 second** (P99) under nominal load (≤ 10 concurrent runs, ≤ 1000 metrics/sec aggregate). The contract is asserted by Tier 3 test `test_sse_live_metric_latency`.

**BLOCKED: polling-based live updates.** Implementations that poll the DB every N seconds from the client side violate the 1-second contract under moderate load and burn CPU. The implementation MUST use a pub-sub broker (in-process `asyncio.Queue` fanout for standalone; Redis pub-sub when the tracker backs to Redis per `ml-tracking.md §13` — Dashboard Contract).

### 5.4 Heartbeat

Every 15 seconds, the server emits `:ping\n\n` (SSE comment) to keep the connection alive through idle proxies. Clients treat `:ping` as a no-op.

### 5.5 Backpressure

If a subscriber's `send()` queue exceeds 1000 events, the server drops the oldest and emits a single `event: warning\ndata: {"kind":"backpressure","dropped":N}\n\n` at the next flush. Runaway subscribers are disconnected after 5 consecutive backpressure warnings.

---

## 6. WebSocket — Bidirectional Run Control

### 6.1 Endpoint

`ws://host:port/api/v1/runs/{run_id}/control` (or `wss://` behind TLS).

Mounted **only** when `MLDashboard(enable_control=True)`. Default is `False` — the dashboard is read-only by default; run control is an explicit opt-in. Per `rules/security.md` § Input Validation, write operations require authentication even in localhost mode (§8.3).

### 6.2 Message Types (Client → Server)

```json
{"op": "kill", "reason": "user_requested"}
{"op": "tag", "key": "status", "value": "reviewed"}
{"op": "promote", "model_name": "churn", "version": 7, "alias": "production"}
{"op": "demote", "model_name": "churn", "alias": "production"}
{"op": "comment", "body": "LR spiked at step 1200, investigating."}
```

### 6.3 Message Types (Server → Client)

```json
{"op": "ack", "for": "kill", "status": "ok"}
{"op": "error", "for": "promote", "message": "version 7 not in Staging"}
{"op": "audit", "actor": "user@example.com", "action": "promote", "details": {...}}
```

### 6.4 Authorization

Every write message is authorized via the `auth` policy (§8). For Nexus-mounted deployments, the JWT claim set is consulted:

- `kill` / `tag` / `comment` — require `kailash-ml:write` scope.
- `promote` / `demote` — require `kailash-ml:registry:admin` scope.

For standalone-localhost mode, all writes are permitted without auth (the dashboard trusts its local user).

### 6.5 Audit Trail

Every write operation (`kill`, `tag`, `promote`, `demote`, `comment`) writes a row to the tracker's `audit_log` table per `ml-tracking.md § audit trail`:

- `(timestamp, actor_id, tenant_id, resource_kind, resource_id, action, prev_state, new_state)`

The `audit` server-event echoes the row to the active WebSocket and broadcasts to all connected admins for the same tenant.

---

## 7. Panels (UI Surface)

### 7.1 Panel Inventory

| Panel          | URL                      | Data source(s)                                      | Key UI elements                                                      |
| -------------- | ------------------------ | --------------------------------------------------- | -------------------------------------------------------------------- |
| Runs           | `/`                      | `/api/v1/runs`                                      | Table, filter bar, select-for-compare checkbox                       |
| Run detail     | `/runs/{run_id}`         | `/api/v1/runs/{id}` + SSE stream                    | Metric line charts, params table, artifact list, figure gallery      |
| Metrics        | (tab on run detail)      | SSE `metric` events                                 | Live plotly line chart, smoothing slider, log-y toggle               |
| Params         | (tab on run detail)      | `/api/v1/runs/{id}/params`                          | Key-value table                                                      |
| Artifacts      | (tab on run detail)      | `/api/v1/runs/{id}/artifacts`                       | Download buttons, figure-preview thumbnails                          |
| Figures        | (tab on run detail)      | `/api/v1/runs/{id}/figures/{name}`                  | Inline plotly render from JSON                                       |
| System metrics | (tab on run detail)      | `/api/v1/runs/{id}/system_metrics` + SSE            | Stacked line charts (CPU, GPU, mem)                                  |
| Models         | `/models`                | `/api/v1/models`                                    | Registry table with stage chips                                      |
| Model detail   | `/models/{name}`         | `/api/v1/models/{name}`                             | Version history, alias map, promotion controls (if `enable_control`) |
| Lineage        | `/runs/{run_id}/lineage` | `/api/v1/lineage/{run_id}`                          | Cytoscape-style DAG                                                  |
| Drift          | `/models/{name}/drift`   | `/api/v1/drift/{model_name}`                        | PSI / KS time-series, per-feature heatmap                            |
| Run-Compare    | `/compare`               | `/api/v1/runs/compare?run_ids=...`                  | Overlaid line charts, params diff table, artifact-by-artifact        |
| Sweep heatmap  | `/sweeps/{sweep_id}`     | `/api/v1/sweeps/{sweep_id}` + SSE `trial_completed` | Parallel-coordinates plot, param-vs-metric heatmap                   |
| Health         | `/health`                | `/api/v1/health`                                    | Status badge + version                                               |

### 7.2 Panel MUST Rules

- **Metrics panel**: MUST render from SSE stream, NOT polling. Contract §5.3 applies.
- **Figures panel**: MUST render plotly figures from JSON (server-side `fig.to_json()`), not via `fig.show()` or iframes. XSS-safe — every user-supplied string (figure title, axis label) routes through the `html.escape()` helper per `rules/security.md § Output Encoding`.
- **Run-Compare**: MUST limit to 10 runs per compare request. More than 10 is rejected at the REST handler with 400.
- **Promotion controls**: visible ONLY when `enable_control=True` AND the WS auth scope check would succeed.

### 7.3 Deep-Link URLs

Every run URL is stable: `http(s)://{host}:{port}/runs/{run_id}`. The dashboard prints this URL to stdout on the producer side at `km.track()` exit when `MLDASHBOARD_URL` env var is set (or auto-detected via `~/.kailash_ml/last_dashboard_url`):

```
async with km.track("my-exp") as run:
    ...

# stdout on exit:
# kailash-ml: run finished — view at http://127.0.0.1:5000/runs/abc123...
```

Closes Round-1 Industry L-2 (W&B / Neptune / Comet all print run URLs).

---

## 8. CLI

### 8.1 Entry Point

```bash
kailash-ml-dashboard [OPTIONS]
```

Registered as a `console_scripts` entry in `packages/kailash-ml/pyproject.toml`:

```toml
[project.scripts]
kailash-ml-dashboard = "kailash_ml.dashboard:main"
```

### 8.2 Options

| Option                     | Default                                          | Description                                                                                          |
| -------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| `--db URL`                 | `$KAILASH_ML_STORE_URL` or `~/.kailash_ml/ml.db` | Tracker store URL (legacy `$KAILASH_ML_TRACKER_DB` accepted during 1.x; removed at 2.0 — see §3.2.1) |
| `--host HOST`              | `127.0.0.1`                                      | Bind host. `0.0.0.0` requires `--auth`.                                                              |
| `--port PORT`              | `5000`                                           | Bind port.                                                                                           |
| `--tenant-id ID`           | (none)                                           | Scope every query to this tenant.                                                                    |
| `--title TITLE`            | `Kailash ML`                                     | Dashboard page title.                                                                                |
| `--enable-control`         | `False`                                          | Mount the WebSocket control routes.                                                                  |
| `--auth nexus://URL`       | (none)                                           | Nexus auth policy URL (JWT validation endpoint).                                                     |
| `--cors-origins O1,O2,...` | empty                                            | Permitted CORS origins.                                                                              |
| `--log-level LEVEL`        | `INFO`                                           | Logging level.                                                                                       |
| `--help`                   |                                                  | Print usage and exit 0.                                                                              |
| `--version`                |                                                  | Print version and exit 0.                                                                            |

### 8.3 Security-Sensitive Defaults

- `--host 0.0.0.0` MUST be paired with `--auth`. Launching without auth and with a non-loopback bind exits 2 with the error message: `refused: --host 0.0.0.0 requires --auth; use --host 127.0.0.1 for local-only.`
- `--enable-control` without `--auth` emits a WARN `mldashboard.control.unauthed` on startup and permits writes only on `127.0.0.1`.

### 8.4 Exit Codes

| Code | Meaning                                                             |
| ---- | ------------------------------------------------------------------- |
| 0    | Clean shutdown (SIGTERM / SIGINT).                                  |
| 1    | Unexpected runtime error.                                           |
| 2    | Invalid CLI arguments (incompatible flags, missing required value). |
| 3    | Tracker store unreachable at startup.                               |
| 4    | Port already in use.                                                |

### 8.5 Help Text (MUST)

`kailash-ml-dashboard --help` output MUST include:

1. The canonical default store path (`~/.kailash_ml/ml.db`) visibly stated.
2. A worked example: `kailash-ml-dashboard --db sqlite:///~/.kailash_ml/ml.db --port 5000`.
3. A worked example for Nexus mount: `# Nexus automatically mounts; do not launch standalone.`.
4. A worked example for tenant scope: `kailash-ml-dashboard --tenant-id acme --db postgresql://...`.

### 8.6 Top-Level `km.dashboard` Python Launcher (Non-Blocking)

In addition to the `kailash-ml-dashboard` CLI (§8.1), `kailash-ml` exports a package-level `km.dashboard(...)` function that launches the dashboard non-blockingly on a background event-loop thread. This is the notebook-friendly complement to the CLI — users in Jupyter / VSCode notebooks call `km.dashboard()`, receive a `DashboardHandle`, and continue executing cells without blocking the kernel.

#### 8.6.1 Signature

```python
def dashboard(
    *,
    db_url: str | None = None,                        # None = $KAILASH_ML_STORE_URL → ~/.kailash_ml/ml.db (§3.2)
    port: int = 5000,
    bind: str = "127.0.0.1",
    auth: "NexusAuthPolicy | None" = None,
    tenant_id: str | None = None,
    title: str = "Kailash ML",
    enable_control: bool = False,
    cors_origins: tuple[str, ...] = (),
    log_level: str = "INFO",
) -> "DashboardHandle": ...
```

The `db_url=None` resolution path is identical to the CLI path (§3.2): `KAILASH_ML_STORE_URL` env var, then `~/.kailash_ml/ml.db`. Legacy `KAILASH_ML_TRACKER_DB` acceptance + one-shot DEBUG log per §3.2.1 applies here too.

Kwargs mirror `MLDashboard.__init__` (§3.1). The launcher is intentionally synchronous (not `async def`) — notebook cells often aren't running an event loop, and the launcher spawns its own.

#### 8.6.2 `DashboardHandle` Surface

```python
@dataclass(frozen=True, slots=True)
class DashboardHandle:
    url: str                            # e.g. "http://127.0.0.1:5000"
    bind: str                           # "127.0.0.1" or "0.0.0.0"
    port: int
    db_url: str                         # resolved store URL actually in use
    tenant_id: str | None
    thread_id: int                      # background thread's identifier for debugging
    pid: int                            # host process PID

    def stop(self) -> None: ...         # graceful shutdown; drains SSE subscribers; joins thread
    @property
    def status(self) -> Literal["starting", "ready", "draining", "stopped"]: ...
```

#### 8.6.3 Behaviour (MUST)

1. Construct an `MLDashboard(db_url=db_url, tenant_id=tenant_id, ...)` instance with the kwargs forwarded.
2. Spawn a background daemon thread that owns its own `asyncio` event loop.
3. Call `uvicorn.run(dashboard.asgi_app, host=bind, port=port, log_level=log_level)` inside the thread.
4. Poll the `/api/v1/health` endpoint up to `launch_timeout_seconds=10` to confirm the server reached `"ready"` status before returning.
5. Return the `DashboardHandle` once the health probe passes. Raise `DashboardError` with an actionable message if the timeout expires (port conflict, DB unreachable, etc.).
6. The daemon thread terminates automatically on process exit; `handle.stop()` is the clean-shutdown path.

#### 8.6.4 MUST: Localhost-Only Default Mirrors CLI Default

`bind` defaults to `"127.0.0.1"`. Passing `bind="0.0.0.0"` without `auth` raises `DashboardError` with the same message the CLI emits (§8.3) — network exposure MUST pair with a JWT auth policy. This invariant is a structural `rules/security.md` guard.

#### 8.6.5 Usage

```python
import kailash_ml as km

# DO — notebook workflow: launch, continue, stop
handle = km.dashboard()
# ... cells produce runs that appear live in the browser at handle.url ...
handle.stop()

# DO — explicit port, custom store, tenant scope
handle = km.dashboard(
    db_url="postgresql://localhost/kml",
    port=5001,
    tenant_id="acme",
    enable_control=True,
    auth=NexusAuthPolicy(...),
)
```

#### 8.6.6 MUST: Not A New `MLEngine` Method

`km.dashboard` is a package-level function. It MUST NOT be added as a ninth method on `MLEngine`. The eight-method surface locked by `ml-engines-v2.md §2.1 MUST 5` is preserved — `km.dashboard` is not dispatched through the engine at all; it constructs `MLDashboard` directly with the same store URL the cached default engine would use.

#### 8.6.7 Relationship To The CLI

The CLI (§8.1) is the blocking / foreground launch path for operators and CI deployments. `km.dashboard(...)` is the non-blocking / notebook path. Both construct the same `MLDashboard` class with the same default store path; the only difference is the launcher. Stop behaviour differs:

- CLI — SIGTERM / SIGINT → exit 0 (§8.4).
- Python launcher — `handle.stop()` → `None`; `KeyboardInterrupt` in the host process triggers the thread's shutdown hook automatically.

**Why:** Notebook users are the dominant kailash-ml onboarding surface; forcing them to open a separate terminal to run the CLI breaks the "everything in one cell" promise of the Quick Start (`ml-engines-v2.md §16`). Dual launchers (CLI + non-blocking Python) match the pattern W&B / Neptune / Comet ship — `wandb.init()` + `wandb` CLI, `neptune.init()` + `neptune` CLI. The CLI remains the correct path for production deployments.

---

## 9. Framework + Templates + Static Assets

### 9.1 HTTP Framework

MUST: Starlette (already a transitive dep via `kailash-nexus`). Uvicorn is the default ASGI server for standalone mode. **No new HTTP framework** — re-using Starlette keeps the dep graph minimal and the auth story unified with Nexus.

### 9.2 Templates

A single Jinja2 template at `packages/kailash-ml/src/kailash_ml/dashboard/templates/index.html` renders the shell (`<head>` + empty `<div id="app">` + bootstrap script tag). All panels render client-side in vanilla JavaScript with `plotly.js` loaded from a CDN-or-bundled location.

Panel-specific partials (e.g. `run_detail.html`) are optional convenience templates for SSR-friendly fallback when JS is disabled — NOT required for MVP.

### 9.3 Static Assets

Under `packages/kailash-ml/src/kailash_ml/dashboard/static/`:

- `app.js` — single-page app bootstrap, ≤ 3000 LOC hand-written (no bundler).
- `app.css` — minimal stylesheet, ≤ 500 LOC. **No third-party CSS framework** (no Bootstrap, no Tailwind, no Material-UI). Pure CSS custom properties for theming.
- `plotly.min.js` — bundled `plotly.js` (~3MB gzipped); version pinned in `pyproject.toml` and the dashboard's `__init__.py`.

### 9.4 Why No Third-Party CSS

Per `rules/independence.md`, foundation-independent dependencies only. A Bootstrap or Tailwind pin ties the dashboard to an external vendor's release cadence and licence. 500 LOC of hand-written CSS is the structural minimum for a maintainable UI without the coupling.

### 9.5 `[dashboard]` Extras Declaration

The dashboard is opt-in via `pip install kailash-ml[dashboard]`. Core `kailash-ml` MUST NOT pull Starlette / uvicorn / jinja2 / sse-starlette / websockets transitively — keeping the base install lean for users who never invoke `MLDashboard`.

```toml
# packages/kailash-ml/pyproject.toml
[project.optional-dependencies]
dashboard = [
    "starlette>=0.35",          # ASGI framework (re-used from kailash-nexus dep graph)
    "uvicorn[standard]>=0.25",  # ASGI server for standalone mode
    "jinja2>=3.1",              # Template rendering for the shell HTML
    "sse-starlette>=2.0",       # SSE primitive compatible with Starlette
    "websockets>=12.0",         # WS transport for `/control` endpoint
]
```

**MUST:** Constructing `MLDashboard()` without the `[dashboard]` extra installed MUST raise `MissingExtraError("kailash-ml[dashboard] required for MLDashboard; install via 'pip install kailash-ml[dashboard]'")` at `__init__` time. Deferring the error to the first request is BLOCKED — users need the failure at import time per `rules/zero-tolerance.md` Rule 6.

**Rationale:**

- Starlette + uvicorn + jinja2 + sse-starlette + websockets combined pull ~30 transitive packages. Adding them to core `kailash-ml` inflates the base install by ~45MB for users who only run `km.train()` in notebooks.
- Nexus users already have Starlette via `kailash-nexus`; when the dashboard is mounted under Nexus, the `[dashboard]` extra is additive (jinja2 + sse-starlette + websockets only).
- The `[dashboard]` extra is parallel to `[dl]`, `[rl]`, `[feature-store]` — every optional surface ships as an extra per Decision 13.

### 9.6 `plotly.min.js` Pin

`plotly.min.js` is bundled as a static asset in the Python wheel (~3MB gzipped). Pin version in two places:

1. `pyproject.toml` `[project.optional-dependencies].dashboard` — `plotly>=5.18,<6` (Python plotly for `fig.to_json()` serialization on the producer side, not runtime dep of dashboard itself but advertised together).
2. `packages/kailash-ml/src/kailash_ml/dashboard/__init__.py` — `PLOTLY_JS_VERSION = "2.30.0"` constant; embedded `plotly.min.js` file hash MUST match this version at build time.

A version mismatch between the Python producer's `fig.to_json()` schema and the embedded `plotly.min.js` MUST be caught by a Tier 2 regression (`test_plotly_json_renders_without_warning`).

---

## 9a. Error Taxonomy

All dashboard errors inherit from `DashboardError(MLError)` at `kailash_ml.dashboard.errors`. `DashboardError` itself inherits from `MLError` per `approved-decisions.md §Implications summary` (MLError hierarchy under Decision 14).

| Error class                           | Raised when                                                                                               | HTTP status |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------- | ----------- |
| `DashboardError`                      | Base class — never raised directly.                                                                       | —           |
| `DashboardStoreUnreachableError`      | Tracker store (SQLite file missing, Postgres connection refused) not reachable at startup OR mid-request. | 503         |
| `DashboardAuthDeniedError`            | JWT validation failed, expired token, or missing `Authorization` header when `auth is not None`.          | 401         |
| `DashboardTenantMismatchError`        | JWT's `tenant_id` claim does not match `MLDashboard(tenant_id=...)` constructor value.                    | 403         |
| `DashboardAuthorizationError`         | Authenticated user lacks the required scope (e.g. `kailash-ml:registry:admin` for promotion WS op).       | 403         |
| `DashboardRunNotFoundError`           | `GET /api/v1/runs/{id}` / `POST /control` op on a non-existent `run_id`.                                  | 404         |
| `DashboardFigurePayloadTooLargeError` | Figure JSON exceeds the 50MB per-request cap (§11).                                                       | 413         |
| `DashboardArtifactPathTraversalError` | Artifact name contains `..`, absolute path components, or null bytes (§11).                               | 400         |
| `DashboardRateLimitExceededError`     | Token-bucket exceeded (default 100 req/s per-IP standalone, per-sub under Nexus).                         | 429         |
| `DashboardBackpressureDroppedError`   | SSE subscriber's send queue exceeded 1000; oldest events dropped. Logged, not raised to HTTP response.    | —           |
| `DashboardLiveStreamError`            | SSE / WS transport failure mid-stream (client disconnect AFTER successful handshake).                     | —           |
| `DashboardInvalidFilterError`         | `search_runs` filter-expression parser rejects malformed input.                                           | 400         |

**MUST:** Every error carries a structured `code` attribute (`error_code` str) + actionable remediation in the message per `rules/zero-tolerance.md` Rule 3a. Error messages MUST NOT echo back user-supplied input verbatim (XSS / log-poisoning defense).

```python
# DO — actionable + structured
class DashboardStoreUnreachableError(DashboardError):
    error_code = "dashboard.store.unreachable"
    def __init__(self, db_url_masked: str, underlying: Exception):
        super().__init__(
            f"Tracker store at {db_url_masked} unreachable — "
            f"verify `ls ~/.kailash_ml/ml.db` or the DB server is running. "
            f"Underlying: {type(underlying).__name__}"
        )
```

Maps to §12 observability events (`mldashboard.store.unreachable` etc.) — every error class has a matching log event.

---

## 10. Authentication

### 10.1 Nexus JWT Integration

When `auth` is a `NexusAuthPolicy` (or when the dashboard's ASGI app is mounted under a Nexus `nexus.FastAPI` with JWT middleware), every request's `Authorization: Bearer <JWT>` header is validated against the Nexus JWT endpoint before routing.

Claims consulted:

- `sub` → `actor_id` — logged in audit trail.
- `tenant_id` → filtered against `MLDashboard(tenant_id=...)`; mismatched tenant returns 403.
- `scope` → `kailash-ml:read` for GET, `kailash-ml:write` for POST/WS-write, `kailash-ml:registry:admin` for promotion.

### 10.2 Localhost-Only Mode

When `auth is None`:

- Bind MUST be `127.0.0.1` (see §8.3).
- Audit rows record `actor_id="local"`.
- Every request MUST have `REMOTE_ADDR == 127.0.0.1`; any other source returns 403.

### 10.3 No Embedded Auth Store

The dashboard does NOT implement its own user/session store. `rules/framework-first.md` routes all authentication through `kailash-nexus`. A dashboard-specific auth config is BLOCKED.

---

## 11. Security Threats

| Threat                                              | Mitigation                                                                                                                                                                            |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| XSS via user-supplied run name / tag / figure title | Every template variable passed through Jinja2 `autoescape=True`; every server-side JSON route emits HTML-safe content types; `html.escape()` on every dynamic label before embedding. |
| SQL injection via filter expressions                | Filter parsing delegated to `ExperimentTracker.search_runs` which uses parameterized queries per `ml-tracking.md § security`. No raw SQL in dashboard handlers.                       |
| CSRF on write endpoints (POST + WS)                 | `SameSite=Strict` session cookies; WS requires `Origin` header match of a configured `cors_origins` entry.                                                                            |
| Credentials in log lines                            | DB URL is masked via `mask_url()` helper before logging per `rules/observability.md § credentials`. SQL query strings are NEVER logged at INFO.                                       |
| Unbounded SSE subscribers                           | Per §5.5 backpressure + §3.1 max 1000 subscribers per dashboard instance (beyond the limit, new connections receive 503).                                                             |
| Path traversal on artifact download                 | Artifact names are validated against the registry (canonical names only); `/api/v1/runs/{id}/artifacts/{name}` rejects `..`, absolute paths, and null bytes.                          |
| Localhost-only bypassed via `--host 0.0.0.0`        | §8.3 mandates `--auth` when bind is non-loopback. CLI exits 2 with a clear message otherwise.                                                                                         |
| Cross-tenant leak via filter                        | `MLDashboard(tenant_id="acme")` appends `tenant_id = 'acme'` to every query. `rules/tenant-isolation.md` §1 applies.                                                                  |
| Large figure JSON DoS                               | `/api/v1/runs/{id}/figures/{name}` streams in chunks; per-request byte cap at 50MB (default); exceeding returns 413.                                                                  |
| Rate abuse on poll endpoints                        | Token bucket per-IP (standalone) or per-sub (Nexus); default 100 req/s; exceeding returns 429.                                                                                        |

---

## 12. Observability

Structured logs emitted with the `mldashboard_` prefix to avoid `LogRecord` reserved-name collision per `rules/observability.md` Rule 9.

| Event                                     | Level | When                                                          |
| ----------------------------------------- | ----- | ------------------------------------------------------------- |
| `mldashboard.start`                       | INFO  | ASGI lifespan startup completes.                              |
| `mldashboard.stop`                        | INFO  | ASGI lifespan shutdown completes.                             |
| `mldashboard.bind.exposed_to_network`     | WARN  | `--host 0.0.0.0` passed (with `--auth`).                      |
| `mldashboard.control.unauthed`            | WARN  | `--enable-control` without `--auth`.                          |
| `mldashboard.sse.subscriber_added`        | INFO  | New SSE subscriber for `run_id`.                              |
| `mldashboard.sse.backpressure`            | WARN  | Subscriber's send queue exceeded 1000; oldest dropped.        |
| `mldashboard.sse.subscriber_disconnected` | INFO  | Subscriber disconnected (clean or timeout).                   |
| `mldashboard.ws.message_received`         | INFO  | WS control message received (op + actor).                     |
| `mldashboard.ws.auth_denied`              | WARN  | WS write denied by auth policy.                               |
| `mldashboard.rest.query`                  | INFO  | REST endpoint invoked (method + path + duration_ms + status). |
| `mldashboard.rest.rate_limit_exceeded`    | WARN  | 429 returned to a client for poll-endpoint abuse.             |
| `mldashboard.store.unreachable`           | WARN  | Health probe found the tracker store unreachable.             |

---

## 13. Industry Parity

| Feature                                | kailash-ml MLDashboard (v0.18.0) | MLflow UI         | W&B Web | TensorBoard.dev | ClearML UI |
| -------------------------------------- | -------------------------------- | ----------------- | ------- | --------------- | ---------- |
| Runs table with filter                 | Yes                              | Yes               | Yes     | No              | Yes        |
| Live metric stream                     | Yes (SSE)                        | Polling           | Live WS | Polling files   | Live WS    |
| Run-Compare (N runs overlaid)          | Yes                              | Yes               | Yes     | Yes             | Yes        |
| Figure gallery (plotly JSON)           | Yes                              | Image-only        | Yes     | Image-only      | Yes        |
| System metrics (CPU/GPU/mem)           | Yes (§7.1)                       | No                | Yes     | Scalar only     | Yes        |
| Sweep heatmap / parallel coordinates   | Yes (§7.1)                       | Limited           | Yes     | No              | Yes        |
| Drift panel                            | Yes (§7.1)                       | No                | No      | No              | Yes        |
| Lineage graph                          | Yes (§7.1)                       | Limited           | No      | No              | Yes        |
| Model registry UI                      | Yes (§7.1)                       | Yes               | Yes     | No              | Yes        |
| Run URL deep-link                      | Yes (§7.3)                       | Yes               | Yes     | Yes             | Yes        |
| Bidirectional run control (kill / tag) | Yes (`enable_control`)           | Limited           | Yes     | No              | Yes        |
| Notebook-inline widget                 | Deferred                         | No                | Yes     | No              | No         |
| Tenant-scoped views                    | Yes (§3.1)                       | No                | No      | No              | Yes        |
| Nexus JWT auth                         | Yes (§10.1)                      | Basic-auth plugin | OAuth   | Google auth     | SSO        |
| Localhost-only safe default            | Yes (§3.3)                       | Yes               | N/A     | N/A             | N/A        |
| No third-party CSS framework           | Yes (§9.4)                       | Bootstrap         | React   | Polymer         | React      |

**Deferred (v0.19.0+):**

- **MLD-GAP-1** — Notebook-inline widget (W&B `wandb.init()` renders an IFrame in Jupyter). Requires an `ipywidgets` bridge + a notebook-specific rendering path; deferred pending `ml-notebook.md` spec.
- **MLD-GAP-2** — Sharable report export (W&B Reports). Requires a report-composition API + static export; deferred pending `ml-reports.md` spec.
- **MLD-GAP-3** — Multimodal tiles (W&B image/audio/video). Requires a `log_image` / `log_audio` / `log_video` primitive on `ExperimentRun` + type-aware rendering; deferred pending `ml-tracking.md §multimodal` extension.

---

## 14. Test Contract

### 14.1 Tier 1 (Unit)

`packages/kailash-ml/tests/unit/test_dashboard_unit.py`:

- `MLDashboard.__init__` validation (bind `0.0.0.0` without auth rejected, `port < 1` rejected).
- Route table — every route in §4.1 is registered on `dashboard.asgi_app.routes`.
- SSE broker — `metric_batch` fan-out to N subscribers, backpressure drop.
- Filter parser — valid and invalid MLflow-compatible expressions.
- CLI argument parsing — every flag combination from §8.2.
- Help text — §8.5 required content present.
- Exit codes — §8.4 every code produced by the documented path.

### 14.2 Tier 2 (Integration) — Real SQLite tracker store

`packages/kailash-ml/tests/integration/test_dashboard_wiring.py`:

- Write a run via `km.track()` + `ExperimentRun.log_metric(...)`.
- Open the dashboard against the SAME store path.
- `GET /api/v1/runs` returns the run.
- `GET /api/v1/runs/{id}/metrics` returns the metric series.
- `isinstance(dashboard, MLDashboard)` + facade import from `kailash_ml` (per `rules/facade-manager-detection.md` §1).
- SSE subscriber — open `/stream`, write a metric, assert the metric arrives within 1 second.
- WebSocket — open `/control`, send `kill`, assert the run's status flips to `KILLED` and the audit row is written.
- Tenant scope — `MLDashboard(tenant_id="acme")` returns zero runs for a run written with `tenant_id="beta"`.
- CLI invocation — spawn `kailash-ml-dashboard --db <sqlite>` as a subprocess, `curl` the health endpoint.

### 14.3 Tier 3 (E2E) — Full round-trip

`packages/kailash-ml/tests/e2e/test_dashboard_roundtrip.py`:

- Run the newbie-UX scenario from `workspaces/kailash-ml-audit/03-user-flows/`:
  1. `async with km.track("exp"): result = km.train(df, target="y")`
  2. Start `kailash-ml-dashboard`.
  3. Playwright opens `/` — asserts the run is visible.
  4. Navigate to `/runs/{run_id}` — asserts metrics + params + figures are visible.
  5. Playwright opens `/compare?run_ids=a,b` with two runs — asserts overlay renders.

This closes the Round-1 F-DASHBOARD-DB-MISMATCH CRITICAL as a regression guard. If the tracker and dashboard ever diverge on store path or schema, the E2E fails at step 3.

---

## 15. Cross-SDK Alignment

- **Python surface**: `kailash_ml.MLDashboard` — single canonical dashboard.
- **Rust surface**: No planned kailash-rs equivalent. Cross-SDK agreement is at the store-schema level (`ml-tracking.md`); a kailash-rs tracker writing to the same SQLite / PostgreSQL store is renderable by this dashboard without any Rust code.
- **Protocol alignment**: `MLDashboard` consumes `ExperimentTracker` per its public Python API. The tracker's query primitives are polars-native and SDK-stable per `ml-tracking.md §5.1` (polars return), so a future Rust tracker writing to the same store schema produces rows the dashboard can read without modification.

---

## 16. Related Specs

- `specs/ml-tracking.md` (v2 draft) — store schema, `ExperimentRun.log_metric`, `log_figure`, `log_artifact`.
- `specs/ml-diagnostics.md` (v2 draft, sibling to this file) — producer of the figures + metrics rendered here.
- `specs/ml-autolog.md` (draft) — auto-emission producer.
- `specs/ml-engines.md` (v2 draft) — training pipeline producer.
- `specs/ml-registry.md` (draft) — model registry CRUD that the /models panel renders.
- `specs/ml-drift.md` (draft) — drift-monitor semantics that the /drift panel renders.
- `specs/nexus-gateway.md` — JWT auth path for mounted mode.

---

## 17. Change Log

| Version | Date       | Change                                                                                                                                                                                                                                                             |
| ------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 0.17.0  | 2026-04-20 | Informal `dashboard/` README — pre-1.0 informal server module (retired at 1.0.0).                                                                                                                                                                                  |
| 1.0.0   | 2026-04-21 | **New spec. Single canonical `MLDashboard` (§2), REST+SSE+WS (§4–§6), panels (§7), CLI (§8), auth (§10), security (§11), industry parity (§13), Tier 2 + Tier 3 tests (§14).** Closes Round-1 F-DASHBOARD-DB-MISMATCH (CRIT), DL-8, Industry #4 / #14 / #15 / #20. |
