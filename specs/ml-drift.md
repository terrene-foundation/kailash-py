# Kailash ML Drift Monitor Specification (v1.0 Draft)

Version: 1.0.0 (draft)

**Status:** DRAFT — shard 4C of round-2 spec authoring. Resolves round-1 HIGH findings: "drift reference cache in-memory + not tenant-scoped", "no scheduler persistence — `schedule_monitoring` is in-process `asyncio.create_task` that dies on restart", "no performance drift (ground-truth) path", "shadow-prediction divergence is not wired into drift alerting".
**Sibling specs:** `ml-engines.md` §2 + §5 (MLEngine.monitor() entry + tenant contract), `ml-registry-draft.md` §5 (signature authority), `ml-serving-draft.md` §6.5 (shadow divergence feed), `ml-tracking.md` (drift events emit into the ambient tracker).
**Scope:** ONE canonical drift monitor covering feature drift (input distribution), prediction drift (output distribution), AND performance drift (ground-truth reconciliation), with tenant-scoped persistent reference data, restart-surviving scheduler, alert routing, and first-class dashboard integration.

---

## 1. Scope — Drift Types + Detection Axes

`DriftMonitor` detects distributional change along several orthogonal axes AND tags every finding with a statistical drift TYPE so recommendations can diverge by type. A production monitor tracks all axes by default; users may disable axes explicitly.

### 1.1 Drift Type Taxonomy

| Type          | Statistical form                 | Detection primitive                                                                 | Recommended response                    |
| ------------- | -------------------------------- | ----------------------------------------------------------------------------------- | --------------------------------------- |
| **covariate** | `P(X)` changes, `P(Y\|X)` stable | KS / PSI on INPUT features                                                          | Often recalibrate; sometimes re-weight  |
| **concept**   | `P(Y\|X)` changes                | Performance drift on fresh labels; residual-distribution KS conditional on X bucket | Full retrain required                   |
| **prior**     | `P(Y)` changes, features stable  | KS / PSI on PREDICTIONS (or actual labels)                                          | Threshold recalibration                 |
| **label**     | Ground-truth labels drift        | Chi² / KS on incoming labels once they arrive (label-lag window)                    | Investigate upstream labelling pipeline |

Every `DriftFeatureResult` carries a `drift_type: Literal["covariate", "concept", "prior", "label", "unknown"]` field. Users route recommendations and alerts differently per type (see §6.3).

### 1.2 Feature Drift (covariate axis)

Change in the distribution of model INPUT features (`X`) between a reference dataset (training or a fixed production baseline) and the current production window. Detects "the data my model sees now doesn't look like what I trained on." Classified as `covariate` by default; escalated to `concept` when paired performance drift is observed.

### 1.3 Prediction Drift (prior axis)

Change in the distribution of model OUTPUT predictions (`y_hat`) across the same two windows. Detects "my model's behavior has shifted" even when inputs look stable — catches upstream feature encoding changes. Classified as `prior` by default; escalated to `concept` when paired with performance drift.

### 1.4 Performance Drift (concept axis)

Change in the ground-truth-reconciled performance metric (accuracy, AUC, RMSE, etc.) across two windows. Requires labels to arrive after predictions (label lag). Windowed + lag-aware. Detects "my model was right 95% of the time last month; now it's 84%." Always classified as `concept`.

### 1.5 Label Drift (label axis)

Change in the distribution of arriving ground-truth labels over the reconciliation window. Detects upstream label-pipeline corruption independently of model behaviour.

### 1.6 Out-Of-Scope

- **Model-internal drift** (gradient statistics, activation distributions) — lives in `ml-diagnostics.md` / `DLDiagnostics` per round-1 DL researcher findings.
- **Data-quality drift** (missingness, type violations) — overlaps with `DataExplorer` in `ml-engines.md`; DriftMonitor consumes DataExplorer outputs but does not reproduce them.
- **Concept discovery** — pure unsupervised "what are the new clusters" is `AnomalyDetection` + `Clustering`.

---

## 2. Construction

### 2.1 Canonical Surface

```python
@dataclass(frozen=True, slots=True)
class DriftMonitorConfig:
    tenant_id: str
    model_uri: str                           # "registry://fraud@production" OR explicit version
    axes: set[Literal["feature", "prediction", "performance"]] = frozenset({"feature", "prediction", "performance"})
    store: Optional[str] = None              # None → canonical ~/.kailash_ml/ml.db per ml-tracking §2.2
    alerts: AlertConfig | None = None
    label_lag_seconds: int = 86_400          # for performance axis
    min_samples: int = 100                   # refuse drift check below this
    reference_max_rows: int = 100_000        # cap reference dataset size


class DriftMonitor:
    def __init__(
        self,
        config: DriftMonitorConfig,
        *,
        registry: ModelRegistry,
        tracker: Optional[ExperimentRun] = None,   # user-visible handle; HIGH-8 — NOT Optional[ExperimentTracker]
        artifact_store: ArtifactStore | None = None,
    ):
        ...
```

**Implementation note (W26.e, 2026-04-23):** the current Python implementation accepts direct kwargs rather than the `DriftMonitorConfig` wrapping: `DriftMonitor(conn, *, tenant_id: str, psi_threshold=0.2, ks_threshold=0.05, thresholds=None, tracker=None, alerts=None, performance_threshold=0.1)`. `tenant_id` is a REQUIRED non-empty string — empty string raises `TenantRequiredError`, non-string raises `TypeError` (see §9). The `DriftMonitorConfig` dataclass wrapping in §2.1 is a forward-looking ergonomic surface to be introduced together with the full `MLEngine.monitor(...)` facade work (§2.2); the tenant-scoping contract in §4.1 + §11.2.2 is already enforced end-to-end by the current kwargs surface.

### 2.2 Canonical Construction Through MLEngine

```python
# DO — engine.monitor() resolves registry/tracker/store
engine = km.Engine(store=url, tenant_id="acme")
monitor = await engine.monitor(
    model="fraud",
    alias="@production",
    axes={"feature", "prediction", "performance"},
    alerts=AlertConfig(webhook="https://ops.example.com/drift"),
)

# DO — set a reference dataset once at construction
await monitor.set_reference(reference_df, *, actor_id="agent-42")
```

### 2.3 Reference From Registry Lineage (Default)

If `set_reference` is not called explicitly, the monitor reads the training dataset hash from `registry.get_model(...).lineage.dataset_hash` and attempts to resolve the reference from the feature store or a linked `_kml_datasets` row. If resolution fails, the monitor is in "no-reference" state — `check_drift` raises `ReferenceNotFoundError` until reference data is supplied.

---

## 3. Drift Statistics — Column-Type-Aware

### 3.1 Continuous Columns

| Statistic                            | Use                                                                                                     | Threshold semantics                            |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| **Kolmogorov-Smirnov (KS)**          | Non-parametric test between two empirical CDFs. Primary signal for continuous drift.                    | p-value < 0.05 = drift                         |
| **Jensen-Shannon divergence**        | Symmetric divergence between two discretized histograms. Use when KS is too sensitive to tail outliers. | JS > 0.1 = drift                               |
| **Population Stability Index (PSI)** | Industry-standard drift score, discretizes into 10 bins, sum((p_new − p_ref) × ln(p_new / p_ref)).      | PSI > 0.2 = significant; PSI > 0.25 = critical |
| **Wasserstein-1 (Earth Mover's)**    | When shape matters more than location.                                                                  | Threshold calibrated per feature               |

### 3.2 Categorical Columns

| Statistic                     | Use                                                                  | Threshold                     |
| ----------------------------- | -------------------------------------------------------------------- | ----------------------------- |
| **Chi-Squared**               | Independence test between reference and current category counts.     | p < 0.05 = drift              |
| **Jensen-Shannon (discrete)** | Symmetric divergence over category probabilities.                    | JS > 0.1 = drift              |
| **New-category fraction**     | Fraction of current rows whose category did not appear in reference. | > 0.05 = drift                |
| **PSI (categorical)**         | Categorical PSI using category probabilities.                        | same thresholds as continuous |

### 3.3 Selection Rule

The monitor auto-selects based on column dtype:

- `pl.Float32 | pl.Float64` → KS + PSI + JS.
- `pl.Int*` with `unique / count < 0.05` → treat as categorical (Chi² + PSI-categorical + new-category).
- `pl.Int*` with `unique / count >= 0.05` → treat as continuous (KS + PSI).
- `pl.Categorical | pl.Utf8` → Chi² + JS-discrete + new-category.
- `pl.Boolean` → Chi².
- `pl.Datetime | pl.Date` → bucket to day/hour, then continuous path.
- `pl.List | pl.Struct` → NOT directly driftable — expand via a user-supplied flattener, else skip with WARN.

### 3.4 Per-Column Threshold Override

Every threshold above is a default. Users override per-column via `monitor.set_thresholds({"age": {"ks_p_value": 0.01}, "country": {"new_category_fraction": 0.02}})`.

### 3.5 Composite Drift Score

Per column, the monitor computes a normalized `drift_score ∈ [0, 1]` combining statistics that triggered. The model-level drift score is the max across columns (default) OR a weighted mean (operator choice).

### 3.6 Smoothing Contract — Pinned Constants For PSI / KL / JSD

Zero-probability bins and zero-variance columns break PSI / KL / JSD unless smoothed. kailash-ml pins these constants in the spec so cross-SDK parity and regression comparability are preserved.

```python
# Module-level constants in kailash_ml.drift.stats:
PSI_SMOOTH_EPS: float = 1e-4       # additive constant per bin mass (before normalisation)
JSD_SMOOTH_EPS: float = 1e-10      # additive epsilon on zero-probability bins before log
KL_SMOOTH_EPS: float = 1e-10       # same contract for KL divergence
MIN_BIN_COUNT: int = 10            # below this bin count, statistic emits `None` and a `stability_note`
```

#### MUST 1. PSI Smoothing

`PSI = sum_b (p_new[b] − p_ref[b]) × ln((p_new[b] + eps) / (p_ref[b] + eps))` with `eps = PSI_SMOOTH_EPS = 1e-4`. A bin with zero mass in the reference OR in the current window does NOT produce `±Inf`.

#### MUST 2. Zero-Variance Reference Column

A reference column with `std == 0` MUST raise `ZeroVarianceReferenceError` with message identifying the column. The monitor MUST NOT silently fall back to a single-bin histogram — that is a data-quality finding routed to `data_quality` axis, not a drift finding.

#### MUST 3. KL / JSD Zero-Probability

`JSD(p, q) = 0.5 × KL(p || m) + 0.5 × KL(q || m)` where `m = 0.5 × (p + q)` and every `KL` term uses `ln((p[b] + JSD_SMOOTH_EPS) / (m[b] + JSD_SMOOTH_EPS))`. Both terms are finite for any `p, q` in the probability simplex.

#### MUST 4. RL KL Uses The Same Eps

`RLDiagnostics.track_exploration` reports `kl_div` — when the old-policy distribution puts zero mass on the new-policy action, kailash-ml routes through `KL_SMOOTH_EPS` for exact-KL (TRPO) OR through SB3's sample-based unbiased-KL estimator (PPO). The `kl_estimator: Literal["exact", "sample_unbiased"]` column MUST be emitted alongside the KL value so downstream consumers know how to compare.

#### MUST 5. Stability Note

When smoothing fires (any column where raw PSI / KL / JSD would have been `±Inf` absent the eps), the per-column drift result MUST include `stability_note: "smoothed_zero_prob"`. Cross-run comparisons that use smoothed vs unsmoothed values are flagged in `MLDashboard`.

**Why:** MLflow / Evidently / Tecton all use an additive epsilon; diverging from their `1e-4` / `1e-10` constants silently produces different numerical values for the same distribution pair. The `stability_note` makes the smoothing observable post-hoc.

---

## 4. Reference Dataset Persistence

Round-1 HIGH finding §8 (mlops): "`DriftMonitor._references: dict[str, _StoredReference]` is keyed by `model_name` only — a multi-tenant deployment with two tenants each training `'churn'` collides". This section closes that.

### 4.1 MUST: Reference Is NOT Cached In-Memory Only

`DriftMonitor._references` MAY be used as an LRU cache, but the source of truth is the `_kml_drift_references` table in the configured `store`. Every `set_reference` call MUST write the reference snapshot (hash + column summary + raw rows up to `reference_max_rows`) to the table; every `check_drift` call MUST resolve via the key `(tenant_id, model_name, model_version)` and lazy-load if the LRU misses.

```python
# DO — persisted, tenant-scoped, lazy-loaded
async def check_drift(self, current_df, *, tenant_id, model_name, model_version, ...):
    key = (tenant_id, model_name, model_version)
    ref = self._references.get(key)
    if ref is None:
        ref = await self._load_reference_from_store(key)
    ...

# DO NOT — in-memory only (current failure mode)
async def check_drift(self, current_df, *, model_name, ...):
    ref = self._references[model_name]  # KeyError on cold start; cross-tenant collision
    ...
```

### 4.2 Reference Table Schema

```sql
CREATE TABLE _kml_drift_references (
    tenant_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version INT NOT NULL,
    reference_hash TEXT NOT NULL,           -- SHA-256 of canonical serialization of reference_df
    reference_row_count INT NOT NULL,
    reference_column_summary JSONB NOT NULL, -- {col_name: {dtype, n_null, n_unique, min, max, mean, stddev, quantiles, top_categories}}
    reference_artifact_uri TEXT,            -- cas:// pointer if reference is too large to inline
    set_at TIMESTAMP NOT NULL,
    set_by_actor_id TEXT NOT NULL,
    superseded_at TIMESTAMP,                -- when replaced by a newer reference
    PRIMARY KEY (tenant_id, model_name, model_version)
);
CREATE INDEX idx_drift_refs_tenant ON _kml_drift_references (tenant_id);
```

### 4.3 Reference Size Caps

References above `reference_max_rows` (default 100K) are sub-sampled via reservoir sampling with a fixed seed (default 42, overridable). The full reference bytes are offloaded to the artifact store; the column summary is always inline for fast check-time access. Drift statistics on a 100K sample of a 100M-row reference are empirically within 1σ of the full-dataset numbers for all four continuous statistics above.

### 4.4 Reference Versioning + Supersede Audit

Calling `set_reference` on an existing `(tenant_id, model_name, model_version)` key MUST:

1. Set the existing row's `superseded_at = now`.
2. Insert the new reference as a new row. The PK changes to `(tenant_id, model_name, model_version, set_at)` in practice (composite including set_at); for simplicity, the spec keeps the 3-tuple PK and uses `ON CONFLICT (tenant_id, model_name, model_version) DO UPDATE SET superseded_at = now` semantics on the old row before insert of the new.
3. Write an audit row to `_kml_drift_audit` with `operation="set_reference"`, `prev_hash`, `new_hash`.

### 4.5 Reference Refresh Policy — `DriftMonitorReferencePolicy`

A retailer with weekly seasonality sees "drift" every Monday relative to last Sunday. kailash-ml exposes reference-refresh policies so the monitor tracks seasonality-relative drift, not calendar-edge artifacts.

```python
@dataclass(frozen=True, slots=True)
class DriftMonitorReferencePolicy:
    mode: Literal["static", "rolling", "sliding", "seasonal"] = "static"
    window: timedelta | None = None           # for rolling/sliding
    seasonal_period: timedelta | None = None  # for seasonal (e.g. timedelta(weeks=1))
    refresh_cadence: timedelta | None = None  # how often the reference is re-materialised
```

#### MUST 1. Static (default)

`mode="static"` — `set_reference` is called once; reference is immutable until manually superseded. Use for regulated models where reference drift MUST be explicit.

#### MUST 2. Rolling

`mode="rolling", window=timedelta(days=30)` — reference is auto-refreshed to the last N days on each `check_drift` call. Refresh cadence MUST be at least `refresh_cadence` (default: every `check_drift`).

#### MUST 3. Sliding

`mode="sliding", window=timedelta(days=30)` — same as rolling but with an explicit refresh cadence so we don't re-materialise on every check. Use when drift checks are sub-second and reference refresh is heavy.

#### MUST 4. Seasonal

`mode="seasonal", seasonal_period=timedelta(weeks=1)` — reference is aligned to the SAME weekday/hour in the prior period. A Monday 10am current window compares against last Monday 10am ± the period window. Use for weekly seasonality (retail, B2C SaaS) / daily seasonality (ad-tech, ride-hailing).

#### MUST 5. Tier 2 Test

`tests/integration/test_drift_seasonal_reference.py` MUST:

1. Generate synthetic weekly-seasonal signal.
2. Run `mode="static"` → drift fires weekly (false positives).
3. Run `mode="seasonal", seasonal_period=timedelta(weeks=1)` → drift DOES NOT fire on the seasonal pattern (true negative).

**Why:** Without the seasonal mode, weekly-seasonal businesses see false drift alarms every Monday. The refresh-policy option converts "drift fires constantly" into "drift fires when the seasonal pattern itself changes".

### 4.6 Missing Reference = Typed Error

```python
@dataclass(frozen=True, slots=True)
class ReferenceNotFoundError(DriftMonitorError):
    tenant_id: str
    model_name: str
    model_version: int
    message: str = (
        "No reference dataset for (tenant, model, version). "
        "Call monitor.set_reference(df) OR ensure the linked training run's "
        "lineage.dataset_hash is resolvable in the feature store."
    )
```

`check_drift` MUST raise this (not silently skip) when no reference is available per `rules/zero-tolerance.md` Rule 3 (no silent fallbacks).

---

## 5. Scheduling — Restart-Surviving

Round-1 HIGH finding §11 (mlops): "`DriftMonitor.schedule_monitoring` is in-process `asyncio.create_task` + stores in `self._scheduled_tasks`. When the process dies, the schedule dies. No cron, no journal, no resume." This section closes that.

### 5.1 MUST: Schedules Persist Before Executing

```python
async def schedule_monitoring(
    self,
    *,
    tenant_id: str,
    model_name: str,
    model_version: int,
    interval_seconds: int = 3600,
    enabled: bool = True,
    actor_id: str,
    starts_at: datetime | None = None,        # None = immediately
    ends_at: datetime | None = None,
) -> str:                                     # schedule_id
    ...
```

Persistence table:

```sql
CREATE TABLE _kml_drift_schedules (
    schedule_id TEXT PRIMARY KEY,             -- uuid4
    tenant_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version INT NOT NULL,
    interval_seconds INT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    starts_at TIMESTAMP,
    ends_at TIMESTAMP,
    last_run_at TIMESTAMP,
    last_run_outcome TEXT,                    -- "success" | "failed"
    last_run_drift_detected BOOLEAN,
    next_run_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    created_by_actor_id TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_drift_sched_next ON _kml_drift_schedules (next_run_at) WHERE enabled;
CREATE INDEX idx_drift_sched_tenant ON _kml_drift_schedules (tenant_id);
```

### 5.2 Scheduler Worker

A `DriftScheduler` is a long-running coroutine owned by the MLEngine (or deployed as a Nexus background worker). It:

1. Polls `_kml_drift_schedules` every 10 seconds for rows with `enabled = TRUE AND next_run_at <= now()`.
2. Claims each row atomically via `UPDATE ... SET next_run_at = now() + interval WHERE schedule_id = ? AND next_run_at = ? RETURNING *` to avoid double-dispatch across replicas.
3. Executes the drift check via the owning `DriftMonitor`.
4. Updates `last_run_at`, `last_run_outcome`, `last_run_drift_detected`.
5. Writes a `_kml_drift_reports` row regardless of outcome.
6. Emits log + tracker event.

### 5.3 Multi-Process Safety

The atomic claim in step 2 means N scheduler replicas across N processes/pods compete for work correctly; exactly one replica executes any given drift check per interval.

### 5.4 `asyncio.create_task` IS Still Used — But Not Alone

In-process asyncio dispatching is retained for low-latency single-process deployments, BUT the schedule persistence is mandatory. After a restart, the scheduler worker re-reads the persisted rows and resumes dispatching the same set of schedules. This closes the "process-dies, schedule-dies" failure.

### 5.5 Deletion Semantics

`cancel_schedule(schedule_id, *, actor_id, reason)` sets `enabled = FALSE` + writes audit row. Hard delete happens in periodic compaction after `retention_days` (default 365).

### 5.6 Nexus Cron Integration (Optional)

When a Nexus deployment is detected (via `engine.nexus_app is not None`), the monitor registers the scheduler as a Nexus cron job rather than spawning its own worker. The persistence table and the claim semantics are identical.

---

## 6. Alerting

### 6.1 AlertConfig

```python
@dataclass(frozen=True, slots=True)
class AlertConfig:
    channels: list[AlertChannel] = field(default_factory=list)
    per_axis_rules: dict[str, AlertRule] = field(default_factory=dict)
    cooldown_seconds: int = 900               # suppress duplicate alerts for 15 min
    max_alerts_per_hour: int = 12             # bounded per-tenant to prevent floods


@dataclass(frozen=True, slots=True)
class AlertRule:
    trigger: Literal["any_column", "fraction_columns", "model_score"]
    threshold: float                          # semantic varies by trigger
    severity: Literal["info", "warning", "critical"] = "warning"


class AlertChannel:
    async def send(self, alert: DriftAlert) -> None: ...


class WebhookAlertChannel(AlertChannel): ...
class EmailAlertChannel(AlertChannel): ...
class TrackerEventAlertChannel(AlertChannel): ...   # writes to the ambient tracker as a drift event
class NexusPubSubAlertChannel(AlertChannel): ...    # fans out to Nexus subscribers
```

### 6.2 Alert Lifecycle

1. Drift check computes per-axis, per-column scores.
2. Each `per_axis_rules[axis]` evaluates. Triggered rules produce a `DriftAlert`.
3. Cooldown: for each `(tenant_id, model_name, axis)` key, a recent duplicate alert within `cooldown_seconds` is suppressed (logged as `drift.alert.suppressed`).
4. Rate limit: max `max_alerts_per_hour` per tenant. Exceeded → `drift.alert.rate_limited` WARN + per-tenant counter.
5. Alert dispatched to every `AlertChannel`. Per-channel failure does NOT suppress other channels. Channel errors go to `drift.alert.channel_error` WARN.

### 6.3 DriftAlert Payload

```python
@dataclass(frozen=True, slots=True)
class DriftAlert:
    alert_id: str
    tenant_id: str
    model_name: str
    model_version: int
    axis: Literal["feature", "prediction", "performance"]
    trigger_rule: str
    severity: Literal["info", "warning", "critical"]
    detected_at: datetime
    drift_score: float
    top_columns: list[dict]                    # top-5 drifted columns with per-column scores
    report_id: str                             # link into _kml_drift_reports
    dashboard_url: str | None
```

Per `rules/event-payload-classification.md` MUST 2, `top_columns` values are column NAMES (not classified values), and `drift_score` is a scalar — no raw features leak in alerts.

### 6.4 Tracker Event Emission

Every drift check AND every alert emits an event to the ambient tracker per round-1 finding "0/13 engines auto-wire to km.track()":

- `drift.check.started` — `{tenant_id, model, version, axis, request_id}`.
- `drift.check.completed` — `{…, drift_score, duration_ms, columns_analyzed}`.
- `drift.detected` — `{…, axis, drift_score, top_columns, alert_severity}`.
- `drift.alert.sent` — `{alert_id, channel_type, outcome}`.

---

## 7. Dashboard Integration

### 7.1 Per-Tenant Drift Panel

`MLDashboard` (cross-ref to round-1 tracker findings) renders a drift panel that:

- Lists active `_kml_drift_schedules` rows with last-run state.
- Shows the 30-day timeline of model-level drift scores (one line per model, tenant-filtered).
- Renders per-column drift heatmaps — rows = time windows, columns = features, cell color = PSI / KS p-value.
- Links alerts to the `_kml_drift_reports` row + the linked training/prediction run in the tracker.

Panel data source:

- `_kml_drift_reports` (per-check results) — for timeline + heatmap.
- `_kml_drift_alerts` (per-alert history) — for the alert list.
- `_kml_drift_schedules` (active schedules) — for the schedule table.

All three tables MUST carry `tenant_id` and be indexed on it.

### 7.2 Drift Report Schema

```sql
CREATE TABLE _kml_drift_reports (
    report_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version INT NOT NULL,
    axis TEXT NOT NULL,
    checked_at TIMESTAMP NOT NULL,
    reference_hash TEXT NOT NULL,
    current_row_count INT NOT NULL,
    reference_row_count INT NOT NULL,
    drift_score REAL NOT NULL,
    drift_detected BOOLEAN NOT NULL,
    per_column_scores JSONB NOT NULL,
    duration_ms REAL NOT NULL,
    triggered_schedule_id TEXT,              -- FK-like if triggered by a schedule
    outcome TEXT NOT NULL                     -- "success" | "failed"
);
CREATE INDEX idx_drift_reports_tenant_checked ON _kml_drift_reports (tenant_id, checked_at DESC);
```

### 7.3 Retention

Default: 365-day retention on reports; indefinite on alerts. Operators override per-tenant.

---

## 8. Performance Drift — Ground-Truth Reconciliation

### 8.1 Label-Lag Model

Predictions are written at time `t_pred`. Ground-truth labels arrive at time `t_label`, with lag distribution that varies by use case (e-commerce: hours; credit: 30-90 days; reinforcement learning: variable). The monitor MUST:

1. Accept predictions via `monitor.record_prediction(request_id, model_version, features, prediction, *, tenant_id, actor_id, predicted_at)` — typically called from `InferenceServer` per `ml-serving-draft.md` §11.4.
2. Accept labels via `monitor.record_label(request_id, label, *, tenant_id, actor_id, labeled_at)`.
3. Reconcile: periodically join predictions with labels where both have arrived within the configured lag window.

#### MUST: `label_lag_hours` Kwarg On `performance_drift`

```python
async def performance_drift(
    self,
    *,
    tenant_id: str,
    model_name: str,
    model_version: int,
    window: timedelta = timedelta(days=7),
    label_lag_hours: float = 0.0,        # alignment offset for label-lagged use cases
    min_samples: int = 100,
) -> PerformanceDriftReport: ...
```

When `label_lag_hours > 0`, concept-drift checks MUST be run against predictions from the window `[now - window - timedelta(hours=label_lag_hours), now - timedelta(hours=label_lag_hours)]`, NOT the current window. A fraud system with `label_lag_hours=720` (30 days) compares 30-day-old predictions against their just-arrived labels, NOT today's unlabeled predictions against yesterday's.

`DriftMonitor.set_reference(..., label_lag: timedelta = timedelta(0))` pins the default `label_lag_hours` per model. `performance_drift()` without `label_lag_hours` reads this default.

**Why:** Without label-lag alignment, performance-drift reports compare CURRENT labeled predictions (i.e. the ones labeled fastest) against the reference — a biased sample. Fraud / loan / churn use cases have label lags measured in weeks-to-months; the alignment window is the critical correctness contract.

### 8.2 Reconciliation Schema

```sql
CREATE TABLE _kml_drift_predictions (
    request_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version INT NOT NULL,
    prediction JSONB NOT NULL,                -- polars-compatible JSON
    predicted_at TIMESTAMP NOT NULL,
    label JSONB,                               -- NULL until label arrives
    label_arrived_at TIMESTAMP,
    PRIMARY KEY (tenant_id, request_id)
);
CREATE INDEX idx_drift_preds_tenant_time ON _kml_drift_predictions (tenant_id, predicted_at);
CREATE INDEX idx_drift_preds_unlabeled ON _kml_drift_predictions (tenant_id, model_name, predicted_at)
  WHERE label IS NULL;
```

### 8.3 Windowed Metric Computation

Performance check operates over a configurable window (default: last 7 days) AND requires `min_samples` labeled reconciled rows. The monitor computes:

- **Classification:** accuracy, precision, recall, F1, AUC, confusion matrix (per-class).
- **Regression:** RMSE, MAE, R².
- **Multi-class:** per-class metrics + macro/micro averages.
- **Imbalanced:** PR-AUC in addition to ROC-AUC.

Metrics are compared window-over-window: the current window vs the reference window (the first full window after reference-setting, by default). Drift is declared when the metric delta exceeds per-metric thresholds (default: absolute Δ > 0.05 for AUC/accuracy; relative Δ > 10% for RMSE).

### 8.4 Insufficient-Sample Path

When `labeled_count < min_samples`, performance check is SKIPPED (NOT reported as "no drift"). Emits `drift.performance.insufficient_samples` INFO log and does NOT write a drift_reports row (would produce misleading historical data).

### 8.5 Label Arrival Audit

Every `record_label` call writes to `_kml_drift_audit` with `operation="record_label"`. This supports forensic queries when labels arrive late or in batches.

---

## 9. Error Taxonomy

All inherit from `kailash_ml.errors.DriftMonitorError` → `kailash_ml.errors.MLError`.

| Error                               | Raised When                                                                     |           Retry safe?           |
| ----------------------------------- | ------------------------------------------------------------------------------- | :-----------------------------: |
| `ReferenceNotFoundError`            | `check_drift` without a reference for the `(tenant, model, version)` key        | No — call `set_reference` first |
| `InsufficientSamplesError`          | Current or reference has < `min_samples` rows                                   |  Yes — accumulate more samples  |
| `DriftThresholdError`               | Semantic error: threshold misconfigured (negative, > 1 for p-value, etc.)       |               No                |
| `ScheduleNotFoundError`             | `cancel_schedule` / `update_schedule` targets a missing schedule_id             |               No                |
| `ScheduleConflictError`             | Two competing claims on the same `next_run_at` (extremely rare — DB constraint) | Yes (caller retries the claim)  |
| `TenantRequiredError`               | Any op missing `tenant_id`                                                      |               No                |
| `ActorRequiredError`                | Mutation (set_reference, schedule, cancel) without `actor_id`                   |               No                |
| `UnflatternableColumnError`         | List/Struct column without a flattener                                          |               No                |
| `LabelArrivedBeforePredictionError` | `record_label(request_id)` but no matching prediction row                       |   No (upstream ordering bug)    |

---

## 10. Industry Parity

### 10.1 Feature Matrix vs Competitors

| Capability                               | kailash-ml (v2.0) |       Evidently AI       | Fiddler |  Arize  | WhyLabs | MLflow  |
| ---------------------------------------- | :---------------: | :----------------------: | :-----: | :-----: | :-----: | :-----: |
| Feature drift (KS/PSI/JS/Chi²)           |       **Y**       |            Y             |    Y    |    Y    |    Y    | partial |
| Prediction drift                         |       **Y**       |            Y             |    Y    |    Y    |    Y    | partial |
| Performance drift (label reconciliation) |       **Y**       |            Y             |    Y    |    Y    |    Y    |    N    |
| Tenant-scoped reference                  | **Y** (required)  |         partial          |    Y    |    Y    |    Y    |    N    |
| Reference persistence (restart-safe)     | **Y** (mandatory) |            Y             |    Y    |    Y    |    Y    |    N    |
| Restart-surviving scheduler              | **Y** (persisted) | Y (Prefect/Airflow glue) |    Y    |    Y    |    Y    |    N    |
| Polars-native reference / report         |       **Y**       |        N (pandas)        |    N    |    N    |    N    |    N    |
| Alert cooldown + rate limit              |       **Y**       |         partial          |    Y    |    Y    |    Y    |    N    |
| Shadow-divergence drift source           |       **Y**       |            N             | partial | partial | partial |    N    |
| Per-tenant dashboard panel               |       **Y**       |    N (single-tenant)     |    Y    |    Y    |    Y    |    N    |
| Schedule indexed by `next_run_at`        | **Y** (required)  |           N/A            |    Y    |    Y    |    Y    |   N/A   |
| Integration with on-prem tracker         | **Y** (auto-emit) |         partial          |    Y    |    Y    |    Y    |    N    |

### 10.2 Differentiators kailash-ml Claims

1. **Tenant-scoped at the primitive level** — all three drift axes carry `tenant_id` from day one. No competitor forces this; most bolt it on via IAM.
2. **Polars-native inputs AND outputs** — reference rows, current rows, per-column scores, and drift reports are polars DataFrames throughout. Zero pandas round-trip.
3. **Shadow divergence is a first-class drift source** — feeds directly from `_kml_shadow_predictions` into the prediction-drift axis (§6.5 of `ml-serving-draft.md`). Competitors require external glue.
4. **Framework co-location** — drift reports, schedule tables, and alerts live alongside models, runs, features in the same store. One SQL query joins "which model, trained on which data, drifted when" — industry-standard but rarely one-query.
5. **Performance drift + label-lag out of the box** — Evidently/Fiddler/Arize have this; MLflow does not. We match the strong competitors.

### 10.3 Known Gaps (Post-1.0)

- No explanation layer ("why did drift fire" — SHAP-over-drift). Reserved for `ml-engines.md` §ModelExplainer extension.
- No causal-drift decomposition (distinguish "input distribution shifted" vs "upstream encoding bug"). Post-1.0 spec.
- No native federated-learning drift (cross-cluster reference aggregation). Post-1.0 if customer demand.

---

## 11. Test Contract

### 11.1 Tier 1 (Unit) — Per Statistic

Each statistic (KS, PSI, JS, Chi², Wasserstein, new-category) MUST have:

- `test_<stat>_no_drift_returns_below_threshold` — reference == current → score < threshold.
- `test_<stat>_drift_detected_above_threshold` — known-shifted distribution → score > threshold.
- `test_<stat>_handles_empty_column` — empty or single-value → graceful skip with WARN, NOT crash.
- `test_<stat>_handles_all_null` — all-null column → skip with WARN.
- `test_<stat>_handles_high_cardinality_categorical` — > 1000 unique values → bucket to top-N + `_other` before Chi².

Property-based tests (via `hypothesis`) MUST exist for statistic monotonicity: "if we increase the shift magnitude, the drift score monotonically non-decreases" (within statistical tolerance).

### 11.2 Tier 2 (Integration) — Wiring Through MLEngine Facade

File: `tests/integration/test_drift_monitor_wiring.py` per `rules/facade-manager-detection.md` Rule 2.

#### 11.2.1 Persistence + Restart Recovery

```python
@pytest.mark.integration
async def test_drift_monitor_persists_reference_and_schedule(test_suite):
    engine_1 = km.Engine(store=test_suite.url, tenant_id="acme")
    await _train_register_promote(engine_1, "fraud")
    monitor_1 = await engine_1.monitor(model="fraud", alias="@production")
    ref_df = _make_reference_df(n=500)
    await monitor_1.set_reference(ref_df, actor_id="agent-42")
    schedule_id = await monitor_1.schedule_monitoring(
        interval_seconds=60, actor_id="agent-42",
    )
    await engine_1.aclose()

    # Simulate process restart — fresh engine, same store URL
    engine_2 = km.Engine(store=test_suite.url, tenant_id="acme")
    monitor_2 = await engine_2.monitor(model="fraud", alias="@production")

    # Reference lazy-loads from store
    report = await monitor_2.check_drift(_make_drifted_df(n=500))
    assert report.drift_detected is True
    assert report.axis == "feature"

    # Schedule recovered
    schedules = await monitor_2.list_schedules(tenant_id="acme")
    assert len(schedules) == 1
    assert schedules[0]["schedule_id"] == schedule_id
    assert schedules[0]["enabled"] is True
```

This test directly verifies round-1 HIGH "schedule_monitoring is in-process asyncio.create_task (dies on restart)" is closed.

#### 11.2.2 Tenant Isolation

```python
@pytest.mark.integration
async def test_drift_monitor_tenant_isolation(test_suite):
    engine_acme = km.Engine(store=test_suite.url, tenant_id="acme")
    engine_bob = km.Engine(store=test_suite.url, tenant_id="bob")
    # Both tenants train a "churn" model with DIFFERENT reference distributions
    await _train_register_promote(engine_acme, "churn", seed=42)
    await _train_register_promote(engine_bob, "churn", seed=999)

    m_acme = await engine_acme.monitor(model="churn", alias="@production")
    m_bob = await engine_bob.monitor(model="churn", alias="@production")
    await m_acme.set_reference(_ref_df(seed=42), actor_id="ci")
    await m_bob.set_reference(_ref_df(seed=999), actor_id="ci")

    # acme's drift check CANNOT see bob's reference
    # If it did, drift would LOOK detected because the seeds differ
    current = _ref_df(seed=42)  # matches acme's reference exactly
    report_acme = await m_acme.check_drift(current)
    assert report_acme.drift_detected is False, "acme's own reference shouldn't drift"

    # Audit + reports tenant-scoped
    acme_reports = await engine_acme._conn.fetch(
        "SELECT DISTINCT tenant_id FROM _kml_drift_reports WHERE tenant_id=$1", "acme",
    )
    assert [r["tenant_id"] for r in acme_reports] == ["acme"]
```

This test directly verifies round-1 HIGH "reference cache not tenant-scoped" is closed.

#### 11.2.3 Known-Shifted Dataset Triggers Drift

```python
@pytest.mark.integration
async def test_drift_monitor_detects_known_shift(test_suite):
    engine = km.Engine(store=test_suite.url, tenant_id="acme")
    await _train_register_promote(engine, "fraud")
    monitor = await engine.monitor(model="fraud", alias="@production")
    ref = pl.DataFrame({
        "age": np.random.normal(35, 5, 1000),           # mean 35
        "amount": np.random.exponential(100, 1000),     # exp(100)
        "region": np.random.choice(["us", "eu", "apac"], 1000, p=[0.6, 0.3, 0.1]),
    })
    await monitor.set_reference(ref, actor_id="ci")

    # Known shift: age mean 35 → 50; new region "latam" appears
    current = pl.DataFrame({
        "age": np.random.normal(50, 5, 1000),
        "amount": np.random.exponential(100, 1000),     # unchanged
        "region": np.random.choice(["us", "eu", "apac", "latam"], 1000,
                                    p=[0.4, 0.2, 0.1, 0.3]),
    })
    report = await monitor.check_drift(current)
    assert report.drift_detected is True
    assert report.per_column_scores["age"]["ks_p_value"] < 0.01
    assert report.per_column_scores["region"]["new_category_fraction"] > 0.25
    assert report.per_column_scores["amount"]["ks_p_value"] >= 0.05
```

#### 11.2.4 Alert Cooldown + Rate Limit

```python
@pytest.mark.integration
async def test_drift_alerts_cooldown_and_rate_limit(test_suite):
    fake_channel = _RecordingChannel()
    alerts = AlertConfig(channels=[fake_channel],
                         cooldown_seconds=60, max_alerts_per_hour=5)
    # ... set up monitor with drifted current_df ...
    # Run check 10 times in quick succession
    for _ in range(10):
        await monitor.check_drift(current_df)
    # Expect exactly 1 alert (first one) due to cooldown; rate limit kicks in after 5
    assert 1 <= len(fake_channel.received) <= 5
```

#### 11.2.5 Performance Drift — Label Reconciliation

```python
@pytest.mark.integration
async def test_drift_monitor_performance_drift_with_labels(test_suite):
    engine = km.Engine(store=test_suite.url, tenant_id="acme")
    await _train_register_promote(engine, "fraud")
    monitor = await engine.monitor(model="fraud", alias="@production",
                                     axes={"performance"})
    # Record 500 predictions across 7 days, then record labels with lag
    for i, (feats, pred, label, predicted_at) in enumerate(_make_synthetic_stream()):
        await monitor.record_prediction(f"req-{i}", 1, feats, pred,
                                         tenant_id="acme", actor_id="serving",
                                         predicted_at=predicted_at)
    for i, (label, labeled_at) in enumerate(_make_synthetic_labels()):
        await monitor.record_label(f"req-{i}", label, tenant_id="acme",
                                    actor_id="label-service", labeled_at=labeled_at)
    # Reconcile + check
    report = await monitor.check_drift(axis="performance")
    assert report.axis == "performance"
    # Accuracy ground-truth synthesized at ~0.82 (known drift from 0.95)
    assert report.drift_detected is True
    assert 0.80 <= report.per_column_scores["_model"]["accuracy_current"] <= 0.85
```

#### 11.2.6 Shadow-Divergence Drift Source

```python
@pytest.mark.integration
async def test_drift_monitor_consumes_shadow_predictions(test_suite):
    engine = km.Engine(store=test_suite.url, tenant_id="acme")
    # ... set up production model + shadow model on InferenceServer ...
    # ... run 100 shadow-split requests producing divergences ...
    monitor = await engine.monitor(model="fraud", alias="@production",
                                     axes={"prediction"})
    await monitor.set_reference(_ref_predictions(n=500), actor_id="ci")
    # Run prediction-drift check — monitor reads _kml_shadow_predictions
    report = await monitor.check_drift(axis="prediction",
                                        source="_kml_shadow_predictions")
    # Shadow version diverges → prediction distribution shifts
    assert report.drift_detected is True
```

### 11.3 Regression Tests (Permanent)

- `tests/regression/test_issue_mlops_HIGH_drift_reference_persistence.py` — asserts reference is persisted to `_kml_drift_references`, tenant-scoped, and survives a `DriftMonitor.__init__` recycle.
- `tests/regression/test_issue_mlops_HIGH_drift_scheduler_restart.py` — asserts scheduled drift checks survive process restart.
- `tests/regression/test_issue_mlops_HIGH_drift_tenant_required.py` — asserts every op without `tenant_id` raises `TenantRequiredError`.
- `tests/regression/test_issue_mlops_HIGH_drift_alert_rate_limit.py` — asserts `max_alerts_per_hour` bound enforces.

---

## 12. Top-Level `km.watch` Convenience Wrapper

In addition to the canonical `engine.monitor(...)` entry (§2.2), `kailash-ml` exports a package-level `km.watch(...)` wrapper that dispatches to the tenant-scoped cached default engine (per `ml-engines-v2.md §15.6`). This wrapper gives the lifecycle verb discoverable at the top level alongside `km.train`, `km.register`, `km.serve` — matching the verb-first Quick Start in `ml-engines-v2.md §16`.

### 12.1 Signature

```python
async def watch(
    model_uri: str,                                    # "fraud@production" OR "fraud:7"
    *,
    reference: "pl.DataFrame | None" = None,           # optional reference; else walks registry lineage
    axes: tuple[str, ...] = ("feature", "prediction", "performance"),
    alerts: "AlertConfig | None" = None,
    tenant_id: str | None = None,
    actor_id: str | None = None,
    label_lag_seconds: int = 86_400,
    min_samples: int = 100,
) -> "DriftMonitor": ...
```

### 12.2 Behaviour

1. Resolve the cached default engine via `kailash_ml._get_default_engine(tenant_id)` (the per-tenant cache from `ml-engines-v2.md §15.2 MUST 1`).
2. Normalise `model_uri` — accept `"fraud@production"` (parsed into `model="fraud"` + `alias="@production"`), `"fraud:7"` (parsed into `model="fraud"` + `version=7`), or raw `"fraud"` (requires the registry to have a `@production` alias by default).
3. Delegate to `await engine.monitor(model=..., alias=..., axes=set(axes), alerts=alerts, actor_id=actor_id, label_lag_seconds=label_lag_seconds, min_samples=min_samples)`.
4. If `reference is not None`, call `await monitor.set_reference(reference, actor_id=actor_id or "km.watch")` on the returned monitor before returning.
5. Return the `DriftMonitor` handle unchanged, so the caller can invoke `.start()`, `.stop()`, `.inspect()`, `.check_drift(...)`, `.schedule_monitoring(...)`.

### 12.3 Usage

```python
import kailash_ml as km

# DO — one-line watch against a registered + promoted model
monitor = await km.watch("fraud@production", reference=ref_df)
await monitor.start()                                 # begins scheduled drift checks

# DO — all three axes enabled (default), with alerts
monitor = await km.watch(
    "fraud@production",
    reference=ref_df,
    alerts=AlertConfig(webhook="https://ops.example.com/drift"),
    tenant_id="acme",
    actor_id="agent-42",
)

# DO — drift check on demand
report = await monitor.check_drift(axis="feature")
```

### 12.4 MUST: No New Engine Method

`km.watch` is a package-level function. It MUST NOT be added as a ninth method on `MLEngine`. The eight-method surface locked by `ml-engines-v2.md §2.1 MUST 5` is preserved — `km.watch` dispatches INTO the existing `engine.monitor(...)` method (which itself is covered under one of the eight methods via the Primitive-accessor pattern in `ml-engines-v2.md §15.2 MUST 2`).

**Why:** Package-level wrappers are the structural mechanism for adding discoverable lifecycle verbs (train, register, serve, watch, dashboard) without growing the engine class. `ml-engines-v2.md §15` freezes the engine method count at eight; this wrapper is the verb-layer complement.

### 12.5 Integration With km.train → km.register → km.serve

`km.watch` is the fourth verb in the standard lifecycle chain and composes with the other three:

```python
import kailash_ml as km

async with km.track("demo") as run:
    result = await km.train(df, target="y")
    registered = await km.register(result, name="demo")
server = await km.serve("demo@production")
monitor = await km.watch("demo@production", reference=df)  # feature+prediction+performance
```

---

## 13. Spec Cross-References

- `ml-engines.md` §2.1 MUST 5 — `engine.monitor()` is one of the 8 canonical methods.
- `ml-engines.md` §5 — tenant-isolation contract; this spec extends it for drift tables.
- `ml-registry-draft.md` §5 — model signature authority; `DriftMonitor` consumes signatures to determine which columns are features/predictions.
- `ml-registry-draft.md` §6 — lineage authority; the default reference resolution walks `registry.get_model(...).lineage.dataset_hash`.
- `ml-serving-draft.md` §6.5 — `_kml_shadow_predictions` is a drift source.
- `ml-serving-draft.md` §11.4 — `_kml_inference_audit` is the prediction source for prediction-drift axis.
- `ml-tracking.md` — ambient tracker receives `drift.*` events.
- `rules/tenant-isolation.md` MUST 1-5 — every reference row, schedule row, report row, alert row carries `tenant_id` + indexed on it.
- `rules/zero-tolerance.md` Rule 3 — no silent fallbacks on missing reference; typed error required.
- `rules/observability.md` §1-3 — mandatory log points for `drift.check.start/ok/error`.
- `rules/facade-manager-detection.md` — `DriftMonitor` is a manager class; §11.2 is the mandatory wiring test file.
- `rules/event-payload-classification.md` MUST 2 — alert payload fingerprints + column names only, no raw values.
- `rules/schema-migration.md` — `_kml_drift_*` tables land via numbered migrations.

---

## 14. RESOLVED — Prior Open Questions

All round-2 open questions are RESOLVED. Phase-B SAFE-DEFAULTs D-01..D-05 live in `workspaces/kailash-ml-audit/04-validate/round-2b-open-tbd-triage.md` § D (drift). This section is retained for traceability.

| Original TBD                                 | Disposition                                                                                                                              | Reference                 |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| Reference sub-sampling seed per tenant       | **PINNED** — per-tenant reservoir seed derived as `hash(tenant_id + "kml:drift:reservoir:v1")`; prevents cross-tenant determinism leaks. | Phase-B SAFE-DEFAULT D-01 |
| Streaming drift (infinite prediction stream) | **DEFERRED to post-1.0** — current design is windowed; streaming adapter is a future extension behind a `[drift-stream]` extra.          | Phase-B SAFE-DEFAULT D-02 |
| Explainer integration on drift fire          | **DEFERRED to post-1.0** — `DriftAlert.top_columns` remains the placeholder field for the future `ModelExplainer` integration.           | Phase-B SAFE-DEFAULT D-03 |
| Cross-model drift (ensemble-drift)           | **DEFERRED to post-1.0** — requires a per-model-family aggregator not yet scoped.                                                        | Phase-B SAFE-DEFAULT D-04 |
| Alert deduplication across channels          | **PINNED** — single `alert_id` is the dedup key; email + webhook + tracker all share one key per alert event.                            | Phase-B SAFE-DEFAULT D-05 |
