# Comprehensive RAG Toolkit Guide

The Kailash SDK includes a state-of-the-art RAG (Retrieval Augmented Generation) toolkit with 40+ specialized nodes covering every aspect of modern RAG systems. This guide covers all components and usage patterns.

## Table of Contents
1. [Quick Start](#quick-start)
2. [Core RAG Strategies](#core-rag-strategies)
3. [Advanced RAG Techniques](#advanced-rag-techniques)
4. [Similarity Approaches](#similarity-approaches)
5. [Query Processing](#query-processing)
6. [Performance Optimization](#performance-optimization)
7. [Graph-Enhanced RAG](#graph-enhanced-rag)
8. [Agentic RAG](#agentic-rag)
9. [Multimodal RAG](#multimodal-rag)
10. [Real-time RAG](#real-time-rag)
11. [RAG Evaluation](#rag-evaluation)
12. [Privacy-Preserving RAG](#privacy-preserving-rag)
13. [Conversational RAG](#conversational-rag)
14. [Federated RAG](#federated-rag)
15. [Complete Examples](#complete-examples)
16. [Best Practices](#best-practices)

## Quick Start

```python
from kailash.nodes.rag import (
    AdaptiveRAGWorkflowNode,
    RAGStrategyRouterNode,
    AsyncParallelRAGNode
)
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Method 1: Fully Adaptive RAG (Recommended)
adaptive_rag = AdaptiveRAGWorkflowNode(
    name="smart_rag",
    llm_model="gpt-4"
)

result = await adaptive_rag.run(
    documents=documents,
    query="How to optimize neural network training?"
)

# Method 2: Manual Strategy Selection with Routing
builder = WorkflowBuilder()

# Add intelligent router
router_id = builder.add_node("RAGStrategyRouterNode", "router")

# Add strategy implementations
semantic_id = builder.add_node("SemanticRAGNode", "semantic_rag")
hybrid_id = builder.add_node("HybridRAGNode", "hybrid_rag")

# Connect based on routing decision
builder.add_node("SwitchNode", "strategy_switch", config={
    "condition_field": "strategy",
    "routes": {
        "semantic": semantic_id,
        "hybrid": hybrid_id
    }
})

# Method 3: Parallel Execution for Maximum Performance
parallel_rag = AsyncParallelRAGNode(
    strategies=["semantic", "sparse", "hybrid"]
)

```

## Core RAG Strategies

### 1. Semantic RAG
Best for conceptual understanding and narrative content.

```python
from kailash.nodes.rag import SemanticRAGNode, RAGConfig

config = RAGConfig(
    chunk_size=512,
    chunk_overlap=50,
    retrieval_k=5,
    embedding_model="text-embedding-3-small"
)

semantic_rag = SemanticRAGNode("semantic", config)

# Index documents
await semantic_rag.run(
    documents=documents,
    operation="index"
)

# Retrieve
results = await semantic_rag.run(
    query="What is machine learning?",
    operation="retrieve"
)

```

### 2. Statistical RAG
Optimal for technical documentation and keyword-heavy content.

```python
from kailash.nodes.rag import StatisticalRAGNode

statistical_rag = StatisticalRAGNode(
    "statistical",
    config=RAGConfig(variance_threshold=0.7)
)

# Works best with technical documents
results = await statistical_rag.run(
    documents=technical_docs,
    query="API endpoint authentication"
)

```

### 3. Hybrid RAG
Combines semantic and statistical approaches for balanced performance.

```python
from kailash.nodes.rag import HybridRAGNode

hybrid_rag = HybridRAGNode(
    "hybrid",
    semantic_weight=0.7,
    statistical_weight=0.3
)

# Automatically balances both approaches
results = await hybrid_rag.run(
    documents=mixed_content,
    query="How to implement OAuth2 authentication?"
)

```

### 4. Hierarchical RAG
Multi-level document processing for complex documents.

```python
from kailash.nodes.rag import HierarchicalRAGNode

hierarchical_rag = HierarchicalRAGNode(
    "hierarchical",
    levels=["document", "section", "paragraph"],
    aggregation_method="weighted"
)

# Processes documents at multiple granularities
results = await hierarchical_rag.run(
    documents=long_documents,
    query="Summary of main findings"
)

```

## Advanced RAG Techniques

### Self-Correcting RAG
Iteratively improves results through verification and refinement.

```python
from kailash.nodes.rag import SelfCorrectingRAGNode

self_correcting = SelfCorrectingRAGNode(
    max_corrections=2,
    confidence_threshold=0.85
)

# Automatically refines until confident
result = await self_correcting.run(
    documents=documents,
    query="Complex technical question requiring accuracy"
)

```

### RAG-Fusion
Multi-query approach with result fusion for comprehensive answers.

```python
from kailash.nodes.rag import RAGFusionNode

rag_fusion = RAGFusionNode(
    num_query_variations=4,
    fusion_method="rrf"  # Reciprocal Rank Fusion
)

# Generates multiple queries and fuses results
result = await rag_fusion.run(
    documents=documents,
    query="Explain transformer architecture"
)

```

### HyDE (Hypothetical Document Embeddings)
Generates hypothetical answers to improve retrieval.

```python
from kailash.nodes.rag import HyDENode

hyde = HyDENode(
    use_multiple_hypotheses=True,
    num_hypotheses=3
)

# Creates hypothetical documents for better matching
result = await hyde.run(
    documents=documents,
    query="What would ideal documentation look like?"
)

```

### Step-Back RAG
Abstract reasoning with background context.

```python
from kailash.nodes.rag import StepBackRAGNode

step_back = StepBackRAGNode()

# Generates abstract query first, then specific
result = await step_back.run(
    documents=documents,
    query="Why does gradient descent converge?"
)

```

## Similarity Approaches

### Dense Retrieval
Advanced dense embeddings with instruction awareness.

```python
from kailash.nodes.rag import DenseRetrievalNode

dense = DenseRetrievalNode(
    embedding_model="text-embedding-3-large",
    use_instruction_embeddings=True,
    instruction_template="Represent this document for retrieval: {text}"
)

```

### Sparse Retrieval
BM25 and TF-IDF with query expansion.

```python
from kailash.nodes.rag import SparseRetrievalNode

sparse = SparseRetrievalNode(
    method="bm25",
    use_query_expansion=True,
    expansion_terms=5
)

```

### ColBERT Retrieval
Token-level late interaction for fine-grained matching.

```python
from kailash.nodes.rag import ColBERTRetrievalNode

colbert = ColBERTRetrievalNode()

# Best for complex queries with multiple concepts
result = await colbert.run(
    documents=documents,
    query="transformers attention mechanism implementation details"
)

```

### Multi-Vector Retrieval
Multiple representations per document.

```python
from kailash.nodes.rag import MultiVectorRetrievalNode

multi_vector = MultiVectorRetrievalNode(
    representations=["summary", "chunks", "questions"]
)

```

### Cross-Encoder Reranking
Two-stage retrieval with neural reranking.

```python
from kailash.nodes.rag import CrossEncoderRerankNode

reranker = CrossEncoderRerankNode(
    rerank_model="cross-encoder/ms-marco-MiniLM-L-12-v2",
    top_k_rerank=20
)

```

## Query Processing

### Query Expansion
Enhances queries with synonyms and related concepts.

```python
from kailash.nodes.rag import QueryExpansionNode

expander = QueryExpansionNode(
    num_expansions=5,
    use_llm=True,
    expansion_strategy="synonyms"
)

```

### Query Decomposition
Breaks complex queries into sub-questions.

```python
from kailash.nodes.rag import QueryDecompositionNode

decomposer = QueryDecompositionNode(
    max_sub_questions=4,
    decomposition_strategy="hierarchical"
)

# Handles multi-part questions
result = await decomposer.run(
    query="Compare transformers vs RNNs for NLP and explain when to use each"
)

```

### Adaptive Query Processing
Intelligently processes queries based on type and complexity.

```python
from kailash.nodes.rag import AdaptiveQueryProcessorNode

processor = AdaptiveQueryProcessorNode()

# Automatically applies optimal processing
result = await processor.run(
    query="wat r transformers?",  # Handles typos, expands, etc.
    context="machine learning"
)

```

## Performance Optimization

### Cache-Optimized RAG
Multi-level caching with semantic similarity.

```python
from kailash.nodes.rag import CacheOptimizedRAGNode

cached_rag = CacheOptimizedRAGNode(
    cache_ttl=3600,  # 1 hour
    similarity_threshold=0.95
)

# First query: ~500ms
result1 = await cached_rag.run(query="What is BERT?")

# Identical query: ~10ms (from cache)
result2 = await cached_rag.run(query="What is BERT?")

# Similar query: ~15ms (semantic cache)
result3 = await cached_rag.run(query="Explain BERT")

```

### Async Parallel RAG
Concurrent execution of multiple strategies.

```python
from kailash.nodes.rag import AsyncParallelRAGNode

parallel = AsyncParallelRAGNode(
    strategies=["semantic", "sparse", "colbert", "hyde"]
)

# Runs all strategies in parallel
result = await parallel.run(
    documents=documents,
    query="Complex query needing multiple perspectives"
)

```

### Streaming RAG
Progressive result delivery for real-time UIs.

```python
from kailash.nodes.rag import StreamingRAGNode

streaming = StreamingRAGNode(chunk_size=100)

# Stream results as they arrive
async for chunk in streaming.stream(
    documents=documents,
    query="Long technical explanation"
):
    print(f"Chunk {chunk['chunk_id']}: {len(chunk['results'])} results")

```

### Batch-Optimized RAG
High-throughput batch processing.

```python
from kailash.nodes.rag import BatchOptimizedRAGNode

batch_rag = BatchOptimizedRAGNode(batch_size=32)

queries = ["query1", "query2", ..., "query100"]

# Processes efficiently in batches
results = await batch_rag.run(
    queries=queries,
    documents=documents
)

```

## Graph-Enhanced RAG

### GraphRAG
Knowledge graph construction and querying for complex reasoning.

```python
from kailash.nodes.rag import GraphRAGNode

graph_rag = GraphRAGNode(
    entity_types=["person", "technology", "concept"],
    max_hops=3
)

# Builds knowledge graph and performs multi-hop reasoning
result = await graph_rag.run(
    documents=research_papers,
    query="How did key researchers influence transformer development?"
)

```

### Graph Builder
Dedicated knowledge graph construction.

```python
from kailash.nodes.rag import GraphBuilderNode

builder = GraphBuilderNode(
    merge_similar_entities=True,
    similarity_threshold=0.85
)

# Build graph from documents
graph = await builder.run(
    documents=documents,
    entity_types=["person", "organization", "technology"]
)

```

### Graph Query
Execute complex graph queries.

```python
from kailash.nodes.rag import GraphQueryNode

querier = GraphQueryNode()

# Find paths between entities
result = await querier.run(
    graph=knowledge_graph,
    query_type="path",
    source_entity="BERT",
    target_entity="GPT",
    max_length=4
)

```

## Agentic RAG

### Autonomous Agent RAG
RAG with reasoning and tool use capabilities.

```python
from kailash.nodes.rag import AgenticRAGNode

agent_rag = AgenticRAGNode(
    tools=["search", "calculator", "database"],
    max_reasoning_steps=5
)

# Agent will plan, use tools, and synthesize
result = await agent_rag.run(
    documents=financial_docs,
    query="Compare revenue growth of tech companies in 2023 vs 2022"
)

```

### Tool-Augmented RAG
Enhances RAG with specialized tools.

```python
from kailash.nodes.rag import ToolAugmentedRAGNode

def calculate_metric(query, context):
    # Custom calculation logic
    return {"result": 42}

tool_rag = ToolAugmentedRAGNode(
    tool_registry={
        "calculator": calculate_metric,
        "unit_converter": convert_units
    }
)

```

## Multimodal RAG

### Text + Image RAG
Retrieval and generation across text and images.

```python
from kailash.nodes.rag import MultimodalRAGNode

multimodal_rag = MultimodalRAGNode(
    image_encoder="clip-base",
    enable_ocr=True
)

# Handles mixed text and image documents
result = await multimodal_rag.run(
    documents=mixed_media_docs,  # Contains text and images
    query="Show me the architecture diagram for transformers"
)

```

### Visual Question Answering
Answer questions about images.

```python
from kailash.nodes.rag import VisualQuestionAnsweringNode

vqa = VisualQuestionAnsweringNode(
    model="blip2-base",
    enable_captioning=True
)

result = await vqa.run(
    image_path="architecture_diagram.png",
    question="What components are shown in this diagram?"
)

```

## Real-time RAG

### Live Data RAG
RAG with continuous updates from live sources.

```python
from kailash.nodes.rag import RealtimeRAGNode

realtime_rag = RealtimeRAGNode(
    update_interval=5.0,  # 5 seconds
    relevance_decay_rate=0.95
)

# Start monitoring data sources
await realtime_rag.start_monitoring([
    {"type": "api", "endpoint": "https://api.news/feed"},
    {"type": "file", "path": "/data/live/*.json"}
])

# Query with real-time data
result = await realtime_rag.run(
    query="What are the latest AI developments?"
)

```

### Incremental Index Updates
Efficient index updates without rebuilding.

```python
from kailash.nodes.rag import IncrementalIndexNode

index = IncrementalIndexNode(
    index_type="hybrid",
    merge_strategy="immediate"
)

# Add new documents
await index.run(
    operation="add",
    documents=new_docs
)

# Remove outdated
await index.run(
    operation="remove",
    document_ids=old_ids
)

```

## RAG Evaluation

### Comprehensive Evaluation
Evaluate RAG quality across multiple dimensions.

```python
from kailash.nodes.rag import RAGEvaluationNode

evaluator = RAGEvaluationNode(
    metrics=["faithfulness", "relevance", "context_precision"],
    use_reference_answers=True
)

# Evaluate your RAG system
results = await evaluator.run(
    test_queries=[
        {
            "query": "What is BERT?",
            "reference": "BERT is a bidirectional transformer..."
        }
    ],
    rag_system=my_rag_node
)

print(f"Overall score: {results['aggregate_metrics']['overall_score']:.2f}")
print(f"Failures: {results['failure_analysis']['failure_count']}")

```

### Performance Benchmarking
Compare RAG systems performance.

```python
from kailash.nodes.rag import RAGBenchmarkNode

benchmark = RAGBenchmarkNode(
    workload_sizes=[10, 100, 1000],
    concurrent_users=[1, 5, 10]
)

results = await benchmark.run(
    rag_systems={
        "semantic": semantic_rag,
        "hybrid": hybrid_rag,
        "graph": graph_rag
    },
    test_queries=benchmark_queries
)

```

### Test Dataset Generation
Generate synthetic test data.

```python
from kailash.nodes.rag import TestDatasetGeneratorNode

generator = TestDatasetGeneratorNode(
    categories=["factual", "analytical", "comparative"],
    include_adversarial=True
)

dataset = await generator.run(
    num_samples=100,
    domain="machine learning"
)

```

## Privacy-Preserving RAG

### Differential Privacy RAG
RAG with privacy guarantees.

```python
from kailash.nodes.rag import PrivacyPreservingRAGNode

private_rag = PrivacyPreservingRAGNode(
    privacy_budget=1.0,  # epsilon for differential privacy
    redact_pii=True,
    anonymize_queries=True
)

# Automatically protects sensitive information
result = await private_rag.run(
    query="What is John Smith's medical condition?",
    documents=medical_records,
    user_consent={"data_usage": True}
)

```

### Secure Multi-Party RAG
Federated computation without data sharing.

```python
from kailash.nodes.rag import SecureMultiPartyRAGNode

smpc_rag = SecureMultiPartyRAGNode(
    parties=["hospital_a", "hospital_b", "research_lab"],
    protocol="secret_sharing"
)

# Compute across parties without exposing data
result = await smpc_rag.run(
    query="Average treatment success rate",
    party_data={
        "hospital_a": encrypted_data_a,
        "hospital_b": encrypted_data_b
    }
)

```

### Compliance-Aware RAG
GDPR/HIPAA compliant RAG operations.

```python
from kailash.nodes.rag import ComplianceRAGNode

compliance_rag = ComplianceRAGNode(
    regulations=["gdpr", "hipaa"],
    default_retention_days=30
)

result = await compliance_rag.run(
    query="Patient treatment history",
    user_consent={
        "purpose": "medical_diagnosis",
        "retention_allowed": True
    },
    jurisdiction="EU"
)

```

## Conversational RAG

### Multi-turn Context Management
RAG with conversation memory.

```python
from kailash.nodes.rag import ConversationalRAGNode

conv_rag = ConversationalRAGNode(
    max_context_turns=10,
    enable_summarization=True
)

# Create session
session = conv_rag.create_session(user_id="user123")

# First turn
response1 = await conv_rag.run(
    query="What is transformer architecture?",
    session_id=session["session_id"]
)

# Follow-up with context
response2 = await conv_rag.run(
    query="How does its attention mechanism work?",  # "its" resolved
    session_id=session["session_id"]
)

```

### Long-term Memory
Persistent user memory across sessions.

```python
from kailash.nodes.rag import ConversationMemoryNode

memory = ConversationMemoryNode(
    memory_types=["episodic", "semantic", "preferences"],
    retention_policy="adaptive"
)

# Store insights
await memory.run(
    operation="store",
    user_id="user123",
    data={
        "facts": [
            {"key": "expertise_level", "value": "intermediate"},
            {"key": "interests", "value": ["NLP", "computer vision"]}
        ],
        "preferences": {"explanation_style": "detailed"}
    }
)

# Retrieve for personalization
memories = await memory.run(
    operation="retrieve",
    user_id="user123",
    context="deep learning question"
)

```

## Federated RAG

### Distributed RAG
RAG across multiple organizations.

```python
from kailash.nodes.rag import FederatedRAGNode

federated_rag = FederatedRAGNode(
    federation_nodes=["org_a", "org_b", "org_c"],
    aggregation_strategy="weighted_average"
)

# Query across all organizations
result = await federated_rag.run(
    query="Industry-wide best practices",
    node_endpoints={
        "org_a": "https://orgA.api/rag",
        "org_b": "https://orgB.api/rag"
    }
)

```

### Edge RAG
Optimized for resource-constrained devices.

```python
from kailash.nodes.rag import EdgeRAGNode

edge_rag = EdgeRAGNode(
    model_size="tiny",  # 50MB model
    max_cache_size_mb=100,
    power_mode="low_power"
)

# Runs locally with minimal resources
result = await edge_rag.run(
    query="Local sensor anomaly detection",
    local_data=sensor_readings,
    sync_with_cloud=False
)

```

### Cross-Silo Federation
RAG with strict data governance.

```python
from kailash.nodes.rag import CrossSiloRAGNode

cross_silo = CrossSiloRAGNode(
    silos=["company_a", "company_b", "company_c"],
    data_sharing_agreement="minimal",
    audit_mode="comprehensive"
)

result = await cross_silo.run(
    query="Market trend analysis",
    requester_org="company_a",
    access_permissions=["read_aggregated"]
)

```

## Complete Examples

### Example 1: Production RAG Pipeline
Complete production-ready RAG with all optimizations.

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.rag import *

builder = WorkflowBuilder()

# 1. Query processing
query_processor = builder.add_node(
    "AdaptiveQueryProcessorNode",
    "query_processor"
)

# 2. Cache check
cache = builder.add_node(
    "CacheOptimizedRAGNode",
    "cache",
    config={"cache_ttl": 3600}
)

# 3. Parallel strategies
parallel = builder.add_node(
    "AsyncParallelRAGNode",
    "parallel_rag",
    config={"strategies": ["semantic", "sparse", "hyde"]}
)

# 4. Reranking
reranker = builder.add_node(
    "CrossEncoderRerankNode",
    "reranker"
)

# 5. Quality check
quality = builder.add_node(
    "RAGQualityAnalyzerNode",
    "quality"
)

# 6. Self-correction if needed
corrector = builder.add_node(
    "SelfCorrectingRAGNode",
    "corrector",
    config={"confidence_threshold": 0.85}
)

# Connect pipeline
builder.add_connection(query_processor, "processed_query", cache, "query")
builder.add_connection(cache, "optimized_results", parallel, "_skip_if_cached")
builder.add_connection(parallel, "parallel_results", reranker, "initial_results")
builder.add_connection(reranker, "reranked_results", quality, "rag_results")
builder.add_connection(quality, "quality_score", corrector, "_skip_if_above_0.8")

# Build and run
workflow = builder.build(name="production_rag")
runtime = LocalRuntime()

result = await runtime.run_workflow(
    workflow,
    input_data={
        "query": "Complex technical question",
        "documents": documents
    }
)

```

### Example 2: Multimodal Conversational RAG
Advanced multimodal RAG with conversation context.

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Initialize components
conv_rag = ConversationalRAGNode(
    max_context_turns=10,
    coreference_resolution=True
)

multimodal = MultimodalRAGNode(
    image_encoder="clip-base",
    enable_ocr=True
)

# Create conversation session
session = conv_rag.create_session(user_id="user123")

# First turn - text query
response1 = await conv_rag.run(
    query="Show me transformer architecture",
    documents=mixed_media_docs,
    session_id=session["session_id"]
)

# Second turn - follow-up with image
response2 = await multimodal.run(
    documents=[
        {"type": "image", "path": "transformer_diagram.png"},
        {"type": "text", "content": response1["response"]}
    ],
    query="What's different in this diagram compared to what you described?"
)

```

### Example 3: Privacy-Preserving Federated RAG
Secure RAG across multiple organizations.

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Setup federated nodes
federated = FederatedRAGNode(
    federation_nodes=["hospital_a", "hospital_b", "clinic_c"],
    aggregation_strategy="secure_average"
)

# Add privacy layer
private = PrivacyPreservingRAGNode(
    privacy_budget=1.0,
    redact_pii=True
)

# Compose pipeline
builder = WorkflowBuilder()

privacy_id = builder.add_node("PrivacyPreservingRAGNode", "privacy",
    config={"redact_pii": True})

federated_id = builder.add_node("FederatedRAGNode", "federated",
    config={"min_participating_nodes": 2})

builder.add_connection(privacy_id, "privacy_preserving_results",
                      federated_id, "query")

# Execute with privacy and federation
workflow = builder.build(name="private_federated_rag")

runtime = LocalRuntime()
workflow.run_workflow(
    workflow,
    input_data={
        "query": "Patient treatment effectiveness analysis",
        "node_endpoints": endpoints,
        "user_consent": {"purpose": "research", "data_usage": True}
    }
)

```

## Best Practices

### 1. Strategy Selection
- Use `AdaptiveRAGWorkflowNode` for automatic strategy selection
- For known document types, choose specific strategies:
  - Technical docs → Statistical/Hybrid RAG
  - Narrative content → Semantic RAG
  - Mixed content → Hybrid RAG
  - Complex reasoning → GraphRAG

### 2. Performance Optimization
- Always enable caching for production systems
- Use parallel execution for quality-critical applications
- Implement streaming for real-time UIs
- Batch queries when possible

### 3. Quality Assurance
- Use `SelfCorrectingRAGNode` for critical applications
- Implement evaluation pipelines with `RAGEvaluationNode`
- Monitor performance with `RAGPerformanceMonitorNode`
- A/B test different strategies

### 4. Privacy and Compliance
- Use `PrivacyPreservingRAGNode` for sensitive data
- Implement audit trails for regulated industries
- Consider federated approaches for multi-org scenarios
- Always validate consent and permissions

### 5. Advanced Techniques
- Combine multiple approaches (e.g., GraphRAG + Multimodal)
- Use conversational context for interactive applications
- Implement progressive enhancement (cache → fast → accurate)
- Leverage agentic capabilities for complex reasoning

### 6. Error Handling
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

try:
    result = await rag_node.run(query=query, documents=docs)
except Exception as e:
    # Fallback to simpler strategy
    fallback = SemanticRAGNode()
    result = await fallback.run(query=query, documents=docs)

```

### 7. Monitoring and Debugging
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Enable detailed logging
import logging
logging.getLogger("kailash.nodes.rag").setLevel(logging.DEBUG)

# Use performance monitor
monitor = RAGPerformanceMonitorNode()
await monitor.run(rag_pipeline=my_pipeline, test_queries=queries)

```

## Next Steps

1. **Start Simple**: Begin with `AdaptiveRAGWorkflowNode`
2. **Evaluate**: Use the evaluation framework to measure quality
3. **Optimize**: Add caching and parallel execution
4. **Specialize**: Implement advanced techniques as needed
5. **Scale**: Consider federated approaches for large deployments

For more examples, see the comprehensive example at:
`examples/feature_examples/rag/comprehensive_rag_enhanced_example.py`

For architecture decisions and trade-offs, refer to:
the SDK architecture decisions documentation
