# ADR-0027: Node Organization Architecture

## Status
**Accepted** - *2025-06-02*

## Context

The Kailash Python SDK has grown to include many specialized nodes for different purposes. Previously, custom nodes for RAG (Retrieval-Augmented Generation) workflows were defined inline within example scripts, making them difficult to reuse and maintain. We needed a clear organizational structure for nodes that:

1. Groups related functionality logically
2. Supports future extensibility (e.g., multiple similarity methods)
3. Follows separation of concerns principles
4. Makes nodes easily discoverable and reusable
5. Maintains backward compatibility with existing workflows

## Decision

We will organize nodes into logical categories based on their **functional purpose** rather than implementation details:

### Node Categories

#### `src/kailash/nodes/data/`
- **sources.py**: Data input/source nodes that provide raw data
  - `DocumentSourceNode` - Sample document provider
  - `QuerySourceNode` - Sample query provider
- **retrieval.py**: Document retrieval and similarity scoring
  - `RelevanceScorerNode` - Multi-method similarity scoring (cosine, BM25, TF-IDF)
- **readers.py**: File reading nodes (existing)
- **writers.py**: File writing nodes (existing)
- **sql.py**: Database interaction nodes (existing)
- **vector_db.py**: Vector database nodes (existing)

#### `src/kailash/nodes/transform/`
- **chunkers.py**: Document chunking and splitting
  - `HierarchicalChunkerNode` - Sentence-aware document chunking
- **formatters.py**: Text formatting and transformation
  - `ChunkTextExtractorNode` - Extract text content from chunks
  - `QueryTextWrapperNode` - Wrap queries for batch processing
  - `ContextFormatterNode` - Format context and create LLM messages
- **processors.py**: Data transformation nodes (existing)

#### `src/kailash/nodes/ai/`
- **llm_agent.py**: Large Language Model agents (existing)
- **embedding_generator.py**: Vector embedding generation (existing)
- **ai_providers.py**: Unified AI provider architecture (existing)

### Key Design Principles

1. **Functional Grouping**: Nodes are grouped by what they do, not how they do it
2. **Extensibility**: Easy to add new similarity methods, chunking strategies, formatters
3. **Reusability**: All nodes can be imported and used across different workflows
4. **Separation of Concerns**:
   - Data operations (sources, retrieval, I/O)
   - Transformations (chunking, formatting, processing)
   - AI operations (LLM, embeddings, providers)

## Implementation

### Node Files Created

1. **`src/kailash/nodes/data/sources.py`**
   ```python
   from kailash.nodes.data.sources import DocumentSourceNode, QuerySourceNode
   ```

2. **`src/kailash/nodes/data/retrieval.py`**
   ```python
   from kailash.nodes.data.retrieval import RelevanceScorerNode
   ```

3. **`src/kailash/nodes/transform/chunkers.py`**
   ```python
   from kailash.nodes.transform.chunkers import HierarchicalChunkerNode
   ```

4. **`src/kailash/nodes/transform/formatters.py`**
   ```python
   from kailash.nodes.transform.formatters import (
       ChunkTextExtractorNode,
       QueryTextWrapperNode,
       ContextFormatterNode
   )
   ```

### Updated Import Structure

Example workflows can now import nodes cleanly:
```python
from kailash.nodes.data.sources import DocumentSourceNode, QuerySourceNode
from kailash.nodes.data.retrieval import RelevanceScorerNode
from kailash.nodes.transform.chunkers import HierarchicalChunkerNode
from kailash.nodes.transform.formatters import (
    ChunkTextExtractorNode,
    QueryTextWrapperNode,
    ContextFormatterNode,
)
```

### Backward Compatibility

- All existing node imports continue to work
- Example workflows updated to use new import structure
- All `__init__.py` files updated to export new nodes

## Consequences

### Positive
- **Better Organization**: Logical grouping makes nodes easier to find
- **Extensibility**: Easy to add new similarity methods (BM25, TF-IDF) to retrieval.py
- **Reusability**: Nodes can be used across multiple workflow types
- **Maintainability**: Related functionality is co-located
- **Discovery**: Developers can easily find relevant nodes by category

### Negative
- **Migration Effort**: Existing custom workflows need import updates
- **Learning Curve**: Developers need to understand the new organization
- **File Count**: More files to maintain (though better organized)

### Neutral
- **Performance**: No impact on runtime performance
- **Testing**: Tests continue to work with updated imports

## Future Extensibility

This organization supports planned features:

1. **Multiple Similarity Methods**:
   - Add BM25, TF-IDF implementations to `retrieval.py`
   - Support hybrid search combining multiple methods

2. **Advanced Chunking**:
   - Add semantic chunking, recursive chunking to `chunkers.py`
   - Support different chunking strategies per document type

3. **Context Strategies**:
   - Add different prompt templates to `formatters.py`
   - Support context windowing, summarization

## Related ADRs

- [ADR-0025: Hierarchical Document Processing](0025-hierarchical-document-processing.md)
- [ADR-0026: Unified AI Provider Architecture](0026-unified-ai-provider-architecture.md)
- [ADR-0009: Source Layout for Package](0009-src-layout-for-package.md)

## Validation

The reorganization was validated by:
1. Successfully running the hierarchical RAG workflow
2. Maintaining all existing functionality
3. Confirming clean import structure
4. Verifying extensibility for future similarity methods

Example workflow continues to produce high-quality results:
- 768-dimensional embeddings via Ollama nomic-embed-text
- Relevance scores: 0.902, 0.754, 0.696 (cosine similarity)
- Quality LLM responses from llama3.2 model
