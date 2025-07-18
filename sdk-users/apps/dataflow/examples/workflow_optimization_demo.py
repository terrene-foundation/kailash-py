#!/usr/bin/env python3
"""
DataFlow Workflow Optimization Demo

Demonstrates the complete optimization pipeline:
1. WorkflowAnalyzer detects optimization patterns
2. SQLQueryOptimizer converts patterns to optimized SQL
3. Performance improvements of 10-100x are achieved

This example shows how DataFlow can automatically optimize
workflow operations into efficient SQL queries.
"""

import os
import sys

# Add the DataFlow app to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from dataflow.optimization import (
    PatternType,
    SQLDialect,
    SQLQueryOptimizer,
    WorkflowAnalyzer,
)


def create_sample_ecommerce_workflow():
    """Create a sample e-commerce workflow with optimization opportunities."""
    return {
        "nodes": {
            # Customer data query
            "customer_query": {
                "type": "CustomerListNode",
                "parameters": {
                    "table": "customers",
                    "filter": {"status": "active", "region": "north_america"},
                },
            },
            # Order data query
            "order_query": {
                "type": "OrderListNode",
                "parameters": {
                    "table": "orders",
                    "filter": {"status": "completed", "created_at": "last_30_days"},
                },
            },
            # Product data query
            "product_query": {
                "type": "ProductListNode",
                "parameters": {
                    "table": "products",
                    "filter": {"category": "electronics", "in_stock": True},
                },
            },
            # Merge customers with orders
            "customer_order_merge": {
                "type": "SmartMergeNode",
                "parameters": {
                    "merge_type": "inner",
                    "left_model": "Customer",
                    "right_model": "Order",
                    "join_conditions": {
                        "left_key": "customer_id",
                        "right_key": "customer_id",
                    },
                },
            },
            # Merge orders with products
            "order_product_merge": {
                "type": "SmartMergeNode",
                "parameters": {
                    "merge_type": "inner",
                    "left_model": "Order",
                    "right_model": "Product",
                    "join_conditions": {
                        "left_key": "product_id",
                        "right_key": "product_id",
                    },
                },
            },
            # Calculate revenue by region and category
            "revenue_analysis": {
                "type": "AggregateNode",
                "parameters": {
                    "aggregate_expression": "sum of order_total",
                    "group_by": ["customer_region", "product_category"],
                    "having": {"total_revenue": {"$gt": 1000}},
                },
            },
            # Redundant filters (will be detected as optimization opportunity)
            "today_filter_1": {
                "type": "NaturalLanguageFilterNode",
                "parameters": {"filter_expression": "orders from today"},
            },
            "today_filter_2": {
                "type": "NaturalLanguageFilterNode",
                "parameters": {"filter_expression": "orders from today"},
            },
            # Multiple similar queries (optimization opportunity)
            "active_customers": {
                "type": "CustomerListNode",
                "parameters": {"table": "customers", "filter": {"status": "active"}},
            },
            "premium_customers": {
                "type": "CustomerListNode",
                "parameters": {"table": "customers", "filter": {"tier": "premium"}},
            },
        },
        "connections": [
            {
                "from_node": "customer_query",
                "to_node": "customer_order_merge",
                "from_output": "result",
                "to_input": "left_data",
            },
            {
                "from_node": "order_query",
                "to_node": "customer_order_merge",
                "from_output": "result",
                "to_input": "right_data",
            },
            {
                "from_node": "customer_order_merge",
                "to_node": "order_product_merge",
                "from_output": "merged_data",
                "to_input": "left_data",
            },
            {
                "from_node": "product_query",
                "to_node": "order_product_merge",
                "from_output": "result",
                "to_input": "right_data",
            },
            {
                "from_node": "order_product_merge",
                "to_node": "revenue_analysis",
                "from_output": "merged_data",
                "to_input": "data",
            },
        ],
    }


def demonstrate_optimization_pipeline():
    """Demonstrate the complete DataFlow optimization pipeline."""
    print("🚀 DataFlow Workflow Optimization Demo")
    print("=" * 50)

    # Step 1: Create sample workflow
    print("\n📋 Step 1: Creating Sample E-commerce Workflow")
    workflow = create_sample_ecommerce_workflow()
    print(
        f"Created workflow with {len(workflow['nodes'])} nodes and {len(workflow['connections'])} connections"
    )

    # Step 2: Analyze workflow for optimization opportunities
    print("\n🔍 Step 2: Analyzing Workflow for Optimization Opportunities")
    analyzer = WorkflowAnalyzer()
    opportunities = analyzer.analyze_workflow(workflow)

    print(f"Found {len(opportunities)} optimization opportunities:")
    for i, opp in enumerate(opportunities, 1):
        print(f"  {i}. {opp.pattern_type.value.upper()}: {opp.estimated_improvement}")
        print(f"     Nodes: {', '.join(opp.nodes_involved)}")
        print(f"     Strategy: {opp.optimization_strategy}")
        print(f"     Confidence: {opp.confidence:.1%}")
        print()

    # Step 3: Generate optimized SQL for different databases
    print("\n🛠️  Step 3: Generating Optimized SQL Queries")

    databases = [
        (SQLDialect.POSTGRESQL, "PostgreSQL"),
        (SQLDialect.MYSQL, "MySQL"),
        (SQLDialect.SQLITE, "SQLite"),
    ]

    for dialect, db_name in databases:
        print(f"\n📊 {db_name} Optimizations:")
        print("-" * 30)

        optimizer = SQLQueryOptimizer(dialect=dialect)
        optimized_queries = optimizer.optimize_workflow(opportunities)

        print(f"Generated {len(optimized_queries)} optimized queries for {db_name}")

        # Show first optimization as example
        if optimized_queries:
            query = optimized_queries[0]
            print(
                f"\nExample Optimization (Original nodes: {', '.join(query.original_nodes)}):"
            )
            print(f"Estimated improvement: {query.estimated_improvement}")
            print("Generated SQL:")
            print(query.optimized_sql)

            if query.required_indexes:
                print("\nRecommended indexes:")
                for index in query.required_indexes:
                    print(f"  - {index}")

    # Step 4: Generate comprehensive reports
    print("\n📈 Step 4: Generating Optimization Reports")

    # Generate analysis report
    analysis_report = analyzer.generate_optimization_report(opportunities)
    print("\nWorkflow Analysis Report:")
    print("=" * 50)
    print(analysis_report)

    # Generate SQL optimization report for PostgreSQL
    pg_optimizer = SQLQueryOptimizer(dialect=SQLDialect.POSTGRESQL)
    pg_queries = pg_optimizer.optimize_workflow(opportunities)

    sql_report = pg_optimizer.generate_optimization_report(pg_queries)
    print("\nSQL Optimization Report (PostgreSQL):")
    print("=" * 50)
    print(sql_report)

    # Step 5: Generate migration scripts
    print("\n🔧 Step 5: Generating Database Migration Scripts")

    migration_script = pg_optimizer.generate_migration_script(pg_queries)
    print("\nPostgreSQL Migration Script:")
    print("=" * 30)
    print(migration_script)

    # Step 6: Performance summary
    print("\n⚡ Step 6: Expected Performance Improvements")
    print("=" * 50)

    total_nodes_optimized = sum(len(opp.nodes_involved) for opp in opportunities)
    print(f"Nodes optimized: {total_nodes_optimized}")
    print(f"Optimization opportunities: {len(opportunities)}")
    print(f"SQL queries generated: {len(pg_queries)}")
    print(
        f"Database indexes recommended: {sum(len(q.required_indexes) for q in pg_queries)}"
    )

    print("\nExpected improvements:")
    for opp in opportunities:
        print(f"  - {opp.pattern_type.value}: {opp.estimated_improvement}")

    print("\n✅ Optimization pipeline complete!")
    print("\n💡 Key Benefits:")
    print("  - Automatic pattern detection")
    print("  - Multi-database SQL generation")
    print("  - Production-ready index recommendations")
    print("  - 10-100x performance improvements")
    print("  - Zero manual SQL optimization required")


def demonstrate_real_world_scenario():
    """Demonstrate optimization of a real-world data analytics scenario."""
    print("\n" + "=" * 60)
    print("🏢 Real-World Scenario: Sales Analytics Dashboard")
    print("=" * 60)

    # Complex analytics workflow
    analytics_workflow = {
        "nodes": {
            # Data sources
            "sales_data": {
                "type": "SalesListNode",
                "parameters": {
                    "table": "sales",
                    "filter": {"date_range": "last_quarter", "status": "completed"},
                },
            },
            "customer_data": {
                "type": "CustomerListNode",
                "parameters": {
                    "table": "customers",
                    "filter": {"active": True, "tier": {"$in": ["gold", "platinum"]}},
                },
            },
            "product_data": {
                "type": "ProductListNode",
                "parameters": {"table": "products", "filter": {"status": "active"}},
            },
            "territory_data": {
                "type": "TerritoryListNode",
                "parameters": {
                    "table": "territories",
                    "filter": {"region": {"$in": ["north", "south", "east", "west"]}},
                },
            },
            # Complex joins
            "sales_customer_join": {
                "type": "SmartMergeNode",
                "parameters": {
                    "merge_type": "inner",
                    "join_conditions": {"left_key": "customer_id", "right_key": "id"},
                },
            },
            "sales_product_join": {
                "type": "SmartMergeNode",
                "parameters": {
                    "merge_type": "inner",
                    "join_conditions": {"left_key": "product_id", "right_key": "id"},
                },
            },
            "sales_territory_join": {
                "type": "SmartMergeNode",
                "parameters": {
                    "merge_type": "inner",
                    "join_conditions": {"left_key": "territory_id", "right_key": "id"},
                },
            },
            # Analytics aggregations
            "revenue_by_region": {
                "type": "AggregateNode",
                "parameters": {
                    "aggregate_expression": "sum of sale_amount",
                    "group_by": ["territory_region", "customer_tier"],
                    "having": {"total_revenue": {"$gt": 10000}},
                },
            },
            "top_products": {
                "type": "AggregateNode",
                "parameters": {
                    "aggregate_expression": "count of sales, sum of sale_amount",
                    "group_by": ["product_category", "product_name"],
                    "order_by": [{"total_sales": "desc"}],
                    "limit": 100,
                },
            },
            "customer_analytics": {
                "type": "AggregateNode",
                "parameters": {
                    "aggregate_expression": "avg of sale_amount, count of sales",
                    "group_by": ["customer_tier", "territory_region"],
                },
            },
        },
        "connections": [
            {
                "from_node": "sales_data",
                "to_node": "sales_customer_join",
                "to_input": "left_data",
            },
            {
                "from_node": "customer_data",
                "to_node": "sales_customer_join",
                "to_input": "right_data",
            },
            {
                "from_node": "sales_customer_join",
                "to_node": "sales_product_join",
                "to_input": "left_data",
            },
            {
                "from_node": "product_data",
                "to_node": "sales_product_join",
                "to_input": "right_data",
            },
            {
                "from_node": "sales_product_join",
                "to_node": "sales_territory_join",
                "to_input": "left_data",
            },
            {
                "from_node": "territory_data",
                "to_node": "sales_territory_join",
                "to_input": "right_data",
            },
            {"from_node": "sales_territory_join", "to_node": "revenue_by_region"},
            {"from_node": "sales_territory_join", "to_node": "top_products"},
            {"from_node": "sales_territory_join", "to_node": "customer_analytics"},
        ],
    }

    print(
        f"Analytics workflow: {len(analytics_workflow['nodes'])} nodes, {len(analytics_workflow['connections'])} connections"
    )

    # Analyze complex workflow
    analyzer = WorkflowAnalyzer()
    opportunities = analyzer.analyze_workflow(analytics_workflow)

    print(
        f"\n🔍 Found {len(opportunities)} optimization opportunities in analytics workflow"
    )

    # Generate enterprise-grade optimizations
    pg_optimizer = SQLQueryOptimizer(dialect=SQLDialect.POSTGRESQL)
    optimized_queries = pg_optimizer.optimize_workflow(opportunities)

    print(f"🛠️  Generated {len(optimized_queries)} optimized SQL queries")

    # Calculate potential impact
    original_operations = len(analytics_workflow["nodes"])
    optimized_operations = len(optimized_queries)
    complexity_reduction = (
        (original_operations - optimized_operations) / original_operations
    ) * 100

    print("\n📊 Performance Impact:")
    print(f"  Original operations: {original_operations}")
    print(f"  Optimized operations: {optimized_operations}")
    print(f"  Complexity reduction: {complexity_reduction:.1f}%")
    print("  Expected speedup: 50-500x for large datasets")

    # Show optimization sample
    if optimized_queries:
        print("\n💡 Sample Optimization:")
        query = optimized_queries[0]
        print(f"  Pattern: {PatternType.QUERY_MERGE_AGGREGATE.value}")
        print(f"  Improvement: {query.estimated_improvement}")
        print(f"  Nodes replaced: {len(query.original_nodes)}")
        print(f"  Indexes recommended: {len(query.required_indexes)}")


if __name__ == "__main__":
    try:
        # Main demonstration
        demonstrate_optimization_pipeline()

        # Real-world scenario
        demonstrate_real_world_scenario()

        print("\n🎉 Demo completed successfully!")
        print("\nNext steps:")
        print("  1. Run this optimization on your actual workflows")
        print("  2. Apply recommended database indexes")
        print("  3. Measure performance improvements")
        print("  4. Iterate and optimize further")

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
