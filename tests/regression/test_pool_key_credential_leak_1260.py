"""Regression tests for issue #1260 — pool-key credential leak in logs/metrics.

`AsyncSQLDatabaseNode` connection-pool keys have the shape
``loop_id|db_type|connection_string|min|max`` (per ``_generate_pool_key``);
the third segment is a raw connection string that can carry
``user:password@`` credentials. Several pool-lifecycle log sites
(disposal, cleanup, lock contention) interpolated the full key at
WARN/ERROR level — which ships to log aggregators (broader access than the
DB) — and the Prometheus metrics layer used the raw key as a label value.
The fix routes every such site through
``kailash.utils.url_credentials.redact_pool_key``.

These tests lock the fix in BEHAVIORALLY — they call the real helper and
the real caller paths (the disposal log path, ``PoolExhaustedError``, the
metrics recorder) and assert the credential never appears, rather than
grepping source. Per ``rules/testing.md`` § Behavioral Regression Tests,
source-grep tests break on refactor to a shared helper.
"""

from __future__ import annotations

import logging

import pytest

from kailash.utils.url_credentials import redact_pool_key

# Canonical secret — must never appear in any redacted output or log line.
SECRET = "s3cr3t-p4ssw0rd-shh"

# A realistic AsyncSQLDatabaseNode pool key (5 |-segments, conn URL in seg 2).
COMPOSITE_KEY = (
    f"140234|postgresql|postgresql://admin:{SECRET}@db.internal:5432/kailash|5|20"
)
# The fallback-pool form prefixes ``fallback_<id>_`` onto the whole key.
FALLBACK_KEY = f"fallback_4567_140234|postgresql|postgresql://admin:{SECRET}@db.internal:5432/kailash|5|20"
# Redis pool keys are ``<redis_url>/db<n>`` — whole-string URL, no |-segments.
REDIS_KEY = f"redis://:{SECRET}@cache.internal:6379/db0"
# The host:port:db:user fallback form carries NO password and is not a URL.
HOST_FORM_KEY = "140234|postgresql|db.internal:5432:kailash:alice|5|20"


@pytest.mark.regression
class TestRedactPoolKeyContract:
    """``redact_pool_key`` masks credentials, preserves correlation segments."""

    def test_composite_key_masks_connection_string_segment(self):
        out = redact_pool_key(COMPOSITE_KEY)
        assert SECRET not in out
        assert "***" in out
        # Non-credential segments survive for forensic correlation.
        assert out.startswith("140234|postgresql|")
        assert out.endswith("|5|20")
        assert "db.internal:5432" in out  # host preserved

    def test_fallback_prefixed_key_masks_embedded_connection_string(self):
        out = redact_pool_key(FALLBACK_KEY)
        assert SECRET not in out
        assert "***" in out
        # The fallback_<id> prefix segment is preserved verbatim.
        assert out.startswith("fallback_4567_140234|postgresql|")

    def test_redis_url_key_masks_whole_url(self):
        out = redact_pool_key(REDIS_KEY)
        assert SECRET not in out
        assert "***" in out
        assert "cache.internal:6379" in out  # host + db index preserved
        assert out.endswith("/db0")

    def test_host_fallback_form_unchanged_no_password(self):
        # ``host:port:db:user`` has no password and no "://" — leave it intact
        # so host context survives; masking it would discard useful data.
        assert redact_pool_key(HOST_FORM_KEY) == HOST_FORM_KEY

    def test_empty_and_none_return_empty_string(self):
        assert redact_pool_key("") == ""
        assert redact_pool_key(None) == ""  # type: ignore[arg-type]

    def test_non_credential_composite_key_unchanged(self):
        # A conn URL with no userinfo has nothing to mask.
        key = "140234|postgresql|postgresql://db.internal:5432/kailash|5|20"
        assert redact_pool_key(key) == key

    def test_deterministic_for_correlation(self):
        # Same input → same output, so log/metric correlation still works
        # AND Prometheus label cardinality stays bounded.
        assert redact_pool_key(COMPOSITE_KEY) == redact_pool_key(COMPOSITE_KEY)

    @pytest.mark.parametrize(
        "scheme", ["postgresql", "mysql", "mariadb", "cockroachdb"]
    )
    def test_masks_across_sql_schemes(self, scheme):
        key = f"140234|{scheme}|{scheme}://u:{SECRET}@h:5432/db|5|20"
        out = redact_pool_key(key)
        assert SECRET not in out
        assert "***" in out

    def test_pipe_in_password_does_not_leak_tail(self):
        # A literal '|' in the password over-splits the key into >5 parts;
        # the helper must reconstruct the middle so the password TAIL after
        # the '|' is not left in a raw trailing segment.
        key = f"140234|postgresql|postgresql://u:pa|{SECRET}@h:5432/db|5|20"
        out = redact_pool_key(key)
        assert SECRET not in out
        assert "pa|" not in out or "***" in out  # masked, not raw
        assert "***" in out
        assert out.startswith("140234|postgresql|")
        assert out.endswith("|5|20")


@pytest.mark.regression
class TestPoolExhaustedErrorRedaction:
    """``PoolExhaustedError`` message + ``.pool_key`` attribute are redacted."""

    def test_message_does_not_leak_credentials(self):
        from kailash.nodes.data.exceptions import PoolExhaustedError

        err = PoolExhaustedError(current=100, cap=100, pool_key=COMPOSITE_KEY)
        msg = str(err)
        assert SECRET not in msg
        assert "***" in msg

    def test_pool_key_attribute_is_redacted(self):
        from kailash.nodes.data.exceptions import PoolExhaustedError

        err = PoolExhaustedError(current=100, cap=100, pool_key=COMPOSITE_KEY)
        assert SECRET not in err.pool_key
        assert "***" in err.pool_key

    def test_credential_free_key_survives_for_correlation(self):
        # The host-form key (no password) must round-trip unchanged so the
        # forensic-correlation contract the attribute documents still holds.
        from kailash.nodes.data.exceptions import PoolExhaustedError

        err = PoolExhaustedError(current=5, cap=5, pool_key="loop|pg|h:p|10|20")
        assert err.pool_key == "loop|pg|h:p|10|20"


@pytest.mark.regression
class TestClearSharedPoolsLogRedaction:
    """The disposal log path emits no raw connection string (issue #1260 AC)."""

    @pytest.mark.asyncio
    async def test_disposal_warning_redacts_credentials(self, caplog):
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        # Unique loop_id so the loop-scoped clear touches ONLY our pool and
        # leaves any concurrently-registered pools untouched.
        loop_id = 999_000_111
        key = f"{loop_id}|postgresql|postgresql://admin:{SECRET}@db.internal:5432/kailash|5|20"

        class _BoomAdapter:
            async def disconnect(self):
                # Force the ``except Exception`` WARNING disposal branch,
                # which interpolates the pool key into the log message.
                raise RuntimeError("simulated disconnect failure")

        AsyncSQLDatabaseNode._shared_pools[key] = (_BoomAdapter(), 1)  # type: ignore[assignment]
        try:
            with caplog.at_level(logging.DEBUG):
                await AsyncSQLDatabaseNode.clear_shared_pools(
                    graceful=True, loop_id=loop_id
                )
        finally:
            AsyncSQLDatabaseNode._shared_pools.pop(key, None)

        full_log = " ".join(rec.getMessage() for rec in caplog.records)
        # A WARNING about the disconnect failure must have been emitted...
        assert "simulated disconnect failure" in full_log
        # ...but it MUST NOT carry the raw credential, and the host must be
        # masked to the canonical ``***@host`` form.
        assert SECRET not in full_log
        assert "***" in full_log


@pytest.mark.regression
class TestReturnValueSurfaceRedaction:
    """Diagnostic RETURN surfaces never expose the raw credential-bearing key."""

    @pytest.mark.asyncio
    async def test_get_pool_metrics_redacts_key(self):
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        loop_id = 999_000_222
        key = f"{loop_id}|postgresql|postgresql://admin:{SECRET}@db.internal:5432/kailash|5|20"

        class _StubAdapter:
            _pool = None

        AsyncSQLDatabaseNode._shared_pools[key] = (_StubAdapter(), 1)  # type: ignore[assignment]
        try:
            metrics = await AsyncSQLDatabaseNode.get_pool_metrics()
        finally:
            AsyncSQLDatabaseNode._shared_pools.pop(key, None)

        keys = [p["key"] for p in metrics["pools"]]
        blob = " ".join(keys)
        assert SECRET not in blob
        # Our injected pool appears, redacted.
        assert any(k.startswith(f"{loop_id}|postgresql|") and "***" in k for k in keys)

    def test_pool_keys_returns_redacted(self):
        from kailash.nodes.data.async_sql import (
            _PROCESS_POOL_REGISTRY,
            AsyncSQLDatabaseNode,
        )

        key = f"888000333|postgresql|postgresql://admin:{SECRET}@db.internal:5432/kailash|5|20"

        class _Live:  # weak-referenceable value for the WeakValueDictionary
            pass

        live = _Live()
        _PROCESS_POOL_REGISTRY[key] = live  # type: ignore[assignment]
        try:
            keys = AsyncSQLDatabaseNode.pool_keys()
        finally:
            _PROCESS_POOL_REGISTRY.pop(key, None)

        blob = " ".join(keys)
        assert SECRET not in blob
        assert any("***" in k and k.startswith("888000333|") for k in keys)


@pytest.mark.regression
class TestMetricsLabelRedaction:
    """Prometheus pool_key labels never carry the raw connection string."""

    def test_pool_operation_label_is_redacted(self):
        prometheus_client = pytest.importorskip("prometheus_client")
        from kailash.monitoring.asyncsql_metrics import AsyncSQLMetrics

        registry = prometheus_client.CollectorRegistry()
        metrics = AsyncSQLMetrics(enabled=True, registry=registry)
        metrics.record_pool_operation(COMPOSITE_KEY, "cleanup")
        metrics.record_lock_acquisition(COMPOSITE_KEY, "timeout", wait_time=0.5)
        metrics.set_active_locks(COMPOSITE_KEY, 3)

        exposition = prometheus_client.generate_latest(registry).decode("utf-8")
        assert SECRET not in exposition
        assert "***" in exposition
