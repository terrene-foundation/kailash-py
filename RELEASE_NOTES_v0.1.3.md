# Release Notes - Kailash Python SDK v0.1.3

**Release Date:** June 3, 2025

## 🎉 Overview

Version 0.1.3 introduces powerful workflow composition and API capabilities to the Kailash Python SDK. The highlight features are the new WorkflowNode for hierarchical workflow composition and the Workflow API Wrapper that transforms any workflow into a production-ready REST API.

## ✨ Key Features

### 1. WorkflowNode - Hierarchical Workflow Composition

The new `WorkflowNode` class enables workflows to be wrapped and used as single nodes within other workflows, creating powerful abstraction and reusability patterns.

**Key Capabilities:**
- 🔄 **Workflow Reusability**: Package complex workflows as reusable components
- 🎯 **Automatic Parameter Discovery**: Intelligently detects inputs from entry nodes
- 📤 **Dynamic Output Mapping**: Maps outputs from workflow exit nodes
- 📁 **Multiple Loading Methods**: Load from instances, YAML/JSON files, or dictionaries
- 🔧 **Custom Mapping**: Define custom input/output parameter mappings
- ⚡ **Lazy Loading**: Runtime created only when needed to avoid circular imports

**Example:**
```python
from kailash.workflow import Workflow
from kailash.nodes.logic import WorkflowNode

# Create a reusable data processing workflow
data_processor = Workflow("processor")
# ... add nodes to workflow ...

# Wrap it as a node
processor_node = WorkflowNode(workflow=data_processor)

# Use in a larger workflow
main_workflow = Workflow("main")
main_workflow.add_node("process", processor_node)
main_workflow.add_node("analyze", analyzer_node)
main_workflow.connect("process", "analyze")
```

### 2. Workflow API Wrapper - Instant REST APIs

Transform any Kailash workflow into a production-ready REST API with just 3 lines of code:

```python
from kailash.api.workflow_api import WorkflowAPI

api = WorkflowAPI(workflow)
api.run(port=8000)  # Your workflow is now a REST API!
```

**Features:**
- 🌐 **Automatic Endpoints**: `/execute`, `/workflow/info`, `/health`, `/docs`
- ⚡ **Execution Modes**: Synchronous and asynchronous execution
- 📊 **OpenAPI Documentation**: Automatic API documentation generation
- 🔒 **Production Ready**: SSL support, multiple workers, customizable configurations
- 🔌 **WebSocket Support**: Real-time updates for long-running workflows
- 🎯 **Specialized APIs**: Domain-specific endpoints for RAG, data processing, etc.

## 📈 Improvements

### Documentation
- Updated README with comprehensive WorkflowNode examples
- Added Workflow API Wrapper section with usage patterns
- Enhanced API documentation with workflow composition patterns
- Updated test count badge to reflect 761 passing tests

### Code Quality
- Consolidated workflow nesting examples into single comprehensive file
- Replaced file I/O dependent nodes with mock nodes for better reliability
- Fixed parameter validation in WorkflowNode for dynamic structures
- Resolved import ordering and linting issues

## 🧪 Testing

- Added 15 comprehensive tests for WorkflowNode functionality
- All 761 tests passing
- Complete example file with 5 different workflow composition patterns

## 🚀 Getting Started

### Install/Upgrade
```bash
pip install --upgrade kailash
```

### Quick Example - Hierarchical Workflows
```python
from kailash.workflow import Workflow
from kailash.nodes.logic import WorkflowNode
from kailash.runtime.local import LocalRuntime

# Create inner workflow
inner = Workflow("data_processor")
# ... build workflow ...

# Wrap and use in larger workflow
processor = WorkflowNode(workflow=inner)
main = Workflow("main")
main.add_node("process", processor)

# Execute
runtime = LocalRuntime()
results, _ = runtime.execute(main)
```

### Quick Example - REST API
```python
from kailash.api.workflow_api import WorkflowAPI

# Any workflow becomes an API
api = WorkflowAPI(my_workflow)
api.run()  # Access at http://localhost:8000/docs
```

## 📋 Complete Changelog

See [CHANGELOG.md](CHANGELOG.md) for the complete list of changes.

## 🙏 Acknowledgments

Thanks to all contributors who helped make this release possible!

---

For questions or issues, please visit our [GitHub repository](https://github.com/terrene-foundation/kailash-py).
