# ML Drift Monitoring

DriftMonitor detects distribution shifts between training (reference) and production (current) data using statistical tests. Supports scheduled monitoring, configurable alert thresholds, and automatic retraining triggers.

## Setup

```python
from kailash_ml import DriftMonitor
from kailash.db.connection import ConnectionManager

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

monitor = DriftMonitor(conn)
await monitor.initialize()
```

## Set Reference Distribution

The reference distribution is the baseline against which all future data is compared. Typically the training data or a validated production snapshot.

```python
import polars as pl

reference_df = pl.read_csv("training_data.csv")
await monitor.set_reference_data("churn_model_v1", reference_df)

# Reference is stored and versioned — can be updated when model is retrained
await monitor.set_reference_data("churn_model_v2", new_training_df)
```

## Check Drift

```python
current_df = pl.read_csv("production_data_this_week.csv")
report = await monitor.check_drift("churn_model_v1", current_df)

# Overall drift assessment
report.overall_drift       # True/False
report.drift_score         # Aggregate score (0.0 = no drift, 1.0 = extreme drift)
report.severity            # "none", "low", "moderate", "severe"

# Per-feature results
for feature in report.feature_results:
    print(f"{feature.name}: drift={feature.is_drifting}, "
          f"score={feature.score:.4f}, test={feature.test_used}")

# Recommendations
for rec in report.recommendations:
    print(f"  {rec}")
# e.g., "Feature 'monthly_spend' shows severe drift (PSI=0.38). Consider retraining."
```

## Statistical Tests

DriftMonitor selects the appropriate test based on feature type. All tests are available for explicit selection.

### Kolmogorov-Smirnov Test (Continuous Features)

Non-parametric test comparing two continuous distributions. Detects any type of distribution change.

```python
report = await monitor.check_drift(
    "churn_model_v1",
    current_df,
    tests={"age": "ks", "monthly_spend": "ks"},
)
# feature.score = KS statistic (0-1)
# feature.p_value = statistical significance
# Drift detected when p_value < threshold (default 0.05)
```

### Chi-Squared Test (Categorical Features)

Tests whether the distribution of categorical values has changed.

```python
report = await monitor.check_drift(
    "churn_model_v1",
    current_df,
    tests={"plan_type": "chi2", "region": "chi2"},
)
# feature.score = chi-squared statistic
# feature.p_value = statistical significance
```

### Population Stability Index (PSI)

Industry-standard metric for monitoring model input stability. Measures how much a distribution has shifted from reference.

```python
report = await monitor.check_drift(
    "churn_model_v1",
    current_df,
    tests={"age": "psi", "monthly_spend": "psi"},
)
# feature.score = PSI value
# PSI < 0.1  → no significant drift
# PSI 0.1-0.2 → moderate drift (investigate)
# PSI > 0.2  → significant drift (action required)
```

### Jensen-Shannon Divergence

Symmetric, bounded (0-1) measure of distribution similarity. More stable than KL divergence.

```python
report = await monitor.check_drift(
    "churn_model_v1",
    current_df,
    tests={"age": "js", "monthly_spend": "js"},
)
# feature.score = JS divergence (0 = identical, 1 = completely different)
```

### Test Selection Guide

| Feature Type            | Recommended Test | Why                                         |
| ----------------------- | ---------------- | ------------------------------------------- |
| Continuous              | KS               | Distribution-free, detects any shift        |
| Categorical             | Chi-squared      | Standard for categorical independence       |
| Model input monitoring  | PSI              | Industry standard, interpretable thresholds |
| Distribution comparison | JS divergence    | Symmetric, bounded, stable                  |

## Alert Thresholds

Configure per-feature or global thresholds.

```python
# Global threshold
monitor = DriftMonitor(conn, default_threshold=0.1)

# Per-feature thresholds
await monitor.set_thresholds("churn_model_v1", {
    "age": 0.15,              # More tolerant (demographics shift slowly)
    "monthly_spend": 0.05,    # Less tolerant (financial features are critical)
    "plan_type": 0.10,        # Moderate
})

# Severity levels based on threshold multiples
# score < threshold        → "none"
# score < 2x threshold     → "low"
# score < 3x threshold     → "moderate"
# score >= 3x threshold    → "severe"
```

## Scheduled Monitoring

Run drift checks on a schedule to catch shifts early.

```python
# Schedule daily drift check
await monitor.schedule(
    model_name="churn_model_v1",
    data_source="feature_store:user_features",  # Pull from FeatureStore
    interval="daily",                            # "hourly", "daily", "weekly"
    alert_on="moderate",                         # Alert severity threshold
)

# Schedule with custom callback
async def on_drift_detected(report):
    if report.severity in ("moderate", "severe"):
        await notify_team(report)
        if report.severity == "severe":
            await trigger_retraining(report.model_name)

await monitor.schedule(
    model_name="churn_model_v1",
    data_source="feature_store:user_features",
    interval="daily",
    callback=on_drift_detected,
)
```

## Retraining Triggers

DriftMonitor can trigger automatic retraining when drift exceeds thresholds.

```python
from kailash_ml import DriftMonitor, TrainingPipeline

monitor = DriftMonitor(conn)
pipeline = TrainingPipeline(feature_store=fs, model_registry=registry)

# Automatic retraining on severe drift
await monitor.set_retraining_trigger(
    model_name="churn_model_v1",
    trigger_severity="severe",        # Only retrain on severe drift
    pipeline=pipeline,
    schema=schema,
    model_spec=model_spec,
    eval_spec=eval_spec,
    auto_promote=False,               # Human approval still required for production
)
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
# Get drift history for a model
history = await monitor.get_drift_history(
    model_name="churn_model_v1",
    days=30,
)

for check in history:
    print(f"{check.timestamp}: drift={check.overall_drift}, "
          f"score={check.drift_score:.4f}, severity={check.severity}")

# Get drift trend for a specific feature
feature_history = await monitor.get_feature_drift_history(
    model_name="churn_model_v1",
    feature_name="monthly_spend",
    days=90,
)
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
