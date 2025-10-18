---
name: core-sdk
description: "Kailash Core SDK fundamentals including workflow creation, node patterns, connections, runtime execution, parameter passing, error handling, cyclic workflows, async patterns, MCP integration, and installation. Use when asking about 'workflow basics', 'core sdk', 'create workflow', 'workflow builder', 'node patterns', 'connections', 'runtime', 'parameters', 'imports', 'installation', 'getting started', 'workflow execution', 'async workflows', 'error handling', 'cyclic workflows', 'PythonCode node', 'SwitchNode', or 'MCP integration'."
---

# Kailash Core SDK - Foundational Skills

Comprehensive guide to Kailash Core SDK fundamentals for workflow automation and integration.

## Overview

The Core SDK provides the foundational building blocks for creating custom workflows with fine-grained control. This skill collection covers:

- **Workflow Creation**: Building workflows from scratch
- **Node Patterns**: Using the 110+ available nodes
- **Connections**: Linking nodes and passing data
- **Runtime Execution**: Running workflows synchronously and asynchronously
- **Parameter Passing**: Managing data flow between nodes
- **Error Handling**: Robust error management patterns
- **Advanced Features**: Cyclic workflows, async patterns, MCP integration

## Quick Start

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("NodeName", "id", {"param": "value"})
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Reference Documentation

### Getting Started
- **[workflow-quickstart](workflow-quickstart.md)** - Create basic workflows with WorkflowBuilder
- **[kailash-installation](kailash-installation.md)** - Installation and setup guide
- **[kailash-imports](kailash-imports.md)** - Import patterns and module organization

### Core Patterns
- **[node-patterns-common](node-patterns-common.md)** - Common node usage patterns
- **[connection-patterns](connection-patterns.md)** - Linking nodes and data flow
- **[param-passing-quick](param-passing-quick.md)** - Parameter passing strategies
- **[runtime-execution](runtime-execution.md)** - Executing workflows (sync/async)

### Advanced Topics
- **[async-workflow-patterns](async-workflow-patterns.md)** - Asynchronous workflow execution
- **[cycle-workflows-basics](cycle-workflows-basics.md)** - Cyclic workflow patterns
- **[error-handling-patterns](error-handling-patterns.md)** - Error management strategies
- **[switchnode-patterns](switchnode-patterns.md)** - Conditional routing with SwitchNode
- **[pythoncode-best-practices](pythoncode-best-practices.md)** - PythonCode node best practices
- **[mcp-integration-guide](mcp-integration-guide.md)** - Model Context Protocol integration

## Key Concepts

### WorkflowBuilder Pattern
- String-based node API: `workflow.add_node("NodeName", "id", {})`
- Always call `.build()` before execution
- Never `workflow.execute(runtime)` - always `runtime.execute(workflow.build())`

### Runtime Selection
- **AsyncLocalRuntime**: For Docker/FastAPI (async contexts)
- **LocalRuntime**: For CLI/scripts (sync contexts)
- **get_runtime()**: Auto-detection helper

### Critical Rules
- ✅ ALWAYS: `runtime.execute(workflow.build())`
- ✅ String-based nodes: `workflow.add_node("NodeName", "id", {})`
- ✅ 4-parameter connections: `(source_id, source_param, target_id, target_param)`
- ❌ NEVER: `workflow.execute(runtime)`
- ❌ NEVER: Instance-based nodes

## When to Use This Skill

Use this skill when you need to:
- Create custom workflows from scratch
- Understand workflow fundamentals
- Learn node patterns and connections
- Set up runtime execution
- Handle errors in workflows
- Implement cyclic or async patterns
- Integrate with MCP
- Get started with Kailash SDK

## Related Skills

- **[02-dataflow](../02-dataflow/SKILL.md)** - Database operations framework
- **[03-nexus](../03-nexus/SKILL.md)** - Multi-channel platform framework
- **[04-kaizen](../04-kaizen/SKILL.md)** - AI agent framework
- **[06-cheatsheets](../06-cheatsheets/SKILL.md)** - Quick reference patterns
- **[08-nodes-reference](../08-nodes-reference/SKILL.md)** - Node reference
- **[09-workflow-patterns](../09-workflow-patterns/SKILL.md)** - Workflow templates
- **[17-gold-standards](../17-gold-standards/SKILL.md)** - Best practices and standards

## Support

For complex workflows or debugging, invoke:
- `pattern-expert` - Workflow patterns and cyclic debugging
- `sdk-navigator` - Find specific nodes or patterns
- `testing-specialist` - Test workflow implementations
