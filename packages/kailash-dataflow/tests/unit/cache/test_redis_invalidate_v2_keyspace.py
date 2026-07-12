# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for post-v2-keyspace Redis invalidation bug.

Context
-------

The BP-049 fix bumped the default cache keyspace from ``v1`` to ``v2``
in :class:`dataflow.cache.key_generator.CacheKeyGenerator`. Cross-SDK
parity with kailash-rs v3.19.0 — classified PKs are pre-hashed before
the ``params_hash`` is computed.

Post-release review found
:meth:`dataflow.cache.async_redis_adapter.AsyncRedisCacheAdapter.invalidate_model`
was still scanning hardcoded ``dataflow:v1:...`` patterns, so every
write-then-invalidate on Redis silently left v2 entries in place and
served stale reads indefinitely.

Fix: match the version segment as a wildcard (``v*``) so legacy v1
entries AND current v2 entries are swept in one invalidation call.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from dataflow.cache.async_redis_adapter import AsyncRedisCacheAdapter

pytestmark = [pytest.mark.regression]


@pytest.mark.asyncio
async def test_invalidate_model_scans_version_agnostic_patterns() -> None:
    """``invalidate_model`` MUST use ``v*`` so v2 entries are swept.

    The pre-fix pattern scanned ``dataflow:v1:...`` only, so the v2
    entries produced by BP-049 were never invalidated on Redis.
    """
    adapter = AsyncRedisCacheAdapter.__new__(AsyncRedisCacheAdapter)
    captured: list[str] = []

    async def fake_clear_pattern(pattern: str) -> int:
        captured.append(pattern)
        return 0

    adapter.clear_pattern = AsyncMock(side_effect=fake_clear_pattern)  # type: ignore[method-assign]

    await adapter.invalidate_model("User")
    await adapter.invalidate_model("User", tenant_id="acme")

    # Every pattern emitted MUST contain ``v*`` so both v1 legacy keys
    # and current v2 keys match.
    assert all("v*" in p for p in captured), (
        f"invalidate_model emitted a version-pinned pattern; this is "
        f"the pre-fix shape that leaked v2 cache entries past "
        f"invalidation. Patterns: {captured}"
    )
    # No pattern MUST pin ``v1`` only (the regression shape).
    assert not any(
        ":v1:" in p for p in captured
    ), f"invalidate_model still pins v1: {captured}"


@pytest.mark.asyncio
async def test_invalidate_model_regression_pin_v2_entries_swept() -> None:
    """Explicit regression pin: a v2-shaped key MUST match the pattern.

    If the fix regresses to a v1-pinned pattern, ``fnmatch`` against
    a v2 key will return False and this test fails. Behavioural, not
    source-grep (per ``rules/testing.md`` MUST rule).
    """
    import fnmatch

    adapter = AsyncRedisCacheAdapter.__new__(AsyncRedisCacheAdapter)
    captured: list[str] = []

    async def fake_clear_pattern(pattern: str) -> int:
        captured.append(pattern)
        return 0

    adapter.clear_pattern = AsyncMock(side_effect=fake_clear_pattern)  # type: ignore[method-assign]

    await adapter.invalidate_model("User", tenant_id="acme")

    # Sample v2 Express key (multi-tenant) as written by
    # CacheKeyGenerator at the pre-#1606 default keyspace. Legacy v2 entries
    # left on Redis after the v3 upgrade MUST still be swept (backward-compat).
    sample_v2_key = "dataflow:v2:acme:User:list:a1b2c3d4"
    assert any(fnmatch.fnmatchcase(sample_v2_key, p) for p in captured), (
        f"v2 key {sample_v2_key!r} did not match any invalidation "
        f"pattern {captured!r} — the v1→v2 keyspace bump from BP-049 "
        f"is not being cleared on Redis."
    )


@pytest.mark.asyncio
async def test_invalidate_model_regression_pin_v3_db_instance_keys_swept() -> None:
    """#1606: a v3 key WITH the inserted db-instance segment MUST be swept.

    The v3 keyspace (issue #1606 / the Rust SDK's #1713) inserts a
    ``db<16 hex>`` db-instance segment directly after the version, BEFORE the
    tenant: ``dataflow:v3:<db_instance>:<tenant>:<model>:<op>:<hash>``. This
    shifts every segment right by one, so this PROVES (not reasons) that the
    ``dataflow:v*:{tenant}:{model}:*`` invalidation glob still matches — the
    greedy ``*`` after ``v*`` spans the ``v3:<db_instance>`` prefix. Without
    this test the v2->v3 bump could silently break Redis invalidation of every
    express entry (``tenant-isolation.md §3a``). Behavioural via ``fnmatch``.
    """
    import fnmatch

    adapter = AsyncRedisCacheAdapter.__new__(AsyncRedisCacheAdapter)
    captured: list[str] = []

    async def fake_clear_pattern(pattern: str) -> int:
        captured.append(pattern)
        return 0

    adapter.clear_pattern = AsyncMock(side_effect=fake_clear_pattern)  # type: ignore[method-assign]

    # Model-wide AND tenant-scoped invalidation both emit patterns.
    await adapter.invalidate_model("User")
    await adapter.invalidate_model("User", tenant_id="acme")

    # Canonical v3 shapes (db-instance from express_db_instance_fingerprint).
    v3_single_tenant = "dataflow:v3:dbd4e3f17d35c2bb57:User:read:abc123"
    v3_multi_tenant = "dataflow:v3:dbd4e3f17d35c2bb57:acme:User:list:a1b2c3d4"
    for sample in (v3_single_tenant, v3_multi_tenant):
        assert any(fnmatch.fnmatchcase(sample, p) for p in captured), (
            f"v3 key {sample!r} did not match any invalidation pattern "
            f"{captured!r} — the #1606 db-instance segment broke Redis "
            f"invalidation of express entries."
        )
