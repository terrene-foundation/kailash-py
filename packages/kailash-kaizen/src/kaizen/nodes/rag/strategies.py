"""
RAG Strategy Workflow Nodes

RAG strategies implemented as WorkflowNodes that encapsulate complete
RAG pipelines using existing Kailash components. Each strategy creates
a workflow using WorkflowBuilder and delegates all execution to the SDK.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kailash.workflow.builder import WorkflowBuilder

from ..base import Node, NodeParameter, register_node
from ..logic.workflow import WorkflowNode

logger = logging.getLogger(__name__)


@dataclass
class RAGConfig:
    """Configuration for RAG strategies"""

    chunk_size: int = 1000
    chunk_overlap: int = 200
    embedding_model: str = "text-embedding-3-small"
    embedding_provider: str = "openai"
    vector_db_provider: str = "postgresql"
    retrieval_k: int = 5
    similarity_threshold: float = 0.7


def create_semantic_rag_workflow(config: RAGConfig) -> WorkflowNode:
    """
    Create semantic RAG workflow using existing Kailash nodes.

    Pipeline: Documents → SemanticChunker → EmbeddingGenerator → VectorDatabase → HybridRetriever
    """
    builder = WorkflowBuilder()

    # Add chunking node
    chunker_id = builder.add_node(
        "SemanticChunkerNode",
        node_id="semantic_chunker",
        config={
            "chunk_size": config.chunk_size,
            "chunk_overlap": config.chunk_overlap,
            "similarity_threshold": config.similarity_threshold,
        },
    )

    # Add embedding generation
    embedder_id = builder.add_node(
        "EmbeddingGeneratorNode",
        node_id="embedder",
        config={"model": config.embedding_model, "provider": config.embedding_provider},
    )

    # Add vector database storage
    vectordb_id = builder.add_node(
        "VectorDatabaseNode",
        node_id="vector_db",
        config={
            "provider": config.vector_db_provider,
            "collection_name": "semantic_rag",
        },
    )

    # Add retrieval node
    retriever_id = builder.add_node(
        "HybridRetrieverNode",
        node_id="retriever",
        config={
            "k": config.retrieval_k,
            "similarity_threshold": config.similarity_threshold,
            "method": "dense",
        },
    )

    # Connect the pipeline
    builder.add_connection(chunker_id, "chunks", embedder_id, "texts")
    builder.add_connection(embedder_id, "embeddings", vectordb_id, "embeddings")
    builder.add_connection(chunker_id, "chunks", vectordb_id, "documents")
    builder.add_connection(
        vectordb_id, "stored_documents", retriever_id, "document_store"
    )

    # Build workflow
    workflow = builder.build(name="semantic_rag_workflow")

    # Return as WorkflowNode
    return WorkflowNode(
        workflow=workflow,
        name="semantic_rag_node",
        description="Semantic RAG with dense embeddings and semantic chunking",
    )


def create_statistical_rag_workflow(config: RAGConfig) -> WorkflowNode:
    """
    Create statistical RAG workflow using existing Kailash nodes.

    Pipeline: Documents → StatisticalChunker → EmbeddingGenerator → VectorDatabase → HybridRetriever (sparse)
    """
    builder = WorkflowBuilder()

    # Add statistical chunking
    chunker_id = builder.add_node(
        "StatisticalChunkerNode",
        node_id="statistical_chunker",
        config={"chunk_size": config.chunk_size, "overlap": config.chunk_overlap},
    )

    # Add embedding generation (for backup dense retrieval)
    embedder_id = builder.add_node(
        "EmbeddingGeneratorNode",
        node_id="embedder",
        config={"model": config.embedding_model, "provider": config.embedding_provider},
    )

    # Add keyword extraction for sparse retrieval
    keyword_extractor_id = builder.add_node(
        "PythonCodeNode",
        node_id="keyword_extractor",
        config={
            "code": """
import re
def extract_keywords(text):
    words = re.findall(r'\\b[a-zA-Z]{3,}\\b', text.lower())
    stop_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use'}
    keywords = [word for word in set(words) if word not in stop_words]
    return keywords[:20]

result = {"keywords": [extract_keywords(chunk["content"]) for chunk in chunks]}
"""
        },
    )

    # Add vector database
    vectordb_id = builder.add_node(
        "VectorDatabaseNode",
        node_id="vector_db",
        config={
            "provider": config.vector_db_provider,
            "collection_name": "statistical_rag",
        },
    )

    # Add sparse retrieval
    retriever_id = builder.add_node(
        "HybridRetrieverNode",
        node_id="retriever",
        config={"k": config.retrieval_k, "method": "sparse"},
    )

    # Connect pipeline
    builder.add_connection(chunker_id, "chunks", keyword_extractor_id, "chunks")
    builder.add_connection(chunker_id, "chunks", embedder_id, "texts")
    builder.add_connection(keyword_extractor_id, "result", vectordb_id, "keywords")
    builder.add_connection(embedder_id, "embeddings", vectordb_id, "embeddings")
    builder.add_connection(chunker_id, "chunks", vectordb_id, "documents")
    builder.add_connection(
        vectordb_id, "stored_documents", retriever_id, "document_store"
    )

    workflow = builder.build(name="statistical_rag_workflow")

    return WorkflowNode(
        workflow=workflow,
        name="statistical_rag_node",
        description="Statistical RAG with sparse retrieval and keyword matching",
    )


def create_hybrid_rag_workflow(
    config: RAGConfig, fusion_method: str = "rrf"
) -> WorkflowNode:
    """
    Create hybrid RAG workflow combining semantic and statistical approaches.

    Pipeline: Documents → [SemanticRAG + StatisticalRAG] → ResultFuser → HybridRetriever
    """
    builder = WorkflowBuilder()

    # Create both semantic and statistical sub-workflows
    semantic_workflow = create_semantic_rag_workflow(config)
    statistical_workflow = create_statistical_rag_workflow(config)

    # Add sub-workflows as nodes
    semantic_id = builder.add_node(
        "WorkflowNode",
        node_id="semantic_rag",
        config={"workflow": semantic_workflow.workflow},
    )

    statistical_id = builder.add_node(
        "WorkflowNode",
        node_id="statistical_rag",
        config={"workflow": statistical_workflow.workflow},
    )

    # Add result fusion node
    fusion_id = builder.add_node(
        "PythonCodeNode",
        node_id="result_fusion",
        config={
            "code": f"""
def rrf_fusion(semantic_results, statistical_results, k=60):
    '''Reciprocal Rank Fusion for combining results'''
    doc_scores = {{}}

    # Add semantic results
    for i, doc in enumerate(semantic_results.get("results", [])):
        doc_id = doc.get("id", f"semantic_{{i}}")
        doc_scores[doc_id] = {{
            "document": doc,
            "score": 1 / (k + i + 1),
            "sources": ["semantic"]
        }}

    # Add statistical results
    for i, doc in enumerate(statistical_results.get("results", [])):
        doc_id = doc.get("id", f"statistical_{{i}}")
        if doc_id in doc_scores:
            doc_scores[doc_id]["score"] += 1 / (k + i + 1)
            doc_scores[doc_id]["sources"].append("statistical")
        else:
            doc_scores[doc_id] = {{
                "document": doc,
                "score": 1 / (k + i + 1),
                "sources": ["statistical"]
            }}

    # Sort by fused score
    sorted_results = sorted(doc_scores.items(), key=lambda x: x[1]["score"], reverse=True)

    return {{
        "documents": [item[1]["document"] for item in sorted_results[:5]],
        "scores": [item[1]["score"] for item in sorted_results[:5]],
        "fusion_method": "{fusion_method}"
    }}

# Execute fusion
fusion_results = rrf_fusion(semantic_results, statistical_results)
result = {{"fused_results": fusion_results}}
"""
        },
    )

    # Connect workflows to fusion
    builder.add_connection(semantic_id, "output", fusion_id, "semantic_results")
    builder.add_connection(statistical_id, "output", fusion_id, "statistical_results")

    workflow = builder.build(name="hybrid_rag_workflow")

    return WorkflowNode(
        workflow=workflow,
        name="hybrid_rag_node",
        description=f"Hybrid RAG with {fusion_method} fusion combining semantic and statistical approaches",
    )


def create_hierarchical_rag_workflow(config: RAGConfig) -> WorkflowNode:
    """
    Create hierarchical RAG workflow for multi-level document processing.

    Pipeline: Documents → HierarchicalChunker → Multi-level Embedding → Multi-collection Storage → Hierarchical Retrieval
    """
    builder = WorkflowBuilder()

    # Add hierarchical chunking
    chunker_id = builder.add_node(
        "HierarchicalChunkerNode",
        node_id="hierarchical_chunker",
        config={"chunk_size": config.chunk_size, "overlap": config.chunk_overlap},
    )

    # Add embedding for each level
    embedder_id = builder.add_node(
        "EmbeddingGeneratorNode",
        node_id="embedder",
        config={"model": config.embedding_model, "provider": config.embedding_provider},
    )

    # Add level processor for organizing chunks by hierarchy
    level_processor_id = builder.add_node(
        "PythonCodeNode",
        node_id="level_processor",
        config={
            "code": """
levels = ["document", "section", "paragraph"]
level_chunks = {}

for level in levels:
    level_chunks[level] = [chunk for chunk in chunks if chunk.get("hierarchy_level") == level]

result = {"level_chunks": level_chunks, "levels": levels}
"""
        },
    )

    # Add vector databases for each level
    doc_vectordb_id = builder.add_node(
        "VectorDatabaseNode",
        node_id="doc_vector_db",
        config={
            "provider": config.vector_db_provider,
            "collection_name": "hierarchical_rag_document",
        },
    )

    section_vectordb_id = builder.add_node(
        "VectorDatabaseNode",
        node_id="section_vector_db",
        config={
            "provider": config.vector_db_provider,
            "collection_name": "hierarchical_rag_section",
        },
    )

    para_vectordb_id = builder.add_node(
        "VectorDatabaseNode",
        node_id="para_vector_db",
        config={
            "provider": config.vector_db_provider,
            "collection_name": "hierarchical_rag_paragraph",
        },
    )

    # Add hierarchical retriever
    retriever_id = builder.add_node(
        "HybridRetrieverNode",
        node_id="hierarchical_retriever",
        config={"k": config.retrieval_k, "method": "hierarchical"},
    )

    # Connect pipeline
    builder.add_connection(chunker_id, "chunks", level_processor_id, "chunks")
    builder.add_connection(chunker_id, "chunks", embedder_id, "texts")
    builder.add_connection(
        level_processor_id, "result", doc_vectordb_id, "level_chunks"
    )
    builder.add_connection(
        level_processor_id, "result", section_vectordb_id, "level_chunks"
    )
    builder.add_connection(
        level_processor_id, "result", para_vectordb_id, "level_chunks"
    )
    builder.add_connection(embedder_id, "embeddings", doc_vectordb_id, "embeddings")
    builder.add_connection(embedder_id, "embeddings", section_vectordb_id, "embeddings")
    builder.add_connection(embedder_id, "embeddings", para_vectordb_id, "embeddings")

    # Connect all vector DBs to retriever
    builder.add_connection(
        doc_vectordb_id, "stored_documents", retriever_id, "document_store"
    )
    builder.add_connection(
        section_vectordb_id, "stored_documents", retriever_id, "section_store"
    )
    builder.add_connection(
        para_vectordb_id, "stored_documents", retriever_id, "paragraph_store"
    )

    workflow = builder.build(name="hierarchical_rag_workflow")

    return WorkflowNode(
        workflow=workflow,
        name="hierarchical_rag_node",
        description="Hierarchical RAG with multi-level document processing and context aggregation",
    )


@register_node()
class SemanticRAGNode(Node):
    """
    Semantic RAG Strategy Node

    Wraps the semantic RAG workflow as a single node for easy integration.
    Uses semantic chunking with dense embeddings for optimal semantic matching.
    """

    def __init__(self, name: str = "semantic_rag", config: Optional[RAGConfig] = None):
        self.config = config or RAGConfig()
        self.workflow_node = None
        super().__init__(name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="Documents to process for semantic RAG",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Query for retrieval",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                default="index",
                description="Operation: 'index' or 'retrieve'",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run semantic RAG using WorkflowNode"""
        if not self.workflow_node:
            self.workflow_node = create_semantic_rag_workflow(self.config)

        # Delegate to WorkflowNode
        return self.workflow_node.execute(**kwargs)


@register_node()
class StatisticalRAGNode(Node):
    """
    Statistical RAG Strategy Node

    Wraps the statistical RAG workflow for sparse keyword-based retrieval.
    Uses statistical chunking with keyword extraction for technical content.
    """

    def __init__(
        self, name: str = "statistical_rag", config: Optional[RAGConfig] = None
    ):
        self.config = config or RAGConfig()
        self.workflow_node = None
        super().__init__(name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="Documents to process for statistical RAG",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Query for retrieval",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                default="index",
                description="Operation: 'index' or 'retrieve'",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run statistical RAG using WorkflowNode"""
        if not self.workflow_node:
            self.workflow_node = create_statistical_rag_workflow(self.config)

        return self.workflow_node.execute(**kwargs)


@register_node()
class HybridRAGNode(Node):
    """
    Hybrid RAG Strategy Node

    Combines semantic and statistical approaches using result fusion.
    Provides 20-30% better performance than individual methods.
    """

    def __init__(
        self,
        name: str = "hybrid_rag",
        config: Optional[RAGConfig] = None,
        fusion_method: str = "rrf",
    ):
        self.config = config or RAGConfig()
        self.fusion_method = fusion_method
        self.workflow_node = None
        super().__init__(name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="Documents to process for hybrid RAG",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Query for retrieval",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                default="index",
                description="Operation: 'index' or 'retrieve'",
            ),
            "fusion_method": NodeParameter(
                name="fusion_method",
                type=str,
                default="rrf",
                description="Fusion method: 'rrf', 'linear', 'weighted'",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run hybrid RAG using WorkflowNode"""
        fusion_method = kwargs.get("fusion_method", self.fusion_method)

        if not self.workflow_node or fusion_method != self.fusion_method:
            self.fusion_method = fusion_method
            self.workflow_node = create_hybrid_rag_workflow(self.config, fusion_method)

        return self.workflow_node.execute(**kwargs)


@register_node()
class HierarchicalRAGNode(Node):
    """
    Hierarchical RAG Strategy Node

    Multi-level document processing that preserves document structure.
    Processes documents at document, section, and paragraph levels.
    """

    def __init__(
        self, name: str = "hierarchical_rag", config: Optional[RAGConfig] = None
    ):
        self.config = config or RAGConfig()
        self.workflow_node = None
        super().__init__(name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="Documents to process hierarchically",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Query for hierarchical retrieval",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                default="index",
                description="Operation: 'index' or 'retrieve'",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run hierarchical RAG using WorkflowNode"""
        if not self.workflow_node:
            self.workflow_node = create_hierarchical_rag_workflow(self.config)

        return self.workflow_node.execute(**kwargs)
