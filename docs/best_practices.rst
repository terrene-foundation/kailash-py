Best Practices
==============

This guide outlines best practices for developing with the Kailash Python SDK.

Node Development
----------------

Creating Custom Nodes
^^^^^^^^^^^^^^^^^^^^^

When creating custom nodes, follow these patterns:

.. code-block:: python

    from kailash.nodes.base import Node
    from typing import Dict, Any, Optional
    from pydantic import BaseModel, Field

    class MyCustomNodeConfig(BaseModel):
        """Configuration schema for MyCustomNode."""
        parameter: str = Field(..., description="Required parameter")
        optional_param: Optional[int] = Field(None, description="Optional parameter")

    class MyCustomNode(Node):
        """
        Custom node for specific business logic.

        Example:
            >>> from kailash.nodes.base import Node
            >>> node = MyCustomNode(
            ...     node_id="custom_1",
            ...     config={"parameter": "value"}
            ... )
            >>> result = node.execute({"input": "data"})
        """

        def __init__(self, node_id: str, config: Dict[str, Any]):
            super().__init__(node_id, config)
            self.config_model = MyCustomNodeConfig(**config)

        def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
            """Execute the node logic."""
            try:
                # Validate inputs
                self.validate_inputs(inputs)

                # Process data
                result = self._process_data(inputs)

                # Return structured output
                return {
                    "success": True,
                    "data": result,
                    "metadata": {"processed_at": "2024-01-01T00:00:00Z"}
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "metadata": {"error_type": type(e).__name__}
                }

**Key Principles:**

1. **Use Pydantic for Configuration**: Define configuration schemas using
   Pydantic models
2. **Input Validation**: Always validate inputs before processing
3. **Structured Output**: Return consistent output formats with success indicators
4. **Error Handling**: Catch and handle exceptions gracefully
5. **Documentation**: Include comprehensive docstrings with examples

Data Handling
^^^^^^^^^^^^^

**File Processing:**

.. code-block:: python

    import pandas as pd
    from pathlib import Path

    def safe_file_read(file_path: str) -> pd.DataFrame:
        """Safely read CSV files with error handling."""
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            return pd.read_csv(path)
        except Exception as e:
            raise ValueError(f"Failed to read file {file_path}: {e}")

**Memory Management:**

.. code-block:: python

    import pandas as pd

    def process_large_dataset(data: pd.DataFrame, chunk_size: int = 10000):
        """Process large datasets in chunks to manage memory."""
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i + chunk_size]
            yield process_chunk(chunk)

Workflow Design
---------------

Workflow Patterns
^^^^^^^^^^^^^^^^^

**Linear Processing:**

.. code-block:: python

    from kailash.workflow.builder import WorkflowBuilder

    def create_linear_workflow():
        """Create a simple linear processing workflow."""
        builder = WorkflowBuilder()

        # Add nodes in sequence
        builder.add_node("reader", "CSVReaderNode", {"file_path": "input.csv"})
        builder.add_node("processor", "DataProcessor", {"operation": "clean"})
        builder.add_node("writer", "CSVWriterNode", {"file_path": "output.csv"})

        # Connect nodes
        builder.add_edge("reader", "processor")
        builder.add_edge("processor", "writer")

        return builder.build()

**Parallel Processing:**

.. code-block:: python

    def create_parallel_workflow():
        """Create workflow with parallel processing branches."""
        builder = WorkflowBuilder()

        # Input node
        builder.add_node("input", "CSVReaderNode", {"file_path": "data.csv"})

        # Parallel processing branches
        builder.add_node("process_a", "ProcessorA", {})
        builder.add_node("process_b", "ProcessorB", {})

        # Merge results
        builder.add_node("merge", "DataMerger", {})

        # Connect parallel branches
        builder.add_edge("input", "process_a")
        builder.add_edge("input", "process_b")
        builder.add_edge("process_a", "merge")
        builder.add_edge("process_b", "merge")

        return builder.build()

**Conditional Routing:**

.. code-block:: python

    def create_conditional_workflow():
        """Create workflow with conditional logic."""
        builder = WorkflowBuilder()

        builder.add_node("input", "CSVReaderNode", {})
        builder.add_node("validator", "DataValidator", {})
        builder.add_node("clean_data", "DataCleaner", {})
        builder.add_node("reject_data", "DataRejector", {})

        # Add conditional routing
        builder.add_conditional_edge(
            "validator",
            condition=lambda x: x.get("valid", False),
            true_target="clean_data",
            false_target="reject_data"
        )

        return builder.build()

Error Handling
--------------

Node-Level Error Handling
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from kailash.nodes.base import Node

    class RobustNode(Node):
        """Node with comprehensive error handling."""

        def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
            try:
                # Validate inputs
                self._validate_inputs(inputs)

                # Process with retries
                result = self._execute_with_retry(inputs)

                return {"success": True, "data": result}

            except ValidationError as e:
                return {
                    "success": False,
                    "error": f"Input validation failed: {e}",
                    "error_type": "validation"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "error_type": "execution"
                }

        def _execute_with_retry(self, inputs: Dict[str, Any], max_retries: int = 3):
            """Execute with retry logic."""
            for attempt in range(max_retries):
                try:
                    return self._core_logic(inputs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(2 ** attempt)  # Exponential backoff

Workflow-Level Error Handling
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    def create_error_resilient_workflow():
        """Create workflow with error handling and recovery."""
        builder = WorkflowBuilder()

        # Main processing path
        builder.add_node("processor", "DataProcessor", {})
        builder.add_node("validator", "ResultValidator", {})

        # Error handling path
        builder.add_node("error_handler", "ErrorHandler", {})
        builder.add_node("fallback", "FallbackProcessor", {})

        # Add error routing
        builder.add_error_handler("processor", "error_handler")
        builder.add_edge("error_handler", "fallback")

        return builder.build()

Testing Strategies
------------------

Unit Testing Nodes
^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import pytest
    from unittest.mock import Mock, patch

    class TestMyCustomNode:
        """Test suite for MyCustomNode."""

        def test_successful_execution(self):
            """Test successful node execution."""
            node = MyCustomNode("test_node", {"parameter": "test"})
            inputs = {"input": "test_data"}

            result = node.execute(inputs)

            assert result["success"] is True
            assert "data" in result

        def test_input_validation(self):
            """Test input validation."""
            node = MyCustomNode("test_node", {"parameter": "test"})
            invalid_inputs = {}

            result = node.execute(invalid_inputs)

            assert result["success"] is False
            assert "error" in result

        @patch('mymodule.external_api_call')
        def test_with_mocked_dependencies(self, mock_api):
            """Test node with mocked external dependencies."""
            mock_api.return_value = {"status": "ok"}

            node = MyCustomNode("test_node", {"parameter": "test"})
            result = node.execute({"input": "data"})

            mock_api.assert_called_once()
            assert result["success"] is True

Integration Testing Workflows
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    class TestWorkflowIntegration:
        """Integration tests for complete workflows."""

        def test_end_to_end_workflow(self, tmp_path):
            """Test complete workflow execution."""
            # Setup test data
            input_file = tmp_path / "input.csv"
            input_file.write_text("name,age\\nJohn,30\\nJane,25")

            # Create workflow
            workflow = create_linear_workflow()

            # Execute workflow
            result = workflow.execute({"input_file": str(input_file)})

            # Verify results
            assert result["success"] is True
            assert (tmp_path / "output.csv").exists()

Performance Optimization
------------------------

Memory Management
^^^^^^^^^^^^^^^^^

.. code-block:: python

    import gc
    from memory_profiler import profile

    @profile
    def memory_efficient_processing(large_dataset):
        """Process large datasets efficiently."""
        # Process in chunks
        chunk_size = 10000
        for i in range(0, len(large_dataset), chunk_size):
            chunk = large_dataset[i:i + chunk_size]

            # Process chunk
            processed = process_chunk(chunk)

            # Yield results immediately
            yield processed

            # Clean up references
            del chunk, processed
            gc.collect()

Parallel Execution
^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
    import multiprocessing as mp

    def parallel_node_execution(nodes, inputs):
        """Execute multiple nodes in parallel."""
        # Use ThreadPoolExecutor for I/O-bound tasks
        with ThreadPoolExecutor(max_workers=mp.cpu_count()) as executor:
            futures = {
                executor.submit(node.execute, inputs): node
                for node in nodes
            }

            results = {}
            for future in futures:
                node = futures[future]
                try:
                    results[node.node_id] = future.result(timeout=30)
                except Exception as e:
                    results[node.node_id] = {"success": False, "error": str(e)}

            return results

Caching Strategies
^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from functools import lru_cache
    import hashlib
    import pickle

    from kailash.nodes.base import Node

    class CacheableNode(Node):
        """Node with built-in caching capabilities."""

        def __init__(self, node_id: str, config: Dict[str, Any]):
            super().__init__(node_id, config)
            self.cache = {}

        def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
            """Execute with caching."""
            cache_key = self._generate_cache_key(inputs)

            if cache_key in self.cache:
                return self.cache[cache_key]

            result = self._execute_logic(inputs)
            self.cache[cache_key] = result

            return result

        def _generate_cache_key(self, inputs: Dict[str, Any]) -> str:
            """Generate cache key from inputs."""
            serialized = pickle.dumps(inputs, protocol=pickle.HIGHEST_PROTOCOL)
            return hashlib.md5(serialized).hexdigest()

Monitoring and Logging
----------------------

Performance Monitoring
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import time
    import logging
    from functools import wraps

    def monitor_performance(func):
        """Decorator to monitor function performance."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            memory_before = get_memory_usage()

            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                memory_after = get_memory_usage()

                logging.info(f"{func.__name__} completed in {execution_time:.2f}s")
                logging.info(f"Memory usage: {memory_after - memory_before:.2f}MB")

                return result
            except Exception as e:
                logging.error(f"{func.__name__} failed: {e}")
                raise

        return wrapper

Structured Logging
^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import logging
    import json
    from datetime import datetime

    class StructuredLogger:
        """Structured logging for workflow execution."""

        def __init__(self, name: str):
            self.logger = logging.getLogger(name)
            self.logger.setLevel(logging.INFO)

        def log_node_execution(self, node_id: str, inputs: dict, outputs: dict):
            """Log node execution details."""
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "event": "node_execution",
                "node_id": node_id,
                "input_size": len(str(inputs)),
                "output_size": len(str(outputs)),
                "success": outputs.get("success", False)
            }

            self.logger.info(json.dumps(log_entry))

Security Considerations
-----------------------

Input Sanitization
^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import re
    from pathlib import Path

    def sanitize_file_path(file_path: str) -> str:
        """Sanitize file paths to prevent directory traversal."""
        # Remove dangerous patterns
        sanitized = re.sub(r'\.\./', '', file_path)
        sanitized = re.sub(r'\.\.\\', '', sanitized)

        # Ensure path is within allowed directory
        path = Path(sanitized).resolve()
        allowed_dir = Path("/allowed/directory").resolve()

        if not str(path).startswith(str(allowed_dir)):
            raise ValueError("Path outside allowed directory")

        return str(path)

Configuration Validation
^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from pydantic import BaseModel, validator

    class SecureNodeConfig(BaseModel):
        """Secure configuration with validation."""

        api_key: str
        file_path: str

        @validator('api_key')
        def validate_api_key(cls, v):
            if len(v) < 32:
                raise ValueError('API key too short')
            return v

        @validator('file_path')
        def validate_file_path(cls, v):
            return sanitize_file_path(v)

Cyclic Workflow Best Practices
------------------------------

Designing Cyclic Workflows
^^^^^^^^^^^^^^^^^^^^^^^^^^

When building iterative workflows, follow these patterns:

.. code-block:: python

    from kailash import Workflow
    from kailash.nodes.base_cycle_aware import CycleAwareNode
    from typing import Dict, Any

    class IterativeProcessorNode(CycleAwareNode):
        """Best practices for cycle-aware nodes."""

        def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
            # 1. Always get iteration info first
            iteration = self.get_iteration(context)
            prev_state = self.get_previous_state(context)

            # 2. Handle first iteration gracefully
            if iteration == 0:
                # Initialize state
                current_value = kwargs.get("initial_value", 0)
                self.log_cycle_info(context, "Starting iterative process")
            else:
                # Use previous state
                current_value = prev_state.get("value", 0)

            # 3. Perform processing
            new_value = self.process_value(current_value)

            # 4. Track metrics for convergence
            self.accumulate_values(context, "value", new_value)
            trend = self.detect_convergence_trend(context, "value")

            # 5. Save state for next iteration
            self.set_cycle_state({
                "value": new_value,
                "history": prev_state.get("history", []) + [new_value]
            })

            # 6. Determine convergence with multiple criteria
            converged = (
                new_value > 0.95 or                    # Threshold reached
                trend["converging"] or                 # Trending toward convergence
                trend["plateau_detected"] or           # No improvement
                iteration >= self.max_iterations - 1   # Safety limit
            )

            # 7. Return structured output
            return {
                "value": new_value,
                "converged": converged,
                "iteration": iteration,
                "improvement": new_value - current_value
            }

Cycle Safety Guidelines
^^^^^^^^^^^^^^^^^^^^^^^

1. **Always Set Convergence Conditions**:

.. code-block:: python

    # Good: Multiple convergence criteria
    workflow.create_cycle("processing_cycle") \
            .connect("processor", "processor") \
            .max_iterations(100) \
            .converge_when("converged == True or error < 0.001") \
            .build()

    # Bad: No convergence check - NEVER DO THIS!
    # workflow.connect("processor", "processor", cycle=True)  # Dangerous!

2. **Use Reasonable Iteration Limits**:

.. code-block:: python

    # Consider the problem domain
    workflow.create_cycle("optimizer_cycle") \
            .connect("optimizer", "optimizer") \
            .max_iterations(1000) \
            .converge_when("loss < 0.01") \
            .build()

    workflow.create_cycle("retry_cycle") \
            .connect("retry", "retry") \
            .max_iterations(5) \
            .converge_when("success == True") \
            .build()

3. **Implement Memory Management**:

.. code-block:: python

    class MemoryEfficientCycleNode(CycleAwareNode):
        def run(self, context, **kwargs):
            # Limit history size
            MAX_HISTORY = 100

            prev_state = self.get_previous_state(context)
            history = prev_state.get("history", [])

            # Trim history to prevent memory growth
            if len(history) > MAX_HISTORY:
                history = history[-MAX_HISTORY:]

            # Process and update
            result = self.process_data(kwargs["data"])
            history.append(result["metric"])

            self.set_cycle_state({"history": history})
            return result

Performance Optimization for Cycles
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from kailash.runtime.parallel_cyclic import ParallelCyclicRuntime

    # Use parallel runtime for independent cycles
    runtime = ParallelCyclicRuntime(
        max_workers=4,
        cycle_batch_size=10  # Process multiple iterations in parallel
    )

    # Example: Parallel optimization with multiple starting points
    workflow = Workflow("parallel_optimization")

    # Add multiple optimizers
    for i in range(4):
        workflow.add_node(f"optimizer_{i}", OptimizerNode())
        workflow.create_cycle(f"optimizer_{i}_cycle") \
                .connect(f"optimizer_{i}", f"optimizer_{i}") \
                .max_iterations(100) \
                .converge_when("converged == True") \
                .build()

    # Execute all optimizers in parallel
    results = runtime.execute(workflow, parameters={
        f"optimizer_{i}": {"initial_value": i * 0.25}
        for i in range(4)
    })

Common Pitfalls to Avoid
^^^^^^^^^^^^^^^^^^^^^^^^

1. **Incorrect Edge Marking**:

.. code-block:: python

    # Wrong: Marking all edges as cycles - DEPRECATED PATTERN
    # workflow.connect("A", "B", cycle=True)  # ❌
    # workflow.connect("B", "C", cycle=True)  # ❌
    # workflow.connect("C", "A", cycle=True)  # ❌

    # Correct: Use CycleBuilder API
    workflow.connect("A", "B")    # ✓ Regular forward edge
    workflow.connect("B", "C")    # ✓ Regular forward edge
    workflow.create_cycle("abc_cycle") \
            .connect("C", "A") \
            .max_iterations(50) \
            .converge_when("converged == True") \
            .build()              # ✓ Cycle with proper configuration

2. **Poor State Management**:

.. code-block:: python

    # Wrong: Storing entire datasets in state
    self.set_cycle_state({"full_dataset": large_dataframe})  # ❌

    # Correct: Store only essential state
    self.set_cycle_state({
        "summary_stats": dataframe.describe().to_dict(),
        "row_count": len(dataframe),
        "quality_score": calculate_quality(dataframe)
    })  # ✓

3. **Missing Error Handling**:

.. code-block:: python

    class RobustCycleNode(CycleAwareNode):
        def run(self, context, **kwargs):
            iteration = self.get_iteration(context)

            try:
                result = self.process_data(kwargs["data"])
                return {"success": True, "result": result}
            except Exception as e:
                # Log error with context
                self.log_cycle_info(context,
                    f"Error at iteration {iteration}: {str(e)}")

                # Decide whether to continue
                if iteration < 3:  # Retry a few times
                    return {"success": False, "retry": True}
                else:
                    # Give up and converge
                    return {"success": False, "error": str(e),
                            "converged": True}
