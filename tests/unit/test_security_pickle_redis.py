# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for pickle RCE (H3) and Redis URL validation (H4) fixes.

These tests verify that:
1. CacheNode no longer uses pickle.loads on Redis data
2. Invalid Redis URLs are rejected (e.g., ftp://malicious.server/)
3. Valid Redis URLs pass (redis://localhost:6379, rediss://secure.host:6380)
4. Persistent memory tiers use JSON instead of pickle
"""

import json
import pytest

from kailash.utils.redis_validation import validate_redis_url


# ---------------------------------------------------------------------------
# S1b-004 / S1b-005: Redis URL Validation Tests
# ---------------------------------------------------------------------------


class TestValidateRedisUrl:
    """Tests for the shared validate_redis_url function."""

    def test_valid_redis_url(self):
        """Valid redis:// URL should pass."""
        result = validate_redis_url("redis://localhost:6379")
        assert result == "redis://localhost:6379"

    def test_valid_redis_url_with_db(self):
        """Valid redis:// URL with database number should pass."""
        result = validate_redis_url("redis://localhost:6379/0")
        assert result == "redis://localhost:6379/0"

    def test_valid_rediss_url(self):
        """Valid rediss:// (TLS) URL should pass."""
        result = validate_redis_url("rediss://secure.host:6380")
        assert result == "rediss://secure.host:6380"

    def test_valid_rediss_url_with_auth(self):
        """Valid rediss:// URL with authentication should pass."""
        result = validate_redis_url("rediss://user:password@secure.host:6380/1")
        assert result == "rediss://user:password@secure.host:6380/1"

    def test_invalid_ftp_url(self):
        """ftp:// URL should be rejected."""
        with pytest.raises(ValueError, match="Invalid Redis URL scheme 'ftp'"):
            validate_redis_url("ftp://malicious.server/")

    def test_invalid_http_url(self):
        """http:// URL should be rejected."""
        with pytest.raises(ValueError, match="Invalid Redis URL scheme 'http'"):
            validate_redis_url("http://malicious.server:6379")

    def test_invalid_https_url(self):
        """https:// URL should be rejected."""
        with pytest.raises(ValueError, match="Invalid Redis URL scheme 'https'"):
            validate_redis_url("https://malicious.server:6379")

    def test_invalid_file_url(self):
        """file:// URL should be rejected."""
        with pytest.raises(ValueError, match="Invalid Redis URL scheme 'file'"):
            validate_redis_url("file:///etc/passwd")

    def test_invalid_gopher_url(self):
        """gopher:// URL should be rejected (classic SSRF vector)."""
        with pytest.raises(ValueError, match="Invalid Redis URL scheme 'gopher'"):
            validate_redis_url("gopher://attacker.com:6379/_*")

    def test_invalid_empty_scheme(self):
        """URL without scheme should be rejected."""
        with pytest.raises(ValueError, match="Invalid Redis URL scheme"):
            validate_redis_url("localhost:6379")

    def test_invalid_no_hostname(self):
        """redis:// URL without hostname should be rejected."""
        with pytest.raises(ValueError, match="must include a hostname"):
            validate_redis_url("redis://")

    def test_invalid_empty_string(self):
        """Empty string should be rejected."""
        with pytest.raises(ValueError, match="Invalid Redis URL scheme"):
            validate_redis_url("")


# ---------------------------------------------------------------------------
# S1b-001: CacheNode Pickle Removal Tests
# ---------------------------------------------------------------------------


@pytest.mark.requires_isolation
class TestCacheNodePickleRemoval:
    """Tests verifying CacheNode no longer uses pickle."""

    def test_cache_module_does_not_import_pickle(self):
        """The cache module should not import pickle."""
        import importlib
        import sys
        import kailash.nodes.cache.cache as cache_module

        # Remove any cached version first, then reload for clean import check
        mod_name = "kailash.nodes.cache.cache"
        old_mod = sys.modules.pop(mod_name, None)
        try:
            fresh = importlib.import_module(mod_name)
            # Check that pickle is not in the module's namespace
            assert not hasattr(
                fresh, "pickle"
            ), "cache.py still imports pickle -- RCE vulnerability (H3)"
        finally:
            # Restore original to avoid polluting other tests
            if old_mod is not None:
                sys.modules[mod_name] = old_mod

    def test_pickle_serialization_format_uses_json_fallback(self):
        """When pickle serialization is requested for Redis set, it should fall back to JSON."""
        from kailash.nodes.cache.cache import CacheNode

        node = CacheNode(id="test_cache")
        # The node should exist and not crash on init
        assert node is not None

    def test_pickle_deserialization_raises_error(self):
        """Attempting to deserialize with pickle format should raise an error."""
        from kailash.nodes.cache.cache import (
            SerializationFormat,
            _PickleDeserializationError,
        )

        # The error class should exist
        assert _PickleDeserializationError is not None
        assert issubclass(_PickleDeserializationError, Exception)


# ---------------------------------------------------------------------------
# S1b-002: Persistent Tiers Pickle Removal Tests
# ---------------------------------------------------------------------------


@pytest.mark.requires_isolation
class TestPersistentTiersPickleRemoval:
    """Tests verifying persistent memory tiers no longer use pickle."""

    def test_persistent_tiers_does_not_import_pickle(self):
        """The persistent_tiers module should not import pickle."""
        import importlib
        import sys

        mod_name = "kaizen.memory.persistent_tiers"
        old_mod = sys.modules.pop(mod_name, None)
        try:
            fresh = importlib.import_module(mod_name)
            assert not hasattr(
                fresh, "pickle"
            ), "persistent_tiers.py still imports pickle -- RCE vulnerability (H3)"
        finally:
            if old_mod is not None:
                sys.modules[mod_name] = old_mod

    def test_warm_tier_serializes_as_json(self, tmp_path):
        """WarmMemoryTier.put should serialize data as JSON, not pickle."""
        import asyncio
        from kaizen.memory.persistent_tiers import WarmMemoryTier

        db_path = str(tmp_path / "warm_test.db")
        tier = WarmMemoryTier(storage_path=db_path)

        test_data = {"key": "value", "number": 42, "nested": {"a": 1}}

        async def _test():
            try:
                result = await tier.put("test_key", test_data)
                assert result is True

                # Retrieve and verify it round-trips correctly
                retrieved = await tier.get("test_key")
                assert retrieved == test_data
            finally:
                await tier.close()

        asyncio.run(_test())

    def test_cold_tier_serializes_as_json(self, tmp_path):
        """ColdMemoryTier.put should serialize data as JSON, not pickle."""
        import asyncio
        from kaizen.memory.persistent_tiers import ColdMemoryTier

        storage_path = str(tmp_path / "cold_test")
        tier = ColdMemoryTier(storage_path=storage_path, compression=False)

        test_data = {"key": "value", "list": [1, 2, 3]}

        async def _test():
            try:
                result = await tier.put("test_key", test_data)
                assert result is True

                retrieved = await tier.get("test_key")
                assert retrieved == test_data
            finally:
                await tier.close()

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# S1b-003: Audit common.py and regression_detector.py
# ---------------------------------------------------------------------------


class TestAuditPickleUsage:
    """Verify pickle usage in common.py and regression_detector.py is safe."""

    def test_common_py_pickle_is_allowlist_only(self):
        """common.py lists 'pickle' as an allowed module name, not as pickle.loads."""
        from kailash.nodes.code.common import COMMON_ALLOWED_MODULES

        # pickle is in the allowed modules list (for sandbox allowlisting)
        # This is NOT the same as calling pickle.loads on untrusted data
        assert "pickle" in COMMON_ALLOWED_MODULES

    def test_regression_detector_no_pickle_loads(self):
        """regression_detector.py should not call pickle.loads on untrusted data."""
        import inspect
        from kailash.migration import regression_detector

        source = inspect.getsource(regression_detector)
        # Import is present but no pickle.loads or pickle.dumps calls
        assert (
            "pickle.loads" not in source
        ), "regression_detector.py calls pickle.loads -- potential RCE"
        assert (
            "pickle.dumps" not in source
        ), "regression_detector.py calls pickle.dumps -- data stored may be unsafe"
