---
skill: nexus-architecture
description: How Nexus works internally - architecture overview, design principles, and implementation details
priority: MEDIUM
tags: [nexus, architecture, design, internal, overview]
---

# Nexus Architecture

Understanding how Nexus works internally.

## High-Level Architecture

```
┌─────────────────────────────────────────────────┐
│                  Nexus Platform                  │
│                                                  │
│  ┌──────────────────────────────────────────┐  │
│  │         Multi-Channel Layer              │  │
│  │  ┌──────┐  ┌──────┐  ┌──────┐          │  │
│  │  │ API  │  │ CLI  │  │ MCP  │          │  │
│  │  └──┬───┘  └──┬───┘  └──┬───┘          │  │
│  └─────┼─────────┼─────────┼──────────────┘  │
│        └─────────┴─────────┘                   │
│                  │                              │
│  ┌───────────────┴──────────────────────────┐  │
│  │        Session Manager & Router          │  │
│  │  - Unified sessions across channels      │  │
│  │  - Request routing and validation        │  │
│  │  - Event broadcasting                    │  │
│  └───────────────┬──────────────────────────┘  │
│                  │                              │
│  ┌───────────────┴──────────────────────────┐  │
│  │         Enterprise Gateway               │  │
│  │  - Authentication & Authorization        │  │
│  │  - Rate Limiting & Circuit Breaker       │  │
│  │  - Caching & Monitoring                  │  │
│  └───────────────┬──────────────────────────┘  │
│                  │                              │
├──────────────────┴──────────────────────────────┤
│              Kailash SDK Core                   │
│  - WorkflowBuilder & Runtime                    │
│  - 110+ Nodes                                   │
│  - Execution Engine                             │
└─────────────────────────────────────────────────┘
```

## Core Components

### 1. Multi-Channel Layer

**Purpose**: Expose workflows via API, CLI, and MCP

**Components**:
- **API Channel**: FastAPI-based REST server
- **CLI Channel**: Command-line interface
- **MCP Channel**: Model Context Protocol server

**Key Features**:
- Single workflow registration
- Automatic endpoint generation
- Unified parameter handling

```python
# Implementation concept
class MultiChannelManager:
    def __init__(self):
        self.api = APIChannel()
        self.cli = CLIChannel()
        self.mcp = MCPChannel()

    def register_workflow(self, name, workflow):
        # Register in all channels
        self.api.register_endpoint(name, workflow)
        self.cli.register_command(name, workflow)
        self.mcp.register_tool(name, workflow)
```

### 2. Session Manager

**Purpose**: Unified session management across channels

**Features**:
- Cross-channel session persistence
- State synchronization
- Session lifecycle management

```python
class SessionManager:
    def __init__(self, backend="redis"):
        self.backend = backend
        self.sessions = {}

    def create_session(self, channel, metadata):
        session_id = generate_id()
        self.sessions[session_id] = {
            "channel": channel,
            "metadata": metadata,
            "created_at": time.time(),
            "state": {}
        }
        return session_id

    def sync_session(self, session_id, target_channel):
        # Sync session state across channels
        session = self.sessions.get(session_id)
        if session:
            session["channel"] = target_channel
            return session
```

### 3. Enterprise Gateway

**Purpose**: Production-grade features

**Components**:
- **Authentication**: OAuth2, JWT, API keys
- **Authorization**: RBAC, permissions
- **Rate Limiting**: Per-user, per-endpoint
- **Circuit Breaker**: Failure handling
- **Caching**: Response caching
- **Monitoring**: Metrics and tracing

```python
class EnterpriseGateway:
    def __init__(self):
        self.auth = AuthenticationManager()
        self.rate_limiter = RateLimiter()
        self.circuit_breaker = CircuitBreaker()
        self.cache = CacheManager()
        self.monitor = MonitoringManager()

    def process_request(self, request):
        # Authentication
        user = self.auth.authenticate(request)

        # Authorization
        if not self.auth.authorize(user, request.workflow):
            raise UnauthorizedError()

        # Rate limiting
        if not self.rate_limiter.check(user):
            raise RateLimitError()

        # Circuit breaker
        if self.circuit_breaker.is_open(request.workflow):
            raise ServiceUnavailableError()

        # Check cache
        cached = self.cache.get(request)
        if cached:
            return cached

        # Execute workflow
        result = self.execute_workflow(request)

        # Cache result
        self.cache.set(request, result)

        # Monitor
        self.monitor.record_request(request, result)

        return result
```

### 4. Workflow Registry

**Purpose**: Manage registered workflows

```python
class WorkflowRegistry:
    def __init__(self):
        self.workflows = {}
        self.metadata = {}

    def register(self, name, workflow, metadata=None):
        self.workflows[name] = workflow
        self.metadata[name] = metadata or {}

    def get(self, name):
        return self.workflows.get(name)

    def list(self):
        return list(self.workflows.keys())

    def get_metadata(self, name):
        return self.metadata.get(name, {})
```

## Design Principles

### 1. Zero Configuration

**Goal**: Work out-of-the-box with no config

```python
# Just works
app = Nexus()
app.start()
```

**Implementation**:
- Smart defaults for all settings
- Auto-detection of environment
- Graceful fallbacks

### 2. Progressive Enhancement

**Goal**: Start simple, add features as needed

```python
# Start simple
app = Nexus()

# Add features progressively
app.enable_auth = True
app.enable_monitoring = True
app.rate_limit = 1000
```

**Implementation**:
- Feature flags for all components
- Lazy initialization
- Optional dependencies

### 3. Multi-Channel Orchestration

**Goal**: Single source, multiple interfaces

**Implementation**:
- Abstract workflow execution layer
- Channel-agnostic request handling
- Unified response formatting

### 4. Built on Core SDK

**Goal**: Leverage existing Kailash SDK

**Benefits**:
- No SDK modification needed
- All 110+ nodes available
- Proven execution engine

```python
# Nexus uses Kailash SDK underneath
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

# Build workflow with SDK
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {...})

# Nexus registers and exposes it
app.register("test", workflow.build())
```

## Request Flow

### API Request Flow

```
1. Client sends HTTP POST to /workflows/name/execute
   ↓
2. API Channel receives request
   ↓
3. Enterprise Gateway processes:
   - Authentication
   - Rate limiting
   - Caching check
   ↓
4. Session Manager creates/retrieves session
   ↓
5. Workflow Registry retrieves workflow
   ↓
6. Kailash Runtime executes workflow
   ↓
7. Response formatted and cached
   ↓
8. Monitoring records metrics
   ↓
9. Response returned to client
```

### CLI Request Flow

```
1. User executes: nexus run workflow-name --param value
   ↓
2. CLI Channel parses arguments
   ↓
3. Converts to workflow request format
   ↓
4. Routes through Enterprise Gateway
   ↓
5. Workflow executed via Runtime
   ↓
6. Output formatted for terminal
   ↓
7. Displayed to user
```

### MCP Request Flow

```
1. AI agent discovers tools via MCP
   ↓
2. Agent calls tool with parameters
   ↓
3. MCP Channel receives request
   ↓
4. Routes through Enterprise Gateway
   ↓
5. Workflow executed
   ↓
6. Result formatted for AI consumption
   ↓
7. Returned to agent
```

## Parameter Broadcasting

```python
# How inputs flow to nodes
class ParameterBroadcaster:
    def broadcast_inputs(self, workflow, inputs):
        """
        Broadcast API inputs to ALL nodes in workflow
        Each node receives the full inputs dict
        """
        parameters = inputs  # inputs → parameters

        for node in workflow.nodes:
            # Each node gets full parameters
            node_params = {**node.config, **parameters}
            node.execute(node_params)
```

## Key Implementation Details

### Auto-Discovery

```python
class WorkflowDiscovery:
    PATTERNS = [
        "workflows/*.py",
        "*.workflow.py",
        "workflow_*.py",
        "*_workflow.py"
    ]

    def discover(self, paths):
        workflows = []
        for pattern in self.PATTERNS:
            for path in paths:
                workflows.extend(glob.glob(f"{path}/{pattern}"))
        return workflows

    def load_workflow(self, file_path):
        # Dynamic import
        spec = importlib.util.spec_from_file_location("module", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, 'workflow'):
            return module.workflow
```

### Health Checking

```python
class HealthChecker:
    def __init__(self):
        self.checks = {}

    def register_check(self, name, check_func):
        self.checks[name] = check_func

    def check_all(self):
        results = {}
        for name, check in self.checks.items():
            try:
                results[name] = check()
            except Exception as e:
                results[name] = {"status": "unhealthy", "error": str(e)}

        overall = "healthy" if all(
            r.get("status") == "healthy" for r in results.values()
        ) else "unhealthy"

        return {
            "status": overall,
            "components": results
        }
```

## Performance Optimizations

### 1. Connection Pooling

```python
# Database connections
pool = ConnectionPool(
    min_connections=5,
    max_connections=20,
    timeout=30
)
```

### 2. Response Caching

```python
# Cache expensive workflows
cache.set(
    key=f"workflow:{name}:{hash(inputs)}",
    value=result,
    ttl=300
)
```

### 3. Async Execution

```python
# Use async runtime for Docker/FastAPI
from kailash.runtime import AsyncLocalRuntime

runtime = AsyncLocalRuntime()
result = await runtime.execute_workflow_async(workflow, inputs)
```

## Key Takeaways

- Multi-layer architecture (Channels → Gateway → SDK)
- Zero-configuration with progressive enhancement
- Built on top of Kailash SDK
- Unified session management across channels
- Enterprise gateway for production features
- Parameter broadcasting to all nodes
- Multiple execution runtimes supported

## Related Skills

- [nexus-quickstart](#) - Get started quickly
- [nexus-multi-channel](#) - Multi-channel deep dive
- [nexus-enterprise-features](#) - Enterprise components
- [nexus-production-deployment](#) - Deploy architecture
