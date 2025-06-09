# Comprehensive Node Catalog - Kailash SDK

This reference guide lists all available nodes in the Kailash SDK and their primary use cases. **Always prefer using these specialized nodes over PythonCodeNode when possible.**

## Table of Contents
- [Data Nodes](#data-nodes)
- [Transform Nodes](#transform-nodes)
- [AI/ML Nodes](#aiml-nodes)
- [API Nodes](#api-nodes)
- [Logic Nodes](#logic-nodes)
- [Code Nodes](#code-nodes)
- [When to Use PythonCodeNode](#when-to-use-pythoncodenode)

## Data Nodes

### File Readers
- **CSVReaderNode**: Read CSV files with configurable delimiters and headers
  ```python
  # Use instead of PythonCodeNode with pd.read_csv()
  node = CSVReaderNode(file_path="data.csv", headers=True, delimiter=",")
  ```

- **JSONReaderNode**: Read JSON files into Python objects
  ```python
  # Use instead of PythonCodeNode with json.load()
  node = JSONReaderNode(file_path="data.json")
  ```

- **TextReaderNode**: Read plain text files
  ```python
  # Use instead of PythonCodeNode with open().read()
  node = TextReaderNode(file_path="document.txt")
  ```

### File Writers
- **CSVWriterNode**: Write data to CSV files
  ```python
  # Use instead of PythonCodeNode with df.to_csv()
  node = CSVWriterNode(file_path="output.csv", headers=True)
  ```

- **JSONWriterNode**: Write data to JSON files
  ```python
  # Use instead of PythonCodeNode with json.dump()
  node = JSONWriterNode(file_path="output.json", pretty=True)
  ```

- **TextWriterNode**: Write text to files
  ```python
  # Use instead of PythonCodeNode with open().write()
  node = TextWriterNode(file_path="output.txt")
  ```

### Database Operations
- **SQLDatabaseNode**: Execute SQL queries and commands
  ```python
  # Use instead of PythonCodeNode with database connections
  node = SQLDatabaseNode(
      connection_string="postgresql://user:pass@host/db",
      query="SELECT * FROM customers WHERE age > 30"
  )
  ```

### SharePoint Integration
- **SharePointGraphReader**: Read files from SharePoint
- **SharePointGraphWriter**: Write files to SharePoint

### Vector Database & Embeddings
- **EmbeddingNode**: Generate embeddings from text
- **VectorDatabaseNode**: Store and query vector embeddings
- **TextSplitterNode**: Split text into chunks for embedding

### Streaming Data
- **KafkaConsumerNode**: Consume messages from Kafka topics
- **StreamPublisherNode**: Publish messages to streams
- **WebSocketNode**: Handle WebSocket connections
- **EventStreamNode**: Process event streams

### Data Sources
- **DocumentSourceNode**: Load documents as workflow input
- **QuerySourceNode**: Generate queries as workflow input

### Retrieval
- **RelevanceScorerNode**: Score document relevance for RAG pipelines

## Transform Nodes

### Data Processing
- **FilterNode**: Filter data based on conditions
  ```python
  # Use instead of PythonCodeNode with df[df['column'] > value]
  node = FilterNode(condition="age > 30")
  ```

- **Map**: Apply transformations to each item
  ```python
  # Use instead of PythonCodeNode with list comprehensions or df.apply()
  node = Map(function=lambda x: x.upper())
  ```

- **Sort**: Sort data by specified criteria
  ```python
  # Use instead of PythonCodeNode with sorted() or df.sort_values()
  node = Sort(key="timestamp", reverse=True)
  ```

- **DataTransformer**: General-purpose data transformation
  ```python
  # Use for complex transformations before resorting to PythonCodeNode
  node = DataTransformer(operations=[...])
  ```

### Text Processing
- **HierarchicalChunkerNode**: Split documents into hierarchical chunks
- **ChunkTextExtractorNode**: Extract text from chunks
- **QueryTextWrapperNode**: Wrap queries with context
- **ContextFormatterNode**: Format context for LLM consumption

## AI/ML Nodes

### LLM Agents
- **LLMAgentNode**: General-purpose LLM agent
  ```python
  # Use instead of PythonCodeNode calling OpenAI/Anthropic APIs
  node = LLMAgentNode(
      provider="openai",
      model="gpt-4",
      system_prompt="You are a helpful assistant"
  )
  ```

- **IterativeLLMAgentNode**: LLM agent with iterative refinement
- **ChatAgent**: Conversational agent
- **RetrievalAgent**: RAG-enabled agent
- **FunctionCallingAgent**: Agent with function calling capabilities
- **PlanningAgent**: Agent for planning and reasoning

### Agent Coordination
- **A2AAgentNode**: Agent-to-agent communication
- **A2ACoordinatorNode**: Coordinate multiple agents
- **SharedMemoryPoolNode**: Shared memory for agent coordination

### Self-Organizing Agents
- **AgentPoolManagerNode**: Manage a pool of agents
- **ProblemAnalyzerNode**: Analyze problems for agent assignment
- **SelfOrganizingAgentNode**: Self-organizing agent capabilities
- **SolutionEvaluatorNode**: Evaluate agent solutions
- **TeamFormationNode**: Form agent teams dynamically

### Intelligent Orchestration
- **OrchestrationManagerNode**: Manage complex orchestrations
- **QueryAnalysisNode**: Analyze queries for routing
- **ConvergenceDetectorNode**: Detect convergence in iterative processes
- **IntelligentCacheNode**: Smart caching for LLM responses
- **MCPAgentNode**: MCP-enabled agent

### Embeddings & ML Models
- **EmbeddingGeneratorNode**: Generate text embeddings
- **TextClassifier**: Classify text into categories
- **SentimentAnalyzer**: Analyze sentiment
- **NamedEntityRecognizer**: Extract named entities
- **TextSummarizer**: Summarize text
- **ModelPredictor**: General ML model predictions

## API Nodes

### HTTP Clients
- **HTTPRequestNode**: Make HTTP requests
  ```python
  # Use instead of PythonCodeNode with requests library
  node = HTTPRequestNode(
      url="https://api.example.com/data",
      method="GET",
      headers={"Authorization": "Bearer token"}
  )
  ```

- **AsyncHTTPRequestNode**: Async HTTP requests

### REST API
- **RESTClientNode**: RESTful API client
  ```python
  # Use instead of PythonCodeNode for REST APIs
  node = RESTClientNode(
      base_url="https://api.example.com",
      endpoint="/users",
      method="POST"
  )
  ```

- **AsyncRESTClientNode**: Async REST client

### GraphQL
- **GraphQLClientNode**: GraphQL API client
- **AsyncGraphQLClientNode**: Async GraphQL client

### Authentication
- **BasicAuthNode**: Basic authentication
- **OAuth2Node**: OAuth2 authentication
- **APIKeyNode**: API key authentication

### Rate Limiting
- **RateLimitedAPINode**: API client with rate limiting
- **AsyncRateLimitedAPINode**: Async rate-limited API client

## Logic Nodes

### Control Flow
- **SwitchNode**: Conditional routing (if/else logic)
  ```python
  # Use instead of PythonCodeNode with if/else
  node = SwitchNode(
      condition="status == 'success'",
      true_output="success_path",
      false_output="error_path"
  )
  ```

- **AsyncSwitchNode**: Async conditional routing

### Data Merging
- **MergeNode**: Merge multiple data streams
  ```python
  # Use instead of PythonCodeNode combining multiple inputs
  node = MergeNode(merge_strategy="concat")
  ```

- **AsyncMergeNode**: Async data merging

### Loops & Cycles
- **LoopNode**: Execute nodes in a loop
- **ConvergenceCheckerNode**: Check for convergence conditions
- **MultiCriteriaConvergenceNode**: Complex convergence criteria

### Workflow Composition
- **WorkflowNode**: Embed workflows within workflows

## Code Nodes

### Python Execution
- **PythonCodeNode**: Execute arbitrary Python code
  - Use when no specialized node exists
  - For custom business logic
  - For complex data transformations not covered by transform nodes
  - For integrations without dedicated nodes

## When to Use PythonCodeNode

Use PythonCodeNode **only** when:

1. **No specialized node exists** for your use case
2. **Complex custom logic** that doesn't fit existing nodes
3. **Temporary prototyping** before creating a custom node
4. **Mathematical computations** not covered by transform nodes
5. **Custom data validation** beyond filter nodes
6. **Integration with libraries** without dedicated nodes

### Examples of When NOT to Use PythonCodeNode

❌ **Reading/Writing Files**
```python
# Don't use PythonCodeNode:
with open('data.csv') as f:
    data = pd.read_csv(f)

# Use CSVReaderNode instead:
node = CSVReaderNode(file_path='data.csv')
```

❌ **API Calls**
```python
# Don't use PythonCodeNode:
response = requests.get('https://api.example.com/data')

# Use HTTPRequestNode instead:
node = HTTPRequestNode(url='https://api.example.com/data', method='GET')
```

❌ **Data Filtering**
```python
# Don't use PythonCodeNode:
filtered = [x for x in data if x['age'] > 30]

# Use FilterNode instead:
node = FilterNode(condition="age > 30")
```

❌ **LLM Calls**
```python
# Don't use PythonCodeNode:
response = openai.ChatCompletion.create(...)

# Use LLMAgentNode instead:
node = LLMAgentNode(provider="openai", model="gpt-4")
```

### Examples of When to Use PythonCodeNode

✅ **Complex Business Logic**
```python
# Custom pricing calculation with multiple rules
node = PythonCodeNode(
    name="custom_pricing",
    code='''
    # Complex pricing logic specific to business
    base_price = product['price']
    if customer['tier'] == 'platinum':
        discount = 0.20
    elif customer['tier'] == 'gold' and order['quantity'] > 10:
        discount = 0.15
    else:
        discount = 0.05

    final_price = base_price * (1 - discount) * order['quantity']
    result = {"final_price": final_price, "discount_applied": discount}
    '''
)
```

✅ **Scientific Computations**
```python
# Statistical analysis not covered by existing nodes
node = PythonCodeNode(
    name="statistical_analysis",
    code='''
    import numpy as np
    from scipy import stats

    # Custom statistical test
    statistic, p_value = stats.ks_2samp(sample1, sample2)
    result = {
        "statistic": statistic,
        "p_value": p_value,
        "significant": p_value < 0.05
    }
    '''
)
```

## Best Practices

1. **Always check for existing nodes first** - Review this catalog before using PythonCodeNode
2. **Use specialized nodes for better:**
   - Error handling
   - Performance optimization
   - Integration testing
   - Documentation
   - Maintenance

3. **Create custom nodes** instead of repeated PythonCodeNode usage for the same logic
4. **Leverage node composition** - Combine multiple specialized nodes instead of one complex PythonCodeNode

## Node Discovery Tips

1. Check node imports: `from kailash.nodes import ...`
2. Use IDE autocomplete after `from kailash.nodes.`
3. Review examples in `/examples` directory
4. Check node docstrings for usage details
5. Look at test files for usage patterns
