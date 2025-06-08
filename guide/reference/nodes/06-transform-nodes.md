# Transform & Processing Nodes

**Module**: `kailash.nodes.transform`
**Last Updated**: 2025-01-06

This document covers data transformation and processing nodes including chunkers, formatters, and processors.

## Table of Contents
- [Chunking Nodes](#chunking-nodes)
- [Formatting Nodes](#formatting-nodes)
- [Processing Nodes](#processing-nodes)

## Chunking Nodes

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
  filter_node = FilterNode()
  result = filter_node.run(
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
  transformer = DataTransformerNode()
  result = transformer.run(
      data=[{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}],
      operations=[
          {"type": "filter", "condition": "age > 25"},
          {"type": "sort", "key": "age", "reverse": True}
      ]
  )
  ```

## See Also
- [Data Nodes](03-data-nodes.md) - Data I/O operations
- [Logic Nodes](05-logic-nodes.md) - Control flow
- [API Reference](../api/07-nodes-transform.yaml) - Detailed API documentation
