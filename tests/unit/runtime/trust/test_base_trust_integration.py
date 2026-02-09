"""Unit tests for BaseRuntime trust integration (CARE-015).

Tests for trust parameter integration in BaseRuntime.
These are Tier 1 unit tests.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from kailash.runtime.base import BaseRuntime
from kailash.runtime.trust.context import (
    RuntimeTrustContext,
    TrustVerificationMode,
    get_runtime_trust_context,
    runtime_trust_context,
    set_runtime_trust_context,
)
from kailash.workflow import Workflow


class ConcreteRuntime(BaseRuntime):
    """Concrete implementation for testing abstract base."""

    def execute(self, workflow: Workflow, **kwargs):
        """Minimal execute implementation."""
        return {}, "test-run-id"


class TestBaseRuntimeTrustParamsOptional:
    """Test that all trust params have defaults and existing code works."""

    def test_base_runtime_trust_params_optional(self):
        """Test all trust params have defaults, existing code works."""
        # Should work without any trust parameters
        runtime = ConcreteRuntime()

        assert runtime is not None
        # Should be able to execute without trust context
        results, run_id = runtime.execute(Workflow(workflow_id="test", name="Test"))
        assert results == {}


class TestBaseRuntimeTrustDisabledDefault:
    """Test default trust verification mode."""

    def test_base_runtime_trust_disabled_default(self):
        """Test default mode is DISABLED."""
        runtime = ConcreteRuntime()

        assert runtime._trust_verification_mode == TrustVerificationMode.DISABLED
        assert runtime._trust_context is None
        assert runtime._trust_verifier is None


class TestBaseRuntimeTrustModeValidation:
    """Test trust mode parameter validation."""

    def test_valid_trust_modes(self):
        """Test valid trust verification modes are accepted."""
        runtime_disabled = ConcreteRuntime(trust_verification_mode="disabled")
        assert (
            runtime_disabled._trust_verification_mode == TrustVerificationMode.DISABLED
        )

        runtime_permissive = ConcreteRuntime(trust_verification_mode="permissive")
        assert (
            runtime_permissive._trust_verification_mode
            == TrustVerificationMode.PERMISSIVE
        )

        runtime_enforcing = ConcreteRuntime(trust_verification_mode="enforcing")
        assert (
            runtime_enforcing._trust_verification_mode
            == TrustVerificationMode.ENFORCING
        )

    def test_invalid_trust_mode_raises_value_error(self):
        """Test invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid trust_verification_mode"):
            ConcreteRuntime(trust_verification_mode="invalid_mode")

        with pytest.raises(ValueError, match="Must be one of"):
            ConcreteRuntime(trust_verification_mode="strict")


class TestBaseRuntimeTrustVerifierWarning:
    """Test warning when trust mode != DISABLED but no verifier."""

    def test_warning_on_missing_verifier_permissive(self, caplog):
        """Test logs warning if mode is PERMISSIVE and no verifier."""
        with caplog.at_level(logging.WARNING):
            runtime = ConcreteRuntime(trust_verification_mode="permissive")

        assert "no trust_verifier provided" in caplog.text
        assert "permissive" in caplog.text
        assert runtime._trust_verifier is None

    def test_warning_on_missing_verifier_enforcing(self, caplog):
        """Test logs warning if mode is ENFORCING and no verifier."""
        with caplog.at_level(logging.WARNING):
            runtime = ConcreteRuntime(trust_verification_mode="enforcing")

        assert "no trust_verifier provided" in caplog.text
        assert "enforcing" in caplog.text

    def test_no_warning_when_disabled(self, caplog):
        """Test no warning when mode is DISABLED."""
        with caplog.at_level(logging.WARNING):
            runtime = ConcreteRuntime(trust_verification_mode="disabled")

        assert "no trust_verifier provided" not in caplog.text

    def test_no_warning_when_verifier_provided(self, caplog):
        """Test no warning when verifier is provided."""
        mock_verifier = MagicMock()

        with caplog.at_level(logging.WARNING):
            runtime = ConcreteRuntime(
                trust_verification_mode="enforcing",
                trust_verifier=mock_verifier,
            )

        assert "no trust_verifier provided" not in caplog.text
        assert runtime._trust_verifier is mock_verifier


class TestBaseRuntimeTrustContextParam:
    """Test trust_context parameter."""

    def test_trust_context_stored(self):
        """Test trust_context is stored when provided."""
        ctx = RuntimeTrustContext(trace_id="test-ctx")
        runtime = ConcreteRuntime(trust_context=ctx)

        assert runtime._trust_context is ctx
        assert runtime._trust_context.trace_id == "test-ctx"

    def test_trust_context_default_none(self):
        """Test trust_context defaults to None."""
        runtime = ConcreteRuntime()
        assert runtime._trust_context is None


class TestGetEffectiveTrustContext:
    """Test _get_effective_trust_context priority resolution."""

    def test_context_priority_constructor_when_no_contextvar(self):
        """Test constructor context used when no ContextVar set."""
        constructor_ctx = RuntimeTrustContext(trace_id="constructor")
        runtime = ConcreteRuntime(trust_context=constructor_ctx)

        # Clear any existing ContextVar
        set_runtime_trust_context(None)

        result = runtime._get_effective_trust_context()
        assert result is constructor_ctx
        assert result.trace_id == "constructor"

    def test_context_priority_contextvar_over_constructor(self):
        """Test ContextVar takes priority over constructor context."""
        constructor_ctx = RuntimeTrustContext(trace_id="constructor")
        contextvar_ctx = RuntimeTrustContext(trace_id="contextvar")

        runtime = ConcreteRuntime(trust_context=constructor_ctx)

        with runtime_trust_context(contextvar_ctx):
            result = runtime._get_effective_trust_context()
            assert result is contextvar_ctx
            assert result.trace_id == "contextvar"

    def test_context_priority_none_when_both_none(self):
        """Test returns None when both ContextVar and constructor are None."""
        runtime = ConcreteRuntime()

        # Clear ContextVar
        set_runtime_trust_context(None)

        result = runtime._get_effective_trust_context()
        assert result is None

    def test_context_resolution_uses_contextvar_get(self):
        """Test that resolution actually uses get_runtime_trust_context."""
        ctx = RuntimeTrustContext(trace_id="test-resolution")
        runtime = ConcreteRuntime()

        set_runtime_trust_context(ctx)
        result = runtime._get_effective_trust_context()

        assert result is ctx


class TestBaseRuntimeBackwardCompatibility:
    """Test backward compatibility with existing code."""

    def test_existing_initialization_patterns(self):
        """Test existing initialization patterns still work."""
        # Pattern 1: Basic initialization
        runtime1 = ConcreteRuntime()
        assert runtime1.debug is False

        # Pattern 2: With debug
        runtime2 = ConcreteRuntime(debug=True)
        assert runtime2.debug is True

        # Pattern 3: With existing params
        runtime3 = ConcreteRuntime(
            debug=True,
            enable_cycles=False,
            connection_validation="strict",
        )
        assert runtime3.enable_cycles is False
        assert runtime3.connection_validation == "strict"

        # Pattern 4: Mix of old and new params
        runtime4 = ConcreteRuntime(
            debug=True,
            trust_verification_mode="permissive",
        )
        assert runtime4.debug is True
        assert runtime4._trust_verification_mode == TrustVerificationMode.PERMISSIVE

    def test_attribute_count_still_valid(self):
        """Test that new attributes are added without breaking existing ones."""
        runtime = ConcreteRuntime()

        # Existing attributes should still be present
        existing_attrs = [
            "debug",
            "enable_cycles",
            "enable_async",
            "max_concurrency",
            "connection_validation",
            "conditional_execution",
        ]

        for attr in existing_attrs:
            assert hasattr(runtime, attr), f"Missing existing attribute: {attr}"

        # New trust attributes should be present
        trust_attrs = [
            "_trust_context",
            "_trust_verifier",
            "_trust_verification_mode",
        ]

        for attr in trust_attrs:
            assert hasattr(runtime, attr), f"Missing trust attribute: {attr}"
