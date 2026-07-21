# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Algorithm Identifier for Signed Records (EATP-08 v1.1 conformant).

This module provides the ``AlgorithmIdentifier`` dataclass and registry used
to thread algorithm-agility metadata through every signed-record API surface
in the trust plane. It implements the EATP-08 v1.1 erratum
(``foundation/docs/02-standards/eatp/08-algorithm-identifier.md``), which
supersedes the pre-publication "#604 scaffold" that awaited mint ISS-31.

Wire encoding (EATP-08 §3.1 / §3.2, binding D3)
-----------------------------------------------

The algorithm identifier is serialised as a **top-level JSON string** field
named ``alg_id`` whose value is a registry token (the default is
``"eatp-v1"``). Under JSON Canonicalization Scheme (JCS, RFC 8785) key
ordering, ``alg_id`` sorts first, so a verifier reads the algorithm before
parsing the payload. The pre-registry nested object ``{"algorithm": "..."}``
and the deprecated literal ``"ed25519+sha256"`` are NON-conformant emissions;
they are accepted only on the bounded D2d legacy path (§4.5) and mapped to
``eatp-v1``.

Registry (EATP-08 §3.3)
-----------------------

``eatp-v1`` is the sole **Active** identifier (Ed25519 + SHA-256). The
reserved rows (``eatp-v1.1``, ``eatp-v2``, ``eatp-v2.ml-dsa``,
``eatp-v2.slh-dsa``) are recognised as registered tokens but are
undispatchable: a verifier presented with one it does not implement MUST emit
``unsupported-algorithm`` and MUST NOT dispatch (and MUST NOT fall through to
``eatp-v1``).

References
----------

- Spec: ``foundation/docs/02-standards/eatp/08-algorithm-identifier.md@v1.1``.
- Issue: terrene-foundation/kailash-py ISS-32 (was #604 scaffold).
- Cross-SDK sibling: the Rust SDK (ISS-33).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, Mapping, Optional

from kailash.trust.exceptions import InvalidSignatureError
from kailash.trust.signing.crypto import verify_signature

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registry constants (EATP-08 §3.3)
# ---------------------------------------------------------------------------

# The current Active default identifier. EATP-08 §3.3: `eatp-v1` is the
# top-level string token for Ed25519 (RFC 8032) + SHA-256 (FIPS 180-4).
# This REPLACES the pre-publication scaffold default "ed25519+sha256".
ALGORITHM_DEFAULT: str = "eatp-v1"

# The deprecated pre-registry literal. EATP-08 §4.5 (D2d) accepts records
# carrying this literal (in nested-object encoding, or in unsigned
# `algorithm` metadata) ONLY on the bounded/witnessed legacy path, mapping
# them to `eatp-v1`. It is NEVER a conformant emission post-adoption.
DEPRECATED_PRE_REGISTRY_LITERAL: str = "ed25519+sha256"

# The pinned adoption date (EATP-08 §7.1). Implementations compare a record's
# witnessed chain-head timestamp against this for the D2a / D2d dated tests.
ADOPTION_DATE: str = "2026-04-26"

# Parsed form of :data:`ADOPTION_DATE`, used by the D2d temporal gate. Kept as
# a ``date`` so the comparison is timezone-agnostic at day granularity (the
# spec pins an ISO-8601 day, §7.1).
ADOPTION_DATE_PARSED: date = date.fromisoformat(ADOPTION_DATE)


class AlgorithmStatus(str, Enum):
    """Registry dispatch states (EATP-08 §3.3)."""

    ACTIVE = "Active"
    RESERVED = "Reserved"
    RESERVED_UNREGISTERED = "Reserved-Unregistered"


@dataclass(frozen=True)
class RegistryEntry:
    """A single row of the EATP-08 §3.3 algorithm registry.

    Attributes:
        alg_id: The on-wire top-level string token.
        signature: Human-readable signature-scheme name.
        hash: Human-readable hash-primitive name.
        status: The dispatch state (Active / Reserved / Reserved-Unregistered).
    """

    alg_id: str
    signature: str
    hash: str
    status: AlgorithmStatus


# EATP-08 §3.3 registry. Implementations MUST recognise at least `eatp-v1`.
# Only `eatp-v1` is Active (dispatchable); every other row is recognised as a
# registered token but is undispatchable until a registry amendment moves it
# to Active (and supplies its canonical-form + conformance vector).
ALGORITHM_REGISTRY: Dict[str, RegistryEntry] = {
    "eatp-v1": RegistryEntry(
        alg_id="eatp-v1",
        signature="Ed25519 (RFC 8032)",
        hash="SHA-256 (FIPS 180-4)",
        status=AlgorithmStatus.ACTIVE,
    ),
    "eatp-v1.1": RegistryEntry(
        alg_id="eatp-v1.1",
        signature="Ed25519",
        hash="SHA-512/256",
        status=AlgorithmStatus.RESERVED,
    ),
    "eatp-v2": RegistryEntry(
        alg_id="eatp-v2",
        signature="reserved",
        hash="reserved",
        status=AlgorithmStatus.RESERVED_UNREGISTERED,
    ),
    "eatp-v2.ml-dsa": RegistryEntry(
        alg_id="eatp-v2.ml-dsa",
        signature="ML-DSA-65 (FIPS 204)",
        hash="SHAKE-256",
        status=AlgorithmStatus.RESERVED,
    ),
    "eatp-v2.slh-dsa": RegistryEntry(
        alg_id="eatp-v2.slh-dsa",
        signature="SLH-DSA-SHA2-128s (FIPS 205)",
        hash="SHA-256",
        status=AlgorithmStatus.RESERVED,
    ),
}


class UnsupportedAlgorithmError(Exception):
    """Raised when an `alg_id` cannot be dispatched (EATP-08 §5.3).

    Carries the normative error code so callers can branch on the failure
    mode rather than parse a message. The two codes this module surfaces:

    - ``unsupported-algorithm``: the token is present and a top-level string
      but is not Active (it is unregistered, Reserved, or
      Reserved-Unregistered, and this verifier does not implement it). The
      verifier MUST NOT fall through to ``eatp-v1`` (§3.3).
    - ``alg-id-shape-mismatch``: the token is present but is not a top-level
      string (object/array/number/null), or the algorithm is carried only
      under a non-``alg_id`` key, and the record does not qualify for D2d
      transitional acceptance (§3.1, §5.3).
    - ``missing-alg-id-post-adoption``: a post-adoption record carries no
      ``alg_id`` and no D2d witness rescues it (§4.2).
    - ``implicit-v1-witness-failure``: a D2d pre-registry form was offered for
      legacy acceptance but the witness is missing or its witnessed/head date
      is not strictly before the adoption date (§4.3.2, §4.5).
    - ``monotonic-upgrade-violation``: a record without ``alg_id`` OR in a
      pre-registry explicit form was offered from a principal-chain that has
      previously emitted a registry-form (v2 / ``eatp-v1``) record — the chain
      crossed the §4.5.3 monotonic boundary, so the downgrade MUST be rejected
      (it takes precedence over D2a/D2d acceptance AND over
      ``missing-alg-id-post-adoption``). The prior-v2 state is supplied by the
      verifier via ``prior_registry_form_seen=True`` or a resolved
      :class:`D2dWitness` carrying ``first_v2_seen``.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {message}")


@dataclass(frozen=True)
class D2dVerifierKeys:
    """Trusted public keys for verifying a D2d signed marker (EATP-08 §4.3).

    The §4.3.2 detection rule requires the marker to be *signed-not-remembered*:
    the verifier holds the trusted public key(s) and verifies ``marker_sig``
    over the signed core ``serialize_for_signing({principal, first_seen})``
    INSIDE the gate, rather than trusting a passed-in value. This config is the
    resolution surface — it mirrors :class:`MultiSigPolicy.signer_public_keys`
    (``multi_sig.py``): a mapping of ``witness_id`` to a base64 Ed25519 public
    key, plus an optional ``default_key`` used when a marker carries no
    ``witness_id`` or an unmatched one.

    §4.3 makes the transport implementation-defined ("a transparency log, an
    in-Foundation witness service, **or per-verifier signing keys**"); this is
    the per-verifier-signing-key transport. A transparency log / witness service
    can later become the marker *source* without changing this verification
    contract (it still resolves a trusted key and verifies ``marker_sig``).

    Attributes:
        keys: Mapping of ``witness_id`` -> base64 Ed25519 public key.
        default_key: Optional base64 Ed25519 public key applied when the
            marker's ``witness_id`` is unset or not present in ``keys``.
    """

    keys: Mapping[str, str]
    default_key: Optional[str] = None

    def resolve(self, witness_id: Optional[str]) -> Optional[str]:
        """Resolve the trusted public key for a marker's ``witness_id``.

        Returns the keyed entry when ``witness_id`` matches, else
        ``default_key`` (which MAY be ``None``). A ``None`` return means no
        trusted key resolves and the gate MUST fail closed.
        """

        if witness_id is not None and witness_id in self.keys:
            return self.keys[witness_id]
        return self.default_key


@dataclass(frozen=True)
class D2dWitness:
    """Dated, signed-marker evidence for D2d legacy acceptance (EATP-08 §4.5).

    The bare ``legacy_path: bool`` of the pre-1.1 scaffold was a perpetual,
    un-sunsetted downgrade-acceptance channel: any caller passing ``True``
    accepted the deprecated ``ed25519+sha256`` / nested form forever, with no
    temporal or witness bound, and :data:`ADOPTION_DATE` was defined but never
    consulted. D2d (§4.5) requires legacy acceptance to be **dated** and
    **witnessed**: a pre-registry explicit form is accepted as ``eatp-v1``
    ONLY when a signed marker is present, verifies against a configured trusted
    key, has not expired, corroborates the claimed pre-adoption head date, and
    its witnessed/head dates are strictly before :data:`ADOPTION_DATE`.

    This dataclass is the structured argument that replaces ``legacy_path:
    bool`` on every signed-record ``from_dict`` site. The §4.3.1 REQUIRED
    signed core is ``{principal, first_seen}``; ``marker_sig`` binds exactly
    that (NOT ``chain_head_date`` — that is the record's CLAIMED head timestamp,
    corroborated AGAINST the signed ``first_seen``). The temporal + signature
    + expiry checks are enforced in :func:`assert_d2d_witness_pre_adoption`,
    not deferred to the caller.

    Attributes:
        witnessed_at: The timestamp of the witness / transparency-log entry.
            MUST be strictly before the adoption date (temporal gate).
        chain_head_date: The record's claimed chain-head ``timestamp``
            (Genesis Record Element 1 / Audit Anchor Element 5). The CLAIMED
            value corroborated against the signed ``first_seen``; MUST be
            strictly before the adoption date.
        principal: The principal-chain id the marker binds (§4.3.1 REQUIRED
            signed-core field). Part of the ``marker_sig`` pre-image.
        first_seen: The signed first-contact/adoption boundary (§4.3.1
            REQUIRED signed-core field). The date the verifier *trusts*: an
            attacker who backdates the record's own ``chain_head_date`` still
            fails because a fresh chain cannot obtain a pre-adoption *signed*
            ``first_seen`` from the trusted witness. Part of the ``marker_sig``
            pre-image.
        marker_sig: Base64 Ed25519 signature over
            ``serialize_for_signing({principal, first_seen})``, produced by the
            witness/verifier key. Absent ``marker_sig`` => unsigned marker =>
            ``implicit-v1-witness-failure``.
        expires_at: Optional marker expiry. When set and ``<= now``, the marker
            is expired => ``implicit-v1-witness-failure``.
        witness_id: Optional id selecting which trusted key in
            :class:`D2dVerifierKeys` verifies ``marker_sig`` (§4.3.1 optional
            field). Unset falls back to the config ``default_key``.
        first_v2_seen: The signed monotonic-upgrade boundary (§4.3.1 / §4.5.3) —
            the timestamp at which this principal-chain FIRST emitted a
            registry-form (v2) record. When set, the chain has crossed the
            monotonic boundary: a subsequent absent-``alg_id`` or pre-registry
            explicit form is a downgrade and MUST be rejected with
            ``monotonic-upgrade-violation``. Because a verifier relies on it for a
            D2 decision it is inside the signed bytes (§4.3.1) — see
            :meth:`signed_marker_payload`, which includes it in the
            ``marker_sig`` pre-image when set (markers without it keep the
            two-field ``{principal, first_seen}`` core, back-compat). The runtime
            read-check (`decode_wire_alg_id`) also accepts an out-of-band
            ``prior_registry_form_seen`` bool when no signed marker carries it.
    """

    witnessed_at: datetime
    chain_head_date: datetime
    principal: Optional[str] = None
    first_seen: Optional[datetime] = None
    marker_sig: Optional[str] = None
    expires_at: Optional[datetime] = None
    witness_id: Optional[str] = None
    first_v2_seen: Optional[datetime] = None

    @staticmethod
    def _as_date(value: datetime) -> date:
        return value.date() if isinstance(value, datetime) else value

    def signed_marker_payload(self) -> Dict[str, Any]:
        """The §4.3.1 signed core ``{principal, first_seen}``.

        ``marker_sig`` binds EXACTLY this object (serialised via the canonical
        cross-SDK :func:`serialize_for_signing`). ``chain_head_date`` is NOT in
        the signed core — it is the claimed value corroborated against the
        signed ``first_seen``.
        """

        payload: Dict[str, Any] = {
            "principal": self.principal,
            "first_seen": (
                self.first_seen.isoformat()
                if isinstance(self.first_seen, datetime)
                else self.first_seen
            ),
        }
        # §4.3.1: a field a verifier relies on for a D2 decision MUST be in the
        # signed bytes. `first_v2_seen` is signed-when-present so the monotonic
        # boundary is tamper-proof; markers without it keep the two-field core
        # (back-compat — existing {principal, first_seen} marker_sigs verify
        # unchanged). JCS sorts keys, so the pre-image is deterministic.
        if self.first_v2_seen is not None:
            payload["first_v2_seen"] = (
                self.first_v2_seen.isoformat()
                if isinstance(self.first_v2_seen, datetime)
                else self.first_v2_seen
            )
        return payload

    def is_pre_adoption(self) -> bool:
        """True iff BOTH witnessed/claimed dates are strictly before adoption.

        Consumes :data:`ADOPTION_DATE_PARSED` (the E5/D2d temporal bound). A
        witness whose witnessed-date OR chain-head date falls on/after the
        adoption date does NOT license legacy acceptance.
        """

        return (
            self._as_date(self.witnessed_at) < ADOPTION_DATE_PARSED
            and self._as_date(self.chain_head_date) < ADOPTION_DATE_PARSED
        )


def _to_aware_utc(value: datetime) -> datetime:
    """Coerce a datetime to timezone-aware UTC for safe comparison.

    A naive datetime is assumed to be UTC (the trust-plane wire convention is
    RFC-3339-Z). Aware datetimes are converted to UTC.
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def assert_d2d_witness_pre_adoption(
    witness: Optional[D2dWitness],
    *,
    verifier_keys: Optional[D2dVerifierKeys] = None,
    now: Optional[datetime] = None,
) -> None:
    """Enforce the D2d signed-marker gate (EATP-08 §4.5 / §4.3.2).

    The §4.3.2 detection rule: emit ``implicit-v1-witness-failure`` when ANY of
    the five fail-closed checks does not hold. Returns silently ONLY when all
    five hold, in which case the caller MAY accept the pre-registry explicit
    form as ``eatp-v1`` and MUST log the acceptance for migration tracking.

    The five checks (all map to ``implicit-v1-witness-failure``):

    1. **missing** — no witness was supplied.
    2. **sig-verify** — the signed core is complete (``principal`` +
       ``marker_sig``) AND a trusted key resolves from ``verifier_keys`` AND
       ``marker_sig`` verifies (Ed25519) over
       ``serialize_for_signing({principal, first_seen})``. This is the
       *signed-not-remembered* property: a passed-in value is not trusted.
    3. **first_seen-corroboration** — the signed ``first_seen`` is present AND
       strictly before adoption (a fresh chain cannot obtain a pre-adoption
       *signed* ``first_seen``, defeating the backdated-``chain_head_date``
       attack — §4.3.2(3)).
    4. **expiry** — the marker is not expired (``expires_at`` unset, or
       ``> now``).
    5. **monotonic-boundary** (temporal) — both ``witnessed_at`` and the
       claimed ``chain_head_date`` are strictly before the adoption date
       (§4.5).

    Args:
        witness: The :class:`D2dWitness`, or ``None`` if no legacy acceptance.
        verifier_keys: The trusted-key config that resolves and verifies
            ``marker_sig`` (check 2). ``None`` => no trusted key => fail closed.
        now: Clock for the expiry check (defaults to ``datetime.now(UTC)``);
            injectable for deterministic tests.

    Raises:
        UnsupportedAlgorithmError: code ``implicit-v1-witness-failure`` when
            any of the five checks fails.
    """

    def _fail(detail: str) -> "UnsupportedAlgorithmError":
        return UnsupportedAlgorithmError("implicit-v1-witness-failure", detail)

    # Check 1 — missing.
    if witness is None:
        raise _fail(
            "D2d legacy acceptance requires a dated, signed marker "
            "(EATP-08 §4.5 / §4.3): no witness was supplied, so the "
            "pre-registry explicit form MUST be rejected, not downgraded "
            f"to {ALGORITHM_DEFAULT!r}."
        )

    # Check 2 — signed-not-remembered: complete signed core + trusted-key verify.
    if witness.principal is None or witness.marker_sig is None:
        raise _fail(
            "D2d marker is unsigned or incomplete: §4.3.1 requires a signed "
            "core {principal, first_seen} bound by marker_sig. A trusted "
            "passed-in witness is NOT sufficient — the marker MUST be "
            "signed-not-remembered (§4.3.2)."
        )
    public_key = (
        verifier_keys.resolve(witness.witness_id) if verifier_keys is not None else None
    )
    if public_key is None:
        raise _fail(
            "D2d marker cannot be verified: no trusted verifier key resolves "
            f"for witness_id={witness.witness_id!r}. Configure D2dVerifierKeys "
            "with the witness's public key (§4.3); an unverifiable marker fails "
            "closed (§4.3.2)."
        )
    try:
        sig_ok = verify_signature(
            witness.signed_marker_payload(), witness.marker_sig, public_key
        )
    except InvalidSignatureError:
        sig_ok = False
    if not sig_ok:
        raise _fail(
            "D2d marker_sig failed Ed25519 verification against the configured "
            "trusted key (§4.3.2): the signed core {principal, first_seen} does "
            "not verify, so the marker is forged, tampered, or signed by an "
            "untrusted key."
        )

    # Check 3 — first_seen corroboration (signed anchor precedes adoption).
    if witness.first_seen is None:
        raise _fail(
            "D2d marker carries no signed first_seen; the claimed pre-adoption "
            "head date is uncorroborated (§4.3.2(3))."
        )
    if not (witness._as_date(witness.first_seen) < ADOPTION_DATE_PARSED):
        raise _fail(
            "D2d witnessed first_seen does not precede the adoption date "
            f"{ADOPTION_DATE!r} (§4.3.2(3)): a fresh chain cannot obtain a "
            "pre-adoption signed first_seen, so the claimed pre-adoption head "
            "date is uncorroborated."
        )

    # Check 4 — expiry.
    if witness.expires_at is not None:
        now_utc = _to_aware_utc(now if now is not None else datetime.now(timezone.utc))
        if now_utc >= _to_aware_utc(witness.expires_at):
            raise _fail(
                "D2d marker is expired (expires_at <= now); an expired marker "
                "does not license legacy acceptance (§4.3.2)."
            )

    # Check 5 — temporal monotonic boundary (claimed dates strictly < adoption).
    if not witness.is_pre_adoption():
        raise _fail(
            "D2d legacy acceptance requires the witnessed_at AND claimed "
            f"chain_head_date to be strictly before the adoption date "
            f"{ADOPTION_DATE!r} (EATP-08 §4.5 / §7.1); the supplied witness is "
            f"dated on/after adoption, so the pre-registry explicit form MUST "
            f"be rejected, not downgraded to {ALGORITHM_DEFAULT!r}."
        )


# Migration-tracking counter (EATP-08 §7.1). Every Compatible-Legacy D2d
# acceptance increments this so an operator can quantify how many records still
# rely on the bounded downgrade path before the marker store + adoption gate
# fully sunset the legacy form. Read via :func:`d2d_legacy_acceptance_count`.
_D2D_LEGACY_ACCEPTANCE_COUNT: int = 0


def d2d_legacy_acceptance_count() -> int:
    """Return the count of D2d Compatible-Legacy acceptances this process (§7.1)."""

    return _D2D_LEGACY_ACCEPTANCE_COUNT


def _reset_d2d_legacy_acceptance_count() -> None:
    """Reset the §7.1 migration counter (test-only helper)."""

    global _D2D_LEGACY_ACCEPTANCE_COUNT
    _D2D_LEGACY_ACCEPTANCE_COUNT = 0


def _log_d2d_legacy_acceptance(form_description: str, witness: D2dWitness) -> None:
    """Log + count a D2d Compatible-Legacy acceptance for migration tracking (§7.1).

    Consolidates the two acceptance log sites (the nested-object `alg_id` form and
    the unsigned-`algorithm`-metadata form) into one helper.

    Level is **WARN** (`observability.md` Rule 3): a Compatible-Legacy acceptance
    is a SUCCEEDED-but-DEGRADED path — the record relied on the bounded
    pre-registry downgrade instead of a conformant top-level `alg_id`, and the
    operator MUST see it to drive migration before the form sunsets.

    The `principal` is a subject/chain identifier; per `observability.md` Rule 8
    it is emitted at WARN only as an 8-char SHA-256 hash (WARN-safe correlation
    without leaking the id to log aggregators) and in full only at DEBUG. The
    `witnessed_at`/adoption dates are temporal metadata, safe at WARN.
    """

    global _D2D_LEGACY_ACCEPTANCE_COUNT
    _D2D_LEGACY_ACCEPTANCE_COUNT += 1

    principal = witness.principal
    principal_hash = (
        hashlib.sha256(principal.encode("utf-8")).hexdigest()[:8]
        if principal is not None
        else None
    )
    logger.warning(
        "EATP-08 D2d Compatible-Legacy acceptance (§7.1): %s accepted as %r via "
        "the bounded/witnessed legacy path (witnessed_at=%s < adoption=%s, "
        "principal_hash=%s, total_legacy_acceptances=%d). Migrate the emitter to "
        "a conformant top-level alg_id.",
        form_description,
        ALGORITHM_DEFAULT,
        witness.witnessed_at,
        ADOPTION_DATE,
        principal_hash,
        _D2D_LEGACY_ACCEPTANCE_COUNT,
    )
    logger.debug(
        "EATP-08 D2d acceptance detail: principal=%s chain_head_date=%s first_seen=%s",
        principal,
        witness.chain_head_date,
        witness.first_seen,
    )


def is_registered(alg_id: str) -> bool:
    """Return True if ``alg_id`` is a known registry token (any Status)."""

    return alg_id in ALGORITHM_REGISTRY


def is_active(alg_id: str) -> bool:
    """Return True if ``alg_id`` is an Active (dispatchable) registry token."""

    entry = ALGORITHM_REGISTRY.get(alg_id)
    return entry is not None and entry.status is AlgorithmStatus.ACTIVE


def resolve_dispatch(alg_id: str) -> RegistryEntry:
    """Resolve a top-level-string ``alg_id`` to a dispatchable registry row.

    Implements the EATP-08 §5.1 step-2 dispatch gate: match by the pinned
    encoding (string equality), then gate on Status. Only an **Active** row
    is dispatchable; every other case raises with ``unsupported-algorithm``
    and MUST NOT fall through to ``eatp-v1`` (§3.3).

    Args:
        alg_id: A top-level registry-token string read off the wire.

    Returns:
        The matched Active :class:`RegistryEntry`.

    Raises:
        UnsupportedAlgorithmError: with code ``unsupported-algorithm`` when
            the token is unregistered, Reserved, or Reserved-Unregistered.
    """

    entry = ALGORITHM_REGISTRY.get(alg_id)
    if entry is None:
        raise UnsupportedAlgorithmError(
            "unsupported-algorithm",
            f"alg_id {alg_id!r} is not present in the EATP-08 §3.3 registry; "
            f"it MUST NOT fall through to {ALGORITHM_DEFAULT!r} semantics.",
        )
    if entry.status is not AlgorithmStatus.ACTIVE:
        raise UnsupportedAlgorithmError(
            "unsupported-algorithm",
            f"alg_id {alg_id!r} is registered with Status "
            f"{entry.status.value!r}, which is not dispatchable by this "
            f"verifier; emit unsupported-algorithm and do not dispatch.",
        )
    return entry


def is_pre_registry_form(value: Any) -> bool:
    """Return True if ``value`` is a recognised D2d pre-registry explicit form.

    EATP-08 §4.5 (D2d), as clarified by the v1.1.1 erratum, recognises the
    deprecated literal ``ed25519+sha256`` as a pre-registry explicit form in
    exactly **two structurally-distinguishable encodings**:

    - the **nested-object** encoding ``{"algorithm": "ed25519+sha256"}`` — the
      value of a signed ``alg_id`` field (the Rust-SDK historical form); and
    - the algorithm carried only in **unsigned ``algorithm`` metadata** with no
      signed ``alg_id`` (the Python-SDK historical form), which reaches this
      predicate as a dict whose ``algorithm`` key holds the literal (see
      :func:`decode_wire_alg_id`).

    A **bare top-level-string** ``alg_id`` equal to ``ed25519+sha256`` is NOT a
    pre-registry form: it is an unregistered top-level token and MUST be
    rejected with ``unsupported-algorithm`` (§3.3 / §5.1 step 2), never rescued
    by a witness. Accepting a bare literal string here would dilute the
    "top-level ``alg_id`` string is a registry token" invariant that the
    anti-strip design (§4.4 / V6) depends on, and no conformant emitter ever
    produced one (the reference scaffolds emitted the nested object or unsigned
    metadata). This is the v1.1.1 / mint#26 ruling (ISS-32).

    Both recognised encodings map to ``eatp-v1`` under the bounded/witnessed
    legacy path. This function only RECOGNISES the shape; the
    dated/witnessed/sunset gating is the verifier's responsibility (§4.5).
    """

    # Only the structurally-distinguishable nested form is a D2d pre-registry
    # shape. A bare string `== DEPRECATED_PRE_REGISTRY_LITERAL` is deliberately
    # NOT matched here (v1.1.1): it falls through to the registry match and
    # raises `unsupported-algorithm`.
    if (
        isinstance(value, dict)
        and value.get("algorithm") == DEPRECATED_PRE_REGISTRY_LITERAL
    ):
        return True
    return False


@dataclass(frozen=True)
class AlgorithmIdentifier:
    """Versioned algorithm identifier for signed records (EATP-08 v1.1).

    Wraps a single registry token. The default is :data:`ALGORITHM_DEFAULT`
    (``"eatp-v1"``). On construction the value is validated against the
    §3.3 registry: an unregistered token raises
    :class:`UnsupportedAlgorithmError` (code ``unsupported-algorithm``).
    Reserved / Reserved-Unregistered tokens are accepted as *values* (they
    are valid registry tokens that may appear on the wire) but are
    undispatchable at verification time via :func:`resolve_dispatch`.

    Attributes:
        algorithm: The registry token string. Defaults to
            :data:`ALGORITHM_DEFAULT`.

    Raises:
        UnsupportedAlgorithmError: If a non-registry token is passed
            (code ``unsupported-algorithm``).

    Examples:
        >>> alg = AlgorithmIdentifier()
        >>> alg.algorithm
        'eatp-v1'
        >>> AlgorithmIdentifier(algorithm="eatp-v1.1").algorithm
        'eatp-v1.1'
    """

    algorithm: str = ALGORITHM_DEFAULT

    def __post_init__(self) -> None:
        if not isinstance(self.algorithm, str):
            raise TypeError(
                f"AlgorithmIdentifier.algorithm must be str, got "
                f"{type(self.algorithm).__name__}"
            )
        if not is_registered(self.algorithm):
            raise UnsupportedAlgorithmError(
                "unsupported-algorithm",
                f"alg_id {self.algorithm!r} is not in the EATP-08 §3.3 "
                f"registry. Recognised tokens: "
                f"{sorted(ALGORITHM_REGISTRY)}.",
            )

    @property
    def is_active(self) -> bool:
        """True if this identifier is dispatchable (Active in the registry)."""

        return is_active(self.algorithm)

    # --- Wire encoding (EATP-08 §3.1, binding D3) --------------------------
    #
    # The conformant on-wire shape is a TOP-LEVEL `alg_id` string member that
    # sorts first under JCS. `to_dict` returns exactly `{"alg_id": "<token>"}`
    # so a signed-record producer can splice the member into the top level of
    # its canonical object (NOT a nested `{"algorithm": "..."}` object).

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to the conformant top-level wire member.

        Returns ``{"alg_id": "<token>"}`` per EATP-08 §3.1. Splice this into
        the top level of a signed record's canonical object so ``alg_id``
        sorts first under JCS (§3.2).
        """

        return {"alg_id": self.algorithm}

    @classmethod
    def from_dict(
        cls,
        data: Any,
        *,
        witness: Optional[D2dWitness] = None,
        verifier_keys: Optional[D2dVerifierKeys] = None,
        prior_registry_form_seen: bool = False,
    ) -> "AlgorithmIdentifier":
        """Reconstruct from a wire value (EATP-08 §4.5 D2b / D2d).

        Two acceptance regimes, selected by ``witness``:

        - **Post-adoption path (default, ``witness=None``)**: the value MUST
          be a top-level registry-token string. A missing or empty value is
          NOT silently defaulted (this is the E6 defect the v1.1 erratum
          closes — see §4.6): it raises with code
          ``missing-alg-id-post-adoption`` per D2b. A present-but-malformed
          value (object/array/number/null, or the deprecated literal) raises
          ``alg-id-shape-mismatch``; an unregistered token raises
          ``unsupported-algorithm``.

        - **Bounded legacy path (``witness`` supplied)**: a caller rescuing a
          pre-registry explicit form passes a :class:`D2dWitness`. Acceptance
          as ``eatp-v1`` happens ONLY when the witness is present AND its
          witnessed/head date is strictly before :data:`ADOPTION_DATE`
          (§4.5); :data:`ADOPTION_DATE` is consumed in that comparison via
          :func:`assert_d2d_witness_pre_adoption`. A witness dated on/after
          adoption raises ``implicit-v1-witness-failure`` and does NOT
          downgrade. The recognised forms are the deprecated literal
          ``ed25519+sha256`` (bare or nested ``{"algorithm": ...}``); on
          acceptance the record re-emits as the ``eatp-v1`` top-level token.

        Args:
            data: The wire value. On the post-adoption path this is the
                top-level ``alg_id`` value; on the legacy path it MAY be the
                pre-registry literal or nested form.
            witness: A :class:`D2dWitness` only when the caller is rescuing a
                pre-registry record; its signed marker + dates are enforced
                here (§4.3.2). ``None`` (default) means strict, no legacy
                acceptance.
            verifier_keys: The :class:`D2dVerifierKeys` config that verifies
                the witness's ``marker_sig`` against a configured trusted key.
                ``None`` (default) => no trusted key => the D2d marker fails
                closed with ``implicit-v1-witness-failure``.

        Returns:
            An :class:`AlgorithmIdentifier`, always carrying a registry token
            (the legacy forms map to ``eatp-v1``).

        Raises:
            UnsupportedAlgorithmError: code ``missing-alg-id-post-adoption``,
                ``alg-id-shape-mismatch``, ``unsupported-algorithm``, or
                ``implicit-v1-witness-failure`` per the regime above.
        """

        # Some historical record shapes nested the token under a top-level
        # `{"alg_id": "<token>"}` member; accept that envelope transparently
        # so `from_dict(record_dict)` and `from_dict(record_dict["alg_id"])`
        # behave identically for a conformant record. A present `alg_id` key is
        # authoritative: when it exists we always resolve from it, even if the
        # record ALSO carries an `algorithm` sibling. This closes a latent
        # bypass where `{"alg_id":"ed25519+sha256","algorithm":"ed25519+sha256"}`
        # could otherwise fall through to the whole-dict `algorithm`-key D2d
        # match and rescue a bare top-level-string literal (v1.1.1 / mint#26).
        # The unsigned-`algorithm`-metadata D2d form applies only when there is
        # NO `alg_id` member (handled by `decode_wire_alg_id`'s second branch).
        if isinstance(data, dict) and "alg_id" in data:
            value: Any = data["alg_id"]
        else:
            value = data

        # Monotonic gate (§4.2 / §4.5.3 / §5.1 step 3): once a principal-chain has
        # emitted a registry-form (v2) record, a subsequent absent/empty alg_id OR
        # pre-registry explicit form is a downgrade → monotonic-upgrade-violation.
        # This takes precedence over the D2d witnessed-acceptance below AND over
        # missing-alg-id-post-adoption. The prior-v2 state is verifier-supplied:
        # an explicit `prior_registry_form_seen` flag, OR a resolved marker whose
        # signed `first_v2_seen` is set (§4.3.1). A bare unregistered string /
        # non-string shape is NOT a pre-registry form and keeps its
        # unsupported-algorithm / alg-id-shape-mismatch disposition regardless.
        prior_v2 = prior_registry_form_seen or (
            witness is not None and witness.first_v2_seen is not None
        )
        if prior_v2 and (is_pre_registry_form(value) or value is None or value == ""):
            raise UnsupportedAlgorithmError(
                "monotonic-upgrade-violation",
                "this principal-chain has previously emitted a registry-form "
                "record (prior_registry_form_seen / signed first_v2_seen), so a "
                f"subsequent absent or pre-registry alg_id ({value!r}) is a "
                "downgrade and MUST be rejected (EATP-08 §4.5.3 / §5.1 step 3); "
                f"it MUST NOT be accepted as {ALGORITHM_DEFAULT!r} via D2a/D2d.",
            )

        if witness is not None and is_pre_registry_form(value):
            # D2d: a pre-registry explicit form is acceptable ONLY when the
            # dated, signed witness places the chain head strictly before the
            # adoption date. A witness dated on/after adoption raises
            # implicit-v1-witness-failure; we never downgrade unconditionally.
            # (When no witness is supplied at all, a pre-registry form falls
            # through to the strict rejection below — shape-mismatch — exactly
            # as the post-adoption default requires.)
            assert_d2d_witness_pre_adoption(witness, verifier_keys=verifier_keys)
            _log_d2d_legacy_acceptance(f"pre-registry explicit form {value!r}", witness)
            return cls(algorithm=ALGORITHM_DEFAULT)

        # Post-adoption path (or legacy path with a non-pre-registry value).
        if value is None or value == "":
            # D2b: a missing/empty alg_id post-adoption MUST be rejected, NOT
            # default-filled. This is the E6 fix.
            raise UnsupportedAlgorithmError(
                "missing-alg-id-post-adoption",
                "alg_id is missing or empty on the post-adoption path; "
                "per EATP-08 §4.2 (D2b) it MUST be rejected, not "
                "default-filled. A pre-registry legacy record must be routed "
                "through the D2d gate (witness=D2dWitness(...)) after the "
                "dated/witnessed check.",
            )

        if not isinstance(value, str):
            # An object/array/number is shape-non-conformant (§3.1). The
            # nested pre-registry object is only acceptable on the legacy
            # path, handled above.
            raise UnsupportedAlgorithmError(
                "alg-id-shape-mismatch",
                f"alg_id must be a top-level string token; got "
                f"{type(value).__name__}. Nested or non-string forms are "
                f"non-conformant post-adoption (EATP-08 §3.1).",
            )

        if value == DEPRECATED_PRE_REGISTRY_LITERAL:
            # The deprecated literal as a bare top-level `alg_id` string is an
            # UNREGISTERED top-level token, not a D2d form (v1.1.1 / mint#26):
            # §5.1 step 2 registry-matches a top-level string, and the literal
            # is not in the registry, so it is `unsupported-algorithm` with or
            # without a witness (a witness MUST NOT rescue it). The two D2d
            # forms are the nested-object `alg_id` value and unsigned
            # `algorithm` metadata (§4.5), both reached structurally above, not
            # here. (is_pre_registry_form no longer matches the bare string, so
            # the witnessed D2d block above is skipped for it.)
            raise UnsupportedAlgorithmError(
                "unsupported-algorithm",
                f"alg_id {value!r} is the deprecated pre-registry literal "
                f"presented as a top-level string; it is an unregistered "
                f"token and MUST be rejected with unsupported-algorithm "
                f"(EATP-08 §3.3 / §5.1, v1.1.1). It MUST NOT fall through to "
                f"{ALGORITHM_DEFAULT!r}, and a D2d witness does not rescue it; "
                f"the D2d legacy path accepts the literal only as a "
                f"nested-object alg_id value or unsigned `algorithm` metadata "
                f"(§4.5).",
            )

        if not is_registered(value):
            raise UnsupportedAlgorithmError(
                "unsupported-algorithm",
                f"alg_id {value!r} is not present in the EATP-08 §3.3 "
                f"registry; it MUST NOT fall through to "
                f"{ALGORITHM_DEFAULT!r}.",
            )

        return cls(algorithm=value)


def decode_wire_alg_id(
    data: Dict[str, Any],
    *,
    witness: Optional[D2dWitness] = None,
    verifier_keys: Optional[D2dVerifierKeys] = None,
    prior_registry_form_seen: bool = False,
) -> str:
    """Decode the ``alg_id`` token from a signed-record wire dict.

    A consumer-site helper for every signed-record ``from_dict`` that carries
    a single top-level ``alg_id`` member. It centralises the EATP-08 §3.1 /
    §4.5 acceptance regime so the producer dataclasses do not each re-derive
    it. The two cases this helper resolves from the dict:

    - the conformant top-level ``alg_id`` string token (post-adoption path);
      and
    - the two pre-registry explicit forms (D2d) — a top-level ``alg_id``
      whose value is the deprecated literal or the nested
      ``{"algorithm": "ed25519+sha256"}`` object, OR the algorithm carried
      only under an unsigned top-level ``algorithm`` key. Both are accepted
      ONLY when a :class:`D2dWitness` is supplied AND its witnessed/head date
      is strictly before :data:`ADOPTION_DATE` (the D2d dated/witnessed gate
      of §4.5); both then map to ``eatp-v1``.

    Args:
        data: The signed-record wire dict.
        witness: A :class:`D2dWitness` only when rescuing a pre-registry
            legacy record; ``None`` (default) means strict, no legacy
            acceptance.
        verifier_keys: The :class:`D2dVerifierKeys` config that verifies the
            witness's ``marker_sig`` against a configured trusted key (§4.3.2).
            ``None`` (default) => no trusted key resolves => any D2d marker
            fails closed with ``implicit-v1-witness-failure``.
        prior_registry_form_seen: The verifier-supplied §4.5.3 monotonic signal —
            ``True`` when this principal-chain has previously emitted a
            registry-form (v2 / ``eatp-v1``) record. When set (or when ``witness``
            carries a signed ``first_v2_seen``), an absent-``alg_id`` or
            pre-registry record is a downgrade and is rejected with
            ``monotonic-upgrade-violation`` BEFORE any D2a/D2d acceptance or the
            ``missing-alg-id-post-adoption`` path (§5.1 step 3). Defaults to
            ``False`` (no prior v2 known — the verifier asserts a fresh chain).

    Returns:
        A registry token string (the legacy forms resolve to ``eatp-v1``).

    Raises:
        UnsupportedAlgorithmError: ``missing-alg-id-post-adoption``,
            ``alg-id-shape-mismatch``, ``unsupported-algorithm``,
            ``implicit-v1-witness-failure``, or ``monotonic-upgrade-violation``
            per EATP-08 §5.3.
    """

    if "alg_id" in data:
        # The alg_id-present monotonic + acceptance regime lives in from_dict
        # (it sees the resolved value); forward the prior-v2 signal so a
        # pre-registry alg_id from a prior-v2 chain is rejected there.
        return AlgorithmIdentifier.from_dict(
            data["alg_id"],
            witness=witness,
            verifier_keys=verifier_keys,
            prior_registry_form_seen=prior_registry_form_seen,
        ).algorithm

    # No top-level `alg_id` member → a "record without alg_id" (§5.3 case 1).
    # If the chain has already emitted a registry-form record, regressing to an
    # absent alg_id is a monotonic downgrade — reject BEFORE the D2d
    # unsigned-`algorithm`-metadata acceptance and before missing-alg-id
    # (§4.2 / §4.5.3 / §5.1 step 3). Only the dict-level chokepoint can see that
    # the `alg_id` KEY is absent (from_dict receives only a value).
    if prior_registry_form_seen or (
        witness is not None and witness.first_v2_seen is not None
    ):
        raise UnsupportedAlgorithmError(
            "monotonic-upgrade-violation",
            "signed record carries no top-level `alg_id`, but this "
            "principal-chain has previously emitted a registry-form record "
            "(prior_registry_form_seen / signed first_v2_seen); regressing to an "
            "absent alg_id is a §4.5.3 monotonic downgrade and MUST be rejected, "
            f"not accepted as {ALGORITHM_DEFAULT!r} via D2a/D2d.",
        )

    # A record carrying the algorithm only under an unsigned top-level
    # `algorithm` key is a D2d pre-registry form (kailash-py's historical
    # metadata-only shape). It is accepted ONLY when a dated, signed witness
    # places the chain head strictly before adoption; otherwise it is a
    # post-adoption record missing its alg_id (D2b).
    if "algorithm" in data:
        legacy_value = data["algorithm"]
        if witness is not None and (
            legacy_value == DEPRECATED_PRE_REGISTRY_LITERAL
            or legacy_value in ("", None)
        ):
            # Enforce ADOPTION_DATE: missing/post-adoption witness rejects.
            assert_d2d_witness_pre_adoption(witness, verifier_keys=verifier_keys)
            _log_d2d_legacy_acceptance(
                f"unsigned `algorithm`={legacy_value!r} metadata", witness
            )
            return ALGORITHM_DEFAULT

    raise UnsupportedAlgorithmError(
        "missing-alg-id-post-adoption",
        "signed record carries no top-level `alg_id`; per EATP-08 §4.2 "
        "(D2b) a post-adoption record without alg_id MUST be rejected. "
        "A pre-registry legacy record must be routed through the D2d gate "
        "(witness=D2dWitness(...)) after the dated/witnessed check.",
    )


def coerce_algorithm_id(
    alg_id: "AlgorithmIdentifier | None",
) -> AlgorithmIdentifier:
    """Default-fill an optional :class:`AlgorithmIdentifier`.

    The canonical helper every producer/verifier site uses so that threading
    ``Optional[AlgorithmIdentifier]`` does not require each call site to
    re-implement the ``alg_id or AlgorithmIdentifier()`` defaulting pattern.
    A ``None`` resolves to the Active default (``eatp-v1``); an explicit
    identifier passes through unchanged.

    Args:
        alg_id: An :class:`AlgorithmIdentifier` instance, or ``None``.

    Returns:
        The given ``alg_id`` if not ``None``, else a default
        :class:`AlgorithmIdentifier` (``eatp-v1``).
    """

    return alg_id if alg_id is not None else AlgorithmIdentifier()


__all__ = [
    "ADOPTION_DATE",
    "ADOPTION_DATE_PARSED",
    "ALGORITHM_DEFAULT",
    "ALGORITHM_REGISTRY",
    "AlgorithmIdentifier",
    "AlgorithmStatus",
    "D2dVerifierKeys",
    "D2dWitness",
    "DEPRECATED_PRE_REGISTRY_LITERAL",
    "RegistryEntry",
    "UnsupportedAlgorithmError",
    "assert_d2d_witness_pre_adoption",
    "coerce_algorithm_id",
    "d2d_legacy_acceptance_count",
    "decode_wire_alg_id",
    "is_active",
    "is_pre_registry_form",
    "is_registered",
    "resolve_dispatch",
]
