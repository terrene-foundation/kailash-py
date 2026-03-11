# Graph RAG - Knowledge Graph-Based Retrieval

**Category**: Advanced RAG
**Pattern**: Graph Pipeline with Multi-Hop Traversal
**Complexity**: Advanced
**Use Cases**: Knowledge graph QA, multi-hop reasoning, entity-relationship extraction, structured data retrieval

## Overview

This example demonstrates knowledge graph-based retrieval using five specialized agents that collaborate to extract entities, map relationships, query graph structures, aggregate context, and synthesize answers from graph evidence.

### Key Features

- **Entity extraction** - Automatically extracts entities from queries
- **Relationship mapping** - Maps relationships between entities
- **Graph traversal** - Multi-hop traversal of knowledge graph
- **Context aggregation** - Aggregates graph context with key insights
- **Evidence-based answers** - Synthesizes answers with graph evidence

## Architecture

\`\`\`
User Query
     |
     v
┌──────────────────────┐
│EntityExtractorAgent  │ - Extracts entities and types
└──────────┬───────────┘
           │ writes to SharedMemoryPool
           v
    ["entity_extraction", "graph_pipeline"]
           │
           v
┌──────────────────────────┐
│RelationshipMapperAgent   │ - Maps entity relationships
└──────────┬───────────────┘
           │ writes to SharedMemoryPool
           v
    ["relationship_mapping", "graph_pipeline"]
           │
           v
┌──────────────────────┐
│ GraphQueryAgent      │ - Queries knowledge graph
└──────────┬───────────┘
           │ writes to SharedMemoryPool (with traversal path)
           v
    ["graph_query", "graph_pipeline"]
           │
           v
┌──────────────────────────┐
│ ContextAggregatorAgent   │ - Aggregates graph context
└──────────┬───────────────┘
           │ writes to SharedMemoryPool
           v
    ["context_aggregation", "graph_pipeline"]
           │
           v
┌──────────────────────────┐
│AnswerSynthesizerAgent    │ - Synthesizes answer with evidence
└──────────┬───────────────┘
           │
           v
    Answer with Graph Evidence
\`\`\`

## Agents

### 1. EntityExtractorAgent

**Signature**: \`EntityExtractionSignature\`
- **Inputs**: \`query\` (str) - User query to extract entities from
- **Outputs**:
  - \`entities\` (str) - Extracted entities as JSON
  - \`entity_types\` (str) - Entity types as JSON

**Responsibilities**:
- Extract entities from query
- Classify entity types
- Write entities to SharedMemoryPool

**SharedMemory Tags**: \`["entity_extraction", "graph_pipeline"]\`, segment: \`"graph_pipeline"\`

### 2. RelationshipMapperAgent

**Signature**: \`RelationshipMappingSignature\`
- **Inputs**: \`entities\` (str) - Entities to map relationships for as JSON
- **Outputs**:
  - \`relationships\` (str) - Entity relationships as JSON
  - \`relationship_types\` (str) - Relationship types as JSON

**Responsibilities**:
- Map relationships between entities
- Classify relationship types
- Write relationships to SharedMemoryPool

**SharedMemory Tags**: \`["relationship_mapping", "graph_pipeline"]\`, segment: \`"graph_pipeline"\`

### 3. GraphQueryAgent

**Signature**: \`GraphQuerySignature\`
- **Inputs**:
  - \`entities\` (str) - Entities to query as JSON
  - \`relationships\` (str) - Relationships to query as JSON
- **Outputs**:
  - \`graph_results\` (str) - Graph query results as JSON
  - \`traversal_path\` (str) - Graph traversal path as JSON

**Responsibilities**:
- Query knowledge graph structure
- Perform multi-hop traversal
- Track traversal path
- Write results to SharedMemoryPool

**SharedMemory Tags**: \`["graph_query", "graph_pipeline"]\`, segment: \`"graph_pipeline"\`

### 4. ContextAggregatorAgent

**Signature**: \`ContextAggregationSignature\`
- **Inputs**: \`graph_results\` (str) - Graph results to aggregate as JSON
- **Outputs**:
  - \`aggregated_context\` (str) - Aggregated context
  - \`key_insights\` (str) - Key insights from graph as JSON

**Responsibilities**:
- Aggregate graph context
- Extract key insights
- Write aggregated context to SharedMemoryPool

**SharedMemory Tags**: \`["context_aggregation", "graph_pipeline"]\`, segment: \`"graph_pipeline"\`

### 5. AnswerSynthesizerAgent

**Signature**: \`AnswerSynthesisSignature\`
- **Inputs**:
  - \`query\` (str) - Original query
  - \`context\` (str) - Graph context as JSON
- **Outputs**:
  - \`answer\` (str) - Synthesized answer
  - \`graph_evidence\` (str) - Graph evidence as JSON

**Responsibilities**:
- Synthesize answer from graph context
- Provide graph evidence
- Write answer to SharedMemoryPool

**SharedMemory Tags**: \`["answer_synthesis", "graph_pipeline"]\`, segment: \`"graph_pipeline"\`

## Quick Start

### 1. Basic Usage

\`\`\`python
from workflow import graph_rag_workflow, GraphRAGConfig

config = GraphRAGConfig(llm_provider="mock")

query = "What is the relationship between transformers and attention mechanisms?"

result = graph_rag_workflow(query, config)
print(f"Entities: {result['entities']}")
print(f"Relationships: {result['relationships']}")
print(f"Hops: {result['hops']}")
print(f"Answer: {result['answer']}")
\`\`\`

### 2. Custom Configuration

\`\`\`python
config = GraphRAGConfig(
    llm_provider="openai",
    model="gpt-4",
    max_hops=3,                  # Maximum graph traversal hops
    enable_entity_linking=True,  # Enable entity linking
    graph_depth=4                # Maximum graph depth
)
\`\`\`

### 3. Multi-Hop Traversal

\`\`\`python
# Query requiring multi-hop reasoning
query = "How do transformers relate to NLP through attention mechanisms?"

result = graph_rag_workflow(query, config)
print(f"Traversal Path: {result['traversal_path']}")
print(f"Hops: {result['hops']}")
print(f"Key Insights: {result['key_insights']}")
\`\`\`

## Configuration

### GraphRAGConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| \`llm_provider\` | str | "mock" | LLM provider (mock, openai, anthropic) |
| \`model\` | str | "gpt-3.5-turbo" | Model name |
| \`max_hops\` | int | 2 | Maximum graph traversal hops |
| \`enable_entity_linking\` | bool | True | Enable entity linking |
| \`graph_depth\` | int | 3 | Maximum graph depth |

## Workflow Execution

### Pipeline Stages

1. **Entity Extraction** - Extract entities and types from query
2. **Relationship Mapping** - Map relationships between entities
3. **Graph Query** - Query knowledge graph with multi-hop traversal
4. **Context Aggregation** - Aggregate graph results and extract insights
5. **Answer Synthesis** - Synthesize answer with graph evidence

### Multi-Hop Traversal

\`\`\`
Query: "How does BERT relate to language models through transformers?"

Hop 1: BERT → uses → transformers
Hop 2: transformers → foundation for → language models
Result: BERT uses transformers, which are the foundation for language models
\`\`\`

## Use Cases

### 1. Entity-Relationship QA

Answer questions about entity relationships.

\`\`\`python
query = "What is the relationship between transformers and attention?"
result = graph_rag_workflow(query, config)
print(f"Relationships: {result['relationships']}")
\`\`\`

### 2. Multi-Hop Reasoning

Traverse multiple hops in knowledge graph.

\`\`\`python
config = GraphRAGConfig(max_hops=3)
query = "How does BERT connect to NLP through transformers?"
result = graph_rag_workflow(query, config)
print(f"Hops: {result['hops']}")
print(f"Path: {result['traversal_path']}")
\`\`\`

### 3. Entity Linking

Link entities across graph structure.

\`\`\`python
config = GraphRAGConfig(enable_entity_linking=True)
query = "Compare BERT and GPT"
result = graph_rag_workflow(query, config)
print(f"Entities: {result['entities']}")
print(f"Entity Types: {result['entity_types']}")
\`\`\`

### 4. Knowledge Graph Exploration

Explore knowledge graph structure.

\`\`\`python
query = "What are the connections between attention, transformers, and BERT?"
result = graph_rag_workflow(query, config)
print(f"Graph Results: {len(result['graph_results'])}")
print(f"Key Insights: {result['key_insights']}")
\`\`\`

## Testing

\`\`\`bash
# Run all tests
pytest tests/unit/examples/test_graph_rag.py -v

# Run specific test class
pytest tests/unit/examples/test_graph_rag.py::TestGraphRAGAgents -v
\`\`\`

**Test Coverage**: 16 tests, 100% passing

## Related Examples

- **agentic-rag** - Adaptive retrieval with quality feedback
- **simple-qa** - Basic question answering
- **rag-research** - RAG with vector search

## Implementation Notes

- **Phase**: 5E.3 (Advanced RAG Examples)
- **Created**: 2025-10-03
- **Tests**: 16/16 passing
- **TDD**: Tests written first, implementation second
- **Pattern**: Graph pipeline with multi-hop traversal

## Advanced Features

### Knowledge Graph Structure

- **Entities**: Named entities extracted from queries
- **Relationships**: Typed relationships between entities
- **Attributes**: Entity and relationship attributes
- **Traversal Paths**: Multi-hop paths through graph

### Multi-Hop Reasoning

- Start from query entities
- Traverse relationships up to max_hops
- Aggregate context from all hops
- Synthesize answer from complete path

### Entity Linking

- Link entities to knowledge graph
- Resolve entity mentions
- Disambiguate entities
- Track entity types

## Author

Kaizen Framework Team
