# Mistake 065: Multi-Node Input Aggregation Without MergeNode

## Problem
When multiple nodes need to send their outputs to a single aggregating node (like PythonCodeNode), directly connecting them causes data access issues and namespace conflicts.

## Symptoms
```
NameError: name 'data' is not defined
Input type not allowed: <class 'NoneType'>
WARNING: Source output '' not found in node 'agent1'. Available outputs: ['response', 'success', ...]
```

## What Happened
In `workflow_mcp_agentic.py`, three LLMAgentNode instances were connected directly to a PythonCodeNode aggregator:
```python
# ❌ WRONG: Direct connections from multiple nodes
workflow.connect("analysis_agent", "aggregator", mapping={"": "data1"})
workflow.connect("strategy_agent", "aggregator", mapping={"": "data2"})
workflow.connect("recommendation_agent", "aggregator", mapping={"": "data3"})
```

This caused:
1. **Empty mapping conflicts**: `""` didn't match any output field
2. **Multiple input confusion**: PythonCodeNode couldn't handle 3 separate inputs
3. **Data access errors**: Variables were undefined in the execution namespace

## Root Cause
**Missing merge pattern for multi-node inputs.** When multiple nodes feed into one node, you need an explicit merge step to combine the data properly.

## Solution: Use MergeNode Pattern

### ✅ CORRECT Pattern:
```python
# 1. Add MergeNode
from kailash.nodes.logic import MergeNode
workflow.add_node("merger", MergeNode(name="merger"))

# 2. Connect all source nodes to MergeNode
workflow.connect("analysis_agent", "merger", mapping={"response": "data1"})
workflow.connect("strategy_agent", "merger", mapping={"response": "data2"})
workflow.connect("recommendation_agent", "merger", mapping={"response": "data3"})

# 3. Connect MergeNode to aggregator
workflow.connect("merger", "aggregator", mapping={"merged_data": "merged_data"})

# 4. Handle merged data in PythonCodeNode
code="""
# merged_data comes as a list from MergeNode (concat mode)
if isinstance(merged_data, list) and len(merged_data) >= 3:
    analysis = merged_data[0]      # data1
    strategy = merged_data[1]      # data2
    recommendations = merged_data[2]  # data3
else:
    analysis = {}
    strategy = {}
    recommendations = {}

# Now process each agent's response safely
result = {
    "analysis_success": analysis.get("finish_reason") == "stop",
    "strategy_success": strategy.get("finish_reason") == "stop",
    "recommendations_success": recommendations.get("finish_reason") == "stop"
}
"""
```

## Key Learning
**Multi-node → Single node = Use MergeNode**

This pattern applies whenever you have:
- Multiple agents feeding into one aggregator
- Parallel processing branches that need to be combined
- Any scenario where N nodes → 1 node

## MergeNode Details
- **Input parameters**: `data1`, `data2`, `data3`, `data4`, `data5` (up to 5 inputs)
- **Output**: `merged_data` (list in concat mode, default)
- **Merge types**: `concat` (list), `zip` (tuples), `merge_dict` (dict merge)

## Prevention
1. **Design review**: When you see multiple arrows pointing to one node, ask "Do I need a MergeNode?"
2. **Connection mapping**: Empty string `""` mappings are usually wrong
3. **Data flow validation**: Trace how data flows through multi-input scenarios

## Related Patterns
- Switch/Merge pattern for conditional flows
- Fan-out/Fan-in for parallel processing
- Agent coordination workflows

## Files Updated
- `examples/workflow_examples/workflow_mcp_agentic.py` - Fixed with MergeNode pattern
- This mistake documentation
