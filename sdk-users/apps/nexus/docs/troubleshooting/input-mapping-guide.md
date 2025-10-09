# Nexus API Input Mapping Guide

## Overview

Understanding how Nexus maps API request inputs to workflow node parameters is critical for building dynamic workflows. This guide explains the complete flow from API request to node parameter access.

## The Complete Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Client sends API request                                 │
│    POST /workflows/contact_search/execute                   │
│    {"inputs": {"sector": "Technology", "limit": 50}}        │
└────────────────────┬────────────────────────────────────────┘
                     │                     ▼┌─────────────────────────────────────────────────────────────┐
│ 2. Nexus WorkflowAPI receives request                       │
│    WorkflowRequest.inputs = {"sector": "Technology", ...}   │
└────────────────────┬────────────────────────────────────────┘
                     │                     ▼┌─────────────────────────────────────────────────────────────┐
│ 3. Runtime executes workflow                                │
│    runtime.execute(workflow, parameters={...})              │
│                                                             │
│    Note: API "inputs" becomes runtime "parameters"          │
└────────────────────┬────────────────────────────────────────┘
                     │                     ▼┌─────────────────────────────────────────────────────────────┐
│ 4. Nexus maps inputs to ALL nodes' parameters               │
│    Each node receives the FULL inputs dict as parameters    │
│                                                             │
│    prepare_filters node gets:                               │
│      parameters = {"sector": "Technology", "limit": 50}     │
│                                                             │
│    search node gets:                                        │
│      parameters = {"sector": "Technology", "limit": 50}     │
└────────────────────┬────────────────────────────────────────┘
                     │                     ▼┌─────────────────────────────────────────────────────────────┐
│ 5. Inside PythonCodeNode code:                              │
│    - Parameters injected as local variables                 │
│    - Access via try/except for optional params              │
│                                                             │
│    try:                                                     │
│        s = sector  # "Technology"                           │
│    except NameError:                                        │
│        s = None                                             │
└─────────────────────────────────────────────────────────────┘
```

## Key Concepts

### 1. Terminology Mapping

| API Layer | Runtime Layer | Node Layer |
|-----------|---------------|------------|
| `{"inputs": {...}}` | `parameters={...}` | `sector` variable |
| Request body field | Runtime execution parameter | Injected local variable |

**Important**:
- The API uses `"inputs"` for clarity
- The runtime uses `"parameters"` internally
- Both refer to the same data!

### 2. Broadcasting Behavior

**Critical Understanding**: Nexus broadcasts the ENTIRE inputs dict to ALL nodes in the workflow.

```python
# API Request
{
  "inputs": {    "sector": "Technology",    "geography": "North America",    "limit": 50  }}

# What EVERY node receives as parameters:
{
  "sector": "Technology",  "geography": "North America",  "limit": 50}
```

**This means**:
- Node A can use `sector` and `limit`
- Node B can use `geography` and `limit`
- Node C can use all three
- Each node extracts what it needs from the full dict

### 3. PythonCodeNode Parameter Access

**WRONG** ❌ - These patterns DO NOT work:
```python
# ❌ NO 'inputs' variable existssector = inputs.get('sector')

# ❌ locals() is restricted in PythonCodeNodesector = locals().get('sector')

# ❌ globals() is also restrictedsector = globals().get('sector')
```

**CORRECT** ✅ - Use try/except for optional parameters:
```python
# ✅ Safe access to optional parameterstry:
    s = sector  # Will be injected if provided in API inputsexcept NameError:
    s = None
try:
    g = geographyexcept NameError:
    g = None
try:
    lim = limitexcept NameError:
    lim = 100  # Default value
# Now use s, g, lim safely
filters = {}
if s:
    filters['sector'] = sif g:
    filters['geography'] = g
result = {'filters': filters, 'limit': lim}
```

## Complete Working Example

### Workflow Definition

```python
from kailash.workflow.builder import WorkflowBuilder

def create_contact_search_workflow():
    workflow = WorkflowBuilder()
    # Node 1: Build filters from API inputs    workflow.add_node(        "PythonCodeNode",        "prepare_filters",        {            "code": """# Access optional parameters via try/except
try:
    s = sectorexcept NameError:
    s = None
try:
    g = geographyexcept NameError:
    g = None
try:
    lim = limitexcept NameError:
    lim = 100
# Build filters
filters = {}
if s and str(s).strip():
    filters['sector'] = str(s).strip()if g and str(g).strip():
    filters['geography'] = str(g).strip()
# Output for next node
result = {
    'filters': filters,    'limit': lim}
"""
        }    )
    # Node 2: Execute search    workflow.add_node(        "ContactListNode",        "search",        {            "filter": {},   # Will be populated via connection            "limit": 100        }    )
    # Connect filter data from prepare_filters to search    workflow.add_connection(        "prepare_filters", "result.filters",        "search", "filter"    )
    workflow.add_connection(        "prepare_filters", "result.limit",        "search", "limit"    )
    return workflow.build()
```

### Nexus Registration

```python
from nexus import Nexus

app = Nexus()
app.register("contact_search", create_contact_search_workflow())
app.start()
```

### API Usage

```bash
# Example 1: Search Technology sector
curl -X POST http://localhost:8000/workflows/contact_search/execute \
  -H "Content-Type: application/json" \  -d '{    "inputs": {      "sector": "Technology",      "limit": 10    }  }'
# Example 2: Search with geography
curl -X POST http://localhost:8000/workflows/contact_search/execute \
  -H "Content-Type: application/json" \  -d '{    "inputs": {      "sector": "Healthcare",      "geography": "Europe",      "limit": 5    }  }'
# Example 3: No filters (get all)
curl -X POST http://localhost:8000/workflows/contact_search/execute \
  -H "Content-Type: application/json" \  -d '{    "inputs": {      "limit": 100    }  }'
```

## Common Pitfalls

### Pitfall 1: Trying to Use Template Syntax in Node Config

**WRONG** ❌:
```python
workflow.add_node(
    "ContactListNode",    "search",    {        "filter": "${prepare_filters.result.filters}",  # ❌ Not evaluated!        "limit": "${prepare_filters.result.limit}"    })
```

**CORRECT** ✅:
```python
# Use explicit connections instead
workflow.add_node(
    "ContactListNode",    "search",    {        "filter": {},   # Default value        "limit": 100    })

workflow.add_connection(
    "prepare_filters", "result.filters",    "search", "filter")

workflow.add_connection(
    "prepare_filters", "result.limit",    "search", "limit")
```

### Pitfall 2: Accessing Nested Output Incorrectly

**WRONG** ❌:
```python
# If prepare_filters outputs: {'result': {'filters': {...}, 'limit': 50}}
workflow.add_connection(
    "prepare_filters", "filters",  # ❌ Missing 'result.' prefix    "search", "filter")
```

**CORRECT** ✅:
```python
# Access nested output with dot notation
workflow.add_connection(
    "prepare_filters", "result.filters",  # ✅ Full path    "search", "filter")
```

### Pitfall 3: Node-Specific vs Broadcast Parameters

**Understanding**:
- API `inputs` are BROADCAST to all nodes
- To pass parameters to specific nodes, use connections
- Don't rely on API inputs for node-to-node data flow

**WRONG** ❌ - Expecting node-specific inputs:
```python
# API Request - trying to target specific nodes
{
  "inputs": {    "prepare_filters": {"sector": "Tech"},  # ❌ Nexus doesn't support this    "search": {"limit": 50}  }}
```

**CORRECT** ✅ - Use flat inputs + connections:
```python
# API Request - flat inputs
{
  "inputs": {    "sector": "Tech",    "limit": 50  }}

# Workflow - use connections for node-to-node data
workflow.add_connection(
    "prepare_filters", "result",    "search", "input")
```

## Backward Compatibility

Nexus supports both `"inputs"` and `"parameters"` in API requests for backward compatibility:

```python
# Modern format (preferred)
{"inputs": {"key": "value"}}

# Legacy format (still works)
{"parameters": {"key": "value"}}
```

Both map to the same `parameters` dict in workflow execution.

## Enterprise Features

Enterprise Nexus supports additional request fields:

```json
{
  "inputs": {    "sector": "Technology"  },  "resources": {    "database": "production_db",    "api_key": "secret_key"  },  "context": {    "user_id": "12345",    "request_id": "abc-def"  }}
```

- `resources`: System resources (databases, APIs, credentials)
- `context`: Request metadata (user, session, trace info)
- `inputs`: Workflow data (mapped to node parameters)

## Debugging Tips

### 1. Inspect What Each Node Receives

Add a debug node to see parameters:

```python
workflow.add_node(
    "PythonCodeNode",    "debug",    {        "code": """import json

# This will show all parameters passed to this node
try:
    s = sector    has_sector = Trueexcept NameError:
    has_sector = False
try:
    lim = limit    has_limit = Trueexcept NameError:
    has_limit = False
result = {
    'debug_info': {        'has_sector': has_sector,        'sector_value': s if has_sector else None,        'has_limit': has_limit,        'limit_value': lim if has_limit else None    }}
"""
    })
```

### 2. Check Workflow Execution Logs

Enable debug logging to see parameter flow:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Look for log lines:
```
dataflow.core.nodes - INFO - Run called with kwargs: {'limit': 2, 'filter': {}, ...}
```

### 3. Verify API Request Format

Use `-v` with curl to see what you're actually sending:

```bash
curl -v -X POST http://localhost:8000/workflows/contact_search/execute \  -H "Content-Type: application/json" \  -d '{"inputs": {"sector": "Technology"}}'```

## Related Documentation

- [Nexus API Reference](../reference/api-reference.md) - Full API specification
- [Multi-Channel Usage](../user-guides/multi-channel-usage.md) - API, CLI, MCP patterns
- [Parameter Passing Guide](../../../../3-development/parameter-passing-guide.md) - Core SDK parameter concepts
- [PythonCodeNode Best Practices](../../../../2-core-concepts/cheatsheet/031-pythoncode-best-practices.md)

## Summary

**Key Takeaways**:

1. API `{"inputs": {...}}` → Runtime `parameters={...}` → Node variables
2. ALL nodes receive the FULL inputs dict
3. Use try/except to access optional parameters in PythonCodeNode
4. Use explicit connections, NOT template syntax in node config
5. Access nested outputs with dot notation: `"result.filters"`
6. Nexus broadcasts inputs; use connections for node-to-node data flow

**Common Pattern**:
```python
# API Request
{"inputs": {"sector": "Tech", "limit": 10}}

# Inside PythonCodeNode
try:
    s = sector  # "Tech"except NameError:
    s = None
# Output
result = {'filters': {'sector': s}, 'limit': limit}

# Connection to next node
workflow.add_connection(
    "prepare_filters", "result.filters",    "search", "filter")
```
