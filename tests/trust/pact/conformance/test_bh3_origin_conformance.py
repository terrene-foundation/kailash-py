# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""BH3 origin-authentication (#1510) conformance — byte-pinned pre-image vectors.

This is a SIGNED CRYPTOGRAPHIC surface — byte-exactness is the security
property. Each vector pins the RAW canonical signing pre-image string + its
SHA-256; assertions compare the encoder's live output against the committed
bytes, NOT a ``startswith`` shape. The Rust SDK mirrors these EXACT bytes for
cross-implementation conformance (EATP D6 / ``rs#1707`` handoff).

``encoding="utf-8"`` on EVERY vector read is LOAD-BEARING (issue #1590
Windows-CI fix).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from kailash.trust._jcs import jcs_subject_hash
from kailash.trust.reasoning.origin import compute_origin_digest, origin_signing_payload
from kailash.trust.reasoning.traces import ReasoningTrace
from kailash.trust.signing.crypto import serialize_for_signing

VECTORS_DIR = Path(__file__).parent / "vectors"

BH3_VECTORS = [
    "bh3_origin_bound.json",
    "bh3_origin_unbound.json",
]


def _load_vector(name: str) -> dict:
    return json.loads((VECTORS_DIR / name).read_text(encoding="utf-8"))


class TestBh3OriginVectorIntegrity:
    """The BH3 family owns its own exact-set orphan check (mirrors weft/eatp3)."""

    def test_all_expected_bh3_vectors_present(self) -> None:
        actual = sorted(p.name for p in VECTORS_DIR.glob("bh3_*.json"))
        assert actual == sorted(BH3_VECTORS), (
            f"BH3 vector files mismatch.\n"
            f"Expected: {sorted(BH3_VECTORS)}\nActual:   {actual}"
        )


class TestBh3UnboundPreimage:
    """Without-origin form: byte-identical to the current trace pre-image."""

    def test_unbound_preimage_matches_pinned_bytes(self) -> None:
        vec = _load_vector("bh3_origin_unbound.json")
        trace = ReasoningTrace.from_dict(vec["input"]["trace"])
        preimage = serialize_for_signing(origin_signing_payload(trace))
        # Raw byte-pin — NOT a startswith.
        assert preimage == vec["expected_signing_preimage"]
        assert (
            hashlib.sha256(preimage.encode("utf-8")).hexdigest()
            == vec["expected_preimage_sha256"]
        )

    def test_unbound_preimage_is_byte_identical_to_current_trace_preimage(
        self,
    ) -> None:
        """The without-origin BH3 pre-image == the pre-BH3 ReasoningTrace
        pre-image, byte-for-byte (the backward-compat guarantee)."""
        vec = _load_vector("bh3_origin_unbound.json")
        trace = ReasoningTrace.from_dict(vec["input"]["trace"])
        bh3_preimage = serialize_for_signing(origin_signing_payload(trace))
        current_preimage = serialize_for_signing(trace.to_signing_payload())
        assert bh3_preimage == current_preimage
        # No 'origin' key leaked into the unbound signed bytes.
        assert '"origin"' not in bh3_preimage


class TestBh3BoundPreimage:
    """With-origin form: current pre-image + bound origin digest."""

    def test_bound_preimage_matches_pinned_bytes(self) -> None:
        vec = _load_vector("bh3_origin_bound.json")
        trace = ReasoningTrace.from_dict(vec["input"]["trace"])
        origin_digest = compute_origin_digest(vec["input"]["originating_instruction"])
        assert origin_digest == vec["expected_origin_digest"]
        preimage = serialize_for_signing(
            origin_signing_payload(trace, origin_digest=origin_digest)
        )
        # Raw byte-pin — NOT a startswith.
        assert preimage == vec["expected_signing_preimage"]
        assert (
            hashlib.sha256(preimage.encode("utf-8")).hexdigest()
            == vec["expected_preimage_sha256"]
        )

    def test_origin_digest_is_jcs_of_instruction(self) -> None:
        """The bound origin digest reuses #1590's RFC 8785 (JCS) encoder — the
        single true canonicalizer, NOT a second one."""
        vec = _load_vector("bh3_origin_bound.json")
        instruction = vec["input"]["originating_instruction"]
        assert vec["expected_origin_digest"] == jcs_subject_hash(instruction)

    def test_bound_preimage_extends_unbound_with_only_origin_key(self) -> None:
        """The with-origin pre-image differs from without-origin by EXACTLY the
        inserted 'origin' key — no other byte churn."""
        bound = _load_vector("bh3_origin_bound.json")["expected_signing_preimage"]
        unbound = _load_vector("bh3_origin_unbound.json")["expected_signing_preimage"]
        digest = _load_vector("bh3_origin_bound.json")["expected_origin_digest"]
        # Removing the origin segment from the bound pre-image yields the unbound.
        origin_segment = f'"origin":"{digest}",'
        assert origin_segment in bound
        assert bound.replace(origin_segment, "") == unbound
