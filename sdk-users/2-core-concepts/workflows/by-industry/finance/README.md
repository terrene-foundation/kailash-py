# Finance Industry Workflows

This directory contains production-ready workflow implementations for common financial services use cases. Each workflow demonstrates best practices using the Kailash SDK with real data processing, AI integration, and comprehensive error handling.

## Available Workflows

### 1. Credit Risk Assessment (`credit_risk_assessment.py`)
**Purpose**: Comprehensive credit risk evaluation for loan applications and credit decisions.

**Key Features**:
- Customer profile analysis with transaction history
- Risk metric calculation (payment frequency, spending patterns)
- AI-powered risk assessment with explanations
- Automated risk categorization (low/medium/high/critical)
- Detailed credit reports with recommendations
- Uses `PythonCodeNode.from_function()` for maintainable code

**Use Cases**:
- Loan application processing
- Credit limit adjustments
- Customer tier evaluation
- Portfolio risk management

**Data Requirements**:
- `customers.csv`: Customer profiles with tier information
- `transactions.csv`: Historical transaction data

### 2. Fraud Detection (`fraud_detection.py`)
**Purpose**: Real-time transaction monitoring and fraud pattern detection.

**Key Features**:
- Velocity checking (frequency and amount patterns)
- Statistical anomaly detection (z-scores, ratios)
- Time-based pattern analysis
- AI-enhanced fraud scoring
- Automated alert generation
- Uses `PythonCodeNode.from_function()` for complex logic

**Use Cases**:
- Payment processing security
- Account takeover detection
- Card testing prevention
- Real-time transaction monitoring

**Data Requirements**:
- `transactions.json`: Real-time transaction stream
- `customers.csv`: Customer baseline data

### 3. Portfolio Optimization (`portfolio_optimization.py`)
**Purpose**: Investment portfolio analysis and rebalancing recommendations.

**Key Features**:
- Portfolio metrics calculation (returns, volatility, Sharpe ratio)
- Risk-based asset allocation
- Modern Portfolio Theory optimization
- AI market insights integration
- Detailed rebalancing plans
- Efficient frontier calculation

**Use Cases**:
- Wealth management
- Robo-advisor systems
- Investment strategy optimization
- Risk-adjusted portfolio management

**Data Requirements**:
- `portfolio_holdings.csv`: Current portfolio positions
- `market_data.csv`: Historical price data (auto-generated if missing)

### 4. Trading Signals (`trading_signals.py`)
**Purpose**: Algorithmic trading signal generation with technical analysis.

**Key Features**:
- Technical indicator calculation (MACD, RSI, Bollinger Bands)
- Trend following and mean reversion strategies
- AI-powered market sentiment analysis
- Risk-adjusted position sizing
- Automated trade alerts with stop-loss/take-profit levels
- Support and resistance level analysis

**Use Cases**:
- Algorithmic trading systems
- Investment research platforms
- Trading desk automation
- Market analysis tools

**Data Requirements**:
- `stock_prices.csv`: Historical price data (auto-generated if missing)
- `stock_volumes.csv`: Volume data (auto-generated if missing)

### 5. Simple Credit Risk (`credit_risk_simple.py`)
**Purpose**: Streamlined risk assessment using single data source, ideal for quick evaluations.

**Key Features**:
- Single CSV data source processing
- Automatic data type conversion
- Activity-based risk scoring
- Business rule recommendations

**Data Requirements**:
- Customer value data with claims/amounts

### 6. Portfolio Analysis with Connection Pool (`portfolio_analysis_with_connection_pool.py`) ⭐ **NEW**
**Purpose**: Production-grade portfolio analysis using WorkflowConnectionPool for high-performance database operations.

**Key Features**:
- WorkflowConnectionPool with automatic connection management
- Connection health monitoring and auto-recycling
- High-concurrency portfolio analysis (50+ concurrent queries)
- Transaction support for data consistency
- Real-time pool performance monitoring
- Fault-tolerant actor-based architecture

**Use Cases**:
- High-frequency portfolio valuations
- Real-time risk calculations
- Multi-portfolio analysis platforms
- Production trading systems

**Data Requirements**:
- PostgreSQL database with portfolio schema
- Market price data
- Portfolio metadata and positions

**Performance Benefits**:
- 10x+ improvement over single connections
- Automatic connection reuse
- Reduced database load
- Better scalability under concurrent load

## Best Practices Demonstrated

### 1. **Data Processing**
- Centralized data path management using `examples.utils.data_paths`
- Automatic data type conversion and validation
- Handling missing or incomplete data gracefully
- DataFrame operations for efficient processing
- Production database operations with WorkflowConnectionPool

### 2. **Code Organization**
- All workflows use `PythonCodeNode.from_function()` for better maintainability
- Clear separation of concerns with dedicated functions
- Comprehensive documentation and type hints
- No hardcoded file paths

### 3. **AI Integration**
- Structured prompts for consistent AI responses
- JSON format enforcement for parsing reliability
- Fallback handling for AI failures
- Context-aware prompt engineering

### 4. **Risk Management**
- Multiple validation layers
- Conservative default values
- Clear risk categorization and thresholds
- Explainable risk scoring

### 5. **Production Readiness**
- Comprehensive error handling
- Detailed logging and reporting
- Performance optimization for large datasets
- JSON serialization for all outputs
- Connection pooling for database scalability
- Health monitoring and auto-recovery

## Quick Start

1. **Install dependencies**:
```bash
pip install kailash pandas numpy
```

2. **Prepare data files** (or use auto-generated sample data):
```bash
# Create data directories
mkdir -p data/inputs/finance
mkdir -p data/outputs/json

# Copy your data files or let workflows generate samples
```

3. **Run a workflow**:
```bash
python scripts/credit_risk_assessment.py
python scripts/fraud_detection.py
python scripts/portfolio_optimization.py
python scripts/trading_signals.py
python scripts/credit_risk_simple.py
python scripts/portfolio_analysis_with_connection_pool.py  # Requires PostgreSQL
```

## Output Structure

All workflows generate structured JSON reports in `data/outputs/json/`:
- `credit_risk_reports.json`: Credit assessment results
- `fraud_detection_report.json`: Fraud alerts and analysis
- `portfolio_optimization_report.json`: Rebalancing recommendations
- `trading_signals_report.json`: Trading alerts and market analysis
- `credit_risk_report.json`: Simple risk assessment

## Common Patterns

### 1. Using from_function Pattern
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def workflow.()  # Type signature example -> dict:
    """Process with full IDE support."""
    # Your complex logic here
    return {'result': processed_data}

node = PythonCodeNode.from_function(
    name="processor",
    func=process_data
)

```

### 2. Data Integration
```python
from examples.utils.data_paths import get_input_data_path, get_output_data_path

# Input data from /data/inputs/
data_file = get_input_data_path("customer_value.csv")

# Output to /data/outputs/
report_file = get_output_data_path("risk_report.json", "json")

```

### 3. Risk Scoring
```python
risk_score = (
    activity_score * 0.5 +
    financial_score * 0.3 +
    history_score * 0.2
)

```

### 4. AI Integration
```python
analyzer = LLMAgentNode(
    model="gpt-4",
    system_prompt="You are a financial risk expert...",
    prompt="Analyze: {{data}}"
)

```

## Customization

Each workflow can be customized by:
1. Modifying risk thresholds and parameters in the functions
2. Adjusting AI prompts for different analysis styles
3. Adding additional data sources or indicators
4. Implementing custom business rules

## Integration

These workflows can be integrated into larger systems via:
- REST API endpoints (see `kailash.api.workflow_api`)
- Message queues for real-time processing
- Scheduled batch processing
- Event-driven architectures

## Performance Considerations

- Workflows are optimized for datasets up to 100k records
- Use parallel processing for larger datasets
- Consider caching for frequently accessed reference data
- Implement streaming for real-time data sources

## Security Notes

- Never commit real customer data to version control
- Use environment variables for API keys
- Implement proper access controls in production
- Audit all AI-generated recommendations before execution

## Node Recommendations

- **CSVReaderNode**: For structured financial data
- **JSONReaderNode**: For real-time transaction streams
- **PythonCodeNode.from_function()**: For complex calculations
- **LLMAgentNode**: For intelligent analysis and recommendations
- **JSONWriterNode**: For structured report output
- **SwitchNode**: For routing based on risk levels
- **WorkflowConnectionPool**: For production database operations
- **AsyncSQLDatabaseNode**: For simple async queries (non-production)

## Training Resources

See the Kailash SDK repository for training examples.

These include:
- Common mistakes and correct patterns
- Wrong vs. right implementations
- Best practices for financial workflows
- Performance optimization techniques

## Support

For questions or issues:
- Check the [Kailash documentation](https://docs.kailash.io)
- Review error messages in `shared/mistakes/`
- Consult the workflow examples in `examples/`
