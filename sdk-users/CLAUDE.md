# SDK Users - Navigation Hub

*Building solutions WITH the Kailash SDK*

## ⚡ CORE IMPLEMENTATION PATTERNS

### Enterprise Workflow (Complete Pattern)
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "api", {"url": "https://api.example.com/data"})
workflow.add_node("LLMAgentNode", "analyzer", {"model": "gpt-4"})
workflow.connect("api", "response", mapping={"analyzer": "input_data"})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Enterprise App Architecture
```python
from kailash.middleware.gateway import create_gateway

app = create_gateway({
    "enable_real_time": True,
    "enable_ai_chat": True,
    "enable_session_management": True
})
```

### Node Selection Priority
```python
# ✅ ALWAYS use specialized nodes first
from kailash.nodes.ai import LLMAgentNode        # NOT custom API calls
from kailash.nodes.api import HTTPRequestNode    # NOT requests library
from kailash.nodes.admin import UserManagementNode  # NOT custom auth
from kailash.nodes.data import CSVReaderNode     # NOT PythonCodeNode for files
```

### Parameter Patterns
```python
# Dot notation for nested outputs
workflow.connect("processor", "result.data", mapping={"analyzer": "input"})

# Runtime overrides
runtime.execute(workflow, parameters={"reader": {"file_path": "new.csv"}})
```

---

## 🚀 Enterprise Middleware Architecture

**🌉 Complete Middleware Stack**: Production-ready enterprise platform with `create_gateway()` - single function creates full app with real-time communication, AI chat, and session management.

**🔄 Real-time Agent-UI Communication**: WebSocket/SSE streaming, dynamic workflow creation from frontend, multi-tenant session isolation.

**🤖 AI Chat Integration**: Natural language workflow generation, context-aware conversations, automatic workflow creation from user descriptions.

**⚡ Unified Async Runtime**: Production-ready AsyncLocalRuntime with 2-10x performance gains. See [developer/10-unified-async-runtime-guide.md](developer/10-unified-async-runtime-guide.md) for complete guide.

**🔧 Resource Registry**: Centralized resource management for database pools, HTTP clients, and caches. See [developer/08-resource-registry-guide.md](developer/08-resource-registry-guide.md) for patterns.

**🚀 AsyncWorkflowBuilder**: Async-first workflow builder with 70%+ code reduction. Built-in patterns (retry, rate limit, timeout, batch, circuit breaker). See [developer/07-async-workflow-builder.md](developer/07-async-workflow-builder.md) and [workflows/async/async-workflow-builder-guide.md](workflows/async/async-workflow-builder-guide.md).

**🛡️ Enterprise Resilience Patterns**: Production-grade fault tolerance with circuit breakers, bulkhead isolation, and health monitoring. Circuit breakers prevent cascade failures with configurable thresholds. Bulkhead isolation partitions resources by operation type. Health monitoring provides real-time infrastructure status with alerting. See [enterprise/resilience-patterns.md](enterprise/resilience-patterns.md).

**🔗 Dot Notation Mapping**: Access nested node outputs with `"result.data"`, `"result.metrics"`, `"source.nested.field"` in workflow connections.

**🎯 Auto-Mapping Parameters**: NodeParameter supports `auto_map_primary=True`, `auto_map_from=["alt1"]`, `workflow_alias="name"` for automatic connection discovery.

**🧪 Production-Certified Testing Framework**: Comprehensive async testing with Docker integration, Ollama LLM workflows, performance validation, and variable passing fully resolved. See [developer/12-testing-production-quality.md](developer/12-testing-production-quality.md).

**🏥 Enterprise MCP Workflows**: Complete healthcare HIPAA, finance SOX, and multi-tenant patterns with 4 production-grade enterprise nodes. See [cheatsheet/040-enterprise-mcp-workflows.md](cheatsheet/040-enterprise-mcp-workflows.md).

**📊 Transaction Monitoring**: Enterprise-grade transaction metrics, deadlock detection, race condition analysis, and performance anomaly detection with 5 production-tested monitoring nodes. See [cheatsheet/048-transaction-monitoring.md](cheatsheet/048-transaction-monitoring.md) and [nodes/monitoring-nodes.md](nodes/monitoring-nodes.md).

**🔄 Distributed Transaction Management**: Enterprise-grade transaction patterns with automatic pattern selection. Supports Saga pattern for high availability and Two-Phase Commit for strong consistency. Includes compensation logic, state persistence, and recovery mechanisms. Complete with 122 unit tests and 23 integration tests. See [cheatsheet/049-distributed-transactions.md](cheatsheet/049-distributed-transactions.md) and [nodes/transaction-nodes.md](nodes/transaction-nodes.md).

## 🏗️ Architecture Decisions First

**⚠️ STOP! Before building any app, make these critical decisions:**

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
| Build from scratch | [developer/](developer/) | 6 focused technical guides |
| **Test workflows** | [developer/12-testing-production-quality.md](developer/12-testing-production-quality.md) | Production-certified testing framework ✅ |
| Quick code snippet | [cheatsheet/](cheatsheet/) | 37 standardized copy-paste patterns |
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
