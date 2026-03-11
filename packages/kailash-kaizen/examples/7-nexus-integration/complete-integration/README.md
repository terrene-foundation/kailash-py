# Complete Kaizen-Nexus Integration

**Category**: Nexus Integration
**Complexity**: Advanced
**Demonstrates**: Complete production-ready integration pattern

## Overview

This example showcases the complete Kaizen-Nexus integration with all features:

- **Multi-Channel Deployment**: Deploy once, access via API, CLI, and MCP
- **Session Management**: Maintain conversation context across channels
- **Performance Monitoring**: Track deployment and execution metrics
- **Deployment Caching**: 90% faster redeployment with automatic caching
- **Production Patterns**: Error handling, resource cleanup, health monitoring

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Nexus Platform                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐      │
│  │   API    │     │   CLI    │     │   MCP    │      │
│  │ Channel  │     │ Channel  │     │ Channel  │      │
│  └────┬─────┘     └────┬─────┘     └────┬─────┘      │
│       │                │                │             │
│       └────────────────┴────────────────┘             │
│              Session Manager                          │
│        (Cross-Channel Synchronization)                │
│                                                        │
├─────────────────────────────────────────────────────────┤
│                  AI Assistant Agent                     │
│          (Kaizen Signature-Based Programming)          │
└─────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Multi-Channel Deployment

Deploy your agent once and access it three ways:

```python
channels = deploy_multi_channel(agent, app, "assistant")

# API: POST /api/workflows/assistant/execute
# CLI: nexus run assistant --query "..."
# MCP: Tool "assistant" for Claude Code
```

### 2. Session Management

Sessions maintain state across channels:

```python
# API updates session
manager.update_session_state(session_id, {"query": "..."}, "api")

# CLI accesses same session
state = manager.get_session_state(session_id, "cli")

# MCP continues conversation
result = agent.process(query="...", context=state)
```

### 3. Performance Monitoring

Track all operations:

```python
metrics = PerformanceMetrics()

with PerformanceMonitor(metrics, 'deployment'):
    deploy_multi_channel(agent, app, "assistant")

summary = metrics.get_summary()
print(f"Deployment: {summary['deployment']['mean']*1000:.1f}ms")
```

### 4. Deployment Caching

Automatic workflow caching for faster redeployment:

```python
# Initial deployment: ~1.5s
channels = deploy_multi_channel(agent, app, "assistant")

# Cached redeployment: ~0.15s (90% faster)
channels = deploy_multi_channel(agent, app, "assistant")
```

## Performance Targets

| Operation         | Target    | Typical   | Status |
|-------------------|-----------|-----------|--------|
| Multi-channel deploy | <2s    | ~1.5s     | ✓      |
| Cached deploy     | <0.2s     | ~0.15s    | ✓      |
| API latency       | <500ms    | ~300ms    | ✓      |
| CLI latency       | <500ms    | ~300ms    | ✓      |
| MCP latency       | <500ms    | ~300ms    | ✓      |
| Session sync      | <50ms     | ~10ms     | ✓      |

## Usage

### Running the Example

```bash
cd examples/7-nexus-integration/complete-integration
python workflow.py
```

### Expected Output

```
======================================================================
COMPLETE KAIZEN-NEXUS INTEGRATION SHOWCASE
======================================================================

[1/8] Initializing performance monitoring...
[2/8] Initializing Nexus platform...
      Platform initialized in 42.3ms

[3/8] Configuring session management...
      Session management configured
      - Cleanup interval: 5 minutes
      - Session TTL: 2 hours

[4/8] Creating AI assistant...
      Assistant created with signature-based programming
      - Provider: mock
      - Model: gpt-4
      - Temperature: 0.7

[5/8] Deploying across all channels (API, CLI, MCP)...
      Deployment completed in 1532.8ms

      Channels available:
      - API     : /api/workflows/assistant/execute
      - CLI     : nexus run assistant
      - MCP     : assistant

[6/8] Demonstrating multi-channel usage...
      Session created: sess_abc123...

      [API] Simulating API request...
      [API] Response time: 287.4ms
      [API] Response: Quantum computing uses quantum mechanics...

      [CLI] Simulating CLI command...
      [CLI] Response time: 294.1ms
      [CLI] Context preserved: Explain quantum computing...

      [MCP] Simulating MCP tool call...
      [MCP] Response time: 301.8ms
      [MCP] Full context available: 7 keys

      Verifying cross-channel session synchronization...
      Session state contains: ['query', 'channel', 'timestamp', ...]
      Channels used: dict_keys(['api', 'cli', 'mcp'])

[7/8] Performance analysis:

      Deployment Performance:
      - Mean:   786.4ms
      - Median: 786.4ms
      - Count:  2

      API Latency:
      - Mean:   287.4ms
      - Target: <500ms ✓

      CLI Latency:
      - Mean:   294.1ms
      - Target: <500ms ✓

      MCP Latency:
      - Mean:   301.8ms
      - Target: <500ms ✓

[8/8] Cleanup and summary...
      Cleaned 0 expired sessions
      Active sessions: 1
      Total sessions: 1
      Platform status: healthy

======================================================================
INTEGRATION SHOWCASE COMPLETE
======================================================================

✓ All systems operational
✓ Multi-channel deployment verified
✓ Session management working
✓ Performance within targets
✓ Production-ready patterns demonstrated
```

## Production Deployment

### 1. Configure for Production

```python
# Use real LLM provider
config = AssistantConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7
)

# Configure Nexus for production
app = Nexus(
    auto_discovery=False,
    api_port=8000,
    mcp_port=3001,
    enable_auth=True,
    enable_monitoring=True
)

# Configure session management
session_manager = NexusSessionManager(
    cleanup_interval=300,   # 5 minutes
    session_ttl=7200        # 2 hours
)
```

### 2. Deploy and Start

```python
# Deploy agent
channels = deploy_multi_channel(agent, app, "assistant")

# Start platform (blocks until stopped)
app.start()
```

### 3. Monitor Performance

```python
# Check platform health
health = app.health_check()
print(f"Status: {health['status']}")

# Review performance metrics
summary = metrics.get_summary()
print(f"API latency: {summary['api']['mean']*1000:.1f}ms")

# Monitor session metrics
session_metrics = session_manager.get_session_metrics()
print(f"Active sessions: {session_metrics['active_sessions']}")
```

## Testing

This example includes comprehensive tests in `tests/integration/test_end_to_end_nexus.py`.

Run tests:
```bash
pytest tests/integration/test_end_to_end_nexus.py -v
```

## Best Practices

### 1. Always Check Nexus Availability

```python
from kaizen.integrations.nexus import NEXUS_AVAILABLE

if not NEXUS_AVAILABLE:
    print("Nexus not available")
    exit(1)
```

### 2. Use auto_discovery=False

```python
# Prevents blocking with DataFlow
app = Nexus(auto_discovery=False)
```

### 3. Enable Caching for Production

```python
# Caching is enabled by default
channels = deploy_multi_channel(agent, app, "assistant")  # use_cache=True
```

### 4. Configure Session Cleanup

```python
# Set appropriate cleanup interval and TTL
session_manager = NexusSessionManager(
    cleanup_interval=300,  # 5 minutes
    session_ttl=7200       # 2 hours
)
```

### 5. Monitor Performance

```python
# Use PerformanceMonitor for critical operations
with PerformanceMonitor(metrics, 'deployment'):
    deploy_multi_channel(agent, app, "assistant")
```

## Troubleshooting

### Nexus Not Available

```
ERROR: Nexus not available. Install with: pip install kailash-nexus
```

**Solution**: Install Nexus integration
```bash
pip install kailash-nexus
# or
pip install kailash[nexus]
```

### Slow Deployment

**Symptoms**: Deployment takes >5 seconds

**Solutions**:
1. Ensure `auto_discovery=False` when using with DataFlow
2. Verify caching is enabled (`use_cache=True`, default)
3. Check for network/database latency

### Session Not Synchronized

**Symptoms**: State not preserved across channels

**Solutions**:
1. Verify same `session_id` used across channels
2. Check `session_manager.get_session_state()` returns expected data
3. Ensure session hasn't expired (check TTL)

## Related Examples

- **Multi-Channel Deployment**: `examples/7-nexus-integration/multi-channel-deployment/`
- **Session Management**: `examples/7-nexus-integration/session-management/`
- **Deployment Patterns**: `examples/7-nexus-integration/deployment-patterns/`

## Documentation

- [Kaizen-Nexus Integration Guide](../../../docs/integrations/nexus/integration-guide.md)
- [Performance Optimization](../../../docs/integrations/nexus/performance.md)
- [Best Practices](../../../docs/integrations/nexus/best-practices.md)

## Part of TODO-149

This example completes **Phase 4: Performance & Testing** of the Kaizen-Nexus integration roadmap.

**Status**: ✅ Production Ready
