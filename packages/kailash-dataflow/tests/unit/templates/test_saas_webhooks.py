"""
SaaS Starter Template - Webhook Handling Tests

Test-first development (TDD) for webhook handling.

Tests (10 total):
1. test_create_webhook_event - Log webhook event
2. test_get_webhook_events - Query webhook events
3. test_retry_failed_webhook - Retry failed webhook
4. test_mark_webhook_delivered - Mark webhook as delivered
5. test_verify_webhook_signature_valid - Verify valid webhook signature
6. test_verify_webhook_signature_invalid - Verify invalid webhook signature
7. test_webhook_event_filtering - Filter webhook events by type/status
8. test_webhook_retry_logic - Test retry logic with backoff
9. test_webhook_delivery_tracking - Track delivery attempts
10. test_webhook_event_ordering - Ensure correct event ordering

CRITICAL: These tests are written BEFORE implementation (RED phase).
Tests define the API contract and expected behavior for webhook handling.
"""

import hashlib
import hmac
import json
import os

# Add templates directory to Python path for imports
import sys
from datetime import datetime, timedelta

import pytest

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "../../../templates")
if TEMPLATES_DIR not in sys.path:
    sys.path.insert(0, TEMPLATES_DIR)


@pytest.mark.unit
class TestWebhookHandling:
    """
    Test webhook handling functions (no complex workflows).

    Tests 1-10: Direct function tests with mocked DataFlow for speed.

    Real database integration tests are in tests/integration/templates/
    """

    def test_create_webhook_event(self, monkeypatch):
        """
        Test creating webhook event record.

        Expected Behavior:
        - Input: db instance, organization_id, event_type, payload
        - Output: created webhook event dict
        - Uses DataFlow WebhookEventCreateNode

        RED Phase: This test will fail because create_webhook_event() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.integrations.webhooks import create_webhook_event

        mock_db = MagicMock()
        org_id = "org_456"
        event_type = "user.created"
        payload = {"user_id": "user_123", "email": "alice@example.com"}

        # Mock workflow execution
        webhook_event = {
            "id": "evt_123",
            "organization_id": org_id,
            "event_type": event_type,
            "payload": payload,
            "status": "pending",
            "retry_count": 0,
            "created_at": datetime.now(),
        }

        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = (
            {"create_event": webhook_event},
            "run_id_123",
        )

        import saas_starter.integrations.webhooks

        with (
            patch.object(
                saas_starter.integrations.webhooks,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.integrations.webhooks,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = create_webhook_event(mock_db, org_id, event_type, payload)

            # Verify webhook event created
            assert result is not None, "Should return webhook event"
            assert result["event_type"] == event_type, "Should have correct event type"
            assert result["organization_id"] == org_id, "Should belong to org"
            assert result["payload"] == payload, "Should have correct payload"
            assert result["status"] == "pending", "Should start as pending"

    def test_get_webhook_events(self, monkeypatch):
        """
        Test querying webhook events.

        Expected Behavior:
        - Input: db instance, organization_id, filters (optional)
        - Output: list of webhook event dicts
        - Uses DataFlow WebhookEventListNode with filters

        RED Phase: This test will fail because get_webhook_events() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.integrations.webhooks import get_webhook_events

        mock_db = MagicMock()
        org_id = "org_456"
        filters = {"event_type": "user.created", "status": "delivered"}

        # Mock webhook events
        webhook_events = [
            {
                "id": "evt_1",
                "organization_id": org_id,
                "event_type": "user.created",
                "payload": {"user_id": "user_1"},
                "status": "delivered",
                "created_at": datetime.now(),
            },
            {
                "id": "evt_2",
                "organization_id": org_id,
                "event_type": "user.created",
                "payload": {"user_id": "user_2"},
                "status": "delivered",
                "created_at": datetime.now(),
            },
        ]

        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = (
            {"list_events": webhook_events},
            "run_id_123",
        )

        import saas_starter.integrations.webhooks

        with (
            patch.object(
                saas_starter.integrations.webhooks,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.integrations.webhooks,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = get_webhook_events(mock_db, org_id, filters)

            # Verify webhook events returned
            assert isinstance(result, list), "Should return list"
            assert len(result) == 2, "Should return 2 events"
            assert all(
                e["organization_id"] == org_id for e in result
            ), "All events should belong to org"
            assert all(
                e["event_type"] == "user.created" for e in result
            ), "Should filter by event type"

    def test_retry_failed_webhook(self, monkeypatch):
        """
        Test retrying failed webhook.

        Expected Behavior:
        - Input: db instance, event_id
        - Output: updated webhook event dict with incremented retry_count
        - Uses DataFlow WebhookEventUpdateNode

        RED Phase: This test will fail because retry_failed_webhook() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.integrations.webhooks import retry_failed_webhook

        mock_db = MagicMock()
        event_id = "evt_failed"

        # Current event (before retry)
        current_event = {
            "id": event_id,
            "organization_id": "org_456",
            "event_type": "user.created",
            "payload": {"user_id": "user_123"},
            "status": "failed",
            "retry_count": 0,
            "created_at": datetime.now() - timedelta(hours=1),
        }

        # Updated webhook event after retry
        retried_event = {
            "id": event_id,
            "organization_id": "org_456",
            "event_type": "user.created",
            "payload": {"user_id": "user_123"},
            "status": "pending",  # Back to pending for retry
            "retry_count": 1,  # Incremented
            "last_retry_at": datetime.now(),
            "created_at": datetime.now() - timedelta(hours=1),
        }

        # Mock workflow execution - first call returns current event, second call returns updated event
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.side_effect = [
            ({"read_event": current_event}, "run_id_1"),
            ({"update_event": retried_event}, "run_id_2"),
        ]

        import saas_starter.integrations.webhooks

        with (
            patch.object(
                saas_starter.integrations.webhooks,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.integrations.webhooks,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = retry_failed_webhook(mock_db, event_id)

            # Verify webhook retried
            assert result is not None, "Should return updated event"
            assert result["retry_count"] == 1, "Should increment retry count"
            assert result["status"] == "pending", "Should be pending for retry"

    def test_mark_webhook_delivered(self, monkeypatch):
        """
        Test marking webhook as delivered.

        Expected Behavior:
        - Input: db instance, event_id
        - Output: updated webhook event dict with status="delivered"
        - Uses DataFlow WebhookEventUpdateNode

        RED Phase: This test will fail because mark_webhook_delivered() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.integrations.webhooks import mark_webhook_delivered

        mock_db = MagicMock()
        event_id = "evt_123"

        # Delivered webhook event
        delivered_event = {
            "id": event_id,
            "organization_id": "org_456",
            "event_type": "user.created",
            "payload": {"user_id": "user_123"},
            "status": "delivered",
            "delivered_at": datetime.now(),
            "created_at": datetime.now() - timedelta(minutes=5),
        }

        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = (
            {"update_event": delivered_event},
            "run_id_123",
        )

        import saas_starter.integrations.webhooks

        with (
            patch.object(
                saas_starter.integrations.webhooks,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.integrations.webhooks,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = mark_webhook_delivered(mock_db, event_id)

            # Verify webhook marked as delivered
            assert result is not None, "Should return updated event"
            assert result["status"] == "delivered", "Should be delivered"
            assert "delivered_at" in result, "Should have delivery timestamp"

    def test_verify_webhook_signature_valid(self):
        """
        Test verifying valid webhook signature.

        Expected Behavior:
        - Input: payload, signature, secret
        - Output: True if signature is valid
        - Uses HMAC-SHA256 for signature verification
        - Pure function (no database access)

        RED Phase: This test will fail because verify_webhook_signature() doesn't exist yet.
        """
        from saas_starter.integrations.webhooks import verify_webhook_signature

        payload = {"event": "user.created", "data": {"user_id": "123"}}
        secret = "webhook_secret_key"

        # Generate valid signature
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        signature = hmac.new(
            secret.encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()

        # Verify signature
        result = verify_webhook_signature(payload, signature, secret)
        assert result is True, "Valid signature should verify"

    def test_verify_webhook_signature_invalid(self):
        """
        Test verifying invalid webhook signature.

        Expected Behavior:
        - Input: payload, wrong signature, secret
        - Output: False if signature is invalid

        RED Phase: This test will fail because verify_webhook_signature() doesn't exist yet.
        """
        from saas_starter.integrations.webhooks import verify_webhook_signature

        payload = {"event": "user.created", "data": {"user_id": "123"}}
        secret = "webhook_secret_key"
        wrong_signature = "invalid_signature_abc123"

        # Verify wrong signature fails
        result = verify_webhook_signature(payload, wrong_signature, secret)
        assert result is False, "Invalid signature should fail"

    def test_webhook_event_filtering(self, monkeypatch):
        """
        Test webhook event filtering by type and status.

        Expected Behavior:
        - Can filter by event_type
        - Can filter by status
        - Can combine multiple filters

        RED Phase: This test will fail because get_webhook_events() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.integrations.webhooks import get_webhook_events

        mock_db = MagicMock()
        org_id = "org_456"

        # Test filtering by event type
        type_filters = {"event_type": "user.deleted"}
        type_events = [
            {
                "id": "evt_del_1",
                "organization_id": org_id,
                "event_type": "user.deleted",
                "status": "delivered",
                "created_at": datetime.now(),
            }
        ]

        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = ({"list_events": type_events}, "run_id_123")

        import saas_starter.integrations.webhooks

        with (
            patch.object(
                saas_starter.integrations.webhooks,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.integrations.webhooks,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = get_webhook_events(mock_db, org_id, type_filters)

            # Verify filtering works
            assert len(result) == 1, "Should return 1 event"
            assert result[0]["event_type"] == "user.deleted", "Should filter by type"

    def test_webhook_retry_logic(self, monkeypatch):
        """
        Test webhook retry logic with exponential backoff.

        Expected Behavior:
        - First retry: immediate
        - Second retry: after delay
        - Max retries: configurable (e.g., 3)
        - Failed after max retries: status="failed"

        RED Phase: This test will fail because retry logic doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.integrations.webhooks import retry_failed_webhook

        mock_db = MagicMock()
        event_id = "evt_retry_test"

        # Current event (at max retries - 1)
        current_event = {
            "id": event_id,
            "organization_id": "org_456",
            "event_type": "user.created",
            "payload": {"user_id": "user_123"},
            "status": "pending",
            "retry_count": 2,  # One retry left before max
            "created_at": datetime.now() - timedelta(hours=2),
        }

        # After max retries
        max_retries_event = {
            "id": event_id,
            "organization_id": "org_456",
            "event_type": "user.created",
            "payload": {"user_id": "user_123"},
            "status": "failed",  # Failed after max retries
            "retry_count": 3,  # Max retries reached
            "created_at": datetime.now() - timedelta(hours=2),
        }

        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.side_effect = [
            ({"read_event": current_event}, "run_id_1"),
            ({"update_event": max_retries_event}, "run_id_2"),
        ]

        import saas_starter.integrations.webhooks

        with (
            patch.object(
                saas_starter.integrations.webhooks,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.integrations.webhooks,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = retry_failed_webhook(mock_db, event_id)

            # Verify max retries handling
            assert result is not None, "Should return event"
            assert result["status"] == "failed", "Should be failed after max retries"
            assert result["retry_count"] == 3, "Should have max retry count"

    def test_webhook_delivery_tracking(self, monkeypatch):
        """
        Test webhook delivery attempt tracking.

        Expected Behavior:
        - Track number of delivery attempts
        - Track timestamps of attempts
        - Track delivery duration
        - Track response codes

        RED Phase: This test will fail because delivery tracking doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.integrations.webhooks import mark_webhook_delivered

        mock_db = MagicMock()
        event_id = "evt_track"

        # Webhook with delivery tracking
        tracked_event = {
            "id": event_id,
            "organization_id": "org_456",
            "event_type": "user.created",
            "payload": {"user_id": "user_123"},
            "status": "delivered",
            "delivery_attempts": [
                {
                    "timestamp": datetime.now() - timedelta(minutes=5),
                    "response_code": 500,
                    "duration_ms": 1200,
                },
                {"timestamp": datetime.now(), "response_code": 200, "duration_ms": 800},
            ],
            "created_at": datetime.now() - timedelta(minutes=10),
        }

        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = (
            {"update_event": tracked_event},
            "run_id_123",
        )

        import saas_starter.integrations.webhooks

        with (
            patch.object(
                saas_starter.integrations.webhooks,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.integrations.webhooks,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = mark_webhook_delivered(mock_db, event_id)

            # Verify delivery tracking
            assert result is not None, "Should return event"
            assert "delivery_attempts" in result, "Should track delivery attempts"
            assert len(result["delivery_attempts"]) == 2, "Should have 2 attempts"
            assert (
                result["delivery_attempts"][-1]["response_code"] == 200
            ), "Last attempt should succeed"

    def test_webhook_event_ordering(self, monkeypatch):
        """
        Test webhook event ordering (chronological).

        Expected Behavior:
        - Events returned in chronological order (oldest first)
        - Can specify reverse order (newest first)
        - Ordering based on created_at timestamp

        RED Phase: This test will fail because event ordering doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.integrations.webhooks import get_webhook_events

        mock_db = MagicMock()
        org_id = "org_456"

        # Webhook events in chronological order
        webhook_events = [
            {
                "id": "evt_1",
                "organization_id": org_id,
                "event_type": "user.created",
                "status": "delivered",
                "created_at": datetime.now() - timedelta(hours=2),
            },
            {
                "id": "evt_2",
                "organization_id": org_id,
                "event_type": "user.updated",
                "status": "delivered",
                "created_at": datetime.now() - timedelta(hours=1),
            },
            {
                "id": "evt_3",
                "organization_id": org_id,
                "event_type": "user.deleted",
                "status": "pending",
                "created_at": datetime.now(),
            },
        ]

        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = (
            {"list_events": webhook_events},
            "run_id_123",
        )

        import saas_starter.integrations.webhooks

        with (
            patch.object(
                saas_starter.integrations.webhooks,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.integrations.webhooks,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = get_webhook_events(mock_db, org_id, {})

            # Verify chronological ordering
            assert len(result) == 3, "Should return 3 events"
            assert (
                result[0]["created_at"] < result[1]["created_at"]
            ), "Should be chronological"
            assert (
                result[1]["created_at"] < result[2]["created_at"]
            ), "Should be chronological"
            assert result[0]["id"] == "evt_1", "Oldest event first"
            assert result[2]["id"] == "evt_3", "Newest event last"
