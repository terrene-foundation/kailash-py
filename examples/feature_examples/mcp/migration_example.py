"""
Migration example from basic to enhanced MCP server.

This shows how existing MCP servers can benefit from enhanced features
with minimal code changes.
"""

import asyncio
import time


def old_basic_server_example():
    """Example of how servers were created before enhancement."""
    print("=== Old Basic Server Pattern ===")
    
    # Old way - using the abstract base class approach
    # (This would be more complex and require manual implementation)
    
    basic_server_code = '''
    class BasicMCPServer(MCPServer):
        def setup(self):
            @self.add_tool()
            def search(query: str) -> list:
                """Basic search without caching."""
                # No caching - every call hits the backend
                results = expensive_search_operation(query)
                return results
                
            @self.add_tool()  
            def get_data(id: str) -> dict:
                """Get data without metrics."""
                # No error tracking or performance monitoring
                return fetch_data_from_api(id)
    
    server = BasicMCPServer("old-server")
    server.start()  # No configuration, caching, or metrics
    '''
    
    print("Old pattern required:")
    print("❌ Manual cache implementation")
    print("❌ Custom metrics collection")
    print("❌ Configuration management from scratch")
    print("❌ Error handling and logging setup")
    print("❌ Response formatting utilities")
    print(f"Code complexity: ~{len(basic_server_code)} characters\n")


def new_enhanced_server_example():
    """Example of enhanced server with same functionality."""
    print("=== New Enhanced Server Pattern ===")
    
    # Import the enhanced server
    from kailash.mcp import MCPServer
    
    # Create server with all enhancements enabled by default
    server = MCPServer("enhanced-server")
    
    @server.tool(cache_key="search", cache_ttl=300)  # Auto-caching
    async def search(query: str) -> list:
        """Enhanced search with caching."""
        print(f"   Searching for: {query}")
        # Simulate expensive operation
        await asyncio.sleep(0.1)
        return [f"Result for {query}", "Additional result"]
    
    @server.tool(format_response="markdown")  # Auto-formatting
    async def get_data(id: str) -> dict:
        """Get data with metrics and formatting."""
        print(f"   Fetching data for ID: {id}")
        # Simulate API call
        await asyncio.sleep(0.05)
        return {
            "id": id,
            "title": f"Data Item {id}",
            "status": "active",
            "metadata": {"created": time.time()}
        }
    
    @server.tool()  # Metrics tracking enabled by default
    async def analyze(data: str) -> dict:
        """Analysis with automatic metrics."""
        if not data:
            raise ValueError("Data cannot be empty")
            
        return {
            "analysis": f"Analyzed: {data}",
            "word_count": len(data.split()),
            "sentiment": "positive"
        }
    
    print("New pattern provides:")
    print("✅ Automatic caching with TTL")
    print("✅ Built-in metrics collection")
    print("✅ Configuration management")
    print("✅ Error handling and logging")
    print("✅ Response formatting utilities")
    print("✅ Performance monitoring")
    print("✅ Zero additional setup required")
    
    return server


async def demonstrate_migration_benefits():
    """Show the benefits of migrating to enhanced server."""
    print("\n=== Migration Benefits Demo ===")
    
    server = new_enhanced_server_example()
    
    # Test caching benefit
    print("\n--- Caching Benefit ---")
    
    # First call - cache miss
    start = time.time()
    result1 = await server._tool_registry['search']['original_function']("machine learning")
    time1 = time.time() - start
    print(f"First search: {time1:.3f}s")
    
    # Second call - would be cache hit in real usage
    start = time.time()
    result2 = await server._tool_registry['search']['original_function']("machine learning")
    time2 = time.time() - start
    print(f"Second search: {time2:.3f}s")
    
    # Test metrics tracking
    print("\n--- Metrics Benefit ---")
    
    # Simulate some tool calls
    server.metrics.track_tool_call("search", 0.1, True)
    server.metrics.track_tool_call("search", 0.05, True)  # Cache hit
    server.metrics.track_tool_call("get_data", 0.05, True)
    server.metrics.track_tool_call("analyze", 0.02, False, "ValueError")
    
    # Show metrics
    tool_stats = server.metrics.get_tool_stats()
    print("Tool performance metrics:")
    for tool, stats in tool_stats.items():
        print(f"  {tool}: {stats['calls']} calls, {stats['error_rate']:.1%} error rate, {stats['avg_latency']:.3f}s avg")
    
    # Test configuration
    print("\n--- Configuration Benefit ---")
    print(f"Cache TTL: {server.config.get('cache.default_ttl')}s")
    print(f"Metrics enabled: {server.config.get('metrics.enabled')}")
    
    # Runtime configuration change
    server.config.set("cache.default_ttl", 600)
    print(f"Updated cache TTL: {server.config.get('cache.default_ttl')}s")
    
    # Show server stats
    print("\n--- Comprehensive Stats ---")
    stats = server.get_server_stats()
    print(f"Registered tools: {stats['tools']['registered_tools']}")
    print(f"Cached tools: {stats['tools']['cached_tools']}")
    print(f"Cache enabled: {stats['server']['config']['cache']['enabled']}")


def migration_checklist():
    """Provide migration checklist for users."""
    print("\n=== Migration Checklist ===")
    
    checklist = [
        "✅ Replace 'from kailash.mcp.server import MCPServer' with 'from kailash.mcp import MCPServer'",
        "✅ No code changes required - enhanced features work automatically",
        "✅ Add @server.tool(cache_key='...') to tools that benefit from caching",
        "✅ Add format_response='markdown' to tools that return structured data",
        "✅ Optionally disable features: MCPServer('name', enable_cache=False)",
        "✅ Use server.config.set() for runtime configuration changes",
        "✅ Use server.get_server_stats() to monitor performance",
        "✅ Use server.clear_cache() to manage cache when needed"
    ]
    
    print("Migration steps:")
    for step in checklist:
        print(f"  {step}")
    
    print("\nBreaking changes: None! 🎉")
    print("All existing code continues to work unchanged.")


def feature_comparison():
    """Compare features between old and new approaches."""
    print("\n=== Feature Comparison ===")
    
    features = [
        ("Caching", "❌ Manual implementation", "✅ Built-in LRU + TTL"),
        ("Metrics", "❌ Custom solution needed", "✅ Automatic collection"),
        ("Configuration", "❌ Environment vars only", "✅ Hierarchical config"),
        ("Error Handling", "❌ Basic try/catch", "✅ Structured error tracking"),
        ("Response Formatting", "❌ Manual string building", "✅ Multiple formatters"),
        ("Performance Monitoring", "❌ No built-in solution", "✅ Latency tracking"),
        ("Resource Usage", "❌ No visibility", "✅ Cache stats & metrics"),
        ("Production Readiness", "❌ Requires custom work", "✅ Ready out of the box"),
        ("Development Speed", "❌ Lots of boilerplate", "✅ Focus on business logic"),
        ("Maintenance", "❌ Maintain custom utils", "✅ SDK handles it")
    ]
    
    print(f"{'Feature':<25} {'Old Approach':<25} {'Enhanced Server'}")
    print("-" * 75)
    for feature, old, new in features:
        print(f"{feature:<25} {old:<25} {new}")


async def main():
    """Run migration demonstration."""
    try:
        old_basic_server_example()
        
        server = new_enhanced_server_example()
        
        await demonstrate_migration_benefits()
        
        migration_checklist()
        
        feature_comparison()
        
        print("\n🎉 Migration demonstration complete!")
        print("\nThe enhanced MCP server provides production-ready capabilities")
        print("while maintaining 100% backward compatibility with existing code.")
        
    except Exception as e:
        print(f"❌ Migration demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())