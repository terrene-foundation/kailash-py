"""
Real-world data processing pipeline tests for production scenarios.

These tests simulate complex, realistic data processing scenarios with
large datasets, concurrent processing, error handling, and performance
monitoring that mirror actual production workflows.
"""

import asyncio
import csv
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest
from kailash.testing import (
    AsyncAssertions,
    AsyncTestUtils,
    AsyncWorkflowFixtures,
    AsyncWorkflowTestCase,
)
from kailash.workflow import AsyncWorkflowBuilder

# Mark all tests as data-intensive and slow
pytestmark = [pytest.mark.slow, pytest.mark.data_intensive]


@pytest.mark.asyncio
class TestRealWorldDataPipelines:
    """Real-world data processing pipeline tests."""

    async def test_financial_data_processing_pipeline(self):
        """Test comprehensive financial data processing with real-time feeds."""

        class FinancialDataPipelineTest(AsyncWorkflowTestCase):
            async def setUp(self):
                await super().setUp()

                # Set up PostgreSQL for financial data
                self.financial_db = await AsyncWorkflowFixtures.create_test_database(
                    engine="postgresql",
                    database="financial_db",
                    user="fin_user",
                    password="fin_secure123",
                )

                try:
                    import asyncpg

                    self.db_conn = await asyncpg.connect(
                        self.financial_db.connection_string
                    )
                    await self.create_test_resource(
                        "financial_db", lambda: self.db_conn
                    )

                    # Set up Redis for real-time caching
                    import docker

                    client = docker.from_env()
                    self.redis_container = client.containers.execute(
                        "redis:7-alpine",
                        ports={"6379/tcp": None},
                        detach=True,
                        remove=False,
                    )

                    self.redis_container.reload()
                    redis_port = int(
                        self.redis_container.ports["6379/tcp"][0]["HostPort"]
                    )
                    await asyncio.sleep(2)

                    import aioredis

                    self.redis_client = aioredis.from_url(
                        f"redis://localhost:{redis_port}"
                    )
                    await self.create_test_resource("cache", lambda: self.redis_client)

                    # Set up financial schema and sample data
                    await self._setup_financial_schema()

                except ImportError as e:
                    pytest.skip(f"Required dependencies not available: {e}")

            async def _setup_financial_schema(self):
                """Set up realistic financial data schema."""
                # Market data table
                await self.db_conn.execute(
                    """
                    CREATE TABLE market_data (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(10),
                        timestamp TIMESTAMP,
                        open_price DECIMAL(12,4),
                        high_price DECIMAL(12,4),
                        low_price DECIMAL(12,4),
                        close_price DECIMAL(12,4),
                        volume BIGINT,
                        market VARCHAR(20),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                # Trading transactions
                await self.db_conn.execute(
                    """
                    CREATE TABLE trading_transactions (
                        id SERIAL PRIMARY KEY,
                        transaction_id VARCHAR(50) UNIQUE,
                        account_id VARCHAR(20),
                        symbol VARCHAR(10),
                        side VARCHAR(4) CHECK (side IN ('BUY', 'SELL')),
                        quantity INTEGER,
                        price DECIMAL(12,4),
                        total_value DECIMAL(15,2),
                        commission DECIMAL(8,2),
                        timestamp TIMESTAMP,
                        status VARCHAR(20) DEFAULT 'PENDING',
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                # Risk metrics
                await self.db_conn.execute(
                    """
                    CREATE TABLE risk_metrics (
                        id SERIAL PRIMARY KEY,
                        account_id VARCHAR(20),
                        metric_date DATE,
                        total_exposure DECIMAL(15,2),
                        var_95 DECIMAL(12,2),
                        beta DECIMAL(6,4),
                        sharpe_ratio DECIMAL(6,4),
                        max_drawdown DECIMAL(6,4),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                # Compliance alerts
                await self.db_conn.execute(
                    """
                    CREATE TABLE compliance_alerts (
                        id SERIAL PRIMARY KEY,
                        alert_type VARCHAR(50),
                        account_id VARCHAR(20),
                        symbol VARCHAR(10),
                        severity VARCHAR(10) CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
                        description TEXT,
                        alert_timestamp TIMESTAMP,
                        resolved BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                # Generate realistic sample data
                await self._generate_financial_data()

            async def _generate_financial_data(self):
                """Generate realistic financial sample data."""
                import random
                from decimal import Decimal

                symbols = [
                    "AAPL",
                    "GOOGL",
                    "MSFT",
                    "AMZN",
                    "TSLA",
                    "NVDA",
                    "META",
                    "JPM",
                    "BAC",
                    "GS",
                ]
                accounts = ["ACC_001", "ACC_002", "ACC_003", "ACC_004", "ACC_005"]

                # Generate market data for last 30 days
                base_date = datetime.now() - timedelta(days=30)

                for symbol in symbols:
                    base_price = random.uniform(50, 300)

                    for day in range(30):
                        date = base_date + timedelta(days=day)

                        # Simulate daily price movement
                        daily_change = random.uniform(-0.05, 0.05)  # ±5% daily change
                        open_price = base_price * (1 + daily_change)

                        high_price = open_price * random.uniform(1.0, 1.03)
                        low_price = open_price * random.uniform(0.97, 1.0)
                        close_price = random.uniform(low_price, high_price)
                        volume = random.randint(1000000, 50000000)

                        await self.db_conn.execute(
                            """
                            INSERT INTO market_data (symbol, timestamp, open_price, high_price, low_price, close_price, volume, market)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """,
                            symbol,
                            date,
                            open_price,
                            high_price,
                            low_price,
                            close_price,
                            volume,
                            "NASDAQ",
                        )

                        base_price = close_price  # Update base price for next day

                # Generate trading transactions
                for _ in range(500):
                    account = random.choice(accounts)
                    symbol = random.choice(symbols)
                    side = random.choice(["BUY", "SELL"])
                    quantity = random.randint(10, 1000)
                    price = random.uniform(50, 300)
                    total_value = quantity * price
                    commission = total_value * 0.001  # 0.1% commission
                    timestamp = datetime.now() - timedelta(days=random.randint(0, 30))
                    status = random.choice(["COMPLETED", "PENDING", "CANCELLED"])

                    await self.db_conn.execute(
                        """
                        INSERT INTO trading_transactions
                        (transaction_id, account_id, symbol, side, quantity, price, total_value, commission, timestamp, status)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                        f"TXN_{random.randint(100000, 999999)}",
                        account,
                        symbol,
                        side,
                        quantity,
                        price,
                        total_value,
                        commission,
                        timestamp,
                        status,
                    )

            async def test_comprehensive_financial_pipeline(self):
                """Test comprehensive financial data processing pipeline."""
                workflow = (
                    AsyncWorkflowBuilder("financial_data_pipeline")
                    .add_async_code(
                        "real_time_market_data_processing",
                        """
# Process real-time market data with technical indicators
import asyncio
from datetime import datetime, timedelta
import json

db = await get_resource("financial_db")
cache = await get_resource("cache")

# Fetch recent market data (last 7 days)
end_date = datetime.now()
start_date = end_date - timedelta(days=7)

market_query = '''
    SELECT symbol, timestamp, close_price, volume,
           LAG(close_price, 1) OVER (PARTITION BY symbol ORDER BY timestamp) as prev_close
    FROM market_data
    WHERE timestamp >= $1 AND timestamp <= $2
    ORDER BY symbol, timestamp
'''

market_data = await db.fetch(market_query, start_date, end_date)

# Calculate technical indicators
symbol_indicators = {}
processed_count = 0

for row in market_data:
    symbol = row['symbol']
    if symbol not in symbol_indicators:
        symbol_indicators[symbol] = {
            'prices': [],
            'volumes': [],
            'daily_returns': [],
            'current_price': 0,
            'volatility': 0,
            'momentum': 0
        }

    indicators = symbol_indicators[symbol]
    indicators['prices'].append(float(row['close_price']))
    indicators['volumes'].append(int(row['volume']))
    indicators['current_price'] = float(row['close_price'])

    # Calculate daily return
    if row['prev_close']:
        daily_return = (float(row['close_price']) - float(row['prev_close'])) / float(row['prev_close'])
        indicators['daily_returns'].append(daily_return)

    processed_count += 1

# Calculate volatility and momentum for each symbol
for symbol, indicators in symbol_indicators.items():
    prices = indicators['prices']
    returns = indicators['daily_returns']

    if len(prices) >= 5:  # Need minimum data points
        # Simple moving average
        sma_5 = sum(prices[-5:]) / 5
        indicators['sma_5'] = sma_5

        # Volatility (standard deviation of returns)
        if len(returns) > 1:
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            indicators['volatility'] = variance ** 0.5

        # Momentum (price change over period)
        if len(prices) >= 2:
            indicators['momentum'] = (prices[-1] - prices[0]) / prices[0]

    # Cache real-time indicators
    cache_key = f"indicators:{symbol}"
    cache_data = {
        'symbol': symbol,
        'current_price': indicators['current_price'],
        'volatility': indicators.get('volatility', 0),
        'momentum': indicators.get('momentum', 0),
        'sma_5': indicators.get('sma_5', indicators['current_price']),
        'last_updated': datetime.now().isoformat()
    }
    await cache.setex(cache_key, 300, json.dumps(cache_data, default=str))  # 5 minute TTL

result = {
    "market_data_processed": processed_count,
    "symbols_analyzed": len(symbol_indicators),
    "technical_indicators": symbol_indicators,
    "cache_updates": len(symbol_indicators),
    "analysis_timestamp": datetime.now().isoformat()
}
""",
                    )
                    .add_async_code(
                        "trading_risk_analysis",
                        """
# Perform comprehensive trading risk analysis
import json
from collections import defaultdict

db = await get_resource("financial_db")
cache = await get_resource("cache")

# Fetch trading transactions for risk analysis
trading_query = '''
    SELECT t.account_id, t.symbol, t.side, t.quantity, t.price, t.total_value,
           t.timestamp, m.close_price as current_price
    FROM trading_transactions t
    LEFT JOIN (
        SELECT symbol, close_price,
               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) as rn
        FROM market_data
    ) m ON t.symbol = m.symbol AND m.rn = 1
    WHERE t.status = 'COMPLETED'
    AND t.timestamp >= NOW() - INTERVAL '30 days'
    ORDER BY t.account_id, t.timestamp
'''

transactions = await db.fetch(trading_query)

# Calculate portfolio positions and risk metrics
account_portfolios = defaultdict(lambda: {
    'positions': defaultdict(lambda: {'quantity': 0, 'avg_cost': 0, 'total_cost': 0}),
    'total_value': 0,
    'realized_pnl': 0,
    'unrealized_pnl': 0,
    'transactions_count': 0
})

for txn in transactions:
    account = txn['account_id']
    symbol = txn['symbol']
    side = txn['side']
    quantity = int(txn['quantity'])
    price = float(txn['price'])
    current_price = float(txn['current_price']) if txn['current_price'] else price

    portfolio = account_portfolios[account]
    position = portfolio['positions'][symbol]

    if side == 'BUY':
        # Update position
        total_quantity = position['quantity'] + quantity
        total_cost = position['total_cost'] + (quantity * price)
        position['quantity'] = total_quantity
        position['total_cost'] = total_cost
        position['avg_cost'] = total_cost / total_quantity if total_quantity > 0 else 0
    elif side == 'SELL':
        # Calculate realized P&L
        if position['quantity'] >= quantity:
            realized_gain = quantity * (price - position['avg_cost'])
            portfolio['realized_pnl'] += realized_gain

            # Update position
            position['quantity'] -= quantity
            if position['quantity'] > 0:
                position['total_cost'] = position['quantity'] * position['avg_cost']
            else:
                position['total_cost'] = 0
                position['avg_cost'] = 0

    portfolio['transactions_count'] += 1

# Calculate current portfolio values and unrealized P&L
portfolio_summaries = {}
risk_alerts = []

for account_id, portfolio in account_portfolios.items():
    total_value = 0
    unrealized_pnl = 0
    positions_summary = []

    for symbol, position in portfolio['positions'].items():
        if position['quantity'] > 0:
            # Get current price from cache
            cache_key = f"indicators:{symbol}"
            cached_data = await cache.get(cache_key)

            if cached_data:
                indicator_data = json.loads(cached_data)
                current_price = indicator_data['current_price']
            else:
                current_price = position['avg_cost']  # Fallback

            current_value = position['quantity'] * current_price
            position_pnl = current_value - position['total_cost']

            positions_summary.append({
                'symbol': symbol,
                'quantity': position['quantity'],
                'avg_cost': round(position['avg_cost'], 4),
                'current_price': round(current_price, 4),
                'current_value': round(current_value, 2),
                'unrealized_pnl': round(position_pnl, 2),
                'pnl_percentage': round((position_pnl / position['total_cost']) * 100, 2) if position['total_cost'] > 0 else 0
            })

            total_value += current_value
            unrealized_pnl += position_pnl

    # Calculate risk metrics
    portfolio_size = len(positions_summary)
    avg_position_size = total_value / portfolio_size if portfolio_size > 0 else 0

    # Generate risk alerts
    for pos in positions_summary:
        # Check for large losses
        if pos['pnl_percentage'] < -20:
            risk_alerts.append({
                'account_id': account_id,
                'alert_type': 'LARGE_LOSS',
                'symbol': pos['symbol'],
                'severity': 'HIGH',
                'description': f"Position down {pos['pnl_percentage']:.1f}%",
                'current_loss': pos['unrealized_pnl']
            })

        # Check for concentration risk
        position_weight = pos['current_value'] / total_value if total_value > 0 else 0
        if position_weight > 0.3:  # More than 30% in single position
            risk_alerts.append({
                'account_id': account_id,
                'alert_type': 'CONCENTRATION_RISK',
                'symbol': pos['symbol'],
                'severity': 'MEDIUM',
                'description': f"Position represents {position_weight:.1%} of portfolio",
                'position_weight': position_weight
            })

    portfolio_summaries[account_id] = {
        'total_value': round(total_value, 2),
        'realized_pnl': round(portfolio['realized_pnl'], 2),
        'unrealized_pnl': round(unrealized_pnl, 2),
        'total_pnl': round(portfolio['realized_pnl'] + unrealized_pnl, 2),
        'positions_count': portfolio_size,
        'transactions_count': portfolio['transactions_count'],
        'positions': positions_summary,
        'avg_position_size': round(avg_position_size, 2)
    }

# Store risk alerts in database
alerts_stored = 0
for alert in risk_alerts:
    await db.execute('''
        INSERT INTO compliance_alerts (alert_type, account_id, symbol, severity, description, alert_timestamp)
        VALUES ($1, $2, $3, $4, $5, $6)
    ''', alert['alert_type'], alert['account_id'], alert['symbol'],
         alert['severity'], alert['description'], datetime.now())
    alerts_stored += 1

# Cache portfolio summaries
for account_id, summary in portfolio_summaries.items():
    cache_key = f"portfolio:{account_id}"
    await cache.setex(cache_key, 600, json.dumps(summary, default=str))  # 10 minute TTL

result = {
    "accounts_analyzed": len(portfolio_summaries),
    "total_positions": sum(len(summary['positions']) for summary in portfolio_summaries.values()),
    "risk_alerts_generated": len(risk_alerts),
    "alerts_stored": alerts_stored,
    "portfolio_summaries": portfolio_summaries,
    "risk_analysis_complete": True
}
""",
                    )
                    .add_async_code(
                        "compliance_monitoring",
                        """
# Monitor trading compliance and generate reports
import json
from datetime import datetime, timedelta

db = await get_resource("financial_db")
cache = await get_resource("cache")

# Fetch recent transactions for compliance analysis
compliance_query = '''
    SELECT t.account_id, t.symbol, t.side, t.quantity, t.price, t.total_value,
           t.timestamp, COUNT(*) OVER (PARTITION BY t.account_id, t.symbol, DATE(t.timestamp)) as daily_trades
    FROM trading_transactions t
    WHERE t.timestamp >= NOW() - INTERVAL '7 days'
    AND t.status = 'COMPLETED'
    ORDER BY t.timestamp DESC
'''

transactions = await db.fetch(compliance_query)

# Compliance checks
compliance_violations = []
daily_trading_volumes = {}
wash_sale_candidates = []

for txn in transactions:
    account_id = txn['account_id']
    symbol = txn['symbol']
    side = txn['side']
    quantity = int(txn['quantity'])
    total_value = float(txn['total_value'])
    timestamp = txn['timestamp']
    daily_trades = int(txn['daily_trades'])

    date_key = timestamp.date()

    # Track daily trading volumes
    day_key = f"{account_id}_{date_key}"
    if day_key not in daily_trading_volumes:
        daily_trading_volumes[day_key] = {
            'account_id': account_id,
            'date': date_key,
            'total_volume': 0,
            'trade_count': 0,
            'symbols_traded': set()
        }

    daily_volumes = daily_trading_volumes[day_key]
    daily_volumes['total_volume'] += total_value
    daily_volumes['trade_count'] += 1
    daily_volumes['symbols_traded'].add(symbol)

    # Check for excessive daily trading (pattern day trading rule)
    if daily_trades > 10:
        compliance_violations.append({
            'account_id': account_id,
            'violation_type': 'EXCESSIVE_DAILY_TRADING',
            'symbol': symbol,
            'details': f"{daily_trades} trades in single day",
            'severity': 'MEDIUM',
            'date': date_key
        })

    # Check for large single transactions
    if total_value > 1000000:  # $1M threshold
        compliance_violations.append({
            'account_id': account_id,
            'violation_type': 'LARGE_TRANSACTION',
            'symbol': symbol,
            'details': f"Transaction value: ${total_value:,.2f}",
            'severity': 'HIGH',
            'date': date_key
        })

# Check for wash sale patterns (buy and sell same security within 30 days)
wash_sale_query = '''
    WITH buy_sell_pairs AS (
        SELECT
            t1.account_id, t1.symbol, t1.timestamp as buy_time, t1.quantity as buy_qty,
            t2.timestamp as sell_time, t2.quantity as sell_qty,
            t2.timestamp - t1.timestamp as time_diff
        FROM trading_transactions t1
        JOIN trading_transactions t2 ON
            t1.account_id = t2.account_id AND
            t1.symbol = t2.symbol AND
            t1.side = 'BUY' AND t2.side = 'SELL' AND
            t2.timestamp > t1.timestamp AND
            t2.timestamp <= t1.timestamp + INTERVAL '30 days'
        WHERE t1.timestamp >= NOW() - INTERVAL '60 days'
        AND t1.status = 'COMPLETED' AND t2.status = 'COMPLETED'
    )
    SELECT account_id, symbol, COUNT(*) as potential_wash_sales
    FROM buy_sell_pairs
    WHERE time_diff <= INTERVAL '30 days'
    GROUP BY account_id, symbol
    HAVING COUNT(*) >= 2
'''

wash_sales = await db.fetch(wash_sale_query)

for wash_sale in wash_sales:
    compliance_violations.append({
        'account_id': wash_sale['account_id'],
        'violation_type': 'POTENTIAL_WASH_SALE',
        'symbol': wash_sale['symbol'],
        'details': f"{wash_sale['potential_wash_sales']} potential wash sale patterns",
        'severity': 'HIGH',
        'date': datetime.now().date()
    })

# Generate compliance summary
daily_volume_summary = []
for day_data in daily_trading_volumes.values():
    daily_volume_summary.append({
        'account_id': day_data['account_id'],
        'date': str(day_data['date']),
        'total_volume': round(day_data['total_volume'], 2),
        'trade_count': day_data['trade_count'],
        'symbols_count': len(day_data['symbols_traded']),
        'avg_trade_size': round(day_data['total_volume'] / day_data['trade_count'], 2)
    })

# Store compliance violations
violations_stored = 0
for violation in compliance_violations:
    await db.execute('''
        INSERT INTO compliance_alerts (alert_type, account_id, symbol, severity, description, alert_timestamp)
        VALUES ($1, $2, $3, $4, $5, $6)
    ''', violation['violation_type'], violation['account_id'], violation['symbol'],
         violation['severity'], violation['details'], datetime.now())
    violations_stored += 1

# Generate compliance score by account
account_scores = {}
for account_id in set(txn['account_id'] for txn in transactions):
    account_violations = [v for v in compliance_violations if v['account_id'] == account_id]

    # Calculate compliance score (100 - penalty points)
    penalty_points = 0
    for violation in account_violations:
        if violation['severity'] == 'HIGH':
            penalty_points += 15
        elif violation['severity'] == 'MEDIUM':
            penalty_points += 8
        else:
            penalty_points += 3

    compliance_score = max(0, 100 - penalty_points)
    account_scores[account_id] = {
        'compliance_score': compliance_score,
        'violation_count': len(account_violations),
        'status': 'COMPLIANT' if compliance_score >= 80 else 'AT_RISK' if compliance_score >= 60 else 'NON_COMPLIANT'
    }

# Cache compliance data
compliance_summary = {
    'total_violations': len(compliance_violations),
    'violations_by_type': {},
    'account_scores': account_scores,
    'daily_volumes': daily_volume_summary,
    'report_timestamp': datetime.now().isoformat()
}

for violation in compliance_violations:
    vtype = violation['violation_type']
    compliance_summary['violations_by_type'][vtype] = compliance_summary['violations_by_type'].get(vtype, 0) + 1

await cache.setex("compliance:summary", 3600, json.dumps(compliance_summary, default=str))

result = {
    "compliance_violations": compliance_violations,
    "violations_stored": violations_stored,
    "accounts_analyzed": len(account_scores),
    "compliance_summary": compliance_summary,
    "wash_sales_detected": len(wash_sales),
    "daily_volume_entries": len(daily_volume_summary),
    "monitoring_complete": True
}
""",
                    )
                    .add_connection(
                        "real_time_market_data_processing",
                        "technical_indicators",
                        "trading_risk_analysis",
                        "market_indicators",
                    )
                    .add_connection(
                        "trading_risk_analysis",
                        "portfolio_summaries",
                        "compliance_monitoring",
                        "portfolios",
                    )
                    .build()
                )

                # Execute financial pipeline with realistic timeout
                async with self.assert_time_limit(60.0):
                    result = await self.execute_workflow(workflow, {})

                # Comprehensive financial pipeline validation
                self.assert_workflow_success(result)

                # Verify market data processing
                market_output = result.get_output("real_time_market_data_processing")
                assert (
                    market_output["market_data_processed"] > 0
                ), "Should process market data"
                assert (
                    market_output["symbols_analyzed"] >= 5
                ), "Should analyze multiple symbols"
                assert market_output["cache_updates"] > 0, "Should update cache"

                # Verify risk analysis
                risk_output = result.get_output("trading_risk_analysis")
                assert risk_output["accounts_analyzed"] > 0, "Should analyze accounts"
                assert risk_output["total_positions"] >= 0, "Should track positions"
                assert (
                    "portfolio_summaries" in risk_output
                ), "Should generate portfolio summaries"

                # Verify compliance monitoring
                compliance_output = result.get_output("compliance_monitoring")
                assert (
                    compliance_output["accounts_analyzed"] > 0
                ), "Should analyze compliance"
                assert compliance_output[
                    "monitoring_complete"
                ], "Should complete monitoring"
                assert (
                    "compliance_summary" in compliance_output
                ), "Should generate compliance summary"

                # Financial-specific validations
                portfolios = risk_output["portfolio_summaries"]
                for account_id, portfolio in portfolios.items():
                    assert isinstance(
                        portfolio["total_value"], (int, float)
                    ), "Should calculate portfolio value"
                    assert isinstance(
                        portfolio["total_pnl"], (int, float)
                    ), "Should calculate P&L"
                    assert (
                        portfolio["transactions_count"] > 0
                    ), "Should have transactions"

                compliance_summary = compliance_output["compliance_summary"]
                assert "account_scores" in compliance_summary, "Should score accounts"
                assert (
                    "violations_by_type" in compliance_summary
                ), "Should categorize violations"

            async def tearDown(self):
                """Clean up financial pipeline resources."""
                if hasattr(self, "db_conn"):
                    await self.db_conn.close()
                if hasattr(self, "redis_client"):
                    await self.redis_client.aclose()
                if hasattr(self, "financial_db"):
                    await self.financial_db.cleanup()
                if hasattr(self, "redis_container"):
                    self.redis_container.stop()
                    self.redis_container.remove()
                await super().tearDown()

        async with FinancialDataPipelineTest("financial_pipeline_test") as test:
            await test.test_comprehensive_financial_pipeline()

    async def test_iot_sensor_data_processing_pipeline(self):
        """Test IoT sensor data processing with time-series analysis."""

        class IoTDataPipelineTest(AsyncWorkflowTestCase):
            async def setUp(self):
                await super().setUp()

                # Set up time-series database
                self.timeseries_db = await AsyncWorkflowFixtures.create_test_database(
                    engine="postgresql",
                    database="iot_timeseries_db",
                    user="iot_user",
                    password="iot_secure456",
                )

                try:
                    import asyncpg

                    self.db_conn = await asyncpg.connect(
                        self.timeseries_db.connection_string
                    )
                    await self.create_test_resource(
                        "timeseries_db", lambda: self.db_conn
                    )

                    # Set up Redis for real-time aggregation
                    import docker

                    client = docker.from_env()
                    self.redis_container = client.containers.execute(
                        "redis:7-alpine",
                        ports={"6379/tcp": None},
                        detach=True,
                        remove=False,
                    )

                    self.redis_container.reload()
                    redis_port = int(
                        self.redis_container.ports["6379/tcp"][0]["HostPort"]
                    )
                    await asyncio.sleep(2)

                    import aioredis

                    self.redis_client = aioredis.from_url(
                        f"redis://localhost:{redis_port}"
                    )
                    await self.create_test_resource("cache", lambda: self.redis_client)

                    # Set up IoT schema and generate sensor data
                    await self._setup_iot_schema()

                except ImportError as e:
                    pytest.skip(f"Required dependencies not available: {e}")

            async def _setup_iot_schema(self):
                """Set up IoT sensor data schema."""
                # Device registry
                await self.db_conn.execute(
                    """
                    CREATE TABLE devices (
                        device_id VARCHAR(50) PRIMARY KEY,
                        device_type VARCHAR(30),
                        location VARCHAR(100),
                        building VARCHAR(50),
                        floor INTEGER,
                        status VARCHAR(20) DEFAULT 'ACTIVE',
                        last_seen TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                # Sensor readings (time-series data)
                await self.db_conn.execute(
                    """
                    CREATE TABLE sensor_readings (
                        id SERIAL PRIMARY KEY,
                        device_id VARCHAR(50),
                        sensor_type VARCHAR(30),
                        reading_value DECIMAL(10,4),
                        unit VARCHAR(10),
                        quality_score DECIMAL(3,2),
                        timestamp TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW(),
                        FOREIGN KEY (device_id) REFERENCES devices(device_id)
                    )
                """
                )

                # Aggregated metrics
                await self.db_conn.execute(
                    """
                    CREATE TABLE sensor_aggregates (
                        id SERIAL PRIMARY KEY,
                        device_id VARCHAR(50),
                        sensor_type VARCHAR(30),
                        time_window VARCHAR(10), -- '1min', '5min', '1hour'
                        window_start TIMESTAMP,
                        avg_value DECIMAL(10,4),
                        min_value DECIMAL(10,4),
                        max_value DECIMAL(10,4),
                        stddev_value DECIMAL(10,4),
                        sample_count INTEGER,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                # Anomaly alerts
                await self.db_conn.execute(
                    """
                    CREATE TABLE anomaly_alerts (
                        id SERIAL PRIMARY KEY,
                        device_id VARCHAR(50),
                        sensor_type VARCHAR(30),
                        anomaly_type VARCHAR(50),
                        severity VARCHAR(10),
                        reading_value DECIMAL(10,4),
                        expected_range_min DECIMAL(10,4),
                        expected_range_max DECIMAL(10,4),
                        confidence_score DECIMAL(3,2),
                        alert_timestamp TIMESTAMP,
                        resolved BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                # Generate realistic IoT device data
                await self._generate_iot_data()

            async def _generate_iot_data(self):
                """Generate realistic IoT sensor data."""
                import random
                from datetime import datetime, timedelta

                # Create devices
                buildings = ["Building_A", "Building_B", "Building_C"]
                device_types = [
                    "temperature_sensor",
                    "humidity_sensor",
                    "pressure_sensor",
                    "vibration_sensor",
                    "power_meter",
                ]

                devices = []
                for i in range(50):
                    device = {
                        "device_id": f"IOT_{i+1:03d}",
                        "device_type": random.choice(device_types),
                        "location": f"Room_{random.randint(101, 350)}",
                        "building": random.choice(buildings),
                        "floor": random.randint(1, 5),
                        "status": random.choice(
                            ["ACTIVE", "ACTIVE", "ACTIVE", "MAINTENANCE"]
                        ),  # Mostly active
                        "last_seen": datetime.now()
                        - timedelta(minutes=random.randint(1, 60)),
                    }
                    devices.append(device)

                    await self.db_conn.execute(
                        """
                        INSERT INTO devices (device_id, device_type, location, building, floor, status, last_seen)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                        device["device_id"],
                        device["device_type"],
                        device["location"],
                        device["building"],
                        device["floor"],
                        device["status"],
                        device["last_seen"],
                    )

                # Generate sensor readings for last 24 hours
                base_time = datetime.now() - timedelta(hours=24)

                for device in devices:
                    if device["status"] != "ACTIVE":
                        continue

                    device_type = device["device_type"]

                    # Define realistic ranges for different sensor types
                    if device_type == "temperature_sensor":
                        base_value = 22.0  # 22°C
                        unit = "C"
                        noise_range = 3.0
                    elif device_type == "humidity_sensor":
                        base_value = 45.0  # 45%
                        unit = "%"
                        noise_range = 10.0
                    elif device_type == "pressure_sensor":
                        base_value = 1013.25  # 1013.25 hPa
                        unit = "hPa"
                        noise_range = 5.0
                    elif device_type == "vibration_sensor":
                        base_value = 0.5  # 0.5 m/s²
                        unit = "m/s2"
                        noise_range = 0.3
                    else:  # power_meter
                        base_value = 150.0  # 150W
                        unit = "W"
                        noise_range = 30.0

                    # Generate readings every 5 minutes for 24 hours
                    for minutes in range(0, 24 * 60, 5):  # Every 5 minutes
                        timestamp = base_time + timedelta(minutes=minutes)

                        # Add some realistic patterns (daily cycles, random noise)
                        hour_of_day = timestamp.hour

                        # Daily pattern (higher values during day)
                        daily_factor = 1.0 + 0.2 * math.sin(
                            (hour_of_day - 6) * math.pi / 12
                        )

                        # Random noise
                        noise = random.uniform(-noise_range, noise_range) * 0.3

                        # Occasional anomalies (5% chance)
                        if random.random() < 0.05:
                            anomaly_factor = random.choice(
                                [0.5, 1.8]
                            )  # 50% lower or 80% higher
                            quality_score = random.uniform(
                                0.3, 0.7
                            )  # Lower quality for anomalies
                        else:
                            anomaly_factor = 1.0
                            quality_score = random.uniform(0.85, 1.0)

                        reading_value = (
                            base_value * daily_factor * anomaly_factor + noise
                        )

                        await self.db_conn.execute(
                            """
                            INSERT INTO sensor_readings (device_id, sensor_type, reading_value, unit, quality_score, timestamp)
                            VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                            device["device_id"],
                            device_type,
                            reading_value,
                            unit,
                            quality_score,
                            timestamp,
                        )

            async def test_iot_sensor_processing_pipeline(self):
                """Test comprehensive IoT sensor data processing."""
                workflow = (
                    AsyncWorkflowBuilder("iot_sensor_pipeline")
                    .add_async_code(
                        "real_time_sensor_ingestion",
                        """
# Process real-time sensor data with quality filtering
import math
import json
from datetime import datetime, timedelta
from collections import defaultdict

db = await get_resource("timeseries_db")
cache = await get_resource("cache")

# Get recent sensor readings (last 2 hours)
recent_cutoff = datetime.now() - timedelta(hours=2)

readings_query = '''
    SELECT sr.device_id, sr.sensor_type, sr.reading_value, sr.unit,
           sr.quality_score, sr.timestamp, d.building, d.floor, d.location
    FROM sensor_readings sr
    JOIN devices d ON sr.device_id = d.device_id
    WHERE sr.timestamp >= $1
    AND d.status = 'ACTIVE'
    ORDER BY sr.timestamp DESC
'''

readings = await db.fetch(readings_query, recent_cutoff)

# Process and filter readings
processed_readings = []
quality_stats = defaultdict(list)
device_stats = defaultdict(lambda: {
    'readings_count': 0,
    'avg_quality': 0,
    'latest_value': 0,
    'latest_timestamp': None
})

high_quality_count = 0
total_readings = len(readings)

for reading in readings:
    device_id = reading['device_id']
    sensor_type = reading['sensor_type']
    value = float(reading['reading_value'])
    quality = float(reading['quality_score'])
    timestamp = reading['timestamp']

    # Quality filtering (keep readings with quality >= 0.7)
    if quality >= 0.7:
        processed_readings.append({
            'device_id': device_id,
            'sensor_type': sensor_type,
            'value': value,
            'unit': reading['unit'],
            'quality': quality,
            'timestamp': timestamp.isoformat(),
            'building': reading['building'],
            'floor': reading['floor'],
            'location': reading['location']
        })
        high_quality_count += 1

    # Track quality statistics
    quality_stats[sensor_type].append(quality)

    # Update device statistics
    stats = device_stats[device_id]
    stats['readings_count'] += 1
    stats['avg_quality'] += quality
    stats['latest_value'] = value
    stats['latest_timestamp'] = timestamp

# Finalize device statistics
for device_id, stats in device_stats.items():
    if stats['readings_count'] > 0:
        stats['avg_quality'] = stats['avg_quality'] / stats['readings_count']

# Calculate quality statistics by sensor type
quality_summary = {}
for sensor_type, qualities in quality_stats.items():
    if qualities:
        quality_summary[sensor_type] = {
            'avg_quality': sum(qualities) / len(qualities),
            'min_quality': min(qualities),
            'max_quality': max(qualities),
            'readings_count': len(qualities)
        }

# Cache current device states
for device_id, stats in device_stats.items():
    cache_key = f"device_state:{device_id}"
    device_state = {
        'device_id': device_id,
        'latest_value': stats['latest_value'],
        'avg_quality': stats['avg_quality'],
        'readings_count': stats['readings_count'],
        'last_updated': stats['latest_timestamp'].isoformat() if stats['latest_timestamp'] else None
    }
    await cache.setex(cache_key, 600, json.dumps(device_state, default=str))

result = {
    "total_readings_processed": total_readings,
    "high_quality_readings": high_quality_count,
    "quality_filter_rate": high_quality_count / total_readings if total_readings > 0 else 0,
    "processed_readings": processed_readings,
    "device_statistics": dict(device_stats),
    "quality_summary": quality_summary,
    "devices_active": len(device_stats),
    "processing_timestamp": datetime.now().isoformat()
}
""",
                    )
                    .add_async_code(
                        "time_series_aggregation",
                        """
# Perform time-series aggregation and trend analysis
import math
import statistics
from datetime import datetime, timedelta
from collections import defaultdict

db = await get_resource("timeseries_db")
cache = await get_resource("cache")

# Group readings by device and sensor type for aggregation
device_series = defaultdict(lambda: defaultdict(list))

for reading in processed_readings:
    device_id = reading['device_id']
    sensor_type = reading['sensor_type']
    device_series[device_id][sensor_type].append(reading)

# Calculate aggregations for different time windows
aggregations = []
trend_analysis = {}

for device_id, sensors in device_series.items():
    for sensor_type, readings in sensors.items():
        if len(readings) < 5:  # Need minimum data points
            continue

        # Sort readings by timestamp
        readings.sort(key=lambda x: x['timestamp'])
        values = [r['value'] for r in readings]

        # Calculate basic statistics
        avg_value = statistics.mean(values)
        min_value = min(values)
        max_value = max(values)

        # Calculate standard deviation if enough data
        if len(values) >= 3:
            stddev_value = statistics.stdev(values)
        else:
            stddev_value = 0

        # Time window aggregation (last hour)
        now = datetime.now()
        hour_start = now.replace(minute=0, second=0, microsecond=0)

        aggregation = {
            'device_id': device_id,
            'sensor_type': sensor_type,
            'time_window': '1hour',
            'window_start': hour_start,
            'avg_value': round(avg_value, 4),
            'min_value': round(min_value, 4),
            'max_value': round(max_value, 4),
            'stddev_value': round(stddev_value, 4),
            'sample_count': len(readings)
        }
        aggregations.append(aggregation)

        # Trend analysis
        if len(values) >= 10:
            # Simple linear trend calculation
            x_values = list(range(len(values)))
            n = len(values)

            sum_x = sum(x_values)
            sum_y = sum(values)
            sum_xy = sum(x * y for x, y in zip(x_values, values))
            sum_x2 = sum(x * x for x in x_values)

            # Linear regression slope
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)

            # Classify trend
            if abs(slope) < 0.01:
                trend = 'stable'
            elif slope > 0:
                trend = 'increasing'
            else:
                trend = 'decreasing'

            trend_analysis[f"{device_id}_{sensor_type}"] = {
                'device_id': device_id,
                'sensor_type': sensor_type,
                'trend': trend,
                'slope': round(slope, 6),
                'confidence': min(1.0, len(values) / 20),  # More data = higher confidence
                'latest_value': values[-1],
                'avg_value': avg_value
            }

# Store aggregations in database
stored_aggregations = 0
for agg in aggregations:
    await db.execute('''
        INSERT INTO sensor_aggregates
        (device_id, sensor_type, time_window, window_start, avg_value, min_value, max_value, stddev_value, sample_count)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    ''', agg['device_id'], agg['sensor_type'], agg['time_window'], agg['window_start'],
         agg['avg_value'], agg['min_value'], agg['max_value'], agg['stddev_value'], agg['sample_count'])
    stored_aggregations += 1

# Cache trend analysis results
for trend_key, trend_data in trend_analysis.items():
    cache_key = f"trend:{trend_key}"
    await cache.setex(cache_key, 3600, json.dumps(trend_data, default=str))

# Calculate overall system health metrics
system_metrics = {
    'total_active_devices': len(device_series),
    'sensor_types_active': len(set(reading['sensor_type'] for reading in processed_readings)),
    'avg_readings_per_device': len(processed_readings) / len(device_series) if device_series else 0,
    'trends_detected': len(trend_analysis),
    'aggregations_created': len(aggregations)
}

result = {
    "aggregations_computed": len(aggregations),
    "aggregations_stored": stored_aggregations,
    "trend_analysis": trend_analysis,
    "system_health_metrics": system_metrics,
    "time_series_summary": {
        "devices_analyzed": len(device_series),
        "sensor_types": list(set(agg['sensor_type'] for agg in aggregations)),
        "time_window_coverage": "1hour",
        "analysis_completeness": 100.0
    }
}
""",
                    )
                    .add_async_code(
                        "anomaly_detection",
                        """
# Detect anomalies in sensor data using statistical methods
import math
import statistics
import json
from datetime import datetime

db = await get_resource("timeseries_db")
cache = await get_resource("cache")

# Retrieve historical baseline data for anomaly detection
baseline_query = '''
    SELECT device_id, sensor_type, avg_value, stddev_value
    FROM sensor_aggregates
    WHERE window_start >= NOW() - INTERVAL '24 hours'
    AND sample_count >= 10
'''

baselines = await db.fetch(baseline_query)

# Create baseline lookup
baseline_lookup = {}
for baseline in baselines:
    key = f"{baseline['device_id']}_{baseline['sensor_type']}"
    if key not in baseline_lookup:
        baseline_lookup[key] = []
    baseline_lookup[key].append({
        'avg': float(baseline['avg_value']),
        'stddev': float(baseline['stddev_value'])
    })

# Calculate stable baselines (average of recent aggregates)
stable_baselines = {}
for key, baseline_list in baseline_lookup.items():
    if len(baseline_list) >= 3:  # Need multiple data points
        avg_of_avgs = statistics.mean([b['avg'] for b in baseline_list])
        avg_of_stddevs = statistics.mean([b['stddev'] for b in baseline_list])

        stable_baselines[key] = {
            'expected_avg': avg_of_avgs,
            'expected_stddev': max(avg_of_stddevs, 0.1),  # Minimum stddev to avoid division by zero
            'data_points': len(baseline_list)
        }

# Analyze current readings for anomalies
anomalies_detected = []
device_anomaly_scores = {}

for reading in processed_readings:
    device_id = reading['device_id']
    sensor_type = reading['sensor_type']
    current_value = reading['value']
    timestamp = reading['timestamp']

    baseline_key = f"{device_id}_{sensor_type}"

    if baseline_key in stable_baselines:
        baseline = stable_baselines[baseline_key]
        expected_avg = baseline['expected_avg']
        expected_stddev = baseline['expected_stddev']

        # Calculate z-score (number of standard deviations from mean)
        z_score = abs(current_value - expected_avg) / expected_stddev

        # Define anomaly thresholds
        if z_score > 3.0:  # Very high anomaly
            severity = 'CRITICAL'
            anomaly_type = 'STATISTICAL_OUTLIER'
        elif z_score > 2.5:  # High anomaly
            severity = 'HIGH'
            anomaly_type = 'STATISTICAL_DEVIATION'
        elif z_score > 2.0:  # Medium anomaly
            severity = 'MEDIUM'
            anomaly_type = 'TREND_DEVIATION'
        else:
            continue  # Not anomalous enough

        # Calculate confidence score
        confidence = min(1.0, z_score / 4.0)  # Scale z-score to confidence

        # Define expected range
        range_multiplier = 2.0  # 2 standard deviations
        expected_min = expected_avg - (expected_stddev * range_multiplier)
        expected_max = expected_avg + (expected_stddev * range_multiplier)

        anomaly = {
            'device_id': device_id,
            'sensor_type': sensor_type,
            'anomaly_type': anomaly_type,
            'severity': severity,
            'reading_value': current_value,
            'expected_range_min': round(expected_min, 4),
            'expected_range_max': round(expected_max, 4),
            'z_score': round(z_score, 4),
            'confidence_score': round(confidence, 4),
            'alert_timestamp': datetime.now(),
            'building': reading['building'],
            'location': reading['location']
        }

        anomalies_detected.append(anomaly)

        # Track device anomaly scores
        if device_id not in device_anomaly_scores:
            device_anomaly_scores[device_id] = {
                'device_id': device_id,
                'anomaly_count': 0,
                'max_z_score': 0,
                'avg_z_score': 0,
                'severity_counts': {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0}
            }

        device_score = device_anomaly_scores[device_id]
        device_score['anomaly_count'] += 1
        device_score['max_z_score'] = max(device_score['max_z_score'], z_score)
        device_score['avg_z_score'] = ((device_score['avg_z_score'] * (device_score['anomaly_count'] - 1)) + z_score) / device_score['anomaly_count']
        device_score['severity_counts'][severity] += 1

# Store anomalies in database
anomalies_stored = 0
for anomaly in anomalies_detected:
    await db.execute('''
        INSERT INTO anomaly_alerts
        (device_id, sensor_type, anomaly_type, severity, reading_value,
         expected_range_min, expected_range_max, confidence_score, alert_timestamp)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    ''', anomaly['device_id'], anomaly['sensor_type'], anomaly['anomaly_type'],
         anomaly['severity'], anomaly['reading_value'], anomaly['expected_range_min'],
         anomaly['expected_range_max'], anomaly['confidence_score'], anomaly['alert_timestamp'])
    anomalies_stored += 1

# Generate anomaly summary by building and floor
building_anomaly_summary = {}
for anomaly in anomalies_detected:
    building = anomaly['building']
    if building not in building_anomaly_summary:
        building_anomaly_summary[building] = {
            'building': building,
            'total_anomalies': 0,
            'by_severity': {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0},
            'affected_devices': set()
        }

    summary = building_anomaly_summary[building]
    summary['total_anomalies'] += 1
    summary['by_severity'][anomaly['severity']] += 1
    summary['affected_devices'].add(anomaly['device_id'])

# Convert sets to counts for JSON serialization
for building, summary in building_anomaly_summary.items():
    summary['affected_devices'] = len(summary['affected_devices'])

# Cache anomaly results
anomaly_cache_data = {
    'total_anomalies': len(anomalies_detected),
    'by_severity': {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0},
    'devices_affected': len(device_anomaly_scores),
    'building_summary': building_anomaly_summary,
    'detection_timestamp': datetime.now().isoformat()
}

for anomaly in anomalies_detected:
    anomaly_cache_data['by_severity'][anomaly['severity']] += 1

await cache.setex("anomalies:summary", 1800, json.dumps(anomaly_cache_data, default=str))

result = {
    "anomalies_detected": anomalies_detected,
    "anomalies_stored": anomalies_stored,
    "devices_with_anomalies": len(device_anomaly_scores),
    "device_anomaly_scores": device_anomaly_scores,
    "building_anomaly_summary": building_anomaly_summary,
    "detection_statistics": {
        "baselines_available": len(stable_baselines),
        "readings_analyzed": len(processed_readings),
        "anomaly_rate": len(anomalies_detected) / len(processed_readings) if processed_readings else 0,
        "critical_anomalies": len([a for a in anomalies_detected if a['severity'] == 'CRITICAL'])
    }
}
""",
                    )
                    .add_connection(
                        "real_time_sensor_ingestion",
                        "processed_readings",
                        "time_series_aggregation",
                        "processed_readings",
                    )
                    .add_connection(
                        "time_series_aggregation",
                        "aggregations_computed",
                        "anomaly_detection",
                        "aggregation_count",
                    )
                    .add_connection(
                        "real_time_sensor_ingestion",
                        "processed_readings",
                        "anomaly_detection",
                        "processed_readings",
                    )
                    .build()
                )

                # Execute IoT pipeline with extended timeout
                async with self.assert_time_limit(90.0):
                    result = await self.execute_workflow(workflow, {})

                # Comprehensive IoT pipeline validation
                self.assert_workflow_success(result)

                # Verify sensor data ingestion
                ingestion_output = result.get_output("real_time_sensor_ingestion")
                assert (
                    ingestion_output["total_readings_processed"] > 0
                ), "Should process sensor readings"
                assert (
                    ingestion_output["quality_filter_rate"] > 0.5
                ), "Should have reasonable quality rate"
                assert (
                    ingestion_output["devices_active"] > 0
                ), "Should have active devices"

                # Verify time-series aggregation
                aggregation_output = result.get_output("time_series_aggregation")
                assert (
                    aggregation_output["aggregations_computed"] > 0
                ), "Should compute aggregations"
                assert (
                    aggregation_output["aggregations_stored"] > 0
                ), "Should store aggregations"

                system_health = aggregation_output["system_health_metrics"]
                assert (
                    system_health["total_active_devices"] > 0
                ), "Should track active devices"
                assert (
                    system_health["sensor_types_active"] > 0
                ), "Should have active sensor types"

                # Verify anomaly detection
                anomaly_output = result.get_output("anomaly_detection")
                detection_stats = anomaly_output["detection_statistics"]
                assert (
                    detection_stats["readings_analyzed"] > 0
                ), "Should analyze readings"
                assert (
                    detection_stats["baselines_available"] >= 0
                ), "Should have baseline data"
                assert (
                    detection_stats["anomaly_rate"] >= 0
                ), "Should calculate anomaly rate"

                # IoT-specific validations
                if anomaly_output["anomalies_detected"]:
                    anomalies = anomaly_output["anomalies_detected"]
                    for anomaly in anomalies[:3]:  # Check first few anomalies
                        assert anomaly["severity"] in [
                            "CRITICAL",
                            "HIGH",
                            "MEDIUM",
                        ], "Should have valid severity"
                        assert (
                            anomaly["confidence_score"] > 0
                        ), "Should have confidence score"
                        assert "z_score" in anomaly, "Should calculate z-score"

                building_summary = anomaly_output["building_anomaly_summary"]
                for building, summary in building_summary.items():
                    assert (
                        summary["total_anomalies"] > 0
                    ), "Building should have anomalies"
                    assert (
                        summary["affected_devices"] > 0
                    ), "Should track affected devices"

            async def tearDown(self):
                """Clean up IoT pipeline resources."""
                if hasattr(self, "db_conn"):
                    await self.db_conn.close()
                if hasattr(self, "redis_client"):
                    await self.redis_client.aclose()
                if hasattr(self, "timeseries_db"):
                    await self.timeseries_db.cleanup()
                if hasattr(self, "redis_container"):
                    self.redis_container.stop()
                    self.redis_container.remove()
                await super().tearDown()

        async with IoTDataPipelineTest("iot_pipeline_test") as test:
            await test.test_iot_sensor_processing_pipeline()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
