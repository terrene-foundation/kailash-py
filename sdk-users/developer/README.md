# Developer Guide - Navigation Hub

*Complete technical guide for building with Kailash SDK*

## 🎯 Learning Path

Follow these guides in order for complete mastery:

### Core Fundamentals (Start Here)
1. **[Fundamentals](01-fundamentals-*.md)** ⭐
   - Core concepts, parameters, connections, best practices (split into 4 focused files)
2. **[Workflows](02-workflows-*.md)** ⭐
   - Creation patterns, connections, execution (split into 2 focused files)
3. **[Advanced Features](03-advanced-features.md)**
   - Enterprise patterns, security, resilience
4. **[Production](04-production.md)**
   - Deployment, monitoring, security
5. **[Custom Development](05-custom-development.md)**
   - Build custom nodes and extensions

### Specialized Topics
- **[RAG Guide](06-comprehensive-rag-guide.md)** - Retrieval-augmented generation
- **[Async Workflow Builder](07-async-workflow-builder.md)** - High-performance patterns
- **[Resource Registry](08-resource-registry-guide.md)** - Resource management
- **[Admin Nodes](09-admin-nodes-guide.md)** - User/role management
- **[Unified Async Runtime](10-unified-async-runtime-guide.md)** - Async execution
- **[Parameter Passing](11-parameter-passing-guide.md)** - Complete parameter reference
- **[Testing Guide](12-testing-production-quality.md)** - Production testing
- **[Validation Framework](13-validation-framework-guide.md)** ⭐ **NEW** - Comprehensive validation & test-driven development
- **[WorkflowBuilder API Patterns](55-workflow-builder-api-patterns.md)** ⭐ **NEW** - Enhanced API flexibility & auto ID generation

### Troubleshooting
- **[Common Mistakes](../validation/common-mistakes.md)** ⭐ - Debug common issues quickly

## ⚡ Quick Start

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# 1. Create workflow
workflow = WorkflowBuilder()

# 2. Add nodes
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'processed': True}"
})

# 3. Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## 🔑 Key Concepts

- **WorkflowBuilder**: Use `WorkflowBuilder()` not `Workflow()`
- **Connections**: `add_connection(from_node, from_output, to_node, to_input)`
- **PythonCodeNode**: Wrap outputs in `result` key
- **Dot Notation**: Access nested data with `"result.data"`

## 🔗 Navigation

**Need help with something specific?**
- **Getting started** → [Fundamentals](01-fundamentals-core-concepts.md)
- **Building workflows** → [Workflows](02-workflows-creation.md)
- **Fixing errors** → [Common Mistakes](../validation/common-mistakes.md)
- **Production deployment** → [Production](04-production.md)
- **Custom nodes** → [Custom Development](05-custom-development.md)

**Advanced patterns:**
- **AI/RAG systems** → [RAG Guide](06-comprehensive-rag-guide.md)
- **High performance** → [Async Workflow Builder](07-async-workflow-builder.md)
- **Enterprise features** → [Admin Nodes](09-admin-nodes-guide.md)

## 📚 Reference

- **[Quick Reference](QUICK_REFERENCE.md)** - Cheat sheet for common patterns
- **[Node Selection Guide](../nodes/node-selection-guide.md)** - Choose the right nodes
- **[Cheatsheet](../cheatsheet/)** - Copy-paste code patterns

## 🗂️ All Available Guides

### Core (5 Essential Guides)
1. **Fundamentals** (split into 4 files):
   - [Core Concepts](01-fundamentals-core-concepts.md) ⭐
   - [Parameters](01-fundamentals-parameters.md)
   - [Connections](01-fundamentals-connections.md)
   - [Best Practices](01-fundamentals-best-practices.md)
2. **Workflows** (split into 2 files):
   - [Creation](02-workflows-creation.md) ⭐
   - [Connections](02-workflows-connections.md)
3. [Advanced Features](03-advanced-features.md)
4. [Production](04-production.md)
5. [Custom Development](05-custom-development.md)

### Specialized Features (17 Guides)
6. [RAG Guide](06-comprehensive-rag-guide.md)
7. [Async Workflow Builder](07-async-workflow-builder.md)
8. [Resource Registry](08-resource-registry-guide.md)
9. [Admin Nodes Guide](09-admin-nodes-guide.md)
10. [Unified Async Runtime Guide](10-unified-async-runtime-guide.md)
11. [Parameter Passing Guide](11-parameter-passing-guide.md)
12. [Testing Production Quality](12-testing-production-quality.md)
13. [Async Testing Framework](13-async-testing-framework.md)
14. [Connection Pool Guide](14-connection-pool-guide.md)
15. [Enhanced Gateway Guide](15-enhanced-gateway-guide.md)
16. [Production Hardening](16-production-hardening.md)
17. [MCP Development Guide](17-mcp-development-guide.md)
18. [Cycle Parameter Passing](18-cycle-parameter-passing.md)
19. [Intelligent Query Routing](19-intelligent-query-routing.md)
20. [Testing Async Workflows](20-testing-async-workflows.md)
21. [MCP Tool Execution](21-mcp-tool-execution.md)
22. [Workflow Parameter Injection](22-workflow-parameter-injection.md)

---

**Building with Kailash SDK?** Start with [Fundamentals](01-fundamentals-core-concepts.md) → [Workflows](02-workflows-creation.md) → [Production](04-production.md)
