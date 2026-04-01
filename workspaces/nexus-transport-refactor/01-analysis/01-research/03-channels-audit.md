# Channels, Engine, and Middleware Audit

## channels.py (392 lines)

**FastAPI coupling**: NONE. This module is pure configuration and session management.

### Contents

- `ChannelConfig` dataclass — port, host, additional_config
- `ChannelManager` — manages API/CLI/MCP channel configs, defaults
- `SessionManager` — cross-channel session sync (in-memory dict)
- Utility: `find_available_port()`, `is_port_available()`
- Global singletons: `get_channel_manager()`, `create_session_manager()`

### Assessment for Refactor

- **No changes needed in B0a or B0b** — already decoupled
- The `ChannelManager` is essentially unused by `core.py` — Nexus manages its own config
- `SessionManager` is a minimal in-memory implementation, used only by `Nexus.create_session()` and `sync_session()`
- Could be enhanced post-refactor to support transport-aware session management

## engine.py (220 lines)

**FastAPI coupling**: NONE. This is a builder-pattern wrapper around `Nexus`.

### Contents

- `Preset` enum — `NONE`, `SAAS`, `ENTERPRISE`
- `EnterpriseMiddlewareConfig` dataclass — frozen, configures enterprise features
- `NexusEngineBuilder` — fluent builder API matching kailash-rs `NexusEngineBuilder`
- `NexusEngine` — wraps `Nexus` with enterprise middleware config

### Assessment for Refactor

- **B0a**: No changes needed
- **B0b**: `NexusEngineBuilder.build()` creates `Nexus(**nexus_kwargs)` and passes preset config. After B0b, `NexusEngine` could gain a `.add_transport()` method, but this is NOT required for backward compatibility
- `NexusEngine.start()` delegates to `Nexus.start()` — transport-aware startup flows through

## middleware/ (2 files)

### csrf.py (167 lines)

- `CSRFMiddleware` extends Starlette `BaseHTTPMiddleware`
- HTTP-specific by design (CSRF tokens in cookies, form submissions)
- **Stays with HTTPTransport scope after B0b**

### security_headers.py (152 lines)

- `SecurityHeadersMiddleware` extends Starlette `BaseHTTPMiddleware`
- Adds standard HTTP security headers (CSP, X-Frame-Options, etc.)
- **Stays with HTTPTransport scope after B0b**

### middleware/**init**.py (16 lines)

- Exports `CSRFMiddleware`, `SecurityHeadersMiddleware`
- No coupling concerns

## What's Already Decoupled (Brief Verification)

| Component                                         | Brief Claim | Verified                             |
| ------------------------------------------------- | ----------- | ------------------------------------ |
| `channels.py` — no framework imports              | YES         | YES — no FastAPI/Starlette imports   |
| `engine.py` — wrapper, no direct FastAPI imports  | YES         | YES — only imports from `nexus.core` |
| `cli/main.py` — standalone HTTP client            | YES         | YES — uses `requests` library only   |
| `mcp/server.py` — independent WebSocket transport | YES         | YES — uses raw `websockets`          |
| `mcp/transport.py` — independent                  | YES         | YES — uses raw `websockets`          |

## Summary

The brief's "already decoupled" claims are all accurate. The middleware directory contains HTTP-specific middleware that correctly stays within HTTPTransport scope. The channels.py and engine.py modules need no changes for B0a and minimal changes for B0b.
