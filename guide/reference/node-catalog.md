# Kailash Python SDK - Node Catalog

Last Updated: 2025-06-04

This comprehensive catalog documents all available nodes in the Kailash Python SDK, organized by category.

## Table of Contents
- [Base Classes](#base-classes)
- [AI Nodes](#ai-nodes)
- [API Nodes](#api-nodes)
- [Code Nodes](#code-nodes)
- [Data Nodes](#data-nodes)
- [Logic Nodes](#logic-nodes)
- [MCP Nodes](#mcp-nodes)
- [Transform Nodes](#transform-nodes)
- [Node Naming Issues](#node-naming-issues)

## Base Classes

### Node
- **Module**: `kailash.nodes.base`
- **Description**: Abstract base class for all synchronous nodes
- **Key Methods**:
  - `get_parameters()`: Define node parameters
  - `run(context, **kwargs)`: Execute node logic
  - `get_output_schema()`: Optional output validation

### AsyncNode
- **Module**: `kailash.nodes.base_async`
- **Description**: Abstract base class for all asynchronous nodes
- **Key Methods**:
  - `async run(context, **kwargs)`: Async execution

## AI Nodes

### EmbeddingGeneratorNode
- **Module**: `kailash.nodes.ai.embedding_generator`
- **Purpose**: Generate text embeddings using various models
- **Parameters**:
  - `text`: Input text to embed
  - `model`: Embedding model to use
  - `dimensions`: Output embedding dimensions
- **Example**:
  ```python
  node = EmbeddingGeneratorNode(
      config={"model": "text-embedding-ada-002"}
  )
  ```

### LLMAgentNode
- **Module**: `kailash.nodes.ai.llm_agent`
- **Purpose**: Interact with Large Language Models
- **Parameters**:
  - `prompt`: Input prompt
  - `model`: LLM model to use
  - `temperature`: Sampling temperature
  - `max_tokens`: Maximum response tokens
- **Example**:
  ```python
  node = LLMAgentNode(
      config={
          "model": "gpt-4",
          "temperature": 0.7,
          "max_tokens": 1000
      }
  )
  ```

### AI Model Nodes (Need Renaming)
- **TextClassifier** → Should be `TextClassifierNode`
- **TextEmbedder** → Should be `TextEmbedderNode`
- **SentimentAnalyzer** → Should be `SentimentAnalyzerNode`
- **NamedEntityRecognizer** → Should be `NamedEntityRecognizerNode`
- **ModelPredictor** → Should be `ModelPredictorNode`
- **TextSummarizer** → Should be `TextSummarizerNode`

### AI Agent Nodes (Need Renaming)
- **ChatAgent** → Should be `ChatAgentNode`
- **RetrievalAgent** → Should be `RetrievalAgentNode`
- **FunctionCallingAgent** → Should be `FunctionCallingAgentNode`
- **PlanningAgent** → Should be `PlanningAgentNode`

## API Nodes

### Authentication Nodes

#### APIKeyNode
- **Module**: `kailash.nodes.api.auth`
- **Purpose**: API key authentication
- **Parameters**:
  - `api_key`: API key value
  - `header_name`: Header field name

#### BasicAuthNode
- **Module**: `kailash.nodes.api.auth`
- **Purpose**: Basic HTTP authentication
- **Parameters**:
  - `username`: Username
  - `password`: Password

#### OAuth2Node
- **Module**: `kailash.nodes.api.auth`
- **Purpose**: OAuth2 authentication flow
- **Parameters**:
  - `client_id`: OAuth client ID
  - `client_secret`: OAuth client secret
  - `token_url`: Token endpoint URL

### HTTP Client Nodes

#### HTTPRequestNode
- **Module**: `kailash.nodes.api.http`
- **Purpose**: Make HTTP requests (synchronous)
- **Parameters**:
  - `url`: Target URL
  - `method`: HTTP method (GET, POST, etc.)
  - `headers`: Request headers
  - `body`: Request body
  - `timeout`: Request timeout

#### AsyncHTTPRequestNode
- **Module**: `kailash.nodes.api.http`
- **Purpose**: Make HTTP requests (asynchronous)
- **Parameters**: Same as HTTPRequestNode

### GraphQL Nodes

#### GraphQLClientNode
- **Module**: `kailash.nodes.api.graphql`
- **Purpose**: Execute GraphQL queries (synchronous)
- **Parameters**:
  - `endpoint`: GraphQL endpoint URL
  - `query`: GraphQL query string
  - `variables`: Query variables

#### AsyncGraphQLClientNode
- **Module**: `kailash.nodes.api.graphql`
- **Purpose**: Execute GraphQL queries (asynchronous)
- **Parameters**: Same as GraphQLClientNode

### REST Client Nodes

#### RESTClientNode
- **Module**: `kailash.nodes.api.rest`
- **Purpose**: RESTful API client (synchronous)
- **Parameters**:
  - `base_url`: API base URL
  - `endpoint`: Specific endpoint
  - `method`: HTTP method
  - `params`: Query parameters
  - `json_data`: JSON payload

#### AsyncRESTClientNode
- **Module**: `kailash.nodes.api.rest`
- **Purpose**: RESTful API client (asynchronous)
- **Parameters**: Same as RESTClientNode

### Rate Limiting Nodes

#### RateLimitedAPINode
- **Module**: `kailash.nodes.api.rate_limiting`
- **Purpose**: API calls with rate limiting (synchronous)
- **Parameters**:
  - `rate_limit`: Calls per time period
  - `time_window`: Time window in seconds

#### AsyncRateLimitedAPINode
- **Module**: `kailash.nodes.api.rate_limiting`
- **Purpose**: API calls with rate limiting (asynchronous)
- **Parameters**: Same as RateLimitedAPINode

## Code Nodes

### PythonCodeNode
- **Module**: `kailash.nodes.code.python`
- **Purpose**: Execute arbitrary Python code
- **Parameters**:
  - `code`: Python code to execute
  - `imports`: Required imports
  - `timeout`: Execution timeout
- **Security**: Sandboxed execution environment
- **Example**:
  ```python
  node = PythonCodeNode(
      config={
          "code": "result = sum(data)",
          "imports": []
      }
  )
  ```

## Data Nodes

### File I/O Nodes

#### CSVReaderNode
- **Module**: `kailash.nodes.data.readers`
- **Purpose**: Read CSV files
- **Parameters**:
  - `file_path`: Path to CSV file
  - `delimiter`: Column delimiter
  - `encoding`: File encoding

#### CSVWriterNode
- **Module**: `kailash.nodes.data.writers`
- **Purpose**: Write CSV files
- **Parameters**:
  - `file_path`: Output file path
  - `data`: Data to write
  - `headers`: Column headers

#### JSONReaderNode
- **Module**: `kailash.nodes.data.readers`
- **Purpose**: Read JSON files
- **Parameters**:
  - `file_path`: Path to JSON file
  - `encoding`: File encoding

#### JSONWriterNode
- **Module**: `kailash.nodes.data.writers`
- **Purpose**: Write JSON files
- **Parameters**:
  - `file_path`: Output file path
  - `data`: Data to write
  - `indent`: JSON indentation

#### TextReaderNode
- **Module**: `kailash.nodes.data.readers`
- **Purpose**: Read text files
- **Parameters**:
  - `file_path`: Path to text file
  - `encoding`: File encoding

#### TextWriterNode
- **Module**: `kailash.nodes.data.writers`
- **Purpose**: Write text files
- **Parameters**:
  - `file_path`: Output file path
  - `content`: Text content

### Database Nodes

#### SQLDatabaseNode
- **Module**: `kailash.nodes.data.sql`
- **Purpose**: Execute SQL queries
- **Parameters**:
  - `connection_string`: Database connection
  - `query`: SQL query
  - `parameters`: Query parameters

#### SQLQueryBuilderNode
- **Module**: `kailash.nodes.data.sql`
- **Purpose**: Build SQL queries programmatically
- **Parameters**:
  - `table`: Table name
  - `operation`: SELECT, INSERT, UPDATE, DELETE
  - `conditions`: WHERE conditions

### Streaming Nodes

#### EventStreamNode
- **Module**: `kailash.nodes.data.streaming`
- **Purpose**: Handle event streams
- **Parameters**:
  - `stream_url`: Stream endpoint
  - `event_types`: Events to handle

#### KafkaConsumerNode
- **Module**: `kailash.nodes.data.streaming`
- **Purpose**: Consume Kafka messages
- **Parameters**:
  - `bootstrap_servers`: Kafka servers
  - `topic`: Topic to consume
  - `group_id`: Consumer group ID

#### StreamPublisherNode
- **Module**: `kailash.nodes.data.streaming`
- **Purpose**: Publish to streams
- **Parameters**:
  - `stream_url`: Stream endpoint
  - `data`: Data to publish

#### WebSocketNode
- **Module**: `kailash.nodes.data.streaming`
- **Purpose**: WebSocket connections
- **Parameters**:
  - `ws_url`: WebSocket URL
  - `on_message`: Message handler

### Vector Database Nodes

#### EmbeddingNode
- **Module**: `kailash.nodes.data.vector_db`
- **Purpose**: Manage embeddings for vector databases
- **Parameters**:
  - `embedding_model`: Model to use
  - `vector_store`: Storage backend

#### TextSplitterNode
- **Module**: `kailash.nodes.data.vector_db`
- **Purpose**: Split text into chunks
- **Parameters**:
  - `chunk_size`: Size of chunks
  - `chunk_overlap`: Overlap between chunks
  - `separator`: Split separator

#### VectorDatabaseNode
- **Module**: `kailash.nodes.data.vector_db`
- **Purpose**: Vector database operations
- **Parameters**:
  - `db_type`: Database type (pinecone, weaviate, etc.)
  - `connection_params`: Connection parameters

### Source Management Nodes

#### DocumentSourceNode
- **Module**: `kailash.nodes.data.sources`
- **Purpose**: Manage document sources
- **Parameters**:
  - `source_path`: Document location
  - `metadata`: Document metadata

#### QuerySourceNode
- **Module**: `kailash.nodes.data.sources`
- **Purpose**: Manage query sources
- **Parameters**:
  - `query_template`: Query template
  - `parameters`: Query parameters

### Retrieval Nodes

#### RelevanceScorerNode
- **Module**: `kailash.nodes.data.retrieval`
- **Purpose**: Score document relevance
- **Parameters**:
  - `query`: Search query
  - `documents`: Documents to score
  - `scoring_method`: Scoring algorithm

### SharePoint Nodes (Need Renaming)
- **SharePointGraphReader** → Should be `SharePointGraphReaderNode`
- **SharePointGraphWriter** → Should be `SharePointGraphWriterNode`

## Logic Nodes

### SwitchNode
- **Module**: `kailash.nodes.logic.operations`
- **Purpose**: Conditional branching (synchronous)
- **Parameters**:
  - `condition`: Condition to evaluate
  - `outputs`: Named output paths
- **Example**:
  ```python
  switch = SwitchNode(
      config={
          "condition": "value > 10",
          "outputs": ["high", "low"]
      }
  )
  ```

### AsyncSwitchNode
- **Module**: `kailash.nodes.logic.async_operations`
- **Purpose**: Conditional branching (asynchronous)
- **Parameters**: Same as SwitchNode

### MergeNode
- **Module**: `kailash.nodes.logic.operations`
- **Purpose**: Merge multiple inputs (synchronous)
- **Parameters**:
  - `merge_strategy`: How to merge (concat, dict_merge, etc.)
  - `wait_for_all`: Wait for all inputs

### AsyncMergeNode
- **Module**: `kailash.nodes.logic.async_operations`
- **Purpose**: Merge multiple inputs (asynchronous)
- **Parameters**: Same as MergeNode

### WorkflowNode
- **Module**: `kailash.nodes.logic.workflow`
- **Purpose**: Execute nested workflows
- **Parameters**:
  - `workflow_path`: Path to workflow definition
  - `parameters`: Parameters to pass
- **Example**:
  ```python
  node = WorkflowNode(
      config={"workflow_path": "sub_workflow.yaml"}
  )
  ```

## MCP Nodes

### MCP Nodes (Need Renaming)
- **MCPClient** → Should be `MCPClientNode`
- **MCPServer** → Should be `MCPServerNode`
- **MCPResource** → Should be `MCPResourceNode`

## Transform Nodes

### HierarchicalChunkerNode
- **Module**: `kailash.nodes.transform.chunkers`
- **Purpose**: Create hierarchical text chunks
- **Parameters**:
  - `levels`: Hierarchy levels
  - `chunk_sizes`: Size per level
  - `overlap_ratios`: Overlap per level

### ChunkTextExtractorNode
- **Module**: `kailash.nodes.transform.formatters`
- **Purpose**: Extract text from chunks
- **Parameters**:
  - `chunks`: Input chunks
  - `extraction_method`: How to extract

### ContextFormatterNode
- **Module**: `kailash.nodes.transform.formatters`
- **Purpose**: Format context for processing
- **Parameters**:
  - `template`: Format template
  - `variables`: Template variables

### QueryTextWrapperNode
- **Module**: `kailash.nodes.transform.formatters`
- **Purpose**: Wrap queries with additional text
- **Parameters**:
  - `query`: Original query
  - `prefix`: Text prefix
  - `suffix`: Text suffix

### Transform Processor Nodes (Need Renaming)
- **Filter** → Should be `FilterNode`
- **Map** → Should be `MapNode`
- **DataTransformer** → Should be `DataTransformerNode`
- **Sort** → Should be `SortNode`

## Node Naming Issues

The following nodes do not follow the standard naming convention (should end with "Node"):

### Critical Naming Issues (22 nodes):
1. **AI Module** (10 nodes):
   - TextClassifier, TextEmbedder, SentimentAnalyzer, NamedEntityRecognizer
   - ModelPredictor, TextSummarizer, ChatAgent, RetrievalAgent
   - FunctionCallingAgent, PlanningAgent

2. **Data Module** (2 nodes):
   - SharePointGraphReader, SharePointGraphWriter

3. **MCP Module** (3 nodes):
   - MCPClient, MCPServer, MCPResource

4. **Transform Module** (4 nodes):
   - Filter, Map, DataTransformer, Sort

### Recommendation
These nodes should be renamed to follow the convention for consistency and to avoid validation errors. For example:
- `TextClassifier` → `TextClassifierNode`
- `MCPClient` → `MCPClientNode`
- `Filter` → `FilterNode`

## Usage Examples

### Basic Workflow
```python
from kailash.workflow import Workflow
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.transform.processors import FilterNode
from kailash.nodes.data.writers import JSONWriterNode

# Create workflow
workflow = Workflow()

# Add nodes
csv_reader = CSVReaderNode(config={"file_path": "data.csv"})
filter_node = FilterNode(config={"condition": "age > 18"})
json_writer = JSONWriterNode(config={"file_path": "output.json"})

workflow.add_node("reader", csv_reader)
workflow.add_node("filter", filter_node)
workflow.add_node("writer", json_writer)

# Connect nodes
workflow.connect("reader", "filter")
workflow.connect("filter", "writer")
```

### AI Pipeline
```python
from kailash.workflow import Workflow
from kailash.nodes.data.readers import TextReaderNode
from kailash.nodes.ai.llm_agent import LLMAgentNode
from kailash.nodes.data.writers import TextWriterNode

workflow = Workflow()

# Text processing pipeline
reader = TextReaderNode(config={"file_path": "input.txt"})
llm = LLMAgentNode(
    config={
        "model": "gpt-4",
        "prompt": "Summarize the following text:"
    }
)
writer = TextWriterNode(config={"file_path": "summary.txt"})

workflow.add_node("reader", reader)
workflow.add_node("llm", llm)
workflow.add_node("writer", writer)

workflow.connect("reader", "llm")
workflow.connect("llm", "writer")
```

## Node Development Guide

### Creating a Custom Node
```python
from kailash.nodes.base import Node

class MyCustomNode(Node):
    def get_parameters(self):
        return {
            "param1": {"type": str, "required": True},
            "param2": {"type": int, "default": 10}
        }
    
    def run(self, context, **kwargs):
        param1 = kwargs.get("param1")
        param2 = kwargs.get("param2", 10)
        
        # Node logic here
        result = f"{param1} processed with {param2}"
        
        return {"result": result}
    
    def get_output_schema(self):
        return {
            "type": "object",
            "properties": {
                "result": {"type": "string"}
            },
            "required": ["result"]
        }
```

### Best Practices
1. Always inherit from `Node` or `AsyncNode`
2. Define clear parameter schemas in `get_parameters()`
3. Implement output validation with `get_output_schema()`
4. Handle errors gracefully
5. Document expected inputs and outputs
6. Follow the naming convention: `YourPurposeNode`

## See Also
- [API Registry](api-registry.yaml) - Complete API reference
- [Pattern Library](pattern-library.md) - Common workflow patterns
- [Validation Guide](validation-guide.md) - Code validation rules