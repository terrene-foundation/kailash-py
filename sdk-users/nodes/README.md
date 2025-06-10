# Kailash Python SDK - Node Catalog

**Version**: 0.1.4 | **Last Updated**: 2025-01-09

This directory contains the complete node catalog for the Kailash Python SDK, organized by category.

**Total Nodes**: 66+ nodes across 8 categories

## 🎯 Quick Start

**[comprehensive-node-catalog.md](comprehensive-node-catalog.md)** - Complete reference with all nodes and their use cases. **Start here to find the right node for your task!**

## 📁 Node Catalog Files

| File | Category | Node Count | Description |
|------|----------|------------|-------------|
| [comprehensive-node-catalog.md](comprehensive-node-catalog.md) | **All Nodes** | **66+** | **Complete reference with use cases** |
| [01-base-nodes.md](01-base-nodes.md) | Base Classes | 3 | Abstract base classes and core interfaces |
| [02-ai-nodes.md](02-ai-nodes.md) | AI & ML | 15+ | LLM agents, embeddings, A2A communication, self-organizing |
| [03-data-nodes.md](03-data-nodes.md) | Data I/O | 15+ | File readers/writers, databases, streaming, SharePoint |
| [04-api-nodes.md](04-api-nodes.md) | API Integration | 10+ | HTTP, REST, GraphQL, authentication |
| [05-logic-nodes.md](05-logic-nodes.md) | Control Flow | 5 | Switch, merge, workflow composition |
| [06-transform-nodes.md](06-transform-nodes.md) | Data Processing | 8+ | Filters, formatters, chunkers, processors |
| [07-code-nodes.md](07-code-nodes.md) | Code Execution | 6+ | Python code execution, MCP tools |
| [08-utility-nodes.md](08-utility-nodes.md) | Utilities | 5+ | Visualization, security, tracking |

## 🚀 Quick Navigation

### By Use Case
- **Building AI Workflows** → [02-ai-nodes.md](02-ai-nodes.md)
- **Data Processing** → [03-data-nodes.md](03-data-nodes.md) + [06-transform-nodes.md](06-transform-nodes.md)
- **API Integration** → [04-api-nodes.md](04-api-nodes.md)
- **Control Flow** → [05-logic-nodes.md](05-logic-nodes.md)
- **Custom Code** → [07-code-nodes.md](07-code-nodes.md)

### By Module
- `from kailash.nodes.ai import ...` → [02-ai-nodes.md](02-ai-nodes.md)
- `from kailash.nodes.data import ...` → [03-data-nodes.md](03-data-nodes.md)
- `from kailash.nodes.api import ...` → [04-api-nodes.md](04-api-nodes.md)
- `from kailash.nodes.logic import ...` → [05-logic-nodes.md](05-logic-nodes.md)

## 📋 Node Naming Convention

All node classes in the Kailash SDK follow a consistent naming convention:

### Standard: ClassNameNode

**Examples**:
- ✅ `CSVReaderNode` - Correct
- ✅ `LLMAgentNode` - Correct
- ✅ `SwitchNode` - Correct
- ❌ `CSVReader` - Incorrect (missing Node suffix)
- ❌ `Filter` - Incorrect (missing Node suffix)

### Benefits:
1. **Consistency**: Easy to identify node classes
2. **Validation**: Automated tools can check naming
3. **Discovery**: Better IDE autocomplete
4. **Documentation**: Clear distinction from other classes

## 🔍 Finding Nodes

1. **Know the category?** → Check the corresponding file number
2. **Know the use case?** → Use Quick Navigation above
3. **Searching for a class?** → Check the table for the right category
4. **Need examples?** → Each node includes usage examples

## See Also
- [API Reference](../api/README.md) - Detailed API documentation
- [Validation Guide](../validation/validation-guide.md) - Node usage rules
- [Cheatsheet](../cheatsheet/README.md) - Quick code snippets
