# PythonCodeNode Best Practices

Essential patterns for maximum developer productivity with PythonCodeNode.

## 🚀 ALWAYS Use `.from_function()` for Non-Trivial Code

### Why This Matters
String-based code blocks provide **ZERO IDE support** - no syntax highlighting, no auto-completion, no error detection, no debugging capabilities. This dramatically reduces developer productivity and code quality.

### The Golden Rule
**If your code is more than 3-5 lines, use `.from_function()`**

## Quick Examples

### ❌ BAD: String Code (No IDE Support)
```python
# DON'T DO THIS - No IDE assistance!
processor = PythonCodeNode(
    name="data_processor",
    code="""
import pandas as pd
import numpy as np

# No syntax highlighting!
# No auto-completion!
# No immediate error detection!
def process_data(df, threshold):
    filtered = df[df['value'] > threshold]  # Hope column exists!
    result = filtered.groupby('category').agg({
        'value': ['mean', 'sum', 'count'],
        'score': 'std'  # No validation this column exists
    })
    return {'summary': result.to_dict()}

# Main execution
df = pd.DataFrame(input_data)
output = process_data(df, 100)
"""
)
```

### ✅ GOOD: Function-Based (Full IDE Support)
```python
# DO THIS - Full IDE power!
import pandas as pd
import numpy as np
from typing import Dict, Any

def process_customer_data(input_data: list, threshold: float = 100) -> Dict[str, Any]:
    """
    Process customer data with filtering and aggregation.
    
    Args:
        input_data: List of customer records
        threshold: Minimum value threshold
        
    Returns:
        Dictionary with summary statistics
    """
    # Full IDE support here!
    df = pd.DataFrame(input_data)
    
    # IDE shows available columns and methods
    if 'value' not in df.columns:
        return {'error': 'Missing value column'}
    
    # Type hints and auto-completion work
    filtered = df[df['value'] > threshold]
    
    # IDE validates column names
    if not filtered.empty and 'category' in filtered.columns:
        summary = filtered.groupby('category').agg({
            'value': ['mean', 'sum', 'count']
        })
        return {
            'summary': summary.to_dict(),
            'total_records': len(filtered),
            'threshold_used': threshold
        }
    
    return {'summary': {}, 'total_records': 0}

# Create node from function - clean and testable!
processor = PythonCodeNode.from_function(
    func=process_customer_data,
    name="customer_processor",
    description="Process customer data with filtering and aggregation"
)
```

## Advanced Patterns

### Complex Data Science Workflow
```python
# Define reusable, testable functions
def clean_data(raw_data: list) -> pd.DataFrame:
    """Clean and prepare data with full IDE support."""
    df = pd.DataFrame(raw_data)
    
    # Handle missing values
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df = df.dropna(subset=['value'])
    
    # Normalize text fields
    if 'category' in df.columns:
        df['category'] = df['category'].str.strip().str.lower()
    
    return df

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create new features from existing data."""
    # IDE helps with pandas methods
    df['value_squared'] = df['value'] ** 2
    df['value_log'] = np.log1p(df['value'])
    
    # Create bins with IDE validation
    df['value_bin'] = pd.qcut(df['value'], q=5, labels=['XS', 'S', 'M', 'L', 'XL'])
    
    return df

def generate_insights(df: pd.DataFrame) -> Dict[str, Any]:
    """Generate business insights from processed data."""
    insights = {
        'total_value': df['value'].sum(),
        'average_value': df['value'].mean(),
        'top_categories': df['category'].value_counts().head(5).to_dict(),
        'value_distribution': {
            'min': df['value'].min(),
            'q1': df['value'].quantile(0.25),
            'median': df['value'].median(),
            'q3': df['value'].quantile(0.75),
            'max': df['value'].max()
        }
    }
    
    return insights

# Compose into workflow nodes
cleaner = PythonCodeNode.from_function(
    func=clean_data,
    name="data_cleaner",
    description="Clean and prepare raw data"
)

feature_engineer = PythonCodeNode.from_function(
    func=engineer_features,
    name="feature_engineer",
    description="Create derived features"
)

insight_generator = PythonCodeNode.from_function(
    func=generate_insights,
    name="insight_generator",
    description="Generate business insights"
)
```

### Machine Learning Pipeline
```python
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
import joblib

def prepare_ml_data(input_data: list, target_column: str = 'target') -> Dict[str, Any]:
    """Prepare data for machine learning with validation."""
    df = pd.DataFrame(input_data)
    
    # Validate target column exists
    if target_column not in df.columns:
        return {'error': f'Target column {target_column} not found'}
    
    # Separate features and target
    feature_columns = [col for col in df.columns if col != target_column]
    X = df[feature_columns].select_dtypes(include=[np.number])
    y = df[target_column]
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    return {
        'X_train': X_train_scaled.tolist(),
        'X_test': X_test_scaled.tolist(),
        'y_train': y_train.tolist(),
        'y_test': y_test.tolist(),
        'feature_names': list(X.columns),
        'scaler': scaler  # Can be serialized with joblib
    }

def train_model(X_train: list, y_train: list, **params) -> Dict[str, Any]:
    """Train a model with hyperparameters."""
    # Convert back to numpy arrays
    X_train = np.array(X_train)
    y_train = np.array(y_train)
    
    # Train model with IDE parameter hints
    model = RandomForestRegressor(
        n_estimators=params.get('n_estimators', 100),
        max_depth=params.get('max_depth', None),
        min_samples_split=params.get('min_samples_split', 2),
        random_state=42
    )
    
    model.fit(X_train, y_train)
    
    # Return serializable model
    return {
        'model': model,
        'feature_importance': dict(zip(
            params.get('feature_names', []),
            model.feature_importances_
        )),
        'training_score': model.score(X_train, y_train)
    }

# Create ML pipeline nodes
ml_prep_node = PythonCodeNode.from_function(
    func=prepare_ml_data,
    name="ml_data_prep",
    description="Prepare data for machine learning"
)

model_trainer = PythonCodeNode.from_function(
    func=train_model,
    name="model_trainer",
    description="Train ML model with parameters"
)
```

## When to Use String Code

String code is acceptable ONLY for:

### 1. Simple Expressions (1-3 lines)
```python
# OK for simple calculations
calc_node = PythonCodeNode(
    name="simple_calc",
    code="result = input_value * 1.1"  # Single line is fine
)
```

### 2. Quick Data Transformations
```python
# OK for basic transformations
transform_node = PythonCodeNode(
    name="quick_transform",
    code="""
# Just 2-3 lines of simple logic
data = input_data.get('values', [])
result = [x * 2 for x in data if x > 0]
"""
)
```

### 3. Dynamic Code Generation
```python
# OK when code is generated dynamically
def create_filter_node(column: str, threshold: float):
    code = f"""
# Dynamically generated filter
df = pd.DataFrame(input_data)
result = df[df['{column}'] > {threshold}].to_dict('records')
"""
    return PythonCodeNode(name=f"filter_{column}", code=code)
```

## Testing Functions Before Node Creation

```python
# Test your function independently first!
def test_process_function():
    # Create test data
    test_data = [
        {'id': 1, 'value': 100, 'category': 'A'},
        {'id': 2, 'value': 200, 'category': 'B'}
    ]
    
    # Test the function directly
    result = process_customer_data(test_data, threshold=150)
    
    assert 'summary' in result
    assert result['total_records'] == 1
    print("✅ Function test passed!")

# Run test before creating node
test_process_function()

# Then create node from tested function
node = PythonCodeNode.from_function(
    func=process_customer_data,
    name="tested_processor"
)
```

## Benefits Summary

| Aspect | String Code | `.from_function()` |
|--------|-------------|-------------------|
| Syntax Highlighting | ❌ None | ✅ Full |
| Auto-completion | ❌ None | ✅ Full |
| Type Hints | ❌ None | ✅ Full |
| Error Detection | ❌ Runtime only | ✅ Immediate |
| Debugging | ❌ Print only | ✅ Breakpoints |
| Testing | ❌ Hard | ✅ Easy |
| Refactoring | ❌ Manual | ✅ IDE tools |
| Code Reuse | ❌ Copy-paste | ✅ Import function |

## Quick Migration Guide

Converting string code to function:

```python
# Before (string code)
node = PythonCodeNode(
    name="processor",
    code="""
data = input_data['records']
filtered = [r for r in data if r['status'] == 'active']
result = {'active_count': len(filtered)}
"""
)

# After (function-based)
def process_active_records(input_data: dict) -> dict:
    """Process only active records."""
    data = input_data.get('records', [])
    filtered = [r for r in data if r.get('status') == 'active']
    return {'active_count': len(filtered)}

node = PythonCodeNode.from_function(
    func=process_active_records,
    name="processor"
)
```

## Remember

**Your IDE is your friend - let it help you write better code!**

Use `.from_function()` and enjoy:
- 🎯 Accurate code completion
- 🐛 Immediate error detection  
- 🔍 Easy debugging
- ✅ Testable functions
- 📝 Proper documentation
- 🚀 Faster development