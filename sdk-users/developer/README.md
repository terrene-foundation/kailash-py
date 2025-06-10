# Developer Guide

This directory contains comprehensive guides and resources for developing with the Kailash SDK.

## 🚨 Start Here: [CLAUDE.md](CLAUDE.md)
Quick reference with critical rules, common patterns, and node selection guide.

## 📁 Contents

### Core Guides
- **[01-node-basics.md](01-node-basics.md)** - Creating nodes, base classes, lifecycle
- **[02-parameter-types.md](02-parameter-types.md)** - ⚠️ CRITICAL: Type constraints to avoid errors
- **[03-common-patterns.md](03-common-patterns.md)** - Data processing, API integration, transforms
- **[04-pythoncode-node.md](04-pythoncode-node.md)** - ⚠️ Input variable exclusion, serialization
- **[05-directory-reader.md](05-directory-reader.md)** - File discovery best practices
- **[06-document-processing.md](06-document-processing.md)** - Multi-file workflow patterns
- **[07-troubleshooting.md](07-troubleshooting.md)** - Common errors and solutions

### Other Resources
- **[pre-commit-hooks.md](pre-commit-hooks.md)** - Git hooks for code quality
- **[examples/](examples/)** - Working code examples demonstrating patterns

## 🚀 Quick Start Paths

### Creating a Custom Node
1. Read [CLAUDE.md](CLAUDE.md) for critical rules
2. Follow [01-node-basics.md](01-node-basics.md)
3. Check [02-parameter-types.md](02-parameter-types.md) for type constraints
4. See [examples/basic_node.py](examples/basic_node.py)

### Using PythonCodeNode
1. **MUST READ**: [04-pythoncode-node.md](04-pythoncode-node.md)
2. Understand input variable exclusion
3. See [examples/pythoncode_patterns.py](examples/pythoncode_patterns.py)

### File Processing Workflows
1. Start with [05-directory-reader.md](05-directory-reader.md)
2. Learn patterns in [06-document-processing.md](06-document-processing.md)
3. See [examples/directory_reader.py](examples/directory_reader.py)

### Debugging Issues
1. Check [07-troubleshooting.md](07-troubleshooting.md)
2. Review [CLAUDE.md](CLAUDE.md) for common mistakes
3. Look for your error in the troubleshooting guide

## ⚠️ Critical Knowledge

### PythonCodeNode Input Exclusion
Variables passed as inputs are EXCLUDED from outputs!
```python
# WRONG
workflow.connect("n1", "n2", mapping={"result": "result"})

# CORRECT
workflow.connect("n1", "n2", mapping={"result": "input_data"})
```

### Node Naming Convention
ALL nodes must end with "Node":
- ✅ `CSVReaderNode`
- ❌ `CSVReader`

### Parameter Types
Only use basic types: `str`, `int`, `float`, `bool`, `list`, `dict`, `Any`
- ❌ `List[str]`, `Optional[int]`, `Union[str, int]`

## 📖 Related Documentation

- [API Reference](../reference/api/)
- [Workflow Patterns](../reference/pattern-library/)
- [Testing Guidelines](../instructions/testing-guidelines.md)
- [Coding Standards](../instructions/coding-standards.md)
- [Mistakes Archive](../mistakes/)

---

*For user-facing SDK documentation, see the [docs/](../../docs/) directory.*