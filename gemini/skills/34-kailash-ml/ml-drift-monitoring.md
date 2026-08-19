# ML Drift Monitoring

DriftMonitor detects distribution shifts between training (reference) and production (current) data using statistical tests. Supports scheduled monitoring, configurable alert thresholds, and automatic retraining triggers.

## Setup

```python
from kailash_ml import DriftMonitor
from kailash.db.connection import ConnectionManager

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

# tenant_id is required; thresholds default (psi=0.2, ks=0.05) unless overridden.
monitor = DriftMonitor(conn, tenant_id="default")
```

## Set Reference Distribution

The reference distribution is the baseline against which all future data is compared. Typically the training data or a validated production snapshot.

```python
import polars as pl

reference_df = pl.read_csv("training_data.csv")
feature_cols = ["age", "tenure_months", "monthly_spend"]
await monitor.set_reference_data("churn_model_v1", reference_df, feature_columns=feature_cols)

# Reference is stored and versioned — can be updated when model is retrained
await monitor.set_reference_data("churn_model_v2", new_training_df, feature_columns=feature_cols)
```

## Check Drift

```python
current_df = pl.read_csv("production_data_this_week.csv")
report = await monitor.check_drift("churn_model_v1", current_df)

# Overall drift assessment
report.overall_drift_detected   # True/False
report.overall_severity         # "none", "moderate", "severe"

# Per-feature results
for feature in report.feature_results:
    print(f"{feature.feature_name}: drift={feature.drift_detected}, "
          f"psi={feature.psi:.4f}, type={feature.drift_type}")
```

## Statistical Tests

`check_drift` selects the appropriate test per feature automatically (continuous →
KS + PSI; categorical → chi-squared; plus Jensen-Shannon). The tests are not chosen
by the caller — each `FeatureDriftResult` carries every computed statistic, and you
read whichever applies:

```python
report = await monitor.check_drift("churn_model_v1", current_df)
for feature in report.feature_results:
    print(
        f"{feature.feature_name}: drift={feature.drift_detected} "
        f"type={feature.drift_type} "
        f"psi={feature.psi:.4f} "
        f"ks={feature.ks_statistic:.4f} (p={feature.ks_pvalue:.4f}) "
        f"chi2={feature.chi2_statistic} "
        f"jsd={feature.jsd:.4f}"
    )
```

### Test Reference

| Statistic                  | `FeatureDriftResult` field      | Applies to  |
| -------------------------- | ------------------------------- | ----------- |
| Kolmogorov-Smirnov         | `ks_statistic`, `ks_pvalue`     | continuous  |
| Population Stability Index | `psi`                           | continuous  |
| Chi-squared                | `chi2_statistic`, `chi2_pvalue` | categorical |
| Jensen-Shannon divergence  | `jsd`                           | both        |

PSI interpretation: `< 0.1` no significant drift · `0.1–0.2` moderate (investigate) ·
`> 0.2` significant (action required).

## Alert Thresholds

Thresholds are set at construction (keyword-only), not via a per-feature setter.

```python
monitor = DriftMonitor(
    conn,
    tenant_id="default",
    psi_threshold=0.2,          # PSI drift cutoff
    ks_threshold=0.05,          # KS p-value cutoff
    performance_threshold=0.1,  # performance-degradation cutoff
)
# report.overall_severity ∈ {"none", "moderate", "severe"} is derived from the
# per-feature results against these thresholds.
```

## Scheduled Monitoring

`schedule_monitoring` registers a periodic check; a `DriftSpec` carries the feature
columns, thresholds, and an `on_drift_detected` callback. Start the scheduler to run
the registered jobs.

```python
from datetime import timedelta
from kailash_ml.engines.drift_monitor import DriftSpec

async def on_drift_detected(report):
    if report.overall_severity in ("moderate", "severe"):
        await notify_team(report)

schedule_id = await monitor.schedule_monitoring(
    "churn_model_v1",
    interval=timedelta(days=1),
    data_fn=fetch_recent_production_data,   # returns a polars DataFrame
    spec=DriftSpec(
        feature_columns=["age", "tenure_months", "monthly_spend"],
        psi_threshold=0.2,
        on_drift_detected=on_drift_detected,
    ),
)
await monitor.start_scheduler()
# ... later: await monitor.stop_scheduler() / await monitor.cancel_schedule(schedule_id)
```

## Retraining Triggers

DriftMonitor can trigger automatic retraining when drift exceeds thresholds.

```python
from datetime import timedelta
from kailash_ml import DriftMonitor, TrainingPipeline
from kailash_ml.engines.drift_monitor import DriftSpec

monitor = DriftMonitor(conn, tenant_id="default")
pipeline = TrainingPipeline(feature_store=fs, registry=registry)

# A drift callback retrains (human approval still gates shadow -> production).
async def on_severe_drift(report):
    if report.overall_severity == "severe":
        await pipeline.retrain(
            "churn_model_v1", schema, model_spec, eval_spec, data=fresh_df
        )

# Schedule periodic checks; the spec carries the drift thresholds + callback.
schedule_id = await monitor.schedule_monitoring(
    "churn_model_v1",
    interval=timedelta(hours=6),
    data_fn=fetch_recent_production_data,   # returns a polars DataFrame
    spec=DriftSpec(
        feature_columns=["age", "tenure_months", "monthly_spend"],
        psi_threshold=0.2,
        on_drift_detected=on_severe_drift,
    ),
)
await monitor.start_scheduler()
```

### Retraining Flow

```
Scheduled Check → Drift Detected → Severity Assessment
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
                "low"              "moderate"           "severe"
                Log only           Alert team      Trigger retraining
                                                        │
                                                  Train new model
                                                        │
                                                  Register (staging)
                                                        │
                                              Human approval gate
                                                        │
                                              Promote to production
```

## Drift History

Query historical drift data for trend analysis.

```python
# Get the most recent drift reports for a model (returns list[dict]).
history = await monitor.get_drift_history("churn_model_v1", limit=30)

for check in history:
    print(
        f"{check['checked_at']}: drift={check['overall_drift']}, "
        f"severity={check['overall_severity']}"
    )
# Each row also carries 'feature_results' (JSON) for per-feature trend analysis.
```

## Integration with InferenceServer

DriftMonitor integrates at the serving layer for real-time drift detection on incoming prediction data. See [ml-inference-server](ml-inference-server.md) for the integration pattern.

## Critical Rules

- Always set a reference distribution before checking drift
- PSI > 0.2 requires action — never ignore significant drift
- Human approval required for production model changes, even when auto-retraining
- Scheduled monitoring catches gradual drift that single checks miss
- Per-feature thresholds for critical features (financial, identity) should be stricter
- All drift data stored via DataFlow's ConnectionManager for dialect portability
