Troubleshooting
===============

This guide helps you diagnose and resolve common issues when working with the Kailash
Python SDK.

Installation Issues
-------------------

Python Version Compatibility
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Problem**: ImportError or syntax errors when importing kailash

**Solution**:

.. code-block:: bash

    # Check Python version
    python --version

    # Kailash requires Python 3.9+
    # If using older version, upgrade Python

    # For macOS (using Homebrew)
    brew install python@3.11

    # For Ubuntu/Debian
    sudo apt update
    sudo apt install python3.11

    # For Windows, download from python.org

Dependency Conflicts
^^^^^^^^^^^^^^^^^^^^

**Problem**: Package dependency conflicts during installation

**Solution**:

.. code-block:: bash

    # Create clean virtual environment
    python -m venv kailash_env
    source kailash_env/bin/activate  # On Windows: kailash_env\Scripts\activate

    # Upgrade pip
    pip install --upgrade pip

    # Install kailash
    pip install kailash

    # If still having issues, try installing specific versions
    pip install "networkx>=2.8,<3.0" "pydantic>=1.10,<2.0"

Missing Optional Dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Problem**: ModuleNotFoundError for optional features

**Solution**:

.. code-block:: bash

    # For visualization features
    pip install "kailash[viz]"

    # For all optional dependencies
    pip install "kailash[all]"

    # Individual optional packages
    pip install pygraphviz  # Advanced visualization
    pip install matplotlib  # Basic plotting
    pip install pandas      # Data processing

Node Development Issues
-----------------------

Import Errors
^^^^^^^^^^^^^

**Problem**: Cannot import custom nodes or base classes

**Symptoms**:

.. code-block:: text

    ImportError: cannot import name 'Node' from 'kailash.nodes.base'

**Solution**:

.. code-block:: python

    # Correct import patterns
    from kailash.nodes.base import Node
    from kailash.nodes.data.readers import CSVReaderNode
    from kailash.workflow.builder import WorkflowBuilder

    # Check if package is properly installed
    import kailash
    print(kailash.__version__)

Configuration Validation Errors
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Problem**: Pydantic validation errors in node configuration

**Symptoms**:

.. code-block:: text

    pydantic.error_wrappers.ValidationError: 1 validation error for NodeConfig
    field_name
      field required (type=value_error.missing)

**Solution**:

.. code-block:: python

    # Define proper configuration schema
    from kailash.nodes.base import Node
    from pydantic import BaseModel, Field
    from typing import Optional, Dict, Any

    class MyNodeConfig(BaseModel):
        required_field: str = Field(..., description="This field is required")
        optional_field: Optional[int] = Field(None, description="This field is optional")

        class Config:
            # Allow extra fields if needed
            extra = "allow"

    # Example custom node using the config
    class MyNode(Node):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.config_model = MyNodeConfig(**kwargs)

        def get_parameters(self):
            return {}

        def run(self, **kwargs):
            return {"success": True, "data": "processed"}

    # Ensure all required fields are provided
    config = {
        "required_field": "value",  # Don't forget required fields
        "optional_field": 42
    }

    node = MyNode(**config)

Node Execution Failures
^^^^^^^^^^^^^^^^^^^^^^^

**Problem**: Nodes fail during execution with unclear errors

**Debug Steps**:

.. code-block:: python

    import logging

    # Enable debug logging
    logging.basicConfig(level=logging.DEBUG)

    class DebugNode(Node):
        def execute(self, inputs):
            try:
                self.logger.debug(f"Inputs received: {inputs}")

                # Validate inputs
                if not inputs:
                    raise ValueError("No inputs provided")

                # Your processing logic here
                result = self.process_data(inputs)

                self.logger.debug(f"Processing complete: {result}")
                return {"success": True, "data": result}

            except Exception as e:
                self.logger.error(f"Node execution failed: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

Workflow Execution Issues
-------------------------

Circular Dependencies
^^^^^^^^^^^^^^^^^^^^^

**Problem**: Workflow fails to execute due to circular references

**Symptoms**:

.. code-block:: text

    WorkflowError: Circular dependency detected in workflow graph

**Solution**:

.. code-block:: python

    import networkx as nx

    # Check for cycles before execution
    def validate_workflow(workflow):
        graph = workflow.graph

        # NetworkX has built-in cycle detection
        import networkx as nx

        if not nx.is_directed_acyclic_graph(graph):
            cycles = list(nx.simple_cycles(graph))
            raise ValueError(f"Circular dependencies found: {cycles}")

    # Example usage
    class MockWorkflow:
        def __init__(self):
            self.graph = nx.DiGraph()

    my_workflow = MockWorkflow()

    # Use workflow validation
    try:
        validate_workflow(my_workflow)
        # result = my_workflow.execute(inputs)
        print("Workflow is valid")
    except ValueError as e:
        print(f"Workflow validation failed: {e}")

Missing Node Dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^

**Problem**: Workflow execution fails because nodes can't find their dependencies

**Symptoms**:

.. code-block:: text

    KeyError: 'expected_input_key'

**Solution**:

.. code-block:: python

    import networkx as nx

    # Debug workflow connections
    def debug_workflow_connections(workflow):
        for node_id, node in workflow.nodes.items():
            print(f"Node: {node_id}")

            # Check incoming edges
            predecessors = list(workflow.graph.predecessors(node_id))
            print(f"  Inputs from: {predecessors}")

            # Check outgoing edges
            successors = list(workflow.graph.successors(node_id))
            print(f"  Outputs to: {successors}")

            # Check edge data (input/output mappings)
            for pred in predecessors:
                edge_data = workflow.graph.get_edge_data(pred, node_id)
                print(f"  Edge {pred} -> {node_id}: {edge_data}")

    # Example workflow mock for testing
    class MockWorkflow:
        def __init__(self):
            self.nodes = {"node1": "mock", "node2": "mock"}
            self.graph = nx.DiGraph()
            self.graph.add_edge("node1", "node2")

    my_workflow = MockWorkflow()

    # Use before execution
    debug_workflow_connections(my_workflow)

Data Passing Issues
^^^^^^^^^^^^^^^^^^^

**Problem**: Data not properly passed between nodes

**Solution**:

.. code-block:: python

    # Ensure consistent output format from nodes
    class ConsistentOutputNode(Node):
        def execute(self, inputs):
            try:
                result = self.process(inputs)

                # Always return structured output
                return {
                    "success": True,
                    "data": result,
                    "metadata": {
                        "node_id": self.node_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "metadata": {
                        "node_id": self.node_id,
                        "error_type": type(e).__name__
                    }
                }

    # Check data flow between nodes
    def trace_data_flow(workflow, inputs):
        results = {}

        for node_id in nx.topological_sort(workflow.graph):
            node = workflow.nodes[node_id]

            # Collect inputs from predecessors
            node_inputs = {}
            for pred in workflow.graph.predecessors(node_id):
                pred_output = results[pred]
                if pred_output.get("success"):
                    node_inputs.update(pred_output["data"])

            # Add initial inputs for source nodes
            if not node_inputs:
                node_inputs = inputs

            # Execute node
            result = node.execute(node_inputs)
            results[node_id] = result

            print(f"Node {node_id}: {result}")

        return results

Memory and Performance Issues
-----------------------------

Memory Leaks
^^^^^^^^^^^^

**Problem**: Memory usage continuously increases during workflow execution

**Diagnosis**:

.. code-block:: python

    import psutil
    import gc
    import objgraph

    def monitor_memory_usage():
        process = psutil.Process()
        memory_info = process.memory_info()
        print(f"RSS: {memory_info.rss / 1024 / 1024:.2f} MB")
        print(f"VMS: {memory_info.vms / 1024 / 1024:.2f} MB")

        # Show most common objects
        objgraph.show_most_common_types(limit=10)

    def debug_memory_leaks():
        # Take snapshots before and after execution
        gc.collect()
        before = objgraph.typestats()

        # Execute your workflow
        workflow.execute(inputs)

        gc.collect()
        after = objgraph.typestats()

        # Show growth
        objgraph.show_growth(limit=10)

**Solutions**:

.. code-block:: python

    # Explicit cleanup in nodes
    class MemoryEfficientNode(Node):
        def execute(self, inputs):
            large_data = None
            try:
                large_data = self.load_large_dataset(inputs)
                result = self.process_in_chunks(large_data)
                return {"success": True, "data": result}
            finally:
                # Explicit cleanup
                del large_data
                gc.collect()

    # Use context managers for resource management
    from contextlib import contextmanager

    @contextmanager
    def managed_large_data(file_path):
        data = load_large_file(file_path)
        try:
            yield data
        finally:
            del data
            gc.collect()

Slow Execution
^^^^^^^^^^^^^^

**Problem**: Workflow execution is slower than expected

**Profiling**:

.. code-block:: python

    import cProfile
    import pstats
    from memory_profiler import profile

    # Profile execution time
    def profile_workflow_execution():
        profiler = cProfile.Profile()
        profiler.enable()

        # Execute workflow
        result = workflow.execute(inputs)

        profiler.disable()

        # Analyze results
        stats = pstats.Stats(profiler)
        stats.sort_stats('cumulative')
        stats.print_stats(20)  # Top 20 functions

        return result

    # Profile memory usage
    @profile
    def memory_profile_execution():
        return workflow.execute(inputs)

**Optimization**:

.. code-block:: python

    # Parallel execution for independent nodes
    from concurrent.futures import ThreadPoolExecutor

    def execute_parallel_nodes(workflow, inputs):
        # Find nodes that can run in parallel
        ready_nodes = find_ready_nodes(workflow)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(node.execute, inputs): node_id
                for node_id, node in ready_nodes.items()
            }

            results = {}
            for future in futures:
                node_id = futures[future]
                results[node_id] = future.result()

            return results

Cyclic Workflow Issues
----------------------

Infinite Loops
^^^^^^^^^^^^^^

**Problem**: Workflow runs indefinitely without converging

**Symptoms**:

.. code-block:: text

    WARNING: Reached maximum iterations (1000) without convergence

**Solutions**:

.. code-block:: python

    # 1. Always set convergence conditions
    workflow.create_cycle("processing_cycle") \
            .connect("processor", "processor") \
            .max_iterations(100) \
            .converge_when("converged == True or error < 0.001") \
            .build()

    # 2. Implement proper convergence logic in your node
    class MyNode(CycleAwareNode):
        def run(self, context, **kwargs):
            iteration = self.get_iteration(context)

            # Always provide a convergence flag
            converged = (
                iteration >= 50 or           # Max iterations
                self.result_good_enough() or # Domain-specific check
                self.no_improvement()        # Plateau detection
            )

            return {"converged": converged, ...}

State Management Errors
^^^^^^^^^^^^^^^^^^^^^^^

**Problem**: State not persisting between iterations

**Common Mistakes**:

.. code-block:: python

    # Wrong: Forgetting to use CycleAwareNode helpers
    class BadNode(Node):  # Should inherit from CycleAwareNode
        def run(self, context, **kwargs):
            # This won't work properly in cycles
            self.state = {"value": 1}  # Lost between iterations

    # Correct: Using CycleAwareNode properly
    class GoodNode(CycleAwareNode):
        def run(self, context, **kwargs):
            prev_state = self.get_previous_state(context)
            new_value = prev_state.get("value", 0) + 1
            self.set_cycle_state({"value": new_value})

Parameter Mapping Issues
^^^^^^^^^^^^^^^^^^^^^^^^

**Problem**: Cycle parameters not being passed correctly

**Solutions**:

.. code-block:: python

    # For PythonCodeNode - use nested path mapping
    workflow.create_cycle("processor_cycle") \
            .connect("processor", "processor", mapping={"result.count": "count"}) \
            .build()

    # For regular nodes - use direct mapping
    workflow.create_cycle("optimizer_cycle") \
            .connect("optimizer", "optimizer", mapping={"value": "input_value"}) \
            .build()

    # Debug parameter flow
    class DebugNode(CycleAwareNode):
        def run(self, context, **kwargs):
            self.log_cycle_info(context, f"Received params: {kwargs}")
            # Your logic here

Connection Parameter Issues (v0.8.4+)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Problem**: Connection parameter validation errors or security issues

**Symptoms**:

.. code-block:: text

    # Connection validation warnings or errors
    runtime.execute(workflow, parameters={"node": {"param": "value"}})
    # May show validation warnings or block execution

**Enhanced Connection Validation**:

.. code-block:: python

    from kailash.runtime.local import LocalRuntime

    # Step 1: Enable connection validation
    runtime = LocalRuntime(
        connection_validation="strict"    # Block invalid connections
    )

    # Step 2: Execute with monitoring
    try:
        results, run_id = runtime.execute(workflow, parameters=params)
    except Exception as e:
        print(f"Connection validation failed: {e}")

    # Step 3: Check validation metrics
    metrics = runtime.get_validation_metrics()
    print(f"Performance: {metrics['performance_summary']}")
    print(f"Security: {metrics['security_report']}")

**Common Connection Issues and Solutions**:

1. **Connection Parameter Mapping**

   **Problem**: Parameters not properly mapped through connections

   .. code-block:: python

       # ❌ WRONG - 2-parameter connection (deprecated)
       workflow.connect("source", "target")

       # ✅ CORRECT - 4-parameter connection with explicit mapping
       workflow.add_connection(
           "source_node", "output_key",    # Source
           "target_node", "input_key"      # Target
       )

2. **Runtime Parameter Precedence**

   **Problem**: Understanding parameter precedence order

   .. code-block:: python

       # Parameter precedence (highest to lowest):
       # 1. Runtime parameters (highest)
       # 2. Connection parameters
       # 3. Node configuration (lowest)

       workflow.add_node("ProcessorNode", "process", {
           "batch_size": 100  # Lowest precedence
       })

       workflow.add_connection("source", "size", "process", "batch_size")
       # Connection parameters override node config

       runtime.execute(workflow, parameters={
           "process": {"batch_size": 500}  # Highest precedence - this wins
       })

3. **Connection Security Validation**

   **Problem**: Preventing parameter injection through connections

   .. code-block:: python

       # Enable strict validation for security
       runtime = LocalRuntime(connection_validation="strict")

       # Monitor security violations
       metrics = runtime.get_validation_metrics()
       security_report = metrics["security_report"]

       if security_report["violations_detected"] > 0:
           print("Security violations detected!")
           for violation in security_report["violations"]:
               print(f"  {violation}")

**Connection Validation Modes**:

.. code-block:: python

    # Development - strict validation
    dev_runtime = LocalRuntime(
        connection_validation="strict"    # Block invalid connections
    )

    # Production - warnings only
    prod_runtime = LocalRuntime(
        connection_validation="warn"      # Log warnings, continue execution
    )

    # Performance - no validation
    perf_runtime = LocalRuntime(
        connection_validation="off"       # No validation overhead
    )

Data Processing Errors
----------------------

File I/O Issues
^^^^^^^^^^^^^^^

**Problem**: Unable to read/write files

**Common Solutions**:

.. code-block:: python

    from pathlib import Path
    import os

    def safe_file_operations(file_path):
        path = Path(file_path)

        # Check if file exists
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Check permissions
        if not os.access(path, os.R_OK):
            raise PermissionError(f"No read permission: {file_path}")

        # Check file size
        if path.stat().st_size > 100 * 1024 * 1024:  # 100MB
            print(f"Warning: Large file detected ({path.stat().st_size} bytes)")

        # Safe reading with context manager
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # Try different encoding
            with open(path, 'r', encoding='latin-1') as f:
                return f.read()

Data Type Mismatches
^^^^^^^^^^^^^^^^^^^^

**Problem**: Type errors when processing data between nodes

**Solution**:

.. code-block:: python

    from typing import Union, Any
    import pandas as pd

    def safe_type_conversion(value: Any, target_type: type):
        """Safely convert values between types."""
        try:
            if target_type == str:
                return str(value)
            elif target_type == int:
                if isinstance(value, str):
                    return int(float(value))  # Handle "1.0" -> 1
                return int(value)
            elif target_type == float:
                return float(value)
            elif target_type == bool:
                if isinstance(value, str):
                    return value.lower() in ('true', '1', 'yes', 'on')
                return bool(value)
            else:
                return target_type(value)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Cannot convert {value} to {target_type}: {e}")

    # Validate data schemas
    def validate_dataframe_schema(df: pd.DataFrame, expected_columns: dict):
        """Validate DataFrame has expected columns and types."""
        missing_columns = set(expected_columns.keys()) - set(df.columns)
        if missing_columns:
            raise ValueError(f"Missing columns: {missing_columns}")

        for col, expected_type in expected_columns.items():
            if df[col].dtype != expected_type:
                try:
                    df[col] = df[col].astype(expected_type)
                except Exception as e:
                    raise ValueError(f"Cannot convert column {col} to {expected_type}: {e}")

Testing and Debugging
---------------------

Unit Test Failures
^^^^^^^^^^^^^^^^^^

**Problem**: Tests fail with unclear error messages

**Solution**:

.. code-block:: python

    import pytest
    from unittest.mock import Mock, patch

    class TestNodeExecution:
        def test_node_with_detailed_assertions(self):
            node = MyNode("test_id", {"param": "value"})
            inputs = {"data": [1, 2, 3]}

            result = node.execute(inputs)

            # Detailed assertions
            assert isinstance(result, dict), f"Expected dict, got {type(result)}"
            assert "success" in result, f"Missing 'success' key in {result.keys()}"
            assert result["success"] is True, f"Execution failed: {result.get('error')}"

            if result["success"]:
                assert "data" in result, "Missing 'data' key in successful result"
                assert len(result["data"]) > 0, "Empty data in result"

        def test_error_handling(self):
            node = MyNode("test_id", {"param": "value"})
            invalid_inputs = None

            result = node.execute(invalid_inputs)

            assert result["success"] is False
            assert "error" in result
            assert isinstance(result["error"], str)

Integration Test Issues
^^^^^^^^^^^^^^^^^^^^^^^

**Problem**: Integration tests fail in CI/CD but pass locally

**Solution**:

.. code-block:: python

    import tempfile
    import os

    def test_with_isolated_environment():
        """Test with completely isolated environment."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Use temporary directory for all file operations
            input_file = os.path.join(temp_dir, "input.csv")
            output_file = os.path.join(temp_dir, "output.csv")

            # Create test data
            with open(input_file, 'w') as f:
                f.write("name,age\\nJohn,30\\nJane,25")

            # Configure nodes to use temporary files
            config = {
                "input_file": input_file,
                "output_file": output_file
            }

            workflow = create_test_workflow(config)
            result = workflow.execute({})

            assert result["success"] is True
            assert os.path.exists(output_file)

Getting Help
------------

Enabling Debug Logging
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import logging

    # Enable comprehensive logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('kailash_debug.log'),
            logging.StreamHandler()
        ]
    )

    # Enable specific logger
    kailash_logger = logging.getLogger('kailash')
    kailash_logger.setLevel(logging.DEBUG)

Collecting Diagnostic Information
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import sys
    import platform
    import kailash

    def collect_diagnostics():
        """Collect system information for bug reports."""
        info = {
            "python_version": sys.version,
            "platform": platform.platform(),
            "kailash_version": kailash.__version__,
            "installed_packages": []
        }

        try:
            import pkg_resources
            installed = [str(d) for d in pkg_resources.working_set]
            info["installed_packages"] = sorted(installed)
        except Exception:
            pass

        return info

    # Include this information when reporting issues
    print(collect_diagnostics())
