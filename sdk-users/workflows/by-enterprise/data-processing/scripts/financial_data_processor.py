#!/usr/bin/env python3
"""
Financial Data Processor - Enterprise Workflow
==============================================

Real-time financial transaction processing with fraud detection,
compliance checks, and automated reporting.

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
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import KafkaConsumerNode, SQLDatabaseNode
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.runtime.local import LocalRuntime


def create_financial_processor_workflow() -> Workflow:
    """Create enterprise financial data processing workflow."""
    workflow = Workflow(
        workflow_id="financial_processor_001",
        name="enterprise_financial_processor",
        description="Real-time financial transaction processing with compliance",
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
    """Add multiple transaction data sources."""

    # Real-time transaction stream
    stream_consumer = KafkaConsumerNode(
        id="transaction_stream",
        bootstrap_servers="${KAFKA_BROKERS}",
        topic="financial_transactions",
        group_id="processor_group",
        batch_size=1000,
    )
    workflow.add_node("transaction_stream", stream_consumer)

    # Batch transaction database
    batch_reader = SQLDatabaseNode(
        id="batch_transactions",
        connection_string="${TRANSACTION_DB}",
        query="""
        SELECT
            transaction_id,
            account_id,
            amount,
            currency,
            transaction_type,
            merchant_id,
            timestamp,
            location,
            device_info
        FROM transactions
        WHERE processed = false
        AND timestamp >= NOW() - INTERVAL '1 hour'
        LIMIT 5000
        """,
        operation_type="read",
    )
    workflow.add_node("batch_transactions", batch_reader)

    # API webhook receiver (simulated)
    webhook_receiver = PythonCodeNode(
        name="webhook_receiver",
        code="""
# Simulate webhook transaction data
import json
from datetime import datetime
import random

# Generate sample webhook transactions
webhook_transactions = []
for i in range(100):
    transaction = {
        'transaction_id': f'WH-{datetime.now().timestamp()}-{i}',
        'account_id': f'ACC-{random.randint(1000, 9999)}',
        'amount': round(random.uniform(10, 10000), 2),
        'currency': random.choice(['USD', 'EUR', 'GBP']),
        'transaction_type': random.choice(['purchase', 'withdrawal', 'transfer', 'payment']),
        'merchant_id': f'MERCH-{random.randint(100, 999)}' if random.random() > 0.3 else None,
        'timestamp': datetime.now().isoformat(),
        'location': {
            'country': random.choice(['US', 'UK', 'FR', 'DE', 'JP']),
            'city': 'Sample City'
        },
        'device_info': {
            'type': random.choice(['mobile', 'web', 'atm', 'pos']),
            'ip': f'{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}'
        },
        'risk_factors': {
            'is_first_transaction': random.random() < 0.1,
            'unusual_amount': random.random() < 0.05,
            'new_merchant': random.random() < 0.15
        }
    }
    webhook_transactions.append(transaction)

result = {
    'transactions': webhook_transactions,
    'source': 'webhook',
    'batch_id': f'WEBHOOK-{int(datetime.now().timestamp())}'
}
""",
    )
    workflow.add_node("webhook_receiver", webhook_receiver)

    # Merge all transaction sources
    transaction_merger = MergeNode(
        id="transaction_merger", merge_strategy="concatenate"
    )
    workflow.add_node("transaction_merger", transaction_merger)

    # Connect sources to merger
    workflow.connect(
        "transaction_stream", "transaction_merger", mapping={"messages": "stream_data"}
    )
    workflow.connect(
        "batch_transactions", "transaction_merger", mapping={"data": "batch_data"}
    )
    workflow.connect(
        "webhook_receiver",
        "transaction_merger",
        mapping={"transactions": "webhook_data"},
    )


def add_validation_pipeline(workflow: Workflow):
    """Add transaction validation and enrichment."""

    # Transaction validator
    validator = PythonCodeNode(
        name="transaction_validator",
        code=r"""
from datetime import datetime
import re

# Validate and enrich transactions
all_transactions = merged_data.get('stream_data', []) + \
                  merged_data.get('batch_data', []) + \
                  merged_data.get('webhook_data', [])

validated_transactions = []
validation_errors = []

for transaction in all_transactions:
    # Validation checks
    errors = []

    # Required fields
    required_fields = ['transaction_id', 'account_id', 'amount', 'currency', 'timestamp']
    for field in required_fields:
        if not transaction.get(field):
            errors.append(f'Missing required field: {field}')

    # Amount validation
    amount = transaction.get('amount', 0)
    if amount <= 0:
        errors.append(f'Invalid amount: {amount}')
    elif amount > 1000000:  # $1M limit
        errors.append(f'Amount exceeds maximum limit: {amount}')

    # Currency validation
    valid_currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD']
    currency = transaction.get('currency', '')
    if currency not in valid_currencies:
        errors.append(f'Invalid currency: {currency}')

    # Account format validation
    account_id = transaction.get('account_id', '')
    if not re.match(r'^ACC-\d{4,}$', account_id):
        errors.append(f'Invalid account ID format: {account_id}')

    # Enrich transaction
    enriched_transaction = transaction.copy()

    # Add validation status
    enriched_transaction['validation_status'] = 'valid' if not errors else 'invalid'
    enriched_transaction['validation_errors'] = errors
    enriched_transaction['validated_at'] = datetime.now().isoformat()

    # Add risk score (initial)
    risk_score = 0
    if amount > 10000:
        risk_score += 20
    if transaction.get('risk_factors', {}).get('is_first_transaction'):
        risk_score += 30
    if transaction.get('risk_factors', {}).get('unusual_amount'):
        risk_score += 25
    if transaction.get('risk_factors', {}).get('new_merchant'):
        risk_score += 15

    enriched_transaction['risk_score'] = min(risk_score, 100)
    enriched_transaction['risk_level'] = 'high' if risk_score > 70 else 'medium' if risk_score > 40 else 'low'

    # Add processing metadata
    enriched_transaction['processing_stage'] = 'validated'
    enriched_transaction['processor_version'] = '2.1.0'

    if not errors:
        validated_transactions.append(enriched_transaction)
    else:
        validation_errors.append(enriched_transaction)

result = {
    'valid_transactions': validated_transactions,
    'invalid_transactions': validation_errors,
    'validation_summary': {
        'total_processed': len(all_transactions),
        'valid_count': len(validated_transactions),
        'invalid_count': len(validation_errors),
        'validation_rate': len(validated_transactions) / len(all_transactions) if all_transactions else 0
    }
}
""",
    )
    workflow.add_node("transaction_validator", validator)
    workflow.connect(
        "transaction_merger", "transaction_validator", mapping={"merged": "merged_data"}
    )

    # Route based on validation
    validation_router = SwitchNode(
        id="validation_router",
        condition="validation_rate >= 0.95",  # 95% validation threshold
    )
    workflow.add_node("validation_router", validation_router)
    workflow.connect(
        "transaction_validator",
        "validation_router",
        mapping={"result": "validation_result"},
    )


def add_fraud_detection(workflow: Workflow):
    """Add ML-based fraud detection system."""

    # Fraud detection model
    fraud_detector = PythonCodeNode(
        name="fraud_detector",
        code='''
import numpy as np
from datetime import datetime, timedelta

# ML-based fraud detection (simplified)
valid_transactions = validation_data.get('valid_transactions', [])
fraud_alerts = []
suspicious_transactions = []
clean_transactions = []

# Load account history (simulated)
def get_account_history(account_id):
    """Simulate account history retrieval."""
    return {
        'avg_transaction_amount': 250.0,
        'typical_merchants': ['MERCH-101', 'MERCH-202', 'MERCH-303'],
        'usual_countries': ['US', 'UK'],
        'daily_limit': 5000,
        'transaction_frequency': 10  # per day
    }

# Fraud detection rules and ML scoring
for transaction in valid_transactions:
    fraud_indicators = []
    fraud_score = transaction.get('risk_score', 0)

    account_id = transaction['account_id']
    amount = transaction['amount']

    # Get account profile
    account_history = get_account_history(account_id)

    # Rule 1: Unusual amount
    avg_amount = account_history['avg_transaction_amount']
    if amount > avg_amount * 10:
        fraud_indicators.append('unusual_high_amount')
        fraud_score += 30

    # Rule 2: New merchant
    merchant_id = transaction.get('merchant_id')
    if merchant_id and merchant_id not in account_history['typical_merchants']:
        fraud_indicators.append('new_merchant')
        fraud_score += 15

    # Rule 3: Unusual location
    location = transaction.get('location', {})
    country = location.get('country', 'US')
    if country not in account_history['usual_countries']:
        fraud_indicators.append('unusual_location')
        fraud_score += 25

    # Rule 4: Velocity check
    recent_amount_today = np.random.uniform(0, 3000)  # Simulated
    if recent_amount_today + amount > account_history['daily_limit']:
        fraud_indicators.append('daily_limit_exceeded')
        fraud_score += 40

    # Rule 5: Device anomaly
    device_type = transaction.get('device_info', {}).get('type', 'web')
    if device_type == 'atm' and country not in ['US', 'CA']:
        fraud_indicators.append('foreign_atm_usage')
        fraud_score += 20

    # ML model scoring (simulated with rules)
    ml_score = min(100, fraud_score * 1.2)  # Simulated ML boost

    # Classify transaction
    transaction['fraud_score'] = ml_score
    transaction['fraud_indicators'] = fraud_indicators
    transaction['fraud_detection_timestamp'] = datetime.now().isoformat()

    if ml_score >= 80:
        transaction['fraud_status'] = 'high_risk'
        transaction['action_required'] = 'block_and_review'
        fraud_alerts.append({
            'transaction_id': transaction['transaction_id'],
            'account_id': account_id,
            'amount': amount,
            'fraud_score': ml_score,
            'indicators': fraud_indicators,
            'alert_level': 'critical',
            'recommended_action': 'immediate_block'
        })
        suspicious_transactions.append(transaction)
    elif ml_score >= 50:
        transaction['fraud_status'] = 'medium_risk'
        transaction['action_required'] = 'additional_verification'
        suspicious_transactions.append(transaction)
    else:
        transaction['fraud_status'] = 'low_risk'
        transaction['action_required'] = 'none'
        clean_transactions.append(transaction)

result = {
    'clean_transactions': clean_transactions,
    'suspicious_transactions': suspicious_transactions,
    'fraud_alerts': fraud_alerts,
    'fraud_summary': {
        'total_analyzed': len(valid_transactions),
        'high_risk_count': len(fraud_alerts),
        'medium_risk_count': len(suspicious_transactions) - len(fraud_alerts),
        'low_risk_count': len(clean_transactions),
        'fraud_rate': len(fraud_alerts) / len(valid_transactions) if valid_transactions else 0
    }
}
''',
    )
    workflow.add_node("fraud_detector", fraud_detector)

    # Connect valid transactions to fraud detection
    workflow.connect(
        "validation_router",
        "fraud_detector",
        output_key="true_output",
        mapping={"validation_result": "validation_data"},
    )


def add_compliance_pipeline(workflow: Workflow):
    """Add regulatory compliance checks."""

    compliance_checker = PythonCodeNode(
        name="compliance_checker",
        code='''
from datetime import datetime
import re

# Compliance checks for various regulations
fraud_detection_result = fraud_data
all_transactions = (fraud_detection_result.get('clean_transactions', []) +
                   fraud_detection_result.get('suspicious_transactions', []))

compliant_transactions = []
compliance_violations = []
compliance_reports = []

# Define compliance rules
def check_aml_compliance(transaction):
    """Anti-Money Laundering checks."""
    violations = []
    amount = transaction['amount']
    currency = transaction['currency']

    # CTR (Currency Transaction Report) threshold
    usd_equivalent = convert_to_usd(amount, currency)
    if usd_equivalent >= 10000:
        violations.append({
            'rule': 'CTR_THRESHOLD',
            'description': 'Transaction exceeds $10,000 USD',
            'report_required': 'CTR',
            'severity': 'mandatory_report'
        })

    # Suspicious activity patterns
    if transaction.get('fraud_score', 0) > 60:
        violations.append({
            'rule': 'SUSPICIOUS_ACTIVITY',
            'description': 'High fraud score indicates suspicious activity',
            'report_required': 'SAR',
            'severity': 'investigation_required'
        })

    return violations

def check_pci_compliance(transaction):
    """Payment Card Industry compliance."""
    violations = []

    # Check for exposed card data (should never happen)
    transaction_str = str(transaction)
    if re.search(r'\b\\d{16}\b', transaction_str):
        violations.append({
            'rule': 'PCI_CARD_EXPOSURE',
            'description': 'Potential card number exposed',
            'severity': 'critical',
            'action': 'immediate_remediation'
        })

    return violations

def check_gdpr_compliance(transaction):
    """GDPR compliance for EU transactions."""
    violations = []
    location = transaction.get('location', {})

    eu_countries = ['FR', 'DE', 'IT', 'ES', 'NL', 'BE', 'PL']
    if location.get('country') in eu_countries:
        # Check data minimization
        if 'unnecessary_field' in transaction:
            violations.append({
                'rule': 'GDPR_DATA_MINIMIZATION',
                'description': 'Unnecessary personal data collected',
                'severity': 'medium',
                'action': 'remove_excess_data'
            })

    return violations

def convert_to_usd(amount, currency):
    """Convert to USD (simplified)."""
    rates = {'USD': 1.0, 'EUR': 1.1, 'GBP': 1.25, 'JPY': 0.009}
    return amount * rates.get(currency, 1.0)

# Check each transaction
for transaction in all_transactions:
    compliance_issues = []

    # Run compliance checks
    aml_violations = check_aml_compliance(transaction)
    pci_violations = check_pci_compliance(transaction)
    gdpr_violations = check_gdpr_compliance(transaction)

    compliance_issues.extend(aml_violations)
    compliance_issues.extend(pci_violations)
    compliance_issues.extend(gdpr_violations)

    # Add compliance status
    transaction['compliance_checked'] = True
    transaction['compliance_timestamp'] = datetime.now().isoformat()
    transaction['compliance_violations'] = compliance_issues
    transaction['compliance_status'] = 'compliant' if not compliance_issues else 'non_compliant'

    if compliance_issues:
        compliance_violations.append(transaction)

        # Generate compliance reports
        for violation in compliance_issues:
            if violation.get('report_required'):
                compliance_reports.append({
                    'report_type': violation['report_required'],
                    'transaction_id': transaction['transaction_id'],
                    'account_id': transaction['account_id'],
                    'amount': transaction['amount'],
                    'currency': transaction['currency'],
                    'violation_details': violation,
                    'generated_at': datetime.now().isoformat()
                })
    else:
        compliant_transactions.append(transaction)

result = {
    'compliant_transactions': compliant_transactions,
    'compliance_violations': compliance_violations,
    'compliance_reports': compliance_reports,
    'compliance_summary': {
        'total_checked': len(all_transactions),
        'compliant_count': len(compliant_transactions),
        'violation_count': len(compliance_violations),
        'reports_generated': len(compliance_reports),
        'compliance_rate': len(compliant_transactions) / len(all_transactions) if all_transactions else 0
    }
}
''',
    )
    workflow.add_node("compliance_checker", compliance_checker)
    workflow.connect(
        "fraud_detector", "compliance_checker", mapping={"result": "fraud_data"}
    )


def add_reporting_system(workflow: Workflow):
    """Add automated reporting and analytics."""

    # Real-time metrics calculator
    metrics_calculator = PythonCodeNode(
        name="metrics_calculator",
        code="""
from datetime import datetime
import numpy as np

# Calculate real-time metrics
compliance_result = compliance_data
transactions = compliance_result.get('compliant_transactions', [])

# Transaction metrics
total_volume = sum(t['amount'] for t in transactions)
transaction_count = len(transactions)
avg_transaction_value = total_volume / transaction_count if transaction_count > 0 else 0

# Risk metrics
risk_distribution = {'high': 0, 'medium': 0, 'low': 0}
for t in transactions:
    risk_level = t.get('risk_level', 'low')
    risk_distribution[risk_level] += 1

# Currency breakdown
currency_volumes = {}
for t in transactions:
    currency = t['currency']
    amount = t['amount']
    currency_volumes[currency] = currency_volumes.get(currency, 0) + amount

# Transaction type analysis
type_distribution = {}
for t in transactions:
    tx_type = t.get('transaction_type', 'unknown')
    type_distribution[tx_type] = type_distribution.get(tx_type, 0) + 1

# Fraud metrics
fraud_alerts = compliance_result.get('fraud_alerts', [])
compliance_reports = compliance_result.get('compliance_reports', [])

# Performance metrics
processing_times = []
for t in transactions:
    if 'validated_at' in t and 'timestamp' in t:
        # Simulated processing time
        processing_times.append(np.random.uniform(50, 200))  # milliseconds

avg_processing_time = np.mean(processing_times) if processing_times else 0
p95_processing_time = np.percentile(processing_times, 95) if processing_times else 0

result = {
    'metrics': {
        'transaction_metrics': {
            'total_volume': total_volume,
            'transaction_count': transaction_count,
            'average_value': avg_transaction_value,
            'currency_breakdown': currency_volumes,
            'type_distribution': type_distribution
        },
        'risk_metrics': {
            'risk_distribution': risk_distribution,
            'fraud_alert_count': len(fraud_alerts),
            'high_risk_percentage': (risk_distribution['high'] / transaction_count * 100) if transaction_count > 0 else 0
        },
        'compliance_metrics': {
            'compliance_rate': compliance_result.get('compliance_summary', {}).get('compliance_rate', 0),
            'reports_generated': len(compliance_reports),
            'violations_found': compliance_result.get('compliance_summary', {}).get('violation_count', 0)
        },
        'performance_metrics': {
            'avg_processing_time_ms': avg_processing_time,
            'p95_processing_time_ms': p95_processing_time,
            'throughput_per_second': transaction_count / 60 if transaction_count > 0 else 0  # Assuming 1 minute batch
        }
    },
    'timestamp': datetime.now().isoformat(),
    'reporting_period': 'real_time'
}
""",
    )
    workflow.add_node("metrics_calculator", metrics_calculator)
    workflow.connect(
        "compliance_checker",
        "metrics_calculator",
        mapping={"result": "compliance_data"},
    )

    # Report generator
    report_generator = PythonCodeNode(
        name="report_generator",
        code="""
from datetime import datetime

# Generate various reports
metrics_data = metrics_result['metrics']

# Executive summary
executive_summary = {
    'report_type': 'executive_summary',
    'generated_at': datetime.now().isoformat(),
    'key_metrics': {
        'total_processed': metrics_data['transaction_metrics']['transaction_count'],
        'total_volume': f"${metrics_data['transaction_metrics']['total_volume']:,.2f}",
        'fraud_rate': f"{metrics_data['risk_metrics']['high_risk_percentage']:.2f}%",
        'compliance_rate': f"{metrics_data['compliance_metrics']['compliance_rate'] * 100:.2f}%",
        'avg_processing_time': f"{metrics_data['performance_metrics']['avg_processing_time_ms']:.0f}ms"
    },
    'alerts': [],
    'recommendations': []
}

# Add alerts if needed
if metrics_data['risk_metrics']['fraud_alert_count'] > 10:
    executive_summary['alerts'].append({
        'type': 'HIGH_FRAUD_ACTIVITY',
        'message': f"{metrics_data['risk_metrics']['fraud_alert_count']} fraud alerts generated",
        'severity': 'high'
    })

if metrics_data['compliance_metrics']['compliance_rate'] < 0.99:
    executive_summary['alerts'].append({
        'type': 'COMPLIANCE_ISSUES',
        'message': f"Compliance rate below threshold: {metrics_data['compliance_metrics']['compliance_rate'] * 100:.2f}%",
        'severity': 'medium'
    })

# Operational report
operational_report = {
    'report_type': 'operational_metrics',
    'generated_at': datetime.now().isoformat(),
    'performance': {
        'throughput': f"{metrics_data['performance_metrics']['throughput_per_second']:.2f} tx/s",
        'latency_avg': f"{metrics_data['performance_metrics']['avg_processing_time_ms']:.2f}ms",
        'latency_p95': f"{metrics_data['performance_metrics']['p95_processing_time_ms']:.2f}ms"
    },
    'volume_breakdown': metrics_data['transaction_metrics']['currency_breakdown'],
    'transaction_types': metrics_data['transaction_metrics']['type_distribution']
}

# Risk report
risk_report = {
    'report_type': 'risk_assessment',
    'generated_at': datetime.now().isoformat(),
    'risk_summary': metrics_data['risk_metrics']['risk_distribution'],
    'fraud_alerts': metrics_data['risk_metrics']['fraud_alert_count'],
    'compliance_violations': metrics_data['compliance_metrics']['violations_found'],
    'action_items': []
}

# Add action items based on risk
if metrics_data['risk_metrics']['high_risk_percentage'] > 5:
    risk_report['action_items'].append({
        'action': 'REVIEW_FRAUD_RULES',
        'reason': 'High percentage of high-risk transactions',
        'priority': 'high'
    })

result = {
    'reports': {
        'executive_summary': executive_summary,
        'operational_report': operational_report,
        'risk_report': risk_report
    },
    'distribution_list': ['cfo@company.com', 'risk-team@company.com', 'ops@company.com'],
    'next_report_due': datetime.now().isoformat()
}
""",
    )
    workflow.add_node("report_generator", report_generator)
    workflow.connect(
        "metrics_calculator", "report_generator", mapping={"result": "metrics_result"}
    )

    # Output writer
    output_writer = SQLDatabaseNode(
        id="output_writer",
        connection_string="${ANALYTICS_DB}",
        operation_type="write",
        table_name="financial_analytics",
        if_exists="append",
    )
    workflow.add_node("output_writer", output_writer)
    workflow.connect("report_generator", "output_writer", mapping={"reports": "data"})


def main():
    """Execute the financial processor workflow."""
    # Create workflow
    workflow = create_financial_processor_workflow()

    # Set up runtime
    runtime = LocalRuntime()

    # Configure parameters
    parameters = {
        "transaction_stream": {
            "bootstrap_servers": os.getenv("KAFKA_BROKERS", "localhost:9092"),
            "consumer_timeout_ms": 1000,
        },
        "batch_transactions": {
            "connection_string": os.getenv(
                "TRANSACTION_DB", "postgresql://user:pass@localhost/transactions"
            )
        },
        "output_writer": {
            "connection_string": os.getenv(
                "ANALYTICS_DB", "postgresql://user:pass@localhost/analytics"
            )
        },
    }

    # Execute workflow
    print("Starting Financial Data Processor...")
    print("=" * 50)

    try:
        result, run_id = runtime.execute(workflow, parameters=parameters)

        # Display results
        if result:
            reports = result.get("reports", {})
            exec_summary = reports.get("executive_summary", {})

            print("\nExecutive Summary:")
            print("-" * 30)
            for metric, value in exec_summary.get("key_metrics", {}).items():
                print(f"{metric}: {value}")

            print("\nAlerts:")
            for alert in exec_summary.get("alerts", []):
                print(f"- [{alert['severity'].upper()}] {alert['message']}")

            print("\nWorkflow completed successfully!")
            print(f"Run ID: {run_id}")

    except Exception as e:
        print(f"Error executing workflow: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
