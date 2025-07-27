=====
Nodes
=====

This section provides comprehensive documentation for all node types available
in the Kailash SDK.

.. contents:: Table of Contents
   :local:
   :depth: 2

Base Node Classes
=================

Node
----

.. autoclass:: kailash.nodes.base.Node
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

AsyncNode
---------

.. autoclass:: kailash.nodes.base_async.AsyncNode
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

CycleAwareNode
--------------

.. autoclass:: kailash.nodes.base_cycle_aware.CycleAwareNode
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

The CycleAwareNode provides built-in helpers for managing state and iteration
tracking in cyclic workflows.

**Helper Methods:**

- ``get_iteration(context)``: Get the current iteration number (0-based)
- ``get_previous_state(context)``: Access state from the previous iteration
- ``set_cycle_state(state)``: Persist state for the next iteration
- ``accumulate_values(context, key, value)``: Build a rolling window of values
- ``detect_convergence_trend(context, metric_key)``: Analyze convergence patterns
- ``log_cycle_info(context, message)``: Log structured cycle information

**Example Usage:**

.. code-block:: python

   from kailash.nodes.base_cycle_aware import CycleAwareNode
   from typing import Dict, Any

   class OptimizerNode(CycleAwareNode):
       """Iterative optimization node that improves results each cycle."""

       def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
           # Get iteration info
           iteration = self.get_iteration(context)
           prev_state = self.get_previous_state(context)

           # Get previous value or start with initial
           current_value = prev_state.get("value", 0.5)

           # Optimization step
           improvement = 0.1 * (1 - current_value)  # Diminishing returns
           new_value = current_value + improvement

           # Track convergence
           self.accumulate_values(context, "value", new_value)
           trend = self.detect_convergence_trend(context, "value")

           # Save state for next iteration
           self.set_cycle_state({"value": new_value})

           # Log progress
           self.log_cycle_info(context, f"Value improved to {new_value:.3f}")

           # Check convergence
           converged = new_value > 0.95 or (trend["converging"] and trend["stability"] > 0.98)

           return {
               "value": new_value,
               "converged": converged,
               "iteration": iteration,
               "improvement": improvement
           }

   # Use in a workflow
   from kailash import Workflow

   workflow = Workflow("optimization")
   workflow.add_node("optimizer", OptimizerNode())

   # Create optimization cycle
   workflow.create_cycle("optimization_cycle") \
           .connect("optimizer", "optimizer", mapping={"value": "initial_value"}) \
           .max_iterations(100) \
           .converge_when("converged == True") \
           .build()

**Common Patterns:**

1. **Retry with Exponential Backoff:**

.. code-block:: python

   class RetryNode(CycleAwareNode):
       def run(self, context, **kwargs):
           iteration = self.get_iteration(context)
           max_retries = kwargs.get("max_retries", 3)

           try:
               result = perform_operation()
               return {"success": True, "result": result}
           except Exception as e:
               if iteration < max_retries:
                   delay = 2 ** iteration  # Exponential backoff
                   time.sleep(delay)
                   self.log_cycle_info(context, f"Retry {iteration + 1} after {delay}s")
                   return {"success": False, "retry": True}
               else:
                   return {"success": False, "error": str(e)}

2. **Data Quality Improvement:**

.. code-block:: python

   class QualityImproverNode(CycleAwareNode):
       def run(self, context, **kwargs):
           data = kwargs["data"]
           prev_state = self.get_previous_state(context)

           # Calculate quality score
           quality = calculate_quality(data)
           self.accumulate_values(context, "quality", quality)

           # Check if we're making progress
           trend = self.detect_convergence_trend(context, "quality")
           if trend["plateau_detected"]:
               self.log_cycle_info(context, "Quality plateau detected")

           # Improve data
           improved_data = improve_quality(data)

           return {
               "data": improved_data,
               "quality": quality,
               "converged": quality > 0.95 or trend["plateau_detected"]
           }

3. **Iterative Model Training:**

.. code-block:: python

   class TrainingNode(CycleAwareNode):
       def run(self, context, **kwargs):
           model = kwargs.get("model")
           data = kwargs["training_data"]
           iteration = self.get_iteration(context)

           # Train for one epoch
           loss = model.train_epoch(data)
           self.accumulate_values(context, "loss", loss)

           # Early stopping check
           trend = self.detect_convergence_trend(context, "loss")
           early_stop = trend["converging"] and trend["stability"] > 0.99

           # Save best model
           prev_best = self.get_previous_state(context).get("best_loss", float('inf'))
           if loss < prev_best:
               self.set_cycle_state({"best_loss": loss, "best_model": model.state_dict()})

           return {
               "model": model,
               "loss": loss,
               "converged": early_stop or iteration >= 100
           }

Data Nodes
==========

.. note::

   Additional data nodes are planned for future releases:

   - **XMLReader/XMLWriter**: For XML file processing
   - **ParquetReader/ParquetWriter**: For Apache Parquet columnar storage
   - **ExcelReader/ExcelWriter**: For Microsoft Excel files

   Track implementation progress in the `GitHub issues <https://github.com/your-org/kailash-sdk/issues>`_.


Data nodes handle input/output operations for various file formats and data
sources.

DirectoryReaderNode (New in v0.2.1)
------------------------------------

.. autoclass:: kailash.nodes.data.directory.DirectoryReaderNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.data import DirectoryReaderNode

   # Discover files dynamically
   dir_reader = DirectoryReaderNode(
       directory_path="./data/inputs",
       recursive=True,
       pattern="*.{csv,json,xml}",
       include_metadata=True
   )

   workflow.add_node("file_discoverer", dir_reader)

   # Use different outputs for different purposes
   workflow.connect(
       "file_discoverer", "csv_processor",
       mapping={"files_by_type": "files_by_type"}
   )

   workflow.connect(
       "file_discoverer", "stats_reporter",
       mapping={"directory_stats": "stats"}
   )

**Key Features:**

- Dynamic file discovery with pattern matching
- MIME type detection and metadata extraction
- Organized output by file type for typed processing
- Performance optimization for large directories
- Recursive scanning with configurable depth

Readers
-------

CSVReaderNode
~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.readers.CSVReaderNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash import Workflow
   from kailash.nodes.data import CSVReaderNode

   workflow = Workflow("csv_example")

   # Create the CSV reader node
   csv_reader = CSVReaderNode(
       file_path="customers.csv",
       encoding="utf-8"
   )

   # Add the node to the workflow
   workflow.add_node("read_customers", csv_reader)

JSONReaderNode
~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.readers.JSONReaderNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("JSONReaderNode", "read_config", config={
       "file_path": "config.json",
       "encoding": "utf-8"
   })

TextReaderNode
~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.readers.TextReaderNode
   :members:
   :undoc-members:
   :show-inheritance:



Writers
-------

CSVWriterNode
~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.writers.CSVWriterNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("CSVWriterNode", "save_results", config={
       "file_path": "output/results.csv",
       "index": False,
       "encoding": "utf-8"
   })

JSONWriterNode
~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.writers.JSONWriterNode
   :members:
   :undoc-members:
   :show-inheritance:

TextWriterNode
~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.writers.TextWriterNode
   :members:
   :undoc-members:
   :show-inheritance:



Database Nodes
--------------

SQLDatabaseNode
~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.sql.SQLDatabaseNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.data import SQLDatabaseNode

   # Direct configuration approach (recommended)
   db_node = SQLDatabaseNode(
       connection_string="sqlite:///data.db",
       pool_size=5,
       max_overflow=10
   )

   # Add to workflow
   workflow.add_node("database", db_node)

   # Execute with runtime parameters
   result = db_node.run(
       query="SELECT * FROM customers WHERE active = ?",
       parameters=[True],
       result_format="dict"
   )

   # PostgreSQL with advanced configuration
   pg_node = SQLDatabaseNode(
       connection_string="postgresql://user:pass@host/db",
       pool_size=10,
       max_overflow=20,
       pool_recycle=1800,
       connect_args={'connect_timeout': 10}
   )

   workflow.add_node("pg_database", pg_node)

   # MySQL example
   mysql_node = SQLDatabaseNode(
       connection_string="mysql+pymysql://user:pass@host/db",
       pool_size=8,
       echo=True  # Enable query logging
   )

   # Execute with different parameter styles
   # SQLite uses ?
   sqlite_result = db_node.run(
       query="SELECT * FROM users WHERE age > ? AND city = ?",
       parameters=[25, "New York"]
   )

   # PostgreSQL uses $1, $2, etc.
   pg_result = pg_node.run(
       query="SELECT * FROM users WHERE age > $1 AND city = $2",
       parameters=[25, "New York"]
   )

   # MySQL uses %s
   mysql_result = mysql_node.run(
       query="SELECT * FROM users WHERE age > %s AND city = %s",
       parameters=[25, "New York"]
   )

**Configuration Parameters:**

- **connection_string** (str, required): Database connection URL

  - SQLite: ``sqlite:///path/to/database.db``
  - PostgreSQL: ``postgresql://user:password@host:port/database``
  - MySQL: ``mysql+pymysql://user:password@host:port/database``

- **pool_size** (int, optional): Number of connections in pool (default: 5)
- **max_overflow** (int, optional): Maximum overflow connections (default: 10)
- **pool_timeout** (int, optional): Timeout to get connection from pool (default: 30)
- **pool_recycle** (int, optional): Time to recycle connections in seconds (default: 3600)
- **pool_pre_ping** (bool, optional): Test connections before use (default: True)
- **echo** (bool, optional): Enable SQLAlchemy query logging (default: False)
- **connect_args** (dict, optional): Additional database-specific connection arguments

**Runtime Parameters:**

- **query** (str, required): SQL query to execute
- **parameters** (list, optional): Query parameters for safe execution
- **result_format** (str, optional): Output format - 'dict', 'list', or 'raw' (default: 'dict')
- **timeout** (int, optional): Query timeout in seconds

**Security Features:**

- Parameterized queries prevent SQL injection
- Connection string password masking in logs
- Query safety validation warnings
- Identifier sanitization for dynamic SQL
- Error message sanitization

SharePoint Nodes
----------------

SharePointGraphReader
~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.sharepoint_graph.SharePointGraphReader
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("SharePointGraphReader", "read_docs", config={
       "tenant_id": "${TENANT_ID}",
       "client_id": "${CLIENT_ID}",
       "client_secret": "${CLIENT_SECRET}",
       "site_url": "https://company.sharepoint.com/sites/docs",
       "operation": "list_files",
       "library": "Shared Documents"
   })

SharePointGraphWriter
~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.sharepoint_graph.SharePointGraphWriter
   :members:
   :undoc-members:
   :show-inheritance:

Transform Nodes
===============

Transform nodes manipulate and process data.

FilterNode
----------

.. autoclass:: kailash.nodes.transform.processors.FilterNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.transform import FilterNode

   # Filter numbers greater than a value
   result = filter_node.run(
       data=[1, 2, 3, 4, 5],
       operator=">",
       value=3
   )  # Returns: {"filtered_data": [4, 5]}

   # Filter dictionaries by field
   users = [
       {"name": "Alice", "age": 30},
       {"name": "Bob", "age": 25},
       {"name": "Charlie", "age": 35}
   ]
   result = filter_node.run(
       data=users,
       field="age",
       operator=">=",
       value=30
   )  # Returns users 30 and older

   # String contains filtering
   items = [
       {"title": "Python Programming"},
       {"title": "Java Development"},
       {"title": "Python for Data Science"}
   ]
   result = filter_node.run(
       data=items,
       field="title",
       operator="contains",
       value="Python"
   )  # Returns items with "Python" in title

Map
---

.. autoclass:: kailash.nodes.transform.processors.Map
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("Map", "add_columns", config={
       "mapping": {
           "full_name": "lambda row: f'{row.first_name} {row.last_name}'",
           "is_vip": "lambda row: row.total_purchases > 10000",
           "category": "lambda row: 'Gold' if row.score > 80 else 'Silver'"
       }
   })

Sort
----

.. autoclass:: kailash.nodes.transform.processors.Sort
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   # Sort by field in ascending order
   workflow.add_node("Sort", "sort_by_age", config={
       "field": "age",
       "reverse": False
   })

   # Sort by multiple criteria
   workflow.add_node("Sort", "sort_complex", config={
       "field": "priority",
       "reverse": True  # Highest priority first
   })

DataTransformer (Enhanced in v0.2.1)
-------------------------------------

.. autoclass:: kailash.nodes.transform.processors.DataTransformer
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("DataTransformer", "transform", config={
       "operations": [
           {"type": "rename", "old": "cust_id", "new": "customer_id"},
           {"type": "cast", "column": "age", "dtype": "int"},
           {"type": "fillna", "column": "email", "value": "unknown@example.com"},
           {"type": "drop", "columns": ["temp_field", "debug_info"]}
       ]
   })

**Enhanced Parameter Mapping (v0.2.1):**

DataTransformer now accepts arbitrary mapped parameters from other nodes, enabling
more flexible data flow patterns:

.. code-block:: python

   # Connect with complex data mapping
   workflow.connect(
       "file_discoverer", "processor",
       mapping={
           "files_by_type": "files_by_type",
           "directory_stats": "stats",
           "metadata": "file_metadata"
       }
   )

   processor = DataTransformer(transformations=['''
   # All mapped parameters are now available
   files_by_type = locals().get("files_by_type", {})
   stats = locals().get("stats", {})
   metadata = locals().get("file_metadata", {})

   # Process the data
   csv_files = files_by_type.get("csv", [])
   result = {"processed_files": len(csv_files), "total_size": stats.get("total_size", 0)}
   '''])

**Bug Fixes in v0.2.1:**

- Fixed dictionary output bug where only keys were passed instead of full dictionaries
- Enhanced input validation to accept arbitrary mapped parameters
- Improved error handling and debugging capabilities

Text Processing
---------------

HierarchicalChunkerNode
~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.transform.chunkers.HierarchicalChunkerNode
   :members:
   :undoc-members:
   :show-inheritance:

ChunkTextExtractorNode
~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.transform.formatters.ChunkTextExtractorNode
   :members:
   :undoc-members:
   :show-inheritance:

QueryTextWrapperNode
~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.transform.formatters.QueryTextWrapperNode
   :members:
   :undoc-members:
   :show-inheritance:

ContextFormatterNode
~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.transform.formatters.ContextFormatterNode
   :members:
   :undoc-members:
   :show-inheritance:

Logic Nodes
===========

.. note::

   The **Validator** node for complex data validation rules is planned for a future release.


Logic nodes control workflow execution flow.

SwitchNode
----------

.. autoclass:: kailash.nodes.logic.operations.SwitchNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("SwitchNode", "route_by_value", config={
       "condition": "customer_segment",
       "routes": {
           "premium": "lifetime_value > 10000",
           "standard": "lifetime_value > 1000",
           "basic": "default"
       }
   })

MergeNode
---------

.. autoclass:: kailash.nodes.logic.operations.MergeNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("MergeNode", "combine_streams", config={
       "strategy": "concat",  # or "join", "union"
       "join_on": "customer_id",  # for join strategy
       "how": "left"  # for join strategy
   })

WorkflowNode
------------

.. autoclass:: kailash.nodes.logic.workflow.WorkflowNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.workflow import Workflow
   from kailash.nodes.logic import WorkflowNode

   # Create a reusable workflow
   data_processor = Workflow("data_processor")
   # ... add nodes to workflow ...

   # Wrap it as a node
   processor_node = WorkflowNode(workflow=data_processor)

   # Use in another workflow
   main_workflow = Workflow("main")
   main_workflow.add_node("process", processor_node)

   # Load from file
   file_processor = WorkflowNode(
       workflow_path="workflows/processor.yaml",
       name="file_processor"
   )

   # Custom parameter mapping
   custom_processor = WorkflowNode(
       workflow=data_processor,
       input_mapping={
           "rows": {"node": "reader", "parameter": "num_rows", "type": int}
       },
       output_mapping={
           "count": {"node": "writer", "output": "row_count", "type": int}
       }
   )

Validator
---------

.. note::
   🚧 **Coming Soon** - This node is planned for a future release.

**Planned Features:**
- Schema validation using JSON Schema
- Data quality checks
- Custom validation rules
- Error reporting and data cleansing

**Alternative:** Use the :doc:`PythonCodeNode <../api/nodes>` for custom
validation logic in the meantime.

AI/ML Nodes
===========

AI and machine learning nodes for intelligent processing.

Provider Architecture
---------------------

The AI nodes use a unified provider architecture that supports multiple LLM
and embedding providers:

.. automodule:: kailash.nodes.ai.ai_providers
   :members: get_provider, get_available_providers
   :undoc-members:

**Supported Providers:**

- **OpenAI**: GPT models and text embeddings
- **Anthropic**: Claude models (LLM only)
- **Ollama**: Local models for both LLM and embeddings
- **Cohere**: Embedding models
- **HuggingFace**: Embedding models (API and local)
- **Mock**: For testing without API keys

**Example: Check Available Providers**

.. code-block:: python

   from kailash.nodes.ai import get_available_providers

   # Check all providers
   providers = get_available_providers()
   for name, info in providers.items():
       if info['available']:
           print(f"{name}: ✓ Chat={info['chat']}, Embeddings={info['embeddings']}")

   # Check only LLM providers
   llm_providers = get_available_providers("chat")

   # Check only embedding providers
   embed_providers = get_available_providers("embeddings")

TextClassifier
--------------

.. autoclass:: kailash.nodes.ai.models.TextClassifier
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("TextClassifier", "sentiment", config={
       "model": "sentiment-analysis",
       "text_column": "review_text",
       "batch_size": 32
   })

EmbeddingGeneratorNode
----------------------

.. autoclass:: kailash.nodes.ai.embedding_generator.EmbeddingGeneratorNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.ai import EmbeddingGeneratorNode

   # Single text embedding
   embedder = EmbeddingGeneratorNode()
   result = embedder.run(
       provider="openai",
       model="text-embedding-3-large",
       input_text="This is a sample document to embed",
       operation="embed_text"
   )

   # Batch embedding with caching
   result = embedder.run(
       provider="huggingface",
       model="sentence-transformers/all-MiniLM-L6-v2",
       input_texts=["Document 1", "Document 2", "Document 3"],
       operation="embed_batch",
       batch_size=32,
       cache_enabled=True
   )

   # Calculate similarity between embeddings
   result = embedder.run(
       operation="calculate_similarity",
       embedding_1=[0.1, 0.2, 0.3, ...],
       embedding_2=[0.15, 0.25, 0.35, ...],
       similarity_metric="cosine"
   )

LLMAgentNode
------------

.. autoclass:: kailash.nodes.ai.llm_agent.LLMAgentNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.ai import LLMAgentNode

   # Basic question-answering
   agent = LLMAgentNode()
   result = agent.run(
       provider="openai",
       model="gpt-4",
       prompt="What is the capital of France?",
       operation="qa"
   )

   # Conversation with memory
   result = agent.run(
       provider="anthropic",
       model="claude-3-sonnet-20240229",
       prompt="Explain quantum computing",
       operation="conversation",
       memory_config={
           "type": "window",
           "window_size": 10
       }
   )

   # Tool calling with functions
   result = agent.run(
       provider="openai",
       model="gpt-4",
       prompt="What's the weather in Paris?",
       operation="tool_calling",
       tools=[{
           "type": "function",
           "function": {
               "name": "get_weather",
               "description": "Get current weather",
               "parameters": {
                   "type": "object",
                   "properties": {
                       "location": {"type": "string"}
                   }
               }
           }
       }]
   )

Self-Organizing Agents
======================

The Kailash SDK includes advanced self-organizing agent capabilities for autonomous
team formation and intelligent problem solving.

Agent-to-Agent Communication
----------------------------

SharedMemoryPoolNode
~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.a2a.SharedMemoryPoolNode
   :members:
   :undoc-members:
   :show-inheritance:

A2AAgentNode
~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.a2a.A2AAgentNode
   :members:
   :undoc-members:
   :show-inheritance:

A2ACoordinatorNode
~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.a2a.A2ACoordinatorNode
   :members:
   :undoc-members:
   :show-inheritance:

Intelligent Orchestration
-------------------------

IntelligentCacheNode
~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.intelligent_agent_orchestrator.IntelligentCacheNode
   :members:
   :undoc-members:
   :show-inheritance:

MCPAgentNode
~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.intelligent_agent_orchestrator.MCPAgentNode
   :members:
   :undoc-members:
   :show-inheritance:

QueryAnalysisNode
~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.intelligent_agent_orchestrator.QueryAnalysisNode
   :members:
   :undoc-members:
   :show-inheritance:

OrchestrationManagerNode
~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.intelligent_agent_orchestrator.OrchestrationManagerNode
   :members:
   :undoc-members:
   :show-inheritance:

ConvergenceDetectorNode
~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.intelligent_agent_orchestrator.ConvergenceDetectorNode
   :members:
   :undoc-members:
   :show-inheritance:

Self-Organizing Agent Pool
--------------------------

AgentPoolManagerNode
~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.self_organizing.AgentPoolManagerNode
   :members:
   :undoc-members:
   :show-inheritance:

ProblemAnalyzerNode
~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.self_organizing.ProblemAnalyzerNode
   :members:
   :undoc-members:
   :show-inheritance:

TeamFormationNode
~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.self_organizing.TeamFormationNode
   :members:
   :undoc-members:
   :show-inheritance:

SolutionEvaluatorNode
~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.self_organizing.SolutionEvaluatorNode
   :members:
   :undoc-members:
   :show-inheritance:

SelfOrganizingAgentNode
~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.self_organizing.SelfOrganizingAgentNode
   :members:
   :undoc-members:
   :show-inheritance:

**Complete Example:**

.. code-block:: python

   from kailash import Workflow
   from kailash.nodes.ai.intelligent_agent_orchestrator import OrchestrationManagerNode
   from kailash.runtime import LocalRuntime

   # Create a complete self-organizing agent workflow
   workflow = Workflow("self_organizing_demo")

   # Add the orchestration manager
   orchestrator = OrchestrationManagerNode()
   workflow.add_node("orchestrator", orchestrator)

   # Execute with a complex business query
   runtime = LocalRuntime()
   result, _ = runtime.execute(workflow, parameters={
       "orchestrator": {
           "query": "Analyze market trends and develop a growth strategy",
           "agent_pool_size": 8,
           "mcp_servers": [
               {"name": "market_data", "command": "mcp-market-server"},
               {"name": "financial_data", "command": "mcp-finance-server"}
           ],
           "quality_threshold": 0.85,
           "max_iterations": 3
       }
   })

   print(f"Solution quality: {result['orchestrator']['quality_score']:.2%}")
   print(f"Iterations completed: {result['orchestrator']['iterations_completed']}")

Agent Providers
---------------

ChatAgent
~~~~~~~~~

.. autoclass:: kailash.nodes.ai.agents.ChatAgent
   :members:
   :undoc-members:
   :show-inheritance:

RetrievalAgent
~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.agents.RetrievalAgent
   :members:
   :undoc-members:
   :show-inheritance:

Provider Infrastructure
-----------------------

BaseAIProvider
~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.ai_providers.BaseAIProvider
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

LLMProvider
~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.ai_providers.LLMProvider
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

EmbeddingProvider
~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.ai.ai_providers.EmbeddingProvider
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

API Nodes
=========

Nodes for external API integrations.

HTTPRequestNode
---------------

.. autoclass:: kailash.nodes.api.http.HTTPRequestNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.api import HTTPRequestNode

   # Simple GET request
   workflow.add_node("HTTPRequestNode", "fetch_data", config={
       "url": "https://api.example.com/data",
       "method": "GET",
       "headers": {
           "Authorization": "Bearer ${API_TOKEN}"
       },
       "timeout": 30
   })

   # POST with authentication
   workflow.add_node("HTTPRequestNode", "create_resource", config={
       "url": "https://api.example.com/resources",
       "method": "POST",
       "auth_type": "bearer",
       "auth_token": "${API_TOKEN}",
       "json_data": {
           "name": "New Resource",
           "type": "example"
       }
   })

RESTClientNode
--------------

.. autoclass:: kailash.nodes.api.rest.RESTClientNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.api import RESTClientNode

   # GET a resource
   workflow.add_node("RESTClientNode", "get_user", config={
       "base_url": "https://api.example.com",
       "resource": "users/{id}",
       "path_params": {"id": "123"},
       "method": "GET",
       "auth_type": "bearer",
       "auth_token": "${API_TOKEN}"
   })

   # Create a new resource
   workflow.add_node("RESTClientNode", "create_user", config={
       "base_url": "https://api.example.com",
       "resource": "users",
       "method": "POST",
       "data": {
           "name": "John Doe",
           "email": "john@example.com"
       },
       "version": "v2"
   })

GraphQLClient
-------------

.. note::
   🚧 **Coming Soon** - This node is planned for a future release.

**Planned Features:**
- GraphQL query and mutation support
- Variable binding and validation
- Schema introspection
- Subscription support

**Alternative:** Use the :doc:`PythonCodeNode <../api/nodes>` with GraphQL
libraries in the meantime.

MCP Nodes
=========

Model Context Protocol (MCP) nodes for AI context management.

MCPClient
---------

.. autoclass:: kailash.middleware.mcp.client_integration.MiddlewareMCPClient
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.mcp import MCPClient

   # List available resources
   client = MCPClient()
   result = client.run(
       server_config={
           "name": "filesystem-server",
           "command": "python",
           "args": ["-m", "mcp_filesystem"]
       },
       operation="list_resources"
   )

   # Read a specific resource
   result = client.run(
       server_config=server_config,
       operation="read_resource",
       resource_uri="file:///path/to/document.txt"
   )

   # Call a tool on the server
   result = client.run(
       server_config=server_config,
       operation="call_tool",
       tool_name="create_file",
       tool_arguments={
           "path": "/path/to/new_file.txt",
           "content": "Hello, World!"
       }
   )

Alert Nodes
============

Nodes for notifications and alerting systems.

DiscordAlertNode
----------------

.. autoclass:: kailash.nodes.alerts.discord.DiscordAlertNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.alerts import DiscordAlertNode

   # Basic alert
   alert = DiscordAlertNode()
   result = alert.run(
       webhook_url="https://discord.com/api/webhooks/...",
       title="System Alert",
       message="Service is running normally",
       alert_type="info"
   )

   # Rich alert with formatting
   result = alert.run(
       webhook_url="${DISCORD_WEBHOOK}",
       title="🚨 Critical Error",
       message="Database connection failed",
       alert_type="critical",
       username="System Monitor",
       mentions=["@here"],
       fields=[
           {"name": "Service", "value": "Database", "inline": True},
           {"name": "Status", "value": "Down", "inline": True},
           {"name": "Error", "value": "Connection timeout", "inline": False}
       ],
       footer_text="Automated alert from monitoring system"
   )

   # Business metrics alert
   result = alert.run(
       webhook_url="${DISCORD_WEBHOOK}",
       title="📊 Daily KPI Report",
       message="Daily performance metrics",
       alert_type="info",
       fields=[
           {"name": "Revenue", "value": "$45,231", "inline": True},
           {"name": "Orders", "value": "127", "inline": True},
           {"name": "Conversion", "value": "3.4%", "inline": True}
       ]
   )

**Key Features:**

- **Rich Discord Embeds**: Automatic color coding, custom fields, mentions
- **Rate Limiting**: Built-in 30 requests/minute sliding window protection
- **Retry Logic**: Exponential backoff with configurable attempts
- **Environment Variables**: Secure webhook URL substitution
- **Production Ready**: Comprehensive error handling and logging

**Alert Types and Colors:**

- ``info`` - Blue (0x3498db)
- ``success`` - Green (0x2ecc71)
- ``warning`` - Orange (0xf39c12)
- ``error`` - Red (0xe74c3c)
- ``critical`` - Dark red (0xc0392b)

**Runtime Parameters:**

- **webhook_url** (str, required): Discord webhook URL (supports ${DISCORD_WEBHOOK})
- **title** (str, required): Alert title
- **message** (str, optional): Alert message/description
- **alert_type** (str, optional): Alert severity - 'info', 'success', 'warning', 'error', 'critical'
- **username** (str, optional): Custom username for the bot
- **mentions** (list, optional): List of mentions (@everyone, @here, <@user_id>)
- **fields** (list, optional): List of embed fields with name, value, inline properties
- **footer_text** (str, optional): Footer text for the embed
- **retry_attempts** (int, optional): Number of retry attempts (default: 3)
- **retry_delay** (float, optional): Base retry delay in seconds (default: 1.0)

**Error Handling:**

- Automatic retry on rate limits and temporary failures
- Graceful degradation on webhook validation errors
- Comprehensive logging for debugging and monitoring
- Non-blocking execution - alerts won't crash workflows

Code Nodes
==========

Nodes for executing custom code.

PythonCodeNode (Enhanced in v0.2.1)
------------------------------------

.. autoclass:: kailash.nodes.code.python.PythonCodeNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   # Inline code execution
   workflow.add_node("PythonCodeNode", "process", config={
       "code": '''
   import pandas as pd

   # Access input data
   df = inputs["data"]

   # Process data
   result = df.groupby("category").agg({
       "revenue": "sum",
       "quantity": "count"
   })

   # Return results
   return {"summary": result}
   '''
   })

   # Execute from file
   workflow.add_node("PythonCodeNode", "analyze", config={
       "mode": "file",
       "file_path": "scripts/analysis.py"
   })

   # Call specific function
   workflow.add_node("PythonCodeNode", "transform", config={
       "mode": "function",
       "code": '''
   def process_data(df):
       df["processed"] = True
       return df.sort_values("timestamp")
   ''',
       "function_name": "process_data"
   })

**Enhanced File Processing (v0.2.1):**

PythonCodeNode now supports additional modules for real-world file processing:

.. code-block:: python

   # File processing with new modules
   file_processor = PythonCodeNode(name="file_processor", code='''
   import csv
   import pathlib
   import mimetypes
   import glob
   import xml.etree.ElementTree as ET

   # Process CSV files
   with open(file_path, 'r') as f:
       reader = csv.DictReader(f)
       data = list(reader)

   # Detect MIME types
   mime_type = mimetypes.guess_type(file_path)[0]

   # Modern path operations
   path = pathlib.Path(file_path)
   file_info = {
       "name": path.name,
       "size": path.stat().st_size,
       "suffix": path.suffix
   }

   # Pattern matching
   related_files = glob.glob(f"{path.parent}/*.{path.suffix[1:]}")

   result = {
       "data": data,
       "mime_type": mime_type,
       "file_info": file_info,
       "related_files": related_files
   }
   ''')

**New Allowed Modules (v0.2.1):**

- ``csv`` - CSV file processing
- ``mimetypes`` - MIME type detection
- ``pathlib`` - Modern path operations
- ``glob`` - File pattern matching
- ``xml`` - XML processing

These modules enable real-world data science and file processing workflows while
maintaining security restrictions for dangerous operations.

Custom Node Development
=======================

Creating custom nodes is straightforward:

.. code-block:: python

   from kailash.nodes import Node, register_node

   @register_node("MyCustomNode")
   class MyCustomNode(Node):
       """Custom node for specific processing."""

       def validate_config(self) -> None:
           """Validate node configuration."""
           required = ["param1", "param2"]
           for param in required:
               if param not in self.config:
                   raise ValueError(f"Missing required parameter: {param}")

       def execute(self, inputs: dict) -> dict:
           """Execute the node logic."""
           # Access configuration
           param1 = self.config["param1"]
           param2 = self.config["param2"]

           # Process inputs
           data = inputs.get("data")
           if data is None:
               raise ValueError("No input data provided")

           # Your custom logic here
           result = self.process_data(data, param1, param2)

           # Return outputs
           return {"processed_data": result}

       def process_data(self, data, param1, param2):
           """Custom processing logic."""
           # Implementation here
           return data

For async operations:

.. code-block:: python

   from kailash.nodes import AsyncNode
   import aiohttp

   @register_node("AsyncAPINode")
   class AsyncAPINode(AsyncNode):
       """Async node for API calls."""

       async def execute(self, inputs: dict) -> dict:
           """Execute async API call."""
           url = self.config["url"]

           async with aiohttp.ClientSession() as session:
               async with session.get(url) as response:
                   data = await response.json()

           return {"api_response": data}

Node Configuration Best Practices
=================================

1. **Use Environment Variables for Secrets**

.. code-block:: python

   workflow.add_node("RESTClientNode", "api", config={
       "auth": {
           "token": "${API_TOKEN}"  # Resolved from environment
       }
   })

2. **Provide Sensible Defaults**

.. code-block:: python

   class MyNode(Node):
       def validate_config(self):
           # Set defaults
           self.config.setdefault("timeout", 30)
           self.config.setdefault("retry_count", 3)

3. **Validate Early and Clearly**

.. code-block:: python

   def validate_config(self):
       if not os.path.exists(self.config["file_path"]):
           raise ValueError(f"File not found: {self.config['file_path']}")

4. **Document Configuration Options**

.. code-block:: python

   class MyNode(Node):
       """
       My custom node.

       Config:
           file_path (str): Path to input file
           encoding (str, optional): File encoding. Defaults to 'utf-8'
           skip_errors (bool, optional): Skip errors. Defaults to False
       """

See Also
========

- :doc:`/guides/custom_nodes` - Guide to creating custom nodes
- :doc:`/best_practices` - Best practices for node usage
- :doc:`/examples/index` - Example workflows using various nodes
