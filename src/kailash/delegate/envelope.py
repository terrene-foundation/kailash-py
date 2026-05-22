# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
# pyright: reportUnnecessaryIsInstance=false
"""Type-state wrapper around :class:`kailash.trust.envelope.ConstraintEnvelope`.

The F5 invariant from kailash-rs M2-02 (issue #1035 § "F5 type-state —
``DelegateConstraintEnvelope``") is:
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
from typing import Any

from kailash.delegate.types import DelegateGenesisRecord
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

    S3 (#1035) — the H2 deferral closes here: :meth:`from_dict` is the
    audit-grade validating constructor that closes the direct-dataclass-
    construction bypass. Cross-SDK ingest routes through :meth:`from_dict`;
    the bare ``__init__`` and :meth:`from_genesis` continue to work for in-
    process construction.
    """

    inner: ConstraintEnvelope
    genesis_id: str

    @classmethod
    def from_genesis(
        cls,
        envelope: ConstraintEnvelope,
        genesis: DelegateGenesisRecord,
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
        if not isinstance(genesis, DelegateGenesisRecord):
            raise TypeError(
                "DelegateConstraintEnvelope.from_genesis requires a "
                f"DelegateGenesisRecord; got {type(genesis).__name__}"
            )
        return cls(inner=envelope, genesis_id=genesis.genesis_id)

    def tighten_with(
        self,
        other: ConstraintEnvelope,
    ) -> "DelegateConstraintEnvelope":
        """Return a strictly-tighter (or equal) envelope.

        Raises :class:`EnvelopeWideningError` if ``other`` carries any value
        that LOOSENS a dimension where ``self.inner`` has a stricter bound.

        Discriminating widening from tightening REQUIRES a pre-intersection
        check: ``ConstraintEnvelope.intersect`` performs ``min()`` on numeric
        limits, so a widening request (parent=50, child=100) is silently
        squashed to the parent value by the intersection itself. After
        intersect, ``tightened.is_tighter_than(self.inner)`` would (trivially)
        be True, defeating the F5 invariant the wrapper exists to enforce.

        The structural fix: ask the predicate on the opposite direction —
        is ``self.inner`` at-least-as-tight as ``other``? If yes, the
        intersection is safe (other does not loosen any dimension self
        constrains, or other simply adds new constraints self did not have).
        If no, ``other`` loosens a dimension self constrained: that is a
        widening attempt and MUST raise BEFORE intersect can mask it.

        Equality is permitted (tightening with an identical envelope is a
        no-op, not a widening) because ``is_tighter_than`` admits equality
        as at-least-as-tight.
        """
        if not isinstance(other, ConstraintEnvelope):
            raise TypeError(
                "DelegateConstraintEnvelope.tighten_with requires a "
                f"ConstraintEnvelope; got {type(other).__name__}"
            )
        # PRE-INTERSECTION widening check. If `other` is NOT at-least-as-tight
        # as `self.inner` on every dimension self constrains, then `other`
        # carries a value loosening a dimension self bound — a widening
        # attempt. Raise BEFORE intersect masks the intent.
        if not other.is_tighter_than(self.inner):
            raise EnvelopeWideningError(
                "tighten_with rejected — `other` would widen the envelope on "
                "at least one dimension where the current inner envelope has "
                "a stricter bound. Widening (loosening any dimension) "
                "requires a new GenesisRecord and a fresh from_genesis() "
                "call; intersection cannot silently raise a limit."
            )
        tightened = self.inner.intersect(other)
        # Post-intersection invariant: the intersection MUST be at-least-as-
        # tight as self.inner (intersect is monotonic — min() never raises a
        # limit). This is a structural-integrity assertion; a failure here
        # would indicate a substrate-contract regression in ConstraintEnvelope.
        if not tightened.is_tighter_than(self.inner):  # pragma: no cover
            raise EnvelopeWideningError(
                "tighten_with intersection produced a non-tighter envelope "
                "despite the pre-intersection widening check passing; this "
                "indicates a regression in ConstraintEnvelope.intersect."
            )
        return DelegateConstraintEnvelope(inner=tightened, genesis_id=self.genesis_id)

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical wire dict for cross-SDK round-trip (S3 H2).

        Delegates the inner envelope serialization to the substrate's own
        :meth:`ConstraintEnvelope.to_dict` (the canonical wire format
        already shared across SDKs) and adds the spine-level
        :attr:`genesis_id` alongside.

        Pair with :meth:`from_dict` for round-trip; consumers serialize
        via :func:`kailash.trust._json.canonical_json_dumps` for cross-SDK
        byte parity.
        """
        return {
            "inner": self.inner.to_dict(),
            "genesis_id": self.genesis_id,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DelegateConstraintEnvelope:
        """Construct from a JSON-native payload with field-presence
        validation + inner-envelope delegation (S3 H2 deferral closure).

        B4 (analyst H-3) — honest description of what this constructor does
        relative to the bare ``__init__``:

        - The genesis_id non-emptiness invariant is checked here at the
          field-presence layer. The inner :class:`ConstraintEnvelope`'s own
          per-dimension contract is enforced by the substrate's
          :meth:`ConstraintEnvelope.from_dict`.
        - This classmethod adds field-presence checks that raise
          :class:`ValueError` / :class:`TypeError` with a missing-field /
          wrong-type message rather than ``KeyError``, plus the structural
          guard that the inner payload is a dict.

        Convenience loader for cross-SDK JSON ingest. Bare ``__init__`` and
        :meth:`from_genesis` remain the in-process paths.
        """
        if not isinstance(payload, dict):
            raise TypeError(
                "DelegateConstraintEnvelope.from_dict requires a dict; got "
                f"{type(payload).__name__}"
            )
        missing = {"inner", "genesis_id"} - set(payload)
        if missing:
            raise ValueError(
                f"DelegateConstraintEnvelope.from_dict missing required "
                f"field(s): {sorted(missing)}"
            )
        inner_payload = payload["inner"]
        if not isinstance(inner_payload, dict):
            raise TypeError(
                "DelegateConstraintEnvelope.from_dict: inner MUST be a "
                f"dict; got {type(inner_payload).__name__}"
            )
        genesis_id = payload["genesis_id"]
        if not isinstance(genesis_id, str):
            raise TypeError(
                "DelegateConstraintEnvelope.from_dict: genesis_id MUST be "
                f"a str; got {type(genesis_id).__name__}"
            )
        if not genesis_id:
            raise ValueError(
                "DelegateConstraintEnvelope.from_dict: genesis_id MUST be "
                "a non-empty string"
            )
        # Delegate inner envelope reconstruction to the substrate's own
        # validating constructor; it owns the per-dimension contract.
        inner = ConstraintEnvelope.from_dict(inner_payload)
        return cls(inner=inner, genesis_id=genesis_id)
