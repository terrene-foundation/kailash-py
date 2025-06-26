"""
RAG (Retrieval Augmented Generation) Toolkit

Comprehensive RAG implementation with swappable strategies, conditional routing,
and enterprise-grade features. Supports semantic, statistical, hybrid, and
hierarchical RAG approaches with advanced similarity methods.

## Quick Start

```python
from kailash.nodes.rag import (
    RAGStrategyRouterNode,
    SemanticRAGWorkflowNode,
    HybridRAGWorkflowNode,
    AdaptiveRAGWorkflowNode,
    ColBERTRetrievalNode,
    AsyncParallelRAGNode
)

# Method 1: AI-driven strategy selection
workflow.add_node("rag_router", RAGStrategyRouterNode())
workflow.add_node("rag_processor", SwitchNode(
    condition_field="strategy",
    routes={
        "semantic": "semantic_rag",
        "hybrid": "hybrid_rag",
        "hierarchical": "hierarchical_rag"
    }
))

# Method 2: Direct strategy selection
workflow.add_node("rag", HybridRAGWorkflowNode(
    chunking_strategy="semantic",
    retrieval_method="hybrid",
    vector_db="postgresql"
))

# Method 3: Advanced similarity approaches
workflow.add_node("colbert", ColBERTRetrievalNode())
workflow.add_node("multi_vector", MultiVectorRetrievalNode())
```

## Available Components

### Core Strategies
- **SemanticRAGNode**: Semantic chunking + dense retrieval
- **StatisticalRAGNode**: Statistical chunking + sparse retrieval
- **HybridRAGNode**: Combines semantic + statistical approaches
- **HierarchicalRAGNode**: Multi-level document processing

### Advanced Techniques
- **SelfCorrectingRAGNode**: Iterative verification and refinement
- **RAGFusionNode**: Multi-query approach with result fusion
- **HyDENode**: Hypothetical Document Embeddings
- **StepBackRAGNode**: Abstract reasoning with background context

### Similarity Approaches
- **DenseRetrievalNode**: Advanced dense embeddings with instruction-awareness
- **SparseRetrievalNode**: BM25, TF-IDF with query expansion
- **ColBERTRetrievalNode**: Token-level late interaction
- **MultiVectorRetrievalNode**: Multiple representations per document
- **CrossEncoderRerankNode**: Two-stage retrieval with reranking
- **HybridFusionNode**: RRF and advanced fusion methods
- **PropositionBasedRetrievalNode**: Atomic fact extraction

### Query Processing
- **QueryExpansionNode**: Synonym and concept expansion
- **QueryDecompositionNode**: Complex query breakdown
- **QueryRewritingNode**: Query optimization for retrieval
- **QueryIntentClassifierNode**: Intent-based routing
- **MultiHopQueryPlannerNode**: Multi-step reasoning
- **AdaptiveQueryProcessorNode**: Intelligent query enhancement

### Performance Optimization
- **CacheOptimizedRAGNode**: Multi-level caching with semantic similarity
- **AsyncParallelRAGNode**: Concurrent strategy execution
- **StreamingRAGNode**: Real-time progressive retrieval
- **BatchOptimizedRAGNode**: High-throughput batch processing

### Workflow Nodes
- **SimpleRAGWorkflowNode**: Basic chunk → embed → store → retrieve
- **AdvancedRAGWorkflowNode**: Multi-stage with quality checks
- **AdaptiveRAGWorkflowNode**: AI-driven strategy selection

### Router & Utilities
- **RAGStrategyRouterNode**: LLM-powered strategy selection
- **RAGQualityAnalyzerNode**: Quality assessment and optimization
- **RAGPerformanceMonitorNode**: Performance tracking and metrics
- **RAGWorkflowRegistry**: Component discovery and recommendations

### Graph-Enhanced RAG
- **GraphRAGNode**: Knowledge graph construction and querying
- **GraphBuilderNode**: Build knowledge graphs from documents
- **GraphQueryNode**: Execute complex graph queries

### Agentic RAG
- **AgenticRAGNode**: Autonomous reasoning with tool use
- **ToolAugmentedRAGNode**: RAG with specialized tool integration
- **ReasoningRAGNode**: Multi-step reasoning chains

### Multimodal RAG
- **MultimodalRAGNode**: Text + image retrieval and generation
- **VisualQuestionAnsweringNode**: Answer questions about images
- **ImageTextMatchingNode**: Cross-modal similarity matching

### Real-time & Streaming
- **RealtimeRAGNode**: Live data updates and monitoring
- **IncrementalIndexNode**: Efficient incremental updates

### Evaluation & Testing
- **RAGEvaluationNode**: Comprehensive quality metrics (RAGAS)
- **RAGBenchmarkNode**: Performance benchmarking
- **TestDatasetGeneratorNode**: Synthetic test data generation

### Privacy & Security
- **PrivacyPreservingRAGNode**: Differential privacy and PII protection
- **SecureMultiPartyRAGNode**: Federated computation without data sharing
- **ComplianceRAGNode**: GDPR/HIPAA compliant RAG

### Conversational RAG
- **ConversationalRAGNode**: Multi-turn context management
- **ConversationMemoryNode**: Long-term memory and personalization

### Federated & Distributed
- **FederatedRAGNode**: Distributed RAG across organizations
- **EdgeRAGNode**: Optimized for edge devices
- **CrossSiloRAGNode**: Cross-organizational data federation
"""

from .advanced import HyDENode, RAGFusionNode, SelfCorrectingRAGNode, StepBackRAGNode

# Agentic RAG
from .agentic import AgenticRAGNode, ReasoningRAGNode, ToolAugmentedRAGNode

# Conversational RAG
from .conversational import ConversationalRAGNode, ConversationMemoryNode

# Evaluation Framework
from .evaluation import RAGBenchmarkNode, RAGEvaluationNode, TestDatasetGeneratorNode

# Federated RAG
from .federated import CrossSiloRAGNode, EdgeRAGNode, FederatedRAGNode

# Graph-based RAG
from .graph import GraphBuilderNode, GraphQueryNode, GraphRAGNode

# Multimodal RAG
from .multimodal import (
    ImageTextMatchingNode,
    MultimodalRAGNode,
    VisualQuestionAnsweringNode,
)
from .optimized import (
    AsyncParallelRAGNode,
    BatchOptimizedRAGNode,
    CacheOptimizedRAGNode,
    StreamingRAGNode,
)

# Privacy-preserving RAG
from .privacy import (
    ComplianceRAGNode,
    PrivacyPreservingRAGNode,
    SecureMultiPartyRAGNode,
)
from .query_processing import (
    AdaptiveQueryProcessorNode,
    MultiHopQueryPlannerNode,
    QueryDecompositionNode,
    QueryExpansionNode,
    QueryIntentClassifierNode,
    QueryRewritingNode,
)

# Real-time RAG
from .realtime import IncrementalIndexNode, RealtimeRAGNode
from .realtime import StreamingRAGNode as RealtimeStreamingRAGNode
from .registry import RAGWorkflowRegistry
from .router import (
    RAGPerformanceMonitorNode,
    RAGQualityAnalyzerNode,
    RAGStrategyRouterNode,
)
from .similarity import (
    ColBERTRetrievalNode,
    CrossEncoderRerankNode,
    DenseRetrievalNode,
    HybridFusionNode,
    MultiVectorRetrievalNode,
    PropositionBasedRetrievalNode,
    SparseRetrievalNode,
)
from .strategies import (
    HierarchicalRAGNode,
    HybridRAGNode,
    RAGConfig,
    SemanticRAGNode,
    StatisticalRAGNode,
)
from .workflows import (
    AdaptiveRAGWorkflowNode,
    AdvancedRAGWorkflowNode,
    SimpleRAGWorkflowNode,
)

__all__ = [
    # Core Strategy Nodes
    "SemanticRAGNode",
    "StatisticalRAGNode",
    "HybridRAGNode",
    "HierarchicalRAGNode",
    "RAGConfig",
    # Workflow Nodes
    "SimpleRAGWorkflowNode",
    "AdvancedRAGWorkflowNode",
    "AdaptiveRAGWorkflowNode",
    # Router & Analysis
    "RAGStrategyRouterNode",
    "RAGQualityAnalyzerNode",
    "RAGPerformanceMonitorNode",
    # Advanced RAG Techniques
    "SelfCorrectingRAGNode",
    "RAGFusionNode",
    "HyDENode",
    "StepBackRAGNode",
    # Similarity Approaches
    "DenseRetrievalNode",
    "SparseRetrievalNode",
    "ColBERTRetrievalNode",
    "MultiVectorRetrievalNode",
    "CrossEncoderRerankNode",
    "HybridFusionNode",
    "PropositionBasedRetrievalNode",
    # Query Processing
    "QueryExpansionNode",
    "QueryDecompositionNode",
    "QueryRewritingNode",
    "QueryIntentClassifierNode",
    "MultiHopQueryPlannerNode",
    "AdaptiveQueryProcessorNode",
    # Performance Optimization
    "CacheOptimizedRAGNode",
    "AsyncParallelRAGNode",
    "StreamingRAGNode",
    "BatchOptimizedRAGNode",
    # Registry
    "RAGWorkflowRegistry",
    # Graph-based RAG
    "GraphRAGNode",
    "GraphBuilderNode",
    "GraphQueryNode",
    # Agentic RAG
    "AgenticRAGNode",
    "ToolAugmentedRAGNode",
    "ReasoningRAGNode",
    # Multimodal RAG
    "MultimodalRAGNode",
    "VisualQuestionAnsweringNode",
    "ImageTextMatchingNode",
    # Real-time RAG
    "RealtimeRAGNode",
    "RealtimeStreamingRAGNode",
    "IncrementalIndexNode",
    # Evaluation Framework
    "RAGEvaluationNode",
    "RAGBenchmarkNode",
    "TestDatasetGeneratorNode",
    # Privacy-preserving RAG
    "PrivacyPreservingRAGNode",
    "SecureMultiPartyRAGNode",
    "ComplianceRAGNode",
    # Conversational RAG
    "ConversationalRAGNode",
    "ConversationMemoryNode",
    # Federated RAG
    "FederatedRAGNode",
    "EdgeRAGNode",
    "CrossSiloRAGNode",
]
