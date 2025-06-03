# Hierarchical RAG Pipeline Workflow Configuration and Model Specialization

This module implements a multi-stage document processing pipeline using OpenAI's hierarchical RAG methodology with optimized Ollama model selection for different processing stages.

## Workflow Composition Examples

### Pre-processing Chain
```
document_ingestion → quality_checks → hierarchical_rag
```
**Purpose:** Clean and validate documents before RAG processing

### Post-processing Chain
```
hierarchical_rag → fact_checker → response_formatter → email_sender
```
**Purpose:** Validate and format RAG responses for distribution

### Multi-stage Pipeline
```
initial_rag → follow_up_questions → detailed_rag → summary
```
**Purpose:** Iterative questioning for comprehensive analysis

## Integration Points

### Input Connections
- **document_content:** Raw text, PDF content, scraped data
- **query:** User questions, search terms, analysis requests
- **model_configs:** Ollama model selection, temperature settings

### Output Connections
- **response:** Generated answer text
- **metadata:** Processing statistics, model usage
- **validation:** Quality scores, confidence metrics

## Ollama Model Specialization

### Document Cutting & Selection (Speed Prioritized)
- **Model:** `qwen2.5:7b-instruct-q8_0`
- **Purpose:** Fast document analysis and relevance assessment
- **Optimization:** Q8_0 quantization for excellent speed and quality
- **Use Case:** Quick filtering of large document sets
- **Memory:** ~4.7GB

### Response Generation (Quality-Speed Balance)
- **Model:** `llama3.1:8b-instruct-q8_0`
- **Purpose:** High-quality response generation
- **Optimization:** Q8_0 quantization for best quality/speed tradeoff
- **Use Case:** Main content generation with good coherence
- **Memory:** ~4.7GB

### Validation (Maximum Quality)
- **Model:** `deepseek-coder-v2:16b-lite-instruct-q8_0`
- **Purpose:** Rigorous response validation and quality assessment
- **Optimization:** Q8_0 quantization with excellent reasoning capabilities
- **Use Case:** Critical validation where accuracy is paramount
- **Memory:** ~9.4GB

**Total Memory Usage:** ~19GB (optimal for Mac Studio M4 with 128GB unified memory)

## Pipeline Architecture

The system implements OpenAI's iterative document chunking methodology:

1. Break documents into 3 parts
2. Identify relevant sections based on query
3. Recursively subdivide selected parts (3-5 iterations)
4. Generate responses using combined relevant chunks
5. Validate generated content for accuracy and completeness

## Performance Characteristics

- Concurrent model loading supported
- No model swapping delays between stages
- Parallel document processing capability
- Optimized for Apple Silicon M-series chips
