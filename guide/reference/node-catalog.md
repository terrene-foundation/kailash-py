# Kailash Python SDK - Node Catalog

Last Updated: 2025-06-05

This comprehensive catalog documents all available nodes in the Kailash Python SDK, organized by category.

## Table of Contents
- [Base Classes](#base-classes)
- [AI Nodes](#ai-nodes)
- [Intelligent Orchestration Nodes](#intelligent-orchestration-nodes)
- [Self-Organizing Agent Nodes](#self-organizing-agent-nodes)
- [A2A Communication Nodes](#a2a-communication-nodes)
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

### LLMAgentNode
- **Module**: `kailash.nodes.ai.llm_agent`
- **Purpose**: Interact with Large Language Models with unified provider architecture
- **Parameters**:
  - `provider`: Provider name (openai, anthropic, ollama, mock)
  - `model`: LLM model to use
  - `prompt` or `messages`: Input prompt or conversation messages
  - `temperature`: Sampling temperature
  - `max_tokens`: Maximum response tokens
  - `operation`: Operation type (qa, conversation, tool_calling)
- **Example**:
  ```python
  node = LLMAgentNode()
  result = node.run(
      provider="openai",
      model="gpt-4",
      prompt="Explain quantum computing",
      temperature=0.7,
      max_tokens=1000
  )
  ```

### EmbeddingGeneratorNode
- **Module**: `kailash.nodes.ai.embedding_generator`
- **Purpose**: Generate text embeddings using various models with caching
- **Parameters**:
  - `provider`: Provider name (openai, ollama, cohere, huggingface, mock)
  - `model`: Embedding model to use
  - `input_text` or `input_texts`: Text to embed (single or batch)
  - `operation`: Operation type (embed_text, embed_batch, calculate_similarity)
  - `batch_size`: Batch size for processing
  - `cache_enabled`: Enable caching of embeddings
- **Example**:
  ```python
  node = EmbeddingGeneratorNode()
  result = node.run(
      provider="openai",
      model="text-embedding-3-large",
      input_text="This is a sample document",
      operation="embed_text"
  )
  ```

### ChatAgent & RetrievalAgent
- **ChatAgent Module**: `kailash.nodes.ai.agents`
- **RetrievalAgent Module**: `kailash.nodes.ai.agents`
- **Purpose**: Specialized agents for conversation and document retrieval
- **Features**: Built on unified provider architecture with enhanced capabilities

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

### A2A Communication Nodes

#### SharedMemoryPoolNode
- **Module**: `kailash.nodes.ai.a2a`
- **Purpose**: Central memory pool for agent-to-agent communication
- **Parameters**:
  - `action`: Memory operation (read, write, subscribe, query)
  - `agent_id`: ID of the agent performing action
  - `content`: Content to write (for write action)
  - `attention_filter`: Filter criteria for reading memories
- **Example**:
  ```python
  memory_pool = SharedMemoryPoolNode()
  result = memory_pool.run(
      action="write",
      agent_id="researcher_001",
      content="Key finding about correlation",
      tags=["research", "correlation"],
      importance=0.8
  )
  ```

#### A2AAgentNode
- **Module**: `kailash.nodes.ai.a2a`
- **Purpose**: Enhanced LLM agent with A2A communication capabilities
- **Parameters**: Extends LLMAgentNode parameters plus:
  - `agent_id`: Unique agent identifier
  - `agent_role`: Agent's role (researcher, analyst, etc.)
  - `memory_pool`: Reference to SharedMemoryPoolNode
  - `attention_filter`: Criteria for filtering relevant information
- **Example**:
  ```python
  agent = A2AAgentNode()
  result = agent.run(
      agent_id="researcher_001",
      provider="openai",
      model="gpt-4",
      messages=[{"role": "user", "content": "Analyze data"}],
      memory_pool=memory_pool,
      attention_filter={"tags": ["data", "analysis"]}
  )
  ```

#### A2ACoordinatorNode
- **Module**: `kailash.nodes.ai.a2a`
- **Purpose**: Coordinates communication and task delegation between agents
- **Parameters**:
  - `action`: Coordination action (register, delegate, broadcast, consensus)
  - `agent_info`: Agent information for registration
  - `task`: Task to delegate or coordinate
  - `coordination_strategy`: Strategy (best_match, round_robin, auction)
- **Example**:
  ```python
  coordinator = A2ACoordinatorNode()
  result = coordinator.run(
      action="delegate",
      task={"type": "research", "description": "Analyze trends"},
      available_agents=[{"id": "agent1", "skills": ["research"]}],
      coordination_strategy="best_match"
  )
  ```

### Self-Organizing Agent Nodes

#### AgentPoolManagerNode
- **Module**: `kailash.nodes.ai.self_organizing`
- **Purpose**: Manages pool of self-organizing agents with capability tracking
- **Parameters**:
  - `action`: Pool operation (register, find_by_capability, update_status)
  - `agent_id`: ID of the agent
  - `capabilities`: List of agent capabilities
  - `required_capabilities`: Capabilities required for search
- **Features**:
  - Agent registry with capability indexing
  - Performance tracking and load balancing
  - Dynamic agent discovery and matching
  - Real-time availability monitoring
- **Example**:
  ```python
  pool_manager = AgentPoolManagerNode()
  result = pool_manager.run(
      action="register",
      agent_id="research_agent_001",
      capabilities=["data_analysis", "research"],
      metadata={"experience_level": "senior"}
  )
  ```

#### ProblemAnalyzerNode
- **Module**: `kailash.nodes.ai.self_organizing`
- **Purpose**: Analyzes problems to determine required capabilities and complexity
- **Parameters**:
  - `problem_description`: Description of problem to solve
  - `context`: Additional context about the problem
  - `decomposition_strategy`: Strategy for decomposing problem
- **Features**:
  - Problem complexity assessment
  - Capability requirement analysis
  - Multi-level problem decomposition
  - Resource estimation and planning
- **Example**:
  ```python
  analyzer = ProblemAnalyzerNode()
  result = analyzer.run(
      problem_description="Predict customer churn",
      context={"domain": "business", "urgency": "high"}
  )
  ```

#### TeamFormationNode
- **Module**: `kailash.nodes.ai.self_organizing`
- **Purpose**: Forms optimal teams based on problem requirements
- **Parameters**:
  - `problem_analysis`: Analysis from ProblemAnalyzerNode
  - `available_agents`: List of available agents
  - `formation_strategy`: Team formation strategy
  - `constraints`: Constraints for team formation
- **Formation Strategies**:
  - `capability_matching`: Match agents to required skills
  - `swarm_based`: Self-organizing exploration teams
  - `market_based`: Auction-based agent allocation
  - `hierarchical`: Structured teams with clear roles
- **Example**:
  ```python
  formation_engine = TeamFormationNode()
  result = formation_engine.run(
      problem_analysis=analysis,
      available_agents=agents,
      formation_strategy="capability_matching"
  )
  ```

#### SelfOrganizingAgentNode
- **Module**: `kailash.nodes.ai.self_organizing`
- **Purpose**: Agent that can autonomously join teams and collaborate
- **Parameters**: Extends A2AAgentNode parameters plus:
  - `capabilities`: Agent's capabilities
  - `team_context`: Current team information
  - `collaboration_mode`: Mode (cooperative, competitive, mixed)
  - `autonomy_level`: Level of autonomous decision making
- **Features**:
  - Autonomous team joining and role adaptation
  - Dynamic capability learning and evolution
  - Context-aware collaboration patterns
  - Performance-based specialization
- **Example**:
  ```python
  agent = SelfOrganizingAgentNode()
  result = agent.run(
      agent_id="adaptive_agent_001",
      capabilities=["data_analysis", "machine_learning"],
      team_context={"team_id": "research_team_1"},
      task="Perform clustering analysis"
  )
  ```

#### SolutionEvaluatorNode
- **Module**: `kailash.nodes.ai.self_organizing`
- **Purpose**: Evaluates solutions and determines if iteration is needed
- **Parameters**:
  - `solution`: Solution to evaluate
  - `problem_requirements`: Original problem requirements
  - `team_performance`: Team performance metrics
  - `evaluation_criteria`: Custom evaluation criteria
- **Features**:
  - Multi-criteria solution assessment
  - Quality threshold monitoring
  - Iterative improvement detection
  - Team performance correlation analysis
- **Example**:
  ```python
  evaluator = SolutionEvaluatorNode()
  result = evaluator.run(
      solution={"approach": "ML model", "confidence": 0.85},
      problem_requirements={"quality_threshold": 0.8},
      team_performance={"collaboration_score": 0.9}
  )
  ```

## Intelligent Orchestration Nodes

### IntelligentCacheNode
- **Module**: `kailash.nodes.ai.intelligent_agent_orchestrator`
- **Purpose**: Intelligent caching system to prevent repeated external calls
- **Features**:
  - Semantic similarity detection for cache hits
  - TTL-based expiration with smart refresh policies
  - Cost-aware caching prioritizing expensive operations
  - Cross-agent information sharing
- **Parameters**:
  - `action`: Cache operation (cache, get, invalidate, stats, cleanup)
  - `cache_key`: Unique key for cached item
  - `data`: Data to cache
  - `metadata`: Metadata including source, cost, semantic tags
  - `ttl`: Time to live in seconds
  - `similarity_threshold`: Threshold for semantic matching
- **Example**:
  ```python
  cache = IntelligentCacheNode()
  result = cache.run(
      action="cache",
      cache_key="weather_api_nyc",
      data={"temperature": 72, "humidity": 65},
      metadata={
          "source": "weather_mcp_server",
          "cost": 0.05,
          "semantic_tags": ["weather", "temperature", "nyc"]
      },
      ttl=3600
  )
  ```

### MCPAgentNode
- **Module**: `kailash.nodes.ai.intelligent_agent_orchestrator`
- **Purpose**: Self-organizing agent enhanced with MCP integration
- **Features**:
  - Access external tools through MCP servers
  - Integration with intelligent caching
  - Tool capability sharing with team members
  - Adaptive tool usage based on team needs
- **Parameters**: Extends SelfOrganizingAgentNode parameters plus:
  - `mcp_servers`: List of MCP server configurations
  - `cache_node_id`: ID of cache node for preventing repeated calls
  - `tool_preferences`: Agent's preferences for tool usage
  - `cost_awareness`: How cost-conscious the agent is (0-1)
- **Example**:
  ```python
  agent = MCPAgentNode()
  result = agent.run(
      agent_id="mcp_agent_001",
      capabilities=["data_analysis", "api_integration"],
      mcp_servers=[{
          "name": "weather_server",
          "command": "python",
          "args": ["-m", "weather_mcp"]
      }],
      task="Get weather for NYC and analyze trends"
  )
  ```

### QueryAnalysisNode
- **Module**: `kailash.nodes.ai.intelligent_agent_orchestrator`
- **Purpose**: Analyzes queries to determine optimal solving approach
- **Features**:
  - Pattern recognition for query types
  - Complexity assessment and capability requirements
  - Team composition suggestions
  - MCP tool requirement analysis
- **Parameters**:
  - `query`: The query to analyze
  - `context`: Additional context about the query
  - `available_agents`: List of available agents
  - `mcp_servers`: Available MCP servers
- **Example**:
  ```python
  analyzer = QueryAnalysisNode()
  result = analyzer.run(
      query="Research renewable energy trends and create strategic plan",
      context={"domain": "strategic_planning", "urgency": "high"},
      mcp_servers=[{"name": "research_server", "type": "web_research"}]
  )
  ```

### OrchestrationManagerNode
- **Module**: `kailash.nodes.ai.intelligent_agent_orchestrator`
- **Purpose**: Central coordinator for entire self-organizing workflow
- **Features**:
  - Multi-phase execution (analysis → formation → collaboration → evaluation)
  - Agent pool management with specializations
  - Iterative solution refinement
  - Performance monitoring and optimization
- **Parameters**:
  - `query`: Main query or problem to solve
  - `context`: Additional context for the query
  - `agent_pool_size`: Number of agents in the pool
  - `mcp_servers`: MCP server configurations
  - `max_iterations`: Maximum number of solution iterations
  - `quality_threshold`: Quality threshold for solution acceptance
  - `time_limit_minutes`: Maximum time limit for solution
  - `enable_caching`: Enable intelligent caching
- **Example**:
  ```python
  orchestrator = OrchestrationManagerNode()
  result = orchestrator.run(
      query="Analyze market trends and develop strategy",
      agent_pool_size=15,
      mcp_servers=[{"name": "market_server", "type": "market_data"}],
      max_iterations=3,
      quality_threshold=0.85
  )
  ```

### ConvergenceDetectorNode
- **Module**: `kailash.nodes.ai.intelligent_agent_orchestrator`
- **Purpose**: Determines when solutions are satisfactory and iteration should terminate
- **Features**:
  - Multiple convergence signals (quality, improvement rate, consensus)
  - Diminishing returns detection
  - Resource efficiency monitoring
  - Recommendation generation
- **Parameters**:
  - `solution_history`: History of solution iterations
  - `quality_threshold`: Minimum quality threshold
  - `improvement_threshold`: Minimum improvement to continue
  - `max_iterations`: Maximum allowed iterations
  - `current_iteration`: Current iteration number
  - `time_limit_seconds`: Maximum time allowed
- **Example**:
  ```python
  detector = ConvergenceDetectorNode()
  result = detector.run(
      solution_history=solution_iterations,
      quality_threshold=0.8,
      improvement_threshold=0.02,
      current_iteration=3
  )
  ```

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
- **Purpose**: Routes data to different outputs based on conditions
- **Features**:
  - Boolean conditions (true/false branching)
  - Multi-case switching (similar to switch statements)
  - Dynamic workflow paths based on data values
- **Parameters**:
  - `input_data`: Input data to route
  - `condition_field`: Field in input data to evaluate (for dict inputs)
  - `operator`: Comparison operator (==, !=, >, <, >=, <=, in, contains, is_null, is_not_null)
  - `value`: Value to compare against for boolean conditions
  - `cases`: List of values for multi-case switching
  - `case_prefix`: Prefix for case output fields (default: "case_")
  - `default_field`: Output field name for default case (default: "default")
  - `pass_condition_result`: Whether to include condition result in outputs (default: True)
- **Example** (with doctest):
  ```python
  >>> # Simple boolean condition
  >>> switch_node = SwitchNode(condition_field="status", operator="==", value="success")
  >>> switch_node.metadata.name
  'SwitchNode'
  ```

### AsyncSwitchNode
- **Module**: `kailash.nodes.logic.async_operations`
- **Purpose**: Asynchronously routes data to different outputs based on conditions
- **Features**:
  - Efficient for I/O-bound condition evaluation
  - Handles large datasets with complex routing criteria
  - Integrates with other async nodes in workflows
- **Parameters**: Same as SwitchNode
- **Example** (with doctest):
  ```python
  >>> import asyncio
  >>> async_switch = AsyncSwitchNode(condition_field="status", operator="==", value="active")
  >>> result = asyncio.run(async_switch.execute_async(
  ...     input_data={"status": "active", "data": "test"}
  ... ))
  >>> result['true_output']
  {'status': 'active', 'data': 'test'}
  ```

### MergeNode
- **Module**: `kailash.nodes.logic.operations`
- **Purpose**: Merges multiple data sources
- **Features**:
  - Combines results from parallel branches
  - Joins related data sets
  - Combines outputs after conditional branching
  - Aggregates collections of data
- **Parameters**:
  - `data1`: First data source (required)
  - `data2`: Second data source (required)
  - `data3`, `data4`, `data5`: Additional data sources (optional)
  - `merge_type`: Type of merge (concat, zip, merge_dict)
  - `key`: Key field for dict merging
  - `skip_none`: Skip None values when merging (default: True)
- **Example** (with doctest):
  ```python
  >>> # Simple list concatenation
  >>> merge_node = MergeNode(merge_type="concat")
  >>> result = merge_node.execute(data1=[1, 2], data2=[3, 4])
  >>> result['merged_data']
  [1, 2, 3, 4]
  ```

### AsyncMergeNode
- **Module**: `kailash.nodes.logic.async_operations`
- **Purpose**: Asynchronously merges multiple data sources
- **Features**:
  - Efficient processing for large datasets
  - Chunk-based processing for memory efficiency
  - Async/await for I/O-bound operations
- **Parameters**: Same as MergeNode, plus:
  - `chunk_size`: Chunk size for processing large datasets (default: 1000)
- **Example** (with doctest):
  ```python
  >>> import asyncio
  >>> async_merge = AsyncMergeNode(merge_type="concat")
  >>> result = asyncio.run(async_merge.execute_async(data1=[1, 2], data2=[3, 4]))
  >>> result['merged_data']
  [1, 2, 3, 4]
  ```

### WorkflowNode
- **Module**: `kailash.nodes.logic.workflow`
- **Purpose**: Encapsulates and executes an entire workflow as a single node
- **Features**:
  - Hierarchical workflow composition
  - Dynamic parameter discovery from entry nodes
  - Multiple loading methods (instance, file, dict)
  - Automatic output mapping from exit nodes
- **Parameters**:
  - `workflow`: Optional workflow instance to wrap
  - `workflow_path`: Path to load workflow from file (JSON/YAML)
  - `workflow_dict`: Dictionary representation of workflow
  - `input_mapping`: Map node inputs to workflow inputs
  - `output_mapping`: Map workflow outputs to node outputs
  - `inputs`: Additional input overrides for workflow nodes
- **Example** (with doctest):
  ```python
  >>> # Direct workflow wrapping
  >>> from kailash.workflow.graph import Workflow
  >>> inner_workflow = Workflow("wf-001", "data_processing")
  >>> node = WorkflowNode(workflow=inner_workflow)
  >>> node.metadata.name
  'WorkflowNode'
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

### FilterNode ✅
- **Module**: `kailash.nodes.transform.processors`
- **Purpose**: Filters data based on configurable conditions and operators
- **Parameters**:
  - `data`: Input data to filter (list)
  - `field`: Field name for dict-based filtering (optional)
  - `operator`: Comparison operator (==, !=, >, <, >=, <=, contains)
  - `value`: Value to compare against
- **Example**:
  ```python
  filter_node = FilterNode()
  result = filter_node.run(
      data=[1, 2, 3, 4, 5],
      operator=">",
      value=3
  )  # Returns: {"filtered_data": [4, 5]}
  ```
- **Backward Compatibility**: Available as `Filter` alias

### Transform Processor Nodes (Need Renaming)
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

## Documentation and Guides

### Usage Guides
- **Self-Organizing Agents**: `docs/guides/self_organizing_agents.rst` - Comprehensive guide for using self-organizing agent pools
- **Examples**: `docs/examples/self_organizing_agents.rst` - Working examples of A2A and self-organizing patterns
- **Integration Examples**: `examples/integration_examples/` - 11 runnable A2A examples

### Architecture Documentation
- **ADR-0030**: `guide/adr/0030-self-organizing-agent-pool-architecture.md` - Design decisions and architecture
- **Design Document**: `SELF_ORGANIZING_AGENT_POOL_DESIGN.md` - Detailed design patterns

## See Also
- [API Registry](api-registry.yaml) - Complete API reference
- [Pattern Library](pattern-library.md) - Common workflow patterns
- [Validation Guide](validation-guide.md) - Code validation rules