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
from enum import Enum
from typing import Any, Dict

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
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {message}")


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

    EATP-08 §4.5 (D2d) recognises two pre-registry explicit forms that carry
    the deprecated literal ``ed25519+sha256``:

    - the bare deprecated literal string (kailash-py historically signed NO
      ``alg_id`` at all, carrying the algorithm in unsigned metadata; when a
      caller surfaces that metadata literal into the field, it lands here);
      and
    - the nested-object encoding ``{"algorithm": "ed25519+sha256"}`` that
      kailash-rs historically signed.

    Both map to ``eatp-v1`` under the bounded/witnessed legacy path. This
    function only RECOGNISES the shape; the dated/witnessed/sunset gating is
    the verifier's responsibility (§4.5).
    """

    if value == DEPRECATED_PRE_REGISTRY_LITERAL:
        return True
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
        cls, data: Any, *, legacy_path: bool = False
    ) -> "AlgorithmIdentifier":
        """Reconstruct from a wire value (EATP-08 §4.5 D2b / D2d).

        Two acceptance regimes, selected by ``legacy_path``:

        - **Post-adoption path (default, ``legacy_path=False``)**: the value
          MUST be a top-level registry-token string. A missing or empty
          value is NOT silently defaulted (this is the E6 defect the v1.1
          erratum closes — see §4.6): it raises with code
          ``missing-alg-id-post-adoption`` per D2b. A present-but-malformed
          value (object/array/number/null, or the deprecated literal) raises
          ``alg-id-shape-mismatch``; an unregistered token raises
          ``unsupported-algorithm``.

        - **Bounded legacy path (``legacy_path=True``)**: a caller that has
          already satisfied the D2d dated-and-witnessed gate (§4.5) passes
          ``legacy_path=True`` to accept a recognised pre-registry explicit
          form — the deprecated literal ``ed25519+sha256`` (bare or nested
          ``{"algorithm": "ed25519+sha256"}``) — mapping it to ``eatp-v1``
          and logging the acceptance for migration tracking. Going forward
          the record re-emits as the ``eatp-v1`` top-level token.

        Args:
            data: The wire value. On the post-adoption path this is the
                top-level ``alg_id`` value; on the legacy path it MAY be the
                pre-registry literal or nested form.
            legacy_path: True only when the caller has satisfied the D2d
                dated/witnessed gate and is rescuing a pre-registry record.

        Returns:
            An :class:`AlgorithmIdentifier`, always carrying a registry token
            (the legacy forms map to ``eatp-v1``).

        Raises:
            UnsupportedAlgorithmError: code ``missing-alg-id-post-adoption``,
                ``alg-id-shape-mismatch``, or ``unsupported-algorithm`` per
                the regime above.
        """

        # Some historical record shapes nested the token under a top-level
        # `{"alg_id": "<token>"}` member; accept that envelope transparently
        # so `from_dict(record_dict)` and `from_dict(record_dict["alg_id"])`
        # behave identically for a conformant record.
        if isinstance(data, dict) and "alg_id" in data and "algorithm" not in data:
            value: Any = data["alg_id"]
        else:
            value = data

        if legacy_path and is_pre_registry_form(value):
            logger.info(
                "EATP-08 D2d: accepting pre-registry explicit form %r as "
                "%r under the bounded/witnessed legacy path; re-emitting as "
                "the eatp-v1 top-level token.",
                value,
                ALGORITHM_DEFAULT,
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
                "through the D2d gate (legacy_path=True) after the "
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
            # The deprecated literal as a bare top-level string is NOT a
            # registry token. Off the legacy path it is a shape mismatch.
            raise UnsupportedAlgorithmError(
                "alg-id-shape-mismatch",
                f"alg_id {value!r} is the deprecated pre-registry literal; "
                f"it is accepted only on the D2d legacy path (§4.5), never "
                f"as a conformant post-adoption emission.",
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
    legacy_path: bool = False,
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
      ONLY when ``legacy_path=True`` (the caller has satisfied the D2d
      dated/witnessed gate), and both map to ``eatp-v1``.

    Args:
        data: The signed-record wire dict.
        legacy_path: True only after the D2d dated/witnessed gate is met.

    Returns:
        A registry token string (the legacy forms resolve to ``eatp-v1``).

    Raises:
        UnsupportedAlgorithmError: ``missing-alg-id-post-adoption``,
            ``alg-id-shape-mismatch``, or ``unsupported-algorithm`` per
            EATP-08 §5.3.
    """

    if "alg_id" in data:
        return AlgorithmIdentifier.from_dict(
            data["alg_id"], legacy_path=legacy_path
        ).algorithm

    # No top-level `alg_id` member. A record carrying the algorithm only under
    # an unsigned top-level `algorithm` key is a D2d pre-registry form
    # (kailash-py's historical metadata-only shape); accept it on the legacy
    # path, otherwise it is a post-adoption record missing its alg_id (D2b).
    if "algorithm" in data:
        legacy_value = data["algorithm"]
        if legacy_path and (
            legacy_value == DEPRECATED_PRE_REGISTRY_LITERAL
            or legacy_value in ("", None)
        ):
            logger.info(
                "EATP-08 D2d: accepting unsigned `algorithm`=%r metadata as "
                "%r under the bounded/witnessed legacy path.",
                legacy_value,
                ALGORITHM_DEFAULT,
            )
            return ALGORITHM_DEFAULT

    raise UnsupportedAlgorithmError(
        "missing-alg-id-post-adoption",
        "signed record carries no top-level `alg_id`; per EATP-08 §4.2 "
        "(D2b) a post-adoption record without alg_id MUST be rejected. "
        "A pre-registry legacy record must be routed through the D2d gate "
        "(legacy_path=True) after the dated/witnessed check.",
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
    "ALGORITHM_DEFAULT",
    "ALGORITHM_REGISTRY",
    "AlgorithmIdentifier",
    "AlgorithmStatus",
    "DEPRECATED_PRE_REGISTRY_LITERAL",
    "RegistryEntry",
    "UnsupportedAlgorithmError",
    "coerce_algorithm_id",
    "decode_wire_alg_id",
    "is_active",
    "is_pre_registry_form",
    "is_registered",
    "resolve_dispatch",
]
