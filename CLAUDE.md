# Kailash SDK

## ⚡ Quick Start

### Installation
```bash
# Core SDK
pip install kailash

# With app frameworks
pip install kailash[dataflow,nexus]  # Database + multi-channel
pip install kailash[all]             # Everything

# Direct app installation
pip install kailash-dataflow  # Zero-config database
pip install kailash-nexus     # Multi-channel platform
```

### Cyclic Workflows
```python
# WorkflowBuilder: Build first, then cycle
built_workflow = workflow.build()
built_workflow.create_cycle("name").connect(...).build()

# Workflow: Direct chaining
workflow.create_cycle("name").connect(...).build()
```

**📖 Detailed patterns**: [sdk-users/](sdk-users/) → Cyclic Workflows section

### Basic Workflow
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", {"model": "gpt-4"})
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### DataFlow Quick Start
```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

db = DataFlow()

@db.model
class User:
    name: str
    age: int

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"name": "Alice", "age": 25})
workflow.add_node("UserListNode", "list", {"filter": {"age": {"$gt": 18}}})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Nexus Quick Start
```bash
# Install Nexus separately
pip install kailash-nexus
```

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {
    "code": "result = {'result': sum(parameters.get('data', []))}"
})

# Register workflow
app.register("process_data", workflow.build())

app.start()  # Available as API, CLI, and MCP
```

### ❌ NEVER & ✅ ALWAYS

#### ❌ DEPRECATED PATTERNS
- `workflow.execute(runtime)` → Use `runtime.execute(workflow)`
- `workflow.addNode()` → Use `workflow.add_node()`
- `inputs={}` → Use `parameters={}`
- String code in PythonCodeNode → Use `.from_function()`
- `workflow.connect(..., cycle=True)` → Use `workflow.create_cycle("name").connect(...).build()`
- Override `execute()` in nodes → Implement `run()` instead
- **Missing required parameters** → See [Parameter Guide](sdk-users/3-development/parameter-passing-guide.md) & [Error Solutions](sdk-users/2-core-concepts/validation/common-mistakes.md)

#### ✅ CRITICAL WORKFLOW PATTERNS
- **WorkflowBuilder**: `built_workflow = workflow.build(); cycle = built_workflow.create_cycle(...)`
- **Workflow**: `workflow.create_cycle(...).connect(...).build()` (direct chaining)
- **SwitchNode + Cycles**: Set forward connections FIRST, then create cycle connections
- **📖 Detailed patterns**: [sdk-users/](sdk-users/) → Cyclic Workflows section

## 🚨 **Debugging Workflow Errors**
**"Node 'X' missing required inputs"** → [Parameter Solution Guide](sdk-users/2-core-concepts/validation/common-mistakes.md#mistake--1-missing-required-parameters-new-in-v070)

### 🚨 PARAMETER PASSING
**Required parameters MUST be provided via one of three methods:**
1. **Node config**: `workflow.add_node("Node", "id", {"param": "value"})`
2. **Connections**: `workflow.add_connection("source", "output", "target", "param")`
3. **Runtime**: `runtime.execute(workflow.build(), parameters={"node_id": {"param": "value"}})`

**See**: [Parameter Passing Guide](sdk-users/3-development/parameter-passing-guide.md)

### 🎯 Multi-Step Strategy (Enterprise Workflow)
1. **First implementation** → Copy basic pattern above
2. **Parameter validation** → [Parameter Guide](sdk-users/3-development/parameter-passing-guide.md) (CRITICAL for avoiding validation errors)
3. **Architecture decisions** → [Architecture Decision Guide](sdk-users/architecture-decision-guide.md) | [Decision Matrix](sdk-users/decision-matrix.md)
4. **Feature discovery** → [Feature Discovery Guide](sdk-users/2-core-concepts/feature-discovery-guide.md) (**Use existing solutions first!**)
5. **Node selection** → [sdk-users/2-core-concepts/nodes/node-selection-guide.md](sdk-users/2-core-concepts/nodes/node-selection-guide.md)
6. **AI Agents with MCP** → Use `use_real_mcp=True` (default) for real tool execution
7. **Multi-agent coordination** → [sdk-users/2-core-concepts/cheatsheet/023-a2a-agent-coordination.md](sdk-users/2-core-concepts/cheatsheet/023-a2a-agent-coordination.md) (A2A agent cards, task delegation)
8. **Multi-channel apps** → [sdk-users/5-enterprise/nexus-patterns.md](sdk-users/5-enterprise/nexus-patterns.md) (API, CLI, MCP unified)
9. **Security & access control** → [sdk-users/5-enterprise/security-patterns.md](sdk-users/5-enterprise/security-patterns.md) (User management, RBAC, auth)
10. **Enterprise integration** → [sdk-users/5-enterprise/gateway-patterns.md](sdk-users/5-enterprise/gateway-patterns.md) (API gateways, external systems)
11. **Custom logic** → [sdk-users/2-core-concepts/cheatsheet/031-pythoncode-best-practices.md](sdk-users/2-core-concepts/cheatsheet/031-pythoncode-best-practices.md) (Use `.from_function()`)
12. **Custom nodes** → [sdk-users/3-development/05-custom-development.md](sdk-users/3-development/05-custom-development.md)
13. **Production deployment** → [sdk-users/5-enterprise/production-patterns.md](sdk-users/5-enterprise/production-patterns.md) (Scaling, monitoring)
14. **Enterprise resilience** → [sdk-users/5-enterprise/resilience-patterns.md](sdk-users/5-enterprise/resilience-patterns.md) (Circuit breaker, bulkhead, health monitoring)
15. **Edge computing** → [sdk-users/3-development/30-edge-computing-guide.md](sdk-users/3-development/30-edge-computing-guide.md) (EdgeCoordinationNode, distributed consensus)
16. **Distributed transactions** → [sdk-users/2-core-concepts/cheatsheet/049-distributed-transactions.md](sdk-users/2-core-concepts/cheatsheet/049-distributed-transactions.md) (Saga, 2PC, automatic pattern selection)
17. **Governance & compliance** → [sdk-users/5-enterprise/compliance-patterns.md](sdk-users/5-enterprise/compliance-patterns.md) (Audit, data policies)
18. **Common errors** → [sdk-users/2-core-concepts/validation/common-mistakes.md](sdk-users/2-core-concepts/validation/common-mistakes.md)

---

## 🏗️ Core SDK vs App Framework Architecture

### Core SDK Components (src/kailash/)
The **Core SDK** provides the foundational building blocks for workflow automation:

- **Runtime System**: `LocalRuntime`, `ParallelRuntime`, `DockerRuntime` - Execute workflows
- **Workflow Builder**: `WorkflowBuilder` - Create and configure workflows programmatically
- **Node Library**: 110+ production-ready nodes (AI, Data, Security, etc.)
- **MCP Integration**: Complete Model Context Protocol support for AI agents
- **Middleware**: API Gateway, Event Store, Checkpoint Manager for enterprise features

### App Framework (apps/)
The **App Framework** provides complete domain-specific applications built on the Core SDK:

- **kailash-dataflow**: Zero-config database framework with enterprise power
- **kailash-mcp**: Enterprise MCP platform with authentication, multi-tenancy, compliance
- **kailash-nexus**: Multi-channel platform (API, CLI, MCP) with unified sessions

### When to Use Each Approach

**Use Core SDK when:**
- Building custom workflows and automation
- Integrating with existing systems
- Need fine-grained control over execution
- Creating domain-specific solutions

**Use App Framework when:**
- Need complete, production-ready applications
- Want zero-configuration setup
- Require enterprise features (auth, compliance, multi-tenancy)
- Building on proven architectural patterns

### Development Paths

1. **Start with Core SDK**: Build workflows using `WorkflowBuilder` and `LocalRuntime`
2. **Add App Framework**: Integrate domain-specific apps for advanced features
3. **Enterprise Scale**: Use Nexus for multi-channel deployment with unified sessions

---

## 📁 Quick Access
| **Core SDK** | **App Framework** | **Contributors** |
|---------------|---------------------|-----------|
| [sdk-users/](sdk-users/) - Complete workflow guides | [apps/](apps/) - Production-ready applications | [# contrib (removed)/architecture/](# contrib (removed)/architecture/) |
| [sdk-users/2-core-concepts/nodes/node-selection-guide.md](sdk-users/2-core-concepts/nodes/node-selection-guide.md) - 110+ nodes | [sdk-users/4-apps/dataflow/](sdk-users/4-apps/dataflow/) - DataFlow guide (PyPI) | [# contrib (removed)/training/](# contrib (removed)/training/) |
| [sdk-users/2-core-concepts/cheatsheet/](sdk-users/2-core-concepts/cheatsheet/) - Copy-paste patterns | [sdk-users/4-apps/nexus/](sdk-users/4-apps/nexus/) - Nexus guide (PyPI) | [tests/](tests/) - 2,400+ tests |
| [sdk-users/5-enterprise/](sdk-users/5-enterprise/) - Advanced features | [apps/kailash-mcp/](apps/kailash-mcp/) - Enterprise MCP platform | [examples/](examples/) - Feature validation |

## ⚠️ MUST FOLLOW
1. **🚨 Node Execution**: ALWAYS use `.execute()` - NEVER `.run()`, `.process()`, or `.call()`
2. **SDK-First Development**: Use SDK components, NO custom orchestration
3. **Real Solutions Only**: Never simplify examples or use mock data
4. **Node Development Rules**: Names end with "Node", set attributes BEFORE `super().__init__()`
5. **PythonCodeNode Patterns**: Use `.from_function()` for multi-line code
6. **Middleware**: Use `create_gateway()` for production apps
7. **Git Safety**: NEVER destroy uncommitted work
    - ❌ **FORBIDDEN**: `git reset --hard`, `git clean -fd`, `rm -rf` on code
    - ✅ **REQUIRED**: `git add . && git commit -m "WIP"` before risky operations
    - ✅ Use `git stash` instead of destructive resets
    - 🚨 **ASK PERMISSION** before any potentially destructive git command
8. **AsyncNode Implementation**: CRITICAL patterns to avoid common mistakes
    - **Implement**: `async_run()` NOT `run()` in AsyncNode subclasses
    - **Tests**: Use `await node.execute_async()` NOT `await node.execute()`
    - **NodeParameter**: ALWAYS include `type` field (str, int, dict, object, etc.)
    - **Full Guide**: [AsyncNode Implementation Guide](sdk-users/3-development/async-node-guide.md)

## ⚡ Critical Patterns
1. **Data Paths**: `get_input_data_path()`, `get_output_data_path()`
2. **Access Control**: `AccessControlManager(strategy="rbac"|"abac"|"hybrid")`
3. **Execution Pattern - CRITICAL**:
   - **Users call**: `node.execute(**params)` - Public API with validation
   - **Nodes implement**: `def run(self, **kwargs)` - Protected method with actual logic
   - **Never override**: `execute()` in custom nodes - breaks validation chain
4. **Ollama Embeddings**: Extract with `[emb["embedding"] for emb in result["embeddings"]]`
5. **Cyclic Workflows - Class-Specific Patterns**:
   - **WorkflowBuilder**: `built = workflow.build(); built.create_cycle("name").connect(...).build()`
   - **Workflow**: `workflow.create_cycle("name").connect(...).build()` (direct chaining)
   - **SwitchNode Cycles**: Forward connections first, then cycle: `workflow.connect(); workflow.create_cycle()`
6. **WorkflowBuilder**: String-based `add_node("CSVReaderNode", ...)`, 4-param `add_connection()`
7. **MCP Integration**: 100% validated, comprehensive testing (407 tests, 100% pass rate) - see [MCP Guide](sdk-users/2-core-concepts/cheatsheet/025-mcp-integration.md)
8. **MCP Real Execution**: All AI agents use `use_real_mcp=True` by default (v0.6.6+) - BREAKING CHANGE from mock execution
9. **Documentation**: Comprehensive validation across 9 critical phases, 100% pass rates achieved - see [SDK Users](sdk-users/) navigation hub
10. **Enterprise Resilience**: Circuit breaker, bulkhead isolation, health monitoring - see [Resilience Patterns](sdk-users/5-enterprise/resilience-patterns.md)
11. **Transaction Monitoring**: 5 production-tested nodes for metrics, deadlock detection, race conditions - see [Transaction Monitoring](sdk-users/2-core-concepts/cheatsheet/048-transaction-monitoring.md)
12. **Distributed Transactions**: Automatic pattern selection (Saga/2PC), compensation logic, recovery - see [Distributed Transactions](sdk-users/2-core-concepts/cheatsheet/049-distributed-transactions.md)
13. **AsyncSQL Parameter Types**: PostgreSQL type inference fix with `parameter_types` for JSONB/COALESCE contexts (v0.6.6+) - see [AsyncSQL Patterns](sdk-users/2-core-concepts/cheatsheet/047-asyncsql-enterprise-patterns.md)
14. **Core SDK Architecture**: TODO-111 resolved critical infrastructure gaps - CyclicWorkflowExecutor, WorkflowVisualizer, and ConnectionManager now production-ready with comprehensive test coverage
15. **Parameter Naming Convention**: Use `action` (not `operation`) for consistency across nodes
16. **Test Performance**: Run unit tests directly for 11x faster execution: `pytest tests/unit/`
17. **Connection Parameter Validation** (v0.8.4+): Enterprise security with comprehensive validation
    - Use `LocalRuntime(connection_validation="strict")` for production
    - Connection contracts with `workflow.add_typed_connection(..., contract_name="no_pii_data")`
    - Type-safe ports with `InputPort[str] = StringPort(required=True)`
    - Monitoring with `get_validation_metrics()` and `AlertManager`
    - Performance optimization with caching and batch validation

## 🔧 Core Nodes (110+ available)
**Quick Access**: [Node Index](sdk-users/2-core-concepts/nodes/node-index.md) - Minimal reference (47 lines)
**Choose Smart**: [Node Selection Guide](sdk-users/2-core-concepts/nodes/node-selection-guide.md) - Decision trees + quick finder
**AI**: **LLMAgentNode**, **IterativeLLMAgentNode** (real MCP execution by default), MonitoredLLMAgentNode, EmbeddingGeneratorNode, A2AAgentNode, SelfOrganizingAgentNode
**Data**: CSVReaderNode, JSONReaderNode, SQLDatabaseNode, AsyncSQLDatabaseNode, DirectoryReaderNode
**RAG**: 47+ specialized nodes - see [RAG Guide](sdk-users/3-development/06-comprehensive-rag-guide.md)
**API**: HTTPRequestNode, RESTClientNode, OAuth2Node, GraphQLClientNode
**Logic**: SwitchNode, MergeNode, WorkflowNode, ConvergenceCheckerNode
**Enterprise**: MultiFactorAuthNode, ThreatDetectionNode, AccessControlManager, GDPRComplianceNode
**Monitoring**: TransactionMetricsNode, TransactionMonitorNode, DeadlockDetectorNode, RaceConditionDetectorNode, PerformanceAnomalyNode - see [Monitoring Guide](sdk-users/2-core-concepts/nodes/monitoring-nodes.md)
**Transactions**: DistributedTransactionManagerNode, SagaCoordinatorNode, TwoPhaseCommitCoordinatorNode - see [Transaction Guide](sdk-users/2-core-concepts/nodes/transaction-nodes.md)
**Full catalog**: [Complete Node Catalog](sdk-users/2-core-concepts/nodes/comprehensive-node-catalog.md) (2194 lines - use sparingly)

## 📂 Directory Navigation Convention
**File Naming Standard**:
- **README.md** = Directory index/navigation (what's here, where to go)
- **QUICK_REFERENCE.md** = Hands-on implementation guide (code patterns, quick fixes)
- **Numbered guides** = Detailed topic-specific documentation

## 🏗️ Architecture Decisions

**For app building guidance:** → [sdk-users/decision-matrix.md](sdk-users/decision-matrix.md)

**Before any app implementation:**
1. Enter `sdk-users/` directory to load full architectural guidance
2. Check decision matrix for patterns and trade-offs
3. Reference complete app guide as needed

## 🔗 Quick Links by Need

| **I need to...** | **Core SDK** | **App Framework** | **Contributors** |
|-----------------|--------------|---------------------|-----------|
| **Build a workflow** | [sdk-users/2-core-concepts/workflows/](sdk-users/2-core-concepts/workflows/) | - | - |
| **Cyclic workflows** | [sdk-users/2-core-concepts/workflows/by-pattern/cyclic/](sdk-users/2-core-concepts/workflows/by-pattern/cyclic/) - Working examples | - | - |
| **Build an app** | [sdk-users/decision-matrix.md](sdk-users/decision-matrix.md) | [apps/DOCUMENTATION_STANDARDS.md](apps/DOCUMENTATION_STANDARDS.md) | - |
| **Database operations** | [sdk-users/2-core-concepts/cheatsheet/047-asyncsql-enterprise-patterns.md](sdk-users/2-core-concepts/cheatsheet/047-asyncsql-enterprise-patterns.md) | [apps/kailash-dataflow/](apps/kailash-dataflow/) - Zero-config | - |
| **Multi-channel platform** | [sdk-users/5-enterprise/nexus-patterns.md](sdk-users/5-enterprise/nexus-patterns.md) | [apps/kailash-nexus/](apps/kailash-nexus/) - Production-ready | - |
| **MCP integration** | [sdk-users/2-core-concepts/cheatsheet/025-mcp-integration.md](sdk-users/2-core-concepts/cheatsheet/025-mcp-integration.md) | [apps/kailash-mcp/](apps/kailash-mcp/) - Enterprise platform | - |
| **AI & RAG** | [sdk-users/3-development/06-comprehensive-rag-guide.md](sdk-users/3-development/06-comprehensive-rag-guide.md) | [apps/ai_registry/](apps/ai_registry/) - Advanced RAG | - |
| **User management** | [sdk-users/5-enterprise/security-patterns.md](sdk-users/5-enterprise/security-patterns.md) | [apps/user_management/](apps/user_management/) - RBAC system | - |
| **Fix an error** | [sdk-users/3-development/05-troubleshooting.md](sdk-users/3-development/05-troubleshooting.md) | [shared/mistakes/](shared/mistakes/) | [shared/mistakes/](shared/mistakes/) |
| **Distributed transactions** | [sdk-users/2-core-concepts/cheatsheet/049-distributed-transactions.md](sdk-users/2-core-concepts/cheatsheet/049-distributed-transactions.md) | - | - |
| **Run tests**   | [tests/README.md](tests/README.md) - Test guide | [tests/](tests/) - Full test suite | [tests/](tests/) - Full test suite |
| **Train LLMs**  | - | - | [# contrib (removed)/training/](# contrib (removed)/training/) |
| **Design architecture** | - | - | [# contrib (removed)/architecture/](# contrib (removed)/architecture/) |

## 🧪 CRITICAL: Testing Requirements
- **Test Guide**: [tests/README.md](tests/README.md) - 3-tier testing strategy

### 1. Fast Unit Tests
**Run unit tests directly**: `pytest tests/unit/ --timeout=1 --tb=short`
- 11x faster execution without process forking overhead
- Proper test isolation through fixtures
- 99.96% pass rate with optimized state management
- Tests requiring isolation (< 1%) are automatically handled with `@pytest.mark.requires_isolation`

### 2. Timeout Enforcement
**ALWAYS enforce timeout limits**:
- **Unit tests**: 1 second max (`--timeout=1`)
- **Integration tests**: 5 seconds max (`--timeout=5`)
- **E2E tests**: 10 seconds max (`--timeout=10`)

### 3. Fix Timeout Violations
When tests exceed timeout:
1. Check for `asyncio.sleep(10)` → change to `asyncio.sleep(0.1)`
2. Check actor/pool cleanup → add proper task cancellation
3. Check database configs → use `health_check_interval=0.1`
4. Mock slow services instead of real calls
5. Use smaller test datasets
6. Add proper cleanup in finally blocks

Use centralized `tests/node_registry_utils.py` for consistent node management

## 📁 Organization Principles
- **Core SDK** → `src/kailash/` (foundational components) + `sdk-users/` (usage guides)
- **App Framework** → `apps/` (complete applications) + domain-specific docs
- **Production workflows** → `sdk-users/2-core-concepts/workflows/` (business value)
- **SDK development** → `examples/` (feature validation)
- **SDK core tests** → `tests/` (unit/integration/e2e for SDK only)
- **App-specific tests** → `apps/*/tests/` (DataFlow, Nexus, etc. have their own test folders)
- **Training data** → `# contrib (removed)/training/` (LLM patterns)
