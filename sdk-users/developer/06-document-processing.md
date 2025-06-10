# Document Processing Workflows

## Overview

Document processing is a common workflow pattern in Kailash. This guide covers best practices for building robust multi-file document processing pipelines.

## Core Pattern

```
DirectoryReaderNode → Router → Type-Specific Processors → Merger → Output
```

## Complete Example

```python
from kailash import Workflow
from kailash.nodes.data import DirectoryReaderNode, CSVReaderNode, JSONReaderNode, JSONWriterNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.logic import MergeNode
from kailash.runtime import LocalRuntime

def create_document_processor():
    workflow = Workflow(
        workflow_id="doc_processor",
        name="Document Processing Pipeline"
    )
    
    # 1. Discover files
    discoverer = DirectoryReaderNode(
        name="discoverer",
        directory_path="data/inputs",
        file_patterns=["*.csv", "*.json", "*.txt", "*.xml"],
        recursive=False
    )
    workflow.add_node("discoverer", discoverer)
    
    # 2. Route by file type
    router = PythonCodeNode(
        name="router",
        code="""
files_by_type = {}
for file in discovered_files:
    ext = file['extension']
    if ext not in files_by_type:
        files_by_type[ext] = []
    files_by_type[ext].append(file)

result = {
    'csv_files': files_by_type.get('.csv', []),
    'json_files': files_by_type.get('.json', []),
    'text_files': files_by_type.get('.txt', []),
    'file_summary': {ext: len(files) for ext, files in files_by_type.items()}
}
"""
    )
    workflow.add_node("router", router)
    workflow.connect("discoverer", "router", mapping={"files": "discovered_files"})
    
    # 3. Process each file type
    # ... processors for each type
    
    return workflow
```

## File Type Processors

### CSV Processor
```python
csv_processor = PythonCodeNode(
    name="csv_processor",
    code="""
import csv

processed_data = []
for file_info in csv_files:
    # In production, use CSVReaderNode
    # Here showing the pattern
    processed_data.append({
        'file': file_info['name'],
        'path': file_info['path'],
        'size': file_info['size'],
        'status': 'processed'
    })

result = {
    'csv_results': processed_data,
    'csv_count': len(processed_data)
}
"""
)
```

### JSON Processor
```python
json_processor = PythonCodeNode(
    name="json_processor",
    code="""
processed_data = []
for file_info in json_files:
    # Process JSON files
    processed_data.append({
        'file': file_info['name'],
        'type': 'json',
        'status': 'processed'
    })

result = {
    'json_results': processed_data,
    'json_count': len(processed_data)
}
"""
)
```

### Text Processor with Analytics
```python
text_processor = PythonCodeNode(
    name="text_processor",
    code="""
text_analytics = []
for file_info in text_files:
    # Simple analytics (in production, read actual content)
    analytics = {
        'file': file_info['name'],
        'size': file_info['size'],
        'size_category': 'large' if file_info['size'] > 10000 else 'small'
    }
    text_analytics.append(analytics)

result = {
    'text_results': text_analytics,
    'text_count': len(text_analytics)
}
"""
)
```

## Result Aggregation

### Using MergeNode
```python
# Add processors to workflow
workflow.add_node("csv_processor", csv_processor)
workflow.add_node("json_processor", json_processor)
workflow.add_node("text_processor", text_processor)

# Connect router to processors (note different variable names!)
workflow.connect("router", "csv_processor", mapping={"csv_files": "csv_files"})
workflow.connect("router", "json_processor", mapping={"json_files": "json_files"})
workflow.connect("router", "text_processor", mapping={"text_files": "text_files"})

# Merge results
merger = MergeNode(name="merger", merge_type="concat")
workflow.add_node("merger", merger)

workflow.connect("csv_processor", "merger", mapping={"csv_results": "data1"})
workflow.connect("json_processor", "merger", mapping={"json_results": "data2"})
workflow.connect("text_processor", "merger", mapping={"text_results": "data3"})
```

### Custom Aggregation
```python
aggregator = PythonCodeNode(
    name="aggregator",
    code="""
# Combine all results
all_results = []
all_results.extend(csv_data)
all_results.extend(json_data)
all_results.extend(text_data)

# Generate summary
summary = {
    'total_files': len(all_results),
    'by_status': {},
    'processing_time': '2.3s'
}

for result in all_results:
    status = result.get('status', 'unknown')
    summary['by_status'][status] = summary['by_status'].get(status, 0) + 1

result = {
    'detailed_results': all_results,
    'summary': summary
}
"""
)

# Connect processors to aggregator
workflow.connect("csv_processor", "aggregator", mapping={"csv_results": "csv_data"})
workflow.connect("json_processor", "aggregator", mapping={"json_results": "json_data"})
workflow.connect("text_processor", "aggregator", mapping={"text_results": "text_data"})
```

## Advanced Patterns

### Pattern 1: Conditional Processing
```python
conditional_processor = PythonCodeNode(
    name="conditional_processor",
    code="""
large_files = []
small_files = []

for file in all_files:
    if file['size'] > 1_000_000:  # 1MB
        large_files.append(file)
    else:
        small_files.append(file)

result = {
    'large_files': large_files,
    'small_files': small_files,
    'routing_decision': 'parallel' if len(large_files) > 5 else 'sequential'
}
"""
)
```

### Pattern 2: Error Recovery
```python
resilient_processor = PythonCodeNode(
    name="resilient_processor",
    code="""
successful = []
failed = []

for file in input_files:
    try:
        # Simulate processing
        if 'corrupt' not in file['name']:
            successful.append({
                'file': file['name'],
                'status': 'success'
            })
        else:
            raise ValueError("Corrupt file")
    except Exception as e:
        failed.append({
            'file': file['name'],
            'status': 'failed',
            'error': str(e)
        })

result = {
    'successful': successful,
    'failed': failed,
    'success_rate': len(successful) / len(input_files) if input_files else 0
}
"""
)
```

### Pattern 3: Batch Processing
```python
batch_processor = PythonCodeNode(
    name="batch_processor",
    code="""
BATCH_SIZE = 10
batches = []

for i in range(0, len(all_files), BATCH_SIZE):
    batch = all_files[i:i + BATCH_SIZE]
    batches.append({
        'batch_id': i // BATCH_SIZE,
        'files': batch,
        'size': len(batch)
    })

result = {
    'batches': batches,
    'total_batches': len(batches)
}
"""
)
```

## Best Practices

### 1. Use Appropriate Readers
```python
# Good: Use dedicated readers
csv_reader = CSVReaderNode(name="csv_reader")
json_reader = JSONReaderNode(name="json_reader")

# Bad: Manual file reading in PythonCodeNode
```

### 2. Handle Empty Directories
```python
empty_handler = PythonCodeNode(
    name="empty_handler",
    code="""
if not discovered_files:
    result = {
        'status': 'no_files',
        'message': 'No files found matching criteria'
    }
else:
    result = {
        'status': 'ready',
        'file_count': len(discovered_files)
    }
"""
)
```

### 3. Validate File Types
```python
validator = PythonCodeNode(
    name="validator",
    code="""
supported_types = {'.csv', '.json', '.txt', '.xml'}
unsupported = []

for file in all_files:
    if file['extension'] not in supported_types:
        unsupported.append(file)

if unsupported:
    result = {
        'status': 'warning',
        'unsupported_files': unsupported,
        'message': f'{len(unsupported)} unsupported files found'
    }
else:
    result = {'status': 'ok', 'all_supported': True}
"""
)
```

## Common Mistakes to Avoid

### ❌ Processing All Types in One Node
```python
# WRONG: Monolithic processor
all_processor = PythonCodeNode(
    name="all_processor",
    code="""
for file in files:
    if file['extension'] == '.csv':
        # CSV logic
    elif file['extension'] == '.json':
        # JSON logic
    # ... becomes unmaintainable
"""
)
```

### ❌ Using Same Variable Names
```python
# WRONG: Causes PythonCodeNode exclusion issue
workflow.connect("router", "processor", mapping={"result": "result"})

# CORRECT: Different names
workflow.connect("router", "processor", mapping={"result": "router_output"})
```

### ❌ Not Handling Errors
```python
# WRONG: No error handling
processor = PythonCodeNode(
    name="processor",
    code="result = {'count': len(files)}"  # What if 'files' is None?
)

# CORRECT: Defensive coding
processor = PythonCodeNode(
    name="processor",
    code="""
files = files or []  # Handle None
result = {'count': len(files)}
"""
)
```

## Performance Optimization

### 1. Parallel Processing
```python
# Process different file types in parallel
# Each processor can run independently
```

### 2. Lazy Loading
```python
# Only load file metadata, not content
metadata_processor = PythonCodeNode(
    name="metadata_processor",
    code="""
# Process based on metadata only
large_files = [f for f in files if f['size'] > 1_000_000]
result = {'large_file_paths': [f['path'] for f in large_files]}
"""
)
```

### 3. Streaming for Large Files
```python
# For very large files, process in chunks
# Use dedicated streaming nodes when available
```

## Testing Your Pipeline

```python
# Test with various scenarios
test_cases = [
    {"name": "empty_directory", "files": []},
    {"name": "single_csv", "files": ["data.csv"]},
    {"name": "mixed_types", "files": ["a.csv", "b.json", "c.txt"]},
    {"name": "large_dataset", "files": ["big1.csv", "big2.csv"]}
]

# Run workflow with different inputs
runtime = LocalRuntime()
for test in test_cases:
    result = runtime.execute(workflow, parameters={
        "discoverer": {"directory_path": f"test_data/{test['name']}"}
    })
    print(f"Test {test['name']}: {result}")
```