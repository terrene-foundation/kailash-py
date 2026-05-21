# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
# pyright: reportUnnecessaryIsInstance=false
"""Type-state wrapper around :class:`kailash.trust.envelope.ConstraintEnvelope`.

The F5 invariant from kailash-rs M2-02 (see
``workspaces/issue-1035-delegate-py/01-analysis/02-kailash-rs-reference-
extraction.md`` § "F5 type-state — ``DelegateConstraintEnvelope``") is:
runtime composition is **TIGHTENING-ONLY**. A child envelope may only be
strictly-tighter (or equal) than its parent; widening requires a new
:class:`~kailash.delegate.types.GenesisRecord`.

The rs side closes four widening hatches via a private inner field plus a
consuming ``tighten(self) -> Self``. Python cannot truly consume self on a
frozen dataclass, but the **frozen + slots + only-classmethod-constructor +
typed-raise-on-widen** combination closes the same hatches in practice:

- No ``Clone`` analog: ``frozen=True, slots=True`` blocks attribute mutation
  and accidental field reconstruction at the call site.
- No widening ``__init__`` path: the public API exposes only
  :meth:`DelegateConstraintEnvelope.from_genesis` (gated on a
  ``GenesisRecord``) as the widening constructor; :meth:`tighten_with`
  composes an existing envelope and validates the result.
- :class:`EnvelopeWideningError` is raised the moment the tightening predicate
  (``inner.is_tighter_than(self.inner)``) returns False.

The canonical ``ConstraintEnvelope`` reused here is the SPEC-07 type at
:mod:`kailash.trust.envelope`:

- ``ConstraintEnvelope.intersect(other)`` (``envelope.py:838``) — per-dim
  monotonic intersection.
- ``ConstraintEnvelope.is_tighter_than(other)`` (``envelope.py:867``) —
  predicate the wrapper uses to guarantee monotonic tightening.

HMAC sign/verify primitives live at ``envelope.py:1380, 1428`` for shards
beyond S2 that need them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from kailash.delegate.types import GenesisRecord
from kailash.trust.envelope import ConstraintEnvelope

logger = logging.getLogger(__name__)

__all__ = [
    "EnvelopeWideningError",
    "DelegateConstraintEnvelope",
]


class EnvelopeWideningError(ValueError):
    """Raised when :meth:`DelegateConstraintEnvelope.tighten_with` would widen.

    Mirrors the rs ``MonotonicTighteningError`` raised by
    ``DelegateConstraintEnvelope::tighten`` (rs ``envelope.rs:109-112``). The
    error class is ``ValueError``-derived because the widening attempt is a
    contract violation by the caller, not a system fault.
    """


@dataclass(frozen=True, slots=True)
class DelegateConstraintEnvelope:
    """Type-state wrapper around :class:`ConstraintEnvelope`.

    Per #1035 invariant: at runtime, composition is TIGHTENING-ONLY (the
    monotonic-tightening invariant from rs M2-02 F5). The only constructor
    that may set a fresh envelope is :meth:`from_genesis` (gated on a
    :class:`GenesisRecord`). Subsequent :meth:`tighten_with` operations
    return a new envelope guaranteed to be at-least-as-tight via the
    existing ``ConstraintEnvelope.intersect`` + ``is_tighter_than`` contract.

    The ``genesis_id`` is preserved across every tighten so audit records
    on the resulting envelope chain back to the originating GenesisRecord
    without re-rooting.
    """

    inner: ConstraintEnvelope
    genesis_id: str

    @classmethod
    def from_genesis(
        cls,
        envelope: ConstraintEnvelope,
        genesis: GenesisRecord,
    ) -> "DelegateConstraintEnvelope":
        """Construct from a genesis-seeded envelope (the only widening path).

        This is the SOLE constructor that may set a fresh underlying
        ``ConstraintEnvelope``. Once constructed, the envelope can only be
        further tightened via :meth:`tighten_with`.
        """
        if not isinstance(envelope, ConstraintEnvelope):
            raise TypeError(
                "DelegateConstraintEnvelope.from_genesis requires a "
                "ConstraintEnvelope; got "
                f"{type(envelope).__name__}"
            )
        if not isinstance(genesis, GenesisRecord):
            raise TypeError(
                "DelegateConstraintEnvelope.from_genesis requires a "
                f"GenesisRecord; got {type(genesis).__name__}"
            )
        return cls(inner=envelope, genesis_id=genesis.genesis_id)

    def tighten_with(
        self,
        other: ConstraintEnvelope,
    ) -> "DelegateConstraintEnvelope":
        """Return a strictly-tighter (or equal) envelope.

        Raises :class:`EnvelopeWideningError` if the intersection with
        ``other`` would NOT be at-least-as-tight as the current inner
        envelope on every dimension. The check is the
        ``ConstraintEnvelope.is_tighter_than`` predicate from SPEC-07.

        Equality is permitted (tightening with an identical envelope is a
        no-op, not a widening).
        """
        if not isinstance(other, ConstraintEnvelope):
            raise TypeError(
                "DelegateConstraintEnvelope.tighten_with requires a "
                f"ConstraintEnvelope; got {type(other).__name__}"
            )
        tightened = self.inner.intersect(other)
        if not tightened.is_tighter_than(self.inner):
            raise EnvelopeWideningError(
                "tighten_with would widen the envelope on at least one "
                "dimension; the intersection is not at-least-as-tight as "
                "the current inner envelope. Widening requires a new "
                "GenesisRecord and a fresh from_genesis() call."
            )
        return DelegateConstraintEnvelope(inner=tightened, genesis_id=self.genesis_id)
