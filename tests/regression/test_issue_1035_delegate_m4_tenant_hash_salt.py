# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for #1035 M4 — unsalted SHA-256 tenant-id hash.

Pre-fix, ``_tenant_id_hash`` in ``src/kailash/delegate/trust.py`` returned
``hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:8]`` for the
log-safe display form. For short tenant IDs (UUIDs, account-ID integers,
organization slugs), 8 hex chars of an unsalted SHA-256 prefix is
rainbow-reversible by a log reader who knows the tenant ID space.

Post-fix, ``_tenant_id_hash`` returns an 8-char prefix of
``HMAC-SHA-256(per_process_salt, tenant_id)``. The salt is per-process
(``secrets.token_bytes(32)`` cached lazily at module scope), never
persisted, never logged.

These tests pin the invariants that survive the fix and would fail loudly
if the salted path regressed to the unsalted form.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys

import pytest


@pytest.mark.regression
def test_tenant_id_hash_is_not_unsalted_sha256() -> None:
    """The unsalted-SHA-256 prefix MUST NOT be the hash output.

    A log reader who knows the tenant ID space can rainbow-precompute
    ``hashlib.sha256(id).hexdigest()[:8]`` for every candidate and reverse
    the 8-char prefix in O(N). Asserting inequality closes that class.
    """
    from kailash.delegate.trust import _tenant_id_hash

    raw = "acme-corp"
    unsalted = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    got = _tenant_id_hash(raw)
    assert got != unsalted, (
        "tenant-id hash regressed to unsalted SHA-256 prefix — rainbow-table "
        "reversibility on short tenant IDs is reopened"
    )


@pytest.mark.regression
def test_tenant_id_hash_is_within_process_stable() -> None:
    """Two calls within the same process MUST produce the same hash.

    Audit correlation depends on this — operators trace cascade-tenant
    violations across multiple log lines via the hash prefix. If the salt
    rotates per call, the correlation property the docstring claims breaks.
    """
    from kailash.delegate.trust import _tenant_id_hash

    raw = "acme-corp"
    assert _tenant_id_hash(raw) == _tenant_id_hash(raw)


@pytest.mark.regression
def test_tenant_id_hash_none_sentinel_preserved() -> None:
    """``None`` (Global variant) MUST render as the literal sentinel.

    The Global variant has no tenant id; the str(exc) form should read
    ``parent_tenant_hash=<none>`` so the message is human-recognizable.
    """
    from kailash.delegate.trust import _tenant_id_hash

    assert _tenant_id_hash(None) == "<none>"


@pytest.mark.regression
def test_tenant_id_hash_shape_is_8_lower_hex_chars() -> None:
    """The hash output MUST be exactly 8 lowercase hex chars.

    The :class:`CascadeTenantViolationError` message format depends on this
    shape; any drift to a different prefix length would change the str(exc)
    contract observability tests depend on.
    """
    from kailash.delegate.trust import _tenant_id_hash

    got = _tenant_id_hash("acme-corp")
    assert re.fullmatch(
        r"[0-9a-f]{8}", got
    ), f"hash output {got!r} is not 8 lowercase hex chars"


@pytest.mark.regression
def test_tenant_id_hash_salt_is_fresh_per_interpreter_process() -> None:
    """Same tenant_id in a NEW Python process MUST produce a DIFFERENT hash.

    The salt is per-process (regenerated on each interpreter startup) so a
    log reader cannot pre-compute the rainbow table for THIS process's
    tenant ID space — cross-process correlation is closed by design.
    A subprocess hash equal to the in-process hash would prove the salt is
    persisted (broken) or the implementation regressed to a deterministic
    digest (broken).
    """
    from kailash.delegate.trust import _tenant_id_hash

    in_process = _tenant_id_hash("acme-corp")

    # Run the same hash call in a fresh interpreter; the salt is freshly
    # generated there, so the output MUST differ from the in-process hash.
    snippet = (
        "from kailash.delegate.trust import _tenant_id_hash;"
        "import sys;sys.stdout.write(_tenant_id_hash('acme-corp'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess_hash = result.stdout.strip()
    assert re.fullmatch(
        r"[0-9a-f]{8}", subprocess_hash
    ), f"subprocess hash {subprocess_hash!r} not 8 hex chars; stderr={result.stderr!r}"
    assert subprocess_hash != in_process, (
        "subprocess hash equals in-process hash — salt is NOT fresh per "
        "interpreter; rainbow-table reversibility may be reopened across "
        "processes (or the implementation regressed to unsalted SHA-256)"
    )
