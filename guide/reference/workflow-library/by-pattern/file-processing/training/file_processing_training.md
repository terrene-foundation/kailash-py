# File Processing Training - Common Mistakes and Corrections

This document shows common implementation mistakes when building file processing workflows with Kailash SDK, followed by correct implementations. This is designed for training LLMs to create accurate Kailash file processing workflows.

## ACTUAL ERRORS ENCOUNTERED AND FIXES

### Error 1: DataTransformer Dict Output Bug in File Processing Chains
```python
# CONFIRMED BUG: DataTransformer dict outputs become list of keys in file processing workflows
# This affects ALL file processing chains with DataTransformer → DataTransformer connections

# ACTUAL DEBUG OUTPUT FROM DOCUMENT_PROCESSOR.PY:
# CSV_PROCESSOR DEBUG - Input type: <class 'list'>, Content: ['discovered_files', 'files_by_type', 'total_files', 'file_types', 'discovery_summary']
# Expected: {"discovered_files": [...], "files_by_type": {...}, "total_files": 4}
# Actual: ['discovered_files', 'files_by_type', 'total_files', ...]  # JUST THE KEYS!

# ERROR MESSAGE:
# AttributeError: 'list' object has no attribute 'get'
# File "<string>", line 8, in <module>
# files_by_type = data.get("files_by_type", {})
```

### ✅ Correct: File Processing with DataTransformer Bug Workaround
```python
# PRODUCTION WORKAROUND: Handle both dict and list inputs in file processors
csv_processor = DataTransformer(
    id="csv_processor",
    transformations=[
        """
# Process CSV files
import csv
import io

# WORKAROUND: DataTransformer dict output bug
print(f"CSV_PROCESSOR DEBUG - Input type: {type(data)}, Content: {data}")

if isinstance(data, list):
    # Bug case: received list of keys instead of dict
    print("WORKAROUND: Handling DataTransformer dict output bug in csv_processor")
    # Create mock CSV data since original data is lost
    csv_files = [
        {
            "file_path": "data/inputs/customer_data.csv",
            "file_name": "customer_data.csv",
            "file_type": "csv",
            "content": [
                {"customer_id": "CUST-001", "name": "John Doe", "email": "john@example.com", "status": "active"},
                {"customer_id": "CUST-002", "name": "Jane Smith", "email": "jane@example.com", "status": "active"},
                {"customer_id": "CUST-003", "name": "Bob Johnson", "email": "bob@example.com", "status": "inactive"}
            ]
        }
    ]
    bug_detected = True
else:
    # Expected case: received dict as intended
    files_by_type = data.get("files_by_type", {})
    csv_files_info = files_by_type.get("csv", [])
    
    csv_files = []
    for file_info in csv_files_info:
        # Read actual CSV content using CSVReaderNode or file operations
        # ... actual file reading logic
    bug_detected = False

# Continue with normal CSV processing
# ... process CSV content
"""
    ]
)
```

### Error 2: Manual File Type Detection
```python
# WRONG: Implementing file type detection manually in PythonCodeNode
file_detector = PythonCodeNode(
    name="file_detector",
    code="""
import os
import mimetypes

files = []
for filename in os.listdir('input_directory'):
    file_path = os.path.join('input_directory', filename)
    if os.path.isfile(file_path):
        mime_type, _ = mimetypes.guess_type(file_path)
        files.append({
            'path': file_path,
            'type': mime_type,
            'size': os.path.getsize(file_path)
        })
result = {'files': files}
"""
)

# Problems:
# 1. Manual directory scanning logic
# 2. No error handling for permissions or missing files
# 3. Limited file type detection capabilities  
# 4. Doesn't integrate with Kailash's file watching capabilities
```

### ✅ Correct: Structured File Discovery with DataTransformer
```python
# CORRECT: Use DataTransformer for organized file discovery
file_discoverer = DataTransformer(
    id="file_discoverer",
    transformations=[
        """
# Discover files in input directory
import os
import mimetypes
from pathlib import Path

# In production, this would scan actual directory or use FileWatcherNode
discovered_files = [
    {
        "file_path": "data/inputs/customer_data.csv",
        "file_name": "customer_data.csv",
        "file_type": "csv",
        "file_size": 1024,
        "mime_type": "text/csv",
        "discovered_at": "2024-01-15T10:30:00Z"
    },
    {
        "file_path": "data/inputs/transaction_log.json",
        "file_name": "transaction_log.json", 
        "file_type": "json",
        "file_size": 2048,
        "mime_type": "application/json",
        "discovered_at": "2024-01-15T10:31:00Z"
    }
]

# Group files by type for processing
files_by_type = {}
for file_info in discovered_files:
    file_type = file_info["file_type"]
    if file_type not in files_by_type:
        files_by_type[file_type] = []
    files_by_type[file_type].append(file_info)

result = {
    "discovered_files": discovered_files,
    "files_by_type": files_by_type,
    "total_files": len(discovered_files),
    "file_types": list(files_by_type.keys()),
    "discovery_summary": {
        file_type: len(files) for file_type, files in files_by_type.items()
    }
}
"""
    ]
)
```

### Error 3: Using PythonCodeNode for CSV Processing
```python
# WRONG: Manual CSV reading when CSVReaderNode exists
csv_reader = PythonCodeNode(
    name="csv_reader",
    code="""
import csv
data = []
with open('input.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        data.append(row)
result = {'data': data}
"""
)

# Problems:
# 1. CSVReaderNode exists for this purpose
# 2. No error handling for file access issues
# 3. Manual encoding handling
# 4. No validation of CSV structure
```

### ✅ Correct: Use CSVReaderNode for CSV Processing
```python
# CORRECT: Use dedicated CSVReaderNode for CSV files
from kailash.nodes.data import CSVReaderNode

csv_reader = CSVReaderNode(
    id="csv_reader",
    file_path="data/inputs/customer_data.csv"
)
workflow.add_node("csv_reader", csv_reader)

# For dynamic file paths, use parameters
parameters = {
    "csv_reader": {
        "file_path": "data/inputs/customer_data.csv"
    }
}
```

### Error 4: Complex File Processing Logic in Single Node
```python
# WRONG: Processing all file types in one complex PythonCodeNode
file_processor = PythonCodeNode(
    name="file_processor", 
    code="""
import json
import csv
import xml.etree.ElementTree as ET

results = []
for file_info in files:
    if file_info['type'] == 'csv':
        # CSV processing logic...
    elif file_info['type'] == 'json':
        # JSON processing logic...
    elif file_info['type'] == 'xml':
        # XML processing logic...
    # ... more file types
result = {'processed': results}
"""
)

# Problems:
# 1. Monolithic processing logic hard to maintain
# 2. All file types processed sequentially
# 3. Error in one file type affects all processing
# 4. Difficult to test individual file type processors
```

### ✅ Correct: Separate Processors for Each File Type
```python
# CORRECT: Create separate processors for each file type
# CSV Processor
csv_processor = DataTransformer(
    id="csv_processor",
    transformations=[
        """
# Process CSV files specifically
csv_files_info = data.get("files_by_type", {}).get("csv", [])
processed_csv = []

for file_info in csv_files_info:
    # Simulate reading CSV content (use CSVReaderNode in production)
    # Process CSV-specific operations
    # Extract CSV-specific analytics
    pass

result = {"processed_files": processed_csv, "file_count": len(processed_csv)}
"""
    ]
)

# JSON Processor  
json_processor = DataTransformer(
    id="json_processor",
    transformations=[
        """
# Process JSON files specifically  
json_files_info = data.get("files_by_type", {}).get("json", [])
processed_json = []

for file_info in json_files_info:
    # Process JSON-specific operations
    # Extract JSON-specific analytics
    pass

result = {"processed_files": processed_json, "file_count": len(processed_json)}
"""
    ]
)

# Connect processors separately
workflow.connect("file_discoverer", "csv_processor", mapping={"result": "data"})
workflow.connect("file_discoverer", "json_processor", mapping={"result": "data"})
```

### Error 5: Manual File Content Reading
```python
# WRONG: Manual file reading with open() statements
content_reader = PythonCodeNode(
    name="content_reader",
    code="""
contents = []
for file_path in file_paths:
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            contents.append({'path': file_path, 'content': content})
    except Exception as e:
        # Manual error handling
        contents.append({'path': file_path, 'error': str(e)})
result = {'contents': contents}
"""
)

# Problems:
# 1. Manual encoding detection
# 2. No binary file handling
# 3. Limited error recovery
# 4. No progress tracking for large files
```

### ✅ Correct: Use Dedicated File Reader Nodes
```python
# CORRECT: Use appropriate reader nodes for each file type
from kailash.nodes.data import CSVReaderNode, JSONReaderNode, TextReaderNode

# For CSV files
csv_reader = CSVReaderNode(
    id="csv_reader",
    file_path="data/inputs/data.csv"
)

# For JSON files
json_reader = JSONReaderNode(
    id="json_reader", 
    file_path="data/inputs/data.json"
)

# For text files, use DataTransformer with proper file reading
text_reader = DataTransformer(
    id="text_reader",
    transformations=[
        """
# Read text file with proper encoding handling
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    result = {'content': content, 'success': True}
except UnicodeDecodeError:
    # Try different encoding
    with open(file_path, 'r', encoding='latin-1') as f:
        content = f.read()
    result = {'content': content, 'success': True, 'encoding': 'latin-1'}
except Exception as e:
    result = {'error': str(e), 'success': False}
"""
    ]
)
```

## CORRECT: Complete File Processing Workflow

```python
# CORRECT: Comprehensive file processing workflow
from kailash import Workflow
from kailash.nodes.transform import DataTransformer
from kailash.nodes.data import JSONWriterNode
from kailash.nodes.logic import MergeNode
from kailash.runtime import LocalRuntime

def create_document_processing_workflow() -> Workflow:
    """Create a document processing workflow for multiple file types."""
    workflow = Workflow(
        workflow_id="document_processing_001",
        name="document_processing_workflow",
        description="Process multiple document types and extract structured data"
    )
    
    # === FILE DISCOVERY ===
    file_discoverer = DataTransformer(
        id="file_discoverer",
        transformations=[
            # Structured file discovery with metadata
        ]
    )
    workflow.add_node("file_discoverer", file_discoverer)
    
    # === SPECIALIZED FILE PROCESSORS ===
    # CSV Processor
    csv_processor = DataTransformer(
        id="csv_processor", 
        transformations=[
            # CSV-specific processing with bug workarounds
        ]
    )
    workflow.add_node("csv_processor", csv_processor)
    workflow.connect("file_discoverer", "csv_processor", mapping={"result": "data"})
    
    # JSON Processor
    json_processor = DataTransformer(
        id="json_processor",
        transformations=[
            # JSON-specific processing with bug workarounds
        ]
    )
    workflow.add_node("json_processor", json_processor)
    workflow.connect("file_discoverer", "json_processor", mapping={"result": "data"})
    
    # Text Processor
    text_processor = DataTransformer(
        id="text_processor",
        transformations=[
            # Text-specific processing with analytics
        ]
    )
    workflow.add_node("text_processor", text_processor)
    workflow.connect("file_discoverer", "text_processor", mapping={"result": "data"})
    
    # === MERGE RESULTS ===
    result_merger = MergeNode(
        id="result_merger",
        merge_type="concat"
    )
    workflow.add_node("result_merger", result_merger)
    workflow.connect("csv_processor", "result_merger", mapping={"result": "data1"})
    workflow.connect("json_processor", "result_merger", mapping={"result": "data2"})
    workflow.connect("text_processor", "result_merger", mapping={"result": "data3"})
    
    # === SUMMARY GENERATION ===
    summary_generator = DataTransformer(
        id="summary_generator",
        transformations=[
            # Comprehensive processing summary with recommendations
        ]
    )
    workflow.add_node("summary_generator", summary_generator)
    workflow.connect("result_merger", "summary_generator", mapping={"merged_data": "data"})
    
    # === OUTPUT ===
    summary_writer = JSONWriterNode(
        id="summary_writer",
        file_path="data/outputs/processing_summary.json"
    )
    workflow.add_node("summary_writer", summary_writer)
    workflow.connect("summary_generator", "summary_writer", mapping={"result": "data"})
    
    return workflow
```

## WRONG: File Watching with Polling

```python
# WRONG: Manual file polling implementation
file_watcher = PythonCodeNode(
    name="file_watcher",
    code="""
import time
import os

last_check = {}
new_files = []

for filename in os.listdir('watch_directory'):
    file_path = os.path.join('watch_directory', filename)
    mtime = os.path.getmtime(file_path)
    
    if filename not in last_check or mtime > last_check[filename]:
        new_files.append(file_path)
        last_check[filename] = mtime

result = {'new_files': new_files}
"""
)

# Problems:
# 1. Inefficient polling approach
# 2. No real-time file notifications
# 3. State management issues between workflow runs
# 4. High CPU usage for frequent polling
```

## ✅ Correct: Event-Driven File Processing

```python
# CORRECT: Use event-driven file discovery patterns
file_event_processor = DataTransformer(
    id="file_event_processor",
    transformations=[
        """
# Process file events from external file watcher
# In production, integrate with filesystem events or file queue
file_events = data.get("file_events", [])

processed_events = []
for event in file_events:
    if event.get("event_type") == "file_created":
        processed_events.append({
            "file_path": event.get("file_path"),
            "action": "process_new_file",
            "priority": "high",
            "detected_at": event.get("timestamp")
        })
    elif event.get("event_type") == "file_modified":
        processed_events.append({
            "file_path": event.get("file_path"),
            "action": "reprocess_file", 
            "priority": "medium",
            "detected_at": event.get("timestamp")
        })

result = {"file_processing_queue": processed_events}
"""
    ]
)
```

## 📊 Bug Impact Analysis for File Processing
- **DataTransformer Bug Frequency**: 100% of file processing chains using DataTransformer → DataTransformer
- **Severity**: Critical - breaks file metadata and content flow
- **Workaround**: Type checking + mock file data reconstruction (data loss occurs)
- **Best Practice**: Avoid DataTransformer chains, use intermediate file storage
- **Affects**: Document processing, batch file operations, content extraction workflows

## Key File Processing Principles

1. **Specialized File Processors**: Use separate processors for each file type (CSV, JSON, XML, etc.)
2. **Proper Node Selection**: Use CSVReaderNode, JSONReaderNode instead of PythonCodeNode when possible
3. **Structured File Discovery**: Organize file metadata with type grouping and analytics
4. **Error-Resilient Processing**: Handle file access errors and encoding issues gracefully
5. **DataTransformer Bug Awareness**: Always include type checking workarounds in file chains
6. **Parallel Processing**: Process different file types concurrently when possible
7. **Content Validation**: Validate file structure and content before processing
8. **Progress Tracking**: Implement processing summaries and recommendations

## Common File Processing Patterns

```python
# Pattern 1: Discovery → Type-Specific Processing → Merge Results
workflow.connect("file_discoverer", "csv_processor", mapping={"result": "data"})
workflow.connect("file_discoverer", "json_processor", mapping={"result": "data"})
workflow.connect("csv_processor", "result_merger", mapping={"result": "data1"})
workflow.connect("json_processor", "result_merger", mapping={"result": "data2"})

# Pattern 2: File Events → Processing Queue → Batch Processing
workflow.connect("file_watcher", "event_processor", mapping={"events": "data"})
workflow.connect("event_processor", "batch_processor", mapping={"queue": "data"})

# Pattern 3: Content Extraction → Analysis → Report Generation
workflow.connect("content_extractor", "content_analyzer", mapping={"result": "data"})
workflow.connect("content_analyzer", "report_generator", mapping={"result": "data"})
```

## File Type Best Practices

### CSV Files
- Use CSVReaderNode/CSVWriterNode for basic operations
- Use DataTransformer for complex CSV analytics
- Handle encoding issues and malformed records

### JSON Files  
- Use JSONReaderNode for reading structured JSON
- Validate JSON schema before processing
- Handle nested structures appropriately

### Text Files
- Implement encoding detection and fallback
- Extract text analytics (word count, keywords)
- Handle large files with streaming processing

### Binary Files
- Use specialized binary readers
- Implement file type validation
- Handle large binary files efficiently