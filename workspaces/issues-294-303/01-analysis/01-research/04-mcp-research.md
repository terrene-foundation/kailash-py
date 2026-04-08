# Research: MCP (#299, #300)

## Issue #299: Nexus Contributor Gaps

**File**: `src/kailash/mcp/contrib/nexus.py`

### Current Tool Status

| Tool               | Status      | Returns                        | Gap                                       |
| ------------------ | ----------- | ------------------------------ | ----------------------------------------- |
| list_handlers()    | Partial     | name, method, path, file, line | Missing: description, channel, middleware |
| list_channels()    | Stub        | `{"channels": [], "total": 0}` | Hardcoded empty — needs runtime detection |
| list_events()      | **Missing** | N/A                            | Entire tool absent                        |
| scaffold_handler() | Complete    | Code template + test template  | —                                         |
| generate_tests()   | Complete    | Pytest scaffold                | —                                         |

### AST Parser (\_parse_add_handler_call, \_parse_handler_decorator)

Lines 96-199 extract handler registrations via AST. Neither captures docstrings, channel associations, or middleware. Extending the parser is the path for description + channel detection.

### list_events() Design

Should scan for EventBus subscriptions in source code. Return:

```python
{"events": [{"name": str, "handlers_subscribed": [str], "event_type": str}]}
```

---

## Issue #300: Platform Server Integration Tests

### Current State

**Existing tests**: `tests/integration/mcp/test_platform_server_integration.py`

- Tests: server creation, tool discovery, contributor assertions, security tiers, graceful degradation
- **Uses in-process** `create_platform_server()` — not McpClient subprocess

**Platform server**: `src/kailash/mcp/platform_server.py`

- `create_platform_server(project_root, ...)` creates FastMCP server
- Contributors: DataFlow, Nexus, Kaizen, Platform

**McpClient**: `src/kailash/middleware/mcp/client_integration.py`

- `MiddlewareMCPClient` with STDIO and SSE transport support

### What Issue Wants

McpClient-based tests that:

1. Spawn platform server as subprocess
2. Connect via McpClient
3. Test real MCP protocol (tools/list, tool calls)
4. Verify security tier enforcement
5. Test graceful degradation

### Fixture Project

`tests/fixtures/mcp_test_project/` exists with:

- handlers/create_user.py
- Models and agents directories

### Gap Assessment

The in-process tests already cover functional correctness. McpClient tests would add transport-level verification (STDIO protocol, serialization). This is a Tier 2 integration concern.
