#!/usr/bin/env python3
"""Real Portfolio Analysis Workflow with Live Database and LLM.

This example demonstrates a real working implementation of the TPC migration
pattern using actual PostgreSQL with pgvector and Ollama for AI insights.

Requires:
- PostgreSQL with pgvector running on localhost:5432
- Ollama with a model installed (e.g., mistral, llama3.2)
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List

import numpy as np
from kailash.access_control import (
    AccessControlManager,
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
)
from kailash.nodes.ai import EmbeddingGeneratorNode, LLMAgentNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import AsyncPostgreSQLVectorNode, AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import NodeExecutionError
from kailash.workflow import Workflow, WorkflowBuilder

# Database connection string
DB_CONN = "postgresql://postgres:postgres@localhost:5432/tpc_db"


async def setup_database():
    """Set up the database schema for the demo."""
    setup_node = AsyncSQLDatabaseNode(
        name="setup_db",
        database_type="postgresql",
        connection_string=DB_CONN,
        query="""
        -- Create portfolios table
        CREATE TABLE IF NOT EXISTS portfolios (
            portfolio_id VARCHAR(50) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            total_value NUMERIC(15,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Create investments table
        CREATE TABLE IF NOT EXISTS investments (
            id SERIAL PRIMARY KEY,
            portfolio_id VARCHAR(50) REFERENCES portfolios(portfolio_id),
            name VARCHAR(255) NOT NULL,
            current_value NUMERIC(15,2),
            investment_type VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Create portfolio embeddings table for vector search
        CREATE TABLE IF NOT EXISTS portfolio_embeddings (
            id SERIAL PRIMARY KEY,
            portfolio_id VARCHAR(50) REFERENCES portfolios(portfolio_id),
            embedding vector(384),
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Create analysis results table
        CREATE TABLE IF NOT EXISTS portfolio_analysis (
            id SERIAL PRIMARY KEY,
            portfolio_id VARCHAR(50) REFERENCES portfolios(portfolio_id),
            risk_score NUMERIC(4,3),
            volatility NUMERIC(4,3),
            sharpe_ratio NUMERIC(4,3),
            var_95 NUMERIC(15,2),
            similar_portfolios JSONB,
            ai_insights TEXT,
            analyzed_at TIMESTAMP,
            analyzed_by VARCHAR(255)
        );

        -- Insert sample data
        INSERT INTO portfolios (portfolio_id, name, total_value) VALUES
            ('PORT001', 'Growth Portfolio Alpha', 5000000.00),
            ('PORT002', 'Balanced Growth Fund', 3500000.00),
            ('PORT003', 'Conservative Income', 2000000.00),
            ('PORT004', 'Tech Innovation Fund', 8000000.00)
        ON CONFLICT (portfolio_id) DO NOTHING;

        -- Insert sample investments
        INSERT INTO investments (portfolio_id, name, current_value, investment_type) VALUES
            ('PORT001', 'NVIDIA Corp', 1500000.00, 'equity'),
            ('PORT001', 'Apple Inc', 1000000.00, 'equity'),
            ('PORT001', 'Corporate Bonds ETF', 1500000.00, 'fixed_income'),
            ('PORT001', 'REIT Index Fund', 1000000.00, 'real_estate'),
            ('PORT002', 'S&P 500 Index', 1750000.00, 'equity'),
            ('PORT002', 'Treasury Bonds', 1000000.00, 'fixed_income'),
            ('PORT002', 'International Equity', 750000.00, 'equity'),
            ('PORT003', 'Government Bonds', 1200000.00, 'fixed_income'),
            ('PORT003', 'Dividend Stocks', 600000.00, 'equity'),
            ('PORT003', 'Money Market Fund', 200000.00, 'cash'),
            ('PORT004', 'Meta Platforms', 2000000.00, 'equity'),
            ('PORT004', 'Amazon', 2500000.00, 'equity'),
            ('PORT004', 'Microsoft', 2000000.00, 'equity'),
            ('PORT004', 'Venture Capital Fund', 1500000.00, 'alternative')
        ON CONFLICT DO NOTHING;
        """,
        fetch_mode="one",
    )

    workflow = Workflow(name="setup")
    workflow.add_node("setup", setup_node)
    runtime = LocalRuntime(enable_async=True)

    try:
        await runtime.execute(workflow)
        print("✅ Database setup complete")
    except Exception as e:
        print(f"Database setup error: {e}")


def calculate_risk_metrics(portfolio_data: dict) -> dict:
    """Calculate real risk metrics for portfolio."""
    if not portfolio_data or not portfolio_data.get("investments"):
        raise ValueError("No portfolio data provided")

    investments = portfolio_data["investments"]
    total_value = float(portfolio_data.get("total_value", 0))

    # Calculate investment type distribution
    type_distribution = {}
    for inv in investments:
        inv_type = inv.get("investment_type", "unknown")
        type_distribution[inv_type] = type_distribution.get(inv_type, 0) + float(
            inv.get("value", 0)
        )

    # Risk scoring based on diversification and asset types
    equity_pct = (
        type_distribution.get("equity", 0) / total_value if total_value > 0 else 0
    )
    fixed_income_pct = (
        type_distribution.get("fixed_income", 0) / total_value if total_value > 0 else 0
    )
    alternative_pct = (
        type_distribution.get("alternative", 0) / total_value if total_value > 0 else 0
    )

    # Risk score calculation (0-1 scale)
    risk_score = min(0.3 + (equity_pct * 0.5) + (alternative_pct * 0.2), 1.0)

    # Volatility estimation based on asset mix
    volatility = 0.05 + (equity_pct * 0.15) + (alternative_pct * 0.25)

    # Sharpe ratio estimation (simplified)
    expected_return = 0.04 + (equity_pct * 0.08) + (alternative_pct * 0.12)
    sharpe_ratio = (expected_return - 0.02) / volatility if volatility > 0 else 0

    # VaR calculation (95% confidence)
    var_95 = total_value * volatility * 1.645

    return {
        "result": {
            "portfolio_id": portfolio_data.get("portfolio_id"),
            "risk_score": round(risk_score, 3),
            "volatility": round(volatility, 3),
            "sharpe_ratio": round(sharpe_ratio, 3),
            "var_95": round(var_95, 2),
            "equity_allocation": round(equity_pct, 3),
            "fixed_income_allocation": round(fixed_income_pct, 3),
            "calculated_at": datetime.now().isoformat(),
        }
    }


def prepare_portfolio_description(portfolio_data: dict, risk_metrics: dict) -> dict:
    """Prepare portfolio description for embedding generation."""
    metrics = risk_metrics.get("result", {})

    description = f"""Portfolio: {portfolio_data.get('name', 'Unknown')}
Total Value: ${portfolio_data.get('total_value', 0):,.2f}
Risk Score: {metrics.get('risk_score', 0)}
Volatility: {metrics.get('volatility', 0)}
Sharpe Ratio: {metrics.get('sharpe_ratio', 0)}
Equity Allocation: {metrics.get('equity_allocation', 0)*100:.1f}%
Fixed Income Allocation: {metrics.get('fixed_income_allocation', 0)*100:.1f}%
Investments: {', '.join([inv['name'] for inv in portfolio_data.get('investments', [])])}
"""

    return {"result": {"text": description}}


def prepare_ai_context(
    portfolio_data: dict, risk_metrics: dict, similar_portfolios: dict
) -> dict:
    """Prepare context for AI analysis."""
    context = {
        "portfolio_name": portfolio_data.get("name", "Unknown"),
        "total_value": f"${portfolio_data.get('total_value', 0):,.2f}",
        "risk_metrics": risk_metrics.get("result", {}),
        "similar_portfolios": similar_portfolios.get("result", {}).get("matches", [])[
            :3
        ],
        "investments": portfolio_data.get("investments", []),
    }

    prompt = f"""Analyze this investment portfolio and provide actionable insights:

Portfolio: {context['portfolio_name']}
Total Value: {context['total_value']}

Risk Metrics:
- Risk Score: {context['risk_metrics'].get('risk_score', 0)} (0-1 scale)
- Volatility: {context['risk_metrics'].get('volatility', 0)}
- Sharpe Ratio: {context['risk_metrics'].get('sharpe_ratio', 0)}
- Value at Risk (95%): ${context['risk_metrics'].get('var_95', 0):,.2f}

Asset Allocation:
- Equity: {context['risk_metrics'].get('equity_allocation', 0)*100:.1f}%
- Fixed Income: {context['risk_metrics'].get('fixed_income_allocation', 0)*100:.1f}%

Provide 3-4 specific recommendations for improving this portfolio's risk-adjusted returns."""

    return {"result": {"prompt": prompt}}


def create_real_portfolio_workflow():
    """Create a real working portfolio analysis workflow."""
    builder = WorkflowBuilder("real_portfolio_analysis")

    # Step 1: Fetch portfolio data with real SQL
    data_fetch = AsyncSQLDatabaseNode(
        name="fetch_portfolio",
        database_type="postgresql",
        connection_string=DB_CONN,
        query="""
            SELECT
                p.portfolio_id,
                p.name,
                p.total_value,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'investment_id', i.id,
                            'name', i.name,
                            'value', i.current_value,
                            'investment_type', i.investment_type
                        ) ORDER BY i.current_value DESC
                    ) FILTER (WHERE i.id IS NOT NULL),
                    '[]'::json
                ) as investments
            FROM portfolios p
            LEFT JOIN investments i ON i.portfolio_id = p.portfolio_id
            WHERE p.portfolio_id = :portfolio_id
            GROUP BY p.portfolio_id, p.name, p.total_value
        """,
        fetch_mode="one",
        pool_size=10,
        max_pool_size=50,
    )

    # Step 2: Calculate risk metrics with real calculations
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

    # Step 3: Generate portfolio description for embedding
    desc_prep = PythonCodeNode.from_function(
        name="prepare_description", func=prepare_portfolio_description
    )

    # Step 4: Generate embedding using Ollama
    embedding_gen = EmbeddingGeneratorNode(
        name="generate_embedding",
        model="nomic-embed-text",  # Using Ollama's embedding model
        api_provider="ollama",
    )

    # Step 5: Store embedding in vector database
    store_embedding = AsyncPostgreSQLVectorNode(
        name="store_embedding",
        connection_string=DB_CONN,
        table_name="portfolio_embeddings",
        operation="insert",
        pool_size=5,
        max_pool_size=30,
    )

    # Step 6: Find similar portfolios using vector search
    similarity_search = AsyncPostgreSQLVectorNode(
        name="find_similar",
        connection_string=DB_CONN,
        table_name="portfolio_embeddings",
        operation="search",
        distance_metric="cosine",
        limit=5,
        metadata_filter="portfolio_id != :exclude_id",
    )

    # Step 7: Prepare context for AI
    ai_prep = PythonCodeNode.from_function(
        name="prepare_ai_context", func=prepare_ai_context
    )

    # Step 8: Generate AI insights using Ollama
    ai_analysis = LLMAgentNode(
        name="generate_insights",
        agent_type="analyst",
        model="mistral",  # Using Ollama's mistral model
        temperature=0.7,
        max_tokens=500,
    )

    # Step 9: Store analysis results
    result_store = AsyncSQLDatabaseNode(
        name="store_results",
        database_type="postgresql",
        connection_string=DB_CONN,
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
                NOW(),
                :analyzed_by
            )
            RETURNING id
        """,
        fetch_mode="one",
    )

    # Build workflow with connections
    workflow = (
        builder.add_nodes(
            [
                data_fetch,
                risk_calc,
                desc_prep,
                embedding_gen,
                store_embedding,
                similarity_search,
                ai_prep,
                ai_analysis,
                result_store,
            ]
        )
        # Data flow
        .connect("fetch_portfolio", "calculate_risk", {"data": "portfolio_data"})
        # Prepare for embedding
        .connect("fetch_portfolio", "prepare_description", {"data": "portfolio_data"})
        .connect("calculate_risk", "prepare_description", {"result": "risk_metrics"})
        # Generate and store embedding
        .connect("prepare_description", "generate_embedding", {"text": "text"})
        .connect("generate_embedding", "store_embedding", {"embedding": "vector"})
        .connect(
            "fetch_portfolio",
            "store_embedding",
            {"portfolio_id": "metadata.portfolio_id"},
        )
        # Find similar portfolios
        .connect("generate_embedding", "find_similar", {"embedding": "vector"})
        .connect("fetch_portfolio", "find_similar", {"portfolio_id": "exclude_id"})
        # Prepare AI context
        .connect("fetch_portfolio", "prepare_ai_context", {"data": "portfolio_data"})
        .connect("calculate_risk", "prepare_ai_context", {"result": "risk_metrics"})
        .connect("find_similar", "prepare_ai_context", {"result": "similar_portfolios"})
        # Generate insights
        .connect("prepare_ai_context", "generate_insights", {"prompt": "prompt"})
        # Store results
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
        .connect("find_similar", "store_results", {"matches": "similar_portfolios"})
        .connect("generate_insights", "store_results", {"response": "ai_insights"})
        .build()
    )

    return workflow


async def demonstrate_real_workflow():
    """Run the real portfolio analysis workflow."""
    print("=== Real TPC Portfolio Analysis Workflow ===\n")

    # Setup database
    print("1. Setting up database...")
    await setup_database()

    # Create workflow
    print("\n2. Creating portfolio analysis workflow...")
    workflow = create_real_portfolio_workflow()
    print(f"   Created workflow with {len(workflow.nodes)} nodes")

    # Create runtime
    runtime = LocalRuntime(max_concurrency=10, enable_async=True)

    # Analyze each portfolio
    portfolio_ids = ["PORT001", "PORT002", "PORT003", "PORT004"]

    print("\n3. Analyzing portfolios...")
    for portfolio_id in portfolio_ids:
        print(f"\n   Analyzing {portfolio_id}...")
        try:
            results = await runtime.execute(
                workflow,
                parameters={
                    "portfolio_id": portfolio_id,
                    "analyzed_by": "demo_analyst",
                },
            )

            # Display results
            if "calculate_risk" in results:
                risk = results["calculate_risk"]["result"]
                print(f"   ✅ Risk Score: {risk['risk_score']}")
                print(f"      Volatility: {risk['volatility']}")
                print(f"      Sharpe Ratio: {risk['sharpe_ratio']}")
                print(f"      VaR (95%): ${risk['var_95']:,.2f}")

            if "find_similar" in results:
                similar = results["find_similar"]["result"]
                print(f"   ✅ Found {similar['count']} similar portfolios")

            if "generate_insights" in results:
                insights = results["generate_insights"]["result"]
                print("   ✅ AI Insights generated")
                print(f"      {insights['response'][:150]}...")

            if "store_results" in results:
                stored = results["store_results"]["result"]
                print(f"   ✅ Analysis stored with ID: {stored['data']['id']}")

        except Exception as e:
            print(f"   ❌ Error analyzing {portfolio_id}: {e}")
            import traceback

            traceback.print_exc()


async def demonstrate_concurrent_analysis():
    """Demonstrate high-performance concurrent analysis."""
    print("\n\n=== Concurrent Portfolio Analysis ===\n")

    workflow = create_real_portfolio_workflow()
    runtime = LocalRuntime(max_concurrency=50, enable_async=True)

    # Analyze all portfolios concurrently
    portfolio_ids = ["PORT001", "PORT002", "PORT003", "PORT004"]

    print(f"Analyzing {len(portfolio_ids)} portfolios concurrently...")
    start_time = asyncio.get_event_loop().time()

    tasks = [
        runtime.execute(
            workflow,
            parameters={"portfolio_id": pid, "analyzed_by": "concurrent_analyzer"},
        )
        for pid in portfolio_ids
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    end_time = asyncio.get_event_loop().time()
    duration = end_time - start_time

    # Process results
    successful = [r for r in results if not isinstance(r, Exception)]
    failed = [r for r in results if isinstance(r, Exception)]

    print(f"\n✅ Completed in {duration:.2f} seconds")
    print(f"   Successful: {len(successful)}")
    print(f"   Failed: {len(failed)}")
    print(f"   Throughput: {len(portfolio_ids)/duration:.1f} portfolios/second")

    if failed:
        print("\n   Errors:")
        for i, error in enumerate(failed):
            print(f"   - Error {i+1}: {error}")


async def demonstrate_abac_integration():
    """Demonstrate ABAC with real database access."""
    print("\n\n=== ABAC Integration Demo ===\n")

    # Create access control manager
    acm = AccessControlManager(strategy="abac")

    # Add ABAC rules for portfolio access
    acm.add_rule(
        PermissionRule(
            id="portfolio_dept_access",
            resource_type="node",
            resource_id="fetch_portfolio",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            conditions={
                "type": "attribute_expression",
                "value": {
                    "operator": "and",
                    "conditions": [
                        {
                            "attribute_path": "user.attributes.department",
                            "operator": "hierarchical_match",
                            "value": "investment_banking",
                        },
                        {
                            "attribute_path": "user.attributes.clearance",
                            "operator": "in",
                            "value": ["secret", "top_secret"],
                        },
                    ],
                },
            },
        )
    )

    # Create test users
    authorized_user = UserContext(
        user_id="ib_analyst_001",
        tenant_id="tpc",
        email="analyst@tpc.com",
        roles=["analyst"],
        attributes={
            "department": "investment_banking.analytics",
            "clearance": "secret",
            "region": "APAC",
        },
    )

    unauthorized_user = UserContext(
        user_id="hr_001",
        tenant_id="tpc",
        email="hr@tpc.com",
        roles=["hr"],
        attributes={
            "department": "human_resources",
            "clearance": "confidential",
            "region": "APAC",
        },
    )

    # Check access
    print("Testing ABAC access control:")

    for user in [authorized_user, unauthorized_user]:
        decision = acm.check_node_access(
            user, "fetch_portfolio", NodePermission.EXECUTE
        )
        print(f"\n{user.email}:")
        print(f"  Department: {user.attributes['department']}")
        print(f"  Clearance: {user.attributes['clearance']}")
        print(f"  Access: {'✅ GRANTED' if decision.allowed else '❌ DENIED'}")
        if decision.reason:
            print(f"  Reason: {decision.reason}")


async def check_analysis_results():
    """Query and display stored analysis results."""
    print("\n\n=== Stored Analysis Results ===\n")

    query_node = AsyncSQLDatabaseNode(
        name="query_results",
        database_type="postgresql",
        connection_string=DB_CONN,
        query="""
            SELECT
                pa.portfolio_id,
                p.name,
                pa.risk_score,
                pa.volatility,
                pa.sharpe_ratio,
                pa.var_95,
                pa.analyzed_at,
                LEFT(pa.ai_insights, 100) as insights_preview
            FROM portfolio_analysis pa
            JOIN portfolios p ON p.portfolio_id = pa.portfolio_id
            ORDER BY pa.analyzed_at DESC
            LIMIT 10
        """,
        fetch_mode="all",
    )

    workflow = Workflow(name="query")
    workflow.add_node("query", query_node)
    runtime = LocalRuntime(enable_async=True)

    results = await runtime.execute(workflow)

    if "query" in results and results["query"]["result"]["data"]:
        print("Recent analyses:")
        for row in results["query"]["result"]["data"]:
            print(f"\n{row['portfolio_id']} - {row['name']}")
            print(f"  Risk Score: {row['risk_score']}")
            print(f"  Sharpe Ratio: {row['sharpe_ratio']}")
            print(f"  VaR: ${row['var_95']:,.2f}")
            print(f"  Analyzed: {row['analyzed_at']}")
            print(f"  Insights: {row['insights_preview']}...")


if __name__ == "__main__":
    # Run all demonstrations
    asyncio.execute(demonstrate_real_workflow())
    asyncio.execute(demonstrate_concurrent_analysis())
    asyncio.execute(demonstrate_abac_integration())
    asyncio.execute(check_analysis_results())

    print("\n\n=== Real Workflow Demo Complete ===")
    print("This demonstrates the TPC migration pattern with:")
    print("- Real PostgreSQL database with pgvector")
    print("- Actual risk calculations")
    print("- Real embeddings using Ollama")
    print("- Vector similarity search")
    print("- AI insights from local LLM")
    print("- ABAC access control")
    print("- Concurrent execution support")
