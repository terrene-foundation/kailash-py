"""
Federated RAG Advanced Example

This example demonstrates federated retrieval in RAG using multi-agent coordination.

Agents:
1. SourceCoordinatorAgent - Coordinates retrieval across multiple sources
2. DistributedRetrieverAgent - Retrieves information from individual sources
3. ResultMergerAgent - Merges and deduplicates results from multiple sources
4. ConsistencyCheckerAgent - Checks consistency across sources
5. FinalAggregatorAgent - Aggregates final answer with source attribution

Use Cases:
- Multi-source information retrieval
- Distributed knowledge bases
- Cross-source consistency checking
- Source attribution and transparency

Architecture Pattern: Distributed Retrieval Pipeline with Consistency Checking
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# ===== Configuration =====


@dataclass
class FederatedRAGConfig:
    """Configuration for federated RAG workflow."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    max_sources: int = 5
    enable_deduplication: bool = True
    consistency_threshold: float = 0.7


# ===== Signatures =====


class SourceCoordinationSignature(Signature):
    """Signature for source coordination."""

    query: str = InputField(description="User query")
    available_sources: str = InputField(description="Available sources as JSON")

    selected_sources: str = OutputField(description="Selected sources as JSON")
    selection_reasoning: str = OutputField(description="Reasoning for source selection")


class DistributedRetrievalSignature(Signature):
    """Signature for distributed retrieval."""

    query: str = InputField(description="User query")
    source: str = InputField(description="Source to retrieve from as JSON")

    documents: str = OutputField(description="Retrieved documents as JSON")
    source_id: str = OutputField(description="Source identifier")


class ResultMergingSignature(Signature):
    """Signature for result merging."""

    retrieval_results: str = InputField(
        description="Retrieval results from all sources as JSON"
    )

    merged_documents: str = OutputField(description="Merged documents as JSON")
    deduplication_count: str = OutputField(description="Number of duplicates removed")


class ConsistencyCheckSignature(Signature):
    """Signature for consistency checking."""

    query: str = InputField(description="User query")
    merged_documents: str = InputField(description="Merged documents as JSON")

    consistency_score: str = OutputField(description="Consistency score (0-1)")
    conflicts: str = OutputField(description="Detected conflicts as JSON")


class FinalAggregationSignature(Signature):
    """Signature for final answer aggregation."""

    query: str = InputField(description="User query")
    merged_documents: str = InputField(description="Merged documents as JSON")
    consistency_result: str = InputField(description="Consistency check result as JSON")

    final_answer: str = OutputField(description="Final aggregated answer")
    source_attribution: str = OutputField(description="Source attribution as JSON")


# ===== Agents =====


class SourceCoordinatorAgent(BaseAgent):
    """Agent for coordinating source selection."""

    def __init__(
        self,
        config: FederatedRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "coordinator",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=SourceCoordinationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.federated_config = config

    def coordinate(
        self, query: str, available_sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Coordinate source selection for query."""
        # Run agent
        result = self.run(query=query, available_sources=json.dumps(available_sources))

        # Extract outputs
        selected_sources_raw = result.get("selected_sources", "[]")
        if isinstance(selected_sources_raw, str):
            try:
                selected_sources = (
                    json.loads(selected_sources_raw) if selected_sources_raw else []
                )
            except:
                selected_sources = available_sources[
                    : self.federated_config.max_sources
                ]
        else:
            selected_sources = (
                selected_sources_raw if isinstance(selected_sources_raw, list) else []
            )

        # Limit to max_sources
        selected_sources = selected_sources[: self.federated_config.max_sources]

        selection_reasoning = result.get(
            "selection_reasoning", "Sources selected based on relevance"
        )

        coordination_result = {
            "selected_sources": selected_sources,
            "selection_reasoning": selection_reasoning,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=coordination_result,  # Auto-serialized
            tags=["source_coordination", "federated_pipeline"],
            importance=0.9,
            segment="federated_pipeline",
        )

        return coordination_result


class DistributedRetrieverAgent(BaseAgent):
    """Agent for distributed retrieval from individual sources."""

    def __init__(
        self,
        config: FederatedRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "retriever",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=DistributedRetrievalSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.federated_config = config

    def retrieve(self, query: str, source: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieve information from specific source."""
        # Run agent
        result = self.run(query=query, source=json.dumps(source))

        # Extract outputs
        documents_raw = result.get("documents", "[]")
        if isinstance(documents_raw, str):
            try:
                documents = json.loads(documents_raw) if documents_raw else []
            except:
                documents = [
                    {"content": documents_raw, "source": source.get("id", "unknown")}
                ]
        else:
            documents = documents_raw if isinstance(documents_raw, list) else []

        source_id_raw = result.get("source_id", source.get("id", "unknown"))
        # Handle placeholder values from mock LLM
        if isinstance(source_id_raw, str) and (
            "placeholder" in source_id_raw.lower() or not source_id_raw
        ):
            source_id = source.get("id", "unknown")
        else:
            source_id = source_id_raw

        retrieval_result = {
            "source_id": source_id,
            "documents": documents,
            "query": query,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=retrieval_result,  # Auto-serialized
            tags=["distributed_retrieval", "federated_pipeline"],
            importance=0.85,
            segment="federated_pipeline",
        )

        return retrieval_result


class ResultMergerAgent(BaseAgent):
    """Agent for merging and deduplicating results."""

    def __init__(
        self,
        config: FederatedRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "merger",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=ResultMergingSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.federated_config = config

    def merge(self, retrieval_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge results from multiple sources."""
        # Run agent
        result = self.run(retrieval_results=json.dumps(retrieval_results))

        # Extract outputs
        merged_documents_raw = result.get("merged_documents", "[]")
        if isinstance(merged_documents_raw, str):
            try:
                merged_documents = (
                    json.loads(merged_documents_raw) if merged_documents_raw else []
                )
            except:
                # Fallback: merge manually
                merged_documents = []
                for retrieval in retrieval_results:
                    docs = retrieval.get("documents", [])
                    for doc in docs:
                        if isinstance(doc, dict):
                            merged_documents.append(doc)
        else:
            merged_documents = (
                merged_documents_raw if isinstance(merged_documents_raw, list) else []
            )

        deduplication_count_raw = result.get("deduplication_count", "0")
        try:
            deduplication_count = (
                int(deduplication_count_raw)
                if isinstance(deduplication_count_raw, str)
                else deduplication_count_raw
            )
        except:
            deduplication_count = 0

        merging_result = {
            "merged_documents": merged_documents,
            "deduplication_count": deduplication_count,
            "total_sources": len(retrieval_results),
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=merging_result,  # Auto-serialized
            tags=["result_merging", "federated_pipeline"],
            importance=0.9,
            segment="federated_pipeline",
        )

        return merging_result


class ConsistencyCheckerAgent(BaseAgent):
    """Agent for checking consistency across sources."""

    def __init__(
        self,
        config: FederatedRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "checker",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=ConsistencyCheckSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.federated_config = config

    def check(
        self, query: str, merged_documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Check consistency across sources."""
        # Run agent
        result = self.run(query=query, merged_documents=json.dumps(merged_documents))

        # Extract outputs
        consistency_score_raw = result.get("consistency_score", "0.8")
        try:
            consistency_score = (
                float(consistency_score_raw)
                if isinstance(consistency_score_raw, str)
                else consistency_score_raw
            )
        except:
            consistency_score = 0.8

        # UX Improvement: One-line extraction

        conflicts = self.extract_list(result, "conflicts", default=[])

        consistency_result = {
            "consistency_score": consistency_score,
            "conflicts": conflicts,
            "is_consistent": consistency_score
            >= self.federated_config.consistency_threshold,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=consistency_result,  # Auto-serialized
            tags=["consistency_check", "federated_pipeline"],
            importance=1.0,
            segment="federated_pipeline",
        )

        return consistency_result


class FinalAggregatorAgent(BaseAgent):
    """Agent for aggregating final answer with attribution."""

    def __init__(
        self,
        config: FederatedRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "aggregator",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=FinalAggregationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.federated_config = config

    def aggregate(
        self,
        query: str,
        merged_documents: List[Dict[str, Any]],
        consistency_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Aggregate final answer from merged documents."""
        # Run agent
        result = self.run(
            query=query,
            merged_documents=json.dumps(merged_documents),
            consistency_result=json.dumps(consistency_result),
        )

        # Extract outputs
        final_answer = result.get("final_answer", "No answer generated")

        source_attribution_raw = result.get("source_attribution", "[]")
        if isinstance(source_attribution_raw, str):
            try:
                source_attribution = (
                    json.loads(source_attribution_raw) if source_attribution_raw else []
                )
            except:
                # Fallback: extract sources from documents
                sources = set()
                for doc in merged_documents:
                    if isinstance(doc, dict) and "source" in doc:
                        sources.add(doc["source"])
                source_attribution = list(sources)
        else:
            source_attribution = (
                source_attribution_raw
                if isinstance(source_attribution_raw, list)
                else []
            )

        aggregation_result = {
            "final_answer": final_answer,
            "source_attribution": source_attribution,
            "consistency_score": consistency_result.get("consistency_score", 0.0),
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=aggregation_result,  # Auto-serialized
            tags=["final_aggregation", "federated_pipeline"],
            importance=1.0,
            segment="federated_pipeline",
        )

        return aggregation_result


# ===== Workflow Functions =====


def federated_rag_workflow(
    query: str,
    available_sources: List[Dict[str, Any]],
    config: Optional[FederatedRAGConfig] = None,
) -> Dict[str, Any]:
    """
    Execute federated RAG workflow with distributed retrieval.

    Args:
        query: User query
        available_sources: List of available sources to retrieve from
        config: Configuration for federated RAG

    Returns:
        Complete federated RAG result with distributed retrieval, merging, consistency checking, and final answer
    """
    if config is None:
        config = FederatedRAGConfig()

    # Create shared memory pool
    shared_pool = SharedMemoryPool()

    # Create agents
    coordinator = SourceCoordinatorAgent(config, shared_pool, "coordinator")
    retriever = DistributedRetrieverAgent(config, shared_pool, "retriever")
    merger = ResultMergerAgent(config, shared_pool, "merger")
    checker = ConsistencyCheckerAgent(config, shared_pool, "checker")
    aggregator = FinalAggregatorAgent(config, shared_pool, "aggregator")

    # Stage 1: Coordinate source selection
    coordination = coordinator.coordinate(query, available_sources)
    selected_sources = coordination["selected_sources"]

    # Stage 2: Distributed retrieval from each source
    retrieval_results = []
    for source in selected_sources:
        retrieval = retriever.retrieve(query, source)
        retrieval_results.append(retrieval)

    # Stage 3: Merge results from all sources
    merging = merger.merge(retrieval_results)
    merged_documents = merging["merged_documents"]

    # Stage 4: Check consistency across sources
    consistency = checker.check(query, merged_documents)

    # Stage 5: Aggregate final answer with attribution
    final_aggregation = aggregator.aggregate(query, merged_documents, consistency)

    return {
        "query": query,
        "selected_sources": selected_sources,
        "selection_reasoning": coordination["selection_reasoning"],
        "retrieval_results": retrieval_results,
        "merged_documents": merged_documents,
        "deduplication_count": merging["deduplication_count"],
        "consistency_score": consistency["consistency_score"],
        "conflicts": consistency["conflicts"],
        "is_consistent": consistency["is_consistent"],
        "final_answer": final_aggregation["final_answer"],
        "source_attribution": final_aggregation["source_attribution"],
    }


# ===== Main Entry Point =====

if __name__ == "__main__":
    # Example usage
    config = FederatedRAGConfig(llm_provider="mock")

    # Federated retrieval query
    query = "What are transformers in deep learning?"

    # Multiple sources
    available_sources = [
        {"id": "arxiv", "type": "papers", "description": "Academic papers"},
        {"id": "wikipedia", "type": "encyclopedia", "description": "General knowledge"},
        {
            "id": "docs",
            "type": "documentation",
            "description": "Technical documentation",
        },
    ]

    print("=== Federated RAG Query ===")
    result = federated_rag_workflow(query, available_sources, config)
    print(f"Query: {result['query']}")
    print(f"Selected Sources: {len(result['selected_sources'])}")
    for source in result["selected_sources"]:
        print(f"  - {source.get('id', 'unknown')} ({source.get('type', 'unknown')})")
    print(f"Retrieved Documents: {len(result['merged_documents'])}")
    print(f"Deduplication: {result['deduplication_count']} duplicates removed")
    print(f"Consistency Score: {result['consistency_score']}")
    print(f"Final Answer: {result['final_answer'][:100]}...")
    print(f"Sources: {result['source_attribution']}")

    # Another example with more sources
    query2 = "Compare transformers and RNNs for sequence processing"

    print("\n=== Federated RAG Query 2 ===")
    result2 = federated_rag_workflow(query2, available_sources, config)
    print(f"Query: {result2['query']}")
    print(f"Sources Selected: {len(result2['selected_sources'])}")
    print(f"Consistency Score: {result2['consistency_score']}")
    print(f"Conflicts Detected: {len(result2['conflicts'])}")
