# AI & ML Nodes

**Module**: `kailash.nodes.ai`
**Last Updated**: 2025-01-06

This document covers all AI and machine learning nodes, including LLM agents, embeddings, A2A communication, self-organizing agents, and intelligent orchestration.

## Table of Contents
- [Core AI Nodes](#core-ai-nodes)
- [A2A Communication Nodes](#a2a-communication-nodes)
- [Self-Organizing Agent Nodes](#self-organizing-agent-nodes)
- [Intelligent Orchestration Nodes](#intelligent-orchestration-nodes)
- [Unified AI Provider Architecture](#unified-ai-provider-architecture)

## Core AI Nodes

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
  result = node.execute(
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
  result = node.execute(
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

## A2A Communication Nodes

### SharedMemoryPoolNode
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

### A2AAgentNode
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

### A2ACoordinatorNode
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

## Self-Organizing Agent Nodes

### AgentPoolManagerNode
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

### ProblemAnalyzerNode
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

### TeamFormationNode
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

### SelfOrganizingAgentNode
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

### SolutionEvaluatorNode
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

## Unified AI Provider Architecture

The SDK features a unified provider architecture supporting multiple AI providers:

**Supported Providers**:
- **OpenAI**: GPT models and text-embedding series
- **Anthropic**: Claude models (chat only)
- **Ollama**: Local LLMs with both chat and embeddings
- **Cohere**: Embedding models
- **HuggingFace**: Sentence transformers and local models
- **Mock**: Testing provider with consistent outputs

**Example**:
```python
from kailash.nodes.ai.ai_providers import get_available_providers
providers = get_available_providers()
# Returns: {"ollama": {"available": True, "chat": True, "embeddings": True}, ...}
```

## See Also
- [Base Classes](01-base-nodes.md) - Core node abstractions
- [Data Nodes](03-data-nodes.md) - Data processing and I/O
- [API Reference](../api/04-nodes-ai.yaml) - Detailed API documentation
