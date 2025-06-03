## Hierarchical RAG Workflow

_Simple hierarchical RAG workflow using LLMAgentNode and EmbeddingGeneratorNode with Ollama_

```mermaid
flowchart TB

    %% Input Data
    input_data([Input Data])

    %% Processing nodes
    doc_source["DocumentSource<br/>doc_source"]
    chunker["HierarchicalChunker<br/>chunker"]
    query_source["QuerySource<br/>query_source"]
    chunk_text_extractor["ChunkTextExtractor<br/>chunk_text_extractor"]
    query_text_wrapper["QueryTextWrapper<br/>query_text_wrapper"]
    chunk_embedder["EmbeddingGenerator<br/>chunk_embedder"]
    query_embedder["EmbeddingGenerator<br/>query_embedder"]
    relevance_scorer["RelevanceScorer<br/>relevance_scorer"]
    context_formatter["ContextFormatter<br/>context_formatter"]
    llm_agent["LLMAgent<br/>llm_agent"]

    %% Output Data
    output_data([Output Data])

    %% Flow
    input_data --> doc_source
    input_data --> query_source
    doc_source -->|documents→documents| chunker
    chunker -->|chunks→chunks| chunk_text_extractor
    chunker -->|chunks→chunks| relevance_scorer
    query_source -->|query→query| query_text_wrapper
    query_source -->|query→query| context_formatter
    chunk_text_extractor -->|input_texts→input_texts| chunk_embedder
    query_text_wrapper -->|input_texts→input_texts| query_embedder
    chunk_embedder -->|embeddings→chunk_embeddings| relevance_scorer
    query_embedder -->|embeddings→query_embedding| relevance_scorer
    relevance_scorer -->|relevant_chunks→relevant_chunks| context_formatter
    context_formatter -->|messages→messages| llm_agent
    llm_agent --> output_data

    %% Styling
    style input_data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,stroke-dasharray: 5 5
    style output_data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,stroke-dasharray: 5 5
    style doc_source fill:#f5f5f5,stroke:#616161,stroke-width:2px
    style chunker fill:#f5f5f5,stroke:#616161,stroke-width:2px
    style query_source fill:#f5f5f5,stroke:#616161,stroke-width:2px
    style chunk_text_extractor fill:#f5f5f5,stroke:#616161,stroke-width:2px
    style query_text_wrapper fill:#f5f5f5,stroke:#616161,stroke-width:2px
    style chunk_embedder fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style query_embedder fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style relevance_scorer fill:#f5f5f5,stroke:#616161,stroke-width:2px
    style context_formatter fill:#f5f5f5,stroke:#616161,stroke-width:2px
    style llm_agent fill:#f5f5f5,stroke:#616161,stroke-width:2px
```

### Nodes

| Node ID | Type | Description |
|---------|------|-------------|
| chunk_embedder | EmbeddingGeneratorNode | Vector embedding generator for RAG systems and semantic similarity operations. |
| chunk_text_extractor | ChunkTextExtractorNode | Extracts text content from chunks for embedding generation. |
| chunker | HierarchicalChunkerNode | Splits documents into hierarchical chunks for better retrieval. |
| context_formatter | ContextFormatterNode | Formats relevant chunks into context for LLM. |
| doc_source | DocumentSourceNode | Provides sample documents for hierarchical RAG processing. |
| llm_agent | LLMAgentNode | Advanced Large Language Model agent with LangChain integration and MCP |
| query_embedder | EmbeddingGeneratorNode | Vector embedding generator for RAG systems and semantic similarity operations. |
| query_source | QuerySourceNode | Provides sample queries for RAG processing. |
| query_text_wrapper | QueryTextWrapperNode | Wraps query string in list for embedding generation. |
| relevance_scorer | RelevanceScorerNode | Scores chunk relevance using various similarity methods including embeddings similarity. |

### Connections

| From | To | Mapping |
|------|-----|---------|
| doc_source | chunker | documents→documents |
| chunker | chunk_text_extractor | chunks→chunks |
| chunker | relevance_scorer | chunks→chunks |
| query_source | query_text_wrapper | query→query |
| query_source | context_formatter | query→query |
| chunk_text_extractor | chunk_embedder | input_texts→input_texts |
| query_text_wrapper | query_embedder | input_texts→input_texts |
| chunk_embedder | relevance_scorer | embeddings→chunk_embeddings |
| query_embedder | relevance_scorer | embeddings→query_embedding |
| relevance_scorer | context_formatter | relevant_chunks→relevant_chunks |
| context_formatter | llm_agent | messages→messages |
