Self-Organizing Agent Pools Guide
=================================

This guide explains how to create and manage self-organizing agent pools that can autonomously collaborate to solve complex problems.

.. contents:: Table of Contents
   :local:
   :depth: 2

Overview
--------

Self-organizing agent pools enable multiple AI agents to:

- **Autonomously form teams** based on problem requirements
- **Share information** through intelligent caching and memory pools  
- **Access external tools** via MCP (Model Context Protocol) integration
- **Evaluate solutions** and determine when to stop iterating
- **Coordinate efficiently** without centralized control

Key Components
--------------

Core Infrastructure
~~~~~~~~~~~~~~~~~~~

**SharedMemoryPoolNode**
   Central memory system with selective attention mechanisms for information sharing.

**IntelligentCacheNode**
   Prevents redundant external calls through semantic similarity detection and TTL-based caching.

**AgentPoolManagerNode**
   Manages agent registry, capabilities, and performance tracking.

Self-Organization Components
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**ProblemAnalyzerNode**
   Decomposes problems into capability requirements and subtasks.

**TeamFormationNode**
   Forms optimal teams using various strategies (capability matching, swarm-based, market-based, hierarchical).

**SelfOrganizingAgentNode**
   Individual agents that adapt roles based on team context.

**SolutionEvaluatorNode**
   Evaluates solution quality across multiple criteria.

Orchestration Components
~~~~~~~~~~~~~~~~~~~~~~~~

**QueryAnalysisNode**
   Analyzes queries to determine complexity and required capabilities.

**MCPAgentNode**
   Agents with MCP integration for external tool access.

**OrchestrationManagerNode**
   Coordinates the entire self-organizing workflow.

**ConvergenceDetectorNode**
   Determines when to stop iterating based on quality, improvement, or time limits.

Basic Usage Pattern
-------------------

.. code-block:: python

   from kailash import Workflow
   from kailash.runtime import LocalRuntime
   from kailash.nodes.ai.intelligent_agent_orchestrator import (
       OrchestrationManagerNode,
       IntelligentCacheNode,
       MCPAgentNode
   )
   from kailash.nodes.ai.self_organizing import (
       AgentPoolManagerNode,
       TeamFormationNode
   )
   from kailash.nodes.ai.a2a import SharedMemoryPoolNode
   
   # Create workflow
   workflow = Workflow("Self-Organizing System")
   
   # Add shared infrastructure
   memory = workflow.add_node(SharedMemoryPoolNode(name="memory"))
   cache = workflow.add_node(IntelligentCacheNode(name="cache", ttl=3600))
   
   # Add orchestration
   orchestrator = workflow.add_node(OrchestrationManagerNode(
       name="orchestrator",
       max_iterations=5,
       quality_threshold=0.8,
       time_limit_minutes=10
   ))
   
   # Execute
   runtime = LocalRuntime()
   result, _ = runtime.execute(workflow, parameters={
       "orchestrator": {
           "query": "Analyze market trends and recommend strategy",
           "mcp_servers": [
               {"name": "market_data", "command": "python", "args": ["-m", "market_mcp"]},
               {"name": "financial", "command": "python", "args": ["-m", "finance_mcp"]}
           ],
           "agent_pool_size": 10
       }
   })

Advanced Configuration
----------------------

MCP Integration
~~~~~~~~~~~~~~~

Configure agents with specific MCP servers for tool access:

.. code-block:: python

   # Create specialized MCP agents
   research_agent = workflow.add_node(MCPAgentNode(
       name="research_agent",
       mcp_server="filesystem",
       capabilities=["file_access", "research", "documentation"],
       shared_cache=cache,
       shared_memory=memory
   ))
   
   data_agent = workflow.add_node(MCPAgentNode(
       name="data_agent",
       mcp_server="database", 
       capabilities=["data_access", "sql", "analytics"],
       shared_cache=cache,
       shared_memory=memory
   ))

Information Reuse
~~~~~~~~~~~~~~~~~

Configure intelligent caching to prevent redundant operations:

.. code-block:: python

   # Cache with semantic similarity detection
   cache = workflow.add_node(IntelligentCacheNode(
       name="cache",
       ttl=3600,  # 1 hour TTL
       similarity_threshold=0.8,  # Semantic matching threshold
       max_entries=1000
   ))
   
   # Cache expensive operations
   cache_result = cache.run(
       action="cache",
       cache_key="market_analysis_2024",
       data={"trends": [...], "predictions": [...]},
       metadata={
           "source": "market_mcp",
           "cost": 2.50,
           "semantic_tags": ["market", "analysis", "trends"]
       }
   )

Convergence Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~

Set up automatic termination conditions:

.. code-block:: python

   # Configure convergence detection
   convergence = workflow.add_node(ConvergenceDetectorNode(
       name="convergence",
       quality_threshold=0.85,      # Stop when quality >= 85%
       improvement_threshold=0.02,   # Stop if improvement < 2%
       max_iterations=10,           # Hard limit on iterations
       timeout=600,                 # 10 minute timeout
       min_iterations=3             # Always run at least 3 iterations
   ))

Team Formation Strategies
-------------------------

Capability Matching
~~~~~~~~~~~~~~~~~~~

Best for tasks requiring specific skills:

.. code-block:: python

   team_former = workflow.add_node(TeamFormationNode(
       name="team_former",
       formation_strategy="capability_matching",
       optimization_rounds=3
   ))

Swarm-Based
~~~~~~~~~~~

For exploration and discovery tasks:

.. code-block:: python

   team_former = workflow.add_node(TeamFormationNode(
       name="team_former",
       formation_strategy="swarm_based",
       cluster_threshold=0.7
   ))

Market-Based
~~~~~~~~~~~~

When resources are constrained:

.. code-block:: python

   team_former = workflow.add_node(TeamFormationNode(
       name="team_former",
       formation_strategy="market_based",
       budget_constraint=100.0
   ))

Hierarchical
~~~~~~~~~~~~

For complex multi-level problems:

.. code-block:: python

   team_former = workflow.add_node(TeamFormationNode(
       name="team_former",
       formation_strategy="hierarchical",
       max_depth=3
   ))

Complete Example
----------------

Here's a comprehensive example of a self-organizing research system:

.. code-block:: python

   from kailash import Workflow
   from kailash.runtime import LocalRuntime
   from kailash.nodes.ai.intelligent_agent_orchestrator import *
   from kailash.nodes.ai.self_organizing import *
   from kailash.nodes.ai.a2a import *
   
   def create_research_system():
       """Create a self-organizing research system."""
       workflow = Workflow("Research System")
       
       # Shared infrastructure
       memory = workflow.add_node(SharedMemoryPoolNode(
           name="memory",
           memory_size_limit=1000,
           attention_window=50
       ))
       
       cache = workflow.add_node(IntelligentCacheNode(
           name="cache",
           ttl=7200,  # 2 hours
           similarity_threshold=0.75
       ))
       
       # Analysis components
       query_analyzer = workflow.add_node(QueryAnalysisNode(name="analyzer"))
       problem_analyzer = workflow.add_node(ProblemAnalyzerNode(name="problem"))
       
       # Agent pool
       pool = workflow.add_node(AgentPoolManagerNode(name="pool"))
       
       # Team formation
       team_former = workflow.add_node(TeamFormationNode(
           name="team_former",
           formation_strategy="capability_matching"
       ))
       
       # Specialized agents
       for i in range(5):
           agent = workflow.add_node(MCPAgentNode(
               name=f"agent_{i}",
               capabilities=["research", "analysis", "synthesis"],
               shared_cache=cache,
               shared_memory=memory
           ))
       
       # Evaluation and convergence
       evaluator = workflow.add_node(SolutionEvaluatorNode(
           name="evaluator",
           criteria=["accuracy", "completeness", "clarity"]
       ))
       
       convergence = workflow.add_node(ConvergenceDetectorNode(
           name="convergence",
           quality_threshold=0.9,
           max_iterations=8
       ))
       
       # Orchestration
       orchestrator = workflow.add_node(OrchestrationManagerNode(
           name="orchestrator",
           max_iterations=10,
           quality_threshold=0.85
       ))
       
       # Connect workflow
       workflow.connect("analyzer", "problem")
       workflow.connect("problem", "team_former")
       workflow.connect("team_former", "orchestrator")
       workflow.connect("orchestrator", "evaluator")
       workflow.connect("evaluator", "convergence")
       
       return workflow
   
   # Use the system
   workflow = create_research_system()
   runtime = LocalRuntime()
   
   result, _ = runtime.execute(workflow, parameters={
       "orchestrator": {
           "query": "Research quantum computing applications in finance",
           "mcp_servers": [
               {"name": "arxiv", "command": "arxiv-mcp"},
               {"name": "finance", "command": "finance-mcp"},
               {"name": "web", "command": "web-mcp"}
           ],
           "context": {
               "domain": "fintech",
               "depth": "comprehensive",
               "output_format": "report"
           }
       }
   })

Best Practices
--------------

1. **Agent Specialization**
   Create agents with focused capabilities rather than generalist agents.

2. **Cache Configuration**
   Set appropriate TTLs based on data volatility:
   
   - Static data: 24-48 hours
   - Market data: 15-60 minutes
   - Real-time data: 1-5 minutes

3. **Team Size**
   Balance team size with coordination overhead:
   
   - Simple tasks: 3-5 agents
   - Medium complexity: 5-10 agents
   - Complex problems: 10-20 agents

4. **Convergence Tuning**
   Balance quality vs. time:
   
   - High stakes: quality_threshold=0.9+, max_iterations=20+
   - Time sensitive: timeout=300s, min_iterations=2
   - Exploratory: improvement_threshold=0.01, no timeout

5. **Memory Management**
   Use attention mechanisms to filter relevant information:
   
   - Set appropriate attention_window sizes
   - Use semantic tags for better filtering
   - Implement memory cleanup for long-running systems

Performance Optimization
------------------------

Caching Strategy
~~~~~~~~~~~~~~~~

.. code-block:: python

   # Implement multi-level caching
   l1_cache = IntelligentCacheNode(name="l1", ttl=300)    # 5 min hot cache
   l2_cache = IntelligentCacheNode(name="l2", ttl=3600)   # 1 hour warm cache
   l3_cache = IntelligentCacheNode(name="l3", ttl=86400)  # 24 hour cold cache

Parallel Execution
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Configure parallel agent execution
   orchestrator = OrchestrationManagerNode(
       name="orchestrator",
       parallel_execution=True,
       max_concurrent_agents=10
   )

Resource Management
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Set resource constraints
   pool = AgentPoolManagerNode(
       name="pool",
       max_active_agents=20,
       agent_timeout=120,  # 2 minutes per task
       memory_limit_mb=1024
   )

Monitoring and Debugging
------------------------

Track Performance
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Access performance metrics
   metrics = result.get("performance_metrics", {})
   print(f"Cache hit rate: {metrics.get('cache_hit_rate', 0):.2%}")
   print(f"Avg response time: {metrics.get('avg_response_time', 0):.2f}s")
   print(f"Total cost saved: ${metrics.get('cost_saved', 0):.2f}")

Debug Agent Interactions
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Enable debug logging
   import logging
   logging.basicConfig(level=logging.DEBUG)
   
   # Track agent communications
   memory_contents = memory.run(action="list", limit=10)
   print(f"Recent memories: {len(memory_contents['memories'])}")

Common Patterns
---------------

Research and Analysis
~~~~~~~~~~~~~~~~~~~~~

Use capability matching with specialized research agents.

Data Processing Pipeline
~~~~~~~~~~~~~~~~~~~~~~~~

Use hierarchical formation for multi-stage processing.

Real-time Monitoring
~~~~~~~~~~~~~~~~~~~~

Use swarm-based formation with fast convergence.

Strategic Planning
~~~~~~~~~~~~~~~~~~

Use market-based formation with quality-focused convergence.

Error Handling
--------------

.. code-block:: python

   try:
       result, _ = runtime.execute(workflow, parameters={...})
       
       if result.get("orchestrator", {}).get("success"):
           solution = result["orchestrator"]["final_solution"]
           print(f"Solution confidence: {solution.get('confidence', 0):.2%}")
       else:
           error = result.get("orchestrator", {}).get("error", "Unknown error")
           print(f"Execution failed: {error}")
           
   except Exception as e:
       print(f"Workflow error: {e}")
       # Access partial results if available
       partial = result.get("partial_results", {})

Next Steps
----------

- Explore the :doc:`../examples/self_organizing_agents` for more examples
- Review :doc:`../api/nodes` for detailed node documentation
- Check :doc:`performance` for optimization tips
- See :doc:`../tutorials/index` for step-by-step tutorials