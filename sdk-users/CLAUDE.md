# SDK Users - Navigation Hub

*Building solutions WITH the Kailash SDK*

## 🚀 v0.4.0 Enterprise Middleware Architecture

**🌉 Complete Middleware Stack**: Production-ready enterprise platform with `create_gateway()` - single function creates full app with real-time communication, AI chat, and session management.

**🔄 Real-time Agent-UI Communication**: WebSocket/SSE streaming, dynamic workflow creation from frontend, multi-tenant session isolation.

**🤖 AI Chat Integration**: Natural language workflow generation, context-aware conversations, automatic workflow creation from user descriptions.

**⚡ Unified Runtime**: LocalRuntime includes async + all enterprise capabilities. See [developer/18-unified-runtime-guide.md](developer/18-unified-runtime-guide.md) for complete guide.

**🔗 Dot Notation Mapping**: Access nested node outputs with `"result.data"`, `"result.metrics"`, `"source.nested.field"` in workflow connections.

**🎯 Auto-Mapping Parameters**: NodeParameter supports `auto_map_primary=True`, `auto_map_from=["alt1"]`, `workflow_alias="name"` for automatic connection discovery.

## 🏗️ Architecture Decisions First

**⚠️ STOP! Before building any app, make these critical decisions:**

### 📋 Decision Matrix → [decision-matrix.md](decision-matrix.md)

The decision matrix provides fast answers to:
- **Workflow Pattern**: Inline vs Class-based vs Hybrid construction
- **Interface Routing**: MCP vs Direct calls vs Hybrid routing
- **Performance Strategy**: Latency thresholds and optimization approaches
- **Common Combinations**: Recommended patterns for different app types

### 📚 Complete Implementation Guidance

| Decision Type | Quick Decisions | Implementation Guide | Technical Details |
|---------------|-----------------|---------------------|-------------------|
| **Workflow Construction** | [decision-matrix.md](decision-matrix.md) | [Apps Guide](../apps/ARCHITECTURAL_GUIDE.md) | [ADR-0045](../# contrib (removed)/architecture/adr/0045-workflow-construction-patterns.md) |
| **Interface Routing** | [decision-matrix.md](decision-matrix.md) | [Apps Guide](../apps/ARCHITECTURAL_GUIDE.md) | [ADR-0046](../# contrib (removed)/architecture/adr/0046-interface-routing-strategies.md) |
| **Performance Strategy** | [decision-matrix.md](decision-matrix.md) | [Apps Guide](../apps/ARCHITECTURAL_GUIDE.md) | [ADR-0047](../# contrib (removed)/architecture/adr/0047-performance-guidelines.md) |

## 🎯 Quick Navigation Guide
| I need to... | Go to | Purpose |
|--------------|-------|---------|
| **Make architecture decisions** | [decision-matrix.md](decision-matrix.md) | Choose workflow patterns, routing |
| **Build complete app** | [../apps/ARCHITECTURAL_GUIDE.md](../apps/ARCHITECTURAL_GUIDE.md) | App implementation guide |
| **Choose right node** | [nodes/node-selection-guide.md](nodes/node-selection-guide.md) | Smart node finder with decision trees |
| Build from scratch | [developer/](developer/) | 6 focused technical guides |
| Quick code snippet | [cheatsheet/](cheatsheet/) | 37 standardized copy-paste patterns |
| Fix an error | [developer/05-troubleshooting.md](developer/05-troubleshooting.md) | Comprehensive error resolution |
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
- [developer/05-troubleshooting.md](developer/05-troubleshooting.md) - Error fixes

**Quick Access:**
- [cheatsheet/](cheatsheet/) - 37 copy-paste patterns
- [workflows/](workflows/) - Industry solutions  
- [enterprise/](enterprise/) - Advanced patterns

## ⚠️ Critical Rules Reference
For validation rules and common mistakes, see:
- **Root CLAUDE.md** - Critical validation rules
- **[decision-matrix.md](decision-matrix.md)** - Architecture decision guidelines
- **[developer/05-troubleshooting.md](developer/05-troubleshooting.md)** - Error fixes
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

**Building workflows?** Start with [developer/](developer/) or [workflows/](workflows/)**Need help?** Check [developer/05-troubleshooting.md](developer/05-troubleshooting.md)
**For SDK development**: See [../# contrib (removed)/CLAUDE.md](../# contrib (removed)/CLAUDE.md)
