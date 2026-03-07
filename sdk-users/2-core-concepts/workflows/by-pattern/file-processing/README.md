# File Processing Workflows

This directory contains comprehensive file processing workflow patterns using the Kailash SDK.

## Overview

File processing workflows handle the discovery, reading, transformation, and analysis of files across various formats. These patterns are designed for real-world enterprise scenarios where documents, data files, and media need to be processed at scale.

## Core Pattern: Document Discovery and Processing

The document processor workflow demonstrates how to:
- **Discover files** using DirectoryReaderNode for real file system traversal
- **Process multiple formats** (CSV, JSON, TXT) with appropriate readers
- **Analyze content** and extract meaningful insights
- **Generate reports** with processing statistics and summaries

### Key Features

✅ **Real File Processing** - No mocks, uses actual file system
✅ **Multi-Format Support** - CSV, JSON, TXT files handled seamlessly
✅ **Comprehensive Analysis** - File metadata, content analysis, and statistics
✅ **Production Ready** - Error handling and proper data validation
✅ **Docker Compatible** - Works with containerized file systems

## Available Scripts

### `scripts/document_processor.py`

**Purpose**: Comprehensive multi-format document processing pipeline

**What it does**:
1. Discovers files in a directory using DirectoryReaderNode
2. Processes CSV files with CSVReaderNode for structured data
3. Processes JSON files with JSONReaderNode for configuration/metadata
4. Processes text files with TextReaderNode for content analysis
5. Merges results and generates comprehensive analytics report

**Usage**:
```bash
# Run the document processor
python sdk-users/workflows/by-pattern/file-processing/scripts/document_processor.py

# The script will:
# - Create sample files in /data/inputs/
# - Process all files in the directory
# - Generate analysis report in /data/outputs/file-processing/
```

**Output**:
- Processing statistics (file counts, sizes, formats)
- Content analysis (record counts, data insights)
- Comprehensive summary report in JSON format

## Node Usage Patterns

### File Discovery
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

# Use DirectoryReaderNode for real file discovery
file_discovery = DirectoryReaderNode(
    name="file_discovery",
    directory_path=str(get_input_data_path(".", subdirectory="mixed_files")),
    include_patterns=["*.csv", "*.json", "*.txt"],
    recursive=True
)

```

### Multi-Format Processing
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

# CSV processing for structured data
csv_processor = CSVReaderNode(
    name="csv_processor",
    file_path=""  # Set at runtime
)

# JSON processing for configuration/metadata
json_processor = JSONReaderNode(
    name="json_processor",
    file_path=""  # Set at runtime
)

# Text processing for content analysis
text_processor = TextReaderNode(
    name="text_processor",
    file_path=""  # Set at runtime
)

```

### Results Aggregation
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

# Merge processing results
results_merger = MergeNode(
    name="results_merger",
    merge_strategy="union"
)

```

## Integration with Enterprise Systems

### File System Integration
- **Network Drives**: Works with mounted network file systems
- **Cloud Storage**: Compatible with cloud-mounted directories
- **Docker Volumes**: Supports containerized file processing

### Data Pipeline Integration
- **ETL Workflows**: Can be part of larger data processing pipelines
- **Content Management**: Integrates with document management systems
- **Analytics Platforms**: Outputs compatible with BI and analytics tools

## Best Practices

### File Organization
```
/data/inputs/mixed_files/
├── data/
│   ├── customers.csv      # Structured data files
│   ├── products.csv
│   └── transactions.csv
├── config/
│   ├── settings.json      # Configuration files
│   └── metadata.json
└── docs/
    ├── readme.txt         # Documentation files
    └── changelog.txt
```

### Error Handling
- Use try/catch blocks for file operations
- Validate file existence before processing
- Handle format-specific parsing errors
- Log processing statistics and errors

### Performance Optimization
- Process files in parallel when possible
- Use appropriate batch sizes for large files
- Implement progress tracking for long-running operations
- Cache results when appropriate

## Common Use Cases

### Document Management
- **Legal Documents**: Process contracts, agreements, policies
- **HR Documents**: Employee records, policies, training materials
- **Financial Documents**: Reports, statements, compliance documents

### Data Integration
- **Multi-Source ETL**: Combine data from various file formats
- **Data Validation**: Verify data consistency across files
- **Data Migration**: Convert between formats and systems

### Content Analysis
- **Text Mining**: Extract insights from document content
- **Metadata Extraction**: Gather file properties and statistics
- **Quality Assessment**: Validate data completeness and accuracy

## Advanced Patterns

### Conditional Processing
Use SwitchNode to route files based on type, size, or content:
```python
# Route files by type for specialized processing
file_router = SwitchNode(
    name="file_router",
    condition_# mapping removed,
        "json_files": "file_extension == 'json'",
        "text_files": "file_extension == 'txt'"
    }
)

```

### Parallel Processing
Use multiple processors for different file types simultaneously:
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

# Process different file types in parallel
workflow = WorkflowBuilder()
workflow.add_connection("file_discovery", ["csv_processor", "json_processor", "text_processor"])

```

### Results Transformation
Transform and enrich file processing results:
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

# Enhance results with additional analysis
enhancer = PythonCodeNode.from_function(
    func=enhance_file_analysis,
    name="file_enhancer"
)

```

## Related Patterns

- **[Data Processing](../data-processing/)** - For structured data workflows
- **[API Integration](../api-integration/)** - For file-based API interactions
- **[ETL Patterns](../etl/)** - For extract, transform, load workflows

## Production Checklist

- [ ] File paths use centralized data structure (`/data/inputs/`, `/data/outputs/`)
- [ ] Error handling covers file not found, permission, and format errors
- [ ] Logging captures processing statistics and errors
- [ ] Output validation ensures data quality
- [ ] Security considerations for file access permissions
- [ ] Performance testing with realistic file sizes and quantities
- [ ] Docker compatibility verified with volume mounts
- [ ] Backup and recovery procedures documented

---

**Next Steps**:
- Review `scripts/document_processor.py` for implementation details
- Adapt the pattern for your specific file types and processing needs
- See the Kailash SDK repository for training examples
