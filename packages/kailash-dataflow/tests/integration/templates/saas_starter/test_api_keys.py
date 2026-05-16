"""
SaaS Starter Template — API Key Management Tier-2 Integration Tests

Rewritten from tests/unit/templates/test_saas_api_keys.py per issue #996
sub-shard B-2b. Verbatim brief AC#5 from
workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:48-50:

    "Any remaining tier-1 test that imports motor, psycopg, or other DB
    drivers is either gated behind importorskip OR moved to
    tests/integration/."

Why this lives in tests/integration/ (Tier-2):
- saas_starter.security.api_keys imports `LocalRuntime` + `WorkflowBuilder`
  at top-of-file (banned in Tier-1 per specs/testing-tiers.md § Tier-1
  Rule 1) and dispatches every create/verify/revoke/list call through a
  real workflow execution against a real database.
- The original unit-tier file ran `runtime.execute(workflow)` against
  aiosqlite which deadlocked on the GH-runner py3.11 worker (issue #979
  brief failure-layer #3).
- Per Tier-2 contract (specs/testing-tiers.md + rules/testing.md
  § "3-Tier Testing"): NO MOCKING. The integration conftest at
  packages/kailash-dataflow/tests/integration/conftest.py AST-scans
  every collected module and refuses collection if it imports any
  unittest.mock primitive (Mock, MagicMock, AsyncMock, patch, ...).
- Real DataFlow against file-backed SQLite — same pattern as the
  api_gateway_starter integration tests (which also use saas_starter's
  api_keys helpers and a temp-file SQLite database). File-backed is
  preferred over `:memory:` because DataFlow's migration pool opens
  multiple short-lived connections that each get isolated databases
  with bare `:memory:`.

Coverage equivalence to the original 10 unit-tier tests:
  1. test_generate_api_key            — pure-function key generation
  2. test_hash_api_key                — pure-function deterministic hash
  3. test_create_api_key              — end-to-end create + DB persistence
  4. test_verify_api_key_valid        — verify a real created key
  5. test_verify_api_key_invalid      — verify rejects nonexistent key
  6. test_revoke_api_key              — revoke + verify status flip
  7. test_list_organization_api_keys  — list scoped to one org
  8. test_api_key_scopes_validation   — pure-function scope whitelist
  9. test_api_key_expiration          — verify rejects expired key
 10. test_api_key_rate_limiting       — verify surfaces rate_limit field

Additional Tier-2 coverage beyond the original mocked unit tests:
 11. test_api_key_uniqueness_across_n_calls — generate_api_key entropy
 12. test_create_api_key_returns_plain_key_only_once — security invariant
 13. test_revoked_key_fails_verify           — end-to-end revoke→verify
 14. test_list_only_returns_caller_org_keys  — tenant isolation
 15. test_hash_does_not_leak_plain_key       — hash one-way contract
"""

import os
import tempfile
import uuid
from datetime import datetime, timedelta
from typing import Optional

import pytest

from dataflow import DataFlow


@pytest.fixture
def db():
    """Real DataFlow instance against a file-backed SQLite database.

    Registers the APIKey model with the schema saas_starter.security
    .api_keys expects (id, organization_id, name, key_hash, scopes,
    status, rate_limit, expires_at). Same pattern as the sibling
    api_gateway_starter integration test fixture.

    File-backed (not `:memory:`) because DataFlow's migration pool
    opens multiple short-lived connections that each get isolated
    databases with bare `:memory:`.

    Cleanup per rules/testing.md § "Fixtures Yield + Cleanup, Never
    Return" — explicit close_async() + temp dir removal.
    """
    tmpdir = tempfile.mkdtemp(prefix="saas_api_keys_test_")
    database_url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmpdir}/test.db")
    db_instance = DataFlow(database_url)

    @db_instance.model
    class APIKey:
        id: str
        organization_id: str
        name: str
        key_hash: str
        scopes: list
        status: str
        rate_limit: Optional[int] = None
        expires_at: Optional[datetime] = None

        __dataflow__ = {
            "indexes": [
                {"name": "idx_apikey_org", "fields": ["organization_id"]},
                {"name": "idx_apikey_hash", "fields": ["key_hash"]},
                {"name": "idx_apikey_status", "fields": ["status"]},
            ]
        }

    yield db_instance

    # Cleanup: close DataFlow instance + remove temp dir
    import shutil

    try:
        import asyncio

        asyncio.run(db_instance.close_async())
    except Exception:
        # Cleanup errors during fixture teardown are expected (event
        # loop may already be closed); OS reclaims the temp dir.
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def org_id():
    """Unique organization id per test for tenant isolation."""
    return f"org-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Pure-function tests (1, 2, 8, 11, 15) — no DB required, but kept in
# Tier-2 so the entire api_keys helper suite has one consistent home and
# anyone running `pytest tests/integration/templates/saas_starter/` sees
# the full picture.
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPureFunctions:
    """Pure-function coverage: key generation, hashing, scope validation."""

    def test_generate_api_key_has_expected_structural_properties(self):
        """generate_api_key MUST return a URL-safe string of ≥32 chars."""
        from templates.saas_starter.security.api_keys import generate_api_key

        api_key = generate_api_key()

        assert isinstance(api_key, str)
        assert len(api_key) >= 32
        # secrets.token_urlsafe output is RFC 3986 URL-safe (A-Z, a-z, 0-9, -, _)
        assert all(c.isalnum() or c in ("-", "_") for c in api_key)

    def test_api_key_uniqueness_across_n_calls(self):
        """100 generated keys MUST all be unique (entropy proof)."""
        from templates.saas_starter.security.api_keys import generate_api_key

        keys = {generate_api_key() for _ in range(100)}
        assert len(keys) == 100  # zero collisions → real CSPRNG entropy

    def test_hash_api_key_returns_sha256_hex(self):
        """hash_api_key MUST return a 64-char hex SHA256 digest."""
        from templates.saas_starter.security.api_keys import hash_api_key

        api_key = "test_api_key_12345"
        hashed = hash_api_key(api_key)

        assert isinstance(hashed, str)
        assert len(hashed) == 64  # SHA256 hex digest length
        assert all(c in "0123456789abcdef" for c in hashed)
        assert hashed != api_key

    def test_hash_api_key_is_deterministic(self):
        """Same input MUST hash to same output across calls."""
        from templates.saas_starter.security.api_keys import hash_api_key

        key = "consistent_test_key_xyz"
        assert hash_api_key(key) == hash_api_key(key)

    def test_hash_api_key_differs_for_different_inputs(self):
        """Different inputs MUST produce different hashes."""
        from templates.saas_starter.security.api_keys import hash_api_key

        assert hash_api_key("key_alpha") != hash_api_key("key_beta")

    def test_hash_does_not_leak_plain_key(self):
        """Hash output MUST NOT contain the plain key as a substring."""
        from templates.saas_starter.security.api_keys import hash_api_key

        plain = "sk_distinctive_marker_98765"
        hashed = hash_api_key(plain)
        assert plain not in hashed

    def test_validate_scopes_accepts_whitelist(self):
        """validate_scopes MUST accept read/write/admin/delete."""
        from templates.saas_starter.security.api_keys import validate_scopes

        assert validate_scopes(["read"]) is True
        assert validate_scopes(["read", "write"]) is True
        assert validate_scopes(["read", "write", "admin", "delete"]) is True

    def test_validate_scopes_rejects_unknown_scope(self):
        """validate_scopes MUST raise ValueError on unknown scope."""
        from templates.saas_starter.security.api_keys import validate_scopes

        with pytest.raises(ValueError, match="invalid_scope_xyz"):
            validate_scopes(["read", "invalid_scope_xyz"])

    def test_validate_scopes_handles_duplicates_when_dedup_true(self):
        """With deduplicate=True, duplicates pass through."""
        from templates.saas_starter.security.api_keys import validate_scopes

        assert validate_scopes(["read", "write", "read"], deduplicate=True) is True


# ---------------------------------------------------------------------------
# Database integration tests (3-7, 9, 10, 12-14) — real DataFlow,
# real SQLite, real workflow execution.
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateAPIKey:
    """End-to-end key creation against real DataFlow."""

    def test_create_api_key_returns_plain_key_and_record(self, db, org_id):
        """create_api_key MUST return both plain key + DB record."""
        from templates.saas_starter.security.api_keys import create_api_key

        result = create_api_key(db, org_id, "Production Key", ["read", "write"])

        assert result is not None
        assert "key" in result, "Plain key must be returned (shown once)"
        assert "record" in result, "Database record must be returned"

        # Plain key is real (not None / empty)
        assert isinstance(result["key"], str)
        assert len(result["key"]) >= 32

        # Record reflects what was stored
        record = result["record"]
        assert record["organization_id"] == org_id
        assert record["name"] == "Production Key"
        assert record["scopes"] == ["read", "write"]
        assert record["status"] == "active"

    def test_create_api_key_returns_plain_key_only_once(self, db, org_id):
        """Security invariant: stored record contains hash, NOT plain key."""
        from templates.saas_starter.security.api_keys import (
            create_api_key,
            hash_api_key,
        )

        result = create_api_key(db, org_id, "One-Time Key", ["read"])

        plain_key = result["key"]
        stored_hash = result["record"]["key_hash"]

        # The DB stores only the hash — plain key is in the returned dict
        # for the caller to display once, never persisted.
        assert stored_hash == hash_api_key(plain_key)
        assert stored_hash != plain_key

    def test_create_api_key_rejects_invalid_scope(self, db, org_id):
        """Invalid scopes MUST raise before any DB write."""
        from templates.saas_starter.security.api_keys import create_api_key

        with pytest.raises(ValueError, match="invalid_scope"):
            create_api_key(db, org_id, "Bad Key", ["read", "invalid_scope"])


@pytest.mark.integration
class TestVerifyAPIKey:
    """End-to-end key verification against real DataFlow."""

    def test_verify_api_key_valid_returns_org_and_scopes(self, db, org_id):
        """A real created key MUST verify successfully."""
        from templates.saas_starter.security.api_keys import (
            create_api_key,
            verify_api_key,
        )

        created = create_api_key(db, org_id, "Test Key", ["read", "write"])
        plain_key = created["key"]

        result = verify_api_key(db, plain_key)

        assert result is not None
        assert result["valid"] is True
        assert result["organization_id"] == org_id
        assert sorted(result["scopes"]) == ["read", "write"]

    def test_verify_api_key_invalid_returns_error(self, db, org_id):
        """A key that was never created MUST be rejected."""
        from templates.saas_starter.security.api_keys import verify_api_key

        result = verify_api_key(db, "definitely_not_a_real_key_xyz_99999")

        assert result is not None
        assert result["valid"] is False
        assert "error" in result


@pytest.mark.integration
class TestRevokeAPIKey:
    """End-to-end key revocation against real DataFlow."""

    def test_revoke_api_key_flips_status_to_revoked(self, db, org_id):
        """revoke_api_key MUST update status to revoked."""
        from templates.saas_starter.security.api_keys import (
            create_api_key,
            revoke_api_key,
        )

        created = create_api_key(db, org_id, "Revocable Key", ["read"])
        key_id = created["record"]["id"]

        revoked = revoke_api_key(db, key_id)

        assert revoked is not None
        assert revoked["id"] == key_id
        assert revoked["status"] == "revoked"

    def test_revoked_key_fails_verify(self, db, org_id):
        """A revoked key MUST no longer verify successfully.

        End-to-end test: create → verify(ok) → revoke → verify(fail).
        This is the security-critical invariant: revocation MUST take
        effect at the verify path.
        """
        from templates.saas_starter.security.api_keys import (
            create_api_key,
            revoke_api_key,
            verify_api_key,
        )

        created = create_api_key(db, org_id, "Will Be Revoked", ["read"])
        plain_key = created["key"]
        key_id = created["record"]["id"]

        # Pre-revoke verify succeeds
        pre = verify_api_key(db, plain_key)
        assert pre["valid"] is True

        # Revoke
        revoke_api_key(db, key_id)

        # Post-revoke verify fails
        post = verify_api_key(db, plain_key)
        assert post["valid"] is False
        assert "error" in post


@pytest.mark.integration
class TestListOrganizationAPIKeys:
    """End-to-end key listing scoped to organization."""

    def test_list_organization_api_keys_returns_all_org_keys(self, db, org_id):
        """list_organization_api_keys MUST return every key for the org."""
        from templates.saas_starter.security.api_keys import (
            create_api_key,
            list_organization_api_keys,
        )

        create_api_key(db, org_id, "Production Key", ["read", "write"])
        create_api_key(db, org_id, "Dev Key", ["read"])

        keys = list_organization_api_keys(db, org_id)

        # ListNode response shape may be a bare list OR a paginated dict
        # ({"records": [...], "count": N, "limit": L}). Normalize both
        # shapes to a list of records — matches the contract surfaced
        # via verify_api_key (which handles the same dual shape).
        records = keys.get("records") if isinstance(keys, dict) else keys
        assert len(records) == 2
        assert all(k["organization_id"] == org_id for k in records)
        names = sorted(k["name"] for k in records)
        assert names == ["Dev Key", "Production Key"]

    def test_list_only_returns_caller_org_keys(self, db, org_id):
        """Tenant isolation: org A's list MUST NOT return org B's keys.

        Security-critical invariant. End-to-end test that a list call
        scoped to one organization_id structurally excludes another
        organization's keys.
        """
        from templates.saas_starter.security.api_keys import (
            create_api_key,
            list_organization_api_keys,
        )

        other_org = f"org-other-{uuid.uuid4().hex[:8]}"

        create_api_key(db, org_id, "Caller Org Key", ["read"])
        create_api_key(db, other_org, "Other Org Key", ["read"])

        # Caller's list returns only the caller's key
        caller_keys = list_organization_api_keys(db, org_id)
        caller_records = (
            caller_keys.get("records") if isinstance(caller_keys, dict) else caller_keys
        )
        assert len(caller_records) == 1
        assert caller_records[0]["organization_id"] == org_id
        assert caller_records[0]["name"] == "Caller Org Key"

        # Other org's list returns only the other org's key
        other_keys = list_organization_api_keys(db, other_org)
        other_records = (
            other_keys.get("records") if isinstance(other_keys, dict) else other_keys
        )
        assert len(other_records) == 1
        assert other_records[0]["organization_id"] == other_org
        assert other_records[0]["name"] == "Other Org Key"


@pytest.mark.integration
class TestAPIKeyExpiration:
    """End-to-end expired-key handling.

    Note: create_api_key does not currently expose expires_at — to
    inject an expired key we read-then-update via DataFlow directly,
    mirroring how operations would set expiry through admin tooling.
    """

    def test_expired_key_fails_verify(self, db, org_id):
        """A key with expires_at < now MUST fail verification with
        an 'expired' error message.
        """
        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        from templates.saas_starter.security.api_keys import (
            create_api_key,
            verify_api_key,
        )

        # Create a normal key
        created = create_api_key(db, org_id, "Expired Key", ["read"])
        plain_key = created["key"]
        key_id = created["record"]["id"]

        # Stamp an expires_at in the past via APIKeyUpdateNode
        # (UpdateNode reads ``filter`` singular — ``filters`` plural is dropped)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "APIKeyUpdateNode",
            "expire_key",
            {
                "filter": {"id": key_id},
                "fields": {"expires_at": datetime.now() - timedelta(days=1)},
            },
        )
        with LocalRuntime() as runtime:
            runtime.execute(workflow.build())

        # Verify rejects the expired key
        result = verify_api_key(db, plain_key)

        assert result is not None
        assert result["valid"] is False
        assert "expired" in result.get("error", "").lower()


@pytest.mark.integration
class TestAPIKeyRateLimiting:
    """End-to-end rate_limit metadata surfacing on verify."""

    def test_rate_limited_key_surfaces_rate_limit_on_verify(self, db, org_id):
        """A key with rate_limit set MUST return rate_limit on verify."""
        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        from templates.saas_starter.security.api_keys import (
            create_api_key,
            verify_api_key,
        )

        # Create a key + set rate_limit via APIKeyUpdateNode (the
        # create_api_key helper does not accept rate_limit as input;
        # admin tooling would populate it post-create).
        created = create_api_key(db, org_id, "Rate Limited Key", ["read"])
        plain_key = created["key"]
        key_id = created["record"]["id"]

        # (UpdateNode reads ``filter`` singular — ``filters`` plural is dropped)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "APIKeyUpdateNode",
            "set_rate_limit",
            {"filter": {"id": key_id}, "fields": {"rate_limit": 1000}},
        )
        with LocalRuntime() as runtime:
            runtime.execute(workflow.build())

        result = verify_api_key(db, plain_key)

        assert result is not None
        assert result["valid"] is True
        assert "rate_limit" in result
        assert result["rate_limit"] == 1000


# ---------------------------------------------------------------------------
# Round-5 timezone-safety regression tests — MED-2
#
# verify_api_key compares expires_at against datetime.now(). Pre-fix the
# right-hand side was naive — a tz-aware expires_at (PostgreSQL
# TIMESTAMP WITH TIME ZONE, aiosqlite-with-detect_types) raised
# TypeError instead of returning the documented expired-key error.
#
# The two tests below exercise BOTH branches of the normalization fix:
#  - tz-aware expires_at compares cleanly (no TypeError)
#  - naive expires_at is normalized to UTC then compared cleanly
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAPIKeyExpirationTimezoneSafety:
    """Round-5 MED-2 regression: tz-aware datetime comparison for expires_at."""

    def test_verify_api_key_handles_tz_aware_expired(self, db, org_id):
        """A tz-aware expires_at in the past MUST return the expired-error,
        NOT raise TypeError."""
        from datetime import timezone as _timezone

        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        from templates.saas_starter.security.api_keys import (
            create_api_key,
            verify_api_key,
        )

        created = create_api_key(db, org_id, "TZ-Aware Expired", ["read"])
        plain_key = created["key"]
        key_id = created["record"]["id"]

        # Stamp a tz-aware (UTC) expires_at in the past.
        tz_aware_past = datetime.now(_timezone.utc) - timedelta(hours=1)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "APIKeyUpdateNode",
            "expire_key",
            {
                "filter": {"id": key_id},
                "fields": {"expires_at": tz_aware_past},
            },
        )
        with LocalRuntime() as runtime:
            runtime.execute(workflow.build())

        # Pre-fix this raised TypeError because datetime.now() returned a
        # naive datetime and tz-aware < naive comparison is illegal.
        result = verify_api_key(db, plain_key)

        assert result is not None, "verify_api_key MUST NOT raise"
        assert result["valid"] is False
        assert "expired" in result.get("error", "").lower()

    def test_verify_api_key_handles_tz_aware_not_expired(self, db, org_id):
        """A tz-aware expires_at in the future MUST verify successfully
        (positive control proving the tz-aware path is exercised)."""
        from datetime import timezone as _timezone

        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        from templates.saas_starter.security.api_keys import (
            create_api_key,
            verify_api_key,
        )

        created = create_api_key(db, org_id, "TZ-Aware Future", ["read"])
        plain_key = created["key"]
        key_id = created["record"]["id"]

        # Stamp a tz-aware (UTC) expires_at in the future.
        tz_aware_future = datetime.now(_timezone.utc) + timedelta(hours=1)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "APIKeyUpdateNode",
            "set_expires",
            {
                "filter": {"id": key_id},
                "fields": {"expires_at": tz_aware_future},
            },
        )
        with LocalRuntime() as runtime:
            runtime.execute(workflow.build())

        result = verify_api_key(db, plain_key)

        assert result is not None, "verify_api_key MUST NOT raise"
        assert result["valid"] is True, "Future-expiry key MUST validate"
        assert result["organization_id"] == org_id

    def test_verify_api_key_handles_naive_string_expired(self, db, org_id):
        """A naive ISO-string expires_at (the aiosqlite path) MUST be
        normalized to UTC and compared cleanly without TypeError.

        SQLite stores DATETIME columns as TEXT and returns them as ISO
        strings; verify_api_key parses with datetime.fromisoformat,
        which produces a NAIVE datetime when the string has no tz
        suffix. Pre-fix, comparing naive < datetime.now(UTC) raised
        TypeError; post-fix the naive value is upgraded to UTC via
        replace(tzinfo=timezone.utc) before comparison.
        """
        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        from templates.saas_starter.security.api_keys import (
            create_api_key,
            verify_api_key,
        )

        created = create_api_key(db, org_id, "Naive String Expired", ["read"])
        plain_key = created["key"]
        key_id = created["record"]["id"]

        # Stamp a NAIVE datetime in the past. On SQLite this stores as
        # an ISO string with no tz suffix and round-trips back as a
        # naive datetime (or as the same ISO string, depending on the
        # adapter — verify_api_key handles both cases).
        naive_past = datetime.now() - timedelta(hours=2)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "APIKeyUpdateNode",
            "expire_key",
            {
                "filter": {"id": key_id},
                "fields": {"expires_at": naive_past},
            },
        )
        with LocalRuntime() as runtime:
            runtime.execute(workflow.build())

        # Pre-fix this raised TypeError on PostgreSQL (tz-aware row +
        # naive datetime.now()); post-fix the naive expires_at branch
        # is normalized to UTC and the comparison runs cleanly.
        result = verify_api_key(db, plain_key)

        assert result is not None, "verify_api_key MUST NOT raise"
        assert result["valid"] is False
        assert "expired" in result.get("error", "").lower()
