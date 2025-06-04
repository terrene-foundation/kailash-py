# Kailash SDK - Quick Reference: Common Mistakes & Solutions

## 🚨 Critical API Patterns (MUST KNOW)

### Workflow Creation & Execution
```python
# ✅ CORRECT
workflow = Workflow("id", "name")
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")  # Config as kwargs
workflow.connect("source", "target", mapping={"output": "input"})    # Use connect()
runtime.execute(workflow, parameters={"node": {"param": "value"}})   # Use parameters=

# ❌ WRONG
workflow.add_node("reader", CSVReaderNode(), {"file_path": "data.csv"})  # Dict config
builder.add_edge("node1", "node2")  # No such method (use connect or add_connection)
runtime.execute(workflow, {"data": [1,2,3]})  # Must use parameters= keyword
workflow.execute(runtime)  # workflow.execute() doesn't take runtime
```

### Configuration vs Runtime Parameters
```python
# Configuration (HOW): Static settings when adding nodes
workflow.add_node("reader", CSVReaderNode(), 
    file_path="data.csv",    # WHERE to read
    delimiter=","            # HOW to parse
)

# Runtime (WHAT): Data flowing through connections
workflow.connect("reader", "processor", mapping={"data": "data"})

# Parameters override: Via runtime.execute()
runtime.execute(workflow, parameters={
    "reader": {"file_path": "custom.csv"},  # Override config
    "processor": {"data": [1,2,3]}          # Inject runtime data
})
```

### Key Rules
1. **ALL node classes end with "Node"**: `CSVReaderNode` ✓, `CSVReader` ✗
2. **Config as kwargs**: `add_node("id", Node(), param=value)` ✓
3. **Use runtime.execute()**: NOT workflow.execute() for production
4. **Parameters can override anything**: Config and runtime both
5. **Any node can be entry point**: No source node requirement

## ⚠️ Common Pitfalls by Category

### Node Implementation
- **Missing methods**: All nodes need `get_parameters()` and `run()`
- **get_parameters() defines ALL params**: Both config AND runtime
- **Output schema mismatch**: Ensure `get_output_schema()` matches `run()` output
- **Mutable state**: Don't store state in node instances

### Workflow Patterns
- **No source node required**: Can inject data via parameters
- **Connect syntax**: Use `workflow.connect()` not WorkflowBuilder
- **Connection validation**: Ensure output/input names match
- **Parameter precedence**: Runtime > Config > Defaults

### Testing
- **Async tests**: Use `@pytest.mark.asyncio`
- **Mock cleanup**: Use `with patch()` context manager
- **Test isolation**: No shared global state
- **Lambda closures**: Use `lambda x=i: func(x)` in loops

### Error Handling
- **No bare except**: Always catch specific exceptions
- **Consistent wrapping**: Use `NodeExecutionError` for all node errors
- **Document exceptions**: Include Raises section in docstrings

### Performance
- **Streaming large data**: Use chunking for large files
- **Bounded collections**: Limit history/cache sizes
- **Async operations**: Use `await asyncio.sleep()` not `time.sleep()`

### File Handling
- **Use pathlib**: `Path.cwd() / "outputs"` not hardcoded paths
- **Validate paths**: Check for path traversal attacks
- **Cross-platform**: Avoid platform-specific paths

## 📋 Quick Validation Checklist

Before submitting code:
- [ ] Node classes end with "Node"
- [ ] Config passed as kwargs to add_node()
- [ ] Using workflow.connect() with mapping dict
- [ ] runtime.execute() with parameters= keyword
- [ ] No bare except clauses
- [ ] Proper async/await usage
- [ ] Path handling with pathlib
- [ ] Tests are isolated (no shared state)

## 🔧 Common Fixes

### "Node missing required inputs" Error
```python
# Option 1: Add source node
workflow.add_node("source", CSVReaderNode(), file_path="data.csv")

# Option 2: Inject via parameters
runtime.execute(workflow, parameters={"node": {"data": [...]}})
```

### "AttributeError: no 'connect' method"
```python
# Using WorkflowBuilder? Different API:
builder.add_connection("source", "output", "target", "input")

# Better: Use Workflow directly:
workflow.connect("source", "target", mapping={"output": "input"})
```

### "TypeError: execute() got unexpected keyword"
```python
# Wrong: runtime.execute(workflow, inputs={...})
# Right: runtime.execute(workflow, parameters={...})
```

## 🚀 Best Practices Summary

1. **Consistency**: Follow established patterns, don't create variants
2. **Simplicity**: Use Workflow.connect(), avoid WorkflowBuilder
3. **Flexibility**: Any node can receive external data via parameters
4. **Testing**: Write tests first, maintain >80% coverage
5. **Documentation**: Keep code and docs in sync
6. **Security**: Validate all inputs, no exec() on user data
7. **Performance**: Stream large data, bound collections
8. **Cross-platform**: Use pathlib, environment variables

---
*For detailed explanations, see the full mistakes document: 000-master.md*