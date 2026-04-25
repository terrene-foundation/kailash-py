# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Algorithm Identifier for Signed Records (Issue #604 Scaffold).

This module provides the ``AlgorithmIdentifier`` dataclass used to thread
algorithm-agility metadata through every signed-record API surface in the
trust plane. The wire format and value space are deliberately constrained
to a single value (``"ed25519+sha256"``) until mint ISS-31 stabilises the
canonical algorithm-identifier serialisation contract.

Forward path (mint ISS-31): only ``__post_init__`` validation and
``serialize_for_wire`` change. The threading through producers, verifiers,
and signed-record dataclasses is already in place and does not need to be
re-touched.

Cross-SDK sibling: esperie/kailash-rs#33.

References:

- Issue: terrene-foundation/kailash-py#604
- Cross-SDK sibling: esperie/kailash-rs#33
- Spec: ``specs/trust-crypto.md`` § "Algorithm Agility (Scaffold #604,
  awaiting mint ISS-31)".
- Rule: ``rules/zero-tolerance.md`` Rule 2 § "Iterative TODOs Permitted".
  The ``NotImplementedError`` raised on non-default algorithms below is
  the *single* permitted scaffold-era stub: it is issue-linked, has a
  documented gate (mint ISS-31), and exists exactly to flag drift.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict

logger = logging.getLogger(__name__)


# The only algorithm value supported until mint ISS-31 stabilises the
# canonical wire format. Producers SHOULD always pass an
# ``AlgorithmIdentifier()`` (i.e. the default) and verifiers SHOULD treat
# missing or empty algorithm fields as this constant.
ALGORITHM_DEFAULT: str = "ed25519+sha256"


@dataclass(frozen=True)
class AlgorithmIdentifier:
    """Versioned algorithm identifier for signed records (Issue #604 scaffold).

    Threaded through every signed-record producer/verifier so that when mint
    ISS-31 stabilises and the canonical wire format lands, only
    ``__post_init__`` validation and the canonical serialiser need to
    change. Today, only ``ed25519+sha256`` is permitted; non-default values
    raise ``NotImplementedError`` to flag drift before the spec gate
    closes.

    Attributes:
        algorithm: The algorithm identifier string. Constrained to
            :data:`ALGORITHM_DEFAULT` until mint ISS-31 lands.

    Raises:
        NotImplementedError: If a non-default algorithm is passed. This is
            the only ``NotImplementedError`` permitted under
            ``rules/zero-tolerance.md`` Rule 2 — issue-linked, gate
            documented (mint ISS-31), and the scaffold's purpose is
            exactly to fail loudly when drift is attempted.

    Examples:
        >>> alg = AlgorithmIdentifier()
        >>> alg.algorithm
        'ed25519+sha256'
        >>> AlgorithmIdentifier(algorithm="ed25519+sha512")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        NotImplementedError: Algorithm 'ed25519+sha512' awaits mint ISS-31 spec.
    """

    algorithm: str = ALGORITHM_DEFAULT

    def __post_init__(self) -> None:
        # Defensive: until mint ISS-31 lands, only the default is supported.
        # See module docstring + rules/zero-tolerance.md Rule 2 for why this
        # NotImplementedError is the single permitted scaffold-era stub.
        if self.algorithm != ALGORITHM_DEFAULT:
            raise NotImplementedError(
                f"Algorithm {self.algorithm!r} awaits mint ISS-31 spec. "
                f"Only {ALGORITHM_DEFAULT!r} is supported in this scaffold "
                f"(issue #604, cross-SDK kailash-rs#33)."
            )

    # --- Serialisation contract (stable) -----------------------------------
    #
    # The serialise/deserialise contract is the dual half of the threading
    # surface; mint ISS-31 will adjust the *value space* but the dict shape
    # ``{"algorithm": "<id>"}`` stays so that downstream consumers do not
    # need to re-thread. Storage shapes embed this dict (or just the
    # ``algorithm`` string field) per ``specs/trust-crypto.md`` §
    # "Algorithm Agility".

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-safe dict.

        Returns the canonical scaffold form ``{"algorithm": "<id>"}``.
        """

        return {"algorithm": self.algorithm}

    @classmethod
    def from_dict(cls, data: Any) -> "AlgorithmIdentifier":
        """Reconstruct from a dict.

        Missing or empty ``algorithm`` keys default to
        :data:`ALGORITHM_DEFAULT` (legacy / pre-#604 records).

        ``data`` is typed ``Any`` because this is a deserialisation
        boundary — callers may pass arbitrary JSON values; the runtime
        ``isinstance`` check below is the only structural defence.
        """

        if not isinstance(data, dict):
            raise TypeError(
                f"AlgorithmIdentifier.from_dict expected dict, got "
                f"{type(data).__name__}"
            )
        algorithm = data.get("algorithm") or ALGORITHM_DEFAULT
        if not isinstance(algorithm, str):
            raise TypeError(
                f"AlgorithmIdentifier.algorithm must be str, got "
                f"{type(algorithm).__name__}"
            )
        return cls(algorithm=algorithm)


def coerce_algorithm_id(
    alg_id: "AlgorithmIdentifier | None",
) -> AlgorithmIdentifier:
    """Default-fill an optional :class:`AlgorithmIdentifier`.

    This is the canonical helper every producer/verifier site uses so that
    threading ``Optional[AlgorithmIdentifier]`` does not require each call
    site to re-implement the ``alg_id or AlgorithmIdentifier()`` defaulting
    pattern.

    Args:
        alg_id: An :class:`AlgorithmIdentifier` instance, or ``None``.

    Returns:
        The given ``alg_id`` if not ``None``, else a default
        :class:`AlgorithmIdentifier`.
    """

    return alg_id if alg_id is not None else AlgorithmIdentifier()


__all__ = [
    "ALGORITHM_DEFAULT",
    "AlgorithmIdentifier",
    "coerce_algorithm_id",
]
