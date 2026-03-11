# Kaizen-Nexus Integration Best Practices

**Version**: 0.1.0
**Status**: Production Ready
**Part of**: TODO-149 Phase 4

## Overview

This guide provides best practices for building production-ready applications with the Kaizen-Nexus integration.

## Table of Contents

1. [Architecture Patterns](#architecture-patterns)
2. [Deployment Strategies](#deployment-strategies)
3. [Session Management](#session-management)
4. [Error Handling](#error-handling)
5. [Performance Optimization](#performance-optimization)
6. [Security Considerations](#security-considerations)
7. [Testing Strategies](#testing-strategies)
8. [Production Deployment](#production-deployment)

## Architecture Patterns

### 1. Optional Dependency Pattern

**Always check Nexus availability** before using integration features.

✅ **GOOD**:
```python
from kaizen.integrations.nexus import NEXUS_AVAILABLE

if NEXUS_AVAILABLE:
    from kaizen.integrations.nexus import deploy_multi_channel
    from nexus import Nexus

    app = Nexus(auto_discovery=False)
    channels = deploy_multi_channel(agent, app, "assistant")
else:
    # Fallback to direct Kaizen usage
    print("Nexus not available, using Kaizen directly")
    result = agent.process(query="...")
```

❌ **BAD**:
```python
# Don't assume Nexus is installed
from nexus import Nexus  # May raise ImportError
from kaizen.integrations.nexus import deploy_multi_channel
```

### 2. Multi-Channel Deployment Pattern

**Deploy once, access everywhere** using multi-channel deployment.

✅ **GOOD**:
```python
from kaizen.integrations.nexus import deploy_multi_channel

# Single deployment for all channels
channels = deploy_multi_channel(agent, app, "assistant")

# Access via:
# - API: POST /api/workflows/assistant/execute
# - CLI: nexus run assistant
# - MCP: tool "assistant"
```

❌ **BAD**:
```python
# Don't deploy separately (wastes resources)
api_endpoint = deploy_as_api(agent, app, "assistant")
cli_command = deploy_as_cli(agent, app, "assistant")
mcp_tool = deploy_as_mcp(agent, app, "assistant")
```

### 3. Session Management Pattern

**Maintain conversation context** across channels.

✅ **GOOD**:
```python
from kaizen.integrations.nexus import NexusSessionManager

# Create session manager
manager = NexusSessionManager(cleanup_interval=300)

# Create session
session = manager.create_session(user_id="user-123")

# Update from API
manager.update_session_state(
    session.session_id,
    {"query": "What is AI?", "source": "api"},
    channel="api"
)

# Read from CLI (sees API state)
state = manager.get_session_state(session.session_id, channel="cli")
assert state["query"] == "What is AI?"
```

❌ **BAD**:
```python
# Don't manage state separately per channel
api_state = {}
cli_state = {}
mcp_state = {}  # Fragmented state!
```

### 4. Configuration Pattern

**Use domain-specific config** with Kaizen UX improvements.

✅ **GOOD**:
```python
from dataclasses import dataclass

@dataclass
class AssistantConfig:
    """Domain-specific configuration."""
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 2000

# Auto-converted to BaseAgentConfig
agent = AIAssistant(config=AssistantConfig())
```

❌ **BAD**:
```python
# Don't use raw dictionaries
agent = AIAssistant(config={
    "llm_provider": "openai",
    "model": "gpt-4",
    # ... hard to maintain
})
```

## Deployment Strategies

### 1. Progressive Deployment

**Start simple, add features as needed.**

```python
# Phase 1: Single channel (API)
from kaizen.integrations.nexus import deploy_as_api

endpoint = deploy_as_api(agent, app, "assistant")

# Phase 2: Add CLI
from kaizen.integrations.nexus import deploy_as_cli

command = deploy_as_cli(agent, app, "assistant")

# Phase 3: Full multi-channel
from kaizen.integrations.nexus import deploy_multi_channel

channels = deploy_multi_channel(agent, app, "assistant")

# Phase 4: Add sessions
from kaizen.integrations.nexus import deploy_with_sessions

channels = deploy_with_sessions(agent, app, "assistant", session_manager)
```

### 2. Environment-Specific Deployment

**Configure differently** for dev, staging, production.

```python
import os

# Development
if os.getenv("ENVIRONMENT") == "development":
    app = Nexus(
        auto_discovery=False,
        api_port=8000,
        mcp_port=3001
    )
    config = AssistantConfig(llm_provider="mock")

# Staging
elif os.getenv("ENVIRONMENT") == "staging":
    app = Nexus(
        auto_discovery=False,
        api_port=8000,
        mcp_port=3001,
        enable_auth=True
    )
    config = AssistantConfig(llm_provider="openai", model="gpt-3.5-turbo")

# Production
else:
    app = Nexus(
        auto_discovery=False,
        api_port=8000,
        mcp_port=3001,
        enable_auth=True,
        enable_monitoring=True,
        rate_limit=100
    )
    config = AssistantConfig(llm_provider="openai", model="gpt-4")
```

### 3. Deployment Validation

**Verify deployment** before serving traffic.

```python
def deploy_and_validate(agent, app, name):
    """Deploy agent and validate deployment."""
    # Deploy
    channels = deploy_multi_channel(agent, app, name)

    # Validate all channels present
    assert "api" in channels, "API channel missing"
    assert "cli" in channels, "CLI channel missing"
    assert "mcp" in channels, "MCP channel missing"

    # Test endpoint
    health = app.health_check()
    assert health["status"] in ["healthy", "ok"], "Platform unhealthy"

    # Return deployment
    return channels
```

## Session Management

### 1. Session Lifecycle

**Create, use, and cleanup** sessions properly.

```python
from kaizen.integrations.nexus import NexusSessionManager

# Initialize manager
manager = NexusSessionManager(
    cleanup_interval=300,  # 5 minutes
    session_ttl=7200       # 2 hours
)

# Create session
session = manager.create_session(user_id="user-123")

# Use session
manager.update_session_state(
    session.session_id,
    {"context": "..."},
    channel="api"
)

# Read session
state = manager.get_session_state(session.session_id)

# Cleanup happens automatically, or manually:
cleaned = manager.cleanup_expired_sessions()
```

### 2. Session Configuration by Use Case

| Use Case | Cleanup Interval | Session TTL | Notes |
|----------|------------------|-------------|-------|
| Web chat | 5 minutes | 1-2 hours | Balance responsiveness/memory |
| CLI tools | 10 minutes | 4-8 hours | Longer sessions for development |
| Background jobs | 30 minutes | 24 hours | Low cleanup overhead |
| High traffic API | 2 minutes | 30 minutes | Aggressive cleanup |
| Long-running tasks | 60 minutes | 48 hours | Keep task context |

### 3. Session State Best Practices

✅ **GOOD**:
```python
# Store minimal, relevant data
manager.update_session_state(
    session_id,
    {
        "user_query": query,
        "response": response,
        "timestamp": time.time(),
        "context_summary": summary  # Not full conversation
    },
    channel="api"
)
```

❌ **BAD**:
```python
# Don't store large objects
manager.update_session_state(
    session_id,
    {
        "full_conversation_history": [...]  # 100+ messages
        "raw_embeddings": [...],            # Large vectors
        "cached_llm_responses": {...}       # Memory waste
    },
    channel="api"
)
```

## Error Handling

### 1. Graceful Degradation

**Handle missing Nexus** gracefully.

✅ **GOOD**:
```python
from kaizen.integrations.nexus import NEXUS_AVAILABLE

if NEXUS_AVAILABLE:
    try:
        from kaizen.integrations.nexus import deploy_multi_channel
        channels = deploy_multi_channel(agent, app, "assistant")
    except Exception as e:
        logger.error(f"Nexus deployment failed: {e}")
        # Fall back to direct usage
        result = agent.process(query="...")
else:
    # Use Kaizen directly
    result = agent.process(query="...")
```

### 2. Deployment Error Handling

**Validate parameters** and handle failures.

✅ **GOOD**:
```python
def safe_deploy(agent, app, name):
    """Deploy with error handling."""
    try:
        # Validate inputs
        if agent is None:
            raise ValueError("Agent cannot be None")
        if not hasattr(app, 'register'):
            raise TypeError("Invalid Nexus app")

        # Deploy
        channels = deploy_multi_channel(agent, app, name)

        # Verify deployment
        assert channels is not None
        return channels

    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        # Clean up partial deployment
        # ... cleanup code ...
        raise
```

### 3. Session Error Handling

**Handle missing or expired sessions**.

✅ **GOOD**:
```python
def get_session_safely(manager, session_id):
    """Get session with error handling."""
    state = manager.get_session_state(session_id)

    if state is None or state == {}:
        # Session not found or expired
        logger.warning(f"Session {session_id} not found, creating new session")
        # Create new session or return default
        return {"context": "new_session"}

    return state
```

## Performance Optimization

### 1. Enable Caching

**Use deployment caching** for production.

✅ **GOOD**:
```python
# Caching enabled by default (recommended)
channels = deploy_multi_channel(agent, app, "assistant")

# Explicit enable
channels = deploy_multi_channel(agent, app, "assistant", use_cache=True)
```

❌ **BAD**:
```python
# Don't disable caching without reason
channels = deploy_multi_channel(agent, app, "assistant", use_cache=False)
```

### 2. Monitor Performance

**Track metrics** for optimization.

✅ **GOOD**:
```python
from kaizen.integrations.nexus import PerformanceMetrics, PerformanceMonitor

metrics = PerformanceMetrics()

# Monitor deployments
with PerformanceMonitor(metrics, 'deployment'):
    deploy_multi_channel(agent, app, "assistant")

# Monitor API calls
with PerformanceMonitor(metrics, 'api'):
    result = agent.process(query="...")

# Analyze periodically
summary = metrics.get_summary()
if summary['api']['mean'] > 0.5:
    logger.warning("API latency exceeds 500ms")
```

### 3. Optimize Session Cleanup

**Configure cleanup** based on traffic.

```python
# High traffic: aggressive cleanup
session_manager = NexusSessionManager(
    cleanup_interval=120,  # 2 minutes
    session_ttl=1800       # 30 minutes
)

# Low traffic: relaxed cleanup
session_manager = NexusSessionManager(
    cleanup_interval=600,  # 10 minutes
    session_ttl=14400      # 4 hours
)
```

## Security Considerations

### 1. Authentication

**Enable authentication** in production.

```python
# Production configuration
app = Nexus(
    auto_discovery=False,
    enable_auth=True,      # Enable authentication
    enable_monitoring=True
)
```

### 2. Session Security

**Validate user_id** and prevent session hijacking.

✅ **GOOD**:
```python
def create_user_session(user_id, auth_token):
    """Create session with validation."""
    # Validate user
    if not validate_auth_token(auth_token):
        raise ValueError("Invalid auth token")

    # Create session
    session = session_manager.create_session(user_id=user_id)

    # Store auth info (not sensitive data)
    session_manager.update_session_state(
        session.session_id,
        {"auth_validated": True, "created_at": time.time()},
        channel="api"
    )

    return session
```

### 3. Rate Limiting

**Protect against abuse**.

```python
app = Nexus(
    auto_discovery=False,
    enable_auth=True,
    rate_limit=100  # 100 requests per minute
)
```

## Testing Strategies

### 1. Unit Testing

**Test components in isolation**.

```python
def test_agent_creation():
    """Test agent creation with config."""
    config = AssistantConfig()
    agent = AIAssistant(config)

    assert agent is not None
    assert agent.config.llm_provider == "mock"

def test_deployment_returns_channels():
    """Test deployment returns all channels."""
    channels = deploy_multi_channel(agent, app, "test")

    assert "api" in channels
    assert "cli" in channels
    assert "mcp" in channels
```

### 2. Integration Testing

**Test end-to-end workflows**.

```python
def test_multi_channel_workflow():
    """Test complete multi-channel workflow."""
    # Deploy
    channels = deploy_multi_channel(agent, app, "integration_test")

    # Create session
    session = session_manager.create_session(user_id="test_user")

    # API interaction
    session_manager.update_session_state(
        session.session_id,
        {"query": "test"},
        channel="api"
    )

    # CLI interaction (should see API state)
    state = session_manager.get_session_state(session.session_id, channel="cli")
    assert state["query"] == "test"
```

### 3. Performance Testing

**Verify performance targets**.

```python
def test_deployment_performance():
    """Test deployment completes within target."""
    start = time.time()

    channels = deploy_multi_channel(agent, app, "perf_test")

    duration = time.time() - start
    assert duration < 2.0, f"Deployment took {duration:.2f}s (target: <2s)"
```

## Production Deployment

### 1. Pre-Deployment Checklist

- [ ] Configure for production environment
- [ ] Enable authentication
- [ ] Enable monitoring
- [ ] Set appropriate rate limits
- [ ] Configure session cleanup
- [ ] Enable deployment caching
- [ ] Set up logging
- [ ] Configure error tracking

### 2. Deployment Steps

```python
# 1. Load configuration
config = load_production_config()

# 2. Initialize Nexus
app = Nexus(
    auto_discovery=False,
    api_port=8000,
    mcp_port=3001,
    enable_auth=True,
    enable_monitoring=True,
    rate_limit=100
)

# 3. Initialize session manager
session_manager = NexusSessionManager(
    cleanup_interval=300,
    session_ttl=7200
)

# 4. Create and deploy agent
agent = AIAssistant(config)
channels = deploy_with_sessions(agent, app, "assistant", session_manager)

# 5. Verify deployment
health = app.health_check()
assert health["status"] in ["healthy", "ok"]

# 6. Start platform
logger.info("Starting Nexus platform...")
app.start()  # Blocks until stopped
```

### 3. Post-Deployment Monitoring

```python
# Health checks
health = app.health_check()
logger.info(f"Platform status: {health['status']}")

# Session metrics
session_metrics = session_manager.get_session_metrics()
logger.info(f"Active sessions: {session_metrics['active_sessions']}")

# Performance metrics
perf_summary = metrics.get_summary()
logger.info(f"API latency: {perf_summary['api']['mean']*1000:.1f}ms")

# Set up alerts
if session_metrics['active_sessions'] > 1000:
    alert("High session count")
if perf_summary['api']['mean'] > 0.5:
    alert("High API latency")
```

## Common Pitfalls

### ❌ Don't: Use auto_discovery=True with DataFlow

```python
# BAD: Causes blocking
app = Nexus(auto_discovery=True)  # Blocks with DataFlow
```

**Solution**:
```python
# GOOD: Prevents blocking
app = Nexus(auto_discovery=False)
```

### ❌ Don't: Forget to cleanup sessions

```python
# BAD: Memory leak
session_manager = NexusSessionManager(cleanup_interval=None)
```

**Solution**:
```python
# GOOD: Regular cleanup
session_manager = NexusSessionManager(cleanup_interval=300)
```

### ❌ Don't: Disable caching without reason

```python
# BAD: Slow redeployments
deploy_multi_channel(agent, app, "assistant", use_cache=False)
```

**Solution**:
```python
# GOOD: Enable caching
deploy_multi_channel(agent, app, "assistant")  # use_cache=True default
```

### ❌ Don't: Store large objects in sessions

```python
# BAD: Memory waste
session_manager.update_session_state(
    session_id,
    {"full_history": [100+ messages]},  # Too large!
    channel="api"
)
```

**Solution**:
```python
# GOOD: Store summaries
session_manager.update_session_state(
    session_id,
    {"summary": "User asked about AI...", "message_count": 100},
    channel="api"
)
```

## Summary

| Best Practice | Impact | Priority | Notes |
|---------------|--------|----------|-------|
| Check NEXUS_AVAILABLE | Reliability | High | Prevents import errors |
| Use multi-channel deployment | Simplicity | High | Single deployment point |
| Enable caching | Performance | High | 90% faster redeployment |
| Configure session cleanup | Memory | High | Prevents leaks |
| Monitor performance | Observability | Medium | Identify bottlenecks |
| Enable authentication | Security | High | Production requirement |
| Test end-to-end | Quality | High | Catch integration issues |
| Use PerformanceMonitor | Debugging | Medium | Track timing |

## Next Steps

1. **Review** the [Performance Guide](performance.md) for optimization strategies
2. **Try** the [Complete Integration Example](../../examples/7-nexus-integration/complete-integration/)
3. **Test** your deployment with the test suite
4. **Deploy** to production following the checklist

## Related Documentation

- [Integration Guide](integration-guide.md)
- [Performance Guide](performance.md)
- [Complete Example](../../examples/7-nexus-integration/complete-integration/README.md)
- [API Reference](api-reference.md)
