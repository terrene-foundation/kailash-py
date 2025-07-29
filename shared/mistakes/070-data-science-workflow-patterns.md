# Mistake 070: Data Science Workflow Patterns

## Problem
Common mistakes when implementing data science workflows with PythonCodeNode, including type restrictions, serialization issues, and memory management.

## Common Issues

### 1. Initial Type Restrictions
```python
# Original error:
Input type not allowed: <class 'pandas.core.frame.DataFrame'>

# Cause: Security module didn't allow data science types
# Solution: Updated security.py to include pandas, numpy, torch, etc.
```

### 2. Exception Handling in Sandboxed Environment
```python
# This fails in PythonCodeNode:
try:
    value = risky_operation()
except NameError:  # ❌ NameError not defined in sandbox
    value = default

# Use bare except instead:
try:
    value = risky_operation()
except:  # ✓ Works in sandbox
    value = default
```

### 3. Memory Management with Large Datasets
```python
# Problematic: Loading entire dataset
df = pd.read_csv('huge_file.csv')  # ❌ May cause OOM
result = {"data": df.to_dict('records')}  # ❌ Doubles memory

# Better: Process in chunks
chunk_results = []
for chunk in pd.read_csv('huge_file.csv', chunksize=10000):
    processed = chunk.groupby('category').sum()
    chunk_results.append(processed.to_dict('records'))
result = {"chunks": chunk_results}
```

## Recommended Patterns

### 1. DataFrame Processing Pipeline
```python
workflow.add_node("data_loader", CSVReaderNode(
    file_path="data.csv"
))

workflow.add_node("data_processor", PythonCodeNode(
    name="data_processor",
    code='''
import pandas as pd
import numpy as np

# Reconstruct DataFrame from CSV reader output
df = pd.DataFrame(data)

# Data cleaning
df = df.dropna()
df['value'] = pd.to_numeric(df['value'], errors='coerce')

# Feature engineering
df['log_value'] = np.log1p(df['value'])
df['value_squared'] = df['value'] ** 2

# Aggregations
summary = {
    'mean': df['value'].mean(),
    'std': df['value'].std(),
    'quantiles': df['value'].quantile([0.25, 0.5, 0.75]).tolist()
}

# Serialize for output
result = {
    'processed_data': df.to_dict('records'),
    'summary': summary,
    'shape': df.shape,
    'columns': df.columns.tolist()
}
'''
))

workflow.add_node("model_trainer", PythonCodeNode(
    name="model_trainer",
    code='''
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
import pickle
import base64

# Reconstruct DataFrame
df = pd.DataFrame(data['processed_data'])

# Prepare features
X = df[['log_value', 'value_squared']]
y = df['value']

# Split data
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# Train model
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Evaluate
train_score = model.score(X_train, y_train)
test_score = model.score(X_test, y_test)

# Serialize model (for small models only)
model_bytes = pickle.dumps(model)
model_b64 = base64.b64encode(model_bytes).decode('utf-8')

result = {
    'train_score': train_score,
    'test_score': test_score,
    'feature_importance': dict(zip(X.columns, model.feature_importances_)),
    'model_b64': model_b64,  # Only for small models
    'model_size_kb': len(model_bytes) / 1024
}
'''
))

# Connect the pipeline
workflow.connect("data_loader", "data_processor")
workflow.connect("data_processor", "model_trainer", {"result": "data"})
```

### 2. Handling Different Data Science Types
```python
workflow.add_node("type_handler", PythonCodeNode(
    name="type_handler",
    code='''
import pandas as pd
import numpy as np

# DataFrames - multiple serialization options
df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
df_serialized = {
    'records': df.to_dict('records'),      # List of rows
    'columns': df.to_dict('list'),         # Dict of columns
    'json': df.to_json(),                  # JSON string
    'values': df.values.tolist(),          # Just the data
    'info': {
        'shape': df.shape,
        'columns': df.columns.tolist(),
        'dtypes': {col: str(dt) for col, dt in df.dtypes.items()}
    }
}

# NumPy arrays - convert to lists
arr = np.array([[1, 2, 3], [4, 5, 6]])
arr_serialized = {
    'data': arr.tolist(),
    'shape': arr.shape,
    'dtype': str(arr.dtype)
}

# Sparse matrices (scipy)
try:
    from scipy.sparse import csr_matrix
    sparse = csr_matrix([[1, 0, 2], [0, 0, 3], [4, 5, 6]])
    sparse_serialized = {
        'data': sparse.data.tolist(),
        'indices': sparse.indices.tolist(),
        'indptr': sparse.indptr.tolist(),
        'shape': sparse.shape
    }
except:
    sparse_serialized = None

result = {
    'dataframe': df_serialized,
    'array': arr_serialized,
    'sparse': sparse_serialized
}
'''
))
```

### 3. Visualization Output Pattern
```python
workflow.add_node("visualizer", PythonCodeNode(
    name="visualizer",
    code='''
import pandas as pd
import matplotlib.pyplot as plt
import base64
from io import BytesIO

# Create DataFrame
df = pd.DataFrame(data['processed_data'])

# Create plot
fig, ax = plt.subplots(figsize=(10, 6))
df.plot(x='date', y='value', ax=ax)
ax.set_title('Data Visualization')

# Convert to base64 for serialization
buffer = BytesIO()
plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
buffer.seek(0)
img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
plt.close()

result = {
    'plot_base64': img_base64,
    'plot_type': 'line',
    'plot_size_kb': len(img_base64) / 1024
}
'''
))
```

### 4. Error Handling Pattern
```python
workflow.add_node("safe_processor", PythonCodeNode(
    name="safe_processor",
    code='''
import pandas as pd
import numpy as np

errors = []
warnings = []

# Safe DataFrame creation
try:
    df = pd.DataFrame(data)
except:
    errors.append("Failed to create DataFrame from input data")
    df = pd.DataFrame()

# Safe numeric conversion
try:
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    null_count = df['value'].isna().sum()
    if null_count > 0:
        warnings.append(f"Converted {null_count} non-numeric values to NaN")
except:
    errors.append("Failed to convert 'value' column to numeric")

# Safe aggregation
try:
    if not df.empty and 'value' in df.columns:
        stats = {
            'mean': float(df['value'].mean()),
            'std': float(df['value'].std()),
            'count': int(df['value'].count())
        }
    else:
        stats = {'mean': None, 'std': None, 'count': 0}
except:
    errors.append("Failed to calculate statistics")
    stats = {}

result = {
    'data': df.to_dict('records') if not df.empty else [],
    'stats': stats,
    'errors': errors,
    'warnings': warnings,
    'success': len(errors) == 0
}
'''
))
```

### 5. Cycle-Based Data Processing
```python
# Iterative data cleaning with quality improvement
workflow.add_node("iterative_cleaner", PythonCodeNode(
    name="iterative_cleaner",
    code='''
import pandas as pd
import numpy as np

# Handle first iteration
try:
    df = pd.DataFrame(data)
    iteration = iteration + 1
    prev_quality = quality_score
except:
    df = pd.DataFrame(initial_data)  # From workflow parameter
    iteration = 1
    prev_quality = 0.0

# Calculate current quality
nulls = df.isna().sum().sum()
duplicates = df.duplicated().sum()
total_issues = nulls + duplicates

# Clean data
df_cleaned = df.dropna().drop_duplicates()

# Calculate quality score
quality_score = 1.0 - (total_issues / (df.shape[0] * df.shape[1]))
improvement = quality_score - prev_quality

# Convergence check
converged = improvement < 0.01 or quality_score > 0.95

result = {
    'cleaned_data': df_cleaned.to_dict('records'),
    'quality_score': quality_score,
    'iteration': iteration,
    'converged': converged,
    'metrics': {
        'nulls_removed': int(nulls),
        'duplicates_removed': int(duplicates),
        'improvement': improvement
    }
}
'''
))

# ❌ WRONG - Using deprecated cycle=True pattern
workflow.connect("iterative_cleaner", "iterative_cleaner",
    mapping={"result": "data"},
    cycle=True,  # DEPRECATED!
    max_iterations=10,
    convergence_check="converged == True"
)

# ✅ CORRECT - Modern CycleBuilder API
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "iterative_cleaner", {
    "code": """
# Data science processing with pandas
import pandas as pd
import numpy as np

try:
    df = pd.DataFrame(data.get("records", []))
    iteration = data.get("iteration", 0)
except NameError:
    # First iteration - create sample data
    df = pd.DataFrame({"values": [1, 2, 3, 4, 5], "quality": [0.6, 0.7, 0.5, 0.8, 0.4]})
    iteration = 0

new_iteration = iteration + 1

# Clean data iteratively
if len(df) > 0:
    # Remove low quality rows
    quality_threshold = 0.6 + (iteration * 0.05)
    cleaned_df = df[df["quality"] >= quality_threshold]

    # Calculate improvement
    improvement = len(cleaned_df) / len(df) if len(df) > 0 else 1.0
    converged = improvement >= 0.9 or new_iteration >= 5
else:
    cleaned_df = df
    converged = True

result = {
    "records": cleaned_df.to_dict("records"),
    "iteration": new_iteration,
    "shape": list(cleaned_df.shape),
    "converged": converged
}
"""
})

# Build workflow and create cycle
built_workflow = workflow.build()
cycle_builder = built_workflow.create_cycle('quality_improvement')
cycle_builder.connect('iterative_cleaner', 'iterative_cleaner', mapping={'result': 'data'})
cycle_builder.max_iterations(10)
cycle_builder.converge_when('converged == True')
cycle_builder.build()

# Execute with runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)
```

## Best Practices

1. **Always serialize data science objects** before returning from PythonCodeNode
2. **Use bare except** clauses for error handling in sandboxed environment
3. **Include metadata** (shape, columns, dtypes) for DataFrame reconstruction
4. **Process large data in chunks** to avoid memory issues
5. **Use base64 encoding** for binary data (models, images)
6. **Check for empty DataFrames** before operations
7. **Convert numpy scalars** to Python types for JSON serialization
8. **Document expected input/output formats** in node descriptions

## Prevention
1. Test with realistic data sizes
2. Monitor memory usage during execution
3. Validate data types at node boundaries
4. Use streaming/chunking for large datasets
5. Consider file-based data passing for very large objects

## Related
- [068-pythoncode-dataframe-serialization.md](068-pythoncode-dataframe-serialization.md)
- [069-numpy-version-compatibility.md](069-numpy-version-compatibility.md)
- [067-phase-6-3-completion-pythoncode-execution-environment.md](067-phase-6-3-completion-pythoncode-execution-environment.md)
