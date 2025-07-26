# Logic & Control Flow Nodes

**Module**: `kailash.nodes.logic`
**Last Updated**: 2025-01-06

This document covers control flow and logic nodes including conditional routing, data merging, and workflow composition.

## Table of Contents
- [Conditional Routing](#conditional-routing)
- [Data Merging](#data-merging)
- [Workflow Composition](#workflow-composition)

## Conditional Routing

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
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  # Simple boolean condition
  switch_node = SwitchNode(condition_field="status", operator="==", value="success")

  ```

### AsyncSwitchNode
- **Module**: `kailash.nodes.logic.async_operations`
- **Purpose**: Asynchronously routes data to different outputs based on conditions
- **Features**:
  - Efficient for I/O-bound condition evaluation
  - Handles large datasets with complex routing criteria
  - Integrates with other async nodes in workflows
- **Parameters**: Same as SwitchNode
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  import asyncio
  async_switch = AsyncSwitchNode(condition_field="status", operator="==", value="active")
  result = asyncio.run(async_switch.execute_async(
      input_data={"status": "active", "data": "test"}
  ))

  ```

## Data Merging

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
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  # Simple list concatenation
  merge_node = MergeNode(merge_type="concat")
  result = merge_node.execute(data1=[1, 2], data2=[3, 4])
  # result['merged_data'] = [1, 2, 3, 4]

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
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  import asyncio
  async_merge = AsyncMergeNode(merge_type="concat")
  result = asyncio.run(async_merge.execute_async(data1=[1, 2], data2=[3, 4]))

  ```

## Workflow Composition

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
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  # Direct workflow wrapping
workflow = WorkflowBuilder()
workflow.graph import Workflow
  inner_workflow = WorkflowBuilder()
workflow.  node = WorkflowNode(workflow=inner_workflow)

  ```

## See Also
- [Transform Nodes](06-transform-nodes.md) - Data processing and transformation
- [AI Nodes](02-ai-nodes.md) - AI and ML capabilities
- [API Reference](../api/06-nodes-logic.yaml) - Detailed API documentation
