# Data File Consolidation Guide

## Overview

This guide documents the data file consolidation implemented in Session 062. Previously, data files were scattered across 3,633+ locations throughout the project. This consolidation centralizes all data files into a well-organized `/data/` directory structure.

## Problem Statement

### Before Consolidation

Data files were scattered across multiple locations:
- `/examples/data/` - Example input files
- `/examples/*/outputs/` - Generated outputs 
- `/tests/sample_data/` - Test fixtures
- `/data/` - Some central files
- `/examples/cycle_patterns/cycle_analysis_output/` - Cycle analysis results
- Various workflow-specific directories

This created several issues:
- **Duplication**: Same files (e.g., customers.csv) existed in 4+ locations
- **Inconsistency**: Different file formats and schemas for similar data
- **Discovery**: Hard to find relevant data files
- **Maintenance**: Updates required changes in multiple places
- **Examples**: Hardcoded paths throughout examples

### Pain Points

1. **File Discovery**: Developers couldn't easily find existing data files
2. **Path Hardcoding**: Examples had brittle file paths like `"examples/data/customers.csv"`
3. **Data Duplication**: Multiple copies of similar files with slight variations
4. **Mixed Purposes**: Input data, test fixtures, and outputs all intermixed
5. **No Standards**: No consistent naming or organization patterns

## Solution: Centralized Data Structure

### New Directory Structure

```
/data/
├── inputs/           # Input data files (read-only)
│   ├── csv/         # CSV input files
│   ├── json/        # JSON input files  
│   ├── txt/         # Text input files
│   ├── images/      # Image input files
│   ├── workflows/   # Workflow definition files
│   └── configs/     # Configuration files
├── outputs/         # Generated output files (CONSOLIDATED!)
│   ├── misc/           # General outputs
│   ├── workflows/      # Workflow execution results
│   ├── cycle_analysis/ # Cycle analysis reports
│   ├── visualizations/ # Charts, graphs, diagrams
│   ├── csv/            # CSV outputs
│   ├── json/           # JSON outputs
│   ├── txt/            # Text outputs
│   ├── images/         # Generated images/charts
│   └── configs/        # Generated configs
├── templates/       # Template data files
│   ├── csv/         # CSV templates
│   ├── json/        # JSON templates
│   └── workflows/   # Workflow templates
├── test/           # Test-specific data
│   ├── csv/        # Test CSV files
│   ├── json/       # Test JSON files
│   └── fixtures/   # Test fixtures
├── examples/       # Example-specific data
│   ├── csv/        # Example CSV files
│   ├── json/       # Example JSON files
│   └── workflows/  # Example workflows
├── tracking/       # Task tracking and metrics
│   ├── csv/        # Metrics CSV files
│   ├── json/       # Task tracking JSON
│   └── configs/    # Tracking configurations
└── reference/      # Reference documentation
    ├── schemas/    # Data schemas
    ├── samples/    # Sample data files
    └── documentation/ # Data documentation
```

### Design Principles

1. **Separation by Purpose**: Clear distinction between inputs, outputs, templates, tests
2. **Type-based Organization**: Group files by format (CSV, JSON, TXT, etc.)
3. **Predictable Paths**: Standard locations for common file types
4. **Backward Compatibility**: Legacy support during migration period
5. **Tool Integration**: Easy integration with data processing tools

## Implementation

### Data Access Utilities

Created `/examples/utils/data_paths.py` with standardized functions:

```python
from examples.utils.data_paths import (
    get_input_data_path,    # Get path to input file
    get_output_data_path,   # Get path to output file
    get_customer_csv_path,  # Standard customer data
    ensure_output_dir_exists, # Create output directories
    migrate_to_centralized_path # Convert old paths
)

# Usage examples
customer_file = get_input_data_path("customers.csv")
output_file = get_output_data_path("results.csv") 
output_dir = ensure_output_dir_exists("csv")
```

### Migration Support

The utility provides backward compatibility:

```python
# Old hardcoded path
old_path = "examples/data/customers.csv"

# Automatically migrated to centralized location
new_path = migrate_to_centralized_path(old_path)
# Returns: /data/inputs/csv/customers.csv
```

### Updated Example Pattern

Before (hardcoded paths):
```python
# Old pattern - brittle and scattered
reader = CSVReaderNode(file_path="examples/data/customers.csv")
writer = CSVWriterNode(file_path="outputs/results.csv")
```

After (centralized):
```python
# New pattern - standardized and maintainable
from examples.utils.data_paths import get_input_data_path, get_output_data_path

customer_file = get_input_data_path("customers.csv")
output_file = get_output_data_path("results.csv")

reader = CSVReaderNode(file_path=str(customer_file))
writer = CSVWriterNode(file_path=str(output_file))
```

## Benefits

### For Developers

1. **Predictable Structure**: Always know where to find/place data files
2. **No Path Guessing**: Standard utilities handle path resolution
3. **Type Safety**: Clear separation of inputs vs outputs
4. **Easy Discovery**: Browse `/data/inputs/csv/` to see available CSV files
5. **Reusable Data**: Centralized files can be shared across examples

### For Examples

1. **Maintainability**: No more hardcoded file paths
2. **Portability**: Examples work regardless of working directory
3. **Consistency**: All examples use same data files
4. **Flexibility**: Easy to switch data files via utility functions

### For Testing

1. **Isolation**: Test data separate from example data
2. **Fixtures**: Standardized test fixture locations
3. **Cleanup**: Clear output directories for test results
4. **Validation**: Known data schemas for testing

## Migration Guide

### Output Directory Consolidation (Session 063)

**Problem**: Multiple `outputs/` directories were created throughout the codebase:
- `/outputs/` - Root level outputs
- `/examples/outputs/` - Example outputs
- `/examples/workflow_examples/outputs/` - Workflow outputs
- `/examples/cycle_analysis_output/` - Cycle analysis outputs
- Various visualization and test outputs

**Solution**: All outputs are now consolidated under `/data/outputs/` with proper categorization:

```python
# ❌ OLD: Hardcoded output paths
os.makedirs("outputs", exist_ok=True)
with open("outputs/report.json", "w") as f:
    json.dump(data, f)

# ✅ NEW: Centralized output management
from examples.utils.data_paths import get_output_data_path, ensure_output_dir_exists

ensure_output_dir_exists()
output_path = str(get_output_data_path("workflows/report.json"))
with open(output_path, "w") as f:
    json.dump(data, f)
```

**Output Categories**:
- **misc/** - General outputs that don't fit other categories
- **workflows/** - Workflow execution results
- **cycle_analysis/** - Cycle analysis reports
- **visualizations/** - Charts, graphs, diagrams
- **csv/**, **json/**, **txt/** - Format-specific outputs

### Phase 1: Gradual Migration (Current)

1. **New Files**: All new data files go to centralized locations
2. **Utilities Available**: Use `data_paths.py` for new examples
3. **Legacy Support**: Old paths still work during transition
4. **Examples Updated**: Key examples demonstrate new patterns

### Phase 2: Systematic Migration (Future)

1. **Audit**: Identify all hardcoded paths in examples
2. **Convert**: Update examples to use centralized utilities
3. **Test**: Verify all examples work with new paths
4. **Cleanup**: Remove duplicate files from old locations

### Phase 3: Enforcement (Future)

1. **Linting**: Add linting rules to catch hardcoded paths
2. **CI/CD**: Automated checks for proper data organization
3. **Documentation**: Update all guides to use new patterns
4. **Training**: Update SDK training materials

## Standard Data Files

### Core Input Files

Located in `/data/inputs/csv/`:
- `customers.csv` - Standard customer data for examples
- `transactions.csv` - Transaction data
- `events.csv` - Event data  
- `customer_value.csv` - Customer analysis data
- `raw_customers.csv` - Unprocessed customer data

Located in `/data/inputs/json/`:
- `transactions.json` - Transaction data in JSON format
- Various task tracking files

### Common Output Patterns

Located in `/data/outputs/csv/`:
- `high_value_customers.csv` - Filtered customer data
- `regional_summary.csv` - Regional analysis results
- `processed_customers.csv` - Transformed customer data

## File Naming Conventions

### Input Files
- Use descriptive names: `customers.csv` not `data.csv`
- Include data type: `customer_transactions.json`
- Version if needed: `customers_v2.csv`

### Output Files  
- Include processing type: `filtered_customers.csv`
- Add timestamp if temporal: `daily_summary_2024-01-15.csv`
- Include result type: `analysis_results.json`

### Template Files
- Prefix with "template": `template_customer_data.csv`
- Include purpose: `workflow_template.yaml`

## Best Practices

### For Examples

1. **Always use utilities**: Import from `examples.utils.data_paths`
2. **Document data requirements**: Specify what input files are needed
3. **Create output directories**: Use `ensure_output_dir_exists()`
4. **Use descriptive names**: Clear output file names
5. **Check file existence**: Verify inputs exist before processing

### For Data Management

1. **Single source of truth**: Each data concept has one canonical file
2. **Version control data**: Check in template/sample data files
3. **Ignore generated outputs**: Don't commit auto-generated files
4. **Document schemas**: Include schema documentation for complex data
5. **Regular cleanup**: Remove obsolete data files

### For Testing

1. **Separate test data**: Use `/data/test/` for test-specific files
2. **Predictable fixtures**: Standard test data for consistent results
3. **Clean state**: Tests should not depend on previous test outputs
4. **Isolated outputs**: Test outputs go to test-specific directories

## Tools and Integration

### File Management
```bash
# Find all CSV files
find data/ -name "*.csv"

# List input files by type
ls data/inputs/csv/
ls data/inputs/json/

# Check output directory size
du -sh data/outputs/
```

### Python Integration
```python
# Get all available input CSV files
import os
csv_files = os.listdir("data/inputs/csv/")

# Check if standard files exist
from examples.utils.data_paths import get_customer_csv_path
if get_customer_csv_path().exists():
    print("Customer data available")
```

## Validation and Quality

### Data Quality Checks

1. **Schema Validation**: Verify CSV headers match expected format
2. **File Size Limits**: Monitor for unexpectedly large files
3. **Encoding Check**: Ensure consistent UTF-8 encoding
4. **Format Validation**: Validate JSON syntax, CSV structure

### Monitoring

1. **File Count**: Track number of files in each directory
2. **Size Growth**: Monitor data directory size growth
3. **Access Patterns**: Log which files are accessed most
4. **Cleanup Needs**: Identify old/unused files

## Troubleshooting

### Common Issues

1. **File Not Found**: Check if file exists in centralized location
2. **Permission Errors**: Ensure directories are writable
3. **Path Errors**: Use utilities instead of hardcoded paths
4. **Import Errors**: Add project root to PYTHONPATH

### Debugging

```python
# Check file location
from examples.utils.data_paths import get_input_data_path
file_path = get_input_data_path("customers.csv")
print(f"Looking for file at: {file_path}")
print(f"File exists: {file_path.exists()}")

# List available files
import os
available_files = os.listdir("data/inputs/csv/")
print(f"Available CSV files: {available_files}")
```

## Future Enhancements

### Planned Improvements

1. **Data Catalog**: Automatic discovery and documentation of data files
2. **Schema Registry**: Centralized schema definitions for data files
3. **Versioning**: Data file versioning and change tracking  
4. **Validation**: Automatic data quality validation
5. **Monitoring**: Data usage analytics and optimization

### Integration Opportunities

1. **CI/CD**: Automated data validation in pipelines
2. **Documentation**: Auto-generated data file documentation
3. **Testing**: Automatic test data generation
4. **Performance**: Data file caching and optimization

## Related Documentation

- [Session 061 Architecture Changes](# contrib (removed)/architecture/adr/0040-session-061-parameter-lifecycle-architecture.md)
- [SDK User Guide](sdk-users/README.md)
- [Example Development Guide](examples/README.md)
- [Testing Guidelines](# contrib (removed)/development/instructions/testing-guidelines.md)