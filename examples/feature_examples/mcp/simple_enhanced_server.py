"""
Simple example of Enhanced MCP Server usage.

This demonstrates how users can create production-ready MCP servers
with caching, metrics, and configuration out of the box.
"""

import asyncio
import time
from kailash.mcp import MCPServer, SimpleMCPServer


def weather_service_example():
    """Example of a weather service MCP server."""
    print("=== Weather Service MCP Server ===")
    
    # Create server with enhanced features
    server = MCPServer("weather-service")
    
    @server.tool()
    async def get_current_weather(city: str) -> dict:
        """Get current weather for a city (no caching)."""
        # Simulate API call
        await asyncio.sleep(0.1)
        return {
            "city": city,
            "temperature": 22,
            "condition": "sunny",
            "humidity": 65,
            "timestamp": time.time()
        }
    
    @server.tool(cache_key="forecast", cache_ttl=600)  # Cache for 10 minutes
    async def get_forecast(city: str, days: int = 5) -> dict:
        """Get weather forecast with caching."""
        # Simulate expensive API call
        await asyncio.sleep(0.5)
        return {
            "city": city,
            "forecast": [
                {"day": i+1, "temperature": 20+i, "condition": "partly cloudy"}
                for i in range(days)
            ],
            "generated_at": time.time()
        }
    
    @server.tool(format_response="markdown")
    async def weather_summary(city: str) -> dict:
        """Get weather summary formatted as markdown."""
        return {
            "title": f"Weather Summary for {city}",
            "current": "Sunny, 22°C",
            "forecast": "Clear skies expected",
            "alerts": ["UV warning in effect"]
        }
    
    @server.resource("weather://current/{city}")
    async def current_weather_resource(city: str) -> str:
        """Resource endpoint for current weather."""
        weather = await get_current_weather(city)
        return f"Current weather in {city}: {weather['condition']}, {weather['temperature']}°C"
    
    print(f"✅ Weather server created with {len(server._tool_registry)} tools")
    print("   Tools:")
    for tool_name, info in server._tool_registry.items():
        cached = "cached" if info['cached'] else "not cached"
        formatted = f", formatted as {info['format_response']}" if info['format_response'] else ""
        print(f"   - {tool_name}: {cached}{formatted}")
    
    return server


def simple_calculator_example():
    """Example using SimpleMCPServer for basic use cases."""
    print("\n=== Simple Calculator MCP Server ===")
    
    # Simple server with minimal features
    server = SimpleMCPServer("calculator", "Basic math operations")
    
    @server.tool()
    def add(a: float, b: float) -> float:
        """Add two numbers."""
        return a + b
    
    @server.tool()
    def multiply(a: float, b: float) -> float:
        """Multiply two numbers."""
        return a * b
    
    @server.tool()
    def factorial(n: int) -> int:
        """Calculate factorial (note: no caching by default in SimpleMCPServer)."""
        if n < 0:
            raise ValueError("Factorial not defined for negative numbers")
        if n <= 1:
            return 1
        return n * factorial(n - 1)
    
    print("✅ Calculator server created")
    print(f"   Cache enabled: {server.cache.enabled}")
    print(f"   Metrics enabled: {server.metrics.enabled}")
    
    return server


def demonstrate_server_features():
    """Demonstrate the enhanced features."""
    print("\n=== Demonstrating Enhanced Features ===")
    
    # Create a server to test features
    server = MCPServer("demo-server")
    
    @server.tool(cache_key="demo", cache_ttl=60)
    async def cached_operation(data: str) -> dict:
        """Operation that benefits from caching."""
        # Simulate expensive work
        await asyncio.sleep(0.1)
        return {
            "processed": data.upper(),
            "length": len(data),
            "timestamp": time.time()
        }
    
    # Simulate calling the tool multiple times
    async def test_caching():
        print("\n--- Testing Caching ---")
        
        # First call - cache miss
        start = time.time()
        result1 = await cached_operation("hello")
        time1 = time.time() - start
        print(f"First call: {time1:.3f}s - {result1}")
        
        # Second call - cache hit (should be much faster)
        start = time.time()
        result2 = await cached_operation("hello")
        time2 = time.time() - start
        print(f"Second call: {time2:.3f}s - {result2}")
        
        print(f"Speed improvement: {(time1/time2):.1f}x faster")
        
        # Check cache stats
        cache_stats = server.cache.stats()
        print(f"Cache stats: {cache_stats}")
    
    # Test metrics
    print("\n--- Testing Metrics ---")
    server.metrics.track_tool_call("manual_tool", 0.05, True)
    server.metrics.track_tool_call("manual_tool", 0.08, False, "TimeoutError")
    
    metrics = server.metrics.export_metrics()
    print(f"Tool metrics: {metrics['tools']}")
    
    # Test configuration
    print("\n--- Testing Configuration ---")
    print(f"Server name: {server.config.get('server.name')}")
    print(f"Cache TTL: {server.config.get('cache.default_ttl')}")
    print(f"Metrics enabled: {server.config.get('metrics.enabled')}")
    
    # Override configuration
    server.config.set("custom.feature", "enabled")
    print(f"Custom setting: {server.config.get('custom.feature')}")
    
    return test_caching


async def main():
    """Run all examples."""
    try:
        # Create example servers
        weather_server = weather_service_example()
        calculator_server = simple_calculator_example()
        
        # Demonstrate features
        test_caching = demonstrate_server_features()
        
        # Run caching test
        await test_caching()
        
        print("\n🎉 All examples completed successfully!")
        print("\nTo run these servers:")
        print("1. Uncomment the server.run() lines below")
        print("2. Use MCP clients to connect via stdio transport")
        print("3. Call tools and see caching/metrics in action")
        
        # Uncomment to run servers (they run indefinitely)
        # print("\nStarting weather server...")
        # weather_server.run()
        
    except Exception as e:
        print(f"❌ Example failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())