---
name: code-templates
description: "Production-ready code templates for Kailash SDK including basic workflows, cyclic workflows, custom nodes, MCP servers, and all three test tiers (unit, integration, end-to-end). Use when asking about 'template', 'example code', 'starter code', 'boilerplate', 'scaffold', 'workflow template', 'custom node template', 'MCP server template', 'test template', 'unit test template', 'integration test template', or 'E2E test template'."
---

# Kailash Code Templates

Production-ready templates for common Kailash development tasks. All follow the **canonical 4-parameter pattern** from `/01-core-sdk`.

## Sub-File Index

### Workflow Templates

- **[template-workflow-basic](template-workflow-basic.md)** - Standard workflow
  - WorkflowBuilder setup, node addition, 4-param connections, runtime execution, result access, error handling
- **[template-cyclic-workflow](template-cyclic-workflow.md)** - Iterative workflows
  - CycleNode setup, convergence checking, state persistence, iteration limits

### Custom Development

- **[template-custom-node](template-custom-node.md)** - Custom node creation
  - Extend BaseNode, parameter definition, execute method, input validation, output formatting, registration
- **[template-mcp-server](template-mcp-server.md)** - MCP server creation
  - MCPServer init, tool/resource registration, transport config, auth, progress reporting

### Test Templates

- **[template-test-unit](template-test-unit.md)** - Tier 1: Unit tests
  - Fixtures, mock setup (allowed in Tier 1), assertions, fast execution
- **[template-test-integration](template-test-integration.md)** - Tier 2: Integration tests
  - Real database setup, workflow execution, real infrastructure fixtures, resource cleanup
- **[template-test-e2e](template-test-e2e.md)** - Tier 3: End-to-end tests
  - Full system setup, real HTTP requests, complete user flows

## Template Selection

| Task              | Template                    | Key Pattern                                          |
| ----------------- | --------------------------- | ---------------------------------------------------- |
| New workflow      | `template-workflow-basic`   | `WorkflowBuilder` + `.build()` + `runtime.execute()` |
| Iterative logic   | `template-cyclic-workflow`  | CycleNode + convergence check                        |
| New node type     | `template-custom-node`      | Extend `BaseNode`, implement `execute()`             |
| MCP integration   | `template-mcp-server`       | `MCPServer` + tool registration                      |
| Fast tests        | `template-test-unit`        | Mocking allowed, <1s                                 |
| Real infra tests  | `template-test-integration` | Real DB/runtime, no mocks                            |
| Full system tests | `template-test-e2e`         | Real HTTP, complete flows                            |

## Usage

1. **Select** the template matching your task
2. **Read** the sub-file for the complete, copy-ready template
3. **Customize** to your specific needs
4. **Test** with real data

## Template Rules

- Keep core structure intact when customizing
- Never skip error handling or input validation
- Never remove resource cleanup
- Maintain type hints and docstrings
- Follow naming conventions from gold standards

## Related Skills

- **[01-core-sdk](../01-core-sdk/SKILL.md)** - Core patterns
- **[06-cheatsheets](../06-cheatsheets/SKILL.md)** - Pattern examples
- **[07-development-guides](../07-development-guides/SKILL.md)** - Development guides
- **[12-testing-strategies](../12-testing-strategies/SKILL.md)** - Testing strategies
- **[17-gold-standards](../17-gold-standards/SKILL.md)** - Best practices

## Support

- `pattern-expert` - Pattern selection
- `tdd-implementer` - Test-first development
