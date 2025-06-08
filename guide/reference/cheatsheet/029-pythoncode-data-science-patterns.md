# PythonCodeNode Data Science Patterns

Quick reference for using PythonCodeNode with data science libraries (pandas, numpy, scikit-learn, etc.).

## DataFrame Processing

### Basic DataFrame Operations
```python
workflow.add_node("df_processor", PythonCodeNode(
    name="df_processor",
    code='''
import pandas as pd
import numpy as np

# Create or receive DataFrame
df = pd.DataFrame(data) if data else pd.DataFrame({
    'A': [1, 2, 3, 4, 5],
    'B': [10, 20, 30, 40, 50],
    'C': ['x', 'y', 'z', 'x', 'y']
})

# Basic operations
df['D'] = df['A'] * df['B']
df['E'] = df['D'].apply(np.sqrt)

# Aggregations
summary = df.groupby('C').agg({
    'A': ['mean', 'std'],
    'B': ['sum', 'count'],
    'D': 'max'
})

# IMPORTANT: Serialize before returning
result = {
    'data': df.to_dict('records'),           # List of row dicts
    'summary': summary.to_dict('index'),      # Nested dict
    'shape': df.shape,                        # Tuple (rows, cols)
    'columns': df.columns.tolist(),           # Column names
    'dtypes': {col: str(dtype) for col, dtype in df.dtypes.items()}
}
'''
))
```

### DataFrame Serialization Options
```python
# Different serialization formats
result = {
    # List of row dictionaries (loses index)
    'records': df.to_dict('records'),
    # [{'A': 1, 'B': 10}, {'A': 2, 'B': 20}, ...]

    # Dictionary of column lists
    'list': df.to_dict('list'),
    # {'A': [1, 2, 3], 'B': [10, 20, 30]}

    # Dictionary of column dictionaries (preserves index)
    'dict': df.to_dict('dict'),
    # {'A': {0: 1, 1: 2}, 'B': {0: 10, 1: 20}}

    # JSON string
    'json': df.to_json(orient='records'),

    # CSV string
    'csv': df.to_csv(index=False),

    # Values only (as nested list)
    'values': df.values.tolist()
}
```

### Preserving DataFrame Index
```python
# Problem: to_dict('records') loses the index
df_indexed = df.set_index('id')

# Solution 1: Reset index before serializing
result = {
    'data': df_indexed.reset_index().to_dict('records'),
    'index_name': df_indexed.index.name
}

# Solution 2: Include index separately
result = {
    'data': df_indexed.to_dict('records'),
    'index': df_indexed.index.tolist(),
    'index_name': df_indexed.index.name
}
```

## NumPy Array Handling

### Array Serialization
```python
workflow.add_node("array_processor", PythonCodeNode(
    name="array_processor",
    code='''
import numpy as np

# Create arrays
arr1d = np.array([1, 2, 3, 4, 5])
arr2d = np.array([[1, 2, 3], [4, 5, 6]])
arr3d = np.random.randn(2, 3, 4)

# Operations
mean_vals = np.mean(arr2d, axis=0)
std_vals = np.std(arr2d, axis=1)

# IMPORTANT: Convert to lists for JSON serialization
result = {
    'array_1d': arr1d.tolist(),
    'array_2d': arr2d.tolist(),
    'array_3d': arr3d.tolist(),
    'mean_values': mean_vals.tolist(),
    'std_values': std_vals.tolist(),
    'shapes': {
        '1d': arr1d.shape,
        '2d': arr2d.shape,
        '3d': arr3d.shape
    },
    'dtypes': {
        '1d': str(arr1d.dtype),
        '2d': str(arr2d.dtype)
    }
}
'''
))
```

### NumPy Type Compatibility
```python
# Handle platform-specific types safely
import numpy as np

# Safe type checking
safe_types = [np.float32, np.float64, np.int32, np.int64]

# Platform-specific types
if hasattr(np, 'float128'):
    safe_types.append(np.float128)

# Version-specific handling
if hasattr(np, 'bytes_'):
    string_type = np.bytes_
elif hasattr(np, 'string_'):  # NumPy < 2.0
    string_type = np.string_
```

## Machine Learning Workflows

### Scikit-learn Integration
```python
workflow.add_node("ml_trainer", PythonCodeNode(
    name="ml_trainer",
    code='''
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
import pickle
import base64

# Load data
df = pd.DataFrame(data)
X = df.drop('target', axis=1)
y = df['target']

# Split data
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# Scale features
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# Train model
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train_scaled, y_train)

# Evaluate
train_score = model.score(X_train_scaled, y_train)
test_score = model.score(X_test_scaled, y_test)
predictions = model.predict(X_test_scaled)

# Get classification report as dict
report = classification_report(y_test, predictions, output_dict=True)

# Serialize model (small models only)
model_bytes = pickle.dumps({'model': model, 'scaler': scaler})
model_b64 = base64.b64encode(model_bytes).decode('utf-8')

result = {
    'train_score': float(train_score),
    'test_score': float(test_score),
    'classification_report': report,
    'feature_importance': dict(zip(X.columns, model.feature_importances_)),
    'model_base64': model_b64,
    'model_size_kb': len(model_bytes) / 1024
}
'''
))
```

### Model Deserialization Pattern
```python
workflow.add_node("ml_predictor", PythonCodeNode(
    name="ml_predictor",
    code='''
import pandas as pd
import pickle
import base64

# Deserialize model
model_b64 = data.get('model_base64')
if model_b64:
    model_bytes = base64.b64decode(model_b64)
    model_dict = pickle.loads(model_bytes)
    model = model_dict['model']
    scaler = model_dict['scaler']

    # Make predictions
    new_data = pd.DataFrame(data.get('new_data', []))
    if not new_data.empty:
        X_new = scaler.transform(new_data)
        predictions = model.predict(X_new)
        probabilities = model.predict_proba(X_new)

        result = {
            'predictions': predictions.tolist(),
            'probabilities': probabilities.tolist(),
            'n_samples': len(predictions)
        }
    else:
        result = {'error': 'No new data provided'}
else:
    result = {'error': 'No model provided'}
'''
))
```

## Visualization Patterns

### Matplotlib to Base64
```python
workflow.add_node("plot_generator", PythonCodeNode(
    name="plot_generator",
    code='''
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import base64
from io import BytesIO

# Create DataFrame
df = pd.DataFrame(data)

# Create figure with subplots
fig, axes = plt.subplots(2, 2, figsize=(12, 10))

# Plot 1: Line plot
axes[0, 0].plot(df.index, df['value'])
axes[0, 0].set_title('Time Series')

# Plot 2: Histogram
axes[0, 1].hist(df['value'], bins=20)
axes[0, 1].set_title('Distribution')

# Plot 3: Scatter plot
axes[1, 0].scatter(df['x'], df['y'], alpha=0.6)
axes[1, 0].set_title('Correlation')

# Plot 4: Box plot
df.boxplot(column='value', by='category', ax=axes[1, 1])
axes[1, 1].set_title('By Category')

plt.tight_layout()

# Convert to base64
buffer = BytesIO()
plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
buffer.seek(0)
img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
plt.close()

result = {
    'plot_base64': img_base64,
    'plot_type': 'multi_panel',
    'size_kb': len(img_base64) / 1024,
    'stats': {
        'mean': float(df['value'].mean()),
        'std': float(df['value'].std())
    }
}
'''
))
```

## Error Handling Patterns

### Safe Data Processing
```python
workflow.add_node("safe_processor", PythonCodeNode(
    name="safe_processor",
    code='''
import pandas as pd
import numpy as np

errors = []
warnings = []
processed_data = None

# Safe DataFrame creation
try:
    if isinstance(data, list):
        df = pd.DataFrame(data)
    elif isinstance(data, dict):
        df = pd.DataFrame(data.get('records', []))
    else:
        df = pd.DataFrame()
except:
    errors.append("Failed to create DataFrame")
    df = pd.DataFrame()

# Safe operations with fallbacks
if not df.empty:
    # Numeric conversion
    for col in df.columns:
        if df[col].dtype == 'object':
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                null_count = df[col].isna().sum()
                if null_count > 0:
                    warnings.append(f"{col}: {null_count} non-numeric values")
            except:
                pass

    # Safe aggregation
    try:
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            stats = {
                col: {
                    'mean': float(df[col].mean()),
                    'std': float(df[col].std()),
                    'min': float(df[col].min()),
                    'max': float(df[col].max())
                }
                for col in numeric_cols
            }
        else:
            stats = {}
            warnings.append("No numeric columns found")
    except:
        errors.append("Failed to calculate statistics")
        stats = {}

    processed_data = df.to_dict('records')
else:
    warnings.append("Empty DataFrame")
    stats = {}

result = {
    'data': processed_data or [],
    'stats': stats,
    'row_count': len(df),
    'column_count': len(df.columns),
    'errors': errors,
    'warnings': warnings,
    'success': len(errors) == 0
}
'''
))
```

## Memory-Efficient Patterns

### Chunked Processing
```python
workflow.add_node("chunk_processor", PythonCodeNode(
    name="chunk_processor",
    code='''
import pandas as pd
import numpy as np

# Process data in chunks to avoid memory issues
chunk_size = 1000
results = []

# If data is large, process in chunks
if isinstance(data, list) and len(data) > chunk_size:
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        df_chunk = pd.DataFrame(chunk)

        # Process chunk
        chunk_result = {
            'mean': float(df_chunk['value'].mean()),
            'count': len(df_chunk),
            'chunk_id': i // chunk_size
        }
        results.append(chunk_result)

    # Combine results
    total_mean = np.mean([r['mean'] for r in results])
    total_count = sum(r['count'] for r in results)
else:
    # Process all at once for small data
    df = pd.DataFrame(data)
    total_mean = float(df['value'].mean())
    total_count = len(df)
    results = [{'mean': total_mean, 'count': total_count, 'chunk_id': 0}]

result = {
    'chunk_results': results,
    'total_mean': total_mean,
    'total_count': total_count,
    'n_chunks': len(results)
}
'''
))
```

## Common Gotchas

1. **Always serialize before returning**: DataFrames, arrays, and models aren't JSON-serializable
2. **Use bare except**: Specific exception types like `NameError` aren't available in sandbox
3. **Convert numpy scalars**: Use `float()`, `int()` to convert np.float64, np.int64
4. **Check for empty DataFrames**: Many operations fail on empty DataFrames
5. **Platform compatibility**: Not all NumPy types exist on all platforms
6. **Memory management**: Large DataFrames can cause OOM - use chunking
7. **Index preservation**: `.to_dict('records')` loses index - handle explicitly
