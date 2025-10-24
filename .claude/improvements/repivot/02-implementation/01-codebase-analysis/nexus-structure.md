# Nexus Structure Analysis

**Purpose:** Understand Nexus architecture and identify extension points for repivot

---

## Overview

**Nexus** = Multi-channel workflow platform built on Core SDK
- **Zero-config deployment** - One workflow → API + CLI + MCP simultaneously
- **Unified sessions** - Session sync across all channels
- **Enterprise gateway** - Built on Core SDK's enterprise server
- **Production-ready** - Authentication, monitoring, health checks

**Version:** 1.0.0
**Location:** `apps/kailash-nexus/`
**Main Module:** `src/nexus/`

---

## Directory Structure

```
apps/kailash-nexus/
├── src/nexus/
│   ├── core.py              # Main Nexus class (1312 lines)
│   ├── __init__.py          # Public API exports
│   ├── channels.py          # Channel management
│   ├── discovery.py         # Auto-discovery
│   ├── plugins.py           # Plugin system
│   ├── resources.py         # Resource management
│   │
│   ├── mcp/                 # MCP server integration
│   │   ├── server.py        # WebSocket-only MCP server
│   │   └── transport.py     # Transport layer
│   │
│   └── cli/                 # CLI interface
│       ├── main.py          # CLI commands
│       └── __main__.py      # Entry point
│
├── examples/                # Example applications
├── tests/                   # Test suite
└── docs/                    # Documentation
```

---

## Architecture

### Three-Channel Deployment

**Single workflow, three interfaces:**

```
           ┌──────────────────────────┐
           │     Nexus Platform       │
           │   (Zero-Config Setup)    │
           └──────────┬───────────────┘
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼                       ▼
    ┌─────────┐             ┌─────────┐          ┌──────────┐
    │   API   │             │   CLI   │          │   MCP    │
    │ Channel │             │ Channel │          │ Channel  │
    └─────────┘             └─────────┘          └──────────┘
    HTTP/REST               Terminal             AI Agents
    Port 8000               subprocess           Port 3001
```

### Core Components

**1. Nexus Class (core.py)**

**Initialization:**
```python
def __init__(
    self,
    api_port: int = 8000,
    mcp_port: int = 3001,
    enable_auth: bool = False,
    enable_monitoring: bool = False,
    rate_limit: Optional[int] = None,
    auto_discovery: bool = True,
    enable_http_transport: bool = False,
    enable_sse_transport: bool = False,
    enable_durability: bool = True,
):
```

**What it does:**
1. Initializes enterprise gateway (from Core SDK)
2. Sets up multi-channel orchestration
3. Configures MCP server for AI agents
4. Enables optional features (auth, monitoring, rate limiting)

**2. Enterprise Gateway Integration**

**Uses Core SDK's `create_gateway()`:**
```python
self._gateway = create_gateway(
    title="Kailash Nexus - Zero-Config Workflow Platform",
    server_type="enterprise",
    enable_durability=True,
    enable_resource_management=True,
    enable_async_execution=True,
    enable_health_checks=True,
    cors_origins=["*"],
    max_workers=20,
)
```

**Gateway provides:**
- Multi-channel support (API, CLI, MCP)
- Authentication and authorization
- Health monitoring and metrics
- Resource management
- Durability and async execution
- Built-in enterprise endpoints

**3. Workflow Registration**

**Core method:**
```python
def register(self, name: str, workflow: Workflow):
    """Register a workflow with Nexus.

    Automatically:
    - Creates API endpoint: POST /workflows/{name}
    - Creates CLI command: nexus run {name}
    - Creates MCP tool: {name}(params)
    - Syncs sessions across channels
    """
```

**Example:**
```python
nexus = Nexus()

workflow = WorkflowBuilder()
workflow.add_node("LLMNode", "chat", {"model": "gpt-4"})

nexus.register("chat", workflow.build())
```

**This creates:**
- API: `POST /workflows/chat` with JSON params
- CLI: `nexus run chat --params '{"prompt": "Hello"}'`
- MCP: `chat(prompt="Hello")` tool for AI agents

**4. Multi-Channel Orchestration**

**Channel Registry:**
```python
self._channel_registry = {
    "api": {"routes": {}, "status": "pending"},
    "cli": {"commands": {}, "status": "pending"},
    "mcp": {"tools": {}, "status": "pending"},
}
```

**Session Management:**
- Unified sessions across channels
- Session sync (API → CLI, CLI → MCP, etc.)
- Execution context tracking

**5. MCP Integration**

**Two modes:**

**Mode 1: WebSocket-only (default)**
```python
from nexus.mcp import MCPServer

self._mcp_server = MCPServer(host="0.0.0.0", port=self._mcp_port)
```

**Mode 2: Full MCP Protocol (enable_http_transport=True)**
```python
from kailash.mcp_server import MCPServer
from kailash.channels import MCPChannel

# Uses Core SDK's production MCP server
self._mcp_server = self._create_sdk_mcp_server()
self._mcp_channel = self._setup_mcp_channel()
```

**MCP Features:**
- Tools (workflow execution)
- Resources (system info, documentation)
- Prompts (workflow templates)
- Multiple transports (stdio, HTTP, SSE, WebSocket)

---

## How It Works

### 1. Simple Usage (Zero-Config)

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Initialize Nexus (zero-config)
nexus = Nexus()

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("LLMNode", "chat", {
    "model": "gpt-4",
    "prompt": "{{user_prompt}}"
})

# Register (automatic multi-channel deployment)
nexus.register("chat", workflow.build())

# Start all channels
nexus.start()
# API: http://localhost:8000/workflows/chat
# CLI: nexus run chat
# MCP: stdio://localhost:3001 (AI agents)
```

### 2. Enterprise Usage (Full Features)

```python
nexus = Nexus(
    api_port=8000,
    mcp_port=3001,
    enable_auth=True,          # JWT authentication
    enable_monitoring=True,     # Prometheus metrics
    rate_limit=1000,           # Requests per minute
    enable_http_transport=True, # Full MCP protocol
    enable_durability=True,     # Request-level durability
)

# Register multiple workflows
nexus.register("chat", chat_workflow)
nexus.register("analyze", analyze_workflow)
nexus.register("summarize", summarize_workflow)

# All workflows available on all channels
nexus.start()
```

### 3. With DataFlow Integration

```python
from nexus import Nexus
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder

# Initialize DataFlow
db = DataFlow("postgresql://...")

@db.model
class Task:
    title: str
    status: str

# Initialize Nexus
nexus = Nexus()

# Create workflow using DataFlow nodes
workflow = WorkflowBuilder()
workflow.add_node("TaskCreateNode", "create", {
    "title": "{{task_title}}",
    "status": "pending"
})

# Register with Nexus
nexus.register("create_task", workflow.build())

# Now accessible via:
# - API: POST /workflows/create_task
# - CLI: nexus run create_task --task_title "My Task"
# - MCP: create_task(task_title="My Task")

nexus.start()
```

---

## Extension Points for Repivot

### High Priority: Template Integration

**Problem:** Templates need to deploy workflows easily

**Solution:** Nexus already works perfectly - just pre-configure in templates

**In SaaS Template:**
```python
# templates/saas-starter/main.py

from nexus import Nexus
from dataflow import DataFlow
from workflows import auth_workflows, user_workflows, admin_workflows

# AI INSTRUCTION: Nexus provides zero-config multi-channel deployment
# - API automatically available at /workflows/{name}
# - CLI automatically available as nexus run {name}
# - MCP automatically available for AI agents

# Initialize components
db = DataFlow("postgresql://...")  # From env
nexus = Nexus(
    api_port=8000,
    mcp_port=3001,
    enable_auth=True,  # Pre-configured for SaaS
    enable_monitoring=True,
)

# Register auth workflows
nexus.register("login", auth_workflows.login)
nexus.register("register", auth_workflows.register)
nexus.register("logout", auth_workflows.logout)

# Register user workflows
nexus.register("get_profile", user_workflows.get_profile)
nexus.register("update_profile", user_workflows.update_profile)

# Register admin workflows
nexus.register("list_users", admin_workflows.list_users)
nexus.register("deactivate_user", admin_workflows.deactivate_user)

# AI INSTRUCTION: To add a new workflow:
# 1. Create workflow in workflows/ directory
# 2. Register with nexus.register(name, workflow)
# 3. Automatically available on all channels

if __name__ == "__main__":
    nexus.start()  # Starts API + CLI + MCP
```

**No Nexus changes needed** - templates just use it correctly.

### Medium Priority: Quick Mode Integration

**Problem:** Quick Mode needs simple deployment

**Solution:** Add Quick Mode convenience method

**New Method (Add to Nexus):**
```python
# In nexus/core.py

def quick_deploy(self):
    """Quick Mode deployment - automatic workflow discovery.

    Discovers workflows in current directory and registers automatically.
    For production, use explicit register() calls.
    """
    if not self._auto_discovery_enabled:
        logger.warning("Auto-discovery disabled, use register() explicitly")
        return

    # Discover workflows from current directory
    from .discovery import discover_workflows

    workflows = discover_workflows()

    for name, workflow in workflows.items():
        self.register(name, workflow)
        logger.info(f"✅ Auto-registered workflow: {name}")

    # Start all channels
    self.start()

    logger.info(f"🚀 Quick Mode deployed {len(workflows)} workflows")
```

**Usage in Quick Mode:**
```python
from kailash.quick import app, db, nexus

# Quick Mode: Define workflows
@app.workflow("create_user")
def create_user(name: str, email: str):
    return db.users.create(name=name, email=email)

# Quick Mode: Deploy automatically
nexus.quick_deploy()
# Automatically:
# - Discovers all @app.workflow functions
# - Registers with Nexus
# - Starts all channels
```

**Changes Needed:** ~50 lines in `nexus/core.py`

### Medium Priority: Better Defaults for IT Teams

**Problem:** IT teams don't want to configure everything

**Solution:** Add configuration presets

**New Method:**
```python
# In nexus/core.py

@classmethod
def for_development(cls):
    """Preset for local development."""
    return cls(
        api_port=8000,
        mcp_port=3001,
        enable_auth=False,  # No auth in dev
        enable_monitoring=False,  # No monitoring in dev
        enable_durability=False,  # No caching in dev (faster iteration)
    )

@classmethod
def for_production(cls):
    """Preset for production deployment."""
    return cls(
        api_port=8000,
        mcp_port=3001,
        enable_auth=True,  # Auth required
        enable_monitoring=True,  # Metrics required
        enable_durability=True,  # Durability required
        enable_http_transport=True,  # Full MCP protocol
    )

@classmethod
def for_saas(cls):
    """Preset for SaaS applications."""
    return cls(
        api_port=8000,
        mcp_port=3001,
        enable_auth=True,
        enable_monitoring=True,
        rate_limit=1000,  # Rate limiting for multi-tenant
        enable_durability=True,
    )
```

**Usage:**
```python
# Development
nexus = Nexus.for_development()

# Production
nexus = Nexus.for_production()

# SaaS
nexus = Nexus.for_saas()
```

**Changes Needed:** ~60 lines in `nexus/core.py`

### Low Priority: Enhanced Error Messages

**Problem:** Errors not AI-friendly

**Solution:** Add error context

**Similar to DataFlow enhancement:**
```python
def register(self, name: str, workflow: Workflow):
    """Register workflow with enhanced error handling."""
    try:
        # Existing registration logic
        self._register_workflow(name, workflow)
    except Exception as e:
        # Enhanced error context
        context = {
            "workflow_name": name,
            "error": str(e),
            "suggestions": self._get_registration_suggestions(e)
        }
        raise NexusRegistrationError(context) from e

def _get_registration_suggestions(self, error: Exception) -> List[str]:
    """Get AI-friendly error suggestions."""
    suggestions = []
    error_str = str(error).lower()

    if "workflow" in error_str and "build" in error_str:
        suggestions.append(
            "Did you forget to call .build()?"
            "workflow = WorkflowBuilder().build()  # ← Must call .build()"
        )

    if "port" in error_str and "use" in error_str:
        suggestions.append(
            "Port already in use. Check if another Nexus instance is running."
            "Try: nexus = Nexus(api_port=8001)"  # Different port
        )

    return suggestions
```

**Changes Needed:** ~80 lines in `nexus/core.py`

---

## Nexus-Specific Repivot Components

### 1. Template Integration (No Changes)

**Templates will:**
- Import Nexus
- Register workflows
- Call `nexus.start()`

**Example structure:**
```
templates/saas-starter/
├── main.py              # Nexus initialization
├── workflows/
│   ├── auth.py         # Auth workflows
│   ├── users.py        # User workflows
│   └── admin.py        # Admin workflows
├── models.py           # DataFlow models
└── config.py           # Configuration
```

### 2. Quick Mode Integration

**Quick Mode will abstract Nexus:**
```python
# kailash/quick/platform.py (new file)

class QuickPlatform:
    """Quick Mode platform abstraction."""

    def __init__(self):
        from nexus import Nexus
        self.nexus = Nexus.for_development()
        self._workflows = {}

    def workflow(self, name: str):
        """Decorator to register workflow."""
        def decorator(func):
            # Convert function to workflow
            workflow = self._func_to_workflow(func)
            self.nexus.register(name, workflow)
            return func
        return decorator

    def deploy(self):
        """Deploy all registered workflows."""
        self.nexus.start()

# Usage
from kailash.quick import platform

@platform.workflow("greet")
def greet(name: str):
    return {"message": f"Hello, {name}!"}

platform.deploy()
# Now available:
# - POST /workflows/greet
# - nexus run greet --name Alice
# - greet(name="Alice") via MCP
```

### 3. Component Marketplace Integration

**Marketplace components using Nexus:**
- `kailash-admin`: Admin dashboard exposed via Nexus API
- `kailash-monitoring`: Metrics dashboard via Nexus
- `kailash-webhooks`: Webhook handlers registered with Nexus

**No Nexus changes needed** - components use Nexus as platform.

---

## DataFlow + Nexus Integration

### Current State (Works but Can Be Better)

**Known Issue:** Startup time 10-30 seconds when using both

**Cause:**
- DataFlow initializes (connection pool, migrations)
- Nexus initializes (gateway, channels)
- Both initialize simultaneously → can block each other

**Current Workaround (Documented):**
```python
# For production (full features, accept startup time)
nexus = Nexus()
db = DataFlow()

# For testing (fast startup, disable features)
nexus = Nexus(
    auto_discovery=False,  # Disable auto-discovery
    enable_durability=False,  # Disable caching
)
db = DataFlow(
    skip_registry=True,  # Skip model persistence
)
```

### Improvement for Repivot (Optional)

**Add lazy initialization:**
```python
# In nexus/core.py

def __init__(self, lazy_init: bool = False, **kwargs):
    """Initialize Nexus.

    Args:
        lazy_init: If True, defer initialization until start() called
    """
    if lazy_init:
        self._lazy_init = True
        self._init_kwargs = kwargs
        return

    # Normal initialization
    self._initialize(**kwargs)

def start(self):
    """Start Nexus (lazy init if needed)."""
    if self._lazy_init:
        self._initialize(**self._init_kwargs)
        self._lazy_init = False

    # Start channels
    self._start_channels()
```

**Usage:**
```python
# Lazy initialization (faster startup)
nexus = Nexus(lazy_init=True)  # Instant return
db = DataFlow()  # Initializes normally

# Both initialized, now start Nexus
nexus.start()  # Deferred initialization
```

**Changes Needed:** ~40 lines in `nexus/core.py`

---

## Changes Summary

### No Changes Needed ✅
- Core Nexus architecture (excellent design)
- Multi-channel orchestration (works perfectly)
- Workflow registration (simple, effective)
- Enterprise features (production-ready)
- DataFlow integration (works with workaround)

### Minor Additions (Optional)
- 🔧 Configuration presets (~60 lines) - `for_development()`, `for_production()`, `for_saas()`
- 🔧 Quick Mode integration (~50 lines) - `quick_deploy()` method
- 🔧 Enhanced error messages (~80 lines) - AI-friendly suggestions
- 🔧 Lazy initialization (~40 lines) - Faster startup with DataFlow

### Template Integration (No Code Changes)
- Templates import and use Nexus
- Pre-configured for SaaS use case
- AI instructions embedded in template code

### Quick Mode Integration (New Module)
- `kailash/quick/platform.py` (~200 lines)
- Abstracts Nexus for simplicity
- Decorator-based workflow registration

---

## Backward Compatibility

**100% backward compatible:**
- All changes are additive
- Existing Nexus usage unchanged
- New methods are optional
- Configuration presets are convenience (can still use constructor)

**Version Strategy:**
- Current: 1.0.0
- With enhancements: 1.1.0 (minor version bump)
- No breaking changes

---

## Key Takeaways

**Nexus is Already Excellent:**
- Zero-config deployment works
- Multi-channel orchestration is elegant
- Enterprise features are complete
- Integration with Core SDK is seamless

**What It Needs:**
- Configuration presets (convenience for IT teams)
- Quick Mode integration (hide complexity)
- Better error messages (AI-friendly)
- Optional lazy initialization (faster startup with DataFlow)

**How to Add:**
- Small additions to core.py (~230 lines total)
- New Quick Mode module (~200 lines)
- Template integration (usage, not code)

**Nexus doesn't need a rewrite - it needs convenience methods and better defaults for IT teams.**
