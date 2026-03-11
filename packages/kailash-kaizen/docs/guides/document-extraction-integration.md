# Document Extraction Integration Guide

Complete guide for integrating document extraction into Kaizen AI workflows.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Integration Patterns](#integration-patterns)
4. [Cost Optimization](#cost-optimization)
5. [Production Deployment](#production-deployment)
6. [Troubleshooting](#troubleshooting)

---

## Overview

Document extraction enables AI agents to process and understand documents (PDF, DOCX, TXT, MD) with:

- **Multi-Provider Support**: Landing AI (98% accuracy), OpenAI Vision (95%), Ollama (85%, FREE)
- **RAG-Ready Chunking**: Semantic chunks with page citations and bounding boxes
- **Cost Optimization**: Budget constraints, prefer-free strategies, cost estimation
- **Zero Breaking Changes**: Opt-in features, backward compatible

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Integration Layers                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ VisionAgent   │  │MultiModalAgent│  │DocumentAgent │     │
│  │ (Enhanced)    │  │  (Enhanced)   │  │ (Standalone) │     │
│  └───────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│          │                  │                  │              │
│          └──────────────────┴──────────────────┘              │
│                             │                                 │
│              ┌──────────────▼──────────────┐                 │
│              │  DocumentExtractionAgent    │                 │
│              │  (Core Implementation)      │                 │
│              └──────────────┬──────────────┘                 │
│                             │                                 │
│         ┌───────────────────┼────────────────────┐           │
│         │                   │                    │           │
│    ┌────▼─────┐      ┌─────▼──────┐      ┌────▼─────┐      │
│    │ Landing  │      │   OpenAI   │      │  Ollama  │      │
│    │   AI     │      │   Vision   │      │  Vision  │      │
│    │ ($0.015) │      │  ($0.068)  │      │  (FREE)  │      │
│    └──────────┘      └────────────┘      └──────────┘      │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Pattern 1: Standalone DocumentExtractionAgent

```python
from kaizen.agents.multi_modal.document_extraction_agent import (
    DocumentExtractionAgent,
    DocumentExtractionConfig,
)

# Configuration
config = DocumentExtractionConfig(
    provider="ollama_vision",  # FREE local provider
    chunk_for_rag=True,
    chunk_size=512,
)

# Create agent
agent = DocumentExtractionAgent(config=config)

# Extract document
result = agent.extract(
    file_path="report.pdf",
    extract_tables=True,
    chunk_for_rag=True,
)

# Access results
print(f"Text: {result['text'][:100]}...")
print(f"Chunks: {len(result['chunks'])}")
print(f"Cost: ${result['cost']:.3f}")
```

### Pattern 2: VisionAgent with Document Extraction

```python
from kaizen.agents.multi_modal.vision_agent import VisionAgent, VisionAgentConfig

# Configuration (opt-in document extraction)
config = VisionAgentConfig(
    enable_document_extraction=True,
    landing_ai_api_key=os.getenv('LANDING_AI_API_KEY'),
)

# Create agent
agent = VisionAgent(config=config)

# Vision analysis (existing)
vision_result = agent.analyze(
    image="photo.jpg",
    question="What is in this image?"
)

# Document extraction (new)
doc_result = agent.extract_document(
    file_path="invoice.pdf",
    chunk_for_rag=True,
)

print(f"Text: {doc_result['text'][:100]}...")
print(f"Chunks: {len(doc_result['chunks'])}")
```

### Pattern 3: MultiModalAgent Auto-Detection

```python
from kaizen.agents.multi_modal.multi_modal_agent import (
    MultiModalAgent,
    MultiModalConfig,
)

# Configuration (opt-in document extraction)
config = MultiModalConfig(
    enable_document_extraction=True,
    landing_ai_api_key=os.getenv('LANDING_AI_API_KEY'),
)

# Create agent
agent = MultiModalAgent(config=config, signature=signature)

# Automatically detects document input
result = agent.analyze(
    document="report.pdf",  # Auto-detected by file extension
    prompt="Summarize the key findings",
)

# Access results
print(f"Extracted text: {result['text'][:100]}...")
print(f"LLM answer: {result['llm_answer']}")  # If prompt provided
print(f"Cost: ${result['cost']:.3f}")
```

---

## Integration Patterns

### Pattern A: Basic RAG Workflow

```python
# 1. Ingest documents
docs = ["report1.pdf", "report2.pdf", "report3.pdf"]

chunks = []
for doc in docs:
    result = agent.extract(
        file_path=doc,
        chunk_for_rag=True,
        chunk_size=512,
    )
    chunks.extend(result['chunks'])

# 2. Store chunks in vector database (simulated)
vector_store = {}
for i, chunk in enumerate(chunks):
    vector_store[i] = {
        "text": chunk['text'],
        "page": chunk['page'],
        "doc": chunk.get('doc_id'),
    }

# 3. Query with semantic search
query = "What are the financial highlights?"
# ... semantic search logic ...

# 4. Generate answer with LLM
# ... LLM processing ...
```

**See**: `examples/8-multi-modal/document-rag/basic_rag.py`

### Pattern B: Multi-Document RAG with Cost Optimization

```python
from kaizen.agents.multi_modal.document_extraction_agent import (
    DocumentExtractionAgent,
    DocumentExtractionConfig,
)

# Cost-aware configuration
config = DocumentExtractionConfig(
    provider="auto",  # Automatic provider selection
    landing_ai_key=os.getenv('LANDING_AI_API_KEY'),
    openai_key=os.getenv('OPENAI_API_KEY'),
    chunk_for_rag=True,
    chunk_size=512,
)

agent = DocumentExtractionAgent(config=config)

# Budget-constrained extraction
for doc in documents:
    # Estimate cost before extraction
    cost_estimate = agent.estimate_cost(doc)

    if cost_estimate > budget_per_doc:
        # Use free provider
        result = agent.extract(doc, provider="ollama_vision")
    else:
        # Use automatic selection
        result = agent.extract(doc, provider="auto")

    process_result(result)
```

**See**: `examples/8-multi-modal/document-rag/advanced_rag.py`

### Pattern C: Core SDK Workflow Integration

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime
from kaizen.agents.multi_modal.document_extraction_agent import (
    DocumentExtractionAgent,
    DocumentExtractionConfig,
)

# Create document extraction agent
config = DocumentExtractionConfig(provider="ollama_vision")
doc_agent = DocumentExtractionAgent(config=config)

# Async extraction function
async def extract_document(file_path: str):
    result = doc_agent.extract(file_path, chunk_for_rag=True)
    return result

# Build workflow
workflow = WorkflowBuilder()
# ... add workflow nodes ...

# Execute with async runtime
runtime = AsyncLocalRuntime()
results = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

**See**: `examples/8-multi-modal/document-rag/workflow_integration.py`

---

## Cost Optimization

### Provider Comparison

| Provider | Accuracy | Cost/Page | Bounding Boxes | Tables | Speed |
|----------|----------|-----------|----------------|--------|-------|
| **Landing AI** | 98% | $0.015 | ✅ Yes | ✅ Yes | 1.2s |
| **OpenAI Vision** | 95% | $0.068 | ❌ No | ✅ Yes | 0.8s (fastest) |
| **Ollama** | 85% | $0.00 (FREE) | ❌ No | ✅ Yes | 2.5s |

### Strategy 1: Prefer Free (Recommended)

```python
config = DocumentExtractionConfig(
    provider="ollama_vision",  # Use free local provider
    chunk_for_rag=True,
)

# Cost: $0.00 per document
# Trade-off: 85% accuracy (acceptable for most use cases)
```

**Savings**: ~$0.05-0.20 per document vs. paid providers

### Strategy 2: Budget-Constrained Auto-Selection

```python
config = DocumentExtractionConfig(
    provider="auto",
    landing_ai_key=os.getenv('LANDING_AI_API_KEY'),
    openai_key=os.getenv('OPENAI_API_KEY'),
)

# Extraction with budget constraint
result = agent.extract(
    file_path="doc.pdf",
    max_cost=0.01,  # $0.01 budget limit
)

# If cost exceeds budget, automatically uses free Ollama
```

### Strategy 3: Accuracy-First Fallback Chain

```python
# Primary: Landing AI (highest accuracy)
# Fallback: OpenAI Vision (faster, cheaper)
# Final fallback: Ollama (free)

config = DocumentExtractionConfig(
    provider="auto",
    landing_ai_key=os.getenv('LANDING_AI_API_KEY'),
    openai_key=os.getenv('OPENAI_API_KEY'),
)

# Automatic fallback if primary provider unavailable
result = agent.extract("doc.pdf", provider="auto")
```

### Cost Estimation

```python
# Estimate before extraction
cost_estimates = agent.estimate_cost("document.pdf", provider="auto")

print(f"Landing AI: ${cost_estimates['landing_ai']:.3f}")
print(f"OpenAI: ${cost_estimates['openai_vision']:.3f}")
print(f"Ollama: ${cost_estimates['ollama_vision']:.3f}")  # Always $0.00

# Make informed decision
if cost_estimates['landing_ai'] > budget:
    provider = "ollama_vision"  # Use free
else:
    provider = "landing_ai"  # Use highest accuracy

result = agent.extract("document.pdf", provider=provider)
```

---

## Production Deployment

### Recommended Configuration

```python
# Production-ready configuration
config = DocumentExtractionConfig(
    # Provider settings
    provider="auto",  # Automatic selection
    landing_ai_key=os.getenv('LANDING_AI_API_KEY'),
    openai_key=os.getenv('OPENAI_API_KEY'),
    ollama_base_url=os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'),

    # RAG settings
    chunk_for_rag=True,
    chunk_size=512,
    chunk_overlap=50,

    # LLM settings (for agent reasoning if needed)
    llm_provider="openai",
    model="gpt-3.5-turbo",
)
```

### Environment Variables

```bash
# .env file
LANDING_AI_API_KEY=lnd_xxx...
OPENAI_API_KEY=sk-xxx...
OLLAMA_BASE_URL=http://localhost:11434
```

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install dependencies
RUN pip install kailash-kaizen

# Install Ollama (for free local processing)
RUN curl https://ollama.ai/install.sh | sh

# Start Ollama service
RUN ollama pull llama3.2-vision

# Copy application
COPY . /app
WORKDIR /app

CMD ["python", "main.py"]
```

### Monitoring

```python
# Track extraction metrics
class DocumentMetrics:
    def __init__(self):
        self.total_docs = 0
        self.total_cost = 0.0
        self.provider_usage = {}

    def record(self, result: dict):
        self.total_docs += 1
        self.total_cost += result['cost']

        provider = result['provider']
        self.provider_usage[provider] = self.provider_usage.get(provider, 0) + 1

    def report(self):
        return {
            "total_documents": self.total_docs,
            "total_cost": self.total_cost,
            "avg_cost": self.total_cost / self.total_docs if self.total_docs > 0 else 0,
            "provider_usage": self.provider_usage,
        }

# Usage
metrics = DocumentMetrics()

for doc in documents:
    result = agent.extract(doc)
    metrics.record(result)

print(metrics.report())
```

---

## Troubleshooting

### Issue 1: Document extraction not enabled

**Error**:
```
RuntimeError: Document extraction not enabled.
Set enable_document_extraction=True in VisionAgentConfig
```

**Solution**:
```python
# Enable document extraction in config
config = VisionAgentConfig(
    enable_document_extraction=True,
    landing_ai_api_key=os.getenv('LANDING_AI_API_KEY'),
)
```

### Issue 2: Provider not available

**Error**:
```
RuntimeError: Provider 'landing_ai' not available. Check API key.
```

**Solution**:
```python
# Check API keys are set
import os
print(f"Landing AI key: {os.getenv('LANDING_AI_API_KEY')[:10]}...")

# Or use free provider
config = DocumentExtractionConfig(provider="ollama_vision")
```

### Issue 3: Ollama not running

**Error**:
```
ConnectionError: Cannot connect to Ollama at http://localhost:11434
```

**Solution**:
```bash
# Start Ollama service
ollama serve

# Pull vision model
ollama pull llama3.2-vision

# Verify service
curl http://localhost:11434/api/tags
```

### Issue 4: Cost exceeds budget

**Error**:
```
RuntimeError: Estimated cost $0.068 exceeds budget $0.01
```

**Solution**:
```python
# Use free provider for budget-constrained scenarios
result = agent.extract(
    file_path="doc.pdf",
    provider="ollama_vision",  # Always $0.00
)

# Or increase budget
config = DocumentExtractionConfig(max_cost=0.10)
```

### Issue 5: Empty chunks

**Problem**: `result['chunks']` is empty

**Solution**:
```python
# Ensure chunk_for_rag=True
result = agent.extract(
    file_path="doc.pdf",
    chunk_for_rag=True,  # Must be True to generate chunks
    chunk_size=512,
)

# Check if document has extractable text
if not result['text']:
    print("Document has no extractable text (may be scanned image)")
```

---

## Next Steps

1. **Try Examples**:
   - `examples/8-multi-modal/document-rag/basic_rag.py`
   - `examples/8-multi-modal/document-rag/advanced_rag.py`
   - `examples/8-multi-modal/document-rag/workflow_integration.py`

2. **Integrate with Vector Database**:
   - ChromaDB, Pinecone, Weaviate, Qdrant
   - Store chunks with embeddings
   - Semantic search for retrieval

3. **Connect to LLM**:
   - Use retrieved chunks as context
   - Generate answers with citations
   - Implement RAG Q&A system

4. **Deploy to Production**:
   - Use Nexus for API/CLI/MCP deployment
   - Monitor costs and usage
   - Optimize provider selection

---

**Last Updated**: 2025-10-22
**Kaizen Version**: v0.4.0 (TODO-167)
**Test Coverage**: 201/201 tests passing (100%)
