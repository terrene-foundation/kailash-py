# Developer Guide

This directory contains comprehensive guides and resources for developing with the Kailash SDK.

## 🚨 Start Here: [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
Critical rules, common patterns, and quick-fix templates for immediate use.

## 📁 Contents

### Core Guides
- **[01-node-basics.md](01-node-basics.md)** - Creating nodes, base classes, lifecycle
- **[02-parameter-types.md](02-parameter-types.md)** - ⚠️ CRITICAL: Type constraints to avoid errors
- **[03-common-patterns.md](03-common-patterns.md)** - Data processing, API integration, transforms
- **[04-pythoncode-node.md](04-pythoncode-node.md)** - ⚠️ Input variable exclusion, serialization
- **[05-directory-reader.md](05-directory-reader.md)** - File discovery best practices
- **[06-enhanced-mcp-server.md](06-enhanced-mcp-server.md)** - 🆕 Production-ready MCP servers with caching & metrics
- **[07-troubleshooting.md](07-troubleshooting.md)** - Common errors and solutions
- **[08-async-database-patterns.md](08-async-database-patterns.md)** - High-performance async database operations
- **[09-workflow-resilience.md](09-workflow-resilience.md)** - 🆕 Enterprise reliability with retry, fallback, circuit breakers
- **[10-credential-management.md](10-credential-management.md)** - 🆕 Secure credential handling with multi-source support
- **[11-sharepoint-multi-auth.md](11-sharepoint-multi-auth.md)** - 🆕 SharePoint with certificate, managed identity, and more

### Other Resources
- **[pre-commit-hooks.md](pre-commit-hooks.md)** - Git hooks for code quality
- **[examples/](examples/)** - Working code examples demonstrating patterns

## 🚀 Quick Start Paths

### Creating a Custom Node
1. Read [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for critical rules
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
2. Review [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for common mistakes
3. Look for your error in the troubleshooting guide

### Building Resilient Workflows
1. Read [09-workflow-resilience.md](09-workflow-resilience.md)
2. Add retry policies and fallbacks
3. Configure circuit breakers for external services

### Managing Credentials
1. Start with [10-credential-management.md](10-credential-management.md)
2. Never hardcode credentials
3. Use appropriate credential sources (vault for production)

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
