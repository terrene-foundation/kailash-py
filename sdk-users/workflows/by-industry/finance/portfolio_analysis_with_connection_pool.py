#!/usr/bin/env python3
"""Portfolio Analysis with Production-Grade Connection Pooling.

This example demonstrates:
1. WorkflowConnectionPool for production database operations
2. High-concurrency portfolio analysis
3. Connection health monitoring and auto-recycling
4. Transaction support for data consistency
5. Real-world financial calculations with proper error handling

Key improvements over AsyncSQLDatabaseNode:
- Connection pooling with min/max limits
- Automatic health monitoring
- Fault tolerance with actor-based architecture
- Better performance under load
"""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List

from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import WorkflowConnectionPool
from kailash.runtime import LocalRuntime
from kailash.workflow import Workflow, WorkflowBuilder


class PortfolioAnalysisService:
    """Production portfolio analysis service with connection pooling."""

    def __init__(self):
        # Create connection pool for high-concurrency operations
        self.pool = WorkflowConnectionPool(
            name="portfolio_pool",
            database_type="postgresql",
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 5432)),
            database=os.getenv("DB_NAME", "portfolio_db"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres"),
            min_connections=10,  # Maintain minimum connections
            max_connections=50,  # Scale up to 50 for peak load
            health_threshold=70,  # Recycle connections below 70% health
            pre_warm=True,  # Pre-warm connections based on patterns
        )
        self._initialized = False

    async def initialize(self):
        """Initialize the connection pool and setup database."""
        if not self._initialized:
            await self.pool.process({"operation": "initialize"})
            await self._setup_database()
            self._initialized = True

            # Start monitoring
            asyncio.create_task(self._monitor_pool_health())

    @asynccontextmanager
    async def get_connection(self):
        """Context manager for safe connection handling."""
        conn = await self.pool.process({"operation": "acquire"})
        conn_id = conn["connection_id"]
        try:
            yield conn_id
        finally:
            await self.pool.process({"operation": "release", "connection_id": conn_id})

    async def _setup_database(self):
        """Set up database schema if needed."""
        async with self.get_connection() as conn_id:
            # Check if tables exist
            result = await self.pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'portfolio_metadata'
                    )
                """,
                    "fetch_mode": "one",
                }
            )

            if not result["data"]["exists"]:
                await self._create_tables(conn_id)

    async def _create_tables(self, conn_id):
        """Create portfolio tables."""
        tables = [
            """CREATE TABLE portfolio_metadata (
                portfolio_id VARCHAR(50) PRIMARY KEY,
                client_name VARCHAR(100),
                risk_profile VARCHAR(20),
                created_at TIMESTAMP DEFAULT NOW(),
                total_value NUMERIC(15,2),
                last_rebalanced TIMESTAMP
            )""",
            """CREATE TABLE portfolio_positions (
                id SERIAL PRIMARY KEY,
                portfolio_id VARCHAR(50) REFERENCES portfolio_metadata(portfolio_id),
                symbol VARCHAR(10),
                quantity INTEGER,
                purchase_price NUMERIC(10,2),
                purchase_date DATE,
                sector VARCHAR(50),
                current_value NUMERIC(15,2)
            )""",
            """CREATE TABLE market_prices (
                symbol VARCHAR(10),
                price_date DATE,
                close_price NUMERIC(10,2),
                volume BIGINT,
                volatility NUMERIC(5,2),
                PRIMARY KEY (symbol, price_date)
            )""",
            """CREATE TABLE portfolio_performance (
                portfolio_id VARCHAR(50),
                calculation_date DATE,
                total_value NUMERIC(15,2),
                daily_return NUMERIC(8,4),
                volatility NUMERIC(8,4),
                sharpe_ratio NUMERIC(8,4),
                PRIMARY KEY (portfolio_id, calculation_date)
            )""",
        ]

        for table_sql in tables:
            await self.pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": table_sql,
                    "fetch_mode": "one",
                }
            )

    async def analyze_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        """Analyze a single portfolio with connection pooling."""
        async with self.get_connection() as conn_id:
            # Get portfolio metadata
            portfolio = await self.pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": """
                    SELECT p.*,
                           COUNT(DISTINCT pos.symbol) as position_count,
                           SUM(pos.current_value) as calculated_value
                    FROM portfolio_metadata p
                    LEFT JOIN portfolio_positions pos ON p.portfolio_id = pos.portfolio_id
                    WHERE p.portfolio_id = $1
                    GROUP BY p.portfolio_id
                """,
                    "params": [portfolio_id],
                    "fetch_mode": "one",
                }
            )

            if not portfolio["data"]:
                return {"error": f"Portfolio {portfolio_id} not found"}

            # Get positions with current prices
            positions = await self.pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": """
                    SELECT
                        pos.*,
                        mp.close_price as current_price,
                        mp.volatility,
                        (pos.quantity * mp.close_price) as market_value,
                        ((mp.close_price - pos.purchase_price) / pos.purchase_price * 100) as return_pct
                    FROM portfolio_positions pos
                    JOIN market_prices mp ON pos.symbol = mp.symbol
                    WHERE pos.portfolio_id = $1
                    AND mp.price_date = (
                        SELECT MAX(price_date) FROM market_prices WHERE symbol = pos.symbol
                    )
                    ORDER BY market_value DESC
                """,
                    "params": [portfolio_id],
                    "fetch_mode": "all",
                }
            )

            # Calculate portfolio metrics
            total_value = sum(pos["market_value"] for pos in positions["data"])
            weighted_return = (
                sum(
                    pos["return_pct"] * (pos["market_value"] / total_value)
                    for pos in positions["data"]
                )
                if total_value > 0
                else 0
            )

            # Sector allocation
            sector_allocation = {}
            for pos in positions["data"]:
                sector = pos["sector"]
                if sector not in sector_allocation:
                    sector_allocation[sector] = 0
                sector_allocation[sector] += pos["market_value"]

            return {
                "portfolio_id": portfolio_id,
                "client_name": portfolio["data"]["client_name"],
                "risk_profile": portfolio["data"]["risk_profile"],
                "total_value": float(total_value),
                "position_count": len(positions["data"]),
                "weighted_return": float(weighted_return),
                "top_positions": positions["data"][:5],
                "sector_allocation": {
                    k: {"value": float(v), "percentage": float(v / total_value * 100)}
                    for k, v in sector_allocation.items()
                },
                "analysis_timestamp": datetime.now().isoformat(),
            }

    async def rebalance_portfolio(
        self, portfolio_id: str, target_allocations: Dict[str, float]
    ):
        """Rebalance portfolio using transactions for consistency."""
        async with self.get_connection() as conn_id:
            try:
                # Start transaction
                await self.pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": "BEGIN",
                        "fetch_mode": "one",
                    }
                )

                # Get current positions
                positions = await self.pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        SELECT pos.*, mp.close_price as current_price
                        FROM portfolio_positions pos
                        JOIN market_prices mp ON pos.symbol = mp.symbol
                        WHERE pos.portfolio_id = $1
                        AND mp.price_date = (
                            SELECT MAX(price_date) FROM market_prices WHERE symbol = pos.symbol
                        )
                    """,
                        "params": [portfolio_id],
                        "fetch_mode": "all",
                    }
                )

                # Calculate total portfolio value
                total_value = sum(
                    pos["quantity"] * pos["current_price"] for pos in positions["data"]
                )

                # Generate rebalancing trades
                trades = []
                for sector, target_pct in target_allocations.items():
                    target_value = total_value * target_pct
                    current_value = sum(
                        pos["quantity"] * pos["current_price"]
                        for pos in positions["data"]
                        if pos["sector"] == sector
                    )

                    if abs(current_value - target_value) > 1000:  # Threshold
                        trades.append(
                            {
                                "sector": sector,
                                "current_value": current_value,
                                "target_value": target_value,
                                "adjustment": target_value - current_value,
                            }
                        )

                # Record rebalancing action
                await self.pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        INSERT INTO portfolio_performance
                        (portfolio_id, calculation_date, total_value, daily_return)
                        VALUES ($1, CURRENT_DATE, $2, 0)
                        ON CONFLICT (portfolio_id, calculation_date)
                        DO UPDATE SET total_value = EXCLUDED.total_value
                    """,
                        "params": [portfolio_id, total_value],
                        "fetch_mode": "one",
                    }
                )

                # Update last rebalanced date
                await self.pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        UPDATE portfolio_metadata
                        SET last_rebalanced = NOW()
                        WHERE portfolio_id = $1
                    """,
                        "params": [portfolio_id],
                        "fetch_mode": "one",
                    }
                )

                # Commit transaction
                await self.pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": "COMMIT",
                        "fetch_mode": "one",
                    }
                )

                return {
                    "portfolio_id": portfolio_id,
                    "total_value": float(total_value),
                    "trades": trades,
                    "status": "rebalanced",
                }

            except Exception as e:
                # Rollback on error
                await self.pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": "ROLLBACK",
                        "fetch_mode": "one",
                    }
                )
                raise

    async def _monitor_pool_health(self):
        """Monitor connection pool health in background."""
        while self._initialized:
            try:
                stats = await self.pool.process({"operation": "stats"})

                # Log metrics
                print(
                    f"""
Pool Health Report:
- Active connections: {stats['current_state']['active_connections']}/{stats['current_state']['total_connections']}
- Queries executed: {stats['queries']['executed']}
- Error rate: {stats['queries']['error_rate']:.2%}
- Pool efficiency: {stats['queries']['executed'] / max(1, stats['connections']['created']):.1f} queries/connection
                """
                )

                # Alert on issues
                if stats["queries"]["error_rate"] > 0.05:
                    print(
                        f"⚠️  WARNING: High error rate detected: {stats['queries']['error_rate']:.2%}"
                    )

                if stats["current_state"]["available_connections"] == 0:
                    print("⚠️  WARNING: Connection pool exhausted!")

                await asyncio.sleep(60)  # Check every minute

            except Exception as e:
                print(f"Error monitoring pool: {e}")
                await asyncio.sleep(60)


# Create workflow using the service
def create_portfolio_analysis_workflow():
    """Create a workflow for portfolio analysis using connection pooling."""
    workflow = WorkflowBuilder("portfolio_analysis")

    # Initialize service
    workflow.add_node(
        "init_service",
        "PythonCodeNode",
        {
            "code": """
service = PortfolioAnalysisService()
await service.initialize()
result = {"service": service, "status": "initialized"}
""",
            "imports": ["PortfolioAnalysisService"],
        },
    )

    # Analyze multiple portfolios concurrently
    workflow.add_node(
        "analyze_portfolios",
        "PythonCodeNode",
        {
            "code": """
portfolio_ids = inputs.get("portfolio_ids", ["PORT001", "PORT002", "PORT003"])

# Analyze portfolios concurrently using the connection pool
analyses = await asyncio.gather(*[
    service.analyze_portfolio(pid) for pid in portfolio_ids
])

# Get pool statistics
stats = await service.pool.process({"operation": "stats"})

result = {
    "analyses": analyses,
    "pool_stats": {
        "total_queries": stats["queries"]["executed"],
        "connections_used": stats["connections"]["created"],
        "efficiency": stats["queries"]["executed"] / max(1, stats["connections"]["created"])
    }
}
""",
            "imports": ["asyncio"],
            "inputs": {
                "service": "{{init_service.result.service}}",
                "portfolio_ids": [
                    "PORT001",
                    "PORT002",
                    "PORT003",
                    "PORT004",
                    "PORT005",
                ],
            },
        },
    )

    # Generate report
    workflow.add_node(
        "generate_report",
        "PythonCodeNode",
        {
            "code": """
analyses = inputs["analyses"]

# Summary statistics
total_aum = sum(a["total_value"] for a in analyses if "error" not in a)
avg_return = sum(a["weighted_return"] for a in analyses if "error" not in a) / len(analyses)

report = {
    "report_date": datetime.now().isoformat(),
    "portfolios_analyzed": len(analyses),
    "total_aum": total_aum,
    "average_return": avg_return,
    "pool_efficiency": inputs["pool_stats"]["efficiency"],
    "top_performers": sorted(
        [a for a in analyses if "error" not in a],
        key=lambda x: x["weighted_return"],
        reverse=True
    )[:3]
}

result = report
""",
            "imports": ["datetime"],
            "inputs": {
                "analyses": "{{analyze_portfolios.result.analyses}}",
                "pool_stats": "{{analyze_portfolios.result.pool_stats}}",
            },
        },
    )

    # Connect workflow
    workflow.add_connection(
        "init_service", "analyze_portfolios", "result.service", "service"
    )
    workflow.add_connection("analyze_portfolios", "generate_report")

    return workflow.build()


async def main():
    """Run the portfolio analysis workflow."""
    # Create workflow
    workflow = create_portfolio_analysis_workflow()

    # Execute with runtime
    runtime = LocalRuntime()
    result = await runtime.execute_async(
        workflow,
        parameters={
            "portfolio_ids": ["PORT001", "PORT002", "PORT003", "PORT004", "PORT005"]
        },
    )

    # Display results
    report = result["generate_report"]["result"]
    print(
        f"""
Portfolio Analysis Report
========================
Date: {report['report_date']}
Portfolios Analyzed: {report['portfolios_analyzed']}
Total AUM: ${report['total_aum']:,.2f}
Average Return: {report['average_return']:.2f}%

Connection Pool Efficiency: {report['pool_efficiency']:.1f} queries/connection

Top Performers:
"""
    )
    for i, portfolio in enumerate(report["top_performers"], 1):
        print(f"{i}. {portfolio['client_name']} ({portfolio['portfolio_id']})")
        print(f"   Return: {portfolio['weighted_return']:.2f}%")
        print(f"   Value: ${portfolio['total_value']:,.2f}")


if __name__ == "__main__":
    asyncio.run(main())
