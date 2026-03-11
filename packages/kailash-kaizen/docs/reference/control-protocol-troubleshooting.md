# Control Protocol Troubleshooting

Common issues and solutions when using the Control Protocol for bidirectional agent communication.

**Version:** Kaizen v0.3.0+

---

## Table of Contents

1. [Configuration Errors](#configuration-errors)
2. [Timeout Issues](#timeout-issues)
3. [Transport Errors](#transport-errors)
4. [Protocol Lifecycle Issues](#protocol-lifecycle-issues)
5. [Message Handling](#message-handling)
6. [Performance Issues](#performance-issues)
7. [Integration Issues](#integration-issues)

---

## Configuration Errors

### Error: "Control protocol not configured"

**Symptom:**
```python
RuntimeError: Control protocol not configured.
Pass control_protocol parameter to BaseAgent.__init__()
```

**Cause:** Agent created without `control_protocol` parameter.

**Solution:**

```python
# L WRONG - Missing control_protocol
agent = BaseAgent(config=config, signature=signature)

#  CORRECT - Include control_protocol
protocol = ControlProtocol(transport)
agent = BaseAgent(
    config=config,
    signature=signature,
    control_protocol=protocol  # Add this!
)
```

**Prevention:** Always pass `control_protocol` when creating agents that need interactive capabilities.

---

### Error: "transport must be a Transport instance"

**Symptom:**
```python
TypeError: transport must be a Transport instance, got NoneType.
Provide a valid Transport implementation (CLITransport, HTTPTransport, etc.)
```

**Cause:** Passed `None` or invalid object to ControlProtocol constructor.

**Solution:**

```python
# L WRONG - No transport
protocol = ControlProtocol(None)

#  CORRECT - Valid transport
from kaizen.core.autonomy.control.transports import CLITransport

transport = CLITransport()
await transport.connect()
protocol = ControlProtocol(transport)
```

---

## Timeout Issues

### Error: Request Times Out

**Symptom:**
```python
TimeoutError: No response received for request 'req_abc123' within 60 seconds.
Check that client is responding to requests.
```

**Cause:** User/client not responding within timeout period.

**Solution 1: Increase Timeout**

```python
# Default timeout is 60 seconds
response = await protocol.send_request(request, timeout=60.0)

# Increase for slow responses
response = await protocol.send_request(request, timeout=120.0)
```

**Solution 2: Handle Timeouts Gracefully**

```python
try:
    answer = await agent.ask_user_question(
        "Continue?",
        timeout=30.0
    )
except TimeoutError:
    # Use default value
    answer = "cancel"
    logger.warning("User didn't respond, using default")
```

**Solution 3: Add Default Values**

```python
# Best practice: Always provide sensible defaults
try:
    answer = await agent.ask_user_question(
        "Choose approach?",
        options=["fast", "thorough"],
        timeout=30.0
    )
except TimeoutError:
    answer = "fast"  # Safe default
```

---

### Error: Methods Return Immediately

**Symptom:** `ask_user_question()` or `request_approval()` return immediately without waiting for user.

**Cause:** Protocol not started in task group.

**Solution:**

```python
# L WRONG - Protocol not started
protocol = ControlProtocol(transport)
answer = await agent.ask_user_question("Continue?")  # Returns immediately!

#  CORRECT - Start protocol in task group
import anyio

async with anyio.create_task_group() as tg:
    await protocol.start(tg)  # Start background reader

    answer = await agent.ask_user_question("Continue?")  # Now waits properly

    await protocol.stop()
```

**Why:** The background message reader needs to run in a task group to pair responses with requests.

---

## Transport Errors

### Error: "Transport not ready"

**Symptom:**
```python
RuntimeError: Cannot write to transport: not connected.
Call connect() first.
```

**Cause:** Forgot to call `transport.connect()`.

**Solution:**

```python
# L WRONG - No connect
transport = CLITransport()
protocol = ControlProtocol(transport)

#  CORRECT - Call connect
transport = CLITransport()
await transport.connect()  # Don't forget!
protocol = ControlProtocol(transport)
```

---

### Error: "Connection closed" or "Broken pipe"

**Symptom:**
```
ConnectionError: Failed to write to transport: Connection closed
BrokenPipeError: [Errno 32] Broken pipe
```

**Cause:** Transport connection lost (network issue, client disconnected, etc.).

**Solution 1: Reconnect**

```python
try:
    await transport.write(message)
except ConnectionError:
    logger.warning("Connection lost, reconnecting...")
    await transport.close()
    await transport.connect()
    await transport.write(message)
```

**Solution 2: Graceful Degradation**

```python
async def send_with_fallback(protocol, request):
    try:
        return await protocol.send_request(request, timeout=30.0)
    except ConnectionError:
        logger.error("Connection lost, using default")
        return ControlResponse(
            request_id=request.request_id,
            data={"answer": "default"}
        )
```

---

### Error: HTTPTransport SSE Connection Issues

**Symptom:**
```
ConnectionError: HTTP error 404: Not Found
```

**Cause:** Incorrect base_url or SSE endpoint not available.

**Solution:**

```python
# L WRONG - Wrong URL
transport = HTTPTransport(base_url="http://localhost:8000/wrong")

#  CORRECT - Correct base URL
transport = HTTPTransport(base_url="http://localhost:8000")
# Expects endpoints:
#   POST http://localhost:8000/control
#   GET  http://localhost:8000/stream
```

**Verification:**

```bash
# Check server is running
curl http://localhost:8000/stream  # Should return SSE stream
```

---

## Protocol Lifecycle Issues

### Error: "Protocol already started"

**Symptom:**
```python
RuntimeError: Protocol already started. Call stop() before starting again.
```

**Cause:** Called `protocol.start()` twice without `stop()`.

**Solution:**

```python
# L WRONG - Multiple starts
await protocol.start(tg)
await protocol.start(tg)  # Error!

#  CORRECT - Stop before restarting
await protocol.start(tg)
# ... use protocol ...
await protocol.stop()
await protocol.start(tg)  # OK now
```

---

### Error: "Protocol not started"

**Symptom:**
```python
RuntimeError: Protocol not started. Call start() before sending requests.
```

**Cause:** Trying to send requests before calling `start()`.

**Solution:**

```python
# L WRONG - Send before start
protocol = ControlProtocol(transport)
request = ControlRequest.create("question", {"q": "Test?"})
response = await protocol.send_request(request)  # Error!

#  CORRECT - Start first
protocol = ControlProtocol(transport)

async with anyio.create_task_group() as tg:
    await protocol.start(tg)  # Start first!

    request = ControlRequest.create("question", {"q": "Test?"})
    response = await protocol.send_request(request)  # OK

    await protocol.stop()
```

---

### Error: Background Reader Crashes

**Symptom:**
```
ERROR: Background message reader error: <exception>
Background message reader exited
```

**Cause:** Malformed messages, transport errors, or protocol bugs.

**Solution 1: Check Logs**

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("kaizen.core.autonomy.control")
```

**Solution 2: Validate Messages**

```python
# Ensure messages are valid JSON
import json

message = '{"request_id": "req_123", "data": {"answer": "yes"}}'
try:
    json.loads(message)  # Validate before sending
except json.JSONDecodeError as e:
    logger.error(f"Invalid message: {e}")
```

---

## Message Handling

### Error: "Received unsolicited response"

**Symptom:**
```
WARNING: Received unsolicited response for request_id: req_xyz.
No pending request found.
```

**Cause:** Response received for request that wasn't sent or already completed.

**Solution:** This is usually harmless (duplicate response or late response). If persistent:

```python
# Ensure you're not sending duplicate responses
async def send_response_once(request_id, data):
    if request_id in sent_responses:
        return  # Already sent
    sent_responses.add(request_id)

    response = ControlResponse(request_id=request_id, data=data)
    await transport.write(response.to_json())
```

---

### Error: "Received malformed response"

**Symptom:**
```
WARNING: Received malformed response: KeyError('request_id')
WARNING: Received invalid JSON message: <error>
```

**Cause:** Client sending invalid JSON or missing required fields.

**Solution:**

**Client Side:**
```python
#  CORRECT - Include all required fields
response = {
    "request_id": request.request_id,  # Required
    "data": {"answer": "yes"}  # Optional (data or error)
}
await transport.write(json.dumps(response))

# L WRONG - Missing request_id
response = {"data": {"answer": "yes"}}  # Missing request_id!
```

---

### Error: Request/Response ID Mismatch

**Symptom:** Responses paired with wrong requests, unexpected behavior.

**Cause:** Client not preserving `request_id` in response.

**Solution:**

```python
# Client must echo request_id in response
async def handle_request(request_json):
    request = json.loads(request_json)
    request_id = request["request_id"]  # Extract request_id

    # Process request...
    answer = process_question(request["data"]["question"])

    # Echo request_id in response
    response = {
        "request_id": request_id,  # CRITICAL: Must match request
        "data": {"answer": answer}
    }
    return json.dumps(response)
```

---

## Performance Issues

### Issue: High Latency

**Symptom:** Requests take longer than expected.

**Diagnosis:**

```python
import time

start = time.time()
response = await protocol.send_request(request, timeout=10.0)
elapsed = time.time() - start
print(f"Request took {elapsed:.2f}s")
```

**Solutions:**

1. **Use Faster Transport:**
```python
# Slow: HTTPTransport (network overhead)
transport = HTTPTransport(base_url="http://localhost:8000")

# Fast: InMemoryTransport (testing) or CLITransport (local)
transport = InMemoryTransport()
```

2. **Reduce Timeout:**
```python
# Don't wait too long
response = await protocol.send_request(request, timeout=5.0)
```

3. **Profile Transport:**
```python
# Check transport performance
start = time.time()
await transport.write(message)
write_time = time.time() - start

start = time.time()
async for msg in transport.read_messages():
    read_time = time.time() - start
    break
```

---

### Issue: Memory Leak

**Symptom:** Memory usage grows over time.

**Cause:** Not cleaning up protocol/transport properly.

**Solution:**

```python
#  CORRECT - Always cleanup
try:
    async with anyio.create_task_group() as tg:
        await protocol.start(tg)
        # ... use protocol ...
finally:
    await protocol.stop()  # Clean up
    await transport.close()  # Release resources
```

---

## Integration Issues

### Issue: Tool Calling + Control Protocol Conflicts

**Symptom:** Tool approval workflows interfere with custom approval requests.

**Solution:** Use separate approval methods:

```python
# For tools (built-in)
result = await agent.execute_tool("delete_file", {"path": "data.txt"})
# Tool approval handled automatically

# For custom operations (explicit)
approved = await agent.request_approval("Delete database", details)
if approved:
    delete_database()
```

---

### Issue: Multi-Agent + Control Protocol

**Symptom:** Multiple agents trying to use same transport.

**Solution:** Each agent needs its own protocol instance:

```python
# L WRONG - Shared protocol
protocol = ControlProtocol(transport)
agent1 = Agent1(config, control_protocol=protocol)
agent2 = Agent2(config, control_protocol=protocol)  # Conflict!

#  CORRECT - Separate transports/protocols
transport1 = CLITransport()
await transport1.connect()
protocol1 = ControlProtocol(transport1)
agent1 = Agent1(config, control_protocol=protocol1)

transport2 = HTTPTransport(base_url="http://localhost:8001")
await transport2.connect()
protocol2 = ControlProtocol(transport2)
agent2 = Agent2(config, control_protocol=protocol2)
```

---

## Debugging Tips

### Enable Debug Logging

```python
import logging

# Enable Control Protocol debug logs
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Specific logger
logger = logging.getLogger("kaizen.core.autonomy.control")
logger.setLevel(logging.DEBUG)
```

### Inspect Messages

```python
# Log all messages
original_write = transport.write

async def logged_write(message):
    logger.debug(f"Sending: {message}")
    return await original_write(message)

transport.write = logged_write
```

### Test Transports Independently

```python
# Test transport without Control Protocol
transport = YourTransport(...)
await transport.connect()

# Test write
await transport.write('{"test": "message"}')

# Test read
async for message in transport.read_messages():
    print(f"Received: {message}")
    break

await transport.close()
```

---

## Common Patterns That Work

### Pattern: Timeout with Retry

```python
async def ask_with_retry(agent, question, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await agent.ask_user_question(
                question,
                timeout=30.0
            )
        except TimeoutError:
            if attempt == max_retries - 1:
                return "default"  # Give up
            logger.warning(f"Timeout, retrying ({attempt + 1}/{max_retries})")
```

### Pattern: Fallback Transport

```python
async def create_protocol_with_fallback():
    # Try HTTP first
    try:
        transport = HTTPTransport(base_url="http://localhost:8000")
        await transport.connect()
        return ControlProtocol(transport)
    except ConnectionError:
        # Fall back to CLI
        logger.warning("HTTP unavailable, using CLI")
        transport = CLITransport()
        await transport.connect()
        return ControlProtocol(transport)
```

### Pattern: Graceful Shutdown

```python
async def run_agent_safely(agent):
    protocol = agent.control_protocol
    transport = protocol._transport

    try:
        async with anyio.create_task_group() as tg:
            await protocol.start(tg)
            result = await agent.process()
            return result
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    finally:
        await protocol.stop()
        await transport.close()
```

---

## When to Ask for Help

If you've tried the solutions above and still have issues:

1. **Check existing issues:** [GitHub Issues](https://github.com/terrene-foundation/kailash-py/issues)
2. **Create minimal reproduction:** Simplest code that shows the problem
3. **Provide context:**
   - Kaizen version: `pip show kailash-kaizen`
   - Python version: `python --version`
   - Transport type
   - Error message and stack trace
   - Code snippet (minimal)

---

## See Also

- **[API Reference](./control-protocol-api.md)** - Complete Control Protocol API
- **[Tutorial](../guides/control-protocol-tutorial.md)** - Step-by-step guide
- **[Migration Guide](../guides/migrating-to-control-protocol.md)** - Migrate existing agents
- **[Custom Transports](../guides/custom-transports.md)** - Build custom transports

---

**Version:** Kaizen v0.3.0+
**Status:** Production-ready 
**Last Updated:** 2025-01-22
