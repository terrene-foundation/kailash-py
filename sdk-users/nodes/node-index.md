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
| Use LLM/AI | `LLMAgentNode`, `IterativeLLMAgentNode` ⭐ ENHANCED | ❌ OpenAI SDK |
| Filter/Transform | `FilterNode`, `DataTransformer` | ❌ List comprehensions |
| Route Logic | `SwitchNode`, `ConditionalRouterNode` | ❌ if/else blocks |
| Validate Code/Workflows | `CodeValidationNode`, `WorkflowValidationNode` ⭐ NEW | ❌ Manual testing |
| Execute Test Suites | `TestSuiteExecutorNode` ⭐ NEW | ❌ Custom test runners |
| Send Alerts | `DiscordAlertNode`, `EmailSenderNode` | ❌ SMTP/webhook code |
| Monitor Transactions | `TransactionMetricsNode`, `TransactionMonitorNode` | ❌ Manual metrics |
| Detect Deadlocks | `DeadlockDetectorNode` | ❌ Custom detection |
| Detect Race Conditions | `RaceConditionDetectorNode` | ❌ Manual analysis |
| Performance Anomalies | `PerformanceAnomalyNode` | ❌ Manual thresholds |
| Distributed Transactions | `DistributedTransactionManagerNode` | ❌ Manual 2PC/Saga |
| Saga Pattern | `SagaCoordinatorNode`, `SagaStepNode` | ❌ Custom compensation |
| Two-Phase Commit | `TwoPhaseCommitCoordinatorNode` | ❌ Manual 2PC protocol |
| Manage Roles/Permissions | `RoleManagementNode`, `PermissionCheckNode` | ❌ Custom RBAC |
| Check User Access | `PermissionCheckNode` | ❌ Manual checks |

## Node Categories (115+ total - Tested & Validated ✅)

| Category | Count | Key Nodes | Test Status | Details |
|----------|-------|-----------|-------------|---------|
| **Admin** | 10+ | UserManagementNode, RoleManagementNode, AccessControlNode | ✅ 100% Pass | [admin-nodes-guide.md](admin-nodes-guide.md) |
| **AI/ML** | 15+ | LLMAgentNode, MonitoredLLMAgentNode, EmbeddingGeneratorNode | ✅ 100% Pass | [02-ai-nodes.md](02-ai-nodes.md) |
| **Data I/O** | 20+ | CSVReaderNode, AsyncSQLDatabaseNode, DirectoryReaderNode | ✅ 99.7% Pass | [03-data-nodes.md](03-data-nodes.md) |
| **API/HTTP** | 10+ | HTTPRequestNode, RESTClientNode, GraphQLClientNode | ✅ 100% Pass | [04-api-nodes.md](04-api-nodes.md) |
| **Transform** | 25+ | DataTransformerNode, FilterNode, AggregationNode | ✅ 100% Pass | [06-transform-nodes.md](06-transform-nodes.md) |
| **Validation** | 5+ | CodeValidationNode, WorkflowValidationNode, TestSuiteExecutorNode | ✅ 100% Pass | **NEW** - Testing & validation nodes |
| **Logic** | 15+ | SwitchNode, MergeNode, ConditionalNode | ✅ 100% Pass | [05-logic-nodes.md](05-logic-nodes.md) |
| **Security** | 15+ | AuthenticationNode, EncryptionNode, ThreatDetectionNode | ✅ 100% Pass | [security-nodes.md](security-nodes.md) |
| **Enterprise** | 10+ | MultiFactorAuthNode, ComplianceNode, DataGovernanceNode | ✅ 100% Pass | [enterprise-nodes.md](enterprise-nodes.md) |
| **Monitoring** | 5+ | TransactionMetricsNode, DeadlockDetectorNode, RaceConditionDetectorNode | ✅ 100% Pass | [monitoring-nodes.md](monitoring-nodes.md) |
| **Transaction** | 10+ | DistributedTransactionManagerNode, SagaCoordinatorNode, TwoPhaseCommitCoordinatorNode | ✅ 100% Pass | [transaction-nodes.md](transaction-nodes.md) |
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
from kailash.nodes.ai import LLMAgentNode, IterativeLLMAgentNode  # Enhanced with test-driven convergence
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.transform import FilterNode, DataTransformer
from kailash.nodes.validation import CodeValidationNode, WorkflowValidationNode  # NEW: Validation framework
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
