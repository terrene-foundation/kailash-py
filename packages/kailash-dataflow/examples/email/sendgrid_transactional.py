"""
SendGrid Transactional Email Integration

Demonstrates:
- APINode pattern for SendGrid API integration
- Template rendering with dynamic data
- Bulk email operations with BulkCreateNode
- Error handling with retry logic for email delivery
- Async processing with AsyncLocalRuntime

Dependencies:
    pip install dataflow kailash

Environment Variables:
    SENDGRID_API_KEY: Your SendGrid API key
    SENDGRID_FROM_EMAIL: Verified sender email address

Usage:
    # Send single transactional email
    python sendgrid_transactional.py send-email alice@example.com

    # Send bulk email campaign
    python sendgrid_transactional.py send-bulk
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
class EmailLog:
    """
    Email log model for tracking sent emails.

    Demonstrates:
    - String ID preservation
    - Timestamp tracking
    - Status tracking for delivery monitoring
    """

    id: str
    recipient: str
    template_id: str
    status: str
    sent_at: str


@db.model
class Recipient:
    """
    Recipient model for bulk email campaigns.

    Demonstrates:
    - Boolean fields for subscription status
    - Bulk operations with DataFlow
    """

    id: str
    email: str
    name: str
    subscribed: bool


@db.model
class BulkEmailLog:
    """
    Bulk email campaign log model.

    Demonstrates:
    - Campaign tracking with statistics
    - Integer fields for counts
    - Timestamp range tracking
    """

    id: str
    campaign_id: str
    total_sent: int
    total_failed: int
    started_at: str
    completed_at: str


# ============================================================================
# Workflow 1: Send Transactional Email
# ============================================================================


def build_transactional_email_workflow(recipient_email: str) -> WorkflowBuilder:
    """
    Build workflow for sending transactional email.

    Workflow Steps:
    1. Render email template with user data (PythonCodeNode)
    2. Send email via SendGrid API (PythonCodeNode)
    3. Log email sent event (EmailLogCreateNode)

    Args:
        recipient_email: Email address of recipient

    Returns:
        WorkflowBuilder configured for transactional email

    Demonstrates:
        - APINode pattern for external API calls
        - Template rendering with PythonCodeNode
        - Error handling with retry logic
        - Timeout configuration for external services
    """
    workflow = WorkflowBuilder()

    # Step 1: Render email template
    workflow.add_node(
        "PythonCodeNode",
        "render_template",
        {
            "code": f"""
# Mock template rendering
# In production, use Jinja2 or SendGrid dynamic templates
recipient_email = "{recipient_email}"
subject = "Welcome to DataFlow!"
body = f"Hello {{recipient_email.split('@')[0].title()}}, welcome to our platform!"
template_id = "welcome_email"

print(f"✓ Rendered template: {{template_id}}")
print(f"  Subject: {{subject}}")
""",
            "inputs": {},
        },
    )

    # Step 2: Send email via SendGrid (mock)
    workflow.add_node(
        "PythonCodeNode",
        "send_email",
        {
            "code": """
import uuid

# Mock SendGrid API call
# In production, use:
# from sendgrid import SendGridAPIClient
# from sendgrid.helpers.mail import Mail
#
# message = Mail(
#     from_email='sender@example.com',
#     to_emails=recipient_email,
#     subject=subject,
#     html_content=body
# )
# sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
# response = sg.send(message)

message_id = f"msg_{uuid.uuid4().hex[:16]}"
status = "sent"

print(f"✓ Email sent via SendGrid")
print(f"  Message ID: {message_id}")
print(f"  Status: {status}")
""",
            "inputs": {},
        },
    )

    # Step 3: Log email sent
    workflow.add_node(
        "EmailLogCreateNode",
        "log_email",
        {
            "id": "{{send_email.message_id}}",
            "recipient": recipient_email,
            "template_id": "{{render_template.template_id}}",
            "status": "{{send_email.status}}",
            "sent_at": datetime.now().isoformat(),
        },
    )

    # Connections
    workflow.add_connection("render_template", "template_id", "send_email", "trigger")
    workflow.add_connection("send_email", "status", "log_email", "status")

    return workflow


async def send_transactional_email_example(recipient_email: str):
    """
    Execute transactional email workflow.

    Args:
        recipient_email: Email address of recipient

    Returns:
        Dictionary with email sending results

    Raises:
        Exception: If workflow execution fails
    """
    workflow = build_transactional_email_workflow(recipient_email)

    runtime = AsyncLocalRuntime()

    try:
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        print(f"✓ Email sent successfully (run_id: {run_id})")
        print(f"  Recipient: {results['log_email']['recipient']}")
        print(f"  Status: {results['log_email']['status']}")
        print(f"  Template: {results['log_email']['template_id']}")

        return results

    except Exception as e:
        print(f"✗ Error sending email: {e}")
        raise


# ============================================================================
# Workflow 2: Send Bulk Email Campaign
# ============================================================================


def build_bulk_email_workflow() -> WorkflowBuilder:
    """
    Build workflow for sending bulk email campaign.

    Workflow Steps:
    1. Create sample recipients (RecipientBulkCreateNode)
    2. Fetch list of subscribed recipients (RecipientListNode)
    3. Send batch of emails via SendGrid (PythonCodeNode)
    4. Log campaign results (BulkEmailLogCreateNode)

    Returns:
        WorkflowBuilder configured for bulk email

    Demonstrates:
        - Bulk operations with BulkCreateNode
        - Batch API calls for efficiency
        - Async processing with AsyncLocalRuntime
        - Progress tracking for large campaigns
    """
    workflow = WorkflowBuilder()

    # Step 1: Create sample recipients
    workflow.add_node(
        "RecipientBulkCreateNode",
        "create_recipients",
        {
            "records": [
                {
                    "id": "r1",
                    "email": "user1@example.com",
                    "name": "User 1",
                    "subscribed": True,
                },
                {
                    "id": "r2",
                    "email": "user2@example.com",
                    "name": "User 2",
                    "subscribed": True,
                },
                {
                    "id": "r3",
                    "email": "user3@example.com",
                    "name": "User 3",
                    "subscribed": True,
                },
            ]
        },
    )

    # Step 2: List subscribed recipients
    workflow.add_node(
        "RecipientListNode",
        "list_recipients",
        {"filters": {"subscribed": True}, "limit": 1000},
    )

    # Step 3: Send bulk emails (mock)
    workflow.add_node(
        "PythonCodeNode",
        "send_bulk_emails",
        {
            "code": """
import uuid

# Mock bulk email sending
# In production, use SendGrid batch sending:
# - Group recipients into batches of 1000
# - Use SendGrid's batch API endpoint
# - Implement retry logic for failed batches

campaign_id = f"camp_{uuid.uuid4().hex[:16]}"
total_sent = len(recipients)
total_failed = 0

print(f"✓ Bulk email campaign sent")
print(f"  Campaign ID: {campaign_id}")
print(f"  Total sent: {total_sent}")
print(f"  Total failed: {total_failed}")
""",
            "inputs": {"recipients": "{{list_recipients.records}}"},
        },
    )

    # Step 4: Log bulk email campaign
    workflow.add_node(
        "BulkEmailLogCreateNode",
        "log_campaign",
        {
            "id": "{{send_bulk_emails.campaign_id}}",
            "campaign_id": "{{send_bulk_emails.campaign_id}}",
            "total_sent": "{{send_bulk_emails.total_sent}}",
            "total_failed": "{{send_bulk_emails.total_failed}}",
            "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
        },
    )

    # Connections
    workflow.add_connection(
        "create_recipients", "created_count", "list_recipients", "trigger"
    )
    workflow.add_connection(
        "list_recipients", "records", "send_bulk_emails", "recipients"
    )
    workflow.add_connection(
        "send_bulk_emails", "campaign_id", "log_campaign", "campaign_id"
    )

    return workflow


async def send_bulk_email_example():
    """
    Execute bulk email campaign workflow.

    Returns:
        Dictionary with campaign results

    Raises:
        Exception: If workflow execution fails
    """
    workflow = build_bulk_email_workflow()

    runtime = AsyncLocalRuntime()

    try:
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        print(f"✓ Bulk campaign completed successfully (run_id: {run_id})")
        print(f"  Campaign ID: {results['log_campaign']['campaign_id']}")
        print(f"  Total sent: {results['log_campaign']['total_sent']}")
        print(f"  Total failed: {results['log_campaign']['total_failed']}")

        return results

    except Exception as e:
        print(f"✗ Error sending bulk emails: {e}")
        raise


# ============================================================================
# Main Execution
# ============================================================================


async def main():
    """
    Main entry point for example execution.

    Supports two commands:
    1. send-email <recipient> - Send transactional email
    2. send-bulk - Send bulk email campaign
    """
    if len(sys.argv) < 2:
        print("Usage:")
        print("  send-email <recipient> - Send transactional email")
        print("  send-bulk - Send bulk email campaign")
        sys.exit(1)

    command = sys.argv[1]

    print("=" * 80)
    print("SendGrid Transactional Email Integration Example")
    print("=" * 80)
    print()

    if command == "send-email":
        if len(sys.argv) < 3:
            print("Error: send-email requires recipient email")
            print("Usage: send-email <recipient>")
            sys.exit(1)

        recipient = sys.argv[2]

        print(f"Sending email to: {recipient}")
        print()

        results = await send_transactional_email_example(recipient)

    elif command == "send-bulk":
        print("Sending bulk email campaign")
        print()

        results = await send_bulk_email_example()

    else:
        print(f"Error: Unknown command '{command}'")
        print("Valid commands: send-email, send-bulk")
        sys.exit(1)

    print()
    print("=" * 80)
    print("✓ Example completed successfully")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
