# Architecture Decision Guide - Core SDK vs App Framework

_Make the right architectural choice for your project from day one_

> **🎯 Critical Decision**: Choose between **Core SDK** (foundational components) and **App Framework** (complete applications) based on your specific needs.

## 🏗️ Two-Tier Architecture Overview

The Kailash ecosystem has evolved into a sophisticated two-tier architecture:

### **Tier 1: Core SDK** (`src/kailash/`)

**Foundational building blocks for custom workflows**

- **Runtime System**: `LocalRuntime`, `ParallelRuntime`, `DockerRuntime`
- **Workflow Builder**: `WorkflowBuilder` with 140+ production-ready nodes
- **Node Library**: AI, Data, Security, Enterprise, Monitoring nodes
- **MCP Integration**: Complete Model Context Protocol support
- **Enterprise Middleware**: API Gateway, Event Store, Checkpoint Manager

### **Tier 2: App Framework** (`apps/`)

**Complete domain-specific applications built on Core SDK**

- **kailash-dataflow**: Zero-config database framework with enterprise power
- **kailash-nexus**: Multi-channel platform (API, CLI, MCP) with unified sessions
- **kailash-mcp**: Enterprise MCP platform with auth, multi-tenancy, compliance

## 🎯 Decision Matrix

| **Requirement**           | **Core SDK**           | **App Framework**        | **Recommendation**   |
| ------------------------- | ---------------------- | ------------------------ | -------------------- |
| **Custom workflows**      | ✅ Perfect fit         | ❌ Too constrained       | Use Core SDK         |
| **Database operations**   | ⚠️ Need expertise      | ✅ Zero-config           | Use kailash-dataflow |
| **Multi-channel apps**    | ⚠️ Complex setup       | ✅ Built-in              | Use kailash-nexus    |
| **Enterprise MCP**        | ⚠️ Security complexity | ✅ Production-ready      | Use kailash-mcp      |
| **Rapid prototyping**     | ⚠️ Longer setup        | ✅ Instant start         | Use App Framework    |
| **Unique business logic** | ✅ Full control        | ⚠️ Framework constraints | Use Core SDK         |
| **Time to market**        | ⚠️ Weeks               | ✅ Hours                 | Use App Framework    |
| **Fine-grained control**  | ✅ Complete control    | ⚠️ Framework decisions   | Use Core SDK         |

## 🚀 Use Case Decision Tree

### **Choose Core SDK When:**

#### **Custom Workflow Automation** ✅

```python
# Complex business logic requiring custom nodes
workflow = WorkflowBuilder()
workflow.add_node("CustomAnalyticsNode", "analyzer", {
    "algorithm": "proprietary_ml_model",
    "thresholds": custom_business_rules
})
workflow.add_node("LLMAgentNode", "decision_maker", {
    "model": "gpt-4",
    "prompt": custom_prompt_template
})
```

#### **System Integration** ✅

```python
# Integrating with existing enterprise systems
workflow.add_node("HTTPRequestNode", "legacy_api", {
    "url": "https://legacy.company.com/api",
    "auth": enterprise_auth_config
})
workflow.add_node("AsyncSQLDatabaseNode", "modern_db", {
    "database_type": "postgresql",
    "connection_pool": shared_pool_config
})
```

#### **Advanced AI Workflows** ✅

```python
# Multi-step AI reasoning with custom logic
workflow.add_node("IterativeLLMAgentNode", "reasoner", {
    "model": "claude-3-5-sonnet",
    "max_iterations": 10,
    "convergence_criteria": custom_criteria
})
workflow.add_node("EmbeddingGeneratorNode", "vectorizer", {
    "model": "text-embedding-ada-002"
})
```

### **Choose App Framework When:**

#### **Database Applications** ✅ **kailash-dataflow**

```python
from dataflow import DataFlow

# Zero-configuration database operations
db = DataFlow()

@db.model
class User:
    name: str
    email: str
    active: bool = True

# Automatic node generation (11 nodes per model)
# UserCreateNode, UserReadNode, UserListNode, etc.
```

#### **Multi-Channel Platforms** ✅ **kailash-nexus**

```python
from nexus import Nexus

# Unified API, CLI, and MCP platform
app = Nexus(
    title="E-commerce Platform",
    enable_api=True,    # REST API
    enable_cli=True,    # Command-line interface
    enable_mcp=True,    # AI agent integration
    channels_synced=True # Unified sessions across channels
)
```

#### **Enterprise MCP** ✅ **kailash-mcp**

```python
from kailash_mcp import EnterpriseMCP

# Production-ready MCP with security
mcp = EnterpriseMCP(
    auth_providers=["oauth2", "saml"],
    multi_tenant=True,
    compliance=["gdpr", "hipaa", "sox"],
    monitoring=True
)
```

## 📊 Feature Comparison Matrix

| **Feature**             | **Core SDK**    | **kailash-dataflow** | **kailash-nexus** | **kailash-mcp** |
| ----------------------- | --------------- | -------------------- | ----------------- | --------------- |
| **Database CRUD**       | Manual setup    | ✅ Zero-config       | ✅ Built-in       | ⚠️ Limited      |
| **Multi-channel**       | Custom build    | ❌ Database-only     | ✅ Native         | ⚠️ MCP-only     |
| **AI Integration**      | ✅ Full control | ⚠️ Basic             | ✅ Advanced       | ✅ Native       |
| **Enterprise Security** | Manual config   | ✅ Built-in          | ✅ Production     | ✅ Maximum      |
| **Custom Nodes**        | ✅ Native       | ⚠️ Limited           | ✅ Supported      | ⚠️ MCP-focused  |
| **Learning Curve**      | ⚠️ Steep        | ✅ Minimal           | ⚠️ Moderate       | ⚠️ Moderate     |
| **Time to Production**  | ⚠️ Weeks        | ✅ Days              | ✅ Days           | ✅ Days         |

## 🎯 Common Decision Scenarios

### **Scenario 1: E-commerce Platform**

```
Requirements:
- Product catalog management
- Order processing workflows
- Customer support AI
- Admin dashboard
- Mobile API

Decision: kailash-nexus + kailash-dataflow
Rationale: Multi-channel needs + database operations
```

### **Scenario 2: Custom AI Pipeline**

```
Requirements:
- Proprietary ML models
- Complex data transformations
- Custom business logic
- Integration with 10+ APIs

Decision: Core SDK
Rationale: Unique workflow requiring full control
```

### **Scenario 3: Enterprise Document Processing**

```
Requirements:
- PDF/Word document ingestion
- AI content extraction
- Compliance tracking
- Multi-tenant isolation

Decision: Core SDK + kailash-mcp
Rationale: Custom processing + enterprise MCP needs
```

### **Scenario 4: Rapid MVP Development**

```
Requirements:
- User management
- Basic CRUD operations
- Simple AI features
- Quick deployment

Decision: kailash-dataflow
Rationale: Zero-config setup for fast iteration
```

## ⚡ Migration Paths

### **Start Simple, Scale Up**

1. **Prototype**: App Framework (hours to working system)
2. **MVP**: App Framework with custom extensions
3. **Scale**: Migrate custom components to Core SDK
4. **Enterprise**: Core SDK + multiple App Frameworks

### **Migration Example**

```python
# Phase 1: Rapid prototype with dataflow
from dataflow import DataFlow
db = DataFlow()  # Zero-config start

# Phase 2: Add custom logic
from kailash.workflow.builder import WorkflowBuilder
workflow = WorkflowBuilder()
workflow.add_node("CustomBusinessNode", "processor", {...})

# Phase 3: Enterprise scaling
from nexus import Nexus
app = Nexus(dataflow_integration=db, custom_workflows=[workflow])
```

## 🚨 Common Architecture Mistakes

### **❌ Don't Do This**

```python
# DON'T: Build custom database management
class CustomDatabase:
    def __init__(self):
        self.connection = psycopg2.connect(...)  # Manual connection

# DON'T: Manual workflow orchestration
def manual_workflow():
    result1 = call_api()
    result2 = process_with_ai(result1)  # No error handling
    save_to_db(result2)  # No transaction management
```

### **✅ Do This Instead**

```python
# DO: Use sophisticated existing implementations
from dataflow import DataFlow
db = DataFlow()  # Automatic connection pooling, transactions, retry logic

# DO: Use WorkflowBuilder for orchestration
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "api_call", {...})
workflow.add_node("LLMAgentNode", "ai_process", {...})
workflow.add_node("UserCreateNode", "save_result", {...})
# Automatic error handling, parameter validation, retry logic
```

## 🏆 Success Patterns

### **1. Framework-First Approach**

- Start with App Framework for domain needs
- Extend with Core SDK only when necessary
- Leverage zero-config patterns where possible

### **2. Gradual Complexity**

- Begin with simple framework setup
- Add custom nodes incrementally
- Scale to Core SDK when framework constraints hit

### **3. Hybrid Architecture**

- Use multiple frameworks for different concerns
- Core SDK for unique business logic
- App Frameworks for standard operations

### **4. Security by Design**

- Enterprise features built into App Frameworks
- Core SDK requires manual security implementation
- Always use SecureGovernedNode patterns

## 📈 Performance Characteristics

### **Core SDK**

- **Latency**: <100ms per workflow (optimized)
- **Throughput**: 1000+ workflows/second
- **Memory**: Base 10MB + node overhead
- **Scaling**: Horizontal with ParallelRuntime

### **App Frameworks**

- **kailash-dataflow**: 10,000+ operations/second
- **kailash-nexus**: 500+ concurrent channels
- **kailash-mcp**: Enterprise-grade security overhead
- **Memory**: 50-100MB base (includes enterprise features)

## 🎯 Quick Decision Guide

**Need database operations?** → **kailash-dataflow**
**Need multi-channel platform?** → **kailash-nexus**
**Need enterprise MCP?** → **kailash-mcp**
**Need custom workflows?** → **Core SDK**
**Need rapid prototyping?** → **App Framework first**
**Need maximum control?** → **Core SDK**
**Need enterprise security?** → **App Framework**
**Have unique requirements?** → **Core SDK**

## 💡 Pro Tips

1. **Start with frameworks** - Most needs are already solved
2. **Measure twice, build once** - Framework constraints vs custom control
3. **Security first** - App Frameworks have enterprise security built-in
4. **Performance testing** - Both tiers support high-throughput scenarios
5. **Migration planning** - Design for evolution from framework to custom

**Remember**: The goal is shipping working software quickly. App Frameworks accelerate 80% of use cases, Core SDK handles the remaining 20% that need custom solutions.
