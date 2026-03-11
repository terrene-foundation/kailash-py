"""
Unit tests for EATP (Enterprise Agent Trust Protocol) v0.8.0 components.

Tests cover:
- HumanOrigin: Immutable human identity record
- ExecutionContext: Context propagation with human traceability
- PseudoAgent: Human facade for trust chain initiation
- ConstraintValidator: Constraint tightening validation
- Context variable functions: Async-safe context propagation

Note: These are unit tests using appropriate mocking.
Integration tests with real infrastructure are in tests/integration/trust/

Author: Kaizen Framework Team
Created: 2026-01-02
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.trust.constraint_validator import (
    ConstraintValidator,
    ConstraintViolation,
    DelegationConstraintValidator,
    ValidationResult,
)
from kaizen.trust.execution_context import (
    ExecutionContext,
    HumanOrigin,
    execution_context,
    get_current_context,
    get_delegation_chain,
    get_human_origin,
    get_trace_id,
    require_current_context,
    set_current_context,
)
from kaizen.trust.pseudo_agent import (
    AuthProvider,
    PseudoAgent,
    PseudoAgentConfig,
    PseudoAgentFactory,
    create_pseudo_agent_for_testing,
)

# =============================================================================
# HumanOrigin Tests
# =============================================================================


class TestHumanOrigin:
    """Tests for HumanOrigin dataclass."""

    def test_human_origin_creation(self):
        """Test creating a HumanOrigin instance."""
        now = datetime.now(timezone.utc)
        origin = HumanOrigin(
            human_id="alice@corp.com",
            display_name="Alice Chen",
            auth_provider="okta",
            session_id="sess-123",
            authenticated_at=now,
        )

        assert origin.human_id == "alice@corp.com"
        assert origin.display_name == "Alice Chen"
        assert origin.auth_provider == "okta"
        assert origin.session_id == "sess-123"
        assert origin.authenticated_at == now

    def test_human_origin_immutable(self):
        """Test that HumanOrigin is immutable (frozen=True)."""
        origin = HumanOrigin(
            human_id="alice@corp.com",
            display_name="Alice Chen",
            auth_provider="okta",
            session_id="sess-123",
            authenticated_at=datetime.now(timezone.utc),
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            origin.human_id = "bob@corp.com"

    def test_human_origin_to_dict(self):
        """Test serialization to dictionary."""
        now = datetime.now(timezone.utc)
        origin = HumanOrigin(
            human_id="alice@corp.com",
            display_name="Alice Chen",
            auth_provider="okta",
            session_id="sess-123",
            authenticated_at=now,
        )

        d = origin.to_dict()
        assert d["human_id"] == "alice@corp.com"
        assert d["display_name"] == "Alice Chen"
        assert d["auth_provider"] == "okta"
        assert d["session_id"] == "sess-123"
        assert d["authenticated_at"] == now.isoformat()

    def test_human_origin_from_dict(self):
        """Test deserialization from dictionary."""
        now = datetime.now(timezone.utc)
        d = {
            "human_id": "alice@corp.com",
            "display_name": "Alice Chen",
            "auth_provider": "okta",
            "session_id": "sess-123",
            "authenticated_at": now.isoformat(),
        }

        origin = HumanOrigin.from_dict(d)
        assert origin.human_id == "alice@corp.com"
        assert origin.display_name == "Alice Chen"

    def test_human_origin_str(self):
        """Test string representation."""
        origin = HumanOrigin(
            human_id="alice@corp.com",
            display_name="Alice Chen",
            auth_provider="okta",
            session_id="sess-123",
            authenticated_at=datetime.now(timezone.utc),
        )

        s = str(origin)
        assert "alice@corp.com" in s
        assert "okta" in s


# =============================================================================
# ExecutionContext Tests
# =============================================================================


class TestExecutionContext:
    """Tests for ExecutionContext dataclass."""

    @pytest.fixture
    def sample_origin(self):
        """Create a sample HumanOrigin for tests."""
        return HumanOrigin(
            human_id="alice@corp.com",
            display_name="Alice Chen",
            auth_provider="okta",
            session_id="sess-123",
            authenticated_at=datetime.now(timezone.utc),
        )

    def test_execution_context_creation(self, sample_origin):
        """Test creating an ExecutionContext."""
        ctx = ExecutionContext(
            human_origin=sample_origin,
            delegation_chain=["pseudo:alice@corp.com"],
            delegation_depth=0,
            constraints={"cost_limit": 10000},
        )

        assert ctx.human_origin is sample_origin
        assert ctx.delegation_chain == ["pseudo:alice@corp.com"]
        assert ctx.delegation_depth == 0
        assert ctx.constraints == {"cost_limit": 10000}
        assert ctx.trace_id  # Should be auto-generated

    def test_execution_context_with_delegation(self, sample_origin):
        """Test creating child context via with_delegation."""
        parent_ctx = ExecutionContext(
            human_origin=sample_origin,
            delegation_chain=["pseudo:alice@corp.com"],
            delegation_depth=0,
            constraints={"cost_limit": 10000},
        )

        child_ctx = parent_ctx.with_delegation("worker-agent", {"cost_limit": 1000})

        # Human origin MUST be preserved (same reference)
        assert child_ctx.human_origin is sample_origin
        # Chain should include new agent
        assert child_ctx.delegation_chain == ["pseudo:alice@corp.com", "worker-agent"]
        # Depth should increase
        assert child_ctx.delegation_depth == 1
        # Constraints should be merged
        assert child_ctx.constraints["cost_limit"] == 1000
        # Trace ID should be preserved
        assert child_ctx.trace_id == parent_ctx.trace_id

    def test_execution_context_to_dict(self, sample_origin):
        """Test serialization to dictionary."""
        ctx = ExecutionContext(
            human_origin=sample_origin,
            delegation_chain=["pseudo:alice@corp.com"],
            delegation_depth=0,
            constraints={"cost_limit": 10000},
        )

        d = ctx.to_dict()
        assert d["human_origin"]["human_id"] == "alice@corp.com"
        assert d["delegation_chain"] == ["pseudo:alice@corp.com"]
        assert d["delegation_depth"] == 0

    def test_execution_context_from_dict(self, sample_origin):
        """Test deserialization from dictionary."""
        d = {
            "human_origin": sample_origin.to_dict(),
            "delegation_chain": ["pseudo:alice@corp.com"],
            "delegation_depth": 0,
            "constraints": {"cost_limit": 10000},
            "trace_id": "trace-123",
        }

        ctx = ExecutionContext.from_dict(d)
        assert ctx.human_origin.human_id == "alice@corp.com"
        assert ctx.trace_id == "trace-123"


# =============================================================================
# Context Variable Tests
# =============================================================================


class TestContextVariables:
    """Tests for context variable functions."""

    @pytest.fixture
    def sample_context(self):
        """Create a sample ExecutionContext for tests."""
        origin = HumanOrigin(
            human_id="alice@corp.com",
            display_name="Alice Chen",
            auth_provider="okta",
            session_id="sess-123",
            authenticated_at=datetime.now(timezone.utc),
        )
        return ExecutionContext(
            human_origin=origin,
            delegation_chain=["pseudo:alice@corp.com"],
            delegation_depth=0,
        )

    def test_get_current_context_when_none(self):
        """Test get_current_context returns None when not set in fresh context."""
        from contextvars import copy_context

        def check_in_clean_context():
            # In a fresh context, there should be no ExecutionContext
            result = get_current_context()
            assert result is None, "Expected None in fresh context"

        # Run in a copy_context to isolate from any previously set context
        ctx = copy_context()
        ctx.run(check_in_clean_context)

    def test_execution_context_manager(self, sample_context):
        """Test execution_context context manager."""
        from contextvars import copy_context

        def check_context_manager():
            # Verify context is None before setting
            assert get_current_context() is None

            with execution_context(sample_context):
                current = get_current_context()
                assert current is sample_context

            # After exiting, context should be reset to None
            assert get_current_context() is None

        # Run in isolated context
        ctx = copy_context()
        ctx.run(check_context_manager)

    def test_require_current_context_raises_when_none(self):
        """Test require_current_context raises RuntimeError when no context."""
        from contextvars import copy_context

        def check_raises_in_clean_context():
            # In a fresh context with no ExecutionContext set,
            # require_current_context should raise RuntimeError
            with pytest.raises(RuntimeError, match="No ExecutionContext"):
                require_current_context()

        # Run in a copy_context to isolate from any previously set context
        ctx = copy_context()
        ctx.run(check_raises_in_clean_context)

    def test_get_human_origin(self, sample_context):
        """Test get_human_origin convenience function."""
        with execution_context(sample_context):
            origin = get_human_origin()
            assert origin.human_id == "alice@corp.com"

    def test_get_delegation_chain(self, sample_context):
        """Test get_delegation_chain convenience function."""
        with execution_context(sample_context):
            chain = get_delegation_chain()
            assert chain == ["pseudo:alice@corp.com"]

    def test_get_trace_id(self, sample_context):
        """Test get_trace_id convenience function."""
        with execution_context(sample_context):
            trace_id = get_trace_id()
            assert trace_id == sample_context.trace_id


# =============================================================================
# ConstraintValidator Tests
# =============================================================================


class TestConstraintValidator:
    """Tests for ConstraintValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a ConstraintValidator instance."""
        return ConstraintValidator()

    def test_valid_tightening_cost_limit(self, validator):
        """Test valid constraint tightening for cost_limit."""
        parent = {"cost_limit": 10000}
        child = {"cost_limit": 1000}  # Tighter

        result = validator.validate_tightening(parent, child)
        assert result.valid is True
        assert len(result.violations) == 0

    def test_invalid_loosening_cost_limit(self, validator):
        """Test invalid constraint loosening for cost_limit."""
        parent = {"cost_limit": 1000}
        child = {"cost_limit": 10000}  # Loosened!

        result = validator.validate_tightening(parent, child)
        assert result.valid is False
        assert ConstraintViolation.COST_LOOSENED in result.violations
        assert "cost_limit" in result.details

    def test_valid_tightening_rate_limit(self, validator):
        """Test valid constraint tightening for rate_limit."""
        parent = {"rate_limit": 100}
        child = {"rate_limit": 50}  # Tighter

        result = validator.validate_tightening(parent, child)
        assert result.valid is True

    def test_invalid_loosening_rate_limit(self, validator):
        """Test invalid constraint loosening for rate_limit."""
        parent = {"rate_limit": 50}
        child = {"rate_limit": 100}  # Loosened!

        result = validator.validate_tightening(parent, child)
        assert result.valid is False
        assert ConstraintViolation.RATE_LIMIT_INCREASED in result.violations

    def test_valid_tightening_time_window(self, validator):
        """Test valid constraint tightening for time_window."""
        parent = {"time_window": "09:00-17:00"}
        child = {"time_window": "10:00-16:00"}  # Subset

        result = validator.validate_tightening(parent, child)
        assert result.valid is True

    def test_invalid_expansion_time_window(self, validator):
        """Test invalid time_window expansion."""
        parent = {"time_window": "10:00-16:00"}
        child = {"time_window": "09:00-17:00"}  # Expanded!

        result = validator.validate_tightening(parent, child)
        assert result.valid is False
        assert ConstraintViolation.TIME_WINDOW_EXPANDED in result.violations

    def test_valid_tightening_resources(self, validator):
        """Test valid constraint tightening for resources."""
        parent = {"resources": ["invoices/**"]}
        child = {"resources": ["invoices/small/*"]}  # Subset

        result = validator.validate_tightening(parent, child)
        assert result.valid is True

    def test_valid_geo_restrictions_subset(self, validator):
        """Test valid geo_restrictions subset."""
        parent = {"geo_restrictions": ["US", "CA", "MX"]}
        child = {"geo_restrictions": ["US", "CA"]}  # Subset

        result = validator.validate_tightening(parent, child)
        assert result.valid is True

    def test_invalid_geo_restrictions_expansion(self, validator):
        """Test invalid geo_restrictions expansion."""
        parent = {"geo_restrictions": ["US", "CA"]}
        child = {"geo_restrictions": ["US", "CA", "MX"]}  # Expanded!

        result = validator.validate_tightening(parent, child)
        assert result.valid is False
        assert ConstraintViolation.GEO_RESTRICTION_REMOVED in result.violations

    def test_multiple_violations(self, validator):
        """Test detecting multiple violations at once."""
        parent = {
            "cost_limit": 1000,
            "rate_limit": 50,
        }
        child = {
            "cost_limit": 5000,  # Loosened
            "rate_limit": 100,  # Loosened
        }

        result = validator.validate_tightening(parent, child)
        assert result.valid is False
        assert len(result.violations) == 2

    def test_validation_result_bool(self, validator):
        """Test ValidationResult can be used in boolean context."""
        parent = {"cost_limit": 10000}
        child = {"cost_limit": 1000}

        result = validator.validate_tightening(parent, child)
        assert bool(result) is True

        result = validator.validate_tightening(child, parent)
        assert bool(result) is False


class TestDelegationConstraintValidator:
    """Tests for DelegationConstraintValidator class."""

    def test_validate_delegation(self):
        """Test validate_delegation convenience method."""
        validator = DelegationConstraintValidator()

        delegator_constraints = {"cost_limit": 10000}
        delegatee_constraints = {"cost_limit": 1000}

        result = validator.validate_delegation(
            delegator_constraints, delegatee_constraints
        )
        assert result.valid is True

    def test_can_delegate(self):
        """Test can_delegate quick check."""
        validator = DelegationConstraintValidator()

        assert (
            validator.can_delegate({"cost_limit": 10000}, {"cost_limit": 1000}) is True
        )

        assert (
            validator.can_delegate({"cost_limit": 1000}, {"cost_limit": 10000}) is False
        )

    def test_get_max_allowed_constraints(self):
        """Test get_max_allowed_constraints returns copy."""
        validator = DelegationConstraintValidator()
        delegator_constraints = {"cost_limit": 10000, "rate_limit": 100}

        max_allowed = validator.get_max_allowed_constraints(delegator_constraints)
        assert max_allowed == delegator_constraints
        # Should be a copy, not the same object
        assert max_allowed is not delegator_constraints


# =============================================================================
# PseudoAgent Tests
# =============================================================================


class TestPseudoAgent:
    """Tests for PseudoAgent class."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create a mock TrustOperations instance."""
        mock = MagicMock()
        mock.delegate = AsyncMock()
        mock.revoke_delegation = AsyncMock()
        return mock

    @pytest.fixture
    def sample_origin(self):
        """Create a sample HumanOrigin for tests."""
        return HumanOrigin(
            human_id="alice@corp.com",
            display_name="Alice Chen",
            auth_provider="okta",
            session_id="sess-123",
            authenticated_at=datetime.now(timezone.utc),
        )

    def test_pseudo_agent_creation(self, sample_origin, mock_trust_ops):
        """Test creating a PseudoAgent."""
        pseudo = PseudoAgent(
            human_origin=sample_origin,
            trust_operations=mock_trust_ops,
        )

        assert pseudo.agent_id == "pseudo:alice@corp.com"
        assert pseudo.human_origin is sample_origin
        assert pseudo.session_id == "sess-123"

    def test_pseudo_agent_create_execution_context(self, sample_origin, mock_trust_ops):
        """Test creating ExecutionContext from PseudoAgent."""
        pseudo = PseudoAgent(
            human_origin=sample_origin,
            trust_operations=mock_trust_ops,
        )

        ctx = pseudo.create_execution_context(initial_constraints={"cost_limit": 10000})

        assert ctx.human_origin is sample_origin
        assert ctx.delegation_chain == ["pseudo:alice@corp.com"]
        assert ctx.delegation_depth == 0
        assert ctx.constraints["cost_limit"] == 10000

    def test_pseudo_agent_session_valid(self, sample_origin, mock_trust_ops):
        """Test session validity check."""
        pseudo = PseudoAgent(
            human_origin=sample_origin,
            trust_operations=mock_trust_ops,
        )

        # No timeout configured = always valid
        assert pseudo.is_session_valid is True

    def test_pseudo_agent_session_expired(self, mock_trust_ops):
        """Test expired session detection."""
        old_origin = HumanOrigin(
            human_id="alice@corp.com",
            display_name="Alice Chen",
            auth_provider="okta",
            session_id="sess-123",
            authenticated_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )

        config = PseudoAgentConfig(session_timeout_minutes=60)
        pseudo = PseudoAgent(
            human_origin=old_origin,
            trust_operations=mock_trust_ops,
            config=config,
        )

        assert pseudo.is_session_valid is False

    @pytest.mark.asyncio
    async def test_pseudo_agent_delegate_to(self, sample_origin, mock_trust_ops):
        """Test delegating trust to an agent."""
        # Configure mock to return a delegation record
        mock_delegation = MagicMock()
        mock_delegation.id = "del-123"
        mock_trust_ops.delegate.return_value = mock_delegation

        pseudo = PseudoAgent(
            human_origin=sample_origin,
            trust_operations=mock_trust_ops,
        )

        delegation, ctx = await pseudo.delegate_to(
            agent_id="invoice-processor",
            task_id="november-invoices",
            capabilities=["read_invoices", "process_invoices"],
            constraints={"cost_limit": 1000},
        )

        # Check delegation was made
        assert mock_trust_ops.delegate.called
        # Check returned context
        assert ctx.human_origin is sample_origin
        assert "invoice-processor" in ctx.delegation_chain

    @pytest.mark.asyncio
    async def test_pseudo_agent_delegate_to_expired_session(self, mock_trust_ops):
        """Test delegation fails with expired session."""
        old_origin = HumanOrigin(
            human_id="alice@corp.com",
            display_name="Alice Chen",
            auth_provider="okta",
            session_id="sess-123",
            authenticated_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )

        config = PseudoAgentConfig(session_timeout_minutes=60)
        pseudo = PseudoAgent(
            human_origin=old_origin,
            trust_operations=mock_trust_ops,
            config=config,
        )

        with pytest.raises(ValueError, match="Session expired"):
            await pseudo.delegate_to(
                agent_id="worker",
                task_id="task-1",
                capabilities=["read"],
            )


class TestPseudoAgentFactory:
    """Tests for PseudoAgentFactory class."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create a mock TrustOperations instance."""
        return MagicMock()

    def test_factory_from_session(self, mock_trust_ops):
        """Test creating PseudoAgent from session data."""
        factory = PseudoAgentFactory(mock_trust_ops)

        pseudo = factory.from_session(
            user_id="user-123",
            email="alice@corp.com",
            display_name="Alice Chen",
            session_id="sess-456",
            auth_provider="okta",
        )

        assert pseudo.agent_id == "pseudo:alice@corp.com"
        assert pseudo.human_origin.display_name == "Alice Chen"

    def test_factory_from_claims(self, mock_trust_ops):
        """Test creating PseudoAgent from JWT claims."""
        factory = PseudoAgentFactory(mock_trust_ops)

        claims = {
            "sub": "user-123",
            "email": "alice@corp.com",
            "name": "Alice Chen",
            "jti": "jwt-789",
        }

        pseudo = factory.from_claims(claims, auth_provider="azure_ad")

        assert pseudo.agent_id == "pseudo:alice@corp.com"
        assert pseudo.human_origin.auth_provider == "azure_ad"

    def test_factory_from_claims_minimal(self, mock_trust_ops):
        """Test creating PseudoAgent from minimal claims."""
        factory = PseudoAgentFactory(mock_trust_ops)

        claims = {"sub": "user-123"}

        pseudo = factory.from_claims(claims, auth_provider="custom")

        assert pseudo.agent_id == "pseudo:user-123"

    def test_factory_from_claims_missing_id(self, mock_trust_ops):
        """Test error when claims lack user identifier."""
        factory = PseudoAgentFactory(mock_trust_ops)

        with pytest.raises(ValueError, match="email.*sub.*user_id"):
            factory.from_claims({}, auth_provider="custom")

    def test_factory_from_http_request(self, mock_trust_ops):
        """Test creating PseudoAgent from HTTP headers."""
        factory = PseudoAgentFactory(mock_trust_ops)

        headers = {
            "X-User-Id": "user-123",
            "X-User-Email": "alice@corp.com",
            "X-User-Name": "Alice Chen",
            "X-Session-Id": "sess-456",
        }

        pseudo = factory.from_http_request(headers)

        assert pseudo.agent_id == "pseudo:alice@corp.com"

    def test_factory_from_http_request_missing_email(self, mock_trust_ops):
        """Test error when email header is missing."""
        factory = PseudoAgentFactory(mock_trust_ops)

        with pytest.raises(ValueError, match="X-User-Email"):
            factory.from_http_request({})


class TestCreatePseudoAgentForTesting:
    """Tests for create_pseudo_agent_for_testing helper."""

    def test_requires_trust_ops(self):
        """Test that trust_ops is required."""
        with pytest.raises(ValueError, match="trust_ops is required"):
            create_pseudo_agent_for_testing()

    def test_creates_test_pseudo_agent(self):
        """Test creating a test PseudoAgent."""
        mock_trust_ops = MagicMock()

        pseudo = create_pseudo_agent_for_testing(
            human_id="test@example.com",
            display_name="Test User",
            trust_ops=mock_trust_ops,
        )

        assert pseudo.agent_id == "pseudo:test@example.com"
        assert pseudo.human_origin.auth_provider == "session"


# =============================================================================
# AuthProvider Enum Tests
# =============================================================================


class TestAuthProvider:
    """Tests for AuthProvider enum."""

    def test_auth_provider_values(self):
        """Test AuthProvider has expected values."""
        assert AuthProvider.OKTA.value == "okta"
        assert AuthProvider.AZURE_AD.value == "azure_ad"
        assert AuthProvider.GOOGLE.value == "google"
        assert AuthProvider.SAML.value == "saml"
        assert AuthProvider.OIDC.value == "oidc"
        assert AuthProvider.LDAP.value == "ldap"
        assert AuthProvider.SESSION.value == "session"
        assert AuthProvider.CUSTOM.value == "custom"
