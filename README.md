# Kailash Python SDK

<p align="center">
  <a href="https://pypi.org/project/kailash/"><img src="https://img.shields.io/pypi/v/kailash.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/kailash/"><img src="https://img.shields.io/pypi/pyversions/kailash.svg" alt="Python versions"></a>
  <a href="https://pepy.tech/project/kailash"><img src="https://static.pepy.tech/badge/kailash" alt="Downloads"></a>
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black">
  <img src="https://img.shields.io/badge/tests-751%20passing-brightgreen.svg" alt="Tests: 751 passing">
  <img src="https://img.shields.io/badge/coverage-100%25-brightgreen.svg" alt="Coverage: 100%">
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
- 📊 **Real-time Monitoring**: Live dashboards with WebSocket streaming and performance metrics
- 🧩 **Extensible**: Easy to create custom nodes for domain-specific operations
- ⚡ **Fast Installation**: Uses `uv` for lightning-fast Python package management
- 🤖 **AI-Powered**: Complete LLM agents, embeddings, and hierarchical RAG architecture
- 🧠 **Retrieval-Augmented Generation**: Full RAG pipeline with intelligent document processing
- 🌐 **REST API Wrapper**: Expose any workflow as a production-ready API in 3 lines
- 🚪 **Multi-Workflow Gateway**: Manage multiple workflows through unified API with MCP integration
- 🤖 **Self-Organizing Agents**: Autonomous agent pools with intelligent team formation and convergence detection
- 🧠 **Agent-to-Agent Communication**: Shared memory pools and intelligent caching for coordinated multi-agent systems
- 🔒 **Production Security**: Comprehensive security framework with path traversal prevention, code sandboxing, and audit logging
- 🎨 **Visual Workflow Builder**: Kailash Workflow Studio - drag-and-drop interface for creating and managing workflows (coming soon)
- 🔁 **Cyclic Workflows (v0.2.0)**: Universal Hybrid Cyclic Graph Architecture with 30,000+ iterations/second performance
- 🛠️ **Developer Tools**: CycleAnalyzer, CycleDebugger, CycleProfiler for production-ready cyclic workflows
- 📈 **High Performance**: Optimized execution engine supporting 100,000+ iteration workflows
- 📁 **Enhanced Documentation (v0.2.2)**: Reorganized structure with production-ready workflow library

## 🎯 Who Is This For?

The Kailash Python SDK is designed for:

- **AI Business Coaches (ABCs)** who need to prototype workflows quickly
- **Data Scientists** building ML pipelines compatible with production infrastructure
- **Engineers** who want to test Kailash workflows locally before deployment
- **Teams** looking to standardize their workflow development process

## 🚀 Quick Start

### Installation

**Requirements:** Python 3.11 or higher

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# For users: Install from PyPI
pip install kailash

# For developers: Clone and sync
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash-python-sdk
uv sync
```

### Your First Workflow

```python
from kailash.workflow import Workflow
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime
import pandas as pd

# Create a workflow
workflow = Workflow("customer_analysis", name="customer_analysis")

# Add data reader
reader = CSVReaderNode(file_path="customers.csv")
workflow.add_node("read_customers", reader)

# Add custom processing using Python code
def analyze_customers(data):
    """Analyze customer data and compute metrics."""
    df = pd.DataFrame(data)
    # Convert total_spent to numeric
    df['total_spent'] = pd.to_numeric(df['total_spent'])
    return {
        "result": {
            "total_customers": len(df),
            "avg_spend": df["total_spent"].mean(),
            "top_customers": df.nlargest(10, "total_spent").to_dict("records")
        }
    }

processor = PythonCodeNode(code=analyze_customers)
workflow.add_node("analyze", processor)

# Connect nodes
workflow.connect("read_customers", "analyze", mapping={"data": "data"})

# Run locally
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "read_customers": {"file_path": "customers.csv"}
})

print(f"Total customers: {results['analyze']['result']['total_customers']}")
print(f"Average spend: ${results['analyze']['result']['avg_spend']:.2f}")
```

### Export to Production

```python
# Export to Kailash container format
from kailash.utils.export import export_workflow

export_workflow(workflow, "customer_analysis.yaml")
```

## 📚 Documentation

### For SDK Users

**Build solutions with the SDK:**
- `sdk-users/` - Everything you need to build with Kailash
  - `developer/` - Node creation patterns and troubleshooting
  - `workflows/` - Production-ready workflow library (NEW in v0.2.2)
    - Quick-start patterns (30-second workflows)
    - Industry-specific solutions (healthcare, finance)
    - Enterprise integration patterns
  - `essentials/` - Quick reference and cheatsheets
  - `nodes/` - Comprehensive node catalog (66+ nodes)
  - `patterns/` - Architectural patterns

### For SDK Contributors

**Develop the SDK itself:**
- `# contrib (removed)/` - Internal SDK development resources
  - `architecture/` - ADRs and design decisions
  - `project/` - TODOs and development tracking
  - `training/` - LLM training examples

### Shared Resources

- `shared/` - Resources for both users and contributors
  - `mistakes/` - Common error patterns and solutions
  - `frontend/` - UI development resources

### Quick Links

- [SDK User Guide](sdk-users/README.md) - Build with the SDK
- [SDK Contributor Guide](# contrib (removed)/README.md) - Develop the SDK
- [API Documentation](https://terrene-foundation.github.io/kailash-python-sdk)
- [Examples](examples/)
- [Release Notes](CHANGELOG.md)

## 🔥 Advanced Features

### Cyclic Workflows (Enhanced in v0.2.2)

Build iterative workflows with the new CycleBuilder API:

```python
# Create an optimization cycle
workflow.create_cycle("optimization_loop")
    .connect("processor", "processor")
    .max_iterations(100)
    .converge_when("quality >= 0.95")
    .timeout(30)
    .build()
```

### Self-Organizing Agent Pools

Create teams of AI agents that autonomously coordinate:

```python
from kailash.nodes.ai import SelfOrganizingAgentPoolNode

agent_pool = SelfOrganizingAgentPoolNode(
    formation_strategy="capability_matching",
    convergence_strategy="quality_voting",
    min_agents=3,
    max_agents=10
)
workflow.add_node("agent_team", agent_pool)
```

### Hierarchical RAG Pipeline

Build sophisticated document processing systems:

```python
from kailash.nodes.data import DocumentSourceNode, HierarchicalChunkerNode
from kailash.nodes.ai import EmbeddingGeneratorNode

# Build a complete RAG pipeline
workflow.add_node("docs", DocumentSourceNode(directory="./knowledge"))
workflow.add_node("chunker", HierarchicalChunkerNode(chunk_size=512))
workflow.add_node("embedder", EmbeddingGeneratorNode(provider="openai"))
```

### REST API Wrapper

Transform any workflow into a production API:

```python
from kailash.api import WorkflowAPI

# Create API from workflow
api = WorkflowAPI(workflow, host="0.0.0.0", port=8000)
api.run()

# Your workflow is now available at:
# POST http://localhost:8000/execute
# GET http://localhost:8000/workflow/info
```

## 🏗️ Key Components

### Nodes (60+ built-in)

- **Data**: CSVReaderNode, JSONReaderNode, SQLDatabaseNode, DirectoryReaderNode
- **Transform**: DataTransformer, DataFrameFilter, DataFrameJoiner
- **AI/ML**: LLMAgentNode, EmbeddingGeneratorNode, A2ACoordinatorNode
- **API**: RESTClientNode, GraphQLNode, AuthNode
- **Logic**: SwitchNode, MergeNode, ConvergenceCheckerNode
- **Code**: PythonCodeNode, WorkflowNode

### Runtimes

- **LocalRuntime**: Test workflows on your machine
- **DockerRuntime**: Run in containers (coming soon)
- **ParallelRuntime**: Execute nodes concurrently
- **CyclicWorkflowExecutor**: Optimized for iterative workflows

### Visualization

- **Mermaid diagrams**: Workflow structure visualization
- **Real-time dashboard**: Monitor execution with WebSocket streaming
- **Performance metrics**: Track execution time, resource usage

## 🧪 Testing Your Workflows

```python
# Use the testing runtime for unit tests
from kailash.runtime.testing import TestingRuntime

runtime = TestingRuntime()
runtime.set_mock_result("read_customers", {"data": test_data})
results, run_id = runtime.execute(workflow)
assert results["analyze"]["result"]["total_customers"] == len(test_data)
```

## 🚢 Production Deployment

1. **Export your workflow**:
   ```python
   export_workflow(workflow, "workflow.yaml", format="kailash")
   ```

2. **Deploy to Kailash**:
   ```bash
   kailash deploy workflow.yaml --environment production
   ```

3. **Monitor in real-time**:
   ```python
   from kailash.visualization import DashboardServer
   
   server = DashboardServer(port=8080)
   server.start()
   # Open http://localhost:8080 for live monitoring
   ```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash-python-sdk

# Install with development dependencies
uv sync

# Run tests
pytest

# Run linting
black .
isort .
ruff check .
```

## 📈 Project Status

- ✅ Core workflow engine
- ✅ 60+ production-ready nodes
- ✅ Local and parallel runtimes
- ✅ Export to container format
- ✅ Real-time monitoring
- ✅ Comprehensive test suite (751 tests)
- ✅ Self-organizing agent systems
- ✅ Hierarchical RAG architecture
- ✅ REST API wrapper
- ✅ Cyclic workflow support with CycleBuilder API
- ✅ Production security framework
- ✅ Comprehensive workflow library (v0.2.2)
- 🚧 Visual workflow builder (in progress)
- 🚧 Docker runtime
- 🚧 Cloud deployment tools

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

Built with ❤️ by the Terrene Foundation team for the Kailash ecosystem.

---

<p align="center">
  <strong>Ready to build your first workflow? Check out our <a href="examples/">examples</a> or dive into the <a href="sdk-users/README.md">documentation</a>!</strong>
</p>
