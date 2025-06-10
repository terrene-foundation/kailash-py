# DirectoryReaderNode - File Discovery Patterns

## Overview

`DirectoryReaderNode` is the recommended way to discover and list files in Kailash workflows. It provides robust file discovery with metadata extraction and error handling.

## Basic Usage

```python
from kailash.nodes.data import DirectoryReaderNode

# Simple file discovery
file_discoverer = DirectoryReaderNode(
    name="file_discoverer",
    directory_path="data/inputs",
    recursive=False,
    file_patterns=["*.csv", "*.json", "*.txt"]
)
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | str | Yes | Node identifier |
| `directory_path` | str | Yes | Path to scan |
| `recursive` | bool | No | Scan subdirectories (default: False) |
| `file_patterns` | list | No | Glob patterns (default: ["*"]) |
| `include_hidden` | bool | No | Include hidden files (default: False) |
| `include_metadata` | bool | No | Add file metadata (default: True) |

## Output Format

```python
{
    "files": [
        {
            "path": "data/inputs/customers.csv",
            "name": "customers.csv",
            "extension": ".csv",
            "size": 1024,
            "modified": "2024-01-15T10:30:00Z",
            "is_file": True,
            "is_directory": False
        },
        # ... more files
    ],
    "summary": {
        "total_files": 5,
        "total_size": 5120,
        "file_types": {
            ".csv": 2,
            ".json": 2,
            ".txt": 1
        }
    }
}
```

## Common Patterns

### Pattern 1: Multi-Type File Processing
```python
# Discover files
discoverer = DirectoryReaderNode(
    name="discoverer",
    directory_path="data/inputs",
    file_patterns=["*.csv", "*.json", "*.xml"]
)

# Route to specific processors
workflow.connect("discoverer", "router", mapping={"files": "discovered_files"})

router = PythonCodeNode(
    name="router",
    code="""
csv_files = [f for f in discovered_files if f['extension'] == '.csv']
json_files = [f for f in discovered_files if f['extension'] == '.json']
xml_files = [f for f in discovered_files if f['extension'] == '.xml']

result = {
    'csv_files': csv_files,
    'json_files': json_files,
    'xml_files': xml_files
}
"""
)
```

### Pattern 2: Recursive Directory Scan
```python
# Scan all subdirectories
deep_scanner = DirectoryReaderNode(
    name="deep_scanner",
    directory_path="project",
    recursive=True,
    file_patterns=["*.py", "*.md"],
    include_hidden=False  # Skip .git, .venv, etc.
)

# Process results
workflow.connect("deep_scanner", "analyzer", mapping={"files": "project_files"})
```

### Pattern 3: File Filtering by Metadata
```python
# Discover with metadata
discoverer = DirectoryReaderNode(
    name="discoverer",
    directory_path="logs",
    file_patterns=["*.log"],
    include_metadata=True
)

# Filter recent files
workflow.connect("discoverer", "filter", mapping={"files": "all_files"})

filter_node = PythonCodeNode(
    name="filter",
    code="""
from datetime import datetime, timedelta

cutoff = datetime.now() - timedelta(days=7)
recent_files = []

for file in all_files:
    modified = datetime.fromisoformat(file['modified'].replace('Z', '+00:00'))
    if modified > cutoff:
        recent_files.append(file)

result = {
    'recent_files': recent_files,
    'count': len(recent_files)
}
"""
)
```

## Best Practices

### 1. Use Specific Patterns
```python
# Good: Specific patterns
file_patterns=["*.csv", "*.json", "*.xml"]

# Bad: Too broad
file_patterns=["*"]  # Includes everything
```

### 2. Handle Empty Results
```python
processor = PythonCodeNode(
    name="processor",
    code="""
if not discovered_files:
    result = {'status': 'no_files_found', 'processed': 0}
else:
    # Process files
    result = {'status': 'success', 'processed': len(discovered_files)}
"""
)
```

### 3. Combine with File Readers
```python
# Discover CSV files
discoverer = DirectoryReaderNode(
    name="discoverer",
    directory_path="data",
    file_patterns=["*.csv"]
)

# Process each CSV
workflow.connect("discoverer", "processor", mapping={"files": "csv_files"})

processor = PythonCodeNode(
    name="processor",
    code="""
results = []
for file_info in csv_files:
    # In real workflow, connect to CSVReaderNode
    results.append({
        'file': file_info['name'],
        'path': file_info['path']
    })
result = {'csv_paths': results}
"""
)

# Then connect to CSVReaderNode for actual reading
```

## Anti-Patterns to Avoid

### ❌ Manual Directory Scanning
```python
# WRONG: Don't use os.listdir in PythonCodeNode
bad_scanner = PythonCodeNode(
    name="scanner",
    code="""
import os
files = []
for f in os.listdir('data'):
    if f.endswith('.csv'):
        files.append(f)
result = {'files': files}
"""
)
```

### ❌ Hardcoded Paths
```python
# WRONG: Hardcoded paths
DirectoryReaderNode(
    name="scanner",
    directory_path="/Users/john/project/data"  # Not portable
)

# BETTER: Relative or configurable paths
DirectoryReaderNode(
    name="scanner",
    directory_path="data/inputs"  # Relative to project
)

# BEST: Centralized data utilities (Session 062)
from examples.utils.data_paths import get_input_data_path
DirectoryReaderNode(
    name="scanner",
    directory_path=str(get_input_data_path(""))  # Centralized, maintainable
)
```

### ❌ Processing Files in Discovery Node
```python
# WRONG: DirectoryReaderNode only discovers, doesn't read content
# Use separate reader nodes for actual file content
```

## Integration Examples

### With CSVReaderNode
```python
# 1. Discover CSV files
discoverer = DirectoryReaderNode(
    name="csv_discoverer",
    directory_path="data",
    file_patterns=["*.csv"]
)

# 2. Process file list to get first CSV
workflow.connect("csv_discoverer", "selector", mapping={"files": "csv_files"})

selector = PythonCodeNode(
    name="selector",
    code="""
if csv_files:
    first_csv = csv_files[0]['path']
    result = {'selected_file': first_csv}
else:
    result = {'error': 'No CSV files found'}
"""
)

# 3. Read the selected CSV
csv_reader = CSVReaderNode(name="csv_reader")
workflow.connect("selector", "csv_reader", mapping={"selected_file": "file_path"})
```

### With Parallel Processing
```python
# Discover files
discoverer = DirectoryReaderNode(
    name="discoverer",
    directory_path="reports",
    file_patterns=["*.pdf", "*.docx"]
)

# Split for parallel processing
splitter = PythonCodeNode(
    name="splitter",
    code="""
pdf_files = [f for f in files if f['extension'] == '.pdf']
docx_files = [f for f in files if f['extension'] == '.docx']

result = {
    'pdf_batch': pdf_files,
    'docx_batch': docx_files
}
"""
)

workflow.connect("discoverer", "splitter", mapping={"files": "files"})
# Connect to parallel processors...
```

## Performance Tips

1. **Use specific patterns** to reduce file system calls
2. **Avoid recursive scans** on large directory trees unless necessary
3. **Filter early** to reduce downstream processing
4. **Cache results** if scanning the same directory multiple times

## Error Handling

The node handles common errors gracefully:
- Non-existent directory → Returns empty file list
- Permission errors → Skips inaccessible files
- Invalid patterns → Falls back to all files

For custom error handling, check the output:
```python
error_handler = PythonCodeNode(
    name="error_handler",
    code="""
if 'error' in discovery_result:
    # Handle error
    result = {'status': 'failed', 'reason': discovery_result['error']}
elif not discovery_result.get('files'):
    result = {'status': 'no_files'}
else:
    result = {'status': 'success', 'count': len(discovery_result['files'])}
"""
)