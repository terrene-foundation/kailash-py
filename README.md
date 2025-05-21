# Kailash Python SDK

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black">
</p>

<p align="center">
  <strong>A Pythonic SDK for the Kailash container-node architecture</strong>
</p>

<p align="center">
  Build workflows that seamlessly integrate with Kailash's production environment while maintaining the flexibility to prototype quickly and iterate locally.
</p>

---

## ✨ Highlights

- 🚀 **Rapid Prototyping**: Create and test workflows locally without containerization
- 🏗️ **Architecture-Aligned**: Automatically ensures compliance with Kailash standards
- 🔄 **Seamless Handoff**: Export prototypes directly to production-ready formats
- 📊 **Built-in Monitoring**: Track workflow execution and performance metrics
- 🧩 **Extensible**: Easy to create custom nodes for domain-specific operations

## 🎯 Who Is This For?

The Kailash Python SDK is designed for:

- **AI Business Coaches (ABCs)** who need to prototype workflows quickly
- **Data Scientists** building ML pipelines compatible with production infrastructure
- **Engineers** who want to test Kailash workflows locally before deployment
- **Teams** looking to standardize their workflow development process

## 🚀 Quick Start

### Installation

```bash
# Install from PyPI
pip install kailash

# Install with development tools
pip install kailash[dev]
```

### Your First Workflow

```python
from kailash.workflow import Workflow
from kailash.nodes.data import CSVReader
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime
import pandas as pd

# Create a workflow
workflow = Workflow(name="customer_analysis")

# Add data reader
reader = CSVReader(file_path="customers.csv")
workflow.add_node(reader, node_id="read_customers")

# Add custom processing using Python code
def analyze_customers(data):
    """Analyze customer data and compute metrics."""
    df = pd.DataFrame(data)
    return {
        "total_customers": len(df),
        "avg_spend": df["total_spent"].mean(),
        "top_customers": df.nlargest(10, "total_spent").to_dict("records")
    }

analyzer = PythonCodeNode.from_function(analyze_customers, name="analyzer")
workflow.add_node(analyzer, node_id="analyze")

# Connect nodes
workflow.connect("read_customers", "analyze", {"data": "data"})

# Run locally
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
print(f"Analysis complete! Results: {results}")

# Export for production
from kailash.utils.export import WorkflowExporter
exporter = WorkflowExporter()
exporter.export_to_kailash(workflow, "customer_analysis.yaml")
```

## 📚 Documentation

| Resource | Description |
|----------|-------------|
| 📖 [User Guide](docs/user-guide.md) | Comprehensive guide for using the SDK |
| 🏛️ [Architecture](docs/adr/) | Architecture Decision Records |
| 📋 [API Reference](docs/api/) | Detailed API documentation |
| 🎓 [Examples](examples/) | Working examples and tutorials |
| 🤝 [Contributing](CONTRIBUTING.md) | Contribution guidelines |

## 🛠️ Features

### 📦 Pre-built Nodes

The SDK includes a rich set of pre-built nodes for common operations:

<table>
<tr>
<td width="50%">

**Data Operations**
- `CSVReader` - Read CSV files
- `JSONReader` - Read JSON files
- `SQLDatabaseNode` - Query databases
- `CSVWriter` - Write CSV files
- `JSONWriter` - Write JSON files

</td>
<td width="50%">

**Processing Nodes**
- `PythonCodeNode` - Custom Python logic
- `DataTransformer` - Transform data
- `Filter` - Filter records
- `Aggregator` - Aggregate data
- `TextProcessor` - Process text

</td>
</tr>
<tr>
<td width="50%">

**AI/ML Nodes**
- `EmbeddingNode` - Generate embeddings
- `VectorDatabaseNode` - Vector search
- `ModelPredictorNode` - ML predictions
- `LLMNode` - LLM integration

</td>
<td width="50%">

**Integration Nodes**
- `HTTPRequestNode` - HTTP requests
- `KafkaConsumerNode` - Kafka streaming
- `WebSocketNode` - WebSocket connections
- `EmailNode` - Send emails

</td>
</tr>
</table>

### 🔧 Core Capabilities

#### Workflow Management
```python
# Create complex workflows with branching logic
workflow = Workflow(name="data_pipeline")

# Add conditional branching
validator = ValidationNode()
workflow.add_node(validator, node_id="validate")

# Different paths based on validation
workflow.add_node(processor_a, node_id="process_valid")
workflow.add_node(error_handler, node_id="handle_errors")

# Connect with conditions
workflow.connect("validate", "process_valid", condition="is_valid")
workflow.connect("validate", "handle_errors", condition="has_errors")
```

#### Immutable State Management
```python
from kailash.workflow.state import WorkflowStateWrapper

# Create and wrap state object
state = MyStateModel()
state_wrapper = workflow.create_state_wrapper(state)

# Single path-based update
updated_wrapper = state_wrapper.update_in(
    ["nested", "field"], 
    new_value
)

# Batch update multiple fields atomically
updated_wrapper = state_wrapper.batch_update([
    (["field1"], value1),
    (["nested", "field2"], value2)
])

# Execute workflow with state management
final_state, results = workflow.execute_with_state(state_model=state)
```

#### Task Tracking
```python
from kailash.tracking import TaskManager

# Initialize task manager with storage backend
task_manager = TaskManager(storage_type="filesystem")

# Run workflow with tracking
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, task_manager=task_manager)

# Query execution history
runs = task_manager.list_runs(status="completed", limit=10)
details = task_manager.get_run(run_id)
```

#### Local Testing
```python
from kailash.runtime.local import LocalRuntime

# Create test runtime with debugging enabled
runtime = LocalRuntime(debug=True)

# Execute with test data
test_data = {"customers": [...]}
results = runtime.execute(workflow, inputs=test_data)

# Validate results
assert results["node_id"]["output_key"] == expected_value
```

#### Export Formats
```python
from kailash.utils.export import WorkflowExporter, ExportConfig

exporter = WorkflowExporter()

# Export to different formats
exporter.export_to_yaml(workflow, "workflow.yaml")      # Kailash YAML format
exporter.export_to_json(workflow, "workflow.json")      # JSON representation

# Export with custom configuration
config = ExportConfig(
    include_metadata=True,
    container_tag="latest"
)
exporter.export_to_kailash(workflow, "deployment.yaml", config=config)
```

### 🎨 Visualization

```python
from kailash.workflow.visualization import WorkflowVisualizer

# Visualize workflow structure
visualizer = WorkflowVisualizer()
visualizer.visualize(workflow, output_path="workflow.png")

# Show in Jupyter notebook
visualizer.show(workflow)
```

## 💻 CLI Commands

The SDK includes a comprehensive CLI for workflow management:

```bash
# Project initialization
kailash init my-project --template data-pipeline

# Workflow operations
kailash validate workflow.yaml
kailash run workflow.yaml --inputs data.json
kailash export workflow.py --format kubernetes

# Task management
kailash tasks list --status running
kailash tasks show run-123
kailash tasks cancel run-123

# Development tools
kailash test workflow.yaml --data test_data.json
kailash debug workflow.yaml --breakpoint node-id
```

## 🏗️ Architecture

The SDK follows a clean, modular architecture:

```
kailash/
├── nodes/           # Node implementations and base classes
│   ├── base.py      # Abstract Node class
│   ├── data/        # Data I/O nodes
│   ├── transform/   # Transformation nodes
│   ├── logic/       # Business logic nodes
│   └── ai/          # AI/ML nodes
├── workflow/        # Workflow management
│   ├── graph.py     # DAG representation
│   └── visualization.py  # Visualization tools
├── runtime/         # Execution engines
│   ├── local.py     # Local execution
│   └── docker.py    # Docker execution (planned)
├── tracking/        # Monitoring and tracking
│   ├── manager.py   # Task management
│   └── storage/     # Storage backends
├── cli/             # Command-line interface
└── utils/           # Utilities and helpers
```

## 🧪 Testing

The SDK is thoroughly tested with comprehensive test suites:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=kailash --cov-report=html

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash-python-sdk

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"

# Set up pre-commit hooks
pre-commit install
```

### Code Quality

We maintain high code quality standards:

```bash
# Format code
black src/ tests/
isort src/ tests/

# Type checking
mypy src/

# Linting
flake8 src/ tests/

# Run all checks
make quality
```

## 📈 Project Status

<table>
<tr>
<td>

**✅ Completed**
- Core node system
- Workflow builder
- Local execution
- Task tracking
- Export functionality
- CLI interface
- Immutable state management
- Unit tests
- Integration tests
- Example workflows

</td>
<td>

**🚧 In Progress**
- Docker runtime
- Advanced visualization
- Performance optimizations
- Additional node types

</td>
<td>

**📋 Planned**
- Cloud deployments
- Real-time monitoring
- Visual workflow editor
- Plugin system

</td>
</tr>
</table>

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- The Terrene Foundation team for the Kailash architecture
- All contributors who have helped shape this SDK
- The Python community for excellent tools and libraries

## 📞 Support

- 📋 [GitHub Issues](https://github.com/terrene-foundation/kailash-py/issues)
- 📧 Email: support@terrene.foundation
- 💬 Slack: [Join our community](https://terrene-foundation.slack.com/kailash-sdk)

---

<p align="center">
  Made with ❤️ by the Terrene Foundation Team
</p>