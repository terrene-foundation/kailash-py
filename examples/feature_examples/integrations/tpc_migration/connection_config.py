#!/usr/bin/env python3
"""Connection Pool Configuration - TPC Migration Pattern.

This example demonstrates the exact connection pool configuration from the
comprehensive migration guide for handling 500+ concurrent users.

Based on comprehensive-migration-guide.md lines 798-829.
"""

import asyncio
import os
from typing import Dict, Any

from kailash.nodes.data import get_connection_manager, AsyncSQLDatabaseNode
from kailash.nodes.data.async_connection import PoolConfig
from kailash.workflow import Workflow
from kailash.runtime.async_local import AsyncLocalRuntime


# Optimal pool sizes for 500+ concurrent users
# From migration guide lines 801-821
POOL_CONFIGS = {
    "main": {
        "min_connections": 10,
        "max_connections": 50,
        "pool_timeout": 30,
        "command_timeout": 60
    },
    "analytics": {
        "min_connections": 5,
        "max_connections": 20,
        "pool_timeout": 60,
        "command_timeout": 300  # Long queries
    },
    "vector": {
        "min_connections": 5,
        "max_connections": 30,
        "pool_timeout": 30,
        "command_timeout": 120
    }
}


def create_pool_config(pool_type: str) -> PoolConfig:
    """Create pool configuration based on type."""
    config = POOL_CONFIGS.get(pool_type, POOL_CONFIGS["main"])
    
    return PoolConfig(
        min_size=config["min_connections"],
        max_size=config["max_connections"],
        pool_timeout=config["pool_timeout"],
        command_timeout=config["command_timeout"],
        health_check_interval=60.0,  # Check every minute
        retry_attempts=3,
        retry_delay=1.0
    )


async def demonstrate_pool_usage():
    """Demonstrate using different pools for different workloads."""
    print("=== TPC Connection Pool Configuration Demo ===\n")
    
    # Get connection manager instance
    manager = get_connection_manager()
    
    # Database configuration
    db_config = {
        "type": "postgresql",
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "tpc_db"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres")
    }
    
    print("1. Creating connection pools with TPC configurations...\n")
    
    # Create different pools for different workloads
    pools_created = []
    
    for pool_type, config in POOL_CONFIGS.items():
        pool_config = create_pool_config(pool_type)
        print(f"Creating {pool_type} pool:")
        print(f"  Min connections: {pool_config.min_size}")
        print(f"  Max connections: {pool_config.max_size}")
        print(f"  Pool timeout: {pool_config.pool_timeout}s")
        print(f"  Command timeout: {pool_config.command_timeout}s")
        
        # Mock pool creation since we're not connected to a real database
        pools_created.append(pool_type)
        print(f"  ✅ {pool_type} pool configured\n")
    
    print("\n2. Example workflows using different pools:\n")
    
    # Main pool - Regular transactional queries
    print("Main Pool Usage - Regular queries:")
    main_query = AsyncSQLDatabaseNode(
        name="fetch_user_data",
        database_type="postgresql",
        connection_string="postgresql://localhost/tpc_db",
        query="SELECT * FROM users WHERE active = true LIMIT 100",
        pool_size=POOL_CONFIGS["main"]["min_connections"],
        max_pool_size=POOL_CONFIGS["main"]["max_connections"],
        timeout=POOL_CONFIGS["main"]["command_timeout"]
    )
    print(f"  Query: User data fetch")
    print(f"  Pool: main (10-50 connections)")
    print(f"  Timeout: {POOL_CONFIGS['main']['command_timeout']}s\n")
    
    # Analytics pool - Long-running analytical queries
    print("Analytics Pool Usage - Heavy queries:")
    analytics_query = AsyncSQLDatabaseNode(
        name="portfolio_performance_analysis",
        database_type="postgresql",
        connection_string="postgresql://localhost/tpc_analytics",
        query="""
            SELECT 
                p.portfolio_id,
                p.name,
                AVG(r.daily_return) as avg_return,
                STDDEV(r.daily_return) as volatility,
                COUNT(*) as trading_days
            FROM portfolios p
            JOIN returns r ON r.portfolio_id = p.portfolio_id
            WHERE r.date >= CURRENT_DATE - INTERVAL '1 year'
            GROUP BY p.portfolio_id, p.name
            ORDER BY avg_return DESC
        """,
        pool_size=POOL_CONFIGS["analytics"]["min_connections"],
        max_pool_size=POOL_CONFIGS["analytics"]["max_connections"],
        timeout=POOL_CONFIGS["analytics"]["command_timeout"]
    )
    print(f"  Query: Annual portfolio performance")
    print(f"  Pool: analytics (5-20 connections)")
    print(f"  Timeout: {POOL_CONFIGS['analytics']['command_timeout']}s (long queries)\n")
    
    # Vector pool - AI/ML workloads
    print("Vector Pool Usage - AI workloads:")
    from kailash.nodes.data import AsyncPostgreSQLVectorNode
    
    vector_search = AsyncPostgreSQLVectorNode(
        name="similar_portfolio_search",
        connection_string="postgresql://localhost/tpc_vectordb",
        table_name="portfolio_embeddings",
        operation="search",
        distance_metric="cosine",
        limit=10,
        pool_size=POOL_CONFIGS["vector"]["min_connections"],
        max_pool_size=POOL_CONFIGS["vector"]["max_connections"],
        tenant_id="tpc"  # Multi-tenant support
    )
    print(f"  Query: Portfolio similarity search")
    print(f"  Pool: vector (5-30 connections)")
    print(f"  Timeout: {POOL_CONFIGS['vector']['command_timeout']}s\n")
    
    print("\n3. Pool Monitoring Example:\n")
    
    # Simulate pool metrics
    mock_metrics = {
        "main": {
            "total_connections": 25,
            "active_connections": 18,
            "idle_connections": 7,
            "total_requests": 15420,
            "failed_requests": 3,
            "avg_wait_time": 0.045,
            "is_healthy": True
        },
        "analytics": {
            "total_connections": 12,
            "active_connections": 8,
            "idle_connections": 4,
            "total_requests": 342,
            "failed_requests": 0,
            "avg_wait_time": 0.23,
            "is_healthy": True
        },
        "vector": {
            "total_connections": 15,
            "active_connections": 10,
            "idle_connections": 5,
            "total_requests": 8765,
            "failed_requests": 12,
            "avg_wait_time": 0.087,
            "is_healthy": True
        }
    }
    
    for pool_name, metrics in mock_metrics.items():
        print(f"{pool_name.capitalize()} Pool Metrics:")
        print(f"  Connections: {metrics['active_connections']}/{metrics['total_connections']} active")
        print(f"  Requests: {metrics['total_requests']:,} total, {metrics['failed_requests']} failed")
        print(f"  Avg wait time: {metrics['avg_wait_time']*1000:.1f}ms")
        print(f"  Health: {'✅ Healthy' if metrics['is_healthy'] else '❌ Unhealthy'}")
        
        # Check if pool is near capacity
        usage = metrics['active_connections'] / POOL_CONFIGS[pool_name]["max_connections"]
        if usage > 0.8:
            print(f"  ⚠️  WARNING: Pool at {usage*100:.1f}% capacity!")
        print()
    
    print("\n4. Performance Optimization Tips:\n")
    print("- Use connection affinity: Route similar queries to same pool")
    print("- Monitor pool usage: Alert at 80% capacity")
    print("- Tune pool sizes based on actual usage patterns")
    print("- Use prepared statements for frequently executed queries")
    print("- Implement query result caching for read-heavy workloads")


async def demonstrate_concurrent_execution():
    """Demonstrate handling 500+ concurrent operations."""
    print("\n\n=== Concurrent Execution Pattern Demo ===\n")
    
    # Create workflow with pooled connections
    workflow = Workflow(name="concurrent_analysis")
    
    # Add node with main pool configuration
    query_node = AsyncSQLDatabaseNode(
        name="concurrent_query",
        database_type="postgresql",
        connection_string="postgresql://localhost/tpc_db",
        query="SELECT portfolio_id, total_value FROM portfolios WHERE active = true",
        pool_size=POOL_CONFIGS["main"]["min_connections"],
        max_pool_size=POOL_CONFIGS["main"]["max_connections"]
    )
    
    workflow.add_node("query", query_node)
    
    print("Simulating 500+ concurrent workflow executions...")
    print("(In production, this would use real database connections)\n")
    
    # Simulate execution pattern from migration guide
    async def simulate_concurrent_load():
        # Create runtime with high concurrency
        runtime = AsyncLocalRuntime(max_concurrency=50)
        
        # Simulate portfolio IDs
        portfolio_ids = [f"PORT{i:04d}" for i in range(100)]  # Reduced for demo
        
        # Mock execution results
        results = {
            'successful': 98,
            'failed': 2,
            'avg_execution_time': 0.234,
            'total_time': 4.68
        }
        
        print(f"Execution Summary:")
        print(f"  Total portfolios: {len(portfolio_ids)}")
        print(f"  Successful: {results['successful']}")
        print(f"  Failed: {results['failed']}")
        print(f"  Average execution time: {results['avg_execution_time']}s")
        print(f"  Total time: {results['total_time']}s")
        print(f"  Throughput: {len(portfolio_ids)/results['total_time']:.1f} portfolios/second")
        
        return results
    
    await simulate_concurrent_load()


# Caching strategy from migration guide lines 831-847
CACHE_CONFIGS = {
    "portfolio_data": {
        "ttl": 300,  # 5 minutes
        "pattern": "portfolio:{portfolio_id}"
    },
    "user_permissions": {
        "ttl": 600,  # 10 minutes
        "pattern": "permissions:{user_id}"
    },
    "ai_results": {
        "ttl": 3600,  # 1 hour
        "pattern": "ai:{workflow_id}:{hash}"
    }
}


def demonstrate_caching_strategy():
    """Show caching configuration from migration guide."""
    print("\n\n=== Caching Strategy Demo ===\n")
    
    print("Redis caching configuration for TPC:")
    for cache_type, config in CACHE_CONFIGS.items():
        print(f"\n{cache_type}:")
        print(f"  TTL: {config['ttl']}s ({config['ttl']/60:.1f} minutes)")
        print(f"  Key pattern: {config['pattern']}")
        
        # Example usage
        if cache_type == "portfolio_data":
            print(f"  Example key: portfolio:PORT123")
            print(f"  Use case: Cache frequently accessed portfolio data")
        elif cache_type == "user_permissions":
            print(f"  Example key: permissions:analyst_001")
            print(f"  Use case: Reduce permission checks overhead")
        elif cache_type == "ai_results":
            print(f"  Example key: ai:portfolio_analysis:a3f8b2c1")
            print(f"  Use case: Cache expensive AI computations")


if __name__ == "__main__":
    # Run all demonstrations
    asyncio.run(demonstrate_pool_usage())
    asyncio.run(demonstrate_concurrent_execution())
    demonstrate_caching_strategy()
    
    print("\n\n=== Demo Complete ===")
    print("This configuration supports the TPC requirement of 500+ concurrent users")
    print("with long-running workflows (5+ minutes) and high I/O operations.")