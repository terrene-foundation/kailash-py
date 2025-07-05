# MCP Troubleshooting Guide

## Overview

This guide provides comprehensive troubleshooting procedures for common issues encountered with MCP (Model Context Protocol) servers and clients. It includes diagnostic steps, solutions, and preventive measures.

## Table of Contents

1. [Common Issues](#common-issues)
2. [Connection Problems](#connection-problems)
3. [Authentication Issues](#authentication-issues)
4. [Performance Problems](#performance-problems)
5. [Tool Execution Errors](#tool-execution-errors)
6. [Transport-Specific Issues](#transport-specific-issues)
7. [Debugging Techniques](#debugging-techniques)
8. [Log Analysis](#log-analysis)
9. [Health Check Failures](#health-check-failures)
10. [Recovery Procedures](#recovery-procedures)

## Common Issues

### Issue: MCP Server Won't Start

**Symptoms:**
- Server fails to start
- Error messages about missing dependencies
- Port already in use errors

**Diagnosis:**
```bash
# Check if port is in use
lsof -i :3000

# Check dependencies
pip list | grep -E "fastmcp|kailash"

# Check configuration
python -c "from mcp_server.config import Config; Config.validate()"

# Check file permissions
ls -la /app/mcp_server/
```

**Solutions:**

1. **Port conflict:**
```bash
# Kill process using port
kill -9 $(lsof -t -i:3000)

# Or use different port
export MCP_PORT=3001
```

2. **Missing dependencies:**
```bash
# Install dependencies
pip install -r requirements.txt

# Or with specific versions
pip install "fastmcp>=0.1.0" "kailash-sdk>=0.6.0"
```

3. **Configuration issues:**
```python
# Fix configuration
import os
os.environ['MCP_AUTH_ENABLED'] = 'false'  # Disable auth for testing
os.environ['MCP_LOG_LEVEL'] = 'DEBUG'     # Enable debug logging
```

### Issue: Tools Not Loading

**Symptoms:**
- Empty tool list
- Tool registration errors
- Import failures

**Diagnosis:**
```python
# Test tool loading
from mcp_server.tools import ToolRegistry

registry = ToolRegistry()
print(f"Loaded tools: {registry.list_tools()}")

# Check tool imports
try:
    from mcp_server.tools.search import SearchTool
    print("SearchTool imported successfully")
except Exception as e:
    print(f"Import error: {e}")
```

**Solutions:**

1. **Fix tool registration:**
```python
# Manually register tools
from mcp_server import MCPServer
from mcp_server.tools import SearchTool, CalculateTool

server = MCPServer()
server.register_tool(SearchTool())
server.register_tool(CalculateTool())
```

2. **Debug tool initialization:**
```python
# Enable verbose logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Test individual tool
tool = SearchTool()
print(f"Tool name: {tool.name}")
print(f"Tool description: {tool.description}")
```

## Connection Problems

### Issue: Client Can't Connect to Server

**Symptoms:**
- Connection refused errors
- Timeout errors
- SSL/TLS errors

**Diagnosis:**
```bash
# Test basic connectivity
curl http://localhost:3000/health

# Test with SSL
curl https://localhost:3000/health --insecure

# Check network
netstat -an | grep 3000

# Test DNS resolution
nslookup mcp-server.example.com
```

**Solutions:**

1. **Network connectivity:**
```python
# Test server accessibility
import requests

def test_connection(url):
    try:
        response = requests.get(f"{url}/health", timeout=5)
        print(f"Status: {response.status_code}")
        return True
    except requests.exceptions.ConnectionError:
        print("Connection refused")
        return False
    except requests.exceptions.Timeout:
        print("Connection timeout")
        return False

test_connection("http://localhost:3000")
```

2. **SSL/TLS issues:**
```python
# Disable SSL verification (development only)
import ssl
import certifi

# Create custom SSL context
ssl_context = ssl.create_default_context(cafile=certifi.where())
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Use in client
from mcp import MCPClient
client = MCPClient(
    server_url="https://localhost:3000",
    ssl_context=ssl_context
)
```

3. **Firewall/proxy issues:**
```bash
# Check firewall rules
sudo iptables -L -n | grep 3000

# Test through proxy
export HTTP_PROXY=http://proxy:8080
export HTTPS_PROXY=http://proxy:8080
curl -x $HTTP_PROXY http://mcp-server:3000/health
```

### Issue: Intermittent Connection Drops

**Symptoms:**
- Random disconnections
- "Connection reset by peer" errors
- WebSocket/SSE connection losses

**Diagnosis:**
```python
# Monitor connection stability
import asyncio
import time
from mcp import MCPClient

async def monitor_connection():
    client = MCPClient("http://localhost:3000")
    connection_count = 0
    drop_count = 0

    while True:
        try:
            await client.connect()
            connection_count += 1
            print(f"Connected successfully ({connection_count} times)")

            # Keep connection alive
            while True:
                await client.ping()
                await asyncio.sleep(30)

        except Exception as e:
            drop_count += 1
            print(f"Connection dropped ({drop_count} times): {e}")
            await asyncio.sleep(5)

asyncio.run(monitor_connection())
```

**Solutions:**

1. **Implement reconnection logic:**
```python
class ReconnectingMCPClient(MCPClient):
    """MCP client with automatic reconnection"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_retries = 5
        self.retry_delay = 1

    async def connect_with_retry(self):
        """Connect with exponential backoff"""
        for attempt in range(self.max_retries):
            try:
                await self.connect()
                print("Connected successfully")
                return
            except Exception as e:
                delay = self.retry_delay * (2 ** attempt)
                print(f"Connection failed, retrying in {delay}s: {e}")
                await asyncio.sleep(delay)

        raise Exception("Max connection retries exceeded")
```

2. **Configure keep-alive:**
```python
# Server-side keep-alive
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

app = FastAPI()

# Add keep-alive headers
@app.middleware("http")
async def add_keep_alive(request, call_next):
    response = await call_next(request)
    response.headers["Connection"] = "keep-alive"
    response.headers["Keep-Alive"] = "timeout=60, max=1000"
    return response
```

## Authentication Issues

### Issue: Authentication Failures

**Symptoms:**
- 401 Unauthorized errors
- Invalid token errors
- Token expiration issues

**Diagnosis:**
```python
# Test authentication
import jwt
import requests

def test_auth(server_url, username, password):
    # Get token
    auth_response = requests.post(
        f"{server_url}/auth/token",
        json={"username": username, "password": password}
    )

    if auth_response.status_code != 200:
        print(f"Auth failed: {auth_response.text}")
        return

    token = auth_response.json()["access_token"]

    # Decode token
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        print(f"Token payload: {payload}")
    except Exception as e:
        print(f"Token decode error: {e}")

    # Test authenticated request
    headers = {"Authorization": f"Bearer {token}"}
    test_response = requests.get(f"{server_url}/tools", headers=headers)
    print(f"Authenticated request status: {test_response.status_code}")

test_auth("http://localhost:3000", "testuser", "testpass")
```

**Solutions:**

1. **Token refresh implementation:**
```python
class TokenManager:
    """Manage authentication tokens"""

    def __init__(self, server_url, credentials):
        self.server_url = server_url
        self.credentials = credentials
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None

    async def get_valid_token(self):
        """Get valid token, refreshing if necessary"""
        if self.token_expiry and datetime.utcnow() < self.token_expiry:
            return self.access_token

        # Try refresh token first
        if self.refresh_token:
            try:
                return await self.refresh_access_token()
            except:
                pass

        # Fall back to full authentication
        return await self.authenticate()

    async def authenticate(self):
        """Perform full authentication"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.server_url}/auth/token",
                json=self.credentials
            ) as response:
                data = await response.json()
                self.access_token = data["access_token"]
                self.refresh_token = data.get("refresh_token")
                self.token_expiry = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
                return self.access_token
```

2. **Debug authentication flow:**
```python
# Enable auth debugging
import logging

logging.getLogger("mcp.auth").setLevel(logging.DEBUG)

# Custom auth handler with debugging
class DebugAuthHandler:
    def __init__(self, auth_handler):
        self.auth_handler = auth_handler

    async def authenticate(self, request):
        print(f"Auth headers: {request.headers}")

        try:
            result = await self.auth_handler.authenticate(request)
            print(f"Auth successful: {result}")
            return result
        except Exception as e:
            print(f"Auth failed: {e}")
            raise
```

## Performance Problems

### Issue: Slow Response Times

**Symptoms:**
- High latency
- Timeouts
- CPU/memory spikes

**Diagnosis:**
```python
# Performance profiling
import time
import psutil
import asyncio
from contextlib import asynccontextmanager

class PerformanceProfiler:
    """Profile MCP operations"""

    @asynccontextmanager
    async def profile(self, operation_name):
        """Profile an operation"""
        start_time = time.time()
        start_cpu = psutil.Process().cpu_percent()
        start_memory = psutil.Process().memory_info().rss / 1024 / 1024

        try:
            yield
        finally:
            end_time = time.time()
            end_cpu = psutil.Process().cpu_percent()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024

            print(f"\nPerformance Profile: {operation_name}")
            print(f"Duration: {end_time - start_time:.2f}s")
            print(f"CPU Usage: {end_cpu - start_cpu:.1f}%")
            print(f"Memory Delta: {end_memory - start_memory:.1f}MB")

# Usage
async def test_performance():
    profiler = PerformanceProfiler()

    async with profiler.profile("Tool Execution"):
        result = await client.execute_tool("search", {"query": "test"})
```

**Solutions:**

1. **Implement caching:**
```python
from functools import lru_cache
import hashlib
import redis

class MCPCache:
    """Caching layer for MCP"""

    def __init__(self, redis_url="redis://localhost:6379"):
        self.redis = redis.from_url(redis_url)
        self.default_ttl = 300  # 5 minutes

    def cache_key(self, tool_name: str, args: dict) -> str:
        """Generate cache key"""
        args_str = json.dumps(args, sort_keys=True)
        return f"mcp:tool:{tool_name}:{hashlib.md5(args_str.encode()).hexdigest()}"

    async def get_or_execute(self, tool_name: str, args: dict, executor):
        """Get from cache or execute"""
        key = self.cache_key(tool_name, args)

        # Check cache
        cached = self.redis.get(key)
        if cached:
            return json.loads(cached)

        # Execute and cache
        result = await executor(tool_name, args)
        self.redis.setex(key, self.default_ttl, json.dumps(result))

        return result
```

2. **Optimize database queries:**
```python
# Connection pooling
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool, QueuePool

# Create engine with connection pooling
engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/db",
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_pre_ping=True  # Verify connections before use
)

# Query optimization
class OptimizedQueries:
    @staticmethod
    async def get_tools_batch(tool_ids: List[str]):
        """Batch query for tools"""
        async with AsyncSession(engine) as session:
            # Use IN clause instead of multiple queries
            result = await session.execute(
                "SELECT * FROM tools WHERE id = ANY(:ids)",
                {"ids": tool_ids}
            )
            return result.fetchall()
```

### Issue: Memory Leaks

**Symptoms:**
- Gradual memory increase
- OOM kills
- Performance degradation

**Diagnosis:**
```python
# Memory leak detection
import gc
import tracemalloc
import asyncio

class MemoryLeakDetector:
    """Detect memory leaks in MCP"""

    def __init__(self):
        tracemalloc.start()
        self.snapshots = []

    def take_snapshot(self, label: str):
        """Take memory snapshot"""
        gc.collect()
        snapshot = tracemalloc.take_snapshot()
        self.snapshots.append((label, snapshot))

        # Get current memory usage
        current, peak = tracemalloc.get_traced_memory()
        print(f"\n{label}:")
        print(f"Current memory: {current / 1024 / 1024:.1f}MB")
        print(f"Peak memory: {peak / 1024 / 1024:.1f}MB")

    def compare_snapshots(self, label1: str, label2: str):
        """Compare two snapshots"""
        snap1 = next(s for l, s in self.snapshots if l == label1)
        snap2 = next(s for l, s in self.snapshots if l == label2)

        top_stats = snap2.compare_to(snap1, 'lineno')

        print(f"\nTop 10 memory increases from {label1} to {label2}:")
        for stat in top_stats[:10]:
            print(stat)

# Usage
detector = MemoryLeakDetector()

# Before operations
detector.take_snapshot("before")

# Run operations
for i in range(1000):
    await client.execute_tool("test", {"iteration": i})

# After operations
detector.take_snapshot("after")
detector.compare_snapshots("before", "after")
```

**Solutions:**

1. **Fix common memory leaks:**
```python
# Proper cleanup in async contexts
class MCPServerWithCleanup(MCPServer):
    """MCP server with proper cleanup"""

    def __init__(self):
        super().__init__()
        self._cleanup_tasks = []

    async def start(self):
        """Start server with cleanup tracking"""
        await super().start()

        # Schedule periodic cleanup
        cleanup_task = asyncio.create_task(self._periodic_cleanup())
        self._cleanup_tasks.append(cleanup_task)

    async def stop(self):
        """Stop server and cleanup"""
        # Cancel all tasks
        for task in self._cleanup_tasks:
            task.cancel()

        # Wait for cancellation
        await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)

        # Clear references
        self._cleanup_tasks.clear()

        await super().stop()

    async def _periodic_cleanup(self):
        """Periodic cleanup of resources"""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes

                # Clear old cache entries
                self._clear_old_cache()

                # Close idle connections
                await self._close_idle_connections()

                # Force garbage collection
                gc.collect()

            except asyncio.CancelledError:
                break
```

## Tool Execution Errors

### Issue: Tool Execution Failures

**Symptoms:**
- Tool not found errors
- Parameter validation errors
- Execution timeouts

**Diagnosis:**
```python
# Tool execution debugging
class ToolDebugger:
    """Debug tool execution issues"""

    async def debug_tool(self, server_url: str, tool_name: str, args: dict):
        """Debug a specific tool"""
        print(f"\nDebugging tool: {tool_name}")
        print(f"Arguments: {json.dumps(args, indent=2)}")

        # Check if tool exists
        async with aiohttp.ClientSession() as session:
            # List tools
            async with session.get(f"{server_url}/tools") as response:
                tools = await response.json()
                tool_names = [t["name"] for t in tools.get("tools", [])]

                if tool_name not in tool_names:
                    print(f"ERROR: Tool '{tool_name}' not found")
                    print(f"Available tools: {tool_names}")
                    return

            # Get tool schema
            async with session.get(f"{server_url}/tools/{tool_name}") as response:
                if response.status == 200:
                    schema = await response.json()
                    print(f"\nTool schema: {json.dumps(schema, indent=2)}")

                    # Validate arguments
                    self.validate_args(args, schema.get("parameters", {}))

            # Execute tool
            headers = {"Content-Type": "application/json"}
            async with session.post(
                f"{server_url}/tools/{tool_name}/execute",
                json=args,
                headers=headers
            ) as response:
                print(f"\nExecution status: {response.status}")
                result = await response.text()
                print(f"Result: {result}")

    def validate_args(self, args: dict, schema: dict):
        """Validate arguments against schema"""
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        # Check required fields
        missing = [field for field in required if field not in args]
        if missing:
            print(f"ERROR: Missing required fields: {missing}")

        # Check field types
        for field, value in args.items():
            if field in properties:
                expected_type = properties[field].get("type")
                actual_type = type(value).__name__

                if not self.type_matches(value, expected_type):
                    print(f"ERROR: Field '{field}' type mismatch")
                    print(f"  Expected: {expected_type}")
                    print(f"  Actual: {actual_type}")
```

**Solutions:**

1. **Implement retry logic:**
```python
class RetryableToolExecutor:
    """Tool executor with retry logic"""

    def __init__(self, max_retries=3, backoff_factor=2):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    async def execute_with_retry(self, client, tool_name, args):
        """Execute tool with exponential backoff retry"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                result = await client.execute_tool(tool_name, args)
                return result

            except Exception as e:
                last_error = e

                # Don't retry on validation errors
                if "validation" in str(e).lower():
                    raise

                # Calculate delay
                delay = self.backoff_factor ** attempt
                print(f"Attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                await asyncio.sleep(delay)

        raise Exception(f"Tool execution failed after {self.max_retries} attempts: {last_error}")
```

2. **Add timeout handling:**
```python
class TimeoutHandler:
    """Handle tool execution timeouts"""

    async def execute_with_timeout(self, executor, tool_name, args, timeout=30):
        """Execute with timeout"""
        try:
            result = await asyncio.wait_for(
                executor(tool_name, args),
                timeout=timeout
            )
            return result

        except asyncio.TimeoutError:
            # Log timeout
            logger.error(f"Tool {tool_name} timed out after {timeout}s", extra={
                "tool_name": tool_name,
                "args": args,
                "timeout": timeout
            })

            # Return timeout response
            return {
                "error": "timeout",
                "message": f"Tool execution timed out after {timeout} seconds",
                "tool": tool_name
            }
```

## Transport-Specific Issues

### Issue: SSE Connection Problems

**Symptoms:**
- Events not received
- Connection drops after timeout
- Buffering issues

**Diagnosis:**
```python
# SSE connection testing
import sseclient

def test_sse_connection(url):
    """Test SSE connection"""
    print(f"Testing SSE connection to {url}")

    messages = []
    try:
        response = requests.get(url, stream=True)
        client = sseclient.SSEClient(response)

        for event in client.events():
            print(f"Event: {event.event}")
            print(f"Data: {event.data}")
            messages.append(event)

            # Test first 5 events
            if len(messages) >= 5:
                break

    except Exception as e:
        print(f"SSE Error: {e}")

    return messages
```

**Solutions:**

1. **Fix SSE buffering:**
```python
# Server-side SSE configuration
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio

app = FastAPI()

@app.get("/events")
async def events():
    async def event_generator():
        while True:
            # Disable buffering
            yield f"data: {json.dumps({'time': time.time()})}\n\n".encode()

            # Flush immediately
            await asyncio.sleep(0)  # Yield control

            # Wait for next event
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
            "Connection": "keep-alive"
        }
    )
```

### Issue: WebSocket Disconnections

**Symptoms:**
- WebSocket closes unexpectedly
- Ping/pong failures
- Message size errors

**Solutions:**

```python
# WebSocket with keep-alive
class WebSocketManager:
    """Manage WebSocket connections"""

    def __init__(self, url):
        self.url = url
        self.ws = None
        self.ping_interval = 30
        self.ping_task = None

    async def connect(self):
        """Connect with keep-alive"""
        self.ws = await websockets.connect(
            self.url,
            ping_interval=self.ping_interval,
            ping_timeout=10,
            close_timeout=10,
            max_size=10 * 1024 * 1024  # 10MB max message size
        )

        # Start ping task
        self.ping_task = asyncio.create_task(self._ping_loop())

    async def _ping_loop(self):
        """Send periodic pings"""
        while self.ws and not self.ws.closed:
            try:
                pong = await self.ws.ping()
                await asyncio.wait_for(pong, timeout=10)
                await asyncio.sleep(self.ping_interval)
            except Exception as e:
                print(f"Ping failed: {e}")
                break
```

## Debugging Techniques

### Enable Debug Logging

```python
# Comprehensive debug logging setup
import logging
import sys

def setup_debug_logging():
    """Setup comprehensive debug logging"""

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console handler with formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    # Detailed formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - '
        '[%(filename)s:%(lineno)d] - %(funcName)s() - %(message)s'
    )
    console_handler.setFormatter(formatter)

    # Add handler
    root_logger.addHandler(console_handler)

    # Configure specific loggers
    loggers = [
        'mcp',
        'mcp.server',
        'mcp.client',
        'mcp.transport',
        'mcp.auth',
        'mcp.tools'
    ]

    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        print(f"Enabled debug logging for: {logger_name}")

# Usage
setup_debug_logging()
```

### Request/Response Debugging

```python
# HTTP request/response interceptor
class DebugInterceptor:
    """Debug HTTP requests and responses"""

    def __init__(self, client):
        self.client = client
        self._original_request = client.request
        client.request = self._intercept_request

    async def _intercept_request(self, method, url, **kwargs):
        """Intercept and log requests"""
        print(f"\n{'='*60}")
        print(f"REQUEST: {method} {url}")
        print(f"Headers: {kwargs.get('headers', {})}")

        if 'json' in kwargs:
            print(f"Body: {json.dumps(kwargs['json'], indent=2)}")
        elif 'data' in kwargs:
            print(f"Body: {kwargs['data']}")

        # Make request
        response = await self._original_request(method, url, **kwargs)

        # Log response
        print(f"\nRESPONSE: {response.status}")
        print(f"Headers: {dict(response.headers)}")

        try:
            body = await response.json()
            print(f"Body: {json.dumps(body, indent=2)}")
        except:
            text = await response.text()
            print(f"Body: {text[:500]}...")

        print(f"{'='*60}\n")

        return response
```

### Performance Profiling

```python
# Detailed performance profiling
import cProfile
import pstats
import io

class PerformanceDebugger:
    """Debug performance issues"""

    def profile_sync_function(self, func, *args, **kwargs):
        """Profile synchronous function"""
        profiler = cProfile.Profile()
        profiler.enable()

        try:
            result = func(*args, **kwargs)
        finally:
            profiler.disable()

        # Get statistics
        s = io.StringIO()
        ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
        ps.print_stats(20)

        print("\nPerformance Profile:")
        print(s.getvalue())

        return result

    async def profile_async_function(self, func, *args, **kwargs):
        """Profile async function"""
        import aiomonitor

        # Start monitoring
        loop = asyncio.get_event_loop()
        with aiomonitor.start_monitor(loop):
            result = await func(*args, **kwargs)

        return result
```

## Log Analysis

### Parsing MCP Logs

```python
# Log parser for MCP
import re
from datetime import datetime
from collections import defaultdict

class MCPLogParser:
    """Parse and analyze MCP logs"""

    def __init__(self):
        self.log_pattern = re.compile(
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)\s+'
            r'(\w+)\s+'
            r'\[([^\]]+)\]\s+'
            r'(.+)'
        )

    def parse_log_file(self, filepath):
        """Parse log file"""
        logs = []

        with open(filepath, 'r') as f:
            for line in f:
                match = self.log_pattern.match(line)
                if match:
                    logs.append({
                        'timestamp': datetime.fromisoformat(match.group(1)),
                        'level': match.group(2),
                        'module': match.group(3),
                        'message': match.group(4)
                    })

        return logs

    def analyze_errors(self, logs):
        """Analyze error patterns"""
        errors = [log for log in logs if log['level'] == 'ERROR']

        # Group by error type
        error_types = defaultdict(list)
        for error in errors:
            # Extract error type from message
            if 'Exception' in error['message']:
                error_type = error['message'].split(':')[0]
                error_types[error_type].append(error)

        # Report
        print("\nError Analysis:")
        for error_type, instances in error_types.items():
            print(f"\n{error_type}: {len(instances)} occurrences")
            print(f"First seen: {instances[0]['timestamp']}")
            print(f"Last seen: {instances[-1]['timestamp']}")

    def find_slow_requests(self, logs, threshold_ms=1000):
        """Find slow requests in logs"""
        slow_requests = []

        for log in logs:
            if 'duration' in log['message']:
                # Extract duration
                match = re.search(r'duration[:\s]+(\d+)ms', log['message'])
                if match:
                    duration = int(match.group(1))
                    if duration > threshold_ms:
                        slow_requests.append({
                            'timestamp': log['timestamp'],
                            'duration': duration,
                            'message': log['message']
                        })

        return slow_requests
```

### Common Log Patterns

```python
# Common MCP log patterns to watch for
LOG_PATTERNS = {
    'auth_failure': r'Authentication failed.*user=(\w+)',
    'tool_error': r'Tool execution failed.*tool=(\w+)',
    'timeout': r'Request timed out.*endpoint=([^\s]+)',
    'rate_limit': r'Rate limit exceeded.*ip=([^\s]+)',
    'memory_warning': r'Memory usage high.*percent=(\d+)',
    'connection_drop': r'Connection lost.*client=([^\s]+)',
    'sql_error': r'Database error.*query=([^"]+)',
    'validation_error': r'Validation failed.*field=(\w+)'
}

def scan_logs_for_patterns(log_file):
    """Scan logs for common patterns"""
    pattern_counts = defaultdict(int)
    pattern_examples = defaultdict(list)

    with open(log_file, 'r') as f:
        for line in f:
            for pattern_name, pattern in LOG_PATTERNS.items():
                match = re.search(pattern, line)
                if match:
                    pattern_counts[pattern_name] += 1
                    if len(pattern_examples[pattern_name]) < 3:
                        pattern_examples[pattern_name].append({
                            'line': line.strip(),
                            'match': match.group(1)
                        })

    # Report findings
    print("\nLog Pattern Analysis:")
    for pattern_name, count in pattern_counts.items():
        print(f"\n{pattern_name}: {count} occurrences")
        for example in pattern_examples[pattern_name]:
            print(f"  Example: {example['match']}")
```

## Health Check Failures

### Diagnosing Health Check Issues

```python
# Health check diagnostic tool
class HealthCheckDiagnostic:
    """Diagnose health check failures"""

    async def run_diagnostics(self, server_url):
        """Run comprehensive diagnostics"""
        results = {
            'timestamp': datetime.utcnow().isoformat(),
            'checks': {}
        }

        # Basic connectivity
        results['checks']['connectivity'] = await self.check_connectivity(server_url)

        # Health endpoint
        results['checks']['health_endpoint'] = await self.check_health_endpoint(server_url)

        # Component health
        results['checks']['components'] = await self.check_components(server_url)

        # Performance metrics
        results['checks']['performance'] = await self.check_performance(server_url)

        # Generate report
        self.generate_report(results)

        return results

    async def check_connectivity(self, server_url):
        """Check basic connectivity"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(server_url, timeout=5) as response:
                    return {
                        'status': 'healthy',
                        'response_time': response.headers.get('X-Response-Time'),
                        'status_code': response.status
                    }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }

    async def check_components(self, server_url):
        """Check individual components"""
        components = ['database', 'redis', 'tools']
        results = {}

        async with aiohttp.ClientSession() as session:
            for component in components:
                try:
                    async with session.get(
                        f"{server_url}/health/{component}",
                        timeout=5
                    ) as response:
                        results[component] = await response.json()
                except Exception as e:
                    results[component] = {
                        'status': 'unhealthy',
                        'error': str(e)
                    }

        return results

    def generate_report(self, results):
        """Generate diagnostic report"""
        print("\n" + "="*60)
        print("MCP HEALTH DIAGNOSTIC REPORT")
        print("="*60)
        print(f"Timestamp: {results['timestamp']}")

        for check_name, check_result in results['checks'].items():
            print(f"\n{check_name.upper()}:")

            if isinstance(check_result, dict):
                for key, value in check_result.items():
                    print(f"  {key}: {value}")
            else:
                print(f"  Result: {check_result}")

        print("\n" + "="*60)
```

## Recovery Procedures

### Automatic Recovery

```python
# Automatic recovery system
class MCPRecoverySystem:
    """Automated recovery procedures"""

    def __init__(self, server):
        self.server = server
        self.recovery_attempts = 0
        self.max_recovery_attempts = 3

    async def monitor_and_recover(self):
        """Monitor server health and recover if needed"""
        while True:
            try:
                # Check health
                health = await self.check_health()

                if health['status'] != 'healthy':
                    await self.attempt_recovery(health)
                else:
                    self.recovery_attempts = 0  # Reset counter

                await asyncio.sleep(60)  # Check every minute

            except Exception as e:
                logger.error(f"Recovery monitor error: {e}")
                await asyncio.sleep(60)

    async def attempt_recovery(self, health_status):
        """Attempt to recover from unhealthy state"""
        self.recovery_attempts += 1

        if self.recovery_attempts > self.max_recovery_attempts:
            logger.critical("Max recovery attempts exceeded, manual intervention required")
            await self.alert_ops_team()
            return

        logger.info(f"Attempting recovery (attempt {self.recovery_attempts})")

        # Identify issue and recover
        if 'database' in health_status.get('failed_components', []):
            await self.recover_database()
        elif 'memory' in health_status.get('issues', []):
            await self.recover_memory()
        elif 'connections' in health_status.get('issues', []):
            await self.recover_connections()
        else:
            # Generic recovery
            await self.generic_recovery()

    async def recover_database(self):
        """Recover database connection"""
        logger.info("Recovering database connection")

        # Close existing connections
        await self.server.database.close_all_connections()

        # Wait for connections to close
        await asyncio.sleep(2)

        # Reinitialize connection pool
        await self.server.database.initialize_pool()

    async def recover_memory(self):
        """Recover from high memory usage"""
        logger.info("Recovering from high memory usage")

        # Clear caches
        self.server.cache.clear()

        # Force garbage collection
        import gc
        gc.collect()

        # Reduce connection pool sizes
        await self.server.reduce_connection_pools()

    async def generic_recovery(self):
        """Generic recovery procedure"""
        logger.info("Performing generic recovery")

        # Restart non-critical services
        await self.server.restart_services(['cache', 'metrics'])

        # Clear temporary data
        await self.server.clear_temp_data()

        # Reload configuration
        await self.server.reload_config()
```

### Manual Recovery Steps

```bash
#!/bin/bash
# manual_recovery.sh - Manual recovery procedures

echo "MCP Manual Recovery Script"
echo "========================="

# Function to check service status
check_service() {
    service=$1
    if systemctl is-active --quiet $service; then
        echo "✓ $service is running"
    else
        echo "✗ $service is not running"
        return 1
    fi
}

# Function to restart service
restart_service() {
    service=$1
    echo "Restarting $service..."
    systemctl restart $service
    sleep 5
    check_service $service
}

# 1. Check all services
echo -e "\n1. Checking services..."
check_service mcp-server || restart_service mcp-server
check_service postgresql || restart_service postgresql
check_service redis || restart_service redis

# 2. Check disk space
echo -e "\n2. Checking disk space..."
df -h | grep -E '(8[0-9]|9[0-9]|100)%' && echo "WARNING: Low disk space detected!"

# 3. Check database connectivity
echo -e "\n3. Checking database..."
psql -U mcp -d mcp_db -c "SELECT 1;" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✓ Database connection successful"
else
    echo "✗ Database connection failed"
    echo "Attempting to repair..."
    systemctl restart postgresql
fi

# 4. Clear temporary files
echo -e "\n4. Clearing temporary files..."
find /tmp -name "mcp-*" -mtime +1 -delete
echo "✓ Temporary files cleared"

# 5. Check and rotate logs
echo -e "\n5. Checking logs..."
log_size=$(du -sh /var/log/mcp/ | cut -f1)
echo "Log directory size: $log_size"
if [ -f /etc/logrotate.d/mcp ]; then
    logrotate -f /etc/logrotate.d/mcp
    echo "✓ Logs rotated"
fi

# 6. Restart MCP server
echo -e "\n6. Restarting MCP server..."
systemctl restart mcp-server
sleep 10

# 7. Verify recovery
echo -e "\n7. Verifying recovery..."
curl -s http://localhost:3000/health | jq .
```

## Best Practices

### 1. Proactive Monitoring
- Set up comprehensive monitoring before issues occur
- Use health checks extensively
- Monitor resource usage trends
- Set up alerting for anomalies

### 2. Logging Strategy
- Use structured logging (JSON)
- Include correlation IDs
- Log at appropriate levels
- Rotate logs regularly

### 3. Error Handling
- Implement proper error boundaries
- Use exponential backoff for retries
- Provide meaningful error messages
- Log full stack traces for debugging

### 4. Performance
- Profile regularly
- Cache appropriately
- Use connection pooling
- Monitor query performance

### 5. Recovery Planning
- Document recovery procedures
- Automate where possible
- Test recovery procedures
- Keep runbooks updated

## Quick Reference

### Common Commands

```bash
# Check MCP server status
systemctl status mcp-server

# View recent logs
journalctl -u mcp-server -n 100 -f

# Test connectivity
curl http://localhost:3000/health

# Check port usage
netstat -tlnp | grep 3000

# Monitor resource usage
htop -p $(pgrep -f mcp-server)

# Database queries
psql -U mcp -d mcp_db -c "SELECT * FROM tools;"

# Redis status
redis-cli ping

# Docker logs (if using Docker)
docker logs mcp-server --tail 100 -f

# Kubernetes logs
kubectl logs -f deployment/mcp-server -n mcp-system
```

### Environment Variables

```bash
# Debug mode
export MCP_DEBUG=true
export MCP_LOG_LEVEL=DEBUG

# Performance tuning
export MCP_WORKERS=4
export MCP_TIMEOUT=60
export MCP_MAX_CONNECTIONS=100

# Feature flags
export MCP_ENABLE_CACHE=true
export MCP_ENABLE_METRICS=true
export MCP_ENABLE_TRACING=true
```

## Conclusion

Effective troubleshooting requires a systematic approach, good logging, and understanding of the system architecture. This guide provides tools and techniques for diagnosing and resolving common MCP issues. Remember to:

1. Always check logs first
2. Use debugging tools liberally
3. Test fixes in development first
4. Document solutions for future reference
5. Monitor after fixes are applied

Keep this guide updated with new issues and solutions as they are discovered.
