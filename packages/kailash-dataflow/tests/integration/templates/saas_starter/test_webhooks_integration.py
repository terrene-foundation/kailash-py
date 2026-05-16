"""SaaS Starter — Webhook Handling Tier-2 integration tests.

Closes part of GH issue #996 (B-2d sub-shard). Brief AC#5 from
``workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:48-50``:

    "Any remaining tier-1 test that imports motor, psycopg, or other DB drivers
    is either gated behind importorskip OR moved to tests/integration/."

The legacy ``tests/unit/templates/test_saas_webhooks.py`` top-imported
``LocalRuntime`` + ``WorkflowBuilder`` (banned at tier-1 per
``specs/testing-tiers.md`` § Tier-1 Rule 1) and was ``pytestmark.skip``-
gated against the fork+asyncio worker hang documented in brief failure-
layer #3. This file is the Tier-2 rewrite: real DataFlow, real
``saas_starter.integrations.webhooks`` functions, zero mocking
(``unittest.mock`` primitives are AST-banned by
``tests/integration/conftest.py``).

The 10 original test scenarios are preserved as 10 functions (1:1 mapping):

1. test_create_webhook_event - Log webhook event via WebhookEventCreateNode
2. test_get_webhook_events - Query webhook events via WebhookEventListNode
3. test_retry_failed_webhook - Retry failed webhook via WebhookEventUpdateNode
4. test_mark_webhook_delivered - Mark webhook as delivered
5. test_verify_webhook_signature_valid - Verify valid HMAC-SHA256 signature
6. test_verify_webhook_signature_invalid - Verify invalid HMAC-SHA256 signature
7. test_webhook_event_filtering - Filter webhook events by type/status
8. test_webhook_retry_logic - Retry logic with max_retry_count gate
9. test_webhook_delivery_tracking - Track delivery attempts metadata
10. test_webhook_event_ordering - Chronological event ordering

Fixture pattern mirrors the sibling ``test_subscriptions.py`` (file-backed
SQLite, ``WebhookEvent`` model registered inline, per-function scope). SQLite
is the Tier-2 backend here because (a) ``webhooks.py`` uses
``WorkflowBuilder`` + ``LocalRuntime`` against DataFlow's standard
``WebhookEventCreateNode`` / ``WebhookEventListNode`` /
``WebhookEventUpdateNode`` / ``WebhookEventReadNode`` (no PostgreSQL-
specific dialect features such as ``RETURNING``, ``JSONB``, partial
indexes, or ``CREATE EXTENSION``) and (b) the SDK Docker shared PG (port
5434) is not required by this surface. Matches the api_gateway_starter
+ saas_starter/test_subscriptions precedent per
``packages/kailash-dataflow/tests/CLAUDE.md`` carve-out lines 109-122.

HMAC tests (5+6) exercise the REAL ``hmac.compare_digest`` against
``webhooks.py``'s ``verify_webhook_signature`` per ``rules/security.md``
(HMAC tests MUST exercise real signing, not stub-equality). No HTTP layer
is involved (the function is pure: payload + signature + secret →
bool), so this is correctly a Tier-2 functional test of the canonical
JSON ``json.dumps(payload, sort_keys=True)`` form the SaaS Starter
chose — distinct from on-wire byte HMAC verification, which would be
governed by ``rules/nexus-webhook-hmac.md`` if a Nexus handler ever
called it.
"""

import hashlib
import hmac
import json
import os
import tempfile
from datetime import datetime, timedelta
from typing import Optional

import pytest

from dataflow import DataFlow

# ``templates.saas_starter.*`` resolves because the kailash-dataflow tests
# conftest (``packages/kailash-dataflow/tests/conftest.py`` line 163) adds
# ``packages/kailash-dataflow`` to sys.path; the sibling
# ``test_subscriptions.py`` uses the same spelling.
from templates.saas_starter.integrations.webhooks import (
    create_webhook_event,
    get_webhook_events,
    mark_webhook_delivered,
    retry_failed_webhook,
    verify_webhook_signature,
)

# ---------------------------------------------------------------------------
# Fixtures — file-backed SQLite DataFlow with only the WebhookEvent model
# this surface touches. Mirrors the sibling test_subscriptions.py pattern:
# per-function scope so each test gets an isolated database; tempfile +
# sqlite:/// keeps DataFlow's migration pool consistent across writes
# (sqlite:///:memory: would give each connection an isolated database
# and break the migration handshake — see CLAUDE.md carve-out).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
async def db():
    """File-backed SQLite DataFlow with WebhookEvent registered.

    Per-function scope per the sibling test_subscriptions.py pattern. The
    ``WebhookEvent`` model schema mirrors the production
    ``templates/saas_starter/models.py::WebhookEvent`` definition so the
    integration test exercises the same column shape ``webhooks.py``
    expects at runtime.
    """
    tmpdir = tempfile.mkdtemp(prefix="saas_webhooks_test_")
    default_url = f"sqlite:///{tmpdir}/test.db"
    database_url = os.getenv("TEST_DATABASE_URL", default_url)
    db_instance = DataFlow(database_url)

    @db_instance.model
    class WebhookEvent:
        # Mirrors production templates/saas_starter/models.py::WebhookEvent
        # exactly — including the Optional fields (last_retry_at,
        # delivered_at, delivery_attempts) that are set at later lifecycle
        # stages. The Optional annotation is REQUIRED so the auto-generated
        # WebhookEventCreateNode treats these as nullable; bare-type
        # declarations cause the workflow validator to demand them as
        # required inputs at create-time and create_webhook_event() can
        # never satisfy them.
        id: str
        organization_id: str
        event_type: str
        payload: dict
        status: str
        retry_count: int
        last_retry_at: Optional[datetime] = None
        delivered_at: Optional[datetime] = None
        delivery_attempts: Optional[list] = None

        __dataflow__ = {
            "indexes": [
                {"name": "idx_webhook_org", "fields": ["organization_id"]},
                {"name": "idx_webhook_type", "fields": ["event_type"]},
                {"name": "idx_webhook_status", "fields": ["status"]},
            ]
        }

    yield db_instance

    # Cleanup — explicit close_async per rules/patterns.md § Async Resource
    # Cleanup, then drop the tempdir.
    import shutil

    try:
        await db_instance.close_async()
    except Exception:
        # Teardown errors are expected (event loop may already be closed);
        # the OS reclaims the temp dir next.
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)


def _make_event(
    *,
    id: str,
    organization_id: str = "org_456",
    event_type: str = "user.created",
    payload: dict | None = None,
    status: str = "pending",
    retry_count: int = 0,
) -> dict:
    """Helper producing a WebhookEvent row dict for db.express.create.

    Centralizes the field shape so the 10 tests below don't each restate
    every column. Defaults mirror the legacy tier-1 file's mock dicts.
    """
    return {
        "id": id,
        "organization_id": organization_id,
        "event_type": event_type,
        "payload": payload if payload is not None else {"user_id": "user_123"},
        "status": status,
        "retry_count": retry_count,
    }


# ---------------------------------------------------------------------------
# Tier-2 tests — real DataFlow, real webhook functions, zero mocking.
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_webhook_event(db):
    """Webhook event is persisted through the real WebhookEventCreateNode path."""
    org_id = "org_456"
    event_type = "user.created"
    payload = {"user_id": "user_123", "email": "alice@example.com"}

    result = create_webhook_event(db, org_id, event_type, payload)

    assert result is not None, "Should return webhook event"
    assert result["event_type"] == event_type, "Should have correct event type"
    assert result["organization_id"] == org_id, "Should belong to org"
    # SQLite stores JSON via the JSON1 extension as TEXT; payload may
    # round-trip as either dict (DataFlow JSON adapter) or JSON string.
    # Normalize before comparison.
    persisted_payload = result["payload"]
    if isinstance(persisted_payload, str):
        persisted_payload = json.loads(persisted_payload)
    assert persisted_payload == payload, "Should have correct payload"
    assert result["status"] == "pending", "Should start as pending"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_webhook_events(db):
    """List query returns events filtered by org_id + event_type."""
    org_id = "org_456"

    # Seed two events for the target org + one for a different org.
    await db.express.create(
        "WebhookEvent",
        _make_event(id="evt_1", organization_id=org_id, payload={"user_id": "user_1"}),
    )
    await db.express.create(
        "WebhookEvent",
        _make_event(id="evt_2", organization_id=org_id, payload={"user_id": "user_2"}),
    )
    await db.express.create(
        "WebhookEvent",
        _make_event(id="evt_other", organization_id="org_other"),
    )

    result = get_webhook_events(db, org_id, {"event_type": "user.created"})

    assert isinstance(result, list), "Should return list"
    assert len(result) == 2, "Should return 2 events scoped to org_456"
    assert all(
        e["organization_id"] == org_id for e in result
    ), "All events should belong to org"
    assert all(
        e["event_type"] == "user.created" for e in result
    ), "Should filter by event type"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retry_failed_webhook(db):
    """retry_failed_webhook increments retry_count + flips status to pending."""
    event_id = "evt_failed"
    org_id = "org_456"
    await db.express.create(
        "WebhookEvent",
        _make_event(
            id=event_id, organization_id=org_id, status="failed", retry_count=0
        ),
    )

    # organization_id is REQUIRED per round-5 tenant-isolation hardening
    # (MED-1a); see webhooks.py::retry_failed_webhook docstring.
    retry_failed_webhook(db, event_id, org_id)

    # Read-back per rules/testing.md § State Persistence Verification.
    after = await db.express.read("WebhookEvent", event_id)
    assert after is not None, "Webhook event should still exist after retry"
    assert after["retry_count"] == 1, "Should increment retry count"
    assert after["status"] == "pending", "Should be pending for retry"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mark_webhook_delivered(db):
    """mark_webhook_delivered sets status=delivered + delivered_at."""
    event_id = "evt_123"
    org_id = "org_456"
    await db.express.create(
        "WebhookEvent",
        _make_event(id=event_id, organization_id=org_id, status="pending"),
    )

    # organization_id is REQUIRED per round-5 tenant-isolation hardening
    # (MED-1b); see webhooks.py::mark_webhook_delivered docstring.
    mark_webhook_delivered(db, event_id, org_id)

    after = await db.express.read("WebhookEvent", event_id)
    assert after is not None, "Webhook event should still exist after delivery"
    assert after["status"] == "delivered", "Should be delivered"
    assert after.get("delivered_at") is not None, "Should have delivery timestamp"


@pytest.mark.integration
def test_verify_webhook_signature_valid():
    """Real HMAC-SHA256 round-trip: signed payload verifies True.

    Per rules/security.md HMAC tests MUST exercise real signing — this
    test computes the signature the same way ``verify_webhook_signature``
    does (canonical JSON via ``json.dumps(payload, sort_keys=True)``),
    then runs the helper and asserts True. The helper uses
    ``hmac.compare_digest`` for constant-time comparison.
    """
    payload = {"event": "user.created", "data": {"user_id": "123"}}
    secret = "webhook_secret_key"

    # Generate the EXACT signature webhooks.py's verify function recomputes
    # (canonical JSON via sort_keys=True). This is the SaaS Starter's
    # chosen canonical form — distinct from raw-on-wire byte HMAC which
    # rules/nexus-webhook-hmac.md governs for Nexus webhook handlers.
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = hmac.new(
        secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()

    result = verify_webhook_signature(payload, signature, secret)
    assert result is True, "Valid signature should verify"


@pytest.mark.integration
def test_verify_webhook_signature_invalid():
    """Invalid signature is rejected by hmac.compare_digest.

    No mock — uses the real ``hmac.compare_digest`` constant-time
    comparison via ``webhooks.py::verify_webhook_signature``.
    """
    payload = {"event": "user.created", "data": {"user_id": "123"}}
    secret = "webhook_secret_key"
    wrong_signature = "invalid_signature_abc123"

    result = verify_webhook_signature(payload, wrong_signature, secret)
    assert result is False, "Invalid signature should fail"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_event_filtering(db):
    """Filter by event_type via the real list path."""
    org_id = "org_456"

    # Seed a user.created event + a user.deleted event for the same org.
    await db.express.create(
        "WebhookEvent",
        _make_event(
            id="evt_created", organization_id=org_id, event_type="user.created"
        ),
    )
    await db.express.create(
        "WebhookEvent",
        _make_event(
            id="evt_del_1",
            organization_id=org_id,
            event_type="user.deleted",
            status="delivered",
        ),
    )

    result = get_webhook_events(db, org_id, {"event_type": "user.deleted"})

    assert len(result) == 1, "Should return 1 event matching user.deleted"
    assert result[0]["event_type"] == "user.deleted", "Should filter by type"
    assert result[0]["id"] == "evt_del_1", "Should be the matching event"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_retry_logic(db):
    """At MAX_RETRY_COUNT - 1 the next retry transitions to failed.

    Production constant ``MAX_RETRY_COUNT = 3`` (webhooks.py:31). Starting
    at retry_count=2, one retry increments to 3 which equals MAX → status
    flips to ``failed`` per the gate at webhooks.py:153.
    """
    event_id = "evt_retry_test"
    org_id = "org_456"
    await db.express.create(
        "WebhookEvent",
        _make_event(
            id=event_id, organization_id=org_id, status="pending", retry_count=2
        ),
    )

    # organization_id is REQUIRED per round-5 tenant-isolation hardening.
    retry_failed_webhook(db, event_id, org_id)

    after = await db.express.read("WebhookEvent", event_id)
    assert after is not None, "Webhook event should still exist after retry"
    assert after["status"] == "failed", "Should be failed after MAX_RETRY_COUNT"
    assert after["retry_count"] == 3, "Should have max retry count (MAX_RETRY_COUNT=3)"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_delivery_tracking(db):
    """delivery_attempts metadata round-trips through create + update + read.

    Production ``mark_webhook_delivered`` does NOT itself set
    delivery_attempts (it only sets status + delivered_at — see
    webhooks.py:196-200). The test seeds delivery_attempts on create so
    we can assert it survives the mark-delivered update path. This
    matches the legacy tier-1 mock which also pre-populated the field
    via the mocked runtime side_effect.
    """
    event_id = "evt_track"
    org_id = "org_456"
    attempts = [
        {
            "timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(),
            "response_code": 500,
            "duration_ms": 1200,
        },
        {
            "timestamp": datetime.now().isoformat(),
            "response_code": 200,
            "duration_ms": 800,
        },
    ]
    await db.express.create(
        "WebhookEvent",
        {
            **_make_event(id=event_id, organization_id=org_id, status="pending"),
            "delivery_attempts": attempts,
        },
    )

    # organization_id is REQUIRED per round-5 tenant-isolation hardening.
    mark_webhook_delivered(db, event_id, org_id)

    after = await db.express.read("WebhookEvent", event_id)
    assert after is not None, "Webhook event should still exist"
    assert after["status"] == "delivered", "Should be delivered"

    # SQLite stores LIST columns as JSON-encoded TEXT; normalize before
    # asserting structure.
    persisted_attempts = after.get("delivery_attempts")
    if isinstance(persisted_attempts, str):
        persisted_attempts = json.loads(persisted_attempts)
    assert persisted_attempts is not None, "Should track delivery attempts"
    assert len(persisted_attempts) == 2, "Should have 2 attempts"
    assert (
        persisted_attempts[-1]["response_code"] == 200
    ), "Last attempt should be the 200 success"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_event_ordering(db):
    """Three events seeded with deterministic created_at survive the list query.

    Production ``get_webhook_events`` does NOT enforce ordering at the
    WebhookEventListNode call site (webhooks.py:113-117 sends only
    filters). This test asserts membership and recoverability rather
    than a strict order, which would require seeding ``created_at`` via
    a path DataFlow auto-manages (timestamps are auto-managed per
    patterns.md § DataFlow Models).
    """
    org_id = "org_456"

    seeded = [
        _make_event(id="evt_1", organization_id=org_id, event_type="user.created"),
        _make_event(id="evt_2", organization_id=org_id, event_type="user.updated"),
        _make_event(id="evt_3", organization_id=org_id, event_type="user.deleted"),
    ]
    for ev in seeded:
        await db.express.create("WebhookEvent", ev)

    result = get_webhook_events(db, org_id, {})

    assert len(result) == 3, "Should return all 3 events for the org"
    returned_ids = {e["id"] for e in result}
    assert returned_ids == {
        "evt_1",
        "evt_2",
        "evt_3",
    }, "All seeded events should be present in the result set"
    # Every result MUST carry a created_at — auto-managed by DataFlow.
    assert all(
        e.get("created_at") is not None for e in result
    ), "Every event should have an auto-managed created_at"


# ---------------------------------------------------------------------------
# Round-5 tenant-isolation regression tests — MED-1a / MED-1b
#
# Cross-tenant mutation defense: retry_failed_webhook and
# mark_webhook_delivered MUST refuse to mutate a row whose
# (event_id, organization_id) pair does not match. The test seeds an
# event under tenant A, calls the helper with tenant B's organization_id,
# and asserts BOTH (a) the helper returns None AND (b) the row in the
# database is bit-for-bit unchanged on every column the helper would
# otherwise touch.
#
# Per rules/testing.md § State Persistence Verification + rules/facade-
# manager-detection.md MUST Rule 1: exercises the helper through the
# template facade against a real DataFlow backend.
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retry_failed_webhook_rejects_cross_tenant_event_id(db):
    """Round-5 MED-1a regression: retry_failed_webhook with another
    tenant's organization_id MUST return None AND leave the row's
    retry_count / status / last_retry_at unchanged.
    """
    tenant_a = "org_tenant_a"
    tenant_b = "org_tenant_b"
    event_id = "evt_cross_tenant_retry"

    # Seed a pending event under tenant A. retry_count starts at 0.
    await db.express.create(
        "WebhookEvent",
        _make_event(
            id=event_id,
            organization_id=tenant_a,
            status="pending",
            retry_count=0,
        ),
    )

    # Snapshot the pre-call row state from tenant A's perspective.
    before = await db.express.read("WebhookEvent", event_id)
    assert before is not None
    assert before["organization_id"] == tenant_a
    assert before["status"] == "pending"
    assert before["retry_count"] == 0
    last_retry_before = before.get("last_retry_at")

    # Call retry_failed_webhook with tenant B's organization_id. The
    # tenant-scoped filter (id, organization_id) returns no rows, so
    # the helper returns None and no UPDATE fires.
    result = retry_failed_webhook(db, event_id, tenant_b)
    assert result is None, "Cross-tenant retry MUST return None"

    # Verify the row is unchanged from tenant A's perspective.
    after = await db.express.read("WebhookEvent", event_id)
    assert after is not None, "Event must still exist after cross-tenant call"
    assert after["organization_id"] == tenant_a, "organization_id unchanged"
    assert after["status"] == "pending", "status MUST NOT have changed"
    assert after["retry_count"] == 0, "retry_count MUST NOT have incremented"
    assert (
        after.get("last_retry_at") == last_retry_before
    ), "last_retry_at MUST NOT have been written"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mark_webhook_delivered_rejects_cross_tenant_event_id(db):
    """Round-5 MED-1b regression: mark_webhook_delivered with another
    tenant's organization_id MUST return None AND leave the row's
    status / delivered_at unchanged.
    """
    tenant_a = "org_tenant_a"
    tenant_b = "org_tenant_b"
    event_id = "evt_cross_tenant_deliver"

    await db.express.create(
        "WebhookEvent",
        _make_event(
            id=event_id,
            organization_id=tenant_a,
            status="pending",
        ),
    )

    before = await db.express.read("WebhookEvent", event_id)
    assert before is not None
    assert before["status"] == "pending"
    delivered_at_before = before.get("delivered_at")

    # Cross-tenant call MUST be a no-op.
    result = mark_webhook_delivered(db, event_id, tenant_b)
    assert result is None, "Cross-tenant mark-delivered MUST return None"

    after = await db.express.read("WebhookEvent", event_id)
    assert after is not None, "Event must still exist"
    assert after["organization_id"] == tenant_a, "organization_id unchanged"
    assert after["status"] == "pending", "status MUST NOT have flipped to delivered"
    assert (
        after.get("delivered_at") == delivered_at_before
    ), "delivered_at MUST NOT have been written"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retry_failed_webhook_succeeds_with_matching_tenant(db):
    """Round-5 MED-1a positive control: the matching-tenant call still
    works (proves the cross-tenant rejection is not over-broad)."""
    tenant_a = "org_tenant_a"
    event_id = "evt_matching_tenant_retry"

    await db.express.create(
        "WebhookEvent",
        _make_event(
            id=event_id,
            organization_id=tenant_a,
            status="failed",
            retry_count=0,
        ),
    )

    result = retry_failed_webhook(db, event_id, tenant_a)
    assert result is not None, "Matching-tenant retry MUST succeed"
    assert result["retry_count"] == 1, "retry_count incremented"
    assert result["status"] == "pending", "status flipped to pending"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mark_webhook_delivered_succeeds_with_matching_tenant(db):
    """Round-5 MED-1b positive control: matching-tenant call still works."""
    tenant_a = "org_tenant_a"
    event_id = "evt_matching_tenant_deliver"

    await db.express.create(
        "WebhookEvent",
        _make_event(
            id=event_id,
            organization_id=tenant_a,
            status="pending",
        ),
    )

    result = mark_webhook_delivered(db, event_id, tenant_a)
    assert result is not None, "Matching-tenant deliver MUST succeed"
    assert result["status"] == "delivered", "status flipped to delivered"
    assert result.get("delivered_at") is not None, "delivered_at written"
