# Kailash SDK Templates

This directory contains ready-to-use templates for common workflow patterns in the Kailash Python SDK. Each template is designed to be copied and customized for your specific use case.

## Template Categories

### 1. Workflow Templates
- **[simple_etl.py](workflow/simple_etl.py)** - Minimal ETL example (RECOMMENDED START HERE)
- **[simple_conditional.py](workflow/simple_conditional.py)** - Basic conditional routing
- **[basic_etl.py](workflow/basic_etl.py)** - Advanced ETL with validation
- **[conditional_routing.py](workflow/conditional_routing.py)** - Complex conditional branching

### 2. Node Templates
- **[simple_custom_node.py](nodes/simple_custom_node.py)** - Minimal custom node (START HERE)
- **[custom_node.py](nodes/custom_node.py)** - Advanced custom node with validation

### 3. Integration Templates
- **[simple_api_call.py](integrations/simple_api_call.py)** - Basic API call (START HERE)
- **[api_integration.py](integrations/api_integration.py)** - Advanced API integration

### 4. Data Processing Templates
- **[data_validation.py](data/data_validation.py)** - Comprehensive data validation

## Quick Start

### 1. Choose a Template
Browse the templates and find one that matches your use case.

### 2. Copy the Template
```bash
cp guide/reference/templates/workflow/basic_etl.py my_workflow.py
```

### 3. Customize
- Replace placeholder values with your configuration
- Modify node logic as needed
- Add additional nodes or connections

### 4. Run
```bash
python my_workflow.py
```

## Template Structure

Each template follows a consistent structure:

```python
"""
Template: [Name]
Purpose: [Description]
Use Case: [When to use this template]

Customization Points:
- [What needs to be customized]
- [Configuration options]
- [Extension points]
"""

# Imports
from kailash.workflow import Workflow
from kailash.nodes.data.readers import CSVReaderNode
# ... other imports

# Configuration (customize these)
INPUT_FILE = "data.csv"
OUTPUT_FILE = "output.json"
# ... other config

# Template implementation
def create_workflow():
    """Create and configure the workflow"""
    workflow = Workflow()

    # Add nodes
    # ... node setup

    # Connect nodes
    # ... connections

    return workflow

# Execution
if __name__ == "__main__":
    workflow = create_workflow()
    # ... execute workflow
```

## Common Customization Points

### Data Sources
- File paths for readers/writers
- Database connection strings
- API endpoints

### Processing Logic
- PythonCodeNode functions
- Transformation rules
- Validation criteria

### Configuration
- Node parameters
- Runtime settings
- Error handling policies

### Output Formats
- File formats (CSV, JSON, etc.)
- Data schemas
- Report templates

## Best Practices

1. **Start Simple**: Begin with a basic template and add complexity as needed
2. **Test Incrementally**: Test each modification before adding more
3. **Document Changes**: Update comments to reflect your customizations
4. **Version Control**: Track template modifications in git
5. **Share Back**: Consider contributing useful patterns back to the SDK

## Contributing New Templates

To contribute a new template:

1. Create a well-documented template file
2. Place it in the appropriate category directory
3. Update this README with a description
4. Include example input/output data if applicable
5. Submit a pull request

## Template Validation

All templates are tested to ensure they:
- Follow SDK best practices
- Include proper error handling
- Have clear documentation
- Work with the latest SDK version

Last Updated: 2025-06-04
