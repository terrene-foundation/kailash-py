# Developer Guide

*Comprehensive technical documentation for Kailash SDK development*

## 🚀 Quick Start

**Building an app?** Start with these in order:
1. **[01-fundamentals.md](01-fundamentals.md)** - Core concepts and basics
2. **[02-workflows.md](02-workflows.md)** - Building and connecting workflows
3. **[10-parameter-passing-guide.md](10-parameter-passing-guide.md)** - **NEW!** Master parameter flow (fixes #1 issue)

**Having issues?** Jump to:
- **[05-troubleshooting.md](05-troubleshooting.md)** - Common errors and solutions
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Critical rules and patterns

## 📚 Complete Guide Index

### Core Development Guides (Start Here)
1. **[01-fundamentals.md](01-fundamentals.md)** - SDK basics, nodes, LocalRuntime
2. **[02-workflows.md](02-workflows.md)** - Workflow construction and execution
3. **[03-advanced-features.md](03-advanced-features.md)** - Cycles, agents, enterprise features
4. **[04-production.md](04-production.md)** - Deployment, monitoring, security
5. **[05-troubleshooting.md](05-troubleshooting.md)** - Error resolution guide
6. **[06-custom-development.md](06-custom-development.md)** - Creating custom nodes

### Specialized Guides
7. **[07-comprehensive-rag-guide.md](07-comprehensive-rag-guide.md)** - RAG implementation patterns
8. **[08-async-workflow-builder.md](08-async-workflow-builder.md)** - Async-first workflow patterns
9. **[08b-resource-registry-guide.md](08b-resource-registry-guide.md)** - Resource management
10. **[09-unified-async-runtime-guide.md](09-unified-async-runtime-guide.md)** - AsyncLocalRuntime (2-10x performance)
11. **[10-parameter-passing-guide.md](10-parameter-passing-guide.md)** ⭐ - **Complete parameter flow reference**
12. **[11-testing-production-quality.md](11-testing-production-quality.md)** - Testing strategies
13. **[12-async-testing-framework-guide.md](12-async-testing-framework-guide.md)** - Production-certified async testing
14. **[13-connection-pool-guide.md](13-connection-pool-guide.md)** - Database connection management
15. **[14-enhanced-gateway-guide.md](14-enhanced-gateway-guide.md)** - Enterprise gateway architecture
16. **[15-enhanced-gateway-user-guide.md](15-enhanced-gateway-user-guide.md)** - Using the gateway

### Quick References
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Critical rules and common patterns
- **[examples/](examples/)** - Working code examples

## 🔥 Key Updates (v0.5.1+)

### Parameter Passing Fix
Initial parameters in cycles are now preserved throughout ALL iterations:
```python
# These parameters are available in every cycle iteration
runtime.execute(workflow, parameters={
    "optimizer": {
        "learning_rate": 0.01,  # No longer lost after iteration 0!
        "target": 0.95          # Consistent across all iterations
    }
})
```
See [10-parameter-passing-guide.md](10-parameter-passing-guide.md) for complete details.

### Unified Runtime
```python
from kailash.runtime.local import LocalRuntime  # Handles sync + async + enterprise
runtime = LocalRuntime()  # That's it!
```

### Dot Notation Mapping
```python
workflow.connect("processor", "writer", mapping={
    "result.data": "input_data",
    "result.stats.count": "record_count"
})
```

## ⚠️ Critical Rules

### 1. Node Initialization Order
```python
class MyNode(Node):
    def __init__(self, name, **kwargs):
        # Set attributes FIRST
        self.threshold = kwargs.get("threshold", 0.8)
        # Then call super()
        super().__init__(name=name)
```

### 2. Declare ALL Parameters
```python
def get_parameters(self):
    return {
        "data": NodeParameter(type=list, required=True),
        "config": NodeParameter(type=dict, required=False, default={})
        # Must declare EVERY parameter the node will use
    }
```

### 3. Use Basic Types Only
```python
# ✅ CORRECT
"items": NodeParameter(type=list, required=True)

# ❌ WRONG - No generic types!
"items": NodeParameter(type=List[str], required=True)
```

## 🎯 Common Workflows

### Data Processing Pipeline
```python
workflow = Workflow("data-pipeline")
workflow.add_node("reader", CSVReaderNode())
workflow.add_node("processor", DataTransformerNode())
workflow.add_node("writer", CSVWriterNode())

workflow.connect("reader", "processor")
workflow.connect("processor", "writer", mapping={"transformed_data": "data"})
```

### Cyclic Optimization
```python
workflow = Workflow("optimization")
workflow.add_node("optimizer", OptimizerNode())
workflow.connect("optimizer", "optimizer",
    cycle=True,
    max_iterations=20,
    convergence_check="converged == True"
)
```

### API Integration
```python
workflow = Workflow("api-workflow")
workflow.add_node("api", HTTPRequestNode())
workflow.add_node("processor", PythonCodeNode(
    code="result = {'parsed': json.loads(response.get('body', '{}'))}"
))
workflow.connect("api", "processor", mapping={"response": "response"})
```

## 📋 Development Paths

### Building a Custom Node
1. Read [06-custom-development.md](06-custom-development.md)
2. Check parameter declaration in [10-parameter-passing-guide.md](10-parameter-passing-guide.md)
3. See examples in [examples/basic_node.py](examples/basic_node.py)

### Testing Your Workflow
1. Start with [12-async-testing-framework-guide.md](12-async-testing-framework-guide.md)
2. Use Docker infrastructure from `tests/docker-compose.test.yml`
3. Check [11-testing-production-quality.md](11-testing-production-quality.md) for strategies

### Debugging Issues
1. Check [05-troubleshooting.md](05-troubleshooting.md) first
2. Review parameter flow in [10-parameter-passing-guide.md](10-parameter-passing-guide.md)
3. Use debug nodes from [QUICK_REFERENCE.md](QUICK_REFERENCE.md)

### Production Deployment
1. Read [04-production.md](04-production.md) for deployment guide
2. Set up monitoring per [14-enhanced-gateway-guide.md](14-enhanced-gateway-guide.md)
3. Configure connection pools via [13-connection-pool-guide.md](13-connection-pool-guide.md)

## 🔗 Related Resources

- **[Cheatsheets](../cheatsheet/)** - Quick copy-paste patterns
- **[Node Catalog](../nodes/)** - Complete node reference
- **[Workflows](../workflows/)** - Production-ready examples
- **[API Reference](../api/)** - Full API documentation

---

*For the latest updates and migration guides, see [migration-guides/](../migration-guides/)*
