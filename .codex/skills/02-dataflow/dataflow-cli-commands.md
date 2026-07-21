# DataFlow CLI Commands

## Overview

DataFlow v0.4.7+ includes 5 CLI commands for workflow analysis, debugging, and generation.

## Available Commands

| Command | Purpose |
|---------|---------|
| `analyze` | Analyze workflow structure and dependencies |
| `debug` | Debug workflow issues with detailed diagnostics |
| `generate` | Generate node code from models |
| `perf` | Performance analysis and profiling |
| `validate` | Validate workflow structure before execution |

## Command 1: analyze

Analyze workflow structure and dependencies.

```bash
dataflow analyze my_workflow.py

# Output:
# Workflow Analysis Report
# - Nodes: 15
# - Connections: 23
# - Cycles: 0
# - Validation: PASSED
# - Estimated Runtime: ~2.5s
```

## Command 2: debug

Debug workflow with detailed diagnostics.

```bash
dataflow debug my_workflow.py --node "user_create"

# Output:
# Node Debug Report: user_create
# - Type: UserCreateNode
# - Parameters: id, name, email
# - Connections: 3 outgoing, 0 incoming
# - Validation: PASSED
# - Potential Issues: None
```

## Command 3: generate

Generate node code from model.

```bash
dataflow generate User --output nodes/

# Generates:
# - nodes/user_create_node.py
# - nodes/user_read_node.py
# - nodes/user_update_node.py
# - nodes/user_delete_node.py
# - nodes/user_list_node.py
```

## Command 4: perf

Analyze workflow performance.

```bash
dataflow perf my_workflow.py --profile

# Output:
# Performance Analysis Report
# - Total Runtime: 1.8s
# - Node Timings:
#   - user_create: 0.5s (28%)
#   - user_read: 0.3s (17%)
#   - email_send: 1.0s (55%)
# - Bottlenecks: email_send (optimize email API calls)
```

## Command 5: validate

Validate workflow before execution.

```bash
dataflow validate my_workflow.py --strict

# Output:
# Workflow Validation Report
# - Structure: PASSED
# - Connections: PASSED (23 connections)
# - Parameters: PASSED (all required parameters present)
# - Types: PASSED (all type constraints satisfied)
# - Cycles: PASSED (no circular dependencies)
# - Overall: PASSED
```

## Quick Diagnostic Commands

```bash
# Full workflow validation
dataflow validate my_workflow.py --strict

# Debug specific node
dataflow debug my_workflow.py --node "problematic_node"

# Analyze performance
dataflow perf my_workflow.py --profile

# Check workflow structure
dataflow analyze my_workflow.py
```

## CLI Commands Overhead

| Command | Execution Time |
|---------|----------------|
| analyze | <50ms for complex workflows |
| debug | <100ms with full diagnostics |
| validate | <25ms for structure checks |

## File Reference

- Implementation: `src/dataflow/cli/*.py` (5 command files)

## Version Requirements

- DataFlow v0.4.7+
