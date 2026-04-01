# kailash-ml-protocols

Frozen interface contracts for the Kailash ML ecosystem. This thin package (~160 lines, zero dependencies) breaks the circular dependency between `kailash-ml` and `kailash-kaizen`.

## Install

```bash
pip install kailash-ml-protocols
```

No dependencies required -- Python 3.10+ stdlib only.

## Protocols

### MLToolProtocol

Tools that Kaizen agents call via MCP to access ML capabilities.

- `predict(model_name, features, *, options=None)` -- Single-record prediction
- `get_metrics(model_name, version=None, *, options=None)` -- Model metrics
- `get_model_info(model_name, *, options=None)` -- Model metadata

### AgentInfusionProtocol

Protocol for agent-augmented engine methods.

- `suggest_model(data_profile, task_type, *, options=None)` -- Suggest model families
- `suggest_features(data_profile, existing_features, *, options=None)` -- Suggest feature engineering
- `interpret_results(experiment_results, *, options=None)` -- Interpret experiment results
- `interpret_drift(drift_report, *, options=None)` -- Interpret drift report

## Schemas

- `FeatureField` -- Single feature column definition
- `FeatureSchema` -- Schema for a feature set with `to_dict()` / `from_dict()` round-trip
- `ModelSignature` -- Input/output schema for a trained model
- `MetricSpec` -- A single evaluation metric with its value

## License

Apache 2.0 -- Terrene Foundation
