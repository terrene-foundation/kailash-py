# Enhanced MCP Server Guide

## Overview

The Kailash SDK provides an enhanced MCP (Model Context Protocol) server that includes production-ready features like caching, metrics collection, and configuration management out of the box. This guide shows how to create powerful MCP servers with minimal code.

## Quick Start

### Basic Enhanced Server

```python
from kailash.mcp import MCPServer

# Create server with all enhancements enabled by default
server = MCPServer("my-server")

@server.tool()
async def search_data(query: str) -> list:
    """Simple tool with automatic metrics tracking."""
    # Your business logic here
    return [f"Result for {query}"]

# Run the server
if __name__ == "__main__":
    server.run()
```

### Simple Server for Prototyping

```python
from kailash.mcp import SimpleMCPServer

# Minimal features for quick development
server = SimpleMCPServer("prototype", "Quick prototype server")

@server.tool()
def calculate(a: float, b: float) -> float:
    """Simple calculation."""
    return a + b

server.run()
```

## Enhanced Features

### Automatic Caching

Cache expensive operations automatically:

```python
@server.tool(cache_key="weather", cache_ttl=600)  # Cache for 10 minutes
async def get_weather(city: str) -> dict:
    """Expensive API call with automatic caching."""
    # First call: hits API and caches result
    # Subsequent calls: returns cached result
    return await fetch_weather_api(city)
```

### Response Formatting

Format responses for better LLM consumption:

```python
@server.tool(format_response="markdown")
async def analyze_data(data: str) -> dict:
    """Analysis with markdown formatting."""
    return {
        "title": "Data Analysis Results",
        "summary": "Analysis complete",
        "details": {"records": 1500, "errors": 0}
    }
    # Automatically formatted as markdown for LLMs
```

Available formats:
- `"json"` - Pretty-printed JSON
- `"markdown"` - Structured markdown
- `"table"` - ASCII tables for tabular data
- `"search"` - Search results with relevance scores

### Automatic Metrics

All tools get automatic performance tracking:

```python
@server.tool()
async def process_data(data: str) -> dict:
    """Tool with automatic metrics."""
    # Metrics tracked automatically:
    # - Call count
    # - Latency (avg, p95, p99)
    # - Error rates
    # - Success rates
    return {"processed": data}

# Check metrics anytime
stats = server.get_server_stats()
print(f"Tool metrics: {stats['metrics']['tools']}")
```

### Configuration Management

Hierarchical configuration with environment overrides:

```python
# Create server with config file
server = MCPServer("my-server", config_file="config.yaml")

# Access configuration
api_key = server.config.get("api.key")
cache_ttl = server.config.get("cache.default_ttl", 300)

# Runtime configuration changes
server.config.set("custom.feature", "enabled")
```

Example `config.yaml`:
```yaml
server:
  name: "production-server"
  version: "1.0.0"

cache:
  enabled: true
  default_ttl: 600
  max_size: 256

api:
  key: "${API_KEY}"  # Environment variable
  timeout: 30

custom:
  feature: "disabled"
```

## Advanced Patterns

### Production Server Example

```python
from kailash.mcp import MCPServer
import asyncio
import aiohttp

class WeatherMCPServer:
    def __init__(self):
        self.server = MCPServer(
            "weather-service",
            config_file="weather_config.yaml"
        )
        self.setup_tools()
        self.setup_resources()
    
    def setup_tools(self):
        @self.server.tool(cache_key="current", cache_ttl=300)
        async def get_current_weather(city: str) -> dict:
            """Get current weather with 5-minute caching."""
            api_key = self.server.config.get("weather.api_key")
            
            async with aiohttp.ClientSession() as session:
                url = f"https://api.weather.com/current?city={city}&key={api_key}"
                async with session.get(url) as response:
                    return await response.json()
        
        @self.server.tool(
            cache_key="forecast", 
            cache_ttl=1800,  # 30 minutes
            format_response="markdown"
        )
        async def get_forecast(city: str, days: int = 5) -> dict:
            """Get weather forecast with caching and markdown formatting."""
            # Implementation here...
            return {
                "city": city,
                "forecast": [
                    {"day": i+1, "temp": 20+i, "condition": "sunny"}
                    for i in range(days)
                ]
            }
    
    def setup_resources(self):
        @self.server.resource("weather://config")
        def get_config() -> str:
            """Weather service configuration."""
            return f"Weather API v{self.server.config.get('server.version')}"
    
    def run(self):
        """Start the weather server."""
        self.server.run()

# Usage
if __name__ == "__main__":
    weather_server = WeatherMCPServer()
    weather_server.run()
```

### Custom Cache Strategies

```python
# Multiple cache strategies
server = MCPServer("data-server")

@server.tool(cache_key="quick", cache_ttl=60)  # 1 minute cache
async def quick_lookup(id: str) -> dict:
    """Fast-changing data."""
    return await quick_api_call(id)

@server.tool(cache_key="reference", cache_ttl=3600)  # 1 hour cache
async def reference_data(id: str) -> dict:
    """Stable reference data."""
    return await reference_api_call(id)

# Clear specific caches when needed
server.clear_cache("quick")  # Clear only quick cache
server.clear_cache()         # Clear all caches
```

### Monitoring and Observability

```python
# Get comprehensive server statistics
stats = server.get_server_stats()

print(f"Server uptime: {stats['metrics']['server']['uptime_seconds']}s")
print(f"Total calls: {stats['metrics']['server']['total_calls']}")
print(f"Error rate: {stats['metrics']['server']['overall_error_rate']:.2%}")

# Per-tool statistics
for tool_name, tool_stats in stats['metrics']['tools'].items():
    print(f"{tool_name}:")
    print(f"  Calls: {tool_stats['calls']}")
    print(f"  Avg latency: {tool_stats['avg_latency']:.3f}s")
    print(f"  Error rate: {tool_stats['error_rate']:.2%}")

# Cache performance
cache_stats = stats['cache']
for cache_name, cache_info in cache_stats.items():
    print(f"Cache {cache_name}: {cache_info['hit_rate']:.2%} hit rate")
```

## Configuration Options

### Server Configuration

```python
server = MCPServer(
    name="my-server",
    config_file="config.yaml",    # Optional config file
    enable_cache=True,            # Enable caching (default: True)
    cache_ttl=300,               # Default cache TTL (default: 300s)
    enable_metrics=True,          # Enable metrics (default: True)
    enable_formatting=True        # Enable response formatting (default: True)
)
```

### Environment Variables

The server automatically reads environment variables with `MCP_` prefix:

```bash
export MCP_CACHE_ENABLED=true
export MCP_CACHE_DEFAULT_TTL=600
export MCP_METRICS_ENABLED=true
export MCP_SERVER_NAME="production-server"
```

Maps to configuration:
- `MCP_CACHE_ENABLED` → `cache.enabled`
- `MCP_CACHE_DEFAULT_TTL` → `cache.default_ttl`
- `MCP_METRICS_ENABLED` → `metrics.enabled`
- `MCP_SERVER_NAME` → `server.name`

## Best Practices

### 1. Use Caching Strategically

```python
# Cache expensive operations
@server.tool(cache_key="expensive", cache_ttl=3600)
async def expensive_computation(data: str) -> dict:
    """Long-running analysis."""
    # Heavy computation here
    return results

# Don't cache time-sensitive data
@server.tool()  # No caching for real-time data
async def get_current_status() -> dict:
    """Real-time status."""
    return {"timestamp": time.time()}
```

### 2. Choose Appropriate Response Formats

```python
# Use markdown for structured data
@server.tool(format_response="markdown")
async def generate_report(data: str) -> dict:
    return {
        "title": "Analysis Report",
        "sections": {"overview": "...", "details": "..."}
    }

# Use table format for tabular data
@server.tool(format_response="table")
async def get_metrics() -> list:
    return [
        {"metric": "cpu", "value": "23%"},
        {"metric": "memory", "value": "1.2GB"}
    ]

# Use JSON for API responses
@server.tool(format_response="json")
async def api_data(endpoint: str) -> dict:
    return await fetch_api_data(endpoint)
```

### 3. Monitor Performance

```python
# Regular health checks
async def health_check():
    stats = server.get_server_stats()
    
    # Check error rates
    error_rate = stats['metrics']['server']['overall_error_rate']
    if error_rate > 0.05:  # 5% threshold
        logger.warning(f"High error rate: {error_rate:.2%}")
    
    # Check cache performance
    for cache_name, cache_stats in stats['cache'].items():
        hit_rate = cache_stats['hit_rate']
        if hit_rate < 0.8:  # 80% threshold
            logger.info(f"Cache {cache_name} hit rate: {hit_rate:.2%}")
```

### 4. Error Handling

```python
@server.tool()
async def robust_operation(data: str) -> dict:
    """Well-designed tool with proper error handling."""
    if not data:
        raise ValueError("Data cannot be empty")
    
    try:
        result = await process_data(data)
        return {"success": True, "result": result}
    except ExternalAPIError as e:
        # Log error for metrics
        logger.error(f"External API failed: {e}")
        return {"success": False, "error": "External service unavailable"}
    except Exception as e:
        # Unexpected errors are tracked automatically
        logger.error(f"Unexpected error: {e}")
        raise
```

## Migration from Basic Servers

### Before (Basic Implementation)

```python
# Old basic server approach
class BasicServer(MCPServer):
    def setup(self):
        @self.add_tool()
        def search(query: str) -> list:
            # No caching, metrics, or formatting
            return expensive_search(query)
```

### After (Enhanced Server)

```python
# New enhanced server - same functionality with production features
server = MCPServer("search-server")

@server.tool(cache_key="search", cache_ttl=600, format_response="search")
async def search(query: str) -> list:
    # Automatic caching, metrics, and formatting
    return await expensive_search(query)
```

### Migration Checklist

- ✅ Replace `from kailash.mcp.server import MCPServer` with `from kailash.mcp import MCPServer`
- ✅ No code changes required - enhanced features work automatically
- ✅ Add `cache_key` to tools that benefit from caching
- ✅ Add `format_response` to tools that return structured data
- ✅ Optionally disable features: `MCPServer('name', enable_cache=False)`
- ✅ Use `server.config.set()` for runtime configuration changes
- ✅ Use `server.get_server_stats()` to monitor performance

**Breaking changes: None!** All existing code continues to work unchanged.

## Resources

- [ADR-0041: Enhanced MCP Server as Default](../../# contrib (removed)/architecture/adr/0041-enhanced-mcp-server-default-capabilities.md)
- [MCP Examples](../../examples/feature_examples/mcp/)
- [Migration Example](../../examples/feature_examples/mcp/migration_example.py)
- [Simple Server Examples](../../examples/feature_examples/mcp/simple_enhanced_server.py)