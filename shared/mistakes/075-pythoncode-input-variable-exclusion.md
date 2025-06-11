# Mistake 075: PythonCodeNode Input Variable Exclusion

## Summary
PythonCodeNode excludes input variables from its output, causing issues when trying to reassign variables that were passed as inputs.

## The Problem
When using PythonCodeNode, if you:
1. Map an output to a variable name (e.g., `mapping={"result": "result"}`)
2. Try to reassign that same variable in your code
3. The reassigned value won't be included in the output

This is because PythonCodeNode's `execute_code` method filters out variables that were in the inputs to avoid circular references.

## Example of the Bug
```python
# WRONG: This will fail
workflow.connect("node1", "node2", mapping={"result": "result"})

# In node2's PythonCodeNode:
code = """
# result is available as input
data = result.get("data")

# But reassigning result won't work!
result = {"processed": data}  # This won't be in output!
"""
```

## Root Cause
In `src/kailash/nodes/code/python.py`, the `execute_code` method:
```python
# Return all non-private variables that weren't in inputs
return {
    k: v
    for k, v in namespace.items()
    if not k.startswith("_")
    and k not in sanitized_inputs  # <-- Excludes input variables!
    and k not in self.allowed_modules
}
```

## Solution
Map to different variable names to avoid the conflict:

```python
# CORRECT: Use different variable names
workflow.connect("node1", "node2", mapping={"result": "input_data"})

# In node2's PythonCodeNode:
code = """
# input_data is available as input
data = input_data.get("data")

# Now we can create result as a new variable
result = {"processed": data}  # This WILL be in output!
"""
```

## Common Scenarios

### Scenario 1: Processing Pipeline
```python
# WRONG
workflow.connect("discovery", "processor", mapping={"result": "result"})

# CORRECT
workflow.connect("discovery", "processor", mapping={"result": "discovery_data"})
```

### Scenario 2: Result Aggregation
```python
# WRONG
workflow.connect("merger", "summarizer", mapping={"result": "result"})

# CORRECT
workflow.connect("merger", "summarizer", mapping={"result": "merged_data"})
```

### Scenario 3: Multi-Stage Processing
```python
# WRONG - all using "data"
workflow.connect("reader", "transformer", mapping={"data": "data"})
workflow.connect("transformer", "writer", mapping={"data": "data"})

# CORRECT - unique names
workflow.connect("reader", "transformer", mapping={"data": "raw_data"})
workflow.connect("transformer", "writer", mapping={"result": "transformed_data"})
```

## Best Practices

1. **Use descriptive variable names** that indicate the data's purpose:
   - `discovery_data`, `raw_data`, `processed_data`
   - `user_input`, `validation_result`, `final_output`

2. **Avoid generic names** for mapped inputs:
   - Don't use: `result`, `data`, `output`
   - Do use: `csv_data`, `api_response`, `aggregated_results`

3. **Document the mapping** in comments:
   ```python
   # Map discovery results to 'files_found' variable
   workflow.connect("scanner", "processor",
                   mapping={"discovered_files": "files_found"})
   ```

4. **For chained processing**, use stage-specific names:
   ```python
   workflow.connect("stage1", "stage2", mapping={"result": "stage1_output"})
   workflow.connect("stage2", "stage3", mapping={"result": "stage2_output"})
   ```

## Related Issues
- DataTransformer dict bug (passes only keys)
- Workflow parameter passing patterns
- Node output validation errors

## Prevention
When designing workflows with PythonCodeNode:
1. Plan your variable names upfront
2. Use unique names for each connection
3. Test with small examples first
4. Check which variables are available with try/except blocks

## Discovery Date
2024-01-09 - Found while fixing document_processor.py workflows
