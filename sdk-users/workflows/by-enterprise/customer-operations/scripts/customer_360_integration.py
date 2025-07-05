#!/usr/bin/env python3
"""
Customer 360° Data Integration Workflow
======================================

Enterprise-grade workflow that creates a unified customer view by integrating data from:
- CRM systems (Salesforce, HubSpot)
- Transaction databases
- Support ticket systems
- Marketing platforms
- Website analytics

This workflow demonstrates real enterprise patterns for:
1. Multi-source data integration
2. Data quality and validation
3. Master data management
4. Real-time customer scoring
5. Automated segmentation
"""

import os

from kailash import Workflow
from kailash.nodes.data import (
    CSVReaderNode,
    CSVWriterNode,
    JSONReaderNode,
    JSONWriterNode,
)
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.nodes.transform import DataTransformer
from kailash.runtime.local import LocalRuntime


def create_customer_360_workflow() -> Workflow:
    """Create a comprehensive Customer 360° integration workflow."""
    workflow = Workflow(
        workflow_id="customer_360_001",
        name="customer_360_integration",
        description="Enterprise Customer 360° data integration workflow",
    )

    # === DATA SOURCES ===

    # CRM data (Salesforce/HubSpot export)
    crm_data = CSVReaderNode(id="crm_data", file_path="data/crm_customers.csv")
    workflow.add_node("crm_data", crm_data)

    # Transaction data from e-commerce/billing system
    transaction_data = CSVReaderNode(
        id="transaction_data", file_path="data/transactions.csv"
    )
    workflow.add_node("transaction_data", transaction_data)

    # Support ticket data
    support_data = CSVReaderNode(
        id="support_data", file_path="data/support_tickets.csv"
    )
    workflow.add_node("support_data", support_data)

    # Marketing engagement data
    marketing_data = JSONReaderNode(
        id="marketing_data", file_path="data/marketing_engagement.json"
    )
    workflow.add_node("marketing_data", marketing_data)

    # === DATA QUALITY & VALIDATION ===

    # Validate CRM data quality
    crm_validator = DataTransformer(
        id="crm_validator", transformations=[]  # Will be provided at runtime
    )
    workflow.add_node("crm_validator", crm_validator)
    workflow.connect("crm_data", "crm_validator", mapping={"data": "data"})

    # Clean and validate transaction data
    transaction_cleaner = DataTransformer(
        id="transaction_cleaner", transformations=[]  # Will be provided at runtime
    )
    workflow.add_node("transaction_cleaner", transaction_cleaner)
    workflow.connect(
        "transaction_data", "transaction_cleaner", mapping={"data": "data"}
    )

    # Process support ticket data
    support_processor = DataTransformer(
        id="support_processor", transformations=[]  # Will be provided at runtime
    )
    workflow.add_node("support_processor", support_processor)
    workflow.connect("support_data", "support_processor", mapping={"data": "data"})

    # === CUSTOMER SCORING & SEGMENTATION ===

    # Calculate customer lifetime value and health scores
    customer_scoring = DataTransformer(
        id="customer_scoring", transformations=[]  # Will be provided at runtime
    )
    workflow.add_node("customer_scoring", customer_scoring)

    # === DATA INTEGRATION ===

    # Merge CRM and transaction data
    crm_transaction_merge = MergeNode(id="crm_transaction_merge")
    workflow.add_node("crm_transaction_merge", crm_transaction_merge)
    workflow.connect(
        "crm_validator", "crm_transaction_merge", mapping={"result": "data1"}
    )
    workflow.connect(
        "transaction_cleaner", "crm_transaction_merge", mapping={"result": "data2"}
    )

    # Merge with support data
    customer_support_merge = MergeNode(id="customer_support_merge")
    workflow.add_node("customer_support_merge", customer_support_merge)
    workflow.connect(
        "crm_transaction_merge",
        "customer_support_merge",
        mapping={"merged_data": "data1"},
    )
    workflow.connect(
        "support_processor", "customer_support_merge", mapping={"result": "data2"}
    )

    # Final merge with marketing data
    final_customer_merge = MergeNode(id="final_customer_merge")
    workflow.add_node("final_customer_merge", final_customer_merge)
    workflow.connect(
        "customer_support_merge",
        "final_customer_merge",
        mapping={"merged_data": "data1"},
    )
    workflow.connect(
        "marketing_data", "final_customer_merge", mapping={"data": "data2"}
    )

    # Connect to scoring
    workflow.connect(
        "final_customer_merge", "customer_scoring", mapping={"merged_data": "data"}
    )

    # === SEGMENTATION & ROUTING ===

    # Route customers based on value and risk
    customer_router = SwitchNode(
        id="customer_router",
        condition_field="customer_segment",
        cases=["VIP", "Premium"],
    )
    workflow.add_node("customer_router", customer_router)
    workflow.connect(
        "customer_scoring", "customer_router", mapping={"result": "input_data"}
    )

    # High-value customer processing
    high_value_processor = DataTransformer(
        id="high_value_processor", transformations=[]  # Will be provided at runtime
    )
    workflow.add_node("high_value_processor", high_value_processor)
    workflow.connect(
        "customer_router", "high_value_processor", mapping={"case_VIP": "data"}
    )

    # Standard customer processing
    standard_processor = DataTransformer(
        id="standard_processor", transformations=[]  # Will be provided at runtime
    )
    workflow.add_node("standard_processor", standard_processor)
    workflow.connect(
        "customer_router", "standard_processor", mapping={"default": "data"}
    )

    # === OUTPUT GENERATION ===

    # High-value customer export
    high_value_output = JSONWriterNode(
        id="high_value_output", file_path="data/outputs/high_value_customers.json"
    )
    workflow.add_node("high_value_output", high_value_output)
    workflow.connect(
        "high_value_processor", "high_value_output", mapping={"result": "data"}
    )

    # Standard customer export
    standard_output = CSVWriterNode(
        id="standard_output", file_path="data/outputs/standard_customers.csv"
    )
    workflow.add_node("standard_output", standard_output)
    workflow.connect(
        "standard_processor", "standard_output", mapping={"result": "data"}
    )

    # Complete customer 360 export
    customer_360_output = JSONWriterNode(
        id="customer_360_output", file_path="data/outputs/customer_360_complete.json"
    )
    workflow.add_node("customer_360_output", customer_360_output)
    workflow.connect(
        "customer_scoring", "customer_360_output", mapping={"result": "data"}
    )

    return workflow


def run_customer_360_integration():
    """Execute the Customer 360° integration workflow."""
    workflow = create_customer_360_workflow()
    runtime = LocalRuntime()

    # Enterprise-grade transformation parameters
    parameters = {
        "crm_validator": {
            "transformations": [
                r"""
# CRM data validation and standardization
import re
from datetime import datetime

validated_customers = []
validation_issues = []

for i, customer in enumerate(data):
    # Create validated customer record
    validated = dict(customer)
    issues = []

    # Email validation
    email = customer.get('email', '').strip().lower()
    if email and re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        validated['email'] = email
        validated['email_valid'] = True
    else:
        validated['email_valid'] = False
        issues.append(f"Invalid email: {email}")

    # Phone standardization
    phone = customer.get('phone', '').strip()
    if phone:
        phone_clean = re.sub(r'[^\d]', '', phone)
        if len(phone_clean) >= 10:
            validated['phone'] = phone_clean
            validated['phone_valid'] = True
        else:
            validated['phone_valid'] = False
            issues.append(f"Invalid phone: {phone}")
    else:
        validated['phone_valid'] = False

    # Company validation
    company = customer.get('company', '').strip()
    validated['company'] = company
    validated['has_company'] = bool(company)

    # Date standardization
    created_date = customer.get('created_date', '')
    if created_date:
        try:
            parsed_date = datetime.strptime(created_date, '%Y-%m-%d')
            validated['created_date'] = parsed_date.isoformat()
            validated['date_valid'] = True
        except ValueError:
            validated['date_valid'] = False
            issues.append(f"Invalid date: {created_date}")
    else:
        validated['date_valid'] = False

    # Quality score
    quality_score = 0
    if validated.get('email_valid'): quality_score += 25
    if validated.get('phone_valid'): quality_score += 25
    if validated.get('has_company'): quality_score += 25
    if validated.get('date_valid'): quality_score += 25

    validated['data_quality_score'] = quality_score
    validated['validation_issues'] = issues
    validated['record_id'] = i

    validated_customers.append(validated)

    if issues:
        validation_issues.extend([f"Record {i}: {issue}" for issue in issues])

result = {
    "validated_customers": validated_customers,
    "validation_summary": {
        "total_records": len(data),
        "high_quality": len([c for c in validated_customers if c['data_quality_score'] >= 75]),
        "medium_quality": len([c for c in validated_customers if 50 <= c['data_quality_score'] < 75]),
        "low_quality": len([c for c in validated_customers if c['data_quality_score'] < 50]),
        "validation_issues": validation_issues
    }
}
"""
            ]
        },
        "transaction_cleaner": {
            "transformations": [
                """
# Transaction data cleaning and aggregation
from datetime import datetime
from collections import defaultdict

customer_transactions = defaultdict(list)
transaction_summary = defaultdict(lambda: {
    'total_amount': 0.0,
    'transaction_count': 0,
    'first_purchase': None,
    'last_purchase': None,
    'avg_order_value': 0.0,
    'purchase_frequency': 0.0
})

for transaction in data:
    customer_id = transaction.get('customer_id')
    if not customer_id:
        continue

    # Clean transaction data
    amount = float(transaction.get('amount', 0))
    date_str = transaction.get('date', '')

    if date_str:
        try:
            transaction_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            continue  # Skip invalid dates
    else:
        continue

    # Add to customer's transaction list
    customer_transactions[customer_id].append({
        'amount': amount,
        'date': transaction_date,
        'product': transaction.get('product', ''),
        'category': transaction.get('category', ''),
        'status': transaction.get('status', 'completed')
    })

    # Update summary
    summary = transaction_summary[customer_id]
    summary['total_amount'] += amount
    summary['transaction_count'] += 1

    if summary['first_purchase'] is None or transaction_date < summary['first_purchase']:
        summary['first_purchase'] = transaction_date

    if summary['last_purchase'] is None or transaction_date > summary['last_purchase']:
        summary['last_purchase'] = transaction_date

# Calculate derived metrics
for customer_id, summary in transaction_summary.items():
    if summary['transaction_count'] > 0:
        summary['avg_order_value'] = summary['total_amount'] / summary['transaction_count']

    if summary['first_purchase'] and summary['last_purchase']:
        days_diff = (summary['last_purchase'] - summary['first_purchase']).days
        if days_diff > 0:
            summary['purchase_frequency'] = summary['transaction_count'] / (days_diff / 30.0)  # per month

# Convert to list format
result = []
for customer_id, summary in transaction_summary.items():
    result.append({
        'customer_id': customer_id,
        'total_spent': summary['total_amount'],
        'transaction_count': summary['transaction_count'],
        'avg_order_value': round(summary['avg_order_value'], 2),
        'purchase_frequency_monthly': round(summary['purchase_frequency'], 2),
        'first_purchase': summary['first_purchase'].isoformat() if summary['first_purchase'] else None,
        'last_purchase': summary['last_purchase'].isoformat() if summary['last_purchase'] else None,
        'customer_lifetime_days': (summary['last_purchase'] - summary['first_purchase']).days if summary['first_purchase'] and summary['last_purchase'] else 0
    })
"""
            ]
        },
        "support_processor": {
            "transformations": [
                """
# Support ticket analysis and customer satisfaction scoring
from collections import defaultdict
from datetime import datetime

customer_support = defaultdict(lambda: {
    'total_tickets': 0,
    'resolved_tickets': 0,
    'avg_resolution_time': 0.0,
    'satisfaction_scores': [],
    'escalated_tickets': 0,
    'recent_tickets': 0
})

current_date = datetime.now()

for ticket in data:
    customer_id = ticket.get('customer_id')
    if not customer_id:
        continue

    status = ticket.get('status', '').lower()
    priority = ticket.get('priority', '').lower()
    satisfaction = ticket.get('satisfaction_score')
    created_date_str = ticket.get('created_date', '')
    resolved_date_str = ticket.get('resolved_date', '')

    summary = customer_support[customer_id]
    summary['total_tickets'] += 1

    # Resolution tracking
    if status in ['resolved', 'closed']:
        summary['resolved_tickets'] += 1

        if created_date_str and resolved_date_str:
            try:
                created = datetime.strptime(created_date_str, '%Y-%m-%d')
                resolved = datetime.strptime(resolved_date_str, '%Y-%m-%d')
                resolution_time = (resolved - created).days
                summary['avg_resolution_time'] = (summary['avg_resolution_time'] * (summary['resolved_tickets'] - 1) + resolution_time) / summary['resolved_tickets']
            except ValueError:
                pass

    # Satisfaction tracking
    if satisfaction:
        try:
            score = float(satisfaction)
            summary['satisfaction_scores'].append(score)
        except ValueError:
            pass

    # Escalation tracking
    if priority in ['high', 'urgent', 'critical']:
        summary['escalated_tickets'] += 1

    # Recent activity (last 30 days)
    if created_date_str:
        try:
            created = datetime.strptime(created_date_str, '%Y-%m-%d')
            if (current_date - created).days <= 30:
                summary['recent_tickets'] += 1
        except ValueError:
            pass

# Convert to list format with calculated metrics
result = []
for customer_id, summary in customer_support.items():
    avg_satisfaction = sum(summary['satisfaction_scores']) / len(summary['satisfaction_scores']) if summary['satisfaction_scores'] else 0
    resolution_rate = (summary['resolved_tickets'] / summary['total_tickets']) * 100 if summary['total_tickets'] > 0 else 0

    # Support health score (0-100)
    support_health = 100
    if avg_satisfaction > 0:
        support_health = avg_satisfaction * 20  # Convert 5-point scale to 100
    if resolution_rate < 90:
        support_health *= 0.9  # Penalty for low resolution rate
    if summary['escalated_tickets'] > summary['total_tickets'] * 0.3:
        support_health *= 0.8  # Penalty for high escalation rate

    result.append({
        'customer_id': customer_id,
        'total_support_tickets': summary['total_tickets'],
        'resolution_rate': round(resolution_rate, 1),
        'avg_resolution_days': round(summary['avg_resolution_time'], 1),
        'avg_satisfaction': round(avg_satisfaction, 2),
        'escalated_tickets': summary['escalated_tickets'],
        'recent_ticket_count': summary['recent_tickets'],
        'support_health_score': round(support_health, 1)
    })
"""
            ]
        },
        "customer_scoring": {
            "transformations": [
                """
# Comprehensive customer scoring and segmentation
from datetime import datetime

scored_customers = []

# Handle flattened data structure from MergeNode concat
if isinstance(data, list) and len(data) > 0:
    # If data is a list of lists (from concat merge), flatten it
    if isinstance(data[0], list):
        flattened_data = []
        for sublist in data:
            if isinstance(sublist, list):
                flattened_data.extend(sublist)
            else:
                flattened_data.append(sublist)
        data = flattened_data

    # Process customer data - iterate through each customer record
    for customer in data:
        # Skip if customer is not a dict (shouldn't happen but safety check)
        if not isinstance(customer, dict):
            continue

        # Base customer info
        customer_id = customer.get('customer_id')
        email = customer.get('email', '')

        # Data quality score
        data_quality = customer.get('data_quality_score', 0)

        # Financial metrics
        total_spent = float(customer.get('total_spent', 0))
        transaction_count = int(customer.get('transaction_count', 0))
        avg_order_value = float(customer.get('avg_order_value', 0))

        # Support metrics
        support_health = float(customer.get('support_health_score', 100))
        resolution_rate = float(customer.get('resolution_rate', 100))

        # Calculate composite scores

        # Value Score (0-100) - based on spending and frequency
        value_score = 0
        if total_spent > 0:
            value_score += min(total_spent / 1000 * 50, 50)  # Up to 50 points for spending
        if transaction_count > 0:
            value_score += min(transaction_count / 10 * 30, 30)  # Up to 30 points for frequency
        if avg_order_value > 0:
            value_score += min(avg_order_value / 200 * 20, 20)  # Up to 20 points for AOV

        # Engagement Score (0-100) - based on data quality and activity
        engagement_score = data_quality * 0.4  # 40% from data quality
        if transaction_count > 5:
            engagement_score += 30  # Active customer bonus
        if support_health > 80:
            engagement_score += 20  # Good support relationship
        if customer.get('email_valid'):
            engagement_score += 10  # Communication ready

        # Risk Score (0-100, lower is better)
        risk_score = 0
        if support_health < 70:
            risk_score += 30  # Support issues
        if resolution_rate < 80:
            risk_score += 25  # Poor resolution rate
        if transaction_count == 0:
            risk_score += 20  # No purchases
        if not customer.get('email_valid'):
            risk_score += 15  # Communication issues
        if data_quality < 50:
            risk_score += 10  # Data quality issues

        # Overall Customer Value Score
        customer_value_score = (value_score * 0.5 + engagement_score * 0.3 + (100 - risk_score) * 0.2)

        # Customer Segment
        if customer_value_score >= 80:
            segment = "VIP"
            priority = "High"
        elif customer_value_score >= 60:
            segment = "Premium"
            priority = "High"
        elif customer_value_score >= 40:
            segment = "Standard"
            priority = "Medium"
        else:
            segment = "Basic"
            priority = "Low"

        # Next Best Action recommendation
        next_action = "None"
        if risk_score > 60:
            next_action = "Retention Campaign"
        elif value_score > 70 and engagement_score < 50:
            next_action = "Engagement Campaign"
        elif segment == "VIP":
            next_action = "VIP Service Check-in"
        elif transaction_count == 0:
            next_action = "Activation Campaign"
        else:
            next_action = "Standard Nurture"

        scored_customer = dict(customer)
        scored_customer.update({
            'value_score': round(value_score, 1),
            'engagement_score': round(engagement_score, 1),
            'risk_score': round(risk_score, 1),
            'customer_value_score': round(customer_value_score, 1),
            'customer_segment': segment,
            'priority_level': priority,
            'next_best_action': next_action,
            'scoring_date': datetime.now().isoformat()
        })

        scored_customers.append(scored_customer)

result = scored_customers
"""
            ]
        },
        "high_value_processor": {
            "transformations": [
                """
# VIP and Premium customer special processing
processed_vips = []

# Handle input data which should be a single dict or None from SwitchNode true_output
if data and isinstance(data, dict):
    if data.get('customer_value_score', 0) >= 80:
        # VIP customer enrichment
        vip_customer = dict(data)
        vip_customer.update({
            'vip_status': True,
            'account_manager_required': True,
            'priority_support': True,
            'exclusive_offers_eligible': True,
            'review_frequency': 'Monthly',
            'escalation_path': 'Direct to Senior Management'
        })
        processed_vips.append(vip_customer)
elif data and isinstance(data, list):
    # Handle list input (fallback)
    for customer in data:
        if isinstance(customer, dict) and customer.get('customer_value_score', 0) >= 80:
            # VIP customer enrichment
            vip_customer = dict(customer)
            vip_customer.update({
                'vip_status': True,
                'account_manager_required': True,
                'priority_support': True,
                'exclusive_offers_eligible': True,
                'review_frequency': 'Monthly',
                'escalation_path': 'Direct to Senior Management'
            })
            processed_vips.append(vip_customer)

result = processed_vips
"""
            ]
        },
        "standard_processor": {
            "transformations": [
                """
# Standard customer processing
processed_standard = []

# Handle input data which should be a single dict or None from SwitchNode false_output
if data and isinstance(data, dict):
    if data.get('customer_value_score', 0) < 80:
        # Standard customer processing
        standard_customer = dict(data)
        standard_customer.update({
            'vip_status': False,
            'automated_communications': True,
            'self_service_preferred': True,
            'review_frequency': 'Quarterly',
            'marketing_campaigns_eligible': True
        })
        processed_standard.append(standard_customer)
elif data and isinstance(data, list):
    # Handle list input (fallback)
    for customer in data:
        if isinstance(customer, dict) and customer.get('customer_value_score', 0) < 80:
            # Standard customer processing
            standard_customer = dict(customer)
            standard_customer.update({
                'vip_status': False,
                'automated_communications': True,
                'self_service_preferred': True,
                'review_frequency': 'Quarterly',
                'marketing_campaigns_eligible': True
            })
            processed_standard.append(standard_customer)

result = processed_standard
"""
            ]
        },
        "crm_transaction_merge": {"merge_type": "concat"},
        "customer_support_merge": {"merge_type": "concat"},
        "final_customer_merge": {"merge_type": "concat"},
        "customer_router": {
            "condition_field": "customer_segment",
            "cases": ["VIP", "Premium"],
        },
    }

    try:
        print("Starting Customer 360° Integration...")
        print("📊 Integrating data from CRM, Transactions, Support, and Marketing...")

        result, run_id = runtime.execute(workflow, parameters=parameters)

        print("\n✅ Customer 360° Integration Complete!")
        print("📁 Outputs generated:")
        print("   - High-value customers: data/outputs/high_value_customers.json")
        print("   - Standard customers: data/outputs/standard_customers.csv")
        print("   - Complete customer 360°: data/outputs/customer_360_complete.json")

        # Summary statistics
        scoring_result = result.get("customer_scoring", {}).get("result", [])
        if scoring_result:
            total_customers = len(scoring_result)
            vip_count = len(
                [c for c in scoring_result if c.get("customer_segment") == "VIP"]
            )
            premium_count = len(
                [c for c in scoring_result if c.get("customer_segment") == "Premium"]
            )

            print("\n📈 Customer Analysis Summary:")
            print(f"   - Total customers processed: {total_customers}")
            print(f"   - VIP customers: {vip_count}")
            print(f"   - Premium customers: {premium_count}")
            print(
                f"   - Average customer value score: {sum(c.get('customer_value_score', 0) for c in scoring_result) / total_customers:.1f}"
            )

        return result

    except Exception as e:
        print(f"❌ Customer 360° Integration failed: {str(e)}")
        raise


def main():
    """Main entry point."""
    # Create output directories
    os.makedirs("data/outputs", exist_ok=True)

    # Run the Customer 360° integration
    run_customer_360_integration()


if __name__ == "__main__":
    main()
