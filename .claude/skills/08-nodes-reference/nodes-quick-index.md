---
name: nodes-quick-index
description: "Quick reference to all Kailash nodes. Use when asking 'node list', 'all nodes', 'node reference', 'what nodes', 'available nodes', or 'node catalog'."
---

# Nodes Quick Index

Quick reference to verified Kailash workflow nodes (source-checked against `src/kailash/nodes/`).

> **Skill Metadata**
> Category: `nodes`
> Priority: `CRITICAL`
> SDK Version: `0.9.25+`
> Related Skills: All node-specific skills
> Related Subagents: `pattern-expert` (node selection, workflow patterns)

## Quick Decision: Which Node to Use?

| Task                     | Use This Node                              | Not PythonCodeNode      |
| ------------------------ | ------------------------------------------ | ----------------------- |
| Read CSV                 | `CSVReaderNode`                            | :x: `pd.read_csv()`     |
| Call REST API            | `HTTPRequestNode`, `RESTClientNode`        | :x: `requests.get()`    |
| Query Database           | `AsyncSQLDatabaseNode`                     | :x: `cursor.execute()`  |
| AI/LLM                   | Use Kaizen framework (`skills/04-kaizen/`) | :x: OpenAI SDK          |
| Filter/Transform         | `FilterNode`, `DataTransformer`            | :x: List comprehensions |
| Route Logic              | `SwitchNode`                               | :x: if/else blocks      |
| Send Alerts              | `DiscordAlertNode`                         | :x: webhook code        |
| Distributed Transactions | `DistributedTransactionManagerNode`        | :x: Manual 2PC/Saga     |

## Node Categories

### Data I/O

```python
# File operations
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.data import JSONReaderNode, JSONWriterNode
from kailash.nodes.data import TextReaderNode
from kailash.nodes.data import DirectoryReaderNode, FileDiscoveryNode

# Database
from kailash.nodes.data import AsyncSQLDatabaseNode  # Production recommended
from kailash.nodes.data import WorkflowConnectionPool  # Connection pooling
from kailash.nodes.data import QueryRouterNode  # Intelligent routing
from kailash.nodes.data import SQLDatabaseNode  # Simple queries
from kailash.nodes.data import QueryPipelineNode
from kailash.nodes.data import OptimisticLockingNode
from kailash.nodes.data import BulkCreateNode, BulkUpdateNode, BulkDeleteNode, BulkUpsertNode

# Vector / Retrieval
from kailash.nodes.data import EmbeddingNode, VectorDatabaseNode, TextSplitterNode
from kailash.nodes.data import AsyncPostgreSQLVectorNode
from kailash.nodes.data import HybridRetrieverNode, RelevanceScorerNode
from kailash.nodes.data import DocumentSourceNode, QuerySourceNode, DocumentProcessorNode

# Streaming
from kailash.nodes.data import EventStreamNode, KafkaConsumerNode
from kailash.nodes.data import StreamPublisherNode, WebSocketNode

# Other
from kailash.nodes.data import RedisNode
from kailash.nodes.data import EventGeneratorNode
from kailash.nodes.data import SharePointGraphReader, SharePointGraphWriter
```

### API

```python
from kailash.nodes.api import HTTPRequestNode, AsyncHTTPRequestNode
from kailash.nodes.api import RESTClientNode, AsyncRESTClientNode
from kailash.nodes.api import GraphQLClientNode, AsyncGraphQLClientNode
from kailash.nodes.api import RateLimitedAPINode, AsyncRateLimitedAPINode
from kailash.nodes.api import OAuth2Node, BasicAuthNode, APIKeyNode
from kailash.nodes.api import APIHealthCheckNode
from kailash.nodes.api import SecurityScannerNode
```

### Logic

```python
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.logic import AsyncSwitchNode, AsyncMergeNode
from kailash.nodes.logic import LoopNode
from kailash.nodes.logic import ConvergenceCheckerNode, MultiCriteriaConvergenceNode
from kailash.nodes.logic import IntelligentMergeNode
from kailash.nodes.logic import SignalWaitNode
from kailash.nodes.logic import WorkflowNode
```

### Transform

```python
from kailash.nodes.transform import FilterNode
from kailash.nodes.transform import DataTransformer
from kailash.nodes.transform import Map, Sort
from kailash.nodes.transform import ContextualCompressorNode
from kailash.nodes.transform import HierarchicalChunkerNode, SemanticChunkerNode, StatisticalChunkerNode
from kailash.nodes.transform import ChunkTextExtractorNode, ContextFormatterNode, QueryTextWrapperNode
```

### Code Execution

```python
from kailash.nodes.code import PythonCodeNode  # Use sparingly!
from kailash.nodes.code import AsyncPythonCodeNode
```

### Security

```python
from kailash.nodes.security import AuditLogNode
from kailash.nodes.security import CredentialManagerNode, RotatingCredentialNode
from kailash.nodes.security import SecurityEventNode
from kailash.nodes.security import ABACPermissionEvaluatorNode
from kailash.nodes.security import BehaviorAnalysisNode
from kailash.nodes.security import ThreatDetectionNode
```

### Admin

```python
from kailash.nodes.admin import UserManagementNode, RoleManagementNode
from kailash.nodes.admin import PermissionCheckNode
from kailash.nodes.admin import EnterpriseAuditLogNode
from kailash.nodes.admin import EnterpriseSecurityEventNode
```

### Auth

```python
from kailash.nodes.auth import SSOAuthenticationNode
from kailash.nodes.auth import MultiFactorAuthNode
from kailash.nodes.auth import SessionManagementNode
from kailash.nodes.auth import EnterpriseAuthProviderNode
from kailash.nodes.auth import DirectoryIntegrationNode
from kailash.nodes.auth import RiskAssessmentNode
```

### Monitoring

```python
from kailash.nodes.monitoring import TransactionMetricsNode
from kailash.nodes.monitoring import TransactionMonitorNode
from kailash.nodes.monitoring import DeadlockDetectorNode
from kailash.nodes.monitoring import RaceConditionDetectorNode
from kailash.nodes.monitoring import PerformanceAnomalyNode
from kailash.nodes.monitoring import ConnectionDashboardNode
from kailash.nodes.monitoring import HealthCheckNode
from kailash.nodes.monitoring import LogProcessorNode
from kailash.nodes.monitoring import MetricsCollectorNode
from kailash.nodes.monitoring import PerformanceBenchmarkNode
```

### Distributed Transactions

```python
from kailash.nodes.transaction import DistributedTransactionManagerNode  # Auto-select
from kailash.nodes.transaction import SagaCoordinatorNode  # High availability
from kailash.nodes.transaction import SagaStepNode
from kailash.nodes.transaction import TwoPhaseCommitCoordinatorNode  # Strong consistency
from kailash.nodes.transaction import TransactionContextNode
```

### Alerts

```python
from kailash.nodes.alerts import DiscordAlertNode
# Only DiscordAlertNode exists. Slack/Email/Teams/PagerDuty are not implemented.
```

### Cache

```python
from kailash.nodes.cache import CacheNode, CacheInvalidationNode
from kailash.nodes.cache import RedisPoolManagerNode
```

### Compliance

```python
from kailash.nodes.compliance import GDPRComplianceNode
from kailash.nodes.compliance import DataRetentionPolicyNode
```

### Edge/Cloud

```python
from kailash.nodes.edge import EdgeNode, EdgeDataNode, EdgeStateMachine
from kailash.nodes.edge import CloudNode, DockerNode, KubernetesNode, PlatformNode
from kailash.nodes.edge import EdgeCoordinationNode
from kailash.nodes.edge import EdgeMigrationNode, EdgeMonitoringNode, EdgeWarmingNode
from kailash.nodes.edge import ResourceAnalyzerNode, ResourceOptimizerNode, ResourceScalerNode
```

### Enterprise

```python
from kailash.nodes.enterprise import EnterpriseAuditLoggerNode
from kailash.nodes.enterprise import BatchProcessorNode
from kailash.nodes.enterprise import DataLineageNode
from kailash.nodes.enterprise import EnterpriseMLCPExecutorNode
from kailash.nodes.enterprise import MCPServiceDiscoveryNode
from kailash.nodes.enterprise import TenantAssignmentNode
```

### System

```python
from kailash.nodes.system import CommandParserNode, CommandRouterNode
from kailash.nodes.system import InteractiveShellNode
```

### Governance

```python
from kailash.nodes.governance import SecureGovernedNode  # Base class
from kailash.nodes.governance import DevelopmentNode, EnterpriseNode
```

### Handler

```python
from kailash.nodes.handler import HandlerNode
```

## Most Used Nodes (Top 10)

```python
from kailash.nodes.data import CSVReaderNode, AsyncSQLDatabaseNode, WorkflowConnectionPool
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.transform import FilterNode, DataTransformer
from kailash.nodes.code import PythonCodeNode
```

## Node Selection by Task

### Data Processing

- **CSV**: [`nodes-data-reference`](nodes-data-reference.md)
- **Database**: `AsyncSQLDatabaseNode`, `WorkflowConnectionPool`, `QueryRouterNode`
- **API**: [`nodes-api-reference`](nodes-api-reference.md)

### AI/ML

- **LLM/Agents**: Use Kaizen framework (`skills/04-kaizen/SKILL.md`)
- **Embeddings**: `EmbeddingNode` (in `kailash.nodes.data`) or Kaizen
- **Multi-Agent**: Use Kaizen framework

### Logic & Control

- **Routing**: [`nodes-logic-reference`](nodes-logic-reference.md)
- **Conditionals**: `SwitchNode` (outputs: `true_output`, `false_output`)
- **Loops**: `LoopNode`

### Enterprise

- **Security**: `ABACPermissionEvaluatorNode`, `ThreatDetectionNode`, `CredentialManagerNode`
- **Auth**: `SSOAuthenticationNode`, `MultiFactorAuthNode`, `OAuth2Node` (in `api/auth`)
- **Admin**: [`nodes-admin-reference`](nodes-admin-reference.md)
- **Monitoring**: [`nodes-monitoring-reference`](nodes-monitoring-reference.md)
- **Transactions**: [`nodes-transaction-reference`](nodes-transaction-reference.md)

## Navigation Strategy

1. **Quick task lookup** -- Use table above
2. **Category browsing** -- Use category-specific skills
3. **Full details** -- See comprehensive-node-catalog.md

## When NOT to Use Nodes

**Avoid PythonCodeNode for:**

- File I/O operations (use CSVReaderNode, etc.)
- HTTP requests (use HTTPRequestNode)
- Database queries (use AsyncSQLDatabaseNode)
- Data filtering/transformation (use FilterNode, DataTransformer)
- Authentication (use OAuth2Node, SSOAuthenticationNode)

**Use PythonCodeNode only for:**

- Ollama/local LLM integration
- Complex custom business logic
- Temporary prototyping

## Related Skills

- **Data Nodes**: [`nodes-data-reference`](nodes-data-reference.md)
- **AI**: Use Kaizen framework (`skills/04-kaizen/SKILL.md`)
- **API Nodes**: [`nodes-api-reference`](nodes-api-reference.md)
- **Database Nodes**: [`nodes-database-reference`](nodes-database-reference.md)
- **Transform Nodes**: [`nodes-transform-reference`](nodes-transform-reference.md)
- **Code Nodes**: [`nodes-code-reference`](nodes-code-reference.md)
- **Logic Nodes**: [`nodes-logic-reference`](nodes-logic-reference.md)
- **File Nodes**: [`nodes-file-reference`](nodes-file-reference.md)
- **Monitoring Nodes**: [`nodes-monitoring-reference`](nodes-monitoring-reference.md)
- **Transaction Nodes**: [`nodes-transaction-reference`](nodes-transaction-reference.md)
- **Admin Nodes**: [`nodes-admin-reference`](nodes-admin-reference.md)

## When to Escalate to Subagent

Use `pattern-expert` subagent when:

- Choosing between multiple node options
- Building complex multi-node workflows
- Optimizing node selection for performance
- Troubleshooting node parameter issues

## Quick Tips

- Start with specialized nodes before considering PythonCodeNode
- Use async variants (AsyncSQLDatabaseNode, AsyncHTTPRequestNode) for production
- Leverage enterprise nodes (monitoring, transactions, security) for production
- Check node-specific skills for detailed usage patterns
- `kailash.nodes.ai` does not exist -- use Kaizen framework for AI/LLM

<!-- Trigger Keywords: node list, all nodes, node reference, what nodes, available nodes, node catalog, kailash nodes, node index, node types, workflow nodes -->
