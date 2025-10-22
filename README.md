# Kailash Python SDK

<p align="center">
  <a href="https://pypi.org/project/kailash/"><img src="https://img.shields.io/pypi/v/kailash.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/kailash/"><img src="https://img.shields.io/pypi/pyversions/kailash.svg" alt="Python versions"></a>
  <a href="https://pepy.tech/project/kailash"><img src="https://static.pepy.tech/badge/kailash" alt="Downloads"></a>
  <img src="https://img.shields.io/badge/license-Apache%202.0%20with%20Additional%20Terms-orange.svg" alt="Apache 2.0 with Additional Terms">
  <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black">
  <img src="https://img.shields.io/badge/tests-4000%2B%20passing-brightgreen.svg" alt="Tests: 4000+ Passing">
  <img src="https://img.shields.io/badge/performance-11x%20faster-yellow.svg" alt="Performance: 11x Faster">
  <img src="https://img.shields.io/badge/docker-integrated-blue.svg" alt="Docker: Integrated">
  <img src="https://img.shields.io/badge/AI-MCP%20validated-purple.svg" alt="AI: MCP Validated">
</p>

<p align="center">
  <strong>Enterprise-Grade Workflow Orchestration Platform</strong>
</p>

<p align="center">
  Build production-ready applications with zero-config database operations, multi-channel platforms, and comprehensive AI integration. From rapid prototyping to enterprise deployment.
</p>

---

## 🔥 Latest Release: v0.9.27 (October 22, 2024)

**CRITICAL: AsyncLocalRuntime Parameter Passing Fix**

### 🐛 Critical Bug Fixes
- **AsyncLocalRuntime Parameter Passing**: Fixed P0 bug causing 100% failure rate for ALL DataFlow operations
  - Root cause: `async_run()` called directly instead of `execute_async()`, bypassing node.config parameter merging
  - Impact: ALL DataFlow CRUD operations (Create, Update, Delete, List) now work correctly with AsyncLocalRuntime
  - Solution: Changed async_local.py:745-756 to call `execute_async()`, matching LocalRuntime pattern
  - **Backward compatible** - no code changes required
  - **Zero regressions** - 587/588 tests passing

### ✨ What's Fixed
- DataFlow CreateNode works with AsyncLocalRuntime
- DataFlow UpdateNode works with AsyncLocalRuntime
- DataFlow DeleteNode works with AsyncLocalRuntime
- DataFlow ListNode works with AsyncLocalRuntime
- All bulk operations work correctly
- Docker/FastAPI deployments using AsyncLocalRuntime now functional

### 📈 Impact
- **Success Rate**: DataFlow with AsyncLocalRuntime - 0% → 100%
- **Production Ready**: AsyncLocalRuntime now fully functional for Docker/FastAPI
- **Pattern Alignment**: Now follows same architecture as LocalRuntime

### 📦 Package Updates
- **kailash**: v0.9.27 - AsyncLocalRuntime parameter passing fix (CRITICAL)
- **kailash-dataflow**: v0.6.3 - Bug fixes and improvements
- **kailash-nexus**: v1.1.0 - Security enhancements
- **kailash-kaizen**: v0.2.0 - AI agent framework

[Full Changelog](CHANGELOG.md) | [Core SDK 0.9.27](https://pypi.org/project/kailash/0.9.27/) | [Release Notes](https://github.com/terrene-foundation/kailash-py/releases/tag/v0.9.27)

## 🎯 What Makes Kailash Different

### 🏗️ **Complete Application Framework**
Not just a toolkit - complete production-ready applications built on enterprise-grade infrastructure:

- **DataFlow**: Zero-config database operations with MongoDB-style queries
- **Nexus**: Multi-channel platform (API + CLI + MCP) from single codebase
- **AI Registry**: Advanced RAG with 47+ specialized nodes
- **User Management**: Enterprise RBAC system with comprehensive security

### 🚀 **Performance & Scale**
- **11x faster test execution** (117s → 10.75s) with smart isolation
- **31.8M operations/second** query performance baseline
- **30,000+ iterations/second** cyclic workflow execution
- **100% test pass rate** across 4,000+ tests

### 🤖 **AI-First Architecture**
- **A2A Google Protocol** for enterprise multi-agent coordination
- **Real MCP execution** by default for all AI agents
- **47+ specialized RAG nodes** for document processing
- **Semantic memory systems** with context-aware retrieval
- **Hybrid search algorithms** for intelligent agent discovery
- **Self-organizing agent pools** with advanced coordination patterns

## 🏗️ Project Architecture

### Three-Layer Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                     🎨 Studio UI Layer                         │
│              Visual workflow builder (coming soon)              │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│                  🏢 Application Framework                       │
│  DataFlow  │  Nexus  │  AI Registry  │  User Management  │...  │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│                     🎯 Core SDK Foundation                      │
│  115+ Nodes  │  Workflows  │  Runtime  │  Security  │  Testing │
└─────────────────────────────────────────────────────────────────┘
```

### Current Project Structure
```
kailash_python_sdk/
├── src/kailash/          # Core SDK - 115+ nodes, workflows, runtime
├── apps/                 # Complete Applications
│   ├── kailash-dataflow/ # Zero-config database operations
│   ├── kailash-nexus/    # Multi-channel platform
│   ├── kailash-mcp/      # Enterprise MCP platform
│   ├── ai_registry/      # Advanced RAG capabilities
│   └── user_management/  # Enterprise RBAC system
├── tests/               # 4,000+ tests (100% pass rate)
├── docs/                # Comprehensive documentation
└── examples/            # Feature validation examples
```

## 🚀 Quick Start

### Installation Options

```bash
# Core SDK only
pip install kailash

# With complete app frameworks
pip install kailash[dataflow,nexus]  # Database + multi-channel
pip install kailash[all]             # Everything

# Or install apps directly
pip install kailash-dataflow  # Zero-config database framework
pip install kailash-nexus     # Multi-channel platform
```

### DataFlow: Zero-Config Database Operations

```python
from dataflow import DataFlow

# Zero-configuration database operations
app = DataFlow()

# MongoDB-style queries across any database
users = app.query("users").where({"age": {"$gt": 18}}).limit(10)

# Redis-powered caching with smart invalidation
cached_result = app.cache().get("user_stats",
    lambda: app.query("users").aggregate([
        {"$group": {"_id": "$department", "count": {"$sum": 1}}}
    ])
)

# Start enterprise API server
app.start()  # Automatic API generation, monitoring, health checks
```

### Nexus: Multi-Channel Platform

```python
from nexus import Nexus

# Single codebase → API + CLI + MCP
app = Nexus()

# Register workflow once, available on all channels
@app.workflow
def process_data(input_data):
    return {"processed": len(input_data)}

# Zero-config startup
app.start()

# Now available as:
# - REST API: POST /workflows/process_data
# - CLI: nexus run process_data
# - MCP: AI agents can call process_data tool
```

### A2A Multi-Agent Coordination

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Build A2A coordination workflow
workflow = WorkflowBuilder()
workflow.add_node("A2ACoordinatorNode", "coordinator", {
    "use_google_protocol": True,
    "enable_semantic_memory": True,
    "delegation_strategy": "skill_based"
})
workflow.add_node("HybridSearchNode", "discovery", {
    "strategies": ["semantic", "keyword", "skill_based"],
    "adaptive_optimization": True
})
workflow.add_node("SemanticMemoryNode", "memory", {
    "embedding_provider": "openai",
    "memory_type": "long_term",
    "context_window": 8192
})

# Connect for intelligent agent coordination
workflow.add_connection("coordinator", "discovery", "agent_request", "search_query")
workflow.add_connection("discovery", "memory", "agent_matches", "context")

# Execute with enterprise monitoring
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## 🎯 Key Features

### 🧪 **Testing Excellence**
- **4,000+ tests** with 100% pass rate
- **11x performance improvement** (117s → 10.75s execution)
- **Docker integration** for real PostgreSQL, Redis, MongoDB
- **Smart isolation** without process forking overhead

### 🏢 **Enterprise Ready**
- **Multi-tenant architecture** with complete isolation
- **RBAC/ABAC security** with fine-grained permissions
- **Audit logging** with compliance frameworks (GDPR, CCPA)
- **Distributed transactions** with Saga/2PC patterns
- **Circuit breaker** and resilience patterns

### 🤖 **AI Integration**
- **115+ production nodes** including 47+ specialized RAG nodes
- **Real MCP execution** by default for all AI agents
- **Self-organizing agent pools** with intelligent coordination
- **Complete LLM integration** with embeddings and vector search

### ⚡ **Performance & Scale**
- **31.8M operations/second** query performance baseline
- **Connection pooling** with automatic resource management
- **Redis caching** with intelligent invalidation patterns
- **Async/await** throughout with proper separation

## 🏗️ Node Ecosystem (115+ Nodes)

### Core Categories
- **Data Nodes**: CSVReaderNode, AsyncSQLDatabaseNode, QueryBuilderNode, QueryCacheNode
- **AI Nodes**: LLMAgentNode, IterativeLLMAgentNode, EmbeddingGeneratorNode, SelfOrganizingAgentNode
- **A2A Nodes**: A2ACoordinatorNode, HybridSearchNode, AdaptiveSearchNode, SemanticMemoryNode, StreamingAnalyticsNode
- **RAG Nodes**: 47+ specialized nodes for document processing and retrieval
- **Security Nodes**: ThreatDetectionNode, AuditLogNode, AccessControlManager
- **Monitoring Nodes**: TransactionMetricsNode, DeadlockDetectorNode, PerformanceAnomalyNode
- **Transaction Nodes**: DistributedTransactionManagerNode, SagaCoordinatorNode

### Advanced Features
- **A2A Communication**: Google Protocol-based multi-agent coordination
- **Semantic Memory**: Long-term memory management for agent interactions
- **Hybrid Search**: Multi-strategy agent discovery and matching
- **Cyclic Workflows**: CycleBuilder API with convergence detection
- **Distributed Transactions**: Automatic Saga/2PC pattern selection
- **Real-time Monitoring**: WebSocket streaming with performance metrics
- **Enterprise Security**: Multi-factor auth, threat detection, compliance

## 📊 Performance Metrics

### Recent Achievements
- **11x faster test execution**: 117s → 10.75s with smart isolation
- **100% test pass rate**: 4,000+ tests across all categories
- **31.8M operations/second**: Query performance baseline
- **30,000+ iterations/second**: Cyclic workflow execution

### Enterprise Benchmarks
- **Query Cache**: 99.9% hit rate with intelligent invalidation
- **Connection Pooling**: 10,000+ concurrent connections
- **MCP Integration**: 407 tests with 100% pass rate
- **Security**: Zero vulnerabilities in production deployment

## 🚀 Applications Built with Kailash

### 1. DataFlow - Zero-Config Database Platform (v0.3.3)
```bash
pip install kailash-dataflow
```
- **MongoDB-style queries** across PostgreSQL, MySQL, SQLite
- **Redis caching** with enterprise-grade invalidation
- **Automatic API generation** with OpenAPI documentation
- **4 production examples** with complete deployment guides
- **Latest**: v0.3.3 - Critical connection parsing fix for special characters in passwords

### 2. Nexus - Multi-Channel Platform (v1.0.3)
```bash
pip install kailash-nexus
```
- **Unified API, CLI, and MCP** from single codebase
- **Enterprise orchestration** with multi-tenancy
- **Session management** with cross-channel synchronization
- **105 tests** with comprehensive validation
- **Latest**: v1.0.3 - Production-ready release with enhanced stability

### 3. AI Registry - Advanced RAG Platform
```bash
pip install kailash-ai-registry
```
- **47+ specialized RAG nodes** for document processing
- **Advanced retrieval** with semantic search and re-ranking
- **Multi-modal support** with image and text processing
- **Enterprise deployment** with scalable architecture

### 4. User Management - Enterprise RBAC
```bash
pip install kailash-user-management
```
- **Complete RBAC system** with role hierarchy
- **Multi-factor authentication** with enterprise integration
- **Audit logging** with compliance frameworks
- **Django-style capabilities** built on SDK architecture

## 🧪 Testing & Quality

### Comprehensive Test Suite
```bash
# All tests (4,000+ tests)
pytest

# Fast unit tests (11x faster execution)
pytest tests/unit/ --timeout=1

# Integration tests with Docker
pytest tests/integration/ --timeout=5

# End-to-end scenarios
pytest tests/e2e/ --timeout=10
```

### Test Infrastructure
- **Docker Integration**: Real PostgreSQL, Redis, MongoDB for testing
- **Smart Isolation**: Fixture-based isolation without process forking
- **Performance Monitoring**: Automated benchmarks and regression detection
- **100% Pass Rate**: Comprehensive fixes across all test categories

## 🛡️ Security & Compliance

### Enterprise Security
- **Multi-factor Authentication**: TOTP, WebAuthn, SMS integration
- **Threat Detection**: Real-time analysis with behavior monitoring
- **Access Control**: Fine-grained RBAC/ABAC with policy engines
- **Audit Logging**: Comprehensive trails with integrity verification

### Compliance Frameworks
- **GDPR/CCPA**: Built-in data protection and privacy controls
- **SOX**: Financial reporting controls and audit trails
- **HIPAA**: Healthcare data protection patterns
- **Multi-tenant Isolation**: Complete tenant-aware operations

## 📚 Documentation & Resources

### For Users
- **[SDK Users Guide](sdk-users/)**: Complete workflow development guide
- **[Node Selection Guide](sdk-users/2-core-concepts/nodes/node-selection-guide.md)**: Smart node selection with decision trees
- **[Enterprise Patterns](sdk-users/5-enterprise/)**: Production deployment patterns
- **[API Documentation](https://terrene-foundation.github.io/kailash-python-sdk)**: Complete API reference

### For Contributors
- **[SDK Contributors Guide](# contrib (removed)/)**: Internal SDK development
- **[Architecture Decisions](# contrib (removed)/architecture/)**: ADRs and design decisions
- **[Testing Guide](tests/README.md)**: 3-tier testing strategy

### Quick References
- **[Cheatsheet](sdk-users/2-core-concepts/cheatsheet/)**: 53 copy-paste patterns
- **[Common Mistakes](sdk-users/2-core-concepts/validation/common-mistakes.md)**: Error patterns and solutions
- **[Performance Guide](sdk-users/5-enterprise/performance/)**: Optimization patterns

## 🚢 Production Deployment

### Container Deployment
```bash
# Export workflow to container format
python -c "
from kailash.utils.export import export_workflow
export_workflow(workflow, 'production.yaml', format='kailash')
"

# Deploy to Kailash platform
kailash deploy production.yaml --environment prod
```

### Monitoring & Observability
```python
from kailash.visualization import DashboardServer

# Real-time monitoring dashboard
server = DashboardServer(port=8080)
server.start()
# Open http://localhost:8080 for live metrics
```

### Enterprise Features
- **Multi-tenant deployment** with complete isolation
- **Distributed transactions** with automatic recovery
- **Circuit breaker patterns** for resilience
- **Health monitoring** with automated alerting

## 🤝 Contributing

We use a **Claude Code-driven workflow** for all development:

### New Team Member?
**Start Here → [NEW_TEAM_MEMBER.md](NEW_TEAM_MEMBER.md)**

### Development Workflow
```bash
# Clone and setup
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash-python-sdk
uv sync

# Run tests (4,000+ tests)
pytest tests/unit/ --timeout=1      # Fast unit tests
pytest tests/integration/ --timeout=5  # Integration tests
pytest tests/e2e/ --timeout=10     # End-to-end tests

# Code quality
black .
isort .
ruff check .
```

### Claude Code Workflow
All project management through conversational AI:
- **No manual TODO editing** - Claude Code handles all updates
- **No direct GitHub issues** - Created through planning sessions
- **All progress tracked** - Through natural conversation

See [Contributing Guide](CONTRIBUTING.md) and [# contrib (removed)/CLAUDE.md](# contrib (removed)/CLAUDE.md).

## 📈 Project Status

### ✅ v0.8.4 - A2A Google Protocol Enhancement
- **Advanced Agent Coordination**: A2ACoordinatorNode with Google Protocol patterns
- **Hybrid Search System**: Multi-strategy agent discovery and matching
- **Semantic Memory**: Long-term memory management for agent interactions
- **Real-time Analytics**: Streaming performance monitoring for A2A workflows
- **Backward Compatible**: Seamless integration with existing implementations
- **Production Ready**: Enterprise-grade multi-agent coordination patterns

### ✅ v0.8.1 - Complete App Framework
- **Complete Application Framework**: DataFlow, Nexus, AI Registry, User Management
- **PyPI Integration**: All packages available with proper extras support
- **Performance Breakthrough**: 11x faster test execution
- **Testing Excellence**: 4,000+ tests with 100% pass rate
- **Enterprise Ready**: Production deployment patterns

### ✅ v0.7.0 - Major Framework Release
- **DataFlow Platform**: Zero-config database operations
- **Nexus Platform**: Multi-channel orchestration
- **AI Registry**: Advanced RAG capabilities
- **User Management**: Enterprise RBAC system
- **Testing Infrastructure**: Docker integration, comprehensive validation

### 🚧 Roadmap
- **Visual Workflow Builder**: Studio UI for drag-and-drop workflow creation
- **Advanced Analytics**: ML-powered workflow optimization
- **Cloud Integration**: Native AWS/GCP/Azure deployment
- **Mobile SDKs**: iOS and Android workflow execution

## 📄 License

This project is licensed under the **Apache License 2.0 with Additional Terms** that protect against standalone commercial distribution while encouraging innovation.

### ✅ What You CAN Do:
- **Use** Kailash SDK in your commercial applications and services
- **Create and sell** derivative works that add substantial functionality
- **Integrate** Kailash as a component of larger systems
- **Use internally** within your organization without restrictions
- **Provide services** using Kailash without distributing the SDK itself

### ❌ What You CANNOT Do:
- **Sell the SDK as-is** without substantial modifications
- **Repackage and sell** with only cosmetic changes
- **Distribute commercially** as a standalone product

### 📋 Summary:
We encourage commercial use of Kailash SDK as part of your innovative solutions while preventing direct resale of our work. This ensures the community benefits from continuous development while protecting the project's sustainability.

For complete license terms, see the [LICENSE](LICENSE) file. For commercial licensing inquiries or clarifications, please contact info@terrene.foundation.

## 🙏 Acknowledgments

Built with ❤️ by the Terrene Foundation team for the Kailash ecosystem.

Special recognition for the **11x performance breakthrough** and **100% test pass rate** achieved through innovative engineering and comprehensive testing strategies.

---

<p align="center">
  <strong>Ready to build enterprise-grade applications?</strong><br>
  <a href="https://pypi.org/project/kailash/">Install from PyPI</a> •
  <a href="sdk-users/README.md">Documentation</a> •
  <a href="examples/">Examples</a> •
  <a href="https://github.com/terrene-foundation/kailash-py">GitHub</a>
</p>
