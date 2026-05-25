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
from concurrent.futures import ThreadPoolExecutor

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


# ---------------------------------------------------------------------------
# R1-followup: eager init + thread-safety
#
# Pre-fix the salt was lazily initialized via ``_get_tenant_hash_salt()``;
# two concurrent first-callers could race on the ``is None`` check-and-set,
# witnessing different salt values on the same first-call boundary. The
# defense-in-depth fix initializes the salt eagerly at module-import time
# (serialized by Python's import lock). These tests pin both invariants.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_tenant_hash_salt_is_initialized_at_module_import() -> None:
    """``_TENANT_HASH_SALT`` MUST be a populated bytes value at import time.

    Pre-fix the module-scope binding was ``None`` until the first call to
    ``_get_tenant_hash_salt()``; this test confirms the eager-init form
    has the salt committed BEFORE any caller of ``_tenant_id_hash`` runs.
    A regression to lazy init would surface here because the value would
    be ``None`` (or absent entirely) immediately after import.
    """
    from kailash.delegate import trust as trust_mod

    # No prior call to _tenant_id_hash in this test body — the import
    # alone MUST be sufficient for the salt to be present and populated.
    salt = trust_mod._TENANT_HASH_SALT
    assert salt is not None, (
        "_TENANT_HASH_SALT is None after module import — regression to "
        "lazy init reopens the concurrent-first-caller race"
    )
    assert isinstance(salt, bytes), (
        f"_TENANT_HASH_SALT is not bytes (got {type(salt).__name__}) — "
        "the eager-init form MUST commit a bytes value at module scope"
    )
    assert len(salt) == 32, (
        f"_TENANT_HASH_SALT length is {len(salt)} bytes — the fix uses "
        "secrets.token_bytes(32); any drift would weaken the HMAC strength"
    )


@pytest.mark.regression
def test_tenant_hash_salt_thread_safe_under_concurrent_first_calls() -> None:
    """N concurrent first-callers MUST witness the same hash for the same id.

    Pre-fix the check-and-set window ``if _TENANT_HASH_SALT is None:`` was
    racy: two threads entering simultaneously both saw None, both called
    ``secrets.token_bytes(32)``, and the racing pair witnessed different
    hashes for the same tenant_id input.

    Post-fix the salt is committed at module import; every thread reads
    the same constant. This test asserts the structural invariant —
    all N concurrent callers return identical 8-char hashes for the
    same input — which would fail loudly under the lazy-init race.
    """
    from kailash.delegate.trust import _tenant_id_hash

    raw = "acme-corp"
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_tenant_id_hash, raw) for _ in range(10)]
        results = [f.result() for f in futures]

    unique = set(results)
    assert len(unique) == 1, (
        f"10 concurrent _tenant_id_hash(raw) calls produced "
        f"{len(unique)} distinct values: {unique}. Regression to lazy "
        f"init reopens the check-and-set race; the same tenant_id MUST "
        f"hash to one value within a process regardless of caller thread."
    )
