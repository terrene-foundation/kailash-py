"""Federated RAG Advanced Example."""

from .workflow import (
    ConsistencyCheckerAgent,
    DistributedRetrieverAgent,
    FederatedRAGConfig,
    FinalAggregatorAgent,
    ResultMergerAgent,
    SourceCoordinatorAgent,
    federated_rag_workflow,
)

__all__ = [
    "FederatedRAGConfig",
    "SourceCoordinatorAgent",
    "DistributedRetrieverAgent",
    "ResultMergerAgent",
    "ConsistencyCheckerAgent",
    "FinalAggregatorAgent",
    "federated_rag_workflow",
]
