#!/usr/bin/env python3
"""
Comprehensive Enhanced RAG Example

Demonstrates the full power of the Kailash RAG toolkit with:
- All similarity approaches
- Advanced query processing
- Performance optimization
- Real-world use cases
"""

import asyncio
import logging
from typing import Any, Dict, List

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kaizen.nodes.rag import (
    AdaptiveQueryProcessorNode,  # Core strategies; Similarity approaches; Query processing; Advanced techniques; Performance optimization; Utilities
)
from kaizen.nodes.rag import (
    AdaptiveRAGWorkflowNode,
    AsyncParallelRAGNode,
    BatchOptimizedRAGNode,
    CacheOptimizedRAGNode,
    ColBERTRetrievalNode,
    CrossEncoderRerankNode,
    DenseRetrievalNode,
    HybridFusionNode,
    HyDENode,
    MultiVectorRetrievalNode,
    PropositionBasedRetrievalNode,
    QueryDecompositionNode,
    QueryExpansionNode,
    QueryIntentClassifierNode,
    QueryRewritingNode,
    RAGFusionNode,
    RAGPerformanceMonitorNode,
    RAGQualityAnalyzerNode,
    SelfCorrectingRAGNode,
    SparseRetrievalNode,
    StepBackRAGNode,
    StreamingRAGNode,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_realistic_documents() -> List[Dict[str, Any]]:
    """Create realistic technical documentation for testing"""
    return [
        {
            "id": "doc_1",
            "title": "Introduction to Transformer Architecture",
            "content": """The Transformer architecture revolutionized natural language processing by introducing
            self-attention mechanisms that capture dependencies regardless of distance in sequences.
            Unlike RNNs, Transformers process all positions simultaneously, enabling massive parallelization.
            The key innovation is multi-head attention, which allows the model to attend to different
            representation subspaces. Combined with positional encodings and layer normalization,
            Transformers achieve state-of-the-art performance on numerous NLP tasks.""",
            "type": "educational",
            "domain": "deep_learning",
        },
        {
            "id": "doc_2",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "content": """BERT (Bidirectional Encoder Representations from Transformers) introduced a new paradigm
            in NLP through masked language modeling and next sentence prediction. By pre-training on massive
            unlabeled text corpora, BERT learns rich contextual representations that can be fine-tuned for
            downstream tasks. The bidirectional nature allows BERT to understand context from both directions,
            unlike previous models like GPT. BERT's architecture consists of stacked transformer encoder layers
            with 12 layers in BERT-base and 24 in BERT-large.""",
            "type": "research",
            "domain": "nlp",
        },
        {
            "id": "doc_3",
            "title": "Implementing Attention Mechanisms in PyTorch",
            "content": """
import torch
import torch.nn as nn
import torch.nn.functional as F

class MultiHeadAttention(nn.Module):
    def __init__(self, d_model, n_heads):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_k = d_model // n_heads

        self.W_q = nn.Linear(d_model, d_model)
        self.W_k = nn.Linear(d_model, d_model)
        self.W_v = nn.Linear(d_model, d_model)
        self.W_o = nn.Linear(d_model, d_model)

    def forward(self, query, key, value, mask=None):
        batch_size = query.size(0)

        # Linear projections in batch from d_model => h x d_k
        Q = self.W_q(query).view(batch_size, -1, self.n_heads, self.d_k).transpose(1, 2)
        K = self.W_k(key).view(batch_size, -1, self.n_heads, self.d_k).transpose(1, 2)
        V = self.W_v(value).view(batch_size, -1, self.n_heads, self.d_k).transpose(1, 2)

        # Attention
        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.d_k)
        if mask is not None:
            scores = scores.masked_fill(mask == 0, -1e9)

        attn_weights = F.softmax(scores, dim=-1)
        context = torch.matmul(attn_weights, V)

        # Concatenate heads and project
        context = context.transpose(1, 2).contiguous().view(
            batch_size, -1, self.d_model
        )
        output = self.W_o(context)

        return output, attn_weights
""",
            "type": "code",
            "domain": "implementation",
        },
        {
            "id": "doc_4",
            "title": "Optimizing Transformer Training",
            "content": """Training large transformer models efficiently requires careful optimization strategies.
            Key techniques include: 1) Mixed precision training using FP16 to reduce memory and increase speed,
            2) Gradient accumulation to simulate larger batch sizes, 3) Learning rate scheduling with warmup
            to stabilize early training, 4) Gradient clipping to prevent exploding gradients, 5) Model
            parallelism and data parallelism for distributed training. Advanced optimizers like Adam with
            weight decay (AdamW) and LAMB enable training with larger batch sizes. Techniques like
            activation checkpointing trade compute for memory, enabling training of deeper models.""",
            "type": "technical",
            "domain": "optimization",
        },
        {
            "id": "doc_5",
            "title": "Vision Transformers (ViT) Architecture",
            "content": """Vision Transformers adapt the transformer architecture for image classification by
            treating images as sequences of patches. An image is divided into fixed-size patches (e.g., 16x16),
            which are linearly embedded and combined with positional embeddings. A special [CLS] token is
            prepended for classification. ViT demonstrates that pure transformer architectures can match or
            exceed CNNs on image classification when pre-trained on large datasets. Key findings include:
            transformers lack inductive biases of CNNs, requiring more data, but scale better with dataset
            size and model capacity.""",
            "type": "research",
            "domain": "computer_vision",
        },
    ]


async def example_1_similarity_comparison():
    """Compare different similarity approaches on the same query"""
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Similarity Approach Comparison")
    print("=" * 80)

    documents = create_realistic_documents()
    query = "How to implement attention mechanism in transformer architecture"

    # Test different similarity approaches
    approaches = {
        "Dense": DenseRetrievalNode(
            embedding_model="text-embedding-3-small", use_instruction_embeddings=True
        ),
        "Sparse": SparseRetrievalNode(method="bm25", use_query_expansion=True),
        "ColBERT": ColBERTRetrievalNode(),
        "Multi-Vector": MultiVectorRetrievalNode(),
        "Proposition": PropositionBasedRetrievalNode(),
    }

    results = {}

    for name, node in approaches.items():
        print(f"\n--- Testing {name} Retrieval ---")
        try:
            result = await node.execute(documents=documents, query=query)

            results[name] = result
            print(f"✅ {name}: Retrieved {len(result.get('results', []))} documents")

            # Show top result
            if result.get("results"):
                top_doc = result["results"][0]
                print(f"   Top result: {top_doc.get('title', 'Unknown')}")
                print(f"   Score: {result.get('scores', [0])[0]:.3f}")

        except Exception as e:
            print(f"❌ {name} failed: {e}")
            results[name] = None

    # Use hybrid fusion to combine results
    print("\n--- Hybrid Fusion of All Approaches ---")
    fusion_node = HybridFusionNode(fusion_method="rrf")

    valid_results = [r for r in results.values() if r is not None]
    if valid_results:
        fused = await fusion_node.execute(retrieval_results=valid_results)
        print(
            f"✅ Fusion completed: {len(fused.get('fused_results', {}).get('results', []))} final results"
        )
        print(
            f"   Fusion improvement: {fused.get('fused_results', {}).get('fusion_ratio', 0):.2f}"
        )


async def example_2_query_processing_pipeline():
    """Demonstrate advanced query processing capabilities"""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Advanced Query Processing Pipeline")
    print("=" * 80)

    # Complex, poorly formed query
    original_query = (
        "wat r the diferrences betwen transformr and cnn 4 visin tasks and nlp"
    )

    print(f"Original query: '{original_query}'")

    # Step 1: Query rewriting
    rewriter = QueryRewritingNode()
    rewritten = await rewriter.execute(query=original_query)

    print("\nQuery Rewriting:")
    print(
        f"  Corrected: {rewritten['rewritten_queries']['versions'].get('corrected', 'N/A')}"
    )
    print(
        f"  Technical: {rewritten['rewritten_queries']['versions'].get('technical', 'N/A')}"
    )
    print(f"  Issues found: {rewritten['rewritten_queries']['issues_found']}")

    corrected_query = rewritten["rewritten_queries"]["recommended"]

    # Step 2: Query intent classification
    classifier = QueryIntentClassifierNode()
    intent = await classifier.execute(query=corrected_query)

    print("\nIntent Classification:")
    print(f"  Type: {intent['routing_decision']['intent_analysis']['query_type']}")
    print(f"  Domain: {intent['routing_decision']['intent_analysis']['domain']}")
    print(
        f"  Complexity: {intent['routing_decision']['intent_analysis']['complexity']}"
    )
    print(
        f"  Recommended strategy: {intent['routing_decision']['recommended_strategy']}"
    )

    # Step 3: Query decomposition (for complex comparative query)
    decomposer = QueryDecompositionNode()
    decomposed = await decomposer.execute(query=corrected_query)

    print("\nQuery Decomposition:")
    for i, sq in enumerate(decomposed["execution_plan"]["sub_questions"]):
        print(f"  {i+1}. {sq['question']} ({sq['type']})")

    # Step 4: Query expansion
    expander = QueryExpansionNode(num_expansions=3)
    expanded = await expander.execute(query=corrected_query)

    print("\nQuery Expansion:")
    for exp in expanded["expanded_query"]["expansions"]:
        print(f"  - {exp}")


async def example_3_advanced_rag_techniques():
    """Demonstrate cutting-edge RAG techniques"""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Advanced RAG Techniques")
    print("=" * 80)

    documents = create_realistic_documents()
    query = "What are the key innovations that make transformers better than previous architectures?"

    # Self-Correcting RAG
    print("\n--- Self-Correcting RAG ---")
    self_correcting = SelfCorrectingRAGNode(
        max_corrections=2, confidence_threshold=0.85
    )

    sc_result = await self_correcting.execute(documents=documents, query=query)

    print("✅ Self-correction completed")
    print(f"   Final confidence: {sc_result['quality_assessment']['confidence']:.3f}")
    print(f"   Attempts: {sc_result['self_correction_metadata']['total_attempts']}")
    print(f"   Status: {sc_result['status']}")

    # RAG-Fusion
    print("\n--- RAG-Fusion ---")
    rag_fusion = RAGFusionNode(num_query_variations=4, fusion_method="rrf")

    fusion_result = await rag_fusion.execute(documents=documents, query=query)

    print("✅ RAG-Fusion completed")
    print(f"   Query variations generated: {len(fusion_result['query_variations'])}")
    for i, variation in enumerate(fusion_result["query_variations"], 1):
        print(f"     {i}. {variation}")
    print(
        f"   Fusion improvement: {fusion_result['fusion_metadata'].get('fusion_score_improvement', 0):.1%}"
    )

    # HyDE
    print("\n--- HyDE (Hypothetical Document Embeddings) ---")
    hyde = HyDENode(use_multiple_hypotheses=True, num_hypotheses=2)

    hyde_result = await hyde.execute(documents=documents, query=query)

    print("✅ HyDE completed")
    print(f"   Hypotheses generated: {len(hyde_result['hypotheses_generated'])}")
    for i, hyp in enumerate(hyde_result["hypotheses_generated"], 1):
        print(f"     {i}. {hyp[:100]}...")

    # Step-Back RAG
    print("\n--- Step-Back RAG ---")
    step_back = StepBackRAGNode()

    sb_result = await step_back.execute(documents=documents, query=query)

    print("✅ Step-Back RAG completed")
    print(f"   Specific query: {sb_result['specific_query']}")
    print(f"   Abstract query: {sb_result['abstract_query']}")
    print(f"   Combined docs: {sb_result['step_back_metadata']['combined_docs_count']}")


async def example_4_performance_optimization():
    """Demonstrate performance optimization techniques"""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Performance Optimization")
    print("=" * 80)

    documents = create_realistic_documents()

    # Cache-Optimized RAG
    print("\n--- Cache-Optimized RAG ---")
    cached_rag = CacheOptimizedRAGNode(cache_ttl=3600, similarity_threshold=0.95)

    # First query (cache miss)
    import time

    start = time.time()
    result1 = await cached_rag.execute(
        documents=documents, query="What is transformer architecture?"
    )
    time1 = time.time() - start

    print(f"✅ First query: {time1:.3f}s (cache miss)")
    print(f"   Source: {result1['optimized_results']['metadata']['source']}")

    # Same query (cache hit)
    start = time.time()
    result2 = await cached_rag.execute(
        documents=documents, query="What is transformer architecture?"
    )
    time2 = time.time() - start

    print(f"✅ Second query: {time2:.3f}s (cache hit)")
    print(f"   Source: {result2['optimized_results']['metadata']['source']}")
    print(f"   Speedup: {time1/time2:.1f}x")

    # Async Parallel RAG
    print("\n--- Async Parallel RAG ---")
    parallel_rag = AsyncParallelRAGNode(strategies=["semantic", "sparse", "hyde"])

    start = time.time()
    parallel_result = await parallel_rag.execute(
        documents=documents, query="How to optimize transformer training?"
    )
    parallel_time = time.time() - start

    print(f"✅ Parallel execution: {parallel_time:.3f}s")
    print(
        f"   Strategies used: {parallel_result['parallel_results']['metadata']['strategies_used']}"
    )
    print(
        f"   Parallel speedup: {parallel_result['parallel_results']['metadata']['parallel_speedup']:.1f}x"
    )

    # Batch Processing
    print("\n--- Batch-Optimized RAG ---")
    batch_rag = BatchOptimizedRAGNode(batch_size=16)

    queries = [
        "What is attention mechanism?",
        "How do transformers work?",
        "What is BERT?",
        "Explain vision transformers",
        "How to train transformers?",
        "What is multi-head attention?",
        "Transformer vs CNN comparison",
        "Self-attention explained",
    ]

    start = time.time()
    batch_result = await batch_rag.execute(queries=queries, documents=documents)
    batch_time = time.time() - start

    print(f"✅ Batch processing: {batch_time:.3f}s for {len(queries)} queries")
    print(f"   Average per query: {batch_time/len(queries):.3f}s")
    print(
        f"   Batch efficiency: {batch_result['final_batch_results']['batch_statistics']['batch_efficiency']:.2f}"
    )


async def example_5_production_pipeline():
    """Complete production-ready RAG pipeline"""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Production RAG Pipeline")
    print("=" * 80)

    documents = create_realistic_documents()
    query = "compair transfomer vs lstm architecure for sequence modeling tasks"

    print(f"Input query: '{query}'")

    # Build production pipeline
    builder = WorkflowBuilder()

    # 1. Adaptive query processing
    query_processor_id = builder.add_node(
        "AdaptiveQueryProcessorNode", "query_processor"
    )

    # 2. Cache check
    cache_id = builder.add_node(
        "CacheOptimizedRAGNode",
        "cache_rag",
        config={"cache_ttl": 3600, "similarity_threshold": 0.9},
    )

    # 3. Intent-based routing
    router_id = builder.add_node("QueryIntentClassifierNode", "intent_router")

    # 4. Parallel RAG strategies
    parallel_id = builder.add_node(
        "AsyncParallelRAGNode",
        "parallel_rag",
        config={"strategies": ["semantic", "sparse", "hyde", "rag_fusion"]},
    )

    # 5. Cross-encoder reranking
    reranker_id = builder.add_node("CrossEncoderRerankNode", "reranker")

    # 6. Quality analysis
    quality_id = builder.add_node("RAGQualityAnalyzerNode", "quality_analyzer")

    # 7. Self-correction if needed
    corrector_id = builder.add_node(
        "SelfCorrectingRAGNode",
        "self_corrector",
        config={"max_corrections": 2, "confidence_threshold": 0.85},
    )

    # 8. Performance monitoring
    monitor_id = builder.add_node("RAGPerformanceMonitorNode", "performance_monitor")

    # Connect pipeline
    builder.add_connection(query_processor_id, "processed_query", cache_id, "query")
    builder.add_connection(
        query_processor_id, "processing_plan", router_id, "query_metadata"
    )
    builder.add_connection(
        cache_id, "optimized_results", parallel_id, "_skip_if_cached"
    )
    builder.add_connection(
        parallel_id, "parallel_results", reranker_id, "initial_results"
    )
    builder.add_connection(reranker_id, "reranked_results", quality_id, "rag_results")
    builder.add_connection(
        quality_id, "quality_score", corrector_id, "_skip_if_above_0.8"
    )
    builder.add_connection(
        corrector_id, "self_correction_metadata", monitor_id, "correction_data"
    )

    # Build and run
    workflow = builder.build(name="production_rag_pipeline")
    runtime = LocalRuntime(enable_async=True)

    print("\n🚀 Running production pipeline...")

    start_time = time.time()
    result = await runtime.run_workflow(
        workflow, input_data={"query": query, "documents": documents}
    )

    total_time = time.time() - start_time

    print(f"\n✅ Pipeline completed in {total_time:.3f}s")
    print(
        f"   Query processed: {result.get('processed_query', {}).get('recommended', query)}"
    )
    print(f"   Cache hit: {result.get('cache_hit', False)}")
    print(f"   Strategies used: {result.get('strategies_used', [])}")
    print(f"   Final quality score: {result.get('quality_score', 0):.3f}")
    print(f"   Self-corrections: {result.get('corrections_made', 0)}")


async def main():
    """Run all RAG toolkit examples"""
    print("🚀 Comprehensive Enhanced RAG Toolkit Demonstration")
    print("=" * 80)
    print("Showcasing the complete Kailash RAG toolkit with:")
    print("- Multiple similarity approaches")
    print("- Advanced query processing")
    print("- Cutting-edge RAG techniques")
    print("- Performance optimization")
    print("- Production-ready pipeline")

    examples = [
        example_1_similarity_comparison,
        example_2_query_processing_pipeline,
        example_3_advanced_rag_techniques,
        example_4_performance_optimization,
        example_5_production_pipeline,
    ]

    for i, example in enumerate(examples, 1):
        try:
            await example()
        except Exception as e:
            print(f"\n❌ Example {i} failed: {e}")
            logger.exception(f"Example {i} failed")

    print("\n" + "=" * 80)
    print("🎉 RAG Toolkit Demonstration Complete!")
    print("=" * 80)
    print("\nKey Takeaways:")
    print("1. ✅ 30+ specialized RAG nodes for every use case")
    print("2. ✅ Multiple similarity approaches with different strengths")
    print("3. ✅ Advanced query processing for real-world queries")
    print("4. ✅ State-of-the-art techniques from 2024 research")
    print("5. ✅ Production-ready performance optimization")
    print("6. ✅ Complete pipeline with quality assurance")
    print("\nAll using 100% Kailash components - no manual orchestration!")


if __name__ == "__main__":
    asyncio.run(main())
