---
name: dataflow-file-import
description: "FileSourceNode for CSV, TSV, Excel, Parquet, JSON, JSONL ingestion into DataFlow models. Use when asking about 'file import', 'CSV import', 'Excel import', 'Parquet import', 'import_file', 'FileSourceNode', 'data ingestion', or 'bulk file load'."
---

# DataFlow File Import

FileSourceNode reads tabular data from CSV, TSV, Excel, Parquet, JSON, and JSONL files into records compatible with BulkCreateNode and BulkUpsertNode.

## Quick Reference

| Feature           | Details                                                                    |
| ----------------- | -------------------------------------------------------------------------- |
| Supported formats | CSV, TSV, Excel (.xlsx/.xls), Parquet, JSON, JSONL                         |
| Auto-detection    | By file extension (`.csv`, `.tsv`, `.xlsx`, `.parquet`, `.json`, `.jsonl`) |
| Express API       | `await db.express.import_file("User", "/path/to/users.csv")`               |
| Column mapping    | `column_mapping={"old_name": "new_name"}`                                  |
| Type coercion     | `type_coercion={"age": "int", "active": "bool"}`                           |
| Batch size        | `batch_size=1000` (default)                                                |
| Optional deps     | Excel requires `openpyxl`, Parquet requires `pyarrow`                      |

## Express Import (Recommended)

```python
# Simple CSV import
result = await db.express.import_file("User", "/data/users.csv")
print(f"Imported {result['count']} records")

# With column mapping and type coercion
result = await db.express.import_file(
    "User",
    "/data/legacy_export.csv",
    column_mapping={"user_name": "name", "user_email": "email"},
    type_coercion={"age": "int", "active": "bool"},
)

# Excel file
result = await db.express.import_file("Product", "/data/catalog.xlsx")

# Parquet file
result = await db.express.import_file("Event", "/data/events.parquet")
```

## Workflow API (For Multi-Step Pipelines)

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Read file
workflow.add_node("FileSourceNode", "read_csv", {
    "file_path": "/data/users.csv",
    "format": "auto",  # or explicit: "csv", "excel", "parquet", "json", "jsonl"
    "column_mapping": {"legacy_id": "id", "full_name": "name"},
    "type_coercion": {"age": "int"},
    "skip_rows": 1,       # Skip header rows (CSV only)
    "encoding": "utf-8",  # File encoding
    "delimiter": ",",     # CSV delimiter override
})

# Connect to bulk create
workflow.add_node("User_BulkCreate", "import_users", {})
workflow.add_connection("read_csv", "records", "import_users", "records")
```

## Output Format

FileSourceNode produces:

```python
{
    "records": [{"id": "1", "name": "Alice"}, ...],
    "count": 1500,
    "errors": []  # Coercion errors (non-fatal)
}
```

## Type Coercion

| Type name  | Coerces to                 | Example                            |
| ---------- | -------------------------- | ---------------------------------- |
| `int`      | `int()`                    | `"42"` -> `42`                     |
| `float`    | `float()`                  | `"3.14"` -> `3.14`                 |
| `str`      | `str()`                    | `42` -> `"42"`                     |
| `bool`     | Boolean                    | `"true"`, `"1"`, `"yes"` -> `True` |
| `datetime` | `datetime.fromisoformat()` | `"2026-01-01"` -> datetime         |

Coercion errors are non-fatal -- they appear in the `errors` list but don't stop processing.

## Security

- Path traversal prevention: `".."` in file paths is blocked
- File must exist (raises `FileNotFoundError`)
- Optional deps use lazy imports (fail only when the format is actually used)

## Optional Dependencies

```bash
# For Excel support
pip install kailash-dataflow[excel]  # installs openpyxl

# For Parquet support
pip install kailash-dataflow[parquet]  # installs pyarrow
```

CSV, TSV, JSON, and JSONL use stdlib only -- no extra dependencies.

## Source Code

- `packages/kailash-dataflow/src/dataflow/nodes/file_source.py` -- FileSourceNode
- `packages/kailash-dataflow/tests/unit/test_file_source_node.py` -- Unit tests
