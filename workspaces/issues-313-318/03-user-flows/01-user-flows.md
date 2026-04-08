# User Flows — Issues #313–#318

## #313: Cardinality Guard

### Before (broken)

```python
pipeline = PreprocessingPipeline()
result = pipeline.setup(data=df, target="fare", categorical_encoding="onehot")
# df has trip_id column with 50k unique values
# Result: 48,611 columns, silent OOM on Colab
```

### After (protected)

```python
pipeline = PreprocessingPipeline()
result = pipeline.setup(
    data=df,
    target="fare",
    categorical_encoding="onehot",
    max_cardinality=50,           # columns above threshold → ordinal
    exclude_columns=["trip_id"],  # explicit exclusion
)
# Warning: "Column 'pickup_zone' has 263 unique values (> max_cardinality=50), using ordinal encoding"
# Result: manageable column count
```

## #314: EDA Charts

### Before (must drop to raw Plotly)

```python
import plotly.express as px
fig = px.histogram(df.to_pandas(), x="price", nbins=50)
fig = px.scatter(df.to_pandas(), x="area", y="price")
fig = px.box(df.to_pandas(), x="region", y="price")
```

### After (stays in Kailash)

```python
viz = ModelVisualizer()
fig = viz.histogram(df, "price", bins=50)
fig = viz.scatter(df, x="area", y="price", color="region")
fig = viz.box_plot(df, "price", group_by="region")
```

## #315: y_label

### Before

```python
fig = viz.training_history(metrics, x_label="Step")
fig.update_layout(yaxis_title="Loss")  # manual workaround
```

### After

```python
fig = viz.training_history(metrics, x_label="Step", y_label="Loss")
```

## #316: Pattern Exports

### Before

```python
from kaizen_agents.patterns.patterns import SupervisorWorkerPattern  # awkward deep import
```

### After

```python
from kaizen_agents import SupervisorWorkerPattern  # clean top-level import
```

## #317: ExperimentTracker Standalone

### Before (3-line boilerplate)

```python
from kailash.db.connection import ConnectionManager
from kailash_ml import ExperimentTracker

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()
tracker = ExperimentTracker(conn)
```

### After (one-liner factory)

```python
from kailash_ml import ExperimentTracker
tracker = await ExperimentTracker.create("sqlite:///ml.db")
```

## #318: ParamDistribution

### Before

```python
p = ParamDistribution("lr", "uniform", low=0.001, high=0.1)
p.type  # works but shadows builtin, confuses beginners
```

### After

```python
p = ParamDistribution("lr", "uniform", low=0.001, high=0.1)
p.distribution  # clean alias, no shadowing
p.type          # still works for backward compatibility
```
