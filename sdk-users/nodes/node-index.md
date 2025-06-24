# Node Index - Quick Reference

> **For detailed selection guidance**: See [node-selection-guide.md](node-selection-guide.md) (436 lines)
> **For exhaustive documentation**: See [comprehensive-node-catalog.md](comprehensive-node-catalog.md) (2194 lines)

## Quick Decision: Which Node to Use?

| Task | Use This Node | Not PythonCodeNode |
|------|---------------|-------------------|
| Read CSV/Excel | `CSVReaderNode`, `ExcelReaderNode` | ❌ `pd.read_csv()` |
| Call REST API | `HTTPRequestNode`, `RESTClientNode` | ❌ `requests.get()` |
| Query Database (Simple) | `SQLDatabaseNode`, `AsyncSQLDatabaseNode` | ❌ `cursor.execute()` |
| Query Database (Production) | `WorkflowConnectionPool` ⭐ | ❌ Manual pooling |
| Use LLM/AI | `LLMAgentNode`, `MonitoredLLMAgentNode` | ❌ OpenAI SDK |
| Filter/Transform | `FilterNode`, `DataTransformer` | ❌ List comprehensions |
| Route Logic | `SwitchNode`, `ConditionalRouterNode` | ❌ if/else blocks |
| Send Alerts | `DiscordAlertNode`, `EmailSenderNode` | ❌ SMTP/webhook code |
| Manage Roles/Permissions | `RoleManagementNode`, `PermissionCheckNode` | ❌ Custom RBAC |
| Check User Access | `PermissionCheckNode` | ❌ Manual checks |

## Node Categories (110+ total)

| Category | Count | Key Nodes | Details |
|----------|-------|-----------|---------|
| **Admin** | 4 | RoleManagementNode, PermissionCheckNode | [admin-nodes-guide.md](admin-nodes-guide.md) |
| **AI/ML** | 20+ | LLMAgentNode, EmbeddingGeneratorNode, A2AAgentNode | [02-ai-nodes.md](02-ai-nodes.md) |
| **Data I/O** | 15+ | CSVReaderNode, SQLDatabaseNode, VectorDatabaseNode | [03-data-nodes.md](03-data-nodes.md) |
| **API/HTTP** | 10+ | HTTPRequestNode, RESTClientNode, GraphQLClientNode | [04-api-nodes.md](04-api-nodes.md) |
| **Transform** | 8+ | FilterNode, DataTransformer, TextSplitterNode | [06-transform-nodes.md](06-transform-nodes.md) |
| **Logic** | 5+ | SwitchNode, MergeNode, WorkflowNode | [05-logic-nodes.md](05-logic-nodes.md) |
| **Alerts** | 5+ | DiscordAlertNode, EmailSenderNode, SlackAlertNode | [09-alert-nodes.md](09-alert-nodes.md) |
| **Security** | 10+ | OAuth2Node, JWTValidatorNode, EncryptionNode | [08-utility-nodes.md](08-utility-nodes.md) |
| **Code** | 6+ | PythonCodeNode, MCPToolNode, ScriptRunnerNode | [07-code-nodes.md](07-code-nodes.md) |

## Navigation Strategy

1. **Quick task lookup** → Use table above
2. **Smart selection** → [node-selection-guide.md](node-selection-guide.md)
3. **Category browsing** → Click category file links
4. **Full details** → [comprehensive-node-catalog.md](comprehensive-node-catalog.md) (only when needed)

## Most Used Nodes

```python
# Top 10 most commonly used nodes
from kailash.nodes.data import CSVReaderNode, SQLDatabaseNode, WorkflowConnectionPool
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.transform import FilterNode, DataTransformer
from kailash.nodes.code import PythonCodeNode  # Use sparingly!

# For production database operations
pool = WorkflowConnectionPool(
    name="main_pool",
    database_type="postgresql",
    host="localhost",
    min_connections=5,
    max_connections=20
)
```
