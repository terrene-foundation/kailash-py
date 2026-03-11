"""
SaaS Starter Template - Webhook Handling

Simplified webhook handling with direct Python functions.

Functions:
- create_webhook_event(db, organization_id, event_type, payload) - Log webhook event
- get_webhook_events(db, organization_id, filters) - Query webhook events
- retry_failed_webhook(db, event_id) - Retry webhook
- mark_webhook_delivered(db, event_id) - Mark as delivered
- verify_webhook_signature(payload, signature, secret) - Verify webhook signature

Architecture:
- Direct Python functions for webhook logic
- Uses hmac+sha256 for signature verification
- DataFlow workflows ONLY for database operations
- Simple, testable, fast functions
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Webhook configuration
MAX_RETRY_COUNT = 3


def create_webhook_event(
    db, organization_id: str, event_type: str, payload: Dict
) -> Optional[Dict]:
    """
    Create webhook event record.

    Args:
        db: DataFlow instance
        organization_id: Organization ID
        event_type: Event type (e.g., "user.created", "user.updated")
        payload: Event payload dict

    Returns:
        Created webhook event dict

    Example:
        >>> event = create_webhook_event(
        ...     db,
        ...     "org_123",
        ...     "user.created",
        ...     {"user_id": "user_456", "email": "alice@example.com"}
        ... )
        >>> print(event["event_type"])
        user.created
    """
    # Generate event ID
    event_id = f"evt_{uuid.uuid4().hex[:16]}"

    # Create webhook event record
    workflow = WorkflowBuilder()
    workflow.add_node(
        "WebhookEventCreateNode",
        "create_event",
        {
            "id": event_id,
            "organization_id": organization_id,
            "event_type": event_type,
            "payload": payload,
            "status": "pending",
            "retry_count": 0,
        },
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    return results.get("create_event")


def get_webhook_events(
    db, organization_id: str, filters: Optional[Dict] = None
) -> List[Dict]:
    """
    Query webhook events.

    Args:
        db: DataFlow instance
        organization_id: Organization ID
        filters: Optional additional filters (event_type, status, etc.)

    Returns:
        List of webhook event dicts ordered by created_at

    Example:
        >>> events = get_webhook_events(
        ...     db,
        ...     "org_123",
        ...     {"event_type": "user.created", "status": "delivered"}
        ... )
        >>> for event in events:
        ...     print(event["event_type"])
        user.created
    """
    # Combine organization filter with additional filters
    query_filters = {"organization_id": organization_id}
    if filters:
        query_filters.update(filters)

    # Query webhook events
    workflow = WorkflowBuilder()
    workflow.add_node("WebhookEventListNode", "list_events", {"filters": query_filters})

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    return results.get("list_events", [])


def retry_failed_webhook(db, event_id: str) -> Optional[Dict]:
    """
    Retry failed webhook.

    Args:
        db: DataFlow instance
        event_id: Webhook event ID to retry

    Returns:
        Updated webhook event dict

    Example:
        >>> event = retry_failed_webhook(db, "evt_123")
        >>> print(event["retry_count"])
        1
    """
    # Get current event to check retry count
    read_workflow = WorkflowBuilder()
    read_workflow.add_node("WebhookEventReadNode", "read_event", {"id": event_id})

    runtime = LocalRuntime()
    read_results, _ = runtime.execute(read_workflow.build())

    current_event = read_results.get("read_event")
    if not current_event:
        return None

    # Increment retry count
    new_retry_count = current_event.get("retry_count", 0) + 1

    # Determine status based on retry count
    if new_retry_count >= MAX_RETRY_COUNT:
        new_status = "failed"
    else:
        new_status = "pending"

    # Update webhook event
    update_workflow = WorkflowBuilder()
    update_workflow.add_node(
        "WebhookEventUpdateNode",
        "update_event",
        {
            "filters": {"id": event_id},
            "fields": {
                "retry_count": new_retry_count,
                "status": new_status,
                "last_retry_at": datetime.now(),
            },
        },
    )

    update_results, _ = runtime.execute(update_workflow.build())
    return update_results.get("update_event")


def mark_webhook_delivered(db, event_id: str) -> Optional[Dict]:
    """
    Mark webhook as delivered.

    Args:
        db: DataFlow instance
        event_id: Webhook event ID

    Returns:
        Updated webhook event dict with status="delivered"

    Example:
        >>> event = mark_webhook_delivered(db, "evt_123")
        >>> print(event["status"])
        delivered
    """
    workflow = WorkflowBuilder()
    workflow.add_node(
        "WebhookEventUpdateNode",
        "update_event",
        {
            "filters": {"id": event_id},
            "fields": {"status": "delivered", "delivered_at": datetime.now()},
        },
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    return results.get("update_event")


def verify_webhook_signature(payload: Dict, signature: str, secret: str) -> bool:
    """
    Verify webhook signature using HMAC-SHA256.

    Args:
        payload: Webhook payload dict
        signature: Signature to verify
        secret: Webhook secret key

    Returns:
        True if signature is valid, False otherwise

    Example:
        >>> payload = {"event": "user.created", "data": {"user_id": "123"}}
        >>> secret = "webhook_secret"
        >>> # Generate signature
        >>> import hmac, hashlib, json
        >>> payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
        >>> sig = hmac.new(secret.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()
        >>> # Verify signature
        >>> verify_webhook_signature(payload, sig, secret)
        True
    """
    try:
        # Convert payload to canonical JSON string
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

        # Generate expected signature
        expected_signature = hmac.new(
            secret.encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()

        # Compare signatures (constant-time comparison)
        return hmac.compare_digest(expected_signature, signature)

    except Exception:
        return False
