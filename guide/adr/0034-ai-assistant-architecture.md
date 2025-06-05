# ADR-0034: AI Assistant Architecture for Workflow Studio

## Status
Proposed

## Context
Users building workflows in Kailash Studio need intelligent assistance to:
- Convert natural language requirements into workflows
- Get recommendations for appropriate nodes
- Debug workflow issues
- Learn best practices
- Access documentation contextually

The assistant should function similarly to Claude Code, with access to project documentation and the ability to manage tasks.

## Decision
Implement an AI Assistant using Ollama with Mistral Codestral model, integrated via MCP (Model Context Protocol) tools.

## Architecture

### 1. AI Backend
```yaml
ai_backend:
  provider: Ollama
  model: mistral/codestral
  features:
    - Code generation
    - Natural language understanding
    - Documentation comprehension
    - Multi-turn conversations
```

### 2. MCP Tool Integration
```python
class KailashMCPServer:
    """MCP server providing tools for the AI assistant"""
    
    tools = {
        # Documentation access
        "read_documentation": {
            "description": "Read Kailash documentation files",
            "parameters": ["file_path"]
        },
        
        # Reference access (Claude.md style)
        "read_reference": {
            "description": "Access reference documents",
            "parameters": ["reference_type"]  # api-registry, node-catalog, etc.
        },
        
        # Todo management
        "read_todos": {
            "description": "Read current todo list",
            "parameters": []
        },
        "write_todos": {
            "description": "Update todo list",
            "parameters": ["todos"]
        },
        
        # Workflow operations
        "create_workflow": {
            "description": "Create a new workflow",
            "parameters": ["definition"]
        },
        "validate_workflow": {
            "description": "Validate workflow syntax",
            "parameters": ["workflow"]
        },
        "get_node_info": {
            "description": "Get information about a node",
            "parameters": ["node_type"]
        },
        
        # Code generation
        "generate_custom_node": {
            "description": "Generate custom node code",
            "parameters": ["requirements"]
        },
        
        # Search
        "search_documentation": {
            "description": "Search through documentation",
            "parameters": ["query"]
        },
        "search_examples": {
            "description": "Find relevant examples",
            "parameters": ["use_case"]
        }
    }
```

### 3. Assistant API Endpoints
```python
# POST /api/assistant/chat
{
    "message": "Create a workflow that processes CSV files and sends emails",
    "context": {
        "current_workflow": {...},
        "selected_node": "node_id"
    }
}

# GET /api/assistant/suggestions
{
    "workflow_id": "...",
    "cursor_position": {...}
}

# POST /api/assistant/generate
{
    "type": "workflow|node|code",
    "requirements": "..."
}
```

### 4. Integration Architecture
```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Studio UI      │────▶│  Assistant API   │────▶│  Ollama Server  │
│                 │     │                  │     │  (Codestral)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────────┐
                        │   MCP Server     │
                        │  (Tool Access)   │
                        └──────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Documentation│     │  Todo Lists  │     │  Reference   │
│    Files     │     │              │     │  Documents   │
└──────────────┘     └──────────────┘     └──────────────┘
```

### 5. Key Features

#### Natural Language to Workflow
```python
# User: "I need to read customer data, filter by age > 30, and export to JSON"
# Assistant generates:
workflow = {
    "nodes": [
        {"id": "reader", "type": "CSVReaderNode", "config": {"file_path": "customers.csv"}},
        {"id": "filter", "type": "FilterNode", "config": {"expression": "age > 30"}},
        {"id": "writer", "type": "JSONWriterNode", "config": {"file_path": "filtered.json"}}
    ],
    "connections": [
        {"from": "reader", "to": "filter"},
        {"from": "filter", "to": "writer"}
    ]
}
```

#### Contextual Help
- Hover over node → Get documentation
- Error in workflow → Get fix suggestions
- Building workflow → Get next step recommendations

#### Documentation Access
- Can read Claude.md for instructions
- Access api-registry.yaml for correct APIs
- Search through examples
- Reference node catalog

### 6. Implementation Plan

#### Phase 1: Core Infrastructure
1. Set up Ollama integration
2. Implement MCP server with basic tools
3. Create assistant API endpoints

#### Phase 2: Tool Implementation
1. Documentation reader tools
2. Todo list management
3. Workflow validation tools

#### Phase 3: Intelligence Features
1. Natural language understanding
2. Workflow generation
3. Error diagnosis

#### Phase 4: UI Integration
1. Chat interface in Studio
2. Inline suggestions
3. Contextual help popups

## Consequences

### Positive
- Significantly improved user experience
- Faster workflow development
- Built-in learning and documentation
- Reduced errors through AI validation
- Self-documenting through todo management

### Negative
- Requires Ollama server running
- Additional infrastructure complexity
- Model size and performance considerations
- Need to keep AI knowledge updated

## References
- MCP Protocol: https://modelcontextprotocol.io/
- Ollama: https://ollama.ai/
- Mistral Codestral: https://mistral.ai/news/codestral/
- Claude Code patterns for reference