# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for ExecutionContext.with_delegation() constraint tightening (F-02).

Verifies:
- Numeric constraints (int/float): child value must be <= parent value
- List constraints: child must be a subset of parent
- String constraints: child must equal parent
- New keys not in parent: allowed (adding constraints is always tightening)
- ConstraintViolationError raised when child tries to loosen any constraint
- Backward compatibility: existing callers with tighter constraints still work
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from eatp.exceptions import ConstraintViolationError
from eatp.execution_context import ExecutionContext, HumanOrigin


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def origin():
    """Create a HumanOrigin for testing."""
    return HumanOrigin(
        human_id="alice@corp.com",
        display_name="Alice Chen",
        auth_provider="okta",
        session_id="sess-123",
        authenticated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def parent_ctx(origin):
    """Create a parent ExecutionContext with various constraint types."""
    return ExecutionContext(
        human_origin=origin,
        delegation_chain=["pseudo:alice@corp.com"],
        delegation_depth=0,
        constraints={
            "cost_limit": 10000,
            "max_retries": 5,
            "timeout_seconds": 60.0,
            "allowed_actions": ["read", "write", "delete"],
            "allowed_regions": ["us-east", "us-west", "eu-west"],
            "environment": "production",
            "data_classification": "confidential",
        },
    )


# ---------------------------------------------------------------------------
# 1 -- Numeric constraints: tightening allowed
# ---------------------------------------------------------------------------


class TestNumericConstraintTightening:
    """F-02: Numeric constraints must only allow tighter (<=) values."""

    def test_tighter_int_allowed(self, parent_ctx):
        """Child with lower int value (tighter) must be allowed."""
        child = parent_ctx.with_delegation("worker-1", {"cost_limit": 5000, "max_retries": 3})
        assert child.constraints["cost_limit"] == 5000
        assert child.constraints["max_retries"] == 3

    def test_equal_int_allowed(self, parent_ctx):
        """Child with equal int value must be allowed (not loosening)."""
        child = parent_ctx.with_delegation("worker-1", {"cost_limit": 10000, "max_retries": 5})
        assert child.constraints["cost_limit"] == 10000
        assert child.constraints["max_retries"] == 5

    def test_tighter_float_allowed(self, parent_ctx):
        """Child with lower float value (tighter) must be allowed."""
        child = parent_ctx.with_delegation("worker-1", {"timeout_seconds": 30.0})
        assert child.constraints["timeout_seconds"] == 30.0

    def test_equal_float_allowed(self, parent_ctx):
        """Child with equal float value must be allowed."""
        child = parent_ctx.with_delegation("worker-1", {"timeout_seconds": 60.0})
        assert child.constraints["timeout_seconds"] == 60.0

    def test_looser_int_raises(self, parent_ctx):
        """Child with higher int value (looser) must raise ConstraintViolationError."""
        with pytest.raises(ConstraintViolationError) as exc_info:
            parent_ctx.with_delegation("worker-1", {"cost_limit": 20000})
        assert "cost_limit" in str(exc_info.value)

    def test_looser_float_raises(self, parent_ctx):
        """Child with higher float value (looser) must raise ConstraintViolationError."""
        with pytest.raises(ConstraintViolationError) as exc_info:
            parent_ctx.with_delegation("worker-1", {"timeout_seconds": 120.0})
        assert "timeout_seconds" in str(exc_info.value)

    def test_looser_max_retries_raises(self, parent_ctx):
        """Increasing max_retries beyond parent must raise ConstraintViolationError."""
        with pytest.raises(ConstraintViolationError):
            parent_ctx.with_delegation("worker-1", {"max_retries": 10})

    def test_zero_numeric_allowed(self, parent_ctx):
        """Setting numeric constraint to 0 (most restrictive) must be allowed."""
        child = parent_ctx.with_delegation("worker-1", {"cost_limit": 0})
        assert child.constraints["cost_limit"] == 0


# ---------------------------------------------------------------------------
# 2 -- List constraints: subset tightening
# ---------------------------------------------------------------------------


class TestListConstraintTightening:
    """F-02: List constraints must only allow subsets of parent."""

    def test_subset_allowed(self, parent_ctx):
        """Child with subset of parent's list must be allowed."""
        child = parent_ctx.with_delegation("worker-1", {"allowed_actions": ["read", "write"]})
        assert child.constraints["allowed_actions"] == ["read", "write"]

    def test_proper_subset_allowed(self, parent_ctx):
        """Child with proper subset (fewer items) must be allowed."""
        child = parent_ctx.with_delegation("worker-1", {"allowed_actions": ["read"]})
        assert child.constraints["allowed_actions"] == ["read"]

    def test_equal_list_allowed(self, parent_ctx):
        """Child with same list must be allowed (not loosening)."""
        child = parent_ctx.with_delegation("worker-1", {"allowed_actions": ["read", "write", "delete"]})
        assert set(child.constraints["allowed_actions"]) == {
            "read",
            "write",
            "delete",
        }

    def test_empty_list_allowed(self, parent_ctx):
        """Child with empty list (most restrictive) must be allowed."""
        child = parent_ctx.with_delegation("worker-1", {"allowed_actions": []})
        assert child.constraints["allowed_actions"] == []

    def test_superset_raises(self, parent_ctx):
        """Child with superset of parent's list must raise ConstraintViolationError."""
        with pytest.raises(ConstraintViolationError) as exc_info:
            parent_ctx.with_delegation("worker-1", {"allowed_actions": ["read", "write", "delete", "admin"]})
        assert "allowed_actions" in str(exc_info.value)

    def test_new_item_in_list_raises(self, parent_ctx):
        """Child adding new items not in parent's list must raise ConstraintViolationError."""
        with pytest.raises(ConstraintViolationError) as exc_info:
            parent_ctx.with_delegation("worker-1", {"allowed_regions": ["us-east", "ap-south"]})
        assert "allowed_regions" in str(exc_info.value)

    def test_completely_different_list_raises(self, parent_ctx):
        """Child with completely different list items must raise ConstraintViolationError."""
        with pytest.raises(ConstraintViolationError):
            parent_ctx.with_delegation("worker-1", {"allowed_actions": ["execute", "deploy"]})


# ---------------------------------------------------------------------------
# 3 -- String constraints: must equal parent
# ---------------------------------------------------------------------------


class TestStringConstraintTightening:
    """F-02: String constraints must equal parent (no loosening)."""

    def test_equal_string_allowed(self, parent_ctx):
        """Child with same string value must be allowed."""
        child = parent_ctx.with_delegation("worker-1", {"environment": "production"})
        assert child.constraints["environment"] == "production"

    def test_different_string_raises(self, parent_ctx):
        """Child with different string value must raise ConstraintViolationError."""
        with pytest.raises(ConstraintViolationError) as exc_info:
            parent_ctx.with_delegation("worker-1", {"environment": "staging"})
        assert "environment" in str(exc_info.value)

    def test_different_data_classification_raises(self, parent_ctx):
        """Changing data_classification string must raise ConstraintViolationError."""
        with pytest.raises(ConstraintViolationError):
            parent_ctx.with_delegation("worker-1", {"data_classification": "public"})


# ---------------------------------------------------------------------------
# 4 -- New keys: adding constraints is always tightening
# ---------------------------------------------------------------------------


class TestNewConstraintKeys:
    """F-02: New keys not in parent must be allowed (adding = tightening)."""

    def test_new_numeric_constraint_allowed(self, parent_ctx):
        """Adding a new numeric constraint not in parent must be allowed."""
        child = parent_ctx.with_delegation("worker-1", {"max_tokens": 1000})
        assert child.constraints["max_tokens"] == 1000

    def test_new_list_constraint_allowed(self, parent_ctx):
        """Adding a new list constraint not in parent must be allowed."""
        child = parent_ctx.with_delegation("worker-1", {"allowed_models": ["gpt-4", "claude-3"]})
        assert child.constraints["allowed_models"] == ["gpt-4", "claude-3"]

    def test_new_string_constraint_allowed(self, parent_ctx):
        """Adding a new string constraint not in parent must be allowed."""
        child = parent_ctx.with_delegation("worker-1", {"audit_level": "detailed"})
        assert child.constraints["audit_level"] == "detailed"

    def test_mixed_new_and_tighter_allowed(self, parent_ctx):
        """Mix of new constraints and tighter existing ones must be allowed."""
        child = parent_ctx.with_delegation(
            "worker-1",
            {
                "cost_limit": 5000,  # tighter existing
                "max_tokens": 1000,  # new constraint
                "allowed_actions": ["read"],  # tighter existing
            },
        )
        assert child.constraints["cost_limit"] == 5000
        assert child.constraints["max_tokens"] == 1000
        assert child.constraints["allowed_actions"] == ["read"]


# ---------------------------------------------------------------------------
# 5 -- ConstraintViolationError details
# ---------------------------------------------------------------------------


class TestConstraintViolationErrorDetails:
    """F-02: ConstraintViolationError must contain informative details."""

    def test_error_includes_constraint_key(self, parent_ctx):
        """Error message must include the constraint key that was violated."""
        with pytest.raises(ConstraintViolationError) as exc_info:
            parent_ctx.with_delegation("worker-1", {"cost_limit": 20000})
        error = exc_info.value
        assert "cost_limit" in str(error)

    def test_error_is_trust_error(self, parent_ctx):
        """ConstraintViolationError must be a TrustError (EATP convention)."""
        from eatp.exceptions import TrustError

        with pytest.raises(TrustError):
            parent_ctx.with_delegation("worker-1", {"cost_limit": 20000})


# ---------------------------------------------------------------------------
# 6 -- None additional_constraints (backward compatibility)
# ---------------------------------------------------------------------------


class TestNoneConstraints:
    """F-02: None additional_constraints must work (backward compat)."""

    def test_none_constraints_no_error(self, parent_ctx):
        """with_delegation(delegatee_id, None) must not raise."""
        child = parent_ctx.with_delegation("worker-1", None)
        assert child.constraints == parent_ctx.constraints

    def test_empty_dict_constraints_no_error(self, parent_ctx):
        """with_delegation(delegatee_id, {}) must not raise."""
        child = parent_ctx.with_delegation("worker-1", {})
        assert child.constraints == parent_ctx.constraints

    def test_no_additional_constraints_arg(self, parent_ctx):
        """with_delegation(delegatee_id) must not raise (default None)."""
        child = parent_ctx.with_delegation("worker-1")
        assert child.constraints == parent_ctx.constraints


# ---------------------------------------------------------------------------
# 7 -- Delegation chain and depth still correct
# ---------------------------------------------------------------------------


class TestDelegationChainIntegrity:
    """F-02: with_delegation must still maintain chain and depth correctly."""

    def test_delegation_chain_extended(self, parent_ctx):
        """Delegation chain must be extended with the new delegatee_id."""
        child = parent_ctx.with_delegation("worker-1", {"cost_limit": 5000})
        assert child.delegation_chain == ["pseudo:alice@corp.com", "worker-1"]

    def test_delegation_depth_incremented(self, parent_ctx):
        """Delegation depth must be incremented by 1."""
        child = parent_ctx.with_delegation("worker-1", {"cost_limit": 5000})
        assert child.delegation_depth == parent_ctx.delegation_depth + 1

    def test_human_origin_preserved(self, parent_ctx):
        """Human origin must be the same object reference (PRESERVED)."""
        child = parent_ctx.with_delegation("worker-1", {"cost_limit": 5000})
        assert child.human_origin is parent_ctx.human_origin

    def test_trace_id_preserved(self, parent_ctx):
        """Trace ID must be preserved for correlation."""
        child = parent_ctx.with_delegation("worker-1", {"cost_limit": 5000})
        assert child.trace_id == parent_ctx.trace_id


# ---------------------------------------------------------------------------
# 8 -- Multi-level delegation tightening
# ---------------------------------------------------------------------------


class TestMultiLevelTightening:
    """F-02: Multi-level delegation must enforce monotonic tightening."""

    def test_three_level_monotonic_tightening(self, parent_ctx):
        """Each level must only tighten constraints further."""
        child1 = parent_ctx.with_delegation("worker-1", {"cost_limit": 5000, "allowed_actions": ["read", "write"]})
        child2 = child1.with_delegation("worker-2", {"cost_limit": 2000, "allowed_actions": ["read"]})

        assert child2.constraints["cost_limit"] == 2000
        assert child2.constraints["allowed_actions"] == ["read"]
        assert child2.delegation_depth == 2

    def test_grandchild_cannot_loosen_parent_constraint(self, parent_ctx):
        """Grandchild cannot loosen what parent already tightened."""
        child1 = parent_ctx.with_delegation("worker-1", {"cost_limit": 5000})

        # child2 tries to go back to 10000 -- must fail
        with pytest.raises(ConstraintViolationError):
            child1.with_delegation("worker-2", {"cost_limit": 10000})
