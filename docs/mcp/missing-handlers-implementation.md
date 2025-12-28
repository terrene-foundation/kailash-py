# MCP Missing Handlers Implementation Guide

## Overview

This guide provides implementation details for the 4 MCP protocol handlers that are defined in the protocol but not exposed in the server:

1. `logging/setLevel` - Dynamic log level adjustment
2. `roots/list` - File system root access listing
3. `completion/complete` - Auto-completion for prompts/resources
4. `sampling/createMessage` - Server-to-client LLM sampling

## Implementation Steps

### 1. Add Handler Methods to MCPServer

Add these methods to the `MCPServer` class in `src/kailash/mcp_server/server.py`:

```python
async def _handle_logging_set_level(self, params: Dict[str, Any], request_id: Any) -> Dict[str, Any]:
    """Handle logging/setLevel request to dynamically adjust log levels."""
    level = params.get("level", "INFO").upper()

    # Validate log level
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if level not in valid_levels:
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32602,
                "message": f"Invalid log level: {level}. Must be one of {valid_levels}"
            },
            "id": request_id
        }

    # Set the log level
    logging.getLogger().setLevel(getattr(logging, level))
    logger.info(f"Log level changed to {level}")

    # Track in event store if available
    if self.event_store:
        await self.event_store.record_event({
            "type": "log_level_changed",
            "level": level,
            "timestamp": time.time(),
            "changed_by": params.get("client_id", "unknown")
        })

    return {
        "jsonrpc": "2.0",
        "result": {
            "level": level,
            "levels": valid_levels
        },
        "id": request_id
    }

async def _handle_roots_list(self, params: Dict[str, Any], request_id: Any) -> Dict[str, Any]:
    """Handle roots/list request to get file system access roots."""
    protocol_mgr = get_protocol_manager()

    # Check if client supports roots
    client_info = self.client_info.get(params.get("client_id", ""))
    if not client_info.get("capabilities", {}).get("roots", {}).get("listChanged", False):
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32601,
                "message": "Client does not support roots capability"
            },
            "id": request_id
        }

    roots = protocol_mgr.roots.list_roots()

    # Apply access control if auth manager is available
    if self.auth_manager and params.get("client_id"):
        filtered_roots = []
        for root in roots:
            if await protocol_mgr.roots.validate_access(
                root["uri"],
                operation="list",
                user_context=self.client_info.get(params["client_id"], {})
            ):
                filtered_roots.append(root)
        roots = filtered_roots

    return {
        "jsonrpc": "2.0",
        "result": {
            "roots": roots
        },
        "id": request_id
    }

async def _handle_completion_complete(self, params: Dict[str, Any], request_id: Any) -> Dict[str, Any]:
    """Handle completion/complete request for auto-completion."""
    protocol_mgr = get_protocol_manager()

    ref = params.get("ref", {})
    argument = params.get("argument", {})

    # Extract completion parameters
    ref_type = ref.get("type")  # "resource", "prompt", "tool"
    ref_name = ref.get("name")  # Optional specific name
    partial_value = argument.get("value", "")

    try:
        completions = await protocol_mgr.completion.get_completions(
            completion_type=ref_type,
            ref_name=ref_name,
            partial=partial_value
        )

        # Format completions based on type
        if ref_type == "resource":
            values = [{"uri": c.get("uri"), "name": c.get("name")} for c in completions]
        elif ref_type == "prompt":
            values = [{"name": c.get("name"), "description": c.get("description")} for c in completions]
        else:
            values = completions

        # Add hasMore flag if there are many completions
        has_more = len(completions) > 100
        if has_more:
            values = values[:100]

        result = {
            "completion": {
                "values": values,
                "total": len(completions)
            }
        }

        if has_more:
            result["completion"]["hasMore"] = True

        return {
            "jsonrpc": "2.0",
            "result": result,
            "id": request_id
        }

    except Exception as e:
        logger.error(f"Completion error: {e}")
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32603,
                "message": f"Completion failed: {str(e)}"
            },
            "id": request_id
        }

async def _handle_sampling_create_message(self, params: Dict[str, Any], request_id: Any) -> Dict[str, Any]:
    """Handle sampling/createMessage - this is typically server-to-client."""
    # This is usually initiated by the server to request LLM sampling from the client
    # For server-side handling, we can validate and forward to connected clients

    protocol_mgr = get_protocol_manager()

    # Check if any client supports sampling
    sampling_clients = [
        client_id for client_id, info in self.client_info.items()
        if info.get("capabilities", {}).get("experimental", {}).get("sampling", False)
    ]

    if not sampling_clients:
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32601,
                "message": "No connected clients support sampling"
            },
            "id": request_id
        }

    # Create sampling request
    messages = params.get("messages", [])
    sampling_params = {
        "messages": messages,
        "model_preferences": params.get("modelPreferences"),
        "system_prompt": params.get("systemPrompt"),
        "temperature": params.get("temperature"),
        "max_tokens": params.get("maxTokens"),
        "metadata": params.get("metadata")
    }

    # Send to first available sampling client (or implement selection logic)
    target_client = sampling_clients[0]

    # Create server-to-client request
    sampling_request = {
        "jsonrpc": "2.0",
        "method": "sampling/createMessage",
        "params": sampling_params,
        "id": f"sampling_{uuid.uuid4().hex[:8]}"
    }

    # Send via WebSocket to client
    if self._transport and hasattr(self._transport, "send_message"):
        await self._transport.send_message(sampling_request, client_id=target_client)

        # Store pending sampling request
        self._pending_sampling_requests[sampling_request["id"]] = {
            "original_request_id": request_id,
            "client_id": params.get("client_id"),
            "timestamp": time.time()
        }

        return {
            "jsonrpc": "2.0",
            "result": {
                "status": "sampling_requested",
                "sampling_id": sampling_request["id"],
                "target_client": target_client
            },
            "id": request_id
        }
    else:
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32603,
                "message": "Transport does not support sampling"
            },
            "id": request_id
        }
```

### 2. Update Message Router

Add handler mappings in the `_handle_websocket_message` method:

```python
elif method == "logging/setLevel":
    return await self._handle_logging_set_level(params, request_id)
elif method == "roots/list":
    return await self._handle_roots_list(params, request_id)
elif method == "completion/complete":
    return await self._handle_completion_complete(params, request_id)
elif method == "sampling/createMessage":
    return await self._handle_sampling_create_message(params, request_id)
```

### 3. Update Capability Advertisement

Modify `_handle_initialize` to include experimental capabilities:

```python
"capabilities": {
    "tools": {"listSupported": True, "callSupported": True},
    "resources": {
        "listSupported": True,
        "readSupported": True,
        "subscribe": self.enable_subscriptions,
        "listChanged": self.enable_subscriptions
    },
    "prompts": {"listSupported": True, "getSupported": True},
    "logging": {"setLevel": True},
    "roots": {"list": True},
    "experimental": {
        "progressNotifications": True,
        "cancellation": True,
        "completion": True,
        "sampling": True
    }
}
```

### 4. Initialize Protocol Components

Ensure the server initializes required protocol managers:

```python
def __init__(self, ...):
    # ... existing init code ...

    # Initialize protocol manager components
    protocol_mgr = get_protocol_manager()

    # Set up default roots if needed
    if not protocol_mgr.roots.list_roots():
        protocol_mgr.roots.add_root(
            uri="file:///",
            name="Root",
            description="File system root"
        )

    # Register completion providers
    protocol_mgr.completion.register_completion_provider(
        "resource",
        self._get_resource_completions
    )
    protocol_mgr.completion.register_completion_provider(
        "prompt",
        self._get_prompt_completions
    )

    # Initialize pending sampling requests tracker
    self._pending_sampling_requests = {}
```

### 5. Add Completion Provider Methods

```python
async def _get_resource_completions(self, ref_name: Optional[str], partial: str) -> List[Dict[str, Any]]:
    """Get resource completions."""
    completions = []
    for uri, info in self._resource_registry.items():
        if partial and not uri.startswith(partial):
            continue
        completions.append({
            "uri": uri,
            "name": info.get("name", uri),
            "description": info.get("description", "")
        })
    return completions

async def _get_prompt_completions(self, ref_name: Optional[str], partial: str) -> List[Dict[str, Any]]:
    """Get prompt completions."""
    completions = []
    for name, info in self._prompt_registry.items():
        if partial and not name.startswith(partial):
            continue
        completions.append({
            "name": name,
            "description": info.get("description", ""),
            "arguments": info.get("arguments", [])
        })
    return completions
```

## Testing the Implementation

### 1. Test Logging Level Change

```python
# Test request
{
    "jsonrpc": "2.0",
    "method": "logging/setLevel",
    "params": {"level": "DEBUG"},
    "id": 1
}

# Expected response
{
    "jsonrpc": "2.0",
    "result": {
        "level": "DEBUG",
        "levels": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    },
    "id": 1
}
```

### 2. Test Roots Listing

```python
# Test request
{
    "jsonrpc": "2.0",
    "method": "roots/list",
    "params": {},
    "id": 2
}

# Expected response
{
    "jsonrpc": "2.0",
    "result": {
        "roots": [
            {
                "uri": "file:///",
                "name": "Root",
                "description": "File system root"
            }
        ]
    },
    "id": 2
}
```

### 3. Test Completion

```python
# Test request
{
    "jsonrpc": "2.0",
    "method": "completion/complete",
    "params": {
        "ref": {"type": "resource"},
        "argument": {"value": "file://"}
    },
    "id": 3
}

# Expected response
{
    "jsonrpc": "2.0",
    "result": {
        "completion": {
            "values": [
                {"uri": "file:///workspace", "name": "Workspace"},
                {"uri": "file:///documents", "name": "Documents"}
            ],
            "total": 2
        }
    },
    "id": 3
}
```

## Security Considerations

1. **Logging Level**: Restrict DEBUG level in production to prevent sensitive data exposure
2. **Roots Access**: Always validate access permissions before exposing file system roots
3. **Completion Data**: Filter completions based on user permissions
4. **Sampling**: Validate client capabilities before forwarding sampling requests

## Integration with Existing Features

The missing handlers integrate seamlessly with existing Kailash features:

- **EventStore**: All operations can be logged for audit trails
- **AuthManager**: Access control applied to all operations
- **Rate Limiting**: Can be applied to prevent abuse
- **Monitoring**: Metrics can track usage patterns

## Next Steps

1. Implement the handlers in `server.py`
2. Add comprehensive unit tests
3. Update integration tests
4. Document in API reference
5. Add examples to the documentation

This implementation will bring the Kailash MCP server to 100% protocol compliance while maintaining its enterprise-grade security and observability features.
