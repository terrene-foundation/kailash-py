# Quickstart

Install kailash-ml and train your first model in under 5 minutes.

## Install

```bash
pip install kailash-ml
```

For deep learning (PyTorch): `pip install kailash-ml[dl]`
For reinforcement learning: `pip install kailash-ml[rl]`

## Train a Model

```python
import kailash_ml as km
from sklearn.datasets import load_iris
import polars as pl

# 1. Load data
iris = load_iris()
df = pl.DataFrame(iris.data, schema=iris.feature_names).with_columns(
    pl.Series("target", iris.target)
)

# 2. Train — family + metrics inferred from the target column's dtype
result = await km.train(df, target="target")

# 3. Register — ONNX format by default
registered = await km.register(result, name="iris-classifier")
print(f"Registered iris-classifier: {registered}")
```

## Profile Your Data

```python
from kailash_ml.engines.data_explorer import DataExplorer

explorer = DataExplorer()
profile = await explorer.profile(df)

print(f"Rows: {profile.n_rows}, Columns: {profile.n_columns}")
for col in profile.columns:
    print(f"  {col.name}: {col.dtype} (nulls: {col.null_pct:.1%})")

# Generate HTML report
html = await explorer.to_html(df, title="Iris Dataset")
```

## Serve Predictions

```python
from kailash_ml.serving.server import InferenceServer

server = await InferenceServer.from_registry(
    "models://iris-classifier@production",
    registry=registry,
    channels=("rest",),
)
await server.start()
result = await server.predict({
    "sepal length (cm)": 5.1,
    "sepal width (cm)": 3.5,
    "petal length (cm)": 1.4,
    "petal width (cm)": 0.2,
})
print(f"Prediction: {result['prediction']}")
await server.stop()
```

## Common Errors

**`ImportError: polars not found`** -- kailash-ml requires polars. Run `pip install kailash-ml` (not just `pip install kailash`).

**`ValueError: target_column not found`** -- Ensure your DataFrame column names match exactly (case-sensitive). Use `df.columns` to verify.

**`ModelNotFoundError`** -- The model must be registered before serving. Call `registry.register()` first.
