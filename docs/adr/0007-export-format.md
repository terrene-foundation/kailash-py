# Export Format

## Status
Accepted

## Context
The Kailash Python SDK needs to export workflows to a format compatible with the Kailash container-node architecture. The export format must:
- Represent nodes and connections
- Include all configuration
- Support environment variables
- Preserve metadata
- Be human-readable
- Enable round-trip conversion

## Decision
We will use YAML as the export format with the following structure:

```yaml
metadata:
  name: workflow_name
  description: Workflow description
  version: 1.0.0
  author: Author Name
  created_at: 2024-01-01T00:00:00
  
nodes:
  node_id:
    type: NodeType
    config:
      param1: value1
      param2: ${ENV_VAR}
    position: [x, y]
    
connections:
  - from: source_node.output_field
    to: target_node.input_field
```

Key features:
1. **YAML format** for human readability
2. **Environment variable** substitution with `${VAR}`
3. **Dotted notation** for connections (node.field)
4. **Position tracking** for visualization
5. **Metadata preservation** for documentation

## Consequences

### Positive
- Human-readable and editable
- Standard format (YAML) with good tooling
- Supports complex configurations
- Environment variable handling
- Compatible with Kailash expectations
- Preserves visualization information

### Negative
- YAML parsing complexities
- Limited to YAML data types
- Potential for syntax errors
- Requires validation after export

### Implementation Notes
The export system:
- Validates exported workflows
- Handles circular references
- Preserves all node configurations
- Supports import back to Python
- Maintains compatibility with containerization

This format bridges the gap between Python development and Kailash deployment.