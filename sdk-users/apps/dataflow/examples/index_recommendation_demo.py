#!/usr/bin/env python3
"""
DataFlow Index Recommendation Engine Demo

Demonstrates the advanced database index recommendation system that analyzes
workflow patterns and suggests optimal indexes for maximum performance improvement.

Features:
- Pattern-based index recommendations
- Multi-database support (PostgreSQL, MySQL, SQLite)
- Composite and covering index optimization
- Performance impact estimation
- Implementation planning
"""

import os
import sys

# Add the DataFlow app to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from dataflow.optimization import SQLDialect, SQLQueryOptimizer, WorkflowAnalyzer
from dataflow.optimization.index_recommendation_engine import (
    IndexPriority,
    IndexRecommendationEngine,
    IndexType,
)


def create_sample_workflow():
    """Create a sample e-commerce workflow for index analysis."""
    return {
        "nodes": {
            "customer_query": {
                "type": "CustomerListNode",
                "parameters": {
                    "table": "customers",
                    "filter": {
                        "status": "active",
                        "tier": "premium",
                        "region": "north_america",
                    },
                },
            },
            "order_query": {
                "type": "OrderListNode",
                "parameters": {
                    "table": "orders",
                    "filter": {
                        "status": "completed",
                        "created_at": "last_quarter",
                        "total": {"$gt": 100},
                    },
                },
            },
            "product_query": {
                "type": "ProductListNode",
                "parameters": {
                    "table": "products",
                    "filter": {
                        "category": "electronics",
                        "in_stock": True,
                        "price": {"$lt": 1000},
                    },
                },
            },
            "customer_order_merge": {
                "type": "SmartMergeNode",
                "parameters": {
                    "merge_type": "inner",
                    "join_conditions": {"left_key": "id", "right_key": "customer_id"},
                },
            },
            "order_product_merge": {
                "type": "SmartMergeNode",
                "parameters": {
                    "merge_type": "inner",
                    "join_conditions": {"left_key": "product_id", "right_key": "id"},
                },
            },
            "sales_analysis": {
                "type": "AggregateNode",
                "parameters": {
                    "aggregate_expression": "sum of total, count of orders, avg of total",
                    "group_by": ["customer_region", "product_category", "order_month"],
                    "having": {"sum_total": {"$gt": 10000}},
                    "order_by": [{"sum_total": "desc"}],
                },
            },
            "high_value_filter": {
                "type": "NaturalLanguageFilterNode",
                "parameters": {"filter_expression": "high value customers"},
            },
            "recent_orders_filter": {
                "type": "NaturalLanguageFilterNode",
                "parameters": {"filter_expression": "orders from last month"},
            },
        },
        "connections": [
            {"from_node": "customer_query", "to_node": "customer_order_merge"},
            {"from_node": "order_query", "to_node": "customer_order_merge"},
            {"from_node": "customer_order_merge", "to_node": "order_product_merge"},
            {"from_node": "product_query", "to_node": "order_product_merge"},
            {"from_node": "order_product_merge", "to_node": "high_value_filter"},
            {"from_node": "high_value_filter", "to_node": "recent_orders_filter"},
            {"from_node": "recent_orders_filter", "to_node": "sales_analysis"},
        ],
    }


def demonstrate_index_recommendation():
    """Demonstrate the complete index recommendation pipeline."""
    print("🚀 DataFlow Index Recommendation Engine Demo")
    print("=" * 60)

    # Step 1: Create and analyze workflow
    print("\n📋 Step 1: Workflow Analysis")
    print("-" * 30)

    workflow = create_sample_workflow()
    print(
        f"Analyzing workflow with {len(workflow['nodes'])} nodes and {len(workflow['connections'])} connections"
    )

    analyzer = WorkflowAnalyzer()
    opportunities = analyzer.analyze_workflow(workflow)

    print(f"Found {len(opportunities)} optimization opportunities:")
    for i, opp in enumerate(opportunities, 1):
        print(f"  {i}. {opp.pattern_type.value}: {opp.estimated_improvement}")
        print(f"     Nodes: {', '.join(opp.nodes_involved)}")

    # Step 2: Generate optimized SQL
    print("\n🛠️ Step 2: SQL Query Generation")
    print("-" * 32)

    sql_optimizer = SQLQueryOptimizer(dialect=SQLDialect.POSTGRESQL)
    optimized_queries = sql_optimizer.optimize_workflow(opportunities)

    print(f"Generated {len(optimized_queries)} optimized SQL queries")

    # Show sample query
    if optimized_queries:
        sample_query = optimized_queries[0]
        print("\nSample optimized query:")
        print(f"Original nodes: {', '.join(sample_query.original_nodes)}")
        print(f"SQL: {sample_query.optimized_sql[:100]}...")

    # Step 3: Index recommendations for different databases
    print("\n📊 Step 3: Index Recommendations")
    print("-" * 33)

    databases = [
        (SQLDialect.POSTGRESQL, "PostgreSQL"),
        (SQLDialect.MYSQL, "MySQL"),
        (SQLDialect.SQLITE, "SQLite"),
    ]

    for dialect, db_name in databases:
        print(f"\n💾 {db_name} Index Recommendations")
        print("-" * (len(db_name) + 25))

        index_engine = IndexRecommendationEngine(dialect=dialect)

        # Simulate existing indexes
        existing_indexes = [
            "idx_customers_email",
            "idx_orders_created_at",
            "idx_products_category",
        ]

        analysis_result = index_engine.analyze_and_recommend(
            opportunities, optimized_queries, existing_indexes
        )

        print("📈 Analysis Summary:")
        print(f"  Total recommendations: {len(analysis_result.recommendations)}")
        print(
            f"  Critical recommendations: {len(analysis_result.missing_critical_indexes)}"
        )
        print(f"  Redundant existing indexes: {len(analysis_result.redundant_indexes)}")
        print(
            f"  Estimated performance gain: {analysis_result.total_estimated_gain:.1f}x"
        )

        # Show top recommendations by priority
        critical_recs = [
            r
            for r in analysis_result.recommendations
            if r.priority == IndexPriority.CRITICAL
        ]
        high_recs = [
            r
            for r in analysis_result.recommendations
            if r.priority == IndexPriority.HIGH
        ]

        if critical_recs:
            print("\n🚨 Critical Indexes (Implement Immediately):")
            for i, rec in enumerate(critical_recs[:3], 1):
                print(f"  {i}. {rec.table_name}.{','.join(rec.column_names)}")
                print(f"     Impact: {rec.estimated_impact}")
                print(f"     SQL: {rec.create_statement}")
                print(f"     Rationale: {rec.rationale}")
                print()

        if high_recs:
            print("⚡ High Priority Indexes:")
            for i, rec in enumerate(high_recs[:2], 1):
                print(
                    f"  {i}. {rec.table_name}.{','.join(rec.column_names)} - {rec.estimated_impact}"
                )

        # Show redundant indexes
        if analysis_result.redundant_indexes:
            print("\n🗑️ Redundant Indexes (Consider Removing):")
            for idx in analysis_result.redundant_indexes:
                print(f"  - {idx}")

    # Step 4: Implementation planning
    print("\n📅 Step 4: Implementation Planning")
    print("-" * 35)

    # Use PostgreSQL for implementation plan
    pg_index_engine = IndexRecommendationEngine(dialect=SQLDialect.POSTGRESQL)
    pg_analysis = pg_index_engine.analyze_and_recommend(
        opportunities, optimized_queries
    )

    implementation_plan = pg_index_engine.generate_implementation_plan(pg_analysis)

    print("Generated implementation plan:")
    print(implementation_plan)

    # Step 5: Performance impact analysis
    print("\n📈 Step 5: Performance Impact Analysis")
    print("-" * 40)

    # Analyze performance impact by index type
    index_type_impact = {}
    total_size_mb = 0

    for rec in pg_analysis.recommendations:
        index_type = rec.index_type.value
        if index_type not in index_type_impact:
            index_type_impact[index_type] = {
                "count": 0,
                "total_gain": 0,
                "total_size": 0,
            }

        index_type_impact[index_type]["count"] += 1
        index_type_impact[index_type]["total_gain"] += rec.performance_gain
        index_type_impact[index_type]["total_size"] += rec.size_estimate_mb
        total_size_mb += rec.size_estimate_mb

    print("Impact by index type:")
    for index_type, stats in index_type_impact.items():
        avg_gain = stats["total_gain"] / stats["count"] if stats["count"] > 0 else 0
        print(f"  {index_type.title()}:")
        print(f"    Count: {stats['count']}")
        print(f"    Avg performance gain: {avg_gain:.1f}x")
        print(f"    Total size: {stats['total_size']:.1f}MB")
        print()

    print(f"Total estimated index size: {total_size_mb:.1f}MB")
    print(f"Total estimated performance gain: {pg_analysis.total_estimated_gain:.1f}x")

    # Step 6: Cost-benefit analysis
    print("\n💰 Step 6: Cost-Benefit Analysis")
    print("-" * 33)

    # Categorize recommendations by cost-benefit ratio
    high_impact_low_cost = []
    high_impact_high_cost = []
    low_impact_low_cost = []

    for rec in pg_analysis.recommendations:
        is_high_impact = rec.performance_gain >= 5.0
        is_high_cost = rec.maintenance_cost == "High" or rec.size_estimate_mb > 50

        if is_high_impact and not is_high_cost:
            high_impact_low_cost.append(rec)
        elif is_high_impact and is_high_cost:
            high_impact_high_cost.append(rec)
        else:
            low_impact_low_cost.append(rec)

    print("Cost-Benefit Classification:")
    print(f"  🎯 High Impact, Low Cost: {len(high_impact_low_cost)} indexes")
    print("     Recommended for immediate implementation")

    print(f"  ⚖️ High Impact, High Cost: {len(high_impact_high_cost)} indexes")
    print("     Evaluate based on usage patterns")

    print(f"  📊 Low Impact, Low Cost: {len(low_impact_low_cost)} indexes")
    print("     Implement when resources allow")

    # Show top cost-effective recommendations
    if high_impact_low_cost:
        print("\n🏆 Most Cost-Effective Recommendations:")
        for i, rec in enumerate(high_impact_low_cost[:3], 1):
            efficiency = rec.performance_gain / max(rec.size_estimate_mb, 1)
            print(f"  {i}. {rec.table_name}.{','.join(rec.column_names)}")
            print(f"     Efficiency: {efficiency:.2f}x per MB")
            print(f"     {rec.estimated_impact}, {rec.size_estimate_mb:.1f}MB")

    # Step 7: Monitoring recommendations
    print("\n📡 Step 7: Monitoring & Maintenance")
    print("-" * 36)

    print("Recommended monitoring after implementation:")
    print("✅ Query performance improvement verification")
    print("✅ Index usage statistics")
    print("✅ Index size growth monitoring")
    print("✅ Maintenance overhead assessment")
    print()

    print("SQL queries for monitoring (PostgreSQL):")
    print("-- Index usage statistics")
    print("SELECT schemaname, tablename, indexname, idx_tup_read, idx_tup_fetch")
    print("FROM pg_stat_user_indexes ORDER BY idx_tup_read DESC;")
    print()
    print("-- Index size monitoring")
    print(
        "SELECT schemaname, tablename, indexname, pg_size_pretty(pg_relation_size(indexrelid))"
    )
    print("FROM pg_stat_user_indexes ORDER BY pg_relation_size(indexrelid) DESC;")

    print("\n✅ Index Recommendation Demo Complete!")
    print("\n💡 Key Benefits:")
    print("  - Automatic index analysis from workflow patterns")
    print("  - Multi-database compatibility")
    print("  - Performance impact estimation")
    print("  - Cost-benefit optimization")
    print("  - Production-ready implementation plans")


def demonstrate_advanced_index_features():
    """Demonstrate advanced index recommendation features."""
    print("\n" + "=" * 60)
    print("🔬 Advanced Index Features Demonstration")
    print("=" * 60)

    # Demonstrate different index types
    print("\n🎯 Index Type Recommendations")
    print("-" * 30)

    index_examples = {
        IndexType.BTREE: "Standard B-tree for equality and range queries",
        IndexType.HASH: "Hash index for exact equality matches",
        IndexType.GIN: "Generalized Inverted Index for full-text search",
        IndexType.GIST: "Generalized Search Tree for geometric data",
        IndexType.PARTIAL: "Partial index for selective filtering",
        IndexType.UNIQUE: "Unique constraint enforcement",
        IndexType.COMPOSITE: "Multi-column index optimization",
        IndexType.COVERING: "Include columns to avoid table lookups",
    }

    for index_type, description in index_examples.items():
        print(f"📊 {index_type.value.upper()}: {description}")

    # Demonstrate priority levels
    print("\n⚡ Priority Classification")
    print("-" * 25)

    priority_examples = {
        IndexPriority.CRITICAL: "Immediate implementation required (>10x impact)",
        IndexPriority.HIGH: "High impact, implement within week (5-10x impact)",
        IndexPriority.MEDIUM: "Moderate impact, implement when possible (2-5x impact)",
        IndexPriority.LOW: "Low impact, implement as resources allow (<2x impact)",
        IndexPriority.OPTIONAL: "Nice to have, lowest priority",
    }

    for priority, description in priority_examples.items():
        print(f"🔥 {priority.value.upper()}: {description}")

    # Demonstrate SQL dialect differences
    print("\n🗄️ Database-Specific Features")
    print("-" * 32)

    print("PostgreSQL:")
    print("  - CONCURRENTLY for non-blocking index creation")
    print("  - Partial indexes with WHERE conditions")
    print("  - INCLUDE columns for covering indexes")
    print("  - GIN/GIST specialized index types")

    print("\nMySQL:")
    print("  - Standard B-tree and Hash indexes")
    print("  - Full-text indexes for search")
    print("  - Composite indexes up to 16 columns")

    print("\nSQLite:")
    print("  - Automatic index optimization")
    print("  - Expression-based indexes")
    print("  - Simple B-tree implementation")

    print("\n🎯 Optimization Strategy Examples")
    print("-" * 35)

    strategies = [
        {
            "pattern": "Query→Merge→Aggregate",
            "indexes": [
                "JOIN column indexes",
                "GROUP BY composite indexes",
                "Covering indexes",
            ],
            "impact": "10-100x faster analytics",
        },
        {
            "pattern": "Multiple Queries",
            "indexes": [
                "Partial indexes",
                "Selective filters",
                "Shared column indexes",
            ],
            "impact": "50% compute reduction",
        },
        {
            "pattern": "Redundant Operations",
            "indexes": ["Cache-optimized indexes", "Frequent access patterns"],
            "impact": "10-50x faster repeated queries",
        },
        {
            "pattern": "Inefficient Joins",
            "indexes": ["Foreign key indexes", "Composite join indexes"],
            "impact": "5-25x faster joins",
        },
    ]

    for strategy in strategies:
        print(f"\n📈 {strategy['pattern']}:")
        print(f"   Recommended indexes: {', '.join(strategy['indexes'])}")
        print(f"   Expected impact: {strategy['impact']}")


def main():
    """Run the index recommendation demonstration."""
    try:
        demonstrate_index_recommendation()
        demonstrate_advanced_index_features()
        return 0
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
