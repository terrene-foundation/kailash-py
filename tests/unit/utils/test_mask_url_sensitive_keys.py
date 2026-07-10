# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Sensitive query-key masking — canonical set + normalized matcher.

A /redteam surfaced that the "sensitive query-string key" denylist used by
the connection-string maskers was matched by EXACT ``k.lower() in SET`` against
a short list (``password``/``sslpassword``/``sslkey``/``authtoken``/``token``/
``apikey``). Common credential param variants — ``access_token``, ``api_key``,
``pwd``, ``passwd``, ``secret``, ``client_secret``, ``access_key``, ``sslcert``,
and every underscore/hyphen spelling — were NOT masked and leaked into logs and
errors.

The fix establishes ONE canonical, expanded, frozen set plus a single
normalized-match helper (``is_sensitive_query_key``) in
``kailash.utils.url_credentials``. All four maskers reference it:

1. ``mask_url`` (the canonical masker used at ~19 call sites)
2. ``DatabaseConfig.get_masked_connection_string``
3. ``SecureLogger`` (log-field masking)
4. the Redis rate-limit backend ``_sanitize_url``

These tests lock in the behavior behaviorally — every assertion calls the real
helper / masker, never greps source (per ``rules/testing.md`` § Behavioral
Regression Tests). They cover: the new variants ARE masked, the over-masking
guard (legit non-secret params are NOT masked), consolidation across all four
sites, and regression on the originally-covered keys.
"""

from __future__ import annotations

import pytest

from kailash.config.database_config import DatabaseConfig
from kailash.trust.rate_limit.backends.redis import RedisBackend
from kailash.utils.secure_logging import SecureLogger
from kailash.utils.url_credentials import is_sensitive_query_key, mask_url

# Value that MUST never survive masking at any surface.
LEAK = "s3cr3t-leak-value"

# Credential query-key variants that MUST be masked. Includes underscore /
# hyphen / mixed-case spellings to prove the normalized matcher.
SENSITIVE_KEYS = [
    "password",
    "passwd",
    "pwd",
    "sslpassword",
    "secret",
    "client_secret",
    "client-secret",
    "clientsecret",
    "secret_key",
    "secretkey",
    "token",
    "authtoken",
    "auth_token",
    "apitoken",
    "api_token",
    "access_token",
    "access-token",
    "accesstoken",
    "apikey",
    "api_key",
    "access_key",
    "accesskey",
    "sslkey",
    "sslcert",
    "ssl_cert",
    "auth",
    # mixed-case to prove case-insensitivity
    "Access_Token",
    "API_KEY",
]

# Originally-covered keys — regression guard against the pre-fix set.
ORIGINAL_KEYS = ["password", "token", "apikey", "sslpassword", "sslkey", "authtoken"]

# Legitimate non-secret params that MUST NOT be masked (over-masking guard).
NON_SENSITIVE_KEYS = [
    "public_key",  # asymmetric public key is NOT a secret
    "publickey",
    "keyspace",  # blind "key in k" substring would wrongly mask this
    "timeout",
    "sslmode",
    "sslrootcert",  # a cert PATH, not a secret; distinct from sslcert
    "application_name",
    "connect_timeout",
    "host",
    "port",
    "dbname",
]


# ---------------------------------------------------------------------------
# is_sensitive_query_key — the single match point
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", SENSITIVE_KEYS)
def test_is_sensitive_query_key_flags_credential_variants(key):
    assert is_sensitive_query_key(key) is True, f"{key!r} should be sensitive"


@pytest.mark.parametrize("key", NON_SENSITIVE_KEYS)
def test_is_sensitive_query_key_allows_non_secret_params(key):
    assert is_sensitive_query_key(key) is False, f"{key!r} should NOT be sensitive"


def test_secret_key_masked_but_public_key_not():
    # The deliberate, pinned distinction: secret_key / access_key ARE secrets;
    # public_key is NOT. A blind substring match on "key" would break this.
    assert is_sensitive_query_key("secret_key") is True
    assert is_sensitive_query_key("access_key") is True
    assert is_sensitive_query_key("public_key") is False


# ---------------------------------------------------------------------------
# mask_url — the canonical masker
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", SENSITIVE_KEYS)
def test_mask_url_masks_sensitive_query_variant(key):
    url = f"postgresql://localhost:5432/db?{key}={LEAK}"
    masked = mask_url(url)
    assert LEAK not in masked, f"{key}={LEAK} leaked through mask_url: {masked}"
    # The masked value is url-encoded '***' → '%2A%2A%2A'.
    assert "%2A%2A%2A" in masked or "***" in masked


@pytest.mark.parametrize("key", ORIGINAL_KEYS)
def test_mask_url_regression_original_keys(key):
    url = f"postgresql://localhost:5432/db?{key}={LEAK}"
    assert LEAK not in mask_url(url)


@pytest.mark.parametrize("key", NON_SENSITIVE_KEYS)
def test_mask_url_does_not_mask_non_secret_params(key):
    # A benign value on a non-secret param must round-trip unchanged.
    benign = "benign-value-42"
    url = f"postgresql://localhost:5432/db?{key}={benign}"
    masked = mask_url(url)
    assert masked == url, f"over-masked non-secret param {key!r}: {masked}"
    assert benign in masked


def test_mask_url_multi_host_masks_new_variant():
    # MongoDB replica-set URL (comma-separated hosts) goes through the
    # hand-rolled multi-host path — it MUST honor the same canonical set.
    url = f"mongodb://h1:27017,h2:27017/db?access_token={LEAK}"
    masked = mask_url(url)
    assert LEAK not in masked


def test_mask_url_mixes_masked_and_unmasked_params():
    url = f"postgresql://localhost/db?access_token={LEAK}&sslmode=require&timeout=5"
    masked = mask_url(url)
    assert LEAK not in masked
    assert "sslmode=require" in masked
    assert "timeout=5" in masked


# ---------------------------------------------------------------------------
# get_masked_connection_string — Site 2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", SENSITIVE_KEYS)
def test_database_config_masks_sensitive_query_variant(key):
    cfg = DatabaseConfig(
        connection_string=f"postgresql://localhost:5432/db?{key}={LEAK}"
    )
    masked = cfg.get_masked_connection_string()
    assert LEAK not in masked, f"{key} leaked through get_masked_connection_string"


@pytest.mark.parametrize("key", ORIGINAL_KEYS)
def test_database_config_regression_original_keys(key):
    cfg = DatabaseConfig(
        connection_string=f"postgresql://localhost:5432/db?{key}={LEAK}"
    )
    assert LEAK not in cfg.get_masked_connection_string()


@pytest.mark.parametrize("key", NON_SENSITIVE_KEYS)
def test_database_config_does_not_mask_non_secret_params(key):
    benign = "benign-value-42"
    conn = f"postgresql://localhost:5432/db?{key}={benign}"
    cfg = DatabaseConfig(connection_string=conn)
    masked = cfg.get_masked_connection_string()
    assert masked == conn, f"over-masked non-secret param {key!r}: {masked}"


# ---------------------------------------------------------------------------
# Consolidation — all four sites resolve the SAME canonical set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["access_token", "api_key", "client_secret", "pwd"])
def test_all_four_sites_mask_the_same_new_variant(key):
    """A newly-covered variant is masked identically at every site."""
    # Site 1 — mask_url
    assert LEAK not in mask_url(f"redis://cache:6379/0?{key}={LEAK}")

    # Site 2 — get_masked_connection_string
    cfg = DatabaseConfig(connection_string=f"postgresql://h/db?{key}={LEAK}")
    assert LEAK not in cfg.get_masked_connection_string()

    # Site 3 — SecureLogger field masking (dict-field key match)
    masked_dict = SecureLogger("t")._mask_dict({key: LEAK})
    assert masked_dict[key] != LEAK
    assert LEAK not in str(masked_dict[key])

    # Site 4 — Redis rate-limit backend _sanitize_url
    sanitized = RedisBackend._sanitize_url(
        f"redis://cache:6379/0?{key}={LEAK}"
    )
    assert LEAK not in sanitized


def test_redis_backend_sanitize_url_masks_userinfo_and_new_variant():
    sanitized = RedisBackend._sanitize_url(
        f"redis://user:{LEAK}@cache:6379/0?access_token={LEAK}"
    )
    assert LEAK not in sanitized
    assert "***@cache" in sanitized


def test_secure_logger_still_masks_broader_pii():
    # Consolidation MUST NOT regress the broader PII coverage SecureLogger owns.
    masked = SecureLogger("t")._mask_dict({"ssn": "123-45-6789", "email": "a@b.com"})
    assert masked["ssn"] != "123-45-6789"
    assert masked["email"] != "a@b.com"


def test_secure_logger_does_not_mask_non_secret_field():
    masked = SecureLogger("t")._mask_dict({"public_key": "pk-abc", "keyspace": "ks1"})
    assert masked["public_key"] == "pk-abc"
    assert masked["keyspace"] == "ks1"
