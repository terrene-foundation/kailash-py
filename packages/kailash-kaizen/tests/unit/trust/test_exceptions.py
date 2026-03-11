"""
Unit tests for EATP exception hierarchy.

Tests cover:
- Base TrustError
- All specialized exception types
- Exception message formatting
- Exception details/attributes
"""

import pytest
from kaizen.trust.exceptions import (
    AgentAlreadyEstablishedError,
    AuthorityInactiveError,
    AuthorityNotFoundError,
    CapabilityNotFoundError,
    ConstraintViolationError,
    DelegationError,
    DelegationExpiredError,
    InvalidSignatureError,
    InvalidTrustChainError,
    TrustChainNotFoundError,
    TrustError,
    VerificationFailedError,
)


class TestTrustError:
    """Tests for base TrustError exception."""

    def test_trust_error_message(self):
        """TrustError stores message."""
        error = TrustError("Test error message")
        assert error.message == "Test error message"
        assert str(error) == "Test error message"

    def test_trust_error_with_details(self):
        """TrustError stores and displays details."""
        error = TrustError("Error", details={"key": "value"})
        assert error.details == {"key": "value"}
        assert "key" in str(error)

    def test_trust_error_is_exception(self):
        """TrustError is an Exception."""
        error = TrustError("Test")
        assert isinstance(error, Exception)

    def test_trust_error_can_be_raised(self):
        """TrustError can be raised and caught."""
        with pytest.raises(TrustError) as exc_info:
            raise TrustError("Test error")
        assert exc_info.value.message == "Test error"


class TestAuthorityNotFoundError:
    """Tests for AuthorityNotFoundError."""

    def test_authority_not_found_message(self):
        """AuthorityNotFoundError formats message correctly."""
        error = AuthorityNotFoundError("auth-001")
        assert "auth-001" in str(error)
        assert "not found" in str(error).lower()

    def test_authority_not_found_stores_id(self):
        """AuthorityNotFoundError stores authority_id."""
        error = AuthorityNotFoundError("auth-001")
        assert error.authority_id == "auth-001"

    def test_authority_not_found_is_trust_error(self):
        """AuthorityNotFoundError inherits from TrustError."""
        error = AuthorityNotFoundError("auth-001")
        assert isinstance(error, TrustError)


class TestAuthorityInactiveError:
    """Tests for AuthorityInactiveError."""

    def test_authority_inactive_message(self):
        """AuthorityInactiveError formats message correctly."""
        error = AuthorityInactiveError("auth-001")
        assert "auth-001" in str(error)
        assert "inactive" in str(error).lower()

    def test_authority_inactive_with_reason(self):
        """AuthorityInactiveError includes reason in message."""
        error = AuthorityInactiveError("auth-001", reason="expired")
        assert "expired" in str(error)

    def test_authority_inactive_stores_attributes(self):
        """AuthorityInactiveError stores authority_id and reason."""
        error = AuthorityInactiveError("auth-001", reason="suspended")
        assert error.authority_id == "auth-001"
        assert error.reason == "suspended"


class TestTrustChainNotFoundError:
    """Tests for TrustChainNotFoundError."""

    def test_trust_chain_not_found_message(self):
        """TrustChainNotFoundError formats message correctly."""
        error = TrustChainNotFoundError("agent-001")
        assert "agent-001" in str(error)
        assert "trust chain" in str(error).lower()

    def test_trust_chain_not_found_stores_id(self):
        """TrustChainNotFoundError stores agent_id."""
        error = TrustChainNotFoundError("agent-001")
        assert error.agent_id == "agent-001"


class TestInvalidTrustChainError:
    """Tests for InvalidTrustChainError."""

    def test_invalid_trust_chain_message(self):
        """InvalidTrustChainError formats message correctly."""
        error = InvalidTrustChainError("agent-001", "signature invalid")
        assert "agent-001" in str(error)
        assert "signature invalid" in str(error)

    def test_invalid_trust_chain_with_violations(self):
        """InvalidTrustChainError stores violations list."""
        violations = ["expired genesis", "invalid capability"]
        error = InvalidTrustChainError("agent-001", "multiple issues", violations)
        assert error.violations == violations

    def test_invalid_trust_chain_stores_attributes(self):
        """InvalidTrustChainError stores all attributes."""
        error = InvalidTrustChainError("agent-001", "test reason", ["v1", "v2"])
        assert error.agent_id == "agent-001"
        assert error.reason == "test reason"
        assert len(error.violations) == 2


class TestCapabilityNotFoundError:
    """Tests for CapabilityNotFoundError."""

    def test_capability_not_found_message(self):
        """CapabilityNotFoundError formats message correctly."""
        error = CapabilityNotFoundError("agent-001", "analyze_data")
        assert "agent-001" in str(error)
        assert "analyze_data" in str(error)

    def test_capability_not_found_stores_attributes(self):
        """CapabilityNotFoundError stores agent_id and capability."""
        error = CapabilityNotFoundError("agent-001", "analyze_data")
        assert error.agent_id == "agent-001"
        assert error.capability == "analyze_data"


class TestConstraintViolationError:
    """Tests for ConstraintViolationError."""

    def test_constraint_violation_message(self):
        """ConstraintViolationError formats message correctly."""
        error = ConstraintViolationError("Action not permitted")
        assert "Action not permitted" in str(error)

    def test_constraint_violation_with_violations(self):
        """ConstraintViolationError stores violations list."""
        violations = [
            {"constraint_id": "c1", "reason": "time window violation"},
            {"constraint_id": "c2", "reason": "resource limit exceeded"},
        ]
        error = ConstraintViolationError("Multiple violations", violations=violations)
        assert len(error.violations) == 2

    def test_constraint_violation_stores_context(self):
        """ConstraintViolationError stores agent_id and action."""
        error = ConstraintViolationError(
            "Test", agent_id="agent-001", action="delete_data"
        )
        assert error.agent_id == "agent-001"
        assert error.action == "delete_data"


class TestDelegationError:
    """Tests for DelegationError."""

    def test_delegation_error_message(self):
        """DelegationError formats message correctly."""
        error = DelegationError("Delegation failed")
        assert "Delegation failed" in str(error)

    def test_delegation_error_stores_ids(self):
        """DelegationError stores delegator and delegatee IDs."""
        error = DelegationError(
            "Cannot delegate",
            delegator_id="super-001",
            delegatee_id="worker-001",
            reason="capability mismatch",
        )
        assert error.delegator_id == "super-001"
        assert error.delegatee_id == "worker-001"
        assert error.reason == "capability mismatch"


class TestInvalidSignatureError:
    """Tests for InvalidSignatureError."""

    def test_invalid_signature_default_message(self):
        """InvalidSignatureError has default message."""
        error = InvalidSignatureError()
        assert "invalid signature" in str(error).lower()

    def test_invalid_signature_custom_message(self):
        """InvalidSignatureError accepts custom message."""
        error = InvalidSignatureError("Genesis signature tampered")
        assert "Genesis signature tampered" in str(error)

    def test_invalid_signature_stores_record_info(self):
        """InvalidSignatureError stores record type and ID."""
        error = InvalidSignatureError(
            "Bad signature", record_type="genesis", record_id="gen-001"
        )
        assert error.record_type == "genesis"
        assert error.record_id == "gen-001"


class TestVerificationFailedError:
    """Tests for VerificationFailedError."""

    def test_verification_failed_message(self):
        """VerificationFailedError formats message correctly."""
        error = VerificationFailedError(
            agent_id="agent-001", action="delete_data", reason="no capability"
        )
        assert "agent-001" in str(error)
        assert "delete_data" in str(error)
        assert "no capability" in str(error)

    def test_verification_failed_with_violations(self):
        """VerificationFailedError stores violations."""
        violations = [{"constraint_id": "c1", "reason": "time violation"}]
        error = VerificationFailedError(
            agent_id="agent-001",
            action="test",
            reason="constraint violation",
            violations=violations,
        )
        assert len(error.violations) == 1

    def test_verification_failed_stores_attributes(self):
        """VerificationFailedError stores all attributes."""
        error = VerificationFailedError(
            agent_id="agent-001", action="analyze", reason="expired"
        )
        assert error.agent_id == "agent-001"
        assert error.action == "analyze"
        assert error.reason == "expired"


class TestDelegationExpiredError:
    """Tests for DelegationExpiredError."""

    def test_delegation_expired_message(self):
        """DelegationExpiredError formats message correctly."""
        error = DelegationExpiredError("del-001", "2025-12-15T18:00:00")
        assert "del-001" in str(error)
        assert "expired" in str(error).lower()

    def test_delegation_expired_stores_attributes(self):
        """DelegationExpiredError stores delegation_id and expired_at."""
        error = DelegationExpiredError("del-001", "2025-12-15T18:00:00")
        assert error.delegation_id == "del-001"
        assert error.expired_at == "2025-12-15T18:00:00"

    def test_delegation_expired_is_delegation_error(self):
        """DelegationExpiredError inherits from DelegationError."""
        error = DelegationExpiredError("del-001", "2025-12-15")
        assert isinstance(error, DelegationError)


class TestAgentAlreadyEstablishedError:
    """Tests for AgentAlreadyEstablishedError."""

    def test_agent_already_established_message(self):
        """AgentAlreadyEstablishedError formats message correctly."""
        error = AgentAlreadyEstablishedError("agent-001")
        assert "agent-001" in str(error)
        assert "already" in str(error).lower()

    def test_agent_already_established_stores_id(self):
        """AgentAlreadyEstablishedError stores agent_id."""
        error = AgentAlreadyEstablishedError("agent-001")
        assert error.agent_id == "agent-001"


class TestExceptionHierarchy:
    """Tests for exception inheritance hierarchy."""

    def test_all_exceptions_inherit_from_trust_error(self):
        """All trust exceptions inherit from TrustError."""
        exceptions = [
            AuthorityNotFoundError("test"),
            AuthorityInactiveError("test"),
            TrustChainNotFoundError("test"),
            InvalidTrustChainError("test", "reason"),
            CapabilityNotFoundError("test", "cap"),
            ConstraintViolationError("test"),
            DelegationError("test"),
            InvalidSignatureError(),
            VerificationFailedError("test", "action", "reason"),
            DelegationExpiredError("test", "date"),
            AgentAlreadyEstablishedError("test"),
        ]

        for exc in exceptions:
            assert isinstance(
                exc, TrustError
            ), f"{type(exc).__name__} should inherit from TrustError"

    def test_exceptions_can_be_caught_by_base(self):
        """All trust exceptions can be caught by TrustError."""
        with pytest.raises(TrustError):
            raise AuthorityNotFoundError("test")

        with pytest.raises(TrustError):
            raise ConstraintViolationError("test")

        with pytest.raises(TrustError):
            raise VerificationFailedError("agent", "action", "reason")
