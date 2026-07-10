# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""BH3 origin-authentication for the EATP/PACT trust plane (issue #1510).

SAFR v1.0 (§ The Governance Envelope) *recommends* that an agent-declared
action-trace be "authenticated against its origin, not merely as a record of
what the agent reported." SAFR is a non-binding white paper; this module
*specifies* the concrete cryptographic contract the recommendation implies for
this SDK.

The gap this closes: an Ed25519 signature over a reasoning/action trace proves
INTEGRITY — the bytes the agent submitted were not tampered after signing. It
does NOT prove ORIGIN — a compromised (but key-holding) agent can sign a
perfectly valid trace while LYING about which instruction originated it. BH3
binds the *originating instruction's* digest into the signed pre-image so a
verifier holding the authoritative instruction can reject a fabricated trace
EVEN WHEN its signature verifies.

Two signed pre-image forms (mirroring the issue #1590 conditional-``subject_hash``
pattern on the Ed25519-signed trace surface):

1. **without origin binding** — byte-IDENTICAL to the CURRENT
   :meth:`ReasoningTrace.to_signing_payload` pre-image (backward-compatible; no
   ``origin`` key in the signed bytes). An unbound trace's signature verifies
   exactly as it did pre-BH3.
2. **with origin binding** — the current pre-image PLUS a bound ``origin``
   digest = ``sha256:<hex>`` over the RFC 8785 (JCS) canonicalization of the
   originating instruction. The digest is computed by the SAME encoder shipped
   in #1590 (:func:`kailash.trust._jcs.jcs_subject_hash`) — there is no second
   canonicalizer.

The ``origin_bound`` discriminator is EXCLUDED from the signed pre-image and is
fail-closed: stripping it (a deserialization that defaults it to ``False``)
forces the no-origin-shape reconstruction, so a signature made over the
with-origin pre-image no longer matches and verification REJECTS — exactly the
#1590 ``schema_version`` trick.

Cross-SDK: the two pre-image byte forms are an EATP D6 contract. The Rust SDK
mirrors these exact bytes (see the ``rs#1707`` handoff). The golden vectors in
``tests/trust/pact/conformance/vectors/bh3_origin_*.json`` pin the raw bytes.
"""

from __future__ import annotations

import hmac as hmac_mod
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from kailash.trust._jcs import jcs_subject_hash
from kailash.trust.reasoning.traces import ReasoningTrace

logger = logging.getLogger(__name__)

__all__ = [
    "OriginBoundTrace",
    "compute_origin_digest",
    "origin_signing_payload",
    "sign_origin_bound_trace",
    "verify_origin_bound_trace",
]


def compute_origin_digest(originating_instruction: Any) -> str:
    """Return ``"sha256:<hex>"`` — the RFC 8785 (JCS) digest of an instruction.

    Reuses :func:`kailash.trust._jcs.jcs_subject_hash` (the single true RFC 8785
    encoder shipped in issue #1590) so the origin digest is byte-stable across
    Python versions AND cross-SDK. The instruction MUST be canonicalized (NOT a
    naive ``str()``) so a Rust verifier reconstructs the identical digest.

    Args:
        originating_instruction: The instruction that spawned the agent action.
            Any JSON-native / typed-scalar structure the JCS encoder accepts.

    Returns:
        ``"sha256:<64-hex>"`` — the origin digest bound into the signed
        pre-image (with-origin form).

    Raises:
        ValueError: If the instruction contains a non-finite float (RFC 8785
            rejects ``NaN`` / ``Infinity``).
        TypeError: If the instruction contains a value with no RFC 8785
            encoding or a non-string object key.
    """
    return jcs_subject_hash(originating_instruction)


def origin_signing_payload(
    trace: ReasoningTrace,
    *,
    origin_digest: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the signed pre-image dict for an action-trace (both BH3 forms).

    * ``origin_digest is None`` (without-origin form) — returns
      :meth:`ReasoningTrace.to_signing_payload` UNCHANGED. The resulting
      canonical bytes are byte-IDENTICAL to the current (pre-BH3) trace signing
      pre-image, so an old signature verifies without change.
    * ``origin_digest`` supplied (with-origin form) — returns the current
      pre-image PLUS a single ``"origin"`` key carrying the bound digest. Under
      :func:`kailash.trust.signing.crypto.serialize_for_signing`'s
      ``sort_keys=True`` emission, ``origin`` sorts deterministically between
      ``methodology`` and ``rationale``; no other byte changes.

    The ``origin_bound`` discriminator is NEVER placed in this payload — it is
    excluded from the signed bytes so a downstream discriminator-strip forces
    the without-origin reconstruction (fail-closed; see module docstring).

    Args:
        trace: The agent-declared action/reasoning trace.
        origin_digest: The bound origin digest (``"sha256:<hex>"``), or ``None``
            for the backward-compatible without-origin form.

    Returns:
        The pre-image dict, ready for
        :func:`kailash.trust.signing.crypto.serialize_for_signing`.
    """
    payload = trace.to_signing_payload()
    if origin_digest is not None:
        # Copy before mutating — to_signing_payload() may return a shared dict
        # in some callers; never leak the origin key back into the trace's own
        # (no-origin) pre-image.
        payload = dict(payload)
        payload["origin"] = origin_digest
    return payload


@dataclass(frozen=True)
class OriginBoundTrace:
    """An Ed25519-signed action-trace, optionally bound to its origin.

    ``frozen=True``: immutable after creation (trust-plane security invariant —
    a signed record MUST NOT be mutated post-signature).

    Attributes:
        trace: The agent-declared action/reasoning trace.
        signature: Base64-encoded Ed25519 signature over the pre-image built by
            :func:`origin_signing_payload` (with-origin form when
            ``origin_bound`` is True, without-origin form otherwise).
        signed_at: When the signature was created (UTC recommended).
        signed_by: Identifier of the signing agent (D/T/R address or key ID).
        origin_bound: The DISCRIMINATOR. ``True`` ⇒ the signed pre-image bound
            ``origin_digest``; ``False`` ⇒ a plain (pre-BH3-compatible) trace
            signature. EXCLUDED from the signed pre-image and fail-closed: a
            deserialization that drops it defaults to ``False``, forcing the
            without-origin reconstruction (signature mismatch → reject).
        origin_digest: The bound ``"sha256:<hex>"`` origin digest when
            ``origin_bound`` is True; ``None`` otherwise.
    """

    trace: ReasoningTrace
    signature: str
    signed_at: datetime
    signed_by: str
    origin_bound: bool
    origin_digest: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-native dict.

        ``origin_digest`` is emitted only for a bound record; ``origin_bound``
        is always emitted (it is the discriminator a verifier reads).
        """
        result: Dict[str, Any] = {
            "trace": self.trace.to_dict(),
            "signature": self.signature,
            "signed_at": self.signed_at.isoformat(),
            "signed_by": self.signed_by,
            "origin_bound": self.origin_bound,
        }
        if self.origin_bound:
            result["origin_digest"] = self.origin_digest
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OriginBoundTrace":
        """Deserialize from a dict.

        A MISSING ``origin_bound`` key defaults to ``False`` — this is the
        fail-closed discriminator-strip behavior: a tampered record that drops
        ``origin_bound`` is reconstructed as an unbound trace, so a signature
        made over the with-origin pre-image no longer matches on verify.
        """
        origin_bound = bool(data.get("origin_bound", False))
        return cls(
            trace=ReasoningTrace.from_dict(data["trace"]),
            signature=data["signature"],
            signed_at=datetime.fromisoformat(data["signed_at"]),
            signed_by=data["signed_by"],
            origin_bound=origin_bound,
            # A stripped/absent discriminator MUST NOT carry a stale digest
            # through: an unbound record has no bound origin.
            origin_digest=data.get("origin_digest") if origin_bound else None,
        )


def sign_origin_bound_trace(
    trace: ReasoningTrace,
    private_key: str,
    signed_by: str,
    *,
    originating_instruction: Optional[Any] = None,
    signed_at: Optional[datetime] = None,
) -> OriginBoundTrace:
    """Sign an action-trace, binding its origin when an instruction is supplied.

    * ``originating_instruction is None`` — signs the without-origin pre-image
      (``origin_bound=False``). Byte-identical to a pre-BH3 trace signature.
    * ``originating_instruction`` supplied — computes the JCS origin digest,
      binds it into the with-origin pre-image, and signs THAT
      (``origin_bound=True``). A later verifier MUST re-authenticate the digest
      against the authoritative instruction (see
      :func:`verify_origin_bound_trace`).

    Args:
        trace: The agent-declared action/reasoning trace.
        private_key: Base64-encoded Ed25519 private key.
        signed_by: Identifier of the signing agent.
        originating_instruction: The instruction that originated the action, or
            ``None`` for an unbound signature.
        signed_at: Signature timestamp (defaults to ``datetime.now(UTC)``).

    Returns:
        A frozen :class:`OriginBoundTrace`.

    Raises:
        ImportError: If PyNaCl is not installed.
        ValueError: If the key is invalid, or the instruction carries a
            non-finite float (RFC 8785 rejects it — fail-closed at sign time).
    """
    from datetime import timezone

    from kailash.trust.signing.crypto import serialize_for_signing, sign

    origin_digest: Optional[str] = None
    if originating_instruction is not None:
        # Fail-closed: a non-canonicalizable instruction raises here rather than
        # producing an unauthenticatable record.
        origin_digest = compute_origin_digest(originating_instruction)

    payload = origin_signing_payload(trace, origin_digest=origin_digest)
    signature = sign(serialize_for_signing(payload), private_key)

    return OriginBoundTrace(
        trace=trace,
        signature=signature,
        signed_at=signed_at or datetime.now(timezone.utc),
        signed_by=signed_by,
        origin_bound=origin_digest is not None,
        origin_digest=origin_digest,
    )


def verify_origin_bound_trace(
    record: OriginBoundTrace,
    public_key: str,
    *,
    originating_instruction: Optional[Any] = None,
) -> bool:
    """Verify a signed action-trace, authenticating its origin when demanded.

    Fail-closed on EVERY error path (returns ``False``, never raises out and
    never silent-passes).

    Semantics (the BH3 authentication contract):

    * **Bound record + authoritative instruction supplied** (the origin-auth
      path): (1) reconstruct the with-origin pre-image from the record's STORED
      ``origin_digest`` and Ed25519-verify the signature over it — INTEGRITY;
      then (2) recompute the origin digest from the AUTHORITATIVE
      ``originating_instruction`` the verifier holds and constant-time-compare
      it to the stored digest — ORIGIN AUTHENTICATION. A mismatch REJECTS even
      when the signature is valid — this is the fabricated-trace defense.
    * **Bound record, NO instruction supplied** — REJECT. A bound record makes
      an origin CLAIM that cannot be authenticated without the authoritative
      instruction; passing it on integrity alone would be the "merely a record
      of what the agent reported" failure SAFR warns against.
    * **Unbound record, instruction supplied** (``require_origin``) — REJECT.
      The caller DEMANDS origin authentication; an unbound record makes no
      authenticatable claim. This closes the downgrade attack where an attacker
      strips ``origin_bound`` to dodge origin auth.
    * **Unbound record, no instruction** — verify the without-origin pre-image
      (backward-compatible; a plain pre-BH3 trace signature).

    Args:
        record: The signed :class:`OriginBoundTrace`.
        public_key: Base64-encoded Ed25519 public key.
        originating_instruction: The authoritative instruction to authenticate
            against, or ``None`` to verify an unbound record's integrity only.

    Returns:
        ``True`` iff the signature is valid AND (when applicable) the origin
        authenticates. ``False`` on any tamper, mismatch, or error.
    """
    try:
        from kailash.trust.signing.crypto import serialize_for_signing, verify_signature

        require_origin = originating_instruction is not None

        if record.origin_bound:
            if record.origin_digest is None:
                # Claims bound but carries no digest — malformed, fail-closed.
                return False
            payload = origin_signing_payload(
                record.trace, origin_digest=record.origin_digest
            )
            preimage = serialize_for_signing(payload)
            if not verify_signature(preimage, record.signature, public_key):
                # Integrity failure. Also the path a discriminator-strip that
                # left origin_bound=True but tampered the digest takes.
                return False
            if not require_origin:
                # Cannot authenticate a bound record's origin without the
                # authoritative instruction. Fail-closed — never pass on
                # integrity alone.
                return False
            expected = compute_origin_digest(originating_instruction)
            # Constant-time compare — never leak the digest byte-by-byte.
            return hmac_mod.compare_digest(expected, record.origin_digest)

        # Unbound record.
        if require_origin:
            # Downgrade defense: caller demands origin authentication but the
            # record makes no bound claim (e.g. a stripped discriminator).
            return False
        payload = origin_signing_payload(record.trace, origin_digest=None)
        preimage = serialize_for_signing(payload)
        return verify_signature(preimage, record.signature, public_key)
    except Exception:
        logger.exception(
            "verify_origin_bound_trace failed for '%s' -- fail-closed to False",
            record.signed_by,
        )
        return False
