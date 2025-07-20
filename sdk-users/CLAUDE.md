# SDK Users - Navigation Hub

*Building solutions WITH the Kailash SDK*

## ⚡ CORE IMPLEMENTATION PATTERNS

### 🚀 Common API Patterns - Quick Reference

#### **Pattern 1: Data Processing Pipeline**
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Most common pattern - data in, process, data out
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "read", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "process", {"code": "result = len(data)"})
workflow.add_node("CSVWriterNode", "write", {"file_path": "output.csv"})

# Connect with 4-parameter syntax: source, source_port, target, target_port
workflow.add_connection("read", "data", "process", "data")
workflow.add_connection("process", "result", "write", "data")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

#### **Pattern 2: AI Analysis Workflow**
```python
# AI-powered analysis with real MCP execution
workflow = WorkflowBuilder()
workflow.add_node("JSONReaderNode", "input", {"file_path": "input.json"})
workflow.add_node("LLMAgentNode", "analyzer", {
    "model": "gpt-4",
    "prompt": "Analyze this data: {data}",
    "use_real_mcp": True  # Real MCP execution (default in v0.6.6+)
})
workflow.add_node("JSONWriterNode", "output", {"file_path": "analysis.json"})

workflow.add_connection("input", "data", "analyzer", "data")
workflow.add_connection("analyzer", "result", "output", "data")
```

#### **Pattern 3: API Integration Pipeline**
```python
# External API integration with error handling
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "api", {
    "url": "https://api.example.com/data",
    "method": "GET",
    "headers": {"Authorization": "Bearer {token}"}
})
workflow.add_node("PythonCodeNode", "transform", {
    "code": "result = {'processed': len(data), 'items': data}"
})
workflow.add_node("SQLDatabaseNode", "store", {
    "connection_string": "postgresql://localhost/db",
    "table": "processed_data",
    "operation": "insert"
})

workflow.add_connection("api", "response", "transform", "data")
workflow.add_connection("transform", "result", "store", "data")
```

### 🎯 Node Selection Decision Tree

**Question 1: What type of operation?**
- **Data Processing** → CSVReaderNode, JSONReaderNode, DataTransformer
- **AI/ML Operations** → LLMAgentNode, EmbeddingGeneratorNode, A2AAgentNode
- **API Integration** → HTTPRequestNode, RESTClientNode, GraphQLClientNode
- **Database Operations** → SQLDatabaseNode, AsyncSQLDatabaseNode, QueryBuilder
- **Logic & Control** → SwitchNode, MergeNode, ConvergenceCheckerNode
- **Custom Logic** → PythonCodeNode (use `.from_function()` for >3 lines)

**Question 2: Performance requirements?**
- **High throughput** → BulkCreateNode, BulkUpdateNode, AsyncSQLDatabaseNode
- **Real-time** → WebSocketNode, EventStreamNode, MonitoringNode
- **Batch processing** → PythonCodeNode, DataTransformer, BulkOperationNode

**Question 3: Security requirements?**
- **Authentication** → OAuth2Node, MultiFactorAuthNode, AccessControlManager
- **Data protection** → EncryptionNode, GDPRComplianceNode, AuditTrailNode
- **Threat detection** → ThreatDetectionNode, SecurityMonitoringNode

### 🔧 Common Mistakes and Solutions

#### **Mistake 1: Wrong API Pattern**
```python
# ❌ DON'T: Instance-based API (deprecated)
workflow.add_node("reader", CSVReaderNode(), {"file_path": "data.csv"})

# ✅ DO: String-based API (correct)
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
```

#### **Mistake 2: Incorrect Connection Syntax**
```python
# ❌ DON'T: 2-parameter connections
workflow.connect("source", "target")

# ✅ DO: 4-parameter connections
workflow.add_connection("source", "data", "target", "input")
```

#### **Mistake 3: Missing Workflow Build**
```python
# ❌ DON'T: Execute without building
runtime.execute(workflow)

# ✅ DO: Always build before execution
runtime.execute(workflow.build())
```

#### **Mistake 4: Wrong PythonCodeNode Usage**
```python
# ❌ DON'T: Long string code
workflow.add_node("PythonCodeNode", "process", {
    "code": "very_long_multi_line_string..."
})

# ✅ DO: Use from_function for >3 lines
def process_data(data):
    return {"processed": len(data), "items": data}

workflow.add_node("process", PythonCodeNode.from_function(process_data))
```

### 📚 Quick Links to Cheatsheets

- **🔗 Connection Patterns**: [cheatsheet/005-connection-patterns.md](cheatsheet/005-connection-patterns.md)
- **🔗 Node Selection**: [nodes/node-selection-guide.md](nodes/node-selection-guide.md)
- **🔗 Common Workflows**: [cheatsheet/012-common-workflow-patterns.md](cheatsheet/012-common-workflow-patterns.md)
- **🔗 PythonCodeNode Best Practices**: [cheatsheet/031-pythoncode-best-practices.md](cheatsheet/031-pythoncode-best-practices.md)
- **🔗 Error Fixes**: [validation/common-mistakes.md](validation/common-mistakes.md)

### Enterprise Workflow (Complete Pattern)
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "api", {"url": "https://api.example.com/data"})
workflow.add_node("LLMAgentNode", "analyzer", {"model": "gpt-4"})
workflow.add_connection("api", "response", "analyzer", "input_data")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Enterprise App Architecture
```python
from kailash.servers.gateway import create_gateway

# Single-channel API gateway with enterprise features
app = create_gateway(
    title="Enterprise Gateway",
    server_type="enterprise",  # Uses EnterpriseWorkflowServer
    enable_durability=True,
    enable_resource_management=True,
    enable_async_execution=True
)
```

### Multi-Channel Architecture
```python
from kailash.channels.api_channel import APIChannel
from kailash.channels.cli_channel import CLIChannel
from kailash.channels.base import ChannelConfig, ChannelType

# Create API channel
api_config = ChannelConfig(
    name="workflow_api",
    channel_type=ChannelType.API,
    host="localhost",
    port=8000,
    enable_sessions=True,
    enable_auth=True
)
api_channel = APIChannel(api_config)

# Register workflows
api_channel.register_workflow("data-processor", workflow)
api_channel.start()
```

### Node Selection Priority
```python
# ✅ ALWAYS use specialized nodes first
from kailash.nodes.ai import LLMAgentNode        # NOT custom API calls
from kailash.nodes.api import HTTPRequestNode    # NOT requests library
from kailash.nodes.admin import UserManagementNode  # NOT custom auth
from kailash.nodes.data import CSVReaderNode     # NOT PythonCodeNode for files
from kailash.nodes.data import QueryBuilder     # NOT raw SQL strings
from kailash.nodes.data import QueryCache       # NOT manual Redis
```

### Query Builder & Cache (New v0.6.6+)
```python
from kailash.nodes.data.query_builder import QueryBuilder, create_query_builder
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

# MongoDB-style query building
builder = create_query_builder("postgresql")
builder.table("users").where("age", "$gt", 18).where("status", "$eq", "active")
sql, params = builder.build_select(["name", "email"])

# Redis query caching with pattern-based invalidation
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED
)
```

### Parameter Patterns
```python
# Dot notation for nested outputs
workflow.connect("processor", "result.data", mapping={"analyzer": "input"})

# Runtime overrides
runtime.execute(workflow, parameters={"reader": {"file_path": "new.csv"}})
```

### Test-Driven Development Patterns (TODO-111)
```python
# 3-tier testing strategy from TODO-111
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor
from kailash.workflow.visualization import WorkflowVisualizer
from kailash.middleware.communication.realtime import ConnectionManager

# Unit Tests: Fast, isolated testing
def test_cyclic_execution():
    executor = CyclicWorkflowExecutor()
    # Test critical methods: _execute_dag_portion, _execute_cycle_groups, _propagate_parameters

# Integration Tests: Real Docker services
def test_workflow_visualization():
    visualizer = WorkflowVisualizer()  # Optional workflow parameter
    # Test with real workflow instances

# E2E Tests: Full scenarios
def test_event_handling():
    manager = ConnectionManager()
    # Test filter_events() and process_event() with real connections
```

---

## 🚀 Enterprise Architecture & Multi-Channel Platform

**🌉 Unified Nexus Platform**: Next-generation multi-channel orchestration with `create_nexus()` - single function creates API, CLI, and MCP interfaces with unified sessions and cross-channel communication.

**🔄 Multi-Channel Communication**: WebSocket/SSE streaming, CLI command interface, MCP tool/resource discovery with synchronized sessions across all channels.

**🤖 Enhanced Gateway Architecture**: Production-ready enterprise platform with `create_gateway()` - fully redesigned server classes (EnterpriseWorkflowServer, DurableWorkflowServer, WorkflowServer) with improved naming and enterprise defaults.

**⚡ Channel Abstraction Framework**: Unified interface management across API, CLI, and MCP channels with cross-channel session management and event routing.

**⚡ Unified Async Runtime**: Production-ready AsyncLocalRuntime with 2-10x performance gains. See [developer/10-unified-async-runtime-guide.md](developer/10-unified-async-runtime-guide.md) for complete guide.

**🔧 Resource Registry**: Centralized resource management for database pools, HTTP clients, and caches. See [developer/08-resource-registry-guide.md](developer/08-resource-registry-guide.md) for patterns.

**🚀 AsyncWorkflowBuilder**: Async-first workflow builder with 70%+ code reduction. Built-in patterns (retry, rate limit, timeout, batch, circuit breaker). See [developer/07-async-workflow-builder.md](developer/07-async-workflow-builder.md) and [workflows/async/async-workflow-builder-guide.md](workflows/async/async-workflow-builder-guide.md).

**🛡️ Enterprise Resilience Patterns**: Production-grade fault tolerance with circuit breakers, bulkhead isolation, and health monitoring. Circuit breakers prevent cascade failures with configurable thresholds. Bulkhead isolation partitions resources by operation type. Health monitoring provides real-time infrastructure status with alerting. See [enterprise/resilience-patterns.md](enterprise/resilience-patterns.md).

**🔗 Dot Notation Mapping**: Access nested node outputs with `"result.data"`, `"result.metrics"`, `"source.nested.field"` in workflow connections.

**🎯 Auto-Mapping Parameters**: NodeParameter supports `auto_map_primary=True`, `auto_map_from=["alt1"]`, `workflow_alias="name"` for automatic connection discovery.

**🧪 Production-Certified Testing Framework**: Comprehensive async testing with Docker integration, Ollama LLM workflows, performance validation, and variable passing fully resolved. **TODO-111**: Core SDK architecture now includes 67 comprehensive tests for CyclicWorkflowExecutor, WorkflowVisualizer, and ConnectionManager with 100% pass rate. See [developer/12-testing-production-quality.md](developer/12-testing-production-quality.md).

**🏥 Enterprise MCP Workflows**: Complete healthcare HIPAA, finance SOX, and multi-tenant patterns with 4 production-grade enterprise nodes. See [cheatsheet/040-enterprise-mcp-workflows.md](cheatsheet/040-enterprise-mcp-workflows.md).

**📊 Transaction Monitoring**: Enterprise-grade transaction metrics, deadlock detection, race condition analysis, and performance anomaly detection with 5 production-tested monitoring nodes. **v0.6.6+ Enhanced**: New operations (`complete_transaction`, `acquire_resource`, `request_resource`, `complete_operation`), success rate calculations, alias support, and improved AsyncNode event loop handling. See [cheatsheet/048-transaction-monitoring.md](cheatsheet/048-transaction-monitoring.md) and [nodes/monitoring-nodes.md](nodes/monitoring-nodes.md).

**🔄 Distributed Transaction Management**: Enterprise-grade transaction patterns with automatic pattern selection. Supports Saga pattern for high availability and Two-Phase Commit for strong consistency. Includes compensation logic, state persistence, and recovery mechanisms. Complete with 122 unit tests and 23 integration tests. See [cheatsheet/049-distributed-transactions.md](cheatsheet/049-distributed-transactions.md) and [nodes/transaction-nodes.md](nodes/transaction-nodes.md).

**🧪 Comprehensive Validation Framework**: Test-driven development with multi-level code validation, workflow validation, and comprehensive test execution. Features enhanced IterativeLLMAgentNode with **real MCP tool execution** (v0.6.5+) and test-driven convergence that only stops when deliverables actually work. Includes sandbox execution, schema validation, and automated quality gates. See [developer/13-validation-framework-guide.md](developer/13-validation-framework-guide.md) and [cheatsheet/050-validation-testing-patterns.md](cheatsheet/050-validation-testing-patterns.md).

**🔌 Nexus Multi-Channel Framework**: Complete multi-channel orchestration platform supporting API, CLI, and MCP interfaces with unified session management. Features cross-channel event routing, synchronized state management, and comprehensive channel abstraction. **MCP initialization issues fully resolved** - fixes WorkflowBuilder syntax, parameter passing, and initialization order. See [cheatsheet/051-nexus-multi-channel-patterns.md](cheatsheet/051-nexus-multi-channel-patterns.md) and [enterprise/nexus-patterns.md](enterprise/nexus-patterns.md).

**🗄️ MongoDB-Style Query Builder**: Production-ready query builder with MongoDB-style operators ($eq, $ne, $lt, $gt, $in, $regex, etc.) that generates optimized SQL for PostgreSQL, MySQL, and SQLite. Includes automatic tenant isolation, multi-database support, and comprehensive validation. Complete with 33 unit tests, 8 integration tests, and real Redis caching. See [cheatsheet/052-query-builder-patterns.md](cheatsheet/052-query-builder-patterns.md) and [nodes/03-data-nodes.md](nodes/03-data-nodes.md).

**⚡ Redis Query Cache**: Enterprise-grade query result caching with Redis backend. Features automatic cache key generation, TTL management, pattern-based invalidation, tenant isolation, and comprehensive health monitoring. Supports multiple invalidation strategies (TTL, pattern-based, event-based) with production-tested performance. Complete with 40 unit tests and 8 integration tests. See [cheatsheet/053-query-cache-patterns.md](cheatsheet/053-query-cache-patterns.md) and [developer/16-query-cache-guide.md](developer/16-query-cache-guide.md).

**🌍 Edge Computing with WorkflowBuilder**: Seamless geo-distributed computing with automatic edge infrastructure management. Features compliance-aware data routing, multiple consistency models (strong, eventual, causal, bounded staleness), and singleton resource sharing. Supports EdgeDataNode for distributed data, EdgeStateMachine for globally unique state instances, and custom edge nodes. Complete with DataFlow integration and zero-config operation. See [developer/edge-workflowbuilder-guide.md](developer/edge-workflowbuilder-guide.md).

**🚀 Nexus Production Hardening** ⭐ **NEW** (2025-07-10): Enterprise-grade production deployment with 100% hardening complete. Features complete Terraform infrastructure automation (AWS EKS, RDS, ElastiCache), performance baseline validation (31.8M ops/sec), zero-vulnerability security compliance, and comprehensive operational documentation. Nexus is now **production-ready** with enterprise monitoring, authentication, and infrastructure automation. See [../apps/kailash-nexus/docs/operations/](../apps/kailash-nexus/docs/operations/) and [../apps/kailash-nexus/docs/performance/](../apps/kailash-nexus/docs/performance/).

**🏗️ DataFlow Architectural Modernization** ⭐ **ACTIVE** (TODO-107): DataFlow framework is undergoing architectural refactoring from monolithic structure to modern modular design for enhanced maintainability and developer experience. All existing functionality remains fully compatible during transition. See [../apps/kailash-dataflow/docs/adr/](../apps/kailash-dataflow/docs/adr/) for architecture decisions.

## 🏗️ Architecture Decisions First

**⚠️ STOP! Before building any app, make these critical decisions:**

### 🔗 App Frameworks Navigation
- **DataFlow (Database)**: [../apps/kailash-dataflow/CLAUDE.md](../apps/kailash-dataflow/CLAUDE.md) - Zero-config database with enterprise power
- **Nexus (Multi-Channel)**: [../apps/kailash-nexus/CLAUDE.md](../apps/kailash-nexus/CLAUDE.md) - Unified API, CLI, MCP platform

### 📋 Decision Matrix → [decision-matrix.md](decision-matrix.md)

The decision matrix provides fast answers to:
- **Workflow Pattern**: Inline vs Class-based vs Hybrid construction
- **Interface Routing**: MCP vs Direct calls vs Hybrid routing
- **Performance Strategy**: Latency thresholds and optimization approaches
- **Common Combinations**: Recommended patterns for different app types

### 📚 Complete Implementation Guidance

| Decision Type | Quick Decisions | Implementation Guide |
|---------------|-----------------|---------------------|
| **Workflow Construction** | [decision-matrix.md](decision-matrix.md) | [Apps Guide](../apps/APP_DEVELOPMENT_GUIDE.md) |
| **Interface Routing** | [decision-matrix.md](decision-matrix.md) | [Apps Guide](../apps/APP_DEVELOPMENT_GUIDE.md) |
| **Performance Strategy** | [decision-matrix.md](decision-matrix.md) | [Apps Guide](../apps/APP_DEVELOPMENT_GUIDE.md) |

## 🎯 Quick Navigation Guide
| I need to... | Go to | Purpose |
|--------------|-------|---------|
| **Make architecture decisions** | [decision-matrix.md](decision-matrix.md) | Choose workflow patterns, routing |
| **Build complete app** | [../apps/APP_DEVELOPMENT_GUIDE.md](../apps/APP_DEVELOPMENT_GUIDE.md) | App implementation guide |
| **Find a node quickly** | [nodes/node-index.md](nodes/node-index.md) | Minimal 47-line reference |
| **Choose right node** | [nodes/node-selection-guide.md](nodes/node-selection-guide.md) | Smart node finder with decision trees |
| Build from scratch | [developer/](developer/) | 7 focused technical guides |
| **Test workflows** | [developer/12-testing-production-quality.md](developer/12-testing-production-quality.md) | Production-certified testing framework ✅ |
| **Validate code/workflows** | [developer/13-validation-framework-guide.md](developer/13-validation-framework-guide.md) | NEW: Test-driven convergence & quality gates ⭐ |
| Quick code snippet | [cheatsheet/](cheatsheet/) | 38 standardized copy-paste patterns |
| Fix an error | [validation/common-mistakes.md](validation/common-mistakes.md) | Comprehensive error resolution |
| Frontend integration | [frontend-integration/](frontend-integration/) | React/Vue + middleware patterns |
| Production deployment | [developer/04-production.md](developer/04-production.md) | Security, monitoring, performance |
| **Enterprise features** | [enterprise/](enterprise/) | Advanced patterns, security, compliance |
| **Production workflows** | [workflows/](workflows/) | Business-focused solutions |
| **Performance tuning** | [monitoring/](monitoring/) | Observability and optimization |

## 📁 Navigation Guide

### **Core Development**
- **[developer/](developer/)** - 6 focused guides: fundamentals → workflows → advanced → production → troubleshooting → custom development
- **[nodes/](nodes/)** - Enhanced with decision trees and smart selection
- **[cheatsheet/](cheatsheet/)** - 37 standardized patterns (200-800 tokens each)

### **Enterprise & Production**
- **[enterprise/](enterprise/)** - Advanced middleware, security, compliance patterns
- **[frontend-integration/](frontend-integration/)** - React/Vue + real-time communication
- **[monitoring/](monitoring/)** - Performance, observability, alerting
- **[production-patterns/](production-patterns/)** - Real app implementations
- **[architecture/](architecture/)** - Simplified ADR guidance

### **Business Solutions**
- **[workflows/](workflows/)** - Production-ready industry solutions

## 🎯 Essential References

**Start Here:**
- [decision-matrix.md](decision-matrix.md) - Architecture decisions
- [nodes/node-selection-guide.md](nodes/node-selection-guide.md) - Smart node selection
- [validation/common-mistakes.md](validation/common-mistakes.md) - Error fixes

**Quick Access:**
- [cheatsheet/](cheatsheet/) - 37 copy-paste patterns
- [workflows/](workflows/) - Industry solutions
- [enterprise/](enterprise/) - Advanced patterns

## ⚠️ Critical Rules Reference
For validation rules and common mistakes, see:
- **Root CLAUDE.md** - Critical validation rules
- **[decision-matrix.md](decision-matrix.md)** - Architecture decision guidelines
- **[validation/common-mistakes.md](validation/common-mistakes.md)** - Error fixes
- **[validation/common-mistakes.md](validation/common-mistakes.md)** - Common mistake database

## 🤖 Critical Workflow

**MANDATORY STEPS before any app implementation:**

1. **ALWAYS load [decision-matrix.md](decision-matrix.md) FIRST**
2. **Ask user performance requirements** (latency/throughput/volume)
3. **Ask about LLM agent integration needs**
4. **Use decision matrix lookup tables** to choose patterns
5. **Reference [../apps/ARCHITECTURAL_GUIDE.md](../apps/ARCHITECTURAL_GUIDE.md)** for implementation
6. **Document architectural choices in implementation plan**
7. **Surface trade-offs to user for approval**

### Planning Template:
```
Based on your requirements, I recommend:

Performance Analysis:
- Expected latency: [X]ms
- Request volume: [X]/second
- LLM integration: [Y/N]

Architectural Decisions:
- Workflow pattern: [inline/class-based/hybrid] because [reason]
- Interface routing: [MCP/direct/hybrid] because [reason]
- Performance strategy: [approach] because [reason]

Trade-offs:
- [List key trade-offs and implications]

Proceed with this approach?
```

**Key Decision Points:**
- **<5ms + >1000req/sec** = Direct calls likely needed
- **LLM integration required** = MCP routing essential
- **Mixed complexity** = Hybrid approach recommended
- **Unsure** = Start with MCP routing + hybrid workflows

---

**Building workflows?** Start with [developer/](developer/) or [workflows/](workflows/)
**Need help?** Check [developer/05-troubleshooting.md](developer/05-troubleshooting.md)
**Upgrading?** See [migration-guides/](migration-guides/) for version migration guides
**For SDK development**: See [../# contrib (removed)/CLAUDE.md](../# contrib (removed)/CLAUDE.md)
