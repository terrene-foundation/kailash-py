# ADR-0013: Simplify Conditional Logic Nodes

## Status
Accepted

## Context
The Kailash SDK currently includes four different nodes for conditional logic and data manipulation in the `kailash.nodes.logic.operations` module:

1. **SwitchNode** - Routes data to different outputs based on conditions
2. **MergeNode** - Combines multiple data sources in various ways
3. **Aggregator** - Aggregates data based on grouping and operations (count, sum, avg, etc.)
4. **Conditional** - Simple if/then/else conditional logic

Analysis of codebase usage revealed that:
- The SwitchNode and MergeNode nodes are used extensively in examples and are sufficient for all conditional routing needs
- The Aggregator node functionality is more appropriately handled by DataTransformer nodes or Python code nodes
- The Conditional node is redundant with SwitchNode functionality (simpler subset of SwitchNode)
- No examples or tests directly use the Aggregator or Conditional nodes

Having four different nodes for related functionality increases API complexity and cognitive load for users who must decide which node type to use for their specific case.

## Decision
We will simplify the conditional logic nodes by removing the **Aggregator** and **Conditional** nodes, keeping only the **SwitchNode** and **MergeNode** nodes.

This decision is based on the following rationale:
1. **SwitchNode** node already provides all the functionality of the **Conditional** node, plus more sophisticated multi-case routing
2. **Aggregator** node functionality can be implemented using **DataTransformer** nodes
3. No existing examples or tests depend directly on the removed nodes
4. Reducing API surface area reduces complexity for users and maintenance burden

## Consequences

### Positive
- Simpler API with fewer overlapping choices
- Clearer guidance for users on which node to use for conditional logic
- Reduced maintenance burden for the codebase
- Easier onboarding for new developers
- Better focus of development resources on improving the core nodes

### Negative
- Users who may have wanted a simpler conditional node will need to use the more powerful SwitchNode node
- Custom code will be needed for data aggregation operations

## Implementation
1. Remove Aggregator and Conditional classes from `kailash.nodes.logic.operations.py`
2. Update the module docstring and imports in `kailash.nodes.logic.__init__.py`
3. Update any documentation or examples that reference these nodes
4. Ensure tests continue to pass without these nodes

## Implementation Notes

The simplification has been successfully implemented:
- Aggregator and Conditional classes have been removed from `kailash.nodes.logic.operations.py`
- Module imports and documentation have been updated accordingly
- All tests continue to pass without these nodes
- Examples have been verified to work with just SwitchNode and MergeNode nodes

## References
- [ADR-0012: Workflow Conditional Routing](0012-workflow-conditional-routing.md)
