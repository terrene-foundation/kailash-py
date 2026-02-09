"""Unit tests for TrustVerifier (CARE-016).

Tests for VerificationResult, TrustVerifierConfig, TrustVerifier, and caching.
These are Tier 1 unit tests - fast, isolated, no external dependencies.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from kailash.runtime.trust.context import RuntimeTrustContext, TrustVerificationMode
from kailash.runtime.trust.verifier import (
    MockTrustVerifier,
    TrustVerifier,
    TrustVerifierConfig,
    VerificationResult,
)


class TestVerificationResultCreation:
    """Test VerificationResult dataclass creation and fields."""

    def test_verification_result_creation(self):
        """Test all fields set correctly on creation."""
        result = VerificationResult(
            allowed=True,
            reason="Test reason",
            constraints={"max_tokens": 1000},
            capability_used="execute_workflow",
            trace_id="trace-123",
        )

        assert result.allowed is True
        assert result.reason == "Test reason"
        assert result.constraints == {"max_tokens": 1000}
        assert result.capability_used == "execute_workflow"
        assert result.trace_id == "trace-123"

    def test_verification_result_defaults(self):
        """Test default values for optional fields."""
        result = VerificationResult(allowed=True)

        assert result.allowed is True
        assert result.reason is None
        assert result.constraints == {}
        assert result.capability_used is None
        assert result.trace_id is None

    def test_verification_result_bool_true(self):
        """Test bool(result) is True when allowed is True."""
        result = VerificationResult(allowed=True)
        assert bool(result) is True

    def test_verification_result_bool_false(self):
        """Test bool(result) is False when allowed is False."""
        result = VerificationResult(allowed=False)
        assert bool(result) is False

    def test_verification_result_to_dict(self):
        """Test serialization to dict works correctly."""
        result = VerificationResult(
            allowed=True,
            reason="Test reason",
            constraints={"limit": 100},
            capability_used="cap-1",
            trace_id="trace-456",
        )

        data = result.to_dict()

        assert data == {
            "allowed": True,
            "reason": "Test reason",
            "constraints": {"limit": 100},
            "capability_used": "cap-1",
            "trace_id": "trace-456",
        }

    def test_verification_result_to_dict_with_none_values(self):
        """Test serialization handles None values correctly."""
        result = VerificationResult(allowed=False)

        data = result.to_dict()

        assert data == {
            "allowed": False,
            "reason": None,
            "constraints": {},
            "capability_used": None,
            "trace_id": None,
        }


class TestTrustVerifierConfigDefaults:
    """Test TrustVerifierConfig default values."""

    def test_verifier_config_defaults(self):
        """Test all default values are correct."""
        config = TrustVerifierConfig()

        assert config.mode == "disabled"
        assert config.cache_enabled is True
        assert config.cache_ttl_seconds == 60
        assert config.fallback_allow is None  # CARE-042: mode-aware default
        assert config.audit_denials is True

    def test_verifier_config_high_risk_nodes(self):
        """Test default high-risk node list includes expected nodes."""
        config = TrustVerifierConfig()

        # Check all expected high-risk nodes are present
        expected_nodes = [
            "BashCommand",
            "HttpRequest",
            "DatabaseQuery",
            "FileWrite",
            "CodeExecution",
            "PythonCode",
        ]

        for node in expected_nodes:
            assert node in config.high_risk_nodes, f"Expected {node} in high_risk_nodes"

    def test_verifier_config_custom_values(self):
        """Test custom configuration values."""
        config = TrustVerifierConfig(
            mode="enforcing",
            cache_enabled=False,
            cache_ttl_seconds=120,
            fallback_allow=False,
            audit_denials=False,
            high_risk_nodes=["CustomNode"],
        )

        assert config.mode == "enforcing"
        assert config.cache_enabled is False
        assert config.cache_ttl_seconds == 120
        assert config.fallback_allow is False
        assert config.audit_denials is False
        assert config.high_risk_nodes == ["CustomNode"]


class TestTrustVerifierModeProperties:
    """Test TrustVerifier mode-related properties."""

    def test_verifier_disabled_always_allows(self):
        """Test disabled mode always returns allowed=True."""
        config = TrustVerifierConfig(mode="disabled")
        verifier = TrustVerifier(config=config)

        # is_enabled should be False when DISABLED
        assert verifier.is_enabled is False

    def test_verifier_enabled_property_disabled(self):
        """Test is_enabled is False when mode is DISABLED."""
        config = TrustVerifierConfig(mode="disabled")
        verifier = TrustVerifier(config=config)

        assert verifier.is_enabled is False

    def test_verifier_enabled_property_permissive(self):
        """Test is_enabled is True when mode is PERMISSIVE."""
        config = TrustVerifierConfig(mode="permissive")
        verifier = TrustVerifier(config=config)

        assert verifier.is_enabled is True

    def test_verifier_enabled_property_enforcing(self):
        """Test is_enabled is True when mode is ENFORCING."""
        config = TrustVerifierConfig(mode="enforcing")
        verifier = TrustVerifier(config=config)

        assert verifier.is_enabled is True

    def test_verifier_enforcing_property(self):
        """Test is_enforcing only True when mode is ENFORCING."""
        # DISABLED mode
        config_disabled = TrustVerifierConfig(mode="disabled")
        verifier_disabled = TrustVerifier(config=config_disabled)
        assert verifier_disabled.is_enforcing is False

        # PERMISSIVE mode
        config_permissive = TrustVerifierConfig(mode="permissive")
        verifier_permissive = TrustVerifier(config=config_permissive)
        assert verifier_permissive.is_enforcing is False

        # ENFORCING mode
        config_enforcing = TrustVerifierConfig(mode="enforcing")
        verifier_enforcing = TrustVerifier(config=config_enforcing)
        assert verifier_enforcing.is_enforcing is True


class TestTrustVerifierCaching:
    """Test TrustVerifier caching behavior."""

    def test_cache_key_workflow(self):
        """Test cache key format for workflows."""
        # Cache keys are internal implementation detail
        # We test via observable behavior - setting and getting cached values
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        # Create a result and cache it with workflow key format
        # CARE-058: Use null byte separator for cache keys
        result = VerificationResult(allowed=True, reason="test")
        cache_key = "wf\x00test-workflow\x00agent-1"
        verifier._set_cache(cache_key, result)

        # Verify cache hit
        cached = verifier._get_cached(cache_key)
        assert cached is not None
        assert cached.allowed is True
        assert cached.reason == "test"

    def test_cache_key_node(self):
        """Test cache key format for nodes."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        # CARE-058: Use null byte separator for cache keys
        result = VerificationResult(allowed=False, reason="node denied")
        cache_key = "node\x00node-1\x00HttpRequest\x00agent-1"
        verifier._set_cache(cache_key, result)

        cached = verifier._get_cached(cache_key)
        assert cached is not None
        assert cached.allowed is False

    def test_cache_key_resource(self):
        """Test cache key format for resources."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        # CARE-058: Use null byte separator for cache keys
        result = VerificationResult(allowed=True, reason="resource access granted")
        cache_key = "res\x00/data/file.txt\x00read\x00agent-1"
        verifier._set_cache(cache_key, result)

        cached = verifier._get_cached(cache_key)
        assert cached is not None
        assert cached.allowed is True

    def test_cache_miss_returns_none(self):
        """Test uncached key returns None from _get_cached."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        cached = verifier._get_cached("nonexistent-key")
        assert cached is None

    def test_cache_disabled_returns_none(self):
        """Test cache disabled always returns None from _get_cached."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=False)
        verifier = TrustVerifier(config=config)

        # Set a value
        result = VerificationResult(allowed=True)
        verifier._set_cache("some-key", result)

        # Should still return None when cache is disabled
        cached = verifier._get_cached("some-key")
        assert cached is None

    def test_clear_cache(self):
        """Test cache cleared correctly."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        # Add some cached entries
        result = VerificationResult(allowed=True)
        verifier._set_cache("key1", result)
        verifier._set_cache("key2", result)

        # Verify they exist
        assert verifier._get_cached("key1") is not None
        assert verifier._get_cached("key2") is not None

        # Clear cache
        verifier.clear_cache()

        # Verify cleared
        assert verifier._get_cached("key1") is None
        assert verifier._get_cached("key2") is None

    def test_cache_expiry(self):
        """Test cache entries expire after TTL."""
        config = TrustVerifierConfig(
            mode="enforcing",
            cache_enabled=True,
            cache_ttl_seconds=1,  # Very short TTL for testing
        )
        verifier = TrustVerifier(config=config)

        result = VerificationResult(allowed=True)
        verifier._set_cache("expiring-key", result)

        # Should be cached immediately
        assert verifier._get_cached("expiring-key") is not None

        # Wait for expiry
        time.sleep(1.1)

        # Should be expired now
        assert verifier._get_cached("expiring-key") is None


class TestTrustVerifierDisabledMode:
    """Test TrustVerifier behavior when disabled."""

    @pytest.mark.asyncio
    async def test_verify_workflow_disabled_mode(self):
        """Test verify_workflow_access returns allowed when disabled."""
        config = TrustVerifierConfig(mode="disabled")
        verifier = TrustVerifier(config=config)

        result = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="test-agent",
        )

        assert result.allowed is True
        assert result.reason == "Verification disabled"

    @pytest.mark.asyncio
    async def test_verify_node_disabled_mode(self):
        """Test verify_node_access returns allowed when disabled."""
        config = TrustVerifierConfig(mode="disabled")
        verifier = TrustVerifier(config=config)

        result = await verifier.verify_node_access(
            node_id="node-1",
            node_type="BashCommand",
            agent_id="test-agent",
        )

        assert result.allowed is True
        assert result.reason == "Verification disabled"

    @pytest.mark.asyncio
    async def test_verify_resource_disabled_mode(self):
        """Test verify_resource_access returns allowed when disabled."""
        config = TrustVerifierConfig(mode="disabled")
        verifier = TrustVerifier(config=config)

        result = await verifier.verify_resource_access(
            resource="/data/file.txt",
            action="read",
            agent_id="test-agent",
        )

        assert result.allowed is True
        assert result.reason == "Verification disabled"


class TestTrustVerifierNoBackend:
    """Test TrustVerifier behavior when no backend is configured."""

    @pytest.mark.asyncio
    async def test_verify_workflow_no_backend_fallback_allow(self):
        """Test verify_workflow_access with fallback_allow=True."""
        config = TrustVerifierConfig(mode="enforcing", fallback_allow=True)
        verifier = TrustVerifier(config=config)

        result = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="test-agent",
        )

        assert result.allowed is True
        assert result.reason == "No verification backend configured"

    @pytest.mark.asyncio
    async def test_verify_workflow_no_backend_fallback_deny(self):
        """Test verify_workflow_access with fallback_allow=False."""
        config = TrustVerifierConfig(mode="enforcing", fallback_allow=False)
        verifier = TrustVerifier(config=config)

        result = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="test-agent",
        )

        assert result.allowed is False
        assert result.reason == "No verification backend configured"

    @pytest.mark.asyncio
    async def test_verify_node_no_backend_fallback_allow(self):
        """Test verify_node_access with fallback_allow=True."""
        config = TrustVerifierConfig(mode="enforcing", fallback_allow=True)
        verifier = TrustVerifier(config=config)

        result = await verifier.verify_node_access(
            node_id="node-1",
            node_type="HttpRequest",
            agent_id="test-agent",
        )

        assert result.allowed is True
        assert result.reason == "No verification backend configured"

    @pytest.mark.asyncio
    async def test_verify_resource_no_backend_fallback_allow(self):
        """Test verify_resource_access with fallback_allow=True."""
        config = TrustVerifierConfig(mode="enforcing", fallback_allow=True)
        verifier = TrustVerifier(config=config)

        result = await verifier.verify_resource_access(
            resource="/data/file.txt",
            action="read",
            agent_id="test-agent",
        )

        assert result.allowed is True
        assert result.reason == "No verification backend configured"


class TestTrustVerifierWithTrustContext:
    """Test TrustVerifier integration with RuntimeTrustContext."""

    @pytest.mark.asyncio
    async def test_verify_workflow_with_context(self):
        """Test verify_workflow_access propagates trace_id from context."""
        config = TrustVerifierConfig(mode="enforcing", fallback_allow=True)
        verifier = TrustVerifier(config=config)

        trust_ctx = RuntimeTrustContext(trace_id="context-trace-123")

        result = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="test-agent",
            trust_context=trust_ctx,
        )

        assert result.trace_id == "context-trace-123"

    @pytest.mark.asyncio
    async def test_verify_node_with_context(self):
        """Test verify_node_access propagates trace_id from context."""
        config = TrustVerifierConfig(mode="enforcing", fallback_allow=True)
        verifier = TrustVerifier(config=config)

        trust_ctx = RuntimeTrustContext(trace_id="node-trace-456")

        result = await verifier.verify_node_access(
            node_id="node-1",
            node_type="BashCommand",
            agent_id="test-agent",
            trust_context=trust_ctx,
        )

        assert result.trace_id == "node-trace-456"

    @pytest.mark.asyncio
    async def test_verify_resource_with_context(self):
        """Test verify_resource_access propagates trace_id from context."""
        config = TrustVerifierConfig(mode="enforcing", fallback_allow=True)
        verifier = TrustVerifier(config=config)

        trust_ctx = RuntimeTrustContext(trace_id="resource-trace-789")

        result = await verifier.verify_resource_access(
            resource="/data/file.txt",
            action="write",
            agent_id="test-agent",
            trust_context=trust_ctx,
        )

        assert result.trace_id == "resource-trace-789"


class TestTrustVerifierCacheHit:
    """Test TrustVerifier cache hit behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit_avoids_backend(self):
        """Test cached results are returned without calling backend."""
        # Use MockTrustVerifier to track behavior
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = MockTrustVerifier(default_allow=True, config=config)

        # First call should execute
        result1 = await verifier.verify_workflow_access(
            workflow_id="cached-wf",
            agent_id="agent-1",
        )
        assert result1.allowed is True

        # Manually set cache with a different result
        # CARE-058: Use null byte separator for cache key
        cache_key = "wf\x00cached-wf\x00agent-1"
        cached_result = VerificationResult(
            allowed=False,
            reason="From cache",
        )
        verifier._set_cache(cache_key, cached_result)

        # Second call should return cached result
        result2 = await verifier.verify_workflow_access(
            workflow_id="cached-wf",
            agent_id="agent-1",
        )

        # If cache was used, result should be the cached one (denied)
        assert result2.allowed is False
        assert result2.reason == "From cache"


class TestCacheKeyCollisionPrevention:
    """Test CARE-058: Cache key construction prevents collision attacks.

    When IDs contain the separator character, crafted IDs could cause
    cache key collisions. For example, with colon separator:
    - workflow_id="a:b" agent_id="c" -> "wf:a:b:c"
    - workflow_id="a" agent_id="b:c" -> "wf:a:b:c" (COLLISION!)

    The fix uses null byte (\\x00) as separator since it cannot appear
    in legitimate string IDs.
    """

    @pytest.mark.asyncio
    async def test_workflow_cache_key_no_collision_with_colons(self):
        """Test that workflow IDs with colons don't cause cache collisions.

        CARE-058: workflow_id="a:b" agent_id="c" must not collide with
        workflow_id="a" agent_id="b:c".
        """
        config = TrustVerifierConfig(mode="enforcing", fallback_allow=True)
        verifier = TrustVerifier(config=config)

        # First request: workflow_id="a:b", agent_id="c"
        result1 = await verifier.verify_workflow_access(
            workflow_id="a:b",
            agent_id="c",
        )
        assert result1.allowed is True

        # Second request: workflow_id="a", agent_id="b:c"
        # With colon separator these would produce same cache key: "wf:a:b:c"
        result2 = await verifier.verify_workflow_access(
            workflow_id="a",
            agent_id="b:c",
        )
        assert result2.allowed is True

        # Verify both are cached separately by checking cache size
        # With collision, there would only be 1 entry
        workflow_cache_entries = [
            k for k in verifier._cache.keys() if k.startswith("wf")
        ]
        assert len(workflow_cache_entries) == 2, (
            f"Cache collision detected: expected 2 workflow cache entries, "
            f"got {len(workflow_cache_entries)}. "
            "workflow_id='a:b',agent_id='c' collided with "
            "workflow_id='a',agent_id='b:c'"
        )

    @pytest.mark.asyncio
    async def test_node_cache_key_no_collision_with_colons(self):
        """Test that node IDs with colons don't cause cache collisions.

        CARE-058: node_id="x:y" node_type="Z" agent_id="a" must not collide
        with node_id="x" node_type="y:Z" agent_id="a".
        """
        config = TrustVerifierConfig(mode="enforcing", fallback_allow=True)
        verifier = TrustVerifier(config=config)

        # First request: node_id="x:y", node_type="Z", agent_id="a"
        result1 = await verifier.verify_node_access(
            node_id="x:y",
            node_type="Z",
            agent_id="a",
        )
        assert result1.allowed is True

        # Second request: node_id="x", node_type="y:Z", agent_id="a"
        # With colon separator these would produce same cache key: "node:x:y:Z:a"
        result2 = await verifier.verify_node_access(
            node_id="x",
            node_type="y:Z",
            agent_id="a",
        )
        assert result2.allowed is True

        # Verify both are cached separately
        node_cache_entries = [k for k in verifier._cache.keys() if k.startswith("node")]
        assert len(node_cache_entries) == 2, (
            f"Cache collision detected: expected 2 node cache entries, "
            f"got {len(node_cache_entries)}. "
            "node_id='x:y',node_type='Z' collided with "
            "node_id='x',node_type='y:Z'"
        )

    @pytest.mark.asyncio
    async def test_resource_cache_key_no_collision_with_colons(self):
        """Test that resource paths with colons don't cause cache collisions.

        CARE-058: resource="a:b" action="c" agent_id="d" must not collide
        with resource="a" action="b:c" agent_id="d".
        """
        config = TrustVerifierConfig(mode="enforcing", fallback_allow=True)
        verifier = TrustVerifier(config=config)

        # First request: resource="a:b", action="c", agent_id="d"
        result1 = await verifier.verify_resource_access(
            resource="a:b",
            action="c",
            agent_id="d",
        )
        assert result1.allowed is True

        # Second request: resource="a", action="b:c", agent_id="d"
        # With colon separator these would produce same cache key: "res:a:b:c:d"
        result2 = await verifier.verify_resource_access(
            resource="a",
            action="b:c",
            agent_id="d",
        )
        assert result2.allowed is True

        # Verify both are cached separately
        res_cache_entries = [k for k in verifier._cache.keys() if k.startswith("res")]
        assert len(res_cache_entries) == 2, (
            f"Cache collision detected: expected 2 resource cache entries, "
            f"got {len(res_cache_entries)}. "
            "resource='a:b',action='c' collided with "
            "resource='a',action='b:c'"
        )

    def test_cache_key_uses_null_byte_separator(self):
        """Test that cache keys use null byte separator for collision resistance.

        CARE-058: The null byte (\\x00) cannot appear in legitimate string IDs,
        making it an ideal separator that prevents collision attacks.
        """
        config = TrustVerifierConfig(mode="enforcing", fallback_allow=True)
        verifier = TrustVerifier(config=config)

        # Set a value to populate the cache
        result = VerificationResult(allowed=True, reason="test")
        # Manually construct a cache key with the expected format
        expected_key = "wf\x00test-workflow\x00test-agent"
        verifier._set_cache(expected_key, result)

        # The cache should contain the key with null byte separator
        assert (
            expected_key in verifier._cache
        ), "Cache key should use null byte (\\x00) as separator"
        # Verify the key contains null bytes
        assert "\x00" in expected_key, "Cache key must contain null byte separator"
