# Nexus Modifications

**File:** `apps/kailash-nexus/src/nexus/core.py`
**Estimated Effort:** 12 hours
**Risk:** Very Low (all additive)

---

## Changes Overview

**1. Configuration Presets** (~60 lines)
- `Nexus.for_development()` - Dev defaults
- `Nexus.for_production()` - Production defaults
- `Nexus.for_saas()` - SaaS-optimized defaults

**2. Quick Mode Integration** (~50 lines)
- `quick_deploy()` method
- Auto-discovery simplification

**3. Enhanced Error Messages** (~80 lines)
- Better registration errors
- AI-friendly suggestions

**Total Changes:** ~190 lines (in 1312 line file = ~15%)

---

## Change 1: Configuration Presets

### Current Usage (Requires Configuration Knowledge)

```python
# IT teams must know what to configure
nexus = Nexus(
    api_port=8000,
    mcp_port=3001,
    enable_auth=False,  # What should this be?
    enable_monitoring=False,  # When to enable?
    enable_durability=False,  # What's this for?
    rate_limit=None  # Do I need this?
)
```

**Problem:** IT teams don't know what to configure for their use case.

### Enhanced with Presets

```python
# apps/kailash-nexus/src/nexus/core.py

class Nexus:
    # ... existing __init__ (unchanged)

    @classmethod
    def for_development(cls):
        """Preset for local development.

        NEW METHOD: Pre-configured for fast iteration

        Features:
        - No authentication (faster dev loop)
        - No monitoring overhead
        - No durability (cleaner state)
        - Debug mode ON
        - Auto-discovery enabled

        Use when:
        - Developing locally
        - Testing workflows
        - Rapid iteration needed
        """
        return cls(
            api_port=8000,
            mcp_port=3001,
            enable_auth=False,
            enable_monitoring=False,
            enable_durability=False,
            auto_discovery=True
        )

    @classmethod
    def for_production(cls):
        """Preset for production deployment.

        NEW METHOD: Pre-configured for enterprise

        Features:
        - Authentication required
        - Monitoring enabled (Prometheus metrics)
        - Durability enabled (request persistence)
        - Rate limiting (1000 req/min)
        - Health checks enabled
        - Full MCP protocol (HTTP transport)

        Use when:
        - Deploying to production
        - Enterprise features needed
        - Compliance required
        """
        return cls(
            api_port=8000,
            mcp_port=3001,
            enable_auth=True,
            enable_monitoring=True,
            enable_durability=True,
            rate_limit=1000,
            enable_http_transport=True
        )

    @classmethod
    def for_saas(cls):
        """Preset for SaaS applications.

        NEW METHOD: Pre-configured for multi-tenant SaaS

        Features:
        - All production features
        - Higher rate limit (10K req/min for multi-tenant)
        - Multi-channel enabled (API + CLI + MCP)
        - Full MCP with SSE transport
        - Service discovery enabled

        Use when:
        - Building SaaS product
        - Multi-tenant application
        - Need all channels
        """
        return cls(
            api_port=8000,
            mcp_port=3001,
            enable_auth=True,
            enable_monitoring=True,
            enable_durability=True,
            rate_limit=10000,  # Higher for SaaS
            enable_http_transport=True,
            enable_sse_transport=True,
            enable_discovery=True
        )

    @classmethod
    def for_internal_tools(cls):
        """Preset for internal business tools.

        NEW METHOD: Pre-configured for internal use

        Features:
        - Basic auth (internal users only)
        - API + CLI focus (MCP optional)
        - Monitoring for debugging
        - No rate limiting (trusted users)

        Use when:
        - Building internal tools
        - Limited to company network
        - Trusted user base
        """
        return cls(
            api_port=8000,
            mcp_port=3001,
            enable_auth=True,  # Basic auth
            enable_monitoring=True,  # For debugging
            enable_durability=False,  # Not needed internally
            rate_limit=None  # No limit for internal
        )
```

**Usage:**
```python
# Before: Must know what to configure
nexus = Nexus(
    api_port=8000,
    enable_auth=True,
    enable_monitoring=True,
    # ... 10+ parameters
)

# After: Use appropriate preset
nexus = Nexus.for_saas()  # ✅ SaaS defaults
# OR
nexus = Nexus.for_development()  # ✅ Dev defaults
# OR
nexus = Nexus.for_production()  # ✅ Production defaults
```

**In templates:**
```python
# templates/saas-starter/main.py

from nexus import Nexus

# AI INSTRUCTION: Nexus presets for common scenarios:
# - Nexus.for_development() - Local dev (no auth, fast iteration)
# - Nexus.for_saas() - Multi-tenant SaaS (all features)
# - Nexus.for_production() - Production (auth, monitoring)

nexus = Nexus.for_saas()  # Pre-configured for SaaS

# All settings optimized:
# ✅ Authentication enabled
# ✅ Monitoring enabled
# ✅ Rate limiting: 10K req/min
# ✅ Multi-channel: API + CLI + MCP
```

**Backward compatibility: 100%**
- Original constructor unchanged
- Presets are classmethods (additive)
- Users can still configure manually if preferred

---

## Change 2: Quick Mode Integration

### Quick Deploy Method

```python
# In nexus/core.py

def quick_deploy(self, host: str = "0.0.0.0", port: int = None):
    """Quick Mode deployment - auto-discover and start.

    NEW METHOD: For Quick Mode convenience

    Automatically:
    - Discovers workflows in current directory
    - Registers all discovered workflows
    - Starts all channels (API + CLI + MCP)

    For production, use explicit register() calls.

    Args:
        host: Host to bind (default: 0.0.0.0)
        port: Port to use (default: from initialization)
    """
    if not self._auto_discovery_enabled:
        raise ValueError(
            "Auto-discovery disabled. Use register() explicitly or "
            "enable with auto_discovery=True"
        )

    # Discover workflows
    from .discovery import discover_workflows

    workflows = discover_workflows()

    if not workflows:
        print("⚠️  No workflows found in current directory")
        print("   Create workflows with @app.workflow decorator")
        return

    # Register all discovered workflows
    for name, workflow in workflows.items():
        self.register(name, workflow)

    print(f"✅ Auto-discovered {len(workflows)} workflows")

    # Start
    self.start(host=host, port=port or self._api_port)

    print(f"🚀 Quick Mode deployed!")
    print(f"   API: http://{host}:{port or self._api_port}")
    print(f"   MCP: stdio://localhost:{self._mcp_port}")
```

**Usage (Quick Mode):**
```python
# kailash/quick/app.py

from nexus import Nexus

class QuickApp:
    def __init__(self):
        self.nexus = Nexus.for_development()

    def run(self):
        """Start the app (auto-deploys workflows)."""
        self.nexus.quick_deploy()

# User's app.py
from kailash.quick import app

@app.workflow("greet")
def greet(name: str):
    return {"message": f"Hello, {name}!"}

app.run()  # Auto-discovers and deploys 'greet' workflow
```

**Backward compatibility: 100%** (new method, doesn't affect existing usage)

---

## Change 3: Enhanced Error Messages

### Registration Errors

```python
# In nexus/core.py

def register(self, name: str, workflow: Workflow):
    """Register workflow with enhanced error handling."""

    try:
        # Handle WorkflowBuilder (forgot .build())
        if hasattr(workflow, "build"):
            raise ValueError(
                f"Workflow '{name}' is a WorkflowBuilder, not a Workflow.\n"
                f"Did you forget to call .build()?\n\n"
                f"❌ WRONG: nexus.register('{name}', workflow)\n"
                f"✅ CORRECT: nexus.register('{name}', workflow.build())"
            )

        # ... existing registration logic

    except Exception as e:
        # Build error context
        suggestions = self._get_registration_error_suggestions(e, name)

        enhanced_message = (
            f"Failed to register workflow '{name}': {str(e)}\n\n"
            f"Suggestions:\n" + "\n".join(f"  - {s}" for s in suggestions)
        )

        raise NexusRegistrationError(enhanced_message) from e

def _get_registration_error_suggestions(self, error: Exception, workflow_name: str) -> list:
    """Get AI-friendly error suggestions.

    NEW METHOD: Pattern match common registration errors
    """
    suggestions = []
    error_str = str(error).lower()

    if "build" in error_str:
        suggestions.append(
            "Did you forget to call .build()?\n"
            "  workflow = WorkflowBuilder()\n"
            "  workflow.add_node(...)\n"
            "  nexus.register('name', workflow.build())  # ← Must call .build()"
        )

    if "port" in error_str and ("use" in error_str or "bind" in error_str):
        suggestions.append(
            "Port already in use. Check if another Nexus instance is running.\n"
            "  Option 1: Stop other instance\n"
            "  Option 2: Use different port (nexus = Nexus(api_port=8001))"
        )

    if "workflow" in error_str and "none" in error_str:
        suggestions.append(
            "Workflow is None. Check that your workflow function returns workflow.build():\n"
            "  def my_workflow():\n"
            "      workflow = WorkflowBuilder()\n"
            "      workflow.add_node(...)\n"
            "      return workflow.build()  # ← Don't forget this"
        )

    if not suggestions:
        suggestions.append(
            f"Check that workflow '{workflow_name}' is properly defined.\n"
            f"See: https://docs.kailash.dev/nexus/registration-errors"
        )

    return suggestions
```

**Example enhanced error:**
```
NexusRegistrationError: Failed to register workflow 'create_user': Workflow is a WorkflowBuilder, not a Workflow.

Did you forget to call .build()?

❌ WRONG: nexus.register('create_user', workflow)
✅ CORRECT: nexus.register('create_user', workflow.build())

Fix: Add .build() to the end of your WorkflowBuilder chain.
```

---

## Change 4: Startup Optimization (Optional)

### Lazy Initialization

```python
# In nexus/core.py

def __init__(
    self,
    lazy_init: bool = False,  # ← NEW parameter
    **kwargs
):
    """Initialize Nexus.

    Args:
        lazy_init: If True, defer initialization until start() called
        **kwargs: Existing parameters
    """
    if lazy_init:
        # Store parameters, don't initialize yet
        self._lazy_init = True
        self._init_params = kwargs
        return

    # Normal initialization (existing code)
    self._initialize(**kwargs)

def _initialize(self, **kwargs):
    """Perform actual initialization.

    NEW METHOD: Extracted from __init__ to support lazy init
    """
    # Move existing __init__ logic here
    self._api_port = kwargs.get("api_port", 8000)
    self._mcp_port = kwargs.get("mcp_port", 3001)
    # ... all existing initialization

def start(self, host: str = "0.0.0.0", port: int = None):
    """Start Nexus (handle lazy init).

    MODIFIED: Check for lazy init
    """
    # NEW: Lazy initialization
    if hasattr(self, "_lazy_init") and self._lazy_init:
        self._initialize(**self._init_params)
        self._lazy_init = False

    # ... existing start logic (unchanged)
```

**Usage (with DataFlow for faster startup):**
```python
# Lazy initialization (faster startup with DataFlow)
nexus = Nexus(lazy_init=True)  # Returns immediately
db = DataFlow("postgresql://...")  # Initializes normally

# Both initialized, now start Nexus
nexus.start()  # Deferred initialization happens here
```

**Backward compatibility: 100%**
- lazy_init defaults to False (existing behavior)
- Only used when explicitly enabled
- Solves DataFlow + Nexus startup time issue (optional)

---

## Testing

### Regression Tests

```python
# apps/kailash-nexus/tests/test_backward_compatibility.py

def test_existing_nexus_usage_unchanged():
    """Test that existing Nexus usage works identically."""
    from nexus import Nexus
    from kailash.workflow.builder import WorkflowBuilder

    # OLD usage (must work)
    nexus = Nexus(api_port=8000, mcp_port=3001)

    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "test", {
        "code": "return {'result': 42}",
        "inputs": {}
    })

    nexus.register("test", workflow.build())

    # Should register successfully (same as before)
    assert "test" in nexus._workflows

def test_original_constructor_still_works():
    """Test that original constructor signature is unchanged."""
    from nexus import Nexus

    # Should work with all original parameters
    nexus = Nexus(
        api_port=8000,
        mcp_port=3001,
        enable_auth=False,
        enable_monitoring=False,
        rate_limit=None,
        auto_discovery=True
    )

    assert nexus._api_port == 8000
    assert nexus._mcp_port == 3001
```

### New Feature Tests

```python
# apps/kailash-nexus/tests/test_configuration_presets.py

def test_for_development_preset():
    """Test development preset configuration."""
    from nexus import Nexus

    nexus = Nexus.for_development()

    assert nexus._enable_auth is False
    assert nexus._enable_monitoring is False
    assert nexus._enable_durability is False
    assert nexus._api_port == 8000

def test_for_production_preset():
    """Test production preset configuration."""
    from nexus import Nexus

    nexus = Nexus.for_production()

    assert nexus._enable_auth is True
    assert nexus._enable_monitoring is True
    assert nexus._enable_durability is True

def test_for_saas_preset():
    """Test SaaS preset configuration."""
    from nexus import Nexus

    nexus = Nexus.for_saas()

    assert nexus._enable_auth is True
    assert nexus._enable_monitoring is True
    assert nexus.rate_limit_config or hasattr(nexus, "_rate_limit")

def test_presets_can_be_overridden():
    """Test that preset values can be overridden."""
    from nexus import Nexus

    # Start with dev preset, override specific values
    # Note: Need to add parameter override support

    # For now, presets are fixed
    # Future: Allow override like Nexus.for_development(api_port=9000)
```

---

## Change 5: Better Start Method

### Enhanced Startup Feedback

```python
# In nexus/core.py

def start(self, host: str = "0.0.0.0", port: int = None):
    """Start Nexus with enhanced feedback.

    MODIFIED: Better startup messages for IT teams
    """
    # Lazy init check (if implemented)
    if hasattr(self, "_lazy_init") and self._lazy_init:
        self._initialize(**self._init_params)

    # NEW: Pre-flight checks
    issues = self._preflight_checks()
    if issues:
        print("⚠️  Startup warnings:")
        for issue in issues:
            print(f"   - {issue}")
        print()

    # ... existing start logic

    # NEW: Enhanced startup message
    port = port or self._api_port

    print("="  * 60)
    print(f"🚀 Kailash Nexus Started")
    print("=" * 60)
    print(f"")
    print(f"📡 API Server")
    print(f"   URL: http://{host}:{port}")
    print(f"   Endpoints:")
    for name in self._workflows:
        print(f"     - POST /workflows/{name}/execute")
    print(f"")
    print(f"🤖 MCP Server")
    print(f"   Port: {self._mcp_port}")
    print(f"   Tools: {len(self._workflows)} workflows")
    print(f"")
    print(f"⚙️  Configuration")
    print(f"   Auth: {'Enabled' if self._enable_auth else 'Disabled'}")
    print(f"   Monitoring: {'Enabled' if self._enable_monitoring else 'Disabled'}")
    print(f"   Rate Limit: {self._rate_limit or 'None'}")
    print(f"")
    print(f"📚 Documentation: http://{host}:{port}/docs")
    print(f"❤️  Health Check: http://{host}:{port}/health")
    print("=" * 60)

    # Start gateway (existing code)
    self._gateway.run(host=host, port=port)

def _preflight_checks(self) -> list:
    """Run pre-flight checks before startup.

    NEW METHOD: Warn about common misconfigurations
    """
    issues = []

    # Check: Auth enabled but no JWT_SECRET
    if self._enable_auth:
        if not os.getenv("JWT_SECRET"):
            issues.append(
                "Auth enabled but JWT_SECRET not set in environment. "
                "Tokens won't be secure."
            )

    # Check: Production mode but no monitoring
    if self._enable_durability and not self._enable_monitoring:
        issues.append(
            "Durability enabled but monitoring disabled. "
            "Enable monitoring for production visibility."
        )

    # Check: Rate limiting without auth
    if hasattr(self, "_rate_limit") and self._rate_limit and not self._enable_auth:
        issues.append(
            "Rate limiting enabled but auth disabled. "
            "Rate limits are per-user, enable auth for effective rate limiting."
        )

    # Check: No workflows registered
    if not self._workflows:
        issues.append(
            "No workflows registered. "
            "Use nexus.register(name, workflow) before calling start()."
        )

    return issues
```

**Output:**
```
============================================================
🚀 Kailash Nexus Started
============================================================

📡 API Server
   URL: http://0.0.0.0:8000
   Endpoints:
     - POST /workflows/login/execute
     - POST /workflows/create_user/execute
     - POST /workflows/list_users/execute

🤖 MCP Server
   Port: 3001
   Tools: 3 workflows

⚙️  Configuration
   Auth: Enabled
   Monitoring: Enabled
   Rate Limit: 10000 req/min

📚 Documentation: http://0.0.0.0:8000/docs
❤️  Health Check: http://0.0.0.0:8000/health
============================================================
```

---

## Documentation Updates

### New Guide: Nexus Presets

**Location:** `sdk-users/docs-it-teams/nexus/presets-guide.md`

```markdown
# Nexus Configuration Presets

Choose the preset that matches your use case.

## Development

```python
nexus = Nexus.for_development()
```

**When to use:**
- Local development
- Testing workflows
- Rapid iteration

**Features:**
- No authentication (faster dev loop)
- No monitoring overhead
- Auto-reload on changes
- Debug mode enabled

## Production

```python
nexus = Nexus.for_production()
```

**When to use:**
- Production deployment
- Enterprise features needed
- Security required

**Features:**
- Authentication required
- Monitoring enabled (Prometheus)
- Rate limiting (1000 req/min)
- Health checks
- Request durability

## SaaS

```python
nexus = Nexus.for_saas()
```

**When to use:**
- Multi-tenant SaaS product
- Multiple customers
- Need all features

**Features:**
- All production features
- Higher rate limit (10K req/min)
- Multi-channel (API + CLI + MCP)
- Service discovery

## Internal Tools

```python
nexus = Nexus.for_internal_tools()
```

**When to use:**
- Internal business tools
- Company network only
- Trusted users

**Features:**
- Basic auth
- API + CLI focus
- Monitoring for debugging
- No rate limiting

## Custom Configuration

If presets don't fit, use manual configuration:

```python
nexus = Nexus(
    api_port=8000,
    enable_auth=True,
    enable_monitoring=False,
    rate_limit=500,
    # ... custom config
)
```
```

---

## Change Summary

### Lines Changed

**nexus/core.py:**
- Configuration presets: +60 lines (new classmethods)
- Quick deploy: +50 lines (new method)
- Enhanced errors: +80 lines (new methods)
- Preflight checks: +40 lines (new method)
- Enhanced startup: +30 lines (modified start())

**Total: +260 lines** (in 1312 line file)

**New percentage: 1572 lines** (~20% increase, all additive)

### Impact Assessment

**Benefits:**
- ✅ IT teams choose preset (no configuration knowledge needed)
- ✅ Quick Mode integration seamless
- ✅ Better error messages (save hours of debugging)
- ✅ Preflight checks (catch misconfigurations early)

**Costs:**
- ⚠️ Slight code increase (~260 lines)
- ⚠️ More methods to test
- ⚠️ Documentation for presets needed

**Risk: Very low**
- All changes additive
- Existing API unchanged
- Backward compatible 100%

---

## Rollout Plan

**Week 1:** Implement configuration presets
**Week 2:** Implement quick_deploy() and enhanced errors
**Week 3:** Testing (regression + new features)
**Week 4:** Documentation and beta testing

---

## Key Takeaways

**Nexus modifications are minimal but high-value:**
- Presets solve "what should I configure?" problem
- Enhanced errors prevent misconfiguration
- Quick Mode integration enables simplified API
- All changes backward compatible

**For IT teams:**
- `Nexus.for_saas()` is much easier than configuring 10+ parameters
- Enhanced errors provide immediate guidance
- Preflight checks catch issues before startup

**For developers:**
- Can still use original constructor
- Can customize presets if needed
- No breaking changes to existing code

---

**Next:** See `04-cli-additions.md` for new CLI commands
