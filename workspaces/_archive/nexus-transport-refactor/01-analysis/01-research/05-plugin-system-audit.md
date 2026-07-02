# Plugin System Audit

## Goal: Identify all plugins that access `_gateway` directly

This is critical for B0a migration — plugins that access `_gateway.app` directly will break when the FastAPI app is wrapped by `HTTPTransport` in B0b.

## Plugin Architecture

### Plugin Protocol (core.py, lines 77-101)

```python
@runtime_checkable
class NexusPluginProtocol(Protocol):
    @property
    def name(self) -> str: ...
    def install(self, app: "Nexus") -> None: ...
```

Plugins receive the `Nexus` instance via `install(app)`. They can call any public method on `app`. The concern is plugins that access `app._gateway` (private attribute).

### Two Plugin Systems

1. **NexusPluginProtocol** (core.py) — used by `app.add_plugin()`. Plugins install via `install(app: Nexus)`.
2. **NexusPlugin ABC** (plugins.py) — used by `app.use_plugin()`. Plugins apply via `apply(nexus_instance)`.

Both systems pass the `Nexus` instance to the plugin.

## Gateway Access Analysis

### plugins.py — Built-in Plugins

**AuthPlugin (lines 75-112)**:

```python
def apply(self, nexus_instance: Any) -> None:
    if hasattr(nexus_instance, "_gateway") and nexus_instance._gateway:
        # Accesses nexus_instance._gateway.set_auth_manager()
        if hasattr(nexus_instance._gateway, "set_auth_manager"):
            nexus_instance._gateway.set_auth_manager(auth_manager)
```

**VERDICT: ACCESSES `_gateway` DIRECTLY** -- but only calls `set_auth_manager()` which does not exist on gateway (uses `hasattr` guard). Falls back to setting `_auth_enabled = True`.

**MonitoringPlugin (lines 115-135)**: Sets `_monitoring_enabled = True` on the Nexus instance. Does NOT access `_gateway`.

**RateLimitPlugin (lines 138-160)**: Sets `_rate_limit` on the Nexus instance. Does NOT access `_gateway`.

### auth/plugin.py — NexusAuthPlugin

**NexusAuthPlugin (lines 22-179)**:

```python
def install(self, app: Any) -> None:
    # All middleware installed via app.add_middleware()
    app.add_middleware(RBACMiddleware, ...)
    app.add_middleware(TenantMiddleware, ...)
    app.add_middleware(JWTMiddleware, ...)
    app.add_middleware(RateLimitMiddleware, ...)
    app.add_middleware(AuditMiddleware, ...)
```

**VERDICT: CLEAN** — uses only `app.add_middleware()`, never accesses `_gateway` directly.

### Preset System (presets.py)

Presets call `apply_preset(app, preset_name, config)` which internally uses `app.add_middleware()`, `app.add_plugin()`, and sets config attributes. Let me verify.

The `apply_preset()` function delegates to preset factories that use `app.add_middleware()` and `app.add_plugin()`. No direct `_gateway` access found in the preset system.

## Summary: Plugin Gateway Access

| Plugin                             | Accesses `_gateway`?                                | Severity                                         | Action                                               |
| ---------------------------------- | --------------------------------------------------- | ------------------------------------------------ | ---------------------------------------------------- |
| `AuthPlugin` (plugins.py)          | YES — `_gateway.set_auth_manager()`                 | LOW (guarded by `hasattr`, method doesn't exist) | Document in MIGRATION.md; deprecation warning in B0b |
| `MonitoringPlugin`                 | No                                                  | None                                             | No action                                            |
| `RateLimitPlugin`                  | No                                                  | None                                             | No action                                            |
| `NexusAuthPlugin` (auth/plugin.py) | No — uses `app.add_middleware()`                    | None                                             | No action                                            |
| Preset factories                   | No — use `app.add_middleware()`, `app.add_plugin()` | None                                             | No action                                            |

## External Plugin Risk

The `PluginLoader` (plugins.py, lines 226-301) loads external plugins from filesystem (`nexus_plugins/*.py`, `plugins/*.py`, `*_plugin.py`). These external plugins could access `_gateway` directly — we cannot audit them.

**Mitigation for B0b**:

1. Add `__getattr__` trap on `_gateway` that logs deprecation warning
2. Expose `app.fastapi_app` property as the public alternative
3. Document in MIGRATION.md

## Plugin Lifecycle Integration for B0a

The plugin lifecycle hooks (`on_startup`, `on_shutdown`) are called in `Nexus.start()` and `Nexus.stop()`. These hooks are Nexus-level, not transport-level. No changes needed for B0a.

However, `BackgroundService` lifecycle (start/stop/is_healthy) should be integrated alongside plugin lifecycle. B0a should ensure:

- `Nexus.start()` calls both plugin startup hooks AND background service `start()`
- `Nexus.stop()` calls both plugin shutdown hooks AND background service `stop()`

This is additive — no existing behavior changes.
