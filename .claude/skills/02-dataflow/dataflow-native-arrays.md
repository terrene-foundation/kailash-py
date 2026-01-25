# PostgreSQL Native Arrays

## Overview

PostgreSQL native arrays (TEXT[], INTEGER[], REAL[]) provide **2-10x faster performance** compared to JSON string storage, with built-in indexing support (GIN/GiST) and PostgreSQL-specific operators.

## Key Features

- **Native PostgreSQL arrays**: TEXT[], INTEGER[], REAL[] instead of JSONB
- **Opt-in feature flag**: Backward compatible, enable per-model with `__dataflow__`
- **Cross-database validated**: Error if used on MySQL/SQLite
- **Performance gains**: 2-10x faster queries with native array operators
- **Index support**: GIN/GiST indexes for array columns

## Basic Usage

```python
from dataflow import DataFlow
from typing import List

db = DataFlow("postgresql://...")

@db.model
class AgentMemory:
    id: str
    tags: List[str]
    scores: List[int]
    ratings: List[float]

    __dataflow__ = {
        'use_native_arrays': True  # Opt-in to PostgreSQL native arrays
    }

# Generates PostgreSQL schema:
# CREATE TABLE agent_memorys (
#     id TEXT PRIMARY KEY,
#     tags TEXT[],      -- Native array instead of JSONB
#     scores INTEGER[],  -- Native array
#     ratings REAL[]     -- Native array
# )
```

## Supported Array Types

| Python Type | PostgreSQL Type | Element Type |
|-------------|-----------------|--------------|
| `List[str]` | `TEXT[]` | Text strings |
| `List[int]` | `INTEGER[]` | Integers |
| `List[float]` | `REAL[]` | Floating point |
| `Optional[List[str]]` | `TEXT[] NULL` | Nullable arrays |

**Unsupported** (defaults to JSONB):
- `List[dict]`, `List[List[...]]` (nested), custom types

## CRUD Operations

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

workflow = WorkflowBuilder()

# Create with array values
workflow.add_node("AgentMemoryCreateNode", "create", {
    "id": "mem-001",
    "tags": ["medical", "urgent", "ai"],
    "scores": [85, 92, 78],
    "ratings": [4.5, 4.8, 4.2]
})

# Update array values
workflow.add_node("AgentMemoryUpdateNode", "update", {
    "filter": {"id": "mem-001"},
    "fields": {
        "tags": ["medical", "urgent", "ai", "reviewed"]
    }
})

# Query with array operators
workflow.add_node("AgentMemoryListNode", "find", {
    "filter": {"tags": {"$contains": "medical"}}
})

runtime = AsyncLocalRuntime()
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

## PostgreSQL Array Operators

DataFlow provides MongoDB-style syntax for PostgreSQL array operators:

### Contains Operator (@>)

```python
# Find records where tags contain "medical"
workflow.add_node("AgentMemoryListNode", "find_medical", {
    "filter": {"tags": {"$contains": "medical"}}
})
# SQL: WHERE tags @> ARRAY['medical']
```

### Overlap Operator (&&)

```python
# Find records where tags overlap with ["medical", "urgent"]
workflow.add_node("AgentMemoryListNode", "find_urgent", {
    "filter": {"tags": {"$overlap": ["medical", "urgent"]}}
})
# SQL: WHERE tags && ARRAY['medical', 'urgent']
```

### Any Operator (= ANY)

```python
# Find records where any score is >= 90
workflow.add_node("AgentMemoryListNode", "high_scores", {
    "filter": {"scores": {"$any": {"$gte": 90}}}
})
# SQL: WHERE 90 <= ANY(scores)
```

## Performance Comparison

### Before (JSON string storage)

```python
tags: str  # Manual encoding: ",".join(tags)
# Query: WHERE tags LIKE '%medical%'  # Slow, no index
# Time: ~50ms for 10k rows
```

### After (Native arrays)

```python
tags: List[str]  # Native PostgreSQL array
# Query: WHERE tags @> ARRAY['medical']  # Fast, GIN index
# Time: ~5ms for 10k rows (10x faster!)
```

## Best Practices

### When to Use Native Arrays

- PostgreSQL production databases
- Large tables (>10k rows) with frequent array queries
- Need for array-specific operators (@>, &&, ANY)
- Performance-critical applications

### When NOT to Use Native Arrays

- Cross-database compatibility required (MySQL, SQLite)
- Small tables (<1k rows) with infrequent queries
- Nested arrays or complex element types
- Development phase (use default JSONB for flexibility)

## Cross-Database Compatibility

```python
# For cross-database compatibility (MySQL, SQLite)
@db.model
class BlogPost:
    title: str
    content: str
    tags_json: Dict[str, Any] = {}  # Use JSON for cross-DB support
```

## Version Requirements

- DataFlow v0.8.0+
- PostgreSQL 9.5+ (for array operators)
