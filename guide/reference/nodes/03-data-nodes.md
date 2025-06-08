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

### RelevanceScorerNode
- **Module**: `kailash.nodes.data.retrieval`
- **Purpose**: Score document relevance
- **Parameters**:
  - `query`: Search query
  - `documents`: Documents to score
  - `scoring_method`: Scoring algorithm

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
