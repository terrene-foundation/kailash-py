"""
Agentic RAG Advanced Example

This example demonstrates adaptive retrieval-augmented generation using multi-agent coordination.

Agents:
1. QueryAnalyzerAgent - Analyzes query intent, complexity, and keywords
2. RetrievalStrategyAgent - Selects optimal retrieval strategy
3. DocumentRetrieverAgent - Retrieves documents using selected strategy
4. QualityAssessorAgent - Assesses retrieval quality and decides if refinement needed
5. AnswerGeneratorAgent - Generates final answer from retrieved documents

Use Cases:
- Adaptive RAG with strategy selection
- Multi-strategy retrieval (semantic, keyword, hybrid)
- Quality-driven iterative refinement
- Complex question answering

Architecture Pattern: Iterative Pipeline with Quality Feedback
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# ===== Configuration =====


@dataclass
class AgenticRAGConfig:
    """Configuration for agentic RAG workflow."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    max_iterations: int = 3
    retrieval_strategy: str = "auto"  # "auto", "semantic", "keyword", "hybrid"
    top_k: int = 5
    quality_threshold: float = 0.7
    adaptive_retrieval: bool = True


# ===== Signatures =====


class QueryAnalysisSignature(Signature):
    """Signature for query analysis."""

    query: str = InputField(description="User query to analyze")

    query_type: str = OutputField(
        description="Query type (factual, analytical, procedural)"
    )
    complexity: str = OutputField(description="Complexity level (low, medium, high)")
    keywords: str = OutputField(description="Extracted keywords as JSON")


class StrategySelectionSignature(Signature):
    """Signature for retrieval strategy selection."""

    query_analysis: str = InputField(description="Query analysis as JSON")

    strategy: str = OutputField(
        description="Selected retrieval strategy (semantic, keyword, hybrid)"
    )
    reasoning: str = OutputField(description="Reasoning for strategy selection")


class DocumentRetrievalSignature(Signature):
    """Signature for document retrieval."""

    query: str = InputField(description="Search query")
    strategy: str = InputField(description="Retrieval strategy to use")

    documents: str = OutputField(description="Retrieved documents as JSON")
    retrieval_metadata: str = OutputField(description="Retrieval metadata as JSON")


class QualityAssessmentSignature(Signature):
    """Signature for quality assessment."""

    query: str = InputField(description="Original query")
    documents: str = InputField(description="Retrieved documents as JSON")

    quality_score: str = OutputField(description="Quality score (0-1)")
    needs_refinement: str = OutputField(
        description="Whether refinement is needed (true/false)"
    )
    feedback: str = OutputField(description="Feedback for improvement")


class AnswerGenerationSignature(Signature):
    """Signature for answer generation."""

    query: str = InputField(description="User query")
    documents: str = InputField(description="Retrieved documents as JSON")

    answer: str = OutputField(description="Generated answer")
    sources: str = OutputField(description="Source citations as JSON")


# ===== Agents =====


class QueryAnalyzerAgent(BaseAgent):
    """Agent for analyzing query intent and complexity."""

    def __init__(
        self,
        config: AgenticRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "analyzer",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=QueryAnalysisSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.rag_config = config

    def analyze(self, query: str) -> Dict[str, Any]:
        """Analyze query intent and complexity."""
        # Run agent
        result = self.run(query=query)

        # Extract outputs
        query_type = result.get("query_type", "factual")
        complexity = result.get("complexity", "medium")

        keywords_raw = result.get("keywords", "[]")
        if isinstance(keywords_raw, str):
            try:
                keywords = json.loads(keywords_raw) if keywords_raw else []
            except:
                keywords = [keywords_raw]
        else:
            keywords = keywords_raw if isinstance(keywords_raw, list) else []

        analysis_result = {
            "query_type": query_type,
            "complexity": complexity,
            "keywords": keywords,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=analysis_result,  # Auto-serialized
            tags=["query_analysis", "rag_pipeline"],
            importance=0.9,
            segment="rag_pipeline",
        )

        return analysis_result


class RetrievalStrategyAgent(BaseAgent):
    """Agent for selecting optimal retrieval strategy."""

    def __init__(
        self,
        config: AgenticRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "strategy",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=StrategySelectionSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.rag_config = config

    def select_strategy(self, query_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Select optimal retrieval strategy based on query analysis."""
        # Run agent
        result = self.run(query_analysis=json.dumps(query_analysis))

        # Extract outputs
        strategy_raw = result.get("strategy", self.rag_config.retrieval_strategy)
        valid_strategies = ["semantic", "keyword", "hybrid"]
        strategy = strategy_raw if strategy_raw in valid_strategies else "semantic"

        reasoning = result.get("reasoning", "Default strategy selection")

        strategy_result = {"strategy": strategy, "reasoning": reasoning}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=strategy_result,  # Auto-serialized
            tags=["strategy_selection", "rag_pipeline"],
            importance=0.85,
            segment="rag_pipeline",
        )

        return strategy_result


class DocumentRetrieverAgent(BaseAgent):
    """Agent for retrieving documents using selected strategy."""

    def __init__(
        self,
        config: AgenticRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "retriever",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=DocumentRetrievalSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.rag_config = config

    def retrieve(self, query: str, strategy: str) -> Dict[str, Any]:
        """Retrieve documents using selected strategy."""
        # Run agent
        result = self.run(query=query, strategy=strategy)

        # Extract outputs
        documents_raw = result.get("documents", "[]")
        if isinstance(documents_raw, str):
            try:
                documents = json.loads(documents_raw) if documents_raw else []
            except:
                documents = [{"content": documents_raw}]
        else:
            documents = documents_raw if isinstance(documents_raw, list) else []

        metadata_raw = result.get("retrieval_metadata", "{}")
        if isinstance(metadata_raw, str):
            try:
                metadata = json.loads(metadata_raw) if metadata_raw else {}
            except:
                metadata = {"raw": metadata_raw}
        else:
            metadata = metadata_raw if isinstance(metadata_raw, dict) else {}

        retrieval_result = {
            "documents": documents[: self.rag_config.top_k],
            "retrieval_metadata": metadata,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=retrieval_result,  # Auto-serialized
            tags=["document_retrieval", "rag_pipeline"],
            importance=1.0,
            segment="rag_pipeline",
        )

        return retrieval_result


class QualityAssessorAgent(BaseAgent):
    """Agent for assessing retrieval quality."""

    def __init__(
        self,
        config: AgenticRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "assessor",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=QualityAssessmentSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.rag_config = config

    def assess(self, query: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess quality of retrieved documents."""
        # Run agent
        result = self.run(query=query, documents=json.dumps(documents))

        # Extract outputs
        quality_score_raw = result.get("quality_score", "0.7")
        try:
            quality_score = float(quality_score_raw)
        except:
            quality_score = 0.7

        needs_refinement_raw = result.get("needs_refinement", "false")
        needs_refinement = needs_refinement_raw.lower() in ["true", "yes", "1"]

        feedback = result.get("feedback", "Quality assessment complete")

        assessment_result = {
            "quality_score": quality_score,
            "needs_refinement": needs_refinement
            or quality_score < self.rag_config.quality_threshold,
            "feedback": feedback,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=assessment_result,  # Auto-serialized
            tags=["quality_assessment", "rag_pipeline"],
            importance=0.95,
            segment="rag_pipeline",
        )

        return assessment_result


class AnswerGeneratorAgent(BaseAgent):
    """Agent for generating final answer."""

    def __init__(
        self,
        config: AgenticRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "generator",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=AnswerGenerationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.rag_config = config

    def generate(self, query: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate answer from retrieved documents."""
        # Run agent
        result = self.run(query=query, documents=json.dumps(documents))

        # Extract outputs
        answer = result.get("answer", "No answer generated")

        sources_raw = result.get("sources", "[]")
        if isinstance(sources_raw, str):
            try:
                sources = json.loads(sources_raw) if sources_raw else []
            except:
                sources = [sources_raw]
        else:
            sources = sources_raw if isinstance(sources_raw, list) else []

        generation_result = {"answer": answer, "sources": sources}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=generation_result,  # Auto-serialized
            tags=["answer_generation", "rag_pipeline"],
            importance=1.0,
            segment="rag_pipeline",
        )

        return generation_result


# ===== Workflow Functions =====


def agentic_rag_workflow(
    query: str,
    config: Optional[AgenticRAGConfig] = None,
    documents_corpus: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Execute agentic RAG workflow with adaptive retrieval.

    Args:
        query: User query
        config: Configuration for agentic RAG
        documents_corpus: Optional document corpus (for testing)

    Returns:
        Complete RAG result with query analysis, retrieval, quality assessment, and answer
    """
    if config is None:
        config = AgenticRAGConfig()

    # Create shared memory pool
    shared_pool = SharedMemoryPool()

    # Create agents
    analyzer = QueryAnalyzerAgent(config, shared_pool, "analyzer")
    strategy_agent = RetrievalStrategyAgent(config, shared_pool, "strategy")
    retriever = DocumentRetrieverAgent(config, shared_pool, "retriever")
    assessor = QualityAssessorAgent(config, shared_pool, "assessor")
    generator = AnswerGeneratorAgent(config, shared_pool, "generator")

    # Stage 1: Analyze query
    query_analysis = analyzer.analyze(query)

    # Iterative retrieval with quality feedback
    iterations = 0
    best_documents = []
    best_quality = 0.0
    strategies_tried = []

    while iterations < config.max_iterations:
        # Stage 2: Select retrieval strategy
        strategy_result = strategy_agent.select_strategy(query_analysis)
        strategy = strategy_result["strategy"]

        # Avoid repeating same strategy
        if strategy in strategies_tried and config.adaptive_retrieval:
            # Try different strategy
            all_strategies = ["semantic", "keyword", "hybrid"]
            remaining = [s for s in all_strategies if s not in strategies_tried]
            if remaining:
                strategy = remaining[0]
            else:
                break

        strategies_tried.append(strategy)

        # Stage 3: Retrieve documents
        retrieval_result = retriever.retrieve(query, strategy)
        documents = retrieval_result["documents"]

        # Stage 4: Assess quality
        assessment = assessor.assess(query, documents)

        # Track best results
        if assessment["quality_score"] > best_quality:
            best_quality = assessment["quality_score"]
            best_documents = documents

        # Check if quality is sufficient
        if not assessment["needs_refinement"]:
            break

        iterations += 1

    # Stage 5: Generate answer using best documents
    answer_result = generator.generate(query, best_documents)

    return {
        "query": query,
        "query_analysis": query_analysis,
        "retrieval_strategy": strategy_result,
        "documents": best_documents,
        "quality_assessment": {
            "quality_score": best_quality,
            "iterations": iterations + 1,
            "strategies_tried": strategies_tried,
        },
        "answer": answer_result["answer"],
        "sources": answer_result["sources"],
        "iterations": iterations + 1,
    }


# ===== Main Entry Point =====

if __name__ == "__main__":
    # Example usage
    config = AgenticRAGConfig(llm_provider="mock")

    # Single query
    query = (
        "What are the key differences between transformers and RNNs in deep learning?"
    )

    print("=== Agentic RAG Query ===")
    result = agentic_rag_workflow(query, config)
    print(f"Query: {result['query']}")
    print(f"Query Type: {result['query_analysis']['query_type']}")
    print(f"Complexity: {result['query_analysis']['complexity']}")
    print(f"Strategy: {result['retrieval_strategy']['strategy']}")
    print(f"Documents Retrieved: {len(result['documents'])}")
    print(f"Quality Score: {result['quality_assessment']['quality_score']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Answer: {result['answer'][:100]}...")

    # Complex multi-hop query
    complex_query = "How do attention mechanisms in transformers differ from LSTM memory cells, and which is better for long-range dependencies?"

    print("\n=== Complex Multi-Hop Query ===")
    complex_result = agentic_rag_workflow(complex_query, config)
    print(f"Query Type: {complex_result['query_analysis']['query_type']}")
    print(f"Iterations: {complex_result['iterations']}")
    print(
        f"Strategies Tried: {complex_result['quality_assessment']['strategies_tried']}"
    )
    print(f"Final Quality: {complex_result['quality_assessment']['quality_score']}")
