# Kailash SDK LLM Reference Documentation

This directory contains lean, LLM-optimized reference documentation for the Kailash Python SDK. These documents are designed for quick lookup and automated code generation by AI assistants like Claude Code.

## Contents

### 1. **[API Reference](api/)**
Complete YAML-based API reference organized by module:
- [Core Workflow](api/01-core-workflow.yaml) - Workflow and WorkflowBuilder classes
- [Runtime](api/02-runtime.yaml) - Execution runtimes (Local, Docker, etc.)
- [AI Nodes](api/04-nodes-ai.yaml) - LLM agents, A2A communication, self-organizing
- [Data Nodes](api/05-nodes-data.yaml) - File I/O, databases, SharePoint integration
- [Logic Nodes](api/06-nodes-logic.yaml) - Control flow (Switch, Merge, WorkflowNode)
- [Security](api/09-security-access.yaml) - Security config and access control
- [Integrations](api/12-integrations.yaml) - API Gateway, MCP, Workflow Studio
- And 6 more focused modules

### 2. **[Quick Reference Cheatsheet](cheatsheet.md)**
Concise, example-driven guide covering:
- Basic workflow creation patterns
- Common node configurations
- Connection patterns
- Execution and error handling
- Custom node creation
- Environment setup

### 3. **[Validation Guide](validation-guide.md)**
Critical rules to prevent common LLM mistakes:
- Exact method names and signatures
- Correct class naming (Node suffix)
- Parameter order and naming
- Configuration key formats
- Import path structures

### 4. **[Validation Tools](validation/)**
Validation tools and guidelines:
- [Validation Guide](validation/validation-guide.md) - Critical rules to prevent LLM mistakes
- [API Validation Schema](validation/api-validation-schema.json) - Machine-readable validation rules
- [Corrections Summary](validation/corrections-summary.md) - Common mistake patterns and fixes
- [Validation Report](validation/validation_report.md) - Documentation accuracy report

### 5. **[Node Catalog](nodes/)**
Comprehensive catalog of all 66+ nodes organized by category:
- [Base Classes](nodes/01-base-nodes.md) - Abstract base classes and core interfaces
- [AI Nodes](nodes/02-ai-nodes.md) - LLM agents, A2A communication, self-organizing
- [Data Nodes](nodes/03-data-nodes.md) - File I/O, databases, streaming, SharePoint
- [API Nodes](nodes/04-api-nodes.md) - HTTP, REST, GraphQL, authentication
- [Logic Nodes](nodes/05-logic-nodes.md) - Control flow (Switch, Merge, WorkflowNode)
- [Transform Nodes](nodes/06-transform-nodes.md) - Data processing and formatting
- [Code Nodes](nodes/07-code-nodes.md) - Python execution, MCP tools
- [Utility Nodes](nodes/08-utility-nodes.md) - Visualization, security, tracking

### 6. **[Pattern Library](pattern-library/)**
Extensive collection of workflow patterns organized by category:
- Core patterns (Linear Pipeline, Direct Execution)
- Control flow patterns (Conditional Routing, Multi-Level Decisions)
- Data processing patterns (Parallel, Batch, Stream)
- Integration patterns (API Gateway, External Services)
- Error handling patterns (Circuit Breaker, Retry with Backoff)
- Performance patterns (Caching, Stream Processing)
- Composition patterns (Nested Workflows, Dynamic Generation)
- Agent patterns (Self-organizing, MCP Integration)
- Deployment patterns (Export, Containerization, Multi-tenant)
- Security patterns (Authentication, Encryption, Audit)
- Best practices and guidelines

### 7. **[Templates](templates/)**
Ready-to-use code templates for common scenarios:
- Workflow templates (ETL, conditional routing, parallel processing)
- Custom node creation templates
- API integration patterns
- Data validation and processing templates
- Error handling and monitoring patterns

## When to Use Each Resource

### Quick Decision Guide:
- **"How do I...?"** → [Cheatsheet](cheatsheet/README.md) - Quick snippets, copy-paste code
- **"What pattern should I use for...?"** → [Pattern Library](pattern-library/README.md) - Full workflow architectures
- **"Is this the right way to...?"** → [Validation Guide](validation-guide.md) - API correctness rules

### Detailed Usage:
1. **[Cheatsheet](cheatsheet/README.md)** - Start here for:
   - Quick code snippets to copy-paste
   - Basic syntax and common operations
   - Topic-focused guides (installation, nodes, connections, etc.)
   - Self-contained examples that just work

2. **[Pattern Library](pattern-library/README.md)** - Use this for:
   - Complete workflow architectures
   - Design patterns and best practices
   - Complex multi-node scenarios
   - Deployment and security patterns
   - When designing a new system

3. **[Validation Guide](validation-guide.md)** - Essential for:
   - Exact API signatures and method names
   - Preventing common LLM mistakes
   - Config vs runtime parameter rules
   - Node naming conventions
   - When something isn't working as expected

## Usage

### For LLMs/AI Assistants:
1. **ALWAYS** check `validation/validation-guide.md` first to avoid common mistakes
2. Browse `api/` directory for comprehensive API details by module
3. Reference `cheatsheet/README.md` for quick code generation
4. Use `nodes/` directory for detailed node specifications
5. Check `pattern-library/` for architectural patterns

### For Developers:
1. Start with `cheatsheet/README.md` for quick reference
2. Browse `api/` directory for detailed specifications
3. Use `validation/validation-guide.md` to ensure correct API usage
4. Check `pattern-library/` and `nodes/` for comprehensive references

## Critical Rules for LLMs

1. **All node class names now end with "Node" suffix**: `CSVReaderNode`, `LLMAgentNode`, `SwitchNode`, etc.
2. **ALL methods use snake_case**: `add_node()` not `addNode()`
3. **ALL config keys use underscores**: `file_path` not `filePath`
4. **Config passed as kwargs**: `workflow.add_node("id", Node(), file_path="data.csv")` not as dict
5. **Two execution patterns**: `runtime.execute(workflow)` OR `workflow.execute(inputs={})`
6. **Connection uses mapping**: `workflow.connect("from", "to", mapping={"out": "in"})`
7. **Parameter order is STRICT**: Check actual implementation, not just documentation
8. **Configuration vs Runtime parameters**: Config = HOW (file paths, settings), Runtime = WHAT (data flows through connections)

## Quick Start Example

```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode

# Create and execute a simple workflow
workflow = Workflow("example_id", "example")
# Configuration parameters: WHERE to read/write (static settings)
workflow.add_node("reader", CSVReaderNode(), file_path="input.csv")
workflow.add_node("writer", CSVWriterNode(), file_path="output.csv")
# Runtime parameters: data flows through connections at execution
workflow.connect("reader", "writer", mapping={"data": "data"})

# Option 1: Execute through runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

# Option 2: Execute directly
results = workflow.execute(inputs={})
```

## Maintenance

These references are extracted from the main codebase and should be updated when:
- New nodes are added
- API signatures change
- New patterns emerge
- Common use cases are identified

Last Updated: Version 0.1.4 (2025-06-04)
