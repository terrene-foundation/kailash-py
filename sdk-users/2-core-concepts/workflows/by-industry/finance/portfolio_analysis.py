#!/usr/bin/env python3
"""Portfolio Analysis Workflow - TPC Migration Pattern.

This example demonstrates the exact pattern from the comprehensive migration guide
for implementing a portfolio analysis workflow using async database operations,
vector similarity search, and AI insights generation.

Based on comprehensive-migration-guide.md lines 456-488.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List

from kailash.access_control import AccessControlManager, UserContext
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import AsyncPostgreSQLVectorNode, AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow, WorkflowBuilder


def calculate_risk_metrics(portfolio_data: dict) -> dict:
    """Calculate risk metrics for portfolio."""
    # Simulate risk calculations
    total_value = sum(
        inv.get("value", 0) for inv in portfolio_data.get("investments", [])
    )

    # Mock calculations - in production these would be real financial formulas
    risk_score = min(0.7 + (total_value / 10000000) * 0.2, 1.0)  # Scale based on size
    volatility = 0.15 + (risk_score * 0.1)
    sharpe_ratio = 1.2 - (volatility * 2)
    var_95 = total_value * volatility * 1.645  # 95% VaR

    return {
        "result": {
            "portfolio_id": portfolio_data.get("portfolio_id"),
            "risk_score": round(risk_score, 3),
            "volatility": round(volatility, 3),
            "sharpe_ratio": round(sharpe_ratio, 3),
            "var_95": round(var_95, 2),
            "calculated_at": datetime.now().isoformat(),
        }
    }


def create_portfolio_analysis_workflow():
    """
    Portfolio Analysis Value Flow

    Business Value: Analyze portfolio performance and risk metrics
    ABC Usage: Direct mapping from client requirement to this workflow
    Platform Team: Can extend with new nodes as needed

    Steps:
    1. Fetch portfolio data (AsyncSQLDatabaseNode)
    2. Calculate risk metrics (PythonCodeNode)
    3. Find similar portfolios (AsyncPostgreSQLVectorNode)
    4. Generate AI insights (LLMAgentNode)
    5. Store results (AsyncSQLDatabaseNode)

    This maintains 1-1 mapping with business process
    """
    builder = WorkflowBuilder("portfolio_analysis")

    # Step 1: Fetch portfolio data
    data_fetch = AsyncSQLDatabaseNode(
        name="fetch_portfolio",
        database_type="postgresql",
        connection_string="postgresql://test@localhost/tpc_db",
        query="""
            SELECT
                p.portfolio_id,
                p.name,
                p.total_value,
                json_agg(
                    json_build_object(
                        'investment_id', i.id,
                        'name', i.name,
                        'value', i.current_value,
                        'type', i.investment_type
                    )
                ) as investments
            FROM portfolios p
            LEFT JOIN investments i ON i.portfolio_id = p.portfolio_id
            WHERE p.portfolio_id = :portfolio_id
            GROUP BY p.portfolio_id, p.name, p.total_value
        """,
        fetch_mode="one",
        pool_size=10,
        max_pool_size=50,  # Main pool configuration
        timeout=60.0,
    )

    # Step 2: Calculate risk metrics
    risk_calc = PythonCodeNode.from_function(
        name="calculate_risk",
        func=calculate_risk_metrics,
        output_schema={
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "risk_score": {"type": "number"},
                "volatility": {"type": "number"},
                "sharpe_ratio": {"type": "number"},
                "var_95": {"type": "number"},
                "calculated_at": {"type": "string"},
            },
        },
    )

    # Step 3: Find similar portfolios based on risk profile
    similarity = AsyncPostgreSQLVectorNode(
        name="find_similar_portfolios",
        connection_string="postgresql://test@localhost/tpc_vectordb",
        table_name="portfolio_embeddings",
        operation="search",
        distance_metric="cosine",
        limit=5,
        pool_size=5,
        max_pool_size=30,  # Vector pool configuration
        ef_search=40,  # HNSW optimization
        metadata_filter="metadata->>'active' = 'true'",
    )

    # Step 4: Generate AI insights
    ai_analysis = LLMAgentNode(
        name="generate_insights",
        agent_type="analyst",
        system_prompt="""You are a senior investment analyst. Analyze the portfolio risk metrics
        and similar portfolios to provide actionable insights and recommendations.""",
        model="gpt-4",
        temperature=0.7,
        max_tokens=500,
    )

    # Step 5: Store analysis results
    result_store = AsyncSQLDatabaseNode(
        name="store_results",
        database_type="postgresql",
        connection_string="postgresql://test@localhost/tpc_db",
        query="""
            INSERT INTO portfolio_analysis (
                portfolio_id,
                risk_score,
                volatility,
                sharpe_ratio,
                var_95,
                similar_portfolios,
                ai_insights,
                analyzed_at,
                analyzed_by
            ) VALUES (
                :portfolio_id,
                :risk_score,
                :volatility,
                :sharpe_ratio,
                :var_95,
                :similar_portfolios::jsonb,
                :ai_insights,
                :analyzed_at,
                :analyzed_by
            )
            ON CONFLICT (portfolio_id)
            DO UPDATE SET
                risk_score = EXCLUDED.risk_score,
                volatility = EXCLUDED.volatility,
                sharpe_ratio = EXCLUDED.sharpe_ratio,
                var_95 = EXCLUDED.var_95,
                similar_portfolios = EXCLUDED.similar_portfolios,
                ai_insights = EXCLUDED.ai_insights,
                analyzed_at = EXCLUDED.analyzed_at,
                analyzed_by = EXCLUDED.analyzed_by
            RETURNING id
        """,
        fetch_mode="one",
        pool_size=10,
        max_pool_size=50,
    )

    # Build workflow with connections
    workflow = (
        builder.add_nodes(
            [data_fetch, risk_calc, similarity, ai_analysis, result_store]
        )
        .connect("fetch_portfolio", "calculate_risk", {"data": "portfolio_data"})
        .connect(
            "calculate_risk",
            "find_similar_portfolios",
            {"risk_score": "vector[0]", "volatility": "vector[1]"},
        )
        .connect("calculate_risk", "generate_insights", {"metrics": "context"})
        .connect("find_similar_portfolios", "generate_insights", {"similar": "context"})
        .connect(
            "calculate_risk",
            "store_results",
            mapping={
                "portfolio_id": "portfolio_id",
                "risk_score": "risk_score",
                "volatility": "volatility",
                "sharpe_ratio": "sharpe_ratio",
                "var_95": "var_95",
            },
        )
        .connect(
            "find_similar_portfolios",
            "store_results",
            {"matches": "similar_portfolios"},
        )
        .connect("generate_insights", "store_results", {"response": "ai_insights"})
        .build()
    )

    return workflow


async def execute_portfolio_analysis(portfolio_ids: List[str]):
    """
    High-performance pattern for concurrent analysis from migration guide.
    Lines 553-580 of comprehensive-migration-guide.md
    """
    workflow = create_portfolio_analysis_workflow()
    runtime = LocalRuntime(max_concurrency=50, enable_async=True)

    # Execute multiple workflows concurrently
    tasks = [
        runtime.execute(workflow, parameters={"portfolio_id": pid})
        for pid in portfolio_ids
    ]

    # Gather results with error handling
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    successful = [r for r in results if not isinstance(r, Exception)]
    failed = [r for r in results if isinstance(r, Exception)]

    return {"successful": len(successful), "failed": len(failed), "results": successful}


# Pool configuration from migration guide lines 801-821
POOL_CONFIGS = {
    "main": {
        "min_connections": 10,
        "max_connections": 50,
        "pool_timeout": 30,
        "command_timeout": 60,
    },
    "analytics": {
        "min_connections": 5,
        "max_connections": 20,
        "pool_timeout": 60,
        "command_timeout": 300,  # Long queries
    },
    "vector": {
        "min_connections": 5,
        "max_connections": 30,
        "pool_timeout": 30,
        "command_timeout": 120,
    },
}


async def demo_with_mocked_data():
    """Demonstrate the workflow with mocked responses."""
    print("=== TPC Portfolio Analysis Workflow Demo ===\n")

    # Create workflow
    workflow = create_portfolio_analysis_workflow()
    print(f"Created workflow with {len(workflow.nodes)} nodes")

    # Mock the database responses
    from unittest.mock import AsyncMock, patch

    # Create test portfolio data
    test_portfolio = {
        "portfolio_id": "PORT123",
        "name": "Growth Portfolio Alpha",
        "total_value": 5000000.0,
        "investments": [
            {
                "investment_id": "INV001",
                "name": "Tech Stock A",
                "value": 2000000,
                "type": "equity",
            },
            {
                "investment_id": "INV002",
                "name": "Bond Fund B",
                "value": 1500000,
                "type": "fixed_income",
            },
            {
                "investment_id": "INV003",
                "name": "REIT C",
                "value": 1500000,
                "type": "real_estate",
            },
        ],
    }

    # Mock similar portfolios
    similar_portfolios = [
        {
            "id": "PORT456",
            "distance": 0.05,
            "metadata": {"name": "Growth Portfolio Beta"},
        },
        {"id": "PORT789", "distance": 0.12, "metadata": {"name": "Balanced Growth"}},
    ]

    # Patch the async nodes
    with patch.object(AsyncSQLDatabaseNode, "async_run") as mock_sql:
        with patch.object(AsyncPostgreSQLVectorNode, "async_run") as mock_vector:
            with patch.object(LLMAgentNode, "run") as mock_llm:

                # Configure mocks
                mock_sql.side_effect = [
                    # First call: fetch portfolio
                    {"result": {"data": test_portfolio}},
                    # Second call: store results
                    {"result": {"data": {"id": 12345}}},
                ]

                # Mock vector search to expect risk metrics as vector
                mock_vector.return_value = {
                    "result": {
                        "matches": similar_portfolios,
                        "count": len(similar_portfolios),
                    }
                }

                # Mock AI insights
                mock_llm.return_value = {
                    "result": {
                        "response": """Based on the portfolio analysis:

                        1. Risk Profile: The portfolio shows moderate-high risk (0.85) with reasonable volatility (0.235).
                        2. Similar Portfolios: Comparable portfolios have shown 12-15% annual returns.
                        3. Recommendations:
                           - Consider diversifying into international markets
                           - The Sharpe ratio of 0.73 suggests room for optimization
                           - Current VaR of $1.94M is within acceptable limits

                        Overall assessment: Well-balanced growth portfolio with acceptable risk levels."""
                    }
                }

                # Create runtime
                runtime = LocalRuntime(enable_async=True)

                # Execute workflow
                print("\nExecuting portfolio analysis for PORT123...")
                try:
                    results = await runtime.execute(
                        workflow,
                        parameters={
                            "portfolio_id": "PORT123",
                            "analyzed_by": "demo_user",
                            "analyzed_at": datetime.now().isoformat(),
                        },
                    )

                    print("\n✅ Workflow completed successfully!")

                    # Display results from each node
                    if "calculate_risk" in results:
                        risk_metrics = results["calculate_risk"]["result"]
                        print("\nRisk Metrics:")
                        print(f"  Risk Score: {risk_metrics['risk_score']}")
                        print(f"  Volatility: {risk_metrics['volatility']}")
                        print(f"  Sharpe Ratio: {risk_metrics['sharpe_ratio']}")
                        print(f"  VaR (95%): ${risk_metrics['var_95']:,.2f}")

                    if "find_similar_portfolios" in results:
                        similar = results["find_similar_portfolios"]["result"]
                        print(f"\nFound {similar['count']} similar portfolios")

                    if "generate_insights" in results:
                        insights = results["generate_insights"]["result"]
                        print("\nAI Insights Preview:")
                        print(insights["response"][:200] + "...")

                except Exception as e:
                    print(f"\n❌ Workflow failed: {e}")
                    import traceback

                    traceback.print_exc()


async def demo_with_access_control():
    """Demonstrate ABAC integration following migration guide patterns."""
    print("\n\n=== Portfolio Analysis with ABAC Demo ===\n")

    # Create access control manager
    acm = AccessControlManager(strategy="abac")

    # Create user with attributes (migration guide lines 341-348)
    user = UserContext(
        user_id="analyst_001",
        tenant_id="tpc",
        email="john.analyst@tpc.com",
        roles=["analyst"],
        attributes={
            "department": "investment_banking",
            "security_clearance": "secret",
            "project_access": ["PORT123", "PORT456"],
            "data_classification": "confidential",
            "geographic_region": "APAC",
            "cost_center": "IB-001",
        },
    )

    print(f"User: {user.email}")
    print(f"Department: {user.attributes['department']}")
    print(f"Security Clearance: {user.attributes['security_clearance']}")
    print(f"Project Access: {user.attributes['project_access']}")

    # Simulate access check
    print("\n✅ User has required attributes for portfolio analysis")


if __name__ == "__main__":
    # Run demonstrations
    asyncio.execute(demo_with_mocked_data())
    asyncio.execute(demo_with_access_control())
