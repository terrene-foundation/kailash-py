# Kailash SDK - Development Guide

## 🚀 ESSENTIAL PATTERNS - COPY THESE FIRST

### Basic Workflow (Required Foundation)
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", {"model": "gpt-4"})  # All classes end with "Node"
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())  # runtime executes workflow
```

### ❌ NEVER
- `workflow.execute(runtime)` → Use `runtime.execute(workflow)`
- `workflow.addNode()` → Use `workflow.add_node()`
- `inputs={}` → Use `parameters={}`
- String code in PythonCodeNode → Use `.from_function()` (step 4)

### 🎯 Multi-Step Strategy (Enterprise Workflow)
1. **First implementation** → Copy basic pattern above
2. **Architecture decisions** → [sdk-users/decision-matrix.md](sdk-users/decision-matrix.md)
3. **Node selection** → [sdk-users/nodes/node-selection-guide.md](sdk-users/nodes/node-selection-guide.md)
4. **Security & access control** → [sdk-users/enterprise/security-patterns.md](sdk-users/enterprise/security-patterns.md) (User management, RBAC, auth)
5. **Enterprise integration** → [sdk-users/enterprise/gateway-patterns.md](sdk-users/enterprise/gateway-patterns.md) (API gateways, external systems)
6. **Custom logic** → [sdk-users/cheatsheet/031-pythoncode-best-practices.md](sdk-users/cheatsheet/031-pythoncode-best-practices.md) (Use `.from_function()`)
7. **Custom nodes** → [sdk-users/developer/05-custom-development.md](sdk-users/developer/05-custom-development.md)
8. **Production deployment** → [sdk-users/enterprise/production-patterns.md](sdk-users/enterprise/production-patterns.md) (Scaling, monitoring)
9. **Enterprise resilience** → [sdk-users/enterprise/resilience-patterns.md](sdk-users/enterprise/resilience-patterns.md) (Circuit breaker, bulkhead, health monitoring)
10. **Distributed transactions** → [sdk-users/cheatsheet/049-distributed-transactions.md](sdk-users/cheatsheet/049-distributed-transactions.md) (Saga, 2PC, automatic pattern selection)
11. **Governance & compliance** → [sdk-users/enterprise/compliance-patterns.md](sdk-users/enterprise/compliance-patterns.md) (Audit, data policies)
12. **Common errors** → [sdk-users/validation/common-mistakes.md](sdk-users/validation/common-mistakes.md)

---

## 📁 Quick Access
| **SDK Users** | **SDK Contributors** | **Shared** |
|---------------|---------------------|-----------|
| [sdk-users/](sdk-users/) | [# contrib (removed)/architecture/](# contrib (removed)/architecture/) | [shared/mistakes/](shared/mistakes/) |
| [sdk-users/nodes/node-selection-guide.md](sdk-users/nodes/node-selection-guide.md) | [# contrib (removed)/training/](# contrib (removed)/training/) | [tests/](tests/) |
| [sdk-users/cheatsheet/](sdk-users/cheatsheet/) | [# contrib (removed)/research/](# contrib (removed)/research/) | [examples/](examples/) |
| [sdk-users/migration-guides/](sdk-users/migration-guides/) | [# contrib (removed)/architecture/migration-guides/](# contrib (removed)/architecture/migration-guides/) | |

## ⚠️ MUST FOLLOW
1. **🚨 Node Execution**: ALWAYS use `.execute()` - NEVER `.run()`, `.process()`, or `.call()`
2. **SDK-First Development**: Use SDK components, NO custom orchestration
3. **Real Solutions Only**: Never simplify examples or use mock data
4. **Node Development Rules**: Names end with "Node", set attributes BEFORE `super().__init__()`
5. **PythonCodeNode Patterns**: Use `.from_function()` for multi-line code
6. **Middleware**: Use `create_gateway()` for production apps
7. **Git Safety**: NEVER destroy uncommitted work

6. **Git Safety**: NEVER destroy uncommitted work
    - ❌ **FORBIDDEN**: `git reset --hard`, `git clean -fd`, `rm -rf` on code
    - ✅ **REQUIRED**: `git add . && git commit -m "WIP"` before risky operations
    - ✅ Use `git stash` instead of destructive resets
    - 🚨 **ASK PERMISSION** before any potentially destructive git command

## ⚡ Critical Patterns
1. **Data Paths**: `get_input_data_path()`, `get_output_data_path()`
2. **Access Control**: `AccessControlManager(strategy="rbac"|"abac"|"hybrid")`
3. **Execution**: Use `.execute()` not `.run()` or `.process()` or `.call()`
4. **Ollama Embeddings**: Extract with `[emb["embedding"] for emb in result["embeddings"]]`
5. **Cyclic Workflows**: Preserve state with `set_cycle_state()`, explicit parameter mapping
6. **WorkflowBuilder**: String-based `add_node("CSVReaderNode", ...)`, 4-param `add_connection()`
7. **MCP Integration**: 100% validated, comprehensive testing (407 tests, 100% pass rate) - see [MCP Guide](sdk-users/cheatsheet/025-mcp-integration.md)
8. **Documentation**: Comprehensive validation across 9 critical phases, 100% pass rates achieved - see [SDK Users](sdk-users/) navigation hub
9. **Enterprise Resilience**: Circuit breaker, bulkhead isolation, health monitoring - see [Resilience Patterns](sdk-users/enterprise/resilience-patterns.md)
10. **Transaction Monitoring**: 5 production-tested nodes for metrics, deadlock detection, race conditions - see [Transaction Monitoring](sdk-users/cheatsheet/048-transaction-monitoring.md)
11. **Distributed Transactions**: Automatic pattern selection (Saga/2PC), compensation logic, recovery - see [Distributed Transactions](sdk-users/cheatsheet/049-distributed-transactions.md)

## 🔧 Core Nodes (110+ available)
**Quick Access**: [Node Index](sdk-users/nodes/node-index.md) - Minimal reference (47 lines)
**Choose Smart**: [Node Selection Guide](sdk-users/nodes/node-selection-guide.md) - Decision trees + quick finder
**AI**: LLMAgentNode, MonitoredLLMAgentNode, EmbeddingGeneratorNode, A2AAgentNode, SelfOrganizingAgentNode
**Data**: CSVReaderNode, JSONReaderNode, SQLDatabaseNode, AsyncSQLDatabaseNode, DirectoryReaderNode
**RAG**: 47+ specialized nodes - see [RAG Guide](sdk-users/developer/06-comprehensive-rag-guide.md)
**API**: HTTPRequestNode, RESTClientNode, OAuth2Node, GraphQLClientNode
**Logic**: SwitchNode, MergeNode, WorkflowNode, ConvergenceCheckerNode
**Enterprise**: MultiFactorAuthNode, ThreatDetectionNode, AccessControlManager, GDPRComplianceNode
**Monitoring**: TransactionMetricsNode, TransactionMonitorNode, DeadlockDetectorNode, RaceConditionDetectorNode, PerformanceAnomalyNode - see [Monitoring Guide](sdk-users/nodes/monitoring-nodes.md)
**Transactions**: DistributedTransactionManagerNode, SagaCoordinatorNode, TwoPhaseCommitCoordinatorNode - see [Transaction Guide](sdk-users/nodes/transaction-nodes.md)
**Full catalog**: [Complete Node Catalog](sdk-users/nodes/comprehensive-node-catalog.md) (2194 lines - use sparingly)

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

| **I need to...** | **SDK User** | **SDK Contributor** |
|-----------------|--------------|---------------------|
| **Build a workflow** | [sdk-users/workflows/](sdk-users/workflows/) | - |
| **Build an app** | [apps/APP_DEVELOPMENT_GUIDE.md](apps/APP_DEVELOPMENT_GUIDE.md) | - |
| **Make arch decisions** | [sdk-users/decision-matrix.md](sdk-users/decision-matrix.md) | [Architecture ADRs](# contrib (removed)/architecture/adr/) |
| **Fix an error** | [sdk-users/developer/05-troubleshooting.md](sdk-users/developer/05-troubleshooting.md) | [shared/mistakes/](shared/mistakes/) |
| **Find patterns** | [sdk-users/patterns/](sdk-users/patterns/) | - |
| **Learn from workflows** | [sdk-users/workflows/](sdk-users/workflows/) - Production workflows | - |
| **Distributed transactions** | [sdk-users/cheatsheet/049-distributed-transactions.md](sdk-users/cheatsheet/049-distributed-transactions.md) - Saga/2PC patterns | - |
| **Run tests**   | [tests/README.md](tests/README.md) - Test guide | [tests/](tests/) - Full test suite |
| **SDK development** | [examples/](examples/) - Feature validation | - |
| **Train LLMs**  | - | [# contrib (removed)/training/](# contrib (removed)/training/) |
| **Design architecture** | - | [# contrib (removed)/architecture/](# contrib (removed)/architecture/) |
| **Version operations** | - | [# contrib (removed)/operations/](# contrib (removed)/operations/) |
| **Track todos** | - | [# contrib (removed)/project/todos/](# contrib (removed)/project/todos/) |

## 📁 Organization Principles
- **Production workflows** → `sdk-users/workflows/` (business value)
- **SDK development** → `examples/` (feature validation)
- **Quality validation** → `tests/` (unit/integration/e2e)
- **Training data** → `# contrib (removed)/training/` (LLM patterns)

## 🎯 Quick Start Guide

**Building Apps/Workflows:**
- **Start**: [sdk-users/](sdk-users/) - Complete solution guide with decision matrix
- **Node Selection**: [Node Selection Guide](sdk-users/nodes/node-selection-guide.md) - Smart finder
- **Quick Patterns**: [Cheatsheet](sdk-users/cheatsheet/) - 37 copy-paste patterns
- **Enterprise**: [Enterprise Patterns](sdk-users/enterprise/) - Advanced features

**SDK Development:**
- **Contributing**: [# contrib (removed)/CLAUDE.md](# contrib (removed)/CLAUDE.md)
- **Architecture**: [# contrib (removed)/architecture/](# contrib (removed)/architecture/)
- **Examples**: [examples/](examples/) - Feature validation

**Testing:**
- **Test Suite**: 2,395+ tests (Unit: 1,606, Integration: 225, E2E: 16 core)
- **MCP Testing**: 407 comprehensive tests across 8 components (100% pass rate)
- **Transaction Monitoring**: 219 unit tests, 8 integration tests, comprehensive E2E (100% pass rate)
- **Distributed Transactions**: 122 unit tests, 23 integration tests, comprehensive E2E (100% pass rate)
- **Test Guide**: [tests/README.md](tests/README.md) - 3-tier testing strategy
- **CI/CD**: Sub-10 minute test execution with Docker infrastructure

**Need Help:**
- **Errors**: [Troubleshooting](sdk-users/developer/05-troubleshooting.md)
- **Common Mistakes**: [sdk-users/validation/common-mistakes.md](sdk-users/validation/common-mistakes.md)
- **New Team**: [NEW_TEAM_MEMBER.md](NEW_TEAM_MEMBER.md)
