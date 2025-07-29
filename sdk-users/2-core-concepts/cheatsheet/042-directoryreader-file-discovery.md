# DirectoryReaderNode File Discovery

## 🎯 Quick Overview
**DirectoryReaderNode** dynamically discovers files in directories with metadata extraction - perfect for workflows that need to process unknown file sets.

## 📦 Basic Usage
```python
from kailash.nodes.data import DirectoryReaderNode

# Discover all files in directory
dir_reader = DirectoryReaderNode(
    directory_path="./data/inputs",
    recursive=True,
    pattern="*",
    include_metadata=True
)

workflow.add_node("file_discoverer", dir_reader)

```

## 🔧 Configuration Options

### Pattern Matching
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Only CSV files
DirectoryReaderNode(directory_path="./data", pattern="*.csv")

# Multiple extensions via glob
DirectoryReaderNode(directory_path="./data", pattern="*.{csv,json,xml}")

# Specific subdirectory pattern
DirectoryReaderNode(directory_path="./data", pattern="reports/*.pdf")

```

### Metadata Control
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Full metadata (default)
DirectoryReaderNode(include_metadata=True)
# Outputs: file_path, file_name, file_type, file_extension,
#          file_size, mime_type, created_time, modified_time

# Minimal metadata (faster for large directories)
DirectoryReaderNode(include_metadata=False)
# Outputs: only file_path and file_name

```

## 📤 Output Structure
```python
# Three output ports available:
{
    "discovered_files": [        # All files as flat list
        {
            "file_path": "/path/to/file.csv",
            "file_name": "file.csv",
            "file_type": "csv",
            "file_extension": ".csv",
            "file_size": 1234,
            "mime_type": "text/csv",
            "created_time": "2025-01-01T12:00:00",
            "modified_time": "2025-01-01T12:00:00",
            "discovered_at": "2025-01-01T12:00:00"
        }
    ],
    "files_by_type": {           # Organized by file type
        "csv": [...],
        "json": [...],
        "xml": [...]
    },
    "directory_stats": {         # Summary statistics
        "total_files": 15,
        "total_size": 12345,
        "file_types": ["csv", "json", "xml"],
        "scan_duration_ms": 45
    }
}

```

## 🔗 Common Connection Patterns

### Connect to File Processors
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Use files_by_type for typed processing
workflow.add_connection("discoverer", "csv_processor", "files_by_type.csv", "files")

# Use discovered_files for generic processing
workflow.add_connection("discoverer", "generic_processor", "discovered_files", "file_list")

```

### Process Specific File Types
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# DataTransformer to extract CSV files only
csv_extractor = DataTransformer(
    transformations=["""
# Extract CSV files from discovery results
files_by_type = globals().get("files_by_type", {})
csv_files = files_by_type.get("csv", [])

result = {"csv_files": csv_files, "count": len(csv_files)}
"""]
)

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## 💡 Real-World Patterns

### Dynamic Multi-Format Processing
```python
# 1. Discover files
dir_reader = DirectoryReaderNode(directory_path="./uploads")

# 2. Process each file type differently
csv_processor = DataTransformer(transformations=["""
csv_files = globals().get("files_by_type", {}).get("csv", [])
# Process CSV files...
"""])

json_processor = DataTransformer(transformations=["""
json_files = globals().get("files_by_type", {}).get("json", [])
# Process JSON files...
"""])

# 3. Connect to processors
workflow.add_connection("discoverer", "csv_proc", "files_by_type", "files_by_type")
workflow.add_connection("discoverer", "json_proc", "files_by_type", "files_by_type")

```

### File Statistics and Reporting
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Generate file inventory report
stats_generator = DataTransformer(transformations=["""
stats = directory_stats
files = discovered_files

report = {
    "inventory_summary": {
        "total_files": stats["total_files"],
        "total_size_mb": round(stats["total_size"] / 1024 / 1024, 2),
        "file_types": stats["file_types"]
    },
    "file_details": files
}

result = report
"""])

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### Large Directory Optimization
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# For directories with thousands of files
big_dir_reader = DirectoryReaderNode(
    directory_path="./big_data",
    recursive=False,          # Avoid deep recursion
    include_metadata=False,   # Skip expensive metadata
    pattern="*.csv"          # Filter early
)

```

## ⚠️ Best Practices

### ✅ Do
- Use specific patterns (`*.csv`) instead of `*` when possible
- Set `recursive=False` for large directory trees
- Use `files_by_type` output for typed processing
- Check file existence in downstream nodes

### ❌ Don't
- Use overly broad patterns in large directories
- Assume all discovered files are readable
- Rely on MIME type detection for security decisions
- Process huge directories without pagination

## 🚨 Common Issues

### File Access Errors
```python
# Handle permission/access issues in DataTransformer
file_processor = DataTransformer(transformations=["""
files = globals().get("files_by_type", {}).get("csv", [])
processed = []

for file_info in files:
    try:
        # Process file...
        processed.append({"file": file_info, "status": "success"})
    except Exception as e:
        processed.append({"file": file_info, "status": "error", "error": str(e)})

result = {"processed_files": processed}
"""])

```

### Performance with Large Directories
```python
# Batch processing for large file sets
batch_processor = DataTransformer(transformations=["""
files = discovered_files
batch_size = 100

batches = [files[i:i+batch_size] for i in range(0, len(files), batch_size)]
result = {"batches": batches, "total_batches": len(batches)}
"""])

```

## 🔗 Related Patterns
- **[File Processing Patterns](012-common-workflow-patterns.md#file-processing)**
- **[DataTransformer Usage](004-common-node-patterns.md#datatransformer)**
- **[Error Handling](007-error-handling.md)**

---
**Created**: Session 060 | **Status**: Production Ready
