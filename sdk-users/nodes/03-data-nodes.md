# Data I/O Nodes

**Module**: `kailash.nodes.data`
**Last Updated**: 2025-01-06

This document covers all data input/output nodes including file operations, databases, streaming, SharePoint integration, and RAG components.

## Table of Contents
- [File I/O Nodes](#file-io-nodes)
- [Database Nodes](#database-nodes)
- [Streaming Nodes](#streaming-nodes)
- [Vector Database Nodes](#vector-database-nodes)
- [Source Management Nodes](#source-management-nodes)
- [Retrieval Nodes](#retrieval-nodes)
- [SharePoint Integration Nodes](#sharepoint-integration-nodes)

## File I/O Nodes

### CSVReaderNode
- **Module**: `kailash.nodes.data.readers`
- **Purpose**: Read CSV files
- **Parameters**:
  - `file_path`: Path to CSV file
  - `delimiter`: Column delimiter
  - `encoding`: File encoding

### CSVWriterNode
- **Module**: `kailash.nodes.data.writers`
- **Purpose**: Write CSV files
- **Parameters**:
  - `file_path`: Output file path
  - `data`: Data to write
  - `headers`: Column headers

### JSONReaderNode
- **Module**: `kailash.nodes.data.readers`
- **Purpose**: Read JSON files
- **Parameters**:
  - `file_path`: Path to JSON file
  - `encoding`: File encoding

### JSONWriterNode
- **Module**: `kailash.nodes.data.writers`
- **Purpose**: Write JSON files
- **Parameters**:
  - `file_path`: Output file path
  - `data`: Data to write
  - `indent`: JSON indentation

### TextReaderNode
- **Module**: `kailash.nodes.data.readers`
- **Purpose**: Read text files
- **Parameters**:
  - `file_path`: Path to text file
  - `encoding`: File encoding

### DocumentProcessorNode ⭐ **NEW**
- **Module**: `kailash.nodes.data.readers`
- **Purpose**: Advanced document processor for multiple formats with automatic format detection and metadata extraction
- **Key Features**:
  - Automatic format detection (PDF, DOCX, MD, HTML, RTF, TXT)
  - Rich metadata extraction (title, author, dates, structure)
  - Structure preservation (sections, headings, pages)
  - Unified output format across all document types
  - Encoding detection and handling
  - Comprehensive error handling with fallbacks
- **Supported Formats**:
  - **PDF**: Text extraction with page information
  - **DOCX**: Content and document properties
  - **Markdown**: Structure parsing with heading detection
  - **HTML**: Clean text extraction with structure
  - **RTF**: Rich text format processing
  - **TXT**: Plain text with encoding detection
- **Parameters**:
  - `file_path`: Path to document file (required)
  - `extract_metadata`: Extract document metadata (default: True)
  - `preserve_structure`: Maintain document structure (default: True)
  - `encoding`: Text encoding for plain text files (default: "utf-8")
  - `page_numbers`: Include page/section numbers (default: True)
  - `extract_images`: Extract image references (default: False)
- **Best For**:
  - Document management systems
  - RAG pipelines requiring document analysis
  - Content migration and processing
  - Multi-format document workflows
  - Metadata-driven applications
- **Example**:
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  processor = DocumentProcessorNode(
      extract_metadata=True,
      preserve_structure=True
  )
  result = processor.run(file_path="report.pdf")

  content = result["content"]           # Extracted text
  metadata = result["metadata"]         # Document properties
  sections = result["sections"]         # Structural elements
  doc_format = result["document_format"] # Detected format

  ```
- **Output Structure**:
  ```python
  {
      "content": "Full document text",
      "metadata": {
          "title": "Document Title",
          "author": "Author Name",
          "creation_date": "2024-01-01",
          "word_count": 1500,
          "character_count": 8500,
          "document_format": "pdf"
      },
      "sections": [
          {
              "type": "heading",
              "level": 1,
              "title": "Chapter 1",
              "content": "Chapter content...",
              "start_position": 0,
              "end_position": 100
          }
      ],
      "document_format": "pdf"
  }

  ```

### TextWriterNode
- **Module**: `kailash.nodes.data.writers`
- **Purpose**: Write text files
- **Parameters**:
  - `file_path`: Output file path
  - `content`: Text content

## Database Nodes

### SQLDatabaseNode
- **Module**: `kailash.nodes.data.sql`
- **Purpose**: Execute SQL queries
- **Parameters**:
  - `connection_string`: Database connection
  - `query`: SQL query
  - `parameters`: Query parameters

### SQLQueryBuilderNode
- **Module**: `kailash.nodes.data.sql`
- **Purpose**: Build SQL queries programmatically
- **Parameters**:
  - `table`: Table name
  - `operation`: SELECT, INSERT, UPDATE, DELETE
  - `conditions`: WHERE conditions

## Streaming Nodes

### EventStreamNode
- **Module**: `kailash.nodes.data.streaming`
- **Purpose**: Handle event streams
- **Parameters**:
  - `stream_url`: Stream endpoint
  - `event_types`: Events to handle

### KafkaConsumerNode
- **Module**: `kailash.nodes.data.streaming`
- **Purpose**: Consume Kafka messages
- **Parameters**:
  - `bootstrap_servers`: Kafka servers
  - `topic`: Topic to consume
  - `group_id`: Consumer group ID

### StreamPublisherNode
- **Module**: `kailash.nodes.data.streaming`
- **Purpose**: Publish to streams
- **Parameters**:
  - `stream_url`: Stream endpoint
  - `data`: Data to publish

### WebSocketNode
- **Module**: `kailash.nodes.data.streaming`
- **Purpose**: WebSocket connections
- **Parameters**:
  - `ws_url`: WebSocket URL
  - `on_message`: Message handler

## Vector Database Nodes

### EmbeddingNode
- **Module**: `kailash.nodes.data.vector_db`
- **Purpose**: Manage embeddings for vector databases
- **Parameters**:
  - `embedding_model`: Model to use
  - `vector_store`: Storage backend

### TextSplitterNode
- **Module**: `kailash.nodes.data.vector_db`
- **Purpose**: Split text into chunks
- **Parameters**:
  - `chunk_size`: Size of chunks
  - `chunk_overlap`: Overlap between chunks
  - `separator`: Split separator

### VectorDatabaseNode
- **Module**: `kailash.nodes.data.vector_db`
- **Purpose**: Vector database operations
- **Parameters**:
  - `db_type`: Database type (pinecone, weaviate, etc.)
  - `connection_params`: Connection parameters

## Source Management Nodes

### DocumentSourceNode
- **Module**: `kailash.nodes.data.sources`
- **Purpose**: Manage document sources
- **Parameters**:
  - `source_path`: Document location
  - `metadata`: Document metadata

### QuerySourceNode
- **Module**: `kailash.nodes.data.sources`
- **Purpose**: Manage query sources
- **Parameters**:
  - `query_template`: Query template
  - `parameters`: Query parameters

## Retrieval Nodes

### HybridRetrieverNode ⭐ **NEW**
- **Module**: `kailash.nodes.data.retrieval`
- **Purpose**: State-of-the-art hybrid retrieval combining dense and sparse methods
- **Key Features**: Combines semantic (dense) and keyword (sparse) retrieval for 20-30% better performance
- **Parameters**:
  - `fusion_strategy`: Fusion method - "rrf", "linear", or "weighted" (default: "rrf")
  - `dense_weight`: Weight for dense retrieval (0.0-1.0, default: 0.6)
  - `sparse_weight`: Weight for sparse retrieval (0.0-1.0, default: 0.4)
  - `top_k`: Number of results to return (default: 5)
  - `rrf_k`: RRF parameter for rank fusion (default: 60)
- **Best For**: Production RAG systems, enterprise search, multi-modal retrieval
- **Example**:
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  retriever = HybridRetrieverNode(fusion_strategy="rrf", top_k=5)
  result = retriever.run(
      query="machine learning algorithms",
      dense_results=vector_search_results,  # From semantic search
      sparse_results=keyword_search_results  # From BM25/keyword search
  )
  hybrid_results = result["hybrid_results"]  # Best of both methods

  ```

### RelevanceScorerNode
- **Module**: `kailash.nodes.data.retrieval`
- **Purpose**: Score document relevance with advanced ranking
- **Parameters**:
  - `similarity_method`: Scoring method - "cosine", "dot", "euclidean" (default: "cosine")
  - `top_k`: Number of top results to return (default: 5)
- **Enhanced Features**: Works with embeddings for precise relevance scoring
- **Example**:
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  scorer = RelevanceScorerNode(similarity_method="cosine", top_k=3)
  result = scorer.run(
      chunks=retrieved_chunks,
      query_embedding=query_embeddings,
      chunk_embeddings=chunk_embeddings
  )
  relevant_chunks = result["relevant_chunks"]  # Top ranked results

  ```

## SharePoint Integration Nodes

### SharePointGraphReader
- **Module**: `kailash.nodes.data.sharepoint_graph`
- **Purpose**: Read files from SharePoint using Microsoft Graph API
- **Parameters**:
  - `tenant_id`: Azure AD tenant ID
  - `client_id`: Azure AD app client ID
  - `client_secret`: Azure AD app client secret
  - `site_url`: SharePoint site URL
  - `operation`: Operation type (list_files, download_file)
  - `library_name`: Document library name
- **Example**:
  ```python
  sharepoint = SharePointGraphReader()
  result = sharepoint.run(
      tenant_id=os.getenv("SHAREPOINT_TENANT_ID"),
      client_id=os.getenv("SHAREPOINT_CLIENT_ID"),
      client_secret=os.getenv("SHAREPOINT_CLIENT_SECRET"),
      site_url="https://company.sharepoint.com/sites/YourSite",
      operation="list_files",
      library_name="Documents"
  )

  ```

### SharePointGraphWriter
- **Module**: `kailash.nodes.data.sharepoint_graph`
- **Purpose**: Upload files to SharePoint using Microsoft Graph API
- **Parameters**: Same authentication parameters plus:
  - `file_path`: Destination file path
  - `content`: File content to upload

## See Also
- [Transform Nodes](06-transform-nodes.md) - Data transformation and processing
- [AI Nodes](02-ai-nodes.md) - AI and ML capabilities
- [API Reference](../api/05-nodes-data.yaml) - Detailed API documentation
