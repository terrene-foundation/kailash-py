---
skill: nexus-config-options
description: Configuration capabilities for Nexus including ports, auth, rate limiting, monitoring
priority: MEDIUM
tags: [nexus, configuration, options, settings]
---

# Nexus Configuration Options

## Configuration Capabilities

Nexus supports configuration through constructor parameters, environment variables, and configuration files. The exact parameter names and defaults vary by SDK.

### Capability Matrix

| Category        | Capability               | Shared API                            |
| --------------- | ------------------------ | ------------------------------------- |
| **Server**      | API port                 | `api_port` / `port`                   |
| **Server**      | API host/bind address    | Constructor param                     |
| **Server**      | MCP port                 | `mcp_port`                            |
| **Discovery**   | Auto-discover workflows  | `auto_discovery` (False for DataFlow) |
| **Security**    | Authentication           | `add_plugin(auth_plugin)`             |
| **Security**    | Rate limiting            | Constructor or plugin                 |
| **Security**    | CORS                     | Constructor or middleware             |
| **Monitoring**  | Enable monitoring        | Constructor param                     |
| **Monitoring**  | Health checks            | `health_check()`                      |
| **Sessions**    | Session timeout          | Constructor param                     |
| **Sessions**    | Session backend          | Constructor param (memory/redis)      |
| **Logging**     | Log level                | Constructor param                     |
| **Logging**     | Log format (text/json)   | Constructor param                     |
| **Performance** | Max concurrent workflows | Constructor param                     |
| **Performance** | Request timeout          | Constructor param                     |
| **API**         | API prefix/versioning    | Constructor param                     |
| **Enterprise**  | Presets                  | `preset` param                        |

## Shared Configuration Patterns

### Port Configuration

```
app = Nexus(api_port=8000, mcp_port=3001)
```

### DataFlow Integration

```
app = Nexus(auto_discovery=False)  # CRITICAL: prevents startup blocking
```

### Presets

```
app = Nexus(preset="saas")
app = Nexus(preset="enterprise")
```

### Middleware and Plugins

```
app.add_middleware(SomeMiddleware, param="value")
app.include_router(my_router)
app.add_plugin(auth_plugin)
```

### Health Check

```
health = app.health_check()
```

## Environment Variables

Common environment variables (exact names may vary by SDK):

```bash
# Environment
export NEXUS_ENV=production          # Controls security auto-enable

# Server
export NEXUS_API_PORT=8000
export NEXUS_MCP_PORT=3001

# Security
export NEXUS_ENABLE_AUTH=true

# Sessions
export NEXUS_REDIS_URL=redis://localhost:6379

# Logging
export NEXUS_LOG_LEVEL=INFO
```

## Configuration Files

Nexus supports YAML configuration files. Load config from file and pass to constructor:

```yaml
# nexus.yaml
server:
  api_port: 8000
  mcp_port: 3001

security:
  auth_enabled: true # Config key varies by SDK
  rate_limit: 1000

monitoring:
  enabled: true

sessions:
  timeout: 3600
  backend: redis

logging:
  level: INFO
  format: json
```

## Production vs Development

| Setting         | Development  | Production                 |
| --------------- | ------------ | -------------------------- |
| Auth            | Disabled     | Enabled (auto or explicit) |
| Rate limiting   | Disabled/low | 100-5000 req/min           |
| Auto-discovery  | Optional     | Disabled                   |
| Session backend | Memory       | Redis                      |
| Log format      | Text         | JSON                       |
| Monitoring      | Optional     | Enabled                    |
| HTTPS           | Optional     | Required                   |

## Security Defaults

Nexus includes production-safe defaults:

- **Environment-aware auth**: auto-enabled when `NEXUS_ENV=production`
- **Rate limiting**: default rate limit for DoS protection
- **Input validation**: dangerous keys blocked, size limits enforced, path traversal prevented across all channels
- **Auto-discovery disabled by default**: prevents blocking with DataFlow

## Best Practices

1. Use environment variables for sensitive config (secrets, URLs)
2. Separate dev/prod configs
3. Enable monitoring in production
4. Disable auto-discovery in production
5. Use Redis for distributed sessions
6. Set appropriate timeouts
7. Enable rate limiting in production
8. Use structured logging (JSON) in production

See language-specific variant for complete constructor parameter reference, default values, and configuration validation examples.

## Related Skills

- [nexus-quickstart](nexus-quickstart.md) - Basic setup
- [nexus-enterprise-features](nexus-enterprise-features.md) - Production features
- [nexus-production-deployment](nexus-production-deployment.md) - Deploy configuration
