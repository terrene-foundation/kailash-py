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
- Cross-SDK sibling: esperie-enterprise/kailash-rs ISS-33.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, Optional

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
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {message}")


@dataclass(frozen=True)
class D2dWitness:
    """Dated, signed-marker evidence for D2d legacy acceptance (EATP-08 §4.5).

    The bare ``legacy_path: bool`` of the pre-1.1 scaffold was a perpetual,
    un-sunsetted downgrade-acceptance channel: any caller passing ``True``
    accepted the deprecated ``ed25519+sha256`` / nested form forever, with no
    temporal or witness bound, and :data:`ADOPTION_DATE` was defined but never
    consulted. D2d (§4.5) requires legacy acceptance to be **dated** and
    **witnessed**: a pre-registry explicit form is accepted as ``eatp-v1``
    ONLY when a witness is present AND its witnessed/head date is strictly
    before :data:`ADOPTION_DATE` (2026-04-26).

    This dataclass is the structured argument that replaces ``legacy_path:
    bool`` on every signed-record ``from_dict`` site. Its presence (not a bare
    boolean) is the affirmative assertion that the caller has resolved a
    pre-adoption witness for the record's chain head; the temporal comparison
    is enforced here, not deferred to the caller.

    Attributes:
        witnessed_at: The timestamp of the witness / transparency-log entry
            that corroborates the chain head (§4.3.1 ``first_seen``). This is
            the date the verifier *trusts* (signed-not-remembered): an
            attacker who backdates the record's own field still fails because
            no pre-adoption witness corroborates it.
        chain_head_date: The record's claimed chain-head ``timestamp``
            (Genesis Record Element 1 / Audit Anchor Element 5). Both this and
            ``witnessed_at`` MUST be strictly before the adoption date.
        principal: Optional principal-chain id the witness binds (§4.3.1).
            Informational here; the monotonic-upgrade boundary is enforced by
            the record consumer, not this temporal gate.
    """

    witnessed_at: datetime
    chain_head_date: datetime
    principal: Optional[str] = None

    @staticmethod
    def _as_date(value: datetime) -> date:
        return value.date() if isinstance(value, datetime) else value

    def is_pre_adoption(self) -> bool:
        """True iff BOTH dates are strictly before :data:`ADOPTION_DATE`.

        Consumes :data:`ADOPTION_DATE_PARSED` (the E5/D2d temporal bound). A
        witness whose witnessed-date OR chain-head date falls on/after the
        adoption date does NOT license legacy acceptance.
        """

        return (
            self._as_date(self.witnessed_at) < ADOPTION_DATE_PARSED
            and self._as_date(self.chain_head_date) < ADOPTION_DATE_PARSED
        )


def assert_d2d_witness_pre_adoption(witness: Optional[D2dWitness]) -> None:
    """Enforce the D2d dated-and-witnessed gate (EATP-08 §4.5 / §4.3.2).

    Raises ``implicit-v1-witness-failure`` when the witness is missing, or
    when its witnessed/head date is not strictly before the pinned adoption
    date. Returns silently only when a witness is present AND pre-adoption, in
    which case the caller MAY accept the pre-registry explicit form as
    ``eatp-v1`` and MUST log the acceptance for migration tracking.

    Args:
        witness: The :class:`D2dWitness`, or ``None`` if the caller asserted
            no legacy acceptance.

    Raises:
        UnsupportedAlgorithmError: code ``implicit-v1-witness-failure`` when
            the witness is missing or dated on/after adoption.
    """

    if witness is None:
        raise UnsupportedAlgorithmError(
            "implicit-v1-witness-failure",
            "D2d legacy acceptance requires a dated, signed witness "
            "(EATP-08 §4.5 / §4.3): no witness was supplied, so the "
            "pre-registry explicit form MUST be rejected, not downgraded "
            f"to {ALGORITHM_DEFAULT!r}.",
        )
    if not witness.is_pre_adoption():
        raise UnsupportedAlgorithmError(
            "implicit-v1-witness-failure",
            "D2d legacy acceptance requires the witnessed chain-head date to "
            f"be strictly before the adoption date {ADOPTION_DATE!r} "
            "(EATP-08 §4.5 / §7.1); the supplied witness is dated on/after "
            "adoption, so the pre-registry explicit form MUST be rejected, "
            f"not downgraded to {ALGORITHM_DEFAULT!r}.",
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
      value of a signed ``alg_id`` field (the kailash-rs historical form); and
    - the algorithm carried only in **unsigned ``algorithm`` metadata** with no
      signed ``alg_id`` (the kailash-py historical form), which reaches this
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
        cls, data: Any, *, witness: Optional[D2dWitness] = None
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
                pre-registry record; its dates are enforced strictly-before
                adoption here. ``None`` (default) means strict, no legacy
                acceptance.

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
        # behave identically for a conformant record.
        if isinstance(data, dict) and "alg_id" in data and "algorithm" not in data:
            value: Any = data["alg_id"]
        else:
            value = data

        if witness is not None and is_pre_registry_form(value):
            # D2d: a pre-registry explicit form is acceptable ONLY when the
            # dated, signed witness places the chain head strictly before the
            # adoption date. A witness dated on/after adoption raises
            # implicit-v1-witness-failure; we never downgrade unconditionally.
            # (When no witness is supplied at all, a pre-registry form falls
            # through to the strict rejection below — shape-mismatch — exactly
            # as the post-adoption default requires.)
            assert_d2d_witness_pre_adoption(witness)
            logger.info(
                "EATP-08 D2d: accepting pre-registry explicit form %r as "
                "%r under the bounded/witnessed legacy path "
                "(witnessed_at=%s, chain_head_date=%s, both < %s); "
                "re-emitting as the eatp-v1 top-level token.",
                value,
                ALGORITHM_DEFAULT,
                witness.witnessed_at if witness else None,
                witness.chain_head_date if witness else None,
                ADOPTION_DATE,
            )
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

    Returns:
        A registry token string (the legacy forms resolve to ``eatp-v1``).

    Raises:
        UnsupportedAlgorithmError: ``missing-alg-id-post-adoption``,
            ``alg-id-shape-mismatch``, ``unsupported-algorithm``, or
            ``implicit-v1-witness-failure`` per EATP-08 §5.3.
    """

    if "alg_id" in data:
        return AlgorithmIdentifier.from_dict(data["alg_id"], witness=witness).algorithm

    # No top-level `alg_id` member. A record carrying the algorithm only under
    # an unsigned top-level `algorithm` key is a D2d pre-registry form
    # (kailash-py's historical metadata-only shape). It is accepted ONLY when a
    # dated, signed witness places the chain head strictly before adoption;
    # otherwise it is a post-adoption record missing its alg_id (D2b).
    if "algorithm" in data:
        legacy_value = data["algorithm"]
        if witness is not None and (
            legacy_value == DEPRECATED_PRE_REGISTRY_LITERAL
            or legacy_value in ("", None)
        ):
            # Enforce ADOPTION_DATE: missing/post-adoption witness rejects.
            assert_d2d_witness_pre_adoption(witness)
            logger.info(
                "EATP-08 D2d: accepting unsigned `algorithm`=%r metadata as "
                "%r under the bounded/witnessed legacy path "
                "(witnessed_at=%s, chain_head_date=%s, both < %s).",
                legacy_value,
                ALGORITHM_DEFAULT,
                witness.witnessed_at,
                witness.chain_head_date,
                ADOPTION_DATE,
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
    "D2dWitness",
    "DEPRECATED_PRE_REGISTRY_LITERAL",
    "RegistryEntry",
    "UnsupportedAlgorithmError",
    "assert_d2d_witness_pre_adoption",
    "coerce_algorithm_id",
    "decode_wire_alg_id",
    "is_active",
    "is_pre_registry_form",
    "is_registered",
    "resolve_dispatch",
]
