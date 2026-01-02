#!/usr/bin/env python3
"""
Trading Signals Workflow

This workflow implements a trading signal generation system that:
1. Analyzes market data with technical indicators
2. Applies momentum and mean reversion strategies
3. Uses AI for pattern recognition and sentiment analysis
4. Generates actionable buy/sell signals with confidence scores

The workflow demonstrates production-ready algorithmic trading with
multiple signal sources, risk management, and real-time alerts.
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


def calculate_technical_indicators(price_data: list, volume_data: list) -> dict:
    """Calculate comprehensive technical indicators for trading signals.

    Args:
        price_data: Historical price data
        volume_data: Historical volume data

    Returns:
        Dict with technical indicators and price data
    """
    # Convert to DataFrames
    prices_df = pd.DataFrame(price_data) if price_data else pd.DataFrame()
    volumes_df = pd.DataFrame(volume_data) if volume_data else pd.DataFrame()

    # Generate synthetic market data if empty
    if prices_df.empty:
        np.random.seed(42)
        dates = pd.date_range(end=datetime.now(), periods=100, freq="D")

        # Generate realistic price data for different stocks
        symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]
        price_data = []

        for symbol in symbols:
            # Different characteristics for each stock
            if symbol == "TSLA":
                base_price = 200
                volatility = 0.04  # High volatility
                trend = 0.001
            elif symbol in ["AAPL", "MSFT"]:
                base_price = 150
                volatility = 0.02  # Medium volatility
                trend = 0.0005
            else:
                base_price = 100
                volatility = 0.025
                trend = 0.0007

            prices = [base_price]
            for i in range(1, len(dates)):
                change = np.random.normal(trend, volatility)
                new_price = prices[-1] * (1 + change)
                prices.append(new_price)

            for i, (date, price) in enumerate(zip(dates, prices, strict=False)):
                price_data.append(
                    {
                        "symbol": symbol,
                        "date": date,
                        "open": price * 0.99,
                        "high": price * 1.01,
                        "low": price * 0.98,
                        "close": price,
                        "volume": np.random.randint(1000000, 10000000),
                    }
                )

        prices_df = pd.DataFrame(price_data)

    # Calculate indicators for each symbol
    results = []

    for symbol in (
        prices_df["symbol"].unique() if "symbol" in prices_df.columns else ["UNKNOWN"]
    ):
        symbol_data = (
            prices_df[prices_df["symbol"] == symbol]
            if "symbol" in prices_df.columns
            else prices_df
        )

        if not symbol_data.empty:
            # Sort by date
            symbol_data = (
                symbol_data.sort_values("date")
                if "date" in symbol_data.columns
                else symbol_data
            )

            # Price data
            closes = (
                symbol_data["close"].values
                if "close" in symbol_data.columns
                else symbol_data.iloc[:, 0].values
            )
            highs = (
                symbol_data["high"].values
                if "high" in symbol_data.columns
                else closes * 1.01
            )
            lows = (
                symbol_data["low"].values
                if "low" in symbol_data.columns
                else closes * 0.99
            )
            volumes = (
                symbol_data["volume"].values
                if "volume" in symbol_data.columns
                else np.ones_like(closes) * 1000000
            )

            # 1. Moving Averages
            sma_20 = (
                pd.Series(closes).rolling(20).mean().iloc[-1]
                if len(closes) >= 20
                else closes[-1]
            )
            sma_50 = (
                pd.Series(closes).rolling(50).mean().iloc[-1]
                if len(closes) >= 50
                else closes[-1]
            )
            ema_12 = pd.Series(closes).ewm(span=12).mean().iloc[-1]
            ema_26 = pd.Series(closes).ewm(span=26).mean().iloc[-1]

            # 2. MACD
            macd_line = ema_12 - ema_26
            signal_line = pd.Series(closes).ewm(span=9).mean().iloc[-1]
            macd_histogram = macd_line - signal_line

            # 3. RSI (Relative Strength Index)
            price_changes = pd.Series(closes).diff()
            gains = price_changes.where(price_changes > 0, 0)
            losses = -price_changes.where(price_changes < 0, 0)
            avg_gain = gains.rolling(14).mean().iloc[-1] if len(gains) >= 14 else 0
            avg_loss = losses.rolling(14).mean().iloc[-1] if len(losses) >= 14 else 1
            rs = avg_gain / avg_loss if avg_loss != 0 else 100
            rsi = 100 - (100 / (1 + rs))

            # 4. Bollinger Bands
            sma_20_series = pd.Series(closes).rolling(20).mean()
            std_20 = (
                pd.Series(closes).rolling(20).std().iloc[-1] if len(closes) >= 20 else 0
            )
            upper_band = sma_20 + (2 * std_20)
            lower_band = sma_20 - (2 * std_20)
            bb_position = (
                (closes[-1] - lower_band) / (upper_band - lower_band)
                if (upper_band - lower_band) != 0
                else 0.5
            )

            # 5. Volume indicators
            avg_volume = (
                pd.Series(volumes).rolling(20).mean().iloc[-1]
                if len(volumes) >= 20
                else volumes[-1]
            )
            volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1

            # 6. Price momentum
            momentum_5 = (closes[-1] / closes[-5] - 1) * 100 if len(closes) >= 5 else 0
            momentum_20 = (
                (closes[-1] / closes[-20] - 1) * 100 if len(closes) >= 20 else 0
            )

            # 7. Support and Resistance
            recent_high = max(highs[-20:]) if len(highs) >= 20 else highs[-1]
            recent_low = min(lows[-20:]) if len(lows) >= 20 else lows[-1]
            resistance_distance = (recent_high - closes[-1]) / closes[-1] * 100
            support_distance = (closes[-1] - recent_low) / closes[-1] * 100

            # Compile indicators
            indicators = {
                "symbol": symbol,
                "current_price": float(closes[-1]),
                "price_change_pct": float(momentum_5),
                "sma_20": float(sma_20),
                "sma_50": float(sma_50),
                "ema_12": float(ema_12),
                "ema_26": float(ema_26),
                "macd": float(macd_line),
                "macd_signal": float(signal_line),
                "macd_histogram": float(macd_histogram),
                "rsi": float(rsi),
                "bb_position": float(bb_position),
                "volume_ratio": float(volume_ratio),
                "momentum_5d": float(momentum_5),
                "momentum_20d": float(momentum_20),
                "resistance_distance": float(resistance_distance),
                "support_distance": float(support_distance),
                "trend": "bullish" if sma_20 > sma_50 else "bearish",
                "timestamp": datetime.now().isoformat(),
            }

            results.append(indicators)

    return {"result": results}


def generate_trading_signals(technical_indicators: list) -> dict:
    """Generate trading signals based on technical indicators.

    Args:
        technical_indicators: List of calculated indicators per symbol

    Returns:
        Dict with trading signals and recommendations
    """
    signals = []

    for indicator in technical_indicators:
        symbol = indicator["symbol"]
        signal_strength = 0
        signal_reasons = []

        # 1. Trend following signals
        if indicator["trend"] == "bullish" and indicator["macd_histogram"] > 0:
            signal_strength += 20
            signal_reasons.append("Bullish trend with positive MACD")

        if indicator["sma_20"] > indicator["sma_50"] and indicator["momentum_20d"] > 5:
            signal_strength += 15
            signal_reasons.append("Golden cross pattern with strong momentum")

        # 2. Mean reversion signals
        if indicator["rsi"] < 30:
            signal_strength += 25
            signal_reasons.append("Oversold condition (RSI < 30)")
        elif indicator["rsi"] > 70:
            signal_strength -= 25
            signal_reasons.append("Overbought condition (RSI > 70)")

        # 3. Bollinger Band signals
        if indicator["bb_position"] < 0.2:
            signal_strength += 20
            signal_reasons.append("Price near lower Bollinger Band")
        elif indicator["bb_position"] > 0.8:
            signal_strength -= 20
            signal_reasons.append("Price near upper Bollinger Band")

        # 4. Volume confirmation
        if indicator["volume_ratio"] > 1.5 and signal_strength > 0:
            signal_strength += 10
            signal_reasons.append("High volume confirmation")

        # 5. Support/Resistance levels
        if indicator["support_distance"] < 2:
            signal_strength += 15
            signal_reasons.append("Price near support level")
        if indicator["resistance_distance"] < 2 and signal_strength < 0:
            signal_strength -= 10
            signal_reasons.append("Price near resistance level")

        # Determine signal type
        if signal_strength >= 40:
            signal_type = "strong_buy"
            action = "BUY"
        elif signal_strength >= 20:
            signal_type = "buy"
            action = "BUY"
        elif signal_strength <= -40:
            signal_type = "strong_sell"
            action = "SELL"
        elif signal_strength <= -20:
            signal_type = "sell"
            action = "SELL"
        else:
            signal_type = "hold"
            action = "HOLD"

        # Calculate position size based on signal strength
        position_size = min(abs(signal_strength) / 100, 1.0)

        # Risk management
        if action == "BUY":
            stop_loss = indicator["current_price"] * 0.98  # 2% stop loss
            take_profit = indicator["current_price"] * 1.05  # 5% take profit
        elif action == "SELL":
            stop_loss = indicator["current_price"] * 1.02
            take_profit = indicator["current_price"] * 0.95
        else:
            stop_loss = None
            take_profit = None

        signal = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "signal_type": signal_type,
            "action": action,
            "signal_strength": abs(signal_strength),
            "confidence": min(abs(signal_strength) / 100, 0.95),
            "current_price": indicator["current_price"],
            "position_size": position_size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "reasons": signal_reasons,
            "technical_summary": {
                "rsi": indicator["rsi"],
                "macd": indicator["macd"],
                "trend": indicator["trend"],
                "momentum": indicator["momentum_20d"],
            },
        }

        signals.append(signal)

    # Sort by signal strength
    signals = sorted(signals, key=lambda x: x["signal_strength"], reverse=True)

    # Summary statistics
    summary = {
        "total_signals": len(signals),
        "buy_signals": len([s for s in signals if s["action"] == "BUY"]),
        "sell_signals": len([s for s in signals if s["action"] == "SELL"]),
        "strong_signals": len([s for s in signals if "strong" in s["signal_type"]]),
        "average_confidence": (
            np.mean([s["confidence"] for s in signals]) if signals else 0
        ),
    }

    return {"result": {"signals": signals, "summary": summary}}


def create_trading_alerts(trading_signals: dict, ai_analysis: Any) -> dict:
    """Create actionable trading alerts with AI insights.

    Args:
        trading_signals: Generated trading signals
        ai_analysis: AI market analysis

    Returns:
        Dict with trading alerts and execution plan
    """
    # Parse AI analysis
    ai_insights = {}
    if isinstance(ai_analysis, str):
        try:
            ai_insights = json.loads(ai_analysis)
        except Exception:
            ai_insights = {"analysis": ai_analysis}

    signals = trading_signals.get("signals", [])
    summary = trading_signals.get("summary", {})

    # Create alerts for actionable signals
    alerts = []
    execution_plan = []

    for signal in signals:
        if signal["action"] in ["BUY", "SELL"] and signal["confidence"] > 0.6:
            alert = {
                "alert_id": f"TRADE-{signal['symbol']}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "symbol": signal["symbol"],
                "action": signal["action"],
                "urgency": "high" if signal["signal_strength"] > 60 else "medium",
                "signal_type": signal["signal_type"],
                "confidence": signal["confidence"],
                "current_price": signal["current_price"],
                "entry_price": signal["current_price"],
                "stop_loss": signal["stop_loss"],
                "take_profit": signal["take_profit"],
                "position_size_pct": signal["position_size"] * 100,
                "reasons": signal["reasons"],
                "ai_sentiment": ai_insights.get("sentiment", {}).get(
                    signal["symbol"], "neutral"
                ),
                "ai_recommendation": ai_insights.get("recommendations", {}).get(
                    signal["symbol"], ""
                ),
                "created_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(hours=4)).isoformat(),
            }
            alerts.append(alert)

            # Add to execution plan if high confidence
            if signal["confidence"] > 0.75:
                execution_plan.append(
                    {
                        "symbol": signal["symbol"],
                        "action": signal["action"],
                        "shares": int(
                            10000 / signal["current_price"] * signal["position_size"]
                        ),  # $10k base position
                        "limit_price": signal["current_price"]
                        * (1.001 if signal["action"] == "BUY" else 0.999),
                        "stop_loss": signal["stop_loss"],
                        "take_profit": signal["take_profit"],
                        "time_in_force": "DAY",
                        "order_type": "LIMIT",
                    }
                )

    # Risk analysis
    total_exposure = sum(
        order["shares"] * order["limit_price"] for order in execution_plan
    )
    risk_metrics = {
        "total_exposure": total_exposure,
        "number_of_positions": len(execution_plan),
        "max_position_size": (
            max([order["shares"] * order["limit_price"] for order in execution_plan])
            if execution_plan
            else 0
        ),
        "portfolio_heat": len([a for a in alerts if a["urgency"] == "high"])
        / max(len(alerts), 1),
    }

    # Market overview
    market_overview = {
        "bullish_signals": len([s for s in signals if s["action"] == "BUY"]),
        "bearish_signals": len([s for s in signals if s["action"] == "SELL"]),
        "market_sentiment": (
            "bullish"
            if summary.get("buy_signals", 0) > summary.get("sell_signals", 0)
            else "bearish"
        ),
        "strongest_buy": next(
            (s["symbol"] for s in signals if s["action"] == "BUY"), None
        ),
        "strongest_sell": next(
            (s["symbol"] for s in signals if s["action"] == "SELL"), None
        ),
    }

    report = {
        "report_timestamp": datetime.now().isoformat(),
        "alerts": alerts,
        "execution_plan": execution_plan,
        "risk_metrics": risk_metrics,
        "market_overview": market_overview,
        "ai_insights": ai_insights,
        "summary": summary,
        "next_update": (datetime.now() + timedelta(hours=1)).isoformat(),
    }

    return {"result": report}


def create_trading_signals_workflow() -> Workflow:
    """Create a comprehensive trading signals workflow."""
    workflow = Workflow(
        "trading-signals", "Algorithmic Trading Signal Generation System"
    )

    # Step 1: Load price data
    price_reader = CSVReaderNode(
        name="price_reader",
        file_path=str(get_input_data_path("stock_prices.csv", "finance")),
    )
    workflow.add_node("price_reader", price_reader)

    # Step 2: Load volume data
    volume_reader = CSVReaderNode(
        name="volume_reader",
        file_path=str(get_input_data_path("stock_volumes.csv", "finance")),
    )
    workflow.add_node("volume_reader", volume_reader)

    # Step 3: Calculate technical indicators
    indicator_calculator = PythonCodeNode.from_function(
        name="indicator_calculator", func=calculate_technical_indicators
    )
    workflow.add_node("indicator_calculator", indicator_calculator)

    workflow.connect(
        "price_reader", "indicator_calculator", mapping={"data": "price_data"}
    )
    workflow.connect(
        "volume_reader", "indicator_calculator", mapping={"data": "volume_data"}
    )

    # Step 4: Generate trading signals
    signal_generator = PythonCodeNode.from_function(
        name="signal_generator", func=generate_trading_signals
    )
    workflow.add_node("signal_generator", signal_generator)
    workflow.connect(
        "indicator_calculator",
        "signal_generator",
        mapping={"result": "technical_indicators"},
    )

    # Step 5: AI market analysis
    market_analyzer = LLMAgentNode(
        name="market_analyzer",
        model="gpt-4",
        system_prompt="""You are a senior quantitative trader and market analyst. Analyze the trading signals and provide:
        1. Market sentiment analysis for each symbol
        2. Validation of technical signals with fundamental context
        3. Risk warnings and market conditions to watch
        4. Optimal entry/exit timing recommendations
        5. Portfolio-level risk assessment

        Consider current market regime, sector rotation, and macro factors.
        Provide analysis in structured JSON format with actionable insights.""",
        prompt="Analyze these trading signals and provide market insights: {{trading_signals}}",
    )
    workflow.add_node("market_analyzer", market_analyzer)
    workflow.connect(
        "signal_generator", "market_analyzer", mapping={"result": "trading_signals"}
    )

    # Step 6: Create trading alerts
    alert_creator = PythonCodeNode.from_function(
        name="alert_creator", func=create_trading_alerts
    )
    workflow.add_node("alert_creator", alert_creator)
    workflow.connect(
        "signal_generator", "alert_creator", mapping={"result": "trading_signals"}
    )
    workflow.connect(
        "market_analyzer", "alert_creator", mapping={"response": "ai_analysis"}
    )

    # Step 7: Save trading signals report
    ensure_output_dir_exists("json")
    report_writer = JSONWriterNode(
        name="report_writer",
        file_path=str(get_output_data_path("trading_signals_report.json", "json")),
        pretty_print=True,
    )
    workflow.add_node("report_writer", report_writer)
    workflow.connect("alert_creator", "report_writer", mapping={"result": "data"})

    return workflow


def main():
    """Execute the trading signals workflow."""
    print("📈 Starting Trading Signals Workflow...")

    # Create placeholder data files if they don't exist
    price_path = get_input_data_path("stock_prices.csv", "finance")
    volume_path = get_input_data_path("stock_volumes.csv", "finance")

    # Create empty files to trigger synthetic data generation
    for path in [price_path, volume_path]:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame().to_csv(path, index=False)
            print(f"Created placeholder file at {path}")

    try:
        workflow = create_trading_signals_workflow()
        runtime = LocalRuntime()

        print("🔍 Analyzing market data and generating signals...")
        results, run_id = runtime.execute(workflow)

        print("\n✅ Workflow completed successfully!")
        print(
            f"📁 Trading signals saved to: {get_output_data_path('trading_signals_report.json', 'json')}"
        )

        # Display summary
        if "alert_creator" in results:
            report = results["alert_creator"].get("result", {})
            alerts = report.get("alerts", [])
            execution_plan = report.get("execution_plan", [])
            market_overview = report.get("market_overview", {})

            print("\n📊 Trading Signal Summary:")
            print(
                f"   Market sentiment: {market_overview.get('market_sentiment', 'neutral')}"
            )
            print(f"   Active alerts: {len(alerts)}")
            print(f"   Executable trades: {len(execution_plan)}")

            if alerts:
                print("\n🚨 Top Trading Alerts:")
                for alert in alerts[:3]:
                    print(
                        f"   - {alert['action']} {alert['symbol']} @ ${alert['current_price']:.2f}"
                    )
                    print(
                        f"     Confidence: {alert['confidence']:.0%}, Signal: {alert['signal_type']}"
                    )

            if execution_plan:
                total_value = sum(
                    order["shares"] * order["limit_price"] for order in execution_plan
                )
                print("\n💼 Execution Plan:")
                print(f"   Total positions: {len(execution_plan)}")
                print(f"   Total exposure: ${total_value:,.2f}")

        return results

    except Exception as e:
        print(f"❌ Error in trading signals generation: {str(e)}")
        raise


if __name__ == "__main__":
    main()
