# Kailash SDK Examples

This directory contains comprehensive examples demonstrating the capabilities of the Kailash Python SDK.

## Directory Structure

```
examples/
├── node_examples/           # Individual node usage examples
├── workflow_examples/       # Workflow construction and patterns
├── integration_examples/    # API and external system integration
├── visualization_examples/  # Workflow visualization and reporting
├── data/                   # Sample data files for examples
├── outputs/                # Generated output files from examples
├── migrations/             # Migration experiments from other systems
└── _utils/                 # Utility scripts for testing examples
```

## Example Categories

### Node Examples (`node_examples/`)
Demonstrates individual node creation and usage:
- `node_basic_connection.py` - Basic node connections
- `node_custom_creation.py` - Creating custom nodes
- `node_docker_test.py` - Docker runtime node testing
- `node_python_code.py` - Python code execution nodes
- `node_python_code_schema.py` - Schema-validated Python nodes
- `node_output_schema.py` - Output schema validation

### Workflow Examples (`workflow_examples/`)
Shows various workflow patterns and use cases:
- `workflow_basic.py` - Simple ETL workflow
- `workflow_complex.py` - Advanced multi-step workflows
- `workflow_comprehensive.py` - Full-featured workflow example
- `workflow_conditional.py` - Conditional routing patterns
- `workflow_parallel.py` - Parallel execution patterns
- `workflow_docker.py` - Docker-based workflow execution
- `workflow_csv_python.py` - CSV processing with Python
- `workflow_data_transformation.py` - Data transformation patterns
- `workflow_error_handling.py` - Error handling strategies
- `workflow_state_management.py` - State management patterns
- `workflow_task_tracking.py` - Task tracking integration
- `workflow_export.py` - Workflow export functionality

### Integration Examples (`integration_examples/`)
External system and API integrations:
- `integration_api_comprehensive.py` - Complete API integration patterns
- `integration_api_simple.py` - Simple API calls
- `integration_hmi_api.py` - HMI-style API usage
- `integration_sharepoint_graph.py` - SharePoint Graph API integration
- `integration_mcp_server.py` - MCP server integration

### Visualization Examples (`visualization_examples/`)
Workflow visualization and reporting:
- `viz_workflow_graphs.py` - Generate workflow visualizations
- `viz_workflow_visual.py` - Visual workflow representations
- `viz_mermaid.py` - Mermaid diagram generation
- `viz_examples_overview.py` - Examples overview generator

## Running Examples

### Basic Usage
```bash
# Run any example directly
python workflow_examples/workflow_basic.py

# Run with help to see options
python workflow_examples/workflow_basic.py --help
```

### Testing All Examples
```bash
# Test that all examples import correctly
python _utils/test_all_examples.py
```

### Data Files
Sample data files are located in the `data/` directory:
- `customers.csv` - Customer data
- `transactions.json` - Transaction records
- `input.csv` - Generic input data
- Various other sample datasets

### Output Files
Generated outputs are saved to the `outputs/` directory:
- Processed data files
- Workflow exports (YAML, JSON)
- Visualization files (Mermaid markdown)
- Analysis reports

## Getting Started

1. **Simple Workflow**: Start with `workflow_examples/workflow_basic.py` to understand the basics
2. **Custom Nodes**: Learn to create custom nodes with `node_examples/node_custom_creation.py`
3. **Advanced Patterns**: Explore `workflow_examples/workflow_comprehensive.py` for complex use cases
4. **Visualizations**: Generate workflow diagrams with `visualization_examples/viz_mermaid.py`

## Requirements

All examples assume the Kailash SDK is installed. From the project root:
```bash
pip install -e .
```

Some examples may require additional dependencies:
```bash
pip install pandas matplotlib networkx
```

## Contributing

When adding new examples:
1. Place them in the appropriate category folder
2. Use the naming convention: `{category}_{description}.py`
3. Include a comprehensive docstring explaining the example
4. Add sample data to `data/` if needed
5. Update this README with the new example
