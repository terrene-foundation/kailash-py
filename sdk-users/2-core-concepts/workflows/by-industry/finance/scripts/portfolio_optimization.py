#!/usr/bin/env python3
"""
Portfolio Optimization Workflow

This workflow implements a portfolio optimization system that:
1. Analyzes current portfolio holdings and market data
2. Calculates risk metrics and correlations
3. Applies modern portfolio theory for optimization
4. Generates rebalancing recommendations

The workflow demonstrates production-ready portfolio management with
risk analysis, optimization algorithms, and actionable recommendations.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow

from examples.utils.data_paths import (
    ensure_output_dir_exists,
    get_input_data_path,
    get_output_data_path,
)


def calculate_portfolio_metrics(holdings: list, market_data: list) -> dict:
    """Calculate comprehensive portfolio metrics.

    Args:
        holdings: Current portfolio holdings
        market_data: Historical market prices

    Returns:
        Dict with portfolio metrics and analytics
    """
    # Convert to DataFrames
    holdings_df = pd.DataFrame(holdings)
    market_df = pd.DataFrame(market_data)

    # Simulate historical returns if not present
    if "returns" not in market_df.columns:
        np.random.seed(42)  # For reproducibility
        symbols = (
            holdings_df["symbol"].unique()
            if "symbol" in holdings_df.columns
            else ["SPY", "AGG", "GLD", "VNQ"]
        )

        # Generate realistic returns for different asset classes
        returns_data = []
        for symbol in symbols:
            if symbol in ["SPY", "QQQ"]:  # Stocks
                daily_returns = np.random.normal(
                    0.0008, 0.015, 252
                )  # ~20% annual, 15% vol
            elif symbol in ["AGG", "BND"]:  # Bonds
                daily_returns = np.random.normal(
                    0.0002, 0.003, 252
                )  # ~5% annual, 3% vol
            elif symbol == "GLD":  # Gold
                daily_returns = np.random.normal(
                    0.0003, 0.01, 252
                )  # ~8% annual, 10% vol
            else:  # Real Estate
                daily_returns = np.random.normal(
                    0.0006, 0.012, 252
                )  # ~15% annual, 12% vol

            for i, ret in enumerate(daily_returns):
                returns_data.append(
                    {
                        "symbol": symbol,
                        "date": datetime.now() - timedelta(days=252 - i),
                        "daily_return": ret,
                        "price": 100 * np.prod(1 + daily_returns[: i + 1]),
                    }
                )

        market_df = pd.DataFrame(returns_data)

    # Calculate portfolio statistics
    portfolio_value = 0
    position_values = []
    weights = []

    for _, holding in holdings_df.iterrows():
        symbol = holding.get("symbol", "UNKNOWN")
        shares = float(holding.get("shares", 0))  # Convert to float

        # Get latest price (simulated)
        symbol_data = (
            market_df[market_df["symbol"] == symbol]
            if "symbol" in market_df.columns
            else market_df
        )
        latest_price = (
            float(symbol_data["price"].iloc[-1]) if not symbol_data.empty else 100.0
        )

        position_value = shares * latest_price
        portfolio_value += position_value

        position_values.append(
            {
                "symbol": symbol,
                "shares": shares,
                "price": latest_price,
                "value": position_value,
                "asset_class": holding.get("asset_class", "equity"),
            }
        )

    # Calculate weights
    for position in position_values:
        position["weight"] = (
            position["value"] / portfolio_value if portfolio_value > 0 else 0
        )
        weights.append(position["weight"])

    # Calculate returns matrix for correlation
    returns_matrix = (
        market_df.pivot_table(values="daily_return", index="date", columns="symbol")
        if "symbol" in market_df.columns
        else pd.DataFrame()
    )

    # Calculate risk metrics
    if not returns_matrix.empty:
        # Portfolio statistics
        portfolio_returns = returns_matrix.mean()
        portfolio_volatility = returns_matrix.std()
        correlation_matrix = returns_matrix.corr()

        # Portfolio metrics
        weighted_return = np.dot(weights[: len(portfolio_returns)], portfolio_returns)
        portfolio_variance = np.dot(
            weights[: len(portfolio_returns)],
            np.dot(
                correlation_matrix
                * np.outer(portfolio_volatility, portfolio_volatility),
                weights[: len(portfolio_returns)],
            ),
        )
        portfolio_std = np.sqrt(portfolio_variance)

        # Sharpe ratio (assuming 2% risk-free rate)
        risk_free_rate = 0.02 / 252  # Daily
        sharpe_ratio = (
            (weighted_return - risk_free_rate) / portfolio_std
            if portfolio_std > 0
            else 0
        )

        # Maximum drawdown calculation
        cumulative_returns = (1 + returns_matrix).cumprod()
        running_max = cumulative_returns.expanding().max()
        drawdowns = (cumulative_returns - running_max) / running_max
        max_drawdown = drawdowns.min().min()
    else:
        weighted_return = 0
        portfolio_std = 0
        sharpe_ratio = 0
        max_drawdown = 0
        correlation_matrix = pd.DataFrame()

    result = {
        "portfolio_value": portfolio_value,
        "positions": position_values,
        "metrics": {
            "expected_return": weighted_return * 252,  # Annualized
            "volatility": portfolio_std * np.sqrt(252),  # Annualized
            "sharpe_ratio": sharpe_ratio * np.sqrt(252),  # Annualized
            "max_drawdown": max_drawdown,
            "diversification_ratio": len(holdings_df) / 10,  # Simple metric
        },
        "asset_allocation": {
            "equity": sum(
                p["weight"] for p in position_values if p.get("asset_class") == "equity"
            ),
            "bonds": sum(
                p["weight"] for p in position_values if p.get("asset_class") == "bonds"
            ),
            "commodities": sum(
                p["weight"]
                for p in position_values
                if p.get("asset_class") == "commodities"
            ),
            "real_estate": sum(
                p["weight"]
                for p in position_values
                if p.get("asset_class") == "real_estate"
            ),
        },
        "correlation_matrix": (
            correlation_matrix.to_dict() if not correlation_matrix.empty else {}
        ),
    }

    return {"result": result}


def optimize_portfolio(portfolio_metrics: dict, risk_profile: str = "moderate") -> dict:
    """Optimize portfolio allocation using modern portfolio theory.

    Args:
        portfolio_metrics: Current portfolio metrics
        risk_profile: Investor risk profile (conservative, moderate, aggressive)

    Returns:
        Dict with optimized allocations and recommendations
    """
    # Define target allocations based on risk profile
    target_allocations = {
        "conservative": {
            "equity": 0.30,
            "bonds": 0.60,
            "commodities": 0.05,
            "real_estate": 0.05,
        },
        "moderate": {
            "equity": 0.60,
            "bonds": 0.30,
            "commodities": 0.05,
            "real_estate": 0.05,
        },
        "aggressive": {
            "equity": 0.80,
            "bonds": 0.10,
            "commodities": 0.05,
            "real_estate": 0.05,
        },
    }

    target = target_allocations.get(risk_profile, target_allocations["moderate"])
    current = portfolio_metrics.get("asset_allocation", {})
    positions = portfolio_metrics.get("positions", [])
    portfolio_value = portfolio_metrics.get("portfolio_value", 0)

    # Calculate rebalancing needs
    rebalancing_trades = []
    total_rebalance_value = 0

    for asset_class, target_weight in target.items():
        current_weight = current.get(asset_class, 0)
        weight_diff = target_weight - current_weight

        if abs(weight_diff) > 0.02:  # 2% threshold
            trade_value = weight_diff * portfolio_value
            total_rebalance_value += abs(trade_value)

            # Determine which positions to adjust
            class_positions = [
                p for p in positions if p.get("asset_class") == asset_class
            ]

            if trade_value > 0:  # Buy more
                action = "buy"
                for position in class_positions[
                    :1
                ]:  # Simplified: adjust first position
                    shares_to_trade = int(abs(trade_value) / position["price"])
                    if shares_to_trade > 0:
                        rebalancing_trades.append(
                            {
                                "symbol": position["symbol"],
                                "action": action,
                                "shares": shares_to_trade,
                                "value": shares_to_trade * position["price"],
                                "reason": f"Increase {asset_class} allocation",
                            }
                        )
            else:  # Sell some
                action = "sell"
                for position in class_positions[
                    :1
                ]:  # Simplified: adjust first position
                    shares_to_trade = int(abs(trade_value) / position["price"])
                    if shares_to_trade > 0 and shares_to_trade <= position["shares"]:
                        rebalancing_trades.append(
                            {
                                "symbol": position["symbol"],
                                "action": action,
                                "shares": shares_to_trade,
                                "value": shares_to_trade * position["price"],
                                "reason": f"Reduce {asset_class} allocation",
                            }
                        )

    # Calculate optimization metrics
    metrics = portfolio_metrics.get("metrics", {})

    # Efficient frontier calculation (simplified)
    optimal_return = sum(
        (
            target[ac] * 0.08
            if ac == "equity"
            else target[ac] * 0.04 if ac == "bonds" else target[ac] * 0.06
        )
        for ac in target
    )

    optimal_volatility = np.sqrt(
        sum(
            target[ac] ** 2
            * (0.15**2 if ac == "equity" else 0.05**2 if ac == "bonds" else 0.10**2)
            for ac in target
        )
    )

    result = {
        "current_allocation": current,
        "target_allocation": target,
        "rebalancing_trades": rebalancing_trades,
        "total_rebalance_value": total_rebalance_value,
        "rebalance_percentage": (
            (total_rebalance_value / portfolio_value * 100)
            if portfolio_value > 0
            else 0
        ),
        "optimization_metrics": {
            "current_return": metrics.get("expected_return", 0),
            "optimal_return": optimal_return,
            "current_volatility": metrics.get("volatility", 0),
            "optimal_volatility": optimal_volatility,
            "current_sharpe": metrics.get("sharpe_ratio", 0),
            "optimal_sharpe": (
                (optimal_return - 0.02) / optimal_volatility
                if optimal_volatility > 0
                else 0
            ),
        },
        "risk_profile": risk_profile,
        "recommendations": [
            f"Rebalance portfolio to achieve {risk_profile} risk profile",
            f"Total rebalancing required: ${total_rebalance_value:,.2f} ({total_rebalance_value/portfolio_value*100:.1f}%)",
            f"Expected improvement in Sharpe ratio: {((optimal_return - 0.02) / optimal_volatility - metrics.get('sharpe_ratio', 0)):.2f}",
        ],
    }

    return {"result": result}


def generate_investment_report(optimization_results: dict, ai_insights: Any) -> dict:
    """Generate comprehensive investment report with recommendations.

    Args:
        optimization_results: Portfolio optimization results
        ai_insights: AI-generated market insights

    Returns:
        Dict with complete investment report
    """
    # Parse AI insights
    insights = {}
    if isinstance(ai_insights, str):
        try:
            insights = json.loads(ai_insights)
        except Exception:
            insights = {"analysis": ai_insights}

    # Extract key data
    current_allocation = optimization_results.get("current_allocation", {})
    target_allocation = optimization_results.get("target_allocation", {})
    trades = optimization_results.get("rebalancing_trades", [])
    metrics = optimization_results.get("optimization_metrics", {})

    # Create executive summary
    executive_summary = {
        "portfolio_status": "rebalancing_recommended" if trades else "well_balanced",
        "risk_profile": optimization_results.get("risk_profile", "moderate"),
        "total_trades": len(trades),
        "rebalance_value": optimization_results.get("total_rebalance_value", 0),
        "expected_improvement": {
            "return": metrics.get("optimal_return", 0)
            - metrics.get("current_return", 0),
            "sharpe_ratio": metrics.get("optimal_sharpe", 0)
            - metrics.get("current_sharpe", 0),
        },
    }

    # Create detailed recommendations
    recommendations = []

    # Asset allocation recommendations
    for asset_class, target_weight in target_allocation.items():
        current_weight = current_allocation.get(asset_class, 0)
        diff = target_weight - current_weight

        if abs(diff) > 0.02:
            if diff > 0:
                recommendations.append(
                    {
                        "action": "increase",
                        "asset_class": asset_class,
                        "current_weight": f"{current_weight:.1%}",
                        "target_weight": f"{target_weight:.1%}",
                        "rationale": f"Increase {asset_class} allocation to match {optimization_results.get('risk_profile')} risk profile",
                    }
                )
            else:
                recommendations.append(
                    {
                        "action": "decrease",
                        "asset_class": asset_class,
                        "current_weight": f"{current_weight:.1%}",
                        "target_weight": f"{target_weight:.1%}",
                        "rationale": f"Reduce {asset_class} allocation to decrease portfolio risk",
                    }
                )

    # Trading recommendations
    trade_summary = []
    for trade in trades[:5]:  # Top 5 trades
        trade_summary.append(
            {
                "symbol": trade["symbol"],
                "action": trade["action"].upper(),
                "shares": trade["shares"],
                "value": f"${trade['value']:,.2f}",
                "reason": trade["reason"],
            }
        )

    # Risk analysis
    risk_analysis = {
        "current_volatility": f"{metrics.get('current_volatility', 0):.1%}",
        "target_volatility": f"{metrics.get('optimal_volatility', 0):.1%}",
        "volatility_reduction": f"{(metrics.get('current_volatility', 0) - metrics.get('optimal_volatility', 0)):.1%}",
        "diversification_score": "good" if len(trades) < 3 else "needs_improvement",
    }

    # Final report
    report = {
        "report_date": datetime.now().isoformat(),
        "executive_summary": executive_summary,
        "current_allocation": {k: f"{v:.1%}" for k, v in current_allocation.items()},
        "target_allocation": {k: f"{v:.1%}" for k, v in target_allocation.items()},
        "recommendations": recommendations,
        "trading_plan": trade_summary,
        "risk_analysis": risk_analysis,
        "ai_market_insights": insights,
        "next_review_date": (datetime.now() + timedelta(days=90)).isoformat(),
    }

    return {"result": report}


def create_portfolio_optimization_workflow() -> Workflow:
    """Create a comprehensive portfolio optimization workflow."""
    workflow = Workflow(
        "portfolio-optimization", "Portfolio Optimization and Rebalancing System"
    )

    # Step 1: Load current holdings
    holdings_reader = CSVReaderNode(
        name="holdings_reader",
        file_path=str(get_input_data_path("portfolio_holdings.csv", "finance")),
    )
    workflow.add_node("holdings_reader", holdings_reader)

    # Step 2: Load market data
    market_reader = CSVReaderNode(
        name="market_reader",
        file_path=str(get_input_data_path("market_data.csv", "finance")),
    )
    workflow.add_node("market_reader", market_reader)

    # Step 3: Calculate portfolio metrics
    metrics_calculator = PythonCodeNode.from_function(
        name="metrics_calculator", func=calculate_portfolio_metrics
    )
    workflow.add_node("metrics_calculator", metrics_calculator)

    workflow.connect(
        "holdings_reader", "metrics_calculator", mapping={"data": "holdings"}
    )
    workflow.connect(
        "market_reader", "metrics_calculator", mapping={"data": "market_data"}
    )

    # Step 4: Optimize portfolio allocation
    optimizer = PythonCodeNode.from_function(name="optimizer", func=optimize_portfolio)
    workflow.add_node("optimizer", optimizer)
    workflow.connect(
        "metrics_calculator", "optimizer", mapping={"result": "portfolio_metrics"}
    )

    # Step 5: AI market analysis
    market_analyzer = LLMAgentNode(
        name="market_analyzer",
        model="gpt-4",
        system_prompt="""You are a senior investment strategist. Analyze the portfolio optimization results and provide:
        1. Market outlook for each asset class
        2. Timing recommendations for rebalancing
        3. Risk factors to monitor
        4. Alternative investment suggestions
        5. Tax-efficient rebalancing strategies

        Consider current market conditions, economic indicators, and the investor's risk profile.
        Provide actionable insights in structured JSON format.""",
        prompt="Analyze this portfolio optimization plan: {{optimization_results}}",
    )
    workflow.add_node("market_analyzer", market_analyzer)
    workflow.connect(
        "optimizer", "market_analyzer", mapping={"result": "optimization_results"}
    )

    # Step 6: Generate comprehensive report
    report_generator = PythonCodeNode.from_function(
        name="report_generator", func=generate_investment_report
    )
    workflow.add_node("report_generator", report_generator)
    workflow.connect(
        "optimizer", "report_generator", mapping={"result": "optimization_results"}
    )
    workflow.connect(
        "market_analyzer", "report_generator", mapping={"response": "ai_insights"}
    )

    # Step 7: Save report
    ensure_output_dir_exists("json")
    report_writer = JSONWriterNode(
        name="report_writer",
        file_path=str(
            get_output_data_path("portfolio_optimization_report.json", "json")
        ),
        pretty_print=True,
    )
    workflow.add_node("report_writer", report_writer)
    workflow.connect("report_generator", "report_writer", mapping={"result": "data"})

    return workflow


def main():
    """Execute the portfolio optimization workflow."""
    print("📊 Starting Portfolio Optimization Workflow...")

    # First create sample data files if they don't exist
    holdings_path = get_input_data_path("portfolio_holdings.csv", "finance")
    market_path = get_input_data_path("market_data.csv", "finance")

    # Create sample holdings data
    if not holdings_path.exists():
        holdings_path.parent.mkdir(parents=True, exist_ok=True)
        sample_holdings = pd.DataFrame(
            [
                {"symbol": "SPY", "shares": 100, "asset_class": "equity"},
                {"symbol": "QQQ", "shares": 50, "asset_class": "equity"},
                {"symbol": "AGG", "shares": 200, "asset_class": "bonds"},
                {"symbol": "GLD", "shares": 30, "asset_class": "commodities"},
                {"symbol": "VNQ", "shares": 40, "asset_class": "real_estate"},
            ]
        )
        sample_holdings.to_csv(holdings_path, index=False)
        print(f"Created sample holdings data at {holdings_path}")

    # Create sample market data
    if not market_path.exists():
        # This will be handled by the workflow with simulated data
        pd.DataFrame().to_csv(market_path, index=False)
        print(f"Created empty market data file at {market_path}")

    try:
        workflow = create_portfolio_optimization_workflow()
        runtime = LocalRuntime()

        print("🔄 Analyzing portfolio and optimizing allocation...")
        results, run_id = runtime.execute(
            workflow, parameters={"optimizer": {"risk_profile": "moderate"}}
        )

        print("\n✅ Workflow completed successfully!")
        print(
            f"📁 Optimization report saved to: {get_output_data_path('portfolio_optimization_report.json', 'json')}"
        )

        # Display summary
        if "optimizer" in results:
            optimization = results["optimizer"].get("result", {})
            trades = optimization.get("rebalancing_trades", [])
            metrics = optimization.get("optimization_metrics", {})

            print("\n📈 Portfolio Optimization Summary:")
            print(f"   Risk Profile: {optimization.get('risk_profile', 'moderate')}")
            print(f"   Rebalancing trades: {len(trades)}")
            print(
                f"   Total rebalance value: ${optimization.get('total_rebalance_value', 0):,.2f}"
            )
            print("\n   Expected improvements:")
            print(
                f"   - Return: {(metrics.get('optimal_return', 0) - metrics.get('current_return', 0))*100:.1f}%"
            )
            print(
                f"   - Sharpe Ratio: {metrics.get('optimal_sharpe', 0) - metrics.get('current_sharpe', 0):.2f}"
            )

            if trades:
                print("\n   Top rebalancing trades:")
                for trade in trades[:3]:
                    print(
                        f"   - {trade['action'].upper()} {trade['shares']} shares of {trade['symbol']}"
                    )

        return results

    except Exception as e:
        print(f"❌ Error in portfolio optimization: {str(e)}")
        raise


if __name__ == "__main__":
    main()
