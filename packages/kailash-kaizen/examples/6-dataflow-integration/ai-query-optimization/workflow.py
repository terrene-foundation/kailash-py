"""
AI Query Optimization Example

Demonstrates natural language to SQL conversion using Kaizen + DataFlow.

This example shows how to use the NLToSQLAgent to convert natural language
queries into DataFlow operations and execute them against a real database.

Example queries:
- "Show me all users who signed up last month"
- "Find products with low inventory and high demand"
- "Get the top 10 customers by revenue"

Prerequisites:
- DataFlow installed: pip install kailash[dataflow]
- PostgreSQL or SQLite database available
"""

from dataclasses import dataclass


@dataclass
class QueryConfig:
    """Configuration for NL query agent."""

    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.2  # Low temp for precise queries
    max_tokens: int = 1000


def setup_database():
    """
    Setup example database with Product model.

    Returns:
        DataFlow instance with Product model
    """
    try:
        from dataflow import DataFlow
    except ImportError:
        raise ImportError(
            "DataFlow not installed. Install with: pip install kailash[dataflow]"
        )

    # Use SQLite for easy demo
    db = DataFlow("sqlite:///ai_query_demo.db", auto_migrate=True)

    # Define product schema
    @db.model
    class Product:
        name: str
        inventory: int
        demand_score: float = None
        category: str = None
        price: float = None

    # Insert sample data (only if database is empty)
    from kailash.runtime.local import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    # Check if data exists
    check_workflow = WorkflowBuilder()
    check_workflow.add_node("ProductListNode", "check", {"limit": 1})

    runtime = LocalRuntime()
    results, _ = runtime.execute(check_workflow.build())

    # Insert sample data if empty
    if not results.get("check"):
        sample_workflow = WorkflowBuilder()
        sample_workflow.add_node(
            "ProductBulkCreateNode",
            "create_products",
            {
                "data": [
                    {
                        "name": "Laptop Pro 15",
                        "inventory": 5,
                        "demand_score": 0.9,
                        "category": "Electronics",
                        "price": 1299.99,
                    },
                    {
                        "name": "Wireless Mouse",
                        "inventory": 150,
                        "demand_score": 0.7,
                        "category": "Electronics",
                        "price": 29.99,
                    },
                    {
                        "name": "USB-C Cable",
                        "inventory": 8,
                        "demand_score": 0.95,
                        "category": "Electronics",
                        "price": 12.99,
                    },
                    {
                        "name": "Office Desk",
                        "inventory": 20,
                        "demand_score": 0.3,
                        "category": "Furniture",
                        "price": 299.99,
                    },
                    {
                        "name": "Ergonomic Chair",
                        "inventory": 3,
                        "demand_score": 0.85,
                        "category": "Furniture",
                        "price": 399.99,
                    },
                ]
            },
        )

        runtime.execute(sample_workflow.build())
        print("✓ Sample data inserted")

    return db


def demonstrate_nl_query():
    """Demonstrate natural language to SQL query conversion."""
    print("\n" + "=" * 60)
    print("AI-Enhanced Natural Language Query Demo")
    print("=" * 60)

    # Setup database
    print("\n1. Setting up database...")
    db = setup_database()

    # Create NL query agent
    print("2. Creating NL to SQL agent...")
    try:
        from kaizen.integrations.dataflow import NLToSQLAgent
    except ImportError:
        print("⚠ NLToSQLAgent not available (DataFlow integration not installed)")
        return

    config = QueryConfig()
    agent = NLToSQLAgent(config=config, db=db)

    print("3. Ready for natural language queries!\n")

    # Example queries
    queries = [
        "Show me products with less than 10 items in stock",
        "Find electronics with high demand",
        "Get all furniture items",
    ]

    for i, query in enumerate(queries, 1):
        print(f"\nQuery {i}: '{query}'")
        print("-" * 60)

        try:
            result = agent.query(query)

            # Show explanation
            print(f"📝 Explanation: {result['explanation']}")

            # Show filter generated
            if result.get("filter"):
                print(f"🔍 Filter: {result['filter']}")

            # Show results
            print(f"📊 Results: {len(result['results'])} items found")

            for product in result["results"]:
                name = product.get("name", "Unknown")
                inventory = product.get("inventory", 0)
                demand = product.get("demand_score", 0)
                category = product.get("category", "N/A")

                print(f"  - {name}")
                print(
                    f"    Category: {category}, Inventory: {inventory}, Demand: {demand}"
                )

        except Exception as e:
            print(f"❌ Error: {e}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


def demonstrate_query_optimization():
    """Demonstrate AI-driven query optimization."""
    print("\n" + "=" * 60)
    print("Query Optimization Demo")
    print("=" * 60)

    try:
        from kaizen.integrations.dataflow import QueryOptimizer
    except ImportError:
        print("⚠ QueryOptimizer not available")
        return

    config = QueryConfig()
    optimizer = QueryOptimizer(config=config)

    # Example query to optimize
    query = {
        "table": "products",
        "filter": {"category": "Electronics", "inventory": {"$lt": 10}},
        "limit": 100,
    }

    print("\n1. Analyzing query...")
    print(f"   Query: {query}")

    result = optimizer.analyze_query(query)

    print("\n2. Optimization suggestions:")
    if result.get("optimizations"):
        for opt in result["optimizations"]:
            print(f"   - {opt}")
    else:
        print("   ✓ Query is already optimal")

    if result.get("index_recommendations"):
        print("\n3. Index recommendations:")
        for idx in result["index_recommendations"]:
            print(f"   - {idx}")

    if "estimated_improvement" in result:
        improvement = result["estimated_improvement"] * 100
        print(f"\n4. Estimated improvement: {improvement:.1f}%")

    print("\n" + "=" * 60)


def main():
    """Run all demonstrations."""
    # Natural language query demo
    demonstrate_nl_query()

    # Query optimization demo
    demonstrate_query_optimization()


if __name__ == "__main__":
    main()
