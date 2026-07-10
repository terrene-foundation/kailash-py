# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""One-shot generator for the BH3 origin-authentication (#1510) conformance vectors.

Byte-pins the TWO signed pre-image forms of an origin-bound action-trace:

* ``bh3_origin_unbound.json`` — the without-origin form; its signed pre-image is
  BYTE-IDENTICAL to the current (pre-BH3) ``ReasoningTrace`` signing pre-image.
* ``bh3_origin_bound.json`` — the with-origin form; the current pre-image PLUS a
  bound ``origin`` digest = ``sha256:<hex>`` over the RFC 8785 (JCS)
  canonicalization of the originating instruction.

Run with the repo on ``PYTHONPATH`` to (re)write the vector JSON into
``vectors/``. Re-run after an intentional canonical change, then re-pin
``PACT_VECTORS.sha256`` in the SAME commit (``cross-sdk-inspection.md`` Rule 4c).

The Rust SDK mirrors these EXACT bytes (EATP D6 / ``rs#1707`` handoff); the
pre-image is the cross-SDK contract, so the pinned field is the raw canonical
string + its SHA-256 — NOT a signature (signatures are key-dependent).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from kailash.trust._jcs import jcs_subject_hash
from kailash.trust.reasoning.origin import compute_origin_digest, origin_signing_payload
from kailash.trust.reasoning.traces import ConfidentialityLevel, ReasoningTrace
from kailash.trust.signing.crypto import serialize_for_signing

VECTORS = Path(__file__).parent / "vectors"

# A stable, fully-populated action-trace (deterministic timestamp).
_TS = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
_TRACE_FIELDS = dict(
    decision="approve deploy",
    rationale="cost within envelope",
    confidentiality=ConfidentialityLevel.RESTRICTED,
    timestamp=_TS,
    alternatives_considered=["defer"],
    evidence=[{"cost": 500}],
    methodology="cost_benefit",
    confidence=0.9,
)

# The authoritative originating instruction the verifier holds out-of-band.
_INSTRUCTION = {
    "instruction": "deploy service X to staging",
    "issued_by": "D1-R1",
    "nonce": "abc123",
}


def _trace() -> ReasoningTrace:
    return ReasoningTrace(**_TRACE_FIELDS)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _emit(name: str, obj: dict) -> None:
    path = VECTORS / name
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.name}: {_sha256(path.read_text(encoding='utf-8'))}")


def main() -> None:
    trace = _trace()
    trace_dict = trace.to_dict()

    # --- without-origin form: byte-identical to the current trace pre-image ---
    preimg_unbound = serialize_for_signing(origin_signing_payload(trace))
    _emit(
        "bh3_origin_unbound.json",
        {
            "description": (
                "BH3 origin-auth (#1510) — WITHOUT origin binding. The signed "
                "pre-image is BYTE-IDENTICAL to the current (pre-BH3) "
                "ReasoningTrace signing pre-image; no 'origin' key in the signed "
                "bytes. An unbound trace's signature verifies exactly as pre-BH3."
            ),
            "pact_type": "OriginBoundTrace",
            "conformance_requirement": "BH3-unbound",
            "origin_bound": False,
            "input": {"trace": trace_dict},
            "expected_signing_preimage": preimg_unbound,
            "expected_preimage_sha256": _sha256(preimg_unbound),
        },
    )

    # --- with-origin form: current pre-image + bound origin digest ---
    origin_digest = compute_origin_digest(_INSTRUCTION)
    # Cross-check: the origin digest is the JCS subject hash of the instruction.
    assert origin_digest == jcs_subject_hash(_INSTRUCTION)
    preimg_bound = serialize_for_signing(
        origin_signing_payload(trace, origin_digest=origin_digest)
    )
    _emit(
        "bh3_origin_bound.json",
        {
            "description": (
                "BH3 origin-auth (#1510) — WITH origin binding. The signed "
                "pre-image is the current trace pre-image PLUS a bound 'origin' "
                "digest = sha256:<hex> over the RFC 8785 (JCS) canonicalization "
                "of the originating instruction (reusing #1590's jcs_subject_hash). "
                "A trace whose declared origin digest != the digest of its TRUE "
                "originating instruction MUST fail authentication even with a "
                "valid Ed25519 signature."
            ),
            "pact_type": "OriginBoundTrace",
            "conformance_requirement": "BH3-bound",
            "origin_bound": True,
            "input": {
                "trace": trace_dict,
                "originating_instruction": _INSTRUCTION,
            },
            "expected_origin_digest": origin_digest,
            "expected_signing_preimage": preimg_bound,
            "expected_preimage_sha256": _sha256(preimg_bound),
        },
    )


if __name__ == "__main__":
    main()
