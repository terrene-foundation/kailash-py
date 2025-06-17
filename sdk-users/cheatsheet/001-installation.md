# Installation & Setup

## Quick Install
```bash
pip install kailash
```

## Verify Installation
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime

# Test basic functionality
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()
print("✅ Kailash SDK installed successfully!")

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
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.code import PythonCodeNode

# Create workflow
workflow = Workflow("first_workflow", name="My First Workflow")

# Add nodes
workflow.add_node("reader", CSVReaderNode(),
    file_path="data/sample.csv", has_header=True)

workflow.add_node("processor", PythonCodeNode(
    name="processor",
    code="result = {'count': len(data), 'data': data}",
    input_types={"data": list}
))

# Connect and execute
workflow.connect("reader", "processor", mapping={"data": "data"})
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
print(f"✅ Workflow executed successfully! Run ID: {run_id}")

```

## Next Steps
- [Basic Imports](002-basic-imports.md) - Essential imports
- [Quick Workflow Creation](003-quick-workflow-creation.md) - Build your first workflow
- [Common Node Patterns](004-common-node-patterns.md) - Frequently used patterns
