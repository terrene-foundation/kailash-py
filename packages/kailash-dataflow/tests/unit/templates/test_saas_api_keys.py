"""
SaaS Starter Template - API Key Management Tests

Test-first development (TDD) for API key management.

Tests (10 total):
1. test_generate_api_key - Generate secure API key
2. test_hash_api_key - Hash API key for storage
3. test_create_api_key - Create API key record
4. test_verify_api_key_valid - Verify valid API key
5. test_verify_api_key_invalid - Verify invalid API key
6. test_revoke_api_key - Revoke API key
7. test_list_organization_api_keys - List organization API keys
8. test_api_key_scopes_validation - Validate API key scopes
9. test_api_key_expiration - Handle API key expiration
10. test_api_key_rate_limiting - API key rate limiting info

CRITICAL: These tests are written BEFORE implementation (RED phase).
Tests define the API contract and expected behavior for API key management.
"""

import hashlib
import os
import secrets

# Add templates directory to Python path for imports
import sys
from datetime import datetime, timedelta

import pytest

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "../../../templates")
if TEMPLATES_DIR not in sys.path:
    sys.path.insert(0, TEMPLATES_DIR)


@pytest.mark.unit
class TestAPIKeyManagement:
    """
    Test API key management functions (no complex workflows).

    Tests 1-10: Direct function tests with mocked DataFlow for speed.

    Real database integration tests are in tests/integration/templates/
    """

    def test_generate_api_key(self):
        """
        Test generating secure API key.

        Expected Behavior:
        - Output: cryptographically secure random API key string
        - Should be long enough (32+ chars)
        - Should be URL-safe
        - Pure function (no database access)

        RED Phase: This test will fail because generate_api_key() doesn't exist yet.
        """
        from saas_starter.security.api_keys import generate_api_key

        # Generate key
        api_key = generate_api_key()

        # Verify key properties
        assert isinstance(api_key, str), "API key should be string"
        assert len(api_key) >= 32, "API key should be at least 32 characters"
        assert (
            api_key.isalnum() or "_" in api_key or "-" in api_key
        ), "Should be URL-safe"

        # Verify randomness (two keys should be different)
        api_key2 = generate_api_key()
        assert api_key != api_key2, "Keys should be random/unique"

    def test_hash_api_key(self):
        """
        Test hashing API key for storage.

        Expected Behavior:
        - Input: plain API key
        - Output: hashed API key string
        - Should use secure hashing (SHA256 or better)
        - Pure function (no database access)

        RED Phase: This test will fail because hash_api_key() doesn't exist yet.
        """
        from saas_starter.security.api_keys import hash_api_key

        api_key = "test_api_key_12345"
        hashed = hash_api_key(api_key)

        # Verify hash properties
        assert isinstance(hashed, str), "Hash should be string"
        assert len(hashed) >= 64, "Hash should be at least 64 chars (SHA256)"
        assert hashed != api_key, "Hash should not equal plain key"

        # Verify deterministic hashing (same input = same output)
        hashed2 = hash_api_key(api_key)
        assert hashed == hashed2, "Same key should produce same hash"

        # Verify different keys produce different hashes
        different_key = "different_api_key_67890"
        different_hash = hash_api_key(different_key)
        assert (
            hashed != different_hash
        ), "Different keys should produce different hashes"

    def test_create_api_key(self, monkeypatch):
        """
        Test creating API key record.

        Expected Behavior:
        - Input: db instance, organization_id, name, scopes
        - Output: created API key dict with plain key (show only once!)
        - Uses DataFlow APIKeyCreateNode

        RED Phase: This test will fail because create_api_key() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.security.api_keys import create_api_key

        mock_db = MagicMock()
        org_id = "org_456"
        key_name = "Production API Key"
        scopes = ["read", "write"]

        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()

        # Create should return both the record and the plain key
        api_key_record = {
            "id": "key_123",
            "organization_id": org_id,
            "name": key_name,
            "key_hash": "abc123hash",
            "scopes": scopes,
            "status": "active",
            "created_at": datetime.now(),
        }

        mock_runtime.execute.return_value = (
            {"create_key": api_key_record},
            "run_id_123",
        )

        import saas_starter.security.api_keys

        with (
            patch.object(
                saas_starter.security.api_keys,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.security.api_keys,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = create_api_key(mock_db, org_id, key_name, scopes)

            # Verify API key created
            assert result is not None, "Should return API key data"
            assert "key" in result, "Should include plain API key (shown only once)"
            assert "record" in result, "Should include database record"
            assert result["record"]["name"] == key_name, "Should have correct name"
            assert result["record"]["organization_id"] == org_id, "Should belong to org"
            assert result["record"]["scopes"] == scopes, "Should have correct scopes"

    def test_verify_api_key_valid(self, monkeypatch):
        """
        Test verifying valid API key.

        Expected Behavior:
        - Input: db instance, plain API key
        - Output: API key info dict (organization_id, scopes, etc.)
        - Uses DataFlow APIKeyListNode with key_hash filter

        RED Phase: This test will fail because verify_api_key() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.security.api_keys import hash_api_key, verify_api_key

        mock_db = MagicMock()
        plain_key = "test_api_key_valid_12345"
        key_hash = hash_api_key(plain_key)

        # Valid API key record
        api_key_record = {
            "id": "key_123",
            "organization_id": "org_456",
            "name": "Test Key",
            "key_hash": key_hash,
            "scopes": ["read", "write"],
            "status": "active",
            "created_at": datetime.now(),
        }

        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = (
            {"list_keys": [api_key_record]},
            "run_id_123",
        )

        import saas_starter.security.api_keys

        with (
            patch.object(
                saas_starter.security.api_keys,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.security.api_keys,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = verify_api_key(mock_db, plain_key)

            # Verify API key validated
            assert result is not None, "Should return API key info"
            assert result["valid"] is True, "Should be valid"
            assert result["organization_id"] == "org_456", "Should return org ID"
            assert result["scopes"] == ["read", "write"], "Should return scopes"

    def test_verify_api_key_invalid(self, monkeypatch):
        """
        Test verifying invalid API key.

        Expected Behavior:
        - Input: db instance, invalid/non-existent API key
        - Output: error dict with valid=False
        - Hash lookup returns no results

        RED Phase: This test will fail because verify_api_key() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.security.api_keys import verify_api_key

        mock_db = MagicMock()
        invalid_key = "invalid_api_key_nonexistent"

        # Mock workflow execution - no keys found
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = ({"list_keys": []}, "run_id_123")

        import saas_starter.security.api_keys

        with (
            patch.object(
                saas_starter.security.api_keys,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.security.api_keys,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = verify_api_key(mock_db, invalid_key)

            # Verify API key rejected
            assert result is not None, "Should return result"
            assert result["valid"] is False, "Should be invalid"
            assert "error" in result, "Should contain error message"

    def test_revoke_api_key(self, monkeypatch):
        """
        Test revoking API key.

        Expected Behavior:
        - Input: db instance, key_id
        - Output: updated API key dict with status="revoked"
        - Uses DataFlow APIKeyUpdateNode

        RED Phase: This test will fail because revoke_api_key() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.security.api_keys import revoke_api_key

        mock_db = MagicMock()
        key_id = "key_123"

        # Revoked API key record
        revoked_key = {
            "id": key_id,
            "organization_id": "org_456",
            "name": "Revoked Key",
            "key_hash": "abc123hash",
            "scopes": ["read"],
            "status": "revoked",
            "created_at": datetime.now(),
        }

        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = ({"update_key": revoked_key}, "run_id_123")

        import saas_starter.security.api_keys

        with (
            patch.object(
                saas_starter.security.api_keys,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.security.api_keys,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = revoke_api_key(mock_db, key_id)

            # Verify API key revoked
            assert result is not None, "Should return updated key"
            assert result["status"] == "revoked", "Should be revoked"
            assert result["id"] == key_id, "Should have correct ID"

    def test_list_organization_api_keys(self, monkeypatch):
        """
        Test listing organization API keys.

        Expected Behavior:
        - Input: db instance, organization_id
        - Output: list of API key dicts (without plain keys!)
        - Uses DataFlow APIKeyListNode with organization_id filter

        RED Phase: This test will fail because list_organization_api_keys() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.security.api_keys import list_organization_api_keys

        mock_db = MagicMock()
        org_id = "org_456"

        # Organization API keys
        api_keys = [
            {
                "id": "key_1",
                "organization_id": org_id,
                "name": "Production Key",
                "key_hash": "hash1",
                "scopes": ["read", "write"],
                "status": "active",
                "created_at": datetime.now(),
            },
            {
                "id": "key_2",
                "organization_id": org_id,
                "name": "Dev Key",
                "key_hash": "hash2",
                "scopes": ["read"],
                "status": "active",
                "created_at": datetime.now(),
            },
        ]

        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = ({"list_keys": api_keys}, "run_id_123")

        import saas_starter.security.api_keys

        with (
            patch.object(
                saas_starter.security.api_keys,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.security.api_keys,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = list_organization_api_keys(mock_db, org_id)

            # Verify API keys listed
            assert isinstance(result, list), "Should return list"
            assert len(result) == 2, "Should return 2 keys"
            assert all(
                k["organization_id"] == org_id for k in result
            ), "All keys should belong to org"

    def test_api_key_scopes_validation(self):
        """
        Test API key scopes validation.

        Expected Behavior:
        - Valid scopes: read, write, admin, delete
        - Invalid scopes should be rejected
        - Scopes should be unique

        RED Phase: This test will fail because scope validation doesn't exist yet.
        """
        from saas_starter.security.api_keys import validate_scopes

        # Valid scopes
        valid_scopes = ["read", "write", "admin"]
        assert validate_scopes(valid_scopes) is True, "Valid scopes should pass"

        # Invalid scopes
        invalid_scopes = ["read", "invalid_scope"]
        try:
            validate_scopes(invalid_scopes)
            assert False, "Invalid scopes should raise error"
        except ValueError as e:
            assert (
                "invalid_scope" in str(e).lower()
            ), "Error should mention invalid scope"

        # Duplicate scopes should be deduplicated
        duplicate_scopes = ["read", "write", "read"]
        result = validate_scopes(duplicate_scopes, deduplicate=True)
        assert result is True, "Should handle duplicates"

    def test_api_key_expiration(self, monkeypatch):
        """
        Test API key expiration handling.

        Expected Behavior:
        - API keys can have expiration dates
        - Expired keys should not verify successfully
        - Expiration check in verify_api_key()

        RED Phase: This test will fail because expiration handling doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.security.api_keys import hash_api_key, verify_api_key

        mock_db = MagicMock()
        plain_key = "test_api_key_expired"
        key_hash = hash_api_key(plain_key)

        # Expired API key record
        expired_key = {
            "id": "key_expired",
            "organization_id": "org_456",
            "name": "Expired Key",
            "key_hash": key_hash,
            "scopes": ["read"],
            "status": "active",
            "expires_at": datetime.now() - timedelta(days=1),  # Expired yesterday
            "created_at": datetime.now() - timedelta(days=30),
        }

        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = ({"list_keys": [expired_key]}, "run_id_123")

        import saas_starter.security.api_keys

        with (
            patch.object(
                saas_starter.security.api_keys,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.security.api_keys,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = verify_api_key(mock_db, plain_key)

            # Verify expired key rejected
            assert result is not None, "Should return result"
            assert result["valid"] is False, "Expired key should be invalid"
            assert (
                "expired" in result.get("error", "").lower()
            ), "Error should mention expiration"

    def test_api_key_rate_limiting(self, monkeypatch):
        """
        Test API key rate limiting information.

        Expected Behavior:
        - API keys can have rate limit metadata
        - Different tiers have different limits
        - Rate limit info returned with verification

        RED Phase: This test will fail because rate limiting metadata doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.security.api_keys import hash_api_key, verify_api_key

        mock_db = MagicMock()
        plain_key = "test_api_key_rate_limited"
        key_hash = hash_api_key(plain_key)

        # API key with rate limit metadata
        rate_limited_key = {
            "id": "key_rate",
            "organization_id": "org_456",
            "name": "Rate Limited Key",
            "key_hash": key_hash,
            "scopes": ["read"],
            "status": "active",
            "rate_limit": 1000,  # Requests per hour
            "created_at": datetime.now(),
        }

        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = (
            {"list_keys": [rate_limited_key]},
            "run_id_123",
        )

        import saas_starter.security.api_keys

        with (
            patch.object(
                saas_starter.security.api_keys,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.security.api_keys,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = verify_api_key(mock_db, plain_key)

            # Verify rate limit info included
            assert result is not None, "Should return result"
            assert result["valid"] is True, "Should be valid"
            assert "rate_limit" in result, "Should include rate limit info"
            assert result["rate_limit"] == 1000, "Should have correct rate limit"
