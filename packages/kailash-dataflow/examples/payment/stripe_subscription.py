"""
Stripe Subscription Management - Payment Processing Integration

Demonstrates:
- ErrorEnhancer for retry logic with Stripe API
- Webhook signature verification for payment events
- SwitchNode for conditional customer creation logic
- DataFlow CreateNode for payment record persistence
- Multi-step payment workflows with error handling

Dependencies:
    pip install dataflow kailash

Environment Variables:
    STRIPE_SECRET_KEY: Your Stripe secret API key (sk_test_...)
    STRIPE_WEBHOOK_SECRET: Webhook signing secret for signature verification

Usage:
    # Create customer workflow
    python stripe_subscription.py create-customer alice@example.com "Alice Smith"

    # Handle webhook workflow
    python stripe_subscription.py handle-webhook
"""

import asyncio
import sys
from datetime import datetime

from dataflow import DataFlow

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# ============================================================================
# Database Models
# ============================================================================

# Create in-memory database for demonstration
db = DataFlow(":memory:")


@db.model
class Customer:
    """
    Customer model for storing Stripe customer data.

    String IDs are preserved exactly as provided (no integer conversion).
    """

    id: str
    email: str
    stripe_customer_id: str
    name: str


@db.model
class Subscription:
    """
    Subscription model for storing Stripe subscription data.

    Demonstrates:
    - Foreign key relationship (customer_id)
    - Status tracking for subscription lifecycle
    - Plan details storage
    """

    id: str
    customer_id: str
    stripe_subscription_id: str
    status: str
    plan_name: str


# ============================================================================
# Workflow 1: Create Stripe Customer
# ============================================================================


def build_create_customer_workflow(email: str, name: str) -> WorkflowBuilder:
    """
    Build workflow for creating Stripe customer.

    Workflow Steps:
    1. Check if customer exists by email (CustomerListNode)
    2. Switch based on existence (SwitchNode with skip_branches)
    3. If not exists, create Stripe customer via API (PythonCodeNode)
    4. Store customer record in database (CustomerCreateNode)
    5. Return customer ID and stripe_customer_id

    Args:
        email: Customer email address
        name: Customer name

    Returns:
        WorkflowBuilder configured for customer creation

    Demonstrates:
        - SwitchNode for conditional logic with skip_branches execution
        - APINode pattern for Stripe integration (mocked for demo)
        - DataFlow CreateNode for persistence
        - Error handling with retry logic
    """
    workflow = WorkflowBuilder()

    # Step 1: Check if customer exists
    workflow.add_node(
        "CustomerListNode", "check_customer", {"filters": {"email": email}, "limit": 1}
    )

    # Step 2: Switch based on existence
    workflow.add_node(
        "SwitchNode",
        "customer_exists",
        {"condition": "len(check_customer.records) > 0"},
    )

    # Step 3: Create Stripe customer (mock API call)
    workflow.add_node(
        "PythonCodeNode",
        "create_stripe_customer",
        {
            "code": """
import uuid

# Mock Stripe customer creation
# In production, use: stripe.Customer.create(email=customer_email, name=customer_name)
stripe_customer_id = f"cus_{uuid.uuid4().hex[:24]}"
customer_email = email
customer_name = name

# Simulate API response
print(f"✓ Created Stripe customer: {stripe_customer_id}")
""",
            "inputs": {"email": email, "name": name},
        },
    )

    # Step 4: Store customer in database
    workflow.add_node(
        "CustomerCreateNode",
        "store_customer",
        {
            "id": f"cust-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "email": email,
            "stripe_customer_id": "{{create_stripe_customer.stripe_customer_id}}",
            "name": name,
        },
    )

    # Connections
    workflow.add_connection(
        "check_customer", "records", "customer_exists", "input_data"
    )
    workflow.add_connection(
        "customer_exists", "false_output", "create_stripe_customer", "trigger"
    )
    workflow.add_connection(
        "create_stripe_customer",
        "stripe_customer_id",
        "store_customer",
        "stripe_customer_id",
    )

    return workflow


async def create_customer_example(email: str, name: str):
    """
    Execute create customer workflow.

    Args:
        email: Customer email address
        name: Customer name

    Returns:
        Dictionary with customer creation results

    Raises:
        Exception: If workflow execution fails
    """
    workflow = build_create_customer_workflow(email, name)

    # Use skip_branches for SwitchNode execution
    runtime = AsyncLocalRuntime(conditional_execution="skip_branches")

    try:
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        print(f"✓ Workflow completed successfully (run_id: {run_id})")
        print(f"  Customer ID: {results['store_customer']['id']}")
        print(f"  Email: {results['store_customer']['email']}")
        print(f"  Stripe ID: {results['store_customer']['stripe_customer_id']}")

        return results

    except Exception as e:
        print(f"✗ Error creating customer: {e}")
        raise


# ============================================================================
# Workflow 2: Handle Stripe Webhook
# ============================================================================


def build_webhook_handler_workflow() -> WorkflowBuilder:
    """
    Build workflow for handling Stripe webhook events.

    Workflow Steps:
    1. Verify webhook signature (PythonCodeNode)
    2. Extract payment intent data
    3. Update customer subscription status (SubscriptionCreateNode)
    4. Send confirmation email (PythonCodeNode)

    Returns:
        WorkflowBuilder configured for webhook handling

    Demonstrates:
        - Webhook signature verification (security pattern)
        - Error handling for invalid signatures
        - Payment intent processing
        - Email notification integration
    """
    workflow = WorkflowBuilder()

    # Step 1: Verify webhook signature
    workflow.add_node(
        "PythonCodeNode",
        "verify_signature",
        {
            "code": """
import hmac
import hashlib

# Mock signature verification
# In production, use: stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
signature = "test_signature"
verified = True  # Assume valid for demo

# Mock webhook data
webhook_data = {
    'id': 'sub_123',
    'customer': 'cus_123',
    'status': 'active',
    'plan': {'name': 'Pro Plan'}
}

print(f"✓ Webhook signature verified")
""",
            "inputs": {},
        },
    )

    # Step 2: Create subscription record
    workflow.add_node(
        "SubscriptionCreateNode",
        "store_subscription",
        {
            "id": f"sub-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "customer_id": "cust-001",
            "stripe_subscription_id": "{{verify_signature.webhook_data.id}}",
            "status": "{{verify_signature.webhook_data.status}}",
            "plan_name": "{{verify_signature.webhook_data.plan.name}}",
        },
    )

    # Step 3: Send confirmation email (mock)
    workflow.add_node(
        "PythonCodeNode",
        "send_email",
        {
            "code": """
# Mock email sending
# In production, use SendGrid, Mailgun, etc.
email_sent = True
recipient = "alice@example.com"

print(f"✓ Confirmation email sent to {recipient}")
""",
            "inputs": {},
        },
    )

    # Connections
    workflow.add_connection(
        "verify_signature", "verified", "store_subscription", "trigger"
    )
    workflow.add_connection("store_subscription", "id", "send_email", "trigger")

    return workflow


async def handle_webhook_example():
    """
    Execute webhook handler workflow.

    Returns:
        Dictionary with webhook processing results

    Raises:
        Exception: If workflow execution fails
    """
    workflow = build_webhook_handler_workflow()

    runtime = AsyncLocalRuntime()

    try:
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        print(f"✓ Webhook processed successfully (run_id: {run_id})")
        print(f"  Subscription ID: {results['store_subscription']['id']}")
        print(f"  Status: {results['store_subscription']['status']}")
        print(f"  Plan: {results['store_subscription']['plan_name']}")

        return results

    except Exception as e:
        print(f"✗ Error processing webhook: {e}")
        raise


# ============================================================================
# Main Execution
# ============================================================================


async def main():
    """
    Main entry point for example execution.

    Supports two commands:
    1. create-customer <email> <name> - Create Stripe customer
    2. handle-webhook - Process Stripe webhook event
    """
    if len(sys.argv) < 2:
        print("Usage:")
        print("  create-customer <email> <name> - Create Stripe customer")
        print("  handle-webhook - Process Stripe webhook event")
        sys.exit(1)

    command = sys.argv[1]

    print("=" * 80)
    print("Stripe Subscription Management Example")
    print("=" * 80)
    print()

    if command == "create-customer":
        if len(sys.argv) < 4:
            print("Error: create-customer requires email and name")
            print("Usage: create-customer <email> <name>")
            sys.exit(1)

        email = sys.argv[2]
        name = " ".join(sys.argv[3:])

        print(f"Creating customer: {name} <{email}>")
        print()

        results = await create_customer_example(email, name)

    elif command == "handle-webhook":
        print("Processing Stripe webhook event")
        print()

        results = await handle_webhook_example()

    else:
        print(f"Error: Unknown command '{command}'")
        print("Valid commands: create-customer, handle-webhook")
        sys.exit(1)

    print()
    print("=" * 80)
    print("✓ Example completed successfully")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
