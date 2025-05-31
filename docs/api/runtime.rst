=======
Runtime
=======

This section covers the runtime execution engines available in the Kailash SDK.

.. contents:: Table of Contents
   :local:
   :depth: 2

Overview
========

The Kailash SDK provides multiple runtime engines for executing workflows:

- **LocalRuntime**: Synchronous execution on the local machine
- **AsyncLocalRuntime**: Asynchronous execution for I/O-bound operations
- **ParallelRuntime**: Parallel execution using multiprocessing
- **DockerRuntime**: Isolated execution in Docker containers
- **TestingRuntime**: Mock runtime for testing

Runtime Selection
=================

Runtimes are automatically selected based on the workflow configuration:

.. code-block:: python

   from kailash import Workflow, RuntimeConfig

   # Default: LocalRuntime
   workflow = Workflow("my_workflow")

   # Async runtime for I/O operations
   workflow = Workflow("async_workflow", runtime="async")

   # Parallel runtime for CPU-intensive tasks
   workflow = Workflow("parallel_workflow", runtime="parallel")

   # Docker runtime for isolation
   workflow = Workflow("docker_workflow", runtime="docker")

LocalRuntime
============

The default runtime for synchronous execution.

.. autoclass:: kailash.runtime.local.LocalRuntime
   :members:
   :undoc-members:
   :show-inheritance:

**Characteristics:**

- Executes nodes sequentially
- Good for debugging and development
- Lower overhead for simple workflows
- Direct access to local filesystem

**Example Usage:**

.. code-block:: python

   from kailash.runtime import LocalRuntime
   from kailash import Workflow

   workflow = Workflow("local_example")
   runtime = LocalRuntime()

   # Add nodes...

   # Execute with local runtime
   results = runtime.execute(workflow)

AsyncLocalRuntime
=================

Asynchronous runtime for I/O-bound operations.

.. autoclass:: kailash.runtime.async_local.AsyncLocalRuntime
   :members:
   :undoc-members:
   :show-inheritance:

**Characteristics:**

- Concurrent execution of async nodes
- Efficient for API calls and file I/O
- Better resource utilization
- Requires async-compatible nodes

**Example Usage:**

.. code-block:: python

   from kailash.runtime import AsyncLocalRuntime
   import asyncio

   workflow = Workflow("async_example")
   runtime = AsyncLocalRuntime()

   # Add async nodes
   workflow.add_node("AsyncHTTPClient", "fetch1", config={"url": "..."})
   workflow.add_node("AsyncHTTPClient", "fetch2", config={"url": "..."})

   # Execute asynchronously
   async def run():
       results = await runtime.execute_async(workflow)
       return results

   results = asyncio.run(run())

ParallelRuntime
===============

Parallel execution using multiprocessing.

.. autoclass:: kailash.runtime.parallel.ParallelRuntime
   :members:
   :undoc-members:
   :show-inheritance:

**Configuration Options:**

.. code-block:: python

   from kailash.runtime import ParallelRuntime

   runtime = ParallelRuntime(
       max_workers=4,              # Number of worker processes
       chunk_size=1000,           # Data chunk size for parallelization
       memory_limit="2GB",        # Memory limit per worker
       timeout=300               # Execution timeout in seconds
   )

**Example Usage:**

.. code-block:: python

   workflow = Workflow("parallel_example")

   # Configure parallel execution
   workflow.add_node("DataProcessor", "process", config={
       "parallel": True,
       "chunk_column": "id",
       "chunks": 10
   })

   runtime = ParallelRuntime(max_workers=8)
   results = runtime.execute(workflow)

**Best Practices:**

1. **CPU-Bound Tasks**: Use for computationally intensive operations
2. **Data Parallelism**: Split large datasets into chunks
3. **Resource Management**: Monitor memory usage per worker
4. **Avoid Shared State**: Ensure nodes are stateless

DockerRuntime
=============

Execute nodes in isolated Docker containers.

.. autoclass:: kailash.runtime.docker.DockerRuntime
   :members:
   :undoc-members:
   :show-inheritance:

**Configuration:**

.. code-block:: python

   from kailash.runtime import DockerRuntime

   runtime = DockerRuntime(
       base_image="python:3.9-slim",
       network_mode="bridge",
       volumes={
           "/local/data": {
               "bind": "/container/data",
               "mode": "rw"
           }
       },
       environment={
           "PYTHONPATH": "/app"
       }
   )

**Node-Specific Docker Config:**

.. code-block:: python

   workflow.add_node("PythonCodeNode", "secure_execution", config={
       "code": "...",
       "docker": {
           "image": "sandboxed-python:latest",
           "memory": "512m",
           "cpu_shares": 512,
           "read_only": True
       }
   })

**Security Features:**

- Process isolation
- Resource limits (CPU, memory)
- Network isolation
- Filesystem sandboxing
- Custom security profiles

TestingRuntime
==============

Mock runtime for unit testing workflows.

.. autoclass:: kailash.runtime.testing.TestingRuntime
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.runtime import TestingRuntime

   # Configure mock responses
   runtime = TestingRuntime()
   runtime.set_node_response("read_data", {
       "data": pd.DataFrame({"id": [1, 2, 3], "value": [10, 20, 30]})
   })
   runtime.set_node_response("process", {
       "result": {"total": 60}
   })

   # Test workflow execution
   results = runtime.execute(workflow)
   assert results["process"]["result"]["total"] == 60

**Testing Patterns:**

.. code-block:: python

   import pytest
   from kailash.runtime import TestingRuntime

   @pytest.fixture
   def mock_runtime():
       runtime = TestingRuntime()

       # Configure common responses
       runtime.set_node_response("api_call", {
           "status": 200,
           "data": {"message": "success"}
       })

       # Simulate errors
       runtime.set_node_error("failing_node",
           ValueError("Simulated error"))

       return runtime

   def test_workflow(mock_runtime):
       workflow = create_workflow()
       results = mock_runtime.execute(workflow)

       # Verify execution
       assert mock_runtime.get_execution_order() == [
           "input", "process", "output"
       ]
       assert mock_runtime.get_node_call_count("process") == 1

Runtime Comparison
==================

.. list-table:: Runtime Feature Comparison
   :widths: 20 20 20 20 20
   :header-rows: 1

   * - Feature
     - Local
     - Async
     - Parallel
     - Docker
   * - Execution Model
     - Sequential
     - Concurrent
     - Parallel
     - Isolated
   * - Best For
     - Development
     - I/O Tasks
     - CPU Tasks
     - Security
   * - Overhead
     - Low
     - Low
     - Medium
     - High
   * - Resource Limits
     - No
     - No
     - Yes
     - Yes
   * - Isolation
     - None
     - None
     - Process
     - Container

Custom Runtime Development
==========================

Create custom runtimes by extending the base class:

.. code-block:: python

   from kailash.runtime.runner import BaseRuntime
   from typing import Dict, Any

   class CloudRuntime(BaseRuntime):
       """Execute workflows in cloud environments."""

       def __init__(self, cloud_config: dict):
           super().__init__()
           self.cloud_config = cloud_config
           self.client = self._init_cloud_client()

       def execute_node(self, node, inputs: Dict[str, Any]) -> Dict[str, Any]:
           """Execute a single node in the cloud."""
           # Package node and inputs
           payload = {
               "node_type": type(node).__name__,
               "config": node.config,
               "inputs": inputs
           }

           # Submit to cloud execution service
           job_id = self.client.submit_job(payload)

           # Wait for completion
           result = self.client.wait_for_job(job_id)

           return result

       def execute(self, workflow) -> Dict[str, Any]:
           """Execute entire workflow in the cloud."""
           # Upload workflow definition
           workflow_id = self.client.upload_workflow(workflow.to_dict())

           # Execute remotely
           execution_id = self.client.execute_workflow(workflow_id)

           # Monitor and return results
           return self.client.get_results(execution_id)

Performance Optimization
========================

Local Runtime
-------------

.. code-block:: python

   # Use caching for repeated operations
   workflow.add_node("CachedDataReader", "read", config={
       "file_path": "large_file.csv",
       "cache": True,
       "cache_ttl": 3600  # 1 hour
   })

Async Runtime
-------------

.. code-block:: python

   # Batch async operations
   workflow.add_node("BatchAPIClient", "fetch", config={
       "urls": ["url1", "url2", "url3"],
       "batch_size": 10,
       "max_concurrent": 5
   })

Parallel Runtime
----------------

.. code-block:: python

   # Optimize chunk size
   from kailash.runtime import ParallelRuntime

   # Calculate optimal chunk size
   data_size = 1_000_000
   num_workers = 8
   chunk_size = data_size // (num_workers * 4)  # 4 chunks per worker

   runtime = ParallelRuntime(
       max_workers=num_workers,
       chunk_size=chunk_size
   )

Docker Runtime
--------------

.. code-block:: python

   # Pre-build images with dependencies
   runtime = DockerRuntime(
       base_image="myapp:latest",  # Pre-built with all dependencies
       pull_policy="if_not_present",
       warm_containers=2  # Keep containers warm
   )

Error Handling
==============

Different runtimes handle errors differently:

.. code-block:: python

   from kailash.runtime import RuntimeError

   try:
       results = runtime.execute(workflow)
   except RuntimeError as e:
       print(f"Runtime error: {e}")

       # Access error details
       if hasattr(e, "node_id"):
           print(f"Failed at node: {e.node_id}")

       if hasattr(e, "partial_results"):
           print(f"Completed nodes: {list(e.partial_results.keys())}")

Runtime-Specific Error Handling:

.. code-block:: python

   # Async runtime
   try:
       results = await async_runtime.execute_async(workflow)
   except asyncio.TimeoutError:
       print("Async execution timed out")

   # Parallel runtime
   try:
       results = parallel_runtime.execute(workflow)
   except MemoryError:
       print("Worker ran out of memory")
       # Reduce chunk size or worker count

   # Docker runtime
   try:
       results = docker_runtime.execute(workflow)
   except DockerException as e:
       print(f"Container error: {e}")
       # Check container logs
       logs = docker_runtime.get_container_logs(e.container_id)

Monitoring and Metrics
======================

Track runtime performance:

.. code-block:: python

   from kailash.runtime import RuntimeMetrics

   # Enable metrics collection
   runtime = LocalRuntime(collect_metrics=True)

   # Execute workflow
   results = runtime.execute(workflow)

   # Access metrics
   metrics = runtime.get_metrics()
   print(f"Total execution time: {metrics.total_time}s")
   print(f"Node execution times: {metrics.node_times}")
   print(f"Memory usage: {metrics.memory_usage}")

   # Export metrics
   metrics.export("runtime_metrics.json")

See Also
========

- :doc:`nodes` - Node types and development
- :doc:`workflow` - Workflow construction
- :doc:`tracking` - Execution tracking
- :doc:`../guides/performance` - Performance optimization guide
- :doc:`../examples/runtime` - Runtime usage examples
