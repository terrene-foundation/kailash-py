# Agentic RAG - Adaptive Retrieval with Multi-Agent Coordination

**Category**: Advanced RAG
**Pattern**: Iterative Pipeline with Quality Feedback
**Complexity**: Advanced
**Use Cases**: Adaptive retrieval, multi-strategy search, quality-driven iteration, complex question answering

## Overview

This example demonstrates adaptive retrieval-augmented generation (RAG) using five specialized agents that collaborate to analyze queries, select optimal retrieval strategies, assess quality, and iteratively refine results.

### Key Features

- **Adaptive retrieval** - Automatically selects optimal retrieval strategy
- **Multi-strategy support** - Semantic, keyword, and hybrid retrieval
- **Quality-driven iteration** - Iteratively refines until quality threshold met
- **Query analysis** - Analyzes intent, complexity, and keywords
- **Self-reflection** - Assesses retrieval quality and provides feedback

## Architecture

\`\`\`
User Query
     |
     v
┌─────────────────────┐
│ QueryAnalyzerAgent  │ - Analyzes intent, complexity, keywords
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["query_analysis", "rag_pipeline"]
           │
           v
┌─────────────────────────┐
│RetrievalStrategyAgent   │ - Selects strategy (semantic/keyword/hybrid)
└──────────┬──────────────┘
           │ writes to SharedMemoryPool
           v
    ["strategy_selection", "rag_pipeline"]
           │
           v
┌─────────────────────────┐
│DocumentRetrieverAgent   │ - Retrieves documents
└──────────┬──────────────┘
           │ writes to SharedMemoryPool
           v
    ["document_retrieval", "rag_pipeline"]
           │
           v
┌─────────────────────────┐
│QualityAssessorAgent     │ - Assesses quality, decides if refinement needed
└──────────┬──────────────┘
           │
           ├──> Quality sufficient? ──> AnswerGeneratorAgent
           │
           └──> Needs refinement? ──> Try different strategy (iterate)
                                        │
                                        └──> Back to RetrievalStrategyAgent
\`\`\`

## Agents

### 1. QueryAnalyzerAgent

**Signature**: \`QueryAnalysisSignature\`
- **Inputs**: \`query\` (str) - User query to analyze
- **Outputs**:
  - \`query_type\` (str) - Query type (factual, analytical, procedural)
  - \`complexity\` (str) - Complexity level (low, medium, high)
  - \`keywords\` (str) - Extracted keywords as JSON

**Responsibilities**:
- Analyze query intent
- Assess complexity level
- Extract key terms
- Write analysis to SharedMemoryPool

**SharedMemory Tags**: \`["query_analysis", "rag_pipeline"]\`, segment: \`"rag_pipeline"\`

### 2. RetrievalStrategyAgent

**Signature**: \`StrategySelectionSignature\`
- **Inputs**: \`query_analysis\` (str) - Query analysis as JSON
- **Outputs**:
  - \`strategy\` (str) - Selected retrieval strategy (semantic, keyword, hybrid)
  - \`reasoning\` (str) - Reasoning for strategy selection

**Responsibilities**:
- Select optimal retrieval strategy
- Provide reasoning for selection
- Adapt based on query characteristics
- Write strategy to SharedMemoryPool

**SharedMemory Tags**: \`["strategy_selection", "rag_pipeline"]\`, segment: \`"rag_pipeline"\`

### 3. DocumentRetrieverAgent

**Signature**: \`DocumentRetrievalSignature\`
- **Inputs**:
  - \`query\` (str) - Search query
  - \`strategy\` (str) - Retrieval strategy to use
- **Outputs**:
  - \`documents\` (str) - Retrieved documents as JSON
  - \`retrieval_metadata\` (str) - Retrieval metadata as JSON

**Responsibilities**:
- Execute retrieval using selected strategy
- Retrieve top-k documents
- Track retrieval metadata
- Write results to SharedMemoryPool

**SharedMemory Tags**: \`["document_retrieval", "rag_pipeline"]\`, segment: \`"rag_pipeline"\`

### 4. QualityAssessorAgent

**Signature**: \`QualityAssessmentSignature\`
- **Inputs**:
  - \`query\` (str) - Original query
  - \`documents\` (str) - Retrieved documents as JSON
- **Outputs**:
  - \`quality_score\` (str) - Quality score (0-1)
  - \`needs_refinement\` (str) - Whether refinement is needed
  - \`feedback\` (str) - Feedback for improvement

**Responsibilities**:
- Assess retrieval quality
- Decide if refinement needed
- Provide actionable feedback
- Write assessment to SharedMemoryPool

**SharedMemory Tags**: \`["quality_assessment", "rag_pipeline"]\`, segment: \`"rag_pipeline"\`

### 5. AnswerGeneratorAgent

**Signature**: \`AnswerGenerationSignature\`
- **Inputs**:
  - \`query\` (str) - User query
  - \`documents\` (str) - Retrieved documents as JSON
- **Outputs**:
  - \`answer\` (str) - Generated answer
  - \`sources\` (str) - Source citations as JSON

**Responsibilities**:
- Generate final answer
- Cite sources
- Synthesize information
- Write answer to SharedMemoryPool

**SharedMemory Tags**: \`["answer_generation", "rag_pipeline"]\`, segment: \`"rag_pipeline"\`

## Quick Start

### 1. Basic Usage

\`\`\`python
from workflow import agentic_rag_workflow, AgenticRAGConfig

config = AgenticRAGConfig(llm_provider="mock")

query = "What are the key differences between transformers and RNNs?"

result = agentic_rag_workflow(query, config)
print(f"Query Type: {result['query_analysis']['query_type']}")
print(f"Strategy: {result['retrieval_strategy']['strategy']}")
print(f"Quality: {result['quality_assessment']['quality_score']}")
print(f"Answer: {result['answer']}")
\`\`\`

### 2. Custom Configuration

\`\`\`python
config = AgenticRAGConfig(
    llm_provider="openai",
    model="gpt-4",
    max_iterations=5,           # Maximum refinement iterations
    retrieval_strategy="auto",  # "auto", "semantic", "keyword", "hybrid"
    top_k=10,                   # Number of documents to retrieve
    quality_threshold=0.8,      # Quality threshold for refinement
    adaptive_retrieval=True     # Enable adaptive strategy selection
)
\`\`\`

### 3. Iterative Refinement

\`\`\`python
# Complex query that may need multiple iterations
query = "How do attention mechanisms in transformers differ from LSTM memory cells?"

result = agentic_rag_workflow(query, config)
print(f"Iterations: {result['iterations']}")
print(f"Strategies Tried: {result['quality_assessment']['strategies_tried']}")
print(f"Final Quality: {result['quality_assessment']['quality_score']}")
\`\`\`

## Configuration

### AgenticRAGConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| \`llm_provider\` | str | "mock" | LLM provider (mock, openai, anthropic) |
| \`model\` | str | "gpt-3.5-turbo" | Model name |
| \`max_iterations\` | int | 3 | Maximum refinement iterations |
| \`retrieval_strategy\` | str | "auto" | Strategy: auto, semantic, keyword, hybrid |
| \`top_k\` | int | 5 | Number of documents to retrieve |
| \`quality_threshold\` | float | 0.7 | Quality threshold (0-1) |
| \`adaptive_retrieval\` | bool | True | Enable adaptive strategy selection |

## Retrieval Strategies

### 1. Semantic Retrieval
Best for conceptual and analytical queries.
\`\`\`python
config = AgenticRAGConfig(retrieval_strategy="semantic")
\`\`\`

### 2. Keyword Retrieval
Best for factual and specific queries.
\`\`\`python
config = AgenticRAGConfig(retrieval_strategy="keyword")
\`\`\`

### 3. Hybrid Retrieval
Combines semantic and keyword for comprehensive coverage.
\`\`\`python
config = AgenticRAGConfig(retrieval_strategy="hybrid")
\`\`\`

### 4. Adaptive (Auto)
Automatically selects best strategy based on query analysis.
\`\`\`python
config = AgenticRAGConfig(retrieval_strategy="auto", adaptive_retrieval=True)
\`\`\`

## Workflow Execution

### Iteration Process

1. **Query Analysis** - Analyze query intent and complexity
2. **Strategy Selection** - Select optimal retrieval strategy
3. **Document Retrieval** - Retrieve documents using strategy
4. **Quality Assessment** - Assess retrieval quality
5. **Decision**:
   - If quality ≥ threshold → Generate answer
   - If quality < threshold → Try different strategy (repeat 2-4)
6. **Answer Generation** - Generate final answer from best documents

### Quality-Driven Refinement

\`\`\`python
# Low quality triggers refinement
iteration_1: semantic retrieval → quality 0.5 → needs refinement
iteration_2: keyword retrieval → quality 0.6 → needs refinement
iteration_3: hybrid retrieval → quality 0.8 → sufficient → generate answer
\`\`\`

## Use Cases

### 1. Complex Question Answering

Handle multi-hop questions with iterative refinement.

\`\`\`python
query = "Compare the computational complexity of transformers and RNNs for long sequences"
result = agentic_rag_workflow(query, config)
\`\`\`

### 2. Adaptive Search

Automatically adapt retrieval strategy based on query type.

\`\`\`python
# Factual query → keyword retrieval
factual = "When was the transformer architecture introduced?"

# Analytical query → semantic retrieval
analytical = "What are the theoretical advantages of self-attention?"
\`\`\`

### 3. Quality-Driven Retrieval

Ensure high-quality results through iterative refinement.

\`\`\`python
config = AgenticRAGConfig(
    quality_threshold=0.9,  # High quality bar
    max_iterations=5        # More refinement attempts
)
\`\`\`

## Testing

\`\`\`bash
# Run all tests
pytest tests/unit/examples/test_agentic_rag.py -v

# Run specific test class
pytest tests/unit/examples/test_agentic_rag.py::TestAgenticRAGAgents -v
\`\`\`

**Test Coverage**: 16 tests, 100% passing

## Related Examples

- **simple-qa** - Basic question answering
- **rag-research** - RAG with vector search
- **chain-of-thought** - Multi-step reasoning

## Implementation Notes

- **Phase**: 5E.3 (Advanced RAG Examples)
- **Created**: 2025-10-03
- **Tests**: 16/16 passing
- **TDD**: Tests written first, implementation second
- **Pattern**: Iterative pipeline with quality feedback loop

## Advanced Features

### Quality Metrics

- **Coverage**: How well documents cover the query
- **Relevance**: How relevant documents are to query
- **Completeness**: Whether documents provide complete answer

### Strategy Selection Heuristics

- **Factual queries** → Keyword retrieval
- **Analytical queries** → Semantic retrieval
- **Complex queries** → Hybrid retrieval
- **High complexity** → More iterations allowed

### Iteration Control

- Maximum iterations prevent infinite loops
- Quality threshold determines when to stop
- Best results tracked across all iterations

## Author

Kaizen Framework Team
