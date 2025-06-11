"""
Test example for Enhanced MCP Server capabilities.

This example demonstrates the enhanced MCP server with caching, metrics,
and configuration management.
"""

import asyncio
import json
import time
from pathlib import Path

# Import the enhanced MCP server
from kailash.mcp.server_enhanced import EnhancedMCPServer


def test_enhanced_server_basic():
    """Test basic enhanced server functionality."""
    print("=== Testing Enhanced MCP Server ===")

    # Create server with all features enabled
    server = EnhancedMCPServer(
        name="test-server", enable_cache=True, cache_ttl=60, enable_metrics=True
    )

    # Add tools with different features
    @server.tool()
    async def simple_tool(message: str) -> str:
        """Simple tool without caching."""
        return f"Echo: {message}"

    @server.tool(cache_key="expensive", cache_ttl=300)
    async def expensive_tool(query: str) -> dict:
        """Tool with caching for expensive operations."""
        # Simulate expensive operation
        await asyncio.sleep(0.1)
        return {
            "query": query,
            "result": f"Processed: {query}",
            "timestamp": time.time(),
        }

    @server.tool(format_response="markdown")
    async def formatted_tool(data: str) -> dict:
        """Tool with markdown formatting."""
        return {
            "title": "Analysis Result",
            "data": data,
            "analysis": "This is formatted as markdown",
        }

    print(f"✅ Server created: {server.name}")
    print(f"✅ Cache enabled: {server.cache.enabled}")
    print(f"✅ Metrics enabled: {server.metrics.enabled}")

    # Test tool registration
    print(f"✅ Tools registered: {len(server._tool_registry)}")
    for tool_name, info in server._tool_registry.items():
        print(f"   - {tool_name}: cached={info['cached']}")

    return server


def test_caching():
    """Test caching functionality."""
    print("\n=== Testing Caching ===")

    from kailash.mcp.utils.cache import CacheManager, LRUCache

    # Test LRU Cache
    cache = LRUCache(max_size=3, ttl=2)

    # Add items
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    cache.set("key3", "value3")

    # Test retrieval
    assert cache.get("key1") == "value1"
    assert cache.get("key2") == "value2"
    assert cache.get("key3") == "value3"

    # Test LRU eviction
    cache.set("key4", "value4")  # Should evict key1
    assert cache.get("key1") is None
    assert cache.get("key4") == "value4"

    print("✅ LRU eviction works")

    # Test TTL expiration
    time.sleep(2.1)
    assert cache.get("key2") is None  # Should be expired
    print("✅ TTL expiration works")

    # Test cache manager
    manager = CacheManager(enabled=True, default_ttl=60)

    @manager.cached("test_cache")
    def expensive_function(x: int) -> int:
        time.sleep(0.01)  # Simulate work
        return x * x

    # First call - cache miss
    start = time.time()
    result1 = expensive_function(5)
    time1 = time.time() - start

    # Second call - cache hit
    start = time.time()
    result2 = expensive_function(5)
    time2 = time.time() - start

    assert result1 == result2 == 25
    assert time2 < time1  # Second call should be faster
    print("✅ Function caching works")

    # Check cache stats
    stats = manager.stats()
    print(f"✅ Cache stats: {stats}")


def test_configuration():
    """Test configuration management."""
    print("\n=== Testing Configuration ===")

    from kailash.mcp.utils.config import ConfigManager

    # Test with defaults
    config = ConfigManager()
    config.set("test.value", 42)
    config.set("nested.deep.value", "hello")

    assert config.get("test.value") == 42
    assert config.get("nested.deep.value") == "hello"
    assert config.get("missing.key", "default") == "default"

    print("✅ Basic configuration works")

    # Test configuration hierarchy
    config.update(
        {
            "server": {"name": "test", "port": 8080},
            "cache": {"enabled": True, "ttl": 300},
        }
    )

    assert config.get("server.name") == "test"
    assert config.get("server.port") == 8080
    assert config.get("cache.enabled") is True

    print("✅ Nested configuration works")

    # Test configuration export
    config_dict = config.to_dict()
    assert "server" in config_dict
    assert "cache" in config_dict

    print("✅ Configuration export works")


def test_metrics():
    """Test metrics collection."""
    print("\n=== Testing Metrics ===")

    from kailash.mcp.utils.metrics import MetricsCollector

    metrics = MetricsCollector(enabled=True)

    # Track some tool calls
    metrics.track_tool_call("test_tool", 0.1, True)
    metrics.track_tool_call("test_tool", 0.2, True)
    metrics.track_tool_call("test_tool", 0.15, False, "ValueError")
    metrics.track_tool_call("other_tool", 0.05, True)

    # Get statistics
    tool_stats = metrics.get_tool_stats()
    server_stats = metrics.get_server_stats()

    print(f"✅ Tool stats: {json.dumps(tool_stats, indent=2)}")
    print(f"✅ Server stats: {json.dumps(server_stats, indent=2)}")

    # Test decorator
    @metrics.track_tool("decorated_tool")
    def test_function(x: int) -> int:
        if x < 0:
            raise ValueError("Negative number")
        return x * 2

    # Test successful call
    result = test_function(5)
    assert result == 10

    # Test error call
    try:
        test_function(-1)
    except ValueError:
        pass

    updated_stats = metrics.get_tool_stats()
    assert "decorated_tool" in updated_stats
    assert updated_stats["decorated_tool"]["calls"] == 2
    assert updated_stats["decorated_tool"]["errors"] == 1

    print("✅ Metrics decorator works")


def test_formatters():
    """Test response formatters."""
    print("\n=== Testing Formatters ===")

    from kailash.mcp.utils.formatters import format_response

    # Test data
    data = {
        "name": "Test Result",
        "value": 42,
        "items": ["a", "b", "c"],
        "nested": {"key": "value"},
    }

    # Test JSON formatting
    json_output = format_response(data, "json")
    assert "Test Result" in json_output
    print("✅ JSON formatting works")

    # Test markdown formatting
    md_output = format_response(data, "markdown")
    assert "**name**" in md_output
    print("✅ Markdown formatting works")

    # Test search results formatting
    search_data = [
        {"name": "Result 1", "description": "First result", "_relevance_score": 0.95},
        {"name": "Result 2", "description": "Second result", "_relevance_score": 0.80},
    ]

    search_output = format_response(search_data, "search", query="test")
    assert "Search Results for: 'test'" in search_output
    assert "**Relevance**: 0.95" in search_output
    print("✅ Search formatting works")


def main():
    """Run all tests."""
    try:
        # Test utilities
        test_caching()
        test_configuration()
        test_metrics()
        test_formatters()

        # Test enhanced server
        server = test_enhanced_server_basic()

        # Display server stats
        print("\n=== Server Statistics ===")
        stats = server.get_server_stats()
        print(json.dumps(stats, indent=2, default=str))

        print("\n🎉 All tests passed!")
        print(
            "\nNote: To actually run the server, uncomment the server.run() line below"
        )
        print("The server will run in stdio mode for MCP client connections.")

        # Uncomment to actually run the server
        # print("\nStarting server...")
        # server.run()

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
