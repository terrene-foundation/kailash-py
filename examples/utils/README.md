# Example Utilities

This directory contains utility scripts and modules for managing and testing Kailash SDK examples.

## Structure

- `paths.py` - Path utilities for data and output directories
- `test_runner.py` - Test runner and example execution utilities
- `maintenance.py` - Maintenance scripts for path fixing and import updates

## Usage

### Testing Examples

Test all examples for syntax and import errors:

```bash
cd examples
python -m utils.test_runner
```

Run a specific example with proper security configuration:

```bash
cd examples
python -m utils.test_runner run workflow_examples/workflow_simple.py
```

Check syntax of specific files:

```bash
cd examples
python -m utils.test_runner syntax workflow_examples/workflow_export.py
```

### Path Utilities

All examples should use these utilities to ensure consistent path handling:

```python
from examples.utils.paths import get_data_dir, get_output_dir

# Reading data files
data_file = get_data_dir() / "customers.csv"
reader = CSVReaderNode(file_path=str(data_file))

# Writing output files
output_file = get_output_dir() / "results.csv"
writer = CSVWriterNode(file_path=str(output_file))
```

### Maintenance

Fix all path references to use correct directory structure:

```bash
cd examples
python -m utils.maintenance fix-paths
```

Update all imports to use full module paths:

```bash
cd examples
python -m utils.maintenance fix-imports
```

Run all maintenance tasks:

```bash
cd examples
python -m utils.maintenance all
```

## Directory Structure

Examples should follow this directory structure:

```
examples/
├── data/               # Input data files
│   ├── customers.csv
│   ├── transactions.json
│   └── outputs/        # All output files go here
│       ├── results.csv
│       └── sharepoint_downloads/
├── node_examples/      # Node-specific examples
├── workflow_examples/  # Workflow examples
├── integration_examples/  # Integration examples
├── visualization_examples/  # Visualization examples
└── utils/              # Utility scripts (this directory)
```

## Important Notes

1. **Input Data**: All input data should be in `examples/data/`
2. **Output Data**: All output should go to `examples/data/outputs/`
3. **Downloads**: Files downloaded by examples (e.g., SharePoint) should go to `examples/data/outputs/<category>/`
4. **Security**: The SDK's security system restricts file access. Use the provided utilities to handle paths correctly.
5. **Module Imports**: Use full module paths: `from examples.utils.paths import get_data_dir, get_output_dir`
