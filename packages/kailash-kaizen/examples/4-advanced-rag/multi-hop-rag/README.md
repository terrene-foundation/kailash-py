# Multi-Hop RAG - Sequential Reasoning Chains

**Category**: Advanced RAG
**Pattern**: Sequential Multi-Hop Pipeline with Reasoning Chains
**Complexity**: Advanced
**Use Cases**: Multi-step reasoning, complex question answering, sequential information gathering, dependency-aware retrieval

## Overview

This example demonstrates multi-hop reasoning in RAG using five specialized agents that collaborate to decompose complex queries, retrieve information sequentially, aggregate answers, build reasoning chains, and synthesize final answers.

### Key Features

- **Question decomposition** - Decomposes complex queries into sub-questions
- **Multi-hop retrieval** - Sequential retrieval for each sub-question
- **Answer aggregation** - Aggregates sub-answers into unified context
- **Reasoning chains** - Builds explicit reasoning chains
- **Dependency tracking** - Tracks dependencies between reasoning steps

## Architecture

\`\`\`
Complex Query
     |
     v
┌──────────────────────────┐
│QuestionDecomposerAgent   │ - Decomposes into sub-questions
└──────────┬───────────────┘
           │ writes to SharedMemoryPool
           v
    ["question_decomposition", "multi_hop_pipeline"]
           │
           v
    For each sub-question:
           │
           v
┌──────────────────────────────┐
│SubQuestionRetrieverAgent     │ - Retrieves for sub-question (Hop 1, 2, 3...)
└──────────┬───────────────────┘
           │ writes to SharedMemoryPool
           v
    ["sub_question_retrieval", "multi_hop_pipeline"]
           │
           v
┌──────────────────────────┐
│AnswerAggregatorAgent     │ - Aggregates sub-answers
└──────────┬───────────────┘
           │ writes to SharedMemoryPool
           v
    ["answer_aggregation", "multi_hop_pipeline"]
           │
           v
┌──────────────────────────┐
│ReasoningChainAgent       │ - Builds reasoning chain
└──────────┬───────────────┘
           │ writes to SharedMemoryPool
           v
    ["reasoning_chain", "multi_hop_pipeline"]
           │
           v
┌──────────────────────────┐
│FinalAnswerAgent          │ - Synthesizes final answer
└──────────┬───────────────┘
           │
           v
    Final Answer with Evidence
\`\`\`

## Agents

### 1. QuestionDecomposerAgent

**Signature**: \`QuestionDecompositionSignature\`
- **Inputs**: \`query\` (str) - Complex query to decompose
- **Outputs**:
  - \`sub_questions\` (str) - Sub-questions as JSON
  - \`reasoning_steps\` (str) - Reasoning steps as JSON

**Responsibilities**:
- Decompose complex query into sub-questions
- Identify reasoning steps
- Write decomposition to SharedMemoryPool

**SharedMemory Tags**: \`["question_decomposition", "multi_hop_pipeline"]\`, segment: \`"multi_hop_pipeline"\`

### 2. SubQuestionRetrieverAgent

**Signature**: \`SubQuestionRetrievalSignature\`
- **Inputs**: \`sub_question\` (str) - Sub-question to retrieve for
- **Outputs**:
  - \`documents\` (str) - Retrieved documents as JSON
  - \`sub_answer\` (str) - Answer to sub-question

**Responsibilities**:
- Retrieve information for each sub-question
- Answer sub-question
- Write retrieval to SharedMemoryPool

**SharedMemory Tags**: \`["sub_question_retrieval", "multi_hop_pipeline"]\`, segment: \`"multi_hop_pipeline"\`

### 3. AnswerAggregatorAgent

**Signature**: \`AnswerAggregationSignature\`
- **Inputs**: \`sub_answers\` (str) - Sub-answers to aggregate as JSON
- **Outputs**:
  - \`aggregated_context\` (str) - Aggregated context
  - \`key_findings\` (str) - Key findings as JSON

**Responsibilities**:
- Aggregate sub-answers
- Extract key findings
- Write aggregation to SharedMemoryPool

**SharedMemory Tags**: \`["answer_aggregation", "multi_hop_pipeline"]\`, segment: \`"multi_hop_pipeline"\`

### 4. ReasoningChainAgent

**Signature**: \`ReasoningChainSignature\`
- **Inputs**:
  - \`query\` (str) - Original query
  - \`sub_questions\` (str) - Sub-questions as JSON
  - \`sub_answers\` (str) - Sub-answers as JSON
- **Outputs**:
  - \`reasoning_chain\` (str) - Reasoning chain
  - \`chain_steps\` (str) - Chain steps as JSON

**Responsibilities**:
- Build reasoning chain from sub-questions/answers
- Track chain steps
- Write chain to SharedMemoryPool

**SharedMemory Tags**: \`["reasoning_chain", "multi_hop_pipeline"]\`, segment: \`"multi_hop_pipeline"\`

### 5. FinalAnswerAgent

**Signature**: \`FinalAnswerSignature\`
- **Inputs**:
  - \`query\` (str) - Original query
  - \`reasoning_chain\` (str) - Reasoning chain as JSON
- **Outputs**:
  - \`final_answer\` (str) - Final synthesized answer
  - \`supporting_evidence\` (str) - Supporting evidence as JSON

**Responsibilities**:
- Synthesize final answer from reasoning chain
- Provide supporting evidence
- Write answer to SharedMemoryPool

**SharedMemory Tags**: \`["final_answer", "multi_hop_pipeline"]\`, segment: \`"multi_hop_pipeline"\`

## Quick Start

### 1. Basic Usage

\`\`\`python
from workflow import multi_hop_rag_workflow, MultiHopRAGConfig

config = MultiHopRAGConfig(llm_provider="mock")

query = "How do transformers improve upon RNNs in terms of parallelization?"

result = multi_hop_rag_workflow(query, config)
print(f"Sub-Questions: {result['sub_questions']}")
print(f"Hops: {result['hops']}")
print(f"Final Answer: {result['final_answer']}")
\`\`\`

### 2. Custom Configuration

\`\`\`python
config = MultiHopRAGConfig(
    llm_provider="openai",
    model="gpt-4",
    max_hops=5,                   # Maximum reasoning hops
    max_sub_questions=10,         # Maximum sub-questions
    enable_chain_tracking=True    # Enable reasoning chain tracking
)
\`\`\`

### 3. Complex Multi-Hop Query

\`\`\`python
# Query requiring multiple reasoning steps
query = "Compare transformers and RNNs in terms of computational complexity and long-range dependencies"

result = multi_hop_rag_workflow(query, config)
print(f"Sub-Questions: {len(result['sub_questions'])}")
print(f"Hops Taken: {result['hops']}")
print(f"Reasoning Chain: {result['reasoning_chain']}")
\`\`\`

## Configuration

### MultiHopRAGConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| \`llm_provider\` | str | "mock" | LLM provider (mock, openai, anthropic) |
| \`model\` | str | "gpt-3.5-turbo" | Model name |
| \`max_hops\` | int | 3 | Maximum reasoning hops |
| \`max_sub_questions\` | int | 5 | Maximum sub-questions |
| \`enable_chain_tracking\` | bool | True | Enable reasoning chain tracking |

## Workflow Execution

### Multi-Hop Pipeline

1. **Question Decomposition** - Decompose complex query into sub-questions
2. **Sequential Retrieval** - For each sub-question (up to max_hops):
   - Retrieve relevant documents
   - Answer sub-question
3. **Answer Aggregation** - Aggregate all sub-answers
4. **Reasoning Chain** - Build explicit reasoning chain
5. **Final Answer** - Synthesize final answer from chain

### Multi-Hop Example

\`\`\`
Query: "How do transformers improve upon RNNs?"

Hop 1: "What are the limitations of RNNs?"
       → Answer: "Sequential processing, vanishing gradients"

Hop 2: "How do transformers address sequential processing?"
       → Answer: "Parallel attention mechanism"

Hop 3: "How do transformers handle long-range dependencies?"
       → Answer: "Self-attention without distance decay"

Final: "Transformers improve upon RNNs through parallel processing
        and direct attention to all positions..."
\`\`\`

## Use Cases

### 1. Multi-Step Reasoning

Answer complex questions requiring multiple reasoning steps.

\`\`\`python
query = "How do transformers relate to language models through attention?"
result = multi_hop_rag_workflow(query, config)
print(f"Reasoning Steps: {result['chain_steps']}")
\`\`\`

### 2. Sequential Information Gathering

Gather information sequentially across multiple hops.

\`\`\`python
config = MultiHopRAGConfig(max_hops=5)
query = "Trace the evolution from RNNs to transformers to GPT"
result = multi_hop_rag_workflow(query, config)
print(f"Hops: {result['hops']}")
\`\`\`

### 3. Dependency-Aware Retrieval

Track dependencies between reasoning steps.

\`\`\`python
config = MultiHopRAGConfig(enable_chain_tracking=True)
query = "How does BERT build on transformers and attention?"
result = multi_hop_rag_workflow(query, config)
print(f"Chain: {result['reasoning_chain']}")
\`\`\`

### 4. Complex Comparison Questions

Compare multiple concepts through multi-hop reasoning.

\`\`\`python
query = "Compare computational complexity of transformers vs RNNs for long sequences"
result = multi_hop_rag_workflow(query, config)
print(f"Sub-Questions: {result['sub_questions']}")
print(f"Key Findings: {result['key_findings']}")
\`\`\`

## Testing

\`\`\`bash
# Run all tests
pytest tests/unit/examples/test_multi_hop_rag.py -v

# Run specific test class
pytest tests/unit/examples/test_multi_hop_rag.py::TestMultiHopRAGAgents -v
\`\`\`

**Test Coverage**: 15 tests, 100% passing

## Related Examples

- **agentic-rag** - Adaptive retrieval with quality feedback
- **graph-rag** - Knowledge graph-based retrieval
- **self-correcting-rag** - Error detection and correction

## Implementation Notes

- **Phase**: 5E.3 (Advanced RAG Examples)
- **Created**: 2025-10-03
- **Tests**: 15/15 passing
- **TDD**: Tests written first, implementation second
- **Pattern**: Sequential multi-hop pipeline with reasoning chains

## Advanced Features

### Question Decomposition

- Automatic decomposition of complex queries
- Identification of reasoning steps
- Dependency detection between sub-questions

### Multi-Hop Retrieval

- Sequential retrieval for each sub-question
- Context preservation across hops
- Hop limit to prevent infinite loops

### Reasoning Chains

- Explicit reasoning chain construction
- Step-by-step tracking
- Evidence linking across hops

### Answer Synthesis

- Aggregation of sub-answers
- Final answer synthesis from chain
- Supporting evidence extraction

## Author

Kaizen Framework Team
