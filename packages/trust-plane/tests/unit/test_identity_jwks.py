# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for JWKSProvider JWKS discovery and caching.

Tier 1 (Unit): Tests JWKSProvider behavior by mocking HTTP calls.
These tests verify discovery, caching, TTL expiry, key rotation,
and error handling without making real network requests.
"""

from __future__ import annotations

import time
from unittest import mock

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from trustplane.identity import (
    JWKSProvider,
)
from trustplane.identity import JWKSError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rsa_key_to_jwk(public_key: RSAPublicKey, kid: str = "test-key-1") -> dict:
    """Convert an RSA public key to a JWK dict."""
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
    import base64

    numbers = public_key.public_numbers()

    def _b64url(n: int, length: int) -> str:
        return (
            base64.urlsafe_b64encode(n.to_bytes(length, "big"))
            .decode("ascii")
            .rstrip("=")
        )

    n_bytes = (numbers.n.bit_length() + 7) // 8
    return {
        "kty": "RSA",
        "kid": kid,
        "alg": "RS256",
        "use": "sig",
        "n": _b64url(numbers.n, n_bytes),
        "e": _b64url(numbers.e, 3),
    }


@pytest.fixture
def rsa_key_and_jwk():
    """Generate an RSA key pair and corresponding JWK."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    jwk = _rsa_key_to_jwk(public_key, kid="test-key-1")
    return private_pem, jwk


@pytest.fixture
def second_rsa_key_and_jwk():
    """Generate a second RSA key pair for key rotation tests."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    jwk = _rsa_key_to_jwk(public_key, kid="rotated-key-2")
    return private_key, jwk


def _make_discovery_response(jwks_uri: str) -> dict:
    """Create a minimal OIDC discovery document."""
    return {
        "issuer": "https://idp.example.com",
        "jwks_uri": jwks_uri,
        "authorization_endpoint": "https://idp.example.com/authorize",
        "token_endpoint": "https://idp.example.com/token",
    }


def _make_jwks_response(keys: list[dict]) -> dict:
    """Create a JWKS response containing the given keys."""
    return {"keys": keys}


# ---------------------------------------------------------------------------
# JWKSProvider Tests
# ---------------------------------------------------------------------------


class TestJWKSProvider:
    """Test JWKSProvider JWKS discovery and caching."""

    def test_empty_issuer_url_raises(self):
        with pytest.raises(ValueError, match="issuer_url must not be empty"):
            JWKSProvider("")

    def test_trailing_slash_stripped(self):
        provider = JWKSProvider("https://idp.example.com/")
        assert provider._issuer_url == "https://idp.example.com"

    def test_empty_kid_raises(self):
        provider = JWKSProvider("https://idp.example.com")
        with pytest.raises(JWKSError, match="missing 'kid'"):
            provider.get_key("")

    def test_discovery_and_fetch(self, rsa_key_and_jwk):
        """End-to-end: discover JWKS URI, fetch keys, return matching key."""
        _, jwk = rsa_key_and_jwk
        jwks_uri = "https://idp.example.com/.well-known/jwks.json"
        discovery = _make_discovery_response(jwks_uri)
        jwks = _make_jwks_response([jwk])

        provider = JWKSProvider("https://idp.example.com")

        call_count = 0

        def mock_get(url):
            nonlocal call_count
            call_count += 1
            if ".well-known/openid-configuration" in url:
                return discovery
            return jwks

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            result = provider.get_key("test-key-1")

        assert result["kid"] == "test-key-1"
        assert result["kty"] == "RSA"
        assert call_count == 2  # discovery + JWKS fetch

    def test_cache_hit_avoids_refetch(self, rsa_key_and_jwk):
        """Once keys are cached, get_key should not re-fetch."""
        _, jwk = rsa_key_and_jwk
        jwks_uri = "https://idp.example.com/.well-known/jwks.json"
        discovery = _make_discovery_response(jwks_uri)
        jwks = _make_jwks_response([jwk])

        provider = JWKSProvider("https://idp.example.com", ttl_seconds=3600)

        call_count = 0

        def mock_get(url):
            nonlocal call_count
            call_count += 1
            if ".well-known/openid-configuration" in url:
                return discovery
            return jwks

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            provider.get_key("test-key-1")
            # Second call should be a cache hit — no additional HTTP requests.
            result = provider.get_key("test-key-1")

        assert result["kid"] == "test-key-1"
        assert call_count == 2  # Only the initial discovery + fetch

    def test_ttl_expiry_triggers_refetch(self, rsa_key_and_jwk):
        """After TTL expires, get_key should re-fetch the JWKS."""
        _, jwk = rsa_key_and_jwk
        jwks_uri = "https://idp.example.com/.well-known/jwks.json"
        discovery = _make_discovery_response(jwks_uri)
        jwks = _make_jwks_response([jwk])

        provider = JWKSProvider("https://idp.example.com", ttl_seconds=60)

        call_count = 0

        def mock_get(url):
            nonlocal call_count
            call_count += 1
            if ".well-known/openid-configuration" in url:
                return discovery
            return jwks

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            provider.get_key("test-key-1")
            assert call_count == 2  # discovery + fetch

            # Simulate TTL expiry by backdating the last fetch time.
            provider._last_fetch_time = time.monotonic() - 120

            provider.get_key("test-key-1")
            # Should have re-fetched JWKS (but not re-discovered since
            # jwks_uri is cached).
            assert call_count == 3  # +1 JWKS re-fetch

    def test_kid_mismatch_triggers_refetch(
        self, rsa_key_and_jwk, second_rsa_key_and_jwk
    ):
        """When kid is not in cache, re-fetch even if TTL is valid."""
        _, jwk1 = rsa_key_and_jwk
        _, jwk2 = second_rsa_key_and_jwk
        jwks_uri = "https://idp.example.com/.well-known/jwks.json"
        discovery = _make_discovery_response(jwks_uri)

        provider = JWKSProvider("https://idp.example.com", ttl_seconds=3600)

        fetch_number = 0

        def mock_get(url):
            nonlocal fetch_number
            if ".well-known/openid-configuration" in url:
                return discovery
            fetch_number += 1
            if fetch_number == 1:
                # First fetch returns only key 1.
                return _make_jwks_response([jwk1])
            # Second fetch returns both keys (simulating rotation).
            return _make_jwks_response([jwk1, jwk2])

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            result1 = provider.get_key("test-key-1")
            assert result1["kid"] == "test-key-1"

            # Requesting a kid not in cache triggers re-fetch.
            result2 = provider.get_key("rotated-key-2")
            assert result2["kid"] == "rotated-key-2"

    def test_kid_not_found_after_refetch_raises(self, rsa_key_and_jwk):
        """If kid is still missing after a fresh fetch, raise JWKSError."""
        _, jwk = rsa_key_and_jwk
        jwks_uri = "https://idp.example.com/.well-known/jwks.json"
        discovery = _make_discovery_response(jwks_uri)
        jwks = _make_jwks_response([jwk])

        provider = JWKSProvider("https://idp.example.com")

        def mock_get(url):
            if ".well-known/openid-configuration" in url:
                return discovery
            return jwks

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            with pytest.raises(JWKSError, match="nonexistent-kid.*not found"):
                provider.get_key("nonexistent-kid")

    def test_invalid_jwks_missing_keys_field(self):
        """JWKS response without 'keys' field raises JWKSError."""
        provider = JWKSProvider("https://idp.example.com")
        provider._jwks_uri = "https://idp.example.com/.well-known/jwks.json"

        def mock_get(url):
            return {"not_keys": []}

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            with pytest.raises(JWKSError, match="missing required 'keys'"):
                provider.get_key("any-kid")

    def test_invalid_jwks_keys_not_array(self):
        """JWKS response with non-array 'keys' raises JWKSError."""
        provider = JWKSProvider("https://idp.example.com")
        provider._jwks_uri = "https://idp.example.com/.well-known/jwks.json"

        def mock_get(url):
            return {"keys": "not-an-array"}

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            with pytest.raises(JWKSError, match="must be an array"):
                provider.get_key("any-kid")

    def test_invalid_jwks_not_json_object(self):
        """JWKS response that is not a JSON object raises JWKSError."""
        provider = JWKSProvider("https://idp.example.com")
        provider._jwks_uri = "https://idp.example.com/.well-known/jwks.json"

        def mock_get(url):
            return [1, 2, 3]  # Array instead of object

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            with pytest.raises(JWKSError, match="must be a JSON object"):
                provider.get_key("any-kid")

    def test_keys_without_kid_skipped(self):
        """Keys missing 'kid' are silently skipped."""
        provider = JWKSProvider("https://idp.example.com")
        provider._jwks_uri = "https://idp.example.com/.well-known/jwks.json"

        # One key with kid, one without.
        keys = [
            {"kty": "RSA", "n": "abc", "e": "AQAB"},  # No kid
            {"kty": "RSA", "kid": "good-key", "n": "abc", "e": "AQAB"},
        ]

        def mock_get(url):
            return {"keys": keys}

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            result = provider.get_key("good-key")
            assert result["kid"] == "good-key"

    def test_keys_without_kty_skipped(self):
        """Keys missing 'kty' are silently skipped."""
        provider = JWKSProvider("https://idp.example.com")
        provider._jwks_uri = "https://idp.example.com/.well-known/jwks.json"

        keys = [
            {"kid": "no-kty-key", "n": "abc", "e": "AQAB"},  # No kty
            {"kty": "RSA", "kid": "good-key", "n": "abc", "e": "AQAB"},
        ]

        def mock_get(url):
            return {"keys": keys}

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            result = provider.get_key("good-key")
            assert result["kid"] == "good-key"

    def test_unsupported_algorithm_skipped(self):
        """Keys with unsupported algorithms are skipped."""
        provider = JWKSProvider("https://idp.example.com")
        provider._jwks_uri = "https://idp.example.com/.well-known/jwks.json"

        keys = [
            {"kty": "RSA", "kid": "unsupported", "alg": "PS256", "n": "a", "e": "AQAB"},
            {"kty": "RSA", "kid": "supported", "alg": "RS256", "n": "b", "e": "AQAB"},
        ]

        def mock_get(url):
            return {"keys": keys}

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            result = provider.get_key("supported")
            assert result["kid"] == "supported"

    def test_encryption_keys_skipped(self):
        """Keys with use='enc' (encryption) are skipped."""
        provider = JWKSProvider("https://idp.example.com")
        provider._jwks_uri = "https://idp.example.com/.well-known/jwks.json"

        keys = [
            {"kty": "RSA", "kid": "enc-key", "use": "enc", "n": "a", "e": "AQAB"},
            {"kty": "RSA", "kid": "sig-key", "use": "sig", "n": "b", "e": "AQAB"},
        ]

        def mock_get(url):
            return {"keys": keys}

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            result = provider.get_key("sig-key")
            assert result["kid"] == "sig-key"

    def test_no_usable_keys_raises(self):
        """JWKS with no usable signing keys raises JWKSError."""
        provider = JWKSProvider("https://idp.example.com")
        provider._jwks_uri = "https://idp.example.com/.well-known/jwks.json"

        # All keys have unsupported algorithms.
        keys = [
            {"kty": "RSA", "kid": "k1", "alg": "PS512", "n": "a", "e": "AQAB"},
        ]

        def mock_get(url):
            return {"keys": keys}

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            with pytest.raises(JWKSError, match="no usable signing keys"):
                provider.get_key("k1")

    def test_discovery_missing_jwks_uri(self):
        """OIDC discovery without jwks_uri raises JWKSError."""
        provider = JWKSProvider("https://idp.example.com")

        def mock_get(url):
            return {"issuer": "https://idp.example.com"}  # No jwks_uri

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            with pytest.raises(JWKSError, match="missing required 'jwks_uri'"):
                provider.get_key("any-kid")

    def test_discovery_non_https_jwks_uri_raises(self):
        """OIDC discovery with non-HTTPS jwks_uri raises JWKSError."""
        provider = JWKSProvider("https://idp.example.com")

        def mock_get(url):
            return {
                "issuer": "https://idp.example.com",
                "jwks_uri": "http://idp.example.com/jwks",  # HTTP, not HTTPS
            }

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            with pytest.raises(JWKSError, match="HTTPS URL"):
                provider.get_key("any-kid")

    def test_discovery_non_dict_response_raises(self):
        """OIDC discovery returning a non-dict raises JWKSError."""
        provider = JWKSProvider("https://idp.example.com")

        def mock_get(url):
            return "not a dict"

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            with pytest.raises(JWKSError, match="must be a JSON object"):
                provider.get_key("any-kid")

    def test_unreachable_endpoint(self):
        """Network errors during fetch raise JWKSError."""
        provider = JWKSProvider("https://idp.example.com")

        def mock_get(url):
            raise JWKSError(f"Failed to connect to {url}: connection refused")

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            with pytest.raises(JWKSError, match="Failed to connect"):
                provider.get_key("any-kid")

    def test_http_error_during_fetch(self):
        """HTTP errors (e.g., 404) are wrapped in JWKSError."""
        provider = JWKSProvider("https://idp.example.com")

        def mock_get(url):
            raise JWKSError(f"HTTP 404 fetching {url}: Not Found")

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            with pytest.raises(JWKSError, match="HTTP 404"):
                provider.get_key("any-kid")

    def test_is_cache_valid_false_when_empty(self):
        """Cache is invalid when no keys have been fetched."""
        provider = JWKSProvider("https://idp.example.com")
        assert provider._is_cache_valid() is False

    def test_is_cache_valid_true_within_ttl(self, rsa_key_and_jwk):
        """Cache is valid within TTL."""
        _, jwk = rsa_key_and_jwk
        provider = JWKSProvider("https://idp.example.com", ttl_seconds=3600)
        provider._keys = {"test-key-1": jwk}
        provider._last_fetch_time = time.monotonic()
        assert provider._is_cache_valid() is True

    def test_is_cache_valid_false_after_ttl(self, rsa_key_and_jwk):
        """Cache is invalid after TTL expires."""
        _, jwk = rsa_key_and_jwk
        provider = JWKSProvider("https://idp.example.com", ttl_seconds=60)
        provider._keys = {"test-key-1": jwk}
        provider._last_fetch_time = time.monotonic() - 120  # 2 minutes ago
        assert provider._is_cache_valid() is False

    def test_keys_without_alg_accepted(self):
        """Keys without an explicit 'alg' field should be accepted."""
        provider = JWKSProvider("https://idp.example.com")
        provider._jwks_uri = "https://idp.example.com/.well-known/jwks.json"

        keys = [
            {"kty": "RSA", "kid": "no-alg-key", "n": "abc", "e": "AQAB"},
        ]

        def mock_get(url):
            return {"keys": keys}

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            result = provider.get_key("no-alg-key")
            assert result["kid"] == "no-alg-key"

    def test_jwks_uri_cached_across_fetches(self, rsa_key_and_jwk):
        """The discovered jwks_uri is reused on subsequent fetches."""
        _, jwk = rsa_key_and_jwk
        jwks_uri = "https://idp.example.com/.well-known/jwks.json"
        discovery = _make_discovery_response(jwks_uri)
        jwks = _make_jwks_response([jwk])

        provider = JWKSProvider("https://idp.example.com", ttl_seconds=1)

        discovery_calls = 0

        def mock_get(url):
            nonlocal discovery_calls
            if ".well-known/openid-configuration" in url:
                discovery_calls += 1
                return discovery
            return jwks

        with mock.patch.object(provider, "_http_get_json", side_effect=mock_get):
            provider.get_key("test-key-1")
            assert discovery_calls == 1

            # Expire the cache
            provider._last_fetch_time = time.monotonic() - 10

            # Second fetch should NOT re-discover.
            provider.get_key("test-key-1")
            assert discovery_calls == 1  # Still 1, no re-discovery
