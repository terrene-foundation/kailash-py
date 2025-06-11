# Mistake #076: Hardcoded Data File Paths

**Date**: 2025-06-10
**Session**: 062
**Severity**: Medium
**Status**: Active (Session 062 Consolidation)

## Problem Description

Using hardcoded file paths for data files in examples and workflows, leading to brittle code and scattered data files across 3,633+ locations.

## Symptoms

```python
# ❌ WRONG: Hardcoded paths
reader = CSVReaderNode(file_path="examples/data/customers.csv")
writer = CSVWriterNode(file_path="outputs/results.csv")
processor = PythonCodeNode(code='data = pd.read_csv("../data/input.csv")')

# ❌ WRONG: Relative path assumptions
data_dir = Path("./examples/data")
output_dir = Path("./outputs")

# ❌ WRONG: Mixed data locations
input_file = "tests/sample_data/customers.csv"  # Test data
output_file = "examples/outputs/results.csv"    # Example output
temp_file = "data/temp.csv"                     # Central data
```

## Root Causes

1. **No Data Organization Strategy**: Files scattered without organization
2. **Hardcoded Path Dependencies**: Examples tied to specific directory structures
3. **Inconsistent Patterns**: Each example uses different path conventions
4. **Data Duplication**: Same files exist in multiple locations
5. **No Central Utilities**: No standardized way to access data files

## Impact

### Development Issues
- **Brittle Examples**: Examples break when run from different directories
- **Path Maintenance**: Updates require changing multiple hardcoded paths
- **Discovery Problems**: Hard to find existing data files
- **Duplication Waste**: Storage waste from duplicate files

### User Experience Issues
- **Setup Complexity**: Users must create specific directory structures
- **Example Failures**: Examples fail with "file not found" errors
- **Inconsistent Behavior**: Same examples behave differently in different environments

## Session 062 Solution: Centralized Data Structure

### New Centralized Structure

```
/data/
├── inputs/           # Input data files
│   ├── csv/         # customers.csv, transactions.csv, etc.
│   ├── json/        # transactions.json, config files
│   ├── txt/         # Text input files
│   └── images/      # Input images
├── outputs/         # Generated outputs
│   ├── csv/         # Processed CSV files
│   ├── json/        # Analysis results
│   └── images/      # Generated charts
├── templates/       # Template data files
├── test/           # Test-specific data
├── examples/       # Example-specific data
└── reference/      # Documentation and schemas
```

### Data Access Utilities

```python
# ✅ CORRECT: Use centralized data utilities
from examples.utils.data_paths import (
    get_input_data_path,
    get_output_data_path,
    ensure_output_dir_exists,
    get_customer_csv_path
)

# Standard file access
customer_file = get_input_data_path("customers.csv")
output_file = get_output_data_path("results.csv")

# Ensure directories exist
output_dir = ensure_output_dir_exists("csv")

# Common files shortcuts
customers = get_customer_csv_path()
```

### Updated Example Pattern

```python
# ✅ CORRECT: Centralized data access
def main():
    # Get file paths using utilities
    input_file = get_input_data_path("customers.csv")
    output_dir = ensure_output_dir_exists("csv")

    # Create nodes with centralized paths
    reader = CSVReaderNode(file_path=str(input_file))
    writer = CSVWriterNode(
        file_path=str(output_dir / "processed_data.csv")
    )

    # Execute workflow
    data = reader.execute()
    results = process_data(data)
    writer.execute(data=results)
```

## Migration Strategy

### For New Code
```python
# ✅ Always use centralized utilities
from examples.utils.data_paths import get_input_data_path, get_output_data_path

# ✅ Check file existence
input_file = get_input_data_path("customers.csv")
if not input_file.exists():
    raise FileNotFoundError(f"Required input file not found: {input_file}")
```

### For Existing Code
```python
# 🔄 MIGRATION: Convert hardcoded paths
from examples.utils.data_paths import migrate_to_centralized_path

# Old hardcoded path
old_path = "examples/data/customers.csv"

# Automatically convert to centralized path
new_path = migrate_to_centralized_path(old_path)
# Returns: /data/inputs/csv/customers.csv
```

## Best Practices

### File Organization
```python
# ✅ Organize by purpose and type
input_csv = get_input_data_path("customers.csv", "csv")
input_json = get_input_data_path("config.json", "json")
output_csv = get_output_data_path("results.csv", "csv")
test_csv = get_test_data_path("sample.csv", "csv")
```

### Error Handling
```python
# ✅ Handle missing files gracefully
def load_customer_data():
    file_path = get_input_data_path("customers.csv")

    if not file_path.exists():
        # Provide helpful error message
        available_files = list(get_central_data_dir().glob("**/*.csv"))
        raise FileNotFoundError(
            f"Customer data not found at {file_path}\n"
            f"Available CSV files: {[f.name for f in available_files]}"
        )

    return pd.read_csv(file_path)
```

### Documentation
```python
def process_customer_data():
    """Process customer data from centralized location.

    Required Files:
        - data/inputs/csv/customers.csv: Customer master data

    Generated Files:
        - data/outputs/csv/processed_customers.csv: Processed results
        - data/outputs/csv/customer_summary.csv: Summary statistics
    """
    pass
```

## Detection Patterns

### Code Review Checklist
- ❌ Hardcoded file paths like `"examples/data/file.csv"`
- ❌ Relative path assumptions like `"../data/"`
- ❌ Direct file system operations without utilities
- ❌ Mixed data locations (test + example + central)

### Automated Detection
```bash
# Find hardcoded paths in examples
grep -r "examples/data/" examples/ --include="*.py"
grep -r "\.\./" examples/ --include="*.py"
grep -r "outputs/" examples/ --include="*.py"

# Find direct file operations
grep -r "pd.read_csv(" examples/ --include="*.py" | grep -v "get_.*_path"
grep -r "open(" examples/ --include="*.py" | grep -v "get_.*_path"
```

## Testing

### Verify File Access
```python
def test_centralized_data_access():
    """Test that centralized data utilities work correctly."""
    from examples.utils.data_paths import get_input_data_path, get_output_data_path

    # Test input file access
    customer_file = get_input_data_path("customers.csv")
    assert customer_file.exists(), f"Customer file not found: {customer_file}"

    # Test output directory creation
    output_dir = ensure_output_dir_exists("csv")
    assert output_dir.exists(), f"Output directory not created: {output_dir}"

    # Test file operations
    test_data = [{"id": 1, "name": "test"}]
    output_file = get_output_data_path("test_output.csv")
    pd.DataFrame(test_data).to_csv(output_file, index=False)
    assert output_file.exists(), f"Output file not created: {output_file}"
```

## Related Issues

- **Mistake #049**: Missing data source nodes in workflow design
- **Mistake #009**: File path inconsistencies
- **Session 061**: Parameter lifecycle architecture changes

## Resolution Status

**Status**: ✅ RESOLVED in Session 062
- Created centralized `/data/` directory structure
- Implemented data access utilities in `examples/utils/data_paths.py`
- Updated key examples to demonstrate new patterns
- Created migration support for backward compatibility
- Documented best practices and standards

## Additional Resources

- [Data Consolidation Guide](docs/data-consolidation-guide.md)
- [Example Development Guidelines](examples/README.md)
- [Session 062 Implementation Notes](# contrib (removed)/project/todos/completed/062-data-consolidation.md)
