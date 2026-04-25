# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
SLIP-0039 Shamir secret-sharing wrapper for Trust Vault backup.

This module wraps the audited reference implementation `shamir-mnemonic`
(SLIP-0039 by SatoshiLabs) to expose an ergonomic ``ShamirRitual`` surface
for splitting and reconstructing Trust Vault key material.

Spec gate
---------

The Trust Vault binding (issue #606, mint ISS-37) is NOT YET STABLE. This
module provides only the SLIP-0039 wrapper API and ritual scaffolding. The
mint-specific binding lives in :mod:`kailash.trust.vault.backup` as a
gate-documented stub awaiting ISS-37.

Optional dependency
-------------------

The audited reference library is shipped as an optional extra so the base
``pip install kailash`` does not pull in cryptographic mnemonic code that
most users do not need. Install via::

    pip install kailash[shamir]

The library is imported lazily inside each public function so module import
of ``kailash.trust.vault.shamir`` succeeds even without the extra; the call
fails loudly with an actionable :class:`RuntimeError` instructing the user
to install the extra. This is the "loud failure at call site" pattern from
``rules/dependencies.md`` -- the silent ``X = None`` fallback is BLOCKED.

Security caveat
---------------

The reference implementation is **not constant-time** and is documented by
its authors as suitable for correctness verification rather than handling
of high-value secrets in adversarial settings. Trust Vault deployments that
need side-channel resistance MUST evaluate hardened alternatives before
production use; the wrapper exists today to (1) freeze the SLIP-0039 API
surface so downstream callers can compile against it and (2) enable the
end-to-end ritual rehearsal.

Public surface
--------------

* :class:`ShamirRitual` -- frozen dataclass capturing ``(threshold, total)``
* :func:`generate` -- produces ``total`` shards from a secret
* :func:`reconstruct` -- recombines ``threshold`` shards into the secret
* :func:`serialize_shard` / :func:`deserialize_shard` -- paper-print form
* :func:`rotate_holders` -- recombine then re-shard with a new ritual

Memory hygiene
--------------

Per ``rules/trust-plane-security.md`` MUST NOT Rule 3, callers MUST ``del``
returned secret bytes immediately after use. The wrapper itself does not
log shard contents at any level (``rules/observability.md`` MUST Rule 4).

Cross-SDK
---------

A matching scaffold is expected on the kailash-rs side using a parallel
audited Rust SLIP-0039 implementation. The serialized paper-print form is
the interop surface across SDKs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List

logger = logging.getLogger(__name__)

__all__ = [
    "ShamirRitual",
    "EntropySource",
    "generate",
    "reconstruct",
    "serialize_shard",
    "deserialize_shard",
    "rotate_holders",
]


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

#: Caller-supplied entropy source for shard generation. Receives the number
#: of bytes requested and returns exactly that many. Defaults to
#: :func:`os.urandom` when unset.
EntropySource = Callable[[int], bytes]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: SLIP-0039 caps the number of shares per group at 16 (4-bit field).
_MAX_TOTAL_SHARDS: int = 16

#: Canonical paper-print delimiter. Single space matches the SLIP-0039
#: mnemonic format, where each shard is rendered as a space-separated
#: sequence of dictionary words.
_SHARD_DELIM: str = " "

#: Error message emitted when the optional ``shamir`` extra is absent.
_EXTRA_HINT: str = (
    "SLIP-0039 Shamir secret-sharing requires the 'shamir' optional extra. "
    "Install via: pip install kailash[shamir]"
)


# ---------------------------------------------------------------------------
# Lazy import helper
# ---------------------------------------------------------------------------


def _require_shamir_mnemonic():
    """Lazy-import the audited SLIP-0039 reference library.

    Returns the imported module on success. Raises :class:`RuntimeError`
    with an actionable install hint if the optional extra is absent.

    This is the "loud failure at call site" pattern from
    ``rules/dependencies.md`` -- absence is surfaced at the FIRST call,
    never silently as ``None``.
    """
    try:
        import shamir_mnemonic  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise RuntimeError(_EXTRA_HINT) from exc
    return shamir_mnemonic


# ---------------------------------------------------------------------------
# Ritual dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShamirRitual:
    """Parameters for an ``m``-of-``n`` Shamir ritual.

    Attributes
    ----------
    threshold:
        ``m`` -- the minimum number of shards required to reconstruct.
    total_shards:
        ``n`` -- the total number of shards generated.

    Validation
    ----------

    Enforced in ``__post_init__``:

    * ``1 <= threshold <= total_shards``
    * ``total_shards <= 16`` (SLIP-0039 4-bit member-index field)
    * ``threshold >= 2`` -- single-shard rituals provide no security beyond
      simple possession of the secret and are rejected by default. Callers
      that genuinely want the trivial ``1``-of-``n`` form (split-only, no
      threshold protection) MUST pass ``allow_trivial=True`` explicitly --
      not yet supported in this scaffold; opens later when mint ISS-37
      lands and the trade-off can be reviewed.

    The frozen dataclass form is mandated by
    ``rules/trust-plane-security.md`` MUST Rule 4: ritual parameters
    captured at governance approval time MUST NOT be mutable thereafter.
    """

    threshold: int
    total_shards: int

    def __post_init__(self) -> None:
        if not isinstance(self.threshold, int) or not isinstance(
            self.total_shards, int
        ):
            raise TypeError(
                "ShamirRitual.threshold and total_shards MUST be int; "
                f"got threshold={type(self.threshold).__name__} "
                f"total_shards={type(self.total_shards).__name__}"
            )
        if self.threshold < 1:
            raise ValueError(
                f"ShamirRitual.threshold must be >= 1 (got {self.threshold})"
            )
        if self.total_shards < 1:
            raise ValueError(
                f"ShamirRitual.total_shards must be >= 1 " f"(got {self.total_shards})"
            )
        if self.threshold > self.total_shards:
            raise ValueError(
                f"ShamirRitual.threshold ({self.threshold}) must be "
                f"<= total_shards ({self.total_shards})"
            )
        if self.total_shards > _MAX_TOTAL_SHARDS:
            raise ValueError(
                f"ShamirRitual.total_shards ({self.total_shards}) exceeds "
                f"SLIP-0039 limit of {_MAX_TOTAL_SHARDS}"
            )
        if self.threshold == 1 and self.total_shards > 1:
            # 1-of-n means any single shard reconstructs the secret -- the
            # ritual provides distribution but zero threshold protection.
            # We reject by default; the gate to relax this opens with mint
            # ISS-37 when the trade-off can be governance-reviewed.
            raise ValueError(
                "ShamirRitual rejects threshold=1 with total_shards>1 "
                "(trivial split: any holder can recover unilaterally). "
                "Use threshold>=2 or wait for mint ISS-37 governance "
                "review if a trivial split is genuinely required."
            )


# ---------------------------------------------------------------------------
# Generate / reconstruct
# ---------------------------------------------------------------------------


def generate(
    secret: bytes,
    ritual: ShamirRitual,
    *,
    passphrase: bytes = b"",
) -> List[List[str]]:
    """Split ``secret`` into ``ritual.total_shards`` shards.

    Parameters
    ----------
    secret:
        The master secret to split. Per SLIP-0039 the secret length MUST
        be 16, 32, or another multiple of 2 bytes that the underlying
        library accepts; passing an invalid length surfaces as a
        :class:`ValueError` from the library, propagated unchanged.
    ritual:
        The ``m``-of-``n`` parameters captured by :class:`ShamirRitual`.
    passphrase:
        Optional passphrase per SLIP-0039 spec. Empty by default.
        Per ``rules/observability.md`` MUST Rule 4 the passphrase is
        NEVER logged.

    Returns
    -------
    list[list[str]]
        A list of exactly ``ritual.total_shards`` shards. Each shard is
        a list of SLIP-0039 dictionary words (the mnemonic).

    Raises
    ------
    RuntimeError
        If the ``shamir`` optional extra is not installed.
    TypeError
        If ``secret`` is not :class:`bytes`.
    ValueError
        If the SLIP-0039 library rejects the secret length or other
        constraint (propagated from the underlying ``MnemonicError``).

    Notes
    -----

    The wrapper uses a single-group ``m``-of-``n`` configuration
    (``group_threshold=1``, ``groups=[(m, n)]``). Multi-group rituals
    are an extension point reserved for the mint ISS-37 binding.

    The function deliberately does NOT log the secret, the passphrase,
    or any returned shard. Callers MUST ``del`` the returned list once
    distribution is complete.
    """
    if not isinstance(secret, (bytes, bytearray)):
        raise TypeError(
            f"generate(secret=...) requires bytes; got {type(secret).__name__}"
        )
    if not isinstance(passphrase, (bytes, bytearray)):
        raise TypeError(
            f"generate(passphrase=...) requires bytes; got "
            f"{type(passphrase).__name__}"
        )

    sm = _require_shamir_mnemonic()

    # Single-group m-of-n: group_threshold=1, one group with (threshold, total).
    groups = [(ritual.threshold, ritual.total_shards)]
    mnemonics = sm.generate_mnemonics(
        group_threshold=1,
        groups=groups,
        master_secret=bytes(secret),
        passphrase=bytes(passphrase),
    )

    # The library returns List[List[str]] where the outer list is groups
    # (length 1 for our single-group ritual) and the inner list is the
    # mnemonics (one per shard, each as a single space-joined string).
    # We split each mnemonic into its constituent words so callers can
    # treat shards as word-lists per the wrapper contract.
    if len(mnemonics) != 1:
        raise RuntimeError(
            "shamir_mnemonic.generate_mnemonics returned unexpected group "
            f"count {len(mnemonics)} for single-group ritual"
        )
    group = mnemonics[0]
    if len(group) != ritual.total_shards:
        raise RuntimeError(
            f"shamir_mnemonic.generate_mnemonics returned {len(group)} "
            f"shards; ritual requested {ritual.total_shards}"
        )
    shards: List[List[str]] = [_words(m) for m in group]
    logger.debug(
        "shamir.generate: produced %d shards (threshold=%d)",
        ritual.total_shards,
        ritual.threshold,
    )
    return shards


def reconstruct(
    shards: List[List[str]],
    *,
    passphrase: bytes = b"",
) -> bytes:
    """Recombine threshold-many ``shards`` into the original secret.

    Parameters
    ----------
    shards:
        A list of at least ``ritual.threshold`` shards previously produced
        by :func:`generate`. Each shard is a list of dictionary words.
    passphrase:
        The passphrase used at :func:`generate` time. MUST match exactly.

    Returns
    -------
    bytes
        The original master secret.

    Raises
    ------
    RuntimeError
        If the ``shamir`` optional extra is not installed.
    TypeError
        If ``shards`` is not a list of lists of strings.
    ValueError
        If the SLIP-0039 library rejects the shard set (insufficient
        threshold, mixed identifiers, checksum failures, etc.).
        Propagated from the underlying ``MnemonicError``.

    Memory hygiene
    --------------

    Per ``rules/trust-plane-security.md`` MUST NOT Rule 3, callers MUST
    ``del`` the returned bytes immediately after use::

        secret = reconstruct(shards)
        try:
            use_secret(secret)
        finally:
            del secret  # remove reference; GC collects backing buffer

    The wrapper deliberately does NOT zeroize the bytes object (Python's
    ``bytes`` is immutable; in-place clearing is not portable). Use a
    hardened secret-handling library if zeroization is required.
    """
    if not isinstance(shards, list):
        raise TypeError(
            f"reconstruct(shards=...) requires list; got {type(shards).__name__}"
        )
    if not shards:
        raise ValueError("reconstruct(shards=...) requires at least one shard")
    for idx, shard in enumerate(shards):
        if not isinstance(shard, list):
            raise TypeError(
                f"reconstruct: shard[{idx}] must be list[str]; got "
                f"{type(shard).__name__}"
            )
        for widx, word in enumerate(shard):
            if not isinstance(word, str):
                raise TypeError(
                    f"reconstruct: shard[{idx}][{widx}] must be str; got "
                    f"{type(word).__name__}"
                )
    if not isinstance(passphrase, (bytes, bytearray)):
        raise TypeError(
            f"reconstruct(passphrase=...) requires bytes; got "
            f"{type(passphrase).__name__}"
        )

    sm = _require_shamir_mnemonic()

    # The library accepts mnemonics as space-joined strings.
    mnemonics = [_join(words) for words in shards]
    secret = sm.combine_mnemonics(mnemonics, passphrase=bytes(passphrase))
    logger.debug("shamir.reconstruct: combined %d shards", len(shards))
    return secret


# ---------------------------------------------------------------------------
# Serialization (paper-print form)
# ---------------------------------------------------------------------------


def serialize_shard(shard: List[str]) -> str:
    """Serialize a shard to its paper-print form.

    The paper-print form is the canonical SLIP-0039 mnemonic: dictionary
    words separated by single spaces. This is the interop surface across
    SDKs and the form holders write down on paper, engrave on metal, or
    print on cards.

    Raises
    ------
    TypeError
        If ``shard`` is not a list of strings.
    ValueError
        If ``shard`` is empty.
    """
    if not isinstance(shard, list):
        raise TypeError(
            f"serialize_shard requires list[str]; got {type(shard).__name__}"
        )
    if not shard:
        raise ValueError("serialize_shard: shard must be non-empty")
    for idx, word in enumerate(shard):
        if not isinstance(word, str):
            raise TypeError(
                f"serialize_shard: shard[{idx}] must be str; got "
                f"{type(word).__name__}"
            )
        if not word or _SHARD_DELIM in word:
            raise ValueError(
                f"serialize_shard: shard[{idx}] is empty or contains the "
                f"delimiter '{_SHARD_DELIM}'"
            )
    return _join(shard)


def deserialize_shard(shard: str) -> List[str]:
    """Reverse :func:`serialize_shard`.

    Whitespace tolerant on input: any run of ASCII whitespace is treated
    as a word separator, so shards copied from paper with extra spaces
    or line breaks survive the round-trip.

    Raises
    ------
    TypeError
        If ``shard`` is not :class:`str`.
    ValueError
        If ``shard`` is empty after stripping.
    """
    if not isinstance(shard, str):
        raise TypeError(f"deserialize_shard requires str; got {type(shard).__name__}")
    words = shard.split()
    if not words:
        raise ValueError("deserialize_shard: shard is empty")
    return words


# ---------------------------------------------------------------------------
# Holder rotation
# ---------------------------------------------------------------------------


def rotate_holders(
    old_shards: List[List[str]],
    new_ritual: ShamirRitual,
    *,
    passphrase: bytes = b"",
) -> List[List[str]]:
    """Recombine ``old_shards``, then re-shard under ``new_ritual``.

    Use this when the holder set changes -- a holder leaves, a new
    holder joins, or the ``(m, n)`` policy is updated. The reconstructed
    secret is held in memory for the duration of the re-shard call;
    callers SHOULD invoke this on an air-gapped or otherwise isolated
    host per Trust Vault operational guidance.

    Parameters
    ----------
    old_shards:
        At least ``old_ritual.threshold`` shards from the previous
        ritual. The old ritual itself is not required because SLIP-0039
        encodes thresholds in the mnemonics.
    new_ritual:
        The ``(m, n)`` configuration for the rotated holder set.
    passphrase:
        The passphrase used at :func:`generate` time for ``old_shards``.
        Re-emitted shards use the same passphrase by default. To rotate
        the passphrase, call :func:`reconstruct` and :func:`generate`
        explicitly.

    Returns
    -------
    list[list[str]]
        ``new_ritual.total_shards`` shards under the new ritual.

    Memory hygiene
    --------------

    The intermediate secret is ``del``-eted before the function returns.
    However, Python's garbage collector may retain the underlying buffer
    until the next collection cycle, and the SLIP-0039 reference
    implementation is not constant-time. Hardened deployments SHOULD
    perform rotation in a process that exits immediately afterward to
    minimize the residence window.
    """
    secret = reconstruct(old_shards, passphrase=passphrase)
    try:
        new_shards = generate(secret, new_ritual, passphrase=passphrase)
    finally:
        # Drop our reference. Python's GC collects the buffer on its own
        # schedule; this is best-effort residence-time minimization, NOT
        # cryptographic zeroization.
        del secret
    logger.debug(
        "shamir.rotate_holders: re-sharded under threshold=%d total=%d",
        new_ritual.threshold,
        new_ritual.total_shards,
    )
    return new_shards


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _words(mnemonic: str) -> List[str]:
    """Split a SLIP-0039 mnemonic into its constituent dictionary words."""
    return mnemonic.split()


def _join(words: List[str]) -> str:
    """Join words back into a SLIP-0039 mnemonic string."""
    return _SHARD_DELIM.join(words)
