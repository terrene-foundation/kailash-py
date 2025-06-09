# Quick Tips

1. **All node classes end with "Node"**: `CSVReaderNode` ✓, `CSVReader` ✗
2. **All methods use snake_case**: `add_node()` ✓, `addNode()` ✗
3. **All config keys use underscores**: `file_path` ✓, `filePath` ✗
4. **Always use runtime.execute()**: Returns (results, run_id) tuple
5. **Use parameters={} for overrides**: Not inputs={} or data={}
6. **Workflow needs ID and name**: `Workflow("id", name="name")`
7. **Prefer Workflow.connect()**: Avoid WorkflowBuilder confusion
8. **Validate before execution**: `workflow.validate()`
9. **Use environment variables**: For API keys and secrets
10. **Enable security in production**: Configure SecurityConfig
