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
```

## Supported Array Types

| Python Type           | PostgreSQL Type | Element Type    |
| --------------------- | --------------- | --------------- |
| `List[str]`           | `TEXT[]`        | Text strings    |
| `List[int]`           | `INTEGER[]`     | Integers        |
| `List[float]`         | `REAL[]`        | Floating point  |
| `Optional[List[str]]` | `TEXT[] NULL`   | Nullable arrays |

## PostgreSQL Array Operators

| Operator | Syntax                                | SQL                                        |
| -------- | ------------------------------------- | ------------------------------------------ |
| Contains | `{"$contains": "medical"}`            | `WHERE tags @> ARRAY['medical']`           |
| Overlap  | `{"$overlap": ["medical", "urgent"]}` | `WHERE tags && ARRAY['medical', 'urgent']` |
| Any      | `{"$any": {"$gte": 90}}`              | `WHERE 90 <= ANY(scores)`                  |

## Best Practices

### When to Use Native Arrays

- PostgreSQL production databases
- Large tables (>10k rows) with frequent array queries
- Need for array-specific operators (@>, &&, ANY)

### When NOT to Use Native Arrays

- Cross-database compatibility required (MySQL, SQLite)
- Small tables (<1k rows) with infrequent queries
- Nested arrays or complex element types

## Version Requirements

- DataFlow v0.8.0+
- PostgreSQL 9.5+ (for array operators)
