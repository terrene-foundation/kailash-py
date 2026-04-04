# Enterprise Features Reference

## Admin Framework

5 specialized admin nodes for enterprise administration:

| Node                  | Purpose                                                 |
| --------------------- | ------------------------------------------------------- |
| `UserManagementNode`  | User CRUD, profile management, account lifecycle        |
| `RoleManagementNode`  | Role hierarchy, permission assignment                   |
| `PermissionCheckNode` | ABAC (Attribute-Based Access Control) with 16 operators |
| `AuditLogNode`        | 25+ event types, immutable audit trail                  |
| `SecurityEventNode`   | ML-based threat detection, anomaly scoring              |

### ABAC Security (16 Operators)

```python
workflow.add_node("PermissionCheckNode", "check_access", {
    "user_id": user_id,
    "resource": "document",
    "action": "edit",
    "context": {"department": "engineering", "clearance": "secret"}
})
```

Operators: `equals`, `not_equals`, `in`, `not_in`, `contains`, `starts_with`, `ends_with`, `gt`, `gte`, `lt`, `lte`, `between`, `regex`, `exists`, `is_null`, `time_range`

### Audit Trail

```python
workflow.add_node("AuditLogNode", "log_action", {
    "event_type": "USER_LOGIN",
    "actor_id": user_id,
    "resource_type": "session",
    "details": {"ip": client_ip, "user_agent": ua}
})
```

---

## MCP Intelligent Integration

Built-in MCP client via the MCP mixin (`kailash.nodes.mixins.mcp`) for tool discovery and execution:

```python
import os

# For MCP tool integration with LLM, use Kaizen agents with MCP tools
# See skills/04-kaizen/ and skills/05-kailash-mcp/ for patterns
workflow.add_node("PythonCodeNode", "smart_agent", {
    "code": "import os; from openai import OpenAI; client = OpenAI(); resp = client.chat.completions.create(model=os.environ.get('LLM_MODEL', ''), messages=messages); result = {'response': resp.choices[0].message.content}",
    "input_variables": ["messages"]
})
```

### Patterns

- **Tool caching**: Cache MCP tool schemas to avoid repeated discovery
- **Service discovery**: Auto-discover MCP servers on the network
- **Authentication**: Pass auth context to MCP servers for access control
- **Load balancing**: Distribute tool calls across multiple MCP server instances
- **Delegation**: Chain MCP calls where one tool's output feeds another

---

## WebSocket Production Deployment

Production patterns for WebSocket MCP implementations:

### Connection Management

```python
# Reconnection with exponential backoff
config = {
    "reconnect_strategy": "exponential_backoff",
    "initial_delay": 1.0,
    "max_delay": 30.0,
    "max_retries": 10,
    "jitter": True
}
```

### Production Concerns

- **Rate limiting**: Per-client message rate limits to prevent abuse
- **Memory management**: Bounded message queues per connection, automatic cleanup of idle connections
- **Load balancing**: Sticky sessions for WebSocket connections (connection affinity)
- **Health checks**: Periodic ping/pong with configurable timeouts
- **Message queue failover**: Buffer messages during brief disconnections, replay on reconnect
