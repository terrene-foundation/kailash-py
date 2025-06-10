# Kailash SDK Examples - Feature Testing & Validation

This directory contains **technical examples for SDK development and testing**. These examples are designed to validate individual features and components during SDK development.

> **Looking for production-ready workflows?** Check out [sdk-users/workflows/](../sdk-users/workflows/) for business-focused, production-ready workflow patterns.

## 📁 Directory Structure (Session 063 Update)

**Naming Convention**: All example folders end with `_examples` for easy test runner detection.

### feature_examples/ (renamed from feature-tests/)
Technical examples organized by feature area for SDK development testing:

#### nodes/
Individual node feature validation:
- **data-nodes/** - CSV, JSON, SQL, Directory readers/writers
- **ai-nodes/** - LLM agents, embeddings, A2A coordination
- **logic-nodes/** - Switch, merge, conditional routing
- **code-nodes/** - PythonCode, custom node creation

#### workflows/
Workflow construction and execution patterns:
- **basic/** - Simple DAG workflows
- **cyclic/** - Iterative and cyclic patterns
- **parallel/** - Concurrent execution

#### integrations/
External system integration testing:
- **mcp/** - MCP client/server examples
- **api/** - REST, GraphQL, webhooks
- **auth/** - Access control, security
- **studio/** - Workflow Studio integration

#### runtime/
Runtime and execution testing:
- **local/** - Local runtime features
- **docker/** - Container runtime (when available)
- **parallel/** - Parallel execution
- **visualization/** - Dashboards and reporting

### test-harness/
Testing utilities and helpers:
- **fixtures/** - Test data and configurations
- **validators/** - Example validation utilities
- **runners/** - Test execution helpers

## 🎯 Usage Guidelines

### For SDK Contributors
1. **When developing a new feature**: Create a minimal example in the appropriate feature_examples/ subdirectory
2. **Test the feature**: Run your example to ensure end-to-end functionality works
3. **Run unit tests**: Use pytest to test individual components
4. **Validate all examples**: Run `python examples/utils/test_runner.py`

### For Workflow Developers
**You're in the wrong place!** 
- For production workflows → [sdk-users/workflows/](../sdk-users/workflows/)
- For workflow patterns → [sdk-users/patterns/](../sdk-users/patterns/)
- For quick start → [sdk-users/essentials/](../sdk-users/essentials/)

## 🧪 Testing Examples

### Run all examples validation:
```bash
python examples/utils/test_runner.py
```

### Run specific feature tests:
```bash
# Test a specific example
python examples/feature_examples/nodes/data-nodes/csv_reader_test.py

# Test all node examples  
python examples/utils/test_runner.py

# Run from examples directory
cd examples && python utils/test_runner.py
```

## 📝 Example Structure

Each example should follow this pattern:

```python
#!/usr/bin/env python3
"""
Feature: [Feature being tested]
Purpose: [What this example validates]
Expected: [Expected behavior/output]
"""

from kailash import Workflow
from kailash.nodes.xxx import XxxNode

def test_feature():
    """Test specific feature functionality."""
    # Setup
    workflow = Workflow("test_id", "Test Feature X")
    
    # Test implementation
    node = XxxNode(...)
    workflow.add_node("test", node)
    
    # Validation
    results = runtime.execute(workflow)
    assert results["test"]["output"] == expected_value
    
    print("✓ Feature test passed")

if __name__ == "__main__":
    test_feature()
```

## 🚫 What NOT to Put Here

1. **Business workflows** - Those belong in sdk-users/workflows/
2. **User documentation** - Use sdk-users/developer/
3. **Production configurations** - Use sdk-users/templates/
4. **Large datasets** - Use data/ with proper utilities

## 📚 Related Documentation

- [SDK Developer Guide](../# contrib (removed)/CLAUDE.md)
- [Production Workflows](../sdk-users/workflows/README.md)
- [Testing Guidelines](../# contrib (removed)/development/instructions/testing-guidelines.md)
- [Node Catalog](../sdk-users/nodes/comprehensive-node-catalog.md)