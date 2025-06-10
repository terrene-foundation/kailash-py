"""
DirectoryReaderNode Example

Demonstrates file discovery patterns using DirectoryReaderNode
instead of manual file operations.
"""

from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import DirectoryReaderNode, JSONWriterNode
from kailash.runtime import LocalRuntime


def create_file_discovery_workflow():
    """Create a workflow that discovers and processes files."""
    workflow = Workflow(workflow_id="file_discovery", name="File Discovery Example")

    # Pattern 1: Basic File Discovery
    # ==============================
    discoverer = DirectoryReaderNode(
        name="discoverer",
        directory_path="data/inputs",  # Relative path
        recursive=False,  # Don't scan subdirectories
        file_patterns=["*.csv", "*.json", "*.txt"],  # Specific patterns
        include_hidden=False,  # Skip hidden files
        include_metadata=True,  # Get file metadata
    )
    workflow.add_node("discoverer", discoverer)

    # Pattern 2: Process Discovery Results
    # ===================================
    file_router = PythonCodeNode(
        name="file_router",
        code="""
# Organize files by type
files_by_type = {}
total_size = 0

for file in discovered_files:
    ext = file.get('extension', 'unknown')
    if ext not in files_by_type:
        files_by_type[ext] = []
    files_by_type[ext].append(file)
    total_size += file.get('size', 0)

# Create summary
summary = {
    'total_files': len(discovered_files),
    'total_size_bytes': total_size,
    'total_size_mb': round(total_size / 1024 / 1024, 2),
    'file_types': list(files_by_type.keys()),
    'files_per_type': {ext: len(files) for ext, files in files_by_type.items()}
}

result = {
    'files_by_type': files_by_type,
    'summary': summary,
    'csv_files': files_by_type.get('.csv', []),
    'json_files': files_by_type.get('.json', []),
    'text_files': files_by_type.get('.txt', [])
}
""",
    )
    workflow.add_node("file_router", file_router)

    # Connect with different variable name (avoid PythonCodeNode exclusion)
    workflow.connect("discoverer", "file_router", mapping={"files": "discovered_files"})

    # Pattern 3: Filter Files by Criteria
    # ==================================
    large_file_filter = PythonCodeNode(
        name="large_file_filter",
        code="""
# Filter files larger than 1KB
THRESHOLD = 1024  # bytes

large_files = []
small_files = []

for file in all_files:
    if file.get('size', 0) > THRESHOLD:
        large_files.append({
            'name': file['name'],
            'path': file['path'],
            'size': file['size'],
            'size_kb': round(file['size'] / 1024, 2)
        })
    else:
        small_files.append(file['name'])

result = {
    'large_files': large_files,
    'large_count': len(large_files),
    'small_files': small_files,
    'small_count': len(small_files),
    'processing_recommendation': 'batch' if len(large_files) > 10 else 'sequential'
}
""",
    )
    workflow.add_node("large_file_filter", large_file_filter)
    workflow.connect("discoverer", "large_file_filter", mapping={"files": "all_files"})

    # Pattern 4: Recent File Detection
    # ===============================
    recent_file_detector = PythonCodeNode(
        name="recent_file_detector",
        code="""
from datetime import datetime, timedelta

# Find files modified in last 24 hours
cutoff = datetime.now() - timedelta(hours=24)
recent_files = []
older_files = []

for file in file_list:
    try:
        # Parse ISO format timestamp
        modified_str = file.get('modified', '')
        if modified_str:
            # Remove 'Z' and add UTC offset for parsing
            modified = datetime.fromisoformat(modified_str.replace('Z', '+00:00'))
            
            if modified > cutoff:
                recent_files.append({
                    'name': file['name'],
                    'modified': modified_str,
                    'hours_ago': round((datetime.now() - modified).seconds / 3600, 1)
                })
            else:
                older_files.append(file['name'])
    except Exception as e:
        # Handle parsing errors
        print(f"Error parsing date for {file.get('name')}: {e}")

result = {
    'recent_files': recent_files,
    'recent_count': len(recent_files),
    'older_count': len(older_files),
    'alert': len(recent_files) > 0
}
""",
    )
    workflow.add_node("recent_file_detector", recent_file_detector)
    workflow.connect(
        "discoverer", "recent_file_detector", mapping={"files": "file_list"}
    )

    # Pattern 5: Prepare for Batch Processing
    # ======================================
    batch_preparer = PythonCodeNode(
        name="batch_preparer",
        code="""
BATCH_SIZE = 5

# Get CSV files from router output
csv_files = router_output.get('csv_files', [])

# Create batches
batches = []
for i in range(0, len(csv_files), BATCH_SIZE):
    batch = csv_files[i:i + BATCH_SIZE]
    batches.append({
        'batch_id': i // BATCH_SIZE + 1,
        'files': [f['path'] for f in batch],
        'file_count': len(batch),
        'total_size': sum(f.get('size', 0) for f in batch)
    })

result = {
    'batches': batches,
    'total_batches': len(batches),
    'files_per_batch': BATCH_SIZE,
    'ready_for_processing': len(batches) > 0
}
""",
    )
    workflow.add_node("batch_preparer", batch_preparer)
    workflow.connect(
        "file_router", "batch_preparer", mapping={"result": "router_output"}
    )

    # Pattern 6: Generate Processing Report
    # ====================================
    report_generator = PythonCodeNode(
        name="report_generator",
        code="""
# Aggregate all analysis results
report = {
    'scan_summary': router_data.get('summary', {}),
    'large_files': size_data.get('large_files', []),
    'recent_activity': recent_data.get('recent_files', []),
    'batch_plan': batch_data.get('batches', []),
    'recommendations': []
}

# Add recommendations based on findings
if size_data.get('large_count', 0) > 5:
    report['recommendations'].append('Consider parallel processing for large files')

if recent_data.get('alert', False):
    report['recommendations'].append('New files detected - prioritize processing')

if batch_data.get('total_batches', 0) > 10:
    report['recommendations'].append('Large dataset - consider distributed processing')

# Add timestamp
from datetime import datetime
report['generated_at'] = datetime.now().isoformat()
report['status'] = 'ready'

result = report
""",
    )
    workflow.add_node("report_generator", report_generator)

    # Connect all analyzers to report generator
    workflow.connect(
        "file_router", "report_generator", mapping={"result": "router_data"}
    )
    workflow.connect(
        "large_file_filter", "report_generator", mapping={"result": "size_data"}
    )
    workflow.connect(
        "recent_file_detector", "report_generator", mapping={"result": "recent_data"}
    )
    workflow.connect(
        "batch_preparer", "report_generator", mapping={"result": "batch_data"}
    )

    # Save report
    report_writer = JSONWriterNode(
        name="report_writer", file_path="data/outputs/discovery_report.json"
    )
    workflow.add_node("report_writer", report_writer)
    workflow.connect("report_generator", "report_writer", mapping={"result": "data"})

    return workflow


def demonstrate_anti_patterns():
    """Show what NOT to do - manual file operations."""

    print("\nANTI-PATTERN: Manual file discovery")
    print("=" * 50)

    # WRONG: Manual file discovery in PythonCodeNode
    _ = PythonCodeNode(
        name="bad_discovery",
        code="""
import os
import glob

# DON'T DO THIS - Use DirectoryReaderNode instead!
files = []
for pattern in ['*.csv', '*.json', '*.txt']:
    files.extend(glob.glob(f'data/inputs/{pattern}'))

# Manual metadata gathering
file_info = []
for file_path in files:
    stat = os.stat(file_path)
    file_info.append({
        'path': file_path,
        'size': stat.st_size,
        'modified': stat.st_mtime
    })

result = {'files': file_info}
""",
    )

    print("Problems with manual discovery:")
    print("- No built-in error handling")
    print("- No consistent metadata format")
    print("- Doesn't integrate with Kailash features")
    print("- More code to maintain")
    print("- Platform-specific issues")


def main():
    """Run the file discovery example."""
    print("DirectoryReaderNode Example")
    print("=" * 50)

    workflow = create_file_discovery_workflow()
    runtime = LocalRuntime()

    # Create sample directory structure
    import os

    os.makedirs("data/inputs", exist_ok=True)
    os.makedirs("data/outputs", exist_ok=True)

    # Create some sample files
    sample_files = [
        ("data/inputs/customers.csv", "id,name,email\n1,John,john@example.com"),
        ("data/inputs/config.json", '{"version": "1.0", "debug": true}'),
        ("data/inputs/readme.txt", "Sample readme file"),
    ]

    for file_path, content in sample_files:
        with open(file_path, "w") as f:
            f.write(content)

    print("\nRunning file discovery workflow...")

    # Execute workflow
    result, _ = runtime.execute(workflow, parameters={})

    print("\nWorkflow completed!")
    print("\nCheck data/outputs/discovery_report.json for results")

    # Show anti-patterns
    demonstrate_anti_patterns()


if __name__ == "__main__":
    main()
