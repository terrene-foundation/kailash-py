# Common Mistakes to Avoid

```python
# ❌ WRONG - Missing "Node" suffix
workflow.add_node("reader", CSVReader())

# ✅ CORRECT
workflow.add_node("reader", CSVReaderNode())

# ❌ WRONG - Wrong parameter name
runtime.execute(workflow, inputs={"data": [1,2,3]})

# ✅ CORRECT
runtime.execute(workflow, parameters={"node_id": {"data": [1,2,3]}})

# ❌ WRONG - Using camelCase
workflow.addNode("reader", node)

# ✅ CORRECT
workflow.add_node("reader", node)

# ❌ WRONG - Direct execution returns only results
results, run_id = workflow.execute()

# ✅ CORRECT - Runtime returns tuple
results, run_id = runtime.execute(workflow)
```
