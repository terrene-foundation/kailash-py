# Nexus Changelog

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
