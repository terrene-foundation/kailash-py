# MCP Protocol Integration Test Port Conflict Fix

## Summary of Changes

Fixed port conflict issues in MCP protocol integration tests that were causing "address already in use" errors and subsequent WebSocket connection failures.

## Key Changes

### 1. Dynamic Port Allocation
- Added `find_free_port()` utility function to dynamically find available ports
- Each test class/fixture now uses unique port ranges:
  - `TestMCPProtocolIntegration`: Starts from port 8900
  - `TestMCPAuthentication`: Starts from port 9100
  - `TestNexusMCPIntegration`: Starts from port 9300

### 2. Server Startup Retry Logic
- Added retry mechanism with timeout to wait for server startup
- Uses socket connection test to verify server is actually listening
- Prevents race conditions where tests try to connect before server is ready

### 3. WebSocket Connection Retry
- Added exponential backoff retry for WebSocket connections
- Handles transient connection errors during test startup
- Maximum 5 retries with increasing delays

### 4. Improved Cleanup
- Added proper exception handling in teardown methods
- Added delays after `app.stop()` to ensure full shutdown
- Prevents port binding issues from incomplete cleanup

### 5. Dynamic Port References
- Updated all hardcoded port assertions to use dynamic values
- Tests now reference `nexus_app._api_port` and `nexus_app._mcp_port`
- Ensures tests work correctly regardless of assigned ports

## Files Modified

1. `/packages/kailash-nexus/tests/integration/test_enhanced_mcp_protocol.py`
   - Added dynamic port allocation
   - Added server startup retry logic
   - Added WebSocket connection retry
   - Updated port assertions

2. `/packages/kailash-nexus/tests/integration/test_enhanced_mcp_simple.py`
   - Added dynamic port allocation
   - Added server startup retry logic
   - Updated port assertions

## Testing

The changes ensure:
- No port conflicts when running tests in parallel
- Reliable server startup verification
- Graceful handling of transient connection issues
- Proper cleanup between test runs

These fixes should resolve the "OSError: [Errno 48] address already in use" and "ConnectionRefusedError: [Errno 61] Connection refused" errors.
