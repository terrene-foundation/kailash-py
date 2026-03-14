# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for EATP exception hierarchy (Phase 8, item 8.7).

Covers:
    1. HookError inherits from TrustError
    2. HookTimeoutError inherits from HookError (and transitively TrustError)
    3. ProximityError inherits from TrustError
    4. BehavioralScoringError inherits from TrustError
    5. KMSConnectionError inherits from TrustError
    6. RevocationError inherits from TrustError
    7. PathTraversalError inherits from TrustError
    8. All exceptions populate .details dict
    9. String representation includes message and details
    10. Each exception can be raised and caught by its parent class
    11. Each exception can be raised and caught by TrustError
    12. Existing exceptions are unaffected by new additions
"""

from __future__ import annotations

import pytest

from eatp.exceptions import (
    BehavioralScoringError,
    HookError,
    HookTimeoutError,
    KMSConnectionError,
    PathTraversalError,
    ProximityError,
    RevocationError,
    TrustError,
)


# ---------------------------------------------------------------------------
# 1. HookError
# ---------------------------------------------------------------------------


class TestHookError:
    """HookError is the base for hook-related failures."""

    def test_inherits_from_trust_error(self):
        assert issubclass(HookError, TrustError)

    def test_is_instance_of_trust_error(self):
        err = HookError("hook failed", details={"hook_name": "pre_delegate"})
        assert isinstance(err, TrustError)

    def test_message_stored(self):
        err = HookError("hook failed", details={"hook_name": "pre_delegate"})
        assert err.message == "hook failed"

    def test_details_populated(self):
        err = HookError("hook failed", details={"hook_name": "pre_delegate"})
        assert err.details == {"hook_name": "pre_delegate"}

    def test_details_defaults_to_empty_dict(self):
        err = HookError("hook failed")
        assert err.details == {}

    def test_str_with_details(self):
        err = HookError("hook failed", details={"hook_name": "pre_delegate"})
        result = str(err)
        assert "hook failed" in result
        assert "pre_delegate" in result

    def test_str_without_details(self):
        err = HookError("hook failed")
        assert str(err) == "hook failed"

    def test_caught_by_trust_error(self):
        with pytest.raises(TrustError):
            raise HookError("hook failed", details={"hook_name": "pre_delegate"})

    def test_caught_by_own_type(self):
        with pytest.raises(HookError):
            raise HookError("hook failed")


# ---------------------------------------------------------------------------
# 2. HookTimeoutError
# ---------------------------------------------------------------------------


class TestHookTimeoutError:
    """HookTimeoutError is raised when a hook exceeds its timeout."""

    def test_inherits_from_hook_error(self):
        assert issubclass(HookTimeoutError, HookError)

    def test_inherits_from_trust_error(self):
        assert issubclass(HookTimeoutError, TrustError)

    def test_is_instance_of_hook_error(self):
        err = HookTimeoutError(hook_name="slow_hook", timeout_seconds=5.0)
        assert isinstance(err, HookError)

    def test_is_instance_of_trust_error(self):
        err = HookTimeoutError(hook_name="slow_hook", timeout_seconds=5.0)
        assert isinstance(err, TrustError)

    def test_message_includes_hook_name_and_timeout(self):
        err = HookTimeoutError(hook_name="slow_hook", timeout_seconds=5.0)
        assert "slow_hook" in err.message
        assert "5.0" in err.message

    def test_details_populated(self):
        err = HookTimeoutError(hook_name="slow_hook", timeout_seconds=5.0)
        assert err.details["hook_name"] == "slow_hook"
        assert err.details["timeout_seconds"] == 5.0

    def test_hook_name_attribute(self):
        err = HookTimeoutError(hook_name="slow_hook", timeout_seconds=5.0)
        assert err.hook_name == "slow_hook"

    def test_timeout_seconds_attribute(self):
        err = HookTimeoutError(hook_name="slow_hook", timeout_seconds=5.0)
        assert err.timeout_seconds == 5.0

    def test_caught_by_hook_error(self):
        with pytest.raises(HookError):
            raise HookTimeoutError(hook_name="slow_hook", timeout_seconds=5.0)

    def test_caught_by_trust_error(self):
        with pytest.raises(TrustError):
            raise HookTimeoutError(hook_name="slow_hook", timeout_seconds=5.0)

    def test_str_representation(self):
        err = HookTimeoutError(hook_name="slow_hook", timeout_seconds=5.0)
        result = str(err)
        assert "slow_hook" in result
        assert "5.0" in result


# ---------------------------------------------------------------------------
# 3. ProximityError
# ---------------------------------------------------------------------------


class TestProximityError:
    """ProximityError is raised for proximity computation failures."""

    def test_inherits_from_trust_error(self):
        assert issubclass(ProximityError, TrustError)

    def test_is_instance_of_trust_error(self):
        err = ProximityError(
            "proximity computation failed",
            details={"agent_id": "agent-001", "dimension": "capability"},
        )
        assert isinstance(err, TrustError)

    def test_message_stored(self):
        err = ProximityError(
            "proximity computation failed",
            details={"agent_id": "agent-001"},
        )
        assert err.message == "proximity computation failed"

    def test_details_populated(self):
        err = ProximityError(
            "proximity computation failed",
            details={"agent_id": "agent-001", "dimension": "capability"},
        )
        assert err.details["agent_id"] == "agent-001"
        assert err.details["dimension"] == "capability"

    def test_details_defaults_to_empty_dict(self):
        err = ProximityError("proximity computation failed")
        assert err.details == {}

    def test_str_with_details(self):
        err = ProximityError(
            "proximity computation failed",
            details={"agent_id": "agent-001"},
        )
        result = str(err)
        assert "proximity computation failed" in result
        assert "agent-001" in result

    def test_caught_by_trust_error(self):
        with pytest.raises(TrustError):
            raise ProximityError("proximity computation failed")

    def test_caught_by_own_type(self):
        with pytest.raises(ProximityError):
            raise ProximityError("proximity computation failed")


# ---------------------------------------------------------------------------
# 4. BehavioralScoringError
# ---------------------------------------------------------------------------


class TestBehavioralScoringError:
    """BehavioralScoringError is raised for scoring computation failures."""

    def test_inherits_from_trust_error(self):
        assert issubclass(BehavioralScoringError, TrustError)

    def test_is_instance_of_trust_error(self):
        err = BehavioralScoringError(
            "scoring failed",
            details={"agent_id": "agent-002", "scorer": "behavioral"},
        )
        assert isinstance(err, TrustError)

    def test_message_stored(self):
        err = BehavioralScoringError(
            "scoring failed",
            details={"agent_id": "agent-002"},
        )
        assert err.message == "scoring failed"

    def test_details_populated(self):
        err = BehavioralScoringError(
            "scoring failed",
            details={"agent_id": "agent-002", "scorer": "behavioral"},
        )
        assert err.details["agent_id"] == "agent-002"
        assert err.details["scorer"] == "behavioral"

    def test_details_defaults_to_empty_dict(self):
        err = BehavioralScoringError("scoring failed")
        assert err.details == {}

    def test_str_with_details(self):
        err = BehavioralScoringError(
            "scoring failed",
            details={"agent_id": "agent-002"},
        )
        result = str(err)
        assert "scoring failed" in result
        assert "agent-002" in result

    def test_caught_by_trust_error(self):
        with pytest.raises(TrustError):
            raise BehavioralScoringError("scoring failed")

    def test_caught_by_own_type(self):
        with pytest.raises(BehavioralScoringError):
            raise BehavioralScoringError("scoring failed")


# ---------------------------------------------------------------------------
# 5. KMSConnectionError
# ---------------------------------------------------------------------------


class TestKMSConnectionError:
    """KMSConnectionError is raised when KMS is unreachable."""

    def test_inherits_from_trust_error(self):
        assert issubclass(KMSConnectionError, TrustError)

    def test_is_instance_of_trust_error(self):
        err = KMSConnectionError(
            "KMS unreachable",
            details={"endpoint": "https://kms.example.com", "reason": "timeout"},
        )
        assert isinstance(err, TrustError)

    def test_message_stored(self):
        err = KMSConnectionError(
            "KMS unreachable",
            details={"endpoint": "https://kms.example.com"},
        )
        assert err.message == "KMS unreachable"

    def test_details_populated(self):
        err = KMSConnectionError(
            "KMS unreachable",
            details={"endpoint": "https://kms.example.com", "reason": "timeout"},
        )
        assert err.details["endpoint"] == "https://kms.example.com"
        assert err.details["reason"] == "timeout"

    def test_details_defaults_to_empty_dict(self):
        err = KMSConnectionError("KMS unreachable")
        assert err.details == {}

    def test_str_with_details(self):
        err = KMSConnectionError(
            "KMS unreachable",
            details={"endpoint": "https://kms.example.com"},
        )
        result = str(err)
        assert "KMS unreachable" in result
        assert "kms.example.com" in result

    def test_caught_by_trust_error(self):
        with pytest.raises(TrustError):
            raise KMSConnectionError("KMS unreachable")

    def test_caught_by_own_type(self):
        with pytest.raises(KMSConnectionError):
            raise KMSConnectionError("KMS unreachable")


# ---------------------------------------------------------------------------
# 6. RevocationError
# ---------------------------------------------------------------------------


class TestRevocationError:
    """RevocationError is raised for revocation failures."""

    def test_inherits_from_trust_error(self):
        assert issubclass(RevocationError, TrustError)

    def test_is_instance_of_trust_error(self):
        err = RevocationError(
            "revocation failed",
            details={"agent_id": "agent-003", "reason": "chain_broken"},
        )
        assert isinstance(err, TrustError)

    def test_message_stored(self):
        err = RevocationError(
            "revocation failed",
            details={"agent_id": "agent-003"},
        )
        assert err.message == "revocation failed"

    def test_details_populated(self):
        err = RevocationError(
            "revocation failed",
            details={"agent_id": "agent-003", "reason": "chain_broken"},
        )
        assert err.details["agent_id"] == "agent-003"
        assert err.details["reason"] == "chain_broken"

    def test_details_defaults_to_empty_dict(self):
        err = RevocationError("revocation failed")
        assert err.details == {}

    def test_str_with_details(self):
        err = RevocationError(
            "revocation failed",
            details={"agent_id": "agent-003"},
        )
        result = str(err)
        assert "revocation failed" in result
        assert "agent-003" in result

    def test_caught_by_trust_error(self):
        with pytest.raises(TrustError):
            raise RevocationError("revocation failed")

    def test_caught_by_own_type(self):
        with pytest.raises(RevocationError):
            raise RevocationError("revocation failed")


# ---------------------------------------------------------------------------
# 7. PathTraversalError
# ---------------------------------------------------------------------------


class TestPathTraversalError:
    """PathTraversalError is raised for invalid IDs that could traverse the filesystem."""

    def test_inherits_from_trust_error(self):
        assert issubclass(PathTraversalError, TrustError)

    def test_is_instance_of_trust_error(self):
        err = PathTraversalError(
            invalid_id="../../../etc/passwd",
            context="agent_id",
        )
        assert isinstance(err, TrustError)

    def test_message_includes_context(self):
        err = PathTraversalError(
            invalid_id="../../../etc/passwd",
            context="agent_id",
        )
        assert "agent_id" in err.message

    def test_details_populated(self):
        err = PathTraversalError(
            invalid_id="../../../etc/passwd",
            context="agent_id",
        )
        assert err.details["invalid_id"] == "../../../etc/passwd"
        assert err.details["context"] == "agent_id"

    def test_invalid_id_attribute(self):
        err = PathTraversalError(
            invalid_id="../../../etc/passwd",
            context="agent_id",
        )
        assert err.invalid_id == "../../../etc/passwd"

    def test_context_attribute(self):
        err = PathTraversalError(
            invalid_id="../../../etc/passwd",
            context="agent_id",
        )
        assert err.context == "agent_id"

    def test_str_representation(self):
        err = PathTraversalError(
            invalid_id="../hack",
            context="delegation_id",
        )
        result = str(err)
        assert "../hack" in result or "delegation_id" in result

    def test_caught_by_trust_error(self):
        with pytest.raises(TrustError):
            raise PathTraversalError(
                invalid_id="../../../etc/passwd",
                context="agent_id",
            )

    def test_caught_by_own_type(self):
        with pytest.raises(PathTraversalError):
            raise PathTraversalError(
                invalid_id="../../../etc/passwd",
                context="agent_id",
            )


# ---------------------------------------------------------------------------
# 8. Cross-cutting: existing exceptions unaffected
# ---------------------------------------------------------------------------


class TestExistingExceptionsUnaffected:
    """Verify that adding new exceptions does not break existing ones."""

    def test_trust_error_still_works(self):
        err = TrustError("base error", details={"key": "value"})
        assert err.message == "base error"
        assert err.details == {"key": "value"}

    def test_trust_error_is_base_of_all_new_exceptions(self):
        new_exceptions = [
            HookError,
            HookTimeoutError,
            ProximityError,
            BehavioralScoringError,
            KMSConnectionError,
            RevocationError,
            PathTraversalError,
        ]
        for exc_class in new_exceptions:
            assert issubclass(
                exc_class, TrustError
            ), f"{exc_class.__name__} must inherit from TrustError"

    def test_hook_timeout_is_subclass_of_hook_error(self):
        """HookTimeoutError -> HookError -> TrustError chain."""
        assert issubclass(HookTimeoutError, HookError)
        assert issubclass(HookTimeoutError, TrustError)
        assert issubclass(HookError, TrustError)


# ---------------------------------------------------------------------------
# 9. __all__ exports
# ---------------------------------------------------------------------------


class TestExceptionsExported:
    """All new exceptions must be listed in exceptions.__all__."""

    def test_all_new_exceptions_in_module_all(self):
        from eatp import exceptions

        expected = [
            "HookError",
            "HookTimeoutError",
            "ProximityError",
            "BehavioralScoringError",
            "KMSConnectionError",
            "RevocationError",
            "PathTraversalError",
        ]
        for name in expected:
            assert name in exceptions.__all__, f"{name} must be in exceptions.__all__"
