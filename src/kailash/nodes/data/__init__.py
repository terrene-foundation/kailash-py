"""Data processing nodes for the Kailash SDK.

This package provides comprehensive data input/output nodes that serve as the
primary interface between the Kailash workflow system and external data sources.
These nodes form the foundation of most workflows by enabling data ingestion,
persistence, and real-time processing.

Module Organization:
- readers.py: Data source nodes for reading files
- writers.py: Data sink nodes for writing files
- sql.py: SQL database interaction nodes
- vector_db.py: Vector database and embedding nodes
- streaming.py: Real-time streaming data nodes

Design Philosophy:
1. Consistent interfaces across data sources
2. Type-safe parameter validation
3. Memory-efficient processing
4. Comprehensive error handling
5. Format-specific optimizations
6. Real-time and batch processing support

Node Categories:
- Readers: Bring external data into workflows
- Writers: Persist processed data to files
- SQL: Interact with relational databases
- Vector DB: Handle embeddings and similarity search
- Streaming: Process real-time data streams

Usage Patterns:
1. ETL pipelines: Read → Transform → Write
2. Data processing: Read → Analyze → Export
3. RAG pipelines: Text → Embed → Store → Search
4. Real-time analytics: Stream → Process → Aggregate
5. Database operations: Query → Transform → Insert

Integration Points:
- Upstream: File systems, APIs, databases, streams
- Downstream: Transform nodes, AI models, analytics
- Parallel: Other data nodes in workflow

Advanced Features:
- Connection pooling for databases
- Batch processing for efficiency
- Real-time streaming support
- Vector similarity search
- Event-driven architectures

Error Handling:
All nodes provide detailed error messages for:
- Connection failures
- Authentication errors
- Format/schema issues
- Rate limiting
- Resource constraints

Example Workflows:
    # Traditional ETL
    workflow = Workflow()
    workflow.add_node('read', CSVReader(file_path='input.csv'))
    workflow.add_node('transform', DataTransform())
    workflow.add_node('write', JSONWriter(file_path='output.json'))
    workflow.connect('read', 'transform')
    workflow.connect('transform', 'write')

    # RAG Pipeline
    workflow = Workflow()
    workflow.add_node('split', TextSplitterNode())
    workflow.add_node('embed', EmbeddingNode())
    workflow.add_node('store', VectorDatabaseNode())
    workflow.connect('split', 'embed')
    workflow.connect('embed', 'store')

    # Real-time Processing
    workflow = Workflow()
    workflow.add_node('consume', KafkaConsumerNode())
    workflow.add_node('process', StreamProcessor())
    workflow.add_node('publish', StreamPublisherNode())
    workflow.connect('consume', 'process')
    workflow.connect('process', 'publish')
"""

from kailash.nodes.data.readers import CSVReader, JSONReader, TextReader
from kailash.nodes.data.retrieval import RelevanceScorerNode
from kailash.nodes.data.sharepoint_graph import (
    SharePointGraphReader,
    SharePointGraphWriter,
)
from kailash.nodes.data.sources import DocumentSourceNode, QuerySourceNode
from kailash.nodes.data.sql import SQLDatabaseNode, SQLQueryBuilderNode
from kailash.nodes.data.streaming import (
    EventStreamNode,
    KafkaConsumerNode,
    StreamPublisherNode,
    WebSocketNode,
)
from kailash.nodes.data.vector_db import (
    EmbeddingNode,
    TextSplitterNode,
    VectorDatabaseNode,
)
from kailash.nodes.data.writers import CSVWriter, JSONWriter, TextWriter

__all__ = [
    # Readers
    "CSVReader",
    "JSONReader",
    "TextReader",
    "SharePointGraphReader",
    # Writers
    "CSVWriter",
    "JSONWriter",
    "TextWriter",
    "SharePointGraphWriter",
    # Sources
    "DocumentSourceNode",
    "QuerySourceNode",
    # Retrieval
    "RelevanceScorerNode",
    # SQL
    "SQLDatabaseNode",
    "SQLQueryBuilderNode",
    # Vector DB
    "EmbeddingNode",
    "VectorDatabaseNode",
    "TextSplitterNode",
    # Streaming
    "KafkaConsumerNode",
    "StreamPublisherNode",
    "WebSocketNode",
    "EventStreamNode",
]
