"""Tests for CARE-042 (fallback_allow mode-aware default) and CARE-043 (cache invalidation).

CARE-042: In ENFORCING mode, fallback_allow MUST default to False (fail-closed).
CARE-043: Cache must be invalidatable per-agent to support immediate revocation.
"""

import asyncio

import pytest
from kailash.runtime.trust.context import RuntimeTrustContext, TrustVerificationMode
from kailash.runtime.trust.verifier import (
    MockTrustVerifier,
    TrustVerifier,
    TrustVerifierConfig,
    VerificationResult,
)

# ─── CARE-042: Fallback Allow Mode-Aware Default ───────────────────────────


class TestFallbackAllowEnforcingDefault:
    """CARE-042: In ENFORCING mode, fallback_allow defaults to False."""

    def test_enforcing_mode_defaults_to_deny(self):
        """ENFORCING mode with no explicit fallback_allow should deny on failure."""
        config = TrustVerifierConfig(mode="enforcing")
        verifier = TrustVerifier(config=config)
        assert verifier._effective_fallback_allow is False

    def test_permissive_mode_defaults_to_allow(self):
        """PERMISSIVE mode with no explicit fallback_allow should allow on failure."""
        config = TrustVerifierConfig(mode="permissive")
        verifier = TrustVerifier(config=config)
        assert verifier._effective_fallback_allow is True

    def test_disabled_mode_defaults_to_allow(self):
        """DISABLED mode with no explicit fallback_allow should allow on failure."""
        config = TrustVerifierConfig(mode="disabled")
        verifier = TrustVerifier(config=config)
        assert verifier._effective_fallback_allow is True

    def test_explicit_fallback_allow_overrides_default(self):
        """Explicit fallback_allow=True in ENFORCING mode should be respected."""
        config = TrustVerifierConfig(mode="enforcing", fallback_allow=True)
        verifier = TrustVerifier(config=config)
        assert verifier._effective_fallback_allow is True

    def test_explicit_fallback_deny_in_permissive(self):
        """Explicit fallback_allow=False in PERMISSIVE mode should be respected."""
        config = TrustVerifierConfig(mode="permissive", fallback_allow=False)
        verifier = TrustVerifier(config=config)
        assert verifier._effective_fallback_allow is False

    def test_enforcing_no_backend_denies_workflow(self):
        """ENFORCING mode with no backend should deny workflow access."""
        config = TrustVerifierConfig(mode="enforcing")
        verifier = TrustVerifier(config=config)
        ctx = RuntimeTrustContext(
            trace_id="test",
            verification_mode=TrustVerificationMode.ENFORCING,
        )
        result = asyncio.run(verifier.verify_workflow_access("wf-1", "agent-1", ctx))
        assert not result.allowed
        assert "No verification backend configured" in result.reason

    def test_enforcing_no_backend_denies_node(self):
        """ENFORCING mode with no backend should deny node access."""
        config = TrustVerifierConfig(mode="enforcing")
        verifier = TrustVerifier(config=config)
        ctx = RuntimeTrustContext(
            trace_id="test",
            verification_mode=TrustVerificationMode.ENFORCING,
        )
        result = asyncio.run(
            verifier.verify_node_access("node-1", "BashCommand", "agent-1", ctx)
        )
        assert not result.allowed

    def test_enforcing_no_backend_denies_resource(self):
        """ENFORCING mode with no backend should deny resource access."""
        config = TrustVerifierConfig(mode="enforcing")
        verifier = TrustVerifier(config=config)
        ctx = RuntimeTrustContext(
            trace_id="test",
            verification_mode=TrustVerificationMode.ENFORCING,
        )
        result = asyncio.run(
            verifier.verify_resource_access("/data", "read", "agent-1", ctx)
        )
        assert not result.allowed


class TestFallbackAllowBackendFailure:
    """CARE-042: Backend failure in ENFORCING mode should deny by default."""

    def test_backend_exception_denies_in_enforcing(self):
        """When backend raises, ENFORCING mode should deny."""

        class FailingBackend:
            async def verify(self, **kwargs):
                raise ConnectionError("Backend unavailable")

        config = TrustVerifierConfig(mode="enforcing")
        verifier = TrustVerifier(kaizen_backend=FailingBackend(), config=config)
        ctx = RuntimeTrustContext(
            trace_id="test",
            verification_mode=TrustVerificationMode.ENFORCING,
        )
        result = asyncio.run(verifier.verify_workflow_access("wf-1", "agent-1", ctx))
        assert not result.allowed
        assert "Verification unavailable" in result.reason

    def test_backend_exception_allows_in_permissive(self):
        """When backend raises, PERMISSIVE mode should allow."""

        class FailingBackend:
            async def verify(self, **kwargs):
                raise ConnectionError("Backend unavailable")

        config = TrustVerifierConfig(mode="permissive")
        verifier = TrustVerifier(kaizen_backend=FailingBackend(), config=config)
        ctx = RuntimeTrustContext(
            trace_id="test",
            verification_mode=TrustVerificationMode.PERMISSIVE,
        )
        result = asyncio.run(verifier.verify_workflow_access("wf-1", "agent-1", ctx))
        assert result.allowed

    def test_enforcing_explicit_allow_fallback_overrides(self):
        """Explicit fallback_allow=True overrides ENFORCING default (opt-in)."""

        class FailingBackend:
            async def verify(self, **kwargs):
                raise ConnectionError("Backend unavailable")

        config = TrustVerifierConfig(mode="enforcing", fallback_allow=True)
        verifier = TrustVerifier(kaizen_backend=FailingBackend(), config=config)
        ctx = RuntimeTrustContext(
            trace_id="test",
            verification_mode=TrustVerificationMode.ENFORCING,
        )
        result = asyncio.run(verifier.verify_workflow_access("wf-1", "agent-1", ctx))
        # Explicit override should allow
        assert result.allowed


# ─── CARE-043: Cache Invalidation ──────────────────────────────────────────


class TestCacheInvalidation:
    """CARE-043: Cache entries must be invalidatable for immediate revocation."""

    def test_invalidate_agent_clears_matching_entries(self):
        """invalidate_agent should remove all cache entries for that agent."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = MockTrustVerifier(default_allow=True, config=config)

        ctx = RuntimeTrustContext(trace_id="test")
        # Populate cache
        asyncio.run(verifier.verify_workflow_access("wf-1", "agent-a", ctx))
        asyncio.run(verifier.verify_node_access("n-1", "HttpRequest", "agent-a", ctx))
        asyncio.run(verifier.verify_workflow_access("wf-1", "agent-b", ctx))

        # Cache should have 3 entries
        assert len(verifier._cache) == 3

        # Invalidate agent-a
        removed = verifier.invalidate_agent("agent-a")
        assert removed == 2
        # Only agent-b entry should remain
        assert len(verifier._cache) == 1

    def test_invalidate_agent_returns_zero_if_no_match(self):
        """invalidate_agent with non-existent agent should return 0."""
        verifier = TrustVerifier(config=TrustVerifierConfig(mode="enforcing"))
        removed = verifier.invalidate_agent("nonexistent")
        assert removed == 0

    def test_invalidate_node_clears_matching_entries(self):
        """invalidate_node should remove all cache entries for that node type."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = MockTrustVerifier(default_allow=True, config=config)

        ctx = RuntimeTrustContext(trace_id="test")
        asyncio.run(verifier.verify_node_access("n-1", "BashCommand", "agent-a", ctx))
        asyncio.run(verifier.verify_node_access("n-2", "BashCommand", "agent-b", ctx))
        asyncio.run(verifier.verify_node_access("n-3", "HttpRequest", "agent-a", ctx))

        assert len(verifier._cache) == 3

        removed = verifier.invalidate_node("BashCommand")
        assert removed == 2
        assert len(verifier._cache) == 1

    def test_revocation_scenario_cache_then_invalidate(self):
        """Simulate: agent verified OK, then revoked, cache invalidated, re-check denied."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = MockTrustVerifier(default_allow=True, config=config)
        ctx = RuntimeTrustContext(trace_id="test")

        # Step 1: Agent verifies OK (cached)
        result = asyncio.run(verifier.verify_workflow_access("wf-1", "agent-a", ctx))
        assert result.allowed

        # Step 2: Revoke agent (add to denied list + invalidate cache)
        verifier._denied_agents.add("agent-a")
        verifier.invalidate_agent("agent-a")

        # Step 3: Re-verify should now be denied
        result = asyncio.run(verifier.verify_workflow_access("wf-1", "agent-a", ctx))
        assert not result.allowed
        assert "denied" in result.reason.lower()

    def test_without_invalidation_revocation_delayed_by_cache(self):
        """Without invalidation, revoked agent still allowed via cache."""
        config = TrustVerifierConfig(
            mode="enforcing", cache_enabled=True, cache_ttl_seconds=3600
        )
        verifier = MockTrustVerifier(default_allow=True, config=config)
        ctx = RuntimeTrustContext(trace_id="test")

        # Step 1: Agent verifies OK (cached for 1 hour)
        result = asyncio.run(verifier.verify_workflow_access("wf-1", "agent-a", ctx))
        assert result.allowed

        # Step 2: Revoke agent but DON'T invalidate cache
        verifier._denied_agents.add("agent-a")

        # Step 3: Still allowed because cached result hasn't expired
        result = asyncio.run(verifier.verify_workflow_access("wf-1", "agent-a", ctx))
        assert (
            result.allowed
        )  # BUG without invalidation - this proves the need for CARE-043

    def test_clear_cache_removes_all_entries(self):
        """clear_cache should remove all entries regardless of agent/node."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = MockTrustVerifier(default_allow=True, config=config)
        ctx = RuntimeTrustContext(trace_id="test")

        asyncio.run(verifier.verify_workflow_access("wf-1", "agent-a", ctx))
        asyncio.run(verifier.verify_workflow_access("wf-2", "agent-b", ctx))

        assert len(verifier._cache) == 2
        verifier.clear_cache()
        assert len(verifier._cache) == 0


class TestCacheInvalidationPrecision:
    """CARE-043: Cache invalidation must not have false positives."""

    def test_invalidate_agent_no_false_positive_on_prefix(self):
        """Invalidating 'agent-a' must NOT remove entries for 'agent-abc'."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = MockTrustVerifier(default_allow=True, config=config)
        ctx = RuntimeTrustContext(trace_id="test")

        asyncio.run(verifier.verify_workflow_access("wf-1", "agent-a", ctx))
        asyncio.run(verifier.verify_workflow_access("wf-1", "agent-abc", ctx))

        assert len(verifier._cache) == 2

        removed = verifier.invalidate_agent("agent-a")
        assert removed == 1  # Only agent-a, not agent-abc
        assert len(verifier._cache) == 1

    def test_invalidate_node_no_false_positive_on_prefix(self):
        """Invalidating 'Bash' must NOT remove entries for 'BashCommand'."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = MockTrustVerifier(default_allow=True, config=config)
        ctx = RuntimeTrustContext(trace_id="test")

        asyncio.run(verifier.verify_node_access("n-1", "Bash", "agent-a", ctx))
        asyncio.run(verifier.verify_node_access("n-2", "BashCommand", "agent-a", ctx))

        assert len(verifier._cache) == 2

        removed = verifier.invalidate_node("Bash")
        assert removed == 1  # Only Bash, not BashCommand
        assert len(verifier._cache) == 1


class TestCriticalLogging:
    """CARE-042: CRITICAL-level logging when fallback triggered in ENFORCING mode."""

    def test_enforcing_backend_failure_logs_critical(self, caplog):
        """Backend failure in ENFORCING mode should log at CRITICAL level."""
        import logging

        class FailingBackend:
            async def verify(self, **kwargs):
                raise ConnectionError("Backend down")

        config = TrustVerifierConfig(mode="enforcing")
        verifier = TrustVerifier(kaizen_backend=FailingBackend(), config=config)
        ctx = RuntimeTrustContext(trace_id="test")

        with caplog.at_level(logging.CRITICAL, logger="kailash.runtime.trust.verifier"):
            asyncio.run(verifier.verify_workflow_access("wf-1", "agent-1", ctx))

        critical_messages = [r for r in caplog.records if r.levelno >= logging.CRITICAL]
        assert len(critical_messages) >= 1
        assert "SECURITY" in critical_messages[0].message
        assert "ENFORCING" in critical_messages[0].message

    def test_permissive_backend_failure_logs_error_not_critical(self, caplog):
        """Backend failure in PERMISSIVE mode should log at ERROR, not CRITICAL."""
        import logging

        class FailingBackend:
            async def verify(self, **kwargs):
                raise ConnectionError("Backend down")

        config = TrustVerifierConfig(mode="permissive")
        verifier = TrustVerifier(kaizen_backend=FailingBackend(), config=config)
        ctx = RuntimeTrustContext(trace_id="test")

        with caplog.at_level(logging.ERROR, logger="kailash.runtime.trust.verifier"):
            asyncio.run(verifier.verify_workflow_access("wf-1", "agent-1", ctx))

        critical_messages = [r for r in caplog.records if r.levelno >= logging.CRITICAL]
        assert len(critical_messages) == 0  # No CRITICAL in permissive mode


class TestBackwardCompatibility:
    """Ensure existing code that passes fallback_allow=True still works."""

    def test_explicit_true_still_works(self):
        """Explicit fallback_allow=True should still be respected."""
        config = TrustVerifierConfig(mode="enforcing", fallback_allow=True)
        verifier = TrustVerifier(config=config)
        assert verifier._effective_fallback_allow is True

    def test_explicit_false_still_works(self):
        """Explicit fallback_allow=False should still be respected."""
        config = TrustVerifierConfig(mode="disabled", fallback_allow=False)
        verifier = TrustVerifier(config=config)
        assert verifier._effective_fallback_allow is False

    def test_mock_verifier_inherits_behavior(self):
        """MockTrustVerifier should respect the same fallback defaults."""
        verifier = MockTrustVerifier(
            default_allow=True,
            config=TrustVerifierConfig(mode="enforcing"),
        )
        assert verifier._effective_fallback_allow is False

    def test_default_config_unchanged(self):
        """Default TrustVerifierConfig should have None fallback_allow."""
        config = TrustVerifierConfig()
        assert config.fallback_allow is None
        assert config.mode == "disabled"
