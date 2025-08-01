# Architecture Decision Matrix

**Version**: v0.6.6+ | **Quick Decisions for Claude Code**

## 🎯 Quick Decision Framework

**Use this matrix to make fast architectural decisions before building any app.**

### 📊 Decision Lookup Tables

#### 1. Workflow Pattern Selection

| Scenario | Pattern | Reasoning |
|----------|---------|-----------|
| **Simple automation (< 5 nodes)** | **Inline** | Fast setup, minimal overhead |
| **Business logic (5-15 nodes)** | **Class-based** | Better structure, reusability |
| **Complex enterprise (15+ nodes)** | **Hybrid** | Flexibility + maintainability |
| **Rapid prototyping** | **Inline** | Quick iteration |
| **Production apps** | **Class-based** | Better testing, maintenance |
| **Mixed complexity** | **Hybrid** | Best of both worlds |

#### 2. Interface Routing Selection

| Use Case | Routing | Reasoning |
|----------|---------|-----------|
| **AI agents with tools** | **MCP** | Essential for tool integration |
| **Ultra-low latency (<5ms)** | **Direct** | No protocol overhead |
| **High throughput (>1000 req/s)** | **Direct** | Performance optimization |
| **Mixed AI + direct calls** | **Hybrid** | Flexibility for different patterns |
| **Microservices integration** | **MCP** | Standard protocol support |
| **Legacy system integration** | **Direct** | Simpler integration path |

#### 3. Performance Strategy Selection

| Requirements | Strategy | Implementation |
|--------------|----------|----------------|
| **<5ms latency** | **Direct calls** | Skip MCP overhead |
| **>1000 req/s** | **Connection pooling** | Pre-established connections |
| **AI-heavy workloads** | **Async runtime** | Non-blocking operations |
| **Variable load** | **Circuit breakers** | Automatic failure protection |
| **Enterprise scale** | **Full middleware** | Complete production stack |

### 🚀 Common Decision Combinations

#### Recommended Patterns by App Type

| App Type | Workflow | Interface | Performance | Rationale |
|----------|----------|-----------|-------------|-----------|
| **AI Assistant** | Class-based | MCP | Async runtime | Structured AI tool integration |
| **Iterative AI Agent** | Class-based | MCP | Async runtime | **IterativeLLMAgent** with real MCP execution |
| **API Gateway** | Hybrid | Hybrid | Full middleware | Maximum flexibility |
| **Data Pipeline** | Class-based | Direct | Connection pooling | High-throughput processing |
| **Enterprise App** | Hybrid | MCP | Full middleware | Complete feature set |
| **Microservice** | Inline | Direct | Circuit breakers | Lightweight + resilient |
| **Prototype** | Inline | MCP | Basic runtime | Quick setup with AI capability |

## 🏗️ Detailed Decision Criteria

### Workflow Pattern Details

#### Inline Workflows
```python
# Best for: Simple automation, prototypes
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("LLMAgentNode", "analyzer", {"model": "gpt-4"})
workflow.add_connection("reader", "result", "analyzer", "input_data")
```

**When to use:**
- ✅ < 5 nodes
- ✅ Simple data flow
- ✅ Rapid prototyping
- ❌ Complex business logic
- ❌ Reusable components

#### Class-based Workflows
```python
# Best for: Business applications, production systems
from kailash.workflow.builder import WorkflowBuilder

class CustomerAnalysisWorkflow:
    def __init__(self):
        self.workflow = self._build_workflow()

    def _build_workflow(self):
        workflow = WorkflowBuilder()
        workflow.add_node("CSVReaderNode", "customer_reader", {
            "file_path": "customers.csv"
        })
        workflow.add_node("LLMAgentNode", "analyzer", {
            "model": "gpt-4",
            "system_prompt": "Analyze customer data for insights"
        })
        workflow.add_connection("customer_reader", "result", "analyzer", "input")
        return workflow.build()
```

**When to use:**
- ✅ 5-15 nodes
- ✅ Business logic encapsulation
- ✅ Testing requirements
- ✅ Team development
- ❌ Very simple tasks

#### Hybrid Workflows
```python
# Best for: Complex enterprise applications
from kailash.workflow.builder import WorkflowBuilder

class EnterpriseWorkflow:
    def __init__(self):
        self.core_workflow = self._build_core()  # Class-based
        self.dynamic_parts = {}  # Inline additions

    def _build_core(self):
        workflow = WorkflowBuilder()
        # Core enterprise processing nodes
        workflow.add_node("SSOAuthenticationNode", "auth", {})
        workflow.add_node("TenantAssignmentNode", "tenant", {})
        return workflow

    def add_dynamic_processing(self, processor_type):
        # Add nodes dynamically based on runtime requirements
        self.dynamic_parts[processor_type] = WorkflowBuilder()
```

**When to use:**
- ✅ 15+ nodes
- ✅ Mixed complexity levels
- ✅ Runtime customization
- ✅ Enterprise requirements

### Interface Routing Details

#### MCP Routing
**Pros:**
- Standard protocol
- AI agent tool integration
- Microservices communication
- Future-proof architecture

**Cons:**
- Protocol overhead (~1-3ms)
- Additional complexity
- Learning curve

**Best for:**
- AI agents with tools
- Microservices architecture
- Standard integrations

#### Direct Routing
**Pros:**
- Ultra-low latency
- Simple integration
- High throughput
- Minimal overhead

**Cons:**
- No AI tool integration
- Custom protocol handling
- Less flexible

**Best for:**
- Performance-critical applications
- Legacy system integration
- High-frequency trading

#### Hybrid Routing
**Pros:**
- Best of both worlds
- Route-specific optimization
- Gradual migration path

**Cons:**
- Increased complexity
- More configuration

**Best for:**
- Mixed requirements
- Enterprise applications
- Migration scenarios

### Performance Strategy Details

#### Latency Thresholds
- **<1ms**: Direct calls only, pre-compiled workflows
- **<5ms**: Direct calls, minimal middleware
- **<50ms**: MCP acceptable, basic middleware
- **<500ms**: Full feature set available
- **>500ms**: All patterns acceptable

#### Throughput Thresholds
- **<10 req/s**: Basic runtime sufficient
- **<100 req/s**: Connection pooling recommended
- **<1000 req/s**: Async runtime required
- **>1000 req/s**: Full middleware + optimization

## 🎯 Quick Decision Workflow

### Step 1: Performance Requirements
```
Latency requirement: [X]ms
Throughput requirement: [X] req/s
AI integration needed: [Y/N]
```

### Step 2: Lookup Decision
Use the tables above to determine:
- Workflow pattern
- Interface routing
- Performance strategy

### Step 3: Validate Combination
Check the "Recommended Patterns" table for your app type.

### Step 4: Implementation Plan
```
Based on your requirements:

Performance Analysis:
- Expected latency: [X]ms → [Strategy]
- Request volume: [X]/second → [Optimizations]
- LLM integration: [Y/N] → [Routing choice]

Architectural Decisions:
- Workflow pattern: [inline/class-based/hybrid] because [reason]
- Interface routing: [MCP/direct/hybrid] because [reason]
- Performance strategy: [approach] because [reason]

Trade-offs:
- [List key trade-offs and implications]

Implementation path:
1. [First step]
2. [Second step]
3. [Third step]
```

## 🔄 Migration Patterns

### From Simple to Complex
1. Start with **Inline + MCP + Basic runtime**
2. Migrate to **Class-based** as complexity grows
3. Add **Hybrid routing** for performance optimization
4. Implement **Full middleware** for enterprise features

### Performance Optimization Path
1. **Basic runtime** → Measure performance
2. **Async runtime** → If CPU-bound operations
3. **Connection pooling** → If I/O-bound operations
4. **Circuit breakers** → If reliability required
5. **Full middleware** → If enterprise features needed

## 🚨 Anti-Patterns to Avoid

### ❌ Wrong Workflow Pattern
- **Don't use Inline for >10 nodes** → Unmaintainable
- **Don't use Class-based for <3 nodes** → Over-engineering
- **Don't use Hybrid without clear need** → Unnecessary complexity

### ❌ Wrong Interface Routing
- **Don't use MCP for <5ms latency** → Too much overhead
- **Don't use Direct for AI agents** → Missing tool integration
- **Don't mix routing without planning** → Inconsistent architecture

### ❌ Wrong Performance Strategy
- **Don't optimize prematurely** → Wasted effort
- **Don't ignore performance requirements** → System failure
- **Don't under-provision for enterprise** → Scalability issues

## 📚 Implementation Guides

After making decisions using this matrix:

1. **Workflow Implementation** → [../apps/APP_DEVELOPMENT_GUIDE.md](../apps/APP_DEVELOPMENT_GUIDE.md)
2. **MCP Integration** → [cheatsheet/025-mcp-integration.md](cheatsheet/025-mcp-integration.md)
3. **Performance Optimization** → [developer/04-production.md](developer/04-production.md)
4. **Enterprise Features** → [enterprise/README.md](enterprise/README.md)

## 🎯 Quick Examples

### AI Assistant App
```
Requirements: AI tools, conversational interface, moderate performance
Decision: Class-based + MCP + Async runtime
Rationale: Structured AI integration with good performance
```

### High-Frequency Trading
```
Requirements: <1ms latency, 10,000+ req/s, no AI
Decision: Inline + Direct + Connection pooling
Rationale: Maximum performance, minimal overhead
```

### Enterprise Analytics
```
Requirements: Complex workflows, AI + direct data, enterprise features
Decision: Hybrid + Hybrid + Full middleware
Rationale: Maximum flexibility and feature set
```

---

**Next Steps**: Use this matrix to make decisions, then implement using the guides referenced above.

**Remember**: Start simple and evolve. Don't over-engineer from the beginning.
