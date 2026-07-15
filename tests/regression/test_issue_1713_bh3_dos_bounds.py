# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: fail-closed resource bounds on the BH3 origin-digest ingress.

Issue #1713 — the BH3 origin digest (and the shared #1590 Audit-Anchor
`subject_hash`) ran an attacker-shaped ``Any`` through TWO unbounded recursive
passes (``canonical_scalars`` → ``_encode``) and a SHA-256 BEFORE any auth
check, an unauthenticated CPU/memory DoS. A crafted wide/large payload burns
unbounded CPU+memory; a deeply-nested payload drives the recursion toward
RecursionError (swallowed → False on the verify path, but propagated UNCAUGHT
on the sign path).

The fix adds a fail-closed bounded-traversal guard at the SHARED ingress
(``jcs_encode``) that rejects an oversize subject with a typed ``ValueError``
naming the exceeded limit BEFORE canonicalization/hashing runs.

These tests are BEHAVIORAL (call the function; assert raise/return) — never a
source-grep (per testing.md § "Behavioral Regression Tests Over Source-Grep").
Byte-neutrality (a valid in-bounds subject digests identically to pre-guard) is
asserted here and doubly pinned by the BH3 conformance vectors.
"""

from __future__ import annotations

import hashlib

import pytest

from kailash.trust._jcs import (
    MAX_DIGEST_CHILDREN,
    MAX_DIGEST_DEPTH,
    MAX_DIGEST_NODES,
    MAX_DIGEST_STRING_TOTAL_BYTES,
    jcs_encode,
    jcs_subject_hash,
)
from kailash.trust.reasoning.origin import (
    compute_origin_digest,
    sign_origin_bound_trace,
    verify_origin_bound_trace,
)
from kailash.trust.reasoning.traces import ReasoningTrace

pytestmark = pytest.mark.regression


# A valid, in-bounds originating instruction (the shape a real BH3 caller uses;
# mirrors tests/trust/pact/conformance/vectors/bh3_origin_bound.json).
VALID_INSTRUCTION = {
    "instruction": "deploy service X to staging",
    "issued_by": "D1-R1",
    "nonce": "abc123",
}

# A valid in-bounds trace (mirrors the bh3_origin_bound.json vector's trace).
VALID_TRACE_DICT = {
    "decision": "approve deploy",
    "rationale": "cost within envelope",
    "confidentiality": "restricted",
    "timestamp": "2026-01-15T10:30:00+00:00",
    "alternatives_considered": ["defer"],
    "evidence": [{"cost": 500}],
    "methodology": "cost_benefit",
    "confidence": 0.9,
}


def _deeply_nested(depth: int):
    """A list nested ``depth`` levels deep: [[[ ... ]]]."""
    node: object = "leaf"
    for _ in range(depth):
        node = [node]
    return node


# ---------------------------------------------------------------------------
# Over-limit DEEP nesting → typed error naming the depth limit.
# ---------------------------------------------------------------------------


def test_over_limit_deep_nesting_rejected_via_compute_origin_digest() -> None:
    payload = _deeply_nested(MAX_DIGEST_DEPTH + 5)
    with pytest.raises(ValueError, match="max nesting depth"):
        compute_origin_digest(payload)


def test_over_limit_deep_nesting_rejected_via_jcs_encode() -> None:
    payload = _deeply_nested(MAX_DIGEST_DEPTH + 5)
    with pytest.raises(ValueError) as exc:
        jcs_encode(payload)
    msg = str(exc.value)
    assert "origin-oversize-rejected" in msg
    assert "max nesting depth" in msg
    assert str(MAX_DIGEST_DEPTH) in msg  # names the limit


def test_deep_nesting_does_not_recursionerror_the_guard() -> None:
    # A payload deep enough to blow Python's default recursion limit MUST be
    # rejected as a clean ValueError, NOT a RecursionError — the guard traverses
    # iteratively so the sign path surfaces a typed error, not a stack blow-up.
    payload = _deeply_nested(10_000)
    with pytest.raises(ValueError, match="max nesting depth"):
        compute_origin_digest(payload)


# ---------------------------------------------------------------------------
# Over-limit WIDE (huge element count) → typed error naming the node limit.
# ---------------------------------------------------------------------------


def test_over_limit_node_count_rejected() -> None:
    # A single container with > MAX_DIGEST_CHILDREN elements is rejected by the
    # per-container children bound; grow past MAX_DIGEST_NODES by nesting so the
    # NODE bound is what trips.
    outer = [[i for i in range(MAX_DIGEST_CHILDREN)] for _ in range(500)]
    with pytest.raises(ValueError) as exc:
        jcs_encode(outer)
    msg = str(exc.value)
    assert "origin-oversize-rejected" in msg
    # Either the node bound or the (inner) children bound may trip first; both
    # are the wide-payload DoS defense. Assert a resource limit is named.
    assert (
        f"max total nodes (limit={MAX_DIGEST_NODES}" in msg
        or f"max children (limit={MAX_DIGEST_CHILDREN}" in msg
    )


def test_over_limit_children_names_the_children_limit() -> None:
    wide = list(range(MAX_DIGEST_CHILDREN + 1))
    with pytest.raises(ValueError, match="max children") as exc:
        compute_origin_digest(wide)
    assert str(MAX_DIGEST_CHILDREN) in str(exc.value)


# ---------------------------------------------------------------------------
# Over-limit LONG string → typed error naming the string/bytes limit.
# ---------------------------------------------------------------------------


def test_over_limit_long_string_rejected() -> None:
    payload = {"instruction": "A" * (MAX_DIGEST_STRING_TOTAL_BYTES + 1)}
    with pytest.raises(ValueError) as exc:
        compute_origin_digest(payload)
    msg = str(exc.value)
    assert "origin-oversize-rejected" in msg
    assert "max cumulative string length" in msg
    assert str(MAX_DIGEST_STRING_TOTAL_BYTES) in msg


# ---------------------------------------------------------------------------
# A valid, in-bounds subject → digests successfully AND byte-identically
# (behavior-invariance). Covers BOTH the sign and verify paths.
# ---------------------------------------------------------------------------

# Pinned pre-guard digest of VALID_INSTRUCTION (from the committed BH3 bound
# conformance vector). The guard MUST NOT alter this byte-for-byte.
EXPECTED_DIGEST = (
    "sha256:be309592b937446a1e63c99921f72d200a44096a5e8cd73a4e450271371276fc"
)


def test_in_bounds_subject_digests_byte_identically() -> None:
    digest = compute_origin_digest(VALID_INSTRUCTION)
    assert digest == EXPECTED_DIGEST  # byte-identical to pre-guard

    # jcs_encode output recomputes the same SHA-256.
    encoded = jcs_encode(VALID_INSTRUCTION)
    assert "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest() == digest
    assert jcs_subject_hash(VALID_INSTRUCTION) == digest


def test_in_bounds_sign_and_verify_roundtrip_unchanged() -> None:
    # Ed25519 keypair for the sign→verify round-trip (both paths run the guard).
    nacl = pytest.importorskip("nacl.signing")
    import base64

    signing_key = nacl.SigningKey.generate()
    private_key = base64.b64encode(bytes(signing_key)).decode("ascii")
    public_key = base64.b64encode(bytes(signing_key.verify_key)).decode("ascii")

    trace = ReasoningTrace.from_dict(VALID_TRACE_DICT)

    # SIGN path — computes the origin digest through the guarded ingress.
    record = sign_origin_bound_trace(
        trace,
        private_key,
        signed_by="D1-R1",
        originating_instruction=VALID_INSTRUCTION,
    )
    assert record.origin_bound is True
    assert record.origin_digest == EXPECTED_DIGEST  # byte-identical

    # VERIFY path — recomputes the origin digest through the guarded ingress.
    assert (
        verify_origin_bound_trace(
            record, public_key, originating_instruction=VALID_INSTRUCTION
        )
        is True
    )


def test_sign_path_surfaces_typed_error_not_recursionerror() -> None:
    # The sign path (origin.py:241) previously propagated an UNCAUGHT
    # RecursionError on a deeply-nested instruction; it now surfaces a clean
    # typed ValueError from the guard.
    nacl = pytest.importorskip("nacl.signing")
    import base64

    signing_key = nacl.SigningKey.generate()
    private_key = base64.b64encode(bytes(signing_key)).decode("ascii")

    trace = ReasoningTrace.from_dict(VALID_TRACE_DICT)
    with pytest.raises(ValueError, match="max nesting depth"):
        sign_origin_bound_trace(
            trace,
            private_key,
            signed_by="D1-R1",
            originating_instruction=_deeply_nested(10_000),
        )


def test_verify_path_fails_closed_on_oversize_instruction() -> None:
    # A bound record whose AUTHORITATIVE instruction (held by the verifier) is
    # oversize: the verify path catches the guard's ValueError and fails closed
    # to False (never raises out, never passes).
    nacl = pytest.importorskip("nacl.signing")
    import base64

    signing_key = nacl.SigningKey.generate()
    private_key = base64.b64encode(bytes(signing_key)).decode("ascii")
    public_key = base64.b64encode(bytes(signing_key.verify_key)).decode("ascii")

    trace = ReasoningTrace.from_dict(VALID_TRACE_DICT)
    record = sign_origin_bound_trace(
        trace,
        private_key,
        signed_by="D1-R1",
        originating_instruction=VALID_INSTRUCTION,
    )
    # Verifier presents an oversize authoritative instruction → fail-closed.
    assert (
        verify_origin_bound_trace(
            record, public_key, originating_instruction=_deeply_nested(10_000)
        )
        is False
    )
