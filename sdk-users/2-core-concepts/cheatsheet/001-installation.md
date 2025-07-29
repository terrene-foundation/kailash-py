# Installation & Setup

## Quick Install
```bash
pip install kailash
```

## Poetry Installation (Recommended)
```bash
# Add to existing project
poetry add kailash

# Or create new project
poetry new my-kailash-project
cd my-kailash-project
poetry add kailash
poetry shell
```

## Virtual Environment Setup
```bash
# Create virtual environment
python -m venv kailash-env
source kailash-env/bin/activate  # Linux/Mac
# kailash-env\Scripts\activate  # Windows

# Install in virtual environment
pip install kailash
```

## Requirements.txt Installation
```bash
# Add to requirements.txt
echo "kailash>=0.6.0" >> requirements.txt

# Install from requirements
pip install -r requirements.txt
```

## Verify Installation
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Test basic functionality
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {
    "code": "result = {'status': 'installed'}"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print("✅ Kailash SDK installed successfully!")
print(f"Test result: {results['test']['result']['status']}")
```

## Docker Environment (Recommended)
```bash
# Start full infrastructure stack
docker-compose up -d

# Verify services are running
docker-compose ps
```

## System Requirements
- **Python**: 3.8+ required
- **Memory**: 4GB+ recommended for AI features
- **Docker**: Required for infrastructure services

## Common Installation Issues

### ImportError: No module named 'kailash'
```bash
# Ensure correct Python environment
python --version
pip list | grep kailash

# Reinstall if necessary
pip uninstall kailash
pip install kailash
```

### ModuleNotFoundError: pydantic
```bash
# Install with all dependencies
pip install kailash[all]
```

### Docker Issues
```bash
# Reset Docker environment
docker-compose down -v
docker-compose up -d
```

## Quick First Workflow
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()

# Add nodes with modern API
workflow.add_node("PythonCodeNode", "data_generator", {
    "code": "result = {'data': [1, 2, 3, 4, 5], 'count': 5}"
})

workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'processed_count': len(input_data.get('data', [])), 'summary': input_data}"
})

# Connect nodes with correct syntax
workflow.add_connection("data_generator", "result", "processor", "input_data")

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(f"✅ Workflow executed successfully! Run ID: {run_id}")
print(f"Processed {results['processor']['result']['processed_count']} items")
```

## Next Steps
- [Basic Imports](002-basic-imports.md) - Essential imports
- [Quick Workflow Creation](003-quick-workflow-creation.md) - Build your first workflow
- [Common Node Patterns](004-common-node-patterns.md) - Frequently used patterns
