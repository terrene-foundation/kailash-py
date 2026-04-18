# Nexus Changelog

## [Unreleased]

### Fixed

- **Custom FastAPI lifespan silently ignored `app.router.on_startup` / `app.router.on_shutdown` handlers** (#500): `WorkflowServer.__init__` passed a custom `lifespan` to `FastAPI()`, which replaces (not wraps) Starlette's default `_DefaultLifespan` — the only code path that iterated the router-level hooks. Any user registering a handler via the documented FastAPI pattern `app.fastapi_app.router.on_startup.append(fn)` saw `fn` silently dropped. Fix: the lifespan now explicitly invokes `await app.router._startup()` on entry and `await app.router._shutdown()` on exit.
- **Plugin `on_startup` async hooks cancelled scheduled background tasks** (#501): `Nexus.start()` called `_call_startup_hooks()` BEFORE uvicorn booted. For async hooks, the sync path used `asyncio.run(hook())` which created a throwaway event loop, ran the hook (commonly scheduling `asyncio.create_task(periodic_job())`), then CLOSED the loop — cancelling every task the hook had just created. Uvicorn then booted its own loop and the tasks were gone. Fix: plugin startup hooks now run via `_call_startup_hooks_async` inside the FastAPI lifespan context manager, which executes on uvicorn's own event loop. Tasks scheduled by a plugin hook therefore survive for the server's lifetime. The pre-uvicorn invocation in `Nexus.start()` was removed; shutdown hooks are now called inside the lifespan via `_call_shutdown_hooks_async` (with an idempotency flag so the sync `stop()` path doesn't double-fire).
- **Partial-startup crash leaked `ShutdownCoordinator`-registered resources** (#500/#501 round-2 sec H1): the lifespan's `try:` only wrapped `yield`, so an exception from `router.startup()` or `startup_hook()` skipped the `finally:` block. The `ThreadPoolExecutor` registered at `WorkflowServer.__init__` never shut down, and any Nexus plugin whose earlier `on_startup` had run saw its paired `on_shutdown` silently skipped. Fix: the `try:` now wraps every startup step, so the shutdown branch runs on every path — graceful exit, startup exception, or timeout. Each teardown step (`shutdown_hook` / `router.shutdown` / `ShutdownCoordinator.shutdown`) is wrapped in its own `try/except` so one failing cleanup cannot block the next.
- **`_shutdown_hooks_fired` TOCTOU between sync `stop()` and async lifespan path** (#500/#501 round-2 sec H2): the idempotency flag was checked and set without a lock. When a signal handler invoked `Nexus.stop()` while uvicorn's lifespan was concurrently running the async shutdown path, both paths could read `False`, both could set `True`, and both could iterate the hook list — firing every `on_shutdown` twice (counter-increment plugins corrupt; token-revocation plugins panic). Fix: added `_shutdown_hooks_fired_lock` (`threading.Lock`) protecting the check-and-set across both paths. CPython's GIL makes the individual load and store atomic; the lock makes the compound check-then-set atomic, which is what the idempotency contract requires.
- **Pre-existing `asyncio.iscoroutinefunction` deprecation sites in `nexus/core.py` L209 (`_wrap_with_guard`) and L1611 (`use_middleware`)** (#500/#501 round-2 MED-2 / zero-tolerance Rule 1): Python 3.14 deprecated the `asyncio` form in favor of `inspect.iscoroutinefunction`. Round-1 swapped the four hook drivers; round-2 swapped the two remaining sites so no deprecation fires from any Nexus code path.

### Added

- `startup_hook` / `shutdown_hook` kwargs on `WorkflowServer.__init__` and `create_gateway()` so upstream wrappers (Nexus) can route lifecycle hooks through the FastAPI lifespan without re-implementing it.
- `startup_hook_timeout` kwarg on `WorkflowServer.__init__` and `create_gateway()` (default `None` = unbounded, matching historical behavior). When set to a finite value, the lifespan wraps `startup_hook()` in `asyncio.wait_for` so a hung plugin `on_startup` cannot pin uvicorn forever and prevent it from accepting connections. On timeout the shutdown branch still runs so partial startup state is torn down. Addresses the DoS vector described in round-2 sec M2.
- `Nexus._call_startup_hooks_async` / `Nexus._call_shutdown_hooks_async`: awaitable hook drivers invoked from the lifespan. Errors logged via `logger.exception` (preserves traceback, zero-tolerance Rule 3); failures in one hook do not prevent later hooks, `router._shutdown`, or the `ShutdownCoordinator` from running.
- Regression tests `tests/regression/test_issue_500_router_on_startup.py` + `tests/regression/test_issue_501_hook_task_lifetime.py` (minimal reproductions, `@pytest.mark.regression`, never deleted).
- Tier 2 wiring tests `tests/integration/nexus/test_router_on_startup_fires.py`, `test_plugin_on_startup_task_survives.py`, `test_shutdown_symmetric.py`, `test_shutdown_idempotency.py` (2 tests covering both path orderings), `test_partial_startup_teardown.py` (crashed-startup teardown), `test_startup_hook_timeout.py` (2 tests covering bounded + unbounded modes) — real uvicorn boot, real FastAPI lifespan, real asyncio tasks; no mocks.

### Changed

- Lifespan log lines now use structured-kwargs form per `observability.md` MUST Rule 3 (`logger.info("workflow_server.lifespan.startup", extra={"title": title, "version": version})` instead of f-strings). Each startup/shutdown step emits a dedicated event name (`startup`, `shutdown`, `shutdown_hook_failed`, `router_shutdown_failed`, `coordinator_shutdown_failed`, `shutdown_complete`, `startup_hook.timeout`) for grep-able operational tracing.

## [1.7.2] - 2026-04-03

### Fixed

- **Nexus auth security hardening** (#226): API key auth validation, token age checking, stale session detection hook
- Auth JWT module refactored for security (constant-time comparison, bounded token cache)

## [1.7.1] - 2026-04-01

### Fixed

- **Connection stampede on Docker Desktop** (#211, #212): Nexus enterprise gateway created a duplicate `AsyncLocalRuntime` independently from Nexus's own runtime, doubling the connection pool footprint. Gateway now shares Nexus's runtime via `runtime=` injection.
- **Hardcoded `server_type="enterprise"` and `max_workers=20`**: Both are now configurable via constructor params (`server_type`, `max_workers`) and env vars (`NEXUS_SERVER_TYPE`, `NEXUS_MAX_WORKERS`). Default auto-detects `min(4, cpu_count)`.
- **Input validation**: `server_type` validates against `{"enterprise", "durable", "basic"}` at construction. `max_workers` rejects `< 1` and non-numeric env var values.
- **MCP transport orphan runtime**: `MCPTransport` now accepts an optional `runtime` parameter to share the parent's pool instead of creating its own.
- **Pre-existing test failures**: 2 tests that required `enable_http_transport=True` for MCP server initialization now pass.

### Added

- 8 regression tests in `tests/regression/test_issue_211.py` covering dual runtime elimination, configurable gateway, and env var overrides.

## [1.7.0] - 2026-04-01

### Added

- **Transport ABC**: Abstract base class for pluggable transport implementations. Clean separation of protocol handling from business logic.
- **HTTPTransport**: Production HTTP transport replacing the monolithic gateway. Supports middleware, CORS, and streaming.
- **MCPTransport**: Dedicated MCP transport with proper protocol handling, resource management, and tool dispatch.
- **HandlerRegistry**: Centralized handler registration and dispatch. Type-safe handler resolution with middleware support.
- **EventBus**: Internal event system for cross-component communication. Publish/subscribe with typed events.
- **BackgroundService**: Managed background task lifecycle with graceful shutdown, health monitoring, and restart policies.
- **Phase 2 APIs**: File serving, bridge patterns, and extended handler capabilities.

### Changed

- Transport layer refactored from monolithic gateway to pluggable architecture. Existing APIs remain backward-compatible.

### Test Results

- 1,153 tests passed, 0 failures

## [1.6.1] - 2026-03-31

### Fixed

- `__del__` finalizer safety for 3 Nexus classes.

## [1.4.1] - 2026-02-22

### V4 Audit Hardening Patch

Post-release reliability hardening from V4 final audit.

### Fixed

- **Stale Transport Test**: Updated `test_receive_message_not_implemented` to test actual queue-based message receiving behavior instead of expecting `NotImplementedError` from implemented method

### Test Results

- Nexus: 1,027 passed

## [1.4.0] - 2026-02-21

### Quality Milestone Release - V4 Audit Cleared

This release completes 4 rounds of production quality audits (V1-V4) with all Nexus-specific gaps remediated.

### Changed

- **Transport Error Sanitization**: WebSocket error messages now return only `type(e).__name__` instead of raw `str(e)` to prevent internal detail leakage
- **JSON Error Messages**: Invalid JSON errors now return generic message instead of parse details

### Security

- Error messages sanitized before sending to WebSocket clients
- Max message size limits enforced on transport
- V4 audit: 0 CRITICAL, 0 HIGH findings

### Test Results

- 638 unit tests passed (+1 pre-existing)

## [1.1.1] - 2025-10-24

### Release Quality

Production-ready release with comprehensive stub implementation fixes and documentation updates.

#### Key Improvements

- All 10 stub implementations replaced with production-quality code
- Zero silent success cases remaining
- Zero breaking changes - fully backward compatible
- 385/411 tests passing (93.7%), 100% stub-related tests passing
- Enterprise production quality maintained

See v1.1.0 changelog entry below for detailed fixes.

## [1.1.0] - 2025-10-24

### CRITICAL: Stub Implementation Fixes

All 10 stub implementations have been fixed with production-ready solutions:

#### CRITICAL Fixes (Silent Success Issues)

1. **Channel Initialization - REMOVED** (was returning success without initialization)
   - Deleted redundant `ChannelManager.initialize_channels()` method
   - Channels now initialized correctly via `Nexus._initialize_gateway()` and `Nexus._initialize_mcp_server()`
   - Added architecture comments explaining ownership

2. **Workflow Registration - REMOVED** (was logging success without registration)
   - Deleted redundant `ChannelManager.register_workflow_on_channels()` method
   - Multi-channel registration handled properly by `Nexus.register()`
   - Single source of truth for workflow registration

3. **Event Broadcasting - UPDATED** (claimed to broadcast but didn't)
   - Updated `Nexus.broadcast_event()` with honest implementation
   - v1.0: Events logged to `_event_log` (retrieve with `get_events()`)
   - v1.1 (planned): Real-time WebSocket/SSE broadcasting
   - Changed logging from INFO to DEBUG with clear capability documentation

#### HIGH Priority Fixes

4. **Resource Configuration** - Fixed AttributeError
   - Changed `self.nexus.enable_auth` → `self.nexus._enable_auth`
   - MCP `config://platform` resource now works correctly

5. **Event Stream Initialization** - Honest Logging
   - Removed fake "✅ initialized" messages
   - Changed logging level from INFO to DEBUG
   - Added clear v1.1 deferral documentation

6. **Workflow Schema Extraction** - Metadata-based
   - Implemented metadata-based schema extraction
   - Returns empty dict when metadata not provided
   - v1.1 (planned): Automatic schema inference from nodes

7. **Plugin Error Handling** - Specific Exceptions
   - Replaced bare `except:` with specific exception handling
   - TypeError logged as warning (constructor args required)
   - Other exceptions logged as errors with full context

#### MEDIUM Priority Fixes

8. **Discovery Error Handling** - Improved Logging
   - Added debug-level logging for discovery failures
   - Differentiates "not a workflow" from "error calling function"

9. **Plugin Validation** - Basic Validation
   - Validates plugin has `name` and `apply` method
   - Returns False for invalid plugins

10. **Shutdown Cleanup** - Error Logging
    - Added error logging during shutdown
    - Graceful handling of cleanup failures

### Documentation Updates

- All methods now have honest docstrings reflecting v1.0 vs v1.1 capabilities
- Architecture comments explain initialization and registration ownership
- Clear roadmap for v1.1 features (WebSocket broadcasting, auto schema inference)

### Test Updates

- 248/248 unit tests passing
- Updated tests to verify actual architecture (not stubs)
- Tests now check real initialization, not just return values

### Breaking Changes

**None** - All fixes are internal improvements with no API changes

### Migration Guide

No migration needed - existing code continues to work unchanged

### Known Limitations (v1.0)

- Event broadcasting only logs events (no real-time broadcast)
- Workflow schema extraction requires explicit metadata
- Events retrievable via `get_events()` helper method

### Planned for v1.1

- Real-time event broadcasting via WebSocket/SSE
- Automatic workflow schema inference
- Enhanced MCP resource capabilities

## [1.0.8] - 2025-10-09

### CRITICAL HOTFIX

- Fixed server startup failure where daemon threads were killed on process exit
- `start()` method now blocks until Ctrl+C (like FastAPI/Flask behavior)
- API server now starts correctly and accepts requests

### Fixed

- Server never starting due to daemon thread + immediate return pattern
- Version string mismatch (`__version__` now correctly set to package version)
- Process exiting immediately after `start()` call
- Port never binding because daemon thread died before uvicorn started

### Changed

- **BREAKING**: `start()` method now blocks until stopped (Ctrl+C or `.stop()`)
- For background execution, run in a thread: `Thread(target=app.start).start()`
- Gateway runs in main thread instead of daemon thread
- Updated docstring to document blocking behavior

### Migration Guide

**BEFORE (v1.0.7 - BROKEN)**:

```python
from nexus import Nexus

app = Nexus()
app.register("my_workflow", workflow.build())
app.start()  # Returned immediately, server never started
# Process exited here - daemon threads were killed
# Result: Connection refused on all requests
```

**AFTER (v1.0.8 - FIXED)**:

```python
# Option 1: Production usage (recommended)
from nexus import Nexus

app = Nexus()
app.register("my_workflow", workflow.build())
app.start()  # Now blocks until Ctrl+C - server stays running!
# Server runs here, handling requests until you press Ctrl+C
```

```python
# Option 2: Background/testing (if needed)
import threading
import time
from nexus import Nexus

app = Nexus()
app.register("my_workflow", workflow.build())

# Run in background thread
thread = threading.Thread(target=app.start, daemon=True)
thread.start()
time.sleep(2)  # Wait for startup

# ... your test code here ...

app.stop()  # Clean shutdown when done
```

**Rollback if needed**:

```bash
# If v1.0.8 causes issues (unlikely)
pip install kailash-nexus==1.0.6  # Last working version before v1.0.7
```

**Key Changes**:

- `start()` now blocks (like FastAPI's `uvicorn.run()`)
- Server stays running until explicit stop (Ctrl+C or `app.stop()`)
- No more daemon thread bug - main thread runs the gateway
- Works correctly on all platforms (Unix, Windows, macOS)

### Technical Details

- Removed `_server_thread` daemon thread for gateway
- Gateway now runs via direct `gateway.run()` call in main thread
- MCP server still runs in background daemon thread (non-critical path)
- Improved error handling with automatic `stop()` on exceptions
- Added graceful KeyboardInterrupt (Ctrl+C) handling
- Added "Press Ctrl+C to stop" message to startup logs

### Testing

- Added 4 new integration tests for real-world startup scenarios
- All tests verify server actually starts and stays running
- Tests confirm port binding and request handling work correctly
- All existing E2E tests pass with no modifications needed

## [1.0.7] - 2025-10-08

### Added

- FastAPI mount behavior documentation
- Enhanced logging with full endpoint URLs
- Custom 404 error handler with helpful guidance
- Better startup logging showing all available endpoints

### Known Issues

- **CRITICAL BUG**: Server never starts due to daemon thread issue
- Process exits immediately after `start()` call
- Port never binds, all requests get "Connection refused"
- This version is non-functional in production
- **Fixed in v1.0.8**

## [1.0.3] - 2025-07-22

### Added

- Comprehensive documentation validation and testing infrastructure
- WebSocket transport implementation for MCP protocol integration
- Full test coverage validation (77% overall coverage achieved)
- Real infrastructure testing for all code examples

### Fixed

- CLAUDE.md documentation examples now work correctly (100% validation rate)
- Corrected `list_workflows()` references to use `app._workflows`
- Fixed `start()` method documentation (corrected async/sync specification)
- All constructor options and enterprise configuration patterns validated

### Improved

- Test quality with non-trivial infrastructure requirements
- Edge case coverage and error scenario validation
- WebSocket client management and concurrent connection handling
- MCP protocol message processing and response handling

### Technical

- 248 unit tests passing with robust timeout enforcement
- Comprehensive WebSocket transport validation
- Real Nexus instance testing without mocking
- Complete API correctness verification

## [1.0.2] - 2025-07-20

### Fixed

- Version mismatch between setup.py/pyproject.toml (1.0.1) and **init**.py (1.0.0)
- Updated CLI module imports in integration tests from `kailash.nexus.cli` to `nexus.cli`

### Changed

- Updated Kailash SDK dependency to >= 0.8.5 to ensure compatibility with removal of `src/kailash/nexus`
- All versions now synchronized at 1.0.2

### Notes

- No breaking changes for Nexus users
- The removal of `src/kailash/nexus` from core SDK does not affect the Nexus app framework
- Users should continue to use `from nexus import Nexus` as documented

## [1.0.1] - Previous Release

### Added

- Zero-configuration multi-channel orchestration
- Unified API, CLI, and MCP interfaces
- Cross-channel session management
- Enterprise features (auth, monitoring)

## [1.0.0] - Initial Release

- First stable release of Nexus framework
- Complete multi-channel platform
- Production-ready with enterprise features
