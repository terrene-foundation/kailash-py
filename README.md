# Kailash Python SDK

<p align="center">
  <a href="https://pypi.org/project/kailash/"><img src="https://img.shields.io/pypi/v/kailash.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/kailash/"><img src="https://img.shields.io/pypi/pyversions/kailash.svg" alt="Python versions"></a>
  <a href="https://pepy.tech/project/kailash"><img src="https://static.pepy.tech/badge/kailash" alt="Downloads"></a>
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black">
  <img src="https://img.shields.io/badge/tests-production%20quality-brightgreen.svg" alt="Tests: Production Quality">
  <img src="https://img.shields.io/badge/docker-integrated-blue.svg" alt="Docker: Integrated">
  <img src="https://img.shields.io/badge/AI-ollama%20validated-purple.svg" alt="AI: Ollama Validated">
</p>

<p align="center">
  <strong>A Pythonic SDK for the Kailash container-node architecture</strong>
</p>

<p align="center">
  Build workflows that seamlessly integrate with Kailash's production environment while maintaining the flexibility to prototype quickly and iterate locally.
</p>

---

## 🔥 Latest Release: v0.8.1 (January 17, 2025)

**Complete App Framework & PyPI Integration**

- 🚀 **App Framework**: Complete application framework with DataFlow & Nexus platforms
- 📦 **PyPI Integration**: All packages now available on PyPI with proper extras support
- 🏢 **Enterprise**: Zero-config database operations and multi-channel platforms
- 🔧 **Platform**: Resolved package naming and distribution issues

[Full Changelog](changelogs/releases/v0.8.1-2025-01-17.md) | [Previous Release](changelogs/releases/v0.6.3-2025-07-05.md)

## ✨ Highlights

- 🚀 **Rapid Prototyping**: Create and test workflows locally without containerization
- 🏗️ **Architecture-Aligned**: Automatically ensures compliance with Kailash standards
- 🔄 **Seamless Handoff**: Export prototypes directly to production-ready formats
- 📊 **Real-time Monitoring**: Live dashboards with WebSocket streaming and performance metrics
- 🧩 **Extensible**: Easy to create custom nodes for domain-specific operations
- ⚡ **Fast Installation**: Uses `uv` for lightning-fast Python package management
- 🤖 **AI-Powered**: Complete LLM agents, embeddings, and hierarchical RAG architecture
- 🧠 **Retrieval-Augmented Generation**: Full RAG pipeline with intelligent document processing
- 🌐 **REST API Wrapper**: Expose any workflow as a production-ready API in 3 lines
- 🚪 **Multi-Workflow Gateway**: Manage multiple workflows through unified API with MCP integration
- 🤖 **Self-Organizing Agents**: Autonomous agent pools with intelligent team formation and convergence detection
- 🧠 **Agent-to-Agent Communication**: Shared memory pools and intelligent caching for coordinated multi-agent systems
- 🔒 **Production Security**: Comprehensive security framework with path traversal prevention, code sandboxing, and audit logging
- 🛡️ **Admin Tool Framework**: Complete enterprise admin infrastructure with React UI, RBAC, audit logging, and LLM-based QA testing
- 🎨 **Visual Workflow Builder**: Kailash Workflow Studio - drag-and-drop interface for creating and managing workflows (coming soon)
- 🔁 **Cyclic Workflows (v0.2.0)**: Universal Hybrid Cyclic Graph Architecture with 30,000+ iterations/second performance
- 🛠️ **Developer Tools**: CycleAnalyzer, CycleDebugger, CycleProfiler for production-ready cyclic workflows
- 📈 **High Performance**: Optimized execution engine supporting 100,000+ iteration workflows
- 📁 **Complete Finance Workflow Library (v0.3.1)**: Production-ready financial workflows with AI analysis
- 💼 **Enterprise Workflow Patterns**: Credit risk, portfolio optimization, trading signals, fraud detection
- 🔔 **Production Alert System**: Rich Discord alerts with rate limiting, retry logic, and rich embed support
- 🏭 **Session 067 Enhancements**: Business workflow templates, data lineage tracking, automatic credential rotation
- 🔄 **Zero-Downtime Operations**: Automatic credential rotation with enterprise notifications and audit trails
- 🌉 **Enterprise Middleware (v0.4.0)**: Production-ready middleware architecture with real-time agent-frontend communication, dynamic workflows, and AI chat integration
- ⚡ **Performance Revolution (v0.5.0)**: 10-100x faster parameter resolution, clear async/sync separation, automatic resource management
- 🧪 **Production-Quality Testing (v0.5.0)**: Comprehensive testing infrastructure with Docker integration, AI workflows, and real-world business scenarios

## 🏗️ Project Architecture

The Kailash project is organized into three distinct layers:

### Core Architecture (v0.5.0)
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Middleware     │    │   Kailash Core  │
│                 │    │                  │    │                 │
│  • React/Vue    │◄───│  • Agent-UI      │◄───│  • Workflows    │
│  • JavaScript   │    │  • Real-time     │    │  • Nodes        │
│  • Mobile Apps  │    │  • API Gateway   │    │  • Runtime      │
│                 │    │  • AI Chat       │    │  • Security     │
│                 │    │  • WebSocket/SSE │    │  • Database     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

```
kailash_python_sdk/
├── src/kailash/          # Core SDK - Framework and building blocks
├── apps/                 # Applications - Production-ready solutions built with the SDK
└── studio/               # UI Layer - Frontend interfaces and visual tools
```

### Layer Overview

1. **SDK Layer** (`src/kailash/`) - The core framework providing:
   - Nodes: Reusable computational units (100+ built-in)
   - Workflows: DAG-based orchestration with cyclic support
   - Runtime: Unified execution engine with optimized async/sync separation (v0.5.0)
   - Middleware: Enterprise communication layer (v0.4.0)
   - Security: RBAC/ABAC access control with audit logging
   - Performance: LRU parameter caching, automatic resource pooling (NEW in v0.5.0)

2. **Application Layer** (`apps/`) - Complete applications including:
   - User Management System (Django++ capabilities)
   - Future: Workflow Designer, Data Pipeline, API Gateway, etc.

3. **UI Layer** (`studio/`) - Modern React interfaces for:
   - Admin dashboards
   - Workflow visualization
   - Application UIs

### Installation Options

```bash
# Core SDK only
pip install kailash

# SDK with DataFlow (zero-config database operations)
pip install kailash[dataflow]

# SDK with Nexus (multi-channel platform)
pip install kailash[nexus]

# Everything
pip install kailash[all]

# Or install apps directly
pip install kailash-dataflow  # Zero-config database framework
pip install kailash-nexus     # Multi-channel platform (API, CLI, MCP)
```

## 🎯 Who Is This For?

The Kailash Python SDK is designed for:

- **AI Business Coaches (ABCs)** who need to prototype workflows quickly
- **Data Scientists** building ML pipelines compatible with production infrastructure
- **Engineers** who want to test Kailash workflows locally before deployment
- **Teams** looking to standardize their workflow development process

## 🚀 Quick Start

### Installation

**Requirements:** Python 3.11 or higher

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# For users: Install from PyPI
pip install kailash

# With additional frameworks
pip install kailash[dataflow,nexus]  # DataFlow + Nexus platforms

# For developers: Clone and sync
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash-python-sdk
uv sync

# Set up SDK development infrastructure (optional but recommended)
./scripts/setup-sdk-environment.sh
```

### Your First Workflow

```python
from kailash.workflow import Workflow
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime
import pandas as pd

# Create a workflow
workflow = Workflow("customer_analysis", name="customer_analysis")

# Add data reader
reader = CSVReaderNode(file_path="customers.csv")
workflow.add_node("read_customers", reader)

# Add custom processing using Python code
def analyze_customers(data):
    """Analyze customer data and compute metrics."""
    df = pd.DataFrame(data)
    # Convert total_spent to numeric
    df['total_spent'] = pd.to_numeric(df['total_spent'])
    return {
        "result": {
            "total_customers": len(df),
            "avg_spend": df["total_spent"].mean(),
            "top_customers": df.nlargest(10, "total_spent").to_dict("records")
        }
    }

processor = PythonCodeNode(code=analyze_customers)
workflow.add_node("analyze", processor)

# Connect nodes
workflow.connect("read_customers", "analyze", mapping={"data": "data"})

# Run locally
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "read_customers": {"file_path": "customers.csv"}
})

print(f"Total customers: {results['analyze']['result']['total_customers']}")
print(f"Average spend: ${results['analyze']['result']['avg_spend']:.2f}")
```

### Export to Production

```python
# Export to Kailash container format
from kailash.utils.export import export_workflow

export_workflow(workflow, "customer_analysis.yaml")
```

## 💼 Finance Workflow Library (New in v0.3.1)

Complete production-ready financial workflows using AI and modern quantitative methods:

### Credit Risk Assessment

```python
from kailash.workflow import Workflow
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.ai import LLMAgentNode

def calculate_risk_metrics(customers, transactions):
    """Calculate comprehensive risk metrics."""
    # Modern risk scoring with AI analysis
    # 100+ lines of production risk calculation
    return {"result": risk_scores}

workflow = Workflow("credit-risk", "Credit Risk Assessment")
workflow.add_node("customer_reader", CSVReaderNode())
workflow.add_node("risk_calculator", PythonCodeNode.from_function(func=calculate_risk_metrics))
workflow.add_node("ai_analyzer", LLMAgentNode(model="gpt-4",
    system_prompt="You are a financial risk expert..."))
```

### Portfolio Optimization

```python
def optimize_portfolio(holdings, market_data, risk_profile="moderate"):
    """Modern Portfolio Theory optimization with rebalancing."""
    # Sharpe ratio optimization, correlation analysis
    # Risk-adjusted returns with AI market insights
    return {"result": optimization_plan}

workflow = Workflow("portfolio-opt", "Portfolio Optimization")
workflow.add_node("optimizer", PythonCodeNode.from_function(func=optimize_portfolio))
# Generates rebalancing trades, risk metrics, AI market analysis
```

### Trading Signals & Fraud Detection

- **Trading Signals**: Technical indicators (RSI, MACD, Bollinger Bands) + AI sentiment
- **Fraud Detection**: Real-time transaction monitoring with velocity analysis

**See complete examples**: `sdk-users/workflows/by-industry/finance/`

## 📚 Documentation

### For SDK Users

**Build solutions with the SDK:**
- `sdk-users/` - Everything you need to build with Kailash
  - `developer/` - Node creation patterns and troubleshooting
  - `workflows/` - Complete production workflow library (v0.3.1)
    - Finance workflows: Credit risk, portfolio optimization, trading signals, fraud detection
    - Quick-start patterns (30-second workflows)
    - Industry-specific solutions by vertical
    - Enterprise integration patterns
  - `essentials/` - Quick reference and cheatsheets
  - `nodes/` - Comprehensive node catalog (93+ nodes including Session 067 enhancements)
  - `patterns/` - Architectural patterns

### For SDK Contributors

**Develop the SDK itself:**
- `# contrib (removed)/` - Internal SDK development resources
  - `architecture/` - ADRs and design decisions
  - `project/` - TODOs and development tracking
  - `training/` - LLM training examples

### Shared Resources

- `shared/` - Resources for both users and contributors
  - `mistakes/` - Common error patterns and solutions
  - `frontend/` - UI development resources

### Quick Links

- [SDK User Guide](sdk-users/README.md) - Build with the SDK
- [SDK Contributor Guide](# contrib (removed)/README.md) - Develop the SDK
- [API Documentation](https://terrene-foundation.github.io/kailash-python-sdk)
- [Examples](examples/)
- [Release Notes](CHANGELOG.md)

## 🌉 Enterprise Middleware (v0.4.0)

### Production-Ready Communication Layer

The new middleware architecture provides enterprise-grade components for building production applications:

```python
from kailash.middleware import (
    AgentUIMiddleware,
    APIGateway,
    create_gateway,
    RealtimeMiddleware,
    AIChatMiddleware
)

# Create enterprise middleware stack
agent_ui = AgentUIMiddleware(
    max_sessions=1000,
    session_timeout_minutes=60,
    enable_persistence=True
)

# API Gateway with authentication
gateway = create_gateway(
    title="My Production API",
    cors_origins=["https://myapp.com"],
    enable_docs=True
)

# Real-time communication
realtime = RealtimeMiddleware(agent_ui)

# AI chat integration
ai_chat = AIChatMiddleware(
    agent_ui,
    enable_vector_search=True,
    llm_provider="ollama"
)
```

### Key Middleware Features

- **Dynamic Workflow Creation**: Create workflows from frontend configurations using `WorkflowBuilder.from_dict()`
- **Real-time Communication**: WebSocket and SSE support for live updates
- **Session Management**: Multi-tenant isolation with automatic cleanup
- **AI Chat Integration**: Natural language workflow generation with context awareness
- **Database Persistence**: Repository pattern with audit logging
- **JWT Authentication**: Enterprise security with RBAC/ABAC access control
- **Health Monitoring**: Built-in health checks and performance metrics

### Frontend Integration

```python
# Create session for frontend client
session_id = await agent_ui.create_session("user123")

# Dynamic workflow from frontend
workflow_config = {
    "name": "data_pipeline",
    "nodes": [...],
    "connections": [...]
}

workflow_id = await agent_ui.create_dynamic_workflow(
    session_id, workflow_config
)

# Execute with real-time updates
execution_id = await agent_ui.execute_workflow(
    session_id, workflow_id, inputs={}
)
```

**Test Excellence**: 17/17 integration tests passing with 100% reliability for production deployment.

See [Middleware Integration Guide](sdk-users/developer/16-middleware-integration-guide.md) for complete documentation.

## 🔥 Advanced Features

### Unified Access Control (v0.3.3)

Single interface for all access control strategies:

```python
from kailash.access_control import AccessControlManager

# Choose your strategy
manager = AccessControlManager(strategy="abac")  # or "rbac" or "hybrid"

# ABAC example with helper functions
from kailash.access_control import create_attribute_condition

condition = create_attribute_condition(
    path="user.attributes.department",
    operator="hierarchical_match",
    value="finance"
)

# Database integration
db_node = AsyncSQLDatabaseNode(
    name="financial_query",
    query="SELECT * FROM sensitive_data",
    access_control_manager=manager
)
```

### Cyclic Workflows (Enhanced in v0.2.2)

Build iterative workflows with the new CycleBuilder API:

```python
# Create an optimization cycle
workflow.create_cycle("optimization_loop")
    .connect("processor", "processor")
    .max_iterations(100)
    .converge_when("quality >= 0.95")
    .timeout(30)
    .build()
```

### Self-Organizing Agent Pools

Create teams of AI agents that autonomously coordinate:

```python
from kailash.nodes.ai import SelfOrganizingAgentPoolNode

agent_pool = SelfOrganizingAgentPoolNode(
    formation_strategy="capability_matching",
    convergence_strategy="quality_voting",
    min_agents=3,
    max_agents=10
)
workflow.add_node("agent_team", agent_pool)
```

### Hierarchical RAG Pipeline

Build sophisticated document processing systems:

```python
from kailash.nodes.data import DocumentSourceNode, HierarchicalChunkerNode
from kailash.nodes.ai import EmbeddingGeneratorNode

# Build a complete RAG pipeline
workflow.add_node("docs", DocumentSourceNode(directory="./knowledge"))
workflow.add_node("chunker", HierarchicalChunkerNode(chunk_size=512))
workflow.add_node("embedder", EmbeddingGeneratorNode(provider="openai"))
```

### REST API Wrapper

Transform any workflow into a production API:

```python
from kailash.api import WorkflowAPI

# Create API from workflow
api = WorkflowAPI(workflow, host="0.0.0.0", port=8000)
api.run()

# Your workflow is now available at:
# POST http://localhost:8000/execute
# GET http://localhost:8000/workflow/info
```

## 🏗️ Key Components

### Nodes (85+ built-in)

- **Data**: CSVReaderNode, JSONReaderNode, SQLDatabaseNode, AsyncSQLDatabaseNode, DirectoryReaderNode
- **Admin**: UserManagementNode, RoleManagementNode, PermissionCheckNode, AuditLogNode, SecurityEventNode
- **Transform**: DataTransformer, DataFrameFilter, DataFrameJoiner
- **AI/ML**: LLMAgentNode, EmbeddingGeneratorNode, A2ACoordinatorNode, MCPAgentNode
- **API**: RESTClientNode, GraphQLNode, AuthNode, HTTPRequestNode
- **Logic**: SwitchNode, MergeNode, ConvergenceCheckerNode
- **Code**: PythonCodeNode, WorkflowNode
- **Alerts**: DiscordAlertNode with rich embeds and rate limiting
- **Security**: EnhancedAccessControlManager (ABAC with 16 operators)

### Runtimes

- **LocalRuntime**: Test workflows on your machine
- **DockerRuntime**: Run in containers (coming soon)
- **ParallelRuntime**: Execute nodes concurrently
- **CyclicWorkflowExecutor**: Optimized for iterative workflows

### Visualization

- **Mermaid diagrams**: Workflow structure visualization
- **Real-time dashboard**: Monitor execution with WebSocket streaming
- **Performance metrics**: Track execution time, resource usage

## 🧪 Testing Your Workflows

```python
# Use the testing runtime for unit tests
from kailash.runtime.testing import TestingRuntime

runtime = TestingRuntime()
runtime.set_mock_result("read_customers", {"data": test_data})
results, run_id = runtime.execute(workflow)
assert results["analyze"]["result"]["total_customers"] == len(test_data)
```

## 🚢 Production Deployment

1. **Export your workflow**:
   ```python
   export_workflow(workflow, "workflow.yaml", format="kailash")
   ```

2. **Deploy to Kailash**:
   ```bash
   kailash deploy workflow.yaml --environment production
   ```

3. **Monitor in real-time**:
   ```python
   from kailash.visualization import DashboardServer

   server = DashboardServer(port=8080)
   server.start()
   # Open http://localhost:8080 for live monitoring
   ```

## 🤝 Contributing

We welcome contributions! We use a **Claude Code-driven workflow** for all team collaboration.

### 🚀 New Team Member?
**Start Here → [NEW_TEAM_MEMBER.md](NEW_TEAM_MEMBER.md)**

### For Contributors
- **SDK Users**: See [sdk-users/CLAUDE.md](sdk-users/CLAUDE.md) for building with the SDK
- **SDK Contributors**: See [# contrib (removed)/CLAUDE.md](# contrib (removed)/CLAUDE.md) for SDK development
- **Team Collaboration**: Use [Claude Code Workflow System](# contrib (removed)/operations/claude-code-workflows/) for all project management

### Claude Code Workflow
All project management is done through conversational interaction with Claude Code:
- **No manual TODO editing** - Claude Code handles all updates
- **No direct GitHub issues** - Created through planning sessions
- **All progress tracked** - Through natural conversation

See [Contributing Guide](CONTRIBUTING.md) for complete details.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash-python-sdk

# Install with development dependencies
uv sync

# Run tests
pytest

# Run linting
black .
isort .
ruff check .

# Test all examples
python scripts/test-all-examples.py
```

## 🧪 Tests & Examples

### Comprehensive Test Suite
The SDK features a fully reorganized test suite with 127 tests organized by purpose:

```bash
# Run all tests
pytest

# Fast unit tests (92 tests)
pytest tests/unit/

# Integration tests (31 tests)
pytest tests/integration/

# End-to-end tests (4 tests)
pytest tests/e2e/

# Specific component tests
pytest tests/unit/nodes/ai/
```

**Test Structure:**
- **Unit Tests**: Fast, isolated component validation
- **Integration Tests**: Component interaction testing
- **E2E Tests**: Complete scenario validation
- **Unified Configuration**: Single `conftest.py` with 76+ fixtures

### Production Workflows & Examples
Clear separation of purpose for maximum value:

**Business Workflows** (`sdk-users/workflows/`):
```
sdk-users/workflows/
├── quickstart/           # 5-minute success stories
├── by-industry/         # Finance, healthcare, manufacturing
├── by-pattern/          # Data processing, AI/ML, API integration
├── integrations/        # Third-party platform connections
└── production-ready/    # Enterprise deployment patterns
```

**SDK Development** (`examples/`):
```
examples/
├── feature-validation/  # SDK component testing
├── test-harness/       # Development utilities
└── utils/              # Shared development tools
```

**Key Principles:**
- **Workflows**: Production business value, real-world solutions
- **Examples**: SDK development, feature validation
- **Tests**: Quality assurance, regression prevention

## 📈 Project Status

### ✅ v0.4.0 - Enterprise Middleware Architecture
- **Middleware Layer**: Complete refactor from monolithic to composable middleware
- **Real-time Communication**: WebSocket/SSE with comprehensive event streaming
- **AI Integration**: Built-in chat middleware with workflow generation
- **Test Excellence**: 799 tests passing (100% pass rate), organized structure
- **Gateway Integration**: Updated for middleware-based architecture
- **Performance**: Excluded slow tests from CI, builds complete in <2 minutes

### ✅ Previous Releases
- ✅ Core workflow engine with 100+ production-ready nodes
- ✅ Unified LocalRuntime (async + enterprise features)
- ✅ Export to container format
- ✅ Reorganized test suite (unit/integration/e2e structure)
- ✅ Self-organizing agent systems and hierarchical RAG
- ✅ Cyclic workflow support with CycleBuilder API
- ✅ Production security framework with RBAC/ABAC/Hybrid
- ✅ Async database infrastructure with pgvector support
- ✅ Admin tool framework with React UI and QA testing
- ✅ Comprehensive workflow library (finance, enterprise patterns)

### 🚧 In Progress
- 🚧 Visual workflow builder (Studio UI)
- 🚧 Docker runtime integration
- 🚧 Cloud deployment tools
- 🚧 Advanced RAG toolkit validation

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

Built with ❤️ by the Terrene Foundation team for the Kailash ecosystem.

---

<p align="center">
  <strong>Ready to build your first workflow? Check out our <a href="examples/">examples</a> or dive into the <a href="sdk-users/README.md">documentation</a>!</strong>
</p>
