# Self-Correcting RAG - Error Detection and Correction

**Category**: Advanced RAG
**Pattern**: Iterative Correction Pipeline with Validation
**Complexity**: Advanced
**Use Cases**: Error detection, self-critique, factual consistency, answer validation

## Overview

This example demonstrates self-correcting RAG using five specialized agents that collaborate to generate answers, detect errors, select correction strategies, refine answers, and validate final quality.

### Key Features

- **Error detection** - Automatically detects factual, consistency, and relevance errors
- **Self-correction** - Iteratively refines answers based on detected errors
- **Strategy selection** - Selects optimal correction strategy for each error type
- **Answer validation** - Validates final answer quality against threshold
- **Correction tracking** - Tracks all corrections made during refinement

## Architecture

\`\`\`
User Query + Documents
     |
     v
┌──────────────────────┐
│AnswerGeneratorAgent  │ - Generates initial answer
└──────────┬───────────┘
           │ writes to SharedMemoryPool
           v
    ["answer_generation", "correction_pipeline"]
           │
           v
┌──────────────────────┐
│ ErrorDetectorAgent   │ - Detects errors in answer
└──────────┬───────────┘
           │
           ├──> No errors? ──> ValidationAgent
           │
           └──> Has errors? ──> CorrectionStrategyAgent
                                │
                                v
                         ┌──────────────────────────┐
                         │CorrectionStrategyAgent   │ - Selects strategy
                         └──────────┬───────────────┘
                                    │
                                    v
                         ┌──────────────────────┐
                         │AnswerRefinerAgent    │ - Refines answer
                         └──────────┬───────────┘
                                    │
                                    └──> Back to ErrorDetectorAgent (iterate)
\`\`\`

## Agents

### 1. AnswerGeneratorAgent

**Signature**: \`AnswerGenerationSignature\`
- **Inputs**:
  - \`query\` (str) - User query
  - \`documents\` (str) - Retrieved documents as JSON
- **Outputs**:
  - \`answer\` (str) - Generated answer
  - \`confidence\` (str) - Confidence score (0-1)

**Responsibilities**:
- Generate initial answer from documents
- Assess confidence level
- Write answer to SharedMemoryPool

**SharedMemory Tags**: \`["answer_generation", "correction_pipeline"]\`, segment: \`"correction_pipeline"\`

### 2. ErrorDetectorAgent

**Signature**: \`ErrorDetectionSignature\`
- **Inputs**:
  - \`query\` (str) - Original query
  - \`answer\` (str) - Generated answer
  - \`documents\` (str) - Source documents as JSON
- **Outputs**:
  - \`has_errors\` (str) - Whether errors detected
  - \`error_types\` (str) - Types of errors as JSON
  - \`error_details\` (str) - Detailed error analysis

**Responsibilities**:
- Detect factual errors
- Detect consistency errors
- Detect relevance errors
- Write detection results to SharedMemoryPool

**SharedMemory Tags**: \`["error_detection", "correction_pipeline"]\`, segment: \`"correction_pipeline"\`

### 3. CorrectionStrategyAgent

**Signature**: \`CorrectionStrategySignature\`
- **Inputs**: \`error_analysis\` (str) - Error analysis as JSON
- **Outputs**:
  - \`strategy\` (str) - Correction strategy to use
  - \`reasoning\` (str) - Reasoning for strategy selection

**Responsibilities**:
- Select correction strategy based on error type
- Provide reasoning for selection
- Write strategy to SharedMemoryPool

**SharedMemory Tags**: \`["correction_strategy", "correction_pipeline"]\`, segment: \`"correction_pipeline"\`

### 4. AnswerRefinerAgent

**Signature**: \`AnswerRefinementSignature\`
- **Inputs**:
  - \`query\` (str) - Original query
  - \`original_answer\` (str) - Answer to refine
  - \`documents\` (str) - Source documents as JSON
  - \`strategy\` (str) - Correction strategy
- **Outputs**:
  - \`refined_answer\` (str) - Refined answer
  - \`corrections_made\` (str) - Corrections made as JSON

**Responsibilities**:
- Refine answer based on strategy
- Track corrections made
- Write refinement to SharedMemoryPool

**SharedMemory Tags**: \`["answer_refinement", "correction_pipeline"]\`, segment: \`"correction_pipeline"\`

### 5. ValidationAgent

**Signature**: \`AnswerValidationSignature\`
- **Inputs**:
  - \`query\` (str) - Original query
  - \`answer\` (str) - Answer to validate
  - \`documents\` (str) - Source documents as JSON
- **Outputs**:
  - \`is_valid\` (str) - Whether answer is valid
  - \`validation_score\` (str) - Validation score (0-1)
  - \`feedback\` (str) - Validation feedback

**Responsibilities**:
- Validate final answer quality
- Score answer against threshold
- Write validation to SharedMemoryPool

**SharedMemory Tags**: \`["answer_validation", "correction_pipeline"]\`, segment: \`"correction_pipeline"\`

## Quick Start

### 1. Basic Usage

\`\`\`python
from workflow import self_correcting_rag_workflow, SelfCorrectingRAGConfig

config = SelfCorrectingRAGConfig(llm_provider="mock")

query = "What are transformers in deep learning?"
documents = [{"content": "Transformers are neural network architectures"}]

result = self_correcting_rag_workflow(query, documents, config)
print(f"Initial Answer: {result['initial_answer']}")
print(f"Corrections Made: {result['correction_count']}")
print(f"Final Answer: {result['final_answer']}")
print(f"Is Valid: {result['is_valid']}")
\`\`\`

### 2. Custom Configuration

\`\`\`python
config = SelfCorrectingRAGConfig(
    llm_provider="openai",
    model="gpt-4",
    max_corrections=5,           # Maximum correction iterations
    validation_threshold=0.9,    # Validation score threshold
    enable_self_critique=True    # Enable self-critique
)
\`\`\`

### 3. Error Detection and Correction

\`\`\`python
# Query with potential errors
query = "What are transformers?"
documents = [{"content": "Transformers are neural networks that use attention"}]

result = self_correcting_rag_workflow(query, documents, config)
print(f"Errors Detected: {result['error_detection']['has_errors']}")
print(f"Error Types: {result['error_detection']['error_types']}")
print(f"Corrections: {result['corrections']}")
\`\`\`

## Configuration

### SelfCorrectingRAGConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| \`llm_provider\` | str | "mock" | LLM provider (mock, openai, anthropic) |
| \`model\` | str | "gpt-3.5-turbo" | Model name |
| \`max_corrections\` | int | 3 | Maximum correction iterations |
| \`validation_threshold\` | float | 0.8 | Validation score threshold (0-1) |
| \`enable_self_critique\` | bool | True | Enable self-critique mode |

## Workflow Execution

### Correction Pipeline

1. **Answer Generation** - Generate initial answer with confidence
2. **Error Detection** - Detect errors (factual, consistency, relevance)
3. **Strategy Selection** - Select correction strategy for detected errors
4. **Answer Refinement** - Refine answer based on strategy
5. **Iteration** - Repeat 2-4 until no errors or max iterations reached
6. **Validation** - Validate final answer quality

### Error Types

- **Factual Errors**: Answer contradicts source documents
- **Consistency Errors**: Answer contradicts itself
- **Relevance Errors**: Answer doesn't address the query

### Correction Strategies

- **replace_with_evidence**: Replace error with evidence from documents
- **rephrase_for_clarity**: Rephrase for better clarity
- **add_context**: Add missing context from documents
- **remove_hallucination**: Remove unsupported claims

## Use Cases

### 1. Factual Error Correction

Detect and correct factual errors in generated answers.

\`\`\`python
query = "What are transformers?"
documents = [{"content": "Transformers are neural networks"}]

result = self_correcting_rag_workflow(query, documents, config)
print(f"Corrections: {result['corrections']}")
\`\`\`

### 2. Consistency Checking

Detect and fix consistency errors in answers.

\`\`\`python
config = SelfCorrectingRAGConfig(enable_self_critique=True)
result = self_correcting_rag_workflow(query, documents, config)
\`\`\`

### 3. Answer Validation

Validate answer quality against threshold.

\`\`\`python
config = SelfCorrectingRAGConfig(validation_threshold=0.9)
result = self_correcting_rag_workflow(query, documents, config)
print(f"Validation Score: {result['validation_score']}")
\`\`\`

### 4. Iterative Refinement

Refine answers through multiple iterations.

\`\`\`python
config = SelfCorrectingRAGConfig(max_corrections=5)
result = self_correcting_rag_workflow(query, documents, config)
print(f"Iterations: {result['correction_count']}")
\`\`\`

## Testing

\`\`\`bash
# Run all tests
pytest tests/unit/examples/test_self_correcting_rag.py -v

# Run specific test class
pytest tests/unit/examples/test_self_correcting_rag.py::TestSelfCorrectingRAGAgents -v
\`\`\`

**Test Coverage**: 16 tests, 100% passing

## Related Examples

- **agentic-rag** - Adaptive retrieval with quality feedback
- **graph-rag** - Knowledge graph-based retrieval
- **simple-qa** - Basic question answering

## Implementation Notes

- **Phase**: 5E.3 (Advanced RAG Examples)
- **Created**: 2025-10-03
- **Tests**: 16/16 passing
- **TDD**: Tests written first, implementation second
- **Pattern**: Iterative correction pipeline with validation

## Advanced Features

### Error Detection

- Factual consistency checking against source documents
- Self-consistency checking within answer
- Relevance checking against query
- Confidence-based error detection

### Correction Strategies

- Evidence-based correction
- Context augmentation
- Hallucination removal
- Clarity improvement

### Validation

- Score-based validation
- Threshold-based acceptance
- Feedback generation
- Quality metrics tracking

## Author

Kaizen Framework Team
