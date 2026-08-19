---
name: dataflow-inspector
description: "Inspector API for DataFlow workflow introspection, debugging, and validation. Use when debugging workflows, tracing parameters, analyzing connections, finding broken links, validating structure, or need workflow analysis."
---

# DataFlow Inspector - Workflow Introspection API

Self-service debugging API for workflows, nodes, connections, and parameters with 18 inspection methods.

> **Skill Metadata**
> Category: `dataflow/dx`
> Priority: `CRITICAL`
> SDK Version: `0.8.0+ / DataFlow 0.8.0`

## Quick Reference

- **18 Inspector Methods**: Connection, parameter, node, and workflow analysis
- **<1ms Per Method**: Cached operations for fast introspection
- **Automatic Validation**: Built-in workflow structure checks
- **CLI Integration**: Works with `dataflow-validate`, `dataflow-debug`
- **Zero Configuration**: Works with any DataFlow workflow

## Inspector Methods (18 Total)

### Connection Analysis (5 methods)

- `connections()` - List all connections
- `validate_connections()` - Check connection validity
- `find_broken_connections()` - Find issues
- `connection_chain()` - Trace connection path
- `connection_graph()` - Build connection graph

### Parameter Tracing (5 methods)

- `trace_parameter()` - Find parameter source
- `parameter_flow()` - Trace complete flow
- `find_parameter_source()` - Locate source node
- `parameter_dependencies()` - Find all dependencies
- `parameter_consumers()` - Find all consumers

### Node Analysis (5 methods)

- `node_dependencies()` - Upstream dependencies
- `node_dependents()` - Downstream dependents
- `execution_order()` - Topological sort
- `node_schema()` - Get node schema
- `compare_nodes()` - Compare two nodes

### Workflow Analysis (3 methods)

- `workflow_summary()` - High-level overview
- `workflow_metrics()` - Detailed metrics
- `workflow_validation_report()` - Comprehensive validation
