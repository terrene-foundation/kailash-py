# Federated RAG - Distributed Retrieval and Consistency

**Category**: Advanced RAG
**Pattern**: Distributed Retrieval Pipeline with Consistency Checking
**Complexity**: Advanced
**Use Cases**: Multi-source retrieval, distributed knowledge bases, cross-source consistency, source attribution

## Overview

This example demonstrates federated retrieval in RAG using five specialized agents that collaborate to coordinate sources, retrieve from multiple distributed sources, merge results, check consistency, and aggregate final answers with attribution.

### Key Features

- **Source coordination** - Intelligent selection of relevant sources for queries
- **Distributed retrieval** - Parallel retrieval from multiple independent sources
- **Result merging** - Deduplication and merging of results across sources
- **Consistency checking** - Cross-source consistency validation and conflict detection
- **Source attribution** - Transparent attribution of answers to sources

## Architecture

```
User Query + Available Sources
     |
     v
┌──────────────────────────┐
│SourceCoordinatorAgent    │ - Selects relevant sources
└──────────┬───────────────┘
           │ writes to SharedMemoryPool
           v
    ["source_coordination", "federated_pipeline"]
           │
           v
    For each selected source (parallel):
           │
           v
┌──────────────────────────────┐
│DistributedRetrieverAgent     │ - Retrieves from source
└──────────┬───────────────────┘
           │ writes to SharedMemoryPool
           v
    ["distributed_retrieval", "federated_pipeline"]
           │
           v
┌──────────────────────────┐
│ResultMergerAgent          │ - Merges and deduplicates
└──────────┬───────────────┘
           │ writes to SharedMemoryPool
           v
    ["result_merging", "federated_pipeline"]
           │
           v
┌──────────────────────────┐
│ConsistencyCheckerAgent    │ - Checks consistency
└──────────┬───────────────┘
           │ writes to SharedMemoryPool
           v
    ["consistency_check", "federated_pipeline"]
           │
           v
┌──────────────────────────┐
│FinalAggregatorAgent       │ - Aggregates with attribution
└──────────┬───────────────┘
           │
           v
    Final Answer + Source Attribution
```

## Agents

### 1. SourceCoordinatorAgent

**Signature**: `SourceCoordinationSignature`
- **Inputs**:
  - `query` (str) - User query
  - `available_sources` (str) - Available sources as JSON
- **Outputs**:
  - `selected_sources` (str) - Selected sources as JSON
  - `selection_reasoning` (str) - Reasoning for selection

**Responsibilities**:
- Analyze query to determine relevant sources
- Select optimal sources based on query type
- Provide reasoning for source selection
- Write coordination to SharedMemoryPool

**SharedMemory Tags**: `["source_coordination", "federated_pipeline"]`, segment: `"federated_pipeline"`

### 2. DistributedRetrieverAgent

**Signature**: `DistributedRetrievalSignature`
- **Inputs**:
  - `query` (str) - User query
  - `source` (str) - Source to retrieve from as JSON
- **Outputs**:
  - `documents` (str) - Retrieved documents as JSON
  - `source_id` (str) - Source identifier

**Responsibilities**:
- Retrieve documents from individual source
- Tag documents with source identifier
- Write retrieval to SharedMemoryPool

**SharedMemory Tags**: `["distributed_retrieval", "federated_pipeline"]`, segment: `"federated_pipeline"`

### 3. ResultMergerAgent

**Signature**: `ResultMergingSignature`
- **Inputs**: `retrieval_results` (str) - Results from all sources as JSON
- **Outputs**:
  - `merged_documents` (str) - Merged documents as JSON
  - `deduplication_count` (str) - Number of duplicates removed

**Responsibilities**:
- Merge results from multiple sources
- Deduplicate similar documents
- Write merging to SharedMemoryPool

**SharedMemory Tags**: `["result_merging", "federated_pipeline"]`, segment: `"federated_pipeline"`

### 4. ConsistencyCheckerAgent

**Signature**: `ConsistencyCheckSignature`
- **Inputs**:
  - `query` (str) - User query
  - `merged_documents` (str) - Merged documents as JSON
- **Outputs**:
  - `consistency_score` (str) - Consistency score (0-1)
  - `conflicts` (str) - Detected conflicts as JSON

**Responsibilities**:
- Check consistency across sources
- Detect conflicts and contradictions
- Score overall consistency
- Write check to SharedMemoryPool

**SharedMemory Tags**: `["consistency_check", "federated_pipeline"]`, segment: `"federated_pipeline"`

### 5. FinalAggregatorAgent

**Signature**: `FinalAggregationSignature`
- **Inputs**:
  - `query` (str) - User query
  - `merged_documents` (str) - Merged documents as JSON
  - `consistency_result` (str) - Consistency result as JSON
- **Outputs**:
  - `final_answer` (str) - Final aggregated answer
  - `source_attribution` (str) - Source attribution as JSON

**Responsibilities**:
- Aggregate final answer from merged documents
- Provide source attribution
- Consider consistency in answer
- Write aggregation to SharedMemoryPool

**SharedMemory Tags**: `["final_aggregation", "federated_pipeline"]`, segment: `"federated_pipeline"`

## Quick Start

### 1. Basic Usage

```python
from workflow import federated_rag_workflow, FederatedRAGConfig

config = FederatedRAGConfig(llm_provider="mock")

query = "What are transformers in deep learning?"
sources = [
    {"id": "arxiv", "type": "papers"},
    {"id": "wikipedia", "type": "encyclopedia"}
]

result = federated_rag_workflow(query, sources, config)
print(f"Selected Sources: {result['selected_sources']}")
print(f"Consistency Score: {result['consistency_score']}")
print(f"Final Answer: {result['final_answer']}")
print(f"Source Attribution: {result['source_attribution']}")
```

### 2. Custom Configuration

```python
config = FederatedRAGConfig(
    llm_provider="openai",
    model="gpt-4",
    max_sources=10,                # Maximum sources to query
    enable_deduplication=True,     # Enable deduplication
    consistency_threshold=0.9      # Consistency threshold (0-1)
)
```

### 3. Multi-Source Retrieval

```python
# Multiple distributed sources
sources = [
    {"id": "arxiv", "type": "papers", "description": "Academic papers"},
    {"id": "wikipedia", "type": "encyclopedia", "description": "General knowledge"},
    {"id": "docs", "type": "documentation", "description": "Technical docs"},
    {"id": "blog", "type": "articles", "description": "Blog posts"}
]

result = federated_rag_workflow(query, sources, config)
print(f"Retrieved from {len(result['selected_sources'])} sources")
print(f"Merged {len(result['merged_documents'])} documents")
print(f"Removed {result['deduplication_count']} duplicates")
```

## Configuration

### FederatedRAGConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm_provider` | str | "mock" | LLM provider (mock, openai, anthropic) |
| `model` | str | "gpt-3.5-turbo" | Model name |
| `max_sources` | int | 5 | Maximum sources to query |
| `enable_deduplication` | bool | True | Enable result deduplication |
| `consistency_threshold` | float | 0.7 | Consistency score threshold (0-1) |

## Workflow Execution

### Federated Pipeline

1. **Source Coordination** - Select relevant sources based on query
2. **Distributed Retrieval** - Retrieve from each selected source in parallel
3. **Result Merging** - Merge and deduplicate results from all sources
4. **Consistency Checking** - Check consistency and detect conflicts across sources
5. **Final Aggregation** - Aggregate answer with source attribution

### Distributed Retrieval Example

```
Query: "What are transformers in deep learning?"

Source Coordination:
  Selected: [arxiv, wikipedia, docs]
  Reasoning: "Technical query requires academic and documentation sources"

Distributed Retrieval:
  arxiv: 3 documents retrieved
  wikipedia: 2 documents retrieved
  docs: 2 documents retrieved

Result Merging:
  Total: 7 documents
  After deduplication: 5 documents

Consistency Check:
  Score: 0.85
  Conflicts: 0

Final Answer:
  "Transformers are neural network architectures..."
  Sources: [arxiv, wikipedia, docs]
```

## Use Cases

### 1. Multi-Source Knowledge Aggregation

Retrieve and aggregate knowledge from multiple distributed sources.

```python
sources = [
    {"id": "internal_kb", "type": "knowledge_base"},
    {"id": "external_docs", "type": "documentation"},
    {"id": "research_papers", "type": "papers"}
]

result = federated_rag_workflow(query, sources, config)
print(f"Aggregated from {len(result['source_attribution'])} sources")
```

### 2. Cross-Source Consistency Checking

Validate consistency of information across multiple sources.

```python
config = FederatedRAGConfig(consistency_threshold=0.9)
result = federated_rag_workflow(query, sources, config)
print(f"Consistency Score: {result['consistency_score']}")
print(f"Conflicts: {result['conflicts']}")
print(f"Is Consistent: {result['is_consistent']}")
```

### 3. Source Attribution and Transparency

Provide transparent source attribution for answers.

```python
result = federated_rag_workflow(query, sources, config)
print(f"Answer: {result['final_answer']}")
print(f"Sources Used: {result['source_attribution']}")
```

### 4. Distributed Enterprise Knowledge

Query across distributed enterprise knowledge bases.

```python
sources = [
    {"id": "sales_kb", "type": "knowledge_base", "department": "sales"},
    {"id": "support_kb", "type": "knowledge_base", "department": "support"},
    {"id": "product_docs", "type": "documentation", "department": "product"}
]

config = FederatedRAGConfig(max_sources=10, enable_deduplication=True)
result = federated_rag_workflow(query, sources, config)
```

## Testing

```bash
# Run all tests
pytest tests/unit/examples/test_federated_rag.py -v

# Run specific test class
pytest tests/unit/examples/test_federated_rag.py::TestFederatedRAGAgents -v
```

**Test Coverage**: 17 tests, 100% passing

## Related Examples

- **agentic-rag** - Adaptive retrieval with quality feedback
- **graph-rag** - Knowledge graph-based retrieval
- **multi-hop-rag** - Sequential multi-hop reasoning

## Implementation Notes

- **Phase**: 5E.3 (Advanced RAG Examples)
- **Created**: 2025-10-03
- **Tests**: 17/17 passing
- **TDD**: Tests written first, implementation second
- **Pattern**: Distributed retrieval pipeline with consistency checking

## Advanced Features

### Source Coordination

- Query-based source selection
- Relevance-based ranking
- Maximum source limiting
- Selection reasoning

### Distributed Retrieval

- Parallel retrieval from multiple sources
- Source-tagged documents
- Independent source queries
- Retrieval failure handling

### Result Merging

- Cross-source deduplication
- Document similarity detection
- Result aggregation
- Duplicate counting

### Consistency Checking

- Cross-source consistency scoring
- Conflict detection
- Contradiction identification
- Consistency thresholds

### Source Attribution

- Transparent source tracking
- Attribution per document
- Multi-source answers
- Provenance tracking

## Author

Kaizen Framework Team
