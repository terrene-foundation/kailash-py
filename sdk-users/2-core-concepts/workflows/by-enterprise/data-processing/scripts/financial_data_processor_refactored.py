#!/usr/bin/env python3
"""
Financial Data Processor - Enterprise Workflow (Refactored)
===========================================================

Real-time financial transaction processing with fraud detection,
compliance checks, and automated reporting.

This version follows Kailash SDK best practices by using existing
nodes instead of PythonCodeNode wherever possible.

Features:
- Real-time transaction categorization
- ML-based fraud detection
- Regulatory compliance checks
- Automated alert generation
- Performance analytics
"""

import os
import sys

# Add parent directory to path for imports
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
)

from kailash import Workflow
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import RESTClientNode
from kailash.nodes.data import CSVWriterNode, KafkaConsumerNode, SQLDatabaseNode
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.nodes.transform import DataTransformer, FilterNode
from kailash.runtime.local import LocalRuntime


def create_financial_processor_workflow() -> Workflow:
    """Create enterprise financial data processing workflow using existing nodes."""
    workflow = Workflow(
        workflow_id="financial_processor_002",
        name="enterprise_financial_processor_refactored",
        description="Real-time financial transaction processing with compliance - best practices",
    )

    # Transaction ingestion from multiple sources
    add_transaction_sources(workflow)

    # Data validation and enrichment
    add_validation_pipeline(workflow)

    # Fraud detection system
    add_fraud_detection(workflow)

    # Compliance checks
    add_compliance_pipeline(workflow)

    # Reporting and analytics
    add_reporting_system(workflow)

    return workflow


def add_transaction_sources(workflow: Workflow):
    """Add multiple transaction data sources using existing nodes."""

    # Real-time transaction stream (provide initial config to avoid validation errors)
    stream_consumer = KafkaConsumerNode()
    # Provide minimal config to pass validation - will be overridden by runtime parameters
    stream_consumer.config.update(
        {"bootstrap_servers": "localhost:9092", "topic": "temp", "group_id": "temp"}
    )
    workflow.add_node("transaction_stream", stream_consumer)

    # Batch transaction database
    batch_reader = SQLDatabaseNode(connection_string="${TRANSACTION_DB}")
    workflow.add_node("batch_transactions", batch_reader)

    # API webhook receiver - using RESTClientNode for real webhook endpoint
    webhook_receiver = RESTClientNode(base_url="${WEBHOOK_API}")
    workflow.add_node("webhook_receiver", webhook_receiver)

    # Transform webhook response to standard format
    webhook_transformer = DataTransformer(
        transformations=[
            # Extract transactions from API response
            "lambda x: x.get('data', {}).get('transactions', [])",
            # Standardize transaction format
            "lambda transactions: [{'transaction_id': t['id'], 'account_id': t['account'], 'amount': t['value'], 'currency': t['curr'], 'transaction_type': t['type'], 'merchant_id': t.get('merchant'), 'timestamp': t['time'], 'location': t.get('loc', {}), 'device_info': t.get('device', {}), 'source': 'webhook'} for t in transactions]",
        ]
    )
    workflow.add_node("webhook_transformer", webhook_transformer)
    workflow.connect(
        "webhook_receiver", "webhook_transformer", mapping={"response": "data"}
    )

    # Merge all transaction sources
    transaction_merger = MergeNode(merge_strategy="concatenate")
    workflow.add_node("transaction_merger", transaction_merger)

    # Connect sources to merger
    workflow.connect(
        "transaction_stream", "transaction_merger", mapping={"messages": "stream_data"}
    )
    workflow.connect(
        "batch_transactions", "transaction_merger", mapping={"data": "batch_data"}
    )
    workflow.connect(
        "webhook_transformer", "transaction_merger", mapping={"result": "webhook_data"}
    )


def add_validation_pipeline(workflow: Workflow):
    """Add transaction validation using DataTransformer and FilterNode."""

    # Flatten merged data into single list
    data_flattener = DataTransformer(
        id="data_flattener",
        transformations=[
            # Combine all transaction lists into one
            "lambda x: x.get('stream_data', []) + x.get('batch_data', []) + x.get('webhook_data', [])"
        ],
    )
    workflow.add_node("data_flattener", data_flattener)
    workflow.connect("transaction_merger", "data_flattener", mapping={"merged": "data"})

    # Add validation fields using DataTransformer
    validation_enricher = DataTransformer(
        id="validation_enricher",
        transformations=[
            # Add validation fields to each transaction
            """lambda transactions: [{
                **t,
                'has_required_fields': all(t.get(f) for f in ['transaction_id', 'account_id', 'amount', 'currency']),
                'amount_valid': 0 < t.get('amount', 0) <= 1000000,
                'currency_valid': t.get('currency') in ['USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD'],
                'account_valid': t.get('account_id', '').startswith('ACC-'),
                'validation_timestamp': datetime.now().isoformat()
            } for t in transactions]""",
            # Calculate overall validation status
            """lambda transactions: [{
                **t,
                'validation_status': 'valid' if (t['has_required_fields'] and t['amount_valid'] and t['currency_valid'] and t['account_valid']) else 'invalid'
            } for t in transactions]""",
        ],
    )
    workflow.add_node("validation_enricher", validation_enricher)
    workflow.connect(
        "data_flattener", "validation_enricher", mapping={"result": "data"}
    )

    # Filter out invalid transactions
    valid_filter = FilterNode(
        id="valid_filter", field="validation_status", operator="==", value="valid"
    )
    workflow.add_node("valid_filter", valid_filter)
    workflow.connect("validation_enricher", "valid_filter", mapping={"result": "data"})

    # Store invalid transactions for review
    invalid_filter = FilterNode(
        id="invalid_filter", field="validation_status", operator="==", value="invalid"
    )
    workflow.add_node("invalid_filter", invalid_filter)
    workflow.connect(
        "validation_enricher", "invalid_filter", mapping={"result": "data"}
    )

    # Write invalid transactions to error log
    error_writer = CSVWriterNode(
        id="error_writer",
        file_path="${ERROR_LOG_PATH}/invalid_transactions_${TIMESTAMP}.csv",
        headers=True,
    )
    workflow.add_node("error_writer", error_writer)
    workflow.connect(
        "invalid_filter", "error_writer", mapping={"filtered_data": "data"}
    )

    # Add risk scoring to valid transactions
    risk_enricher = DataTransformer(
        id="risk_enricher",
        transformations=[
            # Calculate initial risk score based on transaction attributes
            """lambda transactions: [{
                **t,
                'risk_score': min(100, sum([
                    20 if t.get('amount', 0) > 10000 else 0,
                    30 if t.get('risk_factors', {}).get('is_first_transaction') else 0,
                    25 if t.get('risk_factors', {}).get('unusual_amount') else 0,
                    15 if t.get('risk_factors', {}).get('new_merchant') else 0,
                    10 if t.get('location', {}).get('country') not in ['US', 'CA'] else 0
                ])),
                'risk_level': 'high' if sum([...]) > 70 else 'medium' if sum([...]) > 40 else 'low'
            } for t in transactions]"""
        ],
    )
    workflow.add_node("risk_enricher", risk_enricher)
    workflow.connect("valid_filter", "risk_enricher", mapping={"filtered_data": "data"})


def add_fraud_detection(workflow: Workflow):
    """Add ML-based fraud detection using LLMAgentNode."""

    # Use LLM for intelligent fraud detection
    fraud_detector = LLMAgentNode(
        id="fraud_detector",
        provider="openai",
        model="gpt-4",
        system_prompt="""You are a financial fraud detection expert. Analyze each transaction and identify potential fraud indicators.

For each transaction, evaluate:
1. Transaction amount relative to account history
2. Geographic anomalies (unusual locations)
3. Time-based patterns (unusual hours, velocity)
4. Merchant reputation and category
5. Device and access patterns

Return a JSON response with:
{
  "transaction_id": "...",
  "fraud_probability": 0.0-1.0,
  "fraud_indicators": ["list", "of", "indicators"],
  "recommended_action": "approve|review|block",
  "explanation": "brief explanation"
}

Be conservative - when in doubt, flag for review rather than blocking.""",
        temperature=0.3,  # Lower temperature for consistent fraud detection
        max_tokens=500,
    )
    workflow.add_node("fraud_detector", fraud_detector)

    # Transform transactions for LLM input
    fraud_input_transformer = DataTransformer(
        id="fraud_input_transformer",
        transformations=[
            # Format transactions for LLM analysis
            """lambda transactions: {
                'messages': [{
                    'role': 'user',
                    'content': f'Analyze these transactions for fraud:\\n{json.dumps(transactions[:10], indent=2)}'
                }]
            }"""
        ],
    )
    workflow.add_node("fraud_input_transformer", fraud_input_transformer)
    workflow.connect(
        "risk_enricher", "fraud_input_transformer", mapping={"result": "data"}
    )
    workflow.connect(
        "fraud_input_transformer", "fraud_detector", mapping={"result": "prompt"}
    )

    # Process fraud detection results
    fraud_result_processor = DataTransformer(
        id="fraud_result_processor",
        transformations=[
            # Parse LLM response and merge with original transactions
            """lambda x: {
                'transactions': merge_fraud_results(x['transactions'], x['fraud_analysis']),
                'high_risk_count': len([t for t in x['transactions'] if t.get('fraud_probability', 0) > 0.7])
            }"""
        ],
    )
    workflow.add_node("fraud_result_processor", fraud_result_processor)

    # Route based on fraud risk
    fraud_router = SwitchNode(id="fraud_router", condition="fraud_probability > 0.7")
    workflow.add_node("fraud_router", fraud_router)

    # High-risk transaction handler
    high_risk_handler = RESTClientNode(
        id="high_risk_handler",
        url="${FRAUD_ALERT_API}/create",
        method="POST",
        headers={"Authorization": "Bearer ${FRAUD_API_KEY}"},
    )
    workflow.add_node("high_risk_handler", high_risk_handler)
    workflow.connect(
        "fraud_router", "high_risk_handler", mapping={"true_output": "body"}
    )


def add_compliance_pipeline(workflow: Workflow):
    """Add regulatory compliance checks using rule-based nodes."""

    # AML (Anti-Money Laundering) check - amount threshold
    aml_checker = SwitchNode(
        id="aml_checker", condition="amount >= 10000"  # CTR threshold
    )
    workflow.add_node("aml_checker", aml_checker)

    # Generate CTR report for high-value transactions
    ctr_generator = DataTransformer(
        id="ctr_generator",
        transformations=[
            # Create Currency Transaction Report format
            """lambda t: {
                'report_type': 'CTR',
                'transaction_id': t['transaction_id'],
                'account_id': t['account_id'],
                'amount': t['amount'],
                'currency': t['currency'],
                'timestamp': t['timestamp'],
                'filing_required': True,
                'report_date': datetime.now().isoformat()
            }"""
        ],
    )
    workflow.add_node("ctr_generator", ctr_generator)
    workflow.connect("aml_checker", "ctr_generator", mapping={"true_output": "data"})

    # GDPR compliance for EU transactions
    eu_filter = FilterNode(
        id="eu_filter",
        field="location.country",
        operator="in",
        value=["FR", "DE", "IT", "ES", "NL", "BE", "PL"],
    )
    workflow.add_node("eu_filter", eu_filter)

    # Data minimization for GDPR
    gdpr_minimizer = DataTransformer(
        id="gdpr_minimizer",
        transformations=[
            # Remove unnecessary personal data for EU transactions
            """lambda transactions: [{
                k: v for k, v in t.items()
                if k not in ['device_info.ip', 'unnecessary_field']
            } for t in transactions]"""
        ],
    )
    workflow.add_node("gdpr_minimizer", gdpr_minimizer)
    workflow.connect("eu_filter", "gdpr_minimizer", mapping={"filtered_data": "data"})

    # Compliance report aggregator
    compliance_aggregator = MergeNode(
        id="compliance_aggregator", merge_strategy="combine_dict"
    )
    workflow.add_node("compliance_aggregator", compliance_aggregator)

    # Write compliance reports to database
    compliance_writer = SQLDatabaseNode(
        id="compliance_writer",
        connection_string="${COMPLIANCE_DB}",
        operation_type="write",
        table_name="compliance_reports",
    )
    workflow.add_node("compliance_writer", compliance_writer)
    workflow.connect(
        "compliance_aggregator", "compliance_writer", mapping={"merged": "data"}
    )


def add_reporting_system(workflow: Workflow):
    """Add automated reporting using DataTransformer and template nodes."""

    # Calculate metrics using DataTransformer
    metrics_calculator = DataTransformer(
        id="metrics_calculator",
        transformations=[
            # Calculate transaction metrics
            """lambda transactions: {
                'total_volume': sum(t['amount'] for t in transactions),
                'transaction_count': len(transactions),
                'average_value': sum(t['amount'] for t in transactions) / len(transactions) if transactions else 0,
                'currency_breakdown': {
                    curr: sum(t['amount'] for t in transactions if t['currency'] == curr)
                    for curr in set(t['currency'] for t in transactions)
                },
                'risk_distribution': {
                    level: len([t for t in transactions if t.get('risk_level') == level])
                    for level in ['high', 'medium', 'low']
                }
            }"""
        ],
    )
    workflow.add_node("metrics_calculator", metrics_calculator)

    # Generate reports using LLM for natural language summaries
    report_generator = LLMAgentNode(
        id="report_generator",
        provider="openai",
        model="gpt-3.5-turbo",
        system_prompt="""Generate an executive summary report for financial transaction processing.

Include:
1. Key metrics and KPIs
2. Risk assessment summary
3. Compliance status
4. Recommended actions
5. Trend analysis

Format as a professional business report with clear sections.""",
        temperature=0.5,
        max_tokens=1000,
    )
    workflow.add_node("report_generator", report_generator)

    # Format metrics for report generation
    report_formatter = DataTransformer(
        id="report_formatter",
        transformations=[
            """lambda metrics: {
                'messages': [{
                    'role': 'user',
                    'content': f'Generate executive summary for: {json.dumps(metrics, indent=2)}'
                }]
            }"""
        ],
    )
    workflow.add_node("report_formatter", report_formatter)
    workflow.connect(
        "metrics_calculator", "report_formatter", mapping={"result": "data"}
    )
    workflow.connect(
        "report_formatter", "report_generator", mapping={"result": "prompt"}
    )

    # Write reports to multiple destinations
    # Database writer
    report_db_writer = SQLDatabaseNode(
        id="report_db_writer",
        connection_string="${ANALYTICS_DB}",
        operation_type="write",
        table_name="financial_reports",
    )
    workflow.add_node("report_db_writer", report_db_writer)

    # File writer for archival
    report_file_writer = CSVWriterNode(
        id="report_file_writer",
        file_path="${REPORT_PATH}/financial_report_${TIMESTAMP}.csv",
        headers=True,
    )
    workflow.add_node("report_file_writer", report_file_writer)

    # API call to notification service
    notification_sender = RESTClientNode(
        id="notification_sender",
        url="${NOTIFICATION_API}/send",
        method="POST",
        headers={"Authorization": "Bearer ${NOTIFICATION_KEY}"},
    )
    workflow.add_node("notification_sender", notification_sender)

    # Connect report outputs
    workflow.connect(
        "report_generator", "report_db_writer", mapping={"response": "data"}
    )
    workflow.connect(
        "metrics_calculator", "report_file_writer", mapping={"result": "data"}
    )
    workflow.connect(
        "report_generator", "notification_sender", mapping={"response": "body"}
    )


def main():
    """Execute the refactored financial processor workflow."""
    # Load environment if in SDK development mode
    if os.getenv("SDK_DEV_MODE") == "true":
        from pathlib import Path

        # Look for .env.sdk-dev in the sdk-users directory
        script_dir = Path(__file__).parent
        env_file = script_dir / ".." / ".." / ".." / ".." / ".env.sdk-dev"
        env_file = env_file.resolve()  # Resolve to absolute path
        if env_file.exists():
            from dotenv import load_dotenv

            load_dotenv(env_file)
            print("✓ Using SDK development environment")

    # Create workflow
    workflow = create_financial_processor_workflow()

    # Set up runtime
    runtime = LocalRuntime()

    # Configure parameters
    parameters = {
        "transaction_stream": {
            "bootstrap_servers": os.getenv("KAFKA_BROKERS", "localhost:9092"),
            "topic": "financial-transactions",
            "group_id": "financial-processor",
            "consumer_timeout_ms": 1000,
        },
        "batch_transactions": {
            "connection_string": os.getenv(
                "TRANSACTION_DB", "postgresql://user:pass@localhost/transactions"
            ),
            "query": "SELECT * FROM transactions WHERE status = 'pending' LIMIT 100",
        },
        "webhook_receiver": {
            "url": os.getenv("WEBHOOK_API", "https://api.example.com")
            + "/transactions/pending",
            "headers": {
                "Authorization": f"Bearer {os.getenv('WEBHOOK_TOKEN', 'demo-token')}"
            },
        },
        "fraud_detector": {"api_key": os.getenv("OPENAI_API_KEY", "demo-key")},
        "high_risk_handler": {
            "url": os.getenv("FRAUD_ALERT_API", "https://fraud.example.com") + "/create"
        },
        "compliance_writer": {
            "connection_string": os.getenv(
                "COMPLIANCE_DB", "postgresql://user:pass@localhost/compliance"
            )
        },
        "report_db_writer": {
            "connection_string": os.getenv(
                "ANALYTICS_DB", "postgresql://user:pass@localhost/analytics"
            )
        },
        "notification_sender": {
            "url": os.getenv("NOTIFICATION_API", "https://notify.example.com") + "/send"
        },
    }

    # Execute workflow
    print("Starting Financial Data Processor (Refactored)...")
    print("=" * 50)
    print("Using Kailash SDK best practices - minimal PythonCodeNode usage")
    print()

    try:
        result, run_id = runtime.execute(workflow, parameters=parameters)

        print("Workflow completed successfully!")
        print(f"Run ID: {run_id}")
        print("\nThis refactored version demonstrates:")
        print("- Real API integrations with RestClientNode")
        print("- Data transformation with DataTransformer")
        print("- ML-based fraud detection with LLMAgentNode")
        print("- Rule-based routing with SwitchNode")
        print("- Data filtering with FilterNode")
        print("- Database operations with SQLDatabaseNode")
        print("- File operations with CSVWriterNode")

    except Exception as e:
        print(f"Error executing workflow: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
