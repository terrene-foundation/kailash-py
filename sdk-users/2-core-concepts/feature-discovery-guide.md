# Feature Discovery Guide - Find Existing Solutions First

*Before building anything, discover what already exists in the Kailash SDK ecosystem*

> **🎯 Golden Rule**: The SDK has 110+ nodes and sophisticated implementations. Always search before building!

## 🔍 Quick Feature Search

### **Database Operations**
```bash
# Search existing database capabilities
grep -r "class.*DatabaseNode" src/kailash/nodes/data/
grep -r "async def execute" src/kailash/nodes/data/
```

**What You'll Find:**
- `AsyncSQLDatabaseNode` - Sophisticated PostgreSQL, MySQL, SQLite support
- `SQLDatabaseNode` - Synchronous database operations
- Built-in: Connection pooling, transaction management, retry logic, type inference

### **AI & LLM Features**
```bash
# Search existing AI capabilities
ls src/kailash/nodes/ai/
grep -r "LLMNode" src/kailash/nodes/
```

**What You'll Find:**
- `LLMAgentNode` - OpenAI, Anthropic, local models
- `IterativeLLMAgentNode` - Multi-step reasoning
- `EmbeddingGeneratorNode` - Vector embeddings
- Real MCP execution (not mocked)

### **Security & Enterprise**
```bash
# Search security implementations
ls src/kailash/nodes/security/
grep -r "SecureGovernedNode" src/kailash/
```

**What You'll Find:**
- `MultiFactorAuthNode` - Enterprise MFA
- `ThreatDetectionNode` - Security monitoring
- `AccessControlManager` - RBAC/ABAC patterns
- Connection parameter validation

### **Monitoring & Resilience**
```bash
# Search resilience patterns
ls src/kailash/core/resilience/
grep -r "CircuitBreaker" src/kailash/
```

**What You'll Find:**
- `ConnectionCircuitBreaker` - Advanced failure protection
- `HealthMonitor` - System health tracking
- `BulkheadIsolation` - Resource isolation
- Performance anomaly detection

## 🎯 Common Scenarios - Where to Look

### **"I need database connections"**
✅ **Don't Build**: Custom connection managers
✅ **Use Instead**:
- `AsyncSQLDatabaseNode` (advanced features)
- `SQLDatabaseNode` (simple operations)
- Built-in connection pooling with shared pools

### **"I need AI/LLM integration"**
✅ **Don't Build**: Custom OpenAI wrappers
✅ **Use Instead**:
- `LLMAgentNode` (single operations)
- `IterativeLLMAgentNode` (complex reasoning)
- Built-in MCP tool execution

### **"I need error handling"**
✅ **Don't Build**: Custom retry logic
✅ **Use Instead**:
- Built-in circuit breakers (`CircuitBreakerManager`)
- AsyncSQLDatabaseNode retry configuration
- Health monitoring patterns

### **"I need security validation"**
✅ **Don't Build**: Custom input validation
✅ **Use Instead**:
- `SecureGovernedNode` patterns
- Built-in parameter validation
- SQL injection prevention

### **"I need workflow management"**
✅ **Don't Build**: Custom orchestration
✅ **Use Instead**:
- `WorkflowBuilder` (110+ nodes available)
- `LocalRuntime`, `ParallelRuntime`
- Built-in parameter passing and validation

## 🏗️ Architecture Decision Tree

### **Building a Simple App?**
```
Simple App (< 5 workflows)
├── Core SDK: WorkflowBuilder + LocalRuntime
├── Nodes: AsyncSQLDatabaseNode + LLMAgentNode
└── Pattern: Inline workflow construction
```

### **Building a Complex System?**
```
Complex System (> 10 workflows)
├── App Framework: kailash-dataflow OR kailash-nexus
├── Features: Zero-config setup + enterprise patterns
└── Pattern: Framework-first approach
```

### **Enterprise Requirements?**
```
Enterprise App
├── Security: SecureGovernedNode + AccessControlManager
├── Data: Multi-tenant + audit logging
├── Monitoring: Circuit breakers + health checks
└── Framework: kailash-nexus (multi-channel)
```

## 📚 Discovery Resources

### **1. Node Catalog Search**
**Location**: `sdk-users/2-core-concepts/nodes/`
- `node-index.md` - Quick reference (47 lines)
- `node-selection-guide.md` - Decision trees
- `comprehensive-node-catalog.md` - Complete list (2194 lines)

### **2. Implementation Patterns**
**Location**: `sdk-users/2-core-concepts/cheatsheet/`
- Copy-paste patterns for common operations
- Real working examples, not simplified demos
- Pattern categories: AI, Data, Security, Enterprise

### **3. Framework Solutions**
**Location**: `apps/`
- `kailash-dataflow/` - Database operations framework
- `kailash-nexus/` - Multi-channel platform
- `kailash-mcp/` - Enterprise MCP framework

### **4. Common Mistakes**
**Location**: `sdk-users/2-core-concepts/validation/common-mistakes.md`
- Error patterns and solutions
- What NOT to rebuild
- Performance anti-patterns

## 🚀 Feature Discovery Workflow

### **Step 1: Search Existing Nodes**
```python
# Search command
find src/kailash/nodes -name "*.py" | xargs grep -l "YourFeature"

# Or use the node index
# Check: sdk-users/2-core-concepts/nodes/node-index.md
```

### **Step 2: Check App Frameworks**
```python
# Database operations?
# Check: apps/kailash-dataflow/

# Multi-channel platform?
# Check: apps/kailash-nexus/

# Enterprise MCP?
# Check: apps/kailash-mcp/
```

### **Step 3: Review Implementation Patterns**
```python
# Check cheatsheet for your use case
# Location: sdk-users/2-core-concepts/cheatsheet/

# Common patterns:
# - 025-mcp-integration.md (AI agents)
# - 047-asyncsql-enterprise-patterns.md (Database)
# - 048-transaction-monitoring.md (Enterprise)
```

### **Step 4: Validate Against Common Mistakes**
```python
# Before implementing, check common mistakes
# Location: sdk-users/2-core-concepts/validation/common-mistakes.md

# Avoid:
# - Rebuilding existing sophisticated features
# - Custom orchestration (use WorkflowBuilder)
# - Manual connection management (use AsyncSQLDatabaseNode)
```

## ⚡ Quick Discovery Commands

### **Find Database Features**
```bash
grep -r "connection.*pool" src/kailash/nodes/data/
grep -r "transaction.*mode" src/kailash/nodes/data/
grep -r "retry.*config" src/kailash/nodes/data/
```

### **Find AI Features**
```bash
ls src/kailash/nodes/ai/
grep -r "mcp.*tool" src/kailash/nodes/
grep -r "embedding" src/kailash/nodes/
```

### **Find Security Features**
```bash
ls src/kailash/nodes/security/
grep -r "validation" src/kailash/nodes/
grep -r "SecureGoverned" src/kailash/
```

### **Find Enterprise Features**
```bash
grep -r "multi.*tenant" src/kailash/
grep -r "circuit.*breaker" src/kailash/core/
grep -r "health.*monitor" src/kailash/core/
```

## 🎯 Success Metrics

**Good Discovery:**
- Found existing solution in <5 minutes
- Leveraged sophisticated built-in features
- Avoided rebuilding complex systems
- Used established patterns and security practices

**Poor Discovery:**
- Built custom database connection management
- Rebuilt parameter validation systems
- Created custom AI integration wrappers
- Ignored existing security and enterprise patterns

## 💡 Pro Tips

1. **Start with App Frameworks** - Often provide complete solutions
2. **Check Cheatsheet First** - Copy-paste working patterns
3. **Use Node Index** - Quick overview of all available nodes
4. **Review Common Mistakes** - Learn from others' discovery failures
5. **Search Core Implementation** - Understand what's truly built-in

**Remember**: The SDK has been battle-tested with 99.9% test pass rates. Existing implementations are likely more sophisticated and secure than custom solutions.
