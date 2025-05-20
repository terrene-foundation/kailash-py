# ADR-0012: Workflow Conditional Routing

## Status
Accepted

## Context
Workflows in the Kailash SDK need to support conditional branching to enable more complex and dynamic execution paths. Currently, the workflow system executes nodes in a linear fashion based on a directed acyclic graph (DAG), with no built-in support for conditional routing.

Real-world workflows often require different execution paths based on data values, error conditions, user preferences, or other runtime factors. For example:
- Processing data differently based on its type or content
- Handling error conditions with separate recovery paths
- Implementing business logic with multiple branches
- Allowing users to configure workflow behavior dynamically

Without conditional routing, users must either:
1. Implement complex internal conditionals within nodes, making workflows less transparent
2. Create separate workflows for different conditions and manage them externally
3. Build overly complex graphs with redundant nodes and connections

## Decision
We will implement workflow conditional routing through specialized nodes rather than modifying the core workflow execution engine, specifically:

1. **Switch Node**: A specialized node that:
   - Evaluates conditions on input data
   - Routes data to different outputs based on the condition result
   - Supports both boolean (true/false) conditions and multi-case switching
   - Creates named output fields corresponding to condition results

2. **Enhanced Merge Node**: A node that:
   - Combines multiple data sources into a single output
   - Supports various merge strategies (concat, zip, merge_dict)
   - Can handle more than two inputs
   - Includes options for handling None values and conflicts

The workflow graph structure remains a DAG, with conditional logic implemented through the connectivity pattern:
- A Switch node with multiple outputs connected to different processing branches
- Each branch processes data independently
- Branches can reconnect using Merge nodes

## Rationale

We considered three alternative approaches:

### 1. Modify Core Workflow Engine
- **Pros**: Could offer cleaner expression of conditional logic in workflow definition
- **Cons**: 
  - Significantly complicates workflow execution and state management
  - Requires rethinking the DAG model and topological sort approach
  - Higher risk of breaking existing workflow functionality
  - More difficult to visualize and debug

### 2. External Workflow Controller
- **Pros**: Keeps workflow execution simple
- **Cons**:
  - Requires users to implement and manage multiple workflows
  - Makes the overall process less transparent
  - More complex to deploy and manage

### 3. Node-Based Approach (chosen)
- **Pros**:
  - Maintains the DAG nature of workflows
  - No changes to core execution engine required
  - More intuitive for users familiar with visual programming
  - Easier to visualize and debug
  - Consistent with existing node-based design philosophy
- **Cons**:
  - Slightly more verbose workflow definitions
  - Less "native" expression of conditions compared to programming languages

We chose the node-based approach because it offers the best balance of power, simplicity, and compatibility with the existing system. It also aligns with the SDK's design philosophy of composable nodes.

## Consequences

### Positive
- Users can create complex workflows with dynamic execution paths
- Workflows remain visualizable as DAGs
- No breaking changes to existing workflow execution
- Better separation of concerns between data processing and flow control
- Enables more sophisticated use cases like error handling, complex business logic
- Can be extended with additional specialized routing nodes in the future

### Negative
- Conditional branching may create more complex workflow graphs
- Users need to understand the Switch/Merge pattern for effective implementation
- Some conditional logic might be less efficient due to data duplication between branches
- Complex conditions might be more difficult to express compared to code

## Implementation Notes

The implementation consists of the following components:

1. **Switch Node**
```python
class Switch(Node):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        # Parameters include input_data, condition_field, operator, value, cases, etc.
        
    def run(self, **kwargs) -> Dict[str, Any]:
        # If boolean condition: Set true_output or false_output
        # If multi-case: Create dynamic case_X outputs
        # Always include condition_result
```

2. **Enhanced Merge Node**
```python
class Merge(Node):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        # Parameters include data1-data5, merge_type, key, skip_none
        
    def run(self, **kwargs) -> Dict[str, Any]:
        # Collect all data inputs
        # Apply merge according to merge_type
        # Return merged_data
```

3. **Usage Example**:
```python
# Create workflow with conditional branching
workflow = Workflow(name="Conditional Example")

# Add nodes
workflow.add_node("data_source", DataSourceNode())
workflow.add_node("router", Switch(condition_field="status"))
workflow.add_node("success_handler", SuccessProcessor())
workflow.add_node("error_handler", ErrorProcessor())
workflow.add_node("results_merger", Merge(merge_type="merge_dict"))

# Connect with conditional branching
workflow.connect("data_source", "router", {"output": "input_data"})
workflow.connect("router", "success_handler", {"true_output": "input"})
workflow.connect("router", "error_handler", {"false_output": "input"})
workflow.connect("success_handler", "results_merger", {"output": "data1"})
workflow.connect("error_handler", "results_merger", {"output": "data2"})
```

## References
- [NetworkX Directed Acyclic Graphs](https://networkx.org/documentation/stable/reference/classes/digraph.html)
- [Switch Case statements in programming](https://en.wikipedia.org/wiki/Switch_statement)
- Related ADRs:
  - [ADR-0002: Workflow Representation](0002-workflow-representation.md)
  - [ADR-0004: Workflow Representation](0004-workflow-representation.md)
  - [ADR-0005: Local Execution Strategy](0005-local-execution-strategy.md)