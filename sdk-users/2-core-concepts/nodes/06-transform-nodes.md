# Transform & Processing Nodes

**Module**: `kailash.nodes.transform`
**Last Updated**: 2025-01-06

This document covers data transformation and processing nodes including chunkers, formatters, and processors.

## Table of Contents
- [Chunking Nodes](#chunking-nodes)
- [Formatting Nodes](#formatting-nodes)
- [Processing Nodes](#processing-nodes)

## Chunking Nodes

### SemanticChunkerNode ⭐ **NEW**
- **Module**: `kailash.nodes.transform.chunkers`
- **Purpose**: Intelligent text chunking based on semantic similarity
- **Key Features**: Uses embedding analysis to find natural topic boundaries
- **Parameters**:
  - `chunk_size`: Target chunk size in characters (default: 2000)
  - `similarity_threshold`: Similarity threshold for boundaries (0.0-1.0, default: 0.75)
  - `chunk_overlap`: Character overlap between chunks (default: 200)
  - `window_size`: Sentences to consider for similarity (default: 3)
- **Best For**: Narrative text, general documents, content with flowing topics
- **Example**:
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

  chunker = SemanticChunkerNode(chunk_size=1000, similarity_threshold=0.75)
  result = chunker.run(text="Your long document text here...")
  chunks = result["chunks"]  # List of semantically coherent chunks

  ```

### StatisticalChunkerNode ⭐ **NEW**
- **Module**: `kailash.nodes.transform.chunkers`
- **Purpose**: Intelligent text chunking using embedding variance analysis
- **Key Features**: Detects topic boundaries using statistical variance in embeddings
- **Parameters**:
  - `chunk_size`: Target chunk size in characters (default: 1500)
  - `variance_threshold`: Variance threshold for boundaries (0.0-1.0, default: 0.5)
  - `min_sentences_per_chunk`: Minimum sentences per chunk (default: 3)
  - `max_sentences_per_chunk`: Maximum sentences per chunk (default: 15)
  - `use_sliding_window`: Enable sliding window analysis (default: True)
- **Best For**: Technical documents, structured content, academic papers
- **Example**:
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

  chunker = StatisticalChunkerNode(chunk_size=800, variance_threshold=0.6)
  result = chunker.run(text="Your technical document here...")
  chunks = result["chunks"]  # List of variance-based chunks

  ```

### HierarchicalChunkerNode
- **Module**: `kailash.nodes.transform.chunkers`
- **Purpose**: Create hierarchical text chunks
- **Parameters**:
  - `levels`: Hierarchy levels
  - `chunk_sizes`: Size per level
  - `overlap_ratios`: Overlap per level

## Formatting Nodes

### ChunkTextExtractorNode
- **Module**: `kailash.nodes.transform.formatters`
- **Purpose**: Extract text from chunks
- **Parameters**:
  - `chunks`: Input chunks
  - `extraction_method`: How to extract

### ContextFormatterNode
- **Module**: `kailash.nodes.transform.formatters`
- **Purpose**: Format context for processing
- **Parameters**:
  - `template`: Format template
  - `variables`: Template variables

### QueryTextWrapperNode
- **Module**: `kailash.nodes.transform.formatters`
- **Purpose**: Wrap queries with additional text
- **Parameters**:
  - `query`: Original query
  - `prefix`: Text prefix
  - `suffix`: Text suffix

## Processing Nodes

### FilterNode
- **Module**: `kailash.nodes.transform.processors`
- **Purpose**: Filters data based on configurable conditions and operators
- **Parameters**:
  - `data`: Input data to filter (list)
  - `field`: Field name for dict-based filtering (optional)
  - `operator`: Comparison operator (==, !=, >, <, >=, <=, contains)
  - `value`: Value to compare against
- **Example**:
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

  filter_node = FilterNode()
  result = filter_node.execute(
      data=[1, 2, 3, 4, 5],
      operator=">",
      value=3
  )  # Returns: {"filtered_data": [4, 5]}

  ```

### DataTransformerNode
- **Module**: `kailash.nodes.transform.processors`
- **Purpose**: Transform data using configurable operations
- **Operations**:
  - `filter`: Filter data based on conditions
  - `map`: Transform each item
  - `reduce`: Aggregate data
  - `sort`: Sort data by key
  - `group`: Group data by field
- **Example**:
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

  transformer = "DataTransformerNode"
  result = transformer.run(
      data=[{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}],
      operations=[
          {"type": "filter", "condition": "age > 25"},
          {"type": "sort", "key": "age", "reverse": True}
      ]
  )

  ```

### ContextualCompressorNode ⭐ **NEW**
- **Module**: `kailash.nodes.transform.processors`
- **Purpose**: Intelligent compression of retrieved content for optimal context utilization
- **Key Features**:
  - Query-aware relevance scoring and filtering
  - Multiple compression strategies (extractive, abstractive, hierarchical)
  - Token budget management with smart truncation
  - Diversity filtering to avoid redundant content
  - Comprehensive compression metadata
- **Parameters**:
  - `query`: Query for relevance-based compression (required)
  - `retrieved_docs`: List of documents to compress (required)
  - `compression_target`: Target token count (default: 4000)
  - `compression_ratio`: Target compression ratio 0.0-1.0 (default: 0.6)
  - `relevance_threshold`: Minimum relevance score 0.0-1.0 (default: 0.7)
  - `compression_strategy`: Strategy to use (default: "extractive_summarization")
    - `"extractive_summarization"`: Extract most relevant sentences
    - `"abstractive_synthesis"`: Create structured summaries
    - `"hierarchical_organization"`: Organize by importance levels
- **Best For**:
  - Managing LLM context windows
  - RAG systems with large document collections
  - Token-budgeted applications
  - Information density optimization
- **Performance**: Typically achieves 50-70% token reduction while preserving relevance
- **Example**:
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

  compressor = ContextualCompressorNode(
      compression_target=2000,
      relevance_threshold=0.75,
      compression_strategy="extractive_summarization"
  )
  result = compressor.run(
      query="machine learning algorithms",
      retrieved_docs=[
          {"content": "ML algorithms learn from data...", "similarity_score": 0.9},
          {"content": "Deep learning uses neural networks...", "similarity_score": 0.8}
      ]
  )
  compressed_text = result["compressed_context"]
  metadata = result["compression_metadata"]  # Detailed compression stats

  ```
- **Output Structure**:
  ```python
  {
      "compressed_context": "Compressed text content",
      "compression_metadata": {
          "original_document_count": 10,
          "selected_passage_count": 6,
          "compression_ratio": 0.65,
          "avg_relevance_score": 0.82
      },
      "num_input_docs": 10,
      "compression_success": True
  }

  ```

## See Also
- [Data Nodes](03-data-nodes.md) - Data I/O operations
- [Logic Nodes](05-logic-nodes.md) - Control flow
- [API Reference](../api/07-nodes-transform.yaml) - Detailed API documentation
