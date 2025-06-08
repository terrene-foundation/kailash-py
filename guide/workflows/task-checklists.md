# Task Checklists

## Common Task Checklists

### □ Adding a New Node
- [ ] Name ends with "Node" (e.g., `MyCustomNode`)
- [ ] Inherits from `Node` or `AsyncNode`
- [ ] Has `get_parameters()` and `run()` methods (required)
- [ ] Has `get_output_schema()` method (optional, for output validation)
- [ ] Update `guide/reference/api-registry.yaml`
- [ ] Update `guide/reference/node-catalog.md` with node details
- [ ] Create example in `examples/node_examples/`
- [ ] Write unit tests
- [ ] Update docs

### □ Creating a Workflow Example
- [ ] Import from correct paths (check api-registry.yaml)
- [ ] Use exact method names (snake_case)
- [ ] Include all required parameters
- [ ] Validate with `validate_kailash_code.py`
- [ ] Test with `test_all_examples.py`

### □ Updating API
- [ ] Update `guide/reference/api-registry.yaml`
- [ ] Update `guide/reference/api-validation-schema.json`
- [ ] Update examples in `guide/reference/cheatsheet.md`
- [ ] Run validation tests
- [ ] Update CHANGELOG.md

### □ Implementing Cyclic Workflows
- [ ] Mark cycles with `cycle=True` in connect()
- [ ] Set `max_iterations` safety limit
- [ ] Add `convergence_check` expression or callback
- [ ] Handle cycle state with `or {}` pattern
- [ ] Write flexible test assertions (ranges, not exact counts)
- [ ] Document in examples/workflow_examples/

### □ Adding Authentication/Access Control
- [ ] Define UserContext with proper roles
- [ ] Use AccessControlledRuntime
- [ ] Create PermissionRules for resources
- [ ] Test with different user contexts
- [ ] Document security implications

### □ Integrating External APIs
- [ ] Use RESTClientNode or HTTPRequestNode
- [ ] Configure authentication properly
- [ ] Handle rate limiting and retries
- [ ] Mock external calls in tests
- [ ] Document API requirements

### □ Creating MCP Integration
- [ ] Use MCPClient/MCPServer nodes
- [ ] Define tool schemas properly
- [ ] Handle async operations with AsyncNode
- [ ] Test with mock MCP servers
- [ ] Document MCP protocol usage
