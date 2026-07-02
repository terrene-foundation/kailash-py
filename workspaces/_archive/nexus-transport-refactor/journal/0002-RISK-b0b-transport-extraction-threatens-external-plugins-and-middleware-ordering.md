---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T10:04:00+08:00
author: agent
session_id: analyze-phase
session_turn: 1
project: nexus-transport-refactor
topic: B0b transport extraction risks breaking external plugins and middleware ordering
phase: analyze
tags: [b0b, http-transport, plugins, middleware, breaking-change, red-team]
---

# RISK: B0b Transport Extraction Risks Breaking External Plugins and Middleware Ordering

## Risk Statement

The red team identified B0b (HTTPTransport extraction) as MEDIUM-HIGH risk. While B0a (internal refactor) is safe because it preserves the public API, B0b fundamentally changes how FastAPI-specific operations are accessed. Three compounding risks make this the most dangerous part of the refactor.

### Risk 1: External Plugin Breakage (MEDIUM-HIGH)

External plugins loaded by `PluginLoader` may access `self._gateway` directly. The plugin audit found that only 1 of 4 built-in plugins touches `_gateway` (and that access is dead code guarded by `hasattr`). However, **external plugins are opaque** -- they cannot be audited. The planned mitigation is a deprecation warning on `_gateway` access plus a public `app.fastapi_app` property, but some breakage is unavoidable for plugins that directly manipulate the gateway.

The gap analysis notes this as the primary source of uncontrollable risk. No amount of internal testing can catch external plugin failures.

### Risk 2: Middleware Ordering Sensitivity (MEDIUM)

Starlette processes middleware in LIFO order. The current `add_middleware()` delegates directly to `self._gateway.app.add_middleware()`, preserving whatever ordering Starlette enforces. After B0b, middleware goes through HTTPTransport, which must faithfully preserve LIFO ordering. If HTTPTransport batches or reorders middleware (e.g., applying security middleware before user middleware), existing applications that depend on specific ordering will break silently -- middleware ordering bugs are notoriously difficult to diagnose because they manifest as subtle behavioral differences rather than errors.

### Risk 3: Endpoint Decorator Timing (MEDIUM)

The `endpoint()` decorator (lines 824-975, 151 lines) requires the gateway to exist at decoration time. Python decorators execute at class/module load time, which happens during import. If HTTPTransport is not yet created when `@app.endpoint()` is evaluated, the decorator fails. The current queue mechanism (`_middleware_queue`, `_router_queue`) handles this for middleware and routers, but `endpoint()` has its own inline rate limiter that imports `fastapi.Request` directly.

### Compounding Effect

These risks compound because they all manifest at runtime, not at import time or during testing. A test suite that covers all built-in scenarios may pass while an external plugin with custom middleware ordering breaks in production. The test coverage gap identified by the red team (Challenge 5: no integration test for middleware + handler + start()) means regressions in this area would not be caught by the existing test suite.

## Likelihood

- Plugin breakage: MEDIUM (depends on external ecosystem maturity)
- Middleware ordering: LOW-MEDIUM (Starlette's ordering is well-documented, but edge cases exist)
- Endpoint timing: LOW (queue mechanism exists as a pattern to follow)

## Impact

- Plugin breakage: HIGH (external users lose functionality with no clear migration path beyond "update your plugin")
- Middleware ordering: HIGH (silent behavioral changes are worse than errors)
- Endpoint timing: MEDIUM (would manifest as clear ImportError during app construction)

## Mitigation

1. **Before B0a**: Run the full Nexus test suite and record the baseline. After B0a, identical results are required.
2. **During B0b**: Add integration tests that actually start Nexus and make HTTP requests through middleware (addresses red team Challenge 5).
3. **For plugins**: Publish MIGRATION.md during B0a documenting that `_gateway` access will be deprecated. Add `__getattr__` deprecation warning in B0b.
4. **For middleware**: Add explicit middleware ordering test that verifies LIFO behavior is preserved after transport extraction.
5. **For endpoint timing**: Extend the existing queue pattern to `endpoint()` -- queue route definitions until HTTPTransport is ready.

## For Discussion

1. The red team found no integration test that starts Nexus and makes HTTP requests through middleware. If such a test existed today, would it have caught the `broadcast_event()` / `get_events()` conflict with the proposed EventBus earlier -- or are these fundamentally different concerns (HTTP integration vs internal event dispatch)?

2. If Nexus had been designed with a transport abstraction from the start (as kailash-rs's `HandlerRegistry` pattern suggests), would the B0b refactor be unnecessary -- and does the existence of the Rust pattern as prior art reduce the risk by providing a proven design to follow?

3. The plugin audit found that external plugins are "opaque" and cannot be audited. Given that the `PluginLoader` is part of Nexus, could the loader be modified to detect and warn about `_gateway` access patterns before B0b ships -- turning a runtime surprise into a startup warning?
