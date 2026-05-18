"""DataFlow specialized nodes."""

try:
    from .aggregate_operations import AggregateNode
    from .file_source import FileSourceNode
    from .mongodb_nodes import BulkDocumentInsertNode
    from .mongodb_nodes import CreateIndexNode as MongoCreateIndexNode
    from .mongodb_nodes import (
        DocumentCountNode,
        DocumentDeleteNode,
        DocumentFindNode,
        DocumentInsertNode,
        DocumentUpdateNode,
        MongoAggregateNode,
    )
    from .natural_language_filter import NaturalLanguageFilterNode
    from .schema_nodes import MigrationNode, SchemaModificationNode
    from .smart_operations import SmartMergeNode
    from .transaction_nodes import (
        TransactionCommitNode,
        TransactionRollbackNode,
        TransactionRollbackToSavepointNode,
        TransactionSavepointNode,
        TransactionScopeNode,
    )
    from .vector_nodes import (
        CreateVectorIndexNode,
        HybridSearchNode,
        PgVectorHybridSearchNode,
        VectorSearchNode,
    )
    from .workflow_connection_manager import (
        DataFlowConnectionManager,
        SmartNodeConnectionMixin,
    )
except ImportError:
    # kailash 3.x removed Python Node base class; nodes not available in this environment
    pass

__all__ = [
    "TransactionScopeNode",
    "TransactionCommitNode",
    "TransactionRollbackNode",
    "TransactionSavepointNode",
    "TransactionRollbackToSavepointNode",
    "SchemaModificationNode",
    "MigrationNode",
    "DataFlowConnectionManager",
    "SmartNodeConnectionMixin",
    "SmartMergeNode",
    "AggregateNode",
    "NaturalLanguageFilterNode",
    "VectorSearchNode",
    "CreateVectorIndexNode",
    "PgVectorHybridSearchNode",
    "HybridSearchNode",  # deprecation alias for PgVectorHybridSearchNode (issue #891)
    # MongoDB nodes
    "DocumentInsertNode",
    "DocumentFindNode",
    "DocumentUpdateNode",
    "DocumentDeleteNode",
    "MongoAggregateNode",
    "BulkDocumentInsertNode",
    "MongoCreateIndexNode",
    "DocumentCountNode",
    # File ingestion
    "FileSourceNode",
]
