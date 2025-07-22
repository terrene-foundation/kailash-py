#!/usr/bin/env python3
"""Working demo of async database operations using real PostgreSQL.

This example demonstrates:
1. Real PostgreSQL connection with connection pooling
2. Async operations for high concurrency
3. Portfolio analysis with real SQL queries
4. No mocked data - actual database operations
"""

import asyncio
import os
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List

from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


class FlattenedAsyncSQLDatabaseNode(AsyncSQLDatabaseNode):
    """Async SQL node that flattens the result structure for easier workflow connections."""

    async def async_run(self, **inputs) -> dict[str, Any]:
        """Execute and flatten the results."""
        result = await super().execute_async(**inputs)
        # Flatten the structure by moving inner result up
        if "result" in result and isinstance(result["result"], dict):
            return result["result"]
        return result


# Database configuration
DB_CONFIG = {
    "database_type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "tpc_db",
    "user": "postgres",
    "password": "postgres",
    "pool_size": 20,
    "max_pool_size": 50,
}


async def setup_database():
    """Set up database with real portfolio data."""
    # Create tables - need to run each command separately due to asyncpg limitation
    commands = [
        "DROP TABLE IF EXISTS portfolio_positions CASCADE",
        "DROP TABLE IF EXISTS market_prices CASCADE",
        "DROP TABLE IF EXISTS portfolio_metadata CASCADE",
        """
        CREATE TABLE portfolio_metadata (
            portfolio_id VARCHAR(50) PRIMARY KEY,
            client_name VARCHAR(100),
            risk_profile VARCHAR(20),
            created_at TIMESTAMP DEFAULT NOW(),
            total_value NUMERIC(15,2)
        )
        """,
        """
        CREATE TABLE portfolio_positions (
            id SERIAL PRIMARY KEY,
            portfolio_id VARCHAR(50) REFERENCES portfolio_metadata(portfolio_id),
            symbol VARCHAR(10),
            quantity INTEGER,
            purchase_price NUMERIC(10,2),
            purchase_date DATE,
            sector VARCHAR(50)
        )
        """,
        """
        CREATE TABLE market_prices (
            symbol VARCHAR(10),
            price_date DATE,
            close_price NUMERIC(10,2),
            volume BIGINT,
            PRIMARY KEY (symbol, price_date)
        )
        """,
        "CREATE INDEX idx_positions_portfolio ON portfolio_positions(portfolio_id)",
        "CREATE INDEX idx_prices_symbol_date ON market_prices(symbol, price_date)",
    ]

    for cmd in commands:
        setup_node = AsyncSQLDatabaseNode(name="setup_tables", **DB_CONFIG, query=cmd)
        await setup_node.execute_async()

    print("✓ Database tables created")

    # Insert sample portfolio data
    portfolios = [
        ("PORT001", "Acme Corporation", "Conservative", 2500000),
        ("PORT002", "TechStart Inc", "Aggressive", 1800000),
        ("PORT003", "Global Investments", "Moderate", 5200000),
        ("PORT004", "Retirement Fund A", "Conservative", 3100000),
        ("PORT005", "Growth Capital", "Aggressive", 4200000),
    ]

    insert_meta = AsyncSQLDatabaseNode(
        name="insert_portfolios",
        **DB_CONFIG,
        query="""
        INSERT INTO portfolio_metadata (portfolio_id, client_name, risk_profile, total_value)
        VALUES ($1, $2, $3, $4)
        """,
    )

    for portfolio in portfolios:
        await insert_meta.execute_async(params=portfolio)

    print(f"✓ Inserted {len(portfolios)} portfolios")

    # Insert positions
    symbols = {
        "Technology": ["AAPL", "MSFT", "GOOGL", "NVDA", "META"],
        "Finance": ["JPM", "BAC", "WFC", "GS", "MS"],
        "Healthcare": ["JNJ", "UNH", "PFE", "CVS", "ABBV"],
        "Consumer": ["AMZN", "TSLA", "WMT", "HD", "NKE"],
        "Energy": ["XOM", "CVX", "COP", "SLB", "OXY"],
    }

    insert_position = AsyncSQLDatabaseNode(
        name="insert_position",
        **DB_CONFIG,
        query="""
        INSERT INTO portfolio_positions (portfolio_id, symbol, quantity, purchase_price, purchase_date, sector)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
    )

    position_count = 0
    for portfolio_id, _, risk_profile, _ in portfolios:
        # Number of positions based on risk profile
        num_positions = {
            "Conservative": random.randint(10, 15),
            "Moderate": random.randint(15, 25),
            "Aggressive": random.randint(20, 35),
        }[risk_profile]

        # Select random stocks
        selected_stocks = []
        for sector, stocks in symbols.items():
            selected_stocks.extend(
                [
                    (stock, sector)
                    for stock in random.sample(stocks, min(3, len(stocks)))
                ]
            )

        random.shuffle(selected_stocks)
        selected_stocks = selected_stocks[:num_positions]

        # Insert positions
        for symbol, sector in selected_stocks:
            quantity = random.randint(100, 5000)
            purchase_price = random.uniform(50, 500)
            purchase_date = datetime.now() - timedelta(days=random.randint(30, 365))

            await insert_position.execute_async(
                params=(
                    portfolio_id,
                    symbol,
                    quantity,
                    purchase_price,
                    purchase_date.date(),
                    sector,
                )
            )
            position_count += 1

    print(f"✓ Inserted {position_count} positions")

    # Insert market prices (last 30 days)
    insert_price = AsyncSQLDatabaseNode(
        name="insert_price",
        **DB_CONFIG,
        query="""
        INSERT INTO market_prices (symbol, price_date, close_price, volume)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (symbol, price_date) DO NOTHING
        """,
    )

    all_symbols = set()
    for stocks in symbols.values():
        all_symbols.update(stocks)

    price_count = 0
    for symbol in all_symbols:
        base_price = random.uniform(50, 500)
        for days_ago in range(30):
            price_date = datetime.now().date() - timedelta(days=days_ago)
            # Add some volatility
            close_price = base_price * (1 + random.uniform(-0.03, 0.03))
            volume = random.randint(1000000, 50000000)

            await insert_price.execute_async(
                params=(symbol, price_date, close_price, volume)
            )
            price_count += 1

    print(f"✓ Inserted {price_count} price records")


async def create_portfolio_analysis_workflow() -> Workflow:
    """Create a real portfolio analysis workflow."""
    workflow = Workflow(workflow_id="portfolio_analysis", name="portfolio_analysis")

    # 1. Fetch all portfolios
    workflow.add_node(
        "fetch_portfolios",
        FlattenedAsyncSQLDatabaseNode(
            **DB_CONFIG,
            query="""
            SELECT
                portfolio_id,
                client_name,
                risk_profile,
                total_value
            FROM portfolio_metadata
            ORDER BY total_value DESC
            """,
            fetch_mode="all",
        ),
    )

    # 2. Calculate current portfolio values
    workflow.add_node(
        "calculate_values",
        FlattenedAsyncSQLDatabaseNode(
            **DB_CONFIG,
            query="""
            WITH latest_prices AS (
                SELECT DISTINCT ON (symbol)
                    symbol, close_price
                FROM market_prices
                ORDER BY symbol, price_date DESC
            )
            SELECT
                p.portfolio_id,
                SUM(p.quantity * lp.close_price) as current_value,
                SUM(p.quantity * p.purchase_price) as cost_basis,
                COUNT(DISTINCT p.symbol) as num_positions,
                COUNT(DISTINCT p.sector) as num_sectors
            FROM portfolio_positions p
            JOIN latest_prices lp ON p.symbol = lp.symbol
            GROUP BY p.portfolio_id
            """,
            fetch_mode="all",
        ),
    )

    # 3. Analyze sector allocation
    workflow.add_node(
        "sector_analysis",
        FlattenedAsyncSQLDatabaseNode(
            **DB_CONFIG,
            query="""
            WITH latest_prices AS (
                SELECT DISTINCT ON (symbol)
                    symbol, close_price
                FROM market_prices
                ORDER BY symbol, price_date DESC
            ),
            portfolio_sectors AS (
                SELECT
                    p.portfolio_id,
                    p.sector,
                    SUM(p.quantity * lp.close_price) as sector_value
                FROM portfolio_positions p
                JOIN latest_prices lp ON p.symbol = lp.symbol
                GROUP BY p.portfolio_id, p.sector
            ),
            portfolio_totals AS (
                SELECT
                    portfolio_id,
                    SUM(sector_value) as total_value
                FROM portfolio_sectors
                GROUP BY portfolio_id
            )
            SELECT
                ps.portfolio_id,
                ps.sector,
                ps.sector_value,
                ROUND((ps.sector_value / pt.total_value * 100)::numeric, 2) as sector_percentage
            FROM portfolio_sectors ps
            JOIN portfolio_totals pt ON ps.portfolio_id = pt.portfolio_id
            ORDER BY ps.portfolio_id, ps.sector_value DESC
            """,
            fetch_mode="all",
        ),
    )

    # 4. Find top performers
    workflow.add_node(
        "top_performers",
        FlattenedAsyncSQLDatabaseNode(
            **DB_CONFIG,
            query="""
            WITH latest_prices AS (
                SELECT DISTINCT ON (symbol)
                    symbol, close_price
                FROM market_prices
                ORDER BY symbol, price_date DESC
            ),
            position_performance AS (
                SELECT
                    p.portfolio_id,
                    p.symbol,
                    p.quantity,
                    p.purchase_price,
                    lp.close_price as current_price,
                    ((lp.close_price - p.purchase_price) / p.purchase_price * 100) as return_pct,
                    (p.quantity * (lp.close_price - p.purchase_price)) as profit_loss
                FROM portfolio_positions p
                JOIN latest_prices lp ON p.symbol = lp.symbol
            )
            SELECT *
            FROM position_performance
            WHERE return_pct > 0
            ORDER BY return_pct DESC
            LIMIT 20
            """,
            fetch_mode="all",
        ),
    )

    # 5. Generate summary report
    def generate_report(portfolios, values, sectors, performers):
        """Generate portfolio analysis report."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_portfolios": len(portfolios),
                "total_aum": sum(p["total_value"] for p in portfolios),
                "average_portfolio_value": sum(p["total_value"] for p in portfolios)
                / len(portfolios),
            },
            "portfolios": [],
            "top_performers": performers[:10],
            "sector_breakdown": {},
        }

        # Build portfolio details
        portfolio_map = {p["portfolio_id"]: p for p in portfolios}
        value_map = {v["portfolio_id"]: v for v in values}

        for portfolio_id, portfolio in portfolio_map.items():
            if portfolio_id in value_map:
                value_data = value_map[portfolio_id]
                roi = (
                    (value_data["current_value"] - value_data["cost_basis"])
                    / value_data["cost_basis"]
                    * 100
                )

                report["portfolios"].append(
                    {
                        "portfolio_id": portfolio_id,
                        "client_name": portfolio["client_name"],
                        "risk_profile": portfolio["risk_profile"],
                        "current_value": float(value_data["current_value"]),
                        "cost_basis": float(value_data["cost_basis"]),
                        "return_pct": round(roi, 2),
                        "num_positions": value_data["num_positions"],
                        "diversification_score": value_data["num_sectors"],
                    }
                )

        # Aggregate sector data
        for sector_data in sectors:
            sector = sector_data["sector"]
            if sector not in report["sector_breakdown"]:
                report["sector_breakdown"][sector] = {
                    "total_value": 0,
                    "portfolio_count": 0,
                    "avg_allocation_pct": 0,
                }

            report["sector_breakdown"][sector]["total_value"] += float(
                sector_data["sector_value"]
            )
            report["sector_breakdown"][sector]["portfolio_count"] += 1
            report["sector_breakdown"][sector]["avg_allocation_pct"] += float(
                sector_data["sector_percentage"]
            )

        # Calculate averages
        for sector in report["sector_breakdown"]:
            count = report["sector_breakdown"][sector]["portfolio_count"]
            report["sector_breakdown"][sector]["avg_allocation_pct"] /= count

        return {"result": report}

    workflow.add_node(
        "generate_report",
        PythonCodeNode.from_function(
            name="generate_report",
            func=generate_report,
            output_schema={"report": "dict"},
        ),
    )

    # Connect the workflow
    workflow.connect("fetch_portfolios", "generate_report", {"data": "portfolios"})
    workflow.connect("calculate_values", "generate_report", {"data": "values"})
    workflow.connect("sector_analysis", "generate_report", {"data": "sectors"})
    workflow.connect("top_performers", "generate_report", {"data": "performers"})

    return workflow


async def main():
    """Run the async demo with real database operations."""
    print("\n🚀 Real-World Async Portfolio Analysis Demo")
    print("=" * 60)
    print("Using actual PostgreSQL with connection pooling")
    print("No mocked data - all operations are real!\n")

    try:
        # Set up database with real data
        print("📊 Setting up database with portfolio data...")
        await setup_database()

        # Create workflow
        print("\n🔧 Creating portfolio analysis workflow...")
        workflow = await create_portfolio_analysis_workflow()

        # Execute with async runtime
        print("\n⚡ Executing workflow with LocalRuntime...")
        runtime = LocalRuntime(enable_async=True)

        start_time = datetime.now()
        result, run_id = await runtime.execute(workflow)
        execution_time = (datetime.now() - start_time).total_seconds()

        # Display results
        print(f"\n✅ Workflow completed in {execution_time:.2f} seconds\n")

        report_wrapper = result["generate_report"]["result"]
        report = report_wrapper["result"]  # Extract the inner result

        print("\n📈 Portfolio Analysis Summary:")
        print("-" * 60)
        print(f"Total Portfolios: {report['summary']['total_portfolios']}")
        print(f"Total AUM: ${report['summary']['total_aum']:,.2f}")
        print(
            f"Average Portfolio: ${report['summary']['average_portfolio_value']:,.2f}"
        )

        print("\n💼 Portfolio Performance:")
        print("-" * 60)
        for portfolio in sorted(
            report["portfolios"], key=lambda x: x["return_pct"], reverse=True
        ):
            print(f"{portfolio['portfolio_id']}: {portfolio['client_name']}")
            print(f"  Current Value: ${portfolio['current_value']:,.2f}")
            print(f"  Return: {portfolio['return_pct']:.2f}%")
            print(
                f"  Positions: {portfolio['num_positions']}, Sectors: {portfolio['diversification_score']}"
            )
            print()

        print("\n🏆 Top 5 Performing Positions:")
        print("-" * 60)
        for i, position in enumerate(report["top_performers"][:5], 1):
            print(f"{i}. {position['symbol']} ({position['portfolio_id']})")
            print(f"   Return: {position['return_pct']:.2f}%")
            print(f"   Profit: ${position['profit_loss']:,.2f}")

        print("\n📊 Sector Allocation Summary:")
        print("-" * 60)
        for sector, data in sorted(
            report["sector_breakdown"].items(),
            key=lambda x: x[1]["total_value"],
            reverse=True,
        ):
            print(f"{sector}:")
            print(f"  Total Value: ${data['total_value']:,.2f}")
            print(f"  Average Allocation: {data['avg_allocation_pct']:.1f}%")

        print("\n✨ Demo completed successfully!")
        print("\nThis demo used:")
        print("- Real PostgreSQL database with connection pooling")
        print("- Async operations for high concurrency")
        print("- Complex SQL queries with CTEs and aggregations")
        print("- No mocked data - all values calculated from database")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.execute(main())
